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
import os
import logging
import random

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified, MessageIdInvalid, FloodWait
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from pytgcalls import PyTgCalls, filters as tgfilters
from pytgcalls.types import MediaStream, AudioQuality, VideoQuality, StreamEnded
# BUG FIX: AlreadyJoinedError py-tgcalls 2.x mein exist nahi karta — import hataaya.
# Isko ab generic Exception + string check se handle kiya jaata hai _do_play() mein.
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError

from clients import bot, assistant, call_py
from helpers.queue import (
    Song, add_to_queue, get_current, set_current,
    queue_size, pop_queue, get_queue, clear_queue, is_active, shuffle_queue,
)
from helpers.youtube import get_stream, fmt_duration
from config import DOWNLOAD_DIR, FFMPEG_VOLUME_BOOST, LOG_CHANNEL, OWNER_USERNAME, BOT_NAME

log = logging.getLogger("ApexBot.play")

_VOL_EFFECTIVE = min(float(FFMPEG_VOLUME_BOOST), 10.0)

# ── Loop store ────────────────────────────────────────────────────
_loop_enabled: dict[int, bool] = {}

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


# ── Assistant ID cache ────────────────────────────────────────────
_asst_id: int | None = None

async def _get_asst_id() -> int:
    global _asst_id
    if _asst_id is None:
        me = await assistant.get_me()
        _asst_id = me.id
    return _asst_id


# ── Volume + lock stores ──────────────────────────────────────────
_volumes:    dict[int, int]         = {}
_play_locks: dict[int, asyncio.Lock] = {}
_np_msgs:    dict[int, any]         = {}   # store last NP message per chat


def _get_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _play_locks:
        _play_locks[chat_id] = asyncio.Lock()
    return _play_locks[chat_id]


# ══ MUSIC CARD UI ══════════════════════════════════════════════════

def now_playing_buttons(url: str = "", paused: bool = False, queue_count: int = 0) -> InlineKeyboardMarkup:
    toggle = (
        InlineKeyboardButton("▶️ Resume", callback_data="resume")
        if paused else
        InlineKeyboardButton("⏸️ Pause", callback_data="pause")
    )
    queue_label = f"📋 Queue ({queue_count})" if queue_count > 0 else "📋 Queue"
    rows = [
        [
            toggle,
            InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
            InlineKeyboardButton("⏹️ Stop", callback_data="stop"),
        ],
        [
            InlineKeyboardButton("🔉 Vol −", callback_data="vol_down"),
            InlineKeyboardButton(queue_label, callback_data="queue_cb"),
            InlineKeyboardButton("🔊 Vol +", callback_data="vol_up"),
        ],
        [
            InlineKeyboardButton("🔀 Shuffle", callback_data="shuffle_cb"),
            InlineKeyboardButton("🔁 Loop", callback_data="loop_cb"),
            InlineKeyboardButton("🔄 Refresh", callback_data="np_refresh"),
        ],
    ]
    if url and url.startswith("http"):
        rows.append([InlineKeyboardButton("🎬 YouTube pe Dekho", url=url)])
    return InlineKeyboardMarkup(rows)


def np_card_text(song: Song, chat_id: int = 0) -> str:
    """Professional now playing card — Telegram blockquote style."""
    kind_emoji = "🎬" if song.is_video else "🎵"
    vol  = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
    loop = "🔁 ON" if _loop_enabled.get(chat_id) else "OFF"
    q    = queue_size(chat_id)
    q_text = f"{q} songs" if q > 0 else "khaali"
    return (
        f"**{kind_emoji} NOW PLAYING** 🔥\n\n"
        f"> 🎶 **{song.title}**\n"
        f"> ⏱️ `{fmt_duration(song.duration)}`\n"
        f"> 🔊 Volume: `{vol}%`\n"
        f"> 👤 {song.requested_by or 'Unknown'}\n"
        f"> 📋 Queue: `{q_text}`\n"
        f"> 🔁 Loop: `{loop}`"
    )


# ═══ CORE PLAY LOGIC ═══════════════════════════════════════════════

async def _join_vc(chat_id: int):
    """Ensure assistant is in the group VC."""
    try:
        await assistant.get_chat(chat_id)
    except Exception:
        pass
    try:
        await assistant.join_chat(chat_id)
    except Exception:
        pass


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


