import math
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QSizePolicy, QFrame,
)

from ..audio.recorder import AudioRecorder
from ..transcription.worker import TranscriptionWorker
from ..diarization.worker import DiarizationWorker
from ..storage import db
from ..llm.client import is_ollama_available


class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0
        self._history: list[float] = [0.0] * 60
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_level(self, level: float) -> None:
        self._history.pop(0)
        self._history.append(level)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h // 2
        bar_w = max(1, w // len(self._history))
        for i, lvl in enumerate(self._history):
            bar_h = max(2, int(lvl * (h - 4)))
            x = i * bar_w
            alpha = int(80 + 175 * (i / len(self._history)))
            color = QColor(99, 102, 241, alpha)
            p.fillRect(x, mid - bar_h // 2, bar_w - 1, bar_h, color)


class RecordingView(QWidget):
    recording_saved = Signal(int)  # meeting_id

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._meeting_id: Optional[int] = None
        self._recorder: Optional[AudioRecorder] = None
        self._transcriber: Optional[TranscriptionWorker] = None
        self._diarizer: Optional[DiarizationWorker] = None
        self._elapsed_timer: Optional[QTimer] = None
        self._elapsed_secs = 0
        self._is_recording = False
        self._pending_segments: list[dict] = []  # before saving to DB
        self._build_ui()

    def update_settings(self, settings: dict) -> None:
        self._settings = settings

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # ── Title ──────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        self._title_label = QLabel("New Meeting")
        self._title_label.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_row.addWidget(self._title_label)
        title_row.addStretch()
        self._ai_badge = QLabel()
        self._ai_badge.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 8px;")
        self._update_ai_badge()
        title_row.addWidget(self._ai_badge)
        layout.addLayout(title_row)

        # ── Waveform ───────────────────────────────────────────────────
        self._waveform = WaveformWidget()
        layout.addWidget(self._waveform)

        # ── Timer + status ─────────────────────────────────────────────
        status_row = QHBoxLayout()
        self._timer_label = QLabel("00:00")
        self._timer_label.setStyleSheet("font-size: 32px; font-weight: bold; font-family: monospace;")
        status_row.addWidget(self._timer_label)
        status_row.addStretch()
        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: gray; font-size: 13px;")
        status_row.addWidget(self._status_label)
        layout.addLayout(status_row)

        # ── Record button ──────────────────────────────────────────────
        self._record_btn = QPushButton("● Start Recording")
        self._record_btn.setFixedHeight(44)
        self._record_btn.setStyleSheet(
            "QPushButton { background: #ef4444; color: white; border-radius: 8px; font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background: #dc2626; }"
        )
        self._record_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self._record_btn)

        # ── Live transcript ────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #e5e7eb;")
        layout.addWidget(sep)

        transcript_label = QLabel("Live Transcript")
        transcript_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #6b7280;")
        layout.addWidget(transcript_label)

        self._transcript = QTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setPlaceholderText("Transcript will appear here as you speak…")
        self._transcript.setStyleSheet(
            "QTextEdit { border: 1px solid #e5e7eb; border-radius: 6px; "
            "background: #f9fafb; padding: 8px; font-size: 14px; }"
        )
        layout.addWidget(self._transcript, stretch=1)

    def _update_ai_badge(self) -> None:
        url = self._settings.get("ollama_url", "http://localhost:11434")
        if is_ollama_available(url):
            self._ai_badge.setText("AI ready")
            self._ai_badge.setStyleSheet(
                "font-size: 11px; padding: 2px 8px; border-radius: 8px; "
                "background: #d1fae5; color: #065f46;"
            )
        else:
            self._ai_badge.setText("AI offline")
            self._ai_badge.setStyleSheet(
                "font-size: 11px; padding: 2px 8px; border-radius: 8px; "
                "background: #f3f4f6; color: #9ca3af;"
            )

    def _toggle_recording(self) -> None:
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self._is_recording = True
        self._elapsed_secs = 0
        self._pending_segments.clear()
        self._transcript.clear()

        now = datetime.now()
        title = now.strftime("Meeting %b %d, %Y %H:%M")
        self._meeting_id = db.create_meeting(title, now)
        self._title_label.setText(title)

        # audio
        device = self._settings.get("audio_device")
        self._recorder = AudioRecorder(device_index=device)
        self._recorder.level_changed.connect(self._waveform.set_level)
        self._recorder.error_occurred.connect(self._on_audio_error)

        # transcription
        model = self._settings.get("whisper_model", "base.en")
        self._transcriber = TranscriptionWorker(model_size=model)
        self._transcriber.model_loading.connect(lambda: self._set_status("Loading Whisper model…"))
        self._transcriber.model_ready.connect(lambda: self._set_status("Recording"))
        self._transcriber.segment_ready.connect(self._on_segment)
        self._transcriber.error_occurred.connect(self._on_transcription_error)
        self._recorder.chunk_ready.connect(self._transcriber.feed)

        self._transcriber.start()
        self._recorder.start()

        # timer
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._tick)
        self._elapsed_timer.start(1000)

        self._record_btn.setText("■ Stop Recording")
        self._record_btn.setStyleSheet(
            "QPushButton { background: #6b7280; color: white; border-radius: 8px; font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background: #4b5563; }"
        )

    def _stop_recording(self) -> None:
        self._is_recording = False
        if self._elapsed_timer:
            self._elapsed_timer.stop()

        self._set_status("Saving…")
        if self._recorder:
            self._recorder.stop_recording()
        if self._transcriber:
            self._transcriber.stop()

        wav_path = self._recorder.wav_path if self._recorder else ""
        db.finish_meeting(self._meeting_id, datetime.now(), wav_path)

        self._record_btn.setText("● Start Recording")
        self._record_btn.setStyleSheet(
            "QPushButton { background: #ef4444; color: white; border-radius: 8px; font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background: #dc2626; }"
        )

        # run diarization if we have a WAV and an HF token
        if wav_path:
            self._run_diarization(wav_path)
        else:
            self._set_status("Done")
            if self._meeting_id:
                self.recording_saved.emit(self._meeting_id)

    def _run_diarization(self, wav_path: str) -> None:
        self._set_status("Identifying speakers…")
        self._diarizer = DiarizationWorker(wav_path)
        self._diarizer.diarization_complete.connect(self._on_diarization)
        self._diarizer.error_occurred.connect(self._on_diarization_error)
        self._diarizer.progress.connect(self._set_status)
        self._diarizer.start()

    def _on_segment(self, start: float, end: float, text: str) -> None:
        seg_id = db.add_segment(self._meeting_id, start, end, text)
        self._pending_segments.append({"id": seg_id, "start": start, "end": end})
        self._transcript.append(f"<span style='color:#9ca3af;font-size:12px'>[{_fmt_sec(start)}]</span> {text}")

    def _on_diarization(self, turns: list) -> None:
        segments = db.get_segments(self._meeting_id)
        for seg in segments:
            for turn in turns:
                if turn["start"] <= seg.start_sec < turn["end"]:
                    sp_id = db.get_or_create_speaker(self._meeting_id, turn["label"])
                    db.assign_speaker_to_segment(seg.id, sp_id)
                    break
        self._set_status("Done")
        if self._meeting_id:
            self.recording_saved.emit(self._meeting_id)

    def _on_diarization_error(self, msg: str) -> None:
        self._set_status(f"Speaker ID unavailable: {msg.split(':')[0]}")
        if self._meeting_id:
            self.recording_saved.emit(self._meeting_id)

    def _on_audio_error(self, msg: str) -> None:
        self._set_status(f"Audio error: {msg}")

    def _on_transcription_error(self, msg: str) -> None:
        self._set_status(f"Transcription error: {msg}")

    def _tick(self) -> None:
        self._elapsed_secs += 1
        m, s = divmod(self._elapsed_secs, 60)
        self._timer_label.setText(f"{m:02d}:{s:02d}")

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)


def _fmt_sec(secs: float) -> str:
    m, s = divmod(int(secs), 60)
    return f"{m}:{s:02d}"
