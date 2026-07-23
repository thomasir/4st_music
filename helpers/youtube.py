"""
youtube.py — v6.1 (bug-fixed)
✅ FIXED: extractor_args DASH/HLS skip hataya — bestaudio ab kaam karega
✅ FIXED: asyncio.get_running_loop() (Python 3.10+ compatible)
✅ FIXED: http_headers stream cache + search result mein add kiye
✅ FIXED: get_stream() ab (url, dur, headers) return karta hai
✅ Lazy cookie loading — bot crash fix
"""

import os
import yt_dlp
import asyncio
import logging
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("ApexBot.youtube")
_exec = ThreadPoolExecutor(max_workers=6)

# ── Cache ─────────────────────────────────────────────────────────
# tuple: (stream_url, duration, http_headers, expires_at)
_stream_cache: dict[str, tuple[str, int, dict, float]] = {}
_search_cache: dict[str, tuple[dict, float]]           = {}
STREAM_TTL = 3600
SEARCH_TTL = 1800


def _cached_stream(url: str) -> tuple[str, int, dict] | None:
    e = _stream_cache.get(url)
    if e and time.monotonic() < e[3]:
        return e[0], e[1], e[2]
    _stream_cache.pop(url, None)
    return None


def _cache_stream(url: str, su: str, dur: int, headers: dict | None = None):
    _stream_cache[url] = (su, dur, headers or {}, time.monotonic() + STREAM_TTL)


def _cached_search(q: str) -> dict | None:
    e = _search_cache.get(q)
    if e and time.monotonic() < e[1]:
        return e[0]
    _search_cache.pop(q, None)
    return None


def _cache_search(q: str, info: dict):
    _search_cache[q] = (info, time.monotonic() + SEARCH_TTL)


# ── Cookie setup — LAZY (no crash at startup) ─────────────────────
_COOKIE_FILE: str | None = None
_COOKIE_CHECKED: bool = False


def _resolve_cookie_file() -> str | None:
    """Lazy cookie resolution — called on first use, not at import time."""
    global _COOKIE_FILE, _COOKIE_CHECKED
    if _COOKIE_CHECKED:
        return _COOKIE_FILE
    _COOKIE_CHECKED = True

    # 1. Local cookies/youtube.txt
    local = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cookies", "youtube.txt"
    )
    if os.path.isfile(local):
        log.info(f"🍪 Cookies loaded from file: {local}")
        _COOKIE_FILE = local
        return _COOKIE_FILE

    # 2. YOUTUBE_COOKIES env var
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
            log.info(f"🍪 Cookies from env → {tmp.name}")
            _COOKIE_FILE = tmp.name
            return _COOKIE_FILE
        except Exception as e:
            log.warning(f"Cookie env parse failed: {e}")

    log.warning("⚠️  No YOUTUBE_COOKIES found — using no-cookie mode (some videos may fail)")
    _COOKIE_FILE = None
    return None


# ── yt-dlp options ───────────────────────────────────────────────
def _opts(audio_only: bool = True) -> dict:
    cookie = _resolve_cookie_file()
    # FIX: bestaudio/best kuch videos pe "Requested format not available" deta tha.
    # Reason: age-restricted ya region-locked videos mein audio-only DASH streams
    # nahi hote. Long fallback chain use karo taaki koi na koi format mile.
    audio_fmt = (
        "bestaudio[ext=m4a]"
        "/bestaudio[ext=webm]"
        "/bestaudio[acodec!=none]"
        "/bestaudio"
        "/best[acodec!=none][height<=480]"
        "/best[height<=480]"
        "/best"
    )
    video_fmt = (
        "bestvideo[height<=1080]+bestaudio"
        "/best[height<=1080]"
        "/best[height<=720]"
        "/best"
    )
    opts: dict = {
        "format":      audio_fmt if audio_only else video_fmt,
        "quiet":       True,
        "no_warnings": True,
        "noplaylist":  True,
    }
    if cookie:
        opts["cookiefile"] = cookie
    return opts


# ── Sync extractors ───────────────────────────────────────────────
def _pick_url(info: dict, audio_only: bool) -> str:
    """Extract best stream URL from info dict."""
    url = info.get("url") or info.get("manifest_url") or ""
    if url:
        return url
    fmts = info.get("formats") or []
    if audio_only:
        # Prefer audio-only streams sorted by bitrate
        af = [f for f in fmts if f.get("acodec") != "none" and f.get("vcodec") == "none"]
        if af:
            return max(af, key=lambda f: f.get("abr") or f.get("tbr") or 0).get("url", "")
    # Fallback: best combined stream
    best = sorted(fmts, key=lambda f: f.get("quality") or f.get("tbr") or 0, reverse=True)
    return best[0].get("url", "") if best else ""


