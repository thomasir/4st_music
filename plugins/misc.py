"""
misc.py — v6.0 Ultimate
/start — animated welcome + economy reward + must-join check
/help  — paginated modular help with callbacks
/ping, /about, /id
"""

import time
import random
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from config import (
    BOT_NAME, BOT_VERSION, OWNER_ID, OWNER_USERNAME,
    LOG_CHANNEL, SUPPORT_CHAT, MUST_JOIN,
    FIRST_START_MIN, FIRST_START_MAX,
    DAILY_REWARD_MIN, DAILY_REWARD_MAX
)
from database import (
    has_started, init_economy, add_balance, get_balance,
    register_user, register_chat, get_total_chats, get_total_users
)

log = logging.getLogger("ApexBot.misc")
START_TIME = time.time()

MOTIVATIONAL_QUOTES = [
    "\"Sapne woh nahi jo aankh band karne se aate hain, sapne woh hain jo aankh khulne nahi dete.\" — APJ Abdul Kalam ✨",
    "\"Kamyabi ki raah mein mushkilein toh aayengi, par har mushkil ek naya sabak lekar aati hai.\" — Anonymous 🌟",
    "\"Haar mat maano jab tak jeet na jao — phir dekho duniya kya kehti hai.\" — Unknown 🔥",
    "\"Jo aaj ke liye jeeta hai, kal ki fikar usse kabhi nahi hoti.\" — Anonymous 💫",
    "\"Mushkilon se bhaago nahi, unhe apni taaqat banao.\" — Unknown 💪",
    "\"Success is not final, failure is not fatal: It is the courage to continue that counts.\" — Churchill 🏆",
    "\"Believe you can and you're halfway there.\" — Theodore Roosevelt ⭐",
    "\"Zindagi mein do cheezein kabhi waste nahi hoti — waqt aur mehnat.\" — Unknown ⏳",
]


def uptime_str() -> str:
    elapsed = int(time.time() - START_TIME)
    h, rem  = divmod(elapsed, 3600)
    m, s    = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


# ══════════════════════════════════════════════════════════════════
# MODULAR HELP SYSTEM
# ══════════════════════════════════════════════════════════════════

