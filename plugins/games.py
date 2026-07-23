"""
games.py — v6.0 Ultimate
Economy: $ system (kill, rob, revive, protection, leaderboard, transfer, daily)
Social: marry, divorce, slap, fight
Classic: truth, dare, wyr, trivia
BUG FIXES:
  - /daily command added (was missing — help menu mentioned it)
  - /marry, /divorce, /slap, /fight added (were missing — help menu mentioned them)
  - trivia asyncio.sleep(10) moved to create_task (was blocking event loop for 10s)
  - remove_balance return value not checked in kill/rob — now handled properly
"""

import random
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_balance, add_balance, remove_balance, set_balance, transfer_balance,
    get_top_rich, is_protected, set_protection, get_protection_until,
    has_started, init_economy, spam_rank_ban,
    get_daily_last, set_daily_last,
    get_partner, marry_users, divorce_user
)
from config import OWNER_ID, DAILY_REWARD_MIN, DAILY_REWARD_MAX, MUST_JOIN

# ══════════════════════════════════════════════════════
# ── CLASSIC GAMES DATA
# ══════════════════════════════════════════════════════

TRUTHS = [
    "Apna sabse bada secret batao jo kisi ko nahi pata?",
    "Agar zindagi mein ek cheez badal sako, kya badloge?",
    "Tumhara first crush kaun tha?",
    "Kabhi kisi ke saath jhooth bola hai? Kya tha woh?",
    "Sabse embarrassing moment kya tha tumhari zindagi ka?",
    "Agar ek din ke liye invisible ho jao toh kya karoge?",
    "Kaunsa app tumhare phone pe sabse zyada use hota hai?",
    "Aaj tak ki sabse badi galti kya hai?",
    "Tumhara dream job kya hai?",
    "Kounsi baat tumhe raat ko sone nahi deti?",
    "Agar ek celebrity se milne ka mauka mile toh kaun hoga?",
    "Tumhara sabse bura kaam kya hai jo tune kisi ke saath kiya?",
    "Kabhi kisi ke peeche bura bola hai? Kya kaha?",
    "Agar aaj akhri din ho tumhara, kya karoge?",
]

DARES = [
    "Next 5 messages mein sirf CAPS LOCK mein type karo",
    "Apna last received meme bhejo group mein",
    "Abhi apne favourite person ko text karo 'I miss you'",
    "Next 3 messages sirf emoji mein karo",
    "Apna current wallpaper share karo",
    "Apni favourite movie ka dialogue type karo bina Google ke",
    "10 second mein apna naam reverse mein type karo",
    "Kisi bhi group member ko publicly compliment do",
    "Apna pehla message is group mein dhundho aur quote karo",
    "Bina spell check ke koi bhi long word type karo",
    "Apni voice note bhejo '🎵 La la la' gaate hue",
    "Apna password hint batao (sirf hint!)",
]

WYR_QUESTIONS = [
    "🤔 **Would You Rather:**\n\n🔴 Hamesha sach bolna\n🔵 Hamesha jhooth bol sakna",
    "🤔 **Would You Rather:**\n\n🔴 Superpower: udna\n🔵 Superpower: invisible hona",
    "🤔 **Would You Rather:**\n\n🔴 Hamesha khush rehna par gareeb\n🔵 Ameer rehna par kabhi udaas",
    "🤔 **Would You Rather:**\n\n🔴 Bina internet ke rehna\n🔵 Bina ghar ke rehna",
    "🤔 **Would You Rather:**\n\n🔴 Har 30 min mein neend aaye\n🔵 Kabhi neend na aaye",
    "🤔 **Would You Rather:**\n\n🔴 Sirf ek cheez khao baki zindagi\n🔵 Roz naya khana but no repeat",
    "🤔 **Would You Rather:**\n\n🔴 Future mein jaana\n🔵 Past mein jaana",
    "🤔 **Would You Rather:**\n\n🔴 Unlimited paise but koi dost nahi\n🔵 Best dost but paise nahi",
    "🤔 **Would You Rather:**\n\n🔴 Hamesha garam jagah mein rehna\n🔵 Hamesha thand mein rehna",
    "🤔 **Would You Rather:**\n\n🔴 Har kisi ki soch padh sakna\n🔵 Kuch bhi sach kar sakna",
]

