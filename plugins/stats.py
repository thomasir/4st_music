"""
stats.py — v5.0
/stats, /rankings, /topusers, /topgroup
All media count hoti hai
Spam pe 5 min chat rank ban
Works with @botusername in group
"""

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import MessageEntityType
import time

from database import (
    increment_stat, get_top_users, get_chat_total,
    get_all_group_stats, get_total_chats, get_total_users, spam_rank_ban
)

MEDALS = ["🥇", "🥈", "🥉"] + ["🏅"] * 7

_MEDIA_TYPES = frozenset([
    "photo", "video", "audio", "voice", "document",
    "sticker", "animation", "video_note"
])


def _is_media(message: Message) -> bool:
    for mt in _MEDIA_TYPES:
        if getattr(message, mt, None):
            return True
    return False


@Client.on_message(filters.group & ~filters.bot, group=2)
async def count_message(client: Client, message: Message):
    """Count every message and media for stats."""
    if not message.from_user:
        return
    try:
        is_media = _is_media(message)
        await increment_stat(message.chat.id, message.from_user.id, is_media)
    except Exception:
        pass


@Client.on_message(filters.command(["stats"]) & filters.group)
async def stats_cmd(client: Client, message: Message):
    chat_id = message.chat.id
    total   = await get_chat_total(chat_id)
    top     = await get_top_users(chat_id, limit=10)

    me = message.from_user
    my_count = 0
    my_rank  = 0
    for rank, (uid, cnt) in enumerate(top, 1):
        if uid == (me.id if me else 0):
            my_count = cnt
            my_rank  = rank

    text = (
        f"📊 **Group Stats — {message.chat.title}**\n\n"
        f"💬 Total msgs+media: `{total:,}`\n"
    )
    if my_count:
        pct = (my_count / total * 100) if total else 0
        text += (
            f"\n👤 **Tumhari stats:**\n"
            f"  Messages+Media: `{my_count:,}` ({pct:.1f}%)\n"
            f"  Rank: `#{my_rank}`"
        )
    await message.reply(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🏆 Top Users", callback_data="stats_top"),
        InlineKeyboardButton("🔄 Refresh", callback_data="stats_refresh"),
    ]]))


@Client.on_message(filters.command(["rankings", "topusers", "top", "leaderboard"]) & filters.group)
async def topusers_cmd(client: Client, message: Message):
    chat_id = message.chat.id
    top     = await get_top_users(chat_id, limit=10)
    total   = await get_chat_total(chat_id)

    if not top:
        return await message.reply(
            "📊 **Abhi koi stats nahi hain.**\n\nKuch messages bhejo!"
        )

    lines = [f"🏆 **Rankings — {message.chat.title}**\n_(msgs + media sab count hoti hai)_\n"]
    for i, (uid, cnt) in enumerate(top):
        medal = MEDALS[i] if i < len(MEDALS) else f"`{i+1}.`"
        pct   = (cnt / total * 100) if total else 0
        try:
            user = await client.get_users(uid)
            name = user.first_name[:20]
        except Exception:
            name = str(uid)
        lines.append(f"{medal} **{name}** — `{cnt:,}` ({pct:.1f}%)")

    lines.append(f"\n💬 **Total:** `{total:,}` messages+media")
    lines.append(f"\n⚠️ _Spam karoge toh 5 min ke liye rank se ban!_")

    await message.reply("\n".join(lines), reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Refresh", callback_data="stats_top"),
    ]]))


@Client.on_message(filters.command(["topgroup", "topgroups"]))
async def topgroup_cmd(client: Client, message: Message):
    from database import get_all_group_stats
    stats = await get_all_group_stats()
    if not stats:
        return await message.reply("📊 No group stats yet!")

    lines = ["🌍 **Most Active Groups**\n"]
    for i, (chat_id, total) in enumerate(stats):
        medal = MEDALS[i] if i < len(MEDALS) else f"`{i+1}.`"
        try:
            chat = await client.get_chat(chat_id)
            name = chat.title[:25] if chat.title else str(chat_id)
        except Exception:
            name = str(chat_id)
        lines.append(f"{medal} **{name}** — `{total:,}` msgs")

    await message.reply("\n".join(lines))


@Client.on_callback_query(filters.regex("^stats_(top|refresh)$"))
async def stats_callback(client, cq):
    await cq.answer()
    chat_id = cq.message.chat.id
    top     = await get_top_users(chat_id, limit=10)
    total   = await get_chat_total(chat_id)

    if not top:
        return await cq.answer("Abhi koi data nahi!", show_alert=True)

    lines = [f"🏆 **Rankings — {cq.message.chat.title}**\n"]
    for i, (uid, cnt) in enumerate(top):
        medal = MEDALS[i] if i < len(MEDALS) else f"`{i+1}.`"
        pct   = (cnt / total * 100) if total else 0
        try:
            user = await client.get_users(uid)
            name = user.first_name[:20]
        except Exception:
            name = str(uid)
        lines.append(f"{medal} **{name}** — `{cnt:,}` ({pct:.1f}%)")

    lines.append(f"\n💬 **Total:** `{total:,}`")
    try:
        await cq.message.edit("\n".join(lines), reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Refresh", callback_data="stats_top"),
        ]]))
    except Exception:
        pass
