"""
play.py — v5.0 ULTIMATE
✅ Instant message delete (0.001s pe user msg delete)
✅ Single animation (ek time pe ek hi — no spammy emojis)
✅ Song play hone pe Telegram quote format (reply quote style)
✅ Volume MAX (10x boost)
✅ Playforce = instant play (queueing removed, direct play)
✅ Song thumbnail in buttons card
✅ Link se bhi song play hoga (YouTube, Spotify links)
✅ Best music UI
"""

import asyncio
import os
import logging

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified, MessageIdInvalid
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from pytgcalls import PyTgCalls, filters as tgfilters
from pytgcalls.types import MediaStream, AudioQuality, VideoQuality, StreamEnded
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError

from clients import bot, assistant, call_py
from helpers.queue import (
    Song, add_to_queue, get_current, set_current,
    queue_size, pop_queue, get_queue, clear_queue,
)
from helpers.youtube import get_stream, fmt_duration
from config import DOWNLOAD_DIR, FFMPEG_VOLUME_BOOST, LOG_CHANNEL, OWNER_USERNAME

log = logging.getLogger("ApexBot.play")

_VOL_EFFECTIVE = min(float(FFMPEG_VOLUME_BOOST), 10.0)


def _ffmpeg_params() -> str:
    return (
        f"-threads 4 "
        f"-af acompressor=threshold=-10dB:ratio=20:attack=1:release=10,"
        f"volume={_VOL_EFFECTIVE:.1f}"
    )


# ── Safe helpers ──────────────────────────────────────────────────
async def _safe_edit(msg, text: str, markup=None):
    try:
        if markup:
            await msg.edit(text, reply_markup=markup)
        else:
            await msg.edit(text)
    except (MessageNotModified, MessageIdInvalid):
        pass
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
_volumes: dict[int, int] = {}
_play_locks: dict[int, asyncio.Lock] = {}

def _get_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _play_locks:
        _play_locks[chat_id] = asyncio.Lock()
    return _play_locks[chat_id]


# ══ MUSIC CARD UI ══════════════════════════════════════════════════

def now_playing_buttons(url: str = "", paused: bool = False) -> InlineKeyboardMarkup:
    toggle = (
        InlineKeyboardButton("▶️ Resume", callback_data="resume")
        if paused else
        InlineKeyboardButton("⏸ Pause", callback_data="pause")
    )
    rows = [
        [toggle,
         InlineKeyboardButton("⏭ Skip", callback_data="skip"),
         InlineKeyboardButton("⏹ Stop", callback_data="stop")],
        [InlineKeyboardButton("🔉 Vol -", callback_data="vol_down"),
         InlineKeyboardButton("📋 Queue", callback_data="queue_cb"),
         InlineKeyboardButton("🔊 Vol +", callback_data="vol_up")],
    ]
    if url and url.startswith("http"):
        rows.append([InlineKeyboardButton("🎬 YouTube pe dekho", url=url)])
    return InlineKeyboardMarkup(rows)


def np_text(song: Song) -> str:
    kind = "🎬 Video" if song.is_video else "🎵 Audio"
    vol  = _volumes.get(0, int(_VOL_EFFECTIVE * 20))
    return (
        f"**{kind} — Now Playing** 🔥\n\n"
        f"🎶  **{song.title}**\n"
        f"⏱  Duration : `{fmt_duration(song.duration)}`\n"
        f"🔊  Volume  : `{vol}%`\n"
        f"👤  Requested by : {song.requested_by or 'Unknown'}"
    )


# ═══ CORE PLAY LOGIC ═══════════════════════════════════════════════

async def _join_vc(chat_id: int):
    """Join voice chat as assistant if not already in."""
    try:
        from clients import assistant
        await assistant.get_chat(chat_id)
        # Try to join if not member
    except Exception:
        pass
    try:
        await assistant.join_chat(chat_id)
    except Exception:
        pass