TRIVIA = [
    {"q": "🌍 India ki capital kya hai?", "a": "New Delhi"},
    {"q": "🔢 12 × 12 = ?", "a": "144"},
    {"q": "🎵 'Tum Hi Ho' kis movie ka gaana hai?", "a": "Aashiqui 2"},
    {"q": "⚽ FIFA World Cup 2022 kaunse desh ne jeeta?", "a": "Argentina"},
    {"q": "🪐 Solar system mein sabse bada planet?", "a": "Jupiter"},
    {"q": "📱 WhatsApp kab launch hua?", "a": "2009"},
    {"q": "🎬 Baahubali director kaun hain?", "a": "S.S. Rajamouli"},
    {"q": "🌊 Duniya ka sabse bada ocean?", "a": "Pacific Ocean"},
    {"q": "🇮🇳 India ka national fruit?", "a": "Aam (Mango)"},
    {"q": "🎸 Guitar mein standard taar kitne?", "a": "6"},
    {"q": "🧪 Paani ka chemical formula?", "a": "H₂O"},
    {"q": "📺 IPL ki shuruaat kab hui?", "a": "2008"},
    {"q": "🏔️ Duniya ki sabse unchi choti?", "a": "Mount Everest"},
    {"q": "💻 Python kab bani?", "a": "1991"},
    {"q": "🎭 Bollywood ka pehla film kaunsa tha?", "a": "Raja Harishchandra (1913)"},
]

_active_trivia: dict[int, str] = {}

# Marriage proposals pending confirmation
_pending_proposals: dict[int, tuple[int, int]] = {}  # chat_id -> (proposer_id, target_id)

DAILY_COOLDOWN = 86400  # 24 hours in seconds


# ══════════════════════════════════════════════════════
# ── CLASSIC GAME COMMANDS
# ══════════════════════════════════════════════════════

@Client.on_message(filters.command(["truth"]) & filters.group)
async def truth_cmd(client: Client, message: Message):
    q = random.choice(TRUTHS)
    user = message.from_user
    name = user.mention if user else "Player"
    await message.reply(
        f"🎯 **Truth for {name}:**\n\n_{q}_",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎲 New Truth", callback_data="game_truth"),
        ]]),
    )


@Client.on_message(filters.command(["dare"]) & filters.group)
async def dare_cmd(client: Client, message: Message):
    d = random.choice(DARES)
    user = message.from_user
    name = user.mention if user else "Player"
    await message.reply(
        f"🔥 **Dare for {name}:**\n\n_{d}_",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎲 New Dare", callback_data="game_dare"),
        ]]),
    )


@Client.on_message(filters.command(["wyr"]) & filters.group)
async def wyr_cmd(client: Client, message: Message):
    q = random.choice(WYR_QUESTIONS)
    await message.reply(
        q,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 New WYR", callback_data="game_wyr"),
        ]]),
    )


async def _trivia_timeout(chat_id: int, answer: str, reply_func):
    """BUG FIX: asyncio.sleep moved to background task so handler isn't blocked for 10s."""
    await asyncio.sleep(10)
    if chat_id in _active_trivia:
        del _active_trivia[chat_id]
        try:
            await reply_func(f"⏰ **Time's up!** Answer tha: **{answer}**")
        except Exception:
            pass


@Client.on_message(filters.command(["trivia", "quiz"]) & filters.group)
async def trivia_cmd(client: Client, message: Message):
    if message.chat.id in _active_trivia:
        return await message.reply("⚠️ Pehle wala trivia abhi chal raha hai! Jaldi answer do! 🧠")
    item = random.choice(TRIVIA)
    _active_trivia[message.chat.id] = item["a"].lower()
    sent = await message.reply(
        f"🧠 **Trivia Question:**\n\n{item['q']}\n\n"
        f"_10 seconds mein answer karein!_"
    )
    # BUG FIX: create_task so this doesn't block the handler for 10s
    asyncio.create_task(
        _trivia_timeout(message.chat.id, item["a"], sent.reply)
    )


