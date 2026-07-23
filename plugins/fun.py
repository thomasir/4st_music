"""
fun.py — v6.0 Ultimate
Jokes, Shayari, Motivational Quotes, Flip, Dice, 8ball, Quote
"""

import random
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

JOKES = [
    "Teacher: Roz school aao!\nStudent: Agar roz aaunga toh roz padhunga... aur padhunga toh main doctor ban jaunga... aur doctor ban ke bhi tujhe hi treat karunga 😂",
    "Dost: Yaar paisa udhaar de!\nMai: Bhai, paisa udhaar dena aur dost khona same hai. Toh dost rakhun ya paisa? 😅",
    "Zindagi ek ice cream hai... enjoy karo varna pighal jaayegi! Aur main already pighal chuka hun — exam ke results dekh ke 🍦",
    "Wifi password poochha toh uncle ne pura ghar dikhaya... password door pe tha. Pura tour waste gaya 😭",
    "Maa: Padh le beta!\nMain: Padh raha hun.\nMaa: Phone rakh!\nMain: Yeh educational app hai — YouTube pe chemistry dekh raha hun (actually music chal raha tha) 😂",
    "Meri driving dekh ke GPS ne bhi bola: 'Rasta bhool gaya — main bhi lost hun bhai!' 🗺️😂",
    "Bank balance dekha... toh lagaa screenshot lena hi mat — koi nahi manega 😭",
    "GF: Tu mujhse pyaar karta hai?\nMain: Haan bilkul!\nGF: Toh phone kyun nahi kiya?\nMain: Battery thi nahi.\nGF: Main charger bhej sakti thi!\nMain: ...WiFi bhi nahi tha 😅",
    "Exam mein ekdum aasan question tha... memory nahi thi aur dimag ne chutti le li thi 😭",
    "Main diet pe hoon... abhi tak kuch nahi khaya... subah se 9 baje tak. Phir biryani aa gayi 😅",
    "Boss ne pucha: 5 saal mein kahan dikhte ho?\nMain: Sir honestly? Aapki kursi pe 😂",
    "Mujhe neend nahi aati raat ko... kyunki main dopahar ko so leta hun 😴",
    "Gym join kiya 3 saal pehle... abhi tak pehuncha nahi — traffic bahut hai 😅",
    "Doctor: Sone se pehle phone band karo!\nMain: Haan haan bilkul... [3 baje tak reels dekhta raha] 📱😂",
]

SHAYARI = [
    "Mohabbat mein dard bhi hota hai,\nAur dard mein bhi pyaar chupa hota hai.\nDono milke zindagi banaate hain,\nYahi toh rishte ka asli maza hota hai.\n— Apex 🌹",
    "Zindagi ne jo diya thoda sa gam,\nUsne sikhaaya ki khushi kya hoti hai.\nAnsoo aaye, hum roye bhi,\nPar mushkil mein taaqat milti hai.\n— Apex 💫",
    "Waqt badlega, halaat badlenge,\nPar dil se dil ki baat kabhi na badlegi.\nJo rishta sach mein hota hai,\nWoh tufaanon mein bhi na toot-ti.\n— Apex ❤️",
    "Tujhe yaad karta hun toh neend nahi aati,\nSo jaata hun toh sapne mein tu aati hai.\nJaag ke bhi tera chehra dikhta hai,\nYe kya jaadu hai — kuch samajh na aata.\n— Apex 🌙",
    "Rishta ho toh dil se ho,\nWarna door se hi salam kafi hai.\nMehfil mein hazar log honge,\nPar sach wala dost kafi hai.\n— Apex 🙏",
    "Khwaab dekhna band mat karo,\nKyunki wahi toh zindagi ka rang hain.\nJo sapna sach hua — woh kuch kehta hai,\nJo tuta — woh bhi sabak laata hai.\n— Apex 🌈",
    "Har ek dard ki apni ek kahani hoti hai,\nAur har kahani mein ek sabak chhupi hoti hai.\nJo samjha — woh zindagi ko samjha,\nJo na samjha — woh phir wahi galti karta hai.\n— Apex 📖",
    "Jo mila use pyaar se sambhalo,\nJo nahi mila use dua mein maango.\nZindagi sab ko barabar deti hai,\nBas fark hai — kaise dekhte ho.\n— Apex ✨",
]

