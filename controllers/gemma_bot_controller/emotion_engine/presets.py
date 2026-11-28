"""Emotion Engine presets, parametric eye geometry, chirp specs, and mood registry.

MIT-licensed clean-room parametric eye model inspired by procedural OLED eye engines
(12-parameter eye geometry + weighted emotion state specs), designed to run identically
across Webots (128x64 / 410x502), headless Python tests, and future ESP32-S3 ports.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple


@dataclass(frozen=True)
class EyeConfig:
    """12-parameter eye geometry in a 128x64 reference coordinate frame."""

    offset_x: float = 0.0
    offset_y: float = 0.0
    width: float = 28.0
    height: float = 34.0
    slope_top: float = 0.0
    slope_bottom: float = 0.0
    radius_top: float = 6.0
    radius_bottom: float = 6.0
    inverse_radius_top: float = 0.0
    inverse_radius_bottom: float = 0.0
    inverse_offset_top: float = 0.0
    inverse_offset_bottom: float = 0.0

    def lerp(self, other: "EyeConfig", t: float) -> "EyeConfig":
        """Linearly interpolates each eye geometry parameter by t in [0, 1]."""
        u = max(0.0, min(1.0, float(t)))
        inv = 1.0 - u
        return EyeConfig(
            offset_x=self.offset_x * inv + other.offset_x * u,
            offset_y=self.offset_y * inv + other.offset_y * u,
            width=self.width * inv + other.width * u,
            height=self.height * inv + other.height * u,
            slope_top=self.slope_top * inv + other.slope_top * u,
            slope_bottom=self.slope_bottom * inv + other.slope_bottom * u,
            radius_top=self.radius_top * inv + other.radius_top * u,
            radius_bottom=self.radius_bottom * inv + other.radius_bottom * u,
            inverse_radius_top=self.inverse_radius_top * inv + other.inverse_radius_top * u,
            inverse_radius_bottom=self.inverse_radius_bottom * inv + other.inverse_radius_bottom * u,
            inverse_offset_top=self.inverse_offset_top * inv + other.inverse_offset_top * u,
            inverse_offset_bottom=self.inverse_offset_bottom * inv + other.inverse_offset_bottom * u,
        )

    def scaled(self, disp_w: int, disp_h: int) -> "EyeConfig":
        """Scales reference 128x64 eye parameters onto any target display resolution."""
        sx = disp_w / 128.0
        sy = disp_h / 64.0
        sr = min(sx, sy)
        return EyeConfig(
            offset_x=self.offset_x * sx,
            offset_y=self.offset_y * sy,
            width=self.width * sx,
            height=self.height * sy,
            slope_top=self.slope_top,
            slope_bottom=self.slope_bottom,
            radius_top=self.radius_top * sr,
            radius_bottom=self.radius_bottom * sr,
            inverse_radius_top=self.inverse_radius_top * sr,
            inverse_radius_bottom=self.inverse_radius_bottom * sr,
            inverse_offset_top=self.inverse_offset_top * sy,
            inverse_offset_bottom=self.inverse_offset_bottom * sy,
        )


@dataclass(frozen=True)
class ChirpSpec:
    """Declarative synthesized chirp profile for desktop PCM or ESP32-S3 I2S/buzzer."""

    pattern: str  # "sweep" | "arpeggio" | "sigh" | "trill" | "chime"
    freqs_hz: Tuple[int, ...]
    duration_ms: int = 240
    waveform: str = "sine"
    volume: float = 0.35


@dataclass(frozen=True)
class EmotionSpec:
    """Unified declarative definition pairing eyes, posture/idle motion, and chirp."""

    name: str
    eye_left: EyeConfig
    eye_right: Optional[EyeConfig] = None
    default_gesture: Optional[str] = None
    chirp: Optional[ChirpSpec] = None
    idle_behavior: str = "still"  # "roam" | "sway" | "droop" | "bob" | "tremble" | "scan" | "still"
    idle_yaw_amp: float = 0.0
    idle_yaw_freq: float = 0.0
    idle_pitch: Optional[float] = None
    idle_gaze_x: Optional[float] = None
    idle_gaze_y: Optional[float] = None
    is_classic_oled: bool = False
    aliases: Tuple[str, ...] = ()
    emojis: Tuple[str, ...] = ()

    @property
    def right_eye(self) -> EyeConfig:
        return self.eye_right if self.eye_right is not None else self.eye_left


# ---------------------------------------------------------------------------
# Parametric eye geometry building blocks
# ---------------------------------------------------------------------------

_EYE_NEUTRAL = EyeConfig(width=22, height=26, radius_top=8, radius_bottom=8)
_EYE_HAPPY = EyeConfig(offset_y=-2, width=26, height=11, radius_top=9, radius_bottom=2, inverse_radius_bottom=4)
_EYE_GLEE = EyeConfig(offset_y=-3, width=28, height=9, radius_top=8, radius_bottom=0, inverse_radius_bottom=6)
_EYE_SLEEPY = EyeConfig(offset_y=4, width=28, height=6, radius_top=2, radius_bottom=2)
_EYE_ANGRY_L = EyeConfig(width=28, height=26, slope_top=0.45, radius_top=2, radius_bottom=6)
_EYE_ANGRY_R = EyeConfig(width=28, height=26, slope_top=-0.45, radius_top=2, radius_bottom=6)
_EYE_FURIOUS_L = EyeConfig(width=28, height=18, slope_top=0.65, radius_top=1, radius_bottom=4)
_EYE_FURIOUS_R = EyeConfig(width=28, height=18, slope_top=-0.65, radius_top=1, radius_bottom=4)
_EYE_SAD_L = EyeConfig(offset_y=3, width=28, height=18, slope_top=-0.45, radius_top=2, radius_bottom=8)
_EYE_SAD_R = EyeConfig(offset_y=3, width=28, height=18, slope_top=0.45, radius_top=2, radius_bottom=8)
_EYE_WORRIED_L = EyeConfig(offset_y=1, width=26, height=22, slope_top=-0.22, radius_top=6, radius_bottom=7)
_EYE_WORRIED_R = EyeConfig(offset_y=1, width=26, height=22, slope_top=0.22, radius_top=6, radius_bottom=7)
_EYE_SURPRISED = EyeConfig(offset_y=-2, width=32, height=40, radius_top=10, radius_bottom=10)
_EYE_AWE = EyeConfig(offset_y=-2, width=30, height=38, radius_top=12, radius_bottom=12)
_EYE_SCARED = EyeConfig(offset_y=-1, width=30, height=36, slope_top=-0.15, radius_top=9, radius_bottom=9)
_EYE_FOCUSED = EyeConfig(width=28, height=18, radius_top=4, radius_bottom=4)
_EYE_SQUINT = EyeConfig(width=28, height=14, radius_top=3, radius_bottom=3)
_EYE_ANNOYED = EyeConfig(offset_y=1, width=28, height=16, slope_top=0.12, radius_top=2, radius_bottom=5)
_EYE_UNIMPRESSED = EyeConfig(offset_y=2, width=28, height=11, radius_top=1, radius_bottom=5)
_EYE_FRUSTRATED_L = EyeConfig(offset_y=2, width=28, height=14, slope_top=0.32, radius_top=1, radius_bottom=6)
_EYE_FRUSTRATED_R = EyeConfig(offset_y=2, width=28, height=14, slope_top=-0.32, radius_top=1, radius_bottom=6)
_EYE_SKEPTIC_L = EyeConfig(offset_y=-3, width=26, height=28, slope_top=-0.12, radius_top=7, radius_bottom=7)
_EYE_SKEPTIC_R = EyeConfig(offset_y=3, width=26, height=14, slope_top=0.15, radius_top=3, radius_bottom=5)
_EYE_SUSPICIOUS_L = EyeConfig(offset_x=2, width=26, height=14, slope_top=0.20, radius_top=2, radius_bottom=5)
_EYE_SUSPICIOUS_R = EyeConfig(offset_x=2, width=26, height=18, slope_top=-0.10, radius_top=3, radius_bottom=5)
_EYE_THINKING = EyeConfig(offset_x=4, offset_y=-6, width=26, height=32, radius_top=5, radius_bottom=5)
_EYE_PLEADING = EyeConfig(width=30, height=36, radius_top=8, radius_bottom=8)


EMOTIONS: Dict[str, EmotionSpec] = {
    # -----------------------------------------------------------------------
    # 15 Canonical Gemma-Bot Moods (keep classic pixel-exact OLED option)
    # -----------------------------------------------------------------------
    "NEUTRAL": EmotionSpec(
        name="NEUTRAL",
        eye_left=_EYE_NEUTRAL,
        chirp=None,
        idle_behavior="roam",
        is_classic_oled=True,
        aliases=("NEUTRAL", "CALM"),
        emojis=("😐", "😑"),
    ),
    "HAPPY": EmotionSpec(
        name="HAPPY",
        eye_left=_EYE_HAPPY,
        default_gesture="wiggle",
        chirp=ChirpSpec("arpeggio", (520, 680, 880), duration_ms=220),
        idle_behavior="sway",
        idle_yaw_amp=0.15,
        idle_yaw_freq=0.2,
        idle_pitch=-0.12,
        is_classic_oled=True,
        aliases=("HAPPY", "SMILE", "GRIN"),
        emojis=("😀", "😃", "😄", "😁", "😊", "🙂"),
    ),
    "LOVE": EmotionSpec(
        name="LOVE",
        eye_left=_EYE_HAPPY,
        default_gesture="shy",
        chirp=ChirpSpec("chime", (587, 740, 880), duration_ms=280),
        idle_behavior="sway",
        idle_yaw_amp=0.10,
        idle_yaw_freq=0.15,
        idle_pitch=-0.08,
        is_classic_oled=True,
        aliases=("LOVE", "HEART"),
        emojis=("😍", "🥰", "😘", "❤️", "💕"),
    ),
    "WINK": EmotionSpec(
        name="WINK",
        eye_left=_EYE_NEUTRAL,
        eye_right=_EYE_HAPPY,
        default_gesture="tilt_left",
        chirp=ChirpSpec("sweep", (620, 920), duration_ms=140),
        is_classic_oled=True,
        aliases=("WINK",),
        emojis=("😉",),
    ),
    "COOL": EmotionSpec(
        name="COOL",
        eye_left=_EYE_FOCUSED,
        default_gesture="groove",
        chirp=ChirpSpec("arpeggio", (440, 554, 659), duration_ms=240),
        idle_behavior="sway",
        idle_yaw_amp=0.08,
        idle_yaw_freq=0.14,
        idle_pitch=-0.06,
        is_classic_oled=True,
        aliases=("COOL", "SUNGLASSES"),
        emojis=("😎",),
    ),
    "STAR_EYES": EmotionSpec(
        name="STAR_EYES",
        eye_left=_EYE_AWE,
        default_gesture="cheer",
        chirp=ChirpSpec("arpeggio", (520, 780, 1040, 1318), duration_ms=300),
        idle_behavior="bob",
        idle_yaw_amp=0.12,
        idle_yaw_freq=0.24,
        idle_pitch=-0.14,
        is_classic_oled=True,
        aliases=("STAR_EYES", "EXCITED", "STAR"),
        emojis=("🤩", "✨"),
    ),
    "PLEADING": EmotionSpec(
        name="PLEADING",
        eye_left=_EYE_PLEADING,
        default_gesture="shy",
        chirp=ChirpSpec("sweep", (440, 580, 510), duration_ms=280),
        idle_behavior="droop",
        idle_pitch=0.12,
        idle_gaze_y=0.25,
        is_classic_oled=True,
        aliases=("PLEADING", "CUTE", "PUPPY"),
        emojis=("🥺",),
    ),
    "CRYING": EmotionSpec(
        name="CRYING",
        eye_left=_EYE_SAD_L,
        eye_right=_EYE_SAD_R,
        default_gesture="droop",
        chirp=ChirpSpec("sigh", (420, 220), duration_ms=360),
        idle_behavior="droop",
        idle_pitch=0.24,
        idle_gaze_y=0.4,
        is_classic_oled=True,
        aliases=("CRYING", "SAD", "CRY"),
        emojis=("😭", "😢", "😞"),
    ),
    "TONGUE": EmotionSpec(
        name="TONGUE",
        eye_left=_EYE_HAPPY,
        default_gesture="wiggle",
        chirp=ChirpSpec("trill", (600, 750, 600, 820), duration_ms=220),
        is_classic_oled=True,
        aliases=("TONGUE", "PLAYFUL"),
        emojis=("😋", "😛", "😝", "😜"),
    ),
    "SMIRK": EmotionSpec(
        name="SMIRK",
        eye_left=_EYE_NEUTRAL,
        eye_right=_EYE_SLEEPY,
        default_gesture="tilt_right",
        chirp=ChirpSpec("sweep", (380, 510), duration_ms=170),
        is_classic_oled=True,
        aliases=("SMIRK", "SLY"),
        emojis=("😏",),
    ),
    "DIZZY": EmotionSpec(
        name="DIZZY",
        eye_left=_EYE_SCARED,
        default_gesture="dizzy_spin",
        chirp=ChirpSpec("trill", (340, 520, 300, 580), duration_ms=340),
        idle_behavior="sway",
        idle_yaw_amp=0.18,
        idle_yaw_freq=0.35,
        is_classic_oled=True,
        aliases=("DIZZY", "KO"),
        emojis=("😵", "😵‍💫"),
    ),
    "THINKING": EmotionSpec(
        name="THINKING",
        eye_left=_EYE_THINKING,
        default_gesture="curious",
        chirp=ChirpSpec("sweep", (400, 680), duration_ms=200),
        idle_behavior="scan",
        idle_yaw_amp=0.22,
        idle_yaw_freq=0.09,
        idle_pitch=-0.10,
        is_classic_oled=True,
        aliases=("THINKING", "PONDER", "CONFUSED"),
        emojis=("🤔", "🧐"),
    ),
    "SLEEPY": EmotionSpec(
        name="SLEEPY",
        eye_left=_EYE_SLEEPY,
        default_gesture="droop",
        chirp=ChirpSpec("sigh", (380, 190), duration_ms=420),
        idle_behavior="droop",
        idle_pitch=0.32,
        idle_gaze_x=0.0,
        idle_gaze_y=0.5,
        is_classic_oled=True,
        aliases=("SLEEPY", "TIRED", "SLEEP"),
        emojis=("😴", "🥱", "💤"),
    ),
    "SURPRISED": EmotionSpec(
        name="SURPRISED",
        eye_left=_EYE_SURPRISED,
        default_gesture="perk_up",
        chirp=ChirpSpec("sweep", (320, 860), duration_ms=190),
        idle_behavior="bob",
        idle_yaw_amp=0.05,
        idle_yaw_freq=0.18,
        idle_pitch=-0.15,
        is_classic_oled=True,
        aliases=("SURPRISED", "WOW", "SHOCK"),
        emojis=("😮", "😲", "😱"),
    ),
    "ANGRY": EmotionSpec(
        name="ANGRY",
        eye_left=_EYE_ANGRY_L,
        eye_right=_EYE_ANGRY_R,
        default_gesture="shake",
        chirp=ChirpSpec("trill", (220, 180, 210), duration_ms=240, waveform="square"),
        idle_behavior="tremble",
        idle_yaw_amp=0.06,
        idle_yaw_freq=0.45,
        idle_pitch=0.08,
        is_classic_oled=True,
        aliases=("ANGRY", "MAD"),
        emojis=("😡", "😠", "🤬"),
    ),
    # -----------------------------------------------------------------------
    # Extended Emotion Engine States (esp32-eyes / Cozmo-inspired parametric)
    # -----------------------------------------------------------------------
    "GLEE": EmotionSpec(
        name="GLEE",
        eye_left=_EYE_GLEE,
        default_gesture="cheer",
        chirp=ChirpSpec("arpeggio", (660, 880, 1100), duration_ms=230),
        idle_behavior="sway",
        idle_yaw_amp=0.16,
        idle_yaw_freq=0.28,
        idle_pitch=-0.12,
        aliases=("GLEE", "JOYFUL"),
    ),
    "WORRIED": EmotionSpec(
        name="WORRIED",
        eye_left=_EYE_WORRIED_L,
        eye_right=_EYE_WORRIED_R,
        default_gesture="shiver",
        chirp=ChirpSpec("sweep", (480, 390), duration_ms=260),
        idle_behavior="droop",
        idle_pitch=0.10,
        idle_gaze_y=0.2,
        aliases=("WORRIED", "CONCERNED"),
        emojis=("😟", "😨"),
    ),
    "FOCUSED": EmotionSpec(
        name="FOCUSED",
        eye_left=_EYE_FOCUSED,
        default_gesture="perk_up",
        chirp=ChirpSpec("chime", (520, 620), duration_ms=140),
        idle_behavior="still",
        idle_pitch=-0.06,
        aliases=("FOCUSED", "ATTENTIVE"),
    ),
    "ANNOYED": EmotionSpec(
        name="ANNOYED",
        eye_left=_EYE_ANNOYED,
        default_gesture="shake",
        chirp=ChirpSpec("sweep", (280, 210), duration_ms=180),
        idle_behavior="droop",
        idle_pitch=0.05,
        aliases=("ANNOYED", "GRUMPY"),
        emojis=("😒",),
    ),
    "SKEPTIC": EmotionSpec(
        name="SKEPTIC",
        eye_left=_EYE_SKEPTIC_L,
        eye_right=_EYE_SKEPTIC_R,
        default_gesture="curious",
        chirp=ChirpSpec("sweep", (390, 560), duration_ms=210),
        idle_behavior="scan",
        idle_yaw_amp=0.25,
        idle_yaw_freq=0.08,
        idle_pitch=-0.08,
        aliases=("SKEPTIC", "DOUBTFUL"),
        emojis=("🤨",),
    ),
    "FRUSTRATED": EmotionSpec(
        name="FRUSTRATED",
        eye_left=_EYE_FRUSTRATED_L,
        eye_right=_EYE_FRUSTRATED_R,
        default_gesture="shake",
        chirp=ChirpSpec("sigh", (340, 180), duration_ms=300),
        idle_behavior="tremble",
        idle_yaw_amp=0.08,
        idle_yaw_freq=0.30,
        idle_pitch=0.14,
        aliases=("FRUSTRATED",),
        emojis=("😤",),
    ),
    "UNIMPRESSED": EmotionSpec(
        name="UNIMPRESSED",
        eye_left=_EYE_UNIMPRESSED,
        default_gesture="tilt_right",
        chirp=ChirpSpec("sigh", (300, 230), duration_ms=220),
        idle_behavior="droop",
        idle_pitch=0.08,
        aliases=("UNIMPRESSED", "MEH"),
        emojis=("😑",),
    ),
    "SUSPICIOUS": EmotionSpec(
        name="SUSPICIOUS",
        eye_left=_EYE_SUSPICIOUS_L,
        eye_right=_EYE_SUSPICIOUS_R,
        default_gesture="scan",
        chirp=ChirpSpec("sweep", (350, 430), duration_ms=220),
        idle_behavior="scan",
        idle_yaw_amp=0.30,
        idle_yaw_freq=0.10,
        aliases=("SUSPICIOUS",),
    ),
    "SQUINT": EmotionSpec(
        name="SQUINT",
        eye_left=_EYE_SQUINT,
        default_gesture="curious",
        chirp=ChirpSpec("sweep", (440, 520), duration_ms=150),
        idle_behavior="still",
        aliases=("SQUINT",),
    ),
    "FURIOUS": EmotionSpec(
        name="FURIOUS",
        eye_left=_EYE_FURIOUS_L,
        eye_right=_EYE_FURIOUS_R,
        default_gesture="shake",
        chirp=ChirpSpec("trill", (260, 170, 250, 160), duration_ms=280, waveform="square"),
        idle_behavior="tremble",
        idle_yaw_amp=0.10,
        idle_yaw_freq=0.55,
        idle_pitch=0.10,
        aliases=("FURIOUS",),
    ),
    "SCARED": EmotionSpec(
        name="SCARED",
        eye_left=_EYE_SCARED,
        default_gesture="shiver",
        chirp=ChirpSpec("trill", (720, 880, 740, 920), duration_ms=260),
        idle_behavior="tremble",
        idle_yaw_amp=0.09,
        idle_yaw_freq=0.50,
        idle_pitch=-0.10,
        aliases=("SCARED", "AFRAID"),
        emojis=("😨", "😰"),
    ),
    "AWE": EmotionSpec(
        name="AWE",
        eye_left=_EYE_AWE,
        default_gesture="perk_up",
        chirp=ChirpSpec("chime", (440, 659, 880, 1175), duration_ms=340),
        idle_behavior="bob",
        idle_yaw_amp=0.06,
        idle_yaw_freq=0.15,
        idle_pitch=-0.18,
        aliases=("AWE", "AMAZED"),
    ),
    "BORED": EmotionSpec(
        name="BORED",
        eye_left=_EYE_UNIMPRESSED,
        default_gesture="yawn",
        chirp=ChirpSpec("sigh", (420, 210), duration_ms=380),
        idle_behavior="droop",
        idle_pitch=0.18,
        idle_gaze_x=-0.35,
        idle_gaze_y=0.35,
        aliases=("BORED", "BOREDOM"),
    ),
    "SULKING": EmotionSpec(
        name="SULKING",
        eye_left=_EYE_FRUSTRATED_L,
        eye_right=_EYE_FRUSTRATED_R,
        default_gesture="shy",
        chirp=ChirpSpec("sigh", (280, 170), duration_ms=320),
        idle_behavior="droop",
        idle_pitch=0.22,
        idle_gaze_x=-0.6,
        idle_gaze_y=0.3,
        aliases=("SULKING", "SULK", "POUT"),
    ),
}

CLASSIC_MOODS: FrozenSet[str] = frozenset(
    name for name, spec in EMOTIONS.items() if spec.is_classic_oled
)
EXTENDED_MOODS: FrozenSet[str] = frozenset(
    name for name, spec in EMOTIONS.items() if not spec.is_classic_oled
)
ALL_MOODS: FrozenSet[str] = frozenset(EMOTIONS.keys())


def _build_emoji_mood_map() -> Dict[str, str]:
    """Builds canonical emoji/keyword -> mood map from EMOTIONS, classic moods taking precedence."""
    mapping: Dict[str, str] = {}
    ordered = sorted(EMOTIONS.values(), key=lambda s: (not s.is_classic_oled, s.name))
    for spec in ordered:
        for token in (*spec.emojis, *spec.aliases, spec.name):
            mapping.setdefault(token, spec.name)
    return mapping


EMOJI_MOOD_MAP: Dict[str, str] = _build_emoji_mood_map()


def resolve_mood(val) -> str:
    """Normalizes any string, keyword, or unicode emoji into a canonical mood/emotion."""
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


# Declarative conversational state responses (replaces hardcoded state branches in controller)
CONVERSATION_STATE_PRESETS: Dict[str, Dict[str, object]] = {
    "LISTENING": {
        "mood": None,
        "gaze_x": 0.0,
        "gaze_y": 0.0,
        "target_yaw": 0.0,
        "target_pitch": -0.05,
        "gesture": None,
        "interrupt": False,
    },
    "THINKING": {
        "mood": "THINKING",
        "gaze_x": 0.5,
        "gaze_y": -0.6,
        "target_yaw": 0.2,
        "target_pitch": -0.15,
        "gesture": None,
        "interrupt": False,
    },
    "SPEAKING": {
        "mood": "HAPPY",
        "gaze_x": None,
        "gaze_y": None,
        "target_yaw": None,
        "target_pitch": None,
        "gesture": "nod",
        "interrupt": False,
    },
    "INTERRUPTED": {
        "mood": "SURPRISED",
        "gaze_x": None,
        "gaze_y": None,
        "target_yaw": None,
        "target_pitch": None,
        "gesture": None,
        "interrupt": True,
    },
    "CANCELLED": {
        "mood": "SURPRISED",
        "gaze_x": None,
        "gaze_y": None,
        "target_yaw": None,
        "target_pitch": None,
        "gesture": None,
        "interrupt": True,
    },
}
