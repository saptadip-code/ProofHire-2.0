"""Standard error responses (guidebook Section 5.5, B1, B5).

Every non-2xx response has this exact shape:

    {"error": {"code": "...", "message": "...", "fields": [{"field": "...", "message": "..."}]}}

`fields` is always present (an empty list when there is nothing to point at),
so the frontend can rely on it. Responses never contain stack traces, SQL,
input values or secrets.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.db.session import describe_db_error

logger = logging.getLogger("proofhire.errors")

# Section 5.5 codes by HTTP status.
_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    503: "model_unavailable",
    500: "internal_error",
}


class AppError(Exception):
    """Raise this anywhere (routers, services, deps) to produce a 5.5 response."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int,
        fields: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.fields = fields or []
        self.headers = headers


# Shortcuts so call sites read like the Section 5.5 table.
def bad_request(message: str, fields: list[dict[str, str]] | None = None) -> AppError:
    return AppError("bad_request", message, 400, fields)


def unauthorized(message: str = "Authentication required") -> AppError:
    return AppError("unauthorized", message, 401, headers={"WWW-Authenticate": "Bearer"})


def forbidden(message: str = "You do not have permission to do this") -> AppError:
    return AppError("forbidden", message, 403)


def not_found(message: str = "Not found") -> AppError:
    return AppError("not_found", message, 404)


def conflict(message: str) -> AppError:
    return AppError("conflict", message, 409)


def rate_limited(message: str = "Too many requests, please try again shortly") -> AppError:
    return AppError("rate_limited", message, 429)


def model_unavailable(message: str = "The risk model is not available right now") -> AppError:
    return AppError("model_unavailable", message, 503)


def error_body(code: str, message: str, fields: list[dict[str, str]] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "fields": fields or []}}


def _json(status: int, code: str, message: str, fields=None, headers=None) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, fields), headers=headers)


# --------------------------------------------------------------------------
# Validation errors (422)
# --------------------------------------------------------------------------
def format_validation_errors(errors: list[dict]) -> tuple[str, list[dict[str, str]]]:
    """Turn Pydantic/FastAPI error dicts into (message, fields).

    Only the location and the message are used. The submitted value (`input`)
    is never copied, because it may be a password or other private data.
    """
    fields: list[dict[str, str]] = []
    for err in errors:
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "header")]
        field = ".".join(loc) or "body"
        msg = str(err.get("msg", "invalid value"))
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        fields.append({"field": field, "message": msg})

    if len(fields) == 1:
        f0, m0 = fields[0]["field"], fields[0]["message"]
        message = m0 if m0.startswith(f0) else f"{f0}: {m0}"  # avoids "salary_max: salary_max must..."
    else:
        message = f"Validation failed for {len(fields)} fields"
    return message, fields


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------
async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return _json(exc.status, exc.code, exc.message, exc.fields, exc.headers)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    # A body that is not JSON at all is "malformed input not caught by schema" -> 400.
    if any(e.get("type") == "json_invalid" for e in errors):
        return _json(400, "bad_request", "Request body is not valid JSON")
    message, fields = format_validation_errors(errors)
    return _json(422, "validation_error", message, fields)


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Unknown routes (404), wrong methods (405) and other framework errors."""
    status = exc.status_code
    code = _CODE_BY_STATUS.get(status, "bad_request" if status < 500 else "internal_error")
    message = "Not found" if status == 404 else (str(exc.detail) if status < 500 else "Server error")
    return _json(status, code, message, headers=getattr(exc, "headers", None))


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # Full detail goes to the server log only. Database errors are logged as
    # class + MySQL error number because driver messages can echo SQL or hosts.
    if isinstance(exc, SQLAlchemyError):
        logger.error("Unhandled database error on %s %s: %s", request.method, request.url.path, describe_db_error(exc))
    else:
        logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)

    message = "An unexpected error occurred"
    if not get_settings().is_prod:
        message += f" ({type(exc).__name__})"  # class name only, helps while developing
    return _json(500, "internal_error", message)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