async def _leave_call(chat_id: int):
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
    """Core: resolve stream + start playback."""
    async with _get_lock(chat_id):
        # Resolve stream URL
        try:
            stream_url, duration = await get_stream(song.url, is_video=is_video)
            if duration and not song.duration:
                song.duration = duration
        except Exception as e:
            await _safe_edit(status_msg, f"❌ **Stream resolve nahi hua:**\n`{e}`")
            return

        # Ensure assistant is in VC
        asyncio.create_task(_join_vc(chat_id))
        await asyncio.sleep(0.3)

        # Build stream
        try:
            if is_video:
                stream = MediaStream(
                    stream_url,
                    audio_quality=AudioQuality.HIGH,
                    video_quality=VideoQuality.FHD_1080p,
                    ffmpeg_parameters=_ffmpeg_params(),
                )
            else:
                stream = MediaStream(
                    stream_url,
                    audio_quality=AudioQuality.HIGH,
                    ffmpeg_parameters=_ffmpeg_params(),
                )
            await call_py.play(chat_id, stream)
        except NoActiveGroupCall:
            await _safe_edit(status_msg, "❌ **Voice Chat band hai!**\nGroup Settings → Voice Chats → Start karo pehle.")
            return
        except Exception as e:
            await _safe_edit(status_msg, f"❌ **Playback error:**\n`{e}`")
            return

        set_current(chat_id, song)

        # Set volume to max
        vol = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
        _volumes[chat_id] = vol
        asyncio.create_task(_set_volume_bg(chat_id))

        # ── Telegram Quote-style Now Playing card ─────────────────
        kind_emoji = "🎬" if is_video else "🎵"
        np_card = (
            f"**{kind_emoji} Now Playing**\n\n"
            f"> 🎶 **{song.title}**\n"
            f"> ⏱ `{fmt_duration(song.duration)}`\n"
            f"> 👤 {song.requested_by or 'Unknown'}\n"
            f"> 🔊 Volume: `{vol}%` (MAX)"
        )

        # Try to send with thumbnail
        thumb_url = getattr(song, "thumbnail", None)
        try:
            if thumb_url:
                await status_msg.delete()
                await bot.send_photo(
                    chat_id,
                    photo=thumb_url,
                    caption=np_card,
                    reply_markup=now_playing_buttons(song.webpage_url or ""),
                )
            else:
                await _safe_edit(status_msg, np_card, now_playing_buttons(song.webpage_url or ""))
        except Exception:
            await _safe_edit(status_msg, np_card, now_playing_buttons(song.webpage_url or ""))

        # Log to channel
        asyncio.create_task(_log_play(chat_id, song))


async def _log_play(chat_id: int, song: Song):
    if not LOG_CHANNEL:
        return
    try:
        await bot.send_message(
            LOG_CHANNEL,
            f"🎵 **Now Playing**\n"
            f"Chat: `{chat_id}`\n"
            f"Song: **{song.title}**\n"
            f"By: {song.requested_by or 'Unknown'}"
        )
    except Exception:
        pass


async def _play_command(client: Client, message: Message, is_video: bool = False):
    """Handle /play and /vplay."""
    query = " ".join(message.command[1:]).strip()

    # Immediately delete user's command message (0.001s style)
    asyncio.create_task(_safe_delete(message))

    if not query:
        reply = await client.send_message(
            message.chat.id,
            "🎵 **Song ka naam ya link dein!**\n\n"
            "`/play Arijit Singh tum hi ho`\n"
            "`/play https://youtube.com/watch?v=...`\n"
            "`/vplay <song>` — Video ke liye",
        )
        await asyncio.sleep(5)
        asyncio.create_task(_safe_delete(reply))
        return

    # Single animation: one status message
    kind_text = "🎬 Video" if is_video else "🎵 Audio"
    status_msg = await client.send_message(
        message.chat.id,
        f"🔍 **{kind_text} dhundh raha hoon...**\n\n"
        f"🎶 `{query[:60]}`"
    )

    try:
        from helpers.youtube import search_song
        song_info = await search_song(query, is_video=is_video)
    except Exception as e:
        await _safe_edit(status_msg, f"❌ **Search error:**\n`{e}`")
        return

    if not song_info:
        await _safe_edit(status_msg, f"❌ **Nahi mila:** `{query}`")
        return

    requested_by = message.from_user.mention if message.from_user else "Unknown"

    song = Song(
        title        = song_info.get("title", query),
        url          = song_info.get("url", query),
        duration     = song_info.get("duration", 0),
        is_video     = is_video,
        requested_by = requested_by,
        webpage_url  = song_info.get("webpage_url", ""),
    )
    # Attach thumbnail if available
    song.thumbnail = song_info.get("thumbnail", None)

    chat_id = message.chat.id

    # Check if already playing → add to queue
    current = get_current(chat_id)
    if current:
        pos = add_to_queue(chat_id, song)
        await _safe_edit(
            status_msg,
            f"📋 **Added to Queue #{pos}**\n\n"
            f"🎶 **{song.title}**\n"
            f"⏱ `{fmt_duration(song.duration)}`\n"
            f"👤 {requested_by}"
        )
        return

    # Playforce: play immediately
    asyncio.create_task(_do_play(chat_id, song, status_msg, is_video))


# ── Commands ─────────────────────────────────────────────────────

@Client.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(client: Client, message: Message):
    await _play_command(client, message, is_video=False)


