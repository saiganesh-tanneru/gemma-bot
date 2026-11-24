#!/usr/bin/env bash
# ==============================================================================
# Gemma-Bot & Gemma-Talk: All-In-One Unified Launch Script
# ==============================================================================
# Launches all services needed for full conversational desktop buddy:
# 1. Ollama local LLM server (if not already running)
# 2. Webots 3D Simulation (Gemma-Bot in realtime mode)
# 3. Gemma-Talk FastAPI Voice Backend (Silero VAD + Whisper + Ollama + Kokoro TTS)
# 4. Gemma-Talk to Gemma-Bot WebSocket Bridge (physical actions & lip sync)
# 5. Gemma-Talk Web UI Frontend & opens browser at http://localhost:5173
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="$SCRIPT_DIR"
TALK_DIR="${GEMMA_TALK_DIR:-$HOME/Documents/gemma-talk}"
WEBOTS_APP="${WEBOTS_APP:-/Applications/Webots.app/Contents/MacOS/webots}"
LOG_DIR="${GEMMA_LOG_DIR:-$BOT_DIR/logs}"
mkdir -p "$LOG_DIR"

# Color styles
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
MAGENTA="\033[0;35m"
NC="\033[0m"

echo -e "\n${BOLD}${CYAN}╔═════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║           🤖 GEMMA-BOT + GEMMA-TALK UNIFIED LAUNCHER           ║${NC}"
echo -e "${BOLD}${CYAN}╚═════════════════════════════════════════════════════════════════╝${NC}\n"

# Verify directories
if [ ! -d "$TALK_DIR" ]; then
    echo -e "${RED}❌ Error: Gemma-Talk directory not found at $TALK_DIR${NC}"
    echo "Set GEMMA_TALK_DIR environment variable if installed in another location."
    exit 1
fi

if [ ! -x "$WEBOTS_APP" ]; then
    echo -e "${RED}❌ Error: Webots application not found at $WEBOTS_APP${NC}"
    exit 1
fi

# Determine python interpreter (prefer gemma-talk virtual environment with full dependencies)
if [ -f "$TALK_DIR/server/.venv/bin/python3" ]; then
    PYTHON_BIN="$TALK_DIR/server/.venv/bin/python3"
else
    PYTHON_BIN="$(which python3)"
fi

# Track spawned process PIDs for clean exit
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
    echo -e "\n${BOLD}${YELLOW}🛑 Shutting down all Gemma-Bot and Gemma-Talk services...${NC}"
    for pid in "${PIDS[@]}"; do
        kill_tree "$pid"
    done
    echo -e "${GREEN}✓ All services stopped cleanly.${NC}"
}
trap cleanup EXIT
trap 'cleanup; exit 130' SIGINT
trap 'cleanup; exit 143' SIGTERM

# ------------------------------------------------------------------------------
# 1. Check & Launch Ollama
# ------------------------------------------------------------------------------
echo -e "${BOLD}[1/5] Checking Ollama LLM Service...${NC}"
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ollama is already active on http://localhost:11434${NC}"
else
    echo -e "Starting Ollama server..."
    if command -v ollama > /dev/null 2>&1; then
        ollama serve > /dev/null 2>&1 &
        OLLAMA_PID=$!
        PIDS+=("$OLLAMA_PID")
    elif [ -x "$HOME/.local/bin/ollama" ]; then
        "$HOME/.local/bin/ollama" serve > /dev/null 2>&1 &
        OLLAMA_PID=$!
        PIDS+=("$OLLAMA_PID")
    fi
    # Wait for Ollama
    for i in {1..15}; do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    echo -e "${GREEN}✓ Ollama started successfully.${NC}"
fi

# ------------------------------------------------------------------------------
# 2. Launch Webots Simulation
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[2/5] Launching Webots Simulation (Gemma-Bot)...${NC}"
if curl -s http://127.0.0.1:8765/status > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Gemma-Bot simulation is already running in Webots!${NC}"
else
    echo "Starting Webots in real-time mode..."
    "$WEBOTS_APP" --mode=realtime --batch "$BOT_DIR/worlds/gemma_bot.wbt" > /dev/null 2>&1 &
    WEBOTS_PID=$!
    PIDS+=("$WEBOTS_PID")

    echo "Waiting for Gemma-Bot AI controller to initialize..."
    for i in {1..30}; do
        if curl -s http://127.0.0.1:8765/status > /dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    echo -e "${GREEN}✓ Gemma-Bot Webots controller active on http://127.0.0.1:8765${NC}"
fi

# ------------------------------------------------------------------------------
# 3. Launch Gemma-Talk Voice Assistant Backend
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[3/5] Starting Gemma-Talk Voice Backend...${NC}"
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Gemma-Talk backend is already running on http://localhost:8000${NC}"
else
    (
        cd "$TALK_DIR"
        "$TALK_DIR/start-server.sh"
    ) &
    SERVER_PID=$!
    PIDS+=("$SERVER_PID")

    echo "Waiting for voice models (Silero VAD + Whisper + Kokoro TTS) to warm up..."
    while ! curl -s http://localhost:8000/health > /dev/null 2>&1; do
        sleep 0.5
    done
    echo -e "${GREEN}✓ Gemma-Talk backend is ready on http://localhost:8000${NC}"
fi

# ------------------------------------------------------------------------------
# 4. Launch Gemma-Talk to Gemma-Bot Bridge
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[4/5] Launching Gemma-Talk <-> Gemma-Bot Bridge...${NC}"
BRIDGE_LOG="$LOG_DIR/gemma_talk_bridge.log"
"$PYTHON_BIN" "$BOT_DIR/gemma_talk_bridge.py" > "$BRIDGE_LOG" 2>&1 &
BRIDGE_PID=$!
PIDS+=("$BRIDGE_PID")

sleep 0.5
if ! kill -0 "$BRIDGE_PID" > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Gemma-Talk bridge (gemma_talk_bridge.py) died on startup!${NC}"
    if [ -s "$BRIDGE_LOG" ]; then
        echo -e "${YELLOW}--- Bridge log ($BRIDGE_LOG) ---${NC}"
        tail -n 20 "$BRIDGE_LOG"
    fi
    exit 1
fi
echo -e "${GREEN}✓ Gemma-Talk bridge active (PID $BRIDGE_PID, log: $BRIDGE_LOG)${NC}"

# ------------------------------------------------------------------------------
# 5. Launch Gemma-Talk Web UI & Open Browser
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[5/5] Launching Web UI Client...${NC}"
(
    cd "$TALK_DIR"
    "$TALK_DIR/start-client.sh" > /dev/null 2>&1
) &
CLIENT_PID=$!
PIDS+=("$CLIENT_PID")

# Wait for client port 5173
for i in {1..20}; do
    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

echo -e "\n${BOLD}${GREEN}═════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}🎉 ALL SYSTEMS ARE LIVE!${NC}"
echo -e " • 🌐 Web UI:       ${BOLD}${CYAN}http://localhost:5173${NC}"
echo -e " • 🤖 Robot Server: ${BOLD}${CYAN}http://127.0.0.1:8765${NC}"
echo -e " • 🧠 Voice Server: ${BOLD}${CYAN}http://localhost:8000${NC}"
echo -e " • 💡 Just speak naturally into your microphone!"
echo -e " • ⏹️  Press ${BOLD}Ctrl+C${NC} in this terminal to stop everything."
echo -e "${BOLD}${GREEN}═════════════════════════════════════════════════════════════════${NC}\n"

# Open the browser automatically
open "http://localhost:5173" || true

# Keep running until Ctrl+C
wait
