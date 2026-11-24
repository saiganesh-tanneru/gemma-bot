"""Shared thread-safe robot state and command queue."""

import queue

COMMAND_QUEUE: queue.Queue = queue.Queue()

ROBOT_STATE = {
    "mood": "NEUTRAL",
    "gesture": None,
    "screen_theme": "CYAN",
    "screen_color": "#00F0FF",
    "yaw": 0.0,
    "pitch": 0.0,
    "gaze": [0.0, 0.0],
    "is_speaking": False,
    "speech_text": "",
}
