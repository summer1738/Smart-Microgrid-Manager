"""Database session and lifecycle."""
from collections.abc import AsyncGenerator

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base

engine = create_async_engine(
    settings.database_url,
    echo=False,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_lightweight_migrations)


def _run_lightweight_migrations(sync_conn) -> None:
    """
    Lightweight additive migrations for existing MySQL tables.
    """
    insp = inspect(sync_conn)
    if "appliances" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("appliances")}
    if "usage_mode" not in cols:
        sync_conn.exec_driver_sql(
            "ALTER TABLE appliances ADD COLUMN usage_mode VARCHAR(20) NOT NULL DEFAULT 'scheduled'"
        )
    if "default_run_minutes" not in cols:
        sync_conn.exec_driver_sql(
            "ALTER TABLE appliances ADD COLUMN default_run_minutes INTEGER NOT NULL DEFAULT 30"
        )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