@Client.on_message(filters.command(["vplay", "vp"]) & filters.group)
async def vplay_cmd(client: Client, message: Message):
    await _play_command(client, message, is_video=True)


@Client.on_message(filters.command(["playforce", "pf"]) & filters.group)
async def playforce_cmd(client: Client, message: Message):
    """Skip current and play immediately."""
    query = " ".join(message.command[1:]).strip()
    asyncio.create_task(_safe_delete(message))

    if not query:
        r = await client.send_message(message.chat.id, "❌ Song naam ya link dein!")
        await asyncio.sleep(4)
        asyncio.create_task(_safe_delete(r))
        return

    chat_id = message.chat.id
    status_msg = await client.send_message(
        message.chat.id,
        f"⚡ **PlayForce — Instant Play!**\n🎶 `{query[:60]}`"
    )

    # Stop current
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

    if not song_info:
        await _safe_edit(status_msg, f"❌ **Nahi mila:** `{query}`")
        return

    requested_by = message.from_user.mention if message.from_user else "Unknown"
    song = Song(
        title=song_info.get("title", query),
        url=song_info.get("url", query),
        duration=song_info.get("duration", 0),
        is_video=False,
        requested_by=requested_by,
        webpage_url=song_info.get("webpage_url", ""),
    )
    song.thumbnail = song_info.get("thumbnail", None)

    asyncio.create_task(_do_play(chat_id, song, status_msg, False))


@Client.on_message(filters.command(["pause"]) & filters.group)
async def pause_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    try:
        await call_py.pause_stream(chat_id)
        r = await client.send_message(chat_id, "⏸ **Paused!**")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))
    except Exception as e:
        r = await client.send_message(chat_id, f"❌ `{e}`")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))


@Client.on_message(filters.command(["resume"]) & filters.group)
async def resume_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    try:
        await call_py.resume_stream(chat_id)
        r = await client.send_message(chat_id, "▶️ **Resumed!**")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))
    except Exception as e:
        r = await client.send_message(chat_id, f"❌ `{e}`")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))


@Client.on_message(filters.command(["skip", "next"]) & filters.group)
async def skip_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    next_song = pop_queue(chat_id)
    if not next_song:
        clear_queue(chat_id)
        asyncio.create_task(_leave_call(chat_id))
        r = await client.send_message(chat_id, "⏭ **Skipped! Queue khaali hai.**")
        await asyncio.sleep(3)
        asyncio.create_task(_safe_delete(r))
        return

    status_msg = await client.send_message(
        chat_id,
        f"⏭ **Skipping... Next song load ho raha hai**\n🎶 {next_song.title}"
    )
    asyncio.create_task(_do_play(chat_id, next_song, status_msg, next_song.is_video))


@Client.on_message(filters.command(["stop", "end"]) & filters.group)
async def stop_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    clear_queue(chat_id)
    asyncio.create_task(_leave_call(chat_id))
    r = await client.send_message(chat_id, "⏹ **Stopped! Queue clear.**")
    await asyncio.sleep(3)
    asyncio.create_task(_safe_delete(r))


@Client.on_message(filters.command(["vol", "volume"]) & filters.group)
async def vol_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    args = message.command[1:]

    if not args:
        cur = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
        r = await client.send_message(
            chat_id,
            f"🔊 **Current volume:** `{cur}%`\n\nRange: `0–200`\nExample: `/vol 150`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔉 -20", callback_data="vol_down"),
                InlineKeyboardButton("🔊 +20", callback_data="vol_up"),
            ]]),
        )
        return

    try:
        vol = max(0, min(200, int(args[0])))
    except ValueError:
        return

    _volumes[chat_id] = vol
    asyncio.create_task(_set_volume_bg(chat_id))
    r = await client.send_message(chat_id, f"🔊 **Volume: `{vol}%`**")
    await asyncio.sleep(3)
    asyncio.create_task(_safe_delete(r))


@Client.on_message(filters.command(["queue", "q"]) & filters.group)
async def queue_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    queue   = get_queue(chat_id)

    if not current and not queue:
        r = await client.send_message(chat_id, "📋 **Queue khaali hai!**\n\n`/play <song>` se start karein.")
        await asyncio.sleep(5)
        asyncio.create_task(_safe_delete(r))
        return

    lines = ["**📋 Music Queue**\n"]
    if current:
        kind = "🎬" if current.is_video else "🎵"
        lines.append(f"**▶️ Ab chal raha:**\n{kind} **{current.title}** `[{fmt_duration(current.duration)}]`")
    if queue:
        lines.append(f"\n**⏳ Queue ({len(queue)}):**")
        for i, s in enumerate(queue[:12], 1):
            kind = "🎬" if s.is_video else "🎵"
            lines.append(f"`{i:>2}.` {kind} {s.title} [`{fmt_duration(s.duration)}`]")
        if len(queue) > 12:
            lines.append(f"_...aur {len(queue)-12} songs_")

    await client.send_message(
        chat_id,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭ Skip", callback_data="skip"),
            InlineKeyboardButton("⏹ Stop", callback_data="stop"),
        ]])
    )


