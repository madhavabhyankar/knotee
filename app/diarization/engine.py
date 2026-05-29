from typing import Optional
import keyring

_SERVICE = "knotee"
_HF_KEY = "hf_token"


def get_hf_token() -> Optional[str]:
    return keyring.get_password(_SERVICE, _HF_KEY)


def set_hf_token(token: str) -> None:
    keyring.set_password(_SERVICE, _HF_KEY, token)


class DiarizationEngine:
    def __init__(self):
        self._pipeline = None

    def load(self) -> None:
        from pyannote.audio import Pipeline
        token = get_hf_token()
        if not token:
            raise RuntimeError(
                "No HuggingFace token found. Add one in Settings to enable speaker diarization."
            )
        self._pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token,
        )

    def diarize(self, wav_path: str) -> list[dict]:
        """Returns list of {label, start, end} dicts sorted by start."""
        if self._pipeline is None:
            self.load()
        diarization = self._pipeline(wav_path)
        turns = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append({"label": speaker, "start": turn.start, "end": turn.end})
        turns.sort(key=lambda t: t["start"])
        return turns