MODULES = [
    {
        "name": "🎵 Music",
        "desc": (
            "**🎵 Music Module**\n\n"
            "Telegram ka sabse fast music bot — Studio quality audio, 1080p video!\n\n"
            "**▶️ Play Commands:**\n"
            "• `/play <song/link>` — Audio play karo\n"
            "• `/vplay <song/link>` — 1080p Video play karo\n"
            "• `/playforce <song>` — ⚡ Instantly play (queue skip)\n\n"
            "**🎛️ Controls:**\n"
            "• `/pause` — Pause karo\n"
            "• `/resume` — Resume karo\n"
            "• `/skip` — Agli song pe jao\n"
            "• `/stop` — Band karo + queue clear\n"
            "• `/loop` — 🔁 Loop toggle\n"
            "• `/shuffle` — 🔀 Queue shuffle\n\n"
            "**📋 Info:**\n"
            "• `/queue` — Queue dekho\n"
            "• `/np` — Now Playing card\n"
            "• `/vol 0-200` — Volume set karo\n\n"
            "**💡 Tips:**\n"
            "> Song ka naam ya YouTube link dono kaam karte hain!\n"
            "> Buttons se bhi control kar sakte ho 🎛️\n"
            "> `/vol 200` = maximum boost 🔥"
        )
    },
    {
        "name": "👮 Admin",
        "desc": (
            "**👮 Admin Module**\n\n"
            "Complete group management — ek jagah sab kuch!\n\n"
            "**🔨 Ban/Kick/Mute:**\n"
            "• `/ban [user] [reason]` — Ban karo\n"
            "• `/unban [user]` — Unban karo\n"
            "• `/kick [user] [reason]` — Kick karo\n"
            "• `/mute [user]` — Mute karo\n"
            "• `/unmute [user]` — Unmute karo\n\n"
            "**⭐ Promote/Demote:**\n"
            "• `/promote [user] [title]` — Admin banao\n"
            "• `/fpromote [user] [title]` — Full admin\n"
            "• `/demote [user]` — Demote karo\n\n"
            "**⚠️ Warn System:**\n"
            "• `/warn [user] [reason]` — Warn do (3 = auto-ban!)\n"
            "• `/warns [user]` — Warns dekho\n"
            "• `/clearwarn [user]` — Warns clear karo\n\n"
            "**📌 Other:**\n"
            "• `/pin` — Message pin karo\n"
            "• `/unpin` — Unpin karo\n"
            "• `/purge` — Reply se ab tak delete\n"
            "• `/admins` — Admin list\n"
            "• `/report` — Admins ko report karo\n\n"
            "> ⚠️ **Safety:** 10s mein 3+ bans → auto-demote!"
        )
    },
    {
        "name": "💰 Economy",
        "desc": (
            "**💰 Economy & Games Module**\n\n"
            "Virtual $ economy — earn, spend, compete!\n"
            "Shuru karne ke liye bot ko DM mein `/start` karo!\n\n"
            "**💵 Economy:**\n"
            "• `/balance` — Wallet dekho\n"
            "• `/daily` — Daily reward lo\n"
            "• `/transfer @user amount` — Transfer karo\n"
            "• `/richlist` — Top earners\n\n"
            "**🎮 Games:**\n"
            "• `/coinflip heads/tails amount` — Coin flip bet\n"
            "• `/dice amount` — Dice roll bet\n"
            "• `/slap @user` — Thappad maaro 😂\n"
            "• `/fight @user` — Fight karo\n"
            "• `/marry @user` — Shaadi karo 💍\n"
            "• `/divorce` — Divorce karo 💔\n\n"
            "> 💡 `/start` karo DM mein pehli baar ke liye reward milega!"
        )
    },
    {
        "name": "🛡️ Safety",
        "desc": (
            "**🛡️ Safety & Protection Module**\n\n"
            "Group ko safe rakhta hai — 24/7!\n\n"
            "**🚫 Anti-Spam:**\n"
            "• Auto-detect aur ban spam users\n"
            "• Flood control — too many messages\n"
            "• New join protection\n\n"
            "**🔞 Anti-Porn:**\n"
            "• `/antiporn on/off` — Toggle (Admin)\n"
            "• NSFW media auto-detect + delete\n\n"
            "**🌍 Global Ban:**\n"
            "• `/gban @user [reason]` — Global ban\n"
            "• `/ungban @user` — Ungban\n"
            "• `/gbans` — Total GBANs dekho\n\n"
            "**🔤 Word Filter:**\n"
            "• `/addfilter <word>` — Word filter add\n"
            "• `/rmfilter <word>` — Filter remove\n"
            "• `/filters` — All filters dekho\n\n"
            "> 🤖 Bot auto-bans gbanned users on join!"
        )
    },
    {
        "name": "📝 Tools",
        "desc": (
            "**📝 Tools & Utilities Module**\n\n"
            "**📌 Notes:**\n"
            "• `/note <name> <content>` — Note save karo\n"
            "• `/get <name>` — Note dekho\n"
            "• `/notes` — All notes\n"
            "• `/delnote <name>` — Delete note\n\n"
            "**👋 Welcome:**\n"
            "• `/setwelcome <text>` — Welcome msg set\n"
            "• `/setgoodbye <text>` — Goodbye msg set\n"
            "• `/welcome on/off` — Toggle\n\n"
            "**📊 Stats:**\n"
            "• `/stats` — Group stats dekho\n"
            "• `/topusers` — Top chatters\n"
            "• `/topgroups` — Most active groups\n\n"
            "**📢 Broadcast (Owner only):**\n"
            "• `/broadcast <msg>` — Sab ko bhejo\n\n"
            "**🔍 User Info:**\n"
            "• `/id` — User ID dekho\n"
            "• `/info @user` — User details\n"
            "• `/whois @user` — Full info"
        )
    },
    {
        "name": "🎮 Fun",
        "desc": (
            "**🎮 Fun & Entertainment Module**\n\n"
            "**😂 Fun:**\n"
            "• `/joke` — Random joke\n"
            "• `/shayari` — Romantic shayari\n"
            "• `/quote` — Motivational quote\n"
            "• `/flip` — Coin flip\n"
            "• `/dice` — Dice roll\n"
            "• `/8ball <question>` — Magic 8ball\n\n"
            "**🤖 AI Chatbot:**\n"
            "• Group mein mention karo ya reply karo\n"
            "• Bot seekhta hai aur respond karta hai\n"
            "• `/chatbot on/off` — Toggle\n\n"
            "**🏷️ TagAll:**\n"
            "• `/tagall <msg>` — Sab ko tag karo\n"
            "• `/tagadmins <msg>` — Admins ko tag\n\n"
            "**😊 Reactions:**\n"
            "• `/react on/off` — Auto reactions toggle\n\n"
            "> 💡 `/chatbot on` karo aur bot se baat karo!"
        )
    },
]

