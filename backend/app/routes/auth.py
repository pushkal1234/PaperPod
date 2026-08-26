import logging
import re
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import User, get_db, _utcnow
from app.entitlements import get_entitlements, get_usage
from app.security import (
    client_ip,
    create_access_token,
    get_current_user,
    hash_password,
    verify_google_id_token,
    verify_password,
)
from app.services.email_service import (
    generate_code,
    hash_code,
    normalize_email,
    send_password_reset_email,
    send_verification_email,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger("paperpod")

# Non-empty local part, an "@", a dotted domain with a 2+ char TLD, and no
# whitespace anywhere. Kept in sync with the frontend AuthModal guardrail.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)*\.[^@\s.]{2,}$")


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleRequest(BaseModel):
    id_token: str


class VerifyEmailRequest(BaseModel):
    code: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    password: str


def _user_public(user: User) -> dict:
    verified = bool(getattr(user, "email_verified", True))
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "plan": getattr(user, "plan", "free"),
        "email_verified": verified,
        # True only when the server will actually block unverified users, so the
        # frontend knows whether to show the "enter your code" step.
        "verification_required": bool(settings.EMAIL_VERIFICATION_ENABLED and not verified),
    }


def _as_utc(dt):
    """Coerce a possibly-naive stored datetime to timezone-aware UTC.

    SQLite round-trips ``DateTime`` values as naive; comparing them to an aware
    ``_utcnow()`` would raise, so normalize before arithmetic.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _issue_verification(user: User, db: AsyncSession) -> None:
    """Generate, store (hashed), and email a fresh verification code."""
    code = generate_code()
    user.verification_code_hash = hash_code(code)
    user.verification_sent_at = _utcnow()
    user.verification_attempts = 0
    await db.commit()
    sent = await send_verification_email(user.email, code, user.name)
    if not sent and settings.EMAIL_PROVIDER_CONFIGURED:
        logger.error("[auth] Verification email FAILED to send to %s", user.email)


async def _issue_reset(user: User, db: AsyncSession) -> None:
    """Generate, store (hashed), and email a fresh password-reset code."""
    code = generate_code()
    user.reset_code_hash = hash_code(code)
    user.reset_sent_at = _utcnow()
    user.reset_attempts = 0
    await db.commit()
    sent = await send_password_reset_email(user.email, code, user.name)
    if not sent and settings.EMAIL_PROVIDER_CONFIGURED:
        logger.error("[auth] Password reset email FAILED to send to %s", user.email)


async def _user_full(user: User, db: AsyncSession) -> dict:
    """Public profile enriched with entitlements + live usage for the frontend.

    This is the single shape returned by /me AND every auth response, so the
    client always has plan/entitlements/usage regardless of how the session
    started.
    """
    return {
        **_user_public(user),
        "entitlements": get_entitlements(user).to_dict(),
        "usage": await get_usage(db, user),
    }


async def _auth_response(user: User, db: AsyncSession) -> dict:
    return {"token": create_access_token(user.id), "user": await _user_full(user, db)}


@router.post("/register")
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    # Duplicate detection uses the CANONICAL email so alias tricks
    # (a.b+x@gmail.com == ab@gmail.com) can't spawn a second free account.
    norm = normalize_email(email)
    existing = await db.execute(
        select(User).where((User.normalized_email == norm) | (User.email == email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    # When verification is enabled, new accounts start UNVERIFIED and must
    # confirm a code before they can create podcasts. When disabled, behave as
    # before (accounts are usable immediately).
    verified = not settings.EMAIL_VERIFICATION_ENABLED
    user = User(
        email=email,
        normalized_email=norm,
        name=(body.name or "").strip() or None,
        password_hash=hash_password(body.password),
        email_verified=verified,
        signup_ip=client_ip(request),
        created_at=_utcnow(),
    )
    db.add(user)
    await db.commit()
    logger.info(f"[auth] Registered new user {user.id} (verified={verified})")

    if settings.EMAIL_VERIFICATION_ENABLED:
        await _issue_verification(user, db)

    return await _auth_response(user, db)


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    norm = normalize_email(email)
    # Match on the canonical email first (so alias variants resolve to the one
    # real account), then fall back to the exact address for legacy rows.
    result = await db.execute(
        select(User).where((User.normalized_email == norm) | (User.email == email))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return await _auth_response(user, db)


@router.post("/google")
async def google_sign_in(body: GoogleRequest, request: Request, db: AsyncSession = Depends(get_db)):
    claims = verify_google_id_token(body.id_token)
    google_sub = claims["sub"]
    email = claims["email"].strip().lower()
    name = claims.get("name")
    avatar = claims.get("picture")
    norm = normalize_email(email)

    # Match by Google sub first, then fall back to the canonical email so an
    # existing password account can link to Google sign-in.
    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()
    if not user:
        result = await db.execute(
            select(User).where((User.normalized_email == norm) | (User.email == email))
        )
        user = result.scalar_one_or_none()

    if user:
        # Backfill Google fields on an existing account.
        if not user.google_sub:
            user.google_sub = google_sub
        if not user.name and name:
            user.name = name
        if not user.avatar_url and avatar:
            user.avatar_url = avatar
        if not getattr(user, "normalized_email", None):
            user.normalized_email = norm
        # Google has already verified this address — trust it.
        user.email_verified = True
    else:
        user = User(
            email=email,
            normalized_email=norm,
            name=name,
            google_sub=google_sub,
            avatar_url=avatar,
            email_verified=True,
            signup_ip=client_ip(request),
            created_at=_utcnow(),
        )
        db.add(user)

    await db.commit()
    logger.info(f"[auth] Google sign-in for user {user.id}")
    return await _auth_response(user, db)


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm the 6-digit code and mark the account verified."""
    if getattr(user, "email_verified", False):
        return await _user_full(user, db)
    if not user.verification_code_hash or not user.verification_sent_at:
        raise HTTPException(
            status_code=400,
            detail="No verification pending. Request a new code.",
        )

    age = (_utcnow() - _as_utc(user.verification_sent_at)).total_seconds()
    if age > settings.VERIFICATION_CODE_TTL_MINUTES * 60:
        raise HTTPException(
            status_code=400,
            detail="This code has expired. Request a new one.",
        )
    if (user.verification_attempts or 0) >= settings.VERIFICATION_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect attempts. Request a new code.",
        )

    if hash_code(body.code) != user.verification_code_hash:
        user.verification_attempts = (user.verification_attempts or 0) + 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Incorrect code. Please try again.")

    user.email_verified = True
    user.verification_code_hash = None
    user.verification_attempts = 0
    await db.commit()
    logger.info(f"[auth] Email verified for user {user.id}")
    return await _user_full(user, db)


