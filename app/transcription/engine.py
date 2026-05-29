from typing import Optional

_engine_instance = None


def get_engine(model_size: str = "base.en"):
    global _engine_instance
    if _engine_instance is None or _engine_instance._model_size != model_size:
        _engine_instance = WhisperEngine(model_size)
    return _engine_instance


class WhisperEngine:
    def __init__(self, model_size: str = "base.en"):
        self._model_size = model_size
        self._model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel
        self._model = WhisperModel(
            self._model_size,
            device="cpu",
            compute_type="int8",
        )

    def transcribe(self, audio_array, language: str = "en") -> list[dict]:
        if self._model is None:
            self.load()
        segments, _ = self._model.transcribe(
            audio_array,
            language=language,
            beam_size=5,
            vad_filter=True,
        )
        return [
            {"start": s.start, "end": s.end, "text": s.text.strip()}
            for s in segments
        ]
