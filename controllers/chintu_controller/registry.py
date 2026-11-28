"""Chintu mood and gesture registry.

Strictly locked to the 15 canonical moods and 19 canonical gestures.
Never invent a mood or gesture outside these sets.
"""

from typing import FrozenSet, Optional, Tuple

CHINTU_MOODS: Tuple[str, ...] = (
    "NEUTRAL",
    "HAPPY",
    "COOL",
    "STAR_EYES",
    "PLEADING",
    "CRYING",
    "WINK",
    "TONGUE",
    "LOVE",
    "DIZZY",
    "SMIRK",
    "SURPRISED",
    "SLEEPY",
    "ANGRY",
    "THINKING",
)

CHINTU_GESTURES: Tuple[str, ...] = (
    "nod",
    "shake",
    "wiggle",
    "curious",
    "tilt_left",
    "tilt_right",
    "perk_up",
    "droop",
    "bounce",
    "groove",
    "shiver",
    "scan",
    "confused",
    "bow",
    "cheer",
    "yawn",
    "shy",
    "peek_a_boo",
    "dizzy_spin",
)

MOOD_SET: FrozenSet[str] = frozenset(CHINTU_MOODS)
GESTURE_SET: FrozenSet[str] = frozenset(CHINTU_GESTURES)


def validate_mood(mood: str) -> str:
    """Validates and returns a canonical Chintu mood name."""
    norm = str(mood).upper().strip()
    if norm not in MOOD_SET:
        raise ValueError(f"Unknown Chintu mood {mood!r}; allowed: {CHINTU_MOODS}")
    return norm


def validate_gesture(gesture: str) -> str:
    """Validates and returns a canonical Chintu gesture name."""
    norm = str(gesture).lower().strip()
    if norm not in GESTURE_SET:
        raise ValueError(f"Unknown Chintu gesture {gesture!r}; allowed: {CHINTU_GESTURES}")
    return norm


def format_bot_tag(mood: Optional[str] = None, gesture: Optional[str] = None) -> str:
    """Formats a validated [BOT: ...] tag matching the voice pipeline contract."""
    parts = []
    if mood is not None:
        parts.append(f"mood={validate_mood(mood)}")
    if gesture is not None:
        parts.append(f"gesture={validate_gesture(gesture)}")
    if not parts:
        raise ValueError("format_bot_tag requires at least mood or gesture")
    return f"[BOT: {', '.join(parts)}]"
