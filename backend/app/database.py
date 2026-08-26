import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from app.config import settings


def _utcnow() -> datetime:
    """Timezone-aware UTC now (datetime.utcnow() is deprecated and naive)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=True)
    # Null for Google-only accounts (they authenticate via Google, no password).
    password_hash = Column(String, nullable=True)
    # Google "sub" (stable account id) for accounts created via Google Sign-In.
    google_sub = Column(String, nullable=True, unique=True, index=True)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # --- Monetization (Phase 0: columns exist but nothing enforces them yet) ---
    # Current entitlement tier. "free" | "premium". Flipped ONLY by the billing
    # webhook (the single source of truth); never trust the client.
    plan = Column(String, nullable=False, default="free", server_default="free")
    # Raw provider subscription status ("active", "on_trial", "past_due",
    # "cancelled", "expired", ...) for display/debugging; entitlement decisions
    # use `plan`, not this.
    plan_status = Column(String, nullable=True)
    # When the current paid period ends/renews (from the subscription).
    plan_renews_at = Column(DateTime(timezone=True), nullable=True)
    # Provider linkage (Lemon Squeezy) so we can open the customer portal and
    # reconcile webhooks. Named provider-neutrally on purpose.
    billing_customer_id = Column(String, nullable=True, index=True)
    billing_subscription_id = Column(String, nullable=True, index=True)

    # --- Anti-abuse: email verification & multi-account controls ---
    # Canonical form of the email with Gmail dots/plus-aliases collapsed, used to
    # detect duplicate accounts (a.b+x@gmail.com == ab@gmail.com). `email` keeps
    # the address exactly as entered (lowercased).
    normalized_email = Column(String, nullable=True, index=True)
    # Whether the email has been confirmed via code. Google accounts are trusted
    # as verified; pre-existing accounts are grandfathered verified in migration.
    email_verified = Column(Boolean, nullable=False, default=False)
    # sha256 of the current 6-digit code (never store the code in plaintext).
    verification_code_hash = Column(String, nullable=True)
    verification_sent_at = Column(DateTime(timezone=True), nullable=True)
    verification_attempts = Column(Integer, nullable=False, default=0)
    # IP the account was created from (best-effort; first X-Forwarded-For hop
    # behind a proxy) for per-IP free-quota enforcement.
    signup_ip = Column(String, nullable=True, index=True)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Owner of this podcast. Null = anonymous (e.g. created via the browser
    # extension before it authenticates). Anonymous docs are never listed in a
    # signed-in user's library, only reachable by their direct id.
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    raw_text = Column(Text, nullable=False)
    num_chunks = Column(Integer, default=0)
    status = Column(String, default="processing")  # processing | ready | failed
    error_message = Column(Text, nullable=True)
    # sha256 of the source bytes/text — used to dedupe re-uploads and skip
    # paying for the same LLM+TTS generation twice.
    content_hash = Column(String, nullable=True, index=True)
    # Explicit input source for exact analytics breakdowns:
    # pdf | docx | pptx | txt | image | pasted | other. Recorded at upload time
    # because content_type alone is ambiguous (image + pasted text both persist
    # as "text/plain"). Nullable for pre-existing rows; the analytics endpoint
    # falls back to filename-extension inference when it's NULL.
    source = Column(String, nullable=True, index=True)
    # IP the podcast was created from (best-effort; first X-Forwarded-For hop
    # behind a proxy) for per-IP free-quota enforcement across accounts.
    creator_ip = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    # Soft-delete marker. When a user deletes a podcast we KEEP this row (and its
    # audio/Q&A are purged) so the lifetime free-quota keeps counting it — a hard
    # delete would let a free user create -> delete -> create forever. Rows with
    # a non-NULL deleted_at are hidden from the library/stats/dedup but still
    # counted by the entitlement gates. See app/entitlements.py.
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

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


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Owner if signed in; null for anonymous feedback.
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    # Snapshot of who left it at submit time, so the view survives account edits
    # and lets you see "who likes / who dislikes" without a join.
    user_name = Column(String, nullable=True)
    user_email = Column(String, nullable=True)
    rating = Column(Integer, nullable=True)  # 1..5
    comment = Column(Text, nullable=True)
    source = Column(String, default="signout")  # where it was collected
    created_at = Column(DateTime(timezone=True), default=_utcnow)


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


# Best-effort backfill of Document.source for rows created before the column
# existed, inferred from the filename extension. Standard SQL (lower + LIKE) so
# it runs identically on SQLite and Postgres. Note: old text/plain rows are
# ambiguous — an uploaded ".txt" file and pasted text look identical here, so
# ".txt" is mapped to 'pasted' (the far more common origin). New rows are
# classified precisely at upload time and never hit this path.
_BACKFILL_SOURCE_SQL = """
UPDATE documents
SET source = CASE
    WHEN lower(filename) LIKE '%.pdf'  THEN 'pdf'
    WHEN lower(filename) LIKE '%.docx' THEN 'docx'
    WHEN lower(filename) LIKE '%.doc'  THEN 'docx'
    WHEN lower(filename) LIKE '%.pptx' THEN 'pptx'
    WHEN lower(filename) LIKE '%.ppt'  THEN 'pptx'
    WHEN lower(filename) LIKE '%.png'  THEN 'image'
    WHEN lower(filename) LIKE '%.jpg'  THEN 'image'
    WHEN lower(filename) LIKE '%.jpeg' THEN 'image'
    WHEN lower(filename) LIKE '%.webp' THEN 'image'
    WHEN lower(filename) LIKE '%.gif'  THEN 'image'
    WHEN lower(filename) LIKE '%.heic' THEN 'image'
    WHEN lower(filename) LIKE '%.heif' THEN 'image'
    WHEN lower(filename) LIKE '%.bmp'  THEN 'image'
    WHEN lower(filename) LIKE '%.tiff' THEN 'image'
    WHEN lower(filename) LIKE '%.txt'  THEN 'pasted'
    ELSE 'other'
END
WHERE source IS NULL
"""


async def _migrate_schema_sqlite(conn):
    """Backfill SQLite columns added after the initial deploy.

    ``create_all`` never ALTERs existing tables, so new columns on tables that
    predate them must be added by hand. PRAGMA introspection is SQLite-specific.
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
        if "user_id" not in doc_cols:
            sync_conn.execute(
                text("ALTER TABLE documents ADD COLUMN user_id TEXT")
            )
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents (user_id)")
            )
        if "source" not in doc_cols:
            sync_conn.execute(text("ALTER TABLE documents ADD COLUMN source TEXT"))
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_documents_source ON documents (source)")
            )
            # Best-effort backfill of pre-existing rows from the filename extension.
            sync_conn.execute(text(_BACKFILL_SOURCE_SQL))
        if "creator_ip" not in doc_cols:
            sync_conn.execute(text("ALTER TABLE documents ADD COLUMN creator_ip TEXT"))
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_documents_creator_ip ON documents (creator_ip)")
            )
        if "deleted_at" not in doc_cols:
            sync_conn.execute(text("ALTER TABLE documents ADD COLUMN deleted_at TIMESTAMP"))
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_documents_deleted_at ON documents (deleted_at)")
            )

        # Monetization columns on a pre-existing users table (Phase 0).
        user_rows = sync_conn.execute(text("PRAGMA table_info(users)")).fetchall()
        user_cols = {row[1] for row in user_rows}
        if "plan" not in user_cols:
            sync_conn.execute(
                text("ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'")
            )
        if "plan_status" not in user_cols:
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN plan_status TEXT"))
        if "plan_renews_at" not in user_cols:
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN plan_renews_at TIMESTAMP"))
        if "billing_customer_id" not in user_cols:
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN billing_customer_id TEXT"))
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_users_billing_customer_id ON users (billing_customer_id)")
            )
        if "billing_subscription_id" not in user_cols:
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN billing_subscription_id TEXT"))
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_users_billing_subscription_id ON users (billing_subscription_id)")
            )

        # Anti-abuse columns (email verification + multi-account controls).
        if "normalized_email" not in user_cols:
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN normalized_email TEXT"))
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_users_normalized_email ON users (normalized_email)")
            )
            # Backfill so uniqueness checks work for pre-existing accounts. Gmail
            # dot/plus normalization can't run in SQL, but stored emails are
            # already unique+lowercased, so lower(email) is a safe canonical seed.
            sync_conn.execute(
                text("UPDATE users SET normalized_email = lower(email) WHERE normalized_email IS NULL")
            )
        if "email_verified" not in user_cols:
            # Grandfather ALL pre-existing accounts as verified so nobody who
            # already signed up is locked out when verification is turned on.
            sync_conn.execute(
                text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 1")
            )
        if "verification_code_hash" not in user_cols:
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN verification_code_hash TEXT"))
        if "verification_sent_at" not in user_cols:
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN verification_sent_at TIMESTAMP"))
        if "verification_attempts" not in user_cols:
            sync_conn.execute(
                text("ALTER TABLE users ADD COLUMN verification_attempts INTEGER NOT NULL DEFAULT 0")
            )
        if "signup_ip" not in user_cols:
            sync_conn.execute(text("ALTER TABLE users ADD COLUMN signup_ip TEXT"))
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_users_signup_ip ON users (signup_ip)")
            )

    await conn.run_sync(_migrate)


async def _migrate_schema_postgres(conn):
    """Add columns to pre-existing Postgres tables.

    ``create_all`` creates the new ``users`` table but will not add ``user_id``
    to the ``documents`` table that already holds data on Railway. Postgres
    supports ``ADD COLUMN IF NOT EXISTS`` so this is safe to run every boot.
    """
    from sqlalchemy import text

    await conn.execute(
        text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id VARCHAR")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents (user_id)")
    )
    await conn.execute(
        text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS source VARCHAR")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_documents_source ON documents (source)")
    )
    # Best-effort backfill of pre-existing rows from the filename extension.
    await conn.execute(text(_BACKFILL_SOURCE_SQL))

    # Monetization columns on a pre-existing users table (Phase 0).
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan VARCHAR NOT NULL DEFAULT 'free'")
    )
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_status VARCHAR")
    )
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_renews_at TIMESTAMPTZ")
    )
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_customer_id VARCHAR")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_users_billing_customer_id ON users (billing_customer_id)")
    )
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_subscription_id VARCHAR")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_users_billing_subscription_id ON users (billing_subscription_id)")
    )

    # Per-IP quota column on documents.
    await conn.execute(
        text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS creator_ip VARCHAR")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_documents_creator_ip ON documents (creator_ip)")
    )

    # Soft-delete column on documents (preserves lifetime quota after deletion).
    await conn.execute(
        text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_documents_deleted_at ON documents (deleted_at)")
    )

    # Anti-abuse columns (email verification + multi-account controls).
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS normalized_email VARCHAR")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_users_normalized_email ON users (normalized_email)")
    )
    await conn.execute(
        text("UPDATE users SET normalized_email = lower(email) WHERE normalized_email IS NULL")
    )
    # Grandfather pre-existing accounts as verified (DEFAULT TRUE) so nobody who
    # already signed up is locked out when verification is turned on.
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE")
    )
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code_hash VARCHAR")
    )
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_sent_at TIMESTAMPTZ")
    )
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_attempts INTEGER NOT NULL DEFAULT 0")
    )
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_ip VARCHAR")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_users_signup_ip ON users (signup_ip)")
    )


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if _IS_SQLITE:
            await _migrate_schema_sqlite(conn)
        else:
            await _migrate_schema_postgres(conn)


async def get_db():
    async with async_session() as session:
        yield session
