import traceback

from PySide6.QtCore import QThread, Signal

from .engine import DiarizationEngine
from ..storage import db


def apply_diarization_to_meeting(meeting_id: int, turns: list) -> None:
    """Match pyannote speaker turns to transcript segments and persist to DB."""
    segments = db.get_segments(meeting_id)
    for seg in segments:
        for turn in turns:
            if turn["start"] <= seg.start_sec < turn["end"]:
                sp_id = db.get_or_create_speaker(meeting_id, turn["label"])
                db.assign_speaker_to_segment(seg.id, sp_id)
                break


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
            full = traceback.format_exc()
            self.error_occurred.emit(full)
