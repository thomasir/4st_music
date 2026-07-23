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
            "**🎵 Music Module**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "_Studio quality audio · 1080p Video · Cookies-powered_\n\n"
            "**▶️ Play:**\n"
            "`/play <song/link>` — 🎵 Audio play\n"
            "`/vplay <song/link>` — 📺 1080p Video play\n"
            "`/playforce <song>` — ⚡ Queue skip karke instantly play\n\n"
            "**🎛️ Controls:**\n"
            "`/pause` · `/resume` · `/skip` · `/stop`\n"
            "`/loop` — 🔁 Loop ON/OFF\n"
            "`/shuffle` — 🔀 Queue shuffle\n\n"
            "**📋 Info & Volume:**\n"
            "`/np` — Now Playing card 🎶\n"
            "`/queue` — Queue list dekho 📋\n"
            "`/vol 0-200` — Volume set karo 🔊\n\n"
            "> 💡 Song naam ya YouTube link — dono kaam karte hain!\n"
            "> 🎛️ Buttons se bhi sab controls milte hain\n"
            "> 🔥 `/vol 200` = Maximum boost!"
        )
    },
    {
        "name": "👮 Admin",
        "desc": (
            "**👮 Admin Module**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "_Complete group management — ek jagah sab kuch!_\n\n"
            "**🔨 Ban / Kick / Mute:**\n"
            "`/ban [user] [reason]` — Ban karo\n"
            "`/unban [user]` — Unban karo\n"
            "`/kick [user] [reason]` — Kick karo\n"
            "`/mute [user]` — Mute karo\n"
            "`/unmute [user]` — Unmute karo\n\n"
            "**⭐ Promote / Demote:**\n"
            "`/promote [user] [title]` — Limited admin\n"
            "`/fpromote [user] [title]` — Full admin 👑\n"
            "`/demote [user]` — Admin rights hatao\n\n"
            "**⚠️ Warn System:**\n"
            "`/warn [user] [reason]` — Warn do\n"
            "`/warns [user]` — Warns history dekho\n"
            "`/clearwarn [user]` — Warns clear karo\n"
            "> 🔴🔴🔴 3 warns = auto-ban!\n\n"
            "**📌 Messages:**\n"
            "`/pin` — Pin karo · `/unpin` — Unpin\n"
            "`/purge` — Reply se ab tak delete\n"
            "`/admins` — Admin list dekho\n"
            "`/report` — Admins ko report karo\n"
            "`/banall` — Sab ban (owner only)\n\n"
            "> ⚡ Safety: 10s mein 3+ bans → auto-demote!"
        )
    },
    {
        "name": "💰 Economy",
        "desc": (
            "**💰 Economy & Games Module**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "_Virtual $ economy — earn, spend, compete!_\n"
            "_DM mein `/start` karo pehle!_\n\n"
            "**💵 Economy:**\n"
            "`/balance` — 💳 Wallet dekho\n"
            "`/daily` — 🎁 Daily reward lo\n"
            "`/transfer @user amount` — 💸 Transfer karo\n"
            "`/richlist` — 🏆 Top earners\n\n"
            "**🎮 Economy Games:**\n"
            "`/coinflip heads/tails <amount>` — 🪙 Bet lagao\n"
            "`/dice <amount>` — 🎲 Dice bet\n\n"
            "**⚔️ Social Games:**\n"
            "`/slap @user` — 👋 Thappad maaro!\n"
            "`/fight @user` — 🥊 Fight karo\n"
            "`/marry @user` — 💍 Shaadi karo\n"
            "`/divorce` — 💔 Divorce karo\n"
            "`/kill @user` — ☠️ Kill attempt\n"
            "`/rob @user` — 💰 Rob attempt\n\n"
            "> 🛡️ `/protect` se kuch der ke liye safe raho!"
        )
    },
    {
        "name": "🛡️ Safety",
        "desc": (
            "**🛡️ Safety & Protection Module**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "_Group ko 24/7 safe rakhta hai!_\n\n"
            "**🚫 Anti-Spam (Auto):**\n"
            "• Flood control — 7 msgs / 5s pe auto-mute (60s)\n"
            "• Anti-raid — 10+ joins/30s pe group lock\n"
            "• Auto unlocks after 5 minutes\n\n"
            "**🔞 Anti-Porn:**\n"
            "`/antiporn on` · `/antiporn off` — (Admin)\n"
            "• NSFW media auto-detect + delete + warn\n\n"
            "**🌍 Global Ban (GBAN):**\n"
            "`/gban @user [reason]` — Global ban\n"
            "`/ungban @user` — Global unban\n"
            "`/gbans` — Total GBANs count\n"
            "> 🤖 Gbanned users auto-ban on join!\n\n"
            "**🔤 Word Filter:**\n"
            "`/addfilter <word>` — Filter add karo\n"
            "`/rmfilter <word>` — Filter remove\n"
            "`/filters` — All filters list\n\n"
            "**😊 Auto Reactions:**\n"
            "`/reaction on` · `/reaction off` — Toggle"
        )
    },
    {
        "name": "📝 Tools",
        "desc": (
            "**📝 Tools & Utilities Module**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**📌 Notes:**\n"
            "`/note <name> <content>` — Note save\n"
            "`/get <name>` · `#notename` — Note dekho\n"
            "`/notes` — All notes list\n"
            "`/delnote <name>` — Note delete\n\n"
            "**👋 Welcome / Goodbye:**\n"
            "`/setwelcome <text>` — Welcome msg set\n"
            "`/setgoodbye <text>` — Goodbye msg set\n"
            "`/welcome on/off` · `/goodbye on/off`\n"
            "`/resetwelcome` · `/resetgoodbye`\n"
            "> Placeholders: `{mention}` `{name}` `{chat}` `{id}`\n\n"
            "**📊 Stats:**\n"
            "`/stats` — Group message stats\n"
            "`/topusers` — Top chatters 🏆\n"
            "`/topgroups` — Most active groups 🌍\n\n"
            "**🔍 User Info:**\n"
            "`/id` — User/Chat ID\n"
            "`/about` — Bot info\n"
            "`/ping` — Bot speed check\n\n"
            "**📢 Broadcast:**\n"
            "`/broadcast <msg>` — Sab users ko bhejo _(Owner)_"
        )
    },
    {
        "name": "🎮 Fun",
        "desc": (
            "**🎮 Fun & Entertainment Module**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**😂 Fun Commands:**\n"
            "`/joke` — Random joke sunao 😂\n"
            "`/shayari` — Romantic shayari 🌹\n"
            "`/quote` — Motivational quote ✨\n"
            "`/flip` — Coin flip 🪙\n"
            "`/dice` — Dice roll 🎲\n"
            "`/8ball <question>` — Magic 8-Ball 🎱\n\n"
            "**🎭 Games:**\n"
            "`/truth` — Truth question 🤔\n"
            "`/dare` — Dare challenge 😈\n"
            "`/wyr` — Would You Rather? 🤷\n"
            "`/trivia` — Trivia question 🧠\n\n"
            "**✏️ Name & DP:**\n"
            "`/genname <name>` — Fancy fonts generate\n"
            "`/gendp <name>` — Profile picture banao\n\n"
            "**🤖 AI Chatbot:**\n"
            "`/chatbot on/off` — Toggle AI replies\n"
            "• Bot reply karo ya mention karo — AI jawab dega!\n\n"
            "**🏷️ Tag:**\n"
            "`/tagall [msg]` — Sab members tag\n"
            "`/tagadmins [msg]` — Admins tag\n"
            "`/ontag [msg]` — Same as tagall"
        )
    },
]

