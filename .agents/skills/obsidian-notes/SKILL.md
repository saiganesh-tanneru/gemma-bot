---
name: obsidian-notes
description: >-
  Read, create, and update Obsidian-compatible Markdown notes in docs/.
  Use when documenting architecture decisions (ADRs), logging debugging/session
  outcomes, updating task notes, or checking project knowledge before major edits.
---

# Obsidian Knowledge Base Workflow (`docs/`)

This project uses `docs/` as an in-repo Obsidian vault.

## When to Use This Skill
1. Before making architectural or cross-component changes (`gemma_talk_bridge.py`, `voice_server/`, `voice_client/`, `controllers/gemma_bot_controller/`, `worlds/`).
2. After solving a non-obvious bug or completing a feature that changes behavior, config, or device contracts.
3. When the user asks to document a decision, plan, or session log in Obsidian.

## Note Locations
- `docs/00-Index.md` — Hub note (update links when adding major architecture or task docs).
- `docs/Architecture/` — System docs and ADRs (`ADR-NNN-<slug>.md`).
- `docs/DevLogs/` — Dated debugging/session logs (`YYYY-MM-DD-<slug>.md`).
- `docs/Tasks/` — Feature plans and investigation checklists (`<slug>.md`).

## Rules
1. **Frontmatter:** Always include YAML frontmatter (`tags`, `status` or `date`) and preserve existing frontmatter keys when editing.
2. **Wikilinks:** Use Obsidian `[[wikilinks]]` for links between notes inside `docs/` (for example `[[00-Index]]` or `[[Architecture/System-Overview]]`).
3. **No secrets:** Never write API keys, tokens, or `.env` secrets into notes.
4. **Update the index:** When adding a durable architecture doc or active task, add a `[[wikilink]]` entry in `docs/00-Index.md` or the section's `README.md`.
5. **Verify links:** Confirm every `[[target]]` you reference corresponds to an existing `.md` file under `docs/`.
