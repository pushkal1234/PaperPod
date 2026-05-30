import base64
import logging

from google import genai

from app.config import settings

logger = logging.getLogger("paperpod")

_stt_client = genai.Client(api_key=settings.GOOGLE_API_KEY) if settings.GOOGLE_API_KEY else None


def transcribe_audio(audio_bytes: bytes, filename: str = "question.webm") -> str:
    """Transcribe audio bytes to text using Gemini STT."""
    if not _stt_client:
        raise RuntimeError("GOOGLE_API_KEY is not set.")

    # Convert audio bytes to base64
    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')

    # Determine mime type from filename
    mime_type = "audio/webm"
    if filename.endswith(".mp3"):
        mime_type = "audio/mp3"
    elif filename.endswith(".wav"):
        mime_type = "audio/wav"
    elif filename.endswith(".m4a"):
        mime_type = "audio/mp4"

    try:
        response = _stt_client.models.generate_content(
            model=settings.STT_MODEL,
            contents=[{
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": audio_b64}},
                    {"text": "Transcribe this audio to text. Return only the transcription, nothing else."}
                ]
            }],
        )
        text = response.text.strip()
        logger.info(f"[STT] Transcribed {len(audio_bytes)} bytes -> '{text[:80]}...'")
        return text
    except Exception as e:
        logger.error(f"[STT] Failed to transcribe audio: {e}", exc_info=True)
        raise RuntimeError(f"STT error: {e}")
