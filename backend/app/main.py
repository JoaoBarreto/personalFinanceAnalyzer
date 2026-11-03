from fastapi import FastAPI

app = FastAPI(title="personalFinanceAnalyzer")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