async def _do_play(chat_id: int, song: Song, status_msg, is_video: bool = False):
    """Core: resolve stream → join VC → start playback → show NP card."""
    async with _get_lock(chat_id):

        # ── Step 2 animation: Found! Loading... ──────────────────
        await _safe_edit(
            status_msg,
            f"🎯 **Mil gaya!** Loading stream...\n\n"
            f"🎶 **{song.title[:60]}**\n"
            f"⏱️ `{fmt_duration(song.duration)}`"
        )

        # BUG FIX: hamesha webpage_url se fresh stream fetch karo.
        # song.url direct CDN URL hota hai jo expire ho sakta hai.
        # get_stream() cache check karta hai → fresh rehne par instant return,
        # expire hone par auto re-fetch. Headers bhi milte hain.
        source = song.webpage_url or song.url
        if not source:
            await _safe_edit(status_msg, "❌ **Source URL khaali hai.**\nKoi aur song try karo! 🎵")
            return

        try:
            stream_url, dur, http_headers = await get_stream(source, is_video=is_video)
            if dur and not song.duration:
                song.duration = dur
        except Exception as e:
            await _safe_edit(status_msg, f"❌ **Stream nahi mila:**\n`{e}`\n\nDusra song try karo! 🎵")
            return

        if not stream_url:
            await _safe_edit(status_msg, "❌ **Stream URL khaali hai.**\nKoi aur song try karo! 🎵")
            return

        # ── Step 3 animation: Connecting to VC ───────────────────
        await _safe_edit(
            status_msg,
            f"⚡ **Voice Chat connect ho raha hai...**\n\n"
            f"🎶 **{song.title[:60]}**"
        )

        # Ensure assistant is in VC
        await _join_vc(chat_id)
        await asyncio.sleep(0.4)

        # ── Build & start stream ──────────────────────────────────
        # BUG FIX: http_headers MediaStream ko pass karo.
        # YouTube DASH CDN URLs bina User-Agent/origin headers ke 403 deta hai.
        try:
            if is_video:
                stream = MediaStream(
                    stream_url,
                    audio_parameters=AudioQuality.HIGH,
                    video_parameters=VideoQuality.FHD_1080p,
                    ffmpeg_parameters=_ffmpeg_params(),
                    headers=http_headers or None,
                )
            else:
                stream = MediaStream(
                    stream_url,
                    audio_parameters=AudioQuality.HIGH,
                    ffmpeg_parameters=_ffmpeg_params(),
                    headers=http_headers or None,
                )
            await call_py.play(chat_id, stream)

        except NoActiveGroupCall:
            await _safe_edit(
                status_msg,
                "❌ **Voice Chat band hai!**\n\n"
                "Group Settings → Voice Chats → **Start** karo pehle,\nphir `/play` dobara karo. 🎵"
            )
            return
        except Exception as e:
            # BUG FIX: AlreadyJoinedError py-tgcalls 2.x mein nahi hai — string se check
            if "already" in str(e).lower():
                pass  # Already in call — continue, playback shuru ho gaya
            else:
                await _safe_edit(status_msg, f"❌ **Playback error:**\n`{e}`")
                return

        set_current(chat_id, song)

        # ── Set volume ─────────────────────────────────────────────
        if chat_id not in _volumes:
            _volumes[chat_id] = int(_VOL_EFFECTIVE * 20)
        asyncio.create_task(_set_volume_bg(chat_id))

        # ── Now Playing card ─────────────────────────────────────
        vol = _volumes[chat_id]
        q   = queue_size(chat_id)
        np_text = np_card_text(song, chat_id)
        buttons  = now_playing_buttons(song.webpage_url or "", queue_count=q)

        sent_np = None
        # Try sending with thumbnail photo
        if song.thumbnail:
            try:
                await _safe_delete(status_msg)
                sent_np = await bot.send_photo(
                    chat_id,
                    photo=song.thumbnail,
                    caption=np_text,
                    reply_markup=buttons,
                )
            except Exception:
                sent_np = None

        if not sent_np:
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

    # Delete user command instantly
    asyncio.create_task(_safe_delete(message))

    if not query:
        reply = await client.send_message(
            message.chat.id,
            "🎵 **Song ka naam ya link dein!**\n\n"
            "**Examples:**\n"
            "`/play Arijit Singh tum hi ho`\n"
            "`/play https://youtube.com/watch?v=...`\n"
            "`/vplay <song>` — 1080p video ke liye\n\n"
            "💡 YouTube, Spotify links bhi kaam karte hain!",
        )
        await asyncio.sleep(6)
        asyncio.create_task(_safe_delete(reply))
        return

    kind_text = "🎬 Video" if is_video else "🎵 Audio"

    # ── Step 1 animation ─────────────────────────────────────────
    status_msg = await client.send_message(
        message.chat.id,
        f"🔍 **{kind_text} dhundh raha hun...**\n\n"
        f"🎶 `{query[:60]}`\n\n"
        f"_Please wait..._"
    )

    try:
        from helpers.youtube import search_song
        song_info = await search_song(query, is_video=is_video)
    except Exception as e:
        await _safe_edit(status_msg, f"❌ **Search error:**\n`{e}`")
        return

    if not song_info or (not song_info.get("url") and not song_info.get("webpage_url")):
        await _safe_edit(
            status_msg,
            f"❌ **Nahi mila:** `{query[:50]}`\n\n"
            "Try: exact song name ya YouTube link dein! 🎵"
        )
        return

    requested_by = message.from_user.mention if message.from_user else "Unknown"
    song = Song(
        title        = song_info.get("title", query),
        url          = song_info.get("url", ""),
        duration     = song_info.get("duration", 0),
        is_video     = is_video,
        requested_by = requested_by,
        webpage_url  = song_info.get("webpage_url", ""),
        thumbnail    = song_info.get("thumbnail", ""),
        http_headers = song_info.get("http_headers", {}),
    )

    chat_id = message.chat.id
    current = get_current(chat_id)

    if current:
        pos = add_to_queue(chat_id, song)
        await _safe_edit(
            status_msg,
            f"📋 **Queue mein add ho gaya — #{pos}**\n\n"
            f"🎶 **{song.title}**\n"
            f"⏱️ `{fmt_duration(song.duration)}`\n"
            f"👤 {requested_by}\n\n"
            f"⏳ _Apni baari ka wait karo!_",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Queue Dekho", callback_data="queue_cb"),
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
        await asyncio.sleep(4)
        asyncio.create_task(_safe_delete(r))
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
    await asyncio.sleep(0.5)

    try:
        from helpers.youtube import search_song
        song_info = await search_song(query)
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
    asyncio.create_task(_do_play(chat_id, song, status_msg, False))


@Client.on_message(filters.command(["pause"]) & filters.group)
async def pause_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    if not current:
        r = await client.send_message(chat_id, "❌ **Abhi kuch chal nahi raha!**")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))
        return
    try:
        await call_py.pause(chat_id)
        r = await client.send_message(
            chat_id,
            f"⏸️ **Paused!**\n\n🎶 _{current.title}_\n\n`/resume` se dobara chalao.",
        )
        await asyncio.sleep(4)
        asyncio.create_task(_safe_delete(r))
    except Exception as e:
        r = await client.send_message(chat_id, f"❌ `{e}`")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))


