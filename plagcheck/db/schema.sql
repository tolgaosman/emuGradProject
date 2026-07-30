-- Plagiarism Detection System | PostgreSQL Schema v2.1.0
-- Run: psql -U plagcheck_user plagcheck_db < db/schema.sql
--
-- Safe to re-run against an existing v1 database: every CREATE TABLE is
-- IF NOT EXISTS, and the v2 additions (mode/language support, the AI-result
-- table, per-file similarity index, internet-source matches) use named
-- constraints that are dropped and re-added idempotently below, so this
-- file both creates a fresh schema and upgrades an older one in place.

CREATE EXTENSION IF NOT EXISTS pgcrypto; 

CREATE TABLE IF NOT EXISTS app_user (
 user_id SERIAL PRIMARY KEY,
 user_name VARCHAR(100) NOT NULL,
 user_email VARCHAR(150) NOT NULL UNIQUE,
 user_role VARCHAR(20) NOT NULL CHECK (user_role IN ('student','professor','admin')),
 created_at TIMESTAMP NOT NULL DEFAULT NOW()
); 

CREATE INDEX IF NOT EXISTS idx_user_email ON app_user (user_email);

-- Seed a system account so scan_request.user_id has something to reference
-- until real authentication exists (the API/CLI run unauthenticated).
INSERT INTO app_user (user_name, user_email, user_role)
VALUES ('system', 'system@plagcheck.local', 'admin')
ON CONFLICT (user_email) DO NOTHING;

CREATE TABLE IF NOT EXISTS scan_request (
 scan_id SERIAL PRIMARY KEY,
 -- Public API identifier. scan_id (SERIAL) stays the internal PK/FK target;
 -- scan_uuid is what clients see and pass back to GET /api/report/<uuid>.
 scan_uuid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
 user_id INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
 scan_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
 threshold FLOAT NOT NULL DEFAULT 0.70 CHECK (threshold > 0 AND threshold < 1),
 status VARCHAR(20) NOT NULL DEFAULT 'pending'
 CHECK (status IN ('pending','running','complete','error'))
);

CREATE INDEX IF NOT EXISTS idx_scan_user ON scan_request (user_id);
CREATE INDEX IF NOT EXISTS idx_scan_uuid ON scan_request (scan_uuid);

CREATE TABLE IF NOT EXISTS scan_file (
 file_id SERIAL PRIMARY KEY,
 scan_id INTEGER NOT NULL REFERENCES scan_request(scan_id) ON DELETE CASCADE,
 file_name VARCHAR(255) NOT NULL,
 file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
 file_format VARCHAR(10) NOT NULL,
 -- Turnitin-style per-document "% of this file matched something else" in
 -- the batch. Asymmetric (unlike scan_pair.similarity_score), so it lives
 -- on the file, not the pair. NULL for AI-mode scans, where it doesn't apply.
 similarity_index FLOAT
);

ALTER TABLE scan_file DROP CONSTRAINT IF EXISTS chk_file_format;
ALTER TABLE scan_file ADD CONSTRAINT chk_file_format CHECK (
 file_format IN ('txt','py','pdf','docx','java','c','h','cpp','cc','hpp')
);

ALTER TABLE scan_file DROP CONSTRAINT IF EXISTS chk_similarity_index_range;
ALTER TABLE scan_file ADD CONSTRAINT chk_similarity_index_range CHECK (
 similarity_index IS NULL OR (similarity_index >= 0 AND similarity_index <= 1)
);

CREATE INDEX IF NOT EXISTS idx_file_scan ON scan_file (scan_id);

CREATE TABLE IF NOT EXISTS scan_pair (
 pair_id SERIAL PRIMARY KEY,
 scan_id INTEGER NOT NULL REFERENCES scan_request(scan_id) ON DELETE CASCADE,
 file_id_a INTEGER NOT NULL REFERENCES scan_file(file_id),
 file_id_b INTEGER NOT NULL REFERENCES scan_file(file_id),
 similarity_score FLOAT NOT NULL CHECK (similarity_score >= 0 AND similarity_score <= 1),
 flagged BOOLEAN NOT NULL DEFAULT FALSE,
 CONSTRAINT chk_pair_order CHECK (file_id_a < file_id_b)
); 

