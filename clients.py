"""
clients.py — Apex Bot v6.0
✅ in_memory=True for bot: no .session file written to Heroku's ephemeral FS
   (BOT_TOKEN logins don't need a persistent session — auth re-runs on every
    restart anyway; storing a stale file just confuses Pyrogram on DC changes)
✅ Assistant still uses SESSION_STRING (userbot needs persistent auth key)
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pyrogram import Client
from pytgcalls import PyTgCalls
from config import API_ID, API_HASH, BOT_TOKEN, SESSION_STRING

# Bot client — in_memory so no .session file on ephemeral Heroku filesystem.
# BOT_TOKEN always produces a fresh auth; storing the file just causes
# "wrong DC" errors after dyno migration and contributes to FloodWait loops.
bot = Client(
    "ApexBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
    plugins=dict(root="plugins"),
)

# Assistant/userbot client — session string from env (DATABASE_URL preferred
# for production; SESSION_STRING env var is the Heroku-safe alternative).
assistant = Client(
    "ApexAssistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    in_memory=True,
)

call_py = PyTgCalls(assistant)
