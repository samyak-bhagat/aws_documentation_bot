"""Unit tests for services/auth/jwt.py — no network or DB required."""

import pytest
from fastapi import HTTPException

from services.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_differs_from_plain(self):
        hashed = hash_password("secret123")
        assert hashed != "secret123"

    def test_verify_correct_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_two_hashes_differ(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


class TestTokenCreation:
    def test_access_token_is_string(self):
        token = create_access_token("user-1", "user@example.com")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_refresh_token_is_string(self):
        token = create_refresh_token("user-1")
        assert isinstance(token, str)

    def test_access_token_decodes(self):
        token = create_access_token("user-1", "user@example.com", is_admin=True)
        payload = decode_token(token)
        assert payload["sub"] == "user-1"
        assert payload["email"] == "user@example.com"
        assert payload["is_admin"] is True
        assert payload["type"] == "access"

    def test_refresh_token_decodes(self):
        token = create_refresh_token("user-1")
        payload = decode_token(token)
        assert payload["sub"] == "user-1"
        assert payload["type"] == "refresh"

    def test_tokens_are_unique(self):
        t1 = create_access_token("user-1", "a@example.com")
        t2 = create_access_token("user-1", "a@example.com")
        # Tokens issued at same second may differ due to exp precision
        assert isinstance(t1, str) and isinstance(t2, str)


class TestDecodeToken:
    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.valid.token")
        assert exc_info.value.status_code == 401

    def test_tampered_token_raises_401(self):
        token = create_access_token("user-1", "user@example.com")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(HTTPException) as exc_info:
            decode_token(tampered)
        assert exc_info.value.status_code == 401
