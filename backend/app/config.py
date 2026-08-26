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
    # Hard cap on dialogue turns fed to TTS — and, in practice, the EFFECTIVE
    # ceiling on episode length. The heavy-overshoot ceiling is
    # max_lines × HEAVY_OVERSHOOT_CEILING_FACTOR (1.75), clamped to
    # MAX_DIALOGUE_TURNS - 2 (see _overshoot_ceiling in llm_service). On the big
    # tiers the 1.75x value exceeds this cap (e.g. max=189 -> 331, or feasible max
    # 200 -> 350), so 280 - 2 = 278 lines (~40 min of audio) becomes the real
    # upper bound. Small/medium docs never reach it, so their full 1.75x overshoot
    # is preserved. Raise this only if you deliberately want longer episodes.
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
    # ceiling (never below it). 1.75 ≈ keep up to +75% over max before any trim.
    # NOTE: the ceiling is additionally clamped to MAX_DIALOGUE_TURNS - 2 (=278),
    # so on the biggest tiers that cap binds BEFORE the full 1.75x is reached
    # (e.g. max=189 -> 1.75x=331, clamped to 278). Small/medium docs are unaffected.
    HEAVY_OVERSHOOT_CEILING_FACTOR: float = float(os.getenv("HEAVY_OVERSHOOT_CEILING_FACTOR", "1.75"))

    # Bump this whenever the generation pipeline changes (extraction, prompts,
    # LLM/TTS logic). It's folded into the dedup content_hash so re-uploads MISS
    # caches produced by an older, buggy pipeline and regenerate with new code.
    GENERATION_VERSION: str = os.getenv("GENERATION_VERSION", "18")
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

    # --- Monetization / entitlements ---
    # Master kill-switch for the whole paywall. Phase 0 ships with this OFF, so
    # entitlements are computed and surfaced (via /me) but NEVER enforced — the
    # product behaves exactly as today. Flip to "1" only in Phase 2 once Stripe
    # is wired and tested; the enforcement gates read this flag so the paywall
    # can be disabled instantly without a code redeploy.
    BILLING_ENABLED: bool = os.getenv("BILLING_ENABLED", "0") not in ("0", "false", "False")
    # Require a signed-in account to upload/generate at all (closes the anonymous
    # loophole where incognito/cookie-clear grants unlimited free podcasts). When
    # OFF (default), uploads stay open to anonymous callers exactly as today, so
    # this ships dark. Flip to "1" in Phase 2 — but ONLY after the browser
    # extensions are updated to authenticate and the "no sign-up to try" landing
    # copy is updated, otherwise the extensions 401 and the copy misleads.
    REQUIRE_AUTH_UPLOAD: bool = os.getenv("REQUIRE_AUTH_UPLOAD", "0") not in ("0", "false", "False")
    # Lifetime podcasts a FREE (signed-in) account may generate before the
    # paywall. With REQUIRE_AUTH_UPLOAD on there is no anonymous tier — every
    # generation is tied to an account and counted server-side. Failed
    # generations do NOT count toward this.
    FREE_LIFETIME_PODCASTS: int = int(os.getenv("FREE_LIFETIME_PODCASTS", "2"))
    # NOTE: there is intentionally NO free doc-length cap. Free users get the
    # same full-length ceiling as premium (MAX_DOC_CHARS_HARD) so their first
    # ~45-min podcast is a real, full experience that builds trust before paying.
    # Premium's only edge is quantity (unlimited podcasts), not document length.

    # --- Anti-abuse: email verification ---
    # Require users to confirm a 6-digit code emailed to them before they can
    # create podcasts. Closes the "type any fake email -> unlimited free
    # podcasts" loophole. Ships OFF so nothing changes until you flip it. When
    # ON it REQUIRES an email provider below (Resend or SMTP); without one,
    # codes are only logged (dev fallback) and abuse protection is void.
    EMAIL_VERIFICATION_ENABLED: bool = os.getenv("EMAIL_VERIFICATION_ENABLED", "0") not in ("0", "false", "False")
    VERIFICATION_CODE_TTL_MINUTES: int = int(os.getenv("VERIFICATION_CODE_TTL_MINUTES", "15"))
    VERIFICATION_MAX_ATTEMPTS: int = int(os.getenv("VERIFICATION_MAX_ATTEMPTS", "5"))
    VERIFICATION_RESEND_COOLDOWN_SECONDS: int = int(os.getenv("VERIFICATION_RESEND_COOLDOWN_SECONDS", "60"))
    # Email provider — pick ONE (checked in this order): Brevo, Resend, SMTP.
    # Brevo (https://brevo.com) sends over an HTTPS API, so it works on hosts
    # that block outbound SMTP (e.g. Railway's non-Pro plans) and allows a single
    # verified sender email — no domain required. Dashboard -> SMTP & API -> API
    # Keys. Set BREVO_API_KEY and verify your EMAIL_FROM address as a sender.
    BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "")
    # Resend (https://resend.com -> API Keys). HTTPS API; needs a verified domain
    # to email arbitrary recipients. Used only if BREVO_API_KEY is blank.
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    # Generic SMTP — used only if BREVO_API_KEY and RESEND_API_KEY are both blank.
    # NOTE: many PaaS (Railway free/hobby) BLOCK outbound SMTP ports, so prefer an
    # HTTPS provider above in production.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    # From header for outgoing mail, e.g. "PaperPod <noreply@yourdomain.com>".
    # Resend's shared sandbox sender works for testing without a domain.
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "PaperPod <onboarding@resend.dev>")

    # --- Anti-abuse: per-IP free quota (secondary defense) ---
    # Caps how many free podcasts can be created from a single IP across ALL
    # accounts, so spinning up many fake accounts on one machine still shares one
    # allowance. Ships OFF. Premium users are never limited. Behind a proxy the
    # first X-Forwarded-For hop is used; shared networks (offices/campuses) can
    # be affected, so keep the limit generous.
    IP_QUOTA_ENABLED: bool = os.getenv("IP_QUOTA_ENABLED", "0") not in ("0", "false", "False")
    FREE_PODCASTS_PER_IP: int = int(os.getenv("FREE_PODCASTS_PER_IP", "3"))

    # --- Billing provider: Dodo Payments (Merchant of Record) ---
    # MoR chosen because the founder is in India selling to mostly US/UK
    # customers, and Stripe/Lemon Squeezy are invite-only there. Dodo is the
    # merchant of record: it collects global sales tax/VAT and settles to an
    # Indian bank. Only these values differ between test and live.
    DODO_API_KEY: str = os.getenv("DODO_API_KEY", "")
    # Signing secret for the webhook endpoint (Standard Webhooks spec).
    DODO_WEBHOOK_KEY: str = os.getenv("DODO_WEBHOOK_KEY", "")
    # Product id of the $5/mo Premium subscription (Dodo dashboard -> Products).
    DODO_PRODUCT_ID: str = os.getenv("DODO_PRODUCT_ID", "")
    # "test_mode" (default) or "live_mode" — selects the API base URL.
    DODO_ENVIRONMENT: str = os.getenv("DODO_ENVIRONMENT", "test_mode")
    # Where Dodo returns the buyer after checkout, and the base for portal
    # return links. Defaults to the prod frontend; override per environment.
    FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "https://paper-pod-one.vercel.app")

    @property
    def MAX_UPLOAD_BYTES(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def EMAIL_PROVIDER_CONFIGURED(self) -> bool:
        """True when a real email provider (Brevo, Resend, or SMTP) is configured.

        When False and verification is enabled, codes are only logged (dev
        fallback) — surfaced loudly so it's never silently insecure in prod.
        """
        return bool(
            self.BREVO_API_KEY.strip()
            or self.RESEND_API_KEY.strip()
            or (self.SMTP_HOST.strip() and self.SMTP_USER.strip())
        )

    @property
    def DODO_API_BASE(self) -> str:
        """Dodo REST base URL for the configured environment."""
        return (
            "https://live.dodopayments.com"
            if self.DODO_ENVIRONMENT == "live_mode"
            else "https://test.dodopayments.com"
        )

    @property
    def DODO_CONFIGURED(self) -> bool:
        """True only when everything needed to create a checkout is present."""
        return bool(self.DODO_API_KEY.strip() and self.DODO_PRODUCT_ID.strip())


settings = Settings()

Path(settings.AUDIO_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
