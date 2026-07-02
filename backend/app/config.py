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
    # Gemini model used as an automatic fallback when Groq is rate-limited (429)
    # or unavailable. Reuses GOOGLE_API_KEY. Set to "" to disable the fallback.
    LLM_FALLBACK_MODEL: str = os.getenv("LLM_FALLBACK_MODEL", "gemini-2.5-flash")
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
    # Podcast guardrail: documents whose extracted text exceeds this many
    # characters are rejected up-front with a clear "too long" message, instead
    # of firing dozens of summarization calls that drain the free-tier limit.
    # ~40000 chars ≈ 22 pages. Raise this if you move off the free tier.
    MAX_DOC_CHARS: int = int(os.getenv("MAX_DOC_CHARS", "40000"))
    # Cap simultaneous heavy LLM+TTS pipelines so background work can't starve
    # the web process or hammer provider rate limits.
    MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
    # Comma-separated extra CORS origins (in addition to the built-in defaults).
    CORS_EXTRA_ORIGINS: str = os.getenv("CORS_EXTRA_ORIGINS", "")

    # --- Auth ---
    # Secret used to sign JWT session tokens. MUST be set in production; a blank
    # value falls back to an ephemeral random key (tokens won't survive restarts).
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_DAYS: int = int(os.getenv("JWT_EXPIRE_DAYS", "30"))
    # Google OAuth Web client ID — used as the expected audience when verifying
    # Google Sign-In ID tokens. Get it from Google Cloud Console > Credentials.
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

    @property
    def MAX_UPLOAD_BYTES(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024


settings = Settings()

Path(settings.AUDIO_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
