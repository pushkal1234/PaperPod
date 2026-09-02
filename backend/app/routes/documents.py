import uuid
import logging
import traceback
import os
import json
import time
import asyncio
import hashlib
import mimetypes

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db, Document, AudioFile, QASession, User, _utcnow
from app.security import get_current_user, get_upload_user, client_ip
from app.entitlements import (
    enforce_can_create_podcast,
    enforce_email_verified,
    enforce_ip_quota,
)
from app.services.document_service import save_upload, extract_text, chunk_text, clean_extracted_text
from app.services.vector_service import store_chunks, delete_chunks
from app.services.llm_service import generate_podcast_script
from app.services.tts_service import generate_podcast_audio
from app.services.email_service import send_upload_alert_email
from app.mem_utils import trim_memory

logger = logging.getLogger("paperpod")

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Heavy LLM+TTS jobs run in the web process via BackgroundTasks; cap how many
# run at once so a burst of uploads can't exhaust the process or trip provider
# rate limits. (A dedicated Redis-backed worker is the production-grade step.)
_job_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)

# Transient, in-process progress signal for the frontend's processing screen.
# Maps doc_id -> current pipeline stage (see _STAGE_* below). This is deliberately
# in-memory, NOT a DB column: it's an ephemeral UX hint polled via GET /{doc_id},
# costs a few bytes per active job, and is cleared on completion. If the process
# restarts mid-job the job dies anyway (orphan recovery marks it failed), so
# losing the hint is harmless. Single-worker deployment assumed (see start cmd).
_STAGE_READING = "reading"
_STAGE_ANALYZING_FIGURES = "analyzing_figures"
_STAGE_WRITING_SCRIPT = "writing_script"
_STAGE_SYNTHESIZING = "synthesizing"
_doc_stages: dict[str, str] = {}


def _set_stage(doc_id: str, stage: str) -> None:
    """Record the current pipeline stage. Safe to call from any thread (a plain
    dict write is atomic under the GIL), so the sync extraction worker can report
    the figure-description sub-step directly."""
    _doc_stages[doc_id] = stage


def _clear_stage(doc_id: str) -> None:
    _doc_stages.pop(doc_id, None)


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif", ".bmp", ".tiff")


def _source_from_filename(filename: str) -> str:
    """Classify a file upload into an analytics source bucket by extension.

    Returns one of: pdf | docx | pptx | txt | image | other. Kept in sync with
    the backfill CASE in database._BACKFILL_SOURCE_SQL so historical and new
    rows use the same vocabulary. The /text (paste) and /image endpoints set
    their source explicitly and don't call this.
    """
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith((".docx", ".doc")):
        return "docx"
    if name.endswith((".pptx", ".ppt")):
        return "pptx"
    if name.endswith(".txt"):
        return "txt"
    if name.endswith(_IMAGE_EXTS):
        return "image"
    return "other"


def _queue_upload_alert(
    background_tasks: BackgroundTasks, user: User | None, doc_name: str, doc_type: str
) -> None:
    """Fire-and-forget an admin "user uploaded a doc" email, if the flag is on.

    Reuses the LOGIN_ALERTS_ENABLED switch (same traction experiment) and the
    same per-user subject as the sign-in alert, so uploads thread under that
    user's conversation. Only for SIGNED-IN users — anonymous uploads have no
    identity to attribute, so there's nothing to track. Scheduled as a
    background task so it never adds latency to, or fails, an upload.
    """
    if not settings.LOGIN_ALERTS_ENABLED or user is None:
        return
    background_tasks.add_task(
        send_upload_alert_email,
        settings.LOGIN_ALERT_EMAIL,
        user.email,
        user.name,
        doc_name,
        doc_type,
    )


def _content_hash(data: bytes) -> str:
    """sha256 of the source, salted with the generation pipeline version.

    Folding GENERATION_VERSION in means any change to the extraction/prompt/
    LLM/TTS pipeline (bump the version) makes re-uploads MISS caches produced by
    the previous pipeline and regenerate, instead of serving an old, buggy
    podcast. Old rows keep their previous hash and simply never match again.
    """
    return hashlib.sha256(f"{settings.GENERATION_VERSION}:".encode() + data).hexdigest()


