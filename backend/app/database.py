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
    tables = insp.get_table_names()
    if "users" in tables:
        user_cols = {c["name"] for c in insp.get_columns("users")}
        if "username" not in user_cols:
            sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN username VARCHAR(64) NULL")
        if "password_hash" not in user_cols:
            sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL")
        if "is_active" not in user_cols:
            sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE")
        user_indexes = {idx["name"] for idx in insp.get_indexes("users")}
        user_unique_constraints = {
            tuple(col for col in constraint.get("column_names", []) if col)
            for constraint in insp.get_unique_constraints("users")
        }
        if "ix_users_username" not in user_indexes and ("username",) not in user_unique_constraints:
            sync_conn.exec_driver_sql("CREATE UNIQUE INDEX ix_users_username ON users (username)")

    if "appliances" not in tables:
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
    if "manual_override_active" not in cols:
        sync_conn.exec_driver_sql(
            "ALTER TABLE appliances ADD COLUMN manual_override_active BOOLEAN NOT NULL DEFAULT FALSE"
        )

    if "system_settings" in tables:
        sys_cols = {c["name"] for c in insp.get_columns("system_settings")}
        if "auto_ieba_enabled" not in sys_cols:
            sync_conn.exec_driver_sql(
                "ALTER TABLE system_settings ADD COLUMN auto_ieba_enabled BOOLEAN NOT NULL DEFAULT FALSE"
            )
        if "auto_ieba_interval_minutes" not in sys_cols:
            sync_conn.exec_driver_sql(
                "ALTER TABLE system_settings ADD COLUMN auto_ieba_interval_minutes INTEGER NOT NULL DEFAULT 60"
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
