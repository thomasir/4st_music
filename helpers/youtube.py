"""
YouTube search and stream resolution.

Cookies are optional. They can help with age-restricted videos, but making them
mandatory breaks normal playback and turns a missing optional setting into a
misleading "token" error.
"""

import os
import re
import asyncio
import aiohttp
import logging
import time
import tempfile
import json
import shutil
import sys
import urllib.request
from urllib.parse import quote_plus, urljoin, urlsplit
from concurrent.futures import ThreadPoolExecutor

# The build hook installs the bgutil yt-dlp plugin under vendor/. Add that
# namespace before importing yt-dlp so plugin discovery also works when this
# module is imported outside the main process.
_BGUTIL_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "vendor", "bgutil-ytdlp-pot-provider", "plugin",
)
if os.path.isdir(_BGUTIL_PLUGIN_DIR) and _BGUTIL_PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _BGUTIL_PLUGIN_DIR)

import yt_dlp

log = logging.getLogger("ApexBot.youtube")
_exec = ThreadPoolExecutor(max_workers=16)   # ⚡ SPEED: 6→16 for true parallel downloads
_BGUTIL_STATUS_LOGGED = False

# ── Cloud-host CDN-block detection ───────────────────────────────
# On Heroku/Railway/Render/Fly.io the YouTube CDN (googlevideo.com) is
# IP-blocked. Trying to stream from a CDN URL always causes an immediate
# EOF and a 12-second silence before the retry. Detect cloud hosts at
# startup and skip CDN probing entirely — go straight to Invidious/download.
_ON_CLOUD_HOST: bool = bool(
    os.environ.get("DYNO")                  # Heroku
    or os.environ.get("RAILWAY_ENVIRONMENT")  # Railway
    or os.environ.get("RENDER_SERVICE_ID")    # Render
    or os.environ.get("FLY_APP_NAME")         # Fly.io
    or os.environ.get("K_SERVICE")            # Google Cloud Run
    or os.environ.get("WEBSITE_INSTANCE_ID")  # Azure App Service
)

# Runtime flag — flipped True on first premature stream end (CDN EOF).
# Starts True on known cloud hosts so the very first play skips CDN.
_cdn_blocked: bool = _ON_CLOUD_HOST


def mark_cdn_blocked() -> None:
    """Call when a CDN stream fails (premature end) so future plays skip CDN."""
    global _cdn_blocked
    if not _cdn_blocked:
        log.info(
            "🚫 CDN stream premature EOF — switching to Invidious/download-first "
            "mode for all future plays on this host."
        )
        _cdn_blocked = True

# ── Cache ─────────────────────────────────────────────────────────
# tuple: (media_url, audio_url, duration, http_headers, expires_at)
_stream_cache: dict[tuple[str, bool], tuple[str, str | None, int, dict, float]] = {}
_search_cache: dict[tuple[str, bool], tuple[dict, float]] = {}
_stream_tasks: dict[tuple[str, bool], asyncio.Task] = {}
# YouTube CDN URLs are signed and should not be kept for a full hour.
STREAM_TTL = 900
SEARCH_TTL = 1800


def _url_expiry_ttl(cdn_url: str, default_ttl: float = STREAM_TTL) -> float:
    """Parse expire= from a googlevideo CDN URL and return a safe cache TTL.

    YouTube CDN URLs carry an expire= Unix timestamp that can be much shorter
    than STREAM_TTL.  Using a fixed 900-s TTL lets stale (already-expired) URLs
    sit in the cache, causing ntgcalls shell_reader to hit EOF immediately and
    the bot to leave VC after ~1 second.
    """
    import re as _re
    m = _re.search(r"[?&]expire=(\d+)", cdn_url)
    if not m:
        return default_ttl
    expire_epoch = int(m.group(1))
    # Compare against wall-clock; cache itself uses monotonic time.
    ttl_from_url = expire_epoch - time.time() - 120  # 2-min safety buffer
    if ttl_from_url <= 0:
        return 0.0  # URL already expired — must not be cached
    return min(default_ttl, ttl_from_url)


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
    # Respect the URL's own expiry so we never serve an already-expired CDN URL.
    ttl = _url_expiry_ttl(su) if su else STREAM_TTL
    if ttl <= 0:
        log.debug("Skipping cache for expired/expiring CDN URL: %s", (su or "")[:80])
        return
    _stream_cache[_stream_key(url, is_video)] = (
        su,
        audio_url,
        dur,
        headers or {},
        time.monotonic() + ttl,
    )


