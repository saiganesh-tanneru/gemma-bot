---
tags:
  - architecture
aliases:
  - System Architecture
status: active
---

# System Overview

Back to [[00-Index]].

## High-Level Components

1. **Webots Simulation & Controller** (`worlds/`, `protos/`, `controllers/gemma_bot_controller/`)
   - Worlds: `worlds/gemma_bot.wbt` (default fitted-CAD desk world using `GemaBotReview` for Chintu) and `worlds/gemabot_review_plan.wbt` (full WFH desk scene; see [[DEMO_REVIEW_PLAN]]).
   - Controller modules:
     - `gemma_bot_controller.py` — Main Webots supervisor/robot loop, animation state, and auto-detected Display sizing (`502×410` AMOLED in Webots, `128×64` fallback in tests).
     - `emotion_engine/` — Reusable MIT-licensed Emotion Engine (`EyeConfig` 12-float `500 ms` morphing across 29 emotions, `Energy`/`Boredom`/`Bond` weighted roulette, `BlinkController`, declarative idle postures, and PCM chirp synthesis).
     - `gestures.py` — 19 phase-normalized trajectory gestures.
     - `faces/` — OLED/AMOLED expression renderer (classic `128×64` + parametric `EyeConfig` scaling) and 6 color themes, sourcing mood maps from `emotion_engine`.
     - `server.py` — Multi-threaded HTTP command server (`127.0.0.1:8765` by default, `X-Bot-Token` auth).
     - `tts.py` — Pluggable speech (`MacSayTTS`, `SarvamTTS`, `NullTTS`) with audio-duration lip-sync.
     - `input_map.py` & `state.py` — Keyboard mapping and shared controller state.

   See also [[Architecture/ADR-001-emotion-engine-and-solar-head]] for the Emotion Engine and popped-off solar/touch hardware decisions.

2. **CLI & Intent Parsing** (`ai_assistant.py`, `intent_parser.py`)
   - Parses natural-language prompts (English, Telugu, Tanglish) via Sarvam structured JSON output with allowlist validation and word-boundary keyword fallback.

3. **Voice Pipeline & Bridge** (`voice_server/`, `voice_client/`, `gemma_talk_bridge.py`)
   - `voice_client/` — React + Vite web UI streaming audio over `/ws`.
   - `voice_server/` — FastAPI service with Silero VAD, STT, chunking, and Sarvam streaming LLM (`sarvam-105b`) + TTS (`bulbul:v3`).
   - `gemma_talk_bridge.py` — Bridges `voice_server` `/ws/events` to the controller's HTTP `/command` endpoint.

4. **Configuration & Tests** (`config.py`, `tests/`)
   - `config.py` loads `.env` without overriding existing environment variables.
   - `tests/` contains unit, security, structure, golden-master, and pipeline tests.
