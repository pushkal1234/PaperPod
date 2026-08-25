"""Billing via Dodo Payments (Merchant of Record).

Dodo Payments is the *seller of record*: it hosts checkout, collects global
sales tax / VAT, and settles to the founder's Indian bank (chosen because
Stripe and Lemon Squeezy are invite-only in India). We never touch card data.
The flow is:

    /checkout  -> create a hosted checkout session, return its URL
    /webhook   -> Dodo calls us on every subscription change; this is the
                  SINGLE SOURCE OF TRUTH that flips User.plan
    /portal    -> return the customer's self-service billing-portal URL

Design notes:
- Entitlement decisions live in app/entitlements.py; this module only maps the
  provider's subscription events onto User.plan and persists provider ids.
- Webhooks follow the Standard Webhooks spec (https://standardwebhooks.com):
  the signature is base64(HMAC-SHA256(secret, "{id}.{timestamp}.{body}")) in the
  `webhook-signature` header. We verify it with the stdlib before acting.
- Isolated to this file so the rest of the app stays payment-agnostic. Ships
  dark: until the env vars are set, /checkout and /portal return 503.
"""
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import User, get_db
from app.security import get_current_user

router = APIRouter(prefix="/api/billing", tags=["billing"])
logger = logging.getLogger("paperpod")

# Standard Webhooks: reject payloads whose timestamp is too far from now to
# blunt replay attacks.
_WEBHOOK_TOLERANCE_SECONDS = 5 * 60

# Dodo subscription events that grant vs revoke access. Anything else leaves the
# plan unchanged.
_ACTIVATE_EVENTS = {"subscription.active", "subscription.renewed"}
_DEACTIVATE_EVENTS = {
    "subscription.cancelled",
    "subscription.expired",
    "subscription.on_hold",
    "subscription.failed",
    "subscription.paused",
}


def _dodo_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.DODO_API_KEY}",
    }


