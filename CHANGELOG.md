# Changelog

All notable changes to **Gemma-Bot** are documented in this file by phase.

## Voice Pipeline Integration — Sarvam AI (`feat/voice-pipeline-sarvam`)
- **Integrated Voice Server (`voice_server/`)**: Moved `gemma-talk`'s full-duplex voice pipeline (Silero VAD, AI4Bharat/Whisper STT, `SentenceChunker`, `VoiceSession` with barge-in) into `gemma-bot` and replaced `OllamaStreamingClient` (`gemma4`) with `SarvamStreamingClient` (`Sarvam /v1/chat/completions` streaming SSE via `config.SARVAM_CHAT_URL`).
- **Sarvam Voice TTS (`voice_server/pipeline/tts.py`)**: Added Sarvam Bulbul 24kHz Int16 PCM cloud synthesis (`sarvam` engine, default when `SARVAM_API_KEY` is set) alongside optional local `kokoro` ONNX.
- **Event Bus & Bridge Sync (`/ws/events`)**: Added `EventBroadcaster` in `voice_server` and pointed `GEMMA_TALK_WS_URL` at `/ws/events` so `gemma_talk_bridge.py` receives live browser session events without duplicating direct `_notify_robot` calls.
- **Integrated Web UI (`voice_client/`) & Self-Contained `start_all.sh`**: Ported the React/Vite UI into `voice_client/` (branded for Gemma-Bot + Sarvam AI) and updated `start_all.sh` (preserving `wait_for` bounded timeouts) to run entirely inside `gemma-bot` without external `gemma-talk` or Ollama dependencies.
- **Tests**: Added `tests/test_voice_pipeline.py` and updated `tests/test_start_all.py`.

## Unreleased
- **Launcher wait timeouts (`start_all.sh`)**: Added a `wait_for` helper with bounded waits and loud failures — Ollama (8s), Webots (15s), and Gemma-Talk backend (60s) now exit non-zero instead of printing success after a timeout or waiting forever; the Web UI wait (10s) warns instead of failing silently.
- **Sarvam chat endpoint (`config.py`)**: Changed the default `SARVAM_CHAT_URL` from `/v2/chat/completions` to `/v1/chat/completions` — /v1 is the preferred endpoint for sarvam-105b (some /v2 requests to it stall without an answer).
- **Offline-safe tests (`tests/conftest.py`)**: Test sessions now force the keyword intent provider and remove `SARVAM_API_KEY`, so tests never hit the live Sarvam API; added a regression test in `tests/test_ai_assistant.py`.
- **LICENSE**: Replaced the `[COPYRIGHT HOLDER]` placeholder with the owner's name.

## Phase 5 — Speech Abstraction & LLM Intent Parser (`feat/phase-5-speech-llm`)
- **Pluggable TTS (`controllers/gemma_bot_controller/tts.py`)**: Replaced hardcoded `say -v Samantha` with `TTSProvider` and implementations `MacSayTTS`, `SarvamTTS` (`POST https://api.sarvam.ai/text-to-speech`, `bulbul:v3` / `bulbul:v4-flash`, `api-subscription-key`, 2,500-char limit, Telugu auto-detection `te-IN`), and `NullTTS`.
- **Audio-Duration Lip-Sync**: Controller now sizes `speech_timer` from actual WAV audio duration when returned by `TTSHandle`, retaining the word-count estimate only as fallback.
- **Structured LLM Intent Parser (`intent_parser.py`)**: Added swappable `IntentProvider` (`SarvamIntentProvider` targeting `https://api.sarvam.ai/v2/chat/completions` with `json_schema`), strict action/mood/gesture/screen/gaze allowlist validation (`validate_intent_json`), off-loop `parse_async()`, and automatic fallback to Phase 1's word-boundary keyword parser on any failure, timeout, or disallowed output.
- **Documentation & Tests**: Updated `README.md` with setup, environment variables, and text architecture diagram; added `tests/test_phase5_speech_llm.py`.

## Phase 4 — Security & Server Hardening (`feat/phase-4-security`)
- **Multi-threaded HTTP Server**: Upgraded `HTTPServer` to `BotCommandHTTPServer(ThreadingHTTPServer)` with `daemon_threads = True`.
- **Payload Limits & Schema Validation**: Enforced `Content-Length` checks and `MAX_BODY_BYTES` (default 16 KB, returning `413`), plus strict JSON object & field type validation (returning `400`).
- **Token Authentication & Safe Binding**: Added constant-time `X-Bot-Token` (`hmac.compare_digest`) checks on `POST /command` and `GET /status` when `GEMMA_BOT_TOKEN` is set (returning `401` on mismatch), kept `127.0.0.1` as default bind host, and refused non-loopback binds (`0.0.0.0`) unless `GEMMA_BOT_TOKEN` is set.
- **Client & Docs**: Wired `X-Bot-Token` into `ai_assistant.py`, `gemma_talk_bridge.py`, and `start_all.sh`, and documented Raspberry Pi Zero LAN setup in `README.md`.
- **Tests**: Added `tests/test_phase4_security.py` covering `401`, `413`, `400`, `200`, `ThreadingHTTPServer`, and non-loopback bind guard.

