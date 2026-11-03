from fastapi import FastAPI

from .api.routers import accounts, analytics, auth, categories, coverage, imports, rules, transactions, users
from .config import ENABLE_DOCS

app = FastAPI(
    title="personalFinanceAnalyzer",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(imports.router)
app.include_router(categories.router)
app.include_router(rules.router)
app.include_router(transactions.router)
app.include_router(analytics.router)
app.include_router(users.router)
app.include_router(coverage.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
