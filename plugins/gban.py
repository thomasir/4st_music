"""
gban.py — v6.0
Global ban system — sudo/owner only
✅ Fixed filter operator precedence (proper parentheses)
"""

from pyrogram import Client, filters
from pyrogram.types import Message
from helpers.decorators import sudo_only
from database import gban_user, ungban_user, is_gbanned, get_gban_count

_gban_filter  = (filters.command(["gban"])  & filters.private) | (filters.command(["gban"])  & filters.group)
_ungban_filter = (filters.command(["ungban"]) & filters.private) | (filters.command(["ungban"]) & filters.group)


async def _resolve_user(client: Client, message: Message):
    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        try:
            target = await client.get_users(message.command[1])
        except Exception as e:
            await message.reply(f"❌ User nahi mila: `{e}`")
            return None, None

    if not target:
        await message.reply("❌ Reply karein ya username/ID dein.")
        return None, None

    from config import OWNER_ID
    if target.id == OWNER_ID:
        await message.reply("❌ Owner ko gban nahi kar sakte!")
        return None, None

    return target, True


# ── /gban ─────────────────────────────────────────────────────────

@Client.on_message(_gban_filter)
@sudo_only
async def gban_cmd(client: Client, message: Message):
    user, ok = await _resolve_user(client, message)
    if not ok:
        return

    offset  = 1 if message.reply_to_message else 2
    reason  = " ".join(message.command[offset:]) or "No reason"

    await gban_user(user.id, reason, message.from_user.id)

    # Ban from current group too
    try:
        await client.ban_chat_member(message.chat.id, user.id)
    except Exception:
        pass

    await message.reply(
        f"🔨 **Global Ban Executed!**\n\n"
        f"> 👤 {user.mention} (`{user.id}`)\n"
        f"> 📝 Reason: {reason}\n"
        f"> ⚠️ _Yeh user ab sab groups mein auto-ban hoga._"
    )

    from config import LOG_CHANNEL
    if LOG_CHANNEL:
        try:
            await client.send_message(
                LOG_CHANNEL,
                f"🔨 **GBAN**\n\n"
                f"👤 User : {user.mention} (`{user.id}`)\n"
                f"📝 Reason: {reason}\n"
                f"👮 By: {message.from_user.mention}"
            )
        except Exception:
            pass


# ── /ungban ───────────────────────────────────────────────────────

@Client.on_message(_ungban_filter)
@sudo_only
async def ungban_cmd(client: Client, message: Message):
    user, ok = await _resolve_user(client, message)
    if not ok:
        return

    info = await is_gbanned(user.id)
    if not info:
        await message.reply(f"✅ {user.mention} globally banned nahi hai.")
        return

    await ungban_user(user.id)

    try:
        await client.unban_chat_member(message.chat.id, user.id)
    except Exception:
        pass

    await message.reply(f"✅ **Global Unban!**\n\n👤 {user.mention} (`{user.id}`)")


# ── /gbans ────────────────────────────────────────────────────────

@Client.on_message(filters.command(["gbans", "gbanlist"]))
async def gbans_cmd(client: Client, message: Message):
    count = await get_gban_count()
    await message.reply(f"🔨 **Total Global Bans:** `{count}`")


# ── Auto-gban check on join ───────────────────────────────────────

@Client.on_chat_member_updated(filters.group, group=10)
async def check_gban_on_join(client: Client, update):
    from pyrogram.enums import ChatMemberStatus
    new = update.new_chat_member
    if not new or not new.user:
        return
    if new.status != ChatMemberStatus.MEMBER:
        return

    info = await is_gbanned(new.user.id)
    if info:
        try:
            await client.ban_chat_member(update.chat.id, new.user.id)
            await client.send_message(
                update.chat.id,
                f"🔨 **Auto-GBanned:** {new.user.mention}\n"
                f"📝 Reason: {info['reason']}"
            )
        except Exception:
            pass
