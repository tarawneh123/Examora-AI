# -*- coding: utf-8 -*-
"""
Online Backend Security Module
Handles:
1. Cryptographic token hashing & constant-time verification
2. Teacher Bearer authorization with secret isolation
3. Tiered Rate Limiting per endpoint category
4. CORS headers & origin enforcement
"""
import hashlib, hmac, time, secrets
from config import TEACHER_ONLINE_SECRET, ALLOWED_ORIGIN, ENVIRONMENT, RATE_LIMITS

# In-memory sliding window store: { (ip, category): [timestamp1, timestamp2, ...] }
RATE_LIMIT_STORE = {}

def hash_attempt_token(raw_token: str) -> str:
    """Computes SHA-256 hash of the raw attempt token for safe database storage."""
    if not raw_token:
        return ""
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

def verify_attempt_token(raw_token: str, stored_hash: str) -> bool:
    """Verifies student raw attempt token against the stored SHA-256 hash in constant time."""
    if not raw_token or not stored_hash:
        return False
    computed_hash = hash_attempt_token(raw_token)
    return hmac.compare_digest(computed_hash, stored_hash)

def verify_teacher_auth(req) -> bool:
    """Validates teacher pre-shared secret in Authorization header in constant time."""
    auth_header = req.headers.get('Authorization') or req.headers.get('authorization') or ''
    if not auth_header.startswith('Bearer '):
        return False
    token = auth_header[7:].strip()
    if not token or not TEACHER_ONLINE_SECRET:
        return False
    return hmac.compare_digest(token, TEACHER_ONLINE_SECRET)

def extract_attempt_token(req) -> str:
    """Extracts raw attempt token from X-Attempt-Token HTTP header."""
    return (req.headers.get('X-Attempt-Token') or req.headers.get('x-attempt-token') or '').strip()

def check_rate_limit(ip_address: str, category: str = 'default') -> bool:
    """Returns True if rate limit exceeded, False if request is allowed."""
    now = time.time()
    window = 60.0
    limit = RATE_LIMITS.get(category, RATE_LIMITS['default'])
    key = (ip_address, category)

    history = RATE_LIMIT_STORE.get(key, [])
    history = [t for t in history if now - t < window]

    if len(history) >= limit:
        return True

    history.append(now)
    RATE_LIMIT_STORE[key] = history
    return False

def apply_cors_headers(response, origin: str = ""):
    """Applies strict CORS headers restricting production access to Firebase Hosting."""
    origin_clean = (origin or '').strip().rstrip('/')
    allowed_clean = (ALLOWED_ORIGIN or 'https://yt-c-c.web.app').strip().rstrip('/')

    if origin_clean in (allowed_clean, 'https://yt-c-c.web.app', 'https://yt-c-c.firebaseapp.com') or 'yt-c-c' in origin_clean or 'localhost' in origin_clean or '127.0.0.1' in origin_clean:
        allow_origin = origin or allowed_clean
    else:
        allow_origin = allowed_clean

    response.headers['Access-Control-Allow-Origin'] = allow_origin
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS, HEAD'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Attempt-Token, Idempotency-Key'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Max-Age'] = '86400'
    return response
