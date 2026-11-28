"""OLED color themes and Emotion-Engine-backed mood/emoji resolution."""

import sys
from pathlib import Path

_CONTROLLER_DIR = str(Path(__file__).resolve().parents[1])
if _CONTROLLER_DIR not in sys.path:
    sys.path.insert(0, _CONTROLLER_DIR)

from emotion_engine.presets import EMOJI_MOOD_MAP, resolve_mood  # noqa: E402

SCREEN_THEMES = {
    "CYAN": {
        "name": "Electric Cyan",
        "bg_color": 0x000000,
        "eye_color": 0x8EC9DB,
        "eye_dim": 0x5A9AAB,
        "mouth_color": 0x8EC9DB,
        "sunglass_frame": 0x8EC9DB,
    },
    "GREEN": {
        "name": "Matrix Emerald",
        "bg_color": 0x000000,
        "eye_color": 0x00FF66,
        "eye_dim": 0x008833,
        "mouth_color": 0x33FF88,
        "sunglass_frame": 0x00FF66,
    },
    "AMBER": {
        "name": "Retro Amber",
        "bg_color": 0x000000,
        "eye_color": 0xFFAA00,
        "eye_dim": 0x996600,
        "mouth_color": 0xFFCC33,
        "sunglass_frame": 0xFFAA00,
    },
    "BLUE": {
        "name": "Neon Blue",
        "bg_color": 0x000000,
        "eye_color": 0x2979FF,
        "eye_dim": 0x1545A5,
        "mouth_color": 0x5393FF,
        "sunglass_frame": 0x2979FF,
    },
    "PURPLE": {
        "name": "Cyberpunk Violet",
        "bg_color": 0x000000,
        "eye_color": 0xD500F9,
        "eye_dim": 0x7A008F,
        "mouth_color": 0xE040FB,
        "sunglass_frame": 0xD500F9,
    },
    "WHITE": {
        "name": "High Contrast White",
        "bg_color": 0x000000,
        "eye_color": 0xFFFFFF,
        "eye_dim": 0x777777,
        "mouth_color": 0xCCCCCC,
        "sunglass_frame": 0xFFFFFF,
    },
}
THEME_KEYS = list(SCREEN_THEMES.keys())

__all__ = ["EMOJI_MOOD_MAP", "SCREEN_THEMES", "THEME_KEYS", "resolve_mood"]