@Client.on_message(filters.group & ~filters.command([]))
async def trivia_answer(client: Client, message: Message):
    if not message.text:
        return
    chat_id = message.chat.id
    if chat_id not in _active_trivia:
        return
    correct = _active_trivia[chat_id]
    if message.text.lower().strip() == correct:
        del _active_trivia[chat_id]
        reward = random.randint(50, 200)
        if message.from_user:
            await add_balance(message.from_user.id, reward)
        await message.reply(
            f"🎉 **Correct!** {message.from_user.mention if message.from_user else ''}\n"
            f"Answer: **{correct.title()}**\n"
            f"💵 Reward: `+${reward}` credited!"
        )


# Callback handlers for classic games
@Client.on_callback_query(filters.regex("^game_(truth|dare|wyr)$"))
async def game_callbacks(client, cq):
    await cq.answer()
    data = cq.data.split("_")[1]
    if data == "truth":
        q = random.choice(TRUTHS)
        await cq.message.reply(f"🎯 **Truth:**\n\n_{q}_",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎲 New Truth", callback_data="game_truth")]]))
    elif data == "dare":
        d = random.choice(DARES)
        await cq.message.reply(f"🔥 **Dare:**\n\n_{d}_",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎲 New Dare", callback_data="game_dare")]]))
    elif data == "wyr":
        q = random.choice(WYR_QUESTIONS)
        await cq.message.reply(q,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New WYR", callback_data="game_wyr")]]))


# ══════════════════════════════════════════════════════
# ── ECONOMY SYSTEM
# ══════════════════════════════════════════════════════

def _fmt(n: int) -> str:
    return f"${n:,}"


@Client.on_message(filters.command(["balance", "bal", "wallet"]))
async def balance_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    if not await has_started(user.id):
        return await message.reply(
            "❌ **Tumne bot start nahi kiya!**\n\n"
            "Bot ko DM mein `/start` karo pehle 💰"
        )
    bal = await get_balance(user.id)
    # Show partner info if married
    partner_id = await get_partner(user.id)
    partner_text = ""
    if partner_id:
        try:
            partner = await client.get_users(partner_id)
            partner_text = f"\n💍 **Partner:** {partner.mention}"
        except Exception:
            pass
    await message.reply(
        f"💰 **Wallet — {user.first_name}**\n\n"
        f"💵 Balance: **{_fmt(bal)}**"
        f"{partner_text}\n\n"
        f"_/kill /rob /protect /transfer /daily se khelein!_"
    )


@Client.on_message(filters.command(["daily"]) & filters.private)
async def daily_cmd_private(client: Client, message: Message):
    """Daily reward — works in both private and group."""
    await _process_daily(client, message)


@Client.on_message(filters.command(["daily"]) & filters.group)
async def daily_cmd_group(client: Client, message: Message):
    await _process_daily(client, message)


async def _process_daily(client: Client, message: Message):
    """Daily reward — must-join check sirf yahan hoga (bonus redeem pe)."""
    user = message.from_user
    if not user:
        return

    if not await has_started(user.id):
        return await message.reply(
            "❌ **Tumne bot start nahi kiya!**\n\n"
            "Bot ko DM mein `/start` karo pehle 💰"
        )

    # ── Must-join check: sirf bonus claim pe ─────────────────────
    if MUST_JOIN:
        try:
            member = await client.get_chat_member(MUST_JOIN, user.id)
            # Kick/ban status = not a valid member
            from pyrogram.enums import ChatMemberStatus
            if member.status in (ChatMemberStatus.BANNED, ChatMemberStatus.LEFT):
                raise ValueError("not a member")
        except Exception:
            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            return await message.reply(
                f"⚠️ **Daily Bonus Claim Karne Ke Liye Join Karo!**\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"Bonus aur game rewards lene ke liye channel member hona zaroori hai.\n\n"
                f"👉 **[Join Channel](https://t.me/{MUST_JOIN})**\n\n"
                f"_Join karo phir `/daily` dobara karo!_",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📢 Join Channel ✅", url=f"https://t.me/{MUST_JOIN}"),
                ]]),
                disable_web_page_preview=True,
            )

    now = int(time.time())
    last = await get_daily_last(user.id)
    elapsed = now - last
    cooldown = DAILY_COOLDOWN

    if elapsed < cooldown:
        remaining = cooldown - elapsed
        h, rem = divmod(remaining, 3600)
        m, s   = divmod(rem, 60)
        return await message.reply(
            f"⏳ **Daily reward already liya!**\n\n"
            f"Next reward in: `{h}h {m}m {s}s`\n\n"
            f"_Roz ek baar hi milta hai!_ 📅"
        )

    reward = random.randint(DAILY_REWARD_MIN, DAILY_REWARD_MAX)
    await add_balance(user.id, reward)
    await set_daily_last(user.id, now)
    bal = await get_balance(user.id)

    # Streak would require extra DB column — keep simple for now
    await message.reply(
        f"🎁 **Daily Reward Claimed!**\n\n"
        f"👤 {user.mention}\n"
        f"💵 Reward: **{_fmt(reward)}** credited!\n"
        f"💳 New Balance: **{_fmt(bal)}**\n\n"
        f"_Kal phir aana!_ 📅"
    )


