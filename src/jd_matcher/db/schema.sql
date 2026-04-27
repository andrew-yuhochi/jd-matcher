-- jd-matcher SQLite schema
-- All tables carry user_id TEXT NOT NULL DEFAULT 'default' (commercial hedge 3 — namespace-aware data model).
-- Apply via init_db(); all statements use IF NOT EXISTS for idempotency.

PRAGMA foreign_keys = ON;

-- -------------------------------------------------------------------------
-- users — single row per namespace; 'default' pre-seeded by init_db()
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- -------------------------------------------------------------------------
-- postings — one canonical record per unique job role
-- M1: canonical_* filled best-effort from email parsing; LLM fields nullable.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS postings (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                    TEXT NOT NULL DEFAULT 'default' REFERENCES users(id),
    canonical_company          TEXT,
    canonical_title            TEXT,
    canonical_location         TEXT,
    seniority_band             TEXT,
    team_or_department         TEXT,
    top_skills                 TEXT,           -- JSON-encoded list[str]
    role_summary               TEXT,
    full_jd                    TEXT,
    salary_min_cad             INTEGER,
    salary_max_cad             INTEGER,
    industry                   TEXT,
    fit_score                  INTEGER,
    fit_reasoning              TEXT,
    tags                       TEXT,           -- JSON-encoded list[str]
    primary_focus              TEXT,
    requires_pr_or_citizenship INTEGER,        -- 0 / 1
    canadian_employer_likely   INTEGER,        -- 0 / 1
    language_required          TEXT,
    hydration_status           TEXT NOT NULL DEFAULT 'complete'
                                   CHECK (hydration_status IN ('complete', 'partial', 'failed')),
    first_seen                 TIMESTAMP NOT NULL,
    last_seen                  TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_postings_first_seen ON postings (first_seen);

-- -------------------------------------------------------------------------
-- posting_sources — one row per (posting, origin); supports multi-source dedup
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS posting_sources (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id           INTEGER NOT NULL REFERENCES postings(id),
    user_id              TEXT NOT NULL DEFAULT 'default',
    source               TEXT NOT NULL,       -- e.g. linkedin_email, indeed_email, linkedin_hydrator
    source_url           TEXT NOT NULL,
    source_first_seen    TIMESTAMP NOT NULL,
    raw_body             TEXT,
    raw_html             TEXT
);

CREATE INDEX IF NOT EXISTS idx_posting_sources_posting_id ON posting_sources (posting_id);

-- -------------------------------------------------------------------------
-- seen_urls — URL dedup fast path; UNIQUE enforced per user
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seen_urls (
    url        TEXT NOT NULL,
    user_id    TEXT NOT NULL DEFAULT 'default',
    posting_id INTEGER NOT NULL REFERENCES postings(id),
    seen_at    TIMESTAMP NOT NULL,
    UNIQUE (user_id, url)
);

-- -------------------------------------------------------------------------
-- applied — applied-state tracker; one row per (user, posting)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS applied (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id        INTEGER NOT NULL REFERENCES postings(id),
    user_id           TEXT NOT NULL DEFAULT 'default',
    status            TEXT NOT NULL DEFAULT 'Applied'
                          CHECK (status IN ('Applied', 'Screen', 'Interview', 'Offer', 'Rejected', 'Ghosted')),
    applied_at        TIMESTAMP NOT NULL,
    status_updated_at TIMESTAMP NOT NULL,
    notes             TEXT,
    UNIQUE (user_id, posting_id)
);

-- -------------------------------------------------------------------------
-- dismissed — permanent blacklist; one row per (user, posting)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dismissed (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id   INTEGER NOT NULL REFERENCES postings(id),
    user_id      TEXT NOT NULL DEFAULT 'default',
    dismissed_at TIMESTAMP NOT NULL,
    reason       TEXT,
    UNIQUE (user_id, posting_id)
);

-- -------------------------------------------------------------------------
-- events — hedge 2 instrumentation substrate
-- posting_id is nullable: not all event types are tied to a posting.
-- metadata is JSON-encoded for arbitrary per-event fields.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL DEFAULT 'default',
    session_id  TEXT,
    event_type  TEXT NOT NULL,
    posting_id  INTEGER REFERENCES postings(id),
    metadata    TEXT,       -- JSON-encoded
    timestamp   TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp);

