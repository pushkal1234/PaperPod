import base64

import google.generativeai as genai

from app.config import settings

if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)


def transcribe_audio(audio_bytes: bytes, filename: str = "question.webm") -> str:
    """Transcribe audio bytes to text using Gemini STT."""
    if not settings.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set.")
    model = genai.GenerativeModel(settings.STT_MODEL)

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

    response = model.generate_content(
        {
            "parts": [
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": audio_b64
                    }
                },
                {
                    "text": "Transcribe this audio to text. Return only the transcription, nothing else."
                }
            ]
        }
    )

    return response.text.strip()
