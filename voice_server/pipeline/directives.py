"""Extracts and allowlist-validates inline [BOT: ...] expression directives from LLM streams."""

import re
from typing import Any, Dict, Optional

from intent_parser import (
    ALLOWED_GAZES,
    ALLOWED_GESTURES,
    ALLOWED_MOODS,
    ALLOWED_SCREENS,
    parse_keyword_intent,
)

_TAG_RE = re.compile(r"^\s*\[BOT:\s*([^\]]+)\]\s*", re.IGNORECASE)
_KV_RE = re.compile(r"([a-z_]+)\s*=\s*([a-zA-Z0-9_]+)")


def validate_directive_fields(raw_fields: Dict[str, str]) -> Dict[str, Any]:
    """Validates parsed directive key/value pairs against strict robot allowlists."""
    out: Dict[str, Any] = {}
    for k, v in raw_fields.items():
        key = k.lower().strip()
        val = v.strip()
        if key == "mood":
            up = val.upper()
            if up in ALLOWED_MOODS:
                out["mood"] = up
        elif key == "gesture":
            low = val.lower()
            if low in ALLOWED_GESTURES:
                out["gesture"] = low
        elif key in ("screen", "screen_color", "theme", "color"):
            up = val.upper()
            if up in ALLOWED_SCREENS:
                out["screen_color"] = up
        elif key == "gaze":
            low = val.lower()
            if low in ALLOWED_GAZES:
                out["gaze"] = low
    return out


def extract_user_robot_action(transcript: str) -> Dict[str, Any]:
    """Extracts deterministic robot control fields from user speech using Phase 1 keyword parser."""
    parsed = parse_keyword_intent(transcript)
    action: Dict[str, Any] = {}
    for key in ("mood", "gesture", "gaze", "screen_color"):
        if key in parsed and parsed[key]:
            action[key] = parsed[key]
    return action


class DirectiveTagExtractor:
    """Strips an optional leading [BOT: mood=... gesture=...] tag across streamed tokens."""

    def __init__(self, max_header_chars: int = 160):
        self._buffer = ""
        self._max_header_chars = max_header_chars
        self.resolved = False
        self.directives: Dict[str, Any] = {}

    def feed(self, token: str) -> str:
        if self.resolved:
            return token

        self._buffer += token
        stripped = self._buffer.lstrip()
        if not stripped:
            return ""

        # If the stream doesn't start with '[', emit immediately without waiting
        if not stripped.startswith("["):
            self.resolved = True
            out = self._buffer
            self._buffer = ""
            return out

        # Check if it starts with something other than '[BOT:' once we have >= 5 chars
        if len(stripped) >= 5 and not stripped[:5].upper().startswith("[BOT:"):
            self.resolved = True
            out = self._buffer
            self._buffer = ""
            return out

        # Wait for closing ']' or safety limit
        close_idx = self._buffer.find("]")
        if close_idx != -1:
            match = _TAG_RE.match(self._buffer)
            if match:
                raw_body = match.group(1)
                raw_fields = {k: v for k, v in _KV_RE.findall(raw_body)}
                self.directives = validate_directive_fields(raw_fields)
                rest = self._buffer[match.end() :]
            else:
                rest = self._buffer
            self._buffer = ""
            self.resolved = True
            return rest

        if len(self._buffer) >= self._max_header_chars:
            self.resolved = True
            out = self._buffer
            self._buffer = ""
            return out

        return ""

    def flush(self) -> str:
        if self.resolved:
            return ""
        self.resolved = True
        out = self._buffer
        self._buffer = ""
        return out
