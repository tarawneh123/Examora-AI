# -*- coding: utf-8 -*-
"""
Examora AI - Standalone Online Cloud Backend API
Completely independent from the local teacher SQLite database.
"""
import os, sys, json, secrets, time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from wsgi_engine import OnlineApp as Flask, request, jsonify, Response
from config import TEACHER_ONLINE_SECRET, ALLOWED_ORIGIN, ENVIRONMENT, PORT, HOST
from database import OnlineDatabase
from security import (
    hash_attempt_token, verify_attempt_token, verify_teacher_auth,
    extract_attempt_token, check_rate_limit, apply_cors_headers
)
from scoring import evaluate_exam_submission

app = Flask(__name__)
db = OnlineDatabase()

# Global OPTIONS handler for CORS preflight
@app.route('/<path:dummy>', methods=['OPTIONS'])
def handle_options(dummy):
    req_origin = request.headers.get('Origin', '')
    res = Response('', status=200)
    return apply_cors_headers(res, req_origin)

@app.get('/health')
def health():
    req_origin = request.headers.get('Origin', '')
    res = jsonify({
        'ok': True,
        'service': 'Examora Online Cloud Backend',
        'version': '1.0.0',
        'database_type': 'PostgreSQL' if db.is_postgres else 'Isolated Test SQLite',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    return apply_cors_headers(res, req_origin)

# ==============================================================================
# TEACHER MANAGEMENT ENDPOINTS (Authenticated via Authorization: Bearer <KEY>)
# ==============================================================================

@app.post('/api/teacher/publish')
def teacher_publish():
    req_origin = request.headers.get('Origin', '')
    client_ip = request.remote_addr if hasattr(request, 'remote_addr') else '127.0.0.1'
    if check_rate_limit(client_ip, 'teacher'):
        res = jsonify({'ok': False, 'error': 'Rate limit exceeded'})
        res.status_code = 429
        return apply_cors_headers(res, req_origin)

    if not verify_teacher_auth(request):
        res = jsonify({'ok': False, 'error': 'غير مصرح لك بالوصول إلى لوحة إدارة النشر.'})
        res.status_code = 401
        return apply_cors_headers(res, req_origin)

    data = request.json or request.form
    if not isinstance(data, dict):
        res = jsonify({'ok': False, 'error': 'صيغة البيانات غير صحيحة.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    title = (data.get('title') or '').strip()
    subject = (data.get('subject') or '').strip()
    exam_code = str(data.get('exam_code') or '').strip()
    duration = int(data.get('duration') or 30)
    total_marks = float(data.get('total_marks') or 0.0)
    questions = data.get('questions') or []
    allowed_students = data.get('allowed_students') or []
    answer_key = data.get('answer_key') or {}

    if not title or not questions:
        res = jsonify({'ok': False, 'error': 'بيانات الامتحان أو الأسئلة غير مكتملة.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    # Sanitize questions: Guarantee 100% absence of correct answers in public questions payload
    sanitized_questions = []
    for idx, q in enumerate(questions, start=1):
        sanitized_questions.append({
            'id': q.get('id') or idx,
            'number': q.get('number') or idx,
            'text': q.get('text') or q.get('question') or '',
            'options': q.get('options') or {
                'أ': q.get('option_a', ''),
                'ب': q.get('option_b', ''),
                'ج': q.get('option_c', ''),
                'د': q.get('option_d', '')
            },
            'mark': float(q.get('mark') or 1.0)
        })

    idempotency_key = (request.headers.get('Idempotency-Key') or data.get('idempotency_key') or '').strip()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Check for existing exam with this idempotency key to prevent accidental duplicate publishing
    if idempotency_key:
        existing = db.q("SELECT * FROM online_exams WHERE idempotency_key=?", (idempotency_key,), one=True)
        if existing:
            token = existing['publish_token']
            
            # Count existing student attempts (ACTIVE or SUBMITTED)
            att_count = db.q("SELECT COUNT(*) as n FROM online_attempts WHERE publish_token=?", (token,), one=True)['n']
            
            incoming_questions_json = json.dumps(sanitized_questions, ensure_ascii=False)
            incoming_keys_json = json.dumps(answer_key, ensure_ascii=False)
            
            # Retrieve currently stored answer key
            cur_key_row = db.q("SELECT keys_json FROM online_answer_keys WHERE publish_token=?", (token,), one=True)
            cur_keys_json = cur_key_row['keys_json'] if cur_key_row else '{}'
            
            # Check if content (questions or answer key) is being modified
            content_modified = (incoming_questions_json != existing['questions_json'] or incoming_keys_json != cur_keys_json)
            
            # SECURITY GATE: Reject modification if student attempts already exist to prevent corrupting active/submitted attempts
            if att_count > 0 and content_modified:
                res = jsonify({
                    'ok': False,
                    'error': 'لا يمكن تعديل محتوى الامتحان أو مفتاح الإجابة لوجود محاولات طلاب قائمة أو مسلمة مسبقاً على هذا الامتحان. يرجى استخدام رمز أو نشر جديد للامتحان المعدل.',
                    'conflict': True
                })
                res.status_code = 409
                return apply_cors_headers(res, req_origin)

            # If no student attempts exist yet, allow in-place updates of questions & answer keys
            if att_count == 0:
                db.x("""
                    UPDATE online_exams 
                    SET status='ACTIVE', closed_at=NULL, title=?, subject=?, duration=?, total_marks=?, questions_json=?, allowed_students_json=?
                    WHERE id=?
                """, (title, subject, duration, total_marks, incoming_questions_json, json.dumps(allowed_students, ensure_ascii=False), existing['id']))

                db.x("""
                    UPDATE online_answer_keys 
                    SET keys_json=?
                    WHERE publish_token=?
                """, (incoming_keys_json, token))
            else:
                db.x("UPDATE online_exams SET status='ACTIVE', closed_at=NULL WHERE id=?", (existing['id'],))

            web_link = f"https://yt-c-c.web.app/#/e/{token}"
            res = jsonify({
                'ok': True,
                'publish_token': token,
                'web_link': web_link,
                'title': title,
                'published_at': str(existing['created_at']) if existing['created_at'] else now_str,
                'reused': True
            })
            return apply_cors_headers(res, req_origin)

    # Cryptographically secure unguessable publish token
    publish_token = secrets.token_urlsafe(24)

    # Atomic insertion: Exam in online_exams, private answer key in online_answer_keys
    db.insert('online_exams', {
        'publish_token': publish_token,
        'idempotency_key': idempotency_key if idempotency_key else None,
        'exam_code': exam_code if exam_code else None,
        'title': title,
        'subject': subject,
        'duration': duration,
        'total_marks': total_marks,
        'status': 'ACTIVE',
        'questions_json': json.dumps(sanitized_questions, ensure_ascii=False),
        'allowed_students_json': json.dumps(allowed_students, ensure_ascii=False),
        'created_at': now_str
    })

    db.insert('online_answer_keys', {
        'publish_token': publish_token,
        'keys_json': json.dumps(answer_key, ensure_ascii=False),
        'created_at': now_str
    })

    web_link = f"https://yt-c-c.web.app/#/e/{publish_token}"
    res = jsonify({
        'ok': True,
        'publish_token': publish_token,
        'web_link': web_link,
        'title': title,
        'published_at': now_str,
        'reused': False
    })
    return apply_cors_headers(res, req_origin)

@app.post('/api/teacher/exams/<token>/close')
def teacher_close(token):
    req_origin = request.headers.get('Origin', '')
    if not verify_teacher_auth(request):
        res = jsonify({'ok': False, 'error': 'غير مصرح.'})
        res.status_code = 401
        return apply_cors_headers(res, req_origin)

    exam = db.q("SELECT * FROM online_exams WHERE publish_token=?", (token,), one=True)
    if not exam:
        res = jsonify({'ok': False, 'error': 'الامتحان غير موجود.'})
        res.status_code = 404
        return apply_cors_headers(res, req_origin)

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.x("UPDATE online_exams SET status='CLOSED', closed_at=? WHERE publish_token=?", (now_str, token))
    res = jsonify({'ok': True, 'status': 'CLOSED', 'closed_at': now_str})
    return apply_cors_headers(res, req_origin)

@app.get('/api/teacher/exams/<token>/attempts')
def teacher_get_attempts(token):
    req_origin = request.headers.get('Origin', '')
    if not verify_teacher_auth(request):
        res = jsonify({'ok': False, 'error': 'غير مصرح.'})
        res.status_code = 401
        return apply_cors_headers(res, req_origin)

    exam = db.q("SELECT * FROM online_exams WHERE publish_token=?", (token,), one=True)
    if not exam:
        res = jsonify({'ok': False, 'error': 'الامتحان غير موجود.'})
        res.status_code = 404
        return apply_cors_headers(res, req_origin)

    # Fetch submitted attempts
    attempts = db.q("SELECT * FROM online_attempts WHERE publish_token=? AND status='SUBMITTED'", (token,))
    results = []
    for att in attempts:
        ans_rows = db.q("SELECT question_id, answer, answered_at FROM online_answers WHERE attempt_id=?", (att['id'],))
        answers_map = {str(r['question_id']): r['answer'] for r in ans_rows}
        results.append({
            'online_attempt_id': att['id'], # For idempotent sync
            'student_national_id': att['student_national_id'],
            'student_name': att['student_name'],
            'score': float(att['score']),
            'total': float(att['total']),
            'percentage': float(att['percentage']),
            'tier': att['tier'],
            'started_at': str(att['started_at']) if att['started_at'] else '',
            'finished_at': str(att['finished_at']) if att['finished_at'] else '',
            'is_synced': bool(att['is_synced']),
            'answers': answers_map
        })

    res = jsonify({
        'ok': True,
        'publish_token': token,
        'total_attempts': len(results),
        'attempts': results
    })
    return apply_cors_headers(res, req_origin)

@app.post('/api/teacher/exams/<token>/mark-synced')
def teacher_mark_synced(token):
    req_origin = request.headers.get('Origin', '')
    if not verify_teacher_auth(request):
        res = jsonify({'ok': False, 'error': 'غير مصرح.'})
        res.status_code = 401
        return apply_cors_headers(res, req_origin)

    data = request.json or request.form
    attempt_ids = data.get('attempt_ids') or []
    if not attempt_ids:
        # Mark all submitted for this exam
        db.x("UPDATE online_attempts SET is_synced=1 WHERE publish_token=? AND status='SUBMITTED'", (token,))
    else:
        for aid in attempt_ids:
            db.x("UPDATE online_attempts SET is_synced=1 WHERE id=? AND publish_token=?", (aid, token))

    res = jsonify({'ok': True, 'message': 'تم تحديث حالة المزامنة بنجاح.'})
    return apply_cors_headers(res, req_origin)

@app.route('/api/teacher/exams/<token>', methods=['DELETE'])
def teacher_purge(token):
    req_origin = request.headers.get('Origin', '')
    if not verify_teacher_auth(request):
        res = jsonify({'ok': False, 'error': 'غير مصرح.'})
        res.status_code = 401
        return apply_cors_headers(res, req_origin)

    exam = db.q("SELECT * FROM online_exams WHERE publish_token=?", (token,), one=True)
    if not exam:
        # Idempotent response: if already purged, return success
        res = jsonify({'ok': True, 'message': 'الامتحان غير موجود أو تم حذفه مسبقاً من السحابة.', 'already_purged': True})
        return apply_cors_headers(res, req_origin)

    # GATEKEEPER 0: Reject purge if exam is still ACTIVE (must be CLOSED first)
    if exam['status'] != 'CLOSED':
        res = jsonify({'ok': False, 'error': 'لا يمكن حذف الامتحان المنشور وهو لا يزال متاحاً (ACTIVE). يجب إغلاق الامتحان أولاً.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    # GATEKEEPER 1: Reject purge if any attempts are currently ACTIVE
    active_count = db.q("SELECT COUNT(*) as n FROM online_attempts WHERE publish_token=? AND status='ACTIVE'", (token,), one=True)['n']
    if active_count > 0:
        res = jsonify({
            'ok': False,
            'error': f'لا يمكن حذف الامتحان لوجود ({active_count}) محاولات نشطة قيد التقديم حالياً. يرجى إغلاق الامتحان أولاً.'
        })
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    # GATEKEEPER 2: Reject purge if any SUBMITTED attempts have NOT been synced
    unsynced_count = db.q("SELECT COUNT(*) as n FROM online_attempts WHERE publish_token=? AND status='SUBMITTED' AND is_synced=0", (token,), one=True)['n']
    if unsynced_count > 0:
        res = jsonify({
            'ok': False,
            'error': f'لا يمكن حذف الامتحان لوجود ({unsynced_count}) نتائج مقدمة لم تتم مزامنتها محلياً بعد. قم بتنفيذ المزامنة أولاً.'
        })
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    # Safe Cascade Delete
    att_rows = db.q("SELECT id FROM online_attempts WHERE publish_token=?", (token,))
    for a in att_rows:
        db.x("DELETE FROM online_answers WHERE attempt_id=?", (a['id'],))
    db.x("DELETE FROM online_attempts WHERE publish_token=?", (token,))
    db.x("DELETE FROM online_answer_keys WHERE publish_token=?", (token,))
    db.x("DELETE FROM online_exams WHERE publish_token=?", (token,))

    res = jsonify({'ok': True, 'message': 'تم حذف الامتحان المنشور وبياناته السحابية المؤقتة نهائياً بعد التحقق من اكتمال المزامنة.'})
    return apply_cors_headers(res, req_origin)

# ==============================================================================
# PUBLIC STUDENT ENDPOINTS (Accessible over the Internet)
# ==============================================================================

@app.post('/api/public/exam/start')
def student_start():
    req_origin = request.headers.get('Origin', '')
    client_ip = request.remote_addr if hasattr(request, 'remote_addr') else '127.0.0.1'
    if check_rate_limit(client_ip, 'start'):
        res = jsonify({'ok': False, 'error': 'تم تجاوز معدل الطلبات المسموح به. يرجى الانتظار دقيقة واحدة.'})
        res.status_code = 429
        return apply_cors_headers(res, req_origin)

    # Strictly reject if someone mistakenly passes a teacher authorization header here
    if request.headers.get('Authorization'):
        res = jsonify({'ok': False, 'error': 'هذا المسار مخصص للطلاب فقط.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    data = request.json or request.form
    if not isinstance(data, dict):
        res = jsonify({'ok': False, 'error': 'طلب غير صالح.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    national_id = (data.get('national_id') or '').strip()
    publish_token = (data.get('publish_token') or data.get('code') or '').strip()

    if not national_id or not publish_token:
        res = jsonify({'ok': False, 'error': 'يرجى إدخال الرقم الوطني ورمز الامتحان.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    exam = db.q("SELECT * FROM online_exams WHERE (publish_token=? OR exam_code=?) AND status='ACTIVE' ORDER BY id DESC LIMIT 1", (publish_token, publish_token), one=True)
    if not exam or exam['status'] != 'ACTIVE':
        res = jsonify({'ok': False, 'error': 'عذراً، هذا الامتحان غير متاح حالياً أو تم إغلاقه.'})
        res.status_code = 404
        return apply_cors_headers(res, req_origin)
    publish_token = exam['publish_token']

    allowed_students = json.loads(exam['allowed_students_json'] or '[]')
    if allowed_students and national_id not in allowed_students:
        res = jsonify({'ok': False, 'error': 'عذراً، هذا الرقم الوطني غير مسجل في قائمة الطلاب المصرح لهم بتقديم هذا الامتحان.'})
        res.status_code = 403
        return apply_cors_headers(res, req_origin)

    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # Check for submitted attempt
    prev_sub = db.q("""
        SELECT * FROM online_attempts 
        WHERE publish_token=? AND student_national_id=? AND status='SUBMITTED'
        ORDER BY id DESC LIMIT 1
    """, (publish_token, national_id), one=True)
    if prev_sub:
        res = jsonify({'ok': False, 'error': 'لقد قمت بتقديم هذا الامتحان مسبقاً وتم اعتماد إجاباتك. لا يُسمح بإعادة التقديم.'})
        res.status_code = 403
        return apply_cors_headers(res, req_origin)

    # Check for active attempt (Resume)
    active_att = db.q("""
        SELECT * FROM online_attempts 
        WHERE publish_token=? AND student_national_id=? AND status='ACTIVE'
        ORDER BY id DESC LIMIT 1
    """, (publish_token, national_id), one=True)

    if active_att:
        deadline = active_att['server_deadline']
        if isinstance(deadline, str):
            deadline = datetime.strptime(deadline[:19], '%Y-%m-%d %H:%M:%S')
        elif hasattr(deadline, 'tzinfo') and deadline.tzinfo is not None:
            deadline = deadline.replace(tzinfo=None)
        remaining_secs = int((deadline - now).total_seconds())
        if remaining_secs <= 0:
            db.x("UPDATE online_attempts SET status='EXPIRED', finished_at=? WHERE id=?", (now_str, active_att['id']))
            res = jsonify({'ok': False, 'error': 'انتهى الوقت المخصص للامتحان رسمياً.'})
            res.status_code = 403
            return apply_cors_headers(res, req_origin)

        # Generate fresh raw token, update hash
        fresh_raw_token = secrets.token_urlsafe(32)
        fresh_hash = hash_attempt_token(fresh_raw_token)
        db.x("UPDATE online_attempts SET attempt_token_hash=? WHERE id=?", (fresh_hash, active_att['id']))

        ans_rows = db.q("SELECT question_id, answer FROM online_answers WHERE attempt_id=?", (active_att['id'],))
        saved_answers = {str(r['question_id']): r['answer'] for r in ans_rows}

        res = jsonify({
            'ok': True,
            'is_resumed': True,
            'attempt_id': active_att['id'],
            'attempt_token': fresh_raw_token,
            'remaining_seconds': remaining_secs,
            'exam': {
                'title': exam['title'],
                'subject': exam['subject'],
                'duration': exam['duration'],
                'total_marks': float(exam['total_marks'])
            },
            'student': {
                'national_id': national_id,
                'name': active_att['student_name']
            },
            'questions': json.loads(exam['questions_json']),
            'answers': saved_answers
        })
        return apply_cors_headers(res, req_origin)

    # Create new attempt
    duration_mins = int(exam['duration'])
    server_deadline = (now + timedelta(minutes=duration_mins)).strftime('%Y-%m-%d %H:%M:%S')
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_attempt_token(raw_token)

    att_id = db.insert('online_attempts', {
        'publish_token': publish_token,
        'student_national_id': national_id,
        'student_name': f"طالب ({national_id})",
        'attempt_token_hash': token_hash,
        'status': 'ACTIVE',
        'score': 0.0,
        'total': float(exam['total_marks']),
        'percentage': 0.0,
        'started_at': now_str,
        'server_deadline': server_deadline,
        'is_synced': 0
    })

    res = jsonify({
        'ok': True,
        'is_resumed': False,
        'attempt_id': att_id,
        'attempt_token': raw_token, # Sent ONCE to student browser
        'remaining_seconds': duration_mins * 60,
        'exam': {
            'title': exam['title'],
            'subject': exam['subject'],
            'duration': exam['duration'],
            'total_marks': float(exam['total_marks'])
        },
        'student': {
            'national_id': national_id,
            'name': f"طالب ({national_id})"
        },
        'questions': json.loads(exam['questions_json']),
        'answers': {}
    })
    return apply_cors_headers(res, req_origin)

@app.post('/api/public/exam/autosave')
def student_autosave():
    req_origin = request.headers.get('Origin', '')
    client_ip = request.remote_addr if hasattr(request, 'remote_addr') else '127.0.0.1'
    if check_rate_limit(client_ip, 'autosave'):
        res = jsonify({'ok': False, 'error': 'Spam detected'})
        res.status_code = 429
        return apply_cors_headers(res, req_origin)

    raw_token = extract_attempt_token(request)
    data = request.json or request.form
    if not isinstance(data, dict):
        res = jsonify({'ok': False, 'error': 'طلب غير صالح.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    attempt_id = data.get('attempt_id')
    question_id = data.get('question_id')
    answer = str(data.get('answer') or '').strip()

    if not attempt_id or not raw_token or not question_id or not answer:
        res = jsonify({'ok': False, 'error': 'بيانات الحفظ غير مكتملة أو غياب رمز المحاولة.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    # ANTI-IDOR & OWNERSHIP CHECK: Constant-time hash verification
    attempt = db.q("SELECT * FROM online_attempts WHERE id=?", (attempt_id,), one=True)
    if not attempt or not verify_attempt_token(raw_token, attempt['attempt_token_hash']):
        res = jsonify({'ok': False, 'error': 'غير مصرح بالوصول إلى هذه المحاولة.'})
        res.status_code = 403
        return apply_cors_headers(res, req_origin)

    if attempt['status'] != 'ACTIVE':
        res = jsonify({'ok': False, 'error': 'هذه المحاولة غير نشطة.'})
        res.status_code = 403
        return apply_cors_headers(res, req_origin)

    # Server deadline check (with strict 15-second network buffer)
    now = datetime.now()
    deadline = attempt['server_deadline']
    if isinstance(deadline, str):
        deadline = datetime.strptime(deadline[:19], '%Y-%m-%d %H:%M:%S')
    elif hasattr(deadline, 'tzinfo') and deadline.tzinfo is not None:
        deadline = deadline.replace(tzinfo=None)
    if (deadline - now).total_seconds() < -15:
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
        db.x("UPDATE online_attempts SET status='EXPIRED', finished_at=? WHERE id=?", (now_str, attempt_id))
        res = jsonify({'ok': False, 'error': 'انتهى الوقت المخصص للامتحان رسمياً.'})
        res.status_code = 403
        return apply_cors_headers(res, req_origin)

    # Validate option character
    if answer not in ('أ', 'ب', 'ج', 'د', 'A', 'B', 'C', 'D'):
        res = jsonify({'ok': False, 'error': 'الخيار المحدد غير صالح.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # Upsert answer (Idempotent: prevents duplicate answers per question)
    existing = db.q("SELECT id FROM online_answers WHERE attempt_id=? AND question_id=?", (attempt_id, question_id), one=True)
    if existing:
        db.x("UPDATE online_answers SET answer=?, answered_at=? WHERE id=?", (answer, now_str, existing['id']))
    else:
        db.insert('online_answers', {
            'attempt_id': attempt_id,
            'question_id': question_id,
            'answer': answer,
            'answered_at': now_str
        })

    res = jsonify({'ok': True, 'saved_at': now_str})
    return apply_cors_headers(res, req_origin)

@app.post('/api/public/exam/submit')
def student_submit():
    req_origin = request.headers.get('Origin', '')
    client_ip = request.remote_addr if hasattr(request, 'remote_addr') else '127.0.0.1'
    if check_rate_limit(client_ip, 'submit'):
        res = jsonify({'ok': False, 'error': 'Spam detected'})
        res.status_code = 429
        return apply_cors_headers(res, req_origin)

    raw_token = extract_attempt_token(request)
    data = request.json or request.form
    if not isinstance(data, dict):
        res = jsonify({'ok': False, 'error': 'طلب غير صالح.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    attempt_id = data.get('attempt_id')
    submitted_answers = data.get('answers') or {}

    if not attempt_id or not raw_token:
        res = jsonify({'ok': False, 'error': 'معرف المحاولة ورمز الجلسة مطلوبان.'})
        res.status_code = 400
        return apply_cors_headers(res, req_origin)

    # ANTI-IDOR & OWNERSHIP CHECK
    attempt = db.q("SELECT * FROM online_attempts WHERE id=?", (attempt_id,), one=True)
    if not attempt or not verify_attempt_token(raw_token, attempt['attempt_token_hash']):
        res = jsonify({'ok': False, 'error': 'غير مصرح بالوصول إلى هذه المحاولة.'})
        res.status_code = 403
        return apply_cors_headers(res, req_origin)

    if attempt['status'] != 'ACTIVE':
        res = jsonify({'ok': False, 'error': 'تم تسليم هذه المحاولة مسبقاً.'})
        res.status_code = 403
        return apply_cors_headers(res, req_origin)

    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # Save any final answers sent in submit payload
    for qid_str, ans_val in submitted_answers.items():
        ans_clean = str(ans_val).strip()
        if ans_clean in ('أ', 'ب', 'ج', 'د', 'A', 'B', 'C', 'D'):
            existing = db.q("SELECT id FROM online_answers WHERE attempt_id=? AND question_id=?", (attempt_id, qid_str), one=True)
            if existing:
                db.x("UPDATE online_answers SET answer=?, answered_at=? WHERE id=?", (ans_clean, now_str, existing['id']))
            else:
                db.insert('online_answers', {
                    'attempt_id': attempt_id,
                    'question_id': qid_str,
                    'answer': ans_clean,
                    'answered_at': now_str
                })

    # Fetch private answer key from online_answer_keys (ZERO client-side trust)
    key_row = db.q("SELECT keys_json FROM online_answer_keys WHERE publish_token=?", (attempt['publish_token'],), one=True)
    answer_key = json.loads(key_row['keys_json'] or '{}') if key_row else {}

    # Compile all saved student answers
    all_ans_rows = db.q("SELECT question_id, answer FROM online_answers WHERE attempt_id=?", (attempt_id,))
    answers_map = {str(r['question_id']): r['answer'] for r in all_ans_rows}

    # Strict Server-Side Evaluation (Any client-sent score or marks are completely ignored)
    evaluation = evaluate_exam_submission(answers_map, answer_key)

    # Lock attempt as SUBMITTED
    db.x("""
        UPDATE online_attempts 
        SET status='SUBMITTED', score=?, total=?, percentage=?, tier=?, feedback_message=?, finished_at=?
        WHERE id=?
    """, (evaluation['score'], evaluation['total'], evaluation['percentage'], evaluation['tier'], evaluation['feedback_message'], now_str, attempt_id))

    res = jsonify({
        'ok': True,
        'score': evaluation['score'],
        'total': evaluation['total'],
        'percentage': evaluation['percentage'],
        'tier': evaluation['tier'],
        'feedback_message': evaluation['feedback_message']
    })
    return apply_cors_headers(res, req_origin)

if __name__ == '__main__':
    print(f"Examora AI Online Cloud Backend running on {HOST}:{PORT}")
    app.run(host=HOST, port=PORT)
