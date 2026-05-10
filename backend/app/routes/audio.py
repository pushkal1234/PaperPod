from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AudioFile

router = APIRouter(prefix="/api/audio", tags=["audio"])


@router.get("/{audio_id}")
async def stream_audio(audio_id: str, db: AsyncSession = Depends(get_db)):
    """Stream/download the podcast audio file."""
    audio = await db.get(AudioFile, audio_id)
    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")

    return FileResponse(
        audio.file_path,
        media_type="audio/mpeg",
        filename=f"podcast_{audio_id}.mp3",
    )
