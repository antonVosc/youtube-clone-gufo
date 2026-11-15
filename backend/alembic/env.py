from alembic import context
from app import models
from app.config import settings
from app.db import Base
from sqlalchemy import create_engine

target_metadata = Base.metadata
url = settings.database_url.replace("+asyncpg", "+psycopg2")


def run_migrations_online():
    engine = create_engine(url)

    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
