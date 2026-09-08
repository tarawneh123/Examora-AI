-- 001_postgres_schema.sql
-- Production DDL for Examora AI Cloud Database (PostgreSQL 15+)
-- Completely independent from local teacher SQLite database.

CREATE TABLE IF NOT EXISTS online_exams (
    id BIGSERIAL PRIMARY KEY,
    publish_token VARCHAR(64) UNIQUE NOT NULL,
    idempotency_key VARCHAR(128) UNIQUE,
    title VARCHAR(255) NOT NULL,
    subject VARCHAR(128) NOT NULL,
    duration INTEGER NOT NULL,
    total_marks NUMERIC(6,2) NOT NULL DEFAULT 0.0,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, CLOSED, PURGED
    questions_json TEXT NOT NULL, -- Public questions (NO correct answers)
    allowed_students_json TEXT NOT NULL DEFAULT '[]', -- Allowed national IDs
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS online_answer_keys (
    id BIGSERIAL PRIMARY KEY,
    publish_token VARCHAR(64) NOT NULL REFERENCES online_exams(publish_token) ON DELETE CASCADE,
    keys_json TEXT NOT NULL, -- Private server-only evaluation map
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS online_attempts (
    id BIGSERIAL PRIMARY KEY,
    publish_token VARCHAR(64) NOT NULL REFERENCES online_exams(publish_token) ON DELETE CASCADE,
    student_national_id VARCHAR(64) NOT NULL,
    student_name VARCHAR(128) NOT NULL,
    attempt_token_hash VARCHAR(64) UNIQUE NOT NULL, -- SHA-256 hash of student's raw attempt_token
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, SUBMITTED, EXPIRED
    score NUMERIC(6,2) NOT NULL DEFAULT 0.0,
    total NUMERIC(6,2) NOT NULL DEFAULT 0.0,
    percentage NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    tier VARCHAR(32) NOT NULL DEFAULT '',
    feedback_message TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    server_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    is_synced BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS online_answers (
    id BIGSERIAL PRIMARY KEY,
    attempt_id BIGINT NOT NULL REFERENCES online_attempts(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL,
    answer VARCHAR(16) NOT NULL,
    answered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_online_attempt_q UNIQUE (attempt_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_online_exams_status ON online_exams(status);
CREATE INDEX IF NOT EXISTS idx_online_attempts_token ON online_attempts(publish_token);
CREATE INDEX IF NOT EXISTS idx_online_attempts_student ON online_attempts(student_national_id);
CREATE INDEX IF NOT EXISTS idx_online_attempts_hash ON online_attempts(attempt_token_hash);
CREATE INDEX IF NOT EXISTS idx_online_answers_attempt ON online_answers(attempt_id);