@Client.on_message(filters.command(["kill"]) & filters.group)
async def kill_cmd(client: Client, message: Message):
    attacker = message.from_user
    if not attacker:
        return
    if not await has_started(attacker.id):
        return await message.reply("❌ Pehle bot ko DM mein `/start` karo!")

    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply("❌ Kisi user ko reply karo /kill karne ke liye!")

    victim = message.reply_to_message.from_user
    if victim.id == attacker.id:
        return await message.reply("😂 Khud ko kill? Seriously?")
    if victim.is_bot:
        return await message.reply("🤖 Bot ko kill nahi kar sakte!")

    if await is_protected(message.chat.id, victim.id):
        until = await get_protection_until(message.chat.id, victim.id)
        remaining = max(0, int((until - time.time()) / 60))
        return await message.reply(
            f"🛡️ **{victim.mention} protected hai!**\n"
            f"⏳ Aur {remaining} minute baad try karo."
        )

    victim_bal = await get_balance(victim.id)
    if victim_bal <= 0:
        return await message.reply(f"💸 {victim.mention} ke paas kuch nahi hai lootne ke liye!")

    steal_pct  = random.randint(10, 40)
    steal_amt  = max(10, int(victim_bal * steal_pct / 100))
    success    = random.random() < 0.65  # 65% success rate

    kills = [
        f"⚔️ {attacker.mention} ne {victim.mention} pe attack kiya!",
        f"🗡️ {attacker.mention} ne {victim.mention} ko challenge kiya!",
        f"💥 {attacker.mention} ne {victim.mention} par dhancha gira diya!",
        f"🔫 {attacker.mention} ne {victim.mention} ko target kiya!",
    ]
    action = random.choice(kills)

    if success:
        removed = await remove_balance(victim.id, steal_amt)
        if removed:
            await add_balance(attacker.id, steal_amt)
            await message.reply(
                f"{action}\n\n"
                f"✅ **Kill Successful!**\n"
                f"💰 Loota: **{_fmt(steal_amt)}** ({steal_pct}%)\n"
                f"🏆 {attacker.mention} ka naya balance: **{_fmt(await get_balance(attacker.id))}**"
            )
        else:
            await message.reply(
                f"{action}\n\n"
                f"😅 **Kill nearly succeeded but victim's balance changed!** Try again!"
            )
    else:
        penalty = random.randint(20, 100)
        await remove_balance(attacker.id, penalty)
        await message.reply(
            f"{action}\n\n"
            f"❌ **Kill Failed!** {victim.mention} ne counter attack kiya!\n"
            f"💸 Penalty: **{_fmt(penalty)}** kho diya\n"
            f"😅 Better luck next time!"
        )


