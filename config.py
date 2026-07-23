import os
import tempfile

# ── Telegram credentials ───────────────────────────────────────────
API_ID          = int(os.environ.get("API_ID", "0"))
API_HASH        = os.environ.get("API_HASH", "")
BOT_TOKEN       = os.environ.get("BOT_TOKEN", "")
SESSION_STRING  = os.environ.get("SESSION_STRING", "")

# ── Owner & logging ────────────────────────────────────────────────
OWNER_ID        = int(os.environ.get("OWNER_ID", "8098146730"))
OWNER_USERNAME  = os.environ.get("OWNER_USERNAME", "TheY_CaIl_mE_OG")
LOG_CHANNEL     = int(os.environ.get("LOG_CHANNEL", "-1004334848663"))
SUPPORT_CHAT    = os.environ.get("SUPPORT_CHAT", "https://t.me/ApexAssociation")
SUDO_USERS      = [OWNER_ID]

# ── Must-join channel (leave empty to disable) ─────────────────────
MUST_JOIN       = os.environ.get("MUST_JOIN", "").strip().lstrip("@") or None

# ── Bot identity ───────────────────────────────────────────────────
BOT_NAME        = "🎵 Apex Music Bot"
BOT_VERSION     = "v5.0 Ultimate"

# ── Streaming ──────────────────────────────────────────────────────
DURATION_LIMIT_MIN  = 0       # 0 = unlimited
FFMPEG_VOLUME_BOOST = float(os.environ.get("VOLUME_BOOST", "10.0"))

# ── Database ──────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "apex_bot.db")

# ── Download dir ──────────────────────────────────────────────────
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", tempfile.gettempdir())

# ── Economy ───────────────────────────────────────────────────────
DAILY_REWARD_MIN = 5
DAILY_REWARD_MAX = 5000
FIRST_START_MIN  = 1000
FIRST_START_MAX  = 100000