@Client.on_message(filters.command(["resume"]) & filters.group)
async def resume_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    if not current:
        r = await client.send_message(chat_id, "❌ **Queue khaali hai!**")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))
        return
    try:
        await call_py.resume(chat_id)
        r = await client.send_message(
            chat_id,
            f"▶️ **Resumed!**\n\n🎶 _{current.title}_",
        )
        await asyncio.sleep(4)
        asyncio.create_task(_safe_delete(r))
    except Exception as e:
        r = await client.send_message(chat_id, f"❌ `{e}`")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))


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
        await asyncio.sleep(5)
        asyncio.create_task(_safe_delete(r))
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
        f"⏹️ **Stopped!**\n\n"
        f"📋 Queue clear kar diya (`{q}` songs remove)\n"
        f"🎵 `/play <song>` se dobara shuru karo!"
    )
    await asyncio.sleep(5)
    asyncio.create_task(_safe_delete(r))


@Client.on_message(filters.command(["vol", "volume", "v"]) & filters.group)
async def vol_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    args = message.command[1:]

    if not args:
        cur = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
        await client.send_message(
            chat_id,
            f"🔊 **Current Volume: `{cur}%`**\n\n"
            f"Range: `0–200`\n"
            f"Example: `/vol 150` ya `/vol 200` (max!)",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔉 −20", callback_data="vol_down"),
                InlineKeyboardButton("🔊 +20", callback_data="vol_up"),
            ]]),
        )
        return

    try:
        vol = max(0, min(200, int(args[0])))
    except ValueError:
        r = await client.send_message(chat_id, "❌ `/vol 0-200` — number dein!")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))
        return

    _volumes[chat_id] = vol
    asyncio.create_task(_set_volume_bg(chat_id))
    r = await client.send_message(
        chat_id,
        f"🔊 **Volume set: `{vol}%`**"
        + (" 🔥 MAX!" if vol >= 200 else "")
    )
    await asyncio.sleep(3)
    asyncio.create_task(_safe_delete(r))