def help_markup(page: int) -> InlineKeyboardMarkup:
    total = len(MODULES)
    rows = []
    # Module buttons (2 per row)
    mod_btns = [
        InlineKeyboardButton(MODULES[i]["name"], callback_data=f"help_mod_{i}")
        for i in range(total)
    ]
    for i in range(0, len(mod_btns), 2):
        rows.append(mod_btns[i:i+2])
    # Bottom nav
    rows.append([
        InlineKeyboardButton("🔗 Support", url=SUPPORT_CHAT),
        InlineKeyboardButton("❌ Close", callback_data="help_close"),
    ])
    return InlineKeyboardMarkup(rows)


def module_markup(page: int) -> InlineKeyboardMarkup:
    total = len(MODULES)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"help_mod_{page-1}"))
    nav.append(InlineKeyboardButton(f"📋 {page+1}/{total}", callback_data="noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"help_mod_{page+1}"))
    return InlineKeyboardMarkup([
        nav,
        [InlineKeyboardButton("🏠 Main Menu", callback_data="help_main")],
    ])


HELP_TEXT = (
    f"**🎵 {BOT_NAME} — Help Menu**\n\n"
    "Main ek all-in-one bot hun — Music, Admin, Fun sab kuch!\n\n"
    "**Module select karo neeche se** 👇"
)


# ══════════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════════

@Client.on_message(filters.command(["start"]) & filters.private)
async def start_private(client: Client, message: Message):
    user_id  = message.from_user.id
    username = message.from_user.username or "User"
    name     = message.from_user.first_name or "User"

    await register_user(
        user_id,
        username,
        name,
    )

    # Must-join check
    if MUST_JOIN:
        try:
            await client.get_chat_member(MUST_JOIN, user_id)
        except Exception:
            await message.reply(
                f"**⚠️ Pehle join karo!**\n\n"
                f"Bot use karne ke liye pehle hamara channel join karna zaroori hai:\n\n"
                f"👉 **[Join Channel](https://t.me/{MUST_JOIN})**\n\n"
                f"_Join karo phir /start karo!_",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{MUST_JOIN}"),
                ]]),
                disable_web_page_preview=True,
            )
            return

    # Economy first start reward
    reward_text = ""
    already = await has_started(user_id)
    if not already:
        await init_economy(user_id, 0)
        reward = random.randint(FIRST_START_MIN, FIRST_START_MAX)
        await add_balance(user_id, reward)
        reward_text = (
            f"\n\n💰 **Welcome Bonus: `${reward:,}`** 🎉\n"
            f"_Pehli baar aa rahe ho — ye lo ek gift!_"
        )
    else:
        bal = await get_balance(user_id)
        reward_text = f"\n\n💳 **Your Balance: `${bal:,}`**"

    total_users  = await get_total_users()
    total_chats  = await get_total_chats()
    quote        = random.choice(MOTIVATIONAL_QUOTES)

    await message.reply(
        f"**🎵 Namaste, {name}!** 👋\n\n"
        f"Main hun **{BOT_NAME}** — Telegram ka sabse badiya All-in-One bot!\n\n"
        f"**✨ Kya kya kar sakta hun:**\n"
        f"> 🎵 Music + Video streaming (HD quality)\n"
        f"> 👮 Full group management\n"
        f"> 🛡️ Anti-spam, GBAN, Word filter\n"
        f"> 🎮 Games + Economy + AI Chat\n"
        f"> 📝 Notes, Stats, Broadcast\n"
        f"{reward_text}\n\n"
        f"**📊 Bot Stats:**\n"
        f"> 👥 Users: `{total_users:,}`\n"
        f"> 💬 Groups: `{total_chats:,}`\n\n"
        f"**💬 Quote of the Day:**\n"
        f"> _{quote}_\n\n"
        f"_Apne group mein add karo aur enjoy karo!_ 🚀",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Group mein Add karo", url=f"https://t.me/{(await client.get_me()).username}?startgroup=start"),
                InlineKeyboardButton("❓ Help", callback_data="help_main"),
            ],
            [
                InlineKeyboardButton("🔗 Support", url=SUPPORT_CHAT),
                InlineKeyboardButton(f"👤 Owner: @{OWNER_USERNAME}", url=f"https://t.me/{OWNER_USERNAME}"),
            ],
        ]),
        disable_web_page_preview=True,
    )

    # Log new user
    if LOG_CHANNEL and not already:
        try:
            await client.send_message(
                LOG_CHANNEL,
                f"👤 **New User!**\n"
                f"Name: {message.from_user.mention}\n"
                f"ID: `{user_id}`\n"
                f"Username: @{username}\n"
                f"Total users: `{total_users:,}`"
            )
        except Exception:
            pass


