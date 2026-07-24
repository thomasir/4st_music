"""
play.py — v6.0 ULTIMATE
✅ 3-step loading animation: 🔍 → 🎯 → 🎵
✅ Professional now playing card (Telegram blockquote style)
✅ Thumbnail with music card
✅ Better button emojis + layout
✅ Volume MAX (10x boost) + live volume control
✅ Auto-next on stream end
✅ Queue system with position
✅ /playforce — instant play (skip queue)
✅ /shuffle — shuffle queue
✅ /loop — toggle loop
✅ /np — now playing card refresh
✅ Stream error recovery
"""

import asyncio
import json
import os
import logging
import random
import shutil
import tempfile
import time as _time

from pyrogram import Client, filters
from pyrogram.errors import (
    MessageNotModified, MessageIdInvalid, FloodWait,
    ChannelInvalid, ChatAdminRequired, UserNotParticipant,
    UserAlreadyParticipant, InviteHashExpired, PeerIdInvalid,
)
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from pytgcalls import PyTgCalls, filters as tgfilters
from pytgcalls.types import MediaStream, AudioQuality, VideoQuality, StreamEnded
# BUG FIX: AlreadyJoinedError aur NotInCallError py-tgcalls 2.x mein exist nahi karte — dono hataaye.
# NotInCallError ka naam 2.x mein NotInGroupCall ho gaya, lekin yeh use nahi ho raha tha.
# Generic Exception catch se handle ho raha hai _do_play() mein.
from pytgcalls.exceptions import NoActiveGroupCall

from clients import bot, assistant, call_py
from helpers.queue import (
    Song, add_to_queue, get_current, set_current,
    queue_size, pop_queue, get_queue, clear_queue, is_active, shuffle_queue,
)
from helpers.youtube import (
    get_stream, prefetch_stream, fmt_duration, clear_cache_for_url,
    cleanup_temp_file, mark_cdn_blocked,
)
from helpers.youtube import download_audio
from helpers.archive import (
    find_archived,
    upload_local,
    download_archived,
    record_to_song_fields,
)
from database import (
    add_play_history, get_random_history_song, get_history_count,
    get_autoplay, set_autoplay,
)
from config import DOWNLOAD_DIR, FFMPEG_VOLUME_BOOST, LOG_CHANNEL, OWNER_USERNAME, BOT_NAME

log = logging.getLogger("ApexBot.play")

_VOL_EFFECTIVE = min(float(FFMPEG_VOLUME_BOOST), 10.0)

# ── Loop / Autoplay store ─────────────────────────────────────────
_loop_enabled: dict[int, bool] = {}
_autoplay:     dict[int, bool] = {}   # in-memory cache; DB is source of truth
# Tracks chat_id → local temp file path for songs downloaded via yt-dlp.
# File is deleted in on_stream_end to free /tmp disk space.
_stream_local_files: dict[int, str] = {}
_prefetch_tasks: dict[str, asyncio.Task] = {}

def _ffmpeg_params() -> str:
    return f"-af volume={_VOL_EFFECTIVE:.1f}"


# ══ SAFE HELPERS ══════════════════════════════════════════════════

async def _safe_edit(msg, text: str, markup=None, parse_mode=None):
    """Edit text OR photo-caption message safely.

    Pyrogram splits editing into two APIs:
    - Text messages  → msg.edit(text)
    - Photo/media    → msg.edit_caption(caption=text)
    Calling the wrong one raises BadRequest silently in callbacks, which was
    the reason NP-card buttons (pause/vol/loop) never updated the card when
    the song had a thumbnail (photo message).
    """
    try:
        kwargs = {}
        if markup:
            kwargs["reply_markup"] = markup
        # Detect photo/media messages
        is_media = bool(
            getattr(msg, "photo", None)
            or getattr(msg, "video", None)
            or getattr(msg, "document", None)
            or getattr(msg, "audio", None)
        )
        if is_media:
            await msg.edit_caption(caption=text, **kwargs)
        else:
            if parse_mode:
                kwargs["parse_mode"] = parse_mode
            await msg.edit(text, **kwargs)
    except (MessageNotModified, MessageIdInvalid):
        pass
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        log.debug(f"safe_edit: {e}")


async def _safe_delete(msg):
    try:
        await msg.delete()
    except Exception:
        pass


async def _auto_delete(msg, delay: float = 5):
    """Background task: delete message after delay seconds. Non-blocking."""
    await asyncio.sleep(delay)
    await _safe_delete(msg)


# ── Assistant ID cache ────────────────────────────────────────────
_asst_id: int | None = None

async def _get_asst_id() -> int:
    global _asst_id
    if _asst_id is None:
        me = await assistant.get_me()
        _asst_id = me.id
    return _asst_id


# ── Volume + lock + paused state stores ──────────────────────────
_volumes:    dict[int, int]         = {}
_play_locks: dict[int, asyncio.Lock] = {}
_np_msgs:    dict[int, any]         = {}   # store last NP message per chat
_paused:     dict[int, bool]        = {}   # BUG FIX: track paused state per chat

# ── Stream-error retry state ──────────────────────────────────────
# Used to detect an immediate EOF (ntgcalls "Reached end of the file") and
# retry with a force-refreshed URL so the bot does not leave VC after 1 sec.
_play_start_times:   dict[int, float] = {}   # chat_id → monotonic time of last play()
_stream_retry_counts: dict[int, int]  = {}   # chat_id → retries attempted for current song

MAX_STREAM_RETRIES      = 2   # max auto-retries per song before giving up
PREMATURE_END_THRESHOLD = 12  # seconds — stream end within this time → treat as error


def _get_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _play_locks:
        _play_locks[chat_id] = asyncio.Lock()
    return _play_locks[chat_id]


def _song_key(song: Song) -> str:
    return (song.webpage_url or song.url or song.title).strip().lower()


async def _prefetch_song(song: Song) -> str:
    """Prepare a song locally so a queue transition does not hit the network."""
    if song.local_path and os.path.isfile(song.local_path):
        return song.local_path

    key = _song_key(song)
    existing = _prefetch_tasks.get(key)
    if existing:
        try:
            return await existing
        finally:
            if existing.done():
                _prefetch_tasks.pop(key, None)

    async def _run() -> str:
        if song.archive_message_id:
            record = {
                "message_id": song.archive_message_id,
                "source_url": song.webpage_url,
                "title": song.title,
                "artist": song.artist,
                "duration": song.duration,
                "file_id": song.archive_file_id,
            }
            path = await download_archived(record)
        else:
            source = song.webpage_url or song.url
            if not source:
                raise RuntimeError("song source URL is empty")
            path, duration = await download_audio(source, song.is_video)
            if duration and not song.duration:
                song.duration = duration
            if not path:
                raise RuntimeError("local download returned no file")

            # Upload in the background. Playback must not wait for Telegram
            # archive delivery; only the local file is on the critical path.
            asyncio.create_task(
                _archive_downloaded_song(
                    path,
                    title=song.title,
                    artist=song.artist,
                    source_url=source,
                    duration=song.duration,
                    is_video=song.is_video,
                )
            )

        song.local_path = path
        return path

    task = asyncio.create_task(_run())
    _prefetch_tasks[key] = task
    try:
        return await task
    finally:
        if task.done():
            _prefetch_tasks.pop(key, None)


