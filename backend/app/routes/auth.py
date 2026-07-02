import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import User, get_db, _utcnow
from app.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_google_id_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger("paperpod")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleRequest(BaseModel):
    id_token: str


def _user_public(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
    }


def _auth_response(user: User) -> dict:
    return {"token": create_access_token(user.id), "user": _user_public(user)}


@router.post("/register")
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=email,
        name=(body.name or "").strip() or None,
        password_hash=hash_password(body.password),
        created_at=_utcnow(),
    )
    db.add(user)
    await db.commit()
    logger.info(f"[auth] Registered new user {user.id}")
    return _auth_response(user)


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return _auth_response(user)


@router.post("/google")
async def google_sign_in(body: GoogleRequest, db: AsyncSession = Depends(get_db)):
    claims = verify_google_id_token(body.id_token)
    google_sub = claims["sub"]
    email = claims["email"].strip().lower()
    name = claims.get("name")
    avatar = claims.get("picture")

    # Match by Google sub first, then fall back to email so an existing
    # password account can link to Google sign-in.
    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()
    if not user:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if user:
        # Backfill Google fields on an existing account.
        if not user.google_sub:
            user.google_sub = google_sub
        if not user.name and name:
            user.name = name
        if not user.avatar_url and avatar:
            user.avatar_url = avatar
    else:
        user = User(
            email=email,
            name=name,
            google_sub=google_sub,
            avatar_url=avatar,
            created_at=_utcnow(),
        )
        db.add(user)

    await db.commit()
    logger.info(f"[auth] Google sign-in for user {user.id}")
    return _auth_response(user)


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return _user_public(user)