-- -------------------------------------------------------------------------
-- pipeline_runs — per-source run health (non-hideable failure flagging).
-- health_status is NOT NULL — failures cannot be hidden (C11 invariant).
-- One row per source per orchestrator invocation.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 TEXT NOT NULL DEFAULT 'default',
    run_id                  TEXT NOT NULL,
    source                  TEXT NOT NULL,   -- e.g. gmail_linkedin, gmail_indeed, hydrator_linkedin
    health_status           TEXT NOT NULL
                                CHECK (health_status IN ('healthy', 'degraded', 'failed')),
    failure_reason          TEXT,
    started_at              TIMESTAMP NOT NULL,
    finished_at             TIMESTAMP,
    last_successful_fetch_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_run_id ON pipeline_runs (run_id);

-- -------------------------------------------------------------------------
-- email_ingest_log — per-email ingestion telemetry (M1, TASK-M1-005c)
-- One row per Gmail message fetched; counters updated in place by C4/C5.
-- gmail_message_id UNIQUE ensures re-ingesting the same message is idempotent.
-- pipeline_run_id is the canonical orchestrator run_id (NOT ingester sub-run).
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_ingest_log (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                         TEXT NOT NULL DEFAULT 'default',
    gmail_message_id                TEXT NOT NULL UNIQUE,
    source                          TEXT NOT NULL,
    sender                          TEXT NOT NULL,
    subject                         TEXT NOT NULL,
    received_at                     TIMESTAMP NOT NULL,
    ingested_at                     TIMESTAMP NOT NULL,
    pipeline_run_id                 TEXT NOT NULL,
    urls_extracted_count            INTEGER NOT NULL DEFAULT 0,
    urls_new_count                  INTEGER NOT NULL DEFAULT 0,
    postings_created_count          INTEGER NOT NULL DEFAULT 0,
    postings_hydrated_count         INTEGER NOT NULL DEFAULT 0,
    postings_hydration_failed_count INTEGER NOT NULL DEFAULT 0,
    notes                           TEXT
);

