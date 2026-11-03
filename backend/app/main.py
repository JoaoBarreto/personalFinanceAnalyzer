from fastapi import FastAPI

from .api.routers import auth
from .config import ENABLE_DOCS

app = FastAPI(
    title="personalFinanceAnalyzer",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)
app.include_router(auth.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
