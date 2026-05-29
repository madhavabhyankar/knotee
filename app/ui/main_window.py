import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QPushButton, QLabel, QFrame,
)

from ..storage import db
from .recording_view import RecordingView
from .history_view import HistoryView
from .meeting_detail import MeetingDetailView
from .settings_dialog import SettingsDialog

_SETTINGS_PATH = Path.home() / "Knotee" / "settings.json"
_DEFAULT_SETTINGS = {
    "audio_device": None,
    "whisper_model": "base.en",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3.2:3b",
}


def _load_settings() -> dict:
    if _SETTINGS_PATH.exists():
        try:
            return {**_DEFAULT_SETTINGS, **json.loads(_SETTINGS_PATH.read_text())}
        except Exception:
            pass
    return dict(_DEFAULT_SETTINGS)


def _save_settings(s: dict) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(json.dumps(s, indent=2))


class Sidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet("background: #1e1b4b;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        logo = QLabel("  Knotee")
        logo.setStyleSheet(
            "color: white; font-size: 20px; font-weight: bold; padding: 24px 16px 16px;"
        )
        layout.addWidget(logo)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #312e81;")
        layout.addWidget(sep)

        self.record_btn = self._nav_button("● Record")
        self.history_btn = self._nav_button("⊟ Meetings")
        layout.addWidget(self.record_btn)
        layout.addWidget(self.history_btn)
        layout.addStretch()

        self.settings_btn = self._nav_button("⚙ Settings")
        layout.addWidget(self.settings_btn)

    def _nav_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setStyleSheet(
            "QPushButton { color: #c7d2fe; background: transparent; text-align: left; "
            "padding: 12px 20px; border: none; font-size: 14px; }"
            "QPushButton:hover { background: #312e81; }"
            "QPushButton:checked { background: #4338ca; color: white; }"
        )
        return btn


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Knotee")
        self.setMinimumSize(960, 600)
        self._settings = _load_settings()
        db.init_db()
        self._build_ui()
        self._show_record()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar = Sidebar()
        root.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: white;")
        root.addWidget(self._stack, stretch=1)

        # Pages
        self._recording_view = RecordingView(self._settings)
        self._recording_view.recording_saved.connect(self._on_recording_saved)
        self._stack.addWidget(self._recording_view)   # index 0

        self._history_view = HistoryView()
        self._history_view.meeting_selected.connect(self._show_meeting_detail)
        self._stack.addWidget(self._history_view)     # index 1

        self._detail_placeholder = QWidget()          # index 2, replaced dynamically
        self._stack.addWidget(self._detail_placeholder)

        # Sidebar nav
        self._sidebar.record_btn.clicked.connect(self._show_record)
        self._sidebar.history_btn.clicked.connect(self._show_history)
        self._sidebar.settings_btn.clicked.connect(self._open_settings)

    def _show_record(self) -> None:
        self._stack.setCurrentIndex(0)
        self._sidebar.record_btn.setChecked(True)
        self._sidebar.history_btn.setChecked(False)

    def _show_history(self) -> None:
        self._history_view.refresh()
        self._stack.setCurrentIndex(1)
        self._sidebar.record_btn.setChecked(False)
        self._sidebar.history_btn.setChecked(True)

    def _show_meeting_detail(self, meeting_id: int) -> None:
        # replace detail widget
        old = self._stack.widget(2)
        if old:
            self._stack.removeWidget(old)
            old.deleteLater()
        detail = MeetingDetailView(meeting_id, self._settings)
        self._stack.insertWidget(2, detail)
        self._stack.setCurrentIndex(2)
        self._sidebar.history_btn.setChecked(True)

    def _on_recording_saved(self, meeting_id: int) -> None:
        self._show_meeting_detail(meeting_id)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec():
            self._settings = dlg.get_settings()
            _save_settings(self._settings)
            self._recording_view.update_settings(self._settings)