async def _archive_downloaded_song(
    path: str,
    *,
    title: str,
    artist: str,
    source_url: str,
    duration: int,
    is_video: bool = False,
) -> None:
    """Archive a downloaded file without delaying playback."""
    archive_copy = ""
    try:
        # The playback file belongs to the stream lifecycle and can be deleted
        # while this background task is still uploading. Copy it into an
        # independent temporary directory first.
        if not os.path.isfile(path):
            return
        archive_dir = tempfile.mkdtemp(prefix="apex_archive_")
        archive_copy = os.path.join(archive_dir, os.path.basename(path))
        shutil.copy2(path, archive_copy)
        await upload_local(
            archive_copy,
            title=title,
            artist=artist,
            source_url=source_url,
            duration=duration,
            is_video=is_video,
        )
    except Exception as exc:
        log.debug("Background archive upload failed: %s", exc)
    finally:
        if archive_copy:
            try:
                shutil.rmtree(os.path.dirname(archive_copy), ignore_errors=True)
            except Exception:
                pass


def _schedule_prefetch(song: Song) -> None:
    """Start preparing a waiting song, but never block the command handler."""
    task = asyncio.create_task(_prefetch_song(song))

    def _done(completed: asyncio.Task) -> None:
        try:
            completed.result()
            log.info("✅ Next track ready | %s", song.title[:70])
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.warning("Next-track prefetch failed | %s | %s", song.title[:60], exc)

    task.add_done_callback(_done)


def _song_from_archive(record: dict, requested_by: str) -> Song:
    fields = record_to_song_fields(record)
    return Song(
        title=fields["title"],
        url="",
        duration=fields["duration"],
        webpage_url=fields["webpage_url"],
        requested_by=requested_by,
        source="telegram",
        artist=fields["artist"],
        archive_message_id=fields["archive_message_id"],
        archive_file_id=fields["archive_file_id"],
    )


async def _find_cached_song(query: str, requested_by: str) -> Song | None:
    try:
        record = await find_archived(query)
    except Exception as exc:
        log.debug("Archive lookup failed: %s", exc)
        return None
    return _song_from_archive(record, requested_by) if record else None


# ══ MUSIC CARD UI ══════════════════════════════════════════════════

def now_playing_buttons(url: str = "", paused: bool = False, queue_count: int = 0, autoplay: bool = False, chat_id: int = 0) -> InlineKeyboardMarkup:
    toggle = (
        InlineKeyboardButton("▶️ Resume", callback_data="resume")
        if paused else
        InlineKeyboardButton("⏸️ Pause", callback_data="pause")
    )
    queue_label = f"📋 Queue ({queue_count})" if queue_count > 0 else "📋 Empty"
    ap_label = "🔁 Autoplay ✅" if autoplay else "🔁 Autoplay ○"
    rows = [
        [
            toggle,
            InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
            InlineKeyboardButton("⏹️ Stop", callback_data="stop"),
        ],
        [
            InlineKeyboardButton("🔉 Vol−", callback_data="vol_down"),
            InlineKeyboardButton(queue_label, callback_data="queue_cb"),
            InlineKeyboardButton("🔊 Vol+", callback_data="vol_up"),
        ],
        [
            InlineKeyboardButton("🔀 Shuffle", callback_data="shuffle_cb"),
            InlineKeyboardButton("🔁 Loop", callback_data="loop_cb"),
            InlineKeyboardButton("🔄 Refresh", callback_data="np_refresh"),
        ],
        [
            InlineKeyboardButton(ap_label, callback_data="autoplay_cb"),
        ],
    ]
    if url and url.startswith("http"):
        rows.append([
            InlineKeyboardButton("🎬 YouTube pe Dekho", url=url),
        ])
    return InlineKeyboardMarkup(rows)


def _vol_bar(vol: int, total: int = 10) -> str:
    """Visual volume bar using block characters."""
    filled = min(total, round(vol / 200 * total))
    return "▰" * filled + "▱" * (total - filled)


def np_card_text(song: Song, chat_id: int = 0) -> str:
    """Premium now-playing card."""
    kind_emoji  = "🎬" if song.is_video else "🎵"
    quality_tag = "📺 Video 720p" if song.is_video else "🎙️ HQ Audio"
    vol         = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
    loop_on     = _loop_enabled.get(chat_id, False)
    ap_on       = _autoplay.get(chat_id, False)
    q           = queue_size(chat_id)
    dur_text    = fmt_duration(song.duration) if song.duration else "🔴 Live"
    title       = (song.title[:62] + "…") if len(song.title) > 62 else song.title
    q_display   = f"**{q}** song{'s' if q != 1 else ''}" if q > 0 else "Empty"
    vol_bar     = _vol_bar(vol)
    loop_str    = "🔁 **ON**" if loop_on else "○ OFF"
    ap_str      = "🔁 **ON**" if ap_on else "○ OFF"

    return (
        f"**{kind_emoji} NOW PLAYING** ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎶 **{title}**\n"
        f"⏱️ `{dur_text}` · {quality_tag}\n\n"
        f"> 👤 Requested by {song.requested_by or 'Unknown'}\n"
        f"> 🔊 `{vol_bar}` **{vol}%**\n"
        f"> 📋 Queue: {q_display}\n"
        f"> 🔁 Loop: {loop_str}\n"
        f"> 🎲 Autoplay: {ap_str}"
    )


# ═══ CORE PLAY LOGIC ═══════════════════════════════════════════════

async def _ensure_assistant_in_group(chat_id: int) -> bool:
    """
    Make sure the assistant account is a member of the group.

    Flow:
    1. Try get_chat — if it works, assistant already has access → done.
    2. If not a member, ask the bot (which IS an admin) to create a fresh
       invite link, then have the assistant join via that link.
    3. Wait up to 8 s for Telegram to process the membership.

    Returns True if assistant is (now) in the group, False otherwise.
    """
    # Step 1: check if assistant already knows this chat
    try:
        await assistant.get_chat(chat_id)
        return True                            # already a member
    except (UserNotParticipant, PeerIdInvalid, ChannelInvalid):
        pass                                   # not a member — continue
    except Exception:
        pass                                   # unknown error — still try to join

    # Step 2: bot creates a single-use invite link (bot must be admin with invite rights)
    invite_link = None
    try:
        link_obj = await bot.create_chat_invite_link(
            chat_id,
            name="Assistant Auto-Join",
            member_limit=1,          # single-use
        )
        invite_link = link_obj.invite_link
        log.info("🔗 Invite link created for chat %s: %s", chat_id, invite_link)
    except Exception as e:
        log.warning("Could not create invite link for chat %s: %s", chat_id, e)
        # Fallback: try exporting the primary invite link
        try:
            invite_link = await bot.export_chat_invite_link(chat_id)
            log.info("🔗 Exported invite link for chat %s", chat_id)
        except Exception as e2:
            log.error("Could not export invite link for chat %s: %s", chat_id, e2)
            return False

    if not invite_link:
        return False

    # Step 3: assistant joins via the invite link
    try:
        await assistant.join_chat(invite_link)
        log.info("✅ Assistant joined chat %s via invite link", chat_id)
    except UserAlreadyParticipant:
        log.info("ℹ️ Assistant already in chat %s", chat_id)
    except InviteHashExpired:
        log.warning("Invite link expired for chat %s — retrying with export", chat_id)
        try:
            fallback = await bot.export_chat_invite_link(chat_id)
            await assistant.join_chat(fallback)
        except Exception as e:
            log.error("Fallback join also failed for chat %s: %s", chat_id, e)
            return False
    except Exception as e:
        log.error("Assistant join_chat failed for chat %s: %s", chat_id, e)
        return False

    # SPEED FIX: sleep removed — Telegram membership propagation is instant
    return True


async def _join_vc(chat_id: int):
    """Ensure assistant is in the group, then join VC. Returns True on success."""
    return await _ensure_assistant_in_group(chat_id)


async def _leave_call(chat_id: int):
    """Leave VC and clear state."""
    set_current(chat_id, None)
    try:
        await call_py.leave_call(chat_id)
    except Exception:
        pass


