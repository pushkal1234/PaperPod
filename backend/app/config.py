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
    # Max parallel edge-tts calls for LARGE podcasts. edge-tts is free with no
    # documented limit, but it can throttle/drop audio ("No audio received") under
    # heavy concurrency — more so from datacenter IPs. 8 is fast for long episodes
    # whose longer clips stagger naturally.
    TTS_CONCURRENCY: int = int(os.getenv("TTS_CONCURRENCY", "8"))
    # Concurrency for SMALL podcasts. Short docs produce short clips that all
    # finish near-instantly and fire in a tight burst, which is far more likely to
    # trip edge-tts throttling than a long episode. So we cap concurrency lower
    # when a script has <= TTS_SMALL_DOC_MAX_CLIPS turns (reliability > raw speed
    # on tiny jobs, where the absolute time saved by more parallelism is small).
    TTS_CONCURRENCY_SMALL: int = int(os.getenv("TTS_CONCURRENCY_SMALL", "5"))
    TTS_SMALL_DOC_MAX_CLIPS: int = int(os.getenv("TTS_SMALL_DOC_MAX_CLIPS", "40"))
    # Runaway safety cap on dialogue turns fed to TTS. This is NOT a length knob —
    # it must stay >= the LLM's largest possible FINISHED script, which is now the
    # generous overshoot ceiling on the biggest tier: feasible max 200 lines ×
    # HEAVY_OVERSHOOT_CEILING_FACTOR (1.35) ≈ 270, + the deterministic outro. So
    # legitimate long podcasts (and preserved heavy-overshoot content) are never
    # truncated here. Control podcast length via the LLM tiers, not this cap.
    MAX_DIALOGUE_TURNS: int = int(os.getenv("MAX_DIALOGUE_TURNS", "280"))

    # Reject oversized uploads before they are read fully into memory (OOM guard).
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    # Boundary between the "send the WHOLE doc straight to Gemini" lane and the
    # lossy "summarize first" lane. Gemini 2.5 Flash has a ~1M-token context and
    # 250K TPM, so even a doc at MAX_DOC_CHARS_HARD (~270K chars ≈ 77K tokens)
    # fits in ONE direct call. The binding limit on podcast length is OUTPUT
    # (~8K tokens ≈ 132 lines), not input — so summarizing a big doc first only
    # THROWS AWAY material (a ~10K-char summary sustains ~50 lines) without ever
    # enabling a longer episode. We therefore set this EQUAL to the hard cap:
    # any doc we accept is podcasted from its FULL text in one Gemini pass. The
    # lossy chunked-summary lane now only runs as a fallback when Gemini is not
    # configured at all. Lower this only if direct calls start costing too much.
    MAX_DOC_CHARS: int = int(os.getenv("MAX_DOC_CHARS", "270000"))
    MAX_DOC_CHARS_HARD: int = int(os.getenv("MAX_DOC_CHARS_HARD", "270000"))
    # PDF vision: describe diagrams/charts/figures with Gemini so they're narrated
    # in the podcast (PyPDF2 reads text only). Set to "0" to disable.
    PDF_VISION_EXTRACTION: bool = os.getenv("PDF_VISION_EXTRACTION", "1") not in ("0", "false", "False")
    PDF_VISION_MAX_PAGES: int = int(os.getenv("PDF_VISION_MAX_PAGES", "60"))
    PDF_VISION_MAX_FIGURES: int = int(os.getenv("PDF_VISION_MAX_FIGURES", "12"))
    MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
    # Retain the source upload (renamed to the document id) after processing
    # instead of deleting it, so failed/undershoot cases can be inspected later.
    # Set KEEP_UPLOADS=0 to purge on completion (the old behavior) if the storage
    # volume becomes a concern. raw_text is always persisted in the DB regardless.
    KEEP_UPLOADS: bool = os.getenv("KEEP_UPLOADS", "1") not in ("0", "false", "False")
    # --- Token / rate-limit optimizations ---
    # (C) TPM-cooldown router: once a Groq call trips the free-tier 8K-TPM window
    # (429/413 TPM), route the NEXT calls straight to Gemini for this many seconds
    # instead of firing a second Groq call inside the same rolling minute (which is
    # guaranteed to 429 again). Groq's window is ~60s. Set 0 to disable.
    GROQ_TPM_COOLDOWN_SECONDS: float = float(os.getenv("GROQ_TPM_COOLDOWN_SECONDS", "60"))
    # (B) Lossless document compaction: strip non-semantic extraction noise
    # (repeated running headers/footers, standalone page numbers, PDF hyphenation
    # line-break splits, runs of blank lines) before the LLM call. Never touches
    # prose wording. Set "0" to disable if a regression is ever suspected.
    DOC_COMPACTION: bool = os.getenv("DOC_COMPACTION", "1") not in ("0", "false", "False")
    # (A) Prompt-cache optimization: hoist the per-document length numbers to a
    # trailing spec so the podcast system prompt is a byte-stable prefix across
    # documents (maximizes Groq/Gemini automatic prefix-cache hits). Identical
    # content is sent to the model — zero output-quality impact. Set "0" to revert
    # to the inline-number prompt.
    PROMPT_CACHE_OPTIMIZE: bool = os.getenv("PROMPT_CACHE_OPTIMIZE", "1") not in ("0", "false", "False")
    # Content-preserving overshoot handling. When the model returns MORE dialogue
    # lines than the tier max, we do NOT trim back to max_lines — underselling a
    # rich document (chopping real information to hit a line number) is worse UX
    # than a slightly longer episode. We keep everything up to a GENEROUS ceiling
    # of max_lines × this factor, and only shave a heavy overshoot down to that
    # ceiling (never below it). 1.35 ≈ keep up to +35% over max before any trim.
    HEAVY_OVERSHOOT_CEILING_FACTOR: float = float(os.getenv("HEAVY_OVERSHOOT_CEILING_FACTOR", "1.35"))

    # Bump this whenever the generation pipeline changes (extraction, prompts,
    # LLM/TTS logic). It's folded into the dedup content_hash so re-uploads MISS
    # caches produced by an older, buggy pipeline and regenerate with new code.
    GENERATION_VERSION: str = os.getenv("GENERATION_VERSION", "16")
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
