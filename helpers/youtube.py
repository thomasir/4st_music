"""
youtube.py — cookies-only
Sirf YOUTUBE_COOKIES env var ya cookies/youtube.txt file use karta hai.
"""

import os
import yt_dlp
import asyncio
import logging
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("ApexBot.youtube")

_exec = ThreadPoolExecutor(max_workers=8)

# ── Cache ─────────────────────────────────────────────────────────
_stream_cache: dict[str, tuple[str, int, float]] = {}
_search_cache: dict[str, tuple[dict, float]]     = {}
STREAM_TTL = 3600   # 1 hour
SEARCH_TTL = 1800   # 30 min


def _cached_stream(url: str) -> tuple[str, int] | None:
    entry = _stream_cache.get(url)
    if entry and time.monotonic() < entry[2]:
        return entry[0], entry[1]
    _stream_cache.pop(url, None)
    return None


def _cache_stream(url: str, stream_url: str, dur: int):
    _stream_cache[url] = (stream_url, dur, time.monotonic() + STREAM_TTL)


def _cached_search(q: str) -> dict | None:
    entry = _search_cache.get(q)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    _search_cache.pop(q, None)
    return None


def _cache_search(q: str, info: dict):
    _search_cache[q] = (info, time.monotonic() + SEARCH_TTL)


# ── Cookie setup ──────────────────────────────────────────────────
def _get_cookie_file() -> str | None:
    # 1. Local file (VPS/dev)
    local = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cookies", "youtube.txt"
    )
    if os.path.isfile(local):
        log.info(f"🍪 Cookies: local file {local}")
        return local

    # 2. Heroku env var
    raw = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if raw:
        try:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix="yt_cookies_"
            )
            if not raw.startswith("# Netscape HTTP Cookie File"):
                tmp.write("# Netscape HTTP Cookie File\n\n")
            tmp.write(raw)
            tmp.flush()
            tmp.close()
            log.info(f"🍪 Cookies: env var → {tmp.name}")
            return tmp.name
        except Exception as e:
            log.error(f"Cookie file write failed: {e}")

    log.warning("⚠️  No cookies found — YouTube may block requests")
    return None


_COOKIE_FILE: str | None = _get_cookie_file()


# ── yt-dlp options ────────────────────────────────────────────────
def _opts(audio_only: bool = True) -> dict:
    o: dict = {
        "format":                       "bestaudio/best" if audio_only else "bestvideo+bestaudio/best",
        "quiet":                        True,
        "no_warnings":                  True,
        "noplaylist":                   True,
        "socket_timeout":               15,
        "retries":                      5,
        "fragment_retries":             5,
        "extractor_retries":            5,
        "concurrent_fragment_downloads": 4,
    }
    if _COOKIE_FILE:
        o["cookiefile"] = _COOKIE_FILE
    else:
        raise RuntimeError("YOUTUBE_COOKIES not set — cookies required")
    return o


# ── Sync extractors (run in thread pool) ─────────────────────────
def _extract_sync(url: str, audio_only: bool = True) -> dict | None:
    try:
        with yt_dlp.YoutubeDL(_opts(audio_only)) as ydl:
            info = ydl.extract_info(url, download=False)
            return info or None
    except Exception as e:
        log.error(f"yt-dlp extract error: {e}")
        return None


def _search_sync(query: str, audio_only: bool = True) -> dict | None:
    if query.startswith("http://") or query.startswith("https://"):
        return _extract_sync(query, audio_only)
    try:
        with yt_dlp.YoutubeDL(_opts(audio_only)) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if info and "entries" in info and info["entries"]:
                return info["entries"][0]
            return info or None
    except Exception as e:
        log.error(f"yt-dlp search error: {e}")
        return None


# ── Public async API ──────────────────────────────────────────────
async def search_song(query: str, is_video: bool = False) -> dict | None:
    cached = _cached_search(query)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(_exec, _search_sync, query, not is_video)
    if not info:
        return None

    # Pull best stream URL
    stream_url = (
        info.get("url")
        or info.get("manifest_url")
        or ""
    )
    if not stream_url and "formats" in info:
        fmts = info["formats"]
        if not is_video:
            af = [f for f in fmts if f.get("acodec") != "none" and f.get("vcodec") == "none"]
            stream_url = (af[-1] if af else (fmts[-1] if fmts else {})).get("url", "")
        else:
            stream_url = fmts[-1].get("url", "") if fmts else ""

    result = {
        "title":       info.get("title", query)[:100],
        "url":         stream_url,
        "duration":    info.get("duration", 0) or 0,
        "thumbnail":   info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or info.get("original_url", ""),
    }
    _cache_search(query, result)
    return result


async def get_stream(url: str, is_video: bool = False) -> tuple[str, int]:
    cached = _cached_stream(url)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(_exec, _extract_sync, url, not is_video)
    if not info:
        raise Exception(f"Stream resolve nahi hua: {url}")

    stream_url = info.get("url") or info.get("manifest_url") or ""
    if not stream_url and "formats" in info:
        fmts = info["formats"]
        if not is_video:
            af = [f for f in fmts if f.get("acodec") != "none" and f.get("vcodec") == "none"]
            stream_url = (af[-1] if af else (fmts[-1] if fmts else {})).get("url", "")
        else:
            stream_url = fmts[-1].get("url", "") if fmts else ""

    dur = info.get("duration", 0) or 0
    if stream_url:
        _cache_stream(url, stream_url, dur)
    return stream_url, dur


def fmt_duration(secs: int) -> str:
    if not secs or secs <= 0:
        return "LIVE"
    h, r = divmod(int(secs), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
