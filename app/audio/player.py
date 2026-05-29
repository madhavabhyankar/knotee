from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


class MeetingPlayer(QObject):
    position_changed = Signal(float)       # seconds
    duration_changed = Signal(float)       # seconds
    playback_state_changed = Signal(bool)  # True = playing

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio_out = QAudioOutput(self)
        self._audio_out.setVolume(1.0)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.positionChanged.connect(
            lambda ms: self.position_changed.emit(ms / 1000.0)
        )
        self._player.durationChanged.connect(
            lambda ms: self.duration_changed.emit(ms / 1000.0)
        )
        self._player.playbackStateChanged.connect(
            lambda s: self.playback_state_changed.emit(
                s == QMediaPlayer.PlaybackState.PlayingState
            )
        )

    def load(self, path: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(path))

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def seek(self, seconds: float) -> None:
        self._player.setPosition(int(seconds * 1000))

    def stop(self) -> None:
        self._player.stop()

    @property
    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
