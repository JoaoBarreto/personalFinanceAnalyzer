from fastapi import FastAPI

from .api.routers import auth

app = FastAPI(title="personalFinanceAnalyzer")
app.include_router(auth.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
