import json
import logging
import secrets

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, AudioFile, Document

router = APIRouter(prefix="/api/share", tags=["share"])
logger = logging.getLogger("paperpod")


def _generate_token() -> str:
    """Generate a URL-safe share token."""
    return secrets.token_urlsafe(12)


@router.post("/create/{doc_id}")
async def create_share(doc_id: str):
    """Generate or return an existing share token for a document's podcast."""
    async with async_session() as session:
        # Check if document exists and has audio
        doc = await session.get(Document, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        result = await session.execute(
            select(AudioFile).where(AudioFile.document_id == doc_id)
        )
        audio = result.scalar_one_or_none()
        if not audio:
            raise HTTPException(status_code=404, detail="Podcast not ready yet")

        # Return existing token if already shared
        if audio.share_token:
            return {"share_token": audio.share_token, "share_url": f"/share/{audio.share_token}"}

        # Generate new token
        token = _generate_token()
        audio.share_token = token
        await session.commit()

        logger.info(f"[{doc_id}] Share token created: {token}")
        return {"share_token": token, "share_url": f"/share/{token}"}


@router.get("/{token}")
async def get_shared_podcast(token: str):
    """Public endpoint: get podcast metadata for a share token."""
    async with async_session() as session:
        result = await session.execute(
            select(AudioFile).where(AudioFile.share_token == token)
        )
        audio = result.scalar_one_or_none()
        if not audio:
            raise HTTPException(status_code=404, detail="Shared podcast not found")

        doc = await session.get(Document, audio.document_id)
        title = doc.filename if doc else "Shared Podcast"

        transcript_segments = None
        if audio.transcript_segments:
            try:
                transcript_segments = json.loads(audio.transcript_segments)
            except json.JSONDecodeError:
                pass

        return {
            "title": title,
            "audio_id": audio.id,
            "duration_seconds": audio.duration_seconds,
            "dialogue_script": audio.dialogue_script,
            "transcript_segments": transcript_segments,
            "created_at": audio.created_at.isoformat() if audio.created_at else None,
        }
