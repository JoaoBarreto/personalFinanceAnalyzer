from sqlalchemy import create_engine

import app.models  # noqa: F401  (regista as tabelas)
from alembic import context
from app.config import DATABASE_URL
from app.db import Base

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with create_engine(DATABASE_URL).connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


(run_migrations_offline if context.is_offline_mode() else run_migrations_online)()
