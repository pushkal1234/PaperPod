import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("paperpod")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routes import documents, audio, qa
from app.config import settings


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


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "PaperPod",
        "web_search_available": bool(settings.SERPAPI_API_KEY.strip()),
    }
