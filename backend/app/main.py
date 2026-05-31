import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("paperpod")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="PaperPod API",
    description="Document to Podcast-style Conversation + Real-time Q&A",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "https://paper-d672ucect-pushkal1234s-projects.vercel.app",
        "https://paperpod.vercel.app",
    ],
    allow_origin_regex=r"https://paper.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(audio.router)
app.include_router(qa.router)
app.include_router(share.router)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "PaperPod",
        "web_search_available": bool(settings.SERPAPI_API_KEY.strip()),
    }
