import queue
import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal

from .engine import get_engine

SAMPLE_RATE = 16000
WINDOW_SECS = 5        # transcribe every N seconds of audio
OVERLAP_SECS = 0.5     # overlap to avoid clipping words at boundaries


class TranscriptionWorker(QThread):
    segment_ready = Signal(float, float, str)  # start_sec, end_sec, text
    model_loading = Signal()
    model_ready = Signal()
    error_occurred = Signal(str)

    def __init__(self, model_size: str = "base.en", parent=None):
        super().__init__(parent)
        self._model_size = model_size
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._session_offset = 0.0  # seconds elapsed since recording started

    def feed(self, pcm_bytes: bytes) -> None:
        self._queue.put(pcm_bytes)

    def run(self) -> None:
        self._running = True
        self.model_loading.emit()
        try:
            engine = get_engine(self._model_size)
            engine.load()
        except Exception as exc:
            self.error_occurred.emit(f"Failed to load Whisper model: {exc}")
            return
        self.model_ready.emit()

        window_samples = int(WINDOW_SECS * SAMPLE_RATE)
        overlap_samples = int(OVERLAP_SECS * SAMPLE_RATE)
        buffer = np.array([], dtype=np.int16)
        window_start_sec = 0.0

        while self._running or not self._queue.empty():
            try:
                chunk = self._queue.get(timeout=0.1)
            except queue.Empty:
                # flush remaining buffer when stopping
                if not self._running and len(buffer) > 0:
                    self._flush(engine, buffer, window_start_sec)
                    buffer = np.array([], dtype=np.int16)
                continue

            new_samples = np.frombuffer(chunk, dtype=np.int16)
            buffer = np.concatenate([buffer, new_samples])

            if len(buffer) >= window_samples:
                self._flush(engine, buffer[:window_samples], window_start_sec)
                # keep overlap to avoid cutting words
                buffer = buffer[window_samples - overlap_samples:]
                window_start_sec += WINDOW_SECS - OVERLAP_SECS

        # final flush
        if len(buffer) > 0:
            self._flush(engine, buffer, window_start_sec)

    def _flush(self, engine, samples: np.ndarray, offset_sec: float) -> None:
        audio = samples.astype(np.float32) / 32768.0
        try:
            results = engine.transcribe(audio)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
            return
        for seg in results:
            start = offset_sec + seg["start"]
            end = offset_sec + seg["end"]
            if seg["text"]:
                self.segment_ready.emit(start, end, seg["text"])

    def stop(self) -> None:
        self._running = False
        self.wait()
