-- 001_initial_schema.sql: Initial Core Tables and Settings
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

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
