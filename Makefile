COMPOSE ?= docker compose

.PHONY: up down test test-db test-frontend lint migrate create-user reset-data
up:
	$(COMPOSE) up --build -d
down:
	$(COMPOSE) down
test:
	cd backend && .venv/bin/pytest -q
lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
migrate:
	cd backend && .venv/bin/alembic upgrade head
test-db:  # testes com BD: Postgres descartável em Podman/Docker
	-docker rm -f pfa-test-db 2>/dev/null || podman rm -f pfa-test-db 2>/dev/null
	$(or $(shell command -v docker),podman) run -d --name pfa-test-db -e POSTGRES_PASSWORD=t -e POSTGRES_USER=pfa -e POSTGRES_DB=pfa -p 127.0.0.1:55432:5432 docker.io/library/postgres:16
	for i in $$(seq 30); do $(or $(shell command -v docker),podman) exec pfa-test-db pg_isready -U pfa >/dev/null 2>&1 && break; sleep 1; done; sleep 1
	cd backend && TEST_DATABASE_URL=postgresql+psycopg://pfa:t@127.0.0.1:55432/pfa .venv/bin/pytest -q; rc=$$?; $(or $(shell command -v docker),podman) rm -f pfa-test-db; exit $$rc
create-user:  # make create-user USERNAME=joao NOME="João"   (não interativo: echo pw | make create-user ... EXEC=-T ARGS=--password-stdin)
	$(COMPOSE) exec $(EXEC) backend python -m app.cli create-user $(USERNAME) --nome "$(NOME)" $(ARGS)
test-frontend:  # typecheck + vitest num contentor node (não precisa de node local)
	$(or $(shell command -v docker),podman) run --rm -v "$(CURDIR)/frontend":/app:Z -w /app docker.io/library/node:22-alpine sh -c "npm install --no-audit --no-fund && npm run typecheck && npm test"
reset-data:  # make reset-data USERNAME=joao: apaga SÓ os movimentos e importações desse utilizador; mantém categorias, regras e contas; converte categorizações manuais em regras
	$(COMPOSE) exec backend python -m app.cli reset-movements --username $(USERNAME)
