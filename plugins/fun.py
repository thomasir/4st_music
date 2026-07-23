"""
fun.py — v5.0
Jokes, Shayari, Quotes, Flip, Dice, 8ball
"""

import random
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

JOKES = [
    "Teacher: Roz school aao!\nStudent: Agar roz aaunga toh roz padhunga... 😂",
    "Dost: Yaar paisa udhaar de!\nMai: Bhai, paisa udhaar dena aur dost khona same hai 😅",
    "Zindagi ek ice cream hai... enjoy karo varna pighal jaayegi! 🍦",
    "Wifi password poochha toh uncle ne pura ghar dikhaya... password door pe tha 😭",
    "Maa: Padh le beta!\nMain: Padh raha hun.\nMaa: Phone rakh!\nMain: Yeh educational app hai 😂",
    "Meri driving dekh ke GPS ne bhi bola: 'Rasta bhool gaya!' 🗺️😂",
    "Bank balance dekha... toh lagaa mujhe hi dekhna tha, kyunki aur koi nahi dekhta 😭",
    "GF: Tu mujhse pyaar karta hai?\nMain: Haan bilkul!\nGF: Toh phone kyun nahi kiya?\nMain: Charge nahi tha 😅",
    "Teacher: Kya 2+2 bata sakte ho?\nStudent: Yes!\nTeacher: Toh batao!\nStudent: Yes main bata sakta hun 🙂",
    "Exam mein ekdum aasan question tha... memory nahi thi 😭",
    "Main diet pe hoon... abhi tak kuch nahi khaya... subah se 9 baje tak 😅",
    "Boss ne pucha: 5 saal mein kahan dikhte ho?\nMain: Retirement 😂",
]

SHAYARI = [
    "Mohabbat mein dard bhi hota hai,\nAur dard mein bhi pyaar chupa hota hai.\n— Apex Bot 🌹",
    "Zindagi ne jo diya thoda sa gam,\nUsne sikhaaya ki khushi kya hoti hai.\n— Apex Bot 💫",
    "Waqt badlega, halaat badlenge,\nPar dil se dil ki baat kabhi na badlegi.\n— Apex Bot ❤️",
    "Tujhe yaad karta hun toh neend nahi aati,\nSo jaata hun toh sapne mein tu aati hai.\n— Apex Bot 🌙",
    "Rishta ho toh dil se ho,\nWarna door se hi salam kafi hai.\n— Apex Bot 🙏",
    "Khwaab dekhna band mat karo,\nKyunki wahi toh zindagi ka rang hain.\n— Apex Bot 🌈",
    "Har ek dard ki apni ek kahani hoti hai,\nAur har kahani mein ek sabak chhupi hoti hai.\n— Apex Bot 📖",
    "Jo mila use pyaar se sambhalo,\nJo nahi mila use dua mein maango.\n— Apex Bot ✨",
]

QUOTES = [
    "\"Sapne woh nahi jo aankh band karne se aate hain, sapne woh hain jo aankh khulne nahi dete.\" — APJ Abdul Kalam",
    "\"Kamyabi uss waqt milti hai jab aap poori mehnat karte hain.\" — Dhirubhai Ambani",
    "\"Haar mat maano jab tak jeet na jao.\" — Unknown",
    "\"Jo aaj mein jeeta hai, kal ki fikar usse nahi hoti.\" — Anonymous",
    "\"Mushkilon se bhaago nahi, unhe apni taaqat banao.\" — Unknown",
    "\"Zindagi mein do cheezein kabhi waste nahi hoti — waqt aur mehnat.\" — Unknown",
    "\"Ek chota sa kadam aaj uthao, ek badi safalta kal milegi.\" — Unknown",
    "\"Sach bol, seedha chal. Zindagi teri hogi.\" — Unknown",
    "\"Success is not final, failure is not fatal.\" — Churchill",
    "\"Believe you can and you're halfway there.\" — Theodore Roosevelt",
]

EIGHTBALL = [
    "✅ Bilkul haan!", "✅ Pakka!", "✅ Haan, bhai haan!",
    "🤔 Shayad...", "🤔 Abhi clear nahi hai.", "🤔 Baad mein poochho.",
    "❌ Nahi bilkul nahi.", "❌ Kabhi nahi.", "❌ Iska koi chance nahi.",
    "😂 Seriously? Nahi!", "🔮 Magic ball confused hai!", "⭐ Signs haan bol rahe hain!",
    "🎱 Ask again later...", "💯 Absolutely!", "🌟 Without a doubt!",
]


@Client.on_message(filters.command(["joke", "lol"]))
async def joke_cmd(client: Client, message: Message):
    joke = random.choice(JOKES)
    await message.reply(
        f"😂 **Joke Time:**\n\n{joke}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("😂 Aur Joke!", callback_data="fun_joke"),
        ]]),
    )


@Client.on_message(filters.command(["shayari", "poetry"]))
async def shayari_cmd(client: Client, message: Message):
    s = random.choice(SHAYARI)
    await message.reply(
        f"🌹 **Shayari:**\n\n_{s}_",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌹 Aur Shayari", callback_data="fun_shayari"),
        ]]),
    )


@Client.on_message(filters.command(["quote", "motivate"]))
async def quote_cmd(client: Client, message: Message):
    q = random.choice(QUOTES)
    await message.reply(
        f"💫 **Quote:**\n\n{q}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💫 Another Quote", callback_data="fun_quote"),
        ]]),
    )


@Client.on_message(filters.command(["flip", "coinflip"]))
async def flip_cmd(client: Client, message: Message):
    result = random.choice(["🪙 **Heads!**", "🪙 **Tails!**"])
    await message.reply(result)


@Client.on_message(filters.command(["dice", "roll"]))
async def dice_cmd(client: Client, message: Message):
    n = random.randint(1, 6)
    dice_emojis = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
    await message.reply(f"🎲 **Dice Roll:** {dice_emojis[n]} ({n})")


@Client.on_message(filters.command(["8ball", "magic"]))
async def eightball_cmd(client: Client, message: Message):
    question = " ".join(message.command[1:])
    if not question:
        return await message.reply("❓ Koi sawal poochho: `/8ball Kya aaj main khush rahunga?`")
    answer = random.choice(EIGHTBALL)
    await message.reply(
        f"🔮 **Magic 8-Ball**\n\n"
        f"❓ _{question}_\n\n"
        f"**Answer:** {answer}"
    )


# ── Fun callbacks ──────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^fun_(joke|shayari|quote)$"))
async def fun_callbacks(client, cq):
    await cq.answer()
    data = cq.data.split("_")[1]
    if data == "joke":
        joke = random.choice(JOKES)
        await cq.message.reply(f"😂 **Joke:**\n\n{joke}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("😂 Aur!", callback_data="fun_joke")]]))
    elif data == "shayari":
        s = random.choice(SHAYARI)
        await cq.message.reply(f"🌹 **Shayari:**\n\n_{s}_",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌹 Aur!", callback_data="fun_shayari")]]))
    elif data == "quote":
        q = random.choice(QUOTES)
        await cq.message.reply(f"💫 **Quote:**\n\n{q}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💫 Aur!", callback_data="fun_quote")]]))
