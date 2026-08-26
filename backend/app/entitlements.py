"""Plan-based entitlements — the single source of truth for what a user may do.

Design goal: NEVER scatter ``if user.plan == "premium"`` checks across the
codebase. Instead, every caller asks this module "what is this user allowed to
do?" and reads capabilities off an :class:`Entitlements` object. Swapping the
pricing model later (e.g. subscription -> credit packs) then touches only this
file plus the Stripe webhook that sets ``User.plan``.

Phase 0 note: this module is wired into ``/api/auth/me`` so the frontend can
render usage/upgrade UI, but the enforcement gates that consume it are gated
behind ``settings.BILLING_ENABLED`` (default OFF), so nothing is blocked yet.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import Document, User

PLAN_FREE = "free"
PLAN_PREMIUM = "premium"


@dataclass(frozen=True)
class Entitlements:
    """Immutable capability snapshot derived from a user's plan.

    ``max_lifetime_podcasts is None`` means unlimited. Keep this object free of
    any request/DB state so it is trivially cacheable and testable.
    """

    plan: str
    unlimited: bool
    max_lifetime_podcasts: int | None
    max_doc_chars: int

    def to_dict(self) -> dict:
        return {
            "plan": self.plan,
            "unlimited": self.unlimited,
            "max_lifetime_podcasts": self.max_lifetime_podcasts,
            "max_doc_chars": self.max_doc_chars,
        }


def _is_premium(user: User | None) -> bool:
    return bool(user is not None and getattr(user, "plan", PLAN_FREE) == PLAN_PREMIUM)


def get_entitlements(user: User | None) -> Entitlements:
    """Resolve capabilities for a user (or an anonymous ``None`` caller).

    Anonymous callers get the free tier here; their 1-podcast trial is metered
    client-side because the server cannot identify them.
    """
    if _is_premium(user):
        return Entitlements(
            plan=PLAN_PREMIUM,
            unlimited=True,
            max_lifetime_podcasts=None,
            # Premium's doc-size ceiling IS the pipeline's hard cap.
            max_doc_chars=settings.MAX_DOC_CHARS_HARD,
        )
    return Entitlements(
        plan=PLAN_FREE,
        unlimited=False,
        max_lifetime_podcasts=settings.FREE_LIFETIME_PODCASTS,
        # Deliberately NO free doc-length constraint: free users get the SAME
        # full-length ceiling as premium (the pipeline's hard cap). The whole
        # point of the 2 free podcasts is to let people experience a real,
        # full-length (~45 min) podcast and build trust before paying — a short
        # free-doc cap would undercut that. Premium's only edge is *quantity*
        # (unlimited podcasts), not document length.
        max_doc_chars=settings.MAX_DOC_CHARS_HARD,
    )


async def count_user_podcasts(db: AsyncSession, user_id: str) -> int:
    """Server-authoritative lifetime usage: non-failed documents owned by user.

    ``failed`` generations are excluded so a user is never charged a free credit
    for output the pipeline itself rejected (mirrors the dedup/quality-gate
    semantics elsewhere).
    """
    result = await db.execute(
        select(func.count(Document.id)).where(
            Document.user_id == user_id,
            Document.status != "failed",
        )
    )
    return int(result.scalar_one() or 0)


async def get_usage(db: AsyncSession, user: User) -> dict:
    """Usage summary for the frontend meter/upgrade CTA.

    ``remaining`` is ``None`` for unlimited (premium) users.
    """
    ent = get_entitlements(user)
    used = await count_user_podcasts(db, user.id)
    if ent.max_lifetime_podcasts is None:
        remaining: int | None = None
    else:
        remaining = max(0, ent.max_lifetime_podcasts - used)
    return {
        "podcasts_used": used,
        "podcasts_limit": ent.max_lifetime_podcasts,
        "podcasts_remaining": remaining,
        "billing_enabled": settings.BILLING_ENABLED,
    }


# ── Enforcement gates (no-ops unless settings.BILLING_ENABLED) ──
async def enforce_can_create_podcast(db: AsyncSession, user: User | None) -> None:
    """Raise HTTP 402 if a signed-in free user is out of lifetime podcasts.

    No-op when billing is disabled, the caller is anonymous (metered
    client-side), or the user is on an unlimited plan. Call this ONLY on the
    create path after a dedup miss, so reusing an existing podcast is free.
    """
    if not settings.BILLING_ENABLED or user is None:
        return
    ent = get_entitlements(user)
    if ent.max_lifetime_podcasts is None:
        return
    used = await count_user_podcasts(db, user.id)
    if used >= ent.max_lifetime_podcasts:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "quota_exceeded",
                "message": (
                    f"You've used all {ent.max_lifetime_podcasts} free podcasts. "
                    "Upgrade to Premium for unlimited podcasts."
                ),
            },
        )


def enforce_email_verified(user: User | None) -> None:
    """Raise HTTP 403 if a signed-in user hasn't verified their email.

    No-op when email verification is disabled or the caller is anonymous
    (anonymous uploads are governed by REQUIRE_AUTH_UPLOAD, not this). This is
    the primary defense against fake-email multi-account abuse: an account can't
    create podcasts until it proves it owns a real inbox.
    """
    if not settings.EMAIL_VERIFICATION_ENABLED or user is None:
        return
    if getattr(user, "email_verified", True):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "email_unverified",
            "message": (
                "Please verify your email to create podcasts. "
                "Check your inbox for the 6-digit code."
            ),
        },
    )


async def enforce_ip_quota(db: AsyncSession, user: User | None, client_ip: str | None) -> None:
    """Raise HTTP 402 if this IP has used up the shared free-podcast allowance.

    Secondary defense: caps free podcasts per source IP across ALL accounts so
    creating many accounts on one machine still shares one allowance. No-op when
    disabled, when the IP is unknown, or for premium users (who are unlimited).
    """
    if not settings.IP_QUOTA_ENABLED or not client_ip:
        return
    if _is_premium(user):
        return
    result = await db.execute(
        select(func.count(Document.id)).where(
            Document.creator_ip == client_ip,
            Document.status != "failed",
        )
    )
    used = int(result.scalar_one() or 0)
    if used >= settings.FREE_PODCASTS_PER_IP:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "ip_quota_exceeded",
                "message": (
                    "You've reached the free podcast limit for this network. "
                    "Upgrade to Premium for unlimited podcasts."
                ),
            },
        )