MOTIVATIONAL_QUOTES = [
    "💫 \"Sapne woh nahi jo aankh band karne se aate hain, sapne woh hain jo aankh khulne nahi dete.\"\n— **APJ Abdul Kalam**",
    "🔥 \"Kamyabi uss waqt milti hai jab aap poori mehnat karte hain — aur thakke nahi ruk-te.\"\n— **Dhirubhai Ambani**",
    "⭐ \"Haar mat maano jab tak jeet na jao — kyunki haar tab hoti hai jab tum koshish karna band kar dete ho.\"\n— **Unknown**",
    "🌟 \"Jo aaj mein jeeta hai, kal ki fikar usse nahi hoti — aur wahi sabse zyada kamyab hota hai.\"\n— **Anonymous**",
    "💪 \"Mushkilon se bhaago nahi, unhe apni taaqat banao — kyunki yahi mushkilein tumhare andar chhupi taaqat ko bahar laati hain.\"\n— **Unknown**",
    "⏳ \"Zindagi mein do cheezein kabhi waste nahi hoti — waqt aur mehnat. Dono ka sahi istemaal karo.\"\n— **Unknown**",
    "🏆 \"Success is not final, failure is not fatal: It is the courage to continue that counts.\"\n— **Winston Churchill**",
    "🎯 \"Believe you can and you're halfway there — baaki aadha kaam mehnat karta hai.\"\n— **Theodore Roosevelt**",
    "🚀 \"Ek chota sa kadam aaj uthao, ek badi safalta kal milegi — yahi zindagi ka formula hai.\"\n— **Unknown**",
    "💡 \"Andheron mein roshni dhoondho — jo roshni khud banaata hai, woh kabhi andhere mein nahi rehta.\"\n— **Unknown**",
    "🌅 \"Subah uthte hi socho — aaj main kya aisa karunga jo kal main nahi kar paya.\"\n— **Unknown**",
    "🦁 \"Sher ka cub bhi pehli baar toh girta hi hai — par phir uthta hai aur shehnshah banta hai.\"\n— **Unknown**",
    "🎵 \"Zindagi ek gaana hai — agar sahi sur mein gaao toh sab sunta hai.\"\n— **Apex Music Bot** 🎵",
    "🌊 \"Lehren kuch baat kar rahi hain tooti kishti se — 'Haar maan lene se kaam nahi chalta, uthna padega.'\"\n— **Unknown**",
    "📚 \"Kitabein woh dost hain jo kabhi dhoka nahi deti — padho, seekho, badlo.\"\n— **Unknown**",
]

EIGHTBALL = [
    "✅ **Bilkul haan!** Pakka 100%!",
    "✅ **Haan, bhai haan!** Bilkul sahi socha!",
    "✅ **Pakka!** Isme koi shak nahi!",
    "🤔 **Shayad...** Thoda aur sochna padega.",
    "🤔 **Abhi clear nahi hai.** Wait karo.",
    "🤔 **Baad mein poochho.** Stars aligned nahi hain.",
    "❌ **Nahi bilkul nahi.** Yeh hone wala nahi.",
    "❌ **Kabhi nahi.** Zero chance!",
    "❌ **Iska koi chance nahi.** Trust me.",
    "😂 **Seriously? Nahi!** Ye toh impossible hai!",
    "🔮 **Magic ball confused hai!** Dobara try karo.",
    "⭐ **Signs haan bol rahe hain!** Full green light!",
    "🎱 **Ask again later...** Abhi timing sahi nahi.",
    "💯 **Absolutely!** Without any doubt!",
    "🌟 **Without a doubt!** 100% guaranteed!",
    "🤷 **Pata nahi yaar...** Toss karo!",
]


# ── /joke ─────────────────────────────────────────────────────────

@Client.on_message(filters.command(["joke", "lol", "mazak"]))
async def joke_cmd(client: Client, message: Message):
    joke = random.choice(JOKES)
    await message.reply(
        f"😂 **Joke Time!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{joke}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("😂 Aur Joke!", callback_data="fun_joke"),
            InlineKeyboardButton("🌹 Shayari", callback_data="fun_shayari"),
        ]]),
    )


@Client.on_message(filters.command(["shayari", "poetry", "love"]))
async def shayari_cmd(client: Client, message: Message):
    s = random.choice(SHAYARI)
    await message.reply(
        f"🌹 **Shayari**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"_{s}_",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌹 Aur Shayari!", callback_data="fun_shayari"),
            InlineKeyboardButton("✨ Quote", callback_data="fun_quote"),
        ]]),
    )


@Client.on_message(filters.command(["quote", "q", "motivate", "inspire"]))
async def quote_cmd(client: Client, message: Message):
    q = random.choice(MOTIVATIONAL_QUOTES)
    await message.reply(
        f"✨ **Quote of the Day**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{q}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✨ Aur Quote!", callback_data="fun_quote"),
            InlineKeyboardButton("📤 Share", switch_inline_query=q[:100]),
        ]]),
    )


