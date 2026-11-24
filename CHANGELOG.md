# Changelog

All notable changes to **Gemma-Bot** are documented in this file by phase.

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
