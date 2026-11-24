#!/usr/bin/env bash
# ==============================================================================
# Gemma-Bot Unified Launch Script (Self-Contained, Sarvam AI Powered)
# ==============================================================================
# Launches all services from within gemma-bot:
# 1. Sarvam AI configuration check
# 2. Webots 3D Simulation (Gemma-Bot in realtime mode)
# 3. Integrated Voice Server (voice_server: Silero VAD + STT + Sarvam LLM/TTS)
# 4. Robot <-> Voice Bridge (gemma_talk_bridge.py)
# 5. Voice Web UI (voice_client) & opens browser
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="$SCRIPT_DIR"

# Load .env overrides if present without clobbering existing environment variables
if [ -f "$BOT_DIR/.env" ]; then
    while IFS='=' read -r k v; do
        [[ -z "$k" || "$k" == \#* ]] && continue
        k="${k%%[[:space:]]*}"
        v="${v#\"}"; v="${v%\"}"; v="${v#\'}"; v="${v%\'}"
        if [ -z "${!k+x}" ]; then
            export "$k=$v"
        fi
    done < "$BOT_DIR/.env"
fi

if [ -x "$BOT_DIR/.venv/bin/python3" ]; then
    CFG_PYTHON="$BOT_DIR/.venv/bin/python3"
else
    CFG_PYTHON="$(command -v python3)"
fi

PYTHON_BIN="${GEMMA_PYTHON_BIN:-$CFG_PYTHON}"

_cfg() {
    "$CFG_PYTHON" -c "import sys; sys.path.insert(0, '$BOT_DIR'); import config; print($1)"
}

WEBOTS_APP="${WEBOTS_APP:-$(_cfg 'config.WEBOTS_APP')}"
LOG_DIR="${GEMMA_LOG_DIR:-$(_cfg 'str(config.LOG_DIR)')}"
BOT_STATUS_URL="$(_cfg 'config.BOT_STATUS_URL')"
BOT_BASE_URL="$(_cfg 'config.BOT_BASE_URL')"
VOICE_HOST="$(_cfg 'config.VOICE_SERVER_HOST')"
VOICE_PORT="$(_cfg 'config.VOICE_SERVER_PORT')"
VOICE_CLIENT_PORT="$(_cfg 'config.VOICE_CLIENT_PORT')"
WORLD_PATH="$(_cfg 'str(config.WORLD_PATH)')"
mkdir -p "$LOG_DIR"

# Color styles
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

echo -e "\n${BOLD}${CYAN}╔═════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║            🤖 GEMMA-BOT SARVAM VOICE LAUNCHER                   ║${NC}"
echo -e "${BOLD}${CYAN}╚═════════════════════════════════════════════════════════════════╝${NC}\n"

if [ ! -x "$WEBOTS_APP" ]; then
    echo -e "${RED}❌ Error: Webots application not found at $WEBOTS_APP${NC}"
    exit 1
fi

PIDS=()
CLEANED_UP=0

kill_tree() {
    local pid="$1"
    local child
    if command -v pgrep > /dev/null 2>&1; then
        for child in $(pgrep -P "$pid" 2>/dev/null || true); do
            kill_tree "$child"
        done
    fi
    if kill -0 "$pid" > /dev/null 2>&1; then
        kill "$pid" > /dev/null 2>&1 || true
    fi
}

cleanup() {
    if [ "$CLEANED_UP" -eq 1 ]; then
        return 0
    fi
    CLEANED_UP=1
    echo -e "\n${BOLD}${YELLOW}🛑 Shutting down all Gemma-Bot services...${NC}"
    for pid in "${PIDS[@]}"; do
        kill_tree "$pid"
    done
    echo -e "${GREEN}✓ All services stopped cleanly.${NC}"
}
trap cleanup EXIT
trap 'cleanup; exit 130' SIGINT
trap 'cleanup; exit 143' SIGTERM

_check_bot_status() {
    if [ -n "${GEMMA_BOT_TOKEN:-}" ]; then
        curl -sf -H "X-Bot-Token: $GEMMA_BOT_TOKEN" "$BOT_STATUS_URL" > /dev/null 2>&1
    else
        curl -sf "$BOT_STATUS_URL" > /dev/null 2>&1
    fi
}

# wait_for <timeout_seconds> <command...>
wait_for() {
    local timeout_secs="$1"
    shift
    local tries=$((timeout_secs * 2))
    local i
    for ((i = 1; i <= tries; i++)); do
        if "$@" > /dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

# ------------------------------------------------------------------------------
# 1. Check Sarvam AI Configuration
# ------------------------------------------------------------------------------
echo -e "${BOLD}[1/5] Checking Sarvam AI Configuration...${NC}"
if [ -n "${SARVAM_API_KEY:-}" ]; then
    echo -e "${GREEN}✓ SARVAM_API_KEY detected (Sarvam LLM & TTS ready)${NC}"
else
    echo -e "${YELLOW}⚠️  SARVAM_API_KEY not set. Voice LLM & Sarvam TTS will need it in .env or env.${NC}"
fi

# ------------------------------------------------------------------------------
# 2. Launch Webots Simulation
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[2/5] Launching Webots Simulation (Gemma-Bot)...${NC}"
if _check_bot_status; then
    echo -e "${GREEN}✓ Gemma-Bot simulation is already running in Webots!${NC}"
else
    echo "Starting Webots in real-time mode..."
    "$WEBOTS_APP" --mode=realtime --batch "$WORLD_PATH" > /dev/null 2>&1 &
    WEBOTS_PID=$!
    PIDS+=("$WEBOTS_PID")

    echo "Waiting for Gemma-Bot AI controller to initialize..."
    if ! wait_for 15 _check_bot_status; then
        echo -e "${RED}❌ Error: Gemma-Bot controller did not become ready in time.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Gemma-Bot Webots controller active on $BOT_BASE_URL${NC}"
fi

# ------------------------------------------------------------------------------
# 3. Launch Integrated Sarvam Voice Server
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[3/5] Starting Gemma-Bot Voice Server (Sarvam AI)...${NC}"
VOICE_HEALTH_URL="http://127.0.0.1:${VOICE_PORT}/health"
if curl -sf "$VOICE_HEALTH_URL" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Voice server is already running on http://127.0.0.1:${VOICE_PORT}${NC}"
else
    VOICE_LOG="$LOG_DIR/voice_server.log"
    (
        cd "$BOT_DIR"
        export PYTHONPATH="$BOT_DIR"
        exec "$PYTHON_BIN" -m uvicorn voice_server.main:app --host "$VOICE_HOST" --port "$VOICE_PORT"
    ) > "$VOICE_LOG" 2>&1 &
    SERVER_PID=$!
    PIDS+=("$SERVER_PID")

    echo "Waiting for voice server health on $VOICE_HEALTH_URL..."
    for i in {1..60}; do
        if ! kill -0 "$SERVER_PID" > /dev/null 2>&1; then
            echo -e "${RED}❌ Error: voice_server died on startup!${NC}"
            tail -n 20 "$VOICE_LOG" 2>/dev/null || true
            exit 1
        fi
        if curl -sf "$VOICE_HEALTH_URL" > /dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    echo -e "${GREEN}✓ Voice server ready on http://127.0.0.1:${VOICE_PORT} (log: $VOICE_LOG)${NC}"
fi

# ------------------------------------------------------------------------------
# 4. Launch Voice <-> Robot Bridge
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[4/5] Launching Voice <-> Gemma-Bot Bridge...${NC}"
BRIDGE_LOG="$LOG_DIR/gemma_talk_bridge.log"
"$PYTHON_BIN" "$BOT_DIR/gemma_talk_bridge.py" > "$BRIDGE_LOG" 2>&1 &
BRIDGE_PID=$!
PIDS+=("$BRIDGE_PID")

sleep 0.5
if ! kill -0 "$BRIDGE_PID" > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Gemma-Bot bridge (gemma_talk_bridge.py) died on startup!${NC}"
    if [ -s "$BRIDGE_LOG" ]; then
        echo -e "${YELLOW}--- Bridge log ($BRIDGE_LOG) ---${NC}"
        tail -n 20 "$BRIDGE_LOG"
    fi
    exit 1
fi
echo -e "${GREEN}✓ Bridge active (PID $BRIDGE_PID, log: $BRIDGE_LOG)${NC}"

# ------------------------------------------------------------------------------
# 5. Launch Voice Web UI & Open Browser
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[5/5] Launching Voice Web UI Client...${NC}"
CLIENT_URL="http://localhost:${VOICE_CLIENT_PORT}"
if [ -d "$BOT_DIR/voice_client" ] && command -v npm > /dev/null 2>&1; then
    CLIENT_LOG="$LOG_DIR/voice_client.log"
    (
        cd "$BOT_DIR/voice_client"
        exec npm run dev -- --port "$VOICE_CLIENT_PORT"
    ) > "$CLIENT_LOG" 2>&1 &
    CLIENT_PID=$!
    PIDS+=("$CLIENT_PID")

    if ! wait_for 10 curl -sf "$CLIENT_URL"; then
        echo -e "${YELLOW}⚠️ Warning: Web UI did not respond on ${CLIENT_URL} after 10s.${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  npm or voice_client not found; skipping web UI startup.${NC}"
fi

echo -e "\n${BOLD}${GREEN}═════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}🎉 ALL SYSTEMS ARE LIVE!${NC}"
echo -e " • 🌐 Web UI:       ${BOLD}${CYAN}${CLIENT_URL}${NC}"
echo -e " • 🤖 Robot Server: ${BOLD}${CYAN}${BOT_BASE_URL}${NC}"
echo -e " • 🧠 Voice Server: ${BOLD}${CYAN}http://127.0.0.1:${VOICE_PORT}${NC}"
echo -e " • ⏹️  Press ${BOLD}Ctrl+C${NC} in this terminal to stop everything."
echo -e "${BOLD}${GREEN}═════════════════════════════════════════════════════════════════${NC}\n"

open "$CLIENT_URL" || true
wait