@Client.on_message(filters.command(["rob"]) & filters.group)
async def rob_cmd(client: Client, message: Message):
    robber = message.from_user
    if not robber:
        return
    if not await has_started(robber.id):
        return await message.reply("❌ Pehle bot ko DM mein `/start` karo!")

    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply("❌ Kisi user ko reply karo rob karne ke liye!")

    victim = message.reply_to_message.from_user
    if victim.id == robber.id:
        return await message.reply("😂 Khud ko rob? Jaaoo bhai...")
    if victim.is_bot:
        return await message.reply("🤖 Bot ko rob nahi kar sakte!")

    if await is_protected(message.chat.id, victim.id):
        until = await get_protection_until(message.chat.id, victim.id)
        remaining = max(0, int((until - time.time()) / 60))
        return await message.reply(
            f"🛡️ **{victim.mention} protected hai!**\n"
            f"⏳ Aur {remaining} minute baad try karo."
        )

    victim_bal = await get_balance(victim.id)
    if victim_bal < 50:
        return await message.reply(f"💸 {victim.mention} bahut gareeb hai, kuch nahi hai!")

    steal_amt = random.randint(50, min(500, victim_bal))
    success   = random.random() < 0.55  # 55% success

    if success:
        removed = await remove_balance(victim.id, steal_amt)
        if removed:
            await add_balance(robber.id, steal_amt)
            rob_gifs = ["🕵️", "🦹", "💰", "🎭"]
            await message.reply(
                f"{random.choice(rob_gifs)} **Rob Successful!**\n\n"
                f"🎯 {robber.mention} ne {victim.mention} ko loot liya!\n"
                f"💵 Mila: **{_fmt(steal_amt)}**\n"
                f"🏦 Tera balance: **{_fmt(await get_balance(robber.id))}**"
            )
        else:
            await message.reply(f"😅 Rob fail — victim ka balance change ho gaya!")
    else:
        penalty = random.randint(30, 150)
        await remove_balance(robber.id, penalty)
        await message.reply(
            f"👮 **Rob Failed!** Pakde gaye!\n\n"
            f"🚔 {robber.mention} — police ne pakad liya!\n"
            f"💸 Fine: **{_fmt(penalty)}**\n"
            f"😭 Teri balance: **{_fmt(await get_balance(robber.id))}**"
        )


@Client.on_message(filters.command(["revive"]) & filters.group)
async def revive_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    if not await has_started(user.id):
        return await message.reply("❌ Pehle bot ko DM mein `/start` karo!")

    target_user = message.reply_to_message.from_user if message.reply_to_message else None
    if not target_user:
        target_user = user

    cost = 200
    bal  = await get_balance(user.id)
    if bal < cost:
        return await message.reply(
            f"❌ **Revive cost {_fmt(cost)}!**\n"
            f"💰 Tumhara balance: {_fmt(bal)}\n"
            f"_Pehle thoda kamao!_"
        )

    if not await remove_balance(user.id, cost):
        return await message.reply(f"❌ Insufficient balance! Cost: {_fmt(cost)}")

    heal = random.randint(100, 500)
    await add_balance(target_user.id, heal)
    await message.reply(
        f"💊 **Revive!**\n\n"
        f"🌟 {user.mention} ne {target_user.mention} ko revive kiya!\n"
        f"💚 Heal amount: **{_fmt(heal)}**\n"
        f"💸 Cost: {_fmt(cost)} | Tera balance: {_fmt(await get_balance(user.id))}"
    )


@Client.on_message(filters.command(["protect"]) & filters.group)
async def protect_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    if not await has_started(user.id):
        return await message.reply("❌ Pehle bot ko DM mein `/start` karo!")

    target_user = message.reply_to_message.from_user if message.reply_to_message else user

    cost = 300
    bal  = await get_balance(user.id)
    if bal < cost:
        return await message.reply(
            f"❌ **Protection cost {_fmt(cost)}!**\n"
            f"💰 Tumhara balance: {_fmt(bal)}"
        )

    if not await remove_balance(user.id, cost):
        return await message.reply(f"❌ Insufficient balance! Cost: {_fmt(cost)}")

    hours = 4
    await set_protection(message.chat.id, target_user.id, hours)
    await message.reply(
        f"🛡️ **Protection Active!**\n\n"
        f"👤 {target_user.mention} ab {hours} ghante tak protected hai!\n"
        f"🔒 Koi kill/rob nahi kar sakta\n"
        f"💸 Cost: {_fmt(cost)} | Tera balance: {_fmt(await get_balance(user.id))}"
    )