async def _set_volume_bg(chat_id: int):
    vol = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
    try:
        await call_py.change_volume_call(chat_id, vol)
    except Exception:
        pass


async def _do_play(chat_id: int, song: Song, status_msg, is_video: bool = False, force_refresh: bool = False):
    """Core: resolve stream → join VC → start playback → show NP card."""
    # BUG FIX: outer try/except — agar koi bhi unhandled exception aaye toh
    # user ko silently kuch nahi dikhta tha (create_task exceptions swallow karta hai).
    # Ab hamesha error message milega.
    try:
        await _do_play_inner(chat_id, song, status_msg, is_video, force_refresh=force_refresh)
    except Exception as e:
        log.exception("_do_play unhandled crash in chat %s", chat_id)
        try:
            await bot.send_message(
                chat_id,
                f"❌ **Internal error — please report:**\n`{str(e)[:300]}`\n\n"
                "Dobara `/play` karo ya `/stop` karke restart karo! 🎵"
            )
        except Exception:
            pass


async def _do_play_inner(chat_id: int, song: Song, status_msg, is_video: bool = False, force_refresh: bool = False):
    """Actual play logic — called by _do_play which wraps it in error handler."""
    async with _get_lock(chat_id):

        # ── Step 2 animation: Found! Loading... ──────────────────
        await _safe_edit(
            status_msg,
            f"🎯 **Mil gaya!** Stream load ho raha hai...\n\n"
            f"🎶 **{song.title[:60]}**\n"
            f"⏱️ `{fmt_duration(song.duration)}`\n\n"
            f"🔗 _Connecting to Voice Chat..._"
        )

        # Telegram archive/local prefetch is the fast path. It does not need
        # YouTube cookies and avoids Invidious/yt-dlp during queue transitions.
        if song.local_path and os.path.isfile(song.local_path):
            stream_url, audio_url, dur, http_headers = (
                song.local_path,
                None,
                song.duration,
                {},
            )
        elif song.archive_message_id:
            try:
                await asyncio.wait_for(_prefetch_song(song), timeout=45.0)
                stream_url, audio_url, dur, http_headers = (
                    song.local_path,
                    None,
                    song.duration,
                    {},
                )
            except Exception as e:
                await _safe_edit(
                    status_msg,
                    f"❌ **Telegram archive se audio nahi mila:**\n`{str(e)[:300]}`\n\n"
                    "Archive message check karo ya `/play` dobara try karo.",
                )
                return
        else:
            stream_url = audio_url = None
            dur = 0
            http_headers = {}

        # BUG FIX: hamesha webpage_url se fresh stream fetch karo.
        # song.url direct CDN URL hota hai jo expire ho sakta hai.
        # get_stream() cache check karta hai → fresh rehne par instant return,
        # expire hone par auto re-fetch. Headers bhi milte hain.
        source = song.webpage_url or song.url
        if not source:
            await _safe_edit(status_msg, "❌ **Source URL khaali hai.**\nKoi aur song try karo! 🎵")
            return

        # BUG FIX: asyncio.wait_for se 90s timeout — bina iske yt-dlp cloud IPs pe
        # hang karta tha (socket_timeout=20 per attempt, lekin 10 combos = 200s possible).
        # 90s mein fail ho jaayega aur user ko clear error milega.
        if not stream_url:
            # ⚡ SPEED FIX: get_stream() aur _join_vc() parallel chalao
            # Pehle sequential tha: stream(3-8s) PHIR VC join(0-3s) = 3-11s total
            # Ab: asyncio.gather se dono ek saath — combined = max(stream, VC) not sum
            try:
                (stream_url, audio_url, dur, http_headers), joined = await asyncio.gather(
                    asyncio.wait_for(
                        get_stream(source, is_video=is_video, force_refresh=force_refresh),
                        timeout=90.0,
                    ),
                    _join_vc(chat_id),
                )
                if dur and not song.duration:
                    song.duration = dur
            except asyncio.TimeoutError:
                await _safe_edit(
                    status_msg,
                    "⏱️ **Timeout!** YouTube bahut slow hai abhi.\n\n"
                    "Archive channel mein track upload ho jaane ke baad next play "
                    "cookies ke bina fast chalega.",
                )
                return
            except Exception as e:
                await _safe_edit(status_msg, f"❌ **Stream nahi mila:**\n`{e}`\n\nDusra song try karo! 🎵")
                return
        else:
            # local path / archive — VC join sequentially (pehle se fast path hai)
            joined = await _join_vc(chat_id)

        if not stream_url:
            await _safe_edit(status_msg, "❌ **Stream URL khaali hai.**\nKoi aur song try karo! 🎵")
            return

        if not joined:
            await _safe_edit(
                status_msg,
                "❌ **Assistant group join nahi kar paya!**\n\n"
                "**Fix karo:**\n"
                "1️⃣ Bot ko group ka **Admin** banao\n"
                "2️⃣ Admin permissions mein **'Add Members'** ON karo\n"
                "3️⃣ Phir `/play` dobara try karo 🎵"
            )
            return

        # The first play also seeds the Telegram archive. Make a private copy
        # before scheduling the upload because the playback temp directory is
        # deleted as soon as the stream ends.
        if (
            os.path.isabs(stream_url)
            and os.path.isfile(stream_url)
            and not song.archive_message_id
            and source
            and not is_video
        ):
            asyncio.create_task(
                _archive_downloaded_song(
                    stream_url,
                    title=song.title,
                    artist=song.artist,
                    source_url=source,
                    duration=dur or song.duration,
                    is_video=is_video,
                )
            )

        # ── Build & start stream ──────────────────────────────────
        # RACE CONDITION FIX: set_current PEHLE karo, play() baad mein.
        # call_py.play() ke baad agar immediately stream_end fire ho jaaye
        # (network fail, bad URL, etc.), on_stream_end ko get_current() se
        # song milna chahiye — warna wo None dekhta hai, queue khaali samajhta
        # hai, aur _leave_call() call kar deta hai (1-sec VC leave bug).
        set_current(chat_id, song)

        try:
            # ROOT CAUSE FIX: pytgcalls 2.x places ffmpeg_parameters BEFORE -i in
            # the shell_reader FFmpeg command (used for local files).  "-af volume=X"
            # is an OUTPUT-side audio filter — FFmpeg rejects it when it appears as
            # an input option and exits immediately, causing ntgcalls shell_reader to
            # see EOF in 0.0 s (the "bot leaves VC in 1 second" bug with local files).
            # For HTTP/CDN URLs a different code path is used and the bug is hidden.
            # Volume is already controlled via call_py.change_volume_call(), so
            # ffmpeg_parameters is not needed for local paths.
            is_local_file = os.path.isabs(stream_url) and os.path.isfile(stream_url)
            stream = MediaStream(
                stream_url,
                audio_parameters=AudioQuality.HIGH,
                video_parameters=VideoQuality.HD_720p if is_video else VideoQuality.SD_360p,
                # An audio URL must not be probed as a video source. That
                # extra ffmpeg probe can hang after the assistant joins VC.
                video_flags=(
                    MediaStream.Flags.AUTO_DETECT
                    if is_video else MediaStream.Flags.IGNORE
                ),
                ffmpeg_parameters=None if is_local_file else _ffmpeg_params(),
                headers=http_headers if http_headers else None,
            )
            log.info(
                "▶️ Starting voice playback | chat=%s | video=%s | source=%s",
                chat_id,
                is_video,
                stream_url[:100],
            )
            await asyncio.wait_for(call_py.play(chat_id, stream), timeout=25.0)
            log.info("✅ Voice playback started | chat=%s | title=%s", chat_id, song.title[:80])
            # Track when this stream started so on_stream_end can detect immediate EOF.
            _play_start_times[chat_id] = _time.monotonic()
            _stream_retry_counts.pop(chat_id, None)  # reset retry counter on successful start
            # Track local temp file so on_stream_end can clean it up
            if os.path.isabs(stream_url) and os.path.isfile(stream_url):
                _stream_local_files[chat_id] = stream_url
            else:
                _stream_local_files.pop(chat_id, None)

        except NoActiveGroupCall:
            set_current(chat_id, None)
            await _leave_call(chat_id)   # VC properly clean karo
            await _safe_edit(
                status_msg,
                "❌ **Voice Chat band hai!**\n\n"
                "Group Settings → Voice Chats → **Start** karo pehle,\nphir `/play` dobara karo. 🎵"
            )
            return
        except asyncio.TimeoutError:
            set_current(chat_id, None)
            await _leave_call(chat_id)
            log.error("⏱️ Voice playback start timed out in chat %s", chat_id)
            await _safe_edit(
                status_msg,
                "⏱️ **Stream start nahi ho paya.**\n\n"
                "Voice Chat connect hua tha, lekin audio source respond nahi kar raha. "
                "Dobara `/play` try karo. 🎵",
            )
            return
        except (ChannelInvalid, ChatAdminRequired, UserNotParticipant) as e:
            set_current(chat_id, None)
            await _leave_call(chat_id)   # VC properly clean karo
            log.warning("Channel access error in chat %s: %s", chat_id, e)
            await _safe_edit(
                status_msg,
                "❌ **Voice Chat access nahi mila!**\n\n"
                "**Possible reasons:**\n"
                "• Group **Supergroup** nahi hai — Voice Chat sirf supergroups mein kaam karta hai\n"
                "• Assistant ko group mein **admin** banana padega\n"
                "• Assistant pehle group mein **add** nahi hua\n\n"
                "**Fix:** Assistant ko group mein add karo → Admin banao → phir `/play` try karo. 🎵"
            )
            return
        except (json.JSONDecodeError, ProcessLookupError):
            # ROOT CAUSE: ntgcalls race condition.
            #
            # Sequence inside pytgcalls/ffmpeg.py:
            #   1. check_stream() runs ffprobe to verify the stream URL
            #   2. ffprobe exits immediately (ntgcalls call already removed)
            #   3. json.loads(stdout) → JSONDecodeError  (empty stdout)
            #   4. pytgcalls' own except-clause calls ffprobe.kill()
            #   5. Process already gone → ProcessLookupError
            #   6. ProcessLookupError propagates up to our play() call
            #
            # logs mein "Call not found, already removed" WARNING iske saath aata hai.
            # Ye fatal error nahi hai — VC connection play() se pehle drop ho gayi.
            set_current(chat_id, None)
            await _leave_call(chat_id)
            log.warning(
                "ntgcalls race condition in chat %s: call was removed before play() "
                "could start (pytgcalls ffprobe exited early → ProcessLookupError). "
                "User ko retry karna chahiye.",
                chat_id,
            )
            await _safe_edit(
                status_msg,
                "❌ **Voice Chat connection drop ho gayi!**\n\n"
                "Stream shuru hone se pehle Voice Chat band ho gayi.\n"
                "Dobara `/play` try karo — usually 2nd try pe theek ho jaata hai. 🎵"
            )
            return
        except Exception as e:
            set_current(chat_id, None)
            await _leave_call(chat_id)   # VC properly clean karo — warna bot VC mein stuck rehta hai
            err_str = str(e)
            # ntgcalls "call not found" strings — gracefully handle karo
            if any(kw in err_str.lower() for kw in ("not found", "already removed", "ntgcalls")):
                log.warning(
                    "ntgcalls call-not-found error in chat %s: %s",
                    chat_id, e,
                )
                await _safe_edit(
                    status_msg,
                    "❌ **Voice Chat connection problem!**\n\n"
                    "Voice Chat restart ho gayi thi. Dobara `/play` try karo. 🎵"
                )
                return
            if "CHANNEL_INVALID" in err_str or "channel_invalid" in err_str.lower():
                log.warning("Channel invalid (wrapped) in chat %s: %s", chat_id, e)
                await _safe_edit(
                    status_msg,
                    "❌ **Voice Chat access nahi mila!**\n\n"
                    "Assistant ko group mein **Admin** banao, phir `/play` dobara try karo. 🎵"
                )
                return
            log.exception("Playback failed in chat %s", chat_id)
            await _safe_edit(
                status_msg,
                f"❌ **Playback error:**\n`{err_str[:400]}`\n\n"
                "Kuch aur gadbad hai — thodi der mein dobara try karo. 🎵",
            )
            return

        # set_current already called above (before play) — do NOT call again here

        # ── Set volume ─────────────────────────────────────────────
        if chat_id not in _volumes:
            _volumes[chat_id] = int(_VOL_EFFECTIVE * 20)
        asyncio.create_task(_set_volume_bg(chat_id))

        # ── Save to play history (for Autoplay) ──────────────────
        asyncio.create_task(add_play_history(
            chat_id, song.title, song.webpage_url or song.url,
            song.thumbnail, song.duration
        ))

        # ── Now Playing card ─────────────────────────────────────
        vol = _volumes[chat_id]
        q   = queue_size(chat_id)
        ap  = _autoplay.get(chat_id, False)
        np_text = np_card_text(song, chat_id)
        buttons  = now_playing_buttons(song.webpage_url or "", queue_count=q, autoplay=ap, chat_id=chat_id)

        sent_np = None
        deleted_status = False   # BUG FIX: track whether status_msg was deleted

        # Try sending with thumbnail photo
        if song.thumbnail:
            try:
                await _safe_delete(status_msg)
                deleted_status = True
                sent_np = await bot.send_photo(
                    chat_id,
                    photo=song.thumbnail,
                    caption=np_text,
                    reply_markup=buttons,
                )
            except Exception:
                sent_np = None

        if not sent_np:
            if deleted_status:
                # status_msg was deleted — must send a fresh message, editing deleted
                # message raises MessageIdInvalid which _safe_edit silently ignores,
                # causing the user to see nothing (the original "no response" bug).
                try:
                    sent_np = await bot.send_message(chat_id, np_text, reply_markup=buttons)
                except Exception:
                    sent_np = status_msg   # last resort
            else:
                await _safe_edit(status_msg, np_text, buttons)
                sent_np = status_msg

        _np_msgs[chat_id] = sent_np

        # ── Log to channel ────────────────────────────────────────
        asyncio.create_task(_log_play(chat_id, song))


