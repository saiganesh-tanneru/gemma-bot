---
tags:
  - index
  - moc
aliases:
  - Gemma-Bot Home
  - Index
status: active
---

# Gemma-Bot Knowledge Base

Welcome to the `gemma-bot` Obsidian vault (`docs/`). Open this folder in Obsidian using **Open folder as vault → `gemma-bot/docs`**.

## Core Maps
- [[Architecture/System-Overview|System Overview]] — Components, entrypoints, and service boundaries
- [[DEMO_REVIEW_PLAN|Review-Plan Concept World]] — Stationary GemaBot world (`worlds/gemabot_review_plan.wbt`) setup & device contract

## Sections
- **Architecture & Decisions:** [[Architecture/System-Overview]], [[Architecture/ADR-001-emotion-engine-and-solar-head|ADR-001: Emotion Engine & Solar Head]]
- **Active Tasks & Plans:** [[Tasks/README|Tasks Hub]], [[Tasks/esp32-s3-emotion-and-solar-port|ESP32-S3 Emotion Engine & Solar Port]]
- **Dev & Debug Logs:** [[DevLogs/README|DevLogs Hub]]

## Key Repository Entrypoints
- `start_all.sh` — Launches Webots, `voice_server`, `gemma_talk_bridge.py`, and `voice_client`
- `controllers/gemma_bot_controller/gemma_bot_controller.py` — Webots robot controller & HTTP command server
- `ai_assistant.py` & `intent_parser.py` — CLI and English/Telugu/Tanglish intent parsing
- `gemma_talk_bridge.py` — Async WebSocket-to-HTTP bridge (`/ws/events` → `/command`)
- `voice_server/` — FastAPI + Silero VAD + STT + Sarvam LLM/TTS pipeline
- `voice_client/` — React + Vite voice frontend
- `config.py` — Shared configuration and `.env` loader