def help_markup(page: int) -> InlineKeyboardMarkup:
    rows = []
    # Module buttons (2 per row)
    mod_btns = [
        InlineKeyboardButton(MODULES[i]["name"], callback_data=f"help_mod_{i}")
        for i in range(len(MODULES))
    ]
    for i in range(0, len(mod_btns), 2):
        rows.append(mod_btns[i:i+2])
    rows.append([
        InlineKeyboardButton("🔗 Support Chat", url=SUPPORT_CHAT),
        InlineKeyboardButton("❌ Close", callback_data="help_close"),
    ])
    return InlineKeyboardMarkup(rows)


def module_markup(page: int) -> InlineKeyboardMarkup:
    total = len(MODULES)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"help_mod_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1} / {total}", callback_data="noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"help_mod_{page+1}"))
    return InlineKeyboardMarkup([
        nav,
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="help_main"),
            InlineKeyboardButton("🔗 Support", url=SUPPORT_CHAT),
        ],
    ])


HELP_TEXT = (
    f"**🎵 {BOT_NAME}**\n"
    f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    f"🤖 _All-in-One Bot — Music · Admin · Fun · Economy_\n\n"
    f"**📂 Modules:**\n"
    f"🎵 Music — Play, Queue, Volume, Loop\n"
    f"👮 Admin — Ban, Kick, Mute, Warn, Promote\n"
    f"💰 Economy — Balance, Daily, Games\n"
    f"🛡️ Safety — Anti-spam, GBAN, Filter\n"
    f"📝 Tools — Notes, Welcome, Stats, Info\n"
    f"🎮 Fun — Jokes, Games, AI Chat, Tag\n\n"
    f"**👇 Neeche se module select karo:**"
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

    bot_me = await client.get_me()
    await message.reply(
        f"**🎵 Namaste, {name}!** 👋\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Main hun **{BOT_NAME}**\n"
        f"_Telegram ka Ultimate All-in-One Bot!_\n\n"
        f"**✨ Features:**\n"
        f"🎵 Music + Video streaming · HD quality\n"
        f"👮 Full group management suite\n"
        f"🛡️ Anti-spam · GBAN · Word filter\n"
        f"🎮 Economy · Games · AI Chat\n"
        f"📝 Notes · Stats · Broadcast\n"
        f"{reward_text}\n\n"
        f"**📊 Live Stats:**\n"
        f"> 👥 Users: **`{total_users:,}`**\n"
        f"> 💬 Groups: **`{total_chats:,}`**\n"
        f"> ⏱️ Uptime: `{uptime_str()}`\n\n"
        f"**💬 Quote:**\n"
        f"> _{quote}_\n\n"
        f"_Apne group mein add karo aur enjoy karo!_ 🚀",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Group mein Add", url=f"https://t.me/{bot_me.username}?startgroup=start"),
                InlineKeyboardButton("❓ Commands", callback_data="help_main"),
            ],
            [
                InlineKeyboardButton("🔗 Support Chat", url=SUPPORT_CHAT),
                InlineKeyboardButton(f"👑 @{OWNER_USERNAME}", url=f"https://t.me/{OWNER_USERNAME}"),
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
    await message.reply(
        f"**🎵 {BOT_NAME}** — Online Hoon! 🔥\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**▶️ Quick Start:**\n"
        f"• `/play <song>` — Music shuru karo\n"
        f"• `/vplay <song>` — 1080p Video play karo\n"
        f"• `/help` — Sab commands dekho\n\n"
        f"> 💡 _DM mein `/start` karo Economy join ke liye!_",
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
    start = time.monotonic()
    msg   = await message.reply("🏓 _Pinging..._")
    delay = (time.monotonic() - start) * 1000
    quality = "🟢 Excellent" if delay < 100 else "🟡 Good" if delay < 300 else "🔴 Slow"
    await msg.edit(
        f"**🏓 Pong!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ **Ping:** `{delay:.1f}ms` {quality}\n"
        f"⏱️ **Uptime:** `{uptime_str()}`\n"
        f"📦 **Version:** `{BOT_NAME}`\n"
        f"🐍 **Python:** 3.12\n"
        f"🔥 **Status:** Online ✅"
    )


# ── /about ────────────────────────────────────────────────────────

@Client.on_message(filters.command(["about", "info"]))
async def about_cmd(client: Client, message: Message):
    bot_me = await client.get_me()
    total_users = await get_total_users()
    total_chats = await get_total_chats()
    await message.reply(
        f"**🎵 {BOT_NAME}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 **Bot:** @{bot_me.username}\n"
        f"👑 **Owner:** @{OWNER_USERNAME}\n"
        f"📦 **Version:** `{BOT_NAME}`\n"
        f"🐍 **Language:** Python 3.12\n"
        f"📚 **Framework:** Pyrofork + PyTgCalls\n\n"
        f"**📊 Live Stats:**\n"
        f"> ⏱️ Uptime: `{uptime_str()}`\n"
        f"> 👥 Users: **`{total_users:,}`**\n"
        f"> 💬 Groups: **`{total_chats:,}`**\n\n"
        f"**📡 Features:**\n"
        f"🎵 Music/Video streaming · HD Quality\n"
        f"👮 Complete Group management\n"
        f"🛡️ Anti-spam · GBAN · Protection\n"
        f"🎮 Economy · Games · Fun\n"
        f"🤖 AI Chatbot · Auto-reactions\n",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔗 Support Chat", url=SUPPORT_CHAT),
                InlineKeyboardButton(f"👑 @{OWNER_USERNAME}", url=f"https://t.me/{OWNER_USERNAME}"),
            ],
            [
                InlineKeyboardButton("❓ Help / Commands", callback_data="help_main"),
            ]
        ]),
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
