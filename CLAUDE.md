# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Spec: `PersonalFinances.md` (PRD). MVP só para um utilizador (Bankinter); segundo utilizador e backup ficam para depois.

Feito: parser Bankinter CSV + reconciliação (`backend/app/parsers/`), dedup pura (`backend/app/services/dedup.py`), modelos e migrações `0001` (esquema) e `0002` (seed de categorias PT), `/api/health`, Dockerfile e `docker-compose.yml`.
Login feito: `/api/auth/login|logout|me`, sessão no servidor (só o sha256 do token na BD), CSRF por `X-CSRF-Token` em pedidos não-GET, rate limit em memória, `require_auth` em `backend/app/deps.py` (usar em todos os routers novos), CLI `python -m app.cli create-user` (`--password-stdin` para uso não interativo). `tests/test_route_guard.py` percorre `app.openapi()` e exige 401 em todas as rotas novas (exceto health/login). `/docs` e `/openapi.json` estão desligados (`ENABLE_DOCS=true` liga). A URL da BD vem de `POSTGRES_*` (`DATABASE_URL` é override opcional).
Importação feita: normalizador (`services/normalizer.py`), `/api/accounts`, `/api/imports/preview|{id}|{id}/confirm|DELETE {id}` (`services/import_service.py`: staging com Decimals em string, reconciliação em todas as linhas após correções, re-dedup no confirm, possíveis duplicados só gravados se listados em `incluir_possiveis_duplicados`, reversão bloqueada por importação posterior sobreposta). Migração `0003` (`ordem_ambigua`). Dinheiro na API vai sempre como string (o encoder do FastAPI converte `Decimal` de dicts em float, por isso `_s()`).
Categorização feita: `services/categorizer.py` (regras: contem/comeca_por/igual/regex, direção, montante, conta, desempate do PRD 3.5; depois histórico exato; manual nunca sobrescrito), chamada no confirm da importação. APIs: `/api/categories`, `/api/rules` (+`preview-impact`, `apply`), `/api/transactions` (filtros, paginação, `uncategorized?group_by=description`, `PATCH`, `bulk-categorize` com `criar_regra` = aprendizagem).
Analytics feito: `/api/analytics/summary|by-category|monthly` (transferências fora dos totais por omissão; despesa = montante<0).
Frontend feito (`frontend/`: React 19 + Vite + TS, CSS próprio, gráficos em SVG/HTML sem libs; páginas Dashboard, Movimentos, Por categorizar, Regras, Importar; nginx faz proxy de `/api` e serve a SPA). Paleta validada com o skill dataviz (slots 1–3, claro e escuro). `make test-frontend` corre typecheck + vitest num contentor (sem node local); o compose corre com `podman-compose`. Validado a ver a UI com Chromium headless num contentor (capturas e interações), não há testes automáticos de UI.
Dois utilizadores feito: contas com `titular_id` (None = conjunta), `GET /api/users`, `PATCH /api/accounts/{id}`, filtro `titular` (id ou `conjunta`) em movimentos e analytics (`api/scope.py`), `atualizado_por` nos movimentos, página Contas e seletor de titular na UI. Ambos os utilizadores veem os mesmos dados (sem papéis).
Deploy no mini-PC feito (Docker real + `tailscale serve`, 443→8080).
Saldos e vistas feitos: o saldo da conta vem da cadeia de saldos do ficheiro (sem saldo inicial introduzido à mão, de propósito: o Bankinter traz o saldo por linha), `services/balances.py` (DISTINCT ON por conta), `summary.saldo` fecha ao cêntimo (inicio + receitas − despesas ± transferências = fim, com `diferenca`), `monthly?granularidade=mes|ano` (campo `periodos`), `category-matrix`, `/api/coverage` (buracos = `saldo_anterior + montante ≠ saldo_apos`) e avisos de continuidade nos dois lados do ficheiro no preview (nunca bloqueiam). O dashboard separa «Saldo da conta» de «Poupança do período» (receitas − despesas).
Usabilidade: o estado do dashboard (modo, mês/ano, transferências, titular) vive no URL (`useSearchParams`, `replace`), por isso «Voltar» e recarregar mantêm a vista; clicar numa barra abre `/movimentos` com o mesmo período/filtros (`so_despesas`, `transf`, `data_de/ate`) e chips para os remover. Passagens de usabilidade são scripts puppeteer num contentor node (ver histórico), sem testes automáticos de UI.
Categorizar em lote (fluxo principal do utilizador: importar o ano todo e categorizar uma vez cada comerciante): em «Por categorizar» a regra aplica-se por omissão a TODAS as linhas já importadas (`aplicar_retroativamente=true`; manuais nunca são tocados); `POST /api/rules/preview-impact?linhas=N` devolve as linhas afetadas antes de clicar; `bulk-categorize` aceita `excluir_ids` e devolve `alteradas` (com o estado anterior) e `regra`; `POST /api/transactions/restore` desfaz tudo e apaga a regra criada. O painel «Última ação» permite corrigir linha a linha.
Por fazer: CSV anonimizado da esposa (confirmar se o layout é igual ao do Bankinter; senão adaptar parser/mapeamento), backup (só quando a release estiver estável), parser XLSX se o Bankinter o exportar, UI em ecrãs pequenos (verificada a 390 px com Chromium headless: sem scroll horizontal; Movimentos passa a «cartões» abaixo de 700 px; falta ver Regras/Importar com mais atenção). Fase 2: fuzzy/ML, splits, tags, deteção de transferências.

## Commands

- `make test` — pytest em `backend/` (usa `backend/.venv`; a máquina é Fedora atómica com Podman, sem docker; `podman-compose` está em `backend/.venv/bin`, usar `make up COMPOSE="podman compose"` com esse bin no PATH).
- `make test-db` — corre toda a suite, incluindo testes com BD, contra um Postgres descartável (`TEST_DATABASE_URL`); `make test` salta os testes com BD.
- `make lint` — ruff.
- `make create-user USERNAME=joao NOME="João"` — cria o utilizador dentro do contentor (pede a password).
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