@Client.on_message(filters.command(["transfer", "give"]))
async def transfer_cmd(client: Client, message: Message):
    sender = message.from_user
    if not sender:
        return
    if not await has_started(sender.id):
        return await message.reply("❌ Pehle bot ko DM mein `/start` karo!")

    args = message.command[1:]
    if len(args) < 2:
        return await message.reply(
            "❌ **Usage:**\n"
            "`/transfer @username 500`\n"
            "`/transfer user_id 1000`\n\n"
            "_Tum apni 2nd ID pe bhi transfer kar sakte ho!_"
        )

    try:
        amount = int(args[-1])
        target_str = " ".join(args[:-1])
    except ValueError:
        return await message.reply("❌ Amount number mein dena: `/transfer @user 500`")

    if amount <= 0:
        return await message.reply("❌ Amount 0 se zyada hona chahiye!")

    try:
        receiver = await client.get_users(target_str)
    except Exception:
        return await message.reply("❌ User nahi mila!")

    if receiver.id == sender.id:
        return await message.reply("😂 Apne aap ko transfer? Woh toh already tumhara hai!")

    success = await transfer_balance(sender.id, receiver.id, amount)
    if not success:
        bal = await get_balance(sender.id)
        return await message.reply(
            f"❌ **Insufficient balance!**\n"
            f"💰 Tumhara balance: {_fmt(bal)}\n"
            f"💸 Transfer amount: {_fmt(amount)}"
        )

    await message.reply(
        f"✅ **Transfer Complete!**\n\n"
        f"📤 {sender.mention} → 📥 {receiver.mention}\n"
        f"💵 Amount: **{_fmt(amount)}**\n"
        f"🏦 Tumhara balance: {_fmt(await get_balance(sender.id))}"
    )


@Client.on_message(filters.command(["richlist", "toprich", "richboard"]) & filters.group)
async def richlist_cmd(client: Client, message: Message):
    top = await get_top_rich(10)
    if not top:
        return await message.reply("💰 Abhi koi economy data nahi hai!\n`/start` karke shuru karo.")

    lines = ["💎 **Rich List — Top 10**\n"]
    medals = ["🥇", "🥈", "🥉"] + ["💰"] * 7
    for i, (uid, bal) in enumerate(top):
        medal = medals[i]
        try:
            u = await client.get_users(uid)
            name = u.first_name[:18]
        except Exception:
            name = str(uid)
        lines.append(f"{medal} **{name}** — {_fmt(bal)}")

    await message.reply("\n".join(lines))


# ══════════════════════════════════════════════════════
# ── SOCIAL COMMANDS (were missing — added in v6.0)
# ══════════════════════════════════════════════════════

SLAP_TEXTS = [
    "👋 {a} ne {b} ko ek zabardast thappad maara! THAPAK! 😵",
    "🤚 {a} ka haath {b} ke gaal pe landing kar gaya! BAAAAP! 😂",
    "💥 {a} ne {b} ko ek flying slap maara — {b} chakkar khaa ke gir gaya! 🌀",
    "😤 {a} ne {b} ko slap kiya — thappad ki goonj poori group mein sunai di! CRACK! 💢",
    "🐟 {a} ne {b} ko ek badi si machhli se maara! Ye kya ho gaya?! 🤣",
    "👋 THAP! {a} ne {b} ko zero warning ke saath thappad maar diya! 😱",
]

FIGHT_TEXTS = [
    ("🥊 {a} ne {b} ko LEFT HOOK maara!", "💪 {a} ne {b} ko KO kar diya! Winner: **{a}**"),
    ("⚔️ {a} aur {b} ki fight shuru!", "🏆 Intense fight ke baad **{a}** jeet gaya! {b} bhag gaya!"),
    ("🥋 {a} ne {b} ko karate kick maari!", "🎖️ {a} ka upper cut {b} pe laga — {a} wins!"),
    ("💥 {a} aur {b} ka showdown!", "🌟 **{a}** ne strategy se {b} ko defeat kiya!"),
]