CREATE INDEX IF NOT EXISTS idx_email_ingest_log_run      ON email_ingest_log (pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_email_ingest_log_received ON email_ingest_log (received_at);
-- NOTE: idx_email_ingest_log_filter is created in init_db.py AFTER the
-- filter_status column is added via ALTER TABLE (schema.sql runs before the
-- ALTER, so the index must be deferred to the Python helper).

-- =========================================================================
-- M2 ADDITIONS — content-aware dedup + repost detection + title pre-filter
-- =========================================================================

-- -------------------------------------------------------------------------
-- canonical_postings — one row per merged "canonical job" (M2).
-- The unit a card represents on Main from M2 forward; posting_canonical_links
-- many-to-one maps source variants onto a canonical.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS canonical_postings (
    canonical_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT NOT NULL DEFAULT 'default' REFERENCES users(id),
    canonical_title     TEXT NOT NULL,
    canonical_company   TEXT NOT NULL,
    canonical_seniority TEXT NOT NULL,
    canonical_location  TEXT NOT NULL,
    team_or_department  TEXT NULL,
    top_skills          JSON NOT NULL,      -- list[str]; LLM-extracted; ordered by salience
    role_summary        TEXT NOT NULL,      -- ~3-4 sentence neutral summary; the embedding source
    full_jd             TEXT NOT NULL,      -- longer of merged variants
    full_jd_provenance  JSON NOT NULL,      -- {"chosen_from_posting_id": <id>, "source": "linkedin|indeed|..."}
    first_seen          TIMESTAMP NOT NULL, -- earliest first_seen across all linked postings
    last_seen           TIMESTAMP NOT NULL, -- max last_seen across all linked postings
    sources_summary     JSON NOT NULL,      -- denormalised list e.g. ["linkedin", "indeed"]
    created_at          TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- C21 BLOCK key: "same TEAM?"; seniority moved to FUSE
CREATE INDEX IF NOT EXISTS idx_canonical_user_block      ON canonical_postings (user_id, canonical_company, team_or_department, canonical_location);
CREATE INDEX IF NOT EXISTS idx_canonical_user_first_seen ON canonical_postings (user_id, first_seen DESC);

-- -------------------------------------------------------------------------
-- posting_canonical_links — many-to-one mapping postings → canonical_postings.
-- Append-only; a row is inserted whenever C21 returns merge or creates a new
-- canonical. UNIQUE(user_id, posting_id) enforces one canonical per posting.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS posting_canonical_links (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          TEXT NOT NULL DEFAULT 'default' REFERENCES users(id),
    posting_id       TEXT NOT NULL,    -- → postings.id
    canonical_id     INTEGER NOT NULL, -- → canonical_postings.canonical_id
    similarity_score REAL NOT NULL,    -- fused score from C21; 1.0 for the seed posting
    merge_kind       TEXT NOT NULL,    -- 'new_canonical' | 'content_dedup' | 'repost'
    merged_at        TIMESTAMP NOT NULL,
    UNIQUE (user_id, posting_id)
);

CREATE INDEX IF NOT EXISTS idx_links_canonical ON posting_canonical_links (canonical_id);
CREATE INDEX IF NOT EXISTS idx_links_posting   ON posting_canonical_links (posting_id);
CREATE INDEX IF NOT EXISTS idx_links_repost    ON posting_canonical_links (canonical_id, merge_kind);

-- -------------------------------------------------------------------------
-- posting_embeddings — embedding vectors keyed per posting (M2).
-- Replaces the inline postings.embedding BLOB column (never written in M1).
-- Cached: reused across runs if text_hash matches (skip-on-unchanged).
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS posting_embeddings (
    posting_id      TEXT PRIMARY KEY,   -- → postings.id
    user_id         TEXT NOT NULL DEFAULT 'default' REFERENCES users(id),
    text_source     TEXT NOT NULL,      -- 'role_summary' (preferred) | 'full_jd' (fallback)
    text_hash       TEXT NOT NULL,      -- SHA-256 of source text — cache key
    embedding       BLOB NOT NULL,      -- packed float32 vector
    embedding_dim   INTEGER NOT NULL,   -- vector length; cross-validated against model_name on read
    model_name      TEXT NOT NULL,      -- 'text-embedding-3-small' | 'all-MiniLM-L6-v2' | ...
    embedded_at     TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_embeddings_user_model ON posting_embeddings (user_id, model_name);

-- -------------------------------------------------------------------------
-- llm_call_ledger — per-call cost + latency log for cloud LLM/embedding calls.
-- Load-bearing: the cloud-vs-local benchmark sub-task at M3 reads this table.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_call_ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL DEFAULT 'default' REFERENCES users(id),
    provider      TEXT NOT NULL,            -- 'openai' | 'ollama' | 'sentence_transformers'
    model_name    TEXT NOT NULL,            -- e.g. 'gpt-4o-mini' | 'text-embedding-3-small'
    call_kind     TEXT NOT NULL,            -- 'extraction' | 'embedding'
    input_tokens  INTEGER NULL,             -- NULL for local providers without token counts
    output_tokens INTEGER NULL,
    cost_usd      REAL NOT NULL DEFAULT 0.0, -- 0.0 for local; computed for cloud
    latency_ms    INTEGER NOT NULL,
    posting_id    TEXT NULL,                -- → postings.id; NULL for batch/system calls
    called_at     TIMESTAMP NOT NULL,
    status        TEXT NOT NULL            -- 'success' | 'retry' | 'failure'
);

CREATE INDEX IF NOT EXISTS idx_ledger_user_called ON llm_call_ledger (user_id, called_at DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_user_kind   ON llm_call_ledger (user_id, call_kind, model_name);