CREATE INDEX IF NOT EXISTS idx_pair_scan ON scan_pair (scan_id);
CREATE INDEX IF NOT EXISTS idx_pair_flagged ON scan_pair (flagged) WHERE flagged = TRUE;

CREATE TABLE IF NOT EXISTS scan_algorithm (
 scan_id INTEGER NOT NULL REFERENCES scan_request(scan_id) ON DELETE CASCADE,
 -- Historically named for the 4 selectable algorithms; now also stores the
 -- 4 user-facing modes, each of which composes 1-2 of those algorithms
 -- internally (see engine.py's _CODE_*_WEIGHT / _TEXT_*_WEIGHT constants).
 -- Both vocabularies are kept so pre-v2 scan history stays valid.
 algorithm_name VARCHAR(50) NOT NULL,
 PRIMARY KEY (scan_id, algorithm_name)
);

ALTER TABLE scan_algorithm DROP CONSTRAINT IF EXISTS chk_algorithm_name;
ALTER TABLE scan_algorithm ADD CONSTRAINT chk_algorithm_name CHECK (
 algorithm_name IN (
   'cosine','winnowing','jaccard','ast','all','auto',
   'code_similarity','text_similarity','ai_code','ai_text'
 )
);

-- One row per file per AI-mode scan (ai_code / ai_text). Only the headline
-- probability + band are persisted relationally; the per-signal breakdown
-- and sentence/block-level segments are richer analysis data that, like raw
-- file text, live in the JSON sidecar / API response rather than the
-- normalized schema.
CREATE TABLE IF NOT EXISTS scan_ai_result (
 result_id SERIAL PRIMARY KEY,
 scan_id INTEGER NOT NULL REFERENCES scan_request(scan_id) ON DELETE CASCADE,
 file_id INTEGER NOT NULL REFERENCES scan_file(file_id) ON DELETE CASCADE,
 probability FLOAT NOT NULL CHECK (probability >= 0 AND probability <= 1),
 band VARCHAR(10) NOT NULL CHECK (band IN ('low','possible','likely')),
 UNIQUE (scan_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_result_scan ON scan_ai_result (scan_id);

-- One row per fetched web page compared against an uploaded file, for the
-- code_similarity/text_similarity modes' "compare against the internet"
-- feature (see websearch.py). Scoped strictly to files whose mode is
-- web-eligible; empty for AI-mode scans and for any scan where web search
-- was unavailable/disabled.
CREATE TABLE IF NOT EXISTS scan_web_match (
 web_match_id SERIAL PRIMARY KEY,
 scan_id INTEGER NOT NULL REFERENCES scan_request(scan_id) ON DELETE CASCADE,
 file_id INTEGER NOT NULL REFERENCES scan_file(file_id) ON DELETE CASCADE,
 query TEXT NOT NULL,
 url TEXT NOT NULL,
 title TEXT,
 score FLOAT NOT NULL CHECK (score >= 0 AND score <= 1)
);

CREATE INDEX IF NOT EXISTS idx_web_match_scan ON scan_web_match (scan_id);
CREATE INDEX IF NOT EXISTS idx_web_match_file ON scan_web_match (file_id);

CREATE TABLE IF NOT EXISTS audit_log (
 log_id SERIAL PRIMARY KEY,
 scan_id INTEGER REFERENCES scan_request(scan_id) ON DELETE SET NULL,
 user_id INTEGER REFERENCES app_user(user_id) ON DELETE SET NULL,
 event_type VARCHAR(50) NOT NULL,
 event_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
 event_detail TEXT
);

ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_event_type_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_event_type_check CHECK (
 event_type IN (
   'SCAN_START','SCAN_COMPLETE','SCAN_ERROR','FILE_REJECTED',
   'API_REQUEST','API_ERROR','WEB_SEARCH_QUERY'
 )
);

CREATE INDEX IF NOT EXISTS idx_audit_scan ON audit_log (scan_id); 
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (event_timestamp DESC);
