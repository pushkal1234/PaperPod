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
    LLM_FALLBACK_MODEL: str = os.getenv("LLM_FALLBACK_MODEL", "gemini-2.5-flash")
    WHISPER_MODEL: str = "whisper-large-v3"
    # Voice casting:
    #   HOST  = drives the convo / asks questions  -> male voice
    #   GUEST = the expert who explains & speaks more -> Neerja Expressive (female)
    TTS_VOICE_HOST: str = os.getenv("TTS_VOICE_HOST", "en-US-AndrewMultilingualNeural")
    TTS_VOICE_GUEST: str = os.getenv("TTS_VOICE_GUEST", "en-IN-NeerjaExpressiveNeural")
    TTS_RATE_HOST: str = os.getenv("TTS_RATE_HOST", "+10%")
    TTS_PITCH_HOST: str = os.getenv("TTS_PITCH_HOST", "+0Hz")
    TTS_RATE_GUEST: str = os.getenv("TTS_RATE_GUEST", "+8%")
    TTS_PITCH_GUEST: str = os.getenv("TTS_PITCH_GUEST", "+2Hz")

    # Reject oversized uploads before they are read fully into memory (OOM guard).
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    MAX_DOC_CHARS: int = int(os.getenv("MAX_DOC_CHARS", "40000"))
    MAX_DOC_CHARS_HARD: int = int(os.getenv("MAX_DOC_CHARS_HARD", "270000"))
    # PDF vision: describe diagrams/charts/figures with Gemini so they're narrated
    # in the podcast (PyPDF2 reads text only). Set to "0" to disable.
    PDF_VISION_EXTRACTION: bool = os.getenv("PDF_VISION_EXTRACTION", "1") not in ("0", "false", "False")
    PDF_VISION_MAX_PAGES: int = int(os.getenv("PDF_VISION_MAX_PAGES", "60"))
    PDF_VISION_MAX_FIGURES: int = int(os.getenv("PDF_VISION_MAX_FIGURES", "12"))
    MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
    # Bump this whenever the generation pipeline changes (extraction, prompts,
    # LLM/TTS logic). It's folded into the dedup content_hash so re-uploads MISS
    # caches produced by an older, buggy pipeline and regenerate with new code.
    GENERATION_VERSION: str = os.getenv("GENERATION_VERSION", "4")
    # Quality gate: a podcast below these thresholds is marked "failed" instead of
    # "ready", so degenerate output (e.g. a 9-second outro-only clip) is never
    # cached or served — the next upload regenerates instead of deduping to it.
    MIN_PODCAST_DURATION_SECONDS: float = float(os.getenv("MIN_PODCAST_DURATION_SECONDS", "20"))
    MIN_PODCAST_DIALOGUE_LINES: int = int(os.getenv("MIN_PODCAST_DIALOGUE_LINES", "6"))
    # Comma-separated extra CORS origins (in addition to the built-in defaults).
    CORS_EXTRA_ORIGINS: str = os.getenv("CORS_EXTRA_ORIGINS", "")

    # --- Auth ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_DAYS: int = int(os.getenv("JWT_EXPIRE_DAYS", "30"))
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

    @property
    def MAX_UPLOAD_BYTES(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024


settings = Settings()

Path(settings.AUDIO_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