@Client.on_message(filters.command(["queue", "q"]) & filters.group)
async def queue_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    queue   = get_queue(chat_id)

    if not current and not queue:
        r = await client.send_message(
            chat_id,
            "📋 **Queue khaali hai!**\n\n`/play <song>` se start karo. 🎵",
        )
        await asyncio.sleep(5)
        asyncio.create_task(_safe_delete(r))
        return

    lines = ["**📋 Music Queue**\n"]
    if current:
        kind = "🎬" if current.is_video else "🎵"
        lines.append(
            f"**▶️ Ab chal raha hai:**\n"
            f"{kind} **{current.title}** `[{fmt_duration(current.duration)}]`\n"
            f"👤 _{current.requested_by}_"
        )
    if queue:
        lines.append(f"\n**⏳ Waiting ({len(queue)} songs):**")
        for i, s in enumerate(queue[:12], 1):
            kind = "🎬" if s.is_video else "🎵"
            lines.append(f"`{i:>2}.` {kind} {s.title[:40]} `[{fmt_duration(s.duration)}]`")
        if len(queue) > 12:
            lines.append(f"\n_...aur {len(queue)-12} songs hain_")

    await client.send_message(
        chat_id,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
            InlineKeyboardButton("🔀 Shuffle", callback_data="shuffle_cb"),
            InlineKeyboardButton("⏹️ Stop", callback_data="stop"),
        ]])
    )


@Client.on_message(filters.command(["np", "now", "song"]) & filters.group)
async def np_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    if not current:
        r = await client.send_message(
            chat_id,
            "❌ **Abhi kuch nahi chal raha.**\n\n`/play <song>` se shuru karo! 🎵"
        )
        await asyncio.sleep(5)
        asyncio.create_task(_safe_delete(r))
        return

    np_text = np_card_text(current, chat_id)
    buttons  = now_playing_buttons(
        current.webpage_url or "",
        queue_count=queue_size(chat_id)
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
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))
        return
    r = await client.send_message(
        chat_id,
        f"🔀 **Queue shuffle ho gaya!** `{count}` songs.\n_Maza aayega ab!_ 🎵"
    )
    await asyncio.sleep(4)
    asyncio.create_task(_safe_delete(r))


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
    await asyncio.sleep(4)
    asyncio.create_task(_safe_delete(r))


# ── Stream ended → auto-next ──────────────────────────────────────

async def _auto_next(chat_id: int, song: Song):
    try:
        status_msg = await bot.send_message(
            chat_id,
            f"🔍 **Auto-next load ho raha hai...**\n🎶 {song.title}"
        )
        await _do_play(chat_id, song, status_msg, song.is_video)
    except Exception as e:
        log.warning(f"_auto_next {chat_id}: {e}")


@call_py.on_update(tgfilters.stream_end())
async def on_stream_end(client: PyTgCalls, update: StreamEnded):
    """Never await Telegram calls here — use create_task to prevent
    recursive MTProto update propagation (pytgcalls 2.x known issue)."""
    chat_id = update.chat_id

    # Loop mode — replay current
    current = get_current(chat_id)
    if _loop_enabled.get(chat_id) and current:
        asyncio.create_task(_auto_next(chat_id, current))
        return

    next_song = pop_queue(chat_id)
    if not next_song:
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
            # Update button to show Resume
            current = get_current(chat_id)
            if current:
                await _safe_edit(
                    cq.message,
                    np_card_text(current, chat_id),
                    now_playing_buttons(current.webpage_url or "", paused=True, queue_count=queue_size(chat_id))
                )
        except Exception:
            pass

    elif action == "resume":
        await cq.answer("▶️ Resumed!")
        try:
            await call_py.resume(chat_id)
            current = get_current(chat_id)
            if current:
                await _safe_edit(
                    cq.message,
                    np_card_text(current, chat_id),
                    now_playing_buttons(current.webpage_url or "", paused=False, queue_count=queue_size(chat_id))
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
            f"⏹️ **Stopped!**\n\n📋 `{q}` songs queue se remove.\n`/play <song>` se dobara start karo! 🎵"
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
                now_playing_buttons(current.webpage_url or "", queue_count=queue_size(chat_id))
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
                now_playing_buttons(current.webpage_url or "", queue_count=queue_size(chat_id))
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
    try:
        await _safe_edit(
            cq.message,
            np_card_text(current, chat_id),
            now_playing_buttons(current.webpage_url or "", queue_count=queue_size(chat_id))
        )
    except Exception:
        pass
