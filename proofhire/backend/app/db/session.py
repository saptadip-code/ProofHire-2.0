"""Engine and session handling (guidebook B2/B5).

The engine is created lazily, on first use, so importing this module never
needs a database. Small pool because the free MySQL and free web service have
tight limits: pool_size=3, max_overflow=2, pool_pre_ping=True, pool_recycle=280.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import ConfigError, get_settings

logger = logging.getLogger("proofhire.db")


def describe_db_error(exc: BaseException) -> str:
    """Short, secret-free description of a database failure.

    Only the exception class and the MySQL error number are reported. The full
    message is left out on purpose because drivers can echo hosts, users or SQL.
    """
    parts = [type(exc).__name__]
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", None)
    if args and isinstance(args[0], int):
        parts.append(f"MySQL error {args[0]}")
    return " ".join(parts[:1]) + (f" ({parts[1]})" if len(parts) > 1 else "")


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    connect_args: dict = {
        "connect_timeout": settings.db_connect_timeout_seconds,
        # Section 6: timestamps are UTC. CURRENT_TIMESTAMP(3) follows the
        # session time zone, so pin every connection to UTC.
        "init_command": "SET time_zone = '+00:00'",
    }

    ca_path = settings.db_ssl_ca_path
    if ca_path is not None:
        if not ca_path.is_file():
            raise ConfigError(f"DB_SSL_CA file not found: {ca_path}")
        connect_args["ssl"] = {"ca": str(ca_path)}  # B2

    return create_engine(
        settings.database_url_str,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle,
        echo=settings.db_echo,
        hide_parameters=True,  # keep bound values out of error messages
        connect_args=connect_args,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed.

    Routes and services decide when to commit. If anything raises, the open
    transaction is rolled back before the session is closed, so a failed
    request never leaves partial writes behind.
    """
    db = get_sessionmaker()()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_db() -> tuple[bool, str | None]:
    """Run SELECT 1. Returns (ok, safe_error_description). Never raises."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001 - health checks must not crash
        return False, describe_db_error(exc)


def dispose_engine() -> None:
    """Close pooled connections (called on shutdown) if an engine was created."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()
