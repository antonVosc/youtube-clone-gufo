from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

if settings.db_null_pool:
    _kw = {"poolclass": NullPool}
else:
    _kw = {}

engine = create_async_engine(settings.database_url, pool_pre_ping=True, **_kw)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session():
    async with SessionLocal() as session:
        yield session


__all__ = ["AsyncSession", "Base", "SessionLocal", "engine", "get_session"]
