import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://pfa:change-me@localhost:5432/pfa")

SESSION_COOKIE = "session"
SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "14"))
# Cookie Secure por omissão (acesso via HTTPS do `tailscale serve`); desligar só em dev com http.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false"
# IPs dos proxies de confiança (nginx / tailscale serve), separados por vírgula
TRUSTED_PROXIES = {p.strip() for p in os.environ.get("TRUSTED_PROXIES", "").split(",") if p.strip()}
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "5"))
LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "300"))
