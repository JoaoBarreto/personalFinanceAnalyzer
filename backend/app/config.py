import os

from sqlalchemy import URL


def _database_url() -> str:
    """DATABASE_URL (override opcional) ou construída das variáveis POSTGRES_* (escapa a password)."""
    if url := os.environ.get("DATABASE_URL"):
        return url
    return URL.create(
        "postgresql+psycopg",
        username=os.environ.get("POSTGRES_USER", "pfa"),
        password=os.environ.get("POSTGRES_PASSWORD", "change-me"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "pfa"),
    ).render_as_string(hide_password=False)


DATABASE_URL = _database_url()
# /docs, /redoc e /openapi.json desligados por omissão (a app é privada)
ENABLE_DOCS = os.environ.get("ENABLE_DOCS", "false").lower() == "true"

SESSION_COOKIE = "session"
SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "14"))
# Cookie Secure por omissão (acesso via HTTPS do `tailscale serve`); desligar só em dev com http.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false"
# IPs dos proxies de confiança (nginx / tailscale serve), separados por vírgula
TRUSTED_PROXIES = {p.strip() for p in os.environ.get("TRUSTED_PROXIES", "").split(",") if p.strip()}
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "5"))
LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "300"))
