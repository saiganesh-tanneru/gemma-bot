import asyncio
import logging
import sys
import time
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import gemma_talk_bridge


def test_async_send_does_not_block_event_loop():
    """Slow HTTP robot calls must not block concurrent coroutines (e.g. barge-in)."""
    assert hasattr(gemma_talk_bridge, "send_bot_command_async"), (
        "Bridge must expose async send_bot_command_async that runs off the event loop"
    )

    def slow_urlopen(*args, **kwargs):
        time.sleep(0.35)
        raise TimeoutError("simulated slow robot")

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0.01)
            ticks += 1

    async def runner():
        with patch("urllib.request.urlopen", side_effect=slow_urlopen):
            await asyncio.gather(
                gemma_talk_bridge.send_bot_command_async({"interrupt": True}),
                ticker(),
            )

    asyncio.run(runner())
    assert ticks >= 10, f"Event loop was blocked during slow HTTP call (ticks={ticks})"


def test_bridge_logs_errors_and_tracks_webots_health(caplog):
    """Errors must not be swallowed silently; Webots health must surface unreachable state."""
    assert hasattr(gemma_talk_bridge, "WebotsHealth"), "Bridge must track Webots connection health"
    health = gemma_talk_bridge.WebotsHealth(base_backoff=0.1, max_backoff=1.0)

    def failing_urlopen(*args, **kwargs):
        raise ConnectionRefusedError("Connection refused")

    with caplog.at_level(logging.WARNING):
        with patch("urllib.request.urlopen", side_effect=failing_urlopen):
            res = gemma_talk_bridge.send_bot_command({"mood": "HAPPY"}, health=health)

    assert res is None
    assert health.reachable is False
    assert health.consecutive_failures == 1
    assert any("webots unreachable" in rec.message.lower() for rec in caplog.records)
