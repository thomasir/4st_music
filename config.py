import os
import tempfile

def _env_int(name: str, default: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc


# ── Telegram credentials ───────────────────────────────────────────
# Never ship credentials or owner IDs as source-code defaults. All of these
# values must be configured as deployment environment variables.
API_ID          = _env_int("API_ID")
API_HASH        = os.environ.get("API_HASH", "").strip()
BOT_TOKEN       = os.environ.get("BOT_TOKEN", "").strip()
SESSION_STRING  = os.environ.get("SESSION_STRING", "").strip()

# ── Owner & logging ────────────────────────────────────────────────
OWNER_ID        = _env_int("OWNER_ID")
OWNER_USERNAME  = os.environ.get("OWNER_USERNAME", "").strip()
LOG_CHANNEL     = _env_int("LOG_CHANNEL")
SUPPORT_CHAT    = os.environ.get("SUPPORT_CHAT", "https://t.me/ApexAssociation")
SUDO_USERS      = [OWNER_ID] if OWNER_ID else []

# ── Must-join channel (leave empty to disable) ─────────────────────
MUST_JOIN       = os.environ.get("MUST_JOIN", "").strip().lstrip("@") or None

# ── Bot identity ───────────────────────────────────────────────────
BOT_NAME        = "🎵 Apex Music Bot"
BOT_VERSION     = "v6.0 Ultimate"   # BUG FIX: was "v5.0 Ultimate" — now matches main.py

# ── Streaming ──────────────────────────────────────────────────────
DURATION_LIMIT_MIN  = 0       # 0 = unlimited
try:
    FFMPEG_VOLUME_BOOST = float(os.environ.get("VOLUME_BOOST", "10.0"))
except ValueError as exc:
    raise RuntimeError("VOLUME_BOOST must be a number between 1.0 and 10.0") from exc

# ── Database ──────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "apex_bot.db")

# ── Download dir ──────────────────────────────────────────────────
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", tempfile.gettempdir())


def validate_config() -> None:
    """Fail early with an actionable message instead of a Telegram auth error."""
    missing = []
    if API_ID <= 0:
        missing.append("API_ID")
    if not API_HASH:
        missing.append("API_HASH")
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not SESSION_STRING:
        missing.append("SESSION_STRING")
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Configure them in the deployment settings; do not put them in source code."
        )
    if not 1.0 <= FFMPEG_VOLUME_BOOST <= 10.0:
        raise RuntimeError("VOLUME_BOOST must be between 1.0 and 10.0")

# ── Economy ───────────────────────────────────────────────────────
DAILY_REWARD_MIN = 500
DAILY_REWARD_MAX = 5000
FIRST_START_MIN  = 1000
FIRST_START_MAX  = 100000
