"""Section 5.5 error format, using a small throw-away app so Phase 1 needs no real routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.errors import AppError, conflict, error_body, register_exception_handlers


class Body(BaseModel):
    title: str = Field(min_length=3)
    password: str = Field(min_length=8)


@pytest.fixture()
def mini():
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/echo")
    def echo(body: Body):
        return {"ok": True}

    @app.get("/app-error")
    def app_error():
        raise conflict("Email already registered")

    @app.get("/custom")
    def custom():
        raise AppError("forbidden", "Not owner", 403)

    @app.get("/crash")
    def crash():
        raise RuntimeError("secret-connection-string-should-not-leak")

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_error_body_shape():
    assert error_body("x", "msg") == {"error": {"code": "x", "message": "msg", "fields": []}}


def test_app_error_is_rendered(mini):
    r = mini.get("/app-error")
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "conflict", "message": "Email already registered", "fields": []}}


def test_custom_app_error(mini):
    r = mini.get("/custom")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_validation_error_is_422_with_fields_and_never_echoes_input(mini):
    r = mini.post("/echo", json={"title": "ab", "password": "SECRET"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert {f["field"] for f in err["fields"]} == {"title", "password"}
    assert all(set(f) == {"field", "message"} for f in err["fields"])
    assert "SECRET" not in r.text


def test_single_validation_error_message_names_the_field(mini):
    r = mini.post("/echo", json={"title": "ab", "password": "long-enough-pw"})
    err = r.json()["error"]
    assert err["fields"] == [{"field": "title", "message": err["fields"][0]["message"]}]
    assert err["message"].startswith("title: ")


def test_malformed_json_is_400_bad_request(mini):
    r = mini.post("/echo", content="{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


def test_wrong_method_uses_error_shape(mini):
    r = mini.get("/echo")
    assert r.status_code == 405
    assert set(r.json()["error"]) == {"code", "message", "fields"}


def test_unexpected_exception_is_500_without_details(mini):
    r = mini.get("/crash")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret-connection-string" not in r.text
    assert "Traceback" not in r.text
