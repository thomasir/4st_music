"""
youtube.py — cookies only, no fallbacks
"""

import os
import yt_dlp
import asyncio
import logging
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("ApexBot.youtube")
_exec = ThreadPoolExecutor(max_workers=4)

# ── Cache ─────────────────────────────────────────────────────────
_stream_cache: dict[str, tuple[str, int, float]] = {}
_search_cache: dict[str, tuple[dict, float]]     = {}
STREAM_TTL = 3600
SEARCH_TTL = 1800


def _cached_stream(url: str) -> tuple[str, int] | None:
    e = _stream_cache.get(url)
    if e and time.monotonic() < e[2]:
        return e[0], e[1]
    _stream_cache.pop(url, None)
    return None


def _cache_stream(url: str, su: str, dur: int):
    _stream_cache[url] = (su, dur, time.monotonic() + STREAM_TTL)


def _cached_search(q: str) -> dict | None:
    e = _search_cache.get(q)
    if e and time.monotonic() < e[1]:
        return e[0]
    _search_cache.pop(q, None)
    return None


def _cache_search(q: str, info: dict):
    _search_cache[q] = (info, time.monotonic() + SEARCH_TTL)


# ── Cookie setup ──────────────────────────────────────────────────
def _get_cookie_file() -> str:
    local = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cookies", "youtube.txt"
    )
    if os.path.isfile(local):
        log.info(f"🍪 Cookies: {local}")
        return local

    raw = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if not raw:
        raise RuntimeError("YOUTUBE_COOKIES env var not set!")

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="yt_cookies_"
    )
    if not raw.startswith("# Netscape HTTP Cookie File"):
        tmp.write("# Netscape HTTP Cookie File\n\n")
    tmp.write(raw)
    tmp.flush()
    tmp.close()
    log.info(f"🍪 Cookies from env → {tmp.name}")
    return tmp.name


_COOKIE_FILE: str = _get_cookie_file()


# ── yt-dlp options — minimal, cookies only ───────────────────────
def _opts(audio_only: bool = True) -> dict:
    return {
        # "best" always matches — pytgcalls FFmpeg handles audio extraction
        # "bestaudio/best" fails on some videos (SABR/DASH only streams)
        "format":     "bestaudio/best" if audio_only else "best",
        "quiet":      True,
        "no_warnings": True,
        "noplaylist": True,
        "cookiefile": _COOKIE_FILE,
    }


# ── Sync extractors ───────────────────────────────────────────────
def _pick_url(info: dict, audio_only: bool) -> str:
    """Extract best stream URL from info dict."""
    url = info.get("url") or info.get("manifest_url") or ""
    if url:
        return url
    fmts = info.get("formats") or []
    if audio_only:
        af = [f for f in fmts if f.get("acodec") != "none" and f.get("vcodec") == "none"]
        if af:
            return af[-1].get("url", "")
    return fmts[-1].get("url", "") if fmts else ""


def _extract_sync(url: str, audio_only: bool = True) -> dict | None:
    try:
        with yt_dlp.YoutubeDL(_opts(audio_only)) as ydl:
            return ydl.extract_info(url, download=False) or None
    except Exception as e:
        log.error(f"yt-dlp error: {e}")
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

    result = {
        "title":       info.get("title", query)[:100],
        "url":         _pick_url(info, not is_video),
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

    su  = _pick_url(info, not is_video)
    dur = info.get("duration", 0) or 0
    if su:
        _cache_stream(url, su, dur)
    return su, dur


def fmt_duration(secs: int) -> str:
    if not secs or secs <= 0:
        return "LIVE"
    h, r = divmod(int(secs), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
