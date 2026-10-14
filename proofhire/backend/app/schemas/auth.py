"""Request and response models for /auth/* (guidebook Section 5.4 and B4).

    POST /auth/register  {email, password (8-72), display_name (1-100)}
    POST /auth/login     {email, password}
    both answer          {access_token, token_type: "bearer", user: {id, email, display_name, role}}
    GET  /auth/me        {id, email, display_name, role}

Only the documented fields exist. Unknown fields in a request body (for example
a "role") are ignored, so a caller can never choose their own role.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES, password_byte_length

# Same simple pattern the guidebook uses for contact_email (Section 5.2).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalise_email(value: object) -> object:
    """Trim and lower-case before validation (B4: "lower-case email")."""
    return value.strip().lower() if isinstance(value, str) else value


class RegisterRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=72)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("email", mode="before")
    @classmethod
    def _email_before(cls, v: object) -> object:
        return _normalise_email(v)

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("must be a valid email address")
        return v

    @field_validator("display_name", mode="before")
    @classmethod
    def _name_before(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("password")
    @classmethod
    def _password_bytes(cls, v: str) -> str:
        # bcrypt reads at most 72 bytes; see app.core.security.
        if password_byte_length(v) > BCRYPT_MAX_BYTES:
            raise ValueError("must be at most 72 bytes when encoded as UTF-8")
        return v


class LoginRequest(BaseModel):
    # No format check on purpose: an email that does not exist and a badly
    # formed one both get the same 401 as a wrong password.
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def _email_before(cls, v: object) -> object:
        return _normalise_email(v)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: Literal["user", "admin"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut
