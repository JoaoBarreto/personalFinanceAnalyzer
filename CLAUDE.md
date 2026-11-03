# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

The repository is currently empty — no code, build system, or tests exist yet. Update this file with commands and architecture once the project is scaffolded.

## Agent setup

- Main session runs on Sonnet 5.5 with Opus 5.5 as the advisor (`.claude/settings.json`).
- Read-only Haiku 5.5 subagents in `.claude/agents/`:
  - `search` — map the repo (layout, entry points, how modules connect).
  - `grep` — find definitions and call sites of a symbol or pattern.
  - `docs` — pull official API reference for a library or tool.

## Advisor rule

Call the `advisor` tool:
1. Before locking in a plan.
2. After hitting the same error twice.
3. Before declaring a task done — write/save the deliverable first, then call it.
