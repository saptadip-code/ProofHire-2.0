"""POST /auth/register, POST /auth/login, GET /auth/me (guidebook B4).

These are plain `def` routes on purpose: bcrypt is slow and blocking, and
FastAPI runs `def` routes in a worker thread so the event loop is not stalled.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.errors import conflict, unauthorized
from app.core.security import create_access_token, get_dummy_hash, hash_password, verify_password
from app.db.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

logger = logging.getLogger("proofhire.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

# One message for unknown email, wrong password and disabled account (B4).
_BAD_LOGIN = "Invalid email or password"


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    summary="Create an account (role is always 'user')",
)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.scalar(select(User.id).where(User.email == body.email)) is not None:
        raise conflict("An account with this email already exists")

    user = User(
        email=body.email,  # already trimmed and lower-cased by the schema
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role="user",  # never taken from the request
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two registrations with the same email raced past the check above;
        # the UNIQUE index on users.email caught the second one.
        db.rollback()
        raise conflict("An account with this email already exists") from None
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse, summary="Log in and receive a JWT")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email))
    # Always run exactly one bcrypt check, so an unknown email takes about as
    # long as a wrong password.
    password_ok = verify_password(body.password, user.password_hash if user else get_dummy_hash())
    if user is None or not password_ok or not user.is_active:
        raise unauthorized(_BAD_LOGIN)
    return _token_response(user)


@router.get("/me", response_model=UserOut, summary="The signed-in user")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