def clear_cache_for_url(url: str, is_video: bool = False):
    """Remove a URL from the stream cache so the next play fetches a fresh URL."""
    _stream_cache.pop(_stream_key(url, is_video), None)
    _stream_cache.pop(_stream_key(url.strip(), is_video), None)


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

    # Do not force the old mobile clients here. YouTube now gates many of
    # their formats behind PO tokens, while current yt-dlp knows how to pick
    # the best compatible clients when "default" is used.
    default_fmt = (
        "bestaudio/best"
        if audio_only
        else "best[height<=720][vcodec!=none][acodec!=none]/best[height<=720]/best"
    )
    clients = player_client or ["default"]
    extractor_args: dict = {
        "player_client": clients,
    }
    provider_args: dict = {
        "youtube": extractor_args,
    }
    bgutil_server = _bgutil_server_home()
    bgutil_script = os.path.join(bgutil_server, "src", "generate_once.ts")
    if os.path.isfile(bgutil_script):
        provider_args["youtubepot-bgutilscript"] = {
            "server_home": [bgutil_server],
        }
        global _BGUTIL_STATUS_LOGGED
        if not _BGUTIL_STATUS_LOGGED:
            log.info("✅ bgutil PO-token provider configured: %s", bgutil_server)
            _BGUTIL_STATUS_LOGGED = True
    elif not _BGUTIL_STATUS_LOGGED:
        log.warning(
            "⚠️ bgutil PO-token provider is not installed at %s; "
            "YouTube cloud extraction will use built-in providers only",
            bgutil_server,
        )
        _BGUTIL_STATUS_LOGGED = True

    opts: dict = {
        "format":                   fmt if fmt is not None else default_fmt,
        "quiet":                    True,
        "no_warnings":              True,
        "noplaylist":               True,
        "geo_bypass":               True,
        "geo_bypass_country":       "US",    # spoof US location — helps with regional blocks
        "check_formats":            False,   # don't pre-verify URL reachability
        "allow_unplayable_formats": False,
        # socket_timeout: bina iske yt-dlp cloud IPs pe indefinitely hang karta tha.
        # 20s per attempt reasonable hai; combos ka loop overall timeout control karta hai.
        "socket_timeout":           6,   # SPEED FIX: fail-fast per combo; overall cap = wait_for() timeout
        # yt-dlp's YouTube extractor needs the external JS challenge solver.
        # The build hook installs Deno when the host does not provide it.
        "js_runtimes":              {"deno": {"path": _deno_path()}},
        "remote_components":         ["ejs:github"],
        "extractor_args":            provider_args,
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
    # YTDLP_PROXY: set in Heroku Config Vars to route yt-dlp through a proxy.
    # Validate the complete URL, not just its prefix. A value such as
    # ``socks5://host:1080socks5:`` starts with a valid scheme but makes the
    # requests backend fail with "Port could not be cast to integer".
    proxy = _proxy_from_environment()
    if proxy is not None:
        # An empty proxy explicitly disables inherited HTTP(S)_PROXY values.
        opts["proxy"] = proxy
    return opts


def _bgutil_server_home() -> str:
    """Return the build-bundled bgutil provider server directory."""
    configured_root = os.environ.get("YTDLP_BGUTIL_HOME", "").strip()
    if configured_root:
        configured_server = os.path.join(configured_root, "server")
        if os.path.isdir(configured_server):
            return configured_server
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "vendor", "bgutil-ytdlp-pot-provider", "server",
    )


def _deno_path() -> str:
    """Return the bundled/system Deno path used by yt-dlp EJS."""
    configured = os.environ.get("DENO_PATH", "").strip()
    if configured and os.path.isfile(configured):
        return configured

    bundled = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "vendor", "deno", "bin", "deno",
    )
    if os.path.isfile(bundled):
        return bundled

    return shutil.which("deno") or "deno"


