"""
antiporn.py — v5.1
Sirf PORN STICKERS delete karo — normal stickers/media nahi.
/antiporn on | /antiporn off
BUG FIX: asyncio.sleep directly in handler replaced with create_task
          (blocking handler was delaying all other message processing)
"""

import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from helpers.decorators import admin_only
from database import get_antiporn, set_antiporn

log = logging.getLogger("ApexBot.antiporn")

# Known porn sticker set names (partial match, lowercase)
PORN_SETS = [
    "porn", "sex", "nude", "naked", "hentai", "xxx", "nsfw",
    "erotic", "lewd", "adult18", "18plus", "sexy_girls", "horny",
    "bdsm", "kinky", "stripclub", "naughty18",
]


def _is_porn_sticker(message: Message) -> bool:
    if not message.sticker:
        return False
    s = message.sticker
    if s.set_name:
        sname = s.set_name.lower()
        for kw in PORN_SETS:
            if kw in sname:
                return True
    if s.emoji and s.emoji in ("🔞", "💦", "🍆", "🍑"):
        return True
    return False


async def _delete_warn_cleanup(client, chat_id: int, user_mention: str):
    """Background task: send warning and auto-delete it after 5s."""
    try:
        warn_msg = await client.send_message(
            chat_id,
            f"🔞 {user_mention} — Porn sticker deleted!\n"
            f"_Is group mein NSFW content allowed nahi hai._"
        )
        await asyncio.sleep(5)
        await warn_msg.delete()
    except Exception:
        pass


@Client.on_message(filters.command(["antiporn"]) & filters.group)
@admin_only
async def antiporn_toggle(client: Client, message: Message):
    args = message.command[1:]
    if not args or args[0].lower() not in ("on", "off"):
        status = await get_antiporn(message.chat.id)
        await message.reply(
            f"🔞 **AntiPorn Status:** {'✅ ON' if status else '❌ OFF'}\n\n"
            f"Sirf porn stickers delete honge — normal stickers safe hain.\n\n"
            f"`/antiporn on` — enable\n"
            f"`/antiporn off` — disable"
        )
        return
    enabled = args[0].lower() == "on"
    await set_antiporn(message.chat.id, enabled)
    await message.reply(
        f"🔞 **AntiPorn:** {'✅ ON — Porn stickers auto-delete honge!' if enabled else '❌ OFF'}"
    )


@Client.on_message(filters.group & filters.sticker, group=5)
async def antiporn_check(client: Client, message: Message):
    if not message.sticker:
        return
    try:
        enabled = await get_antiporn(message.chat.id)
        if not enabled:
            return
        if _is_porn_sticker(message):
            await message.delete()
            user_mention = message.from_user.mention if message.from_user else "User"
            # BUG FIX: use create_task so handler returns immediately
            asyncio.create_task(_delete_warn_cleanup(client, message.chat.id, user_mention))
            log.info(f"Deleted porn sticker in {message.chat.id} by "
                     f"{message.from_user.id if message.from_user else '?'}")
    except Exception as e:
        log.debug(f"antiporn_check error: {e}")
