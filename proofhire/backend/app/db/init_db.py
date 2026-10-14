"""Create the eight tables with Base.metadata.create_all (decision D6, no Alembic).

Used two ways:
  * from the FastAPI lifespan startup:  init_db()
  * from the command line (backend/):   python -m app.db.init_db

create_all only creates tables that do not exist yet. It never alters an
existing table. If you change a model during development, drop the table (or
the whole local database) and run this again.

Failures raise DatabaseInitError / ConfigError with messages that never contain
passwords, tokens or SQL.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import ConfigError, get_settings
from app.db.base import Base
from app.db.session import describe_db_error, get_engine

logger = logging.getLogger("proofhire.db")

# Section 6: exactly eight tables.
EXPECTED_TABLES = (
    "users",
    "listings",
    "assessments",
    "evidence_items",
    "assessment_checklist_items",
    "entity_signals",
    "reports",
    "llm_calls",
)

# Plain-language hints for the most common MySQL failures (error numbers are
# public MySQL codes, so showing them is safe).
_HINTS = {
    2003: "MySQL is not reachable: is the server/Docker container running, and are the host and port right?",
    2005: "The database host name could not be resolved: check the host in DATABASE_URL.",
    1045: "MySQL rejected the user name or password: check DATABASE_URL (see backend/.env).",
    1044: "This MySQL user may not use that database: re-run the GRANT statements from guidebook B7.",
    1049: "The database does not exist yet: run the CREATE DATABASE statement from guidebook B7.",
}


class DatabaseInitError(RuntimeError):
    """Raised when the database cannot be reached or the tables are not right."""


def _hint(exc: BaseException) -> str:
    args = getattr(getattr(exc, "orig", None), "args", None)
    code = args[0] if args and isinstance(args[0], int) else None
    return _HINTS.get(code, "") if code is not None else ""


def missing_tables() -> list[str]:
    """Names from EXPECTED_TABLES that do not exist in the database."""
    existing = set(inspect(get_engine()).get_table_names())
    return [t for t in EXPECTED_TABLES if t not in existing]


def init_db() -> tuple[str, ...]:
    """Create any missing tables and verify all eight exist."""
    # Importing the models registers them on Base.metadata. Without this import
    # create_all would silently create nothing.
    from app.db import models  # noqa: F401

    registered = set(Base.metadata.tables)
    if registered != set(EXPECTED_TABLES):
        raise DatabaseInitError(
            "Model/table mismatch: registered "
            f"{sorted(registered)} but Section 6 requires {sorted(EXPECTED_TABLES)}"
        )

    where = get_settings().safe_database_url  # password already masked
    try:
        Base.metadata.create_all(get_engine())
        missing = missing_tables()
    except SQLAlchemyError as exc:
        hint = _hint(exc)
        raise DatabaseInitError(
            f"Could not initialise the database at {where}: {describe_db_error(exc)}."
            + (f" {hint}" if hint else "")
        ) from None

    if missing:
        raise DatabaseInitError(f"Tables still missing after create_all: {', '.join(missing)}")

    logger.info("Database ready at %s (%d tables)", where, len(EXPECTED_TABLES))
    return EXPECTED_TABLES


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        tables = init_db()
    except (ConfigError, DatabaseInitError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {len(tables)} tables present: {', '.join(tables)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
