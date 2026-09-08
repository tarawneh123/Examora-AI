-- 002_domain_entities_and_snapshots.sql: Subjects, Packages, and Immutable Attempt Snapshots
PRAGMA foreign_keys = ON;

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

CREATE TABLE IF NOT EXISTS exam_questions (
    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    position INTEGER DEFAULT 1,
    PRIMARY KEY(exam_id, question_id)
);

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
