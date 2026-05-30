import os
import tempfile
import logging

from groq import Groq

from app.config import settings

logger = logging.getLogger("paperpod")

_stt_client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None


def transcribe_audio(audio_bytes: bytes, filename: str = "question.webm") -> str:
    """Transcribe audio bytes to text using Groq Whisper."""
    if not _stt_client:
        raise RuntimeError("GROQ_API_KEY is not set.")

    # Determine file extension
    ext = os.path.splitext(filename)[1] or ".webm"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio_file:
            response = _stt_client.audio.transcriptions.create(
                file=audio_file,
                model=settings.WHISPER_MODEL,
                response_format="text",
            )
        text = response.text if hasattr(response, "text") else str(response)
        logger.info(f"[STT] Transcribed {len(audio_bytes)} bytes -> '{text[:80]}...'")
        return text.strip()
    except Exception as e:
        logger.error(f"[STT] Failed to transcribe audio: {e}", exc_info=True)
        raise RuntimeError(f"STT error: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
