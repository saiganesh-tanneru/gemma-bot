"""OLED color themes and mood/emoji resolution."""

SCREEN_THEMES = {
    "CYAN": {
        "name": "Electric Cyan",
        "bg_color": 0x000000,
        "eye_color": 0x00F0FF,
        "eye_dim": 0x007799,
        "mouth_color": 0x00D0FF,
        "sunglass_frame": 0x00F0FF,
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

EMOJI_MOOD_MAP = {
    # Happy / Smile
    "😀": "HAPPY", "😃": "HAPPY", "😄": "HAPPY", "😁": "HAPPY", "😊": "HAPPY", "🙂": "HAPPY",
    "HAPPY": "HAPPY", "SMILE": "HAPPY", "GRIN": "HAPPY",
    # Love / Heart
    "😍": "LOVE", "🥰": "LOVE", "😘": "LOVE", "❤️": "LOVE", "💕": "LOVE", "LOVE": "LOVE", "HEART": "LOVE",
    # Wink
    "😉": "WINK", "WINK": "WINK",
    # Cool / Sunglasses
    "😎": "COOL", "COOL": "COOL", "SUNGLASSES": "COOL",
    # Pleading / Cute
    "🥺": "PLEADING", "PLEADING": "PLEADING", "CUTE": "PLEADING", "PUPPY": "PLEADING",
    # Crying / Sad
    "😭": "CRYING", "😢": "CRYING", "😞": "CRYING", "SAD": "CRYING", "CRY": "CRYING", "CRYING": "CRYING",
    # Surprised / Shock
    "😮": "SURPRISED", "😲": "SURPRISED", "😱": "SURPRISED",
    "SURPRISED": "SURPRISED", "WOW": "SURPRISED", "SHOCK": "SURPRISED",
    # Sleepy / Tired
    "😴": "SLEEPY", "🥱": "SLEEPY", "💤": "SLEEPY", "SLEEPY": "SLEEPY", "TIRED": "SLEEPY", "SLEEP": "SLEEPY",
    # Angry / Mad
    "😡": "ANGRY", "😠": "ANGRY", "🤬": "ANGRY", "ANGRY": "ANGRY", "MAD": "ANGRY",
    # Thinking / Ponder (consistent with GESTURE_DEFAULT_MOOD["confused"] = "THINKING")
    "🤔": "THINKING", "🧐": "THINKING", "THINKING": "THINKING", "PONDER": "THINKING", "CONFUSED": "THINKING",
    # Dizzy / KO
    "😵": "DIZZY", "😵‍💫": "DIZZY", "DIZZY": "DIZZY", "KO": "DIZZY",
    # Star Eyes / Excited
    "🤩": "STAR_EYES", "✨": "STAR_EYES", "STAR_EYES": "STAR_EYES", "EXCITED": "STAR_EYES", "STAR": "STAR_EYES",
    # Tongue / Playful
    "😋": "TONGUE", "😛": "TONGUE", "😝": "TONGUE", "😜": "TONGUE", "TONGUE": "TONGUE", "PLAYFUL": "TONGUE",
    # Smirk
    "😏": "SMIRK", "SMIRK": "SMIRK", "SLY": "SMIRK",
    # Neutral
    "😐": "NEUTRAL", "😑": "NEUTRAL", "NEUTRAL": "NEUTRAL",
}


def resolve_mood(val) -> str:
    """Normalizes any string, keyword, or unicode emoji into a canonical mood."""
    if not val:
        return "NEUTRAL"
    s = str(val).strip()
    if s in EMOJI_MOOD_MAP:
        return EMOJI_MOOD_MAP[s]
    upper = s.upper()
    if upper in EMOJI_MOOD_MAP:
        return EMOJI_MOOD_MAP[upper]
    for char, mood in EMOJI_MOOD_MAP.items():
        if char in s:
            return mood
    return "NEUTRAL"