@router.post("/resend-verification")
async def resend_verification(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-issue a verification code, rate-limited by a short cooldown."""
    if getattr(user, "email_verified", False):
        return {"ok": True, "already_verified": True}

    if user.verification_sent_at:
        age = (_utcnow() - _as_utc(user.verification_sent_at)).total_seconds()
        if age < settings.VERIFICATION_RESEND_COOLDOWN_SECONDS:
            wait = int(settings.VERIFICATION_RESEND_COOLDOWN_SECONDS - age)
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {wait}s before requesting another code.",
            )

    await _issue_verification(user, db)
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Email a 6-digit reset code to a registered address.

    Always returns the SAME generic success response whether or not the email
    exists, so this endpoint can't be used to enumerate which addresses have
    accounts. Rate-limited per-account by a short resend cooldown.
    """
    generic = {"ok": True, "message": "If an account exists for that email, a reset code is on its way."}

    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    norm = normalize_email(email)
    result = await db.execute(
        select(User).where((User.normalized_email == norm) | (User.email == email))
    )
    user = result.scalar_one_or_none()
    if not user:
        return generic

    # Throttle: don't let someone spam a user's inbox with reset codes.
    if user.reset_sent_at:
        age = (_utcnow() - _as_utc(user.reset_sent_at)).total_seconds()
        if age < settings.VERIFICATION_RESEND_COOLDOWN_SECONDS:
            # Silently succeed (generic) so timing can't reveal account existence.
            return generic

    await _issue_reset(user, db)
    return generic


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Verify the reset code and set a new password, then sign the user in.

    Confirming the emailed code also proves inbox ownership, so we mark the
    account verified here as a convenient side effect.
    """
    email = body.email.strip().lower()
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    code = (body.code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(status_code=400, detail="Enter the 6-digit code from your email.")

    norm = normalize_email(email)
    result = await db.execute(
        select(User).where((User.normalized_email == norm) | (User.email == email))
    )
    user = result.scalar_one_or_none()
    # Uniform error for "no pending reset" whether the account is missing or just
    # never requested one — avoids leaking which emails are registered.
    if not user or not user.reset_code_hash or not user.reset_sent_at:
        raise HTTPException(status_code=400, detail="No password reset pending. Request a new code.")

    age = (_utcnow() - _as_utc(user.reset_sent_at)).total_seconds()
    if age > settings.VERIFICATION_CODE_TTL_MINUTES * 60:
        raise HTTPException(status_code=400, detail="This code has expired. Request a new one.")
    if (user.reset_attempts or 0) >= settings.VERIFICATION_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many incorrect attempts. Request a new code.")

    if hash_code(code) != user.reset_code_hash:
        user.reset_attempts = (user.reset_attempts or 0) + 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Incorrect code. Please try again.")

    # Success: set the new password and clear the reset challenge.
    user.password_hash = hash_password(body.password)
    user.reset_code_hash = None
    user.reset_attempts = 0
    user.reset_sent_at = None
    # Proving the code confirms the inbox — safe to treat the email as verified.
    user.email_verified = True
    await db.commit()
    logger.info(f"[auth] Password reset for user {user.id}")
    return await _auth_response(user, db)


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _user_full(user, db)
