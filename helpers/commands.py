"""Telegram command menu definitions and registration.

The handlers live in the plugin modules, but Telegram's slash-command menu is
managed centrally so it cannot silently drift away from the commands that are
actually available.
"""

from collections.abc import Iterable

from pyrogram import Client
from pyrogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)


def _commands(items: Iterable[tuple[str, str]]) -> list[BotCommand]:
    return [BotCommand(command, description) for command, description in items]


# Commands available to users in private chats. Group-only features are kept
# out of this scope because Telegram displays the scope-specific list.
PRIVATE_COMMANDS = _commands(
    (
        ("start", "Start the bot and claim your welcome bonus"),
        ("help", "Open the complete command guide"),
        ("ping", "Check bot response time and uptime"),
        ("about", "See bot information and features"),
        ("id", "Show your Telegram user ID"),
        ("info", "Show a user's profile information"),
        ("whois", "Show a user's profile information"),
        ("balance", "Check your wallet balance"),
        ("daily", "Claim your daily wallet reward"),
        ("transfer", "Transfer money to another user"),
        ("broadcast", "Broadcast a message to all bot chats"),
        ("gban", "Globally ban a user"),
        ("ungban", "Remove a global ban"),
        ("gbans", "Show the global ban count"),
        ("givemoney", "Give money to a user (owner only)"),
        ("takemoney", "Take money from a user (owner only)"),
        ("setmoney", "Set a user's balance (owner only)"),
        ("genname", "Generate a fancy name"),
        ("gendp", "Generate a profile picture"),
        ("joke", "Get a random joke"),
        ("shayari", "Get a shayari"),
        ("quote", "Get a motivational quote"),
        ("flip", "Flip a coin"),
        ("dice", "Roll a dice"),
        ("8ball", "Ask the magic 8-ball"),
    )
)


GROUP_COMMANDS = _commands(
    (
        ("start", "Show group bot information"),
        ("help", "Open the complete command guide"),
        ("ping", "Check bot response time and uptime"),
        ("about", "See bot information and features"),
        ("id", "Show a user's or chat's ID"),
        ("info", "Show a user's profile information"),
        ("whois", "Show a user's profile information"),
        ("play", "Play audio from YouTube"),
        ("vplay", "Play video from YouTube"),
        ("playforce", "Play immediately and clear the current queue"),
        ("pause", "Pause the current stream"),
        ("resume", "Resume the current stream"),
        ("skip", "Skip to the next song"),
        ("stop", "Stop playback and clear the queue"),
        ("vol", "Set playback volume"),
        ("queue", "Show the music queue"),
        ("np", "Show the currently playing song"),
        ("shuffle", "Shuffle the music queue"),
        ("loop", "Toggle song loop"),
        ("autoplay", "Toggle history-based autoplay"),
        ("balance", "Check your wallet balance"),
        ("daily", "Claim your daily wallet reward"),
        ("transfer", "Transfer money to another user"),
        ("richlist", "Show the richest group users"),
        ("truth", "Get a truth question"),
        ("dare", "Get a dare challenge"),
        ("wyr", "Play would-you-rather"),
        ("trivia", "Get a timed trivia question"),
        ("kill", "Attack another user"),
        ("rob", "Try to rob another user"),
        ("revive", "Revive another user"),
        ("protect", "Buy temporary protection"),
        ("slap", "Slap another user"),
        ("fight", "Fight another user"),
        ("marry", "Propose marriage"),
        ("divorce", "End your current marriage"),
        ("couples", "Show group couples"),
        ("gban", "Globally ban a user"),
        ("ungban", "Remove a global ban"),
        ("gbans", "Show the global ban count"),
        ("antiporn", "Toggle NSFW sticker protection"),
        ("addfilter", "Add a word filter"),
        ("rmfilter", "Remove a word filter"),
        ("filters", "List word filters"),
        ("savenote", "Save a group note"),
        ("get", "Read a saved group note"),
        ("delnote", "Delete a saved group note"),
        ("notes", "List saved group notes"),
        ("setwelcome", "Set the welcome message"),
        ("setgoodbye", "Set the goodbye message"),
        ("welcome", "Toggle or view welcome settings"),
        ("goodbye", "Toggle or view goodbye settings"),
        ("resetwelcome", "Reset the welcome message"),
        ("resetgoodbye", "Reset the goodbye message"),
        ("stats", "Show group activity statistics"),
        ("rankings", "Show the most active users"),
        ("topgroups", "Show the most active groups"),
        ("chatbot", "Toggle the group chatbot"),
        ("tagall", "Mention group members"),
        ("ontag", "Toggle automatic tag replies"),
        ("reaction", "Toggle automatic reactions"),
        ("joke", "Get a random joke"),
        ("shayari", "Get a shayari"),
        ("quote", "Get a motivational quote"),
        ("flip", "Flip a coin"),
        ("dice", "Roll a dice"),
        ("8ball", "Ask the magic 8-ball"),
    )
)


