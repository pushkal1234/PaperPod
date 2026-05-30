import uuid
import logging
import traceback
import os
import json
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db, Document, AudioFile, QASession
from app.services.document_service import save_upload, extract_text, chunk_text
from app.services.vector_service import store_chunks, delete_chunks
from app.services.llm_service import generate_podcast_script
from app.services.tts_service import generate_podcast_audio

logger = logging.getLogger("paperpod")

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _parse_transcript_segments(audio: AudioFile | None) -> list[dict] | None:
    if not audio or not audio.transcript_segments:
        return None
    try:
        return json.loads(audio.transcript_segments)
    except (json.JSONDecodeError, TypeError):
        return None


async def _process_document(doc_id: str, file_path: str, content_type: str):
    """Background task: extract text → LLM script → TTS audio."""
    from app.database import async_session

    current_step = "initializing"
    try:
        current_step = "extracting text from PDF"
        logger.info(f"[{doc_id}] Step 1/4: Extracting text...")
        raw_text = extract_text(file_path, content_type)
        logger.info(f"[{doc_id}] Extracted {len(raw_text)} chars")

        current_step = "chunking and storing text"
        chunks = chunk_text(raw_text)
        store_chunks(doc_id, chunks)
        logger.info(f"[{doc_id}] Step 2/4: Stored {len(chunks)} chunks")

        async with async_session() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.raw_text = raw_text
                doc.num_chunks = len(chunks)
                await session.commit()

        current_step = "generating podcast script (Gemini LLM)"
        logger.info(f"[{doc_id}] Step 3/4: Generating podcast script via LLM...")
        script = generate_podcast_script(raw_text)
        logger.info(f"[{doc_id}] Script generated ({len(script)} chars)")

        current_step = "synthesizing audio (Gemini TTS)"
        logger.info(f"[{doc_id}] Step 4/4: Synthesizing audio (TTS)...")
        audio_path, duration, transcript_segments = await generate_podcast_audio(script, doc_id)
        logger.info(f"[{doc_id}] Audio ready: {duration:.1f}s at {audio_path}")

        audio_id = str(uuid.uuid4())
        async with async_session() as session:
            audio = AudioFile(
                id=audio_id,
                document_id=doc_id,
                file_path=audio_path,
                duration_seconds=duration,
                dialogue_script=script,
                transcript_segments=json.dumps(transcript_segments),
                created_at=datetime.utcnow(),
            )
            session.add(audio)
            doc = await session.get(Document, doc_id)
            if doc:
                doc.status = "ready"
            await session.commit()

        logger.info(f"[{doc_id}] ✅ DONE — podcast ready (audio_id={audio_id})")

    except Exception as e:
        error_detail = f"Failed while {current_step}: {e}"
        logger.error(f"[{doc_id}] ❌ {error_detail}")
        logger.error(traceback.format_exc())
        # Mark as failed so frontend stops polling
        try:
            async with async_session() as session:
                doc = await session.get(Document, doc_id)
                if doc:
                    doc.status = "failed"
                    doc.error_message = error_detail[:500]
                    await session.commit()
        except Exception:
            logger.error(f"[{doc_id}] Could not update status to failed")


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document and start podcast generation in background."""
    content_type = file.content_type or "text/plain"

    file_bytes = await file.read()
    file_path = save_upload(file_bytes, file.filename)

    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        filename=file.filename,
        content_type=content_type,
        raw_text="",
        num_chunks=0,
        created_at=datetime.utcnow(),
    )
    db.add(doc)
    await db.commit()

    logger.info(f"[{doc_id}] Upload received: {file.filename} ({content_type})")

    background_tasks.add_task(
        _process_document, doc_id, file_path, content_type
    )

    return {"doc_id": doc_id, "filename": file.filename, "status": "processing"}


@router.get("/list")
async def list_documents(db: AsyncSession = Depends(get_db)):
    """List all uploaded documents."""
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    docs = result.scalars().all()

    items = []
    for doc in docs:
        audio_result = await db.execute(
            select(AudioFile).where(AudioFile.document_id == doc.id)
        )
        audio = audio_result.scalar_one_or_none()
        items.append({
            "doc_id": doc.id,
            "filename": doc.filename,
            "num_chunks": doc.num_chunks,
            "created_at": doc.created_at.isoformat(),
            "status": doc.status or ("ready" if audio else "processing"),
            "audio_id": audio.id if audio else None,
        })

    return {"documents": items}


@router.get("/{doc_id}")
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Get document metadata and processing status."""
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(AudioFile).where(AudioFile.document_id == doc_id)
    )
    audio = result.scalar_one_or_none()

    status = doc.status or ("ready" if audio else "processing")

    return {
        "doc_id": doc.id,
        "filename": doc.filename,
        "num_chunks": doc.num_chunks,
        "created_at": doc.created_at.isoformat(),
        "status": status,
        "error": doc.error_message if status == "failed" else None,
        "audio": {
            "audio_id": audio.id,
            "duration_seconds": audio.duration_seconds,
            "audio_url": f"/api/audio/{audio.id}",
            "dialogue_script": audio.dialogue_script,
            "transcript_segments": _parse_transcript_segments(audio),
        }
        if audio
        else None,
    }


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a document and all associated audio + Q&A history."""
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Collect file paths to delete (best-effort)
    audio_result = await db.execute(
        select(AudioFile).where(AudioFile.document_id == doc_id)
    )
    audio = audio_result.scalar_one_or_none()

    qa_result = await db.execute(
        select(QASession).where(QASession.document_id == doc_id)
    )
    qa_sessions = qa_result.scalars().all()

    file_paths: list[str] = []
    if audio and audio.file_path:
        file_paths.append(audio.file_path)
    for s in qa_sessions:
        if s.question_audio_path:
            file_paths.append(s.question_audio_path)
        if s.answer_audio_path:
            file_paths.append(s.answer_audio_path)

    # Delete DB rows
    await db.execute(delete(QASession).where(QASession.document_id == doc_id))
    await db.execute(delete(AudioFile).where(AudioFile.document_id == doc_id))
    await db.execute(delete(Document).where(Document.id == doc_id))
    await db.commit()

    # Remove in-memory chunks (if present)
    delete_chunks(doc_id)

    # Delete files after commit (best-effort)
    deleted_files = 0
    for p in file_paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
                deleted_files += 1
        except Exception:
            # best-effort cleanup; DB delete already succeeded
            pass

    return {"ok": True, "doc_id": doc_id, "deleted_files": deleted_files}
