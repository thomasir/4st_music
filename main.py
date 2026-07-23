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


async def main():
    from pyrogram import idle
    from clients import bot, assistant, call_py
    from database import init_db

    log.info("🚀 Starting Apex All-in-One Bot v4.0 ...")

    await init_db()
    log.info("✅ Database initialised")

    await bot.start()
    log.info("✅ Bot client started")

    await assistant.start()
    log.info("✅ Assistant client started")

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
    log.info("🔥 Apex Bot v4.0 is LIVE!")

    await idle()

    log.info("🛑 Shutting down...")
    try:
        await call_py.stop()
    except Exception:
        pass
    await assistant.stop()
    await bot.stop()
    log.info("👋 Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
