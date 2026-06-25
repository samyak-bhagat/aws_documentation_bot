"""JWT authentication helpers — Phase 8.

Handles:
  - Password hashing (bcrypt via passlib)
  - JWT token creation and verification (HS256 via python-jose)
  - FastAPI dependency for extracting the current user
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


# ── Pydantic token schemas ─────────────────────────────────────────────────────


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str  # user id
    email: str
    is_admin: bool = False
    exp: int = 0


# ── Password helpers ──────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── Token creation ────────────────────────────────────────────────────────────


def _create_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, email: str, is_admin: bool = False) -> str:
    return _create_token(
        {"sub": user_id, "email": email, "is_admin": is_admin, "type": "access"},
        timedelta(minutes=settings.jwt_expire_minutes),
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id, "type": "refresh"},
        timedelta(days=7),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> TokenPayload:
    """Dependency — extracts and validates the Bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return TokenPayload(
        sub=payload["sub"],
        email=payload.get("email", ""),
        is_admin=payload.get("is_admin", False),
    )


async def get_admin_user(
    current_user: TokenPayload = Depends(get_current_user),  # noqa: B008
) -> TokenPayload:
    """Dependency — requires the user to have admin privileges."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def get_user_from_db(user_id: str, session: AsyncSession):  # type: ignore[return]
    """Look up a User row by id."""
    from services.auth.models import User

    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
