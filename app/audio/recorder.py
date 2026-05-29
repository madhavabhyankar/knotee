import collections
import os
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QThread, Signal

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK_MS = 30  # milliseconds per callback frame
CHUNK_FRAMES = int(SAMPLE_RATE * CHUNK_MS / 1000)


class AudioRecorder(QThread):
    level_changed = Signal(float)    # RMS 0.0–1.0 for waveform display
    chunk_ready = Signal(bytes)      # raw PCM bytes for transcription worker
    error_occurred = Signal(str)

    def __init__(self, device_index: Optional[int] = None, parent=None):
        super().__init__(parent)
        self._device = device_index
        self._buffer: collections.deque = collections.deque()
        self._wav_path: Optional[str] = None
        self._wav_file: Optional[wave.Wave_write] = None
        self._running = False
        self._stream: Optional[sd.InputStream] = None

    @property
    def wav_path(self) -> Optional[str]:
        return self._wav_path

    def run(self) -> None:
        recordings_dir = Path.home() / "Knotee" / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._wav_path = str(recordings_dir / f"{ts}.wav")

        self._wav_file = wave.open(self._wav_path, "wb")
        self._wav_file.setnchannels(CHANNELS)
        self._wav_file.setsampwidth(2)  # int16 = 2 bytes
        self._wav_file.setframerate(SAMPLE_RATE)

        self._running = True
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=CHUNK_FRAMES,
                device=self._device,
                callback=self._callback,
            ):
                while self._running:
                    self.msleep(50)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            if self._wav_file:
                self._wav_file.close()

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        if status:
            pass  # tolerate minor underruns
        pcm = indata.flatten().tobytes()
        # write to WAV
        if self._wav_file:
            self._wav_file.writeframes(pcm)
        # emit level for waveform display
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
        self.level_changed.emit(min(rms * 10, 1.0))
        # emit chunk for transcription
        self.chunk_ready.emit(pcm)

    def stop_recording(self) -> None:
        self._running = False
        self.wait()
