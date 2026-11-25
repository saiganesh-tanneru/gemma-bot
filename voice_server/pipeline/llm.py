import json
import logging
import re
from typing import AsyncGenerator, Dict, List, Optional

import httpx

import config

logger = logging.getLogger(__name__)


class SarvamStreamingClient:
    """Async streaming client for Sarvam AI Chat Completions with cooperative cancellation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: str = config.SARVAM_CHAT_URL,
        model: str = config.SARVAM_LLM_MODEL,
        max_tokens: int = 512,
    ):
        self.api_key = config.SARVAM_API_KEY if api_key is None else api_key
        self.endpoint = endpoint
        self.model = model
        self.max_tokens = max_tokens
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))

    async def close(self):
        await self.client.aclose()

    @staticmethod
    def clean_voice_text(text: str) -> str:
        """Strip [BOT: ...] tags, markdown, code blocks, and <think> tags for natural TTS playback."""
        text = re.sub(r"\[BOT:[^\]]*\]?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        return " ".join(text.split()).strip()

    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Streams tokens from Sarvam Chat Completions SSE endpoint."""
        if not self.api_key:
            logger.warning("SARVAM_API_KEY is not configured; cannot stream response.")
            yield "Please set your SARVAM API key in the environment to talk with me."
            return

        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": True,
            "temperature": 0.6,
            "max_tokens": self.max_tokens,
            "reasoning_effort": None,
        }
        headers = {
            "Content-Type": "application/json",
            "api-subscription-key": self.api_key,
        }

        try:
            async with self.client.stream("POST", self.endpoint, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                    else:
                        raw = line.strip()
                    if not raw or raw == "[DONE]":
                        if raw == "[DONE]":
                            break
                        continue
                    try:
                        data = json.loads(raw)
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        chunk = delta.get("content") or ""
                        if chunk:
                            yield chunk
                    except json.JSONDecodeError:
                        continue
        except httpx.HTTPStatusError as exc:
            logger.error("Sarvam LLM HTTP error %s: %s", exc.response.status_code, exc)
            yield "I encountered a communication error with Sarvam AI."
        except Exception as exc:
            logger.error("Sarvam LLM stream exception: %s", exc)
            raise