async def _log_play(chat_id: int, song: Song):
    if not LOG_CHANNEL:
        return
    try:
        await bot.send_message(
            LOG_CHANNEL,
            f"**🎵 Now Playing**\n"
            f"💬 Chat: `{chat_id}`\n"
            f"🎶 Song: **{song.title}**\n"
            f"👤 By: {song.requested_by or 'Unknown'}\n"
            f"⏱️ Duration: `{fmt_duration(song.duration)}`"
        )
    except Exception:
        pass


async def _play_command(client: Client, message: Message, is_video: bool = False):
    """Handle /play and /vplay."""
    query = " ".join(message.command[1:]).strip()
    chat_id_early = message.chat.id
    log.info("▶️ /play received | chat=%s | query=%r", chat_id_early, query[:60])

    # Delete user command instantly
    asyncio.create_task(_safe_delete(message))

    if not query:
        reply = await client.send_message(
            message.chat.id,
            "🎵 **Song ka naam ya YouTube link dein!**\n\n"
            "**▶️ Examples:**\n"
            "• `/play Arijit Singh tum hi ho`\n"
            "• `/play https://youtube.com/watch?v=...`\n"
            "• `/vplay <song>` — 720p Video\n"
            "• `/playforce <song>` — ⚡ Queue skip\n\n"
            "> 💡 Song name, YouTube URL — dono kaam karte hain!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Queue", callback_data="queue_cb"),
                InlineKeyboardButton("🎵 Now Playing", callback_data="np_refresh"),
            ]])
        )
        asyncio.create_task(_auto_delete(reply, 6))
        return

    kind_text = "🎬 Video" if is_video else "🎵 Audio"

    # ── Step 1 animation ─────────────────────────────────────────
    status_msg = await client.send_message(
        message.chat.id,
        f"🔍 **{kind_text} Search ho raha hai...**\n\n"
        f"🎵 `{query[:60]}`\n\n"
        f"⏳ _Thoda wait karo, dhundh raha hun!_"
    )

    # ⚡ SPEED FIX: VC join background mein start karo JABKI search chal raha hai
    # Agar assistant already in group hai → 0.3s mein done (sirf get_chat check)
    # Agar naya group hai → join bhi search ke saath parallel hota hai
    # _do_play_inner mein bhi _join_vc() call hota hai — idempotent hai, instantly returns True
    chat_id = message.chat.id
    asyncio.create_task(_join_vc(chat_id))

    # BUG FIX: asyncio.wait_for 45s timeout — bina iske yt-dlp ka ytsearch1: call
    # cloud IPs pe hang karta tha, status message hamesha "🔍 Searching..." pe
    # stuck rehta tha. Ab 45s mein timeout ho jaayega aur clear error milega.
    try:
        from helpers.youtube import search_song
        requested_by = message.from_user.mention if message.from_user else "Unknown"
        cached_song = None if is_video else await _find_cached_song(query, requested_by)
        if cached_song:
            song = cached_song
            song.is_video = is_video
            log.info("⚡ Archive hit | query=%r | title=%s", query[:50], song.title[:70])
            song_info = None
        else:
            song_info = await asyncio.wait_for(
                search_song(query, is_video=is_video),
                timeout=45.0,
            )
    except asyncio.TimeoutError:
        await _safe_edit(
            status_msg,
            f"⏱️ **Search timeout!** YouTube respond nahi kar raha.\n\n"
            f"💡 **Fix:** Heroku mein `YOUTUBE_COOKIES` set karo\n"
            f"Ya seedha YouTube link deke try karo:\n"
            f"`/play https://youtube.com/watch?v=...`"
        )
        return
    except Exception as e:
        await _safe_edit(status_msg, f"❌ **Search error:**\n`{e}`")
        return

    if not cached_song and (
        not song_info or (not song_info.get("url") and not song_info.get("webpage_url"))
    ):
        await _safe_edit(
            status_msg,
            f"❌ **Nahi mila:** `{query[:50]}`\n\n"
            "Try: exact song name ya YouTube link dein! 🎵"
        )
        return

    if not cached_song:
        song = Song(
            title        = song_info.get("title", query),
            url          = song_info.get("url", ""),
            duration     = song_info.get("duration", 0),
            is_video     = is_video,
            requested_by = requested_by,
            webpage_url  = song_info.get("webpage_url", ""),
            thumbnail    = song_info.get("thumbnail", ""),
            http_headers = song_info.get("http_headers", {}),
            artist       = song_info.get("uploader", "") or song_info.get("channel", ""),
        )
        # Flat search returns metadata quickly. Resolve the signed media URL
        # while Telegram/UI work continues so _do_play can consume the shared
        # task instead of waiting for extraction after the search completes.
        prefetch_stream(song.webpage_url, is_video=is_video)

    # chat_id already set above (before search, for VC pre-join task)
    current = get_current(chat_id)

    if current:
        pos = add_to_queue(chat_id, song)
        _schedule_prefetch(song)
        title_short = (song.title[:55] + "…") if len(song.title) > 55 else song.title
        await _safe_edit(
            status_msg,
            f"📋 **Queue #{pos} mein add ho gaya!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎶 **{title_short}**\n"
            f"⏱️ `{fmt_duration(song.duration)}`\n"
            f"👤 {requested_by}\n\n"
            f"> ⏳ Position: **#{pos}** in queue\n"
            f"> 🎵 _Ab chal raha hai phir aayegi tumhari song!_",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Queue Dekho", callback_data="queue_cb"),
                InlineKeyboardButton("⏭️ Skip Current", callback_data="skip"),
            ]])
        )
        return

    asyncio.create_task(_do_play(chat_id, song, status_msg, is_video))


