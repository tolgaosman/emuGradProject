-- Plagiarism Detection System | PostgreSQL Schema v1.0.0 
-- Run: psql -U plagcheck_user plagcheck_db < db/schema.sql 

CREATE EXTENSION IF NOT EXISTS pgcrypto; 

CREATE TABLE IF NOT EXISTS app_user (
 user_id SERIAL PRIMARY KEY,
 user_name VARCHAR(100) NOT NULL,
 user_email VARCHAR(150) NOT NULL UNIQUE,
 user_role VARCHAR(20) NOT NULL CHECK (user_role IN ('student','professor','admin')),
 created_at TIMESTAMP NOT NULL DEFAULT NOW()
); 

CREATE INDEX IF NOT EXISTS idx_user_email ON app_user (user_email);

CREATE TABLE IF NOT EXISTS scan_request (
 scan_id SERIAL PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
 scan_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
 threshold FLOAT NOT NULL DEFAULT 0.70 CHECK (threshold > 0 AND threshold < 1),
 status VARCHAR(20) NOT NULL DEFAULT 'pending'
 CHECK (status IN ('pending','running','complete','error'))
); 

CREATE INDEX IF NOT EXISTS idx_scan_user ON scan_request (user_id); 

CREATE TABLE IF NOT EXISTS scan_file (
 file_id SERIAL PRIMARY KEY,
 scan_id INTEGER NOT NULL REFERENCES scan_request(scan_id) ON DELETE CASCADE,
 file_name VARCHAR(255) NOT NULL,
 file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
 file_format VARCHAR(10) NOT NULL CHECK (file_format IN ('txt','py','pdf','docx'))
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
 algorithm_name VARCHAR(50) NOT NULL CHECK (algorithm_name IN ('cosine','winnowing','jaccard','ast','all')),
 PRIMARY KEY (scan_id, algorithm_name)
); 

CREATE TABLE IF NOT EXISTS audit_log (
 log_id SERIAL PRIMARY KEY,
 scan_id INTEGER REFERENCES scan_request(scan_id) ON DELETE SET NULL,
 user_id INTEGER REFERENCES app_user(user_id) ON DELETE SET NULL,
 event_type VARCHAR(50) NOT NULL
 CHECK (event_type IN ('SCAN_START','SCAN_COMPLETE','SCAN_ERROR','FILE_REJECTED','API_REQUEST','API_ERROR')),
 event_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
 event_detail TEXT 
); 

CREATE INDEX IF NOT EXISTS idx_audit_scan ON audit_log (scan_id); 
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (event_timestamp DESC);
