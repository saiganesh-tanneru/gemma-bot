import http.server
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = REPO_ROOT / "controllers" / "gemma_bot_controller"
for p in (str(REPO_ROOT), str(CONTROLLER_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import server as bot_server
from state import COMMAND_QUEUE


def _drain_queue():
    while not COMMAND_QUEUE.empty():
        COMMAND_QUEUE.get_nowait()


def _post(url, body_bytes, headers=None):
    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers=headers or {"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


def test_server_is_threading_http_server():
    srv = bot_server.start_command_server(port=0, host="127.0.0.1", auth_token="tok-123")
    assert srv is not None
    try:
        assert isinstance(srv, http.server.ThreadingHTTPServer)
    finally:
        srv.shutdown()
        srv.server_close()


def test_bind_non_loopback_without_token_refuses_to_start():
    with pytest.raises(ValueError):
        bot_server.start_command_server(port=0, host="0.0.0.0", auth_token="")


def test_token_auth_401_and_200():
    _drain_queue()
    srv = bot_server.start_command_server(port=0, host="127.0.0.1", auth_token="super-secret")
    assert srv is not None
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}/command"
    payload = json.dumps({"mood": "HAPPY"}).encode("utf-8")

    try:
        # Missing token -> 401
        code, resp = _post(url, payload, headers={"Content-Type": "application/json"})
        assert code == 401

        # Wrong token -> 401
        code, resp = _post(
            url,
            payload,
            headers={"Content-Type": "application/json", "X-Bot-Token": "wrong"},
        )
        assert code == 401

        # Valid token -> 200
        code, resp = _post(
            url,
            payload,
            headers={"Content-Type": "application/json", "X-Bot-Token": "super-secret"},
        )
        assert code == 200
        assert resp["status"] == "received"
    finally:
        srv.shutdown()
        srv.server_close()
        _drain_queue()


def test_oversized_body_returns_413_and_invalid_fields_return_400():
    _drain_queue()
    srv = bot_server.start_command_server(
        port=0,
        host="127.0.0.1",
        auth_token="tok",
        max_body_bytes=128,
    )
    assert srv is not None
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}/command"
    headers = {"Content-Type": "application/json", "X-Bot-Token": "tok"}

    try:
        # Oversized body -> 413
        big_payload = json.dumps({"speech": "x" * 200}).encode("utf-8")
        code, _ = _post(url, big_payload, headers=headers)
        assert code == 413

        # Non-object JSON -> 400
        code, _ = _post(url, b'["not", "an", "object"]', headers=headers)
        assert code == 400

        # Invalid field type (look_at must be 2-element numeric sequence) -> 400
        code, _ = _post(url, json.dumps({"look_at": "bad"}).encode("utf-8"), headers=headers)
        assert code == 400

        # Invalid field type (mood must be string) -> 400
        code, _ = _post(url, json.dumps({"mood": 123}).encode("utf-8"), headers=headers)
        assert code == 400
    finally:
        srv.shutdown()
        srv.server_close()
        _drain_queue()