# ══ COMMANDS ══════════════════════════════════════════════════════

@Client.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(client: Client, message: Message):
    await _play_command(client, message, is_video=False)


@Client.on_message(filters.command(["vplay", "vp"]) & filters.group)
async def vplay_cmd(client: Client, message: Message):
    await _play_command(client, message, is_video=True)


@Client.on_message(filters.command(["playforce", "pf", "fplay"]) & filters.group)
async def playforce_cmd(client: Client, message: Message):
    """Skip current and play immediately — no queue."""
    query = " ".join(message.command[1:]).strip()
    asyncio.create_task(_safe_delete(message))

    if not query:
        r = await client.send_message(message.chat.id, "⚡ **PlayForce:** Song naam ya link dein!")
        asyncio.create_task(_auto_delete(r, 4))
        return

    chat_id = message.chat.id
    status_msg = await client.send_message(
        message.chat.id,
        f"⚡ **PlayForce — Instant Play!**\n🔍 Dhundh raha hun...\n🎶 `{query[:60]}`"
    )

    # Stop current + clear queue
    clear_queue(chat_id)
    try:
        await call_py.leave_call(chat_id)
    except Exception:
        pass
    # SPEED FIX: 0.5s → 0.1s — leave_call propagation is near-instant
    await asyncio.sleep(0.1)

    try:
        from helpers.youtube import search_song
        song_info = await asyncio.wait_for(
            search_song(query, is_video=False),
            timeout=45.0,
        )
    except asyncio.TimeoutError:
        await _safe_edit(status_msg, "⏱️ **Search timeout!** Seedha YouTube link try karo.")
        return
    except Exception as e:
        await _safe_edit(status_msg, f"❌ **Search error:**\n`{e}`")
        return

    if not song_info or (not song_info.get("url") and not song_info.get("webpage_url")):
        await _safe_edit(status_msg, f"❌ **Nahi mila:** `{query[:50]}`")
        return

    requested_by = message.from_user.mention if message.from_user else "Unknown"
    song = Song(
        title        = song_info.get("title", query),
        url          = song_info.get("url", ""),
        duration     = song_info.get("duration", 0),
        is_video     = False,
        requested_by = requested_by,
        webpage_url  = song_info.get("webpage_url", ""),
        thumbnail    = song_info.get("thumbnail", ""),
        http_headers = song_info.get("http_headers", {}),
    )
    prefetch_stream(song.webpage_url, is_video=False)
    asyncio.create_task(_do_play(chat_id, song, status_msg, False))


@Client.on_message(filters.command(["pause"]) & filters.group)
async def pause_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    if not current:
        r = await client.send_message(chat_id, "❌ **Abhi kuch chal nahi raha!**\n\n`/play <song>` se start karo! 🎵")
        asyncio.create_task(_auto_delete(r, 4))
        return
    try:
        await call_py.pause(chat_id)
        _paused[chat_id] = True   # BUG FIX: track paused state
        # Update NP card if it exists
        np_msg = _np_msgs.get(chat_id)
        if np_msg:
            asyncio.create_task(_safe_edit(
                np_msg,
                np_card_text(current, chat_id),
                now_playing_buttons(current.webpage_url or "", paused=True, queue_count=queue_size(chat_id), autoplay=_autoplay.get(chat_id, False), chat_id=chat_id)
            ))
        r = await client.send_message(
            chat_id,
            f"⏸️ **Paused!**\n\n"
            f"🎶 _{current.title[:55]}_\n\n"
            f"`/resume` se dobara chalao ▶️",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ Resume", callback_data="resume"),
                InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
            ]])
        )
        asyncio.create_task(_auto_delete(r, 4))
    except Exception as e:
        r = await client.send_message(chat_id, f"❌ `{e}`")
        asyncio.create_task(_auto_delete(r, 3))


