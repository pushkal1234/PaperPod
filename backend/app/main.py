import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("paperpod")
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, update

from app.database import init_db, async_session, Document
from app.routes import documents, audio, qa, share
from app.config import settings

# Startup configuration check
logger.info("=" * 50)
logger.info("PaperPod starting up...")
logger.info(f"GOOGLE_API_KEY set: {bool(settings.GOOGLE_API_KEY)}")
logger.info(f"GROQ_API_KEY set: {bool(settings.GROQ_API_KEY)}")
logger.info(f"LLM_MODEL: {settings.LLM_MODEL}")
logger.info(f"WHISPER_MODEL: {settings.WHISPER_MODEL}")
logger.info(f"TTS_VOICES: Host={settings.TTS_VOICE_HOST}, Guest={settings.TTS_VOICE_GUEST}")
logger.info(f"SERPAPI_API_KEY set: {bool(settings.SERPAPI_API_KEY)}")
logger.info("=" * 50)


async def _recover_orphaned_jobs():
    """Fail documents left in 'processing' by a previous run.

    Generation happens in in-process BackgroundTasks, so any job that was
    mid-flight when the server stopped is dead on the next boot. Without this
    the frontend would poll those docs forever.
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                update(Document)
                .where(Document.status == "processing")
                .values(
                    status="failed",
                    error_message="Processing was interrupted by a server restart. Please try again.",
                )
            )
            await session.commit()
            if result.rowcount:
                logger.info(f"Startup recovery: {result.rowcount} orphaned 'processing' doc(s) -> failed")
    except Exception:
        logger.error("Startup recovery of orphaned jobs failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _recover_orphaned_jobs()
    yield


app = FastAPI(
    title="PaperPod API",
    description="Document to Podcast-style Conversation + Real-time Q&A",
    version="0.1.0",
    lifespan=lifespan,
)

_DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "https://paper-pod-one.vercel.app",
    "https://paperpod.vercel.app",
]
_extra_origins = [o.strip() for o in settings.CORS_EXTRA_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_ORIGINS + _extra_origins,
    # Scope Vercel preview deploys to THIS project only (the previous
    # `paper.*\.vercel\.app` matched any attacker-owned `paper-*` site).
    # chrome-extension origins are kept for the browser extension.
    allow_origin_regex=r"https://paper-pod-[a-z0-9-]+-pushkal1234s-projects\.vercel\.app|chrome-extension://.*",
    # No cookies/Authorization are used, so credentials can stay off — which is
    # also what lets the scoped origins above be safe.
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(audio.router)
app.include_router(qa.router)
app.include_router(share.router)


@app.get("/api/health")
async def health():
    db_ok = True
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
        logger.error("Health check: database connectivity failed", exc_info=True)
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "PaperPod",
        "database": "ok" if db_ok else "error",
        "web_search_available": bool(settings.SERPAPI_API_KEY.strip()),
    }
