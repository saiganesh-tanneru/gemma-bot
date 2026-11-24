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
import re
import json
import urllib.request
import urllib.error
import argparse

import config

SERVER_URL = config.BOT_BASE_URL

def send_command(cmd_dict):
    """Sends a JSON command dict to Gemma-Bot in Webots."""
    url = f"{SERVER_URL}/command"
    data = json.dumps(cmd_dict).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
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
    try:
        with urllib.request.urlopen(url, timeout=config.CLI_STATUS_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def _matches_keyword(text: str, keyword: str) -> bool:
    """Match word/phrase keywords on word boundaries; emojis match directly."""
    if not keyword:
        return False
    is_word_kw = (keyword[0].isalnum() or keyword[0] == "_") and (keyword[-1].isalnum() or keyword[-1] == "_")
    if not is_word_kw:
        return keyword in text
    parts = keyword.split()
    pattern = r"\b" + r"[\s-]+".join(re.escape(part) for part in parts) + r"\b"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _match_first_rule(text: str, rules):
    """Evaluate multi-word phrases before single words and return the winning rule payload."""
    candidates = []
    for keywords, payload in rules:
        for kw in keywords:
            candidates.append((len(kw.split()), len(kw), kw, payload))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    for _, _, kw, payload in candidates:
        if _matches_keyword(text, kw):
            return payload
    return None


GAZE_RULES = [
    (["look left", "turn left"], {"gaze": "left"}),
    (["look right", "turn right"], {"gaze": "right"}),
    (["look up"], {"gaze": "up"}),
    (["look down"], {"gaze": "down"}),
    (["look at me", "center", "forward"], {"gaze": "center"}),
]

SCREEN_COLOR_RULES = [
    (["green screen", "green eye", "green eyes", "matrix screen", "matrix theme", "emerald"],
     {"screen_color": "GREEN", "speech": "Switching screen to Matrix Emerald!"}),
    (["amber screen", "amber eye", "amber eyes", "yellow screen", "orange screen", "gold screen"],
     {"screen_color": "AMBER", "speech": "Switching screen to Retro Amber!"}),
    (["cyan screen", "cyan eye", "cyan eyes", "electric screen", "teal screen"],
     {"screen_color": "CYAN", "speech": "Switching screen to Electric Cyan!"}),
    (["purple screen", "purple eye", "purple eyes", "violet screen"],
     {"screen_color": "PURPLE", "speech": "Switching screen to Cyberpunk Violet!"}),
    (["blue screen", "blue eye", "blue eyes"],
     {"screen_color": "BLUE", "speech": "Switching screen to Neon Blue!"}),
    (["white screen", "white eye", "white eyes"],
     {"screen_color": "WHITE", "speech": "Switching screen to High-Contrast White!"}),
]

GESTURE_RULES = [
    (["curious", "tilt head", "inquisitive"], {"gesture": "curious", "mood": "THINKING", "speech": "Hmm, interesting!"}),
    (["perk up", "perk_up", "perk", "attentive", "alert"], {"gesture": "perk_up", "mood": "SURPRISED", "speech": "I'm listening!"}),
    (["droop", "slump"], {"gesture": "droop", "mood": "SLEEPY", "speech": "So sleepy..."}),
    (["tilt left", "lean left", "tilt_left"], {"gesture": "tilt_left"}),
    (["tilt right", "lean right", "tilt_right"], {"gesture": "tilt_right"}),
    (["bounce", "hop", "jump"], {"gesture": "bounce", "mood": "STAR_EYES", "speech": "Boing! Boing!"}),
    (["groove", "dance", "boogie"], {"gesture": "groove", "mood": "COOL", "speech": "Grooving to the beat!"}),
    (["shiver", "tremble", "quiver", "cold", "nervous"], {"gesture": "shiver", "mood": "CRYING", "speech": "Brrr... so cold!"}),
    (["scan", "look around", "search", "survey"], {"gesture": "scan", "speech": "Scanning the surroundings..."}),
    (["bow", "respect", "curtsy"], {"gesture": "bow", "speech": "At your service!"}),
    (["cheer", "celebrate", "hooray", "hurray"], {"gesture": "cheer", "mood": "STAR_EYES", "speech": "Hooray! Congratulations!"}),
    (["yawn"], {"gesture": "yawn", "mood": "SLEEPY", "speech": "Yaaawn..."}),
    (["shy", "bashful", "blush"], {"gesture": "shy", "mood": "LOVE", "speech": "Aw, thank you..."}),
    (["peek a boo", "peekaboo", "peek_a_boo", "hide and seek"], {"gesture": "peek_a_boo", "mood": "SURPRISED", "speech": "Peek-a-boo! I see you!"}),
    (["spin", "swirl", "orbit", "dizzy spin", "dizzy_spin"], {"gesture": "dizzy_spin", "mood": "DIZZY", "speech": "Round and round we go!"}),
    (["confused", "puzzled"], {"gesture": "confused", "mood": "THINKING", "speech": "I'm a little confused..."}),
    (["nod", "yes", "agree"], {"gesture": "nod", "mood": "HAPPY", "speech": "Yes, absolutely!"}),
    (["shake", "no", "disagree"], {"gesture": "shake", "speech": "No, I don't think so."}),
    (["wiggle", "shimmy"], {"gesture": "wiggle", "mood": "HAPPY", "speech": "Wiggle wiggle!"}),
]

MOOD_RULES = [
    (["cool", "sunglasses", "shades", "😎"], {"mood": "COOL", "speech": "Stay cool!"}),
    (["star", "excited", "sparkle", "🤩", "✨"], {"mood": "STAR_EYES", "speech": "Amazing!"}),
    (["plead", "puppy", "beg", "please", "🥺"], {"mood": "PLEADING", "speech": "Pretty please?"}),
    (["cry", "sad", "tear", "sob", "😭", "😢"], {"mood": "CRYING", "speech": "Sniff... I am sad."}),
    (["wink", "😉", "flirt"], {"mood": "WINK", "speech": "Wink wink!"}),
    (["tongue", "silly", "playful", "😋", "😜"], {"mood": "TONGUE", "speech": "Blep!"}),
    (["love", "heart", "cute", "kiss", "adore", "😍", "❤️", "🥰"], {"mood": "LOVE", "speech": "I love you!"}),
    (["dizzy", "ko", "😵"], {"mood": "DIZZY", "speech": "Whoa, my head is spinning!"}),
    (["smirk", "sly", "mischief", "😏"], {"mood": "SMIRK", "speech": "Heh, you know it."}),
    (["happy", "smile", "laugh", "pet", "😀", "😊"], {"mood": "HAPPY", "speech": "Hehe, happy to be here!"}),
    (["surprised", "wow", "omg", "shocked", "😮", "😲"], {"mood": "SURPRISED", "speech": "Whoa!"}),
    (["sleep", "tired", "goodnight", "nap", "😴"], {"mood": "SLEEPY", "speech": "Goodnight... Zzz"}),
    (["angry", "mad", "grumpy", "furious", "😡"], {"mood": "ANGRY", "speech": "Hmph!"}),
    (["think", "ponder", "calculate", "why", "🤔"], {"mood": "THINKING", "speech": "Hmm, let me think..."}),
    (["neutral", "calm", "😐"], {"mood": "NEUTRAL"}),
    (["hello", "hi", "hey"], {"mood": "HAPPY", "gesture": "nod", "speech": "Hello! I am Gemma-Bot!"}),
]


def parse_natural_language_intent(prompt):
    """
    Translates natural language instructions into structured Gemma-Bot commands.
    Uses word-boundary matching with multi-word phrases taking precedence over single words.
    """
    p = prompt.lower().strip()
    action = {
        "thought": prompt
    }

    for rules in (GAZE_RULES, SCREEN_COLOR_RULES, GESTURE_RULES):
        matched = _match_first_rule(p, rules)
        if matched:
            action.update(matched)

    if "mood" not in action:
        matched_mood = _match_first_rule(p, MOOD_RULES)
        if matched_mood:
            action.update(matched_mood)

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
