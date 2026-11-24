"""Data-driven keyboard input mapping replacing the if/elif ladder."""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class KeyAction:
    mood: Optional[str] = None
    gesture: Optional[str] = None
    cycle_theme: bool = False
    yaw_delta: float = 0.0
    pitch_delta: float = 0.0
    gaze_x: Optional[float] = None
    gaze_y: Optional[float] = None
    log_label: Optional[str] = None


def _build_base_keymap() -> Dict[int, KeyAction]:
    mapping: Dict[int, KeyAction] = {
        ord("1"): KeyAction(mood="NEUTRAL", log_label="Mood -> NEUTRAL 😐"),
        ord("2"): KeyAction(mood="HAPPY", gesture="wiggle", log_label="Mood -> HAPPY 😀"),
        ord(" "): KeyAction(mood="HAPPY", gesture="wiggle", log_label="Mood -> HAPPY 😀"),
        ord("3"): KeyAction(mood="SURPRISED", gesture="perk_up", log_label="Mood -> SURPRISED 😮"),
        ord("4"): KeyAction(mood="SLEEPY", gesture="droop", log_label="Mood -> SLEEPY 😴"),
        ord("5"): KeyAction(mood="ANGRY", log_label="Mood -> ANGRY 😡"),
        ord("6"): KeyAction(mood="THINKING", gesture="curious", log_label="Mood -> THINKING 🤔"),
        ord("7"): KeyAction(mood="LOVE", gesture="wiggle", log_label="Mood -> LOVE 😍"),
        ord("8"): KeyAction(mood="COOL", log_label="Mood -> COOL 😎"),
        ord("9"): KeyAction(mood="STAR_EYES", gesture="perk_up", log_label="Mood -> STAR_EYES 🤩"),
        ord("0"): KeyAction(mood="PLEADING", log_label="Mood -> PLEADING 🥺"),
        ord("["): KeyAction(gesture="tilt_left", log_label="Gesture -> TILT LEFT"),
        ord("]"): KeyAction(gesture="tilt_right", log_label="Gesture -> TILT RIGHT"),
    }

    letter_actions = {
        "w": KeyAction(mood="WINK", log_label="Mood -> WINK 😉"),
        "c": KeyAction(mood="CRYING", gesture="droop", log_label="Mood -> CRYING 😭"),
        "t": KeyAction(mood="TONGUE", gesture="wiggle", log_label="Mood -> TONGUE 😋"),
        "d": KeyAction(mood="DIZZY", gesture="shake", log_label="Mood -> DIZZY 😵"),
        "s": KeyAction(mood="SMIRK", log_label="Mood -> SMIRK 😏"),
        "n": KeyAction(gesture="nod", log_label="Gesture -> NOD"),
        "h": KeyAction(gesture="shake", log_label="Gesture -> SHAKE"),
        "b": KeyAction(gesture="bounce", log_label="Gesture -> BOUNCE"),
        "g": KeyAction(gesture="groove", log_label="Gesture -> GROOVE / DANCE"),
        "v": KeyAction(gesture="shiver", log_label="Gesture -> SHIVER / TREMBLE"),
        "r": KeyAction(gesture="scan", log_label="Gesture -> SCAN / LOOK AROUND"),
        "p": KeyAction(gesture="perk_up", log_label="Gesture -> PERK UP"),
        "y": KeyAction(gesture="yawn", log_label="Gesture -> YAWN"),
        "o": KeyAction(gesture="bow", log_label="Gesture -> BOW"),
        "u": KeyAction(gesture="confused", log_label="Gesture -> CONFUSED TILT"),
        "z": KeyAction(gesture="dizzy_spin", log_label="Gesture -> DIZZY SPIN"),
        "j": KeyAction(gesture="cheer", log_label="Gesture -> CHEER / CELEBRATE"),
        "k": KeyAction(gesture="shy", log_label="Gesture -> SHY / BASHFUL"),
        "q": KeyAction(gesture="peek_a_boo", log_label="Gesture -> PEEK-A-BOO"),
        "x": KeyAction(cycle_theme=True),
    }
    for ch, action in letter_actions.items():
        mapping[ord(ch.lower())] = action
        mapping[ord(ch.upper())] = action
    return mapping


KEYMAP: Dict[int, KeyAction] = _build_base_keymap()


def build_keymap(keyboard_cls) -> Dict[int, KeyAction]:
    """Returns KEYMAP augmented with Webots Keyboard arrow key codes."""
    full_map = dict(KEYMAP)
    full_map[keyboard_cls.LEFT] = KeyAction(yaw_delta=0.2, gaze_x=-0.9)
    full_map[keyboard_cls.RIGHT] = KeyAction(yaw_delta=-0.2, gaze_x=0.9)
    full_map[keyboard_cls.UP] = KeyAction(pitch_delta=-0.1, gaze_y=-0.8)
    full_map[keyboard_cls.DOWN] = KeyAction(pitch_delta=0.1, gaze_y=0.8)
    return full_map


def apply_key_action(bot, action: KeyAction) -> None:
    """Applies a KeyAction to a GemmaBotCompanion instance."""
    if action.cycle_theme:
        bot.cycle_screen_theme()
    if action.mood is not None:
        bot.mood = action.mood
    if action.gesture is not None:
        bot.trigger_gesture(action.gesture)
    if action.yaw_delta:
        bot.target_yaw = max(-1.2, min(1.2, bot.target_yaw + action.yaw_delta))
    if action.pitch_delta:
        bot.target_pitch = max(-0.4, min(0.4, bot.target_pitch + action.pitch_delta))
    if action.gaze_x is not None:
        bot.gaze_x = action.gaze_x
    if action.gaze_y is not None:
        bot.gaze_y = action.gaze_y
    if action.log_label:
        print(action.log_label)