@Client.on_message(filters.command(["flip", "coin"]))
async def flip_cmd(client: Client, message: Message):
    result = random.choice(["🪙 **Heads!** (Sher ka muh)", "🪙 **Tails!** (Lakeer wali side)"])
    await message.reply(
        f"🪙 **Coin Flip!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{result}\n\n"
        f"_Naseeb ne decide kiya!_ 🎰",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Flip Again!", callback_data="fun_flip"),
            InlineKeyboardButton("🎲 Dice Roll!", callback_data="fun_dice"),
        ]]),
    )


@Client.on_message(filters.command(["dice", "roll"]))
async def dice_cmd(client: Client, message: Message):
    result = random.randint(1, 6)
    emoji  = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"][result - 1]
    comment = "_🎉 Jackpot! Lucky ho tum!_" if result == 6 else "_😢 Kitna bura! Ek aur try karo!_" if result == 1 else "_😏 Theek thak result!_"
    msg = (
        f"🎲 **Dice Roll!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{emoji} **{result}** aaya!\n\n"
        f"{comment}"
    )
    await message.reply(
        msg,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎲 Roll Again!", callback_data="fun_dice"),
            InlineKeyboardButton("🪙 Coin Flip", callback_data="fun_flip"),
        ]]),
    )


@Client.on_message(filters.command(["8ball", "eightball", "magic"]))
async def eightball_cmd(client: Client, message: Message):
    question = " ".join(message.command[1:]).strip()
    if not question:
        await message.reply(
            "🎱 **Magic 8-Ball**\n\n"
            "Koi sawaal poochho!\n\n"
            "Example: `/8ball Kya aaj meri kismat achhi hai?`"
        )
        return
    answer = random.choice(EIGHTBALL)
    await message.reply(
        f"🎱 **Magic 8-Ball**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"❓ _{question}_\n\n"
        f"**🔮 Jawab:** {answer}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎲 Dice Roll", callback_data="fun_dice"),
            InlineKeyboardButton("🪙 Coin Flip", callback_data="fun_flip"),
        ]]),
    )


# ── Callbacks ─────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^fun_joke$"))
async def cb_joke(client, cq):
    await cq.answer()
    joke = random.choice(JOKES)
    try:
        await cq.message.edit(
            f"😂 **Joke Time!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{joke}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("😂 Aur Joke!", callback_data="fun_joke"),
                InlineKeyboardButton("🌹 Shayari", callback_data="fun_shayari"),
            ]]),
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^fun_shayari$"))
async def cb_shayari(client, cq):
    await cq.answer()
    s = random.choice(SHAYARI)
    try:
        await cq.message.edit(
            f"🌹 **Shayari**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"_{s}_",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🌹 Aur Shayari!", callback_data="fun_shayari"),
                InlineKeyboardButton("✨ Quote", callback_data="fun_quote"),
            ]]),
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^fun_quote$"))
async def cb_quote(client, cq):
    await cq.answer()
    q = random.choice(MOTIVATIONAL_QUOTES)
    try:
        await cq.message.edit(
            f"✨ **Quote of the Day**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{q}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✨ Aur Quote!", callback_data="fun_quote"),
                InlineKeyboardButton("📤 Share", switch_inline_query=q[:100]),
            ]]),
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^fun_flip$"))
async def cb_flip(client, cq):
    await cq.answer()
    result = random.choice(["🪙 **Heads!** (Sher ka muh)", "🪙 **Tails!** (Lakeer wali side)"])
    try:
        await cq.message.edit(
            f"🪙 **Coin Flip!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n"
            f"_Naseeb ne decide kiya!_ 🎰",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Flip Again!", callback_data="fun_flip"),
                InlineKeyboardButton("🎲 Dice Roll", callback_data="fun_dice"),
            ]]),
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^fun_dice$"))
async def cb_dice(client, cq):
    await cq.answer()
    result = random.randint(1, 6)
    emoji  = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"][result - 1]
    comment = "🎉 Jackpot! Lucky ho tum!" if result == 6 else "😢 Itna bura! Ek aur try!" if result == 1 else "😏 Theek thak!"
    msg = (
        f"🎲 **Dice Roll!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{emoji} **{result}** aaya!\n\n"
        f"_{comment}_"
    )
    try:
        await cq.message.edit(
            msg,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Roll Again!", callback_data="fun_dice"),
            ]]),
        )
    except Exception:
        pass
