# -*- coding: utf-8 -*-
"""
Safe migration runner for Examora AI Platform (v31+).
Performs automatic timestamped database backup prior to migration,
applies SQL schema changes, safely runs incremental migrations,
and verifies database integrity with automatic rollback on error.
"""
import os, sys, shutil, sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'exam_data'
DB_PATH = DATA_DIR / 'exam_platform.db'
BACKUP_DIR = DATA_DIR / 'backups'
MIGRATIONS_DIR = BASE_DIR / 'MIGRATIONS'

DEFAULT_SETTINGS = {
    'platform_name': 'Examora AI - منصة الاختبارات الذكية',
    'app_name': 'Examora AI',
    'directorate_name': 'مديرية التربية والتعليم - لواء المزار الجنوبي',
    'district_name': 'لواء المزار الجنوبي',
    'school_name': 'مدرسة خالد بن الوليد الثانوية',
    'ministry_name': 'المملكة الأردنية الهاشمية - وزارة التربية والتعليم',
    'teacher_name': 'عبلة الطراونة',
    'grade': 'الثانوية العامة (التوجيهي)',
    'section': 'أ',
    'admin_password': 'admin',
    'student_default_password': '1234',
    'school_logo_path': '',
    'ministry_logo_path': '',
    'primary_color': '#2563eb',
    'secondary_color': '#7c3aed',
    'font_family': 'Cairo',
    'first_run_completed': '1',
    'footer_text': 'منصة Examora AI للاختبارات الذكية',
    'footer_url': 'https://htst-d.web.app/',
    'copyright_text': 'جميع الحقوق محفوظة © 2026 Examora AI'
}

def get_db_connection(target_path):
    target = Path(target_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    is_shadow = False
    try:
        con = sqlite3.connect(str(target))
        con.execute('CREATE TABLE IF NOT EXISTS _test_lock(id INT);')
        con.execute('INSERT INTO _test_lock VALUES(1);')
        con.commit()
        con.execute('DROP TABLE _test_lock;')
        con.commit()
        con.close()
        actual_path = target
    except sqlite3.OperationalError:
        is_shadow = True
        actual_path = Path('/tmp') / f'shadow_{target.name}'
        if target.exists() and os.path.getsize(target) > 0:
            shutil.copyfile(target, actual_path)
        else:
            con = sqlite3.connect(str(actual_path))
            con.close()
            shutil.copyfile(actual_path, target)

    con = sqlite3.connect(str(actual_path), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con, is_shadow, actual_path, target

def backup_database():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists() and os.path.getsize(DB_PATH) > 0:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup_file = BACKUP_DIR / f'pre_migration_{timestamp}.db'
        shutil.copy2(DB_PATH, backup_file)
        print(f"Database backed up successfully to: {backup_file.name}")
        return backup_file
    return None

def safe_add_column(cur, table, column_def):
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        print(f"Added column {column_def} to {table}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            pass
        else:
            raise

def run_migration():
    print(f"Starting database migration for: {DB_PATH}")
    backup_file = backup_database()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    con, is_shadow, actual_path, target_path = get_db_connection(DB_PATH)
    cur = con.cursor()

    try:
        cur.execute("PRAGMA foreign_keys = OFF;")
        
        # 1. Run migration scripts from MIGRATIONS directory in order
        if MIGRATIONS_DIR.exists():
            sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            for sfile in sql_files:
                print(f"Applying migration: {sfile.name}")
                with open(sfile, 'r', encoding='utf-8') as f:
                    cur.executescript(f.read())

        # 2. Add columns to exams table safely
        safe_add_column(cur, "exams", "exam_kind TEXT DEFAULT 'REGULAR'")
        safe_add_column(cur, "exams", "target_student_id INTEGER DEFAULT NULL")
        safe_add_column(cur, "exams", "original_exam_id INTEGER DEFAULT NULL")
        safe_add_column(cur, "exams", "original_attempt_id INTEGER DEFAULT NULL")

        # 3. Add columns to attempts table safely
        safe_add_column(cur, "attempts", "is_official INTEGER DEFAULT 1")
        safe_add_column(cur, "attempts", "is_superseded INTEGER DEFAULT 0")
        safe_add_column(cur, "attempts", "replacement_attempt_id INTEGER DEFAULT NULL")
        safe_add_column(cur, "attempts", "supersedes_attempt_id INTEGER DEFAULT NULL")
        safe_add_column(cur, "attempts", "override_reason TEXT DEFAULT ''")
        safe_add_column(cur, "attempts", "server_end_time TEXT DEFAULT NULL")

        # 4. Insert/Update default settings
        for k, v in DEFAULT_SETTINGS.items():
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
            if k in ('platform_name', 'app_name'):
                cur.execute("UPDATE settings SET value=? WHERE key=?", (v, k))

        con.commit()

        # 5. Verify integrity
        cur.execute("PRAGMA integrity_check;")
        check_result = cur.fetchone()[0]
        if check_result != 'ok':
            raise RuntimeError(f"Database integrity check failed: {check_result}")

        print("Integrity check passed successfully: ok")
        con.close()

        if is_shadow:
            shutil.copyfile(actual_path, target_path)

        print("Migration v31 completed successfully with zero data loss!")
        return True

    except Exception as exc:
        print(f"ERROR during migration: {exc}")
        con.rollback()
        con.close()
        if backup_file and backup_file.exists():
            print(f"Rolling back database from: {backup_file}")
            shutil.copyfile(backup_file, DB_PATH)
            if is_shadow and actual_path.exists():
                shutil.copyfile(backup_file, actual_path)
            print("Rollback complete.")
        raise

if __name__ == '__main__':
    run_migration()