@Client.on_message(filters.command(["resume"]) & filters.group)
async def resume_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    if not current:
        r = await client.send_message(chat_id, "❌ **Queue khaali hai!**\n\n`/play <song>` se start karo! 🎵")
        asyncio.create_task(_auto_delete(r, 4))
        return
    try:
        await call_py.resume(chat_id)
        _paused[chat_id] = False   # BUG FIX: clear paused state on resume
        # Update NP card if it exists
        np_msg = _np_msgs.get(chat_id)
        if np_msg:
            asyncio.create_task(_safe_edit(
                np_msg,
                np_card_text(current, chat_id),
                now_playing_buttons(current.webpage_url or "", paused=False, queue_count=queue_size(chat_id), autoplay=_autoplay.get(chat_id, False), chat_id=chat_id)
            ))
        r = await client.send_message(
            chat_id,
            f"▶️ **Resumed!**\n\n🎶 _{current.title}_",
        )
        asyncio.create_task(_auto_delete(r, 4))
    except Exception as e:
        r = await client.send_message(chat_id, f"❌ `{e}`")
        asyncio.create_task(_auto_delete(r, 3))


@Client.on_message(filters.command(["skip", "next", "s"]) & filters.group)
async def skip_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    next_song = pop_queue(chat_id)
    if not next_song:
        clear_queue(chat_id)
        asyncio.create_task(_leave_call(chat_id))
        r = await client.send_message(
            chat_id,
            "⏭️ **Skipped!**\n\n📋 Queue khaali hai — ab aur koi song nahi!\n`/play <song>` se nayi playlist banao. 🎵"
        )
        asyncio.create_task(_auto_delete(r, 5))
        return

    status_msg = await client.send_message(
        chat_id,
        f"⏭️ **Skipping...**\n🔍 Next song load ho raha hai...\n\n🎶 **{next_song.title}**"
    )
    asyncio.create_task(_do_play(chat_id, next_song, status_msg, next_song.is_video))


@Client.on_message(filters.command(["stop", "end"]) & filters.group)
async def stop_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    q = queue_size(chat_id)
    clear_queue(chat_id)
    asyncio.create_task(_leave_call(chat_id))
    _loop_enabled.pop(chat_id, None)
    r = await client.send_message(
        chat_id,
        f"⏹️ **Music Band Kar Diya!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 **{q}** song{'s' if q != 1 else ''} queue se remove\n"
        f"🎵 `/play <song>` se dobara shuru karo!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Play Again", switch_inline_query_current_chat="/play "),
        ]])
    )
    asyncio.create_task(_auto_delete(r, 5))


@Client.on_message(filters.command(["vol", "volume", "v"]) & filters.group)
async def vol_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    args = message.command[1:]

    if not args:
        cur = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
        vbar = _vol_bar(cur)
        await client.send_message(
            chat_id,
            f"🔊 **Volume Control**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> Current: `{vbar}` **{cur}%**\n\n"
            f"Range: `0 – 200` · `/vol 150`\n"
            f"💥 `/vol 200` = Maximum Boost!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔉 Vol−20", callback_data="vol_down"),
                InlineKeyboardButton("🔊 Vol+20", callback_data="vol_up"),
            ]]),
        )
        return

    try:
        vol = max(0, min(200, int(args[0])))
    except ValueError:
        r = await client.send_message(chat_id, "❌ `/vol 0-200` — number dein!")
        asyncio.create_task(_auto_delete(r, 3))
        return

    _volumes[chat_id] = vol
    asyncio.create_task(_set_volume_bg(chat_id))
    vbar = _vol_bar(vol)
    emoji = "🔇" if vol == 0 else "🔉" if vol < 80 else "🔊" if vol < 160 else "📢"
    label = " 🔇 Muted!" if vol == 0 else " 🔥 Max Boost!" if vol >= 200 else ""
    r = await client.send_message(
        chat_id,
        f"{emoji} **Volume: `{vol}%`**{label}\n"
        f"`{vbar}`"
    )
    asyncio.create_task(_auto_delete(r, 3))


@Client.on_message(filters.command(["queue", "q"]) & filters.group)
async def queue_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    queue   = get_queue(chat_id)

    if not current and not queue:
        r = await client.send_message(
            chat_id,
            "📋 **Queue Khaali Hai!**\n\n"
            "> 🎵 Abhi koi song queue mein nahi hai\n\n"
            "`/play <song>` likho aur music start karo! 🔥",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ Play Something", switch_inline_query_current_chat="/play "),
            ]])
        )
        asyncio.create_task(_auto_delete(r, 6))
        return

    lines = ["**📋 Music Queue**\n━━━━━━━━━━━━━━━━━━━━━━\n"]
    if current:
        kind = "🎬" if current.is_video else "🎵"
        lines.append(
            f"**▶️ Ab Chal Raha Hai:**\n"
            f"{kind} **{current.title[:50]}** `[{fmt_duration(current.duration)}]`\n"
            f"👤 _{current.requested_by}_\n"
        )
    if queue:
        lines.append(f"**⏳ Queue ({len(queue)} song{'s' if len(queue)!=1 else ''}):**")
        for i, s in enumerate(queue[:15], 1):
            kind = "🎬" if s.is_video else "🎵"
            dur  = fmt_duration(s.duration)
            title = s.title[:38] + ("…" if len(s.title) > 38 else "")
            lines.append(f"`{i:>2}.` {kind} {title} `[{dur}]`")
        if len(queue) > 15:
            lines.append(f"\n_...aur **{len(queue)-15}** songs hain_")

    await client.send_message(
        chat_id,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
                InlineKeyboardButton("🔀 Shuffle", callback_data="shuffle_cb"),
                InlineKeyboardButton("⏹️ Stop", callback_data="stop"),
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="np_refresh"),
            ]
        ])
    )


@Client.on_message(filters.command(["np", "now", "song"]) & filters.group)
async def np_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    if not current:
        r = await client.send_message(
            chat_id,
            "🎵 **Abhi Koi Song Nahi Chal Raha**\n\n"
            "> Queue bilkul khaali hai!\n\n"
            "`/play <song>` se music start karo! 🔥",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ Play Now", switch_inline_query_current_chat="/play "),
            ]])
        )
        asyncio.create_task(_auto_delete(r, 6))
        return

    np_text = np_card_text(current, chat_id)
    buttons  = now_playing_buttons(
        current.webpage_url or "",
        paused=_paused.get(chat_id, False),
        queue_count=queue_size(chat_id),
        autoplay=_autoplay.get(chat_id, False),
        chat_id=chat_id,
    )

    if current.thumbnail:
        try:
            await bot.send_photo(
                chat_id,
                photo=current.thumbnail,
                caption=np_text,
                reply_markup=buttons,
            )
            return
        except Exception:
            pass

    await client.send_message(chat_id, np_text, reply_markup=buttons)


