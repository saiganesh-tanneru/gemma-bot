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


if os.environ.get("GEMMA_SKIP_DOTENV") != "1":
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

# Sarvam AI API (env-only secret; never log or commit)
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")

# Voice Server & Web UI (integrated pipeline)
VOICE_SERVER_HOST = os.environ.get("GEMMA_VOICE_HOST", "0.0.0.0")
VOICE_SERVER_PORT = _env_int("GEMMA_VOICE_PORT", 8000)
VOICE_CLIENT_PORT = _env_int("GEMMA_VOICE_CLIENT_PORT", 5173)
VOICE_MODELS_DIR = Path(os.environ.get("GEMMA_MODELS_DIR", str(REPO_ROOT / "voice_server" / "models")))
VOICE_AUDIO_SAMPLE_RATE = _env_int("GEMMA_AUDIO_SAMPLE_RATE", 16000)
VOICE_AUDIO_CHUNK_SAMPLES = _env_int("GEMMA_AUDIO_CHUNK_SAMPLES", 512)
VOICE_VAD_THRESHOLD = _env_float("GEMMA_VAD_THRESHOLD", 0.35)
VOICE_VAD_SILENCE_MS = _env_int("GEMMA_VAD_SILENCE_MS", 400)
VOICE_STT_ENGINE = os.environ.get(
    "GEMMA_STT_ENGINE",
    "sarvam" if SARVAM_API_KEY else "ai4bharat",
).lower().strip()
VOICE_INDIC_LANG = os.environ.get("GEMMA_INDIC_LANG", "te")
VOICE_WHISPER_MODEL = os.environ.get("GEMMA_WHISPER_MODEL", "small")
VOICE_WHISPER_DEVICE = os.environ.get("GEMMA_WHISPER_DEVICE", "cpu")
VOICE_WHISPER_COMPUTE_TYPE = os.environ.get("GEMMA_WHISPER_COMPUTE_TYPE", "int8")
VOICE_WHISPER_CPU_THREADS = _env_int("GEMMA_WHISPER_CPU_THREADS", 4)
VOICE_WHISPER_LANGUAGE = os.environ.get("GEMMA_WHISPER_LANGUAGE", "") or None
VOICE_TTS_VOICE = os.environ.get("GEMMA_VOICE_TTS_VOICE", "af_heart")
VOICE_TTS_SPEED = _env_float("GEMMA_VOICE_TTS_SPEED", 1.0)
VOICE_TTS_SAMPLE_RATE = 24000
VOICE_SYSTEM_PROMPT = os.environ.get(
    "GEMMA_VOICE_SYSTEM_PROMPT",
    (
        "You are Gemma-Bot, a friendly, expressive, and natural conversational desktop companion. "
        "Respond naturally and concisely in 1-3 sentences (supporting English, Telugu, or Tanglish as the user speaks), "
        "avoiding markdown, bullet points, asterisks, emojis, and code blocks unless requested."
    ),
)

# Voice Server Bridge WebSocket URL (subscribes to /ws/events on voice_server)
GEMMA_TALK_WS_URL = os.environ.get("GEMMA_TALK_WS_URL", f"ws://127.0.0.1:{VOICE_SERVER_PORT}/ws/events")

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

# Speech / TTS configuration (defaults to sarvam when SARVAM_API_KEY is set)
_DEFAULT_TTS = "sarvam" if SARVAM_API_KEY else ("mac_say" if sys.platform == "darwin" else "null")
TTS_PROVIDER = os.environ.get("GEMMA_TTS_PROVIDER", _DEFAULT_TTS).lower().strip()
TTS_MAC_VOICE = os.environ.get("GEMMA_TTS_MAC_VOICE", "Samantha")

SARVAM_STT_URL = os.environ.get("GEMMA_SARVAM_STT_URL", "https://api.sarvam.ai/speech-to-text")
SARVAM_STT_MODEL = os.environ.get("GEMMA_SARVAM_STT_MODEL", "saaras:v4")
SARVAM_STT_LANGUAGE = os.environ.get("GEMMA_SARVAM_STT_LANGUAGE", "unknown")
SARVAM_STT_MODE = os.environ.get("GEMMA_SARVAM_STT_MODE", "transcribe")
SARVAM_STT_TIMEOUT_SECONDS = _env_float("GEMMA_SARVAM_STT_TIMEOUT", 10.0)

SARVAM_TTS_URL = os.environ.get("GEMMA_SARVAM_TTS_URL", "https://api.sarvam.ai/text-to-speech")
SARVAM_TTS_MODEL = os.environ.get("GEMMA_SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_TTS_SPEAKER = os.environ.get("GEMMA_SARVAM_TTS_SPEAKER", "shubh")
SARVAM_TTS_LANGUAGE = os.environ.get("GEMMA_SARVAM_TTS_LANGUAGE", "en-IN")
SARVAM_TTS_TIMEOUT_SECONDS = _env_float("GEMMA_SARVAM_TTS_TIMEOUT", 5.0)
VOICE_TTS_ENGINE = os.environ.get(
    "GEMMA_VOICE_TTS_ENGINE",
    "sarvam" if SARVAM_API_KEY else "kokoro",
).lower().strip()

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