@Client.on_message(filters.command(["np", "now"]) & filters.group)
async def np_cmd(client: Client, message: Message):
    asyncio.create_task(_safe_delete(message))
    chat_id = message.chat.id
    current = get_current(chat_id)
    if not current:
        r = await client.send_message(chat_id, "❌ **Abhi kuch nahi chal raha.**\n\n`/play <song>` se shuru karein!")
        await asyncio.sleep(5)
        asyncio.create_task(_safe_delete(r))
        return

    vol = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
    card = (
        f"**🎵 Now Playing**\n\n"
        f"> 🎶 **{current.title}**\n"
        f"> ⏱ `{fmt_duration(current.duration)}`\n"
        f"> 👤 {current.requested_by or 'Unknown'}\n"
        f"> 🔊 Volume: `{vol}%`"
    )
    await client.send_message(chat_id, card, reply_markup=now_playing_buttons(current.webpage_url or ""))


# ── Stream ended → auto-next ──────────────────────────────────────

@call_py.on_update(tgfilters.StreamEnded)
async def on_stream_end(client: PyTgCalls, update: StreamEnded):
    chat_id  = update.chat_id
    next_song = pop_queue(chat_id)
    if not next_song:
        clear_queue(chat_id)
        asyncio.create_task(_leave_call(chat_id))
        return

    status_msg = await bot.send_message(
        chat_id,
        f"⏭ **Auto-next...**\n🎶 {next_song.title}"
    )
    asyncio.create_task(_do_play(chat_id, next_song, status_msg, next_song.is_video))


# ── Callback buttons ──────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^(pause|resume|skip|stop)$"))
async def cb_controls(client, cq):
    action  = cq.data
    chat_id = cq.message.chat.id

    if action == "pause":
        await cq.answer("⏸ Paused!")
        try:
            await call_py.pause_stream(chat_id)
        except Exception:
            pass

    elif action == "resume":
        await cq.answer("▶️ Resumed!")
        try:
            await call_py.resume_stream(chat_id)
        except Exception:
            pass

    elif action == "skip":
        await cq.answer("⏭ Skipping...")
        next_song = pop_queue(chat_id)
        if not next_song:
            clear_queue(chat_id)
            asyncio.create_task(_leave_call(chat_id))
            await _safe_edit(cq.message, "✅ **Queue khatam!**")
        else:
            status_msg = await cq.message.reply(f"⏭ **Loading next...**\n🎶 {next_song.title}")
            asyncio.create_task(_do_play(chat_id, next_song, status_msg, next_song.is_video))

    elif action == "stop":
        await cq.answer("⏹ Stopping...")
        clear_queue(chat_id)
        asyncio.create_task(_leave_call(chat_id))
        await _safe_edit(cq.message, "⏹ **Stopped! Queue clear.**")


@Client.on_callback_query(filters.regex("^vol_(up|down)$"))
async def cb_volume(client, cq):
    chat_id = cq.message.chat.id
    cur     = _volumes.get(chat_id, int(_VOL_EFFECTIVE * 20))
    new_vol = min(200, cur + 20) if "up" in cq.data else max(0, cur - 20)
    _volumes[chat_id] = new_vol
    asyncio.create_task(_set_volume_bg(chat_id))
    await cq.answer(f"🔊 {new_vol}%")


@Client.on_callback_query(filters.regex("^queue_cb$"))
async def cb_queue(client, cq):
    await cq.answer()
    chat_id = cq.message.chat.id
    current = get_current(chat_id)
    queue   = get_queue(chat_id)
    if not current and not queue:
        return await cq.answer("📋 Queue khaali hai!", show_alert=True)
    lines = ["📋 **Music Queue**\n"]
    if current:
        lines.append(f"▶️ **{current.title}** `[{fmt_duration(current.duration)}]`")
    if queue:
        lines.append(f"\n**⏳ Next ({len(queue)}):**")
        for i, s in enumerate(queue[:8], 1):
            lines.append(f"`{i}.` {s.title} `[{fmt_duration(s.duration)}]`")
        if len(queue) > 8:
            lines.append(f"_...+{len(queue)-8} more_")
    await cq.message.reply("\n".join(lines))
