"""Pytest session configuration for Gemma-Bot.

Forces deterministic, offline-safe defaults for the whole test session:
- Intent parsing uses the local keyword parser, never the live Sarvam LLM,
  even when SARVAM_API_KEY is set in the developer's environment.
- The Sarvam API key is removed so no test can accidentally construct a
  live Sarvam provider.
"""

import os

os.environ["GEMMA_INTENT_PROVIDER"] = "keyword"
os.environ.pop("SARVAM_API_KEY", None)
