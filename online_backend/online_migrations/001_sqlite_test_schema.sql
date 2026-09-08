-- 001_sqlite_test_schema.sql
-- Isolated Test Schema for SQLite Environment (Unit Tests Only)
-- STRICT RULE: Must NEVER connect to or reference exam_platform.db

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS online_exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publish_token TEXT UNIQUE NOT NULL,
    idempotency_key TEXT UNIQUE,
    title TEXT NOT NULL,
    subject TEXT NOT NULL,
    duration INTEGER NOT NULL,
    total_marks REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, CLOSED, PURGED
    questions_json TEXT NOT NULL,
    allowed_students_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS online_answer_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publish_token TEXT NOT NULL REFERENCES online_exams(publish_token) ON DELETE CASCADE,
    keys_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS online_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publish_token TEXT NOT NULL REFERENCES online_exams(publish_token) ON DELETE CASCADE,
    student_national_id TEXT NOT NULL,
    student_name TEXT NOT NULL,
    attempt_token_hash TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, SUBMITTED, EXPIRED
    score REAL NOT NULL DEFAULT 0.0,
    total REAL NOT NULL DEFAULT 0.0,
    percentage REAL NOT NULL DEFAULT 0.0,
    tier TEXT NOT NULL DEFAULT '',
    feedback_message TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    server_deadline TEXT NOT NULL,
    finished_at TEXT,
    is_synced INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS online_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES online_attempts(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL,
    answer TEXT NOT NULL,
    answered_at TEXT NOT NULL,
    UNIQUE(attempt_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_online_exams_status ON online_exams(status);
CREATE INDEX IF NOT EXISTS idx_online_attempts_token ON online_attempts(publish_token);
CREATE INDEX IF NOT EXISTS idx_online_attempts_student ON online_attempts(student_national_id);
CREATE INDEX IF NOT EXISTS idx_online_attempts_hash ON online_attempts(attempt_token_hash);
CREATE INDEX IF NOT EXISTS idx_online_answers_attempt ON online_answers(attempt_id);
