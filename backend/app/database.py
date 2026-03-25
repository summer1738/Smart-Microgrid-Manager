"""Database session and lifecycle."""
from collections.abc import AsyncGenerator

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
        # Lightweight SQLite migration for adding new columns to system_settings.
        # This avoids introducing Alembic for this project.
        await conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS system_settings (id INTEGER PRIMARY KEY)"
        )
        cols = await conn.exec_driver_sql("PRAGMA table_info(system_settings)")
        existing = {row[1] for row in cols.fetchall()}  # type: ignore[index]

        def _add(col_sql: str, name: str) -> None:
            if name in existing:
                return
            # SQLite supports ADD COLUMN with a default.
            # Use IF NOT EXISTS via Python guard (older SQLite).
            return None

        # Add columns if missing
        if "auto_train_enabled" not in existing:
            await conn.exec_driver_sql("ALTER TABLE system_settings ADD COLUMN auto_train_enabled BOOLEAN DEFAULT 0")
        if "weather_forecast_enabled" not in existing:
            await conn.exec_driver_sql("ALTER TABLE system_settings ADD COLUMN weather_forecast_enabled BOOLEAN DEFAULT 1")
        if "weather_latitude" not in existing:
            await conn.exec_driver_sql("ALTER TABLE system_settings ADD COLUMN weather_latitude FLOAT DEFAULT -17.8")
        if "weather_longitude" not in existing:
            await conn.exec_driver_sql("ALTER TABLE system_settings ADD COLUMN weather_longitude FLOAT DEFAULT 31.05")
        if "weather_pv_capacity_kw" not in existing:
            await conn.exec_driver_sql("ALTER TABLE system_settings ADD COLUMN weather_pv_capacity_kw FLOAT DEFAULT 1.0")
        if "weather_panel_derate" not in existing:
            await conn.exec_driver_sql("ALTER TABLE system_settings ADD COLUMN weather_panel_derate FLOAT DEFAULT 0.85")


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