async def _find_reusable_document(
    db: AsyncSession, content_hash: str, user_id: str | None
) -> Document | None:
    """Return an existing non-failed document with the same content hash.

    Lets repeated uploads of identical content reuse the already-generated
    podcast instead of paying for LLM+TTS again (idempotent uploads).

    Scoped to the uploader: a signed-in user only dedupes against their own
    podcasts, and anonymous uploads only dedupe against anonymous ones. This
    prevents one account's content from leaking into another via dedup.
    """
    result = await db.execute(
        select(Document)
        .where(
            Document.content_hash == content_hash,
            Document.status.in_(["ready", "processing"]),
            Document.user_id == user_id,
            # Never dedupe onto a soft-deleted podcast: its audio has been purged,
            # so reusing it would hand back a broken (playback-less) result.
            Document.deleted_at.is_(None),
        )
        .order_by(Document.created_at.desc())
    )
    return result.scalars().first()

# Provider keywords that must never leak to the user
_PROVIDER_KEYWORDS = ["groq", "whisper", "edge-tts", "edge_tts", "google", "gemini", "gtts", "g_tts", "serpapi", "azure"]


def _sanitize_error(msg: str) -> str:
    """Strip provider names from error messages before sending to frontend."""
    if not msg:
        return msg
    clean = msg
    for kw in _PROVIDER_KEYWORDS:
        clean = clean.replace(kw, "the service")
        clean = clean.replace(kw.upper(), "the service")
        clean = clean.replace(kw.title(), "the service")
    # Also catch API-key style references
    clean = clean.replace("api_key", "configuration")
    clean = clean.replace("API_KEY", "configuration")
    return clean


def _podcast_quality_issue(script: str, duration: float) -> str | None:
    """Return a reason string if the generated podcast is degenerate, else None.

    Guards against caching/serving broken output (e.g. the 9-second, outro-only
    episode). Callers should mark such docs "failed" — failed docs are excluded
    from dedup, so the next upload regenerates instead of reusing the bad one.
    """
    lines = [
        l for l in (script or "").split("\n")
        if l.strip().lower().startswith(("host:", "guest:"))
    ]
    if len(lines) < settings.MIN_PODCAST_DIALOGUE_LINES:
        return f"script too short ({len(lines)} dialogue lines, need >= {settings.MIN_PODCAST_DIALOGUE_LINES})"
    if duration < settings.MIN_PODCAST_DURATION_SECONDS:
        return f"audio too short ({duration:.0f}s, need >= {settings.MIN_PODCAST_DURATION_SECONDS:.0f}s)"
    return None


def _parse_transcript_segments(audio: AudioFile | None) -> list[dict] | None:
    if not audio or not audio.transcript_segments:
        return None
    try:
        return json.loads(audio.transcript_segments)
    except (json.JSONDecodeError, TypeError):
        return None


async def _process_document(doc_id: str, file_path: str, content_type: str):
    """Background entrypoint (file upload) — concurrency-limited pipeline."""
    async with _job_semaphore:
        try:
            await _run_document_pipeline(doc_id, file_path, content_type)
        finally:
            # The source upload is only needed for text extraction; raw_text is
            # persisted in the DB. By default we now RETAIN the upload (renamed to
            # the doc id, so it's easy to correlate with logs/DB) for inspecting
            # failed/undershoot cases; set KEEP_UPLOADS=0 to purge it instead so
            # the storage volume doesn't grow with every upload.
            if settings.KEEP_UPLOADS:
                try:
                    ext = os.path.splitext(file_path)[1]
                    kept_path = os.path.join(settings.UPLOAD_DIR, f"{doc_id}{ext}")
                    if os.path.abspath(kept_path) != os.path.abspath(file_path):
                        os.replace(file_path, kept_path)
                except OSError:
                    pass
            else:
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            # Hand freed heap (PDF/vision/TTS buffers) back to the OS so idle RSS
            # falls instead of plateauing. Off the event loop — malloc_trim blocks.
            await run_in_threadpool(trim_memory)
            _clear_stage(doc_id)


