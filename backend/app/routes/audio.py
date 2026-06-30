import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AudioFile

router = APIRouter(prefix="/api/audio", tags=["audio"])


def _range_response(file_path: str, range_header: str, filename: str):
    """Return a 206 Partial Content response for HTTP Range requests.

    Mobile browsers (especially Safari) require Range support to report the
    correct audio duration and allow seeking.  Without this the duration shows
    as Infinity and the seek bar is unusable.
    """
    file_size = os.path.getsize(file_path)

    # Parse "bytes=start-end"
    try:
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
    except (ValueError, IndexError):
        start, end = 0, file_size - 1

    start = max(0, start)
    end = min(end, file_size - 1)
    content_length = end - start + 1

    def iter_file():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = f.read(min(8192, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_file(),
        status_code=206,
        media_type="audio/mpeg",
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Disposition": f'inline; filename="{filename}"',
            # A partial (206) response must NEVER be stored by a shared/CDN
            # cache. If it were, the edge could serve that single byte-slice
            # for every request to this URL (including non-Range requests),
            # returning a truncated, header-less MP3 that won't play, seek, or
            # download. Keep partials browser-private only; the full 200
            # response below is what gets cached long-term.
            "Cache-Control": "private, no-store",
            "Vary": "Range",
        },
    )


@router.get("/{audio_id}")
async def stream_audio(audio_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Stream/download the podcast audio file with Range request support."""
    audio = await db.get(AudioFile, audio_id)
    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")

    # The row can outlive the file (e.g. storage wiped before persistent
    # volumes were attached). Return a clean 404 instead of a 500 from
    # os.stat / FileResponse on a missing path.
    if not audio.file_path or not os.path.exists(audio.file_path):
        raise HTTPException(status_code=404, detail="This podcast's audio is no longer available.")

    filename = f"podcast_{audio_id}.mp3"
    range_header = request.headers.get("range")

    # Mobile browsers send Range requests; respond with 206 for proper duration/seeking
    if range_header:
        return _range_response(audio.file_path, range_header, filename)

    # Normal full-file response with Content-Length so browsers know the duration.
    # Only the complete file (200) is safe to cache long-term; `Vary: Range`
    # keeps it from ever being served in place of a Range request and vice versa.
    stat = os.stat(audio.file_path)
    return FileResponse(
        audio.file_path,
        media_type="audio/mpeg",
        filename=filename,
        stat_result=stat,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=31536000, immutable",
            "Vary": "Range",
        },
    )
