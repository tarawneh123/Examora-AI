-- Migration SQL for Educational Exam Management Platform (Abla Exam AI)
-- Enforces Single Source of Truth, Subject Domain Entity, Question Packages,
-- Immutable Attempt Snapshots, and Audit Logging.

PRAGMA foreign_keys = ON;

-- 1. Settings Table
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 2. Subjects Domain Entity
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'ar',
    direction TEXT NOT NULL DEFAULT 'rtl',
    is_default INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

-- 3. Question Packages Table
CREATE TABLE IF NOT EXISTS question_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT DEFAULT "",
    sort_order INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(subject_id, name)
);

-- 4. Questions Table
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    package_id INTEGER REFERENCES question_packages(id) ON DELETE SET NULL,
    subject TEXT DEFAULT "",
    unit TEXT DEFAULT "",
    lesson TEXT DEFAULT "",
    question TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct TEXT NOT NULL DEFAULT 'أ',
    mark REAL DEFAULT 1.0,
    difficulty TEXT DEFAULT 'متوسط',
    image_path TEXT DEFAULT "",
    status TEXT DEFAULT 'APPROVED',
    approved INTEGER DEFAULT 1,
    confidence REAL DEFAULT 1.0,
    warnings TEXT DEFAULT "",
    source_file TEXT DEFAULT "",
    source_page INTEGER DEFAULT 1,
    language TEXT DEFAULT 'ar',
    direction TEXT DEFAULT 'rtl',
    created_at TEXT,
    updated_at TEXT
);

-- 5. Students Table
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT UNIQUE NOT NULL,
    class_name TEXT DEFAULT "",
    section TEXT DEFAULT "",
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TEXT
);

-- 6. Exams Table
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE RESTRICT,
    package_id INTEGER REFERENCES question_packages(id) ON DELETE SET NULL,
    subject TEXT DEFAULT "",
    class_name TEXT DEFAULT "",
    section TEXT DEFAULT "",
    duration INTEGER DEFAULT 45,
    question_count INTEGER DEFAULT 0,
    password TEXT DEFAULT "",
    password_hash TEXT DEFAULT "",
    status TEXT DEFAULT 'DRAFT',
    active INTEGER DEFAULT 0,
    unit_filter TEXT DEFAULT "",
    random_order INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

-- 7. Exam Questions Mapping
CREATE TABLE IF NOT EXISTS exam_questions (
    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    position INTEGER DEFAULT 1,
    PRIMARY KEY(exam_id, question_id)
);

-- 8. Attempts Table
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    student_name TEXT NOT NULL,
    attempt_number INTEGER DEFAULT 1,
    status TEXT DEFAULT 'NOT_STARTED',
    score REAL DEFAULT 0.0,
    total REAL DEFAULT 0.0,
    percentage REAL DEFAULT 0.0,
    started_at TEXT,
    finished_at TEXT,
    submitted_at TEXT,
    last_activity_at TEXT,
    ip_address TEXT DEFAULT ""
);

-- 9. Attempt Snapshots (Immutable Question Snapshots)
CREATE TABLE IF NOT EXISTS attempt_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    question_id INTEGER,
    position INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct_option TEXT NOT NULL,
    mark REAL DEFAULT 1.0,
    image_path TEXT DEFAULT "",
    language TEXT DEFAULT 'ar',
    direction TEXT DEFAULT 'rtl'
);

-- 10. Answers Table
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    snapshot_id INTEGER REFERENCES attempt_snapshots(id) ON DELETE CASCADE,
    question_id INTEGER,
    answer TEXT DEFAULT "",
    correct TEXT DEFAULT "",
    is_correct INTEGER DEFAULT 0,
    mark REAL DEFAULT 0.0,
    answered_at TEXT
);

-- 11. Audit Log Table
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    before_state TEXT DEFAULT "",
    after_state TEXT DEFAULT "",
    status TEXT DEFAULT 'SUCCESS',
    timestamp TEXT NOT NULL
);

-- Indexes for optimal performance
CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject_id);
CREATE INDEX IF NOT EXISTS idx_questions_package ON questions(package_id);
CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
CREATE INDEX IF NOT EXISTS idx_exams_subject ON exams(subject_id);
CREATE INDEX IF NOT EXISTS idx_attempts_exam ON attempts(exam_id);
CREATE INDEX IF NOT EXISTS idx_attempts_student ON attempts(student_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_attempt ON attempt_snapshots(attempt_id);
CREATE INDEX IF NOT EXISTS idx_answers_attempt ON answers(attempt_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
