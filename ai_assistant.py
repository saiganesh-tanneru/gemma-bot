#!/usr/bin/env python3
"""
Gemma-Bot AI Command Interface
------------------------------
Send natural language prompts or structured JSON commands to Gemma-Bot in Webots.

Usage:
  # Quick single commands:
  python3 ai_assistant.py "nod yes and smile"
  python3 ai_assistant.py "look left and act surprised"
  python3 ai_assistant.py "tell me a joke"
  python3 ai_assistant.py "go to sleep"
  
  # Interactive conversation mode:
  python3 ai_assistant.py -i
  
  # Direct JSON command:
  python3 ai_assistant.py --json '{"mood": "LOVE", "gesture": "wiggle", "speech": "I love robotics!"}'
"""

import sys
import os
import json
import urllib.request
import urllib.error
import argparse

import config
from intent_parser import create_intent_parser, parse_keyword_intent

SERVER_URL = config.BOT_BASE_URL

def _auth_headers(extra=None):
    headers = dict(extra or {})
    if config.BOT_AUTH_TOKEN:
        headers["X-Bot-Token"] = config.BOT_AUTH_TOKEN
    return headers


def send_command(cmd_dict):
    """Sends a JSON command dict to Gemma-Bot in Webots."""
    url = f"{SERVER_URL}/command"
    data = json.dumps(cmd_dict).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_auth_headers({"Content-Type": "application/json"}))
    try:
        with urllib.request.urlopen(req, timeout=config.CLI_COMMAND_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"❌ Connection error: Could not reach Gemma-Bot at {SERVER_URL}.")
        print("   Make sure Webots is running with the 'gemma_bot.wbt' world loaded!")
        return None

def get_robot_status():
    """Gets the current status of Gemma-Bot from Webots."""
    url = f"{SERVER_URL}/status"
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=config.CLI_STATUS_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def parse_natural_language_intent(prompt, parser=None):
    """
    Translates natural language instructions (English, Telugu, Tanglish) into validated
    Gemma-Bot commands using the configured LLM provider with keyword fallback.
    """
    active_parser = parser or create_intent_parser()
    return active_parser.parse(prompt)

def main():
    parser = argparse.ArgumentParser(description="Gemma-Bot AI Command Interface")
    parser.add_argument("prompt", nargs="*", help="Natural language command (e.g. 'nod yes and smile')")
    parser.add_argument("-i", "--interactive", action="store_true", help="Start interactive AI chat shell")
    parser.add_argument("--json", type=str, help="Send raw JSON command directly")
    parser.add_argument("--status", action="store_true", help="Print current Gemma-Bot status")
    args = parser.parse_args()

    if args.status:
        st = get_robot_status()
        if st:
            print("🤖 Gemma-Bot Status:")
            for k, v in st.items():
                print(f"  • {k}: {v}")
        else:
            print("❌ Gemma-Bot is offline. Start the simulation in Webots first.")
        return

    if args.json:
        try:
            cmd = json.loads(args.json)
            res = send_command(cmd)
            if res:
                print(f"✅ Executed JSON command: {cmd}")
        except Exception as e:
            print(f"Invalid JSON: {e}")
        return

    if args.interactive:
        print("=" * 60)
        print("🤖 Gemma-Bot Interactive AI Shell")
        print("Type commands like:")
        print("  - 'nod yes and smile'")
        print("  - 'shake your head no'")
        print("  - 'look left and act surprised'")
        print("  - 'tell me a joke'")
        print("  - 'go to sleep'")
        print("Type 'exit' or 'quit' to stop.")
        print("=" * 60)
        while True:
            try:
                line = input("\n👤 You: ").strip()
                if not line:
                    continue
                if line.lower() in ("exit", "quit", "q"):
                    break
                cmd = parse_natural_language_intent(line)
                res = send_command(cmd)
                if res:
                    sp = cmd.get("speech", "")
                    if sp:
                        print(f"🤖 Gemma-Bot: \"{sp}\" [Mood: {cmd.get('mood')}, Gesture: {cmd.get('gesture')}]")
                    else:
                        print(f"🤖 Gemma-Bot: [Mood: {cmd.get('mood')}, Gesture: {cmd.get('gesture')}, Gaze: {cmd.get('gaze')}]")
            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break
        return

    # Single prompt via command line arguments
    if args.prompt:
        user_prompt = " ".join(args.prompt)
        cmd = parse_natural_language_intent(user_prompt)
        res = send_command(cmd)
        if res:
            sp = cmd.get("speech", "")
            if sp:
                print(f"🤖 Gemma-Bot: \"{sp}\" [Mood: {cmd.get('mood')}, Gesture: {cmd.get('gesture')}]")
            else:
                print(f"🤖 Gemma-Bot: [Mood: {cmd.get('mood')}, Gesture: {cmd.get('gesture')}, Gaze: {cmd.get('gaze')}]")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
