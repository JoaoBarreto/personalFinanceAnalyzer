# personalFinanceAnalyzer

WebApp self-hosted (Docker Compose) para importar extratos bancários (CSV/XLSX do Bankinter), reconciliar saldos, categorizar movimentos com regras locais e ver um dashboard. Todos os dados ficam na máquina do utilizador, sem APIs externas.

Especificação completa: [PersonalFinances.md](PersonalFinances.md).

## Estado

Em arranque. O MVP é para um único utilizador (Bankinter). Suporte a segundo utilizador e a outros bancos fica para depois, e o backup só entra quando a release estiver estável.

## Stack

Frontend: React + Vite + TypeScript. Backend: Python 3.12 + FastAPI + SQLAlchemy + Alembic. Base de dados: PostgreSQL 16.

## Desenvolvimento

Estado atual: parser Bankinter CSV (com reconciliação por cadeia de saldos), deduplicação (função pura), modelos SQLAlchemy, migrações (esquema + seed de categorias) `/api/health` e login (sessões, CSRF). Ainda não há importação (preview/confirm), regras nem frontend.

```bash
cp .env.example .env                      # preencher os valores
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e "backend[dev]"
make test                                 # pytest (parser, dedup; salta os testes com BD)
make test-db                              # idem + testes com BD num Postgres descartável
make lint                                 # ruff
make up                                   # docker compose (backend + db); o frontend ainda não existe
make up COMPOSE="podman compose"          # em máquinas só com Podman (precisa de podman-compose no PATH)
```

Primeiro utilizador: `make up` e depois `make create-user USERNAME=joao NOME="João"`. Em http sem TLS pôr `COOKIE_SECURE=false` no `.env` (com `tailscale serve` deixar `true`).

Migrações: `cd backend && DATABASE_URL=... .venv/bin/alembic upgrade head`. O contentor do backend corre-as ao arrancar.

O `docker-compose.yml` foi testado com `podman-compose` (db + backend, migrações e seed aplicados, `/api/health` a responder). Com Docker propriamente dito não foi testado.

## Dados e privacidade

Extratos reais e ficheiros de dados nunca vão para o repositório (ver `.gitignore`). Os fixtures de teste têm de estar anonimizados e vivem em `backend/tests/fixtures/`.
