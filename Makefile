COMPOSE ?= docker compose

.PHONY: up down test lint migrate
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
