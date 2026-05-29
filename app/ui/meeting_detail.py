import bisect
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter,
    QFrame, QFileDialog, QMessageBox, QInputDialog,
    QMenu, QAbstractItemView, QWidgetAction, QSlider,
)

from ..storage import db
from ..storage.models import Meeting, Segment
from ..llm import client as llm
from ..export.exporter import to_txt, to_pdf
from ..audio.player import MeetingPlayer


class SpeakerPanel(QWidget):
    speaker_renamed = Signal()

    def __init__(self, meeting_id: int, parent=None):
        super().__init__(parent)
        self._meeting_id = meeting_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        label = QLabel("Speakers")
        label.setStyleSheet("font-weight: bold; font-size: 13px;")
        header.addWidget(label)
        header.addStretch()
        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(24)
        add_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 0 8px; border-radius: 4px; "
            "background: #ede9fe; color: #4338ca; border: none; }"
            "QPushButton:hover { background: #ddd6fe; }"
        )
        add_btn.clicked.connect(self._add_speaker)
        header.addWidget(add_btn)
        layout.addLayout(header)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { border: 1px solid #e5e7eb; border-radius: 4px; font-size: 13px; }"
            "QListWidget::item { padding: 6px 8px; }"
            "QListWidget::item:selected { background: #ede9fe; color: black; }"
        )
        self._list.itemDoubleClicked.connect(self._rename_speaker)
        layout.addWidget(self._list)

        hint = QLabel("Double-click to rename  ·  Right-click segment to assign")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9ca3af; font-size: 10px;")
        layout.addWidget(hint)
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        for sp in db.get_speakers(self._meeting_id):
            item = QListWidgetItem(sp.display_name)
            item.setData(Qt.UserRole, sp.id)
            item.setData(Qt.UserRole + 1, sp.display_name)
            self._list.addItem(item)

    def _add_speaker(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Speaker", "Speaker name:")
        if ok and name.strip():
            db.create_manual_speaker(self._meeting_id, name.strip())
            self.refresh()
            self.speaker_renamed.emit()

    def _rename_speaker(self, item: QListWidgetItem) -> None:
        sp_id = item.data(Qt.UserRole)
        current = item.data(Qt.UserRole + 1)
        name, ok = QInputDialog.getText(self, "Rename Speaker", "New name:", text=current)
        if ok and name.strip():
            db.rename_speaker(sp_id, name.strip())
            self.refresh()
            self.speaker_renamed.emit()


class _LLMThread(QThread):
    token_received = Signal(str)
    finished_ok = Signal()
    error = Signal(str)

    def __init__(self, gen_func, parent=None):
        super().__init__(parent)
        self._gen_func = gen_func

    def run(self):
        try:
            for token in self._gen_func():
                self.token_received.emit(token)
            self.finished_ok.emit()
        except Exception as exc:
            self.error.emit(str(exc))


class MeetingDetailView(QWidget):
    def __init__(self, meeting_id: int, settings: dict, parent=None):
        super().__init__(parent)
        self._meeting_id = meeting_id
        self._settings = settings
        self._llm_thread: Optional[_LLMThread] = None
        self._segment_ids: list[int] = []
        # sorted list of start_sec values — index matches transcript list row
        self._seg_starts: list[float] = []
        self._seg_ends: list[float] = []
        self._auto_scrolling = False   # guard to avoid feedback loops
        self._slider_dragging = False
        self._player = MeetingPlayer(self)
        self._player.position_changed.connect(self._on_position)
        self._player.duration_changed.connect(self._on_duration)
        self._player.playback_state_changed.connect(self._on_state)
        self._build_ui()
        self.load()

    def update_settings(self, settings: dict) -> None:
        self._settings = settings

    def refresh(self) -> None:
        self.load()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Title row
        title_row = QHBoxLayout()
        self._title_label = QLabel("Meeting")
        self._title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        title_row.addWidget(self._title_label)
        title_row.addStretch()
        self._export_btn = QPushButton("Export ▾")
        self._export_btn.clicked.connect(self._show_export_menu)
        title_row.addWidget(self._export_btn)
        layout.addLayout(title_row)

        self._date_label = QLabel()
        self._date_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self._date_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #e5e7eb;")
        layout.addWidget(sep)

        # AI buttons
        ai_row = QHBoxLayout()
        self._summary_btn = QPushButton("✦ Generate Summary")
        self._summary_btn.setStyleSheet(
            "QPushButton { background: #4338ca; color: white; border-radius: 6px; "
            "padding: 6px 14px; font-size: 13px; }"
            "QPushButton:hover { background: #3730a3; }"
            "QPushButton:disabled { background: #e5e7eb; color: #9ca3af; }"
        )
        self._summary_btn.clicked.connect(self._gen_summary)
        self._actions_btn = QPushButton("✦ Extract Action Items")
        self._actions_btn.setStyleSheet(self._summary_btn.styleSheet())
        self._actions_btn.clicked.connect(self._gen_actions)
        ai_row.addWidget(self._summary_btn)
        ai_row.addWidget(self._actions_btn)
        ai_row.addStretch()
        layout.addLayout(ai_row)

        # ── Playback bar ──────────────────────────────────────────────────────
        self._playback_bar = QWidget()
        self._playback_bar.setStyleSheet(
            "background: #f3f4f6; border-radius: 10px; padding: 0px;"
        )
        pb_layout = QHBoxLayout(self._playback_bar)
        pb_layout.setContentsMargins(12, 8, 12, 8)
        pb_layout.setSpacing(10)

        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.setStyleSheet(
            "QPushButton { background: #4338ca; color: white; border-radius: 18px; "
            "font-size: 14px; border: none; }"
            "QPushButton:hover { background: #3730a3; }"
        )
        self._play_btn.clicked.connect(self._player.toggle)
        pb_layout.addWidget(self._play_btn)

        self._pos_label = QLabel("0:00")
        self._pos_label.setStyleSheet("font-size: 12px; color: #6b7280; font-family: monospace; min-width: 36px;")
        pb_layout.addWidget(self._pos_label)

        self._seek_slider = QSlider(Qt.Horizontal)
        self._seek_slider.setRange(0, 0)
        self._seek_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #d1d5db; border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #4338ca; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px; border-radius: 7px; "
            "background: #4338ca; margin: -5px 0; }"
        )
        self._seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self._seek_slider.sliderReleased.connect(self._on_slider_released)
        pb_layout.addWidget(self._seek_slider, stretch=1)

        self._dur_label = QLabel("0:00")
        self._dur_label.setStyleSheet("font-size: 12px; color: #6b7280; font-family: monospace; min-width: 36px;")
        pb_layout.addWidget(self._dur_label)

        self._playback_bar.setVisible(False)
        layout.addWidget(self._playback_bar)

        # ── Main splitter ─────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        t_label = QLabel("Transcript")
        t_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #6b7280;")
        left_layout.addWidget(t_label)

        self._transcript_list = QListWidget()
        self._transcript_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._transcript_list.setStyleSheet(
            "QListWidget { border: 1px solid #e5e7eb; border-radius: 6px; "
            "background: #f9fafb; font-size: 13px; }"
            "QListWidget::item { padding: 6px 10px; border-bottom: 1px solid #f3f4f6; }"
            "QListWidget::item:selected { background: #ede9fe; color: black; }"
        )
        self._transcript_list.setWordWrap(True)
        self._transcript_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._transcript_list.customContextMenuRequested.connect(self._segment_context_menu)
        self._transcript_list.itemClicked.connect(self._on_segment_clicked)
        left_layout.addWidget(self._transcript_list)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._speaker_panel = SpeakerPanel(self._meeting_id)
        self._speaker_panel.speaker_renamed.connect(self.load)
        right_layout.addWidget(self._speaker_panel)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #e5e7eb;")
        right_layout.addWidget(sep2)

        sum_label = QLabel("Summary")
        sum_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #6b7280;")
        right_layout.addWidget(sum_label)
        self._summary_edit = QTextEdit()
        self._summary_edit.setPlaceholderText("Click 'Generate Summary' to create one…")
        self._summary_edit.setStyleSheet(
            "border: 1px solid #e5e7eb; border-radius: 6px; background: #f9fafb; "
            "padding: 8px; font-size: 12px;"
        )
        right_layout.addWidget(self._summary_edit)

        act_label = QLabel("Action Items")
        act_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #6b7280;")
        right_layout.addWidget(act_label)
        self._actions_edit = QTextEdit()
        self._actions_edit.setPlaceholderText("Click 'Extract Action Items' to create one…")
        self._actions_edit.setStyleSheet(
            "border: 1px solid #e5e7eb; border-radius: 6px; background: #f9fafb; "
            "padding: 8px; font-size: 12px;"
        )
        right_layout.addWidget(self._actions_edit)

        splitter.addWidget(right)
        splitter.setSizes([620, 280])
        layout.addWidget(splitter, stretch=1)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(self._status_label)

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self) -> None:
        meeting = db.get_meeting(self._meeting_id)
        if not meeting:
            return
        self._title_label.setText(meeting.title)
        self._date_label.setText(meeting.started_at.strftime("%B %d, %Y  %H:%M"))

        # Rebuild transcript list and segment time index
        self._transcript_list.clear()
        self._segment_ids.clear()
        self._seg_starts.clear()
        self._seg_ends.clear()

        for seg in meeting.segments:
            speaker = seg.speaker_display or "Unknown"
            ts = _fmt_sec(seg.start_sec)
            item = QListWidgetItem(f"[{ts}]  {speaker}: {seg.text}")
            item.setData(Qt.UserRole, seg.id)
            item.setData(Qt.UserRole + 2, seg.start_sec)  # for click-to-seek
            if seg.speaker_display:
                item.setForeground(Qt.black)
            else:
                item.setForeground(Qt.gray)
            self._transcript_list.addItem(item)
            self._segment_ids.append(seg.id)
            self._seg_starts.append(seg.start_sec)
            self._seg_ends.append(seg.end_sec)

        self._speaker_panel.refresh()

        if meeting.summary:
            self._summary_edit.setPlainText(meeting.summary)
        if meeting.action_items:
            self._actions_edit.setPlainText(meeting.action_items)

        # Show/hide playback bar
        audio_ok = bool(meeting.audio_path and Path(meeting.audio_path).exists())
        self._playback_bar.setVisible(audio_ok)
        if audio_ok:
            self._player.stop()
            self._player.load(meeting.audio_path)

        # Ollama check
        ollama_url = self._settings.get("ollama_url", llm.DEFAULT_URL)
        if not llm.is_ollama_available(ollama_url):
            self._status_label.setText(
                "Ollama not running — install from ollama.com then run: ollama serve"
            )
            self._summary_btn.setEnabled(False)
            self._actions_btn.setEnabled(False)
        else:
            self._status_label.setText("")
            self._summary_btn.setEnabled(True)
            self._actions_btn.setEnabled(True)

    # ── Playback callbacks ────────────────────────────────────────────────────

    def _on_position(self, secs: float) -> None:
        if not self._slider_dragging:
            self._seek_slider.setValue(int(secs * 10))
        self._pos_label.setText(_fmt_sec(secs))
        self._sync_transcript(secs)

    def _on_duration(self, secs: float) -> None:
        self._seek_slider.setRange(0, int(secs * 10))
        self._dur_label.setText(_fmt_sec(secs))

    def _on_state(self, playing: bool) -> None:
        self._play_btn.setText("⏸" if playing else "▶")

    def _on_slider_pressed(self) -> None:
        self._slider_dragging = True

    def _on_slider_released(self) -> None:
        self._slider_dragging = False
        self._player.seek(self._seek_slider.value() / 10.0)

    def _sync_transcript(self, pos_sec: float) -> None:
        if not self._seg_starts or not self._player.is_playing:
            return
        # find the last segment whose start_sec <= pos_sec
        idx = bisect.bisect_right(self._seg_starts, pos_sec) - 1
        if idx < 0:
            return
        # only highlight if pos is within this segment's end
        if pos_sec > self._seg_ends[idx]:
            return
        current = self._transcript_list.currentRow()
        if idx != current:
            self._auto_scrolling = True
            self._transcript_list.setCurrentRow(idx)
            self._transcript_list.scrollToItem(
                self._transcript_list.item(idx),
                QAbstractItemView.PositionAtCenter,
            )
            self._auto_scrolling = False

    def _on_segment_clicked(self, item: QListWidgetItem) -> None:
        if self._auto_scrolling:
            return
        start = item.data(Qt.UserRole + 2)
        if start is not None:
            self._player.seek(float(start))

    # ── Speaker assignment ────────────────────────────────────────────────────

    def _segment_context_menu(self, pos) -> None:
        item = self._transcript_list.itemAt(pos)
        if not item:
            return
        seg_id = item.data(Qt.UserRole)
        speakers = db.get_speakers(self._meeting_id)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                padding: 6px 4px;
                min-width: 180px;
            }
            QMenu::item {
                padding: 8px 18px 8px 14px;
                border-radius: 6px;
                font-size: 13px;
                color: #111827;
            }
            QMenu::item:selected { background: #ede9fe; color: #4338ca; }
            QMenu::item:disabled { color: #9ca3af; }
            QMenu::separator { height: 1px; background: #e5e7eb; margin: 4px 8px; }
        """)

        header = QAction("Assign to speaker", menu)
        font = header.font()
        font.setPointSize(11)
        header.setFont(font)
        header.setEnabled(False)
        menu.addAction(header)
        menu.addSeparator()

        if not speakers:
            empty = menu.addAction("No speakers yet")
            empty.setEnabled(False)
        else:
            for sp in speakers:
                act = menu.addAction(f"  {sp.display_name}")
                act.triggered.connect(
                    lambda checked=False, sid=seg_id, spid=sp.id: self._assign_speaker(sid, spid)
                )

        menu.addSeparator()
        new_act = menu.addAction("+ New speaker…")
        new_act.triggered.connect(lambda: self._new_speaker_for_segment(seg_id))

        menu.exec(self._transcript_list.viewport().mapToGlobal(pos))

    def _assign_speaker(self, segment_id: int, speaker_id: int) -> None:
        db.assign_speaker_to_segment(segment_id, speaker_id)
        self.load()

    def _new_speaker_for_segment(self, segment_id: int) -> None:
        name, ok = QInputDialog.getText(self, "New Speaker", "Speaker name:")
        if ok and name.strip():
            sp_id = db.create_manual_speaker(self._meeting_id, name.strip())
            db.assign_speaker_to_segment(segment_id, sp_id)
            self.load()

    # ── LLM ──────────────────────────────────────────────────────────────────

    def _transcript_text(self) -> str:
        meeting = db.get_meeting(self._meeting_id)
        if not meeting:
            return ""
        lines = []
        for seg in meeting.segments:
            speaker = seg.speaker_display or "Unknown"
            lines.append(f"[{_fmt_sec(seg.start_sec)}] {speaker}: {seg.text}")
        return "\n".join(lines)

    def _gen_summary(self) -> None:
        self._run_llm("summary")

    def _gen_actions(self) -> None:
        self._run_llm("actions")

    def _run_llm(self, mode: str) -> None:
        ollama_url = self._settings.get("ollama_url", llm.DEFAULT_URL)
        if not llm.is_ollama_available(ollama_url):
            QMessageBox.warning(
                self, "Ollama not running",
                "Install Ollama from ollama.com, then run:\n\n"
                "  ollama pull llama3.2:3b\n"
                "  ollama serve\n\n"
                "Knotee will detect it automatically on the next meeting load."
            )
            return

        if self._llm_thread and self._llm_thread.isRunning():
            return

        transcript = self._transcript_text()
        model = self._settings.get("ollama_model", llm.DEFAULT_MODEL)

        if mode == "summary":
            target_edit = self._summary_edit
            gen_func = lambda: llm.generate_summary(transcript, model, ollama_url)
        else:
            target_edit = self._actions_edit
            gen_func = lambda: llm.generate_action_items(transcript, model, ollama_url)

        target_edit.clear()
        self._summary_btn.setEnabled(False)
        self._actions_btn.setEnabled(False)

        self._llm_thread = _LLMThread(gen_func)
        self._llm_thread.token_received.connect(lambda t: target_edit.insertPlainText(t))
        self._llm_thread.finished_ok.connect(self._on_llm_done)
        self._llm_thread.error.connect(self._on_llm_error)
        self._llm_thread.start()

    def _on_llm_done(self) -> None:
        self._summary_btn.setEnabled(True)
        self._actions_btn.setEnabled(True)
        db.save_summary(
            self._meeting_id,
            self._summary_edit.toPlainText(),
            self._actions_edit.toPlainText(),
        )

    def _on_llm_error(self, msg: str) -> None:
        self._status_label.setText(f"LLM error: {msg}")
        self._summary_btn.setEnabled(True)
        self._actions_btn.setEnabled(True)

    # ── Export ────────────────────────────────────────────────────────────────

    def _show_export_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Export as TXT", self._export_txt)
        menu.addAction("Export as PDF", self._export_pdf)
        menu.exec(self._export_btn.mapToGlobal(self._export_btn.rect().bottomLeft()))

    def _export_txt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export as TXT", "", "Text files (*.txt)")
        if path:
            to_txt(db.get_meeting(self._meeting_id), path)

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export as PDF", "", "PDF files (*.pdf)")
        if path:
            to_pdf(db.get_meeting(self._meeting_id), path)


def _fmt_sec(secs: float) -> str:
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
