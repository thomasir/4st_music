"""
main.py — Apex Bot v6.0 Ultimate
✅ FloodWait retry loop (no more crash-restart death spiral on Heroku)
✅ Proper shutdown handling
"""

import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("pytgcalls").setLevel(logging.WARNING)
logging.getLogger("ntgcalls").setLevel(logging.WARNING)

log = logging.getLogger("ApexBot")


async def _start_client(client, name: str, max_retries: int = 10):
    """Start a Pyrogram client with FloodWait retry.

    This prevents the crash-restart death spiral on Heroku:
    - Without this: FloodWait → crash → Heroku restarts → FloodWait again → loop
    - With this: FloodWait → sleep inside the process → retry → success
    """
    from pyrogram.errors import FloodWait, AuthKeyUnregistered, UserDeactivated

    for attempt in range(1, max_retries + 1):
        try:
            await client.start()
            log.info(f"✅ {name} started successfully (attempt {attempt})")
            return
        except FloodWait as e:
            wait = e.value + 10   # add 10s buffer
            log.warning(
                f"⏳ FloodWait on {name}: Telegram says wait {e.value}s "
                f"(sleeping {wait}s, attempt {attempt}/{max_retries})..."
            )
            # Log progress every 30s so Heroku doesn't think we're dead
            elapsed = 0
            while elapsed < wait:
                chunk = min(30, wait - elapsed)
                await asyncio.sleep(chunk)
                elapsed += chunk
                remaining = wait - elapsed
                if remaining > 0:
                    log.info(f"  ⏳ {name}: {remaining:.0f}s remaining before retry...")
            log.info(f"  ✅ FloodWait over — retrying {name}...")
        except (AuthKeyUnregistered, UserDeactivated) as e:
            log.error(
                f"❌ {name} session is invalid: {e}\n"
                f"   → For BOT: regenerate BOT_TOKEN env var\n"
                f"   → For ASSISTANT: regenerate SESSION_STRING env var"
            )
            raise
        except Exception as e:
            log.error(f"❌ {name} start error (attempt {attempt}): {e}")
            if attempt >= max_retries:
                raise
            await asyncio.sleep(5 * attempt)   # exponential backoff

    raise RuntimeError(f"Could not start {name} after {max_retries} attempts")


async def main():
    from pyrogram import idle
    from clients import bot, assistant, call_py
    from database import init_db

    log.info("🚀 Starting Apex All-in-One Bot v6.0 ...")

    await init_db()
    log.info("✅ Database initialised")

    # ── Start clients with FloodWait protection ──────────────────────
    await _start_client(bot, "Bot")
    await _start_client(assistant, "Assistant")

    await call_py.start()
    log.info("✅ PyTgCalls started")

    bot_me  = await bot.get_me()
    asst_me = await assistant.get_me()

    log.info(f"🤖 Bot       : @{bot_me.username} ({bot_me.first_name})")
    log.info(f"👤 Assistant : @{asst_me.username} ({asst_me.first_name})")
    log.info("━" * 55)
    log.info("  🎵 MUSIC  : /play /vplay /pause /resume /skip /stop")
    log.info("  👮 ADMIN  : /ban /kick /mute /warn /promote /demote")
    log.info("  🛡️  SAFETY : Anti-spam, Word Filter, GBAN, Captcha")
    log.info("  📝 TOOLS  : Notes, Stats, Broadcast, Welcome")
    log.info("  🎮 FUN    : Games, AI Chat, Jokes, Shayari")
    log.info("━" * 55)
    log.info("🔥 Apex Bot v6.0 is LIVE!")

    await idle()

    log.info("🛑 Shutting down...")
    try:
        await call_py.stop()
    except Exception:
        pass
    try:
        await assistant.stop()
    except Exception:
        pass
    try:
        await bot.stop()
    except Exception:
        pass
    log.info("👋 Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
