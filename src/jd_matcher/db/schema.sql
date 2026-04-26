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