@Client.on_message(filters.command(["start"]) & filters.group)
async def start_group(client: Client, message: Message):
    await register_chat(message.chat.id, message.chat.title, "group")
    bot_me = await client.get_me()
    await message.reply(
        f"**🎵 {BOT_NAME}** — Online hun! 🔥\n\n"
        f"• `/play <song>` — Music shuru karo\n"
        f"• `/help` — Sab commands dekho\n\n"
        f"_DM mein /start karo economy join karne ke liye!_",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❓ Help & Commands", callback_data="help_main"),
            InlineKeyboardButton("🔗 Support", url=SUPPORT_CHAT),
        ]]),
    )


# ── /help ─────────────────────────────────────────────────────────

@Client.on_message(filters.command(["help", "h"]))
async def help_cmd(client: Client, message: Message):
    asyncio.create_task(_try_delete(message))
    await message.reply(
        HELP_TEXT,
        reply_markup=help_markup(0),
    )


async def _try_delete(msg):
    try:
        await msg.delete()
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^help_main$"))
async def cb_help_main(client, cq):
    await cq.answer()
    try:
        await cq.message.edit(HELP_TEXT, reply_markup=help_markup(0))
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^help_mod_(\d+)$"))
async def cb_help_module(client, cq):
    await cq.answer()
    page = int(cq.data.split("_")[-1])
    if page >= len(MODULES):
        return
    mod = MODULES[page]
    try:
        await cq.message.edit(mod["desc"], reply_markup=module_markup(page))
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^help_close$"))
async def cb_help_close(client, cq):
    await cq.answer("✅ Closed!")
    try:
        await cq.message.delete()
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^noop$"))
async def cb_noop(client, cq):
    await cq.answer()


# ── /ping ─────────────────────────────────────────────────────────

@Client.on_message(filters.command(["ping"]))
async def ping_cmd(client: Client, message: Message):
    start  = time.monotonic()
    msg    = await message.reply("🏓 Pinging...")
    delay  = (time.monotonic() - start) * 1000
    await msg.edit(
        f"**🏓 Pong!**\n\n"
        f"⚡ Ping: `{delay:.1f}ms`\n"
        f"⏱️ Uptime: `{uptime_str()}`\n"
        f"📦 Version: `{BOT_NAME}`"
    )


# ── /about ────────────────────────────────────────────────────────

@Client.on_message(filters.command(["about", "info"]))
async def about_cmd(client: Client, message: Message):
    bot_me = await client.get_me()
    total_users = await get_total_users()
    total_chats = await get_total_chats()
    await message.reply(
        f"**🎵 {BOT_NAME}**\n\n"
        f"> 🤖 Bot: @{bot_me.username}\n"
        f"> 👑 Owner: @{OWNER_USERNAME}\n"
        f"> 📦 Version: `{BOT_NAME}`\n"
        f"> 🐍 Language: Python 3.12\n"
        f"> 📚 Framework: Pyrofork + PyTgCalls\n"
        f"> ⏱️ Uptime: `{uptime_str()}`\n"
        f"> 👥 Users: `{total_users:,}`\n"
        f"> 💬 Groups: `{total_chats:,}`\n\n"
        f"**📡 Features:**\n"
        f"> 🎵 Music/Video streaming\n"
        f"> 👮 Group management\n"
        f"> 🛡️ Anti-spam & GBAN\n"
        f"> 🎮 Economy & Games\n"
        f"> 🤖 AI Chatbot\n",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔗 Support", url=SUPPORT_CHAT),
            InlineKeyboardButton("👤 Owner", url=f"https://t.me/{OWNER_USERNAME}"),
        ]]),
        disable_web_page_preview=True,
    )


# ── /id ───────────────────────────────────────────────────────────

@Client.on_message(filters.command(["id"]))
async def id_cmd(client: Client, message: Message):
    user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    chat = message.chat
    lines = [
        f"**🆔 ID Info**\n",
        f"👤 **User:** {user.mention}",
        f"🔢 **User ID:** `{user.id}`",
    ]
    if user.username:
        lines.append(f"📛 **Username:** @{user.username}")
    if chat.type.name in ("GROUP", "SUPERGROUP", "CHANNEL"):
        lines.append(f"\n💬 **Chat:** {chat.title}")
        lines.append(f"🔢 **Chat ID:** `{chat.id}`")
    await message.reply("\n".join(lines))
