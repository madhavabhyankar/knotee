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
        from huggingface_hub import login as hf_login
        token = get_hf_token()
        if not token:
            raise RuntimeError(
                "No HuggingFace token found. Add one in Settings to enable speaker diarization."
            )
        # Authenticate globally so from_pretrained needs no token kwarg —
        # avoids breaking changes across pyannote versions (3.x vs 4.x).
        hf_login(token=token, add_to_git_credential=False)
        self._pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
        )

    def diarize(self, wav_path: str) -> list[dict]:
        """Returns list of {label, start, end} dicts sorted by start."""
        if self._pipeline is None:
            self.load()
        result = self._pipeline(wav_path)
        # pyannote 4.x wraps the annotation in DiarizeOutput
        annotation = getattr(result, "speaker_diarization", result)
        turns = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            turns.append({"label": speaker, "start": turn.start, "end": turn.end})
        turns.sort(key=lambda t: t["start"])
        return turns
