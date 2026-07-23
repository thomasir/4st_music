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

    log.warning(
        "⚠️  No YouTube cookies found! Heroku/cloud IPs need cookies to stream YouTube. "
        "Set YOUTUBE_COOKIES env var in Heroku dashboard (Netscape format). "
        "Export from Chrome: F12 → Application → Cookies, or use a browser extension like 'Get cookies.txt'."
    )
    _COOKIE_FILE = None
    return None


# ── yt-dlp options ───────────────────────────────────────────────
def _opts(
    audio_only: bool = True,
    fmt: str | None = None,
    player_client: list | None = None,
    skip_cookies: bool = False,
    ignore_no_formats: bool = False,
    skip_webpage: bool = False,
) -> dict:
    # skip_cookies=True → mobile client attempts (mobile clients don't use
    # browser session cookies — mixing them causes auth conflicts on YouTube).
    cookie = None if skip_cookies else _resolve_cookie_file()

    default_fmt = (
        "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"
        if audio_only
        else "best[height<=720][vcodec!=none][acodec!=none]/best[height<=480]/best"
    )
    clients = player_client or ["tv_embedded", "ios", "android", "mweb"]
    extractor_args: dict = {
        "player_client": clients,
    }
    # skip_webpage=True: skip JS player extraction entirely.
    # Cloud/Heroku IPs often fail JS player extraction → "Requested format is not available".
    # tv_embedded + skip_webpage is the most reliable combo on restricted IPs.
    if skip_webpage:
        extractor_args["skip"] = ["webpage", "configs", "js"]

    opts: dict = {
        "format":                   fmt if fmt is not None else default_fmt,
        "quiet":                    True,
        "no_warnings":              True,
        "noplaylist":               True,
        "geo_bypass":               True,
        "check_formats":            False,   # don't pre-verify URL reachability
        "allow_unplayable_formats": False,
        # socket_timeout: bina iske yt-dlp cloud IPs pe indefinitely hang karta tha.
        # 20s per attempt reasonable hai; combos ka loop overall timeout control karta hai.
        "socket_timeout":           20,
        "extractor_args": {
            "youtube": extractor_args,
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.youtube.com/",
        },
    }
    if ignore_no_formats:
        opts["ignore_no_formats_error"] = True
        opts["allow_unplayable_formats"] = True
    if cookie:
        opts["cookiefile"] = cookie
    return opts


