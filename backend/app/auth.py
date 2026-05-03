"""Authentication helpers: password hashing, session cookies, and role checks."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import SessionToken, User

ROLE_RANK = {
    "viewer": 0,
    "operator": 1,
    "admin": 2,
}

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedSession:
    user: User
    session_token: SessionToken


def normalize_username(username: str) -> str:
    return username.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = int(settings.auth_password_iterations)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${derived}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        algo, iterations_raw, salt, expected = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations).hex()
    return hmac.compare_digest(actual, expected)


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def create_session_token(db: AsyncSession, user: User) -> tuple[str, datetime]:
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=int(settings.auth_session_ttl_hours))
    db.add(
        SessionToken(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=expires_at,
        )
    )
    await db.flush()
    return raw_token, expires_at


def set_auth_cookie(response: Response, raw_token: str, expires_at: datetime) -> None:
    max_age = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(
        key=settings.auth_session_cookie_name,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        secure=bool(settings.auth_cookie_secure),
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_session_cookie_name,
        httponly=True,
        secure=bool(settings.auth_cookie_secure),
        samesite="lax",
        path="/",
    )


def _extract_raw_token(request: Request, creds: HTTPAuthorizationCredentials | None) -> str | None:
    if creds and creds.scheme.lower() == "bearer":
        return creds.credentials
    return request.cookies.get(settings.auth_session_cookie_name)


async def get_current_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedSession:
    raw_token = _extract_raw_token(request, creds)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(SessionToken, User)
        .join(User, SessionToken.user_id == User.id)
        .where(SessionToken.token_hash == hash_session_token(raw_token))
        .where(SessionToken.revoked_at.is_(None))
        .where(SessionToken.expires_at > now)
        .where(User.is_active.is_(True))
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    session_token, user = row
    return AuthenticatedSession(user=user, session_token=session_token)


async def get_current_user(auth: AuthenticatedSession = Depends(get_current_auth)) -> User:
    return auth.user


def require_min_role(min_role: str):
    async def dependency(auth: AuthenticatedSession = Depends(get_current_auth)) -> User:
        current_rank = ROLE_RANK.get(auth.user.role, -1)
        required_rank = ROLE_RANK.get(min_role, 0)
        if current_rank < required_rank:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return auth.user

    return dependency
