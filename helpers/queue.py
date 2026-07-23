"""
queue.py — v6.0 — In-memory song queue per chat
Song dataclass: url = direct stream URL, thumbnail optional
✅ Added shuffle_queue() — no more private dict access from play.py
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Song:
    title:        str
    url:          str           # direct stream URL (filled after yt-dlp)
    duration:     int           = 0
    webpage_url:  str           = ""
    thumbnail:    str           = ""
    requested_by: str           = "Unknown"
    source:       str           = "youtube"
    is_video:     bool          = False
    http_headers: dict          = field(default_factory=dict)


_queues:  Dict[int, List[Song]] = {}
_current: Dict[int, Song]       = {}


def get_queue(chat_id: int) -> List[Song]:
    return list(_queues.get(chat_id, []))


def get_current(chat_id: int) -> Optional[Song]:
    return _current.get(chat_id)


def set_current(chat_id: int, song: Optional[Song]):
    if song is None:
        _current.pop(chat_id, None)
    else:
        _current[chat_id] = song


def add_to_queue(chat_id: int, song: Song) -> int:
    """Add song to queue, return its 1-indexed position."""
    _queues.setdefault(chat_id, []).append(song)
    return len(_queues[chat_id])


def pop_queue(chat_id: int) -> Optional[Song]:
    q = _queues.get(chat_id)
    if q:
        return q.pop(0)
    return None


def clear_queue(chat_id: int):
    _queues[chat_id] = []
    _current.pop(chat_id, None)


def queue_size(chat_id: int) -> int:
    return len(_queues.get(chat_id, []))


def is_active(chat_id: int) -> bool:
    return chat_id in _current


def shuffle_queue(chat_id: int) -> int:
    """Shuffle the waiting queue in-place. Returns number of songs shuffled."""
    q = _queues.get(chat_id, [])
    if q:
        random.shuffle(q)
    return len(q)
