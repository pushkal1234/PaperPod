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
    LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
    WHISPER_MODEL: str = "whisper-large-v3"
    # Voice casting:
    #   HOST  = drives the convo / asks questions  -> male voice
    #   GUEST = the expert who explains & speaks more -> Neerja Expressive (female)
    TTS_VOICE_HOST: str = os.getenv("TTS_VOICE_HOST", "en-US-AndrewMultilingualNeural")
    TTS_VOICE_GUEST: str = os.getenv("TTS_VOICE_GUEST", "en-IN-NeerjaExpressiveNeural")
    # Per-speaker prosody (edge-tts rate/pitch). Explicit sign required.
    # Host slightly faster/livelier to counter the male monotone; Guest (female)
    # kept at her natural, well-liked settings.
    TTS_RATE_HOST: str = os.getenv("TTS_RATE_HOST", "+10%")
    TTS_PITCH_HOST: str = os.getenv("TTS_PITCH_HOST", "+0Hz")
    TTS_RATE_GUEST: str = os.getenv("TTS_RATE_GUEST", "+8%")
    TTS_PITCH_GUEST: str = os.getenv("TTS_PITCH_GUEST", "+2Hz")

    # Reject oversized uploads before they are read fully into memory (OOM guard).
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    # Cap simultaneous heavy LLM+TTS pipelines so background work can't starve
    # the web process or hammer provider rate limits.
    MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
    # Comma-separated extra CORS origins (in addition to the built-in defaults).
    CORS_EXTRA_ORIGINS: str = os.getenv("CORS_EXTRA_ORIGINS", "")

    @property
    def MAX_UPLOAD_BYTES(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024


settings = Settings()

Path(settings.AUDIO_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
