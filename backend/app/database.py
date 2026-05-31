import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from app.config import settings


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
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="audio_file")


class QASession(Base):
    __tablename__ = "qa_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=False)
    question_audio_path = Column(String, nullable=True)
    answer_audio_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="qa_sessions")


engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _migrate_schema(conn):
    """Add columns introduced after initial deploy (SQLite create_all won't alter tables)."""
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

    await conn.run_sync(_migrate)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_schema(conn)


async def get_db():
    async with async_session() as session:
        yield session
