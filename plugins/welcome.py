"""
welcome.py — v5.0
Beautiful welcome/goodbye with buttons
/setwelcome /setgoodbye /welcome /goodbye /resetwelcome /resetgoodbye
"""

from pyrogram import Client, filters
from pyrogram.types import (
    Message, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.enums import ChatMemberStatus

from helpers.decorators import admin_only
from database import get_welcome, set_welcome, register_chat, register_user


async def _format(text: str, user, chat) -> str:
    mention = user.mention if hasattr(user, "mention") else str(user.id)
    name    = user.first_name if hasattr(user, "first_name") else str(user.id)
    return (
        text
        .replace("{mention}", mention)
        .replace("{name}", name)
        .replace("{chat}", chat.title or "this group")
        .replace("{id}", str(user.id))
    )


def _welcome_buttons(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👋 Say Hi!", callback_data=f"wc_hi_{chat_id}"),
            InlineKeyboardButton("🎵 Play Music", switch_inline_query_current_chat="/play "),
        ]
    ])


@Client.on_chat_member_updated(filters.group)
async def member_update(client: Client, update: ChatMemberUpdated):
    chat = update.chat
    new  = update.new_chat_member
    old  = update.old_chat_member

    if not new or not new.user:
        return

    user = new.user

    # Register for stats
    try:
        await register_chat(chat.id, chat.title or "")
        await register_user(user.id, user.username or "", user.first_name or "")
    except Exception:
        pass

    settings = await get_welcome(chat.id)

    # User joined
    if (old is None or old.status == ChatMemberStatus.LEFT) and \
       new.status == ChatMemberStatus.MEMBER:
        if settings["welcome_enabled"]:
            text = await _format(settings["welcome_text"], user, chat)
            try:
                await client.send_message(
                    chat.id, text,
                    reply_markup=_welcome_buttons(chat.id)
                )
            except Exception:
                pass

    # User left/banned
    elif old and old.status == ChatMemberStatus.MEMBER and \
         new.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        if settings["goodbye_enabled"]:
            text = await _format(settings["goodbye_text"], user, chat)
            try:
                await client.send_message(chat.id, text)
            except Exception:
                pass


@Client.on_callback_query(filters.regex(r"^wc_hi_(-?\d+)$"))
async def wc_hi_callback(client, cq):
    await cq.answer(f"👋 Hello {cq.from_user.first_name}! Welcome!", show_alert=True)


# ── Admin commands ─────────────────────────────────────────────────

@Client.on_message(filters.command(["setwelcome"]) & filters.group)
@admin_only
async def setwelcome_cmd(client: Client, message: Message):
    text = " ".join(message.command[1:])
    if not text:
        return await message.reply(
            "❌ Text dein.\n\n"
            "**Placeholders:** `{mention}` `{name}` `{chat}` `{id}`\n\n"
            "Example:\n`/setwelcome 👋 Welcome {mention} to {chat}! Enjoy! 🎉`"
        )
    await set_welcome(message.chat.id, "welcome_text", text)
    await message.reply(f"✅ **Welcome message set!**\n\nPreview:\n{text}")


@Client.on_message(filters.command(["setgoodbye"]) & filters.group)
@admin_only
async def setgoodbye_cmd(client: Client, message: Message):
    text = " ".join(message.command[1:])
    if not text:
        return await message.reply("❌ Text dein. Placeholders: `{mention}` `{name}` `{chat}`")
    await set_welcome(message.chat.id, "goodbye_text", text)
    await message.reply(f"✅ **Goodbye message set!**\n\nPreview:\n{text}")


@Client.on_message(filters.command(["welcome"]) & filters.group)
@admin_only
async def welcome_toggle(client: Client, message: Message):
    args = message.command[1:]
    if not args or args[0].lower() not in ("on", "off"):
        s = await get_welcome(message.chat.id)
        status = "✅ ON" if s["welcome_enabled"] else "❌ OFF"
        await message.reply(
            f"👋 **Welcome status:** {status}\n\n"
            f"`/welcome on` ya `/welcome off`"
        )
        return
    val = 1 if args[0].lower() == "on" else 0
    await set_welcome(message.chat.id, "welcome_enabled", val)
    await message.reply(f"👋 **Welcome:** {'✅ ON' if val else '❌ OFF'}")


@Client.on_message(filters.command(["goodbye"]) & filters.group)
@admin_only
async def goodbye_toggle(client: Client, message: Message):
    args = message.command[1:]
    if not args or args[0].lower() not in ("on", "off"):
        s = await get_welcome(message.chat.id)
        status = "✅ ON" if s["goodbye_enabled"] else "❌ OFF"
        await message.reply(f"👋 **Goodbye status:** {status}\n\n`/goodbye on` ya `/goodbye off`")
        return
    val = 1 if args[0].lower() == "on" else 0
    await set_welcome(message.chat.id, "goodbye_enabled", val)
    await message.reply(f"👋 **Goodbye:** {'✅ ON' if val else '❌ OFF'}")


@Client.on_message(filters.command(["resetwelcome"]) & filters.group)
@admin_only
async def resetwelcome_cmd(client: Client, message: Message):
    await set_welcome(message.chat.id, "welcome_text", "👋 Welcome {mention} to **{chat}**! 🎉")
    await message.reply("✅ Welcome message reset to default!")


@Client.on_message(filters.command(["resetgoodbye"]) & filters.group)
@admin_only
async def resetgoodbye_cmd(client: Client, message: Message):
    await set_welcome(message.chat.id, "goodbye_text", "👋 {mention} ne {chat} chhod diya.")
    await message.reply("✅ Goodbye message reset to default!")
