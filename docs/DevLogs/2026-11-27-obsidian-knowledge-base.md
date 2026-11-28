---
tags:
  - devlog
date: 2026-11-27
status: active
related:
  - "[[00-Index]]"
  - "[[Architecture/System-Overview]]"
  - "[[DEMO_REVIEW_PLAN]]"
  - "[[Tasks/README]]"
---

# Obsidian knowledge base and agent notes

## Context

Working tree had no controller, voice, or world edits. The uncommitted work adds an Obsidian vault under `docs/`, instructions so coding agents treat that vault as project memory, and a `.gitignore` rule for local Obsidian workspace state.

`docs/DEMO_REVIEW_PLAN.md` and `docs/assets/` (`color_themes.png`, `expressions_grid.png`, `gemma_bot_webots.jpg`) are already committed and were left unchanged.

## Findings / Changes

- `AGENTS.md` tells agents to read [[00-Index]] and [[Architecture/System-Overview]] before cross-component work, and to search `docs/` before editing the controller, `gemma_talk_bridge.py`, `intent_parser.py`, `voice_server/`, `voice_client/`, or `worlds/`. Write-back rules: ADRs in `docs/Architecture/`, session logs in `docs/DevLogs/YYYY-MM-DD-<topic>.md`, multi-step plans in `docs/Tasks/`. Wikilinks stay inside `docs/`; root `README.md` stays standard Markdown. No secrets in notes. After code changes, run `.venv/bin/pytest`.
- `.agents/skills/obsidian-notes/SKILL.md` is the same workflow as a project skill: when to write notes, where they live, frontmatter, wikilinks, and a check that every `[[target]]` matches a file under `docs/`.
- New vault notes (all untracked):
  - [[00-Index]] — hub. Links [[Architecture/System-Overview]], [[DEMO_REVIEW_PLAN]], [[Tasks/README]], and [[DevLogs/README]], plus the main repo entrypoints (`start_all.sh`, controller, intent parser, talk bridge, voice stack, `config.py`).
  - [[Architecture/System-Overview]] — Webots controller modules, CLI/intent parsing (English, Telugu, Tanglish), voice pipeline and `gemma_talk_bridge.py`, and `config.py` / `tests/`.
  - [[DevLogs/README]] and [[Tasks/README]] — naming conventions and note templates. No task notes yet.
- `.gitignore` now ignores `.obsidian/workspace*.json` and `.obsidian/cache`. Because the pattern contains a slash, Git anchors it at the repo root. It ignores `.obsidian/workspace.json` and does not ignore `docs/.obsidian/workspace.json`. That workspace file is still untracked and holds local UI state (open tabs, layout).
- Two Obsidian config trees are untracked and match each other: repo-root `.obsidian/` and `docs/.obsidian/`. `app.json` is empty, the ribbon is hidden, and core plugins are the usual set (explorer, search, graph, backlinks, properties, daily notes, templates, outline). [[00-Index]] says to open `docs/` as the vault. The root `.obsidian/` folder is a second vault on the repo root.

## Verification

- Compared `git status` and `git diff .gitignore` with the new files. No application code is in the diff, so pytest was not run.
- Wikilinks in this note resolve to notes that exist under `docs/`.