def _parse_dt(value: str | None) -> datetime | None:
    """Parse a Dodo ISO-8601 timestamp (e.g. '...Z') to an aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def plan_from_event(event_type: str, sub_status: str | None) -> str | None:
    """Map a Dodo subscription event/status onto 'premium' | 'free' | None.

    None means "leave the plan unchanged" (an event we don't act on). Dodo keeps
    a cancelled-at-period-end subscription in status 'active' until it actually
    ends, then fires subscription.cancelled/expired — so status is authoritative.
    """
    if event_type in _ACTIVATE_EVENTS or sub_status == "active":
        return "premium"
    if event_type in _DEACTIVATE_EVENTS or sub_status in (
        "cancelled", "expired", "on_hold", "failed", "paused",
    ):
        return "free"
    return None


def _verify_signature(raw: bytes, headers) -> bool:
    """Verify a Standard Webhooks signature (as used by Dodo Payments).

    signed_content = "{webhook-id}.{webhook-timestamp}.{raw_body}"
    expected       = base64(HMAC_SHA256(secret_key_bytes, signed_content))
    The `webhook-signature` header is a space-separated list of "v1,<sig>"
    tokens; a match against any token passes.
    """
    secret = settings.DODO_WEBHOOK_KEY.strip()
    if not secret:
        return False
    webhook_id = headers.get("webhook-id", "")
    timestamp = headers.get("webhook-timestamp", "")
    sig_header = headers.get("webhook-signature", "")
    if not (webhook_id and timestamp and sig_header):
        return False

    try:
        if abs(time.time() - int(timestamp)) > _WEBHOOK_TOLERANCE_SECONDS:
            return False
    except ValueError:
        return False

    # The secret is "whsec_<base64>"; the signing key is the decoded base64.
    key_part = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(key_part)
    except Exception:
        key = secret.encode()

    signed_content = f"{webhook_id}.{timestamp}.{raw.decode()}".encode()
    expected = base64.b64encode(
        hmac.new(key, signed_content, hashlib.sha256).digest()
    ).decode()

    for token in sig_header.split():
        _, _, provided = token.partition(",")
        if provided and hmac.compare_digest(expected, provided):
            return True
    return False


@router.post("/checkout")
async def create_checkout(user: User = Depends(get_current_user)):
    """Create a hosted Dodo Payments checkout session for the current user.

    We attach ``metadata.user_id`` so the webhook can map the subscription back
    to this account, and prefill the customer's email/name.
    """
    if not settings.DODO_CONFIGURED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured yet.",
        )

    payload = {
        "product_cart": [{"product_id": settings.DODO_PRODUCT_ID, "quantity": 1}],
        "customer": {"email": user.email, "name": user.name or user.email},
        "return_url": f"{settings.FRONTEND_BASE_URL}/?upgrade=success",
        # Echoed back on the subscription in every webhook's data.metadata.
        "metadata": {"user_id": str(user.id)},
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{settings.DODO_API_BASE}/checkouts",
                headers=_dodo_headers(),
                json=payload,
            )
    except httpx.HTTPError as e:
        logger.error(f"[billing] Checkout request failed: {e}")
        raise HTTPException(status_code=502, detail="Could not reach the payment provider.")

    if resp.status_code >= 300:
        logger.error(f"[billing] Checkout create failed {resp.status_code}: {resp.text[:500]}")
        raise HTTPException(status_code=502, detail="Could not start checkout. Please try again.")

    url = resp.json().get("checkout_url")
    if not url:
        logger.error(f"[billing] Checkout response missing checkout_url: {resp.text[:500]}")
        raise HTTPException(status_code=502, detail="Could not start checkout. Please try again.")
    logger.info(f"[billing] Checkout created for user {user.id}")
    return {"url": url}


@router.get("/portal")
async def customer_portal(user: User = Depends(get_current_user)):
    """Return the self-service customer-portal URL (manage/cancel subscription)."""
    if not settings.DODO_API_KEY.strip():
        raise HTTPException(status_code=503, detail="Billing is not configured yet.")
    if not user.billing_customer_id:
        raise HTTPException(status_code=404, detail="No active subscription found.")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{settings.DODO_API_BASE}/customers/{user.billing_customer_id}/customer-portal/session",
                headers=_dodo_headers(),
            )
    except httpx.HTTPError as e:
        logger.error(f"[billing] Portal request failed: {e}")
        raise HTTPException(status_code=502, detail="Could not reach the payment provider.")

    if resp.status_code >= 300:
        logger.error(f"[billing] Portal create failed {resp.status_code}: {resp.text[:500]}")
        raise HTTPException(status_code=502, detail="Could not open the billing portal.")

    portal_url = resp.json().get("link")
    if not portal_url:
        raise HTTPException(status_code=502, detail="Could not open the billing portal.")
    return {"url": portal_url}


async def _resolve_user(db: AsyncSession, metadata: dict, customer: dict) -> User | None:
    """Find the account a webhook refers to: by metadata.user_id, else by email."""
    user_id = (metadata or {}).get("user_id")
    if user_id:
        user = await db.get(User, user_id)
        if user:
            return user
    email = (customer or {}).get("email")
    if email:
        result = await db.execute(select(User).where(User.email == email.strip().lower()))
        return result.scalar_one_or_none()
    return None


@router.post("/webhook")
async def dodo_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Dodo Payments webhooks — the source of truth for User.plan.

    Verifies the Standard Webhooks signature before trusting the payload, then
    updates the matching user's plan/subscription fields.
    """
    if not settings.DODO_WEBHOOK_KEY.strip():
        logger.error("[billing] Webhook received but DODO_WEBHOOK_KEY is unset")
        raise HTTPException(status_code=503, detail="Webhook not configured.")

    raw = await request.body()
    if not _verify_signature(raw, request.headers):
        logger.warning("[billing] Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature.")

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid payload.")

    event_type = body.get("type", "")
    data = body.get("data", {}) or {}

    # Only act on subscription lifecycle events; ACK the rest so Dodo stops
    # retrying (e.g. one-off payment.succeeded, refund.succeeded).
    if data.get("payload_type") != "Subscription" and not event_type.startswith("subscription."):
        return {"ok": True, "ignored": event_type}

    metadata = data.get("metadata") or {}
    customer = data.get("customer") or {}
    user = await _resolve_user(db, metadata, customer)
    if not user:
        # ACK anyway (200) so it isn't retried forever; log for reconciliation.
        logger.warning(f"[billing] Webhook '{event_type}' could not be matched to a user")
        return {"ok": True, "unmatched": True}

    sub_status = data.get("status")
    if data.get("subscription_id"):
        user.billing_subscription_id = str(data.get("subscription_id"))
    if customer.get("customer_id"):
        user.billing_customer_id = str(customer.get("customer_id"))
    user.plan_status = sub_status
    user.plan_renews_at = _parse_dt(data.get("next_billing_date"))
    new_plan = plan_from_event(event_type, sub_status)
    if new_plan:
        user.plan = new_plan
    await db.commit()

    logger.info(
        f"[billing] {event_type} -> user {user.id} plan={user.plan} status={sub_status}"
    )
    return {"ok": True}


@router.get("/config")
async def billing_config():
    """Lightweight public flags so the frontend knows whether to show upgrade UI."""
    return {
        "billing_enabled": settings.BILLING_ENABLED,
        "checkout_available": settings.DODO_CONFIGURED,
    }
