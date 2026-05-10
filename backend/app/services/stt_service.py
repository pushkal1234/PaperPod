import os
import uuid

from groq import Groq

from app.config import settings

_client = Groq(api_key=settings.GROQ_API_KEY)


def transcribe_audio(audio_bytes: bytes, filename: str = "question.webm") -> str:
    """Transcribe audio bytes to text using Groq's Whisper API (free, no local model)."""
    temp_path = os.path.join(settings.AUDIO_DIR, f"temp_stt_{uuid.uuid4()}.webm")
    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)
        with open(temp_path, "rb") as audio_file:
            transcription = _client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                response_format="text",
            )
        return transcription.strip()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
