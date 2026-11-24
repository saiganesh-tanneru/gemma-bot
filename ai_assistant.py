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

SERVER_URL = "http://127.0.0.1:8765"

def send_command(cmd_dict):
    """Sends a JSON command dict to Gemma-Bot in Webots."""
    url = f"{SERVER_URL}/command"
    data = json.dumps(cmd_dict).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"❌ Connection error: Could not reach Gemma-Bot at {SERVER_URL}.")
        print("   Make sure Webots is running with the 'gemma_bot.wbt' world loaded!")
        return None

def get_robot_status():
    """Gets the current status of Gemma-Bot from Webots."""
    url = f"{SERVER_URL}/status"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def parse_natural_language_intent(prompt):
    """
    Translates natural language instructions into structured Gemma-Bot commands.
    Supports gestures, moods, gaze direction, and companion speech.
    """
    p = prompt.lower().strip()
    action = {
        "thought": prompt,
        "mood": "NEUTRAL"
    }

    # 1. Gaze & Direction
    if "look left" in p or "turn left" in p:
        action["gaze"] = "left"
    elif "look right" in p or "turn right" in p:
        action["gaze"] = "right"
    elif "look up" in p:
        action["gaze"] = "up"
    elif "look down" in p:
        action["gaze"] = "down"
    elif "look at me" in p or "center" in p or "forward" in p:
        action["gaze"] = "center"

    # 2. Gestures & Moods / Emojis
    if any(w in p for w in ["wink", "😉", "flirt"]):
        action["mood"] = "WINK"
        action["speech"] = "Wink wink!"
    elif any(w in p for w in ["cool", "sunglasses", "shades", "😎"]):
        action["mood"] = "COOL"
        action["speech"] = "Stay cool!"
    elif any(w in p for w in ["star", "excited", "wow", "sparkle", "🤩", "✨"]):
        action["mood"] = "STAR_EYES"
        action["gesture"] = "perk_up"
        action["speech"] = "Amazing!"
    elif any(w in p for w in ["plead", "puppy", "beg", "please", "🥺"]):
        action["mood"] = "PLEADING"
        action["speech"] = "Pretty please?"
    elif any(w in p for w in ["cry", "sad", "tear", "sob", "😭", "😢"]):
        action["mood"] = "CRYING"
        action["gesture"] = "droop"
        action["speech"] = "Sniff... I am sad."
    elif any(w in p for w in ["dizzy", "ko", "confused", "spin", "😵"]):
        action["mood"] = "DIZZY"
        action["gesture"] = "shake"
        action["speech"] = "Whoa, my head is spinning!"
    elif any(w in p for w in ["tongue", "silly", "playful", "😋", "😜"]):
        action["mood"] = "TONGUE"
        action["gesture"] = "wiggle"
        action["speech"] = "Blep!"
    elif any(w in p for w in ["smirk", "sly", "mischief", "😏"]):
        action["mood"] = "SMIRK"
        action["speech"] = "Heh, you know it."
    elif any(w in p for w in ["love", "heart", "cute", "kiss", "adore", "😍", "❤️", "🥰"]):
        action["mood"] = "LOVE"
        action["gesture"] = "wiggle"
        action["speech"] = "I love you!"
    elif any(w in p for w in ["nod", "yes", "agree"]):
        action["gesture"] = "nod"
        action["mood"] = "HAPPY"
        action["speech"] = "Yes, absolutely!"
    elif any(w in p for w in ["shake", "no", "disagree"]):
        action["gesture"] = "shake"
        action["mood"] = "NEUTRAL"
        action["speech"] = "No, I don't think so."
    elif any(w in p for w in ["sleep", "tired", "goodnight", "nap", "😴"]):
        action["mood"] = "SLEEPY"
        action["gesture"] = "droop"
        action["speech"] = "Goodnight... Zzz"
    elif any(w in p for w in ["surprised", "omg", "shocked", "alert", "😮", "😲"]):
        action["mood"] = "SURPRISED"
        action["gesture"] = "perk_up"
        action["speech"] = "Whoa!"
    elif any(w in p for w in ["angry", "mad", "grumpy", "furious", "😡"]):
        action["mood"] = "ANGRY"
        action["speech"] = "Hmph!"
    elif any(w in p for w in ["think", "ponder", "calculate", "question", "why", "🤔"]):
        action["mood"] = "THINKING"
        action["gesture"] = "curious"
        action["speech"] = "Hmm, let me think..."
    elif any(w in p for w in ["joke", "funny"]):
        action["mood"] = "HAPPY"
        action["gesture"] = "wiggle"
        action["speech"] = "Why did the robot go on vacation? To recharge its batteries!"
    elif any(w in p for w in ["happy", "smile", "laugh", "pet", "wiggle", "dance", "😀", "😊"]):
        action["mood"] = "HAPPY"
        action["gesture"] = "wiggle"
        action["speech"] = "Hehe, happy to be here!"
    elif any(w in p for w in ["hello", "hi", "hey"]):
        action["mood"] = "HAPPY"
        action["gesture"] = "nod"
        action["speech"] = "Hello! I am Gemma-Bot!"

    return action

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