def _extract_sync(url: str, audio_only: bool = True) -> dict | None:
    try:
        with yt_dlp.YoutubeDL(_opts(audio_only)) as ydl:
            return ydl.extract_info(url, download=False) or None
    except yt_dlp.utils.DownloadError as e:
        log.error(f"yt-dlp download error: {e}")
        return None
    except Exception as e:
        log.error(f"yt-dlp error: {e}")
        return None


def _search_sync(query: str, audio_only: bool = True) -> dict | None:
    if query.startswith("http://") or query.startswith("https://"):
        return _extract_sync(query, audio_only)
    try:
        # BUG FIX: extract_flat=True — search ke time sirf metadata fetch karo.
        # Stream URL baad mein get_stream() fetch karega.
        # Bina flat ke yt-dlp full stream extraction karta hai jo YouTube
        # bots ke liye block kar deta hai (403/429) → None return hota tha.
        search_opts = {
            **_opts(audio_only),
            "extract_flat": True,
        }
        with yt_dlp.YoutubeDL(search_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if info and "entries" in info and info["entries"]:
                entry = info["entries"][0]
                # Flat entry ka url = YouTube watch page URL — yahi chahiye.
                # webpage_url set karo agar sirf url mile.
                if entry.get("url") and not entry.get("webpage_url"):
                    entry["webpage_url"] = entry["url"]
                return entry
            return info or None
    except yt_dlp.utils.DownloadError as e:
        log.error(f"yt-dlp search error: {e}")
        return None
    except Exception as e:
        log.error(f"yt-dlp search error: {e}")
        return None


# ── Public async API ──────────────────────────────────────────────

async def search_song(query: str, is_video: bool = False) -> dict | None:
    """Search for a song/video. Returns info dict or None."""
    cached = _cached_search(query)
    if cached:
        log.debug(f"Cache hit: {query[:40]}")
        return cached

    # BUG FIX: get_running_loop() use karo — get_event_loop() Python 3.10+ mein deprecated hai
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(_exec, _search_sync, query, not is_video)
    if not info:
        return None

    http_headers = info.get("http_headers") or {}

    # webpage_url: prefer explicit field, fallback to building from video ID
    vid_id = info.get("id", "")
    webpage_url = (
        info.get("webpage_url")
        or info.get("original_url")
        or (f"https://www.youtube.com/watch?v={vid_id}" if vid_id else "")
    )

    # stream url: only use if it looks like a real CDN URL (not a YouTube watch page)
    raw_url = _pick_url(info, not is_video)
    is_cdn_url = raw_url and "youtube.com/watch" not in raw_url and "youtu.be/" not in raw_url

    result = {
        "title":        info.get("title", query)[:100],
        "url":          raw_url if is_cdn_url else "",
        "duration":     info.get("duration", 0) or 0,
        "thumbnail":    info.get("thumbnail") or "",
        "webpage_url":  webpage_url,
        "uploader":     info.get("uploader") or info.get("channel") or "",
        "view_count":   info.get("view_count") or 0,
        "http_headers": http_headers,
    }

    # Cache stream URL only if it's a real CDN URL (not YouTube watch page)
    if result["webpage_url"] and is_cdn_url:
        _cache_stream(result["webpage_url"], result["url"], result["duration"], http_headers)
    _cache_search(query, result)
    return result


async def get_stream(url: str, is_video: bool = False) -> tuple[str, int, dict]:
    """
    Get direct stream URL for playback.
    Returns (stream_url, duration_secs, http_headers).

    BUG FIX: ab 3-tuple return karta hai — headers bhi milte hain
    taaki MediaStream ko pass kar sakein aur YouTube 403 se bache.
    """
    cached = _cached_stream(url)
    if cached:
        return cached  # (stream_url, dur, headers)

    # BUG FIX: get_running_loop() — Python 3.10+ compatible
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(_exec, _extract_sync, url, not is_video)
    if not info:
        raise Exception(f"❌ Stream resolve nahi hua: {url[:60]}")

    su      = _pick_url(info, not is_video)
    dur     = info.get("duration", 0) or 0
    headers = info.get("http_headers") or {}

    if not su:
        raise Exception(f"❌ Stream URL empty hai: {url[:60]}")

    _cache_stream(url, su, dur, headers)
    return su, dur, headers


def fmt_duration(secs: int) -> str:
    """Format seconds → M:SS or H:MM:SS or LIVE."""
    if not secs or secs <= 0:
        return "🔴 LIVE"
    h, r = divmod(int(secs), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def clear_cache():
    """Clear all caches (call after yt-dlp update)."""
    _stream_cache.clear()
    _search_cache.clear()
    log.info("🗑️ YouTube cache cleared")