@Client.on_message(filters.command(["shuffle"]) & filters.group)
async def shuffle_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    count = shuffle_queue(chat_id)
    if not count:
        r = await client.send_message(chat_id, "❌ Queue khaali hai — shuffle kya karein? 😅")
        asyncio.create_task(_auto_delete(r, 3))
        return
    r = await client.send_message(
        chat_id,
        f"🔀 **Queue shuffle ho gaya!** `{count}` songs.\n_Maza aayega ab!_ 🎵"
    )
    asyncio.create_task(_auto_delete(r, 4))


@Client.on_message(filters.command(["loop"]) & filters.group)
async def loop_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    _loop_enabled[chat_id] = not _loop_enabled.get(chat_id, False)
    state = _loop_enabled[chat_id]
    r = await client.send_message(
        chat_id,
        f"🔁 **Loop: {'ON ✅' if state else 'OFF ❌'}**\n\n"
        + (f"_Current song repeat hoti rahegi!_" if state else "_Loop band kar diya._")
    )
    asyncio.create_task(_auto_delete(r, 4))


# ── Stream ended → auto-next ──────────────────────────────────────

async def _retry_stream(chat_id: int, song: Song):
    """Retry playing a song after an immediate EOF (expired/bad CDN URL).

    Called from on_stream_end when the stream ended within PREMATURE_END_THRESHOLD
    seconds — a signal that the CDN URL was expired or blocked, not that the song
    genuinely finished.  Forces a fresh yt-dlp fetch (bypassing the URL cache) and
    restarts playback.  Stops after MAX_STREAM_RETRIES to avoid infinite loops.
    """
    retry_count = _stream_retry_counts.get(chat_id, 0)
    if retry_count >= MAX_STREAM_RETRIES:
        log.warning(
            "❌ Max stream retries (%d) reached for chat %s, giving up",
            MAX_STREAM_RETRIES, chat_id,
        )
        clear_queue(chat_id)
        await _leave_call(chat_id)
        try:
            await bot.send_message(
                chat_id,
                "❌ **Stream baar baar fail ho rahi hai!**\n\n"
                "YouTube CDN URL expire/block ho rahi hai.\n"
                "Thodi der baad dobara `/play` karo. 🎵"
            )
        except Exception:
            pass
        return

    _stream_retry_counts[chat_id] = retry_count + 1
    # Drop the cached (expired) URL so get_stream() fetches a fresh one.
    source = song.webpage_url or song.url
    if source:
        clear_cache_for_url(source, song.is_video)

    # ⚡ SPEED FIX: Mark CDN as blocked so ALL future plays skip CDN probing
    # and go straight to Invidious/download race. One premature EOF is enough
    # evidence that this server IP is CDN-blocked (Heroku, Railway, etc.).
    mark_cdn_blocked()

    log.info(
        "🔄 Stream retry %d/%d for chat %s | song=%s",
        retry_count + 1, MAX_STREAM_RETRIES, chat_id, song.title[:50],
    )
    try:
        status_msg = await bot.send_message(
            chat_id,
            f"🔄 **Auto-retry {retry_count + 1}/{MAX_STREAM_RETRIES}...**\n"
            f"🎶 **{song.title[:55]}**\n"
            f"_Fresh stream URL fetch ho rahi hai..._"
        )
        await _do_play(chat_id, song, status_msg, song.is_video, force_refresh=True)
    except Exception as e:
        log.warning("Stream retry failed for chat %s: %s", chat_id, e)
        clear_queue(chat_id)
        asyncio.create_task(_leave_call(chat_id))


async def _auto_next(chat_id: int, song: Song):
    try:
        status_msg = await bot.send_message(
            chat_id,
            f"🔍 **Auto-next load ho raha hai...**\n🎶 {song.title}"
        )
        await _do_play(chat_id, song, status_msg, song.is_video)
    except Exception as e:
        log.warning(f"_auto_next {chat_id}: {e}")


async def _autoplay_next(chat_id: int):
    """Pick a random song from history and play it (autoplay mode)."""
    try:
        count = await get_history_count(chat_id)
        if count == 0:
            asyncio.create_task(_leave_call(chat_id))
            return
        song_info = await get_random_history_song(chat_id)
        if not song_info or not song_info.get("webpage_url"):
            asyncio.create_task(_leave_call(chat_id))
            return
        song = Song(
            title       = song_info["title"],
            url         = "",
            webpage_url = song_info["webpage_url"],
            thumbnail   = song_info.get("thumbnail", ""),
            duration    = song_info.get("duration", 0),
            requested_by= "🎲 Autoplay",
            is_video    = False,
        )
        status_msg = await bot.send_message(
            chat_id,
            f"🎲 **Autoplay — Random Song!**\n🔍 Load ho raha hai...\n\n🎶 **{song.title[:55]}**"
        )
        await _do_play(chat_id, song, status_msg, False)
    except Exception as e:
        log.warning(f"_autoplay_next {chat_id}: {e}")
        asyncio.create_task(_leave_call(chat_id))


@call_py.on_update(tgfilters.stream_end())
async def on_stream_end(client: PyTgCalls, update: StreamEnded):
    """Never await Telegram calls here — use create_task to prevent
    recursive MTProto update propagation (pytgcalls 2.x known issue)."""
    chat_id = update.chat_id
    current = get_current(chat_id)

    # Cleanup any local temp file used by the stream that just ended
    _local = _stream_local_files.pop(chat_id, None)
    if _local:
        cleanup_temp_file(_local)

    # ── Premature-end detection (expired / bad CDN URL) ───────────
    # If a stream ends within PREMATURE_END_THRESHOLD seconds of starting,
    # and the song had a real duration > 30s, it almost certainly hit an
    # immediate EOF caused by an expired or IP-blocked CDN URL (the
    # "bot 1 sec pe aake chala gaya" bug).  Retry with a fresh URL instead
    # of advancing the queue or leaving VC.
    elapsed = _time.monotonic() - _play_start_times.get(chat_id, 0)
    if (
        current
        and elapsed < PREMATURE_END_THRESHOLD
        and (current.duration or 0) > 30
        and not _loop_enabled.get(chat_id)
    ):
        log.warning(
            "⚡ Premature stream end detected | chat=%s | elapsed=%.1fs | song=%s — retrying",
            chat_id, elapsed, current.title[:50],
        )
        asyncio.create_task(_retry_stream(chat_id, current))
        return

    # ── Loop mode — replay current ────────────────────────────────
    if _loop_enabled.get(chat_id) and current:
        asyncio.create_task(_auto_next(chat_id, current))
        return

    # ── Normal end — advance queue ────────────────────────────────
    next_song = pop_queue(chat_id)
    if not next_song:
        # Autoplay mode — play random song from history
        if _autoplay.get(chat_id, False):
            asyncio.create_task(_autoplay_next(chat_id))
        else:
            clear_queue(chat_id)
            asyncio.create_task(_leave_call(chat_id))
        return
    asyncio.create_task(_auto_next(chat_id, next_song))


