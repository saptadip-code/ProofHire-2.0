"""SQLAlchemy 2.0 declarative base shared by all ORM models (guidebook Section 6).

Tables are created with Base.metadata.create_all (decision D6, no Alembic),
so every model must be imported before create_all runs (init_db.py does this).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Predictable constraint/index names. Without this MySQL invents names, which
# makes error messages and later schema comparisons harder to read.
# Names given explicitly on a model (e.g. idx_signal) always win over these.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Section 6: MySQL 8.4, InnoDB, utf8mb4, collation utf8mb4_0900_ai_ci.
# Each model passes these as table options (merged with its own indexes).
MYSQL_TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
