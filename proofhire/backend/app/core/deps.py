"""Reusable FastAPI dependencies (guidebook B1).

    get_db              one database session per request (defined in app.db.session)
    get_current_user    a valid Bearer JWT is required        -> User, else 401
    get_optional_user   no Authorization header -> None; a header that is present
                        must still be valid                   -> User | None, else 401
    require_admin       get_current_user + role "admin"       -> User, else 403
    verify_internal_key X-Internal-Key for the /ml POST routes

Authorisation always uses the user row in the database, never the `role` claim
inside the token. That way a demoted or deactivated account loses access at once
instead of when its token expires.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import forbidden, unauthorized
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db  # re-exported so routers import every dependency from here

__all__ = [
    "get_db",
    "get_current_user",
    "get_optional_user",
    "require_admin",
    "verify_internal_key",
]

# auto_error=False: a missing header is reported by us in the Section 5.5 shape
# (and with 401, not FastAPI's default 403). The scheme still shows up in
# Swagger as the "Authorize" button.
_bearer = HTTPBearer(auto_error=False, description="JWT from /auth/login or /auth/register")


def _user_from_token(token: str, db: Session) -> User:
    payload = decode_access_token(token)  # raises 401 for bad/expired tokens
    user = db.scalar(select(User).where(User.id == payload["user_id"]))
    # Same message as a bad token: do not reveal whether the account exists.
    if user is None or not user.is_active:
        raise unauthorized("Invalid token")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise unauthorized("Authentication required")
    return _user_from_token(credentials.credentials, db)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """For endpoints open to anonymous callers (POST /assessments, POST /reports).

    No header means anonymous. A header that is present but invalid or expired
    is an error (401), not silently treated as anonymous: otherwise someone with
    a stale token would believe their work was saved to their account.
    """
    if credentials is None:
        return None
    if not credentials.credentials:
        raise unauthorized("Invalid token")
    return _user_from_token(credentials.credentials, db)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise forbidden("Administrator access is required")
    return user


def verify_internal_key(x_internal_key: str | None = Header(default=None, alias="X-Internal-Key")) -> None:
    """Guard for the /ml POST endpoints (Section 5.4, A11).

    If INTERNAL_API_KEY is empty (local development) the check is skipped. If it
    is set, the header must match it exactly, otherwise 401.
    """
    configured = get_settings().internal_api_key
    expected = configured.get_secret_value() if configured is not None else ""
    if not expected:
        return
    if not x_internal_key or not hmac.compare_digest(x_internal_key.encode("utf-8"), expected.encode("utf-8")):
        raise unauthorized("Invalid internal key")
