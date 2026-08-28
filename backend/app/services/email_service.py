"""Transactional email + email-hygiene helpers for the anti-abuse flow.

Two responsibilities live here:

1. ``normalize_email`` — canonicalize an address (collapse Gmail dots and strip
   ``+tag`` aliases) so ``a.b+promo@gmail.com`` and ``ab@gmail.com`` map to the
   SAME account, closing the easy "alias -> another free account" trick.
2. Verification codes — generate, hash, and email a 6-digit code.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import smtplib
from email.message import EmailMessage

import httpx

from app.config import settings

logger = logging.getLogger("paperpod")

# Providers that support Gmail-style dot-insensitive local parts.
_DOT_INSENSITIVE_DOMAINS = {"gmail.com", "googlemail.com"}
# Gmail treats googlemail.com as an alias of gmail.com.
_DOMAIN_ALIASES = {"googlemail.com": "gmail.com"}


def normalize_email(email: str) -> str:
    """Return a canonical form used for duplicate-account detection.

    - lowercases and trims
    - drops ``+tag`` sub-addressing (Gmail, Outlook, Fastmail, Proton, ...)
    - for Gmail/Googlemail: removes dots in the local part and folds
      googlemail.com -> gmail.com

    Falls back to the lowercased input if the address has no ``@``.
    """
    e = (email or "").strip().lower()
    if "@" not in e:
        return e
    local, _, domain = e.partition("@")
    # Strip sub-addressing tag; keep the part before the first '+'.
    local = local.split("+", 1)[0]
    domain = _DOMAIN_ALIASES.get(domain, domain)
    if domain in _DOT_INSENSITIVE_DOMAINS:
        local = local.replace(".", "")
    return f"{local}@{domain}" if local else e


def generate_code() -> str:
    """A cryptographically-random, zero-padded 6-digit code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    """sha256 of the code — we never persist the plaintext code."""
    return hashlib.sha256((code or "").strip().encode("utf-8")).hexdigest()


def _build_bodies(code: str, name: str | None) -> tuple[str, str]:
    greeting = f"Hi {name}," if name else "Hi,"
    ttl = settings.VERIFICATION_CODE_TTL_MINUTES
    text_body = (
        f"{greeting}\n\n"
        f"Your PaperPod verification code is: {code}\n\n"
        f"Enter it in the app to start creating podcasts. "
        f"This code expires in {ttl} minutes.\n\n"
        f"If you didn't request this, you can safely ignore this email.\n\n"
        f"— PaperPod"
    )
    html_body = f"""\
<div style="font-family:Inter,Segoe UI,Arial,sans-serif;max-width:480px;margin:0 auto;color:#1c1917">
  <h2 style="color:#136458;margin:0 0 8px">Verify your email</h2>
  <p style="margin:0 0 16px;color:#57534e">{greeting}</p>
  <p style="margin:0 0 16px;color:#57534e">Use this code to start creating podcasts on PaperPod:</p>
  <div style="font-size:32px;font-weight:700;letter-spacing:8px;background:#effaf7;color:#136458;
              padding:16px 0;text-align:center;border-radius:12px;margin:0 0 16px">{code}</div>
  <p style="margin:0 0 8px;color:#78716c;font-size:13px">This code expires in {ttl} minutes.</p>
  <p style="margin:0;color:#a8a29e;font-size:12px">If you didn't request this, you can safely ignore this email.</p>
</div>"""
    return text_body, html_body


def _build_reset_bodies(code: str, name: str | None) -> tuple[str, str]:
    greeting = f"Hi {name}," if name else "Hi,"
    ttl = settings.VERIFICATION_CODE_TTL_MINUTES
    text_body = (
        f"{greeting}\n\n"
        f"Your PaperPod password reset code is: {code}\n\n"
        f"Enter it in the app to set a new password. "
        f"This code expires in {ttl} minutes.\n\n"
        f"If you didn't request a password reset, you can safely ignore this "
        f"email — your password won't change.\n\n"
        f"— PaperPod"
    )
    html_body = f"""\
<div style="font-family:Inter,Segoe UI,Arial,sans-serif;max-width:480px;margin:0 auto;color:#1c1917">
  <h2 style="color:#136458;margin:0 0 8px">Reset your password</h2>
  <p style="margin:0 0 16px;color:#57534e">{greeting}</p>
  <p style="margin:0 0 16px;color:#57534e">Use this code to set a new password on PaperPod:</p>
  <div style="font-size:32px;font-weight:700;letter-spacing:8px;background:#effaf7;color:#136458;
              padding:16px 0;text-align:center;border-radius:12px;margin:0 0 16px">{code}</div>
  <p style="margin:0 0 8px;color:#78716c;font-size:13px">This code expires in {ttl} minutes.</p>
  <p style="margin:0;color:#a8a29e;font-size:12px">If you didn't request a password reset, you can safely ignore this email — your password won't change.</p>
</div>"""
    return text_body, html_body