# Admins get a more useful list than regular group members. Telegram applies
# this scope only to administrators, while GROUP_COMMANDS remains the fallback
# for everyone else.
_ADMIN_ONLY_COMMANDS = (
    ("ban", "Ban a user from the group"),
    ("unban", "Unban a user"),
    ("kick", "Remove a user from the group"),
    ("mute", "Mute a user"),
    ("unmute", "Unmute a user"),
    ("warn", "Warn a user"),
    ("warns", "View a user's warnings"),
    ("clearwarn", "Clear a user's warnings"),
    ("promote", "Promote a user to admin"),
    ("fpromote", "Promote a user with full rights"),
    ("demote", "Remove admin rights"),
    ("pin", "Pin a replied message"),
    ("unpin", "Unpin the latest message"),
    ("purge", "Delete messages from a reply"),
    ("admins", "List group administrators"),
    ("report", "Report a user to group admins"),
    ("banall", "Ban all listed target users"),
    ("unbanall", "Unban all listed target users"),
    ("antiporn", "Toggle NSFW sticker protection"),
    ("addfilter", "Add a word filter"),
    ("rmfilter", "Remove a word filter"),
    ("filters", "List word filters"),
    ("setwelcome", "Set the welcome message"),
    ("setgoodbye", "Set the goodbye message"),
    ("welcome", "Toggle or view welcome settings"),
    ("goodbye", "Toggle or view goodbye settings"),
    ("resetwelcome", "Reset the welcome message"),
    ("resetgoodbye", "Reset the goodbye message"),
    ("chatbot", "Toggle the group chatbot"),
    ("tagall", "Mention group members"),
    ("ontag", "Toggle automatic tag replies"),
    ("reaction", "Toggle automatic reactions"),
)

# Telegram uses the most specific matching scope. Include the regular group
# menu here as well, otherwise administrators would lose music and fun
# commands when the administrator-specific menu is applied.
_ADMIN_COMMANDS_BY_NAME = {
    command.command: command.description for command in GROUP_COMMANDS
}
for _command, _description in _ADMIN_ONLY_COMMANDS:
    _ADMIN_COMMANDS_BY_NAME.setdefault(_command, _description)
ADMIN_COMMANDS = _commands(_ADMIN_COMMANDS_BY_NAME.items())

# Useful for static checks and documentation tooling. Aliases remain accepted
# by the handlers but are intentionally not all shown in Telegram's menu.
COMMAND_ALIASES = {
    "play": ("p", "fplay", "pf"),
    "vplay": ("vp",),
    "playforce": ("pf", "fplay"),
    "skip": ("next", "s"),
    "stop": ("end",),
    "vol": ("volume", "v"),
    "queue": ("q",),
    "np": ("now", "song"),
    "balance": ("bal", "wallet"),
    "transfer": ("give",),
    "richlist": ("toprich", "richboard"),
    "trivia": ("quiz",),
    "couples": ("couple", "ship"),
    "gban": ("gbanlist",),
    "ungban": (),
    "addfilter": ("filter",),
    "rmfilter": ("unfilter", "delfilter"),
    "filters": ("listfilters",),
    "savenote": ("note",),
    "delnote": ("deletenote",),
    "notes": ("listnotes",),
    "rankings": ("topusers", "top", "leaderboard"),
    "admins": ("adminlist", "staff"),
    "tagall": ("tg", "mentionall"),
    "genname": ("fname", "fancyname"),
    "gendp": ("dp", "genpic"),
    "broadcast": ("bc",),
    "joke": ("lol", "mazak"),
    "shayari": ("poetry", "love"),
    "quote": ("q", "motivate", "inspire"),
    "flip": ("coin",),
    "dice": ("roll",),
    "8ball": ("eightball", "magic"),
    "givemoney": ("addmoney",),
    "takemoney": ("removemoney",),
}


async def register_bot_commands(client: Client) -> None:
    """Publish all slash menus after the bot client has started.

    Registration is deliberately best-effort: a Telegram API issue should be
    logged by the caller without taking down music playback and other handlers.
    """

    await client.set_bot_commands(
        PRIVATE_COMMANDS,
        scope=BotCommandScopeAllPrivateChats(),
    )
    await client.set_bot_commands(
        GROUP_COMMANDS,
        scope=BotCommandScopeAllGroupChats(),
    )
    await client.set_bot_commands(
        ADMIN_COMMANDS,
        scope=BotCommandScopeAllChatAdministrators(),
    )