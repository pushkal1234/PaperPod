import uuid
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, Document, QASession
from app.services.stt_service import transcribe_audio
from app.services.vector_service import query_chunks
from app.services.llm_service import answer_question
from app.services.tts_service import synthesize_answer

router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.post("/ask")
async def ask_question(
    doc_id: str = Form(...),
    question_text: str = Form(None),
    audio: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Ask a question about a document. Accepts text or audio input.
    
    Returns answer text + audio URL.
    """
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if audio and audio.size and audio.size > 0:
        audio_bytes = await audio.read()
        question_text = transcribe_audio(audio_bytes)

    if not question_text:
        raise HTTPException(status_code=400, detail="No question provided (text or audio)")

    context_chunks = query_chunks(question_text, doc_id, top_k=5)

    answer_text = answer_question(question_text, context_chunks)

    qa_id = str(uuid.uuid4())
    answer_audio_path = await synthesize_answer(answer_text, doc_id, qa_id)

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
