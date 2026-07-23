"""
reaction.py — v5.0
/reaction on | /reaction off
Auto-reacts to random messages, welcome msgs, link msgs
"""

import random
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from helpers.decorators import admin_only
from database import get_reaction_enabled, set_reaction

# Reaction emojis pool
REACTIONS = ["❤️", "👍", "🔥", "🎉", "😂", "🤩", "👏", "😍", "💯", "🥰", "😎", "⚡", "🌟", "💪", "🎵"]


@Client.on_message(filters.command(["reaction"]) & filters.group)
@admin_only
async def reaction_toggle(client: Client, message: Message):
    args = message.command[1:]
    if not args or args[0].lower() not in ("on", "off"):
        status = await get_reaction_enabled(message.chat.id)
        await message.reply(
            f"⚡ **Auto Reaction:** {'✅ ON' if status else '❌ OFF'}\n\n"
            f"Bot random messages pe, welcome pe aur links pe react karega.\n\n"
            f"`/reaction on` — enable\n"
            f"`/reaction off` — disable"
        )
        return
    enabled = args[0].lower() == "on"
    await set_reaction(message.chat.id, enabled)
    await message.reply(
        f"⚡ **Auto Reaction:** {'✅ ON' if enabled else '❌ OFF'}"
    )


@Client.on_message(filters.group & ~filters.bot, group=8)
async def auto_react(client: Client, message: Message):
    try:
        if not message.from_user:
            return
        enabled = await get_reaction_enabled(message.chat.id)
        if not enabled:
            return

        # React to 1 in 7 random messages, or always to welcome/link messages
        has_link = bool(message.entities and any(
            e.type.name in ("URL", "TEXT_LINK") for e in message.entities
        ))
        should_react = has_link or (random.random() < 1/7)

        if not should_react:
            return

        emoji = random.choice(REACTIONS)
        try:
            await message.react(emoji)
        except Exception:
            pass  # Some chats don't support reactions
    except Exception:
        pass
