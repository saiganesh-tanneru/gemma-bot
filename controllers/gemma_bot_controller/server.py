"""Embedded multi-threaded HTTP command server with token auth and payload validation."""

import hmac
import http.server
import json
import math
import threading
from typing import Any, Dict, Optional

import config
from state import COMMAND_QUEUE, ROBOT_STATE

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_STR_FIELDS = {
    "action", "mood", "gesture", "screen", "screen_color", "theme", "color",
    "gaze", "speech", "thought", "state",
}
_BOOL_FIELDS = {"interrupt", "flush", "audio"}


def validate_bind_config(host: str, auth_token: str) -> None:
    """Refuses to bind non-loopback interfaces (such as 0.0.0.0) without an auth token."""
    if host not in _LOOPBACK_HOSTS and not auth_token:
        raise ValueError(
            f"Refusing to bind non-loopback host {host!r} without GEMMA_BOT_TOKEN set"
        )


def validate_command_payload(cmd: Any) -> Dict[str, Any]:
    """Validates decoded JSON command structure and field types."""
    if not isinstance(cmd, dict):
        raise ValueError("Command payload must be a JSON object")

    for field in _STR_FIELDS:
        if field in cmd and cmd[field] is not None and not isinstance(cmd[field], str):
            raise ValueError(f"Field '{field}' must be a string")

    for field in _BOOL_FIELDS:
        if field in cmd and cmd[field] is not None and not isinstance(cmd[field], bool):
            raise ValueError(f"Field '{field}' must be a boolean")

    if "look_at" in cmd and cmd["look_at"] is not None:
        coords = cmd["look_at"]
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            raise ValueError("Field 'look_at' must be a [yaw, pitch] array of 2 numbers")
        for val in coords[:2]:
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError("Field 'look_at' values must be finite numbers")

    return cmd


class BotCommandHTTPServer(http.server.ThreadingHTTPServer):
    """Threading HTTP server storing per-instance security configuration."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, auth_token: str, max_body_bytes: int):
        self.auth_token = auth_token
        self.max_body_bytes = max_body_bytes
        super().__init__(server_address, RequestHandlerClass)


class AICommandHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler to receive external AI commands and report robot status."""

    def log_message(self, format, *args):
        pass

    def _send_json(self, status_code: int, payload: Dict[str, Any], close: bool = False) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _check_auth(self) -> bool:
        expected = getattr(self.server, "auth_token", "")
        if not expected:
            return True
        provided = self.headers.get("X-Bot-Token", "")
        if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
            self._send_json(401, {"error": "Unauthorized"})
            return False
        return True

    def do_GET(self):
        if self.path == "/status":
            if not self._check_auth():
                return
            self._send_json(200, ROBOT_STATE)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Gemma-Bot AI Command Server Active\n")

    def do_POST(self):
        if self.path != "/command":
            self.send_response(404)
            self.end_headers()
            return

        if not self._check_auth():
            return

        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            self._send_json(400, {"error": "Missing Content-Length header"})
            return
        try:
            content_length = int(raw_len)
        except ValueError:
            self._send_json(400, {"error": "Invalid Content-Length header"})
            return
        if content_length < 0:
            self._send_json(400, {"error": "Negative Content-Length header"})
            return

        max_bytes = getattr(self.server, "max_body_bytes", config.MAX_BODY_BYTES)
        if content_length > max_bytes:
            self._send_json(413, {"error": f"Payload exceeds {max_bytes} byte limit"}, close=True)
            return

        body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            cmd = validate_command_payload(parsed)
        except Exception as exc:
            self._send_json(400, {"error": str(exc)})
            return

        COMMAND_QUEUE.put(cmd)
        self._send_json(200, {"status": "received", "command": cmd})


def start_command_server(
    port: int = config.BOT_PORT,
    host: str = config.BOT_HOST,
    auth_token: Optional[str] = None,
    max_body_bytes: Optional[int] = None,
):
    """Starts the background multi-threaded AI command server."""
    token = config.BOT_AUTH_TOKEN if auth_token is None else auth_token
    limit = config.MAX_BODY_BYTES if max_body_bytes is None else max_body_bytes
    validate_bind_config(host, token)

    try:
        server = BotCommandHTTPServer((host, port), AICommandHandler, auth_token=token, max_body_bytes=limit)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server
    except Exception as e:
        print(f"[AI Server] Warning: Could not bind {host}:{port}: {e}")
        return None