async def _run_document_pipeline(doc_id: str, file_path: str, content_type: str):
    """Extract text → LLM script → TTS audio."""
    from app.database import async_session

    overall_start = time.perf_counter()
    step_times = {}
    current_step = "initializing"
    try:
        current_step = "extracting text from PDF"
        t0 = time.perf_counter()
        logger.info(f"[{doc_id}] Step 1/4: Extracting text...")
        _set_stage(doc_id, _STAGE_READING)
        # Fires only if the PDF actually has figures worth describing, so the
        # "Analyzing diagrams & figures" step surfaces to the user exactly when
        # that (~30-60s) vision call runs — and never for figure-less docs.
        on_figures = lambda: _set_stage(doc_id, _STAGE_ANALYZING_FIGURES)
        # Offload blocking PDF/DOCX parsing to a thread so the event loop stays free.
        raw_text = await run_in_threadpool(extract_text, file_path, content_type, on_figures)
        step_times['extract'] = time.perf_counter() - t0
        logger.info(f"[{doc_id}] Extracted {len(raw_text)} chars in {step_times['extract']:.2f}s")

        current_step = "chunking and storing text"
        t0 = time.perf_counter()
        chunks = chunk_text(raw_text)
        store_chunks(doc_id, chunks)
        step_times['chunk'] = time.perf_counter() - t0
        logger.info(f"[{doc_id}] Step 2/4: Stored {len(chunks)} chunks in {step_times['chunk']:.2f}s")

        async with async_session() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.raw_text = raw_text
                doc.num_chunks = len(chunks)
                await session.commit()

        current_step = "generating podcast script"
        t0 = time.perf_counter()
        logger.info(f"[{doc_id}] Step 3/4: Generating podcast script via LLM...")
        _set_stage(doc_id, _STAGE_WRITING_SCRIPT)
        # The Groq client is synchronous/blocking — run it off the event loop.
        script = await run_in_threadpool(generate_podcast_script, raw_text)
        step_times['llm'] = time.perf_counter() - t0
        logger.info(f"[{doc_id}] Script generated ({len(script)} chars) in {step_times['llm']:.2f}s")

        current_step = "synthesizing audio"
        t0 = time.perf_counter()
        logger.info(f"[{doc_id}] Step 4/4: Synthesizing audio (TTS)...")
        _set_stage(doc_id, _STAGE_SYNTHESIZING)
        audio_path, duration, transcript_segments = await generate_podcast_audio(script, doc_id)
        step_times['tts'] = time.perf_counter() - t0
        logger.info(f"[{doc_id}] Audio ready: {duration:.1f}s at {audio_path} in {step_times['tts']:.2f}s")

        current_step = "validating podcast"
        quality_issue = _podcast_quality_issue(script, duration)
        if quality_issue:
            try:
                os.remove(audio_path)
            except OSError:
                pass
            raise RuntimeError(f"Generated podcast failed quality check: {quality_issue}")

        audio_id = str(uuid.uuid4())
        async with async_session() as session:
            audio = AudioFile(
                id=audio_id,
                document_id=doc_id,
                file_path=audio_path,
                duration_seconds=duration,
                dialogue_script=script,
                transcript_segments=json.dumps(transcript_segments),
                created_at=_utcnow(),
            )
            session.add(audio)
            doc = await session.get(Document, doc_id)
            if doc:
                doc.status = "ready"
            await session.commit()

        total = time.perf_counter() - overall_start
        logger.info(
            f"[{doc_id}] ⏱️ TIMING — extract={step_times['extract']:.2f}s, "
            f"chunk={step_times['chunk']:.2f}s, llm={step_times['llm']:.2f}s, "
            f"tts={step_times['tts']:.2f}s, total={total:.2f}s, "
            f"chars={len(raw_text)}, chunks={len(chunks)}, turns={len([l for l in script.split(chr(10)) if l.strip()])}"
        )
        logger.info(f"[{doc_id}] ✅ DONE — podcast ready (audio_id={audio_id})")

    except Exception as e:
        total = time.perf_counter() - overall_start
        error_detail = _sanitize_error(f"Failed while {current_step}: {e}")
        logger.error(f"[{doc_id}] ❌ {error_detail} (total elapsed: {total:.2f}s)")
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
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_upload_user),
):
    """Upload a document and start podcast generation in background."""
    content_type = file.content_type or "text/plain"
    ip = client_ip(request)

    file_bytes = await file.read()
    if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_MB} MB.")
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    user_id = user.id if user else None
    content_hash = _content_hash(file_bytes)
    existing = await _find_reusable_document(db, content_hash, user_id)
    if existing:
        logger.info(f"[{existing.id}] Dedup hit for re-upload of {file.filename}")
        return {"doc_id": existing.id, "filename": existing.filename, "status": existing.status, "deduped": True}

    enforce_email_verified(user)
    await enforce_can_create_podcast(db, user)
    await enforce_ip_quota(db, user, ip)

    file_path = save_upload(file_bytes, file.filename)

    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        user_id=user_id,
        filename=file.filename,
        content_type=content_type,
        raw_text="",
        num_chunks=0,
        content_hash=content_hash,
        source=_source_from_filename(file.filename),
        creator_ip=ip,
        created_at=_utcnow(),
    )
    db.add(doc)
    await db.commit()

    logger.info(f"[{doc_id}] Upload received: {file.filename} ({content_type})")
    background_tasks.add_task(_process_document, doc_id, file_path, content_type)
    _queue_upload_alert(background_tasks, user, doc.filename, doc.source)
    return {"doc_id": doc_id, "filename": file.filename, "status": "processing"}


