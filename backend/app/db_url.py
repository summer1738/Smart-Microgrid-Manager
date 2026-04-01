"""Helpers for working with SQLAlchemy database URLs."""

from __future__ import annotations


def to_sync_database_url(url: str) -> str:
    """
    Convert async MySQL SQLAlchemy URLs to a sync variant for CLI/scripts.
    Example:
      mysql+aiomysql://user:pass@host/db -> mysql+pymysql://user:pass@host/db
    """
    out = str(url)
    if out.startswith("mysql+aiomysql://"):
        return out.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
    return out

