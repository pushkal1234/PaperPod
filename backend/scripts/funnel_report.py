"""Where do users drop off? Prints PaperPod's sign-up-to-paying funnel.

Run from the backend folder, with DATABASE_URL pointing at the database:

    python -m scripts.funnel_report              # users who signed up in the last 30 days
    python -m scripts.funnel_report --days 90
    python -m scripts.funnel_report --users      # also list each user's furthest step

Sign-ups, podcasts, Q&A and payments come from their own tables, so those
steps cover every user. Listening, paywall and visit steps come from the
`events` table, which only fills from the day tracking was deployed: users who
signed up before then show 0 for those steps.

Read-only: it never writes to the database.
"""
import argparse
import asyncio
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Document, Event, QASession, User, async_session  # noqa: E402


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# Funnel steps in order. Each is (label, test on one user's facts).
STEPS = [
    ("Signed up", lambda f: True),
    ("Verified email", lambda f: f["verified"]),
    ("Started a podcast", lambda f: f["docs"] > 0),
    ("Got a finished podcast", lambda f: f["ready"] > 0),
    ("Pressed play", lambda f: f["played"]),
    ("Heard 25%+ of a podcast", lambda f: f["heard"] >= 25),
    ("Heard 50%+", lambda f: f["heard"] >= 50),
    ("Heard all of it", lambda f: f["heard"] >= 100),
    ("Asked a Q&A question", lambda f: f["qa"] > 0),
    ("Used all free podcasts", lambda f: f["used"] >= settings.FREE_LIFETIME_PODCASTS),
    ("Saw the paywall", lambda f: f["paywall"]),
    ("Clicked pay", lambda f: f["clicked_pay"]),
    ("Reached checkout page", lambda f: f["checkout"]),
    ("Paying now", lambda f: f["premium"]),
]


async def build(days: int, exclude: set[str]):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with async_session() as db:
        users = (await db.execute(
            select(User.id, User.email, User.created_at, User.email_verified, User.plan)
            .where(User.created_at >= since)
        )).all()
        users = [u for u in users if (u.email or "").lower() not in exclude]
        ids = [u.id for u in users]

        docs = (await db.execute(
            select(Document.user_id, Document.status, Document.created_at)
            .where(Document.user_id.in_(ids))
        )).all() if ids else []
        qa = (await db.execute(
            select(Document.user_id, func.count(QASession.id))
            .join(QASession, QASession.document_id == Document.id)
            .where(Document.user_id.in_(ids))
            .group_by(Document.user_id)
        )).all() if ids else []
        events = (await db.execute(
            select(Event.name, Event.user_id, Event.anon_id, Event.value, Event.detail, Event.created_at)
            .where(Event.created_at >= since)
        )).all()
        first_event = (await db.execute(select(func.min(Event.created_at)))).scalar()

    facts = {}
    for u in users:
        facts[u.id] = {
            "email": u.email, "signed_up": _aware(u.created_at),
            "verified": bool(u.email_verified), "premium": u.plan == "premium",
            "docs": 0, "ready": 0, "failed": 0, "used": 0, "qa": 0,
            "played": False, "heard": 0, "paywall": False, "clicked_pay": False,
            "checkout": False, "downloaded": False, "transcript": False, "active_days": set(),
        }
    for d in docs:
        f = facts.get(d.user_id)
        if not f:
            continue
        f["docs"] += 1
        f["ready"] += d.status == "ready"
        f["failed"] += d.status == "failed"
        f["used"] += d.status != "failed"  # same rule as the free-podcast quota
        if d.created_at:
            f["active_days"].add(_aware(d.created_at).date())
    for user_id, n in qa:
        if user_id in facts:
            facts[user_id]["qa"] = n

    anon_to_user = {e.anon_id: e.user_id for e in events if e.anon_id and e.user_id}
    for e in events:
        # Steps taken while signed out count for the account that browser
        # signed in to later.
        f = facts.get(e.user_id or anon_to_user.get(e.anon_id))
        if not f:
            continue
        if e.created_at:
            f["active_days"].add(_aware(e.created_at).date())
        if e.name == "play_started":
            f["played"] = True
        elif e.name == "listen_progress":
            f["played"] = True
            f["heard"] = max(f["heard"], int(e.value or 0))
        elif e.name == "paywall_shown":
            f["paywall"] = True
        elif e.name == "upgrade_clicked":
            f["clicked_pay"] = True
        elif e.name == "checkout_started":
            f["checkout"] = f["clicked_pay"] = True
        elif e.name == "audio_downloaded":
            f["downloaded"] = True
        elif e.name == "transcript_downloaded":
            f["transcript"] = True

    visits = [e for e in events if e.name == "visit" and e.anon_id]
    promo_sound = {e.anon_id or e.user_id for e in events if e.name == "promo_sound_on"}
    return since, facts, visits, anon_to_user, _aware(first_event), len(promo_sound)


