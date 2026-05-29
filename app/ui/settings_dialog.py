from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QTabWidget, QWidget,
    QMessageBox,
)
from PySide6.QtCore import Qt

from ..audio.devices import list_input_devices, default_input_device
from ..diarization.engine import get_hf_token, set_hf_token
from ..llm.client import is_ollama_available, list_models, DEFAULT_URL, DEFAULT_MODEL

_WHISPER_MODELS = ["tiny.en", "base.en", "small.en", "medium.en"]


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self._settings = dict(settings)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(self._audio_tab(), "Audio")
        tabs.addTab(self._transcription_tab(), "Transcription")
        tabs.addTab(self._diarization_tab(), "Speaker ID")
        tabs.addTab(self._llm_tab(), "Local AI")

        btns = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        layout.addLayout(btns)

    # ── Audio tab ──────────────────────────────────────────────────────────

    def _audio_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._device_combo = QComboBox()
        devices = list_input_devices()
        default_idx = self._settings.get("audio_device", default_input_device())
        sel = 0
        for i, d in enumerate(devices):
            self._device_combo.addItem(d["name"], d["index"])
            if d["index"] == default_idx:
                sel = i
        self._device_combo.setCurrentIndex(sel)
        form.addRow("Input device:", self._device_combo)
        hint = QLabel(
            "For phone calls, install BlackHole 2ch and select it here\n"
            "after routing your system audio output through it."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", hint)
        return w

    # ── Transcription tab ──────────────────────────────────────────────────

    def _transcription_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._whisper_combo = QComboBox()
        for m in _WHISPER_MODELS:
            self._whisper_combo.addItem(m)
        cur = self._settings.get("whisper_model", "base.en")
        idx = _WHISPER_MODELS.index(cur) if cur in _WHISPER_MODELS else 1
        self._whisper_combo.setCurrentIndex(idx)
        form.addRow("Whisper model:", self._whisper_combo)
        hint = QLabel(
            "larger = more accurate but slower to start.\n"
            "Models download automatically on first use (~150 MB – 1.5 GB)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", hint)
        return w

    # ── Diarization tab ───────────────────────────────────────────────────

    def _diarization_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        current_token = get_hf_token() or ""
        display = "••••••••" if current_token else ""
        self._hf_token_edit = QLineEdit()
        self._hf_token_edit.setPlaceholderText("hf_...")
        self._hf_token_edit.setText(display)
        self._hf_token_edit.setEchoMode(QLineEdit.Password)
        self._hf_token_edit.textChanged.connect(lambda: None)
        form.addRow("HuggingFace token:", self._hf_token_edit)
        hint = QLabel(
            "Required for speaker identification (pyannote model).\n"
            "Get a free token at huggingface.co → Settings → Access Tokens.\n"
            "Accept the pyannote/speaker-diarization-3.1 model license on HF."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", hint)
        return w

    # ── LLM tab ───────────────────────────────────────────────────────────

    def _llm_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._ollama_url_edit = QLineEdit(self._settings.get("ollama_url", DEFAULT_URL))
        form.addRow("Ollama URL:", self._ollama_url_edit)

        self._ollama_model_edit = QLineEdit(self._settings.get("ollama_model", DEFAULT_MODEL))
        form.addRow("Model:", self._ollama_model_edit)

        test_btn = QPushButton("Test connection")
        test_btn.clicked.connect(self._test_ollama)
        form.addRow("", test_btn)

        hint = QLabel(
            "Install Ollama from ollama.com then run:\n"
            "  ollama pull llama3.2:3b\n"
            "Knotee works without Ollama; AI summaries will be unavailable."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", hint)
        return w

    def _test_ollama(self) -> None:
        url = self._ollama_url_edit.text().strip()
        if is_ollama_available(url):
            models = list_models(url)
            QMessageBox.information(self, "Ollama", f"Connected.\nAvailable models: {', '.join(models) or 'none'}")
        else:
            QMessageBox.warning(self, "Ollama", "Could not connect. Is Ollama running?")

    # ── Save ──────────────────────────────────────────────────────────────

    def _save(self) -> None:
        self._settings["audio_device"] = self._device_combo.currentData()
        self._settings["whisper_model"] = self._whisper_combo.currentText()
        self._settings["ollama_url"] = self._ollama_url_edit.text().strip()
        self._settings["ollama_model"] = self._ollama_model_edit.text().strip()

        token = self._hf_token_edit.text().strip()
        if token and token != "••••••••":
            set_hf_token(token)

        self.accept()

    def get_settings(self) -> dict:
        return self._settings
