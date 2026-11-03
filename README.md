# personalFinanceAnalyzer

WebApp self-hosted (Docker Compose) para importar extratos bancários (CSV/XLSX do Bankinter), reconciliar saldos, categorizar movimentos com regras locais e ver um dashboard. Todos os dados ficam na máquina do utilizador, sem APIs externas.

Especificação completa: [PersonalFinances.md](PersonalFinances.md).

## Estado

Em arranque. O MVP é para um único utilizador (Bankinter). Suporte a segundo utilizador e a outros bancos fica para depois, e o backup só entra quando a release estiver estável.

## Stack

Frontend: React + Vite + TypeScript. Backend: Python 3.12 + FastAPI + SQLAlchemy + Alembic. Base de dados: PostgreSQL 16.

## Desenvolvimento

Ainda sem código. Quando existir:

```bash
cp .env.example .env   # preencher os valores
docker compose up
```

## Dados e privacidade

Extratos reais e ficheiros de dados nunca vão para o repositório (ver `.gitignore`). Os fixtures de teste têm de estar anonimizados e vivem em `backend/tests/fixtures/`.
