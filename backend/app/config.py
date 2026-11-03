import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://pfa:change-me@localhost:5432/pfa")
