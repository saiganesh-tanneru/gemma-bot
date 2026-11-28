"""Local-first HTTP command & Face Playground server for Chintu by Sarworks."""

import hmac
import http.server
import json
import os
from pathlib import Path
import queue
import threading
from typing import Any, Dict, Optional

from controllers.chintu_controller.audio_cues import (
    BABY_YAWN_WAV_PATH,
    SFX_KINDS,
    synthesize_sfx_wav,
    synthesize_stir_chirp_wav,
)

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_PLAYGROUND_HTML_PATH = Path(__file__).resolve().parent / "playground.html"

CHINTU_COMMAND_QUEUE: "queue.Queue[Dict[str, Any]]" = queue.Queue()
CHINTU_STATUS: Dict[str, Any] = {
    "product": "Chintu",
    "manufacturer": "Sarworks",
    "state": "SLEEP",
    "mood": "SLEEPY",
    "pan_deg": 0.0,
    "tilt_deg": -12.0,
    "is_charging": False,
    "is_docked": True,
    "servos_attached": True,
    "energy": 100.0,
    "boredom": 0.0,
    "bond": 0.0,
    "wake_count": 0,
    "last_wake_duration_s": None,
    "yawn_wav_duration_s": None,
    "tts_calls_during_wake": 0,
    "host_audio": False,
    "last_audio_cue": None,
    "tag_log": [],
    "frame": {},
}


class ChintuHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, auth_token: str = "", max_body_bytes: int = 16384):
        self.auth_token = auth_token
        self.max_body_bytes = max_body_bytes
        super().__init__(server_address, RequestHandlerClass)


class ChintuRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_bytes(self, status_code: int, content_type: str, body: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        self._send_bytes(status_code, "application/json", json.dumps(payload).encode("utf-8"))

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
        if self.path in ("/", "/playground", "/playground.html"):
            if _PLAYGROUND_HTML_PATH.is_file():
                self._send_bytes(200, "text/html; charset=utf-8", _PLAYGROUND_HTML_PATH.read_bytes())
            else:
                self._send_json(404, {"error": "Playground HTML not found"})
            return

        if self.path == "/assets/chintu-baby-yawn.wav":
            if BABY_YAWN_WAV_PATH.is_file():
                self._send_bytes(200, "audio/wav", BABY_YAWN_WAV_PATH.read_bytes())
            else:
                self._send_json(404, {"error": "Baby yawn WAV missing"})
            return

        if self.path == "/assets/stir-chirp.wav":
            self._send_bytes(200, "audio/wav", synthesize_stir_chirp_wav())
            return

        if self.path.startswith("/assets/sfx/") and self.path.endswith(".wav"):
            kind = self.path[len("/assets/sfx/") : -4]
            if kind in SFX_KINDS:
                self._send_bytes(200, "audio/wav", synthesize_sfx_wav(kind))
                return
            self._send_json(404, {"error": f"Unknown SFX kind {kind!r}"})
            return

        if self.path == "/status":
            if not self._check_auth():
                return
            self._send_json(200, dict(CHINTU_STATUS))
            return

        self._send_bytes(200, "text/plain; charset=utf-8", b"Chintu by Sarworks Controller Active\n")

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
        max_bytes = getattr(self.server, "max_body_bytes", 16384)
        if content_length > max_bytes:
            self._send_json(413, {"error": f"Payload exceeds {max_bytes} byte limit"})
            return

        body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            if not isinstance(parsed, dict):
                raise ValueError("Command payload must be a JSON object")
        except Exception as exc:
            self._send_json(400, {"error": str(exc)})
            return

        CHINTU_COMMAND_QUEUE.put(parsed)
        self._send_json(200, {"status": "received", "command": parsed})


def start_chintu_server(
    port: Optional[int] = None,
    host: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Optional[ChintuHTTPServer]:
    bind_host = host or os.environ.get("CHINTU_HOST", "127.0.0.1")
    bind_port = int(port if port is not None else os.environ.get("CHINTU_PORT", "8765"))
    token = os.environ.get("CHINTU_TOKEN", "") if auth_token is None else auth_token
    if bind_host not in _LOOPBACK_HOSTS and not token:
        raise ValueError(f"Refusing to bind non-loopback host {bind_host!r} without CHINTU_TOKEN")
    try:
        srv = ChintuHTTPServer((bind_host, bind_port), ChintuRequestHandler, auth_token=token)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv
    except Exception as exc:
        print(f"[Chintu Server] Warning: Could not bind {bind_host}:{bind_port}: {exc}")
        return None
