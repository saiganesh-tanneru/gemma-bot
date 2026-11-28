# AGENTS.md — Instructions for Coding Models & Agents

This repository (`gemma-bot`) uses `docs/` as an **Obsidian-compatible knowledge base**.
Coding models and agents working in this repo should treat `docs/` as shared project memory.

## 1. Read Before Implementing
- Start at `docs/00-Index.md` and `docs/Architecture/System-Overview.md` when onboarding or working across components.
- Before modifying `controllers/gemma_bot_controller/`, `gemma_talk_bridge.py`, `intent_parser.py`, `voice_server/`, `voice_client/`, or `worlds/`, search `docs/` for related architecture notes, design constraints, and open tasks (for example, `docs/DEMO_REVIEW_PLAN.md`).

## 2. Write Back Important Decisions & Findings
Keep documentation lightweight and high-signal—only write notes that help future coding sessions:
- **Architecture decisions:** Add or update a note in `docs/Architecture/` (for example `ADR-001-<topic>.md`) when changing protocols, hardware/Webots device contracts, API schemas, or cross-service flows.
- **Debugging / implementation logs:** When resolving a non-trivial bug or completing a multi-file change, add a short summary in `docs/DevLogs/YYYY-MM-DD-<topic>.md`.
- **Task tracking:** Track multi-step feature plans or investigations in `docs/Tasks/<topic>.md`.

## 3. Obsidian Formatting Rules
- **Preserve YAML frontmatter:** Do not remove or corrupt existing frontmatter keys (`tags`, `aliases`, `status`, `updated`) when editing notes in `docs/`.
- **Use `[[wikilinks]]` inside `docs/`:** Link between vault notes using Obsidian wikilinks (e.g., `[[Architecture/System-Overview]]` or `[[DEMO_REVIEW_PLAN]]`).
- **Keep `README.md` standard Markdown:** Use standard relative links in root `README.md` so GitHub renders them cleanly.
- **Never store secrets:** Never write API keys, tokens, or `.env` values into `docs/`.

## 4. Verification
- Run the test suite with `.venv/bin/pytest` (or `pytest`) after code changes.
