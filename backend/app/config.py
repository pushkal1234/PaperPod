import os
from pathlib import Path

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    SERPAPI_API_KEY: str = os.getenv("SERPAPI_API_KEY", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./paperpod.db")
    AUDIO_DIR: str = os.getenv("AUDIO_DIR", "./audio_files")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    LLM_MODEL: str = "llama-3.1-8b-instant"
    WHISPER_MODEL: str = "whisper-large-v3"
    # Indian English voices for a natural, conversational podcast feel.
    # Neerja "Expressive" varies intonation far more than the standard neural
    # voices, which fixes the flat/robotic/monotone delivery.
    TTS_VOICE_HOST: str = os.getenv("TTS_VOICE_HOST", "en-IN-NeerjaExpressiveNeural")
    TTS_VOICE_GUEST: str = os.getenv("TTS_VOICE_GUEST", "en-IN-PrabhatNeural")
    # Per-speaker prosody (edge-tts rate/pitch) to add contrast between the two
    # hosts and keep the energy up. Strings must carry an explicit sign.
    TTS_RATE_HOST: str = os.getenv("TTS_RATE_HOST", "+8%")
    TTS_PITCH_HOST: str = os.getenv("TTS_PITCH_HOST", "+2Hz")
    TTS_RATE_GUEST: str = os.getenv("TTS_RATE_GUEST", "+5%")
    TTS_PITCH_GUEST: str = os.getenv("TTS_PITCH_GUEST", "-2Hz")


settings = Settings()

Path(settings.AUDIO_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