# ── URL validation ────────────────────────────────────────────────
def _is_streamable_url(url: str) -> bool:
    """
    Return True only if 'url' is a direct CDN media URL that ffmpeg/ntgcalls
    can actually pipe.

    fmt=None + ignore_no_formats sometimes returns:
      - youtube.com/watch?v=... (HTML page → 0 bytes → ntgcalls EOF)
      - youtu.be/... (redirect, not media)
      - HLS .m3u8 manifests (ntgcalls shell_reader can't follow segments)
      - DASH .mpd manifests (same problem)

    All of the above cause "Reached end of the file" in shell_reader.cpp
    and the bot leaving VC within 1 second of joining.
    """
    if not url:
        return False
    bad = (
        "youtube.com/watch",
        "youtu.be/",
        "youtube.com/shorts",
        "youtube.com/embed",
        ".m3u8",
        ".mpd",
    )
    if any(b in url for b in bad):
        return False
    # Real YouTube audio/video CDN URLs always contain googlevideo.com
    # or the videoplayback path. Accept those; reject everything else.
    good = ("googlevideo.com", "videoplayback")
    return any(g in url for g in good)


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
    # NEVER return manifest_url here — ntgcalls shell_reader can't follow
    # HLS/DASH segment manifests and immediately hits EOF ("Reached end of file").
    url = info.get("url") or ""
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
    """Try (format, clients) combos in priority order — always with cookies.

    When a cloud/Heroku IP is flagged by YouTube, ALL clients (web + mobile)
    return "Sign in to confirm". yt-dlp extracts visitor_data + auth tokens
    from the cookiefile and injects them into mobile API calls too — so
    always pass cookies. Never skip them.

    "ba/b" = yt-dlp shorthand: best-audio / best — no ext filter, accepts
    any codec the client returns (more permissive than [ext=m4a]).
    """
    cookie = _resolve_cookie_file()
    log.info(f"🍪 Cookie status: {'loaded ✅' if cookie else 'NOT SET ❌ (set YOUTUBE_COOKIES env var!)'}")

    # fmt=None means "let yt-dlp decide — no restriction"
    # NOTE: fmt=None + ignore_no_formats combos often return storyboard thumbnail
    # URLs (i.ytimg.com) on cloud/Heroku IPs. _is_streamable_url() rejects those.
    #
    # Combo tuple: (format_selector, player_clients, ignore_no_formats, skip_webpage)
    # skip_webpage=True: skips JS player extraction entirely — most reliable on Heroku/cloud IPs.
    # tv_embedded + skip_webpage is the #1 fix for "Requested format is not available" on cloud IPs.
    if audio_only:
        combos: list[tuple[str | None, list, bool, bool]] = [
            # Best combos for cloud/Heroku IPs — tv_embedded bypasses most restrictions
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["tv_embedded"],                    False, True),
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["tv_embedded"],                    False, False),
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["ios"],                             False, True),
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["ios"],                             False, False),
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["android"],                        False, True),
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["android"],                        False, False),
            # sabr client — YouTube's Streaming ABR, designed to bypass IP-level restrictions
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["sabr"],                           False, False),
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["sabr", "tv_embedded"],            False, False),
            # Broader client combos
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["tv_embedded", "ios", "android"],  False, True),
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["mweb"],                           False, False),
            ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", ["web"],                            False, False),
            # Last resort — only accept if _is_streamable_url validates the CDN URL
            (None,                                                     ["tv_embedded"],                    True,  True),
            (None,                                                     ["ios"],                            True,  True),
            (None,                                                     ["android"],                        True,  False),
            (None,                                                     ["tv_embedded", "ios", "android", "mweb"], True, False),
        ]
    else:
        combos = [
            ("best[height<=720][vcodec!=none][acodec!=none]/best[height<=720]/best", ["tv_embedded"],                      False, True),
            ("best[height<=720][vcodec!=none][acodec!=none]/best[height<=720]/best", ["tv_embedded"],                      False, False),
            ("best[height<=720][vcodec!=none][acodec!=none]/best[height<=720]/best", ["ios", "android"],                   False, True),
            ("best[height<=720][vcodec!=none][acodec!=none]/best[height<=720]/best", ["ios", "android"],                   False, False),
            ("best[height<=480][vcodec!=none][acodec!=none]/best[height<=480]/best", ["ios", "android", "mweb"],           False, False),
            ("best[height<=720]/best",                                               ["tv_embedded", "ios", "android"],    False, True),
            ("best[height<=720]/best",                                               ["sabr"],                             False, False),
            (None,                                                                   ["tv_embedded", "ios"],               True,  True),
            (None,                                                                   ["tv_embedded", "ios", "android"],    True,  False),
        ]

    _RETRYABLE = (
        "Requested format is not available",
        "format is not available",
        "No video formats found",
        "Sign in to confirm",
        "This video is not available",
        "HTTP Error 403",
        "HTTP Error 429",
        "requires payment",
        "members-only",
    )

    for fmt, clients, ignore_no_fmt, skip_wp in combos:
        try:
            opts = _opts(
                audio_only,
                fmt=fmt,
                player_client=clients,
                skip_cookies=False,
                ignore_no_formats=ignore_no_fmt,
                skip_webpage=skip_wp,
            )
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    # Collect all candidate URLs (never manifest_url — ntgcalls
                    # shell_reader can't follow HLS/DASH segments and hits EOF).
                    candidate_urls = [
                        u for u in (
                            [info.get("url")]
                            + [f.get("url") for f in (info.get("formats") or [])]
                        ) if u
                    ]
                    url_ok = bool(candidate_urls)

                    if url_ok and ignore_no_fmt:
                        # fmt=None last-resort combos sometimes return HTML
                        # redirects (youtube.com/watch) or manifest URLs —
                        # these cause ntgcalls "Reached end of the file" and
                        # the bot leaving VC in 1 second.
                        # Only accept if at least one URL is a real CDN URL.
                        cdn_urls = [u for u in candidate_urls if _is_streamable_url(u)]
                        if not cdn_urls:
                            log.warning(
                                f"fmt=None returned no CDN URL (got: {candidate_urls[0][:80]!r}) "
                                f"— skipping clients={clients}"
                            )
                            continue   # try next combo

                    if url_ok:
                        log.info(f"✅ yt-dlp OK | fmt={fmt!r} clients={clients} | {url[:55]}")
                        return info
                    log.warning(f"yt-dlp returned info but no URL | fmt={fmt!r} clients={clients}")
        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            if any(r in err for r in _RETRYABLE):
                log.warning(f"Retrying: fmt={fmt!r} clients={clients} — {err[:80]}")
                continue
            log.error(f"yt-dlp fatal error: {e}")
            return None
        except RuntimeError:
            raise
        except Exception as e:
            log.error(f"yt-dlp unexpected error: {e}")
            return None

    log.error(f"❌ All formats exhausted for {url[:60]}")
    if not cookie:
        log.error(
            "➡️  FIX: Export YouTube cookies from Chrome/Firefox (Netscape format) "
            "and set as YOUTUBE_COOKIES env var in Heroku dashboard → Settings → Config Vars."
        )
    else:
        log.error(
            "➡️  Cookies are set but YouTube is still blocking this IP. "
            "Try refreshing cookies (re-export from browser while logged into YouTube)."
        )
    return None


