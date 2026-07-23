"""
chatbot.py — v5.1
/chatbot on | /chatbot off
Learns from user conversations and replies intelligently.
Built-in responses + learns from chat.
Reply to bot message = teach it (trigger → response)
BUG FIX: Removed duplicate `import random` inside functions (was already imported at top)
"""

import random
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from helpers.decorators import admin_only
from database import (
    get_chatbot_enabled, set_chatbot,
    get_chatbot_response, learn_response
)

log = logging.getLogger("ApexBot.chatbot")

# ── Built-in responses (seeded) ───────────────────────────────────
BUILTIN = {
    "hello": ["Hello! 👋 Kya haal hai?", "Hi! 😊", "Namaste! 🙏 Kaisa ho?"],
    "hi": ["Hiiii! 😄", "Hey! Kya haal chaal?", "Hi bhai! 👋"],
    "kya haal": ["Sab badhiya! Tum batao 😊", "Mast hun yaar! Tu bata.", "Ekdum fit! 💪"],
    "how are you": ["I'm great! How about you? 😊", "Doing awesome! 🔥"],
    "tera naam": ["Mera naam Apex hai! 🎵 Tumhara bot, tumhara dost!", "Main hoon Apex Bot! 🤖"],
    "bot": ["Haan main bot hun! Par dil se original hun 😄", "Bot hoon, par intelligent! 🤖"],
    "kaise ho": ["Main bilkul theek hun! Tum batao 😊", "Mast hun! Apex Ban raha hai! 💪"],
    "good morning": ["Good Morning! ☀️ Aaj ka din aacha ho!", "Subah ki shubhkamnaen! 🌅"],
    "good night": ["Good Night! 🌙 Meethe sapne aayein!", "Shubh Ratri! 😴"],
    "thanks": ["Welcome! 😊", "Koi baat nahi! 💫", "Always here to help! 🤖"],
    "love you": ["Aww! 🥰 Main bhi tumse pyaar karta hun (ek bot ki taraf se)!", "❤️ Bot luv!"],
    "bored": ["Chalo khelte hain! /truth /dare /wyr try karo! 🎮", "Music suno! /play try karo 🎵"],
    "music": ["Haan! /play se koi bhi song suno! 🎵🔥", "/play <song name> likho — instant!"],
    "play": ["Haan! /play <song name> likho group mein! 🎵", "Music ke liye /play use karo!"],
    "help": ["Main yahan hun! /help likho sab commands dekhne ke liye 📖", "Bilkul! /help try karo!"],
    "bye": ["Bye bye! 👋 Jaldi wapas aana!", "Take care! 💫"],
    "ok": ["👍", "Achha!", "Theek hai! 😊"],
    "haha": ["😂😂", "Haha mast joke tha!", "Lol 😄"],
    "lol": ["😂🤣", "Hahaha!", "Too funny! 😄"],
    "sad": ["Aw, mat rona! 🥺 Main yahan hun. Kuch sunao.", "Sab theek ho jayega! 💙"],
    "happy": ["Yayy! 🎉 Khushi mein main bhi khush! 😄", "Great vibes! 🌟"],
    "winner": ["🏆 You're a winner!", "Congrats! 🎉🏆"],
    "daily": ["Apna daily reward lena na bhoolo! /daily try karo! 💰", "/daily se roz paise milte hain! 🤑"],
    "paise": ["Economy ka maza lo! /balance dekho aur /kill /rob try karo! 💵", "/daily karo paise kamao! 💰"],
}


def _find_builtin(text: str) -> str | None:
    text_lower = text.lower().strip()
    for key, responses in BUILTIN.items():
        if key in text_lower:
            return random.choice(responses)
    return None


@Client.on_message(filters.command(["chatbot"]) & filters.group)
@admin_only
async def chatbot_toggle(client: Client, message: Message):
    args = message.command[1:]
    if not args or args[0].lower() not in ("on", "off"):
        status = await get_chatbot_enabled(message.chat.id)
        await message.reply(
            f"🤖 **ChatBot Status:** {'✅ ON' if status else '❌ OFF'}\n\n"
            f"**Features:**\n"
            f"• Bot random messages ka reply karega\n"
            f"• Bot ke reply pe koi message karo → bot seekh jayega\n"
            f"• Built-in Hinglish responses + learned responses\n\n"
            f"`/chatbot on` — enable\n"
            f"`/chatbot off` — disable"
        )
        return
    enabled = args[0].lower() == "on"
    await set_chatbot(message.chat.id, enabled)
    await message.reply(
        f"🤖 **ChatBot:** {'✅ ON — Main ab baat karunga! 😄' if enabled else '❌ OFF — Chup ho gaya! 🤐'}"
    )


@Client.on_message(filters.group & ~filters.command([]) & ~filters.bot, group=9)
async def chatbot_handler(client: Client, message: Message):
    if not message.text or not message.from_user:
        return
    try:
        enabled = await get_chatbot_enabled(message.chat.id)
        if not enabled:
            return

        # Learn mode: if user replies to bot's message → teach it
        if (message.reply_to_message and
                message.reply_to_message.from_user and
                message.reply_to_message.from_user.is_bot):
            trigger = message.reply_to_message.text
            if trigger and message.text:
                await learn_response(trigger[:200], message.text[:500])
                # Silently learn — don't reply here

        # Check if bot is mentioned or replied to
        bot_me = await client.get_me()
        is_mentioned = (
            message.reply_to_message and
            message.reply_to_message.from_user and
            message.reply_to_message.from_user.id == bot_me.id
        )
        mention_text = f"@{bot_me.username}".lower() if bot_me.username else ""
        text_has_mention = mention_text and mention_text in message.text.lower()

        if not is_mentioned and not text_has_mention:
            # Random 1 in 10 chance to reply in chatbot-enabled groups
            if random.random() > 0.1:   # BUG FIX: removed duplicate `import random`
                return

        text = message.text.strip()
        if mention_text:
            text = text.replace(mention_text, "").strip()

        # Try learned responses first
        response = await get_chatbot_response(text)

        # Try built-in
        if not response:
            response = _find_builtin(text)

        # Fallback
        if not response:
            fallbacks = [
                "Hmm... 🤔 Samjha nahi, thoda aur batao!",
                "Interesting! 😮 Aur details do!",
                "Achha! Main seekh raha hun 🤖",
                "Bhai ek dum sahi point! 👍",
                "Mujhe aur sikhao! 📚",
                "Waah! 👏 Zabardast baat boli!",
                "Haan haan, bilkul! 😄",
            ]
            response = random.choice(fallbacks)  # BUG FIX: removed duplicate `import random`

        await message.reply(response)
    except Exception as e:
        log.debug(f"chatbot_handler error: {e}")
