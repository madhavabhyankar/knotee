import sqlite3
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Meeting, Segment, Speaker

_DB_PATH: Optional[str] = None


def get_db_path() -> str:
    if _DB_PATH:
        return _DB_PATH
    data_dir = Path.home() / "Knotee"
    data_dir.mkdir(exist_ok=True)
    return str(data_dir / "knotee.db")


def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS meetings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                started_at  TEXT NOT NULL,
                ended_at    TEXT,
                audio_path  TEXT,
                summary     TEXT,
                action_items TEXT
            );

            CREATE TABLE IF NOT EXISTS speakers (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id   INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                label        TEXT NOT NULL,
                display_name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS segments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id      INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                start_sec       REAL NOT NULL,
                end_sec         REAL NOT NULL,
                text            TEXT NOT NULL,
                speaker_id      INTEGER REFERENCES speakers(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_segments_meeting ON segments(meeting_id);
            CREATE INDEX IF NOT EXISTS idx_speakers_meeting ON speakers(meeting_id);
        """)


# ── Meetings ─────────────────────────────────────────────────────────────────

def create_meeting(title: str, started_at: datetime) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO meetings (title, started_at) VALUES (?, ?)",
            (title, started_at.isoformat()),
        )
        return cur.lastrowid


def finish_meeting(meeting_id: int, ended_at: datetime, audio_path: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE meetings SET ended_at=?, audio_path=? WHERE id=?",
            (ended_at.isoformat(), audio_path, meeting_id),
        )


def update_meeting_title(meeting_id: int, title: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE meetings SET title=? WHERE id=?", (title, meeting_id))


def save_summary(meeting_id: int, summary: str, action_items: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE meetings SET summary=?, action_items=? WHERE id=?",
            (summary, action_items, meeting_id),
        )


def list_meetings() -> list[Meeting]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM meetings ORDER BY started_at DESC"
        ).fetchall()
    return [_row_to_meeting(r) for r in rows]


def get_meeting(meeting_id: int) -> Optional[Meeting]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM meetings WHERE id=?", (meeting_id,)
        ).fetchone()
        if not row:
            return None
        meeting = _row_to_meeting(row)
        meeting.segments = get_segments(meeting_id)
        meeting.speakers = get_speakers(meeting_id)
    return meeting


def delete_meeting(meeting_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))


# ── Segments ──────────────────────────────────────────────────────────────────

def add_segment(meeting_id: int, start_sec: float, end_sec: float, text: str,
                speaker_id: Optional[int] = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO segments (meeting_id, start_sec, end_sec, text, speaker_id) VALUES (?,?,?,?,?)",
            (meeting_id, start_sec, end_sec, text, speaker_id),
        )
        return cur.lastrowid


def assign_speaker_to_segment(segment_id: int, speaker_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE segments SET speaker_id=? WHERE id=?", (speaker_id, segment_id)
        )


def get_segments(meeting_id: int) -> list[Segment]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT s.*, sp.display_name
               FROM segments s
               LEFT JOIN speakers sp ON s.speaker_id = sp.id
               WHERE s.meeting_id=?
               ORDER BY s.start_sec""",
            (meeting_id,),
        ).fetchall()
    return [
        Segment(
            id=r["id"],
            meeting_id=r["meeting_id"],
            start_sec=r["start_sec"],
            end_sec=r["end_sec"],
            text=r["text"],
            speaker_id=r["speaker_id"],
            speaker_display=r["display_name"],
        )
        for r in rows
    ]


# ── Speakers ──────────────────────────────────────────────────────────────────

def create_manual_speaker(meeting_id: int, display_name: str) -> int:
    with _connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) as c FROM speakers WHERE meeting_id=?", (meeting_id,)
        ).fetchone()["c"]
        label = f"MANUAL_{n}"
        cur = conn.execute(
            "INSERT INTO speakers (meeting_id, label, display_name) VALUES (?,?,?)",
            (meeting_id, label, display_name),
        )
        return cur.lastrowid


def get_or_create_speaker(meeting_id: int, label: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM speakers WHERE meeting_id=? AND label=?",
            (meeting_id, label),
        ).fetchone()
        if row:
            return row["id"]
        n = conn.execute(
            "SELECT COUNT(*) as c FROM speakers WHERE meeting_id=?", (meeting_id,)
        ).fetchone()["c"]
        display = f"Speaker {n + 1}"
        cur = conn.execute(
            "INSERT INTO speakers (meeting_id, label, display_name) VALUES (?,?,?)",
            (meeting_id, label, display),
        )
        return cur.lastrowid


def rename_speaker(speaker_id: int, display_name: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE speakers SET display_name=? WHERE id=?", (display_name, speaker_id)
        )


def get_speakers(meeting_id: int) -> list[Speaker]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM speakers WHERE meeting_id=? ORDER BY id", (meeting_id,)
        ).fetchall()
    return [
        Speaker(id=r["id"], meeting_id=r["meeting_id"],
                label=r["label"], display_name=r["display_name"])
        for r in rows
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_meeting(r: sqlite3.Row) -> Meeting:
    return Meeting(
        id=r["id"],
        title=r["title"],
        started_at=datetime.fromisoformat(r["started_at"]),
        ended_at=datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None,
        audio_path=r["audio_path"],
        summary=r["summary"],
        action_items=r["action_items"],
    )
