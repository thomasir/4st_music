"""
filter_words.py — v4.1
Word filter: auto-delete messages containing banned words
BUG FIX: asyncio.sleep directly in handler replaced with create_task
          (blocking handler was delaying all other message processing)
"""

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from helpers.decorators import admin_only
from database import add_filter, remove_filter, get_filters
from config import SUDO_USERS
import time as _fw_time_

_fw_admin_cache: dict = {}
_FW_CACHE_TTL = 30

async def _fw_is_admin(client, chat_id: int, user_id: int) -> bool:
    now = _fw_time_.time()
    key = (chat_id, user_id)
    cached = _fw_admin_cache.get(key)
    if cached and now < cached[1]:
        return cached[0]
    try:
        from pyrogram.enums import ChatMemberStatus
        member = await client.get_chat_member(chat_id, user_id)
        is_admin = member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        is_admin = False
    _fw_admin_cache[key] = (is_admin, now + _FW_CACHE_TTL)
    return is_admin


async def _warn_and_cleanup(client, chat_id: int, mention: str):
    """Background: send filter warning and auto-delete after 5s."""
    try:
        warn_msg = await client.send_message(
            chat_id,
            f"⚠️ {mention} ne banned word use kiya. Message delete!"
        )
        await asyncio.sleep(5)
        await warn_msg.delete()
    except Exception:
        pass


@Client.on_message(filters.group & filters.text, group=2)
async def check_filters(client: Client, message: Message):
    if not message.from_user:
        return
    if message.from_user.id in SUDO_USERS:
        return
    if await _fw_is_admin(client, message.chat.id, message.from_user.id):
        return

    words = await get_filters(message.chat.id)
    if not words:
        return

    text_lower = (message.text or "").lower()
    for word in words:
        if word in text_lower:
            try:
                await message.delete()
                mention = message.from_user.mention
                # BUG FIX: use create_task so handler returns immediately
                asyncio.create_task(_warn_and_cleanup(client, message.chat.id, mention))
            except Exception:
                pass
            return


@Client.on_message(filters.command(["addfilter", "filter"]) & filters.group)
@admin_only
async def addfilter_cmd(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        return await message.reply("❌ Word dein. Example: `/addfilter badword`")
    word = " ".join(args).lower()
    await add_filter(message.chat.id, word)
    await message.reply(f"✅ **Filter added:** `{word}`")


@Client.on_message(filters.command(["rmfilter", "unfilter", "delfilter"]) & filters.group)
@admin_only
async def rmfilter_cmd(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        return await message.reply("❌ Word dein. Example: `/rmfilter badword`")
    word = " ".join(args).lower()
    await remove_filter(message.chat.id, word)
    await message.reply(f"✅ **Filter removed:** `{word}`")


@Client.on_message(filters.command(["filters", "listfilters"]) & filters.group)
async def filters_cmd(client: Client, message: Message):
    words = await get_filters(message.chat.id)
    if not words:
        return await message.reply("📋 **Koi filter nahi hai.**\n\n`/addfilter <word>` se add karein.")
    text = "🚫 **Word Filters in this group:**\n\n"
    text += "\n".join(f"• `{w}`" for w in sorted(words))
    await message.reply(text)