## Phase 3 — Controller Structure & Refactor (`refactor/phase-3-structure`)
- **Modularized Controller**: Split `gemma_bot_controller.py` into `faces/` (`themes.py`, `renderer.py`), `gestures.py`, `state.py`, `server.py`, and `input_map.py` so the OLED renderer is importable without Webots or starting the HTTP server.
- **Unified Phase-Based Gesture Registry**: Collapsed duplicated gesture duration/trajectory `if/elif` chains into a single `GESTURES` registry (`Gesture(frames, trajectory(p))` with `p = t / total in [0, 1]`), replacing hardcoded frame offsets (`t < 40`, `t - 18`, etc.) with phase math.
- **Data-Driven Keyboard Mapping**: Replaced the ~120-line keyboard `if/elif` ladder with a declarative `KEYMAP` table in `input_map.py`.
- **Shared README Renderer**: Updated `scripts/generate_readme_assets.py` to import `FaceRenderer`, `CanvasTarget`, and `SCREEN_THEMES` directly from `faces/` instead of re-implementing them.
- **Golden-Master Tests**: Captured `tests/golden_master.json` (all 19 gesture trajectories + all 15 mood render hashes) before refactoring and verified exact behavior preservation in `tests/test_phase3_structure.py`.

## Phase 2 — Hygiene & Configuration (`chore/phase-2-hygiene`)
- **Git & Packaging**: Untracked committed `__pycache__/gemma_talk_bridge.cpython-311.pyc`, updated `.gitignore` (`.env`, `.env.*` excluding `.env.example`, `.venv/`, `.pytest_cache/`, `logs/`, `*.pyc`), added pinned `requirements.txt` and `requirements-dev.txt`, and removed the runtime `pip install websockets` call from `gemma_talk_bridge.py`.
- **License**: Added MIT `LICENSE` (with placeholder `[COPYRIGHT HOLDER]` pending owner confirmation).
- **Centralized Config**: Added `config.py` (with `.env` support and env overrides for host, port, URLs, paths, timeouts, and auth token) and `.env.example`. Replaced all hardcoded `8765` ports and `/Users/` paths in `ai_assistant.py`, `gemma_talk_bridge.py`, `controllers/gemma_bot_controller/gemma_bot_controller.py`, `scripts/generate_readme_assets.py`, and `start_all.sh`.
- **Note**: Sharing the real OLED renderer with `scripts/generate_readme_assets.py` depends on Phase 3's module extraction (`faces/`).
- **Tests**: Added `tests/test_phase2_hygiene.py`.

## Phase 1 — Bug Fixes (`fix/phase-1-bugs`)
- **`start_all.sh`**: Step 4 now actually launches `gemma_talk_bridge.py` in the background with file logging (`logs/gemma_talk_bridge.log`), PID tracking, recursive child process cleanup on `SIGINT`/`SIGTERM`/`EXIT`, and a startup liveness check that fails loudly if the bridge crashes.
- **`ai_assistant.py`**: Replaced substring `in` matching in `parse_natural_language_intent()` with `\b` word-boundary regex matching (while preserving direct emoji matching) and multi-word phrase precedence over single words.
- **`gemma_talk_bridge.py`**: Moved `send_bot_command()` off the asyncio event loop via `asyncio.to_thread` (`send_bot_command_async`) and non-blocking task dispatch so slow/unreachable Webots requests no longer block barge-in `flush` handling. Added structured `logging`, `WebotsHealth` tracking with exponential backoff, and periodic `/status` health checks.
- **`controllers/gemma_bot_controller/gemma_bot_controller.py`**:
  - Removed duplicate `idle_timer += 1` increments inside `NEUTRAL`, `HAPPY`, and `SLEEPY` idle branches so `idle_timer` advances once per tick.
  - Standardized `"CONFUSED"` mood mapping to `"THINKING"` (matching `GESTURE_DEFAULT_MOOD["confused"]` and `ai_assistant.py`).
  - Changed head touch sensor handling to rising-edge detection so petting while already `HAPPY` re-triggers `wiggle` and refreshes `idle_timer`.
  - Logged warnings and skipped activation when `trigger_gesture()` receives an unknown gesture name.
- **Tests**: Added `tests/` (`pytest`) with regression tests for all Phase 1 fixes.
