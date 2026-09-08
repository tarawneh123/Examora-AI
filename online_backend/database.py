# -*- coding: utf-8 -*-
"""
Online Database Manager
Handles schema initialization and queries for the isolated online storage.
STRICT ISOLATION: Completely disconnected from local teacher database.
"""
import os, sqlite3, threading
from pathlib import Path
from config import DATABASE_URL, SQLITE_TEST_PATH, BASE_DIR

class OnlineDatabase:
    def __init__(self, db_url=None, sqlite_path=None):
        self.db_url = db_url if db_url is not None else DATABASE_URL
        self.sqlite_path = str(sqlite_path or SQLITE_TEST_PATH)
        self.lock = threading.Lock()
        
        # Enforce strict isolation
        if "exam_platform.db" in self.sqlite_path or "exam_platform.db" in str(self.db_url):
            raise PermissionError("[CRITICAL] Online Database cannot connect to local teacher database!")

        self.is_postgres = bool(self.db_url and (self.db_url.startswith("postgres://") or self.db_url.startswith("postgresql://")))
        self.init_schema()

    def get_connection(self):
        if self.is_postgres:
            import psycopg2
            import psycopg2.extras
            con = psycopg2.connect(self.db_url)
            return con
        else:
            con = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys = ON;")
            return con

    def init_schema(self):
        with self.lock:
            con = self.get_connection()
            cur = con.cursor()
            
            schema_file = BASE_DIR / 'online_migrations' / ('001_postgres_schema.sql' if self.is_postgres else '001_sqlite_test_schema.sql')
            if schema_file.exists():
                with open(schema_file, 'r', encoding='utf-8') as f:
                    schema_sql = f.read()
                if self.is_postgres:
                    cur.execute(schema_sql)
                else:
                    cur.executescript(schema_sql)

            if not self.is_postgres:
                cols = [r[1] for r in cur.execute("PRAGMA table_info(online_exams);").fetchall()]
                if 'idempotency_key' not in cols:
                    cur.execute("ALTER TABLE online_exams ADD COLUMN idempotency_key TEXT;")
                if 'exam_code' not in cols:
                    cur.execute("ALTER TABLE online_exams ADD COLUMN exam_code TEXT;")
            else:
                try:
                    cur.execute("ALTER TABLE online_exams ADD COLUMN IF NOT EXISTS exam_code VARCHAR(32);")
                    cur.execute("ALTER TABLE online_exams ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);")
                except Exception:
                    pass
            con.commit()
            con.close()

    def q(self, sql, params=(), one=False):
        con = self.get_connection()
        try:
            if self.is_postgres:
                import psycopg2.extras
                cur = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
                # Convert SQLite ? placeholders to %s for postgres if needed
                pg_sql = sql.replace('?', '%s')
                cur.execute(pg_sql, params)
                res = cur.fetchall()
                if one:
                    return dict(res[0]) if res else None
                return [dict(r) for r in res]
            else:
                cur = con.cursor()
                cur.execute(sql, params)
                res = cur.fetchall()
                if one:
                    return res[0] if res else None
                return res
        finally:
            con.close()

    def x(self, sql, params=()):
        with self.lock:
            con = self.get_connection()
            try:
                cur = con.cursor()
                if self.is_postgres:
                    pg_sql = sql.replace('?', '%s')
                    if pg_sql.strip().upper().startswith('INSERT INTO') and 'RETURNING' not in pg_sql.upper():
                        pg_sql += ' RETURNING id'
                        cur.execute(pg_sql, params)
                        con.commit()
                        row = cur.fetchone()
                        return row[0] if row else None
                    else:
                        cur.execute(pg_sql, params)
                        con.commit()
                        return None
                else:
                    cur.execute(sql, params)
                    con.commit()
                    return cur.lastrowid
            finally:
                con.close()

    def insert(self, table, data):
        keys = list(data.keys())
        ph = ', '.join(['?'] * len(keys))
        cols = ', '.join(keys)
        sql = f"INSERT INTO {table} ({cols}) VALUES ({ph})"
        return self.x(sql, list(data.values()))
