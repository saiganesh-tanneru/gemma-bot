"""Single-registry phase-based gesture engine (p = t / total in [0, 1])."""

import math
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple


@dataclass(frozen=True)
class GesturePose:
    """Target head/gaze/blink pose returned by a gesture trajectory at phase p."""

    yaw: Optional[float] = None
    pitch: Optional[float] = None
    gaze_x: Optional[float] = None
    gaze_y: Optional[float] = None
    blink_progress: Optional[float] = None


@dataclass(frozen=True)
class Gesture:
    """Declarative gesture definition with duration (frames) and phase trajectory fn(p)."""

    frames: int
    trajectory: Callable[[float], GesturePose]
    default_mood: Optional[str] = None
    aliases: Tuple[str, ...] = ()


def _nod(p: float) -> GesturePose:
    return GesturePose(pitch=math.sin(p * 15.0) * 0.25, yaw=0.0)


def _shake(p: float) -> GesturePose:
    return GesturePose(yaw=math.sin(p * 17.5) * 0.35, pitch=0.0)


def _wiggle(p: float) -> GesturePose:
    return GesturePose(
        yaw=math.sin(p * 24.0) * 0.25,
        pitch=-0.15 + abs(math.sin(p * 16.0)) * 0.1,
    )


def _curious(p: float) -> GesturePose:
    if p < 0.25:
        ease = math.sin(p * 2.0 * math.pi * 0.5)
        return GesturePose(
            yaw=0.58 * ease,
            pitch=-0.15 * ease,
            gaze_x=-0.90 * ease,
            gaze_y=-0.35 * ease,
        )
    if p < 0.75:
        subtle_bob = math.sin((p - 0.24) * 21.0) * 0.06
        return GesturePose(
            yaw=0.55 + subtle_bob,
            pitch=-0.15 + subtle_bob * 0.6,
            gaze_x=-0.90,
            gaze_y=-0.30,
        )
    ease_back = (1.0 - p) / 0.25
    return GesturePose(
        yaw=0.55 * ease_back,
        pitch=-0.15 * ease_back,
        gaze_x=-0.90 * ease_back,
        gaze_y=-0.30 * ease_back,
    )


def _tilt_left(_p: float) -> GesturePose:
    return GesturePose(yaw=0.45, pitch=-0.08, gaze_x=-0.8)


def _tilt_right(_p: float) -> GesturePose:
    return GesturePose(yaw=-0.45, pitch=-0.08, gaze_x=0.8)


def _perk_up(p: float) -> GesturePose:
    if p < 0.20:
        snap = math.sin(p * 2.5 * math.pi)
        return GesturePose(pitch=-0.38 * snap, yaw=0.0, gaze_y=-0.95)
    if p < 0.75:
        alert_flutter = math.sin((p - 0.20) * 29.25) * 0.05
        return GesturePose(
            pitch=-0.36 + alert_flutter,
            yaw=math.sin((p - 0.20) * 16.25) * 0.08,
            gaze_y=-0.90,
        )
    ease_back = (1.0 - p) / 0.25
    return GesturePose(pitch=-0.36 * ease_back, gaze_y=-0.90 * ease_back)


def _droop(p: float) -> GesturePose:
    if p < 0.35:
        slump = math.sin(p * (math.pi / 0.7))
        return GesturePose(pitch=0.40 * slump, yaw=0.0, gaze_y=0.90 * slump)
    if p < 0.78:
        sleep_breath = math.sin((p - 0.352941) * 13.6) * 0.06
        return GesturePose(
            pitch=0.38 + sleep_breath,
            yaw=math.sin((p - 0.352941) * 6.8) * 0.04,
            gaze_y=0.90,
        )
    ease_back = (1.0 - p) / 0.22
    return GesturePose(pitch=0.38 * ease_back, gaze_y=0.90 * ease_back)


def _bounce(p: float) -> GesturePose:
    return GesturePose(
        pitch=-0.18 + math.sin(p * 20.0) * 0.18,
        yaw=math.sin(p * 10.0) * 0.08,
        gaze_y=-0.6,
    )


def _groove(p: float) -> GesturePose:
    return GesturePose(
        yaw=math.sin(p * 16.2) * 0.38,
        pitch=math.sin(p * 32.4) * 0.16,
        gaze_x=math.sin(p * 16.2) * 0.7,
    )


def _shiver(p: float) -> GesturePose:
    return GesturePose(
        yaw=math.sin(p * 108.0) * 0.07,
        pitch=0.14 + math.cos(p * 90.0) * 0.05,
        gaze_y=0.4,
    )


def _scan(p: float) -> GesturePose:
    return GesturePose(
        yaw=math.sin(p * 7.0) * 0.85,
        pitch=-0.05 + math.cos(p * 14.0) * 0.08,
        gaze_x=math.sin(p * 7.0) * 0.95,
    )


