"""Authentication helpers: password hashing, JWT sessions, Google Sign-In
verification, and FastAPI dependencies for resolving the current user.

The app uses self-hosted, stateless JWT auth (no session table). Tokens are
signed with ``settings.JWT_SECRET`` and carry the user id in ``sub``.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import User, get_db

logger = logging.getLogger("paperpod")

# If no JWT_SECRET is configured, fall back to a random per-process key so the
# app still boots in dev. Tokens won't survive a restart — set JWT_SECRET in
# production (Railway env var) to keep sessions stable.
_JWT_SECRET = settings.JWT_SECRET.strip()
if not _JWT_SECRET:
    _JWT_SECRET = secrets.token_urlsafe(48)
    logger.warning(
        "JWT_SECRET is not set — using an ephemeral key. Sessions will be "
        "invalidated on restart. Set JWT_SECRET in the environment for production."
    )

# auto_error=False so a missing/invalid header yields None instead of a 403,
# which lets us support both required- and optional-auth endpoints.
_bearer = HTTPBearer(auto_error=False)


# ── Passwords ──
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT ──
def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.JWT_EXPIRE_DAYS)).timestamp()),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_access_token(token: str) -> str | None:
    """Return the user id from a valid token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[settings.JWT_ALG])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# ── Google Sign-In ──
def verify_google_id_token(id_token_str: str) -> dict:
    """Verify a Google ID token and return its claims.

    Raises HTTPException(401) if the token is invalid or the audience does not
    match our configured GOOGLE_CLIENT_ID.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sign-In is not configured on this server.",
        )
    # Imported lazily so the rest of auth works even if google-auth is absent.
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests

    try:
        claims = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google sign-in token.")

    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status_code=401, detail="Invalid Google token issuer.")
    if not claims.get("email"):
        raise HTTPException(status_code=401, detail="Google account has no email.")
    return claims


# ── Dependencies ──
async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Resolve the current user if a valid token is present, else None.

    Used on endpoints that must keep working for anonymous callers (e.g. the
    browser extension) while still tagging content to a user when signed in.
    """
    if not credentials or not credentials.credentials:
        return None
    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        return None
    return await db.get(User, user_id)


async def get_current_user(
    user: User | None = Depends(get_optional_user),
) -> User:
    """Require a signed-in user; raise 401 otherwise."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