@Client.on_message(filters.command(["slap"]) & filters.group)
async def slap_cmd(client: Client, message: Message):
    """BUG FIX: Was missing — help menu had /slap."""
    slapper = message.from_user
    if not slapper:
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply("❌ Kisi user ko reply karo /slap karne ke liye! 👋")

    victim = message.reply_to_message.from_user
    if victim.id == slapper.id:
        return await message.reply("😂 Khud ko slap?! Therapy lo bhai!")
    if victim.is_bot:
        return await message.reply("🤖 Bot ko slap? Mujhe dard nahi hota! 😄")

    text = random.choice(SLAP_TEXTS).format(
        a=slapper.mention, b=victim.mention
    )
    await message.reply(
        f"{text}\n\n"
        f"😵 {victim.mention} — health: 💔💔💔"
    )


@Client.on_message(filters.command(["fight"]) & filters.group)
async def fight_cmd(client: Client, message: Message):
    """BUG FIX: Was missing — help menu had /fight."""
    challenger = message.from_user
    if not challenger:
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply("❌ Kisi user ko reply karo /fight karne ke liye! 🥊")

    opponent = message.reply_to_message.from_user
    if opponent.id == challenger.id:
        return await message.reply("😂 Khud se fight? Therapy lo bhai!")
    if opponent.is_bot:
        return await message.reply("🤖 Main toh bot hun — tum haaroge! 😈")

    # Random winner
    winner, loser = (challenger, opponent) if random.random() < 0.5 else (opponent, challenger)
    intro, result = random.choice(FIGHT_TEXTS)

    reward = random.randint(50, 300)
    await add_balance(winner.id, reward)

    await message.reply(
        f"{intro.format(a=challenger.mention, b=opponent.mention)}\n\n"
        f"_{result.format(a=winner.mention, b=loser.mention)}_\n\n"
        f"🏆 **{winner.first_name}** ko `+${reward}` prize milega!"
    )


@Client.on_message(filters.command(["marry"]) & filters.group)
async def marry_cmd(client: Client, message: Message):
    """BUG FIX: Was missing — help menu had /marry."""
    proposer = message.from_user
    if not proposer:
        return

    if not await has_started(proposer.id):
        return await message.reply("❌ Pehle bot ko DM mein `/start` karo!")

    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply("❌ Kisi user ko reply karo proposal bhejne ke liye! 💍")

    target = message.reply_to_message.from_user
    if target.id == proposer.id:
        return await message.reply("😂 Khud se shaadi?! Lonely ho gaye kya? 💔")
    if target.is_bot:
        return await message.reply("🤖 Bot se shaadi?! Main already busy hun 😅")

    # Check if already married
    my_partner = await get_partner(proposer.id)
    if my_partner:
        try:
            p = await client.get_users(my_partner)
            return await message.reply(
                f"💍 Tum already {p.mention} se shaadi-shuda ho!\n"
                f"Pehle `/divorce` karo!"
            )
        except Exception:
            pass

    their_partner = await get_partner(target.id)
    if their_partner:
        return await message.reply(f"💔 {target.mention} already kisi aur se shaadi-shuda hai!")

    # Store pending proposal
    _pending_proposals[message.chat.id] = (proposer.id, target.id)

    await message.reply(
        f"💍 **Marriage Proposal!**\n\n"
        f"💌 {proposer.mention} ne {target.mention} ko propose kiya!\n\n"
        f"_{target.mention}_ — `/accept` karo agree karne ke liye\n"
        f"ya `/reject` karo mana karne ke liye! ⏳",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Accept", callback_data=f"marry_accept_{proposer.id}_{target.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"marry_reject_{proposer.id}_{target.id}"),
        ]])
    )


