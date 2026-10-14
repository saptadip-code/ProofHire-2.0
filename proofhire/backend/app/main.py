"""FastAPI application factory and lifespan (guidebook B1, B3, B5).

Run from backend/:   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
Swagger UI:          http://localhost:8000/docs
Health:              http://localhost:8000/api/v1/health

Startup (B3):
  1. Read settings (a bad .env stops the app with a clear message, no secrets).
  2. Create the eight tables with Base.metadata.create_all.
  3. Create the first admin from ADMIN_EMAIL / ADMIN_PASSWORD if none exists.
  4. Call app.ml.pipeline.load_model() if Member 1's package exists.
  5. Log Python, FastAPI, scikit-learn and model versions.

A database or model failure at startup is logged and the app keeps running:
GET /health then reports status "degraded" with db/model_loaded false instead
of the process crashing (B3, B4).
"""

from __future__ import annotations

import logging
import platform
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import metadata

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import APP_VERSION, get_settings
from app.core.errors import register_exception_handlers
from app.db.init_db import DatabaseInitError, init_db
from app.db.seed import seed_admin
from app.db.session import dispose_engine
from app.routers import admin, assessments, auth, dashboard, health, ml, reports

logger = logging.getLogger("proofhire.main")

API_PREFIX = "/api/v1"


def _version_of(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "not installed"


def _load_model() -> str | None:
    """Call Member 1's load_model(); return the model version or None.

    The ML package is owned by Member 1 (change C2), so this only calls the
    documented interface. If the package is missing or raises, the app keeps
    running and /health reports model_loaded=false (B3).
    """
    try:
        from app.ml import pipeline  # Member 1's public interface
    except ImportError:
        logger.warning("app.ml.pipeline is not available yet: model not loaded")
        return None
    except Exception as exc:  # noqa: BLE001 - startup must not crash on ML code
        logger.error("Importing app.ml.pipeline failed: %s", type(exc).__name__)
        return None

    try:
        pipeline.load_model()
        status = pipeline.model_status()
    except Exception as exc:  # noqa: BLE001
        logger.error("Model load failed: %s (continuing; /health will show model_loaded=false)", type(exc).__name__)
        return None

    if isinstance(status, dict) and status.get("loaded"):
        version = status.get("model_version")
        return version if isinstance(version, str) else None
    return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.getLogger("proofhire").setLevel(logging.INFO)

    # B3 step 1: tables. init_db() is blocking, but runs once before serving.
    db_ready = False
    try:
        init_db()
        db_ready = True
    except DatabaseInitError as exc:
        # Message is already secret-free (password masked, no SQL). The app
        # stays up so /health can report db:false and the cause is in the log.
        logger.error("Startup: database not ready: %s", exc)

    # B3 step 2: first admin (only if the tables exist). Never raises.
    if db_ready:
        seed_admin()

    if settings.jwt_secret is None:
        logger.warning("JWT_SECRET is not set: /auth/register and /auth/login will fail until it is (see .env.example)")

    # B3 step 3: model.
    model_version = _load_model()

    # B3 step 4: versions.
    logger.info(
        "ProofHire API %s started: env=%s python=%s fastapi=%s sqlalchemy=%s scikit-learn=%s model_version=%s",
        APP_VERSION,
        settings.env,
        platform.python_version(),
        _version_of("fastapi"),
        _version_of("SQLAlchemy"),
        _version_of("scikit-learn"),
        model_version or "none",
    )

    yield

    dispose_engine()
    logger.info("ProofHire API stopped")


def create_app() -> FastAPI:
    settings = get_settings()  # fails fast with a readable ConfigError

    app = FastAPI(
        title="ProofHire API",
        version=APP_VERSION,
        description="ProofHire gives a risk estimate, not a verification of the employer.",
        lifespan=lifespan,
    )

    # CORS comes from CORS_ORIGINS (B5). Never '*' in prod (config.py enforces it).
    # allow_headers=['*'] covers Authorization and X-Owner-Token.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(assessments.router)
    api.include_router(reports.router)
    api.include_router(admin.router)
    api.include_router(dashboard.router)
    app.include_router(api)

    # AI/ML-owned endpoints coexist with the backend API under the frozen prefix.
    app.include_router(ml.router, prefix=f"{API_PREFIX}/ml", tags=["ml"])

    return app


app = create_app()
