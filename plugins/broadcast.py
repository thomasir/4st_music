"""
broadcast.py — v5.0
/broadcast — Owner only, sends to ALL users + groups + channels
"""

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from helpers.decorators import owner_only
from database import get_all_chats, get_all_users_ids


@Client.on_message(filters.command(["broadcast", "bc"]) & filters.private)
@owner_only
async def broadcast_cmd(client: Client, message: Message):
    # Support both text + reply
    text = " ".join(message.command[1:])
    replied = message.reply_to_message if not text else None

    if not text and not replied:
        return await message.reply(
            "❌ **Usage:**\n"
            "`/broadcast Hello everyone!`\n\n"
            "Ya kisi message ko reply karein `/broadcast` se.\n\n"
            "📢 Yeh **sabhi users + groups + channels** mein jayega!"
        )

    chats = await get_all_chats()
    try:
        user_ids = await get_all_users_ids()
    except Exception:
        user_ids = []

    all_targets = list(set(chats + user_ids))
    status_msg = await message.reply(
        f"📢 **Broadcasting...**\n"
        f"👥 Users: `{len(user_ids)}`\n"
        f"💬 Groups/Channels: `{len(chats)}`\n"
        f"📊 Total: `{len(all_targets)}`\n\n"
        f"⏳ Please wait..."
    )

    success = failed = 0
    for target_id in all_targets:
        try:
            if replied:
                await replied.copy(target_id)
            else:
                await client.send_message(target_id, text)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await status_msg.edit(
        f"📢 **Broadcast Complete!**\n\n"
        f"✅ Delivered : `{success}`\n"
        f"❌ Failed    : `{failed}`\n"
        f"📊 Total     : `{len(all_targets)}`"
    )
