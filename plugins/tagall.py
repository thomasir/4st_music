"""
tagall.py — v5.0
/tagall [message] — tag all members
/ontag [message]  — same as tagall
"""

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from helpers.decorators import admin_only


@Client.on_message(filters.command(["tagall", "tg", "mentionall"]) & filters.group)
@admin_only
async def tagall_cmd(client: Client, message: Message):
    # Get custom text if provided
    text_parts = message.command[1:]
    custom_text = " ".join(text_parts) if text_parts else None

    header = f"📢 **{message.chat.title} — Tag All**\n\n"
    if custom_text:
        header += f"💬 {custom_text}\n\n"

    members = []
    try:
        async for m in client.get_chat_members(message.chat.id):
            if not m.user.is_bot and not m.user.is_deleted:
                members.append(m.user)
    except Exception as e:
        return await message.reply(f"❌ Members load nahi ho sake: {e}")

    if not members:
        return await message.reply("❌ Koi member nahi mila.")

    # Send in chunks of 15 (to avoid message length limits)
    chunk_size = 15
    for i in range(0, len(members), chunk_size):
        chunk = members[i:i + chunk_size]
        mentions = " ".join(u.mention for u in chunk)
        prefix = header if i == 0 else ""
        await message.reply(prefix + mentions)
        await asyncio.sleep(0.8)


@Client.on_message(filters.command(["ontag"]) & filters.group)
@admin_only
async def ontag_cmd(client: Client, message: Message):
    """Same as tagall with optional message."""
    text_parts = message.command[1:]
    custom_text = " ".join(text_parts) if text_parts else None

    header = f"🔔 **Everyone — {message.chat.title}**\n\n"
    if custom_text:
        header += f"📌 {custom_text}\n\n"

    members = []
    try:
        async for m in client.get_chat_members(message.chat.id):
            if not m.user.is_bot and not m.user.is_deleted:
                members.append(m.user)
    except Exception as e:
        return await message.reply(f"❌ Members load nahi ho sake: {e}")

    if not members:
        return await message.reply("❌ Koi member nahi mila.")

    chunk_size = 15
    for i in range(0, len(members), chunk_size):
        chunk = members[i:i + chunk_size]
        mentions = " ".join(u.mention for u in chunk)
        prefix = header if i == 0 else ""
        await message.reply(prefix + mentions)
        await asyncio.sleep(0.8)
