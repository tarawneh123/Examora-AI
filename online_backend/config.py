# -*- coding: utf-8 -*-
"""
Online Backend Configuration for Examora AI
Supports environment variable overrides for production deployment.
STRICT ISOLATION: Must NEVER point to or touch exam_data/exam_platform.db
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Database configuration
DATABASE_URL = os.environ.get('DATABASE_URL', '')
SQLITE_TEST_PATH = os.environ.get('SQLITE_TEST_PATH', '/tmp/examora_online_isolated_test.db')

# Strict isolation check
if 'exam_platform.db' in DATABASE_URL or 'exam_platform.db' in str(SQLITE_TEST_PATH):
    raise RuntimeError("[SECURITY ERROR] Online Backend is strictly forbidden from connecting to exam_platform.db!")

# Teacher Pre-Shared Authentication Secret (Server-Side Environment Variable)
TEACHER_ONLINE_SECRET = os.environ.get('TEACHER_ONLINE_SECRET', 'examora-cloud-secret-token-prod-2026')

# CORS policy
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production').lower()
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', 'https://yt-c-c.web.app')

# Tiered Rate Limiting (Requests per minute per IP)
RATE_LIMITS = {
    'start': int(os.environ.get('RATE_LIMIT_START', 30)),
    'autosave': int(os.environ.get('RATE_LIMIT_AUTOSAVE', 180)),
    'submit': int(os.environ.get('RATE_LIMIT_SUBMIT', 15)),
    'teacher': int(os.environ.get('RATE_LIMIT_TEACHER', 60)),
    'default': 60
}

PORT = int(os.environ.get('PORT', 8080))
HOST = os.environ.get('HOST', '0.0.0.0')
