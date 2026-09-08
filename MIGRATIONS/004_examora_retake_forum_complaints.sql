-- 004_examora_retake_forum_complaints.sql
-- Adds Support for:
-- 1. Examora Retake and Individual Student Exams
-- 2. Official vs Superseded Attempts & Grade Replacement
-- 3. Teachers' Community Forum (Topics, Replies, Likes)
-- 4. Complaints & Suggestions System with In-App Notifications
-- 5. Staged Published Exams for Online Delivery

-- 1. Forum Topics
CREATE TABLE IF NOT EXISTS forum_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER,
    author_name TEXT NOT NULL,
    author_email TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT DEFAULT 'عام',
    tags TEXT DEFAULT '',
    views_count INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    is_pinned INTEGER DEFAULT 0,
    is_locked INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Forum Replies
CREATE TABLE IF NOT EXISTS forum_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    author_id INTEGER,
    author_name TEXT NOT NULL,
    author_email TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (topic_id) REFERENCES forum_topics(id) ON DELETE CASCADE
);

-- 3. Forum Likes
CREATE TABLE IF NOT EXISTS forum_likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    user_email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(topic_id, user_email)
);

-- 4. Complaints & Suggestions
CREATE TABLE IF NOT EXISTS complaints_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number TEXT UNIQUE NOT NULL,
    teacher_id INTEGER,
    teacher_name TEXT NOT NULL,
    teacher_email TEXT NOT NULL,
    type TEXT NOT NULL, -- SUGGESTION, COMPLAINT, BUG, FEATURE_REQUEST
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT DEFAULT 'MEDIUM', -- LOW, MEDIUM, HIGH, URGENT
    attachment_path TEXT DEFAULT '',
    status TEXT DEFAULT 'NEW', -- NEW, IN_REVIEW, IN_PROGRESS, RESOLVED, REJECTED, CLOSED
    admin_response TEXT DEFAULT '',
    responded_by TEXT DEFAULT '',
    responded_at TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 5. In-App Notifications
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_type TEXT NOT NULL, -- TEACHER, STUDENT, SUPER_ADMIN
    recipient_email TEXT NOT NULL,
    recipient_id INTEGER,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    link TEXT DEFAULT '',
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- 6. Published Exams (Online Staging)
CREATE TABLE IF NOT EXISTS published_exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_exam_id INTEGER NOT NULL,
    publish_token TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    duration INTEGER NOT NULL,
    status TEXT DEFAULT 'ACTIVE', -- ACTIVE, CLOSED, SYNCED, PURGED
    payload_json TEXT NOT NULL,
    published_at TEXT NOT NULL,
    closed_at TEXT,
    synced_at TEXT,
    purged_at TEXT
);

CREATE TABLE IF NOT EXISTS published_exam_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publish_token TEXT NOT NULL,
    student_national_id TEXT NOT NULL,
    student_name TEXT NOT NULL,
    answers_json TEXT NOT NULL,
    score REAL DEFAULT 0.0,
    total_marks REAL DEFAULT 0.0,
    is_synced INTEGER DEFAULT 0,
    submitted_at TEXT NOT NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_forum_topics_category ON forum_topics(category);
CREATE INDEX IF NOT EXISTS idx_forum_topics_created ON forum_topics(created_at);
CREATE INDEX IF NOT EXISTS idx_forum_replies_topic ON forum_replies(topic_id);
CREATE INDEX IF NOT EXISTS idx_complaints_teacher ON complaints_suggestions(teacher_email);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints_suggestions(status);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_email, is_read);
CREATE INDEX IF NOT EXISTS idx_published_exams_token ON published_exams(publish_token);
