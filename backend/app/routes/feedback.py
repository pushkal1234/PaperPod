import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Feedback, User, get_db, _utcnow
from app.security import get_optional_user

router = APIRouter(prefix="/api/feedback", tags=["feedback"])
logger = logging.getLogger("paperpod")


class FeedbackRequest(BaseModel):
    rating: int | None = None
    comment: str | None = None
    source: str = "signout"


@router.post("")
async def submit_feedback(
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Persist a star rating / comment. Works for anonymous users too, but
    captures the signed-in user's name+email so ratings can be attributed."""
    if body.rating is not None and not (1 <= body.rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5.")
    if body.rating is None and not (body.comment and body.comment.strip()):
        raise HTTPException(status_code=400, detail="Provide a rating or a comment.")

    fb = Feedback(
        user_id=user.id if user else None,
        user_name=user.name if user else None,
        user_email=user.email if user else None,
        rating=body.rating,
        comment=(body.comment or "").strip() or None,
        source=(body.source or "signout")[:50],
        created_at=_utcnow(),
    )
    db.add(fb)
    await db.commit()
    logger.info(
        f"[feedback] rating={body.rating} source={body.source} "
        f"by={user.email if user else 'anonymous'}"
    )
    return {"ok": True}
