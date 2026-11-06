"""Product-usage events: the funnel steps no other table records.

The browser sends a few named steps (a visit, listening progress, the paywall
opening, an upgrade click). Sign-ups, podcasts, Q&A and payments are already in
their own tables, so they are not duplicated here. Everything stays in our own
database; no third-party tracker is involved.

Recording is best-effort and silent: a bad or rate-limited event is dropped
with a 200 so tracking can never break the app or show the user an error.
"""
import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Event, User, _utcnow, get_db
from app.security import client_ip, get_optional_user

router = APIRouter(prefix="/api/events", tags=["events"])
logger = logging.getLogger("paperpod")

# Steps the browser may send. Anything else is ignored, so the table can't be
# filled with arbitrary names.
CLIENT_EVENTS = {
    "visit",              # first page load in a browser tab session
    "play_started",       # pressed play on a podcast
    "listen_progress",    # value = 25 / 50 / 75 / 100 (% of the podcast heard)
    "audio_downloaded",
    "transcript_downloaded",
    "paywall_shown",      # detail = reason (quota_exceeded, upgrade, ...)
    "paywall_closed",     # closed without paying
    "upgrade_clicked",    # pressed the pay button in the paywall
    "promo_sound_on",     # turned on the sound of the home-page promo video
}
_PROGRESS_STEPS = {25.0, 50.0, 75.0, 100.0}
# Recorded once per person per podcast; repeats add nothing to the report.
_ONCE_PER_DOC = {"play_started", "listen_progress", "audio_downloaded", "transcript_downloaded"}

# Per-IP cap so nobody can flood the table. Generous: one real session sends
# well under 20 events.
_RATE_WINDOW_SECONDS = 600
_RATE_MAX_EVENTS = 120
_recent_by_ip: dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()
_SWEEP_EVERY_CALLS = 500
_calls_since_sweep = 0
# Hard cap on IPs tracked at once. The IP comes from X-Forwarded-For, which a
# client can fake per request; without a cap that could grow memory. Past the
# cap, events from new IPs are dropped until the next sweep frees room.
_MAX_TRACKED_IPS = 20_000

# Browsers whose signed-out events were already labelled with their email in
# this process, so the relabel UPDATE runs once per browser, not on every event.
_relabelled_anon_ids: set[str] = set()
_MAX_RELABELLED = 50_000


def _over_rate_limit(ip: str | None) -> bool:
    global _calls_since_sweep
    key = ip or "unknown"
    now = time.time()
    with _rate_lock:
        # Forget IPs with nothing in the window, so the table only ever holds
        # the last 10 minutes of visitors, however long the server runs.
        _calls_since_sweep += 1
        if _calls_since_sweep >= _SWEEP_EVERY_CALLS:
            _calls_since_sweep = 0
            for k in [k for k, v in _recent_by_ip.items() if not v or now - v[-1] > _RATE_WINDOW_SECONDS]:
                del _recent_by_ip[k]
        if key not in _recent_by_ip and len(_recent_by_ip) >= _MAX_TRACKED_IPS:
            return True
        q = _recent_by_ip[key]
        while q and now - q[0] > _RATE_WINDOW_SECONDS:
            q.popleft()
        if len(q) >= _RATE_MAX_EVENTS:
            return True
        q.append(now)
        return False


def _clip(value: str | None, limit: int) -> str | None:
    value = (value or "").strip()
    return value[:limit] or None


async def record_event(
    db: AsyncSession,
    name: str,
    *,
    user_id: str | None = None,
    anon_id: str | None = None,
    document_id: str | None = None,
    value: float | None = None,
    detail: str | None = None,
    user_email: str | None = None,
    user_name: str | None = None,
) -> None:
    """Store one event. Never raises: tracking must not break a request."""
    try:
        db.add(Event(
            name=name[:40],
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            anon_id=_clip(anon_id, 64),
            document_id=_clip(document_id, 64),
            value=value,
            detail=_clip(detail, 120),
            created_at=_utcnow(),
        ))
        await db.commit()
    except Exception:  # noqa: BLE001 — best-effort
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001 — a dead connection must not fail the caller
            pass
        logger.warning(f"[events] Could not record {name!r}", exc_info=True)


class EventRequest(BaseModel):
    name: str
    anon_id: str | None = None
    document_id: str | None = None
    value: float | None = None
    detail: str | None = None


@router.post("")
async def track(
    body: EventRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    name = (body.name or "").strip()
    if name not in CLIENT_EVENTS:
        return {"ok": False}
    if name == "listen_progress" and body.value not in _PROGRESS_STEPS:
        return {"ok": False}
    if _over_rate_limit(client_ip(request)):
        return {"ok": False}

    user_id = user.id if user else None
    anon_id = _clip(body.anon_id, 64)
    document_id = _clip(body.document_id, 64)
    value = body.value if name == "listen_progress" else None

    if name in _ONCE_PER_DOC and document_id and (user_id or anon_id):
        who = Event.user_id == user_id if user_id else Event.anon_id == anon_id
        q = select(Event.id).where(
            Event.name == name, Event.document_id == document_id, who,
        )
        if value is not None:
            q = q.where(Event.value == value)
        if (await db.execute(q.limit(1))).first():
            return {"ok": True}

    await record_event(
        db, name, user_id=user_id, anon_id=anon_id,
        document_id=document_id, value=value, detail=body.detail,
        user_email=user.email if user else None,
        user_name=user.name if user else None,
    )
    if user and anon_id and anon_id not in _relabelled_anon_ids:
        # This browser is now signed in: label its earlier signed-out steps
        # (e.g. the visit) with the same email and name. Once per browser.
        if len(_relabelled_anon_ids) >= _MAX_RELABELLED:
            _relabelled_anon_ids.clear()
        _relabelled_anon_ids.add(anon_id)
        try:
            await db.execute(
                update(Event)
                .where(Event.anon_id == anon_id, Event.user_email.is_(None))
                .values(user_email=user.email, user_name=user.name)
            )
            await db.commit()
        except Exception:  # noqa: BLE001 — best-effort, like the event itself
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
    return {"ok": True}