def _confused(p: float) -> GesturePose:
    if p < 0.50:
        return GesturePose(yaw=0.42, pitch=-0.1, gaze_x=-0.7)
    return GesturePose(yaw=-0.42, pitch=-0.05, gaze_x=0.7)


def _bow(p: float) -> GesturePose:
    pitch = (p / 0.50) * 0.38 if p < 0.50 else ((1.0 - p) / 0.50) * 0.38
    return GesturePose(pitch=pitch, yaw=0.0, gaze_y=0.8)


def _cheer(p: float) -> GesturePose:
    return GesturePose(
        pitch=-0.32 + math.sin(p * 21.0) * 0.08,
        yaw=math.sin(p * 28.0) * 0.25,
        gaze_y=-0.85,
    )


def _yawn(p: float) -> GesturePose:
    split = 0.5625
    if p < split:
        return GesturePose(pitch=-0.28 * (p / split), gaze_y=-0.7)
    return GesturePose(pitch=0.25 * ((p - split) / (1.0 - split)), gaze_y=0.5)


def _shy(_p: float) -> GesturePose:
    return GesturePose(yaw=-0.45, pitch=0.24, gaze_x=-0.8, gaze_y=0.6)


def _peek_a_boo(p: float) -> GesturePose:
    if p < (45.0 / 85.0):
        return GesturePose(pitch=0.38, blink_progress=1.0, yaw=0.0)
    return GesturePose(pitch=-0.25, blink_progress=0.0, yaw=math.sin(p * 25.5) * 0.15)


def _dizzy_spin(p: float) -> GesturePose:
    return GesturePose(
        yaw=math.sin(p * 16.2) * 0.35,
        pitch=math.cos(p * 16.2) * 0.22,
        gaze_x=math.sin(p * 16.2) * 0.8,
        gaze_y=math.cos(p * 16.2) * 0.8,
    )


GESTURES: Dict[str, Gesture] = {
    "nod": Gesture(frames=60, trajectory=_nod, default_mood="HAPPY", aliases=("yes",)),
    "shake": Gesture(frames=70, trajectory=_shake, aliases=("no", "shake_head")),
    "wiggle": Gesture(frames=80, trajectory=_wiggle, default_mood="HAPPY"),
    "curious": Gesture(frames=75, trajectory=_curious, default_mood="THINKING", aliases=("tilt",)),
    "tilt_left": Gesture(frames=55, trajectory=_tilt_left, aliases=("lean_left",)),
    "tilt_right": Gesture(frames=55, trajectory=_tilt_right, aliases=("lean_right",)),
    "perk_up": Gesture(frames=65, trajectory=_perk_up, default_mood="SURPRISED", aliases=("alert",)),
    "droop": Gesture(frames=85, trajectory=_droop, default_mood="SLEEPY"),
    "bounce": Gesture(frames=50, trajectory=_bounce, default_mood="STAR_EYES", aliases=("hop",)),
    "groove": Gesture(frames=90, trajectory=_groove, default_mood="COOL", aliases=("dance",)),
    "shiver": Gesture(frames=60, trajectory=_shiver, default_mood="CRYING", aliases=("tremble", "quiver")),
    "scan": Gesture(frames=100, trajectory=_scan, aliases=("look_around", "search")),
    "confused": Gesture(frames=80, trajectory=_confused, default_mood="THINKING", aliases=("ponder",)),
    "bow": Gesture(frames=70, trajectory=_bow, default_mood="HAPPY", aliases=("respect",)),
    "cheer": Gesture(frames=70, trajectory=_cheer, default_mood="STAR_EYES", aliases=("celebrate",)),
    "yawn": Gesture(frames=80, trajectory=_yawn, default_mood="SLEEPY"),
    "shy": Gesture(frames=65, trajectory=_shy, default_mood="LOVE", aliases=("bashful",)),
    "peek_a_boo": Gesture(frames=85, trajectory=_peek_a_boo, default_mood="SURPRISED", aliases=("hide",)),
    "dizzy_spin": Gesture(frames=90, trajectory=_dizzy_spin, default_mood="DIZZY", aliases=("swirl", "orbital")),
}

GESTURE_ALIASES: Dict[str, str] = {}
GESTURE_DEFAULT_MOOD: Dict[str, str] = {}
for _name, _gesture in GESTURES.items():
    GESTURE_ALIASES[_name] = _name
    if _gesture.default_mood:
        GESTURE_DEFAULT_MOOD[_name] = _gesture.default_mood
    for _alias in _gesture.aliases:
        GESTURE_ALIASES[_alias] = _name
        if _gesture.default_mood:
            GESTURE_DEFAULT_MOOD[_alias] = _gesture.default_mood


def resolve_gesture(gesture_name: str) -> Optional[str]:
    """Resolves a canonical gesture name or alias, returning None if unknown."""
    key = str(gesture_name).lower().strip()
    return GESTURE_ALIASES.get(key)