@router.post("/text")
async def upload_text(
    background_tasks: BackgroundTasks,
    request: Request,
    text: str = Form(...),
    title: str = Form("Pasted text"),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_upload_user),
):
    """Upload raw text directly (copy-paste)."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text provided.")
    ip = client_ip(request)
    # Strip NUL/control bytes before hashing or storing — pasted text can carry
    # them (e.g. copied from a PDF) and Postgres rejects 0x00 in text columns.
    text = clean_extracted_text(text)
    text_bytes = text.encode("utf-8")
    if len(text_bytes) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Text too large. Maximum size is {settings.MAX_UPLOAD_MB} MB.")

    user_id = user.id if user else None
    content_hash = _content_hash(text_bytes)
    existing = await _find_reusable_document(db, content_hash, user_id)
    if existing:
        logger.info(f"[{existing.id}] Dedup hit for re-submitted text")
        return {"doc_id": existing.id, "filename": existing.filename, "status": existing.status, "deduped": True}

    enforce_email_verified(user)
    await enforce_can_create_podcast(db, user)
    await enforce_ip_quota(db, user, ip)

    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        user_id=user_id,
        filename=f"{title}.txt",
        content_type="text/plain",
        raw_text=text,
        num_chunks=0,
        content_hash=content_hash,
        source="pasted",
        creator_ip=ip,
        created_at=_utcnow(),
    )
    db.add(doc)
    await db.commit()

    logger.info(f"[{doc_id}] Text upload received: {len(text)} chars")
    background_tasks.add_task(_process_text_document, doc_id, text)
    _queue_upload_alert(background_tasks, user, doc.filename, doc.source)
    return {"doc_id": doc_id, "filename": f"{title}.txt", "status": "processing"}


@router.post("/image")
async def upload_image(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_upload_user),
):
    """Upload an image — OCR extracts text in background, then generates podcast."""
    ip = client_ip(request)
    image_bytes = await file.read()
    if len(image_bytes) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Image too large. Maximum size is {settings.MAX_UPLOAD_MB} MB.")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    mime_type = file.content_type or "image/jpeg"

    user_id = user.id if user else None
    content_hash = _content_hash(image_bytes)
    existing = await _find_reusable_document(db, content_hash, user_id)
    if existing:
        logger.info(f"[{existing.id}] Dedup hit for re-uploaded image {file.filename}")
        return {"doc_id": existing.id, "filename": existing.filename, "status": existing.status, "deduped": True}

    enforce_email_verified(user)
    await enforce_can_create_podcast(db, user)
    await enforce_ip_quota(db, user, ip)

    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        user_id=user_id,
        filename=file.filename,
        content_type="text/plain",
        raw_text="",
        num_chunks=0,
        content_hash=content_hash,
        source="image",
        creator_ip=ip,
        created_at=_utcnow(),
    )
    db.add(doc)
    await db.commit()

    logger.info(f"[{doc_id}] Image upload received: {file.filename} ({len(image_bytes)} bytes)")
    background_tasks.add_task(_process_image_document, doc_id, image_bytes, mime_type)
    _queue_upload_alert(background_tasks, user, doc.filename, doc.source)
    return {"doc_id": doc_id, "filename": file.filename, "status": "processing"}


async def _process_image_document(doc_id: str, image_bytes: bytes, mime_type: str):
    """Background task: OCR image, then chunks → LLM → TTS."""
    from app.services.image_service import extract_text_from_image
    from app.database import async_session

    # Retain the source image for inspection (parity with the file-upload path in logs)
    if settings.KEEP_UPLOADS:
        try:
            ext = mimetypes.guess_extension((mime_type or "").split(";")[0].strip() or "image/jpeg")
            if ext in (None, ".jpe"):
                ext = ".jpg"
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            with open(os.path.join(settings.UPLOAD_DIR, f"{doc_id}{ext}"), "wb") as f:
                f.write(image_bytes)
        except OSError:
            pass

    # Step 1: OCR (can take 10-60s for large camera photos). The upload IS an
    # image, so surface this vision pass as the "Analyzing diagrams & figures"
    # step — the same honest signal the PDF/PPTX/DOCX figure pass uses.
    _set_stage(doc_id, _STAGE_ANALYZING_FIGURES)
    try:
        t0 = time.perf_counter()
        raw_text = await run_in_threadpool(extract_text_from_image, image_bytes, mime_type)
        # OCR output can contain NUL/control bytes that Postgres rejects.
        raw_text = clean_extracted_text(raw_text)
        ocr_time = time.perf_counter() - t0
        logger.info(f"[{doc_id}] OCR extracted {len(raw_text)} chars in {ocr_time:.2f}s")
    except Exception as e:
        error_detail = _sanitize_error(f"OCR failed: {e}")
        logger.error(f"[{doc_id}] ❌ {error_detail}")
        try:
            async with async_session() as session:
                doc = await session.get(Document, doc_id)
                if doc:
                    doc.status = "failed"
                    doc.error_message = error_detail[:500]
                    await session.commit()
        except Exception:
            pass
        _clear_stage(doc_id)
        return

    # Save extracted text to DB
    try:
        async with async_session() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.raw_text = raw_text
                await session.commit()
    except Exception:
        logger.error(f"[{doc_id}] Failed to persist OCR text before generation", exc_info=True)

    # Step 2: Use the shared text pipeline
    await _process_text_document(doc_id, raw_text)


async def _process_text_document(doc_id: str, raw_text: str):
    """Background entrypoint (text/image) — concurrency-limited pipeline."""
    async with _job_semaphore:
        try:
            await _run_text_pipeline(doc_id, raw_text)
        finally:
            # Release freed heap back to the OS after the job (see _process_document).
            await run_in_threadpool(trim_memory)
            _clear_stage(doc_id)


async def _run_text_pipeline(doc_id: str, raw_text: str):
    """Skip file extraction, go straight to chunks → LLM → TTS."""
    from app.database import async_session

    overall_start = time.perf_counter()
    step_times = {}
    current_step = "initializing"
    try:
        current_step = "chunking and storing text"
        t0 = time.perf_counter()
        chunks = chunk_text(raw_text)
        store_chunks(doc_id, chunks)
        step_times['chunk'] = time.perf_counter() - t0
        logger.info(f"[{doc_id}] Step 2/4: Stored {len(chunks)} chunks in {step_times['chunk']:.2f}s")

        async with async_session() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.num_chunks = len(chunks)
                await session.commit()

        current_step = "generating podcast script"
        t0 = time.perf_counter()
        logger.info(f"[{doc_id}] Step 3/4: Generating podcast script via LLM...")
        _set_stage(doc_id, _STAGE_WRITING_SCRIPT)
        # The Groq client is synchronous/blocking — run it off the event loop.
        script = await run_in_threadpool(generate_podcast_script, raw_text)
        step_times['llm'] = time.perf_counter() - t0
        logger.info(f"[{doc_id}] Script generated ({len(script)} chars) in {step_times['llm']:.2f}s")

        current_step = "synthesizing audio"
        t0 = time.perf_counter()
        logger.info(f"[{doc_id}] Step 4/4: Synthesizing audio (TTS)...")
        _set_stage(doc_id, _STAGE_SYNTHESIZING)
        audio_path, duration, transcript_segments = await generate_podcast_audio(script, doc_id)
        step_times['tts'] = time.perf_counter() - t0
        logger.info(f"[{doc_id}] Audio ready: {duration:.1f}s in {step_times['tts']:.2f}s")

        current_step = "validating podcast"
        quality_issue = _podcast_quality_issue(script, duration)
        if quality_issue:
            try:
                os.remove(audio_path)
            except OSError:
                pass
            raise RuntimeError(f"Generated podcast failed quality check: {quality_issue}")

        audio_id = str(uuid.uuid4())
        async with async_session() as session:
            audio = AudioFile(
                id=audio_id,
                document_id=doc_id,
                file_path=audio_path,
                duration_seconds=duration,
                dialogue_script=script,
                transcript_segments=json.dumps(transcript_segments),
                created_at=_utcnow(),
            )
            session.add(audio)
            doc = await session.get(Document, doc_id)
            if doc:
                doc.status = "ready"
            await session.commit()

        total = time.perf_counter() - overall_start
        logger.info(
            f"[{doc_id}] ⏱️ TIMING — chunk={step_times['chunk']:.2f}s, llm={step_times['llm']:.2f}s, "
            f"tts={step_times['tts']:.2f}s, total={total:.2f}s, "
            f"chars={len(raw_text)}, chunks={len(chunks)}"
        )
        logger.info(f"[{doc_id}] ✅ DONE — podcast ready (audio_id={audio_id})")

    except Exception as e:
        total = time.perf_counter() - overall_start
        error_detail = _sanitize_error(f"Failed while {current_step}: {e}")
        logger.error(f"[{doc_id}] ❌ {error_detail} (total elapsed: {total:.2f}s)")
        logger.error(traceback.format_exc())
        try:
            async with async_session() as session:
                doc = await session.get(Document, doc_id)
                if doc:
                    doc.status = "failed"
                    doc.error_message = error_detail[:500]
                    await session.commit()
        except Exception:
            logger.error(f"[{doc_id}] Could not update status to failed")


@router.get("/list")
async def list_documents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List the signed-in user's podcasts only.

    Requires auth: this is what keeps each user's library private and stops
    every tester's document from piling up on a new user's home screen.
    Anonymous (owner-less) documents are intentionally never listed here.
    """
    result = await db.execute(
        select(Document)
        .where(Document.user_id == user.id, Document.deleted_at.is_(None))
        .options(selectinload(Document.audio_file))
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()

    items = []
    for doc in docs:
        audio = doc.audio_file
        items.append({
            "doc_id": doc.id,
            "filename": doc.filename,
            "num_chunks": doc.num_chunks,
            "created_at": doc.created_at.isoformat(),
            "status": doc.status or ("ready" if audio else "processing"),
            "audio_id": audio.id if audio else None,
        })

    return {"documents": items}


@router.get("/stats")
async def document_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Aggregate analytics for the signed-in user's library (My Podcasts view).

    Registered BEFORE ``/{doc_id}`` so it isn't swallowed by that catch-all.
    Everything is computed from a single lightweight column-only query (no
    ``raw_text`` payloads) and bucketed in Python to stay portable across
    SQLite (local/dev) and Postgres (prod) without DB-specific date functions.
    """
    result = await db.execute(
        select(
            Document.status,
            Document.source,
            Document.filename,
            Document.created_at,
            func.length(Document.raw_text),
            AudioFile.duration_seconds,
        )
        .select_from(Document)
        .outerjoin(AudioFile, AudioFile.document_id == Document.id)
        .where(Document.user_id == user.id, Document.deleted_at.is_(None))
    )

    total = ready = failed = processing = 0
    total_seconds = 0.0
    total_chars = 0
    ready_count = 0
    longest_seconds = 0.0
    by_source: dict[str, int] = {}
    by_month: dict[str, int] = {}
    by_month_seconds: dict[str, float] = {}

    for status_, source, filename, created_at, char_len, duration in result.all():
        total += 1
        st = status_ or "processing"
        if st == "ready":
            ready += 1
        elif st == "failed":
            failed += 1
        else:
            processing += 1

        # Exact source when recorded; fall back to filename inference for
        # pre-source rows (mirrors the backfill logic).
        src = source or _source_from_filename(filename or "")
        by_source[src] = by_source.get(src, 0) + 1

        if created_at:
            key = created_at.strftime("%Y-%m")
            by_month[key] = by_month.get(key, 0) + 1
            if st == "ready":
                by_month_seconds[key] = by_month_seconds.get(key, 0.0) + float(duration or 0.0)

        if st == "ready":
            ready_count += 1
            dur = float(duration or 0.0)
            total_seconds += dur
            total_chars += int(char_len or 0)
            if dur > longest_seconds:
                longest_seconds = dur

    avg_seconds = (total_seconds / ready_count) if ready_count else 0.0
    # ~5.7 chars/word is a decent English estimate; avoids loading raw_text.
    total_words = int(total_chars / 5.7) if total_chars else 0

    over_time = [
        {"month": m, "count": c, "seconds": round(by_month_seconds.get(m, 0.0))}
        for m, c in sorted(by_month.items())
    ]
    source_breakdown = [
        {"source": s, "count": c}
        for s, c in sorted(by_source.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return {
        "totals": {
            "podcasts": total,
            "ready": ready,
            "failed": failed,
            "processing": processing,
            "listening_seconds": round(total_seconds),
            "avg_seconds": round(avg_seconds),
            "longest_seconds": round(longest_seconds),
            "words": total_words,
        },
        "by_source": source_breakdown,
        "status_breakdown": [
            {"status": "ready", "count": ready},
            {"status": "failed", "count": failed},
            {"status": "processing", "count": processing},
        ],
        "over_time": over_time,
    }


@router.get("/{doc_id}")
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Get document metadata and processing status."""
    doc = await db.get(Document, doc_id)
    if not doc or doc.deleted_at is not None:
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
        # Transient sub-step (reading | analyzing_figures | writing_script |
        # synthesizing) for the processing screen; only meaningful while the job
        # is still running, so null it out once we're no longer processing.
        "stage": _doc_stages.get(doc_id) if status == "processing" else None,
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
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft-delete a document, purging its audio + Q&A history and files.

    Requires auth and ownership: a user can only delete a podcast they own.

    The ``documents`` row is deliberately KEPT (marked with ``deleted_at``) while
    its audio/Q&A rows and on-disk files are removed. This reclaims storage yet
    preserves lifetime free-quota accounting — hard-deleting the row would let a
    free user create -> delete -> create podcasts forever without paying. The
    row is hidden from the library, stats and dedup via its ``deleted_at`` marker.
    """
    doc = await db.get(Document, doc_id)
    if not doc or doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.user_id is not None and doc.user_id != user.id:
        raise HTTPException(status_code=403, detail="You don't have permission to delete this podcast.")

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

    # Purge the audio + Q&A rows (reclaim space) but KEEP the document row,
    # marking it soft-deleted so the lifetime free-quota still counts it.
    await db.execute(delete(QASession).where(QASession.document_id == doc_id))
    await db.execute(delete(AudioFile).where(AudioFile.document_id == doc_id))
    doc.deleted_at = _utcnow()
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
