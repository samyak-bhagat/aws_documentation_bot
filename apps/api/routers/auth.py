"""Authentication endpoints — Phase 8.

POST /auth/register  — create account
POST /auth/login     — get token pair
POST /auth/refresh   — exchange refresh token for new access token
GET  /me             — current user info
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from core.logging import get_logger
from services.auth.jwt import (
    TokenPair,
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from services.auth.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


# ── Request / Response schemas ────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = {
        "json_schema_extra": {"example": {"email": "user@example.com", "password": "secret123"}}
    }


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    is_admin: bool


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request) -> UserResponse:
    """Create a new user account."""
    from core.database import _session_factory

    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")

    async with _session_factory() as session:
        existing = await session.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")

        user = User(email=body.email, hashed_password=hash_password(body.password))
        session.add(user)
        await session.commit()
        await session.refresh(user)

    logger.info("User registered", extra={"email": body.email})
    return UserResponse(id=user.id, email=user.email, is_admin=user.is_admin)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, request: Request) -> TokenPair:
    """Authenticate and return access + refresh tokens."""
    from core.database import _session_factory

    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")

    async with _session_factory() as session:
        result = await session.execute(select(User).where(User.email == body.email))
        user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    logger.info("User logged in", extra={"email": body.email})
    return TokenPair(
        access_token=create_access_token(user.id, user.email, user.is_admin),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(body: RefreshRequest) -> TokenPair:
    """Exchange a refresh token for a new token pair."""
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id: str = payload["sub"]

    from core.database import _session_factory

    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")

    async with _session_factory() as session:
        from services.auth.jwt import get_user_from_db

        user = await get_user_from_db(user_id, session)

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    return TokenPair(
        access_token=create_access_token(user.id, user.email, user.is_admin),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: TokenPayload = Depends(get_current_user)) -> UserResponse:  # noqa: B008
    """Return the current authenticated user's profile."""
    return UserResponse(
        id=current_user.sub, email=current_user.email, is_admin=current_user.is_admin
    )
