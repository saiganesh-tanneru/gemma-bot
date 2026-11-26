"""Extracts and allowlist-validates inline [BOT: ...] expression directives from LLM streams."""

import re
from typing import Any, Dict

from intent_parser import (
    ALLOWED_GAZES,
    ALLOWED_GESTURES,
    ALLOWED_MOODS,
    ALLOWED_SCREENS,
    parse_keyword_intent,
)

_TAG_RE = re.compile(r"\[BOT:\s*([^\]]+)\]\s*", re.IGNORECASE)
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
    """Strips [BOT: mood=... gesture=...] tags anywhere in streamed LLM tokens."""

    def __init__(self, max_header_chars: int = 160):
        self._buffer = ""
        self._max_header_chars = max_header_chars
        self.resolved = False
        self.directives: Dict[str, Any] = {}
        self._dirty = False

    def has_new_directives(self) -> bool:
        return self._dirty

    def mark_emitted(self) -> None:
        self._dirty = False

    def feed(self, token: str) -> str:
        self._buffer += token
        output_parts = []

        while self._buffer:
            idx = self._buffer.find("[")
            if idx == -1:
                output_parts.append(self._buffer)
                self._buffer = ""
                break

            if idx > 0:
                output_parts.append(self._buffer[:idx])
                self._buffer = self._buffer[idx:]

            # Buffer now starts with '['
            if len(self._buffer) < 5:
                if not "[BOT:".startswith(self._buffer.upper()):
                    output_parts.append(self._buffer[0])
                    self._buffer = self._buffer[1:]
                    continue
                break

            if not self._buffer[:5].upper().startswith("[BOT:"):
                output_parts.append(self._buffer[0])
                self._buffer = self._buffer[1:]
                continue

            close_idx = self._buffer.find("]")
            if close_idx != -1:
                match = _TAG_RE.match(self._buffer)
                if match:
                    raw_body = match.group(1)
                    raw_fields = {k: v for k, v in _KV_RE.findall(raw_body)}
                    validated = validate_directive_fields(raw_fields)
                    if validated:
                        self.directives.update(validated)
                        self._dirty = True
                    self.resolved = True
                    self._buffer = self._buffer[match.end() :]
                    continue
                output_parts.append(self._buffer[0])
                self._buffer = self._buffer[1:]
                continue

            if len(self._buffer) >= self._max_header_chars:
                output_parts.append(self._buffer[0])
                self._buffer = self._buffer[1:]
                continue
            break

        return "".join(output_parts)

    def flush(self) -> str:
        if not self._buffer:
            return ""
        # Strip any incomplete trailing [BOT:... tag
        if self._buffer.upper().startswith("[BOT:"):
            self._buffer = ""
            return ""
        out = self._buffer
        self._buffer = ""
        return out
