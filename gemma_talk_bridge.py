#!/usr/bin/env python3
"""
Gemma-Talk Bridge for Gemma-Bot
-------------------------------
Connects Gemma-Bot (in Webots) to the Gemma-Talk voice assistant backend.

It mirrors the real-time conversational states of Gemma-Talk into physical
robot behaviors and expressions:
- LISTENING   -> Eyes attentive, head turns toward user, perks up.
- THINKING    -> Mood 'THINKING', eyes look up, curious head tilt while Ollama runs.
- SPEAKING    -> Mood 'HAPPY', lip-sync mouth animation, conversational nodding.
- INTERRUPTED -> Instant barge-in cutoff: silences speech, halts mouth, blinks.

Usage:
  # 1. Start Gemma-Talk server in another terminal:
  #    cd /Users/saiganeshtanneru/Documents/gemma-talk && ./start-server.sh
  #
  # 2. Run this bridge:
  #    python3 gemma_talk_bridge.py
"""

import sys
import os
import json
import time
import asyncio
import urllib.request
import urllib.error

# Gemma-Bot Webots AI server endpoint
BOT_COMMAND_URL = "http://127.0.0.1:8765/command"
# Gemma-Talk backend WebSocket URL
GEMMA_TALK_WS_URL = "ws://localhost:8000/ws"

def send_bot_command(payload):
    """Sends a state/action payload to Gemma-Bot in Webots."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(BOT_COMMAND_URL, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        # Webots might be paused or starting
        return None

async def connect_to_gemma_talk():
    """Connects to Gemma-Talk WebSocket and streams session states to Gemma-Bot."""
    try:
        import websockets
    except ImportError:
        print("Installing websockets library...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
        import websockets

    print("=" * 65)
    print("🤖 Gemma-Talk <-> Gemma-Bot Bridge")
    print(f"🔗 Connecting to Gemma-Talk at {GEMMA_TALK_WS_URL}...")
    print(f"🤖 Forwarding actions to Gemma-Bot at {BOT_COMMAND_URL}...")
    print("=" * 65)

    retry_delay = 2
    while True:
        try:
            async with websockets.connect(GEMMA_TALK_WS_URL) as ws:
                print("✅ Connected to Gemma-Talk server!")
                send_bot_command({
                    "mood": "HAPPY",
                    "gesture": "nod",
                    "speech": "Connected to Gemma-Talk!"
                })

                async for message in ws:
                    if isinstance(message, str):
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type")

                            # 1. Handle State Changes
                            if msg_type == "state_change":
                                state = data.get("state", "").upper()
                                print(f"🔄 Gemma-Talk State: [{state}]")
                                if state == "LISTENING":
                                    send_bot_command({
                                        "state": "LISTENING",
                                        "mood": "NEUTRAL",
                                        "gaze": "center",
                                        "look_at": [0.0, -0.05]
                                    })
                                elif state == "THINKING":
                                    send_bot_command({
                                        "state": "THINKING",
                                        "gesture": "curious"
                                    })
                                elif state == "SPEAKING":
                                    send_bot_command({
                                        "state": "SPEAKING",
                                        "gesture": "nod"
                                    })
                                elif state in ("INTERRUPTED", "IDLE"):
                                    send_bot_command({
                                        "state": state,
                                        "interrupt": True
                                    })

                            # 2. Instant Flush / Interruption
                            elif msg_type == "flush":
                                print("⚡ Barge-in interruption detected! Silencing Gemma-Bot.")
                                send_bot_command({"interrupt": True})

                            # 3. Transcripts & LLM Tokens
                            elif msg_type == "transcript":
                                user_text = data.get("text", "")
                                print(f"👤 User: \"{user_text}\"")
                            elif msg_type == "llm_sentence":
                                bot_text = data.get("text", "")
                                print(f"🗣️ Gemma: \"{bot_text}\"")
                                send_bot_command({
                                    "mood": "HAPPY",
                                    "speech": bot_text
                                })

                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            print(f"⚠️ Gemma-Talk server not connected ({e}). Reconnecting in {retry_delay}s...")
            await asyncio.sleep(retry_delay)

def main():
    try:
        asyncio.run(connect_to_gemma_talk())
    except KeyboardInterrupt:
        print("\nBridge stopped.")

if __name__ == "__main__":
    main()
