import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from app.config import settings


def _utcnow() -> datetime:
    """Timezone-aware UTC now (datetime.utcnow() is deprecated and naive)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    raw_text = Column(Text, nullable=False)
    num_chunks = Column(Integer, default=0)
    status = Column(String, default="processing")  # processing | ready | failed
    error_message = Column(Text, nullable=True)
    # sha256 of the source bytes/text — used to dedupe re-uploads and skip
    # paying for the same LLM+TTS generation twice.
    content_hash = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    audio_file = relationship("AudioFile", back_populates="document", uselist=False)
    qa_sessions = relationship("QASession", back_populates="document")


class AudioFile(Base):
    __tablename__ = "audio_files"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), unique=True, nullable=False)
    file_path = Column(String, nullable=False)
    duration_seconds = Column(Float, default=0.0)
    dialogue_script = Column(Text, nullable=True)
    transcript_segments = Column(Text, nullable=True)  # JSON: [{speaker, text, start_seconds, end_seconds}]
    share_token = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    document = relationship("Document", back_populates="audio_file")


class QASession(Base):
    __tablename__ = "qa_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=False)
    question_audio_path = Column(String, nullable=True)
    answer_audio_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    document = relationship("Document", back_populates="qa_sessions")


def _normalize_async_url(url: str) -> str:
    """Coerce a DB URL to its async SQLAlchemy driver.

    Railway/Heroku expose Postgres as ``postgres://`` or ``postgresql://``,
    but SQLAlchemy's async engine needs an explicit async driver
    (``postgresql+asyncpg://``). SQLite URLs are passed through unchanged.
    """
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalize_async_url(settings.DATABASE_URL)
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

# pool_pre_ping recycles connections dropped by the DB/proxy (important for
# managed Postgres that closes idle connections); harmless for SQLite.
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Surface (without leaking credentials) whether we're on the free private
# endpoint or a billed public proxy, so it's verifiable from deploy logs.
_logger = logging.getLogger("paperpod")
if _IS_SQLITE:
    _logger.info("DB endpoint: local SQLite")
elif "railway.internal" in DATABASE_URL:
    _logger.info("DB endpoint: private (railway.internal) — no egress charges")
else:
    _logger.warning(
        "DB endpoint: NON-private host in use — this likely incurs Railway egress "
        "charges. Point DATABASE_URL at the private railway.internal endpoint."
    )


if _IS_SQLITE:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        """Enable WAL + a busy timeout so concurrent readers/writers don't trip
        'database is locked' under the background-job + request workload."""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


async def _migrate_schema(conn):
    """Backfill columns added after the initial SQLite deploy.

    Only runs on SQLite: Postgres starts from an empty database where
    ``create_all`` already produces the full, current schema, and the
    ``PRAGMA`` introspection used here is SQLite-specific.
    """
    from sqlalchemy import text

    def _migrate(sync_conn):
        rows = sync_conn.execute(text("PRAGMA table_info(audio_files)")).fetchall()
        cols = {row[1] for row in rows}
        if "transcript_segments" not in cols:
            sync_conn.execute(
                text("ALTER TABLE audio_files ADD COLUMN transcript_segments TEXT")
            )
        if "share_token" not in cols:
            sync_conn.execute(
                text("ALTER TABLE audio_files ADD COLUMN share_token TEXT UNIQUE")
            )

        doc_rows = sync_conn.execute(text("PRAGMA table_info(documents)")).fetchall()
        doc_cols = {row[1] for row in doc_rows}
        if "content_hash" not in doc_cols:
            sync_conn.execute(
                text("ALTER TABLE documents ADD COLUMN content_hash TEXT")
            )
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_documents_content_hash ON documents (content_hash)")
            )

    await conn.run_sync(_migrate)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if _IS_SQLITE:
            await _migrate_schema(conn)


async def get_db():
    async with async_session() as session:
        yield session
