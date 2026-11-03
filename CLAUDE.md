# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Spec: `PersonalFinances.md` (PRD). MVP só para um utilizador (Bankinter); segundo utilizador e backup ficam para depois.

Feito: parser Bankinter CSV + reconciliação (`backend/app/parsers/`), dedup pura (`backend/app/services/dedup.py`), modelos e migrações `0001` (esquema) e `0002` (seed de categorias PT), `/api/health`, Dockerfile e `docker-compose.yml`.
Por fazer (por esta ordem): login de utilizador único (argon2, sessões, CSRF, `make create-user`), import_service (preview/confirm/reversão, ligando parser + dedup à BD), normalizador, regras, frontend. A flag de ordem ambígua de `detect_order` ainda não é guardada.

## Commands

- `make test` — pytest em `backend/` (usa `backend/.venv`; a máquina é Fedora atómica com Podman, sem docker; `podman-compose` está em `backend/.venv/bin`, usar `make up COMPOSE="podman compose"` com esse bin no PATH).
- `make lint` — ruff.
- Migração: `cd backend && DATABASE_URL=postgresql+psycopg://... .venv/bin/alembic upgrade head`. Testada contra `docker.io/library/postgres:16` via `podman run`.
- Testes: CSV sintético gerado em `backend/tests/conftest.py` (sem dados pessoais; constantes escritas à mão). Exports reais ficam em `backend/tests/fixtures/local/` (ignorado pelo git; `test_local_real.py` verifica a reconciliação se existirem). **Nunca fazer commit de `dados.csv` nem de extratos reais.**

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
