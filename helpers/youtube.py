"""
YouTube search and stream resolution.

Cookies are optional. They can help with age-restricted videos, but making them
mandatory breaks normal playback and turns a missing optional setting into a
misleading "token" error.
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
# tuple: (media_url, audio_url, duration, http_headers, expires_at)
_stream_cache: dict[tuple[str, bool], tuple[str, str | None, int, dict, float]] = {}
_search_cache: dict[tuple[str, bool], tuple[dict, float]] = {}
# YouTube CDN URLs are signed and should not be kept for a full hour.
STREAM_TTL = 900
SEARCH_TTL = 1800


def _stream_key(url: str, is_video: bool) -> tuple[str, bool]:
    return url.strip(), is_video


def _cached_stream(
    url: str,
    is_video: bool,
) -> tuple[str, str | None, int, dict] | None:
    e = _stream_cache.get(_stream_key(url, is_video))
    if e and time.monotonic() < e[4]:
        return e[0], e[1], e[2], e[3]
    _stream_cache.pop(_stream_key(url, is_video), None)
    return None


def _cache_stream(
    url: str,
    is_video: bool,
    su: str,
    audio_url: str | None,
    dur: int,
    headers: dict | None = None,
):
    _stream_cache[_stream_key(url, is_video)] = (
        su,
        audio_url,
        dur,
        headers or {},
        time.monotonic() + STREAM_TTL,
    )


def _cached_search(q: str, is_video: bool) -> dict | None:
    e = _search_cache.get((q.strip().lower(), is_video))
    if e and time.monotonic() < e[1]:
        return e[0]
    _search_cache.pop((q.strip().lower(), is_video), None)
    return None


def _cache_search(q: str, is_video: bool, info: dict):
    _search_cache[(q.strip().lower(), is_video)] = (
        info,
        time.monotonic() + SEARCH_TTL,
    )


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

    log.info("No YouTube cookies configured; using public extraction")
    _COOKIE_FILE = None
    return None


# ── yt-dlp options ───────────────────────────────────────────────
def _opts(
    audio_only: bool = True,
    fmt: str | None = None,
    player_client: list | None = None,
    skip_cookies: bool = False,
) -> dict:
    # skip_cookies=True → mobile client attempts (mobile clients don't use
    # browser session cookies — mixing them causes auth conflicts on YouTube).
    cookie = None if skip_cookies else _resolve_cookie_file()

    default_fmt = (
        "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"
        if audio_only
        else "best[height<=720][vcodec!=none][acodec!=none]/best[height<=480]/best"
    )
    clients = player_client or ["ios", "android", "mweb", "web"]
    opts: dict = {
        "format":         fmt or default_fmt,
        "quiet":          True,
        "no_warnings":    True,
        "noplaylist":     True,
        "geo_bypass":     True,
        "extractor_args": {
            "youtube": {
                "player_client": clients,
            }
        },
        "http_headers":   {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.youtube.com/",
        },
    }
    if cookie:
        opts["cookiefile"] = cookie
    return opts


# ── Sync extractors ───────────────────────────────────────────────
def _pick_urls(info: dict, audio_only: bool) -> tuple[str, str | None]:
    """Extract media and optional separate audio URLs from yt-dlp output."""
    fmts = info.get("formats") or []
    requested = info.get("requested_formats") or []

    if audio_only:
        # Do not accidentally return a combined video URL for /play.
        # Prefer audio-only streams sorted by bitrate
        af = [f for f in fmts if f.get("acodec") != "none" and f.get("vcodec") == "none"]
        if af:
            return (
                max(af, key=lambda f: f.get("abr") or f.get("tbr") or 0).get("url", ""),
                None,
            )
    else:
        # yt-dlp returns requested_formats for bestvideo+bestaudio. PyTgCalls
        # can consume those as media_path + audio_path and FFmpeg combines
        # them while preserving the signed request headers.
        if requested:
            video = next(
                (f for f in requested if f.get("vcodec") != "none" and f.get("url")),
                None,
            )
            audio = next(
                (f for f in requested if f.get("acodec") != "none" and f.get("url")),
                None,
            )
            if video and audio:
                return video["url"], audio["url"]

        # If only progressive formats are available, use one URL.
        av = [
            f for f in fmts
            if f.get("acodec") != "none" and f.get("vcodec") != "none"
        ]
        if av:
            best = max(
                av,
                key=lambda f: (
                    f.get("height") or 0,
                    f.get("fps") or 0,
                    f.get("tbr") or 0,
                ),
            )
            return best.get("url", ""), None

    # Direct extraction results do not always include a formats list.
    url = info.get("url") or info.get("manifest_url") or ""
    if url and (
        audio_only
        or (info.get("acodec", "none") != "none" and info.get("vcodec", "none") != "none")
    ):
        return url, None
    best = sorted(fmts, key=lambda f: f.get("quality") or f.get("tbr") or 0, reverse=True)
    return (best[0].get("url", ""), None) if best else ("", None)


def _pick_url(info: dict, audio_only: bool) -> str:
    """Compatibility helper for search metadata."""
    return _pick_urls(info, audio_only)[0]


def _extract_sync(url: str, audio_only: bool = True) -> dict | None:
    """Try (format, clients, skip_cookies) combos in priority order.

    Key insight:
    - Browser cookies are for YouTube WEB session → use with ["web"] client only.
    - Mobile clients (ios/android/mweb) authenticate differently — mixing cookies
      with them confuses YouTube and makes ALL formats appear unavailable.
    - "ba/b" is yt-dlp shorthand (best-audio / best) — no ext filter, so it
      accepts whatever codec the client returns rather than demanding m4a/webm.
    """
    cookie = _resolve_cookie_file()

    if audio_only:
        combos: list[tuple[str, list, bool]] = []
        # Step 1: cookies + web client (if cookies available)
        if cookie:
            combos += [
                ("ba/b",         ["web"], False),   # permissive shorthand
                ("bestaudio/best", ["web"], False),
            ]
        # Step 2: mobile clients WITHOUT cookies (they bypass datacenter blocks)
        combos += [
            ("ba/b",                                           ["ios"],            True),
            ("ba/b",                                           ["android"],        True),
            ("ba/b",                                           ["mweb"],           True),
            ("bestaudio/best",                                 ["ios", "android"], True),
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio", ["ios", "android", "mweb"], True),
            # Step 3: last resort — any client, any format
            ("ba/b",  ["ios", "android", "mweb", "web"], cookie is None),
            ("best",  ["ios", "android", "mweb", "web"], cookie is None),
        ]
    else:
        cookie_combos: list[tuple[str, list, bool]] = ([
            ("bestvideo[height<=720]+bestaudio/best[height<=720]/best", ["web"], False),
        ] if cookie else [])
        combos = cookie_combos + [
            ("bestvideo[height<=720]+bestaudio/best[height<=720]/best", ["ios", "android", "mweb"], True),
            ("bestvideo[height<=480]+bestaudio/best[height<=480]/best", ["ios", "android", "mweb"], True),
            ("best[height<=720]/best",                                  ["ios", "android", "mweb", "web"], cookie is None),
            ("best",                                                     ["ios", "android", "mweb", "web"], cookie is None),
        ]

    _RETRYABLE = (
        "Requested format is not available",
        "format is not available",
        "No video formats found",
        "Sign in to confirm",
        "This video is not available",
        "HTTP Error 403",
        "HTTP Error 429",
    )

    for fmt, clients, skip_ck in combos:
        try:
            opts = _opts(audio_only, fmt=fmt, player_client=clients, skip_cookies=skip_ck)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    log.debug(f"yt-dlp fmt={fmt!r} clients={clients} skip_ck={skip_ck} OK: {url[:55]}")
                    return info
        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            if any(r in err for r in _RETRYABLE):
                log.warning(f"Format {fmt!r} clients={clients} not available, retrying with next…")
                continue
            log.error(f"yt-dlp download error: {e}")
            return None
        except RuntimeError:
            raise
        except Exception as e:
            log.error(f"yt-dlp error: {e}")
            return None
    log.error(f"All formats exhausted for {url[:60]}")
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
    cached = _cached_search(query, is_video)
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
        _cache_stream(result["webpage_url"], is_video, result["url"], None, result["duration"], http_headers)
    _cache_search(query, is_video, result)
    return result


async def get_stream(
    url: str,
    is_video: bool = False,
    force_refresh: bool = False,
) -> tuple[str, str | None, int, dict]:
    """
    Get direct stream URL for playback.
    Returns (media_url, optional_audio_url, duration_secs, http_headers).

    BUG FIX: ab 3-tuple return karta hai — headers bhi milte hain
    taaki MediaStream ko pass kar sakein aur YouTube 403 se bache.
    """
    cached = None if force_refresh else _cached_stream(url, is_video)
    if cached:
        return cached

    # BUG FIX: get_running_loop() — Python 3.10+ compatible
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(_exec, _extract_sync, url, not is_video)
    if not info:
        raise Exception(f"❌ Stream resolve nahi hua: {url[:60]}")

    su, audio_url = _pick_urls(info, not is_video)
    dur     = info.get("duration", 0) or 0
    headers = info.get("http_headers") or {}

    if not su:
        raise Exception(f"❌ Stream URL empty hai: {url[:60]}")

    _cache_stream(url, is_video, su, audio_url, dur, headers)
    return su, audio_url, dur, headers


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
