"""Password hashing, JWT and owner-token helpers. No database needed."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core import security
from app.core.config import Settings
from app.core.errors import AppError

TEST_JWT_SECRET = os.environ["JWT_SECRET"]  # set in conftest.py

GOOD_URL = "mysql+pymysql://proofhire:SECRETPW@localhost:3306/proofhire?charset=utf8mb4"


# ---------------------------------------------------------------- passwords
def test_hash_is_bcrypt_and_not_the_plain_password():
    h = security.hash_password("correct horse battery")
    assert h.startswith("$2")
    assert "correct horse battery" not in h
    assert len(h) == 60


def test_same_password_gets_different_hashes_because_of_salt():
    assert security.hash_password("same-password-1") != security.hash_password("same-password-1")


def test_verify_password_true_and_false():
    h = security.hash_password("right-password")
    assert security.verify_password("right-password", h) is True
    assert security.verify_password("wrong-password", h) is False
    assert security.verify_password("", h) is False


def test_verify_password_with_malformed_hash_returns_false_not_error():
    assert security.verify_password("anything", "not-a-bcrypt-hash") is False
    assert security.verify_password("anything", "") is False


def test_unicode_password_round_trip():
    pw = "pässwörd-🔐-ok"
    assert security.verify_password(pw, security.hash_password(pw)) is True


def test_password_limit_is_72_bytes_not_characters():
    ok = "a" * 72
    assert security.verify_password(ok, security.hash_password(ok)) is True

    too_long = "a" * 73
    with pytest.raises(ValueError):
        security.hash_password(too_long)
    assert security.verify_password(too_long, security.hash_password(ok)) is False

    # 37 two-byte characters = 37 characters but 74 bytes.
    multibyte = "é" * 37
    assert len(multibyte) == 37 and security.password_byte_length(multibyte) == 74
    with pytest.raises(ValueError):
        security.hash_password(multibyte)


def test_dummy_hash_is_a_valid_bcrypt_hash_and_is_reused():
    first = security.get_dummy_hash()
    assert first.startswith("$2")
    assert security.get_dummy_hash() == first
    assert security.verify_password("some-guess", first) is False


def test_bcrypt_cost_comes_from_settings(monkeypatch):
    s = Settings.model_validate({"database_url": GOOD_URL, "bcrypt_rounds": 5})
    monkeypatch.setattr(security, "get_settings", lambda: s)
    assert security.hash_password("cost-check-pw").startswith("$2b$05$")


# --------------------------------------------------------------------- JWT
def test_token_round_trip():
    token = security.create_access_token(42, "admin")
    assert security.decode_access_token(token) == {"user_id": 42, "role": "admin"}


def test_token_uses_hs256_and_expected_claims():
    token = security.create_access_token(7, "user")
    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    claims = jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])
    assert claims["sub"] == "7"
    assert claims["role"] == "user"
    assert {"iat", "exp"} <= set(claims)


def test_token_lifetime_defaults_to_configured_minutes():
    token = security.create_access_token(1, "user")
    claims = jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 1440 * 60


def test_expired_token_is_rejected_with_401():
    token = security.create_access_token(1, "user", expires_minutes=-5)
    with pytest.raises(AppError) as info:
        security.decode_access_token(token)
    assert info.value.status == 401
    assert info.value.code == "unauthorized"
    assert "expired" in info.value.message.lower()


@pytest.mark.parametrize("bad", ["", "garbage", "a.b.c", "x" * 200])
def test_garbage_tokens_are_rejected(bad):
    with pytest.raises(AppError) as info:
        security.decode_access_token(bad)
    assert info.value.status == 401


def test_token_signed_with_another_secret_is_rejected():
    forged = jwt.encode(
        {"sub": "1", "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "a-different-secret-that-is-long-enough-123456",
        algorithm="HS256",
    )
    with pytest.raises(AppError) as info:
        security.decode_access_token(forged)
    assert info.value.status == 401


def test_alg_none_token_is_rejected():
    unsigned = jwt.encode(
        {"sub": "1", "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        None,
        algorithm="none",
    )
    with pytest.raises(AppError) as info:
        security.decode_access_token(unsigned)
    assert info.value.status == 401


def test_other_hmac_algorithm_is_rejected():
    hs512 = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, TEST_JWT_SECRET, algorithm="HS512"
    )
    with pytest.raises(AppError):
        security.decode_access_token(hs512)


def test_token_missing_exp_or_sub_is_rejected():
    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    no_exp = jwt.encode({"sub": "1"}, TEST_JWT_SECRET, algorithm="HS256")
    no_sub = jwt.encode({"exp": soon}, TEST_JWT_SECRET, algorithm="HS256")
    for token in (no_exp, no_sub):
        with pytest.raises(AppError) as info:
            security.decode_access_token(token)
        assert info.value.status == 401


def test_token_with_non_numeric_subject_is_rejected():
    bad = jwt.encode(
        {"sub": "not-a-number", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, TEST_JWT_SECRET, algorithm="HS256"
    )
    with pytest.raises(AppError) as info:
        security.decode_access_token(bad)
    assert info.value.status == 401


def test_tampered_token_is_rejected():
    token = security.create_access_token(1, "user")
    header, payload, signature = token.split(".")
    # Change the FIRST signature character: the last one carries unused bits, so
    # altering only it can leave the decoded signature unchanged.
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(AppError):
        security.decode_access_token(f"{header}.{payload}.{flipped}")


def test_missing_jwt_secret_is_a_server_error_not_a_crash(monkeypatch):
    s = Settings.model_validate({"database_url": GOOD_URL})  # no jwt_secret
    monkeypatch.setattr(security, "get_settings", lambda: s)
    with pytest.raises(AppError) as info:
        security.create_access_token(1, "user")
    assert info.value.status == 500
    assert info.value.code == "internal_error"
    assert "JWT_SECRET" not in info.value.message  # no configuration detail for callers


# ------------------------------------------------------------ owner tokens
def test_owner_token_is_32_urlsafe_characters_and_random():
    a, b = security.generate_owner_token(), security.generate_owner_token()
    assert len(a) == 32 and a != b
    assert all(c.isalnum() or c in "-_" for c in a)


def test_owner_token_hash_and_match():
    token = security.generate_owner_token()
    stored = security.hash_owner_token(token)
    assert len(stored) == 64 and token not in stored
    assert security.owner_token_matches(token, stored) is True
    assert security.owner_token_matches(security.generate_owner_token(), stored) is False
    assert security.owner_token_matches(None, stored) is False
    assert security.owner_token_matches(token, None) is False
    assert security.owner_token_matches("", stored) is False
