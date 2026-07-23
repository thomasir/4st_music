"""
misc.py — v5.0 Ultimate
/start (DM) — ekdam badiya welcome, $ reward, must-join check
/start (group) — quick info
/help — modular help with Next/Back navigation (Hinglish)
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
        "emoji": "🎵",
        "desc": (
            "**🎵 Music Module**\n\n"
            "Telegram ke sabse fast music bot — Studio quality audio, 1080p video!\n\n"
            "**Commands:**\n"
            "• `/play <song/link>` — Audio play karo (YouTube link bhi!)\n"
            "• `/vplay <song/link>` — 1080p Video play karo\n"
            "• `/playforce <song>` — ⚡ Instantly play karo (queue skip)\n"
            "• `/pause` — Pause karo\n"
            "• `/resume` — Resume karo\n"
            "• `/skip` — Agli song pe jao\n"
            "• `/stop` — Band karo + queue clear\n"
            "• `/queue` — Queue dekho\n"
            "• `/np` — Abhi kya chal raha hai\n"
            "• `/vol 0-200` — Volume set karo\n\n"
            "**Tips:**\n"
            "• Song ka naam ya YouTube link dono kaam karte hain\n"
            "• Volume max hoti hai automatically\n"
            "• Buttons se bhi control kar sakte ho 🎛"
        )
    },
    {
        "name": "👮 Admin",
        "emoji": "👮",
        "desc": (
            "**👮 Admin Module**\n\n"
            "Complete group management suite — ek command mein sab!\n\n"
            "**Ban/Kick/Mute:**\n"
            "• `/ban [user] [reason]` — Ban karo\n"
            "• `/unban [user]` — Unban karo\n"
            "• `/kick [user] [reason]` — Kick karo\n"
            "• `/mute [user]` — Mute karo\n"
            "• `/unmute [user]` — Unmute karo\n\n"
            "**Promote/Demote:**\n"
            "• `/promote [user] [title]` — Admin banao (limited, no ban rights)\n"
            "• `/fpromote [user] [title]` — Full admin banao (sabhi rights)\n"
            "• `/demote [user]` — Demote karo instantly\n\n"
            "**Warn System:**\n"
            "• `/warn [user] [reason]` — Warn do (3 warns = auto-ban!)\n"
            "• `/warns [user]` — Warns dekho\n"
            "• `/clearwarn [user]` — Warns clear karo\n\n"
            "**Bulk Actions (careful!):**\n"
            "• `/banall` — Owner only: sab ban\n"
            "• `/unbanall` — Sab unban\n"
            "• `/purge` — Reply se ab tak ke messages delete\n\n"
            "**Info:**\n"
            "• `/admins` — Admin list dekho\n"
            "• `/report` — Kisi message ko admins ko report karo\n\n"
            "**⚠️ Safety:** Koi admin 10s mein 3+ ban kare → auto-demote!"
        )
    },
    {
        "name": "💰 Economy",
        "emoji": "💰",
        "desc": (
            "**💰 Economy & Games Module**\n\n"
            "Virtual $ economy — earn, spend, loot!\n"
            "Shuru karne ke liye bot ko DM mein `/start` karo!\n\n"
            "**Economy Commands:**\n"
            "• `/balance` — Apna wallet dekho\n"
            "• `/kill @user` — User ko attack karo, balance looto (65% success)\n"
            "• `/rob @user` — Rob karo (55% success)\n"
            "• `/revive [@user]` — Heal karo ($200 cost)\n"
            "• `/protect [@user]` — 4 ghante protection ($300 cost)\n"
            "• `/transfer @user amount` — Paise transfer karo\n"
            "• `/richlist` — Top 10 ameer log\n\n"
            "**First Start Bonus:** `$1,000 – $100,000` random milega!\n"
            "**Trivia Reward:** Sahi jawab pe `$50-$200` milega\n\n"
            "**Owner Controls (private):**\n"
            "• `/givemoney @user amount`\n"
            "• `/takemoney @user amount`\n"
            "• `/setmoney @user amount`\n\n"
            "**Note:** Apni 2 IDs ke beech transfer kar sakte ho!"
        )
    },
    {
        "name": "🛡 Safety",
        "emoji": "🛡",
        "desc": (
            "**🛡 Safety Module**\n\n"
            "Group ko safe rakhna humara kaam!\n\n"
            "**AntiPorn:**\n"
            "• `/antiporn on` — Enable karo\n"
            "• `/antiporn off` — Disable karo\n"
            "• Sirf **porn stickers** delete honge — normal stickers safe!\n\n"
            "**AntiSpam (Auto):**\n"
            "• 7 messages/5 seconds → 60 sec mute\n"
            "• Anti-raid: 10+ joins/30s → group lock\n\n"
            "**Word Filter:**\n"
            "• `/addfilter <word>` — Bad word add karo\n"
            "• `/rmfilter <word>` — Remove karo\n"
            "• `/filters` — List dekho\n\n"
            "**Global Ban:**\n"
            "• `/gban @user reason` — Globally ban (sudo only)\n"
            "• `/ungban @user` — Global unban\n"
            "• `/gbans` — Count dekho\n"
            "• GBanned users kisi bhi group mein aayenge to auto-ban!\n\n"
            "**Stats Spam Protection:**\n"
            "• Spam karne pe 5 min ke liye chat ranking se ban!\n"
            "• Unka message count is time mein nahi hoga"
        )
    },
    {
        "name": "📊 Stats",
        "emoji": "📊",
        "desc": (
            "**📊 Stats & Rankings Module**\n\n"
            "Group activity track karo — messages + media sab count!\n\n"
            "**Commands:**\n"
            "• `/stats` — Apni stats + group stats dekho\n"
            "• `/rankings` — Top 10 active members\n"
            "• `/topusers` — Same as rankings\n"
            "• `/leaderboard` — Same as rankings\n"
            "• `/topgroup` — Sabse active groups (global)\n\n"
            "**Works with @username:**\n"
            "• `/rankings@botusername` — Group mein bhi kaam karta hai\n\n"
            "**What counts:**\n"
            "• ✅ Messages, Photos, Videos, Audio, Stickers, Documents — sab!\n"
            "• ❌ Spam karne pe 5 min ke liye rank se temporary ban"
        )
    },
    {
        "name": "👋 Welcome",
        "emoji": "👋",
        "desc": (
            "**👋 Welcome Module**\n\n"
            "Members ko pyaar se welcome karo!\n\n"
            "**Commands:**\n"
            "• `/setwelcome <text>` — Custom welcome set karo\n"
            "• `/setgoodbye <text>` — Custom goodbye set karo\n"
            "• `/welcome on/off` — Toggle\n"
            "• `/goodbye on/off` — Toggle\n"
            "• `/resetwelcome` — Default pe wapas\n"
            "• `/resetgoodbye` — Default pe wapas\n\n"
            "**Placeholders:**\n"
            "• `{mention}` — User ka mention\n"
            "• `{name}` — User ka naam\n"
            "• `{chat}` — Group ka naam\n"
            "• `{id}` — User ID\n\n"
            "**Example:**\n"
            "`/setwelcome 🎉 {mention} welcome to {chat}! Enjoy! 🔥`"
        )
    },
    {
        "name": "📝 Notes",
        "emoji": "📝",
        "desc": (
            "**📝 Notes Module**\n\n"
            "Group ke important notes save karo!\n\n"
            "**Save & Get:**\n"
            "• `/savenote rules Hello! Follow rules!` — Note save karo\n"
            "• `#rules` — Note get karo (anytime!)\n\n"
            "**Manage:**\n"
            "• `/notes` — Sab notes ki list\n"
            "• `/delnote rules` — Note delete karo\n\n"
            "**Tip:** Note naam lowercase hota hai automatically"
        )
    },
    {
        "name": "🎮 Games",
        "emoji": "🎮",
        "desc": (
            "**🎮 Classic Games Module**\n\n"
            "Group mein mazaa karo!\n\n"
            "**Games:**\n"
            "• `/truth` — Random truth question\n"
            "• `/dare` — Random dare challenge\n"
            "• `/wyr` — Would You Rather?\n"
            "• `/trivia` — Quiz question (sahi jawab pe $ milenge!)\n\n"
            "**Economy Games (in Economy section):**\n"
            "• /kill, /rob, /revive, /protect, /transfer\n\n"
            "**Tip:** Trivia ka sahi jawab 10 sec mein dena hai!"
        )
    },
    {
        "name": "🤖 ChatBot",
        "emoji": "🤖",
        "desc": (
            "**🤖 ChatBot Module**\n\n"
            "Bot group mein baat karta hai — aur seekhta bhi hai!\n\n"
            "**Commands:**\n"
            "• `/chatbot on` — Enable karo\n"
            "• `/chatbot off` — Disable karo\n\n"
            "**Kaise kaam karta hai:**\n"
            "• Bot ke message ko reply karo → Bot seekh lega\n"
            "• Bot ka mention karo → Direct reply milega\n"
            "• Random 10% messages pe bhi reply karega\n"
            "• Hinglish mein baat karta hai 😄\n\n"
            "**Learning:**\n"
            "• Users ki conversations se data collect karta hai\n"
            "• Jitna zyada use karo, utna smart hoga!\n"
            "• Built-in 50+ responses already hain"
        )
    },
    {
        "name": "🔔 Reactions",
        "emoji": "🔔",
        "desc": (
            "**🔔 Auto Reaction Module**\n\n"
            "Bot messages pe automatically react karta hai!\n\n"
            "**Commands:**\n"
            "• `/reaction on` — Enable karo\n"
            "• `/reaction off` — Disable karo\n\n"
            "**Kab react karta hai:**\n"
            "• 1 in 7 random messages pe\n"
            "• Links wale messages pe (hamesha)\n"
            "• Welcome messages pe\n\n"
            "**Reactions:** ❤️ 👍 🔥 🎉 😂 🤩 👏 😍 💯 aur bhi!"
        )
    },
    {
        "name": "📢 Tag All",
        "emoji": "📢",
        "desc": (
            "**📢 Tag All Module**\n\n"
            "Saare members ko ek saath tag karo!\n\n"
            "**Commands:**\n"
            "• `/tagall` — Sab ko tag karo\n"
            "• `/tagall <message>` — Tag + custom message\n"
            "• `/ontag` — Same as tagall\n"
            "• `/ontag <message>` — Tag + message\n\n"
            "**Note:** Sirf admins use kar sakte hain\n\n"
            "**Tip:** Bot+sticker wale skip hote hain automatically"
        )
    },
    {
        "name": "🎨 Utility",
        "emoji": "🎨",
        "desc": (
            "**🎨 Utility Module**\n\n"
            "Fun utility commands!\n\n"
            "**Info:**\n"
            "• `/info` ya `/info @user` — User info + name history\n"
            "  Dikhata hai: kitne groups mein hai, kab-kab naam badla\n\n"
            "**Fancy Name Generator:**\n"
            "• `/genname YourName` — 10+ fancy Unicode fonts mein naam\n"
            "  (Bold, Script, Fraktur, Double Struck, Gothic aur bhi!)\n\n"
            "**DP Generator:**\n"
            "• `/gendp YourName` — Colored profile picture banao\n"
            "• `/gendp birthday Name` — Birthday DP 🎂\n"
            "• `/gendp couple Name1 & Name2` — Couple DP 💑\n\n"
            "**Couples:**\n"
            "• `/couples` — Group ke random members ki jodian banao 💑\n\n"
            "**Other:**\n"
            "• `/id` — User/Chat ID dekho\n"
            "• `/ping` — Bot ki speed check karo"
        )
    },
    {
        "name": "😂 Fun",
        "emoji": "😂",
        "desc": (
            "**😂 Fun Module**\n\n"
            "Group mein entertainment ke liye!\n\n"
            "**Commands:**\n"
            "• `/joke` — Random Hindi/English joke 😂\n"
            "• `/shayari` — Dil se shayari 🌹\n"
            "• `/quote` — Motivational quote 💫\n"
            "• `/flip` — Coin flip 🪙\n"
            "• `/dice` — Dice roll 🎲\n"
            "• `/8ball <question>` — Magic 8-ball 🔮\n\n"
            "**Broadcast:**\n"
            "• `/broadcast <text>` — Owner only: sab users + groups + channels mein bhejo"
        )
    },
]

PAGE_SIZE = 1  # One module per page for clean navigation


def _help_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Back", callback_data=f"help_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total}", callback_data="help_noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"help_{page+1}"))
    buttons.append(nav)
    buttons.append([InlineKeyboardButton("🏠 Home", callback_data="help_home")])
    return InlineKeyboardMarkup(buttons)


def _module_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    """Module list keyboard for /help home."""
    rows = []
    row = []
    for i, m in enumerate(MODULES):
        row.append(InlineKeyboardButton(m["name"], callback_data=f"help_{i}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


HOME_TEXT = (
    f"**📖 Apex Bot Help**\n\n"
    f"Neeche se module choose karo — har module ki full guide milegi!\n\n"
    f"**Quick Commands:**\n"
    f"🎵 `/play <song>` — Music\n"
    f"💰 `/balance` — Economy wallet\n"
    f"📊 `/rankings` — Top users\n"
    f"👤 `/info` — User info\n"
    f"✨ `/genname Name` — Fancy fonts\n"
    f"🔔 `/reaction on` — Auto reactions\n"
    f"🤖 `/chatbot on` — AI ChatBot\n"
    f"🔞 `/antiporn on` — AntiPorn\n"
    f"📢 `/tagall` — Tag all members\n\n"
    f"_Ek module select karo detailed guide ke liye_ 👇"
)


# ══ MUST JOIN CHECK ════════════════════════════════════════════════

async def _check_must_join(client: Client, user_id: int) -> bool:
    """Returns True if user can proceed (joined or no must-join required)."""
    if not MUST_JOIN:
        return True
    try:
        from pyrogram.enums import ChatMemberStatus
        member = await client.get_chat_member(f"@{MUST_JOIN}", user_id)
        return member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    except Exception:
        return True  # If can't check, let through


async def _log_start(client: Client, message: Message):
    if not LOG_CHANNEL:
        return
    user  = message.from_user
    if not user:
        return
    uname = f"@{user.username}" if user.username else user.first_name
    try:
        await client.send_message(
            LOG_CHANNEL,
            f"**📲 New /start**\n"
            f"👤 {uname} (`{user.id}`)\n"
            f"💬 Chat: `{message.chat.id}`"
        )
    except Exception:
        pass


# ══ /start ════════════════════════════════════════════════════════

@Client.on_message(filters.command(["start"]) & filters.private)
async def start_private(client: Client, message: Message):
    user = message.from_user
    if not user:
        return

    asyncio.create_task(_log_start(client, message))

    # Register user
    try:
        await register_user(user.id, user.username or "", user.first_name or "")
    except Exception:
        pass

    # Must-join check
    if MUST_JOIN and not await _check_must_join(client, user.id):
        try:
            chat = await client.get_chat(f"@{MUST_JOIN}")
            chan_title = chat.title or MUST_JOIN
            invite = f"https://t.me/{MUST_JOIN}"
        except Exception:
            chan_title = MUST_JOIN
            invite = f"https://t.me/{MUST_JOIN}"

        await message.reply(
            f"⚠️ **Pehle humara channel join karo!**\n\n"
            f"📢 **{chan_title}** join karo, phir wapas `/start` karo.\n\n"
            f"_Bot use karne ke liye channel membership zaroori hai!_",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"➕ {chan_title} Join", url=invite)],
                [InlineKeyboardButton("✅ Join kar liya!", callback_data="check_join")],
            ])
        )
        return

    bot_me = await client.get_me()

    # Economy: first start bonus
    is_first = not await has_started(user.id)
    bonus_text = ""
    if is_first:
        bonus = random.randint(FIRST_START_MIN, FIRST_START_MAX)
        await init_economy(user.id, bonus)
        bonus_text = (
            f"\n\n🎁 **FIRST START BONUS!**\n"
            f"💰 **${bonus:,}** tumhare wallet mein aa gaye!\n"
            f"`/balance` se check karo 💎"
        )
    else:
        bal = await get_balance(user.id)
        bonus_text = f"\n\n💰 **Tumhara balance:** `${bal:,}`"

    total_chats = await get_total_chats()
    total_users = await get_total_users()

    welcome_msg = (
        f"**🎵 Apex All-in-One Bot**\n"
        f"_{BOT_VERSION}_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ **Ultra-fast** music (< 3s start)\n"
        f"🎵 Studio quality audio + 1080p video\n"
        f"👮 Full admin suite (promote/demote/ban)\n"
        f"🛡 AntiPorn + AntiSpam + Word Filter\n"
        f"💰 Economy system ($kill/rob/protect)\n"
        f"🤖 AI ChatBot (Hinglish + learning)\n"
        f"📊 Complete rankings + stats\n"
        f"🎨 DP & Font generator\n"
        f"📢 Tag all, Auto reactions, Couples\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Groups served: `{total_chats:,}` | 👤 Users: `{total_users:,}`"
        f"{bonus_text}"
    )

    await message.reply(
        welcome_msg,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Help & Commands", callback_data="help_home"),
             InlineKeyboardButton("💰 My Wallet", callback_data="my_wallet")],
            [InlineKeyboardButton("➕ Add to Group",
                                  url=f"https://t.me/{bot_me.username}?startgroup=true")],
            [InlineKeyboardButton("💬 Support", url=SUPPORT_CHAT),
             InlineKeyboardButton(f"👑 @{OWNER_USERNAME}", url=f"https://t.me/{OWNER_USERNAME}")],
        ])
    )


@Client.on_callback_query(filters.regex("^check_join$"))
async def check_join_cb(client, cq):
    user_id = cq.from_user.id
    if await _check_must_join(client, user_id):
        await cq.answer("✅ Verified! Ab /start karo.", show_alert=True)
        try:
            await cq.message.delete()
        except Exception:
            pass
    else:
        await cq.answer("❌ Abhi bhi join nahi kiya!", show_alert=True)


@Client.on_callback_query(filters.regex("^my_wallet$"))
async def my_wallet_cb(client, cq):
    user_id = cq.from_user.id
    if not await has_started(user_id):
        return await cq.answer("❌ /start karo pehle!", show_alert=True)
    bal = await get_balance(user_id)
    await cq.answer(f"💰 Balance: ${bal:,}", show_alert=True)


@Client.on_message(filters.command(["start"]) & filters.group)
async def start_group(client: Client, message: Message):
    try:
        await register_chat(message.chat.id, message.chat.title or "")
    except Exception:
        pass
    asyncio.create_task(_log_start(client, message))
    bot_me = await client.get_me()
    await message.reply(
        f"**🎵 Apex Bot — Ready to rock!**\n\n"
        f"📖 `/help` — Full commands guide\n"
        f"🎵 `/play <song>` — Music shuru karo\n"
        f"💰 DM mein `/start` karo economy ke liye!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Help", callback_data="help_home"),
             InlineKeyboardButton("🎵 Play Music", callback_data="play_help")],
        ])
    )


# ══ /help ═════════════════════════════════════════════════════════

@Client.on_message(filters.command(["help", "h"]))
async def help_cmd(client: Client, message: Message):
    await message.reply(
        HOME_TEXT,
        reply_markup=_module_keyboard(0, len(MODULES))
    )


@Client.on_callback_query(filters.regex("^help_home$"))
async def help_home_cb(client, cq):
    await cq.answer()
    try:
        await cq.message.edit(HOME_TEXT, reply_markup=_module_keyboard(0, len(MODULES)))
    except Exception:
        await cq.message.reply(HOME_TEXT, reply_markup=_module_keyboard(0, len(MODULES)))


@Client.on_callback_query(filters.regex(r"^help_(\d+)$"))
async def help_page_cb(client, cq):
    await cq.answer()
    page = int(cq.data.split("_")[1])
    total = len(MODULES)
    if page < 0 or page >= total:
        return
    mod = MODULES[page]
    text = mod["desc"]
    kb   = _help_keyboard(page, total)
    try:
        await cq.message.edit(text, reply_markup=kb)
    except Exception:
        await cq.message.reply(text, reply_markup=kb)


@Client.on_callback_query(filters.regex("^help_noop$"))
async def help_noop(client, cq):
    await cq.answer()


@Client.on_callback_query(filters.regex("^play_help$"))
async def play_help_cb(client, cq):
    await cq.answer()
    await cq.message.reply(
        "🎵 `/play <song naam ya YouTube link>` — Audio\n"
        "🎬 `/vplay <song naam ya YouTube link>` — Video\n"
        "⚡ `/playforce <song>` — Instant play!"
    )


# ══ /ping ══════════════════════════════════════════════════════════

@Client.on_message(filters.command(["ping"]))
async def ping_cmd(client: Client, message: Message):
    start = time.time()
    msg   = await message.reply("🏓 Pinging...")
    ms    = round((time.time() - start) * 1000, 2)
    await msg.edit(
        f"🏓 **Pong!**\n\n"
        f"⚡ Response: `{ms}ms`\n"
        f"⏰ Uptime: `{uptime_str()}`"
    )


# ══ /id ════════════════════════════════════════════════════════════

@Client.on_message(filters.command(["id"]))
async def id_cmd(client: Client, message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        text = (
            f"👤 **User ID Info:**\n"
            f"🏷 Name : {u.mention}\n"
            f"🆔 ID   : `{u.id}`\n"
            f"📛 Username: @{u.username or 'None'}"
        )
    else:
        user_id_text = f"`{message.from_user.id}`" if message.from_user else "_Unknown (anonymous/channel)_"
        text = (
            f"💬 **Chat ID:** `{message.chat.id}`\n"
            f"👤 **Your ID:** {user_id_text}"
        )
    await message.reply(text)
