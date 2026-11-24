"""
Structured-output intent parser (English, Telugu, Tanglish) with strict schema
validation, action allowlist, non-blocking async wrapper, and Phase 1 keyword fallback.
"""

from abc import ABC, abstractmethod
import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional
import urllib.request

import config

logger = logging.getLogger("gemma_intent_parser")

ALLOWED_ACTIONS = frozenset({"express", "move", "speak", "theme", "interrupt", "none"})
ALLOWED_MOODS = frozenset({
    "NEUTRAL", "HAPPY", "LOVE", "WINK", "COOL", "STAR_EYES",
    "PLEADING", "CRYING", "TONGUE", "SMIRK", "DIZZY", "THINKING",
    "SLEEPY", "SURPRISED", "ANGRY",
})
ALLOWED_GESTURES = frozenset({
    "nod", "shake", "wiggle", "curious", "tilt_left", "tilt_right",
    "perk_up", "droop", "bounce", "groove", "shiver", "scan",
    "confused", "bow", "cheer", "yawn", "shy", "peek_a_boo", "dizzy_spin",
})
ALLOWED_SCREENS = frozenset({"CYAN", "GREEN", "AMBER", "BLUE", "PURPLE", "WHITE"})
ALLOWED_GAZES = frozenset({"left", "right", "up", "down", "center"})
ALLOWED_KEYS = frozenset({"action", "gesture", "mood", "screen", "gaze", "speech"})

# ---------------------------------------------------------------------------
# Phase 1 word-boundary keyword parser (used as deterministic fallback)
# ---------------------------------------------------------------------------

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


def parse_keyword_intent(prompt: str) -> Dict[str, Any]:
    """Word-boundary keyword parser with multi-word phrase precedence."""
    p = prompt.lower().strip()
    action: Dict[str, Any] = {"thought": prompt}

    for rules in (GAZE_RULES, SCREEN_COLOR_RULES, GESTURE_RULES):
        matched = _match_first_rule(p, rules)
        if matched:
            action.update(matched)

    if "mood" not in action:
        matched_mood = _match_first_rule(p, MOOD_RULES)
        if matched_mood:
            action.update(matched_mood)

    return action


# ---------------------------------------------------------------------------
# Structured LLM output validation & provider interface
# ---------------------------------------------------------------------------

def validate_intent_json(raw_text: str) -> Dict[str, Any]:
    """Parses and strictly validates LLM structured output against allowlists."""
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("Intent output must be a JSON object")

    unknown = set(data.keys()) - ALLOWED_KEYS
    if unknown:
        raise ValueError(f"Disallowed keys in intent output: {sorted(unknown)}")

    action = data.get("action")
    if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
        raise ValueError(f"Disallowed or missing action: {action!r}")

    out: Dict[str, Any] = {"action": action}

    if "gesture" in data and data["gesture"] is not None:
        g = str(data["gesture"]).lower().strip()
        if g not in ALLOWED_GESTURES:
            raise ValueError(f"Disallowed gesture: {g!r}")
        out["gesture"] = g

    if "mood" in data and data["mood"] is not None:
        m = str(data["mood"]).upper().strip()
        if m not in ALLOWED_MOODS:
            raise ValueError(f"Disallowed mood: {m!r}")
        out["mood"] = m

    if "screen" in data and data["screen"] is not None:
        s = str(data["screen"]).upper().strip()
        if s not in ALLOWED_SCREENS:
            raise ValueError(f"Disallowed screen color: {s!r}")
        out["screen"] = s
        out["screen_color"] = s

    if "gaze" in data and data["gaze"] is not None:
        gz = str(data["gaze"]).lower().strip()
        if gz not in ALLOWED_GAZES:
            raise ValueError(f"Disallowed gaze: {gz!r}")
        out["gaze"] = gz

    if "speech" in data and data["speech"] is not None:
        if not isinstance(data["speech"], str):
            raise ValueError("Field 'speech' must be a string")
        sp = data["speech"].strip()[:500]
        if sp:
            out["speech"] = sp

    if action == "interrupt":
        out["interrupt"] = True

    return out


