import os
import uuid
import time
import logging
from datetime import timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, async_session, Document, QASession, _utcnow
from app.languages import detect_language, get_language_profile
from app.services.stt_service import transcribe_audio
from app.services.vector_service import query_chunks, store_chunks
from app.services.document_service import chunk_text
from app.services.llm_service import answer_question, strip_markdown_for_speech
from app.services.tts_service import synthesize_answer
from app.services import serpapi_service

router = APIRouter(prefix="/api/qa", tags=["qa"])
logger = logging.getLogger("paperpod")

# The answer's audio is synthesized in the background after the text is returned.
# Its state lives in QASession.answer_audio_path so every worker sees the same
# thing: NULL = still synthesizing, "" = synthesis failed, a path = ready.
_AUDIO_FAILED = ""
# A NULL path older than this means the worker died mid-synthesis (restart or
# redeploy), so the audio is never coming — report it as failed, not pending.
_AUDIO_PENDING_TIMEOUT = timedelta(minutes=15)

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
    clean = clean.replace("api_key", "configuration")
    clean = clean.replace("API_KEY", "configuration")
    return clean


def _audio_status(qa: QASession) -> str:
    """'ready', 'pending' or 'failed' for a Q&A answer's audio."""
    if qa.answer_audio_path:
        return "ready" if os.path.exists(qa.answer_audio_path) else "failed"
    if qa.answer_audio_path is None and qa.created_at:
        created = qa.created_at
        if created.tzinfo is None:  # SQLite hands back naive UTC datetimes
            created = created.replace(tzinfo=timezone.utc)
        if _utcnow() - created < _AUDIO_PENDING_TIMEOUT:
            return "pending"
    return "failed"


async def _synthesize_answer_audio(qa_id: str, doc_id: str, answer_text: str):
    """Background task: voice a saved answer, then record the MP3 path (or the
    failure) on its QASession. Native voice follows the answer's language."""
    t0 = time.perf_counter()
    lang_code = await run_in_threadpool(detect_language, answer_text)
    voice = get_language_profile(lang_code)["guest_voice"]
    path = None
    try:
        path = await synthesize_answer(strip_markdown_for_speech(answer_text), doc_id, qa_id, voice=voice)
    except Exception as e:
        logger.error(f"[QA][{doc_id}] TTS failed for {qa_id}: {e}", exc_info=not isinstance(e, RuntimeError))

    async with async_session() as session:
        qa = await session.get(QASession, qa_id)
        if qa is None:
            # The document (and its Q&A) was deleted while we were synthesizing.
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
            return
        qa.answer_audio_path = path or _AUDIO_FAILED
        await session.commit()

    logger.info(
        f"[QA][{doc_id}] ⏱️ TTS (background) — {time.perf_counter() - t0:.2f}s, "
        f"lang={lang_code}, voice={voice}, ok={bool(path)}, chars={len(answer_text)}"
    )