@Client.on_callback_query(filters.regex(r"^marry_(accept|reject)_(\d+)_(\d+)$"))
async def marry_callback(client, cq):
    action     = cq.data.split("_")[1]
    proposer_id = int(cq.data.split("_")[2])
    target_id   = int(cq.data.split("_")[3])

    # Only the target can accept/reject
    if cq.from_user.id != target_id:
        return await cq.answer("Yeh proposal tumhare liye nahi hai! 😅", show_alert=True)

    await cq.answer()
    if action == "accept":
        await marry_users(proposer_id, target_id)
        try:
            proposer = await client.get_users(proposer_id)
            target   = await client.get_users(target_id)
            await cq.message.edit(
                f"💍 **Shaadi Ho Gayi!** 🎊\n\n"
                f"👫 {proposer.mention} ❤️ {target.mention}\n\n"
                f"_Congratulations! Dono ko mubarak ho!_ 🥳🎉"
            )
        except Exception:
            pass
    else:
        try:
            proposer = await client.get_users(proposer_id)
            target   = await client.get_users(target_id)
            await cq.message.edit(
                f"💔 **Proposal Reject Ho Gaya!**\n\n"
                f"{target.mention} ne {proposer.mention} ka proposal thukra diya!\n\n"
                f"_Dil toot gaya bhai..._ 😢"
            )
        except Exception:
            pass


@Client.on_message(filters.command(["divorce"]) & filters.group)
async def divorce_cmd(client: Client, message: Message):
    """BUG FIX: Was missing — help menu had /divorce."""
    user = message.from_user
    if not user:
        return

    partner_id = await get_partner(user.id)
    if not partner_id:
        return await message.reply(
            "❌ Tum abhi single ho!\n_Pehle kisi se `/marry` karo!_ 💍"
        )

    try:
        partner = await client.get_users(partner_id)
        partner_name = partner.mention
    except Exception:
        partner_name = str(partner_id)

    await divorce_user(user.id)
    await message.reply(
        f"💔 **Divorce Complete!**\n\n"
        f"😢 {user.mention} aur {partner_name} ab alag ho gaye hain.\n\n"
        f"_Zindagi aage badti hai..._ 🌸"
    )


# ══════════════════════════════════════════════════════
# ── OWNER ECONOMY CONTROLS
# ══════════════════════════════════════════════════════

@Client.on_message(filters.command(["givemoney", "addmoney"]) & filters.private)
async def givemoney_cmd(client: Client, message: Message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply("❌ Owner only!")
    args = message.command[1:]
    if len(args) < 2:
        return await message.reply("Usage: `/givemoney @user 5000`")
    try:
        amount = int(args[-1])
        target = await client.get_users(" ".join(args[:-1]))
    except Exception as e:
        return await message.reply(f"❌ Error: {e}")
    await add_balance(target.id, amount)
    await message.reply(f"✅ {_fmt(amount)} added to {target.mention}\nNew balance: {_fmt(await get_balance(target.id))}")


@Client.on_message(filters.command(["takemoney", "removemoney"]) & filters.private)
async def takemoney_cmd(client: Client, message: Message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply("❌ Owner only!")
    args = message.command[1:]
    if len(args) < 2:
        return await message.reply("Usage: `/takemoney @user 5000`")
    try:
        amount = int(args[-1])
        target = await client.get_users(" ".join(args[:-1]))
    except Exception as e:
        return await message.reply(f"❌ Error: {e}")
    await set_balance(target.id, max(0, await get_balance(target.id) - amount))
    await message.reply(f"✅ {_fmt(amount)} removed from {target.mention}\nNew balance: {_fmt(await get_balance(target.id))}")


@Client.on_message(filters.command(["setmoney"]) & filters.private)
async def setmoney_cmd(client: Client, message: Message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply("❌ Owner only!")
    args = message.command[1:]
    if len(args) < 2:
        return await message.reply("Usage: `/setmoney @user 50000`")
    try:
        amount = int(args[-1])
        target = await client.get_users(" ".join(args[:-1]))
    except Exception as e:
        return await message.reply(f"❌ Error: {e}")
    await set_balance(target.id, amount)
    await message.reply(f"✅ Balance set to {_fmt(amount)} for {target.mention}")
