"""Password hashing, JWT helpers and owner-token helpers (guidebook B1, B5, D7).

* Passwords: bcrypt only, never stored or logged in plain text. Cost comes from
  BCRYPT_ROUNDS (12 locally, 10 on the Render free CPU, B5).
* Tokens: JWT, HS256, signed with JWT_SECRET from the environment. Claims are
  `sub` (user id as text), `role`, `iat` and `exp`.
* Owner tokens: random 32-character strings given once to anonymous callers.
  Only their SHA-256 hash is stored (assessments.owner_token_hash).

Nothing here touches the database or FastAPI, so it is easy to test.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.errors import AppError, unauthorized

logger = logging.getLogger("proofhire.security")

JWT_ALGORITHM = "HS256"  # D7: the only algorithm we sign or accept

# bcrypt only looks at the first 72 BYTES of a password. A longer password would
# be silently cut (or rejected, depending on the library version), so we refuse
# it explicitly instead. Section 5.4 says "8-72"; we apply that limit in bytes
# because a multi-byte character (for example an accented letter) is more than
# one byte.
BCRYPT_MAX_BYTES = 72


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def password_byte_length(password: str) -> int:
    return len(password.encode("utf-8"))


def hash_password(password: str) -> str:
    """Return a bcrypt hash (text, starts with "$2"). Raises ValueError if over 72 bytes."""
    raw = password.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        raise ValueError("password is longer than 72 bytes")
    salt = bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)
    return bcrypt.hashpw(raw, salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """True only if `password` matches the bcrypt hash. Never raises."""
    raw = password.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        return False  # could never have been stored, so it cannot match
    try:
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        return False  # malformed hash in the database


_dummy_hash: str | None = None


def get_dummy_hash() -> str:
    """A throw-away bcrypt hash used when a login email is unknown.

    Login still runs one bcrypt check in that case, so "unknown email" and
    "wrong password" take about the same time (no account-guessing by timing).
    Built on first use so importing this module stays fast.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_urlsafe(16))
    return _dummy_hash


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
def _jwt_secret() -> str:
    secret = get_settings().jwt_secret
    value = secret.get_secret_value() if secret is not None else ""
    if not value:
        # A server mistake, not the caller's: standard error shape, no detail.
        logger.error("JWT_SECRET is not set; authentication cannot work (see backend/.env.example)")
        raise AppError("internal_error", "Authentication is not configured on the server", 500)
    return value


def create_access_token(user_id: int, role: str, *, expires_minutes: int | None = None) -> str:
    """Sign a JWT for a user. `expires_minutes` defaults to JWT_EXPIRE_MINUTES (1440)."""
    settings = get_settings()
    minutes = settings.jwt_expire_minutes if expires_minutes is None else expires_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),  # JWT subjects are text
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Verify signature, algorithm and expiry. Returns {"user_id": int, "role": str}.

    Raises AppError 401 (Section 5.5 `unauthorized`) for anything wrong. The
    algorithm list is fixed to HS256, so a token that claims "alg: none" or any
    other algorithm is rejected.
    """
    secret = _jwt_secret()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        user_id = int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise unauthorized("Token has expired") from None
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise unauthorized("Invalid token") from None
    role = payload.get("role")
    return {"user_id": user_id, "role": role if isinstance(role, str) else None}


# --------------------------------------------------------------------------
# Owner tokens (anonymous assessments; used from the assessments phase)
# --------------------------------------------------------------------------
def generate_owner_token() -> str:
    """32 URL-safe random characters (24 random bytes)."""
    return secrets.token_urlsafe(24)


def hash_owner_token(token: str) -> str:
    """SHA-256 hex digest (64 characters), what assessments.owner_token_hash stores."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def owner_token_matches(token: str | None, stored_hash: str | None) -> bool:
    """Constant-time check of a presented owner token against the stored hash."""
    if not token or not stored_hash:
        return False
    return hmac.compare_digest(hash_owner_token(token), stored_hash)
