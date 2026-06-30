import os
import tempfile
import time
import logging

from groq import Groq

from app.config import settings

logger = logging.getLogger("paperpod")

_stt_client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None

RATE_LIMIT_MSG = "You've reached PaperPod's free-tier rate limit. Please try again in a few moments."
SERVICE_ERROR_MSG = "PaperPod's speech service is temporarily busy. Please try again shortly."
CONFIG_ERROR_MSG = "Speech-to-text is not configured on this server. Please contact support."

# Hard ceiling on total retry backoff so a single transcription can't pin a
# worker thread for minutes when the provider is degraded.
STT_MAX_TOTAL_SECONDS = 75


def _is_rate_limit(err_str: str) -> bool:
    """Detect rate-limit / quota errors from any provider."""
    low = err_str.lower()
    return any(k in low for k in ["rate_limit", "429", "quota", "too many requests", "limit exceeded"])


def transcribe_audio(audio_bytes: bytes, filename: str = "question.webm") -> str:
    """Transcribe audio bytes to text with retry and brand-safe errors."""
    if not _stt_client:
        raise RuntimeError(CONFIG_ERROR_MSG)

    ext = os.path.splitext(filename)[1] or ".webm"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    last_error = None
    deadline = time.monotonic() + STT_MAX_TOTAL_SECONDS
    try:
        for attempt in range(4):
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
                last_error = e
                err_str = str(e)
                if _is_rate_limit(err_str):
                    wait = min(10 * (attempt + 1), max(0.0, deadline - time.monotonic()))
                    if wait <= 0:
                        break
                    logger.warning(f"[STT] Rate limited (attempt {attempt + 1}/4), waiting {wait:.1f}s...")
                    time.sleep(wait)
                elif any(k in err_str.lower() for k in ["connection", "timeout", "unavailable", "network"]):
                    wait = min(5 * (attempt + 1), max(0.0, deadline - time.monotonic()))
                    if wait <= 0:
                        break
                    logger.warning(f"[STT] Connection error (attempt {attempt + 1}/4), retrying in {wait:.1f}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"[STT] Unrecoverable error: {e}")
                    raise
        # All retries exhausted
        if last_error and _is_rate_limit(str(last_error)):
            raise RuntimeError(RATE_LIMIT_MSG)
        raise RuntimeError(SERVICE_ERROR_MSG)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
