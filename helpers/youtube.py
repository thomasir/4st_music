"""
youtube.py — v5.1 ULTRA-FAST
✅ search_song() — returns dict with title, url, duration, thumbnail, webpage_url
✅ get_stream() — returns (stream_url, duration)
✅ Link pass karo ya naam — dono kaam karega
✅ 16-worker thread pool, aggressive caching, multi-client rotation
✅ socket_timeout=3, concurrent=True for faster extraction
"""

import os
import yt_dlp
import asyncio
import logging
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("ApexBot.youtube")

_exec = ThreadPoolExecutor(max_workers=16)

# ── Cookie setup ──────────────────────────────────────────────────
_COOKIE_FILE: str | None = None

def _setup_cookies() -> str | None:
    local_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cookies", "youtube.txt"
    )
    if os.path.isfile(local_path):
        log.info(f"🍪 Cookies from LOCAL: {local_path}")
        return local_path

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
            log.info(f"🍪 Cookies from ENV: {tmp.name}")
            return tmp.name
        except Exception as e:
            log.error(f"Cookie setup failed: {e}")
    return None

_COOKIE_FILE = _setup_cookies()

# ── Client rotation ───────────────────────────────────────────────
_AUTH_ERRORS = (
    "please sign in", "sign in to confirm",
    "no video formats found", "format is not available",
    "http error 403", "age", "blocked",
    "requested format is not available",
)

def _is_retriable(err: str) -> bool:
    return any(k in err.lower() for k in _AUTH_ERRORS)

# Fast clients first — ios and android_vr are fastest
_CLIENT_ROTATION = [
    (["ios"],         True),
    (["android_vr"],  True),
    (["android"],     True),
    (["web_creator"], True),
    (["tv_embedded"], True),
    (["android_vr"],  False),
    (["mweb"],        False),
]

# ── Stream cache (10h TTL) + search cache (30min TTL) ────────────
_stream_cache: dict[str, tuple[str, int, float]] = {}
_search_cache: dict[str, tuple[dict, float]]     = {}
STREAM_CACHE_TTL = 36000   # 10 hours
SEARCH_CACHE_TTL = 1800    # 30 minutes


def _cached_stream(url: str) -> tuple[str, int] | None:
    if url in _stream_cache:
        stream_url, duration, expires = _stream_cache[url]
        if time.monotonic() < expires:
            return stream_url, duration
        del _stream_cache[url]
    return None


def _cache_stream(url: str, stream_url: str, duration: int):
    _stream_cache[url] = (stream_url, duration, time.monotonic() + STREAM_CACHE_TTL)


def _cached_search(query: str) -> dict | None:
    if query in _search_cache:
        info, expires = _search_cache[query]
        if time.monotonic() < expires:
            return info
        del _search_cache[query]
    return None


def _cache_search(query: str, info: dict):
    _search_cache[query] = (info, time.monotonic() + SEARCH_CACHE_TTL)


# ── yt-dlp extract (sync, runs in thread) ─────────────────────────

def _ydl_opts(clients: list, use_cookies: bool, audio_only: bool = True) -> dict:
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best" if audio_only else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 3,
        "noplaylist": True,
        "concurrent_fragment_downloads": 4,
        "extractor_args": {"youtube": {"player_client": clients}},
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    }
    if use_cookies and _COOKIE_FILE:
        opts["cookiefile"] = _COOKIE_FILE
    return opts


def _extract_sync(url: str, audio_only: bool = True) -> dict | None:
    """Try all client rotations, return info dict on success."""
    for clients, use_cookies in _CLIENT_ROTATION:
        try:
            opts = _ydl_opts(clients, use_cookies, audio_only)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return info
        except Exception as e:
            err = str(e)
            if _is_retriable(err):
                continue
            log.debug(f"yt-dlp [{clients}]: {err}")
    return None


def _search_sync(query: str, audio_only: bool = True) -> dict | None:
    """Search YouTube for a query, return first result info."""
    # If it's already a URL, extract directly
    if query.startswith("http://") or query.startswith("https://"):
        return _extract_sync(query, audio_only)

    search_url = f"ytsearch1:{query}"
    for clients, use_cookies in _CLIENT_ROTATION:
        try:
            opts = _ydl_opts(clients, use_cookies, audio_only)
            opts["default_search"] = "ytsearch"
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(search_url, download=False)
                if info and "entries" in info and info["entries"]:
                    return info["entries"][0]
                elif info and info.get("url"):
                    return info
        except Exception as e:
            err = str(e)
            if _is_retriable(err):
                continue
            log.debug(f"search [{clients}]: {err}")
    return None


# ── Public async API ──────────────────────────────────────────────

async def search_song(query: str, is_video: bool = False) -> dict | None:
    """
    Returns dict: {title, url, duration, thumbnail, webpage_url}
    'url' is the direct stream URL, 'webpage_url' is the YouTube page URL.
    Uses 30-min search cache for repeated queries.
    """
    cache_key = f"{'v' if is_video else 'a'}:{query}"
    cached = _cached_search(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(_exec, _search_sync, query, not is_video)
    if not info:
        return None

    # Get best stream URL
    stream_url = info.get("url") or info.get("manifest_url") or ""
    if not stream_url and "formats" in info:
        fmts = info["formats"]
        if not is_video:
            audio_fmts = [f for f in fmts if f.get("acodec") != "none" and f.get("vcodec") == "none"]
            if audio_fmts:
                stream_url = audio_fmts[-1].get("url", "")
        if not stream_url:
            stream_url = fmts[-1].get("url", "") if fmts else ""

    result = {
        "title":       info.get("title", query)[:100],
        "url":         stream_url,
        "duration":    info.get("duration", 0) or 0,
        "thumbnail":   info.get("thumbnail", None),
        "webpage_url": info.get("webpage_url", info.get("original_url", "")),
    }
    _cache_search(cache_key, result)
    return result


async def get_stream(url: str, is_video: bool = False) -> tuple[str, int]:
    """
    Given a URL (webpage or stream), return (stream_url, duration).
    Uses 10h cache to avoid re-fetching.
    """
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
            audio_fmts = [f for f in fmts if f.get("acodec") != "none" and f.get("vcodec") == "none"]
            if audio_fmts:
                stream_url = audio_fmts[-1].get("url", "")
        if not stream_url:
            stream_url = fmts[-1].get("url", "") if fmts else ""

    duration = info.get("duration", 0) or 0
    if stream_url:
        _cache_stream(url, stream_url, duration)
    return stream_url, duration


def fmt_duration(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "LIVE"
    h, rem = divmod(int(seconds), 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