class IntentProvider(ABC):
    """Swappable LLM provider interface for natural-language -> JSON intent parsing."""

    @abstractmethod
    def parse_raw(self, text: str, timeout: float) -> str:
        """Returns raw JSON string from the model for the given user text."""


class SarvamIntentProvider(IntentProvider):
    """Sarvam AI Chat Completions structured-output intent provider."""

    SYSTEM_PROMPT = (
        "You translate English, Telugu, or Tanglish user requests for a desktop companion robot "
        "(Gemma-Bot) into a single JSON object. "
        "Allowed action: express, move, speak, theme, interrupt, none. "
        "Allowed moods: NEUTRAL, HAPPY, LOVE, WINK, COOL, STAR_EYES, PLEADING, CRYING, "
        "TONGUE, SMIRK, DIZZY, THINKING, SLEEPY, SURPRISED, ANGRY. "
        "Allowed gestures: nod, shake, wiggle, curious, tilt_left, tilt_right, perk_up, "
        "droop, bounce, groove, shiver, scan, confused, bow, cheer, yawn, shy, peek_a_boo, dizzy_spin. "
        "Allowed screen: CYAN, GREEN, AMBER, BLUE, PURPLE, WHITE. "
        "Allowed gaze: left, right, up, down, center. "
        "Reply ONLY with JSON."
    )

    RESPONSE_FORMAT = {
        "type": "json_schema",
        "json_schema": {
            "name": "gemma_bot_intent",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": sorted(ALLOWED_ACTIONS)},
                    "gesture": {"type": ["string", "null"], "enum": sorted(ALLOWED_GESTURES) + [None]},
                    "mood": {"type": ["string", "null"], "enum": sorted(ALLOWED_MOODS) + [None]},
                    "screen": {"type": ["string", "null"], "enum": sorted(ALLOWED_SCREENS) + [None]},
                    "gaze": {"type": ["string", "null"], "enum": sorted(ALLOWED_GAZES) + [None]},
                    "speech": {"type": ["string", "null"]},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: str = config.SARVAM_CHAT_URL,
        model: str = config.SARVAM_LLM_MODEL,
    ):
        self.api_key = config.SARVAM_API_KEY if api_key is None else api_key
        self.endpoint = endpoint
        self.model = model

    def parse_raw(self, text: str, timeout: float) -> str:
        if not self.api_key:
            raise RuntimeError("SARVAM_API_KEY is not configured")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "response_format": self.RESPONSE_FORMAT,
            "temperature": 0.1,
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "api-subscription-key": self.api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


class IntentParser:
    """Runs an IntentProvider with strict validation and deterministic keyword fallback."""

    def __init__(
        self,
        provider: Optional[IntentProvider] = None,
        timeout: float = config.INTENT_TIMEOUT_SECONDS,
    ):
        self.provider = provider
        self.timeout = timeout

    def parse(self, text: str) -> Dict[str, Any]:
        if self.provider is not None:
            try:
                raw = self.provider.parse_raw(text, timeout=self.timeout)
                validated = validate_intent_json(raw)
                validated["thought"] = text
                return validated
            except Exception as exc:
                logger.warning("LLM intent parser failed (%s); falling back to keyword parser", exc)
        return parse_keyword_intent(text)

    async def parse_async(self, text: str) -> Dict[str, Any]:
        """Executes intent parsing off the asyncio event loop."""
        return await asyncio.to_thread(self.parse, text)


def create_intent_parser(provider_name: Optional[str] = None) -> IntentParser:
    """Creates an IntentParser from configuration."""
    name = (provider_name or config.INTENT_PROVIDER).lower().strip()
    if name == "sarvam" and config.SARVAM_API_KEY:
        return IntentParser(provider=SarvamIntentProvider(), timeout=config.INTENT_TIMEOUT_SECONDS)
    return IntentParser(provider=None, timeout=config.INTENT_TIMEOUT_SECONDS)
