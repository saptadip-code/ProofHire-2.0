"""Application settings (guidebook B1/B2).

Plain pydantic BaseModel + os.environ; python-dotenv loads backend/.env for
local development. Real environment variables always win over the .env file.
Secrets are SecretStr and are never printed or included in error messages.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator, model_validator
from sqlalchemy.engine import make_url

# backend/app/core/config.py -> parents[2] == backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"

LOCAL_DEFAULT_CORS = ["http://localhost:5173"]
APP_VERSION = "1.0.0"  # reported by GET /health


class ConfigError(RuntimeError):
    """Raised when settings are missing/invalid. Message never contains secrets."""


class Settings(BaseModel):
    env: Literal["dev", "prod"] = "dev"

    # Database (B2). No default: a missing URL must fail loudly.
    database_url: SecretStr
    db_ssl_ca: str | None = None  # e.g. certs/aiven-ca.pem (relative to backend/)
    db_pool_size: int = 3
    db_max_overflow: int = 2
    db_pool_recycle: int = 280
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    db_echo: bool = False

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: list(LOCAL_DEFAULT_CORS))

    # Listed in B2; used from later phases (auth, ML internal key, admin seed).
    jwt_secret: SecretStr | None = None
    jwt_expire_minutes: int = Field(default=1440, ge=1)
    bcrypt_rounds: int = Field(default=12, ge=4, le=15)  # B5: 12 (10 on Render free CPU)
    internal_api_key: SecretStr | None = None
    admin_email: str | None = None
    admin_password: SecretStr | None = None

    # ---- validators (messages never echo the offending value) -------------
    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value().strip()
        try:
            url = make_url(raw)
        except Exception:
            raise ValueError("DATABASE_URL is not a valid SQLAlchemy URL") from None
        if url.drivername != "mysql+pymysql":
            raise ValueError("DATABASE_URL must start with mysql+pymysql://")
        if not url.database:
            raise ValueError("DATABASE_URL must include a database name")
        return SecretStr(raw)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return [p.strip().rstrip("/") for p in v.split(",") if p.strip()]
        return v

    @model_validator(mode="after")
    def _check_prod(self) -> "Settings":
        if self.env == "prod":
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must not contain '*' in prod")
            if any(o.startswith(("http://localhost", "http://127.0.0.1")) for o in self.cors_origins):
                raise ValueError("CORS_ORIGINS must not contain localhost in prod")
            if self.jwt_secret is None or len(self.jwt_secret.get_secret_value()) < 32:
                raise ValueError("JWT_SECRET must be set (32+ chars) in prod")
        return self

    # ---- helpers -----------------------------------------------------------
    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def database_url_str(self) -> str:
        """Real URL for create_engine(). Never log this."""
        return self.database_url.get_secret_value()

    @property
    def safe_database_url(self) -> str:
        """URL with the password masked: safe for logs and error messages."""
        try:
            return make_url(self.database_url_str).render_as_string(hide_password=True)
        except Exception:
            return "<unreadable DATABASE_URL>"

    @property
    def db_ssl_ca_path(self) -> Path | None:
        if not self.db_ssl_ca:
            return None
        p = Path(self.db_ssl_ca)
        return p if p.is_absolute() else BACKEND_DIR / p

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(ENV_FILE, override=False)  # real env vars win over .env
        e = os.environ

        def opt(name: str) -> str | None:
            val = e.get(name)
            return val.strip() if val and val.strip() else None

        raw: dict[str, object] = {}
        mapping = {
            "env": "ENV", "database_url": "DATABASE_URL", "db_ssl_ca": "DB_SSL_CA",
            "cors_origins": "CORS_ORIGINS", "jwt_secret": "JWT_SECRET",
            "jwt_expire_minutes": "JWT_EXPIRE_MINUTES", "bcrypt_rounds": "BCRYPT_ROUNDS",
            "internal_api_key": "INTERNAL_API_KEY",
            "admin_email": "ADMIN_EMAIL", "admin_password": "ADMIN_PASSWORD",
            "db_echo": "DB_ECHO",
        }
        for field, var in mapping.items():
            val = opt(var)
            if val is not None:
                raw[field] = val
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            # Report variable names and reasons only; never the input values.
            problems = []
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"]) or "settings"
                var = mapping.get(loc, loc).upper() if loc in mapping else loc.upper()
                problems.append(f"{var}: {err['msg']}")
            raise ConfigError(
                "Invalid configuration (check backend/.env): " + "; ".join(problems)
            ) from None


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