def report(days: int, exclude: set[str], list_users: bool) -> None:
    since, facts, visits, anon_to_user, first_event, promo_sound = asyncio.run(build(days, exclude))
    people = list(facts.values())
    total = len(people)

    print(f"\nPaperPod funnel: users who signed up since {since:%Y-%m-%d} ({days} days)")
    if exclude:
        print(f"Excluding: {', '.join(sorted(exclude))}")
    if first_event is None:
        print("NOTE: no tracking events yet, so listening/paywall steps are all 0.")
    elif first_event > since:
        print(
            f"NOTE: tracking started {first_event:%Y-%m-%d}. Users who signed up before "
            f"that show 0 for listening and paywall steps. Use --days "
            f"{max(1, (datetime.now(timezone.utc) - first_event).days)} for a clean view."
        )

    if visits:
        visitors = {e.anon_id for e in visits}
        signed = {a for a in visitors if a in anon_to_user}
        print(f"\nVisitors (browsers): {len(visitors)}   later signed in: {len(signed)}")
        by_source = Counter()
        seen = set()
        for e in visits:
            if e.anon_id not in seen:
                seen.add(e.anon_id)
                by_source[(e.detail or "direct")[:30]] += 1
        print("  where they came from: " + ", ".join(f"{s} {n}" for s, n in by_source.most_common(8)))

    print(f"Turned on the home-page promo video's sound: {promo_sound}")

    print()
    if not total:
        print("No sign-ups in this period.")
        return
    # "% of previous step" = of the people who did the step above, how many
    # also did this one (steps aren't strictly nested, e.g. Q&A without listening).
    prev_test = None
    width = max(len(label) for label, _ in STEPS)
    for label, test in STEPS:
        n = sum(1 for f in people if test(f))
        of_all = 100 * n / total
        line = f"  {label:<{width}}  {n:>5}  {of_all:5.1f}% of sign-ups"
        if prev_test is not None:
            base = [f for f in people if prev_test(f)]
            kept = sum(1 for f in base if test(f))
            line += f"   {100 * kept / len(base):5.1f}% of previous step" if base else "       -  of previous step"
        print(line)
        prev_test = test

    failed = sum(1 for f in people if f["failed"])
    only_failed = sum(1 for f in people if f["failed"] and not f["ready"])
    came_back = sum(
        1 for f in people
        if f["signed_up"] and any(d > f["signed_up"].date() for d in f["active_days"])
    )
    print(f"\n  Had a podcast fail:            {failed:>5}   (never got one that worked: {only_failed})")
    print(f"  Came back on a later day:      {came_back:>5}")
    print(f"  Downloaded audio:              {sum(f['downloaded'] for f in people):>5}")
    print(f"  Downloaded transcript:         {sum(f['transcript'] for f in people):>5}")

    if list_users:
        print("\nEach user's furthest step:")
        for f in sorted(people, key=lambda f: f["signed_up"] or since):
            furthest = [label for label, test in STEPS if test(f)][-1]
            print(f"  {f['signed_up']:%Y-%m-%d}  {f['email']:<38} {furthest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PaperPod sign-up-to-paying funnel")
    parser.add_argument("--days", type=int, default=30, help="look-back window (default 30)")
    parser.add_argument(
        "--exclude", default=settings.LOGIN_ALERT_EMAIL,
        help="comma-separated emails to leave out, e.g. your own test accounts "
             "(default: LOGIN_ALERT_EMAIL)",
    )
    parser.add_argument("--users", action="store_true", help="list each user's furthest step")
    args = parser.parse_args()
    exclude = {e.strip().lower() for e in (args.exclude or "").split(",") if e.strip()}
    report(args.days, exclude, args.users)


if __name__ == "__main__":
    main()
