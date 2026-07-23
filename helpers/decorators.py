"""
decorators.py — Permission checks for commands
"""

from functools import wraps
from pyrogram import Client
from pyrogram.types import Message
from config import OWNER_ID, SUDO_USERS


def owner_only(func):
    """Only bot owner can use this command."""
    @wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        if message.from_user and message.from_user.id == OWNER_ID:
            return await func(client, message, *args, **kwargs)
        await message.reply("❌ **Sirf bot owner use kar sakta hai.**")
    return wrapper


def sudo_only(func):
    """Sudo users + owner can use this command."""
    @wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        if message.from_user and message.from_user.id in SUDO_USERS:
            return await func(client, message, *args, **kwargs)
        await message.reply("❌ **Yeh command authorized users ke liye hai.**")
    return wrapper


def admin_only(func):
    """Group admins + owner can use this command."""
    @wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        if not message.from_user:
            return
        user_id = message.from_user.id
        if user_id in SUDO_USERS:
            return await func(client, message, *args, **kwargs)
        try:
            member = await client.get_chat_member(message.chat.id, user_id)
            from pyrogram.enums import ChatMemberStatus
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                return await func(client, message, *args, **kwargs)
        except Exception:
            pass
        await message.reply("❌ **Sirf group admins use kar sakte hain.**")
    return wrapper
