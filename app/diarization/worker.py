from PySide6.QtCore import QThread, Signal

from .engine import DiarizationEngine


class DiarizationWorker(QThread):
    diarization_complete = Signal(list)   # list of {label, start, end}
    error_occurred = Signal(str)
    progress = Signal(str)

    def __init__(self, wav_path: str, parent=None):
        super().__init__(parent)
        self._wav_path = wav_path

    def run(self) -> None:
        self.progress.emit("Loading speaker model…")
        try:
            engine = DiarizationEngine()
            engine.load()
            self.progress.emit("Identifying speakers…")
            turns = engine.diarize(self._wav_path)
            self.diarization_complete.emit(turns)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
