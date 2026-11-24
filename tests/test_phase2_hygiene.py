import importlib
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_hygiene_files_exist():
    assert (REPO_ROOT / "LICENSE").is_file()
    assert "MIT License" in (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert (REPO_ROOT / "requirements.txt").is_file()
    assert (REPO_ROOT / "requirements-dev.txt").is_file()
    assert (REPO_ROOT / ".env.example").is_file()

    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("__pycache__/", "*.pyc", ".env", ".env.*", ".venv/", "logs/"):
        assert pattern in gitignore, f"Missing {pattern} in .gitignore"


def test_no_runtime_pip_install_in_bridge():
    bridge_src = (REPO_ROOT / "gemma_talk_bridge.py").read_text(encoding="utf-8")
    assert "check_call" not in bridge_src
    assert '"pip"' not in bridge_src and "'pip'" not in bridge_src


def test_no_hardcoded_port_or_user_paths_outside_config():
    targets = [
        REPO_ROOT / "ai_assistant.py",
        REPO_ROOT / "gemma_talk_bridge.py",
        REPO_ROOT / "controllers" / "gemma_bot_controller" / "gemma_bot_controller.py",
        REPO_ROOT / "scripts" / "generate_readme_assets.py",
        REPO_ROOT / "start_all.sh",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "8765" not in text, f"Found hardcoded 8765 in {path.name}"
        assert "/Users/" not in text, f"Found hardcoded /Users/ path in {path.name}"


def test_config_defaults_and_env_overrides(monkeypatch):
    sys.path.insert(0, str(REPO_ROOT))
    import config

    monkeypatch.setenv("GEMMA_BOT_HOST", "0.0.0.0")
    monkeypatch.setenv("GEMMA_BOT_PORT", "9123")
    monkeypatch.setenv("GEMMA_TALK_WS_URL", "ws://10.0.0.5:8000/ws")
    monkeypatch.setenv("GEMMA_BOT_TOKEN", "secret-test-token")
    monkeypatch.setenv("GEMMA_BRIDGE_TIMEOUT", "2.5")

    cfg = importlib.reload(config)
    assert cfg.BOT_HOST == "0.0.0.0"
    assert cfg.BOT_PORT == 9123
    assert cfg.BOT_COMMAND_URL == "http://0.0.0.0:9123/command"
    assert cfg.BOT_STATUS_URL == "http://0.0.0.0:9123/status"
    assert cfg.GEMMA_TALK_WS_URL == "ws://10.0.0.5:8000/ws"
    assert cfg.BOT_AUTH_TOKEN == "secret-test-token"
    assert cfg.BRIDGE_TIMEOUT_SECONDS == 2.5

    # Reload back to defaults after clearing overrides
    for var in (
        "GEMMA_BOT_HOST",
        "GEMMA_BOT_PORT",
        "GEMMA_TALK_WS_URL",
        "GEMMA_BOT_TOKEN",
        "GEMMA_BRIDGE_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = importlib.reload(config)
    assert cfg.BOT_HOST == "127.0.0.1"
    assert cfg.BOT_PORT == 8765
