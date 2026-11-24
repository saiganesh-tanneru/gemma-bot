"""Embedded HTTP command server for Gemma-Bot."""

import http.server
import json
import threading

import config
from state import COMMAND_QUEUE, ROBOT_STATE


class AICommandHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler to receive external AI commands and report robot status."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(ROBOT_STATE).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Gemma-Bot AI Command Server Active\n")

    def do_POST(self):
        if self.path == "/command":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                cmd = json.loads(body)
                COMMAND_QUEUE.put(cmd)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "received", "command": cmd}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def start_command_server(port=config.BOT_PORT, host=config.BOT_HOST):
    """Starts the background AI command server."""
    try:
        server = http.server.HTTPServer((host, port), AICommandHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server
    except Exception as e:
        print(f"[AI Server] Warning: Could not bind {host}:{port}: {e}")
        return None
