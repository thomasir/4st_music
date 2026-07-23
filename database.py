"""
database.py — Apex Bot v5.0 Ultimate
Tables: gbans, warns, notes, word_filters, welcome_settings, stats,
        chats, users, name_history, economy, antiporn_settings,
        chatbot_data, reaction_settings, admin_ban_tracker, spam_rank_ban,
        game_protection, user_connections
"""

import aiosqlite
import logging
from config import DB_PATH

log = logging.getLogger("ApexBot.db")
DB  = DB_PATH


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS gbans (
            user_id   INTEGER PRIMARY KEY,
            reason    TEXT,
            banned_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS warns (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER,
            chat_id   INTEGER,
            reason    TEXT,
            warned_by INTEGER,
            UNIQUE(user_id, chat_id, reason)
        );
        CREATE TABLE IF NOT EXISTS notes (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id  INTEGER,
            name     TEXT,
            content  TEXT,
            UNIQUE(chat_id, name)
        );
        CREATE TABLE IF NOT EXISTS word_filters (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            word    TEXT,
            UNIQUE(chat_id, word)
        );
        CREATE TABLE IF NOT EXISTS welcome_settings (
            chat_id          INTEGER PRIMARY KEY,
            welcome_text     TEXT DEFAULT '👋 Welcome {mention} to {chat}! 🎉',
            goodbye_text     TEXT DEFAULT '👋 {mention} ne {chat} chhod diya.',
            welcome_enabled  INTEGER DEFAULT 1,
            goodbye_enabled  INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS stats (
            chat_id        INTEGER,
            user_id        INTEGER,
            msg_count      INTEGER DEFAULT 0,
            media_count    INTEGER DEFAULT 0,
            spam_banned    INTEGER DEFAULT 0,
            spam_ban_until INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title   TEXT,
            chat_type TEXT DEFAULT 'group'
        );
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            name          TEXT,
            first_seen    INTEGER DEFAULT 0,
            joined_chats  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS name_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            name       TEXT,
            changed_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS economy (
            user_id     INTEGER PRIMARY KEY,
            balance     INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            started     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS antiporn_settings (
            chat_id  INTEGER PRIMARY KEY,
            enabled  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS chatbot_data (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger  TEXT UNIQUE,
            response TEXT
        );
        CREATE TABLE IF NOT EXISTS chatbot_settings (
            chat_id  INTEGER PRIMARY KEY,
            enabled  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS reaction_settings (
            chat_id  INTEGER PRIMARY KEY,
            enabled  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS admin_ban_tracker (
            chat_id     INTEGER,
            admin_id    INTEGER,
            ban_count   INTEGER DEFAULT 0,
            window_start INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, admin_id)
        );
        CREATE TABLE IF NOT EXISTS game_protection (
            chat_id  INTEGER,
            user_id  INTEGER,
            until    INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS user_connections (
            requester_id  INTEGER,
            target_id     INTEGER,
            chat_id       INTEGER,
            created_at    INTEGER DEFAULT (strftime('%s','now')),
            PRIMARY KEY(requester_id, target_id)
        );
        """)
        await db.commit()
    log.info("✅ Database initialised")


# ══ GBAN ══════════════════════════════════════════════════════════

async def gban_user(user_id: int, reason: str, banned_by: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO gbans (user_id, reason, banned_by) VALUES (?,?,?)",
            (user_id, reason, banned_by)
        )
        await db.commit()


async def ungban_user(user_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM gbans WHERE user_id=?", (user_id,))
        await db.commit()


async def is_gbanned(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT reason, banned_by FROM gbans WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return {"reason": row[0], "banned_by": row[1]} if row else None


async def get_gban_count() -> int:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT COUNT(*) FROM gbans") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


# ══ WARNS ═════════════════════════════════════════════════════════

async def warn_user(user_id: int, chat_id: int, reason: str, warned_by: int) -> int:
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO warns (user_id, chat_id, reason, warned_by) VALUES (?,?,?,?)",
            (user_id, chat_id, reason, warned_by)
        )
        await db.commit()
        async with db.execute(
            "SELECT COUNT(*) FROM warns WHERE user_id=? AND chat_id=?", (user_id, chat_id)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_warns(user_id: int, chat_id: int) -> list:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT reason FROM warns WHERE user_id=? AND chat_id=?", (user_id, chat_id)
        ) as cur:
            return [r[0] for r in await cur.fetchall()]


async def clear_warns(user_id: int, chat_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "DELETE FROM warns WHERE user_id=? AND chat_id=?", (user_id, chat_id)
        )
        await db.commit()


# ══ NOTES ═════════════════════════════════════════════════════════

async def save_note(chat_id: int, name: str, content: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO notes (chat_id, name, content) VALUES (?,?,?)",
            (chat_id, name.lower(), content)
        )
        await db.commit()


async def get_note(chat_id: int, name: str) -> str | None:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT content FROM notes WHERE chat_id=? AND name=?", (chat_id, name.lower())
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def del_note(chat_id: int, name: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "DELETE FROM notes WHERE chat_id=? AND name=?", (chat_id, name.lower())
        )
        await db.commit()


async def get_all_notes(chat_id: int) -> list:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT name FROM notes WHERE chat_id=? ORDER BY name", (chat_id,)
        ) as cur:
            return [r[0] for r in await cur.fetchall()]


# ══ WORD FILTERS ══════════════════════════════════════════════════

async def add_filter(chat_id: int, word: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO word_filters (chat_id, word) VALUES (?,?)",
            (chat_id, word.lower())
        )
        await db.commit()


async def remove_filter(chat_id: int, word: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "DELETE FROM word_filters WHERE chat_id=? AND word=?", (chat_id, word.lower())
        )
        await db.commit()


async def get_filters(chat_id: int) -> list:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT word FROM word_filters WHERE chat_id=?", (chat_id,)
        ) as cur:
            return [r[0] for r in await cur.fetchall()]


# ══ WELCOME ═══════════════════════════════════════════════════════

async def get_welcome(chat_id: int) -> dict:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT welcome_text, goodbye_text, welcome_enabled, goodbye_enabled "
            "FROM welcome_settings WHERE chat_id=?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "welcome_text":    row[0],
                    "goodbye_text":    row[1],
                    "welcome_enabled": bool(row[2]),
                    "goodbye_enabled": bool(row[3]),
                }
            return {
                "welcome_text":    "👋 Welcome {mention} to **{chat}**! 🎉\n\nHope you enjoy your stay here! 💫",
                "goodbye_text":    "👋 {mention} ne {chat} chhod diya.",
                "welcome_enabled": True,
                "goodbye_enabled": True,
            }


async def set_welcome(chat_id: int, field: str, value):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO welcome_settings (chat_id) VALUES (?)", (chat_id,)
        )
        await db.execute(
            f"UPDATE welcome_settings SET {field}=? WHERE chat_id=?", (value, chat_id)
        )
        await db.commit()


# ══ STATS ═════════════════════════════════════════════════════════

async def increment_stat(chat_id: int, user_id: int, is_media: bool = False):
    import time
    now = int(time.time())
    async with aiosqlite.connect(DB) as db:
        # Check spam_ban_until
        async with db.execute(
            "SELECT spam_ban_until FROM stats WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            if row and row[0] and row[0] > now:
                return  # Still spam-rank-banned

        media_inc = 1 if is_media else 0
        await db.execute(
            "INSERT INTO stats (chat_id, user_id, msg_count, media_count) VALUES (?,?,1,?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET "
            "msg_count=msg_count+1, media_count=media_count+?",
            (chat_id, user_id, media_inc, media_inc)
        )
        await db.commit()


async def get_top_users(chat_id: int, limit: int = 10) -> list:
    import time
    now = int(time.time())
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT user_id, msg_count+media_count FROM stats WHERE chat_id=? "
            "AND (spam_ban_until IS NULL OR spam_ban_until <= ?) "
            "ORDER BY msg_count+media_count DESC LIMIT ?",
            (chat_id, now, limit)
        ) as cur:
            return await cur.fetchall()


async def get_chat_total(chat_id: int) -> int:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT SUM(msg_count+media_count) FROM stats WHERE chat_id=?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] or 0


async def spam_rank_ban(chat_id: int, user_id: int, minutes: int = 5):
    import time
    until = int(time.time()) + (minutes * 60)
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO stats (chat_id, user_id, spam_ban_until) VALUES (?,?,?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET spam_ban_until=?",
            (chat_id, user_id, until, until)
        )
        await db.commit()


async def get_all_group_stats() -> list:
    """Returns (chat_id, total_msgs) for all groups sorted by activity."""
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT chat_id, SUM(msg_count+media_count) as total FROM stats "
            "GROUP BY chat_id ORDER BY total DESC LIMIT 10"
        ) as cur:
            return await cur.fetchall()


# ══ CHATS / USERS ════════════════════════════════════════════════

async def register_chat(chat_id: int, title: str, chat_type: str = "group"):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO chats (chat_id, title, chat_type) VALUES (?,?,?)",
            (chat_id, title, chat_type)
        )
        await db.commit()


async def get_all_chats() -> list:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT chat_id FROM chats") as cur:
            return [r[0] for r in await cur.fetchall()]


async def get_total_chats() -> int:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT COUNT(*) FROM chats") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_total_users() -> int:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def register_user(user_id: int, username: str, name: str):
    import time
    async with aiosqlite.connect(DB) as db:
        # Get existing name
        async with db.execute("SELECT name FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        existing_name = row[0] if row else None

        now = int(time.time())
        await db.execute(
            "INSERT INTO users (user_id, username, name, first_seen) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=?, name=?",
            (user_id, username, name, now, username, name)
        )

        # Track name history if changed
        if name and existing_name and existing_name != name:
            await db.execute(
                "INSERT INTO name_history (user_id, name) VALUES (?,?)",
                (user_id, name)
            )
        elif name and not existing_name:
            # First time registration
            await db.execute(
                "INSERT INTO name_history (user_id, name) VALUES (?,?)",
                (user_id, name)
            )
        await db.commit()


async def get_name_history(user_id: int) -> list:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT name, changed_at FROM name_history WHERE user_id=? ORDER BY changed_at DESC LIMIT 20",
            (user_id,)
        ) as cur:
            return await cur.fetchall()


async def get_common_chats_count(user_id: int) -> int:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT COUNT(DISTINCT chat_id) FROM stats WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_user_info(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT username, name, first_seen FROM users WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {"username": row[0], "name": row[1], "first_seen": row[2]}
            return None


# ══ ECONOMY ═══════════════════════════════════════════════════════

async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT balance FROM economy WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def has_started(user_id: int) -> bool:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT started FROM economy WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return bool(row and row[0])


async def init_economy(user_id: int, amount: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO economy (user_id, balance, total_earned, started) VALUES (?,?,?,1)",
            (user_id, amount, amount)
        )
        await db.execute(
            "UPDATE economy SET started=1 WHERE user_id=? AND started=0",
            (user_id,)
        )
        await db.commit()


async def add_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO economy (user_id, balance, total_earned, started) VALUES (?,?,?,1) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "balance=balance+?, total_earned=total_earned+?",
            (user_id, amount, amount, amount, amount)
        )
        await db.commit()


async def remove_balance(user_id: int, amount: int) -> bool:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT balance FROM economy WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or row[0] < amount:
            return False
        await db.execute(
            "UPDATE economy SET balance=balance-? WHERE user_id=?", (amount, user_id)
        )
        await db.commit()
        return True


async def set_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO economy (user_id, balance, total_earned, started) VALUES (?,?,?,1) "
            "ON CONFLICT(user_id) DO UPDATE SET balance=?",
            (user_id, amount, amount, amount)
        )
        await db.commit()


async def get_top_rich(limit: int = 10) -> list:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT user_id, balance FROM economy ORDER BY balance DESC LIMIT ?", (limit,)
        ) as cur:
            return await cur.fetchall()


async def transfer_balance(from_id: int, to_id: int, amount: int) -> bool:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT balance FROM economy WHERE user_id=?", (from_id,)) as cur:
            row = await cur.fetchone()
        if not row or row[0] < amount:
            return False
        await db.execute("UPDATE economy SET balance=balance-? WHERE user_id=?", (amount, from_id))
        await db.execute(
            "INSERT INTO economy (user_id, balance, total_earned, started) VALUES (?,?,?,1) "
            "ON CONFLICT(user_id) DO UPDATE SET balance=balance+?, total_earned=total_earned+?",
            (to_id, amount, amount, amount, amount)
        )
        await db.commit()
        return True


# ══ ANTIPORN ══════════════════════════════════════════════════════

async def get_antiporn(chat_id: int) -> bool:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT enabled FROM antiporn_settings WHERE chat_id=?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return bool(row and row[0])


async def set_antiporn(chat_id: int, enabled: bool):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO antiporn_settings (chat_id, enabled) VALUES (?,?)",
            (chat_id, int(enabled))
        )
        await db.commit()


# ══ CHATBOT ═══════════════════════════════════════════════════════

async def get_chatbot_enabled(chat_id: int) -> bool:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT enabled FROM chatbot_settings WHERE chat_id=?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return bool(row and row[0])


async def set_chatbot(chat_id: int, enabled: bool):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO chatbot_settings (chat_id, enabled) VALUES (?,?)",
            (chat_id, int(enabled))
        )
        await db.commit()


async def learn_response(trigger: str, response: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO chatbot_data (trigger, response) VALUES (?,?)",
            (trigger.lower().strip(), response)
        )
        await db.commit()


async def get_chatbot_response(text: str) -> str | None:
    text_lower = text.lower().strip()
    async with aiosqlite.connect(DB) as db:
        # Exact match first
        async with db.execute(
            "SELECT response FROM chatbot_data WHERE trigger=?", (text_lower,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row[0]
        # Partial match
        words = text_lower.split()
        for word in words:
            if len(word) > 3:
                async with db.execute(
                    "SELECT response FROM chatbot_data WHERE trigger LIKE ? LIMIT 1",
                    (f"%{word}%",)
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        return row[0]
    return None


# ══ REACTION ══════════════════════════════════════════════════════

async def get_reaction_enabled(chat_id: int) -> bool:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT enabled FROM reaction_settings WHERE chat_id=?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return bool(row and row[0])


async def set_reaction(chat_id: int, enabled: bool):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO reaction_settings (chat_id, enabled) VALUES (?,?)",
            (chat_id, int(enabled))
        )
        await db.commit()


# ══ ADMIN BAN TRACKER (auto-demote safety) ═══════════════════════

async def track_admin_ban(chat_id: int, admin_id: int) -> int:
    """Returns ban count in last 10 seconds. Resets window if >10s passed."""
    import time
    now = int(time.time())
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT ban_count, window_start FROM admin_ban_tracker WHERE chat_id=? AND admin_id=?",
            (chat_id, admin_id)
        ) as cur:
            row = await cur.fetchone()

        if row:
            count, window_start = row
            if now - window_start > 10:
                # Reset window
                count = 1
                window_start = now
            else:
                count += 1
            await db.execute(
                "UPDATE admin_ban_tracker SET ban_count=?, window_start=? "
                "WHERE chat_id=? AND admin_id=?",
                (count, window_start, chat_id, admin_id)
            )
        else:
            count = 1
            await db.execute(
                "INSERT INTO admin_ban_tracker (chat_id, admin_id, ban_count, window_start) VALUES (?,?,1,?)",
                (chat_id, admin_id, now)
            )
        await db.commit()
        return count


async def reset_admin_ban_tracker(chat_id: int, admin_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "DELETE FROM admin_ban_tracker WHERE chat_id=? AND admin_id=?",
            (chat_id, admin_id)
        )
        await db.commit()


# ══ GAME PROTECTION ═══════════════════════════════════════════════

async def set_protection(chat_id: int, user_id: int, hours: int = 4):
    import time
    until = int(time.time()) + (hours * 3600)
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO game_protection (chat_id, user_id, until) VALUES (?,?,?)",
            (chat_id, user_id, until)
        )
        await db.commit()


async def is_protected(chat_id: int, user_id: int) -> bool:
    import time
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT until FROM game_protection WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            return bool(row and row[0] > int(time.time()))


async def get_protection_until(chat_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT until FROM game_protection WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_all_users_ids() -> list:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            return [r[0] for r in await cur.fetchall()]
