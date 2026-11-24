#!/usr/bin/env python3
"""
Gemma-Talk Bridge for Gemma-Bot
-------------------------------
Connects Gemma-Bot (in Webots) to the Gemma-Talk voice assistant backend.

It mirrors the real-time conversational states of Gemma-Talk into physical
robot behaviors and expressions:
- LISTENING   -> Eyes attentive, head turns toward user, perks up.
- THINKING    -> Mood 'THINKING', eyes look up, curious head tilt while Ollama runs.
- SPEAKING    -> Mood 'HAPPY', lip-sync mouth animation, conversational nodding.
- INTERRUPTED -> Instant barge-in cutoff: silences speech, halts mouth, blinks.

Usage:
  # 1. Start Gemma-Talk server in another terminal:
  #    cd "$GEMMA_TALK_DIR" && ./start-server.sh
  #
  # 2. Run this bridge:
  #    python3 gemma_talk_bridge.py
"""

import sys
import os
import json
import time
import logging
import asyncio
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

import config

logger = logging.getLogger("gemma_talk_bridge")

# Gemma-Bot Webots AI server endpoints
BOT_COMMAND_URL = config.BOT_COMMAND_URL
BOT_STATUS_URL = config.BOT_STATUS_URL
# Gemma-Talk backend WebSocket URL
GEMMA_TALK_WS_URL = config.GEMMA_TALK_WS_URL


@dataclass
class WebotsHealth:
    """Tracks Webots HTTP reachability and exponential retry backoff."""
    base_backoff: float = 1.0
    max_backoff: float = 30.0
    reachable: Optional[bool] = None
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    next_probe_at: float = 0.0

    def current_backoff(self) -> float:
        if self.consecutive_failures <= 0:
            return 0.0
        return min(self.max_backoff, self.base_backoff * (2 ** (self.consecutive_failures - 1)))

    def record_success(self) -> None:
        if self.reachable is False:
            logger.info(
                "Webots reachable at %s (recovered after %d failed attempts)",
                BOT_COMMAND_URL,
                self.consecutive_failures,
            )
        self.reachable = True
        self.consecutive_failures = 0
        self.last_error = None
        self.next_probe_at = 0.0

    def record_failure(self, exc: Exception, context: str = "") -> None:
        self.consecutive_failures += 1
        self.last_error = str(exc)
        delay = self.current_backoff()
        self.next_probe_at = time.monotonic() + delay
        was_reachable = self.reachable
        self.reachable = False
        if was_reachable is not False or self.consecutive_failures % 5 == 0:
            logger.warning(
                "Webots unreachable at %s%s: %s (failures=%d, backoff=%.1fs)",
                BOT_COMMAND_URL,
                f" [{context}]" if context else "",
                exc,
                self.consecutive_failures,
                delay,
            )

    def should_probe(self, now: Optional[float] = None) -> bool:
        if self.reachable is not False:
            return True
        return (time.monotonic() if now is None else now) >= self.next_probe_at