@router.post("/ask")
async def ask_question(
    background_tasks: BackgroundTasks,
    doc_id: str = Form(...),
    question_text: str = Form(None),
    search_mode: str = Form("document"),
    audio: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Ask a question about a document. Accepts text or audio input.

    Returns the answer text as soon as the LLM is done. The audio is synthesized
    in the background: poll ``/api/qa/audio-status/{qa_id}`` until it's ready.
    """
    overall_start = time.perf_counter()
    step_times = {}

    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # STT if voice input
    if audio and audio.size and audio.size > 0:
        t0 = time.perf_counter()
        audio_bytes = await audio.read()
        try:
            question_text = await run_in_threadpool(transcribe_audio, audio_bytes)
        except RuntimeError as e:
            raise HTTPException(status_code=429, detail=_sanitize_error(str(e)))
        except Exception as e:
            logger.error(f"[QA][{doc_id}] STT failed: {e}", exc_info=True)
            raise HTTPException(status_code=503, detail=_sanitize_error("PaperPod's speech service is temporarily busy. Please try again shortly."))
        step_times['stt'] = time.perf_counter() - t0
        logger.info(f"[QA][{doc_id}] STT: {step_times['stt']:.2f}s -> '{question_text[:60]}...'")

    if not question_text:
        raise HTTPException(status_code=400, detail="No question provided (text or audio)")

    # Retrieve context. top_k is only the FALLBACK path now (used when the doc is
    # too large to fit whole, or Gemini is unavailable) — the preferred path in
    # answer_question answers from the entire document. We still retrieve so that
    # fallback has good material.
    t0 = time.perf_counter()
    top_k = settings.QA_RETRIEVAL_TOP_K
    context_chunks = await run_in_threadpool(query_chunks, question_text, doc_id, top_k)
    # The chunk index lives in process memory and is lost on restart/redeploy
    # (and isn't shared across workers). On a miss, rebuild it from the
    # persisted raw_text so Q&A keeps working instead of silently answering
    # with no document context.
    if not context_chunks and doc.raw_text:
        rebuilt = await run_in_threadpool(chunk_text, doc.raw_text)
        store_chunks(doc_id, rebuilt)
        context_chunks = await run_in_threadpool(query_chunks, question_text, doc_id, top_k)
        logger.info(f"[QA][{doc_id}] Rebuilt {len(rebuilt)} chunks from persisted text")
    step_times['retrieve'] = time.perf_counter() - t0

    citations: list = []
    mode = (search_mode or "document").lower().strip()
    if mode not in ("document", "hybrid"):
        mode = "document"

    # Generate answer
    t0 = time.perf_counter()
    try:
        if mode == "hybrid" and serpapi_service.is_configured():
            # The full document goes to the preferred Gemini path. document_context
            # is only for the Groq fallback, which keeps its first 8K chars — so the
            # question-matched chunks go FIRST, ahead of the document's opening.
            doc_context_parts = []
            if context_chunks:
                doc_context_parts.append("\n\n---\n\n".join(context_chunks))
            if doc.raw_text:
                doc_context_parts.append(doc.raw_text[:8000])
            document_context = "\n\n---\n\n".join(doc_context_parts) or "No document text available."
            try:
                result = await run_in_threadpool(
                    serpapi_service.answer_with_web_search, question_text, document_context, doc.raw_text
                )
                answer_text = result["answer"]
                citations = result.get("citations") or []
            except Exception as e:
                logger.warning(f"[QA][{doc_id}] Web search failed, falling back to document-only: {e}")
                answer_text = await run_in_threadpool(answer_question, question_text, context_chunks, doc.raw_text)
                mode = "document"
                citations = [{"note": "Web search unavailable, answered from document only."}]
        else:
            if mode == "hybrid" and not serpapi_service.is_configured():
                mode = "document"
            answer_text = await run_in_threadpool(answer_question, question_text, context_chunks, doc.raw_text)
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=_sanitize_error(str(e)))
    except Exception as e:
        logger.error(f"[QA][{doc_id}] LLM failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=_sanitize_error("PaperPod's AI engine is temporarily busy. Please try again shortly."))
    step_times['llm'] = time.perf_counter() - t0

    # Save the answer with no audio yet (NULL path = synthesizing), return the
    # text now, and voice it in the background — TTS can take far longer than
    # the LLM, and the user shouldn't wait for it to read the answer.
    qa_id = str(uuid.uuid4())
    qa_session = QASession(
        id=qa_id,
        document_id=doc_id,
        question_text=question_text,
        answer_text=answer_text,
        answer_audio_path=None,
        created_at=_utcnow(),
    )
    db.add(qa_session)
    await db.commit()
    background_tasks.add_task(_synthesize_answer_audio, qa_id, doc_id, answer_text)

    total = time.perf_counter() - overall_start
    logger.info(
        f"[QA][{doc_id}] ⏱️ TIMING — stt={step_times.get('stt', 0):.2f}s, "
        f"retrieve={step_times['retrieve']:.2f}s, llm={step_times['llm']:.2f}s, "
        f"tts=background, total={total:.2f}s, "
        f"mode={mode}, chars_in={len(question_text)}, chars_out={len(answer_text)}"
    )

    return {
        "qa_id": qa_id,
        "question": question_text,
        "answer": answer_text,
        "answer_audio_url": f"/api/qa/audio/{qa_id}",
        "audio_status": "pending",
        "search_mode": mode,
        "citations": citations,
        "web_search_available": serpapi_service.is_configured(),
    }


@router.get("/audio-status/{qa_id}")
async def get_qa_audio_status(qa_id: str, db: AsyncSession = Depends(get_db)):
    """Whether a Q&A answer's background audio is 'pending', 'ready' or 'failed'."""
    qa = await db.get(QASession, qa_id)
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A not found")
    return {"qa_id": qa_id, "status": _audio_status(qa)}


@router.get("/audio/{qa_id}")
async def get_qa_audio(qa_id: str, db: AsyncSession = Depends(get_db)):
    """Get the audio response for a Q&A session."""
    qa = await db.get(QASession, qa_id)
    if not qa or not qa.answer_audio_path:
        raise HTTPException(status_code=404, detail="Q&A audio not found")

    if not os.path.exists(qa.answer_audio_path):
        raise HTTPException(status_code=404, detail="This answer's audio is no longer available.")

    return FileResponse(
        qa.answer_audio_path,
        media_type="audio/mpeg",
        filename=f"answer_{qa_id}.mp3",
    )


@router.get("/history/{doc_id}")
async def get_qa_history(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Get Q&A history for a document."""
    from sqlalchemy import select

    result = await db.execute(
        select(QASession)
        .where(QASession.document_id == doc_id)
        .order_by(QASession.created_at.desc())
    )
    sessions = result.scalars().all()

    return {
        "doc_id": doc_id,
        "sessions": [
            {
                "qa_id": s.id,
                "question": s.question_text,
                "answer": s.answer_text,
                "answer_audio_url": f"/api/qa/audio/{s.id}",
                "audio_status": _audio_status(s),
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
    }