def _valid_proxy_url(value: str) -> str | None:
    """Return a usable proxy URL, or None for a malformed value.

    yt-dlp eventually hands this value to urllib3/requests, whose error for a
    bad port is cryptic and otherwise aborts every search attempt. Validate it
    here so a bad optional proxy can never take down playback.
    """
    value = value.strip()
    if not value:
        return ""

    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {
            "http", "https", "socks4", "socks4a", "socks5", "socks5h"
        }:
            return None
        if not parsed.hostname or parsed.port is None:
            return None
        if not 1 <= parsed.port <= 65535:
            return None
    except ValueError:
        return None
    return value


def _proxy_from_environment() -> str | None:
    """Read and validate the optional yt-dlp proxy configuration.

    ``YTDLP_PROXY`` is the app-specific setting. If it is absent, leave valid
    system proxy settings alone, but explicitly disable malformed inherited
    values because requests may discover them automatically.
    """
    configured = os.environ.get("YTDLP_PROXY", "").strip()
    if configured:
        proxy = _valid_proxy_url(configured)
        if proxy is None:
            log.error(
                "❌ YTDLP_PROXY invalid hai; direct connection use ho rahi hai. "
                "Format: socks5://host:port ya http://host:port"
            )
            return ""
        return proxy

    for name in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        inherited = os.environ.get(name, "").strip()
        if inherited and _valid_proxy_url(inherited) is None:
            log.error(
                "❌ Inherited proxy setting %s invalid hai; yt-dlp ke liye "
                "direct connection use ho rahi hai.",
                name,
            )
            return ""
    return None


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
    # Keep the list short: every failed client adds latency and can trigger
    # more YouTube rate limiting. The default client set is maintained by
    # yt-dlp and is the most reliable option for current YouTube changes.
    # SPEED FIX: tv_downgraded + ios combos hataye — dono rarely help aur
    # har failed attempt = socket_timeout (6s) ka extra wait. 2 fast combos
    # kaafi hain; agar dono fail hon tab last-resort None combo chalti hai.
    if audio_only:
        combos: list[tuple[str | None, list, bool, bool]] = [
            ("bestaudio/best", ["default"],      False, False),
            ("bestaudio/best", ["web_embedded"], False, False),
            (None,             ["default"],      True,  False),
        ]
    else:
        combos = [
            ("best[height<=720][vcodec!=none][acodec!=none]/best[height<=720]/best", ["default"],      False, False),
            ("best[height<=720][vcodec!=none][acodec!=none]/best[height<=720]/best", ["web_embedded"], False, False),
            (None,                                                                   ["default"],      True,  False),
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
            **_opts(audio_only, player_client=["default"]),
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
            **_opts(audio_only, player_client=["default"]),
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

    # ── Last resort: search through Invidious ──────────────────────────────
    # A blocked YouTube/Heroku IP can make yt-dlp fail before it even gets a
    # video ID. Invidious can still return the ID, after which get_stream()
    # uses its proxied audio fallback below.
    fallback_entry = _invidious_search_sync(query)
    if fallback_entry:
        log.info(
            "✅ Search OK (Invidious fallback): %r",
            fallback_entry.get("title", query)[:50],
        )
        return fallback_entry

    log.error(f"❌ All search methods failed for: {query[:60]!r}")
    return None


def _invidious_search_sync(query: str) -> dict | None:
    """Search public Invidious instances without inheriting bad proxy env."""
    request_headers = {"User-Agent": "Mozilla/5.0 (compatible; ApexBot/1.0)"}
    encoded_query = quote_plus(query)

    for instance in _INVIDIOUS_INSTANCES:
        try:
            endpoint = f"{instance}/api/v1/search?q={encoded_query}&type=video"
            request = urllib.request.Request(endpoint, headers=request_headers)
            # ProxyHandler({}) is intentional: a malformed HTTP(S)_PROXY
            # setting must not break this emergency search path.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=10) as response:
                if response.status != 200:
                    continue
                items = json.loads(response.read().decode("utf-8"))

            result = next(
                (
                    item for item in items
                    if item.get("type") == "video" and item.get("videoId")
                ),
                None,
            )
            if not result:
                continue

            thumbnails = result.get("videoThumbnails") or []
            thumbnail = (
                next(
                    (
                        item.get("url", "")
                        for item in thumbnails
                        if item.get("quality") in {"medium", "high"}
                    ),
                    "",
                )
                or (thumbnails[0].get("url", "") if thumbnails else "")
            )
            video_id = result["videoId"]
            return {
                "id": video_id,
                "title": result.get("title") or query,
                "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
                "duration": int(result.get("lengthSeconds", 0) or 0),
                "thumbnail": thumbnail,
                "uploader": result.get("author") or "",
                "view_count": int(result.get("viewCount", 0) or 0),
            }
        except Exception as exc:
            log.debug("Invidious search failed (%s): %s", instance, exc)
            continue
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


def _download_audio_sync(url: str, audio_only: bool) -> tuple[str, int]:
    """
    Download audio/video to a local temp file using yt-dlp.
    Returns (local_file_path, duration_secs), or ("", 0) on failure.

    WHY THIS WORKS: yt-dlp ships with curl_cffi which impersonates Chrome's
    TLS fingerprint. YouTube CDN (googlevideo.com) blocks requests with a
    generic OpenSSL TLS stack (ntgcalls/ffmpeg) but allows Chrome-fingerprint
    downloads even from Heroku/cloud IPs. Reading from a local file bypasses
    all streaming CDN restrictions entirely.
    """
    cookie = _resolve_cookie_file()
    tmpdir = tempfile.mkdtemp(prefix="apex_dl_")
    fmt = (
        "best[height<=720][vcodec!=none][acodec!=none]/best[height<=720]/best"
        if not audio_only
        else "bestaudio/best"
    )
    opts: dict = {
        "format": fmt,
        "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if cookie:
        opts["cookiefile"] = cookie

    # Carry over bgutil/PO-token extractor args and custom headers
    base = _opts(audio_only)
    for k in ("extractor_args", "http_headers"):
        if k in base:
            opts[k] = base[k]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                shutil.rmtree(tmpdir, ignore_errors=True)
                return "", 0

            ext = info.get("ext", "opus")
            path = os.path.join(tmpdir, f"audio.{ext}")
            if not os.path.exists(path):
                files = [
                    f for f in os.listdir(tmpdir)
                    if os.path.isfile(os.path.join(tmpdir, f))
                ]
                if not files:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                    return "", 0
                path = os.path.join(tmpdir, files[0])

            dur = info.get("duration", 0) or 0
            size_mb = os.path.getsize(path) / 1e6
            log.info(
                "✅ yt-dlp download OK | %s → %s (%.1f MB, %ds)",
                url[:60], os.path.basename(path), size_mb, dur,
            )
            return path, dur
    except Exception as e:
        log.error("❌ yt-dlp local download failed: %s", e)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return "", 0


def cleanup_temp_file(path: str) -> None:
    """
    Delete the apex_dl_ temp directory containing a downloaded audio file.
    Safe to call with any path — no-op if path is not an apex_dl_ temp file.
    """
    if not path:
        return
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if (
            os.path.basename(parent).startswith(("apex_dl_", "apex_tg_"))
            and os.path.isdir(parent)
        ):
            shutil.rmtree(parent, ignore_errors=True)
            log.debug("🗑️ Cleaned up temp download dir: %s", parent)
    except Exception as e:
        log.debug("Temp cleanup error for %s: %s", path, e)


async def _resolve_stream(
    url: str,
    is_video: bool = False,
    force_refresh: bool = False,
) -> tuple[str, str | None, int, dict]:
    """
    Get direct stream URL for playback.
    Returns (media_url, optional_audio_url, duration_secs, http_headers).

    ⚡ SPEED ARCHITECTURE:
    - skip_cdn=True  (cloud host OR force_refresh):
        Invidious proxy + yt-dlp local download race in parallel.
        Winner used immediately, loser cancelled.
        On Heroku this means ~4s (Invidious) instead of 32s (CDN fail + download).
    - skip_cdn=False (VPS / home server, CDN not known blocked):
        yt-dlp signed URL + Invidious race. CDN wins if URL is streamable.
        Falls back to local download only if both fail.
    """
    cached = None if force_refresh else _cached_stream(url, is_video)
    if cached:
        return cached

    loop = asyncio.get_running_loop()
    vid_id = _extract_video_id(url)

    # ── Fast path: CDN known-blocked OR force_refresh ─────────────
    # On cloud/Heroku IPs, the CDN is always blocked. Trying it first wastes
    # 12 s of silence before the premature-end retry kicks in.
    # Skip CDN entirely and race Invidious (fast, ~4s) vs download (~15s).
    skip_cdn = force_refresh or _cdn_blocked
    if skip_cdn:
        reason = "force_refresh" if force_refresh else "cdn_blocked"
        log.info("⚡ skip_cdn=%s | racing Invidious vs download | %s", reason, url[:60])

        inv_future: asyncio.Future = asyncio.ensure_future(
            _try_invidious(vid_id, not is_video)
            if vid_id
            else asyncio.sleep(0, result=None)
        )
        dl_future: asyncio.Future = asyncio.ensure_future(
            loop.run_in_executor(_exec, _download_audio_sync, url, not is_video)
        )
        pending_set = {inv_future, dl_future}

        inv_win = dl_win = None
        while pending_set:
            done, pending_set = await asyncio.wait(
                pending_set, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                try:
                    res = task.result()
                except Exception as exc:
                    log.debug("skip_cdn task error: %s", exc)
                    continue
                if task is inv_future and isinstance(res, tuple) and res and res[0]:
                    inv_win = res
                    break
                elif task is dl_future:
                    path, dur2 = res if res else ("", 0)
                    if path:
                        dl_win = (path, dur2)
                        break
            if inv_win or dl_win:
                break

        # Cancel whatever is still running
        for t in (inv_future, dl_future):
            if not t.done():
                t.cancel()
        await asyncio.gather(inv_future, dl_future, return_exceptions=True)

        if inv_win:
            su, dur = inv_win
            log.info("✅ Invidious proxy won the race | vid=%s", vid_id)
            _cache_stream(url, is_video, su, None, dur, {})
            return su, None, dur, {}

        if dl_win:
            path, dur = dl_win
            log.info("✅ Download won the race | %s → %s", url[:60], os.path.basename(path))
            return path, None, dur, {}

        raise Exception(f"❌ Invidious + download dono fail ho gaye: {url[:60]}")

    # ── Normal path: CDN not known-blocked (VPS / home server) ───
    # Race yt-dlp signed URL against Invidious. Falls back to local download
    # only if both fail to give a streamable URL.
    ytdlp_task = loop.run_in_executor(_exec, _extract_sync, url, not is_video)
    inv_task = asyncio.create_task(
        _try_invidious(vid_id, not is_video)
        if vid_id
        else asyncio.sleep(0, result=None)
    )
    info_result = inv_result = None
    done, pending = await asyncio.wait(
        {ytdlp_task, inv_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if inv_task in done:
        try:
            inv_result = inv_task.result()
        except Exception as exc:
            inv_result = exc
        if isinstance(inv_result, tuple) and inv_result:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        else:
            try:
                info_result = await ytdlp_task
            except Exception as exc:
                info_result = exc
    elif ytdlp_task in done:
        try:
            info_result = ytdlp_task.result()
        except Exception as exc:
            info_result = exc
        if info_result:
            inv_task.cancel()
            await asyncio.gather(inv_task, return_exceptions=True)
        else:
            try:
                inv_result = await inv_task
            except Exception as exc:
                inv_result = exc

    if isinstance(inv_result, tuple) and inv_result:
        su, dur = inv_result
        log.info("✅ Invidious proxy URL use ho rahi hai | vid=%s", vid_id)
        _cache_stream(url, is_video, su, None, dur, {})
        return su, None, dur, {}

    if isinstance(inv_result, Exception):
        log.warning("Invidious failed for %s: %s", vid_id, inv_result)

    info = None if isinstance(info_result, Exception) else info_result
    if not info:
        exc_msg = str(info_result) if isinstance(info_result, Exception) else ""
        raise Exception(
            f"❌ Stream resolve nahi hua: {url[:60]}"
            + (f" — {exc_msg}" if exc_msg else "")
        )

    su, audio_url = _pick_urls(info, not is_video)
    dur = info.get("duration", 0) or 0
    headers = info.get("http_headers") or {}

    if su and _is_streamable_url(su):
        log.info("✅ Direct signed stream ready | %s", url[:60])
        _cache_stream(url, is_video, su, audio_url, dur, headers)
        return su, audio_url, dur, headers

    log.info(
        "📥 %s — downloading locally via yt-dlp | %s",
        "Direct stream unavailable" if not su else "CDN retry fallback",
        url[:60],
    )
    local_path, dur = await loop.run_in_executor(
        _exec, _download_audio_sync, url, not is_video
    )
    if local_path:
        return local_path, None, dur, {}

    if not su:
        raise Exception(f"❌ Stream URL empty hai: {url[:60]}")
    log.warning("⚠️ Falling back to CDN URL after local download failure: %s", su[:80])
    _cache_stream(url, is_video, su, audio_url, dur, headers)
    return su, audio_url, dur, headers


async def get_stream(
    url: str,
    is_video: bool = False,
    force_refresh: bool = False,
) -> tuple[str, str | None, int, dict]:
    """Return a shared stream-resolution task for normal playback."""
    key = _stream_key(url, is_video)
    if not force_refresh:
        cached = _cached_stream(url, is_video)
        if cached:
            return cached
        pending = _stream_tasks.get(key)
        if pending:
            try:
                return await pending
            finally:
                if pending.done() and _stream_tasks.get(key) is pending:
                    _stream_tasks.pop(key, None)

    task = asyncio.create_task(_resolve_stream(url, is_video, force_refresh))
    if not force_refresh:
        _stream_tasks[key] = task
    try:
        return await task
    finally:
        if not force_refresh and _stream_tasks.get(key) is task:
            _stream_tasks.pop(key, None)


def prefetch_stream(url: str, is_video: bool = False) -> None:
    """Resolve a stream as soon as search returns, without blocking the UI.

    Search deliberately uses yt-dlp's flat mode for fast metadata. Starting the
    real stream resolution here overlaps that work with Telegram message
    handling and VC setup, so _do_play() can consume the same task instead of
    performing a second sequential extraction.
    """
    if not url:
        return
    key = _stream_key(url, is_video)
    if key in _stream_tasks or _cached_stream(url, is_video):
        return

    task = asyncio.create_task(_resolve_stream(url, is_video=is_video))
    _stream_tasks[key] = task

    def _remove_completed(completed: asyncio.Task) -> None:
        if _stream_tasks.get(key) is completed:
            _stream_tasks.pop(key, None)

    def _consume_error(completed: asyncio.Task) -> None:
        if completed.cancelled():
            return
        try:
            completed.exception()
        except Exception:
            pass

    task.add_done_callback(_remove_completed)
    task.add_done_callback(_consume_error)


async def download_audio(url: str, is_video: bool = False) -> tuple[str, int]:
    """Download media locally for queue prefetch/archive upload."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_exec, _download_audio_sync, url, not is_video)


# ── Invidious fallback ────────────────────────────────────────────
# Public Invidious instances — used when yt-dlp fails on Heroku/cloud IPs.
# IMPORTANT: We do NOT use the direct CDN URLs from adaptiveFormats — those are
# googlevideo.com links that are still blocked from Heroku.
# Instead we use /latest_version?local=true which makes Invidious proxy the
# stream through its own server, bypassing the IP block entirely.
_INVIDIOUS_INSTANCES = [
    # companion-proxy instances (stream via their own servers, not bare CDN).
    # invidious.f5.si routes through jp1-cmp.invidious.f5.si — 3-hop chain but
    # confirmed working (200 audio/webm) as of 2026-07-24.
    "https://invidious.f5.si",
    "https://invidious.privacydev.net",
    "https://invidious.nerdvpn.de",
    "https://invidious.fdn.fr",
    "https://invidious.io.lol",
    "https://yt.drgnz.club",
    "https://invidious.einfachzocken.eu",
    "https://inv.us.projectsegfau.lt",
    "https://inv.in.projectsegfau.lt",
    "https://invidious.protokolla.fi",
    "https://invidious.privacyredirect.com",
    "https://invidious.jing.rocks",
]

# Common YouTube audio itags. These let the fallback work even when an
# Invidious instance disables /api/v1/videos but still serves /latest_version.
_INVIDIOUS_AUDIO_ITAGS = (251, 140, 250, 139)


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from any YouTube URL format."""
    patterns = [
        r"[?&]v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"embed/([a-zA-Z0-9_-]{11})",
        r"shorts/([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


async def _try_invidious(video_id: str, audio_only: bool) -> tuple[str, int] | None:
    """
    Try public Invidious instances as a last-resort fallback.
    Returns (stream_url, duration_secs) or None.

    KEY: We use /latest_version?local=true — NOT the direct CDN URLs from
    adaptiveFormats. The adaptiveFormats URLs are googlevideo.com CDN links
    that are STILL blocked from Heroku IPs. With local=true, Invidious
    fetches and re-serves the stream through its own server, so ntgcalls
    pulls audio from Invidious (not blocked) instead of YouTube CDN (blocked).
    """
    # Metadata endpoints are frequently disabled, while /latest_version still
    # works. Probe known itags directly and probe all instances concurrently;
    # serially waiting on dead public instances was adding 40–60 seconds.
    itags = _INVIDIOUS_AUDIO_ITAGS if audio_only else (18, 22)
    # connect=5: companion servers (jp1-cmp.invidious.f5.si etc.) need a fresh
    # TLS handshake that takes >2s from Heroku — old connect=2 always timed out.
    # total=20: allow up to 6 redirect hops, each needing its own round-trip.
    timeout = aiohttp.ClientTimeout(total=20, connect=5)
    headers = {"User-Agent": "Mozilla/5.0"}

    async def _probe(instance: str) -> tuple[str, int] | None:
        for itag in itags:
            current = (
                f"{instance}/latest_version?"
                f"id={video_id}&itag={itag}&local=true"
            )
            # Up to 6 hops: instance → companion/latest_version →
            # companion/videoplayback (3 hops for f5.si-style setups).
            for _ in range(6):
                try:
                    async with session.get(
                        current,
                        headers=headers,
                        allow_redirects=False,
                    ) as response:
                        if response.status in (301, 302, 303, 307, 308):
                            location = response.headers.get("Location", "")
                            if not location:
                                break
                            current = urljoin(current, location)
                            # If the redirect lands on a bare googlevideo CDN
                            # URL (no /companion/ prefix) it will be blocked from
                            # Heroku — skip this itag immediately.
                            if (
                                'googlevideo.com/videoplayback' in current
                                and '/companion/' not in current
                            ):
                                log.debug(
                                    'Invidious → bare CDN redirect (blocked) | %s itag=%s',
                                    instance, itag,
                                )
                                break
                            continue

                        if response.status not in (200, 206):
                            break

                        content_type = response.headers.get(
                            "Content-Type", ""
                        ).lower()
                        # Whitelist: only audio/* or video/* is a real stream.
                        # text/plain (error messages), text/html (login pages),
                        # application/json, and empty types are all rejected.
                        # inv.in.projectsegfau.lt returns 'text/plain; charset=utf-8'
                        # with a 25-byte error body — the old blacklist accepted it.
                        if not (
                            content_type.startswith("audio/")
                            or content_type.startswith("video/")
                        ):
                            break

                        log.info(
                            f"✅ Invidious proxy OK | {instance} | "
                            f"{video_id} | itag={itag} | hops<=4"
                        )
                        return current, 0
                except Exception as e:
                    log.debug(
                        f"Invidious probe failed "
                        f"({instance}, itag={itag}): {e}"
                    )
                    break
        return None

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = {
            asyncio.create_task(_probe(instance))
            for instance in _INVIDIOUS_INSTANCES
        }
        try:
            pending = tasks
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    try:
                        result = task.result()
                    except Exception as e:
                        log.debug(f"Invidious worker failed: {e}")
                        continue
                    if result:
                        for other in pending:
                            other.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        return result
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    log.error(f"❌ All Invidious instances failed for {video_id}")
    return None


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
