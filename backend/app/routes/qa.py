import uuid
import time
import logging
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, Document, QASession
from app.services.stt_service import transcribe_audio
from app.services.vector_service import query_chunks
from app.services.llm_service import answer_question
from app.services.tts_service import synthesize_answer
from app.services import serpapi_service

router = APIRouter(prefix="/api/qa", tags=["qa"])
logger = logging.getLogger("paperpod")


@router.post("/ask")
async def ask_question(
    doc_id: str = Form(...),
    question_text: str = Form(None),
    search_mode: str = Form("document"),
    audio: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Ask a question about a document. Accepts text or audio input.
    
    Returns answer text + audio URL.
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
        question_text = transcribe_audio(audio_bytes)
        step_times['stt'] = time.perf_counter() - t0
        logger.info(f"[QA][{doc_id}] STT: {step_times['stt']:.2f}s -> '{question_text[:60]}...'")

    if not question_text:
        raise HTTPException(status_code=400, detail="No question provided (text or audio)")

    # Retrieve context
    t0 = time.perf_counter()
    context_chunks = query_chunks(question_text, doc_id, top_k=5)
    step_times['retrieve'] = time.perf_counter() - t0

    citations: list = []
    mode = (search_mode or "document").lower().strip()
    if mode not in ("document", "hybrid"):
        mode = "document"

    # Generate answer
    t0 = time.perf_counter()
    if mode == "hybrid" and serpapi_service.is_configured():
        doc_context_parts = []
        if doc.raw_text:
            doc_context_parts.append(doc.raw_text[:8000])
        if context_chunks:
            doc_context_parts.append("\n\n---\n\n".join(context_chunks))
        document_context = "\n\n---\n\n".join(doc_context_parts) or "No document text available."
        try:
            result = serpapi_service.answer_with_web_search(question_text, document_context)
            answer_text = result["answer"]
            citations = result.get("citations") or []
        except Exception as e:
            answer_text = answer_question(question_text, context_chunks)
            mode = "document"
            citations = [{"note": f"Web search unavailable, answered from document only: {e}"}]
    else:
        if mode == "hybrid" and not serpapi_service.is_configured():
            mode = "document"
        answer_text = answer_question(question_text, context_chunks)
    step_times['llm'] = time.perf_counter() - t0

    # TTS answer
    t0 = time.perf_counter()
    qa_id = str(uuid.uuid4())
    answer_audio_path = await synthesize_answer(answer_text, doc_id, qa_id)
    step_times['tts'] = time.perf_counter() - t0

    total = time.perf_counter() - overall_start
    logger.info(
        f"[QA][{doc_id}] ⏱️ TIMING — stt={step_times.get('stt', 0):.2f}s, "
        f"retrieve={step_times['retrieve']:.2f}s, llm={step_times['llm']:.2f}s, "
        f"tts={step_times['tts']:.2f}s, total={total:.2f}s, "
        f"mode={mode}, chars_in={len(question_text)}, chars_out={len(answer_text)}"
    )

    qa_session = QASession(
        id=qa_id,
        document_id=doc_id,
        question_text=question_text,
        answer_text=answer_text,
        answer_audio_path=answer_audio_path,
        created_at=datetime.utcnow(),
    )
    db.add(qa_session)
    await db.commit()

    return {
        "qa_id": qa_id,
        "question": question_text,
        "answer": answer_text,
        "answer_audio_url": f"/api/qa/audio/{qa_id}",
        "search_mode": mode,
        "citations": citations,
        "web_search_available": serpapi_service.is_configured(),
    }


@router.get("/audio/{qa_id}")
async def get_qa_audio(qa_id: str, db: AsyncSession = Depends(get_db)):
    """Get the audio response for a Q&A session."""
    qa = await db.get(QASession, qa_id)
    if not qa or not qa.answer_audio_path:
        raise HTTPException(status_code=404, detail="Q&A audio not found")

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
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
    }