async def _dispatch(to_email: str, subject: str, html_body: str, text_body: str, *, log_label: str, code: str) -> bool:
    """Send via the first configured provider, with a dev-only log fallback.

    Order: Brevo -> Resend -> SMTP -> DEV fallback (log only). Never raises; a
    failed send is logged and returns False so the caller can surface it.
    """
    if settings.BREVO_API_KEY.strip():
        return await _send_via_brevo(to_email, subject, html_body, text_body)
    if settings.RESEND_API_KEY.strip():
        return await _send_via_resend(to_email, subject, html_body, text_body)
    if settings.SMTP_HOST.strip():
        return await asyncio.to_thread(_send_via_smtp, to_email, subject, html_body, text_body)

    # DEV fallback — no provider configured. Log loudly so it's obvious this is
    # not secure for production, but let the flow proceed for local testing.
    logger.warning(
        "[email] No provider configured — DEV fallback. %s for %s: %s",
        log_label, to_email, code,
    )
    return False


async def send_verification_email(to_email: str, code: str, name: str | None = None) -> bool:
    """Send the sign-up verification code via the configured provider."""
    text_body, html_body = _build_bodies(code, name)
    return await _dispatch(
        to_email, "Your PaperPod verification code", html_body, text_body,
        log_label="Verification code", code=code,
    )


async def send_password_reset_email(to_email: str, code: str, name: str | None = None) -> bool:
    """Send the password-reset code via the configured provider."""
    text_body, html_body = _build_reset_bodies(code, name)
    return await _dispatch(
        to_email, "Your PaperPod password reset code", html_body, text_body,
        log_label="Password reset code", code=code,
    )


async def send_login_alert_email(
    admin_email: str, user_email: str, user_name: str | None, method: str
) -> bool:
    """Notify the admin that a user just signed in/up (traction experiment).

    Carries only the user's name + email + the auth method. Fire-and-forget:
    never raises, returns False if no provider is configured or the send fails.
    """
    display_name = (user_name or "").strip() or "(no name)"
    subject = f"PaperPod login: {display_name}"
    text_body = (
        "A user just signed in to PaperPod.\n\n"
        f"Name:   {display_name}\n"
        f"Email:  {user_email}\n"
        f"Method: {method}\n"
    )
    html_body = f"""\
<div style="font-family:Inter,Segoe UI,Arial,sans-serif;max-width:480px;margin:0 auto;color:#1c1917">
  <h2 style="color:#136458;margin:0 0 12px">New PaperPod sign-in</h2>
  <table style="border-collapse:collapse;font-size:14px;color:#44403c">
    <tr><td style="padding:4px 12px 4px 0;color:#78716c">Name</td><td style="padding:4px 0;font-weight:600">{display_name}</td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#78716c">Email</td><td style="padding:4px 0;font-weight:600">{user_email}</td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#78716c">Method</td><td style="padding:4px 0;font-weight:600">{method}</td></tr>
  </table>
</div>"""
    if not settings.EMAIL_PROVIDER_CONFIGURED:
        logger.warning(
            "[email] Login alert requested but no provider configured (user=%s)", user_email
        )
        return False
    return await _dispatch(
        admin_email, subject, html_body, text_body,
        log_label="Login alert", code=user_email,
    )


def _parse_from(value: str) -> tuple[str, str]:
    """Split an EMAIL_FROM header into (display_name, address).

    Accepts both ``"PaperPod <a@b.com>"`` and a bare ``"a@b.com"``. Providers
    with a structured sender object (Brevo) need the two parts separately.
    """
    v = (value or "").strip()
    if "<" in v and ">" in v:
        name = v[: v.index("<")].strip().strip('"')
        addr = v[v.index("<") + 1 : v.index(">")].strip()
        return name, addr
    return "", v


async def _send_via_brevo(to_email: str, subject: str, html: str, text: str) -> bool:
    name, addr = _parse_from(settings.EMAIL_FROM)
    sender = {"email": addr}
    if name:
        sender["name"] = name
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": settings.BREVO_API_KEY.strip(),
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json={
                    "sender": sender,
                    "to": [{"email": to_email}],
                    "subject": subject,
                    "htmlContent": html,
                    "textContent": text,
                },
            )
        if resp.status_code >= 400:
            logger.error("[email] Brevo failed %s: %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # network/timeout/etc — never crash the request
        logger.error("[email] Brevo error: %s", exc)
        return False


async def _send_via_resend(to_email: str, subject: str, html: str, text: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY.strip()}"},
                json={
                    "from": settings.EMAIL_FROM,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
        if resp.status_code >= 400:
            logger.error("[email] Resend failed %s: %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # network/timeout/etc — never crash the request
        logger.error("[email] Resend error: %s", exc)
        return False


def _send_via_smtp(to_email: str, subject: str, html: str, text: str) -> bool:
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = to_email
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except smtplib.SMTPException:
                # Server without STARTTLS (rare); proceed if credentials still work.
                pass
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:
        logger.error("[email] SMTP error: %s", exc)
        return False
