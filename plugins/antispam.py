"""
antispam.py — v6.0
Flood control + anti-raid protection
✅ Fixed: asyncio.sleep inside handlers replaced with create_task
   (handler returns immediately; unmute/unlock runs in background task)
"""

import asyncio
import time
from collections import defaultdict
from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions
from pyrogram.errors import UserAdminInvalid
from config import SUDO_USERS
from database import spam_rank_ban
import time as _time_

# Admin status cache: chat_id -> {user_id -> (status, expire_time)}
_admin_cache: dict = {}
_ADMIN_CACHE_TTL = 30  # seconds

async def _is_admin_cached(client, chat_id: int, user_id: int) -> bool:
    """Check admin status with 30s caching to avoid per-message API calls."""
    now = _time_.time()
    key = (chat_id, user_id)
    cached = _admin_cache.get(key)
    if cached and now < cached[1]:
        return cached[0]
    try:
        from pyrogram.enums import ChatMemberStatus
        member = await client.get_chat_member(chat_id, user_id)
        is_admin = member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        is_admin = False
    _admin_cache[key] = (is_admin, now + _ADMIN_CACHE_TTL)
    return is_admin

# chat_id -> {user_id -> [timestamps]}
_flood: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))

FLOOD_LIMIT  = 7    # messages
FLOOD_WINDOW = 5    # seconds
FLOOD_MUTE   = 60   # mute for 60 seconds

# Anti-raid: track how many new members join in a time window
_raid: dict[int, list] = defaultdict(list)
RAID_LIMIT  = 10    # new joins
RAID_WINDOW = 30    # seconds
_raid_active: set = set()


def _check_flood(chat_id: int, user_id: int) -> bool:
    now = time.time()
    times = _flood[chat_id][user_id]
    times = [t for t in times if now - t < FLOOD_WINDOW]
    times.append(now)
    _flood[chat_id][user_id] = times
    return len(times) >= FLOOD_LIMIT


async def _do_unmute(client, chat_id: int, user_id: int, delay: int):
    """Background task: wait delay seconds then restore user's send rights."""
    await asyncio.sleep(delay)
    try:
        await client.restrict_chat_member(
            chat_id,
            user_id,
            ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
            ),
        )
    except Exception:
        pass


async def _do_unlock(client, chat_id: int, delay: int):
    """Background task: wait delay seconds then unlock the group."""
    await asyncio.sleep(delay)
    try:
        await client.set_chat_permissions(
            chat_id,
            ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        )
        await client.send_message(chat_id, "✅ **Group unlock ho gaya. Anti-raid mode off.**")
    except Exception:
        pass
    finally:
        _raid_active.discard(chat_id)
        _raid[chat_id] = []


@Client.on_message(filters.group & ~filters.bot, group=1)
async def flood_check(client: Client, message: Message):
    if not message.from_user:
        return

    if message.from_user.id in SUDO_USERS:
        return

    # Skip admins
    if await _is_admin_cached(client, message.chat.id, message.from_user.id):
        return

    if _check_flood(message.chat.id, message.from_user.id):
        _flood[message.chat.id][message.from_user.id] = []
        try:
            await client.restrict_chat_member(
                message.chat.id,
                message.from_user.id,
                ChatPermissions(can_send_messages=False),
            )
            await message.reply(
                f"⚠️ {message.from_user.mention} **flood karne par {FLOOD_MUTE}s ke liye mute!**"
            )
            # BUG FIX: Record spam strike in DB (spam_rank_ban was imported but never called)
            await spam_rank_ban(message.chat.id, message.from_user.id, minutes=1)
            # Unmute in background — handler returns immediately
            asyncio.create_task(
                _do_unmute(client, message.chat.id, message.from_user.id, FLOOD_MUTE)
            )
        except Exception:
            pass


@Client.on_chat_member_updated(filters.group, group=1)
async def raid_check(client: Client, update):
    from pyrogram.enums import ChatMemberStatus
    new = update.new_chat_member
    if not new or not new.user:
        return
    if new.status != ChatMemberStatus.MEMBER:
        return

    chat_id = update.chat.id
    now = time.time()
    times = _raid[chat_id]
    times = [t for t in times if now - t < RAID_WINDOW]
    times.append(now)
    _raid[chat_id] = times

    if len(times) >= RAID_LIMIT and chat_id not in _raid_active:
        _raid_active.add(chat_id)
        try:
            # Lock group immediately
            await client.set_chat_permissions(chat_id, ChatPermissions(can_send_messages=False))
            await client.send_message(
                chat_id,
                f"🚨 **ANTI-RAID MODE ACTIVE!**\n\n"
                f"⚠️ {RAID_LIMIT} log {RAID_WINDOW} seconds mein join hue — group lock ho gaya!\n"
                f"⏳ 5 minutes mein automatically unlock hoga."
            )
            # Unlock in background — handler returns immediately
            asyncio.create_task(_do_unlock(client, chat_id, 300))
        except Exception:
            _raid_active.discard(chat_id)
            _raid[chat_id] = []
