"""Telegram-backed media archive for instant, cookie-free music playback.

The archive is deliberately implemented with Telegram message IDs/file IDs
instead of local disk or a second database. Telegram keeps the uploaded media
available across dyno restarts, while the channel caption contains enough
metadata to rebuild the playback queue by scanning the channel.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass

from clients import bot
from config import ARCHIVE_SCAN_LIMIT, MUSIC_ARCHIVE_CHANNEL

log = logging.getLogger("ApexBot.archive")

_VIDEO_ID = re.compile(r"(?im)^video_id:\s*([A-Za-z0-9_-]{11})\s*$")
_SOURCE_URL = re.compile(r"(?im)^source:\s*(\S+)\s*$")
_TITLE = re.compile(r"(?im)^title:\s*(.+?)\s*$")
_ARTIST = re.compile(r"(?im)^artist:\s*(.+?)\s*$")
_DURATION = re.compile(r"(?im)^duration:\s*(\d+)\s*$")
_scan_lock = asyncio.Lock()
_last_scan = 0.0
_index_by_id: dict[str, dict] = {}
_index_by_title: dict[str, dict] = {}
_SCAN_TTL = 30.0


@dataclass
class ArchiveRecord:
    video_id: str
    title: str
    artist: str
    source_url: str
    duration: int
    message_id: int
    file_id: str
    file_type: str


def _video_id(url: str) -> str:
    match = re.search(
        r"(?:[?&]v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})",
        url or "",
    )
    return match.group(1) if match else ""


def _normalise(value: str) -> str:
    return " ".join((value or "").lower().split())


def _match_value(pattern: re.Pattern, text: str, default: str = "") -> str:
    match = pattern.search(text)
    return match.group(1).strip() if match else default


def _caption_for(
    *,
    video_id: str,
    title: str,
    artist: str,
    source_url: str,
    duration: int,
) -> str:
    # Keep this machine-readable and human-readable. It is also the fallback
    # index when the bot restarts and the local filesystem/database is empty.
    return (
        "ApexMusic Archive v1\n"
        f"Video_ID: {video_id}\n"
        f"Title: {title[:180]}\n"
        f"Artist: {(artist or 'Unknown')[:120]}\n"
        f"Duration: {int(duration or 0)}\n"
        f"Source: {source_url}\n"
        "Playback: Telegram cache (no YouTube cookies required)"
    )


def _record_from_message(message) -> ArchiveRecord | None:
    caption = getattr(message, "caption", None) or getattr(message, "text", None) or ""
    if "ApexMusic Archive" not in caption:
        return None
    video_id = _match_value(_VIDEO_ID, caption)
    source_url = _match_value(_SOURCE_URL, caption)
    video_id = video_id or _video_id(source_url)
    if not video_id:
        return None
    title = _match_value(_TITLE, caption, "Unknown")
    artist = _match_value(_ARTIST, caption, "Unknown")
    duration_raw = _match_value(_DURATION, caption, "0")
    try:
        duration = int(duration_raw)
    except ValueError:
        duration = 0

    media = (
        getattr(message, "audio", None)
        or getattr(message, "video", None)
        or getattr(message, "document", None)
    )
    if not media or not getattr(media, "file_id", None):
        return None
    if getattr(message, "audio", None):
        file_type = "audio"
    elif getattr(message, "video", None):
        file_type = "video"
    else:
        file_type = "document"
    return ArchiveRecord(
        video_id=video_id,
        title=title,
        artist=artist,
        source_url=source_url or f"https://www.youtube.com/watch?v={video_id}",
        duration=duration,
        message_id=int(message.id),
        file_id=media.file_id,
        file_type=file_type,
    )


async def _scan_archive() -> None:
    global _last_scan
    if MUSIC_ARCHIVE_CHANNEL == 0:
        return
    async with _scan_lock:
        if time.monotonic() - _last_scan < _SCAN_TTL:
            return
        try:
            async for message in bot.get_chat_history(
                MUSIC_ARCHIVE_CHANNEL, limit=max(1, ARCHIVE_SCAN_LIMIT)
            ):
                record = _record_from_message(message)
                if record:
                    data = record.__dict__.copy()
                    _index_by_id[record.video_id] = data
                    _index_by_title[_normalise(record.title)] = data
            _last_scan = time.monotonic()
            log.info(
                "✅ Archive scan complete | channel=%s | indexed=%d",
                MUSIC_ARCHIVE_CHANNEL,
                len(_index_by_id),
            )
        except Exception as exc:
            # Archive is an optimisation. A missing/incorrect channel must not
            # prevent regular YouTube playback.
            log.warning("Archive scan unavailable for %s: %s", MUSIC_ARCHIVE_CHANNEL, exc)


async def find_archived(query: str) -> dict | None:
    """Find an archived track by YouTube URL/video ID or title words."""
    await _scan_archive()
    video_id = _video_id(query)
    if video_id and video_id in _index_by_id:
        return _index_by_id[video_id].copy()

    needle = _normalise(query)
    if not needle:
        return None
    exact = _index_by_title.get(needle)
    if exact:
        return exact.copy()
    words = [word for word in needle.split() if len(word) > 2]
    for title, record in reversed(list(_index_by_title.items())):
        if words and all(word in title for word in words):
            return record.copy()
    return None


async def upload_local(
    path: str,
    *,
    title: str,
    artist: str,
    source_url: str,
    duration: int,
    is_video: bool = False,
) -> dict | None:
    """Upload a downloaded track once and add it to the archive index."""
    if (
        MUSIC_ARCHIVE_CHANNEL == 0
        or not path
        or not os.path.isfile(path)
        or not source_url
    ):
        return None
    video_id = _video_id(source_url)
    if not video_id:
        return None
    existing = await find_archived(video_id)
    if existing:
        return existing
    try:
        caption = _caption_for(
            video_id=video_id,
            title=title,
            artist=artist,
            source_url=source_url,
            duration=duration,
        )
        if is_video:
            # Keep the original container untouched. Telegram documents can
            # store webm/mkv files that send_video would reject or transcode.
            sent = await bot.send_document(
                MUSIC_ARCHIVE_CHANNEL,
                document=path,
                caption=caption,
            )
        else:
            sent = await bot.send_audio(
                MUSIC_ARCHIVE_CHANNEL,
                audio=path,
                caption=caption,
                title=title[:64],
                performer=(artist or "YouTube")[:64],
                duration=int(duration or 0),
            )
        record = _record_from_message(sent)
        if not record:
            log.warning("Archive upload succeeded but media metadata was missing")
            return None
        data = record.__dict__.copy()
        _index_by_id[record.video_id] = data
        _index_by_title[_normalise(record.title)] = data
        log.info("✅ Archived audio | video_id=%s | message_id=%s", video_id, record.message_id)
        return data
    except Exception as exc:
        log.warning("Archive upload failed for %s: %s", title[:60], exc)
        return None


async def download_archived(record: dict) -> str:
    """Download Telegram media to a short-lived local path for PyTgCalls."""
    directory = tempfile.mkdtemp(prefix="apex_tg_")
    try:
        message = await bot.get_messages(
            MUSIC_ARCHIVE_CHANNEL, int(record["message_id"])
        )
        if not message:
            raise RuntimeError("archive message not found")
        result = await bot.download_media(
            message,
            file_name=os.path.join(directory, "audio"),
        )
        if not result or not os.path.isfile(result):
            raise RuntimeError("archive media download returned no file")
        return result
    except Exception:
        try:
            for name in os.listdir(directory):
                os.unlink(os.path.join(directory, name))
            os.rmdir(directory)
        except OSError:
            pass
        raise


def record_to_song_fields(record: dict) -> dict:
    return {
        "title": record.get("title", "Unknown"),
        "artist": record.get("artist", "Unknown"),
        "duration": int(record.get("duration") or 0),
        "webpage_url": record.get("source_url", ""),
        "archive_message_id": int(record.get("message_id") or 0),
        "archive_file_id": record.get("file_id", ""),
    }