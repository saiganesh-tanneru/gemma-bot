"""Reusable Emotion Engine package for Gemma-Bot / Chintu."""

from emotion_engine.chirp import (
    ChirpPlayer,
    MacAfplayChirpPlayer,
    NullChirpPlayer,
    create_chirp_player,
    synthesize_chirp_wav,
)
from emotion_engine.engine import (
    BlinkController,
    EmotionEngine,
    EmotionReaction,
    EmotionState,
)
from emotion_engine.presets import (
    ALL_MOODS,
    CLASSIC_MOODS,
    CONVERSATION_STATE_PRESETS,
    EMOJI_MOOD_MAP,
    EMOTIONS,
    EXTENDED_MOODS,
    ChirpSpec,
    EmotionSpec,
    EyeConfig,
    resolve_mood,
)

__all__ = [
    "ALL_MOODS",
    "CLASSIC_MOODS",
    "CONVERSATION_STATE_PRESETS",
    "EMOJI_MOOD_MAP",
    "EMOTIONS",
    "EXTENDED_MOODS",
    "BlinkController",
    "ChirpPlayer",
    "ChirpSpec",
    "EmotionEngine",
    "EmotionReaction",
    "EmotionSpec",
    "EmotionState",
    "EyeConfig",
    "MacAfplayChirpPlayer",
    "NullChirpPlayer",
    "create_chirp_player",
    "resolve_mood",
    "synthesize_chirp_wav",
]
