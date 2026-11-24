"""
Centralized configuration for Gemma-Bot.
All settings have safe local defaults and can be overridden via environment variables or .env.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def _load_dotenv(env_path: Path) -> None:
    """Loads key=value pairs from .env without overriding already-set environment variables."""
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)


_load_dotenv(REPO_ROOT / ".env")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


# HTTP Command Server (Webots controller)
BOT_HOST = os.environ.get("GEMMA_BOT_HOST", "127.0.0.1")
BOT_PORT = _env_int("GEMMA_BOT_PORT", 8765)
BOT_BASE_URL = os.environ.get("GEMMA_BOT_URL", f"http://{BOT_HOST}:{BOT_PORT}").rstrip("/")
BOT_COMMAND_URL = f"{BOT_BASE_URL}/command"
BOT_STATUS_URL = f"{BOT_BASE_URL}/status"

# Optional shared secret for HTTP command authentication (used in Phase 4)
BOT_AUTH_TOKEN = os.environ.get("GEMMA_BOT_TOKEN", "")
MAX_BODY_BYTES = _env_int("GEMMA_MAX_BODY_BYTES", 16384)

# Gemma-Talk Voice Server / Bridge
GEMMA_TALK_WS_URL = os.environ.get("GEMMA_TALK_WS_URL", "ws://localhost:8000/ws")
GEMMA_TALK_DIR = Path(os.environ.get("GEMMA_TALK_DIR", str(Path.home() / "Documents" / "gemma-talk")))

# Paths
WORLD_PATH = Path(os.environ.get("GEMMA_WORLD_PATH", str(REPO_ROOT / "worlds" / "gemma_bot.wbt")))
ASSETS_DIR = Path(os.environ.get("GEMMA_ASSETS_DIR", str(REPO_ROOT / "docs" / "assets")))
LOG_DIR = Path(os.environ.get("GEMMA_LOG_DIR", str(REPO_ROOT / "logs")))
WEBOTS_APP = os.environ.get("WEBOTS_APP", "/Applications/Webots.app/Contents/MacOS/webots")

# Timeouts & intervals (seconds)
BRIDGE_TIMEOUT_SECONDS = _env_float("GEMMA_BRIDGE_TIMEOUT", 1.5)
BRIDGE_HEALTH_TIMEOUT_SECONDS = _env_float("GEMMA_BRIDGE_HEALTH_TIMEOUT", 1.0)
BRIDGE_HEALTH_INTERVAL_SECONDS = _env_float("GEMMA_BRIDGE_HEALTH_INTERVAL", 5.0)
BRIDGE_WS_RETRY_BASE_SECONDS = _env_float("GEMMA_BRIDGE_WS_RETRY_BASE", 2.0)
BRIDGE_WS_RETRY_MAX_SECONDS = _env_float("GEMMA_BRIDGE_WS_RETRY_MAX", 30.0)
CLI_COMMAND_TIMEOUT_SECONDS = _env_float("GEMMA_CLI_COMMAND_TIMEOUT", 3.0)
CLI_STATUS_TIMEOUT_SECONDS = _env_float("GEMMA_CLI_STATUS_TIMEOUT", 2.0)

# Speech / TTS configuration
_DEFAULT_TTS = "mac_say" if sys.platform == "darwin" else "null"
TTS_PROVIDER = os.environ.get("GEMMA_TTS_PROVIDER", _DEFAULT_TTS).lower().strip()
TTS_MAC_VOICE = os.environ.get("GEMMA_TTS_MAC_VOICE", "Samantha")

# Sarvam AI API (env-only secret; never log or commit)
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_TTS_URL = os.environ.get("GEMMA_SARVAM_TTS_URL", "https://api.sarvam.ai/text-to-speech")
SARVAM_TTS_MODEL = os.environ.get("GEMMA_SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_TTS_SPEAKER = os.environ.get("GEMMA_SARVAM_TTS_SPEAKER", "shubh")
SARVAM_TTS_LANGUAGE = os.environ.get("GEMMA_SARVAM_TTS_LANGUAGE", "en-IN")
SARVAM_TTS_TIMEOUT_SECONDS = _env_float("GEMMA_SARVAM_TTS_TIMEOUT", 5.0)

# Intent Parser / LLM configuration
INTENT_PROVIDER = os.environ.get(
    "GEMMA_INTENT_PROVIDER",
    "sarvam" if SARVAM_API_KEY else "keyword",
).lower().strip()
# NOTE: /v1 is the preferred endpoint for sarvam-105b. /v2 also serves it, but
# some /v2 requests to sarvam-105b have been observed stalling without an answer
# (LiteLLM keeps sarvam-105b on /v1 for this reason). Open-weight models must use /v2.
SARVAM_CHAT_URL = os.environ.get("GEMMA_SARVAM_CHAT_URL", "https://api.sarvam.ai/v1/chat/completions")
SARVAM_LLM_MODEL = os.environ.get("GEMMA_SARVAM_LLM_MODEL", "sarvam-105b")
INTENT_TIMEOUT_SECONDS = _env_float("GEMMA_INTENT_TIMEOUT", 4.0)
