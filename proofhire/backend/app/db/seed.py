"""Create the first administrator from environment variables (guidebook B2, B3 step 2).

At startup, if ADMIN_EMAIL and ADMIN_PASSWORD are both set and no admin exists
yet, one admin account is created. Nothing is hardcoded: with no ADMIN_*
variables, no admin is created and the app still starts.

Safety rules:
  * An existing user with the same email is NEVER promoted to admin. Silently
    upgrading an account that someone else may have registered would be a
    privilege-escalation hole, so it is only logged.
  * The password is hashed with bcrypt and never logged. Failures are logged as
    short reasons, never with the password or the full email.
  * seed_admin() never raises: a seeding problem must not stop the API (B3).
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import BCRYPT_MAX_BYTES, hash_password, password_byte_length
from app.db.models import User
from app.db.session import describe_db_error, get_sessionmaker

logger = logging.getLogger("proofhire.seed")

# Outcomes (returned as text so tests and logs can read them).
CREATED = "created"
ADMIN_EXISTS = "admin_exists"
EMAIL_TAKEN = "email_taken"
INVALID_CONFIG = "invalid_config"
SKIPPED = "skipped_no_config"
FAILED = "failed"

ADMIN_DISPLAY_NAME = "Administrator"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_ADMIN_PASSWORD_LENGTH = 8  # same minimum as registration


def ensure_admin_user(db: Session, email: str, password: str) -> str:
    """Create the admin if no admin exists. Returns one of the outcome strings above."""
    email = email.strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 255:
        logger.error("ADMIN_EMAIL is not a valid email address; no admin created")
        return INVALID_CONFIG
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH or password_byte_length(password) > BCRYPT_MAX_BYTES:
        logger.error(
            "ADMIN_PASSWORD must be %d to %d bytes long; no admin created", MIN_ADMIN_PASSWORD_LENGTH, BCRYPT_MAX_BYTES
        )
        return INVALID_CONFIG

    if db.scalar(select(User.id).where(User.role == "admin").limit(1)) is not None:
        return ADMIN_EXISTS

    if db.scalar(select(User.id).where(User.email == email)) is not None:
        logger.warning(
            "A non-admin account already uses ADMIN_EMAIL. It was NOT promoted; "
            "use a different ADMIN_EMAIL or change that user's role in the database yourself."
        )
        return EMAIL_TAKEN

    db.add(
        User(
            email=email,
            password_hash=hash_password(password),
            display_name=ADMIN_DISPLAY_NAME,
            role="admin",
            is_active=True,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # another process created it first
        return ADMIN_EXISTS
    logger.info("Admin account created from ADMIN_EMAIL / ADMIN_PASSWORD")
    return CREATED


def seed_admin() -> str:
    """Startup hook. Reads ADMIN_EMAIL / ADMIN_PASSWORD and never raises."""
    try:
        settings = get_settings()
        if not settings.admin_email or settings.admin_password is None:
            logger.info("ADMIN_EMAIL / ADMIN_PASSWORD not set: no admin account is created")
            return SKIPPED  # no database access at all

        with get_sessionmaker()() as db:
            return ensure_admin_user(db, settings.admin_email, settings.admin_password.get_secret_value())
    except SQLAlchemyError as exc:
        logger.error("Admin bootstrap failed: %s", describe_db_error(exc))
        return FAILED
    except Exception as exc:  # noqa: BLE001 - startup must not crash
        logger.error("Admin bootstrap failed: %s", type(exc).__name__)
        return FAILED
