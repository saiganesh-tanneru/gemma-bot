---
tags:
  - devlog
  - emotion-engine
  - faces
date: 2026-11-27
related:
  - "[[Architecture/System-Overview]]"
  - "[[DEMO_REVIEW_PLAN]]"
---

# Reusable MIT Emotion Engine Integration

## Context
Replaced scattered hardcoded mood, blink, idle posture, stimulus, and allowlist logic across `gemma_bot_controller.py`, `faces/`, and `intent_parser.py` with a standalone, Webots-independent `emotion_engine` package modeled on the decided 12-parameter eye morphing + weighted roulette architecture.

## Findings / Changes
- Added [emotion_engine/](../../controllers/gemma_bot_controller/emotion_engine/__init__.py) (`presets.py`, `engine.py`, `chirp.py`) in clean MIT-licensed Python:
  - `EyeConfig` (12-float parametric eye geometry with `lerp()` and `scaled(disp_w, disp_h)` for `128×64` OLED and `410×502` AMOLED).
  - `EMOTIONS` registry combining the 15 classic `gemma-bot` moods with 14 extended Emotion Engine states (`GLEE`, `WORRIED`, `FOCUSED`, `ANNOYED`, `SKEPTIC`, `FRUSTRATED`, `UNIMPRESSED`, `SUSPICIOUS`, `SQUINT`, `FURIOUS`, `SCARED`, `AWE`, `BORED`, `SULKING` — 29 total), paired with `default_gesture`, declarative `idle_behavior` posture specs, and `ChirpSpec`.
  - `EmotionEngine` with `500 ms` eye morph transitions, `EmotionState` (`energy`, `boredom`, `bond`, `detached`, `battery_pct`, `thermal_hot`), dynamic weighted roulette selection, `BlinkController`, and unified stimulus handlers (`handle_conversation_state`, `handle_touch`, `handle_detach`, `handle_shake`).
  - `synthesize_chirp_wav()` + `ChirpPlayer` (`NullChirpPlayer` under pytest / `TTS_PROVIDER=null`, `MacAfplayChirpPlayer` on macOS).
- Refactored [faces/themes.py](../../controllers/gemma_bot_controller/faces/themes.py) and [faces/renderer.py](../../controllers/gemma_bot_controller/faces/renderer.py) so `EMOJI_MOOD_MAP`, `resolve_mood`, and parametric eye rendering source from `emotion_engine` while keeping settled classic moods `128×64` pixel-compatible with `tests/golden_master.json`.
- Refactored [gemma_bot_controller.py](../../controllers/gemma_bot_controller/gemma_bot_controller.py), [input_map.py](../../controllers/gemma_bot_controller/input_map.py), and [intent_parser.py](../../intent_parser.py) to consume `EmotionEngine`, `ALL_MOODS`, and `GESTURES` as the single source of truth, and auto-detect PROTO `Display` dimensions (`502×410` in Webots vs. `128×64` in unit tests).
- Updated [generate_review_plan_world.py](../../scripts/generate_review_plan_world.py) and regenerated `protos/GemaBotReview.proto`, `protos/GemaClockDock.proto`, and `worlds/gemabot_review_plan.wbt` to match the fitted CAD (`146 mm` tall, `Ø86 mm` base, `Ø32 mm` ball socket at `z=72.5 mm`, `68×58×46 mm` head, `502×410` `2.06"` AMOLED, `50×30 mm` solar crown `head_touch` bumper, `±26°` ball-center tilt).
- Replaced the legacy inline `ORANGE_BODY` robot in [worlds/gemma_bot.wbt](../../worlds/gemma_bot.wbt) with `GemaClockDock` + `GemaBotReview` so `./start_all.sh` launches the fitted CAD model by default.
- Added [test_emotion_engine.py](../../tests/test_emotion_engine.py).

## Verification
- `.venv/bin/python scripts/generate_review_plan_world.py` — regenerated PROTOs/world (`total height 0.146`, `ball-center z=0.0725`), all VRML & device guards passed.
- `.venv/bin/pytest -v` — 48 passed in 5.17s (golden-master digests, controller, intent parser, voice directives, Emotion Engine, and Webots PROTO/world checks).
