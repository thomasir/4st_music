"""
notes.py — v5.0
Notes system: #notename trigger, /savenote, /get, /delnote, /notes
BUG FIX: Added /get <name> command (was missing — help menu mentioned it)
"""

import re
from pyrogram import Client, filters
from pyrogram.types import Message
from helpers.decorators import admin_only
from database import save_note, get_note, del_note, get_all_notes


@Client.on_message(filters.group & filters.text, group=3)
async def hashtag_note(client: Client, message: Message):
    text = message.text or ""
    match = re.match(r"#(\w+)", text.strip())
    if not match:
        return
    name = match.group(1).lower()
    content = await get_note(message.chat.id, name)
    if content:
        await message.reply(content)


@Client.on_message(filters.command(["savenote", "note"]) & filters.group)
@admin_only
async def savenote_cmd(client: Client, message: Message):
    args = message.command[1:]
    if len(args) < 2:
        await message.reply(
            "❌ **Format:** `/savenote <name> <content>`\n\n"
            "**Example:** `/savenote rules Follow group rules!`\n"
            "**Get it:** `/get rules` ya `#rules`"
        )
        return
    name    = args[0].lower()
    content = " ".join(args[1:])
    await save_note(message.chat.id, name, content)
    await message.reply(
        f"✅ **Note saved!**\n\n"
        f"📌 Name: `#{name}`\n\n"
        f"**Retrieve:** `/get {name}` ya `#{name}`"
    )


@Client.on_message(filters.command(["get"]) & filters.group)
async def get_note_cmd(client: Client, message: Message):
    """BUG FIX: This was missing — help menu had /get but no handler."""
    args = message.command[1:]
    if not args:
        return await message.reply(
            "❌ Note ka naam dein.\n\n"
            "**Example:** `/get rules`\n"
            "Ya shortcut: `#rules`"
        )
    name = args[0].lower()
    content = await get_note(message.chat.id, name)
    if not content:
        await message.reply(
            f"❌ **Note `#{name}` nahi mila!**\n\n"
            f"`/notes` se all notes dekho."
        )
        return
    await message.reply(content)


@Client.on_message(filters.command(["delnote", "deletenote"]) & filters.group)
@admin_only
async def delnote_cmd(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        return await message.reply("❌ Note name dein. Example: `/delnote rules`")
    name = args[0].lower()
    await del_note(message.chat.id, name)
    await message.reply(f"✅ **Note deleted:** `#{name}`")


@Client.on_message(filters.command(["notes", "listnotes"]) & filters.group)
async def notes_cmd(client: Client, message: Message):
    notes = await get_all_notes(message.chat.id)
    if not notes:
        await message.reply(
            "📝 **Koi notes nahi hain.**\n\n"
            "`/savenote <name> <content>` se banao."
        )
        return
    text = "📝 **Notes in this group:**\n\n"
    text += "\n".join(f"• `#{n}`" for n in notes)
    text += "\n\n_Note lene ke liye `/get <name>` ya `#notename` type karein._"
    await message.reply(text)