def send_bot_command(
    payload,
    health: Optional[WebotsHealth] = None,
    timeout: float = config.BRIDGE_TIMEOUT_SECONDS,
):
    """Sends a state/action payload to Gemma-Bot in Webots."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            BOT_COMMAND_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if health is not None:
            health.record_success()
        return result
    except Exception as exc:
        context = f"keys={sorted(payload.keys())}" if isinstance(payload, dict) else "payload"
        if health is not None:
            health.record_failure(exc, context=context)
        else:
            logger.warning("Webots unreachable at %s [%s]: %s", BOT_COMMAND_URL, context, exc)
        return None


async def send_bot_command_async(
    payload,
    health: Optional[WebotsHealth] = None,
    timeout: float = config.BRIDGE_TIMEOUT_SECONDS,
):
    """Non-blocking wrapper that executes the HTTP POST off the asyncio event loop."""
    return await asyncio.to_thread(send_bot_command, payload, health, timeout)


def check_webots_health(
    health: WebotsHealth,
    timeout: float = config.BRIDGE_HEALTH_TIMEOUT_SECONDS,
) -> bool:
    """Probes Webots /status endpoint and updates health state."""
    try:
        with urllib.request.urlopen(BOT_STATUS_URL, timeout=timeout) as resp:
            resp.read()
        health.record_success()
        return True
    except Exception as exc:
        health.record_failure(exc, context="healthcheck")
        return False


async def health_monitor_loop(
    health: WebotsHealth,
    interval: float = config.BRIDGE_HEALTH_INTERVAL_SECONDS,
):
    """Periodically checks Webots reachability with backoff when unreachable."""
    while True:
        if health.should_probe():
            await asyncio.to_thread(check_webots_health, health)
        await asyncio.sleep(interval)


def _enqueue_command(command_queue: asyncio.Queue, payload: dict) -> None:
    """Queues a robot command in FIFO order without blocking the WebSocket loop."""
    command_queue.put_nowait(payload)


def _drain_pending_commands(command_queue: asyncio.Queue) -> int:
    """Drops queued non-interrupt commands on barge-in so stale speech never plays after flush."""
    dropped = 0
    while not command_queue.empty():
        try:
            command_queue.get_nowait()
            command_queue.task_done()
            dropped += 1
        except asyncio.QueueEmpty:
            break
    return dropped


async def command_sender_loop(command_queue: asyncio.Queue, health: WebotsHealth):
    """Drains queued robot commands in order off the event loop."""
    while True:
        payload = await command_queue.get()
        try:
            await send_bot_command_async(payload, health=health)
        except Exception as exc:
            logger.error("Unexpected bridge sender error: %s", exc)
        finally:
            command_queue.task_done()


def _dispatch_urgent(pending_tasks: set, payload: dict, health: WebotsHealth) -> None:
    """Sends an urgent barge-in interrupt immediately without waiting behind an in-flight POST."""
    task = asyncio.create_task(send_bot_command_async(payload, health=health))
    pending_tasks.add(task)

    def _on_done(done_task: asyncio.Task) -> None:
        pending_tasks.discard(done_task)
        if not done_task.cancelled():
            exc = done_task.exception()
            if exc is not None:
                logger.error("Unexpected urgent bridge dispatch error: %s", exc)

    task.add_done_callback(_on_done)


async def connect_to_gemma_talk():
    """Connects to Gemma-Talk WebSocket and streams session states to Gemma-Bot."""
    try:
        import websockets
    except ImportError as exc:
        raise ImportError(
            "Missing dependency 'websockets'. Install project dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    print("=" * 65)
    print("🤖 Gemma-Talk <-> Gemma-Bot Bridge")
    print(f"🔗 Connecting to Gemma-Talk at {GEMMA_TALK_WS_URL}...")
    print(f"🤖 Forwarding actions to Gemma-Bot at {BOT_COMMAND_URL}...")
    print("=" * 65)

    health = WebotsHealth()
    command_queue: asyncio.Queue = asyncio.Queue()
    pending_tasks = set()
    health_task = asyncio.create_task(health_monitor_loop(health))
    sender_task = asyncio.create_task(command_sender_loop(command_queue, health))
    retry_delay = config.BRIDGE_WS_RETRY_BASE_SECONDS
    try:
        while True:
            try:
                async with websockets.connect(GEMMA_TALK_WS_URL) as ws:
                    logger.info("Connected to Gemma-Talk server at %s", GEMMA_TALK_WS_URL)
                    retry_delay = config.BRIDGE_WS_RETRY_BASE_SECONDS
                    _enqueue_command(
                        command_queue,
                        {
                            "mood": "HAPPY",
                            "gesture": "nod",
                            "speech": "Connected to Gemma-Talk!",
                        },
                    )

                    async for message in ws:
                        if isinstance(message, str):
                            try:
                                data = json.loads(message)
                                msg_type = data.get("type")

                                # 1. Handle State Changes
                                if msg_type == "state_change":
                                    state = data.get("state", "").upper()
                                    logger.info("Gemma-Talk State: [%s]", state)
                                    if state == "LISTENING":
                                        _enqueue_command(
                                            command_queue,
                                            {
                                                "state": "LISTENING",
                                                "mood": "NEUTRAL",
                                                "gaze": "center",
                                                "look_at": [0.0, -0.05],
                                            },
                                        )
                                    elif state == "THINKING":
                                        _enqueue_command(
                                            command_queue,
                                            {"state": "THINKING", "gesture": "curious"},
                                        )
                                    elif state == "SPEAKING":
                                        _enqueue_command(
                                            command_queue,
                                            {"state": "SPEAKING", "gesture": "nod"},
                                        )
                                    elif state in ("INTERRUPTED", "IDLE"):
                                        _drain_pending_commands(command_queue)
                                        _dispatch_urgent(
                                            pending_tasks,
                                            {"state": state, "interrupt": True},
                                            health,
                                        )

                                # 2. Instant Flush / Interruption
                                elif msg_type == "flush":
                                    logger.info("Barge-in interruption detected! Silencing Gemma-Bot.")
                                    _drain_pending_commands(command_queue)
                                    _dispatch_urgent(pending_tasks, {"interrupt": True}, health)

                                # 3. Transcripts & LLM Tokens
                                elif msg_type == "transcript":
                                    user_text = data.get("text", "")
                                    logger.info("User: %r", user_text)
                                elif msg_type == "llm_sentence":
                                    bot_text = data.get("text", "")
                                    logger.info("Gemma: %r", bot_text)
                                    _enqueue_command(
                                        command_queue,
                                        {"mood": "HAPPY", "speech": bot_text},
                                    )

                            except json.JSONDecodeError as exc:
                                logger.warning("Ignoring malformed JSON message from Gemma-Talk: %s", exc)
            except Exception as exc:
                logger.warning("Gemma-Talk server not connected (%s). Reconnecting in %ss...", exc, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(config.BRIDGE_WS_RETRY_MAX_SECONDS, retry_delay * 2)
    finally:
        health_task.cancel()
        sender_task.cancel()
        for task in list(pending_tasks):
            task.cancel()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(connect_to_gemma_talk())
    except KeyboardInterrupt:
        print("\nBridge stopped.")

if __name__ == "__main__":
    main()
