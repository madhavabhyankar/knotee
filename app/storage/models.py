from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Speaker:
    id: int
    meeting_id: int
    label: str           # pyannote label e.g. "SPEAKER_00"
    display_name: str    # user-assigned name e.g. "John"


@dataclass
class Segment:
    id: int
    meeting_id: int
    start_sec: float
    end_sec: float
    text: str
    speaker_id: Optional[int] = None
    speaker_display: Optional[str] = None  # denormalized for fast display


@dataclass
class Meeting:
    id: int
    title: str
    started_at: datetime
    ended_at: Optional[datetime]
    audio_path: Optional[str]
    summary: Optional[str] = None
    action_items: Optional[str] = None
    segments: list = field(default_factory=list)
    speakers: list = field(default_factory=list)
