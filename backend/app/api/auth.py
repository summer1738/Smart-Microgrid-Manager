"""Username/password authentication and cookie-backed sessions."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    AuthenticatedSession,
    clear_auth_cookie,
    create_session_token,
    get_current_auth,
    hash_password,
    normalize_username,
    set_auth_cookie,
    verify_password,
)
from app.database import get_db
from app.models import User
from app.schemas import AuthSessionOut, LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthSessionOut)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthSessionOut:
    username = normalize_username(body.username)
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    raw_token, expires_at = await create_session_token(db, user)
    set_auth_cookie(response, raw_token, expires_at)
    return AuthSessionOut(user=UserOut.model_validate(user), expires_at=expires_at)


@router.post("/register", response_model=AuthSessionOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthSessionOut:
    username = normalize_username(body.username)
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name must be at least 2 characters")

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is already taken")

    user = User(
        name=name,
        username=username,
        password_hash=hash_password(body.password),
        is_active=True,
        role="viewer",
    )
    db.add(user)
    await db.flush()

    raw_token, expires_at = await create_session_token(db, user)
    set_auth_cookie(response, raw_token, expires_at)
    return AuthSessionOut(user=UserOut.model_validate(user), expires_at=expires_at)


@router.get("/me", response_model=UserOut)
async def me(auth: AuthenticatedSession = Depends(get_current_auth)) -> UserOut:
    return UserOut.model_validate(auth.user)


@router.post("/logout")
async def logout(
    response: Response,
    auth: AuthenticatedSession = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth.session_token.revoked_at = auth.session_token.revoked_at or datetime.now(timezone.utc)
    await db.flush()
    clear_auth_cookie(response)
    return {"ok": True}