def _search_sync(query: str, audio_only: bool = True) -> dict | None:
    if query.startswith("http://") or query.startswith("https://"):
        return _extract_sync(query, audio_only)

    # ── Fast path: extract_flat search (just metadata, no stream URL) ──────
    # FIX: noplaylist=False is REQUIRED here.
    # _opts() sets noplaylist=True (correct for direct video URLs), but
    # ytsearch1: returns a "SearchResultsPlaylist" internally. With
    # noplaylist=True, yt-dlp 2025.x refuses to process it and returns
    # nothing — causing silent "Nahi mila" errors with no log entry.
    try:
        search_opts = {
            **_opts(audio_only, player_client=["tv_embedded", "ios", "android"]),
            "extract_flat": "in_playlist",
            "check_formats": False,
            "noplaylist":    False,   # CRITICAL FIX: allow ytsearch playlist processing
        }
        with yt_dlp.YoutubeDL(search_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if info and "entries" in info and info["entries"]:
                entry = info["entries"][0]
                # Ensure webpage_url is set so _do_play_inner can fetch stream later
                if entry.get("url") and not entry.get("webpage_url"):
                    entry["webpage_url"] = entry["url"]
                vid_id = entry.get("id", "")
                if not entry.get("webpage_url") and vid_id:
                    entry["webpage_url"] = f"https://www.youtube.com/watch?v={vid_id}"
                log.info(f"✅ Search OK (flat): {entry.get('title', query)[:50]!r}")
                return entry
            log.warning(f"⚠️  extract_flat returned no entries for: {query[:50]!r}")
    except yt_dlp.utils.DownloadError as e:
        log.error(f"yt-dlp flat-search error: {e}")
    except Exception as e:
        log.error(f"yt-dlp flat-search error: {e}")

    # ── Fallback: full extraction search (slower but more reliable) ─────────
    # Used when extract_flat returns nothing (e.g. regional blocks, sign-in walls).
    log.info(f"🔄 Trying full-extraction fallback search for: {query[:50]!r}")
    try:
        fallback_opts = {
            **_opts(audio_only, player_client=["ios", "tv_embedded", "android"]),
            "noplaylist": False,   # same fix applies here
        }
        with yt_dlp.YoutubeDL(fallback_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if info and "entries" in info and info["entries"]:
                entry = info["entries"][0]
                vid_id = entry.get("id", "")
                if entry.get("url") and not entry.get("webpage_url"):
                    entry["webpage_url"] = entry["url"]
                if not entry.get("webpage_url") and vid_id:
                    entry["webpage_url"] = f"https://www.youtube.com/watch?v={vid_id}"
                log.info(f"✅ Search OK (fallback): {entry.get('title', query)[:50]!r}")
                return entry
            # Last resort: info itself might be the video entry
            if info and info.get("id"):
                return info
    except yt_dlp.utils.DownloadError as e:
        log.error(f"yt-dlp fallback-search error: {e}")
    except Exception as e:
        log.error(f"yt-dlp fallback-search error: {e}")

    log.error(f"❌ All search methods failed for: {query[:60]!r}")
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
