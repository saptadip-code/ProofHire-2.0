"""Settings loading and secret handling. No database needed."""

from __future__ import annotations

import pytest

from app.core import config
from app.core.config import ConfigError, Settings
from app.db.session import describe_db_error

GOOD_URL = "mysql+pymysql://proofhire:SECRETPW@localhost:3306/proofhire?charset=utf8mb4"


def test_defaults_and_cors_split():
    s = Settings.model_validate({"database_url": GOOD_URL, "cors_origins": "http://a.com/, http://b.com"})
    assert s.env == "dev"
    assert s.cors_origins == ["http://a.com", "http://b.com"]
    assert s.db_pool_size == 3 and s.db_max_overflow == 2 and s.db_pool_recycle == 280


def test_password_is_masked_everywhere():
    s = Settings.model_validate({"database_url": GOOD_URL})
    assert "SECRETPW" not in repr(s)
    assert "SECRETPW" not in str(s)
    assert "SECRETPW" not in s.safe_database_url
    assert "SECRETPW" in s.database_url_str  # only the engine factory reads the real one


@pytest.mark.parametrize(
    "url",
    ["postgresql://u:SECRETPW@h/db", "mysql+pymysql://u:SECRETPW@h:3306/", "not a url SECRETPW"],
)
def test_bad_database_url_rejected_without_leaking(url, monkeypatch, tmp_path):
    # Settings.from_env is the only path the app uses; it reports variable names
    # and reasons, never the submitted value. (Pydantic's own ValidationError text
    # would echo the input, which is exactly why from_env rewrites it.)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ConfigError) as info:
        Settings.from_env()
    assert "DATABASE_URL" in str(info.value)
    assert "SECRETPW" not in str(info.value)


def test_prod_rejects_localhost_cors_wildcard_and_weak_jwt():
    base = {"database_url": GOOD_URL, "env": "prod", "jwt_secret": "x" * 40}
    with pytest.raises(Exception):
        Settings.model_validate({**base, "cors_origins": "http://localhost:5173"})
    with pytest.raises(Exception):
        Settings.model_validate({**base, "cors_origins": "*"})
    with pytest.raises(Exception):
        Settings.model_validate({**base, "cors_origins": "https://app.example.com", "jwt_secret": "short"})
    ok = Settings.model_validate({**base, "cors_origins": "https://app.example.com"})
    assert ok.is_prod


def test_from_env_reads_environment_and_ignores_missing_dotenv(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("DATABASE_URL", GOOD_URL)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("ENV", "dev")
    s = Settings.from_env()
    assert s.database_url_str == GOOD_URL


def test_from_env_without_database_url_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError) as info:
        Settings.from_env()
    assert "DATABASE_URL" in str(info.value)


def test_from_env_error_names_variable_but_not_value(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:SECRETPW@h/db")
    with pytest.raises(ConfigError) as info:
        Settings.from_env()
    assert "DATABASE_URL" in str(info.value)
    assert "SECRETPW" not in str(info.value)


def test_describe_db_error_reports_class_and_mysql_number_only():
    from sqlalchemy.exc import OperationalError

    exc = OperationalError("SELECT 1", {}, Exception(1045, "Access denied for user 'x'@'h' (using password: SECRETPW)"))
    text = describe_db_error(exc)
    assert text == "OperationalError (MySQL error 1045)"
    assert "SECRETPW" not in text