# ══ CALLBACK BUTTONS ══════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^(pause|resume|skip|stop)$"))
async def cb_controls(client, cq):
    action  = cq.data
    chat_id = cq.message.chat.id

    if action == "pause":
        await cq.answer("⏸️ Paused!")
        try:
            await call_py.pause(chat_id)
            _paused[chat_id] = True   # BUG FIX: track paused state via button too
            current = get_current(chat_id)
            if current:
                await _safe_edit(
                    cq.message,
                    np_card_text(current, chat_id),
                    now_playing_buttons(current.webpage_url or "", paused=True, queue_count=queue_size(chat_id), autoplay=_autoplay.get(chat_id, False), chat_id=chat_id)
                )
        except Exception:
            pass

    elif action == "resume":
        await cq.answer("▶️ Resumed!")
        try:
            await call_py.resume(chat_id)
            _paused[chat_id] = False   # BUG FIX: clear paused state via button too
            current = get_current(chat_id)
            if current:
                await _safe_edit(
                    cq.message,
                    np_card_text(current, chat_id),
                    now_playing_buttons(current.webpage_url or "", paused=False, queue_count=queue_size(chat_id), autoplay=_autoplay.get(chat_id, False), chat_id=chat_id)
                )
        except Exception:
            pass

    elif action == "skip":
        await cq.answer("⏭️ Skipping...")
        next_song = pop_queue(chat_id)
        if not next_song:
            clear_queue(chat_id)
            asyncio.create_task(_leave_call(chat_id))
            await _safe_edit(cq.message, "⏹️ **Queue khatam! Sab songs bajaa diye.** 🎵")
        else:
            await _safe_edit(
                cq.message,
                f"🔍 **Loading next...**\n🎶 **{next_song.title}**"
            )
            asyncio.create_task(_do_play(chat_id, next_song, cq.message, next_song.is_video))

    elif action == "stop":
        await cq.answer("⏹️ Stopping...")
        q = queue_size(chat_id)
        clear_queue(chat_id)
        _loop_enabled.pop(chat_id, None)
        asyncio.create_task(_leave_call(chat_id))
        await _safe_edit(
            cq.message,
            f"⏹️ **Music Band Kar Diya!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 **{q}** song{'s' if q != 1 else ''} queue se remove\n"
            f"🎵 `/play <song>` se dobara shuru karo!",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ Play Again", switch_inline_query_current_chat="/play "),
            ]])
        )


@Client.on_callback_query(filters.regex("^vol_(up|down)$"))
async def cb_volume(client, cq):
    chat_id = cq.message.chat.id
    cur     = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
    new_vol = min(200, cur + 20) if "up" in cq.data else max(0, cur - 20)
    _volumes[chat_id] = new_vol
    asyncio.create_task(_set_volume_bg(chat_id))
    await cq.answer(f"🔊 Volume: {new_vol}%" + (" 🔥 MAX!" if new_vol >= 200 else ""))

    # Refresh NP card
    current = get_current(chat_id)
    if current:
        try:
            await _safe_edit(
                cq.message,
                np_card_text(current, chat_id),
                now_playing_buttons(current.webpage_url or "", queue_count=queue_size(chat_id), autoplay=_autoplay.get(chat_id, False), chat_id=chat_id)
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex("^queue_cb$"))
async def cb_queue(client, cq):
    await cq.answer()
    chat_id = cq.message.chat.id
    current = get_current(chat_id)
    queue   = get_queue(chat_id)
    if not current and not queue:
        return await cq.answer("📋 Queue khaali hai!", show_alert=True)
    lines = ["**📋 Music Queue**\n"]
    if current:
        kind = "🎬" if current.is_video else "🎵"
        lines.append(f"**▶️ Playing:** {kind} **{current.title[:40]}** `[{fmt_duration(current.duration)}]`")
    if queue:
        lines.append(f"\n**⏳ Next ({len(queue)}):**")
        for i, s in enumerate(queue[:10], 1):
            kind = "🎬" if s.is_video else "🎵"
            lines.append(f"`{i:>2}.` {kind} {s.title[:35]} `[{fmt_duration(s.duration)}]`")
        if len(queue) > 10:
            lines.append(f"_...+{len(queue)-10} more_")
    await cq.message.reply(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
            InlineKeyboardButton("🔀 Shuffle", callback_data="shuffle_cb"),
            InlineKeyboardButton("⏹️ Stop", callback_data="stop"),
        ]])
    )


@Client.on_callback_query(filters.regex("^shuffle_cb$"))
async def cb_shuffle(client, cq):
    chat_id = cq.message.chat.id
    count = shuffle_queue(chat_id)
    if not count:
        return await cq.answer("📋 Queue khaali hai!", show_alert=True)
    await cq.answer(f"🔀 Shuffled {count} songs!")


@Client.on_callback_query(filters.regex("^loop_cb$"))
async def cb_loop(client, cq):
    chat_id = cq.message.chat.id
    _loop_enabled[chat_id] = not _loop_enabled.get(chat_id, False)
    state = _loop_enabled[chat_id]
    await cq.answer(f"🔁 Loop: {'ON ✅' if state else 'OFF ❌'}", show_alert=True)

    # Refresh NP card
    current = get_current(chat_id)
    if current:
        try:
            await _safe_edit(
                cq.message,
                np_card_text(current, chat_id),
                now_playing_buttons(current.webpage_url or "", queue_count=queue_size(chat_id), autoplay=_autoplay.get(chat_id, False), chat_id=chat_id)
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex("^autoplay_cb$"))
async def cb_autoplay(client, cq):
    chat_id = cq.message.chat.id
    # Toggle in-memory cache
    new_state = not _autoplay.get(chat_id, False)
    _autoplay[chat_id] = new_state
    # Persist to DB
    asyncio.create_task(set_autoplay(chat_id, new_state))

    count = await get_history_count(chat_id)
    state_text = "ON ✅" if new_state else "OFF ❌"
    await cq.answer(
        f"🎲 Autoplay: {state_text}" +
        (f" ({count} songs in history)" if new_state and count else ""),
        show_alert=new_state and count == 0
    )
    if new_state and count == 0:
        await cq.answer(
            "⚠️ History khaali hai! Pehle kuch songs play karo — phir autoplay random songs chalayega.",
            show_alert=True,
        )

    # Refresh NP card
    current = get_current(chat_id)
    if current:
        try:
            await _safe_edit(
                cq.message,
                np_card_text(current, chat_id),
                now_playing_buttons(current.webpage_url or "", queue_count=queue_size(chat_id), autoplay=new_state, chat_id=chat_id)
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex("^np_refresh$"))
async def cb_np_refresh(client, cq):
    chat_id = cq.message.chat.id
    current = get_current(chat_id)
    if not current:
        return await cq.answer("❌ Abhi kuch nahi chal raha!", show_alert=True)
    await cq.answer("🔄 Refreshed!")
    # Sync autoplay state from DB on refresh
    _autoplay[chat_id] = await get_autoplay(chat_id)
    try:
        await _safe_edit(
            cq.message,
            np_card_text(current, chat_id),
            now_playing_buttons(current.webpage_url or "", queue_count=queue_size(chat_id), autoplay=_autoplay.get(chat_id, False), chat_id=chat_id)
        )
    except Exception:
        pass


@Client.on_message(filters.command(["autoplay", "ap"]) & filters.group)
async def autoplay_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    new_state = not _autoplay.get(chat_id, False)
    # If first use, sync from DB
    if chat_id not in _autoplay:
        new_state = not await get_autoplay(chat_id)
    _autoplay[chat_id] = new_state
    asyncio.create_task(set_autoplay(chat_id, new_state))

    count = await get_history_count(chat_id)
    state_emoji = "✅" if new_state else "❌"
    r = await client.send_message(
        chat_id,
        f"🎲 **Autoplay: {state_emoji} {'ON' if new_state else 'OFF'}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        + (
            f"Queue khatam hone ke baad **{count}** songs mein se\nrandom song automatically play hoga! 🎵\n\n"
            f"_Jitna zyada songs play karoge, utna better random selection._"
            if new_state and count > 0 else
            f"⚠️ History abhi khaali hai!\nPehle kuch songs play karo, phir autoplay kaam karega. 🎵"
            if new_state and count == 0 else
            f"_Autoplay band kar diya. Queue khatam hone par bot VC chhod dega._"
        ),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"🎲 Autoplay {'Band Karo' if new_state else 'Chalu Karo'}",
                callback_data="autoplay_cb"
            )
        ]])
    )
    asyncio.create_task(_auto_delete(r, 8))
