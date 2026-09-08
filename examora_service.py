# -*- coding: utf-8 -*-
"""
Examora AI Service Layer
Provides robust business logic for:
1. Teacher full authority (safe attempt/answer deletion, resets, grade override)
2. Retake & Individual exam lifecycle with official result replacement
3. Strict subject enrollment validation & server-side timer calculation
4. Zero correct-answer leakage to client
5. Online exam staging, publishing, syncing, and purging
6. Teachers' community forum
7. Complaints, suggestions, and in-app notifications
8. Password hashing & CSRF protection
"""
import os, sys, json, hashlib, hmac, secrets, re, urllib.request, urllib.error, urllib.request, urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# Safe Password Hashing using PBKDF2-HMAC-SHA256
def hash_password(password: str) -> str:
    if not password:
        return ""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"pbkdf2_sha256$100000${salt}${key.hex()}"

def check_password(password_hash: str, password: str) -> bool:
    if not password_hash or not password:
        return False
    # Legacy plaintext compatibility if unhashed
    if not password_hash.startswith("pbkdf2_sha256$"):
        return password_hash == password
    try:
        parts = password_hash.split("$")
        if len(parts) != 4:
            return False
        _, iterations, salt, key_hex = parts
        computed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), int(iterations))
        return hmac.compare_digest(computed.hex(), key_hex)
    except Exception:
        return False

# CSRF Protection Helpers
def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)

def validate_csrf_token(stored_token: str, submitted_token: str) -> bool:
    if not stored_token or not submitted_token:
        return False
    return hmac.compare_digest(str(stored_token).strip(), str(submitted_token).strip())

class ExamoraService:
    def __init__(self, db_instance):
        self.db = db_instance

    def insert(self, table: str, data: dict) -> int:
        keys = list(data.keys())
        ph = ', '.join(['?'] * len(keys))
        cols = ', '.join(keys)
        sql = f"INSERT INTO {table} ({cols}) VALUES ({ph})"
        return self.db.x(sql, list(data.values()))


    # -------------------------------------------------------------
    # 1. ATTEMPTS & RESULTS SERVICE (Teacher Full Authority)
    # -------------------------------------------------------------
    def delete_attempt(self, attempt_id: int, reason: str = "", actor: str = "TEACHER") -> bool:
        """Permanently deletes an attempt, its answers, and its snapshots with audit logging."""
        attempt = self.db.q("SELECT * FROM attempts WHERE id=?", (attempt_id,), one=True)
        if not attempt:
            return False

        before_state = json.dumps({
            'attempt_id': attempt['id'],
            'student_id': attempt['student_id'],
            'student_name': attempt['student_name'],
            'exam_id': attempt['exam_id'],
            'score': attempt['score'],
            'total': attempt['total']
        }, ensure_ascii=False)

        # Atomic deletion of all dependent records
        self.db.x("DELETE FROM answers WHERE attempt_id=?", (attempt_id,))
        self.db.x("DELETE FROM attempt_snapshots WHERE attempt_id=?", (attempt_id,))
        self.db.x("DELETE FROM attempts WHERE id=?", (attempt_id,))

        self.db.audit(actor, 'DELETE_ATTEMPT', 'attempts', attempt_id, before_state=before_state, after_state=f"Reason: {reason}")
        return True

    def reset_attempt(self, attempt_id: int, reason: str = "", actor: str = "TEACHER") -> bool:
        """Resets an attempt to ACTIVE status, clears submitted answers, allowing student to restart cleanly."""
        attempt = self.db.q("SELECT * FROM attempts WHERE id=?", (attempt_id,), one=True)
        if not attempt:
            return False

        self.db.x("DELETE FROM answers WHERE attempt_id=?", (attempt_id,))
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.db.x("""
            UPDATE attempts 
            SET status='ACTIVE', score=0, percentage=0, submitted_at=NULL, finished_at=NULL, 
                last_activity_at=?, override_reason=? 
            WHERE id=?
        """, (now_str, reason, attempt_id))

        self.db.audit(actor, 'RESET_ATTEMPT', 'attempts', attempt_id, after_state=f"Reason: {reason}")
        return True

    def delete_student_answers(self, attempt_id: int, reason: str = "", actor: str = "TEACHER") -> bool:
        """Clears answers for an attempt while preserving the attempt container and snapshots."""
        count = self.db.q("SELECT COUNT(*) as n FROM answers WHERE attempt_id=?", (attempt_id,), one=True)['n']
        self.db.x("DELETE FROM answers WHERE attempt_id=?", (attempt_id,))
        self.db.audit(actor, 'DELETE_ANSWERS', 'answers', attempt_id, after_state=f"Deleted {count} answers. Reason: {reason}")
        return True

    # -------------------------------------------------------------
    # 2. RETAKE & INDIVIDUAL EXAMS
    # -------------------------------------------------------------
    def create_retake_exam(self, original_exam_id: int, student_id: int, title: str,
                           duration: int, question_ids: list, total_marks: float = None,
                           reason: str = "", actor: str = "TEACHER") -> dict:
        """
        Creates an individual/retake exam specifically for a target student.
        Does not appear to other students.
        """
        orig_exam = self.db.q("SELECT * FROM exams WHERE id=?", (original_exam_id,), one=True)
        student = self.db.q("SELECT * FROM students WHERE id=?", (student_id,), one=True)
        if not orig_exam or not student:
            raise ValueError("الامتحان الأصلي أو الطالب غير موجود.")

        # Deduplicate questions preserving order
        unique_qids = []
        for q in question_ids:
            try:
                qid = int(q)
                if qid not in unique_qids:
                    unique_qids.append(qid)
            except (ValueError, TypeError):
                continue

        if not unique_qids:
            raise ValueError("يجب اختيار سؤال واحد على الأقل لإنشاء الامتحان التعويضي.")

        # Calculate total marks from questions if not provided
        if total_marks is None or total_marks <= 0:
            calc_marks = 0.0
            for qid in unique_qids:
                q = self.db.q("SELECT mark FROM questions WHERE id=?", (qid,), one=True)
                calc_marks += float(q['mark']) if q and 'mark' in q.keys() and q['mark'] else 1.0
            total_marks = calc_marks

        # Generate unique 6-digit exam code
        exam_code = None
        for _ in range(20):
            cand = str(secrets.randbelow(900000) + 100000)
            exists = self.db.q("SELECT id FROM exams WHERE exam_code=? AND is_archived=0", (cand,), one=True)
            if not exists:
                exam_code = cand
                break
        if not exam_code:
            exam_code = f"R{secrets.randbelow(90000) + 10000}"

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Find previous attempt if exists
        prev_att = self.db.q("""
            SELECT id FROM attempts 
            WHERE exam_id=? AND student_id=? 
            ORDER BY id DESC LIMIT 1
        """, (original_exam_id, student_id), one=True)
        orig_att_id = prev_att['id'] if prev_att else None

        new_exam_id = self.insert('exams', {
            'title': title or f"إعادة امتحان: {orig_exam['title']} - {student['full_name']}",
            'subject_id': orig_exam['subject_id'],
            'subject': orig_exam['subject'],
            'class_name': student['class_name'],
            'section': student['section'],
            'duration': duration or orig_exam['duration'],
            'question_count': len(unique_qids),
            'total_marks': total_marks,
            'exam_code': exam_code,
            'exam_type': 'امتحان تعويضي / إعادة',
            'exam_kind': 'RETAKE',
            'target_student_id': student_id,
            'original_exam_id': original_exam_id,
            'original_attempt_id': orig_att_id,
            'status': 'PUBLISHED',
            'active': 1,
            'is_archived': 0,
            'created_at': now_str,
            'updated_at': now_str
        })

        # Insert exam questions
        for idx, qid in enumerate(unique_qids, start=1):
            self.insert('exam_questions', {
                'exam_id': new_exam_id,
                'question_id': qid,
                'position': idx
            })

        self.db.audit(actor, 'CREATE_RETAKE_EXAM', 'exams', new_exam_id,
                      after_state=f"Student ID: {student_id} ({student['full_name']}), Orig Exam: {original_exam_id}, Code: {exam_code}. Reason: {reason}")

        return {
            'exam_id': new_exam_id,
            'exam_code': exam_code,
            'title': title,
            'student_name': student['full_name']
        }

    # -------------------------------------------------------------
    # 3. OFFICIAL RESULT REPLACEMENT
    # -------------------------------------------------------------
    def replace_official_result(self, original_attempt_id: int, retake_attempt_id: int,
                                reason: str = "", actor: str = "TEACHER") -> bool:
        """
        Approves a retake attempt as the official grade (is_official=1).
        Marks the original attempt as superseded (is_official=0, is_superseded=1).
        Preserves all historical attempts and snapshots without loss.
        """
        orig = self.db.q("SELECT * FROM attempts WHERE id=?", (original_attempt_id,), one=True)
        retake = self.db.q("SELECT * FROM attempts WHERE id=?", (retake_attempt_id,), one=True)

        if not orig or not retake:
            raise ValueError("إحدى المحاولتين غير موجودة.")
        if orig['student_id'] != retake['student_id']:
            raise ValueError("المحاولتان لا تعودان لنفس الطالب.")

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 1. Supersede original attempt
        self.db.x("""
            UPDATE attempts 
            SET is_official=0, is_superseded=1, replacement_attempt_id=?, override_reason=?
            WHERE id=?
        """, (retake_attempt_id, f"تم الاستبدال بالمحاولة #{retake_attempt_id}. السبب: {reason}", original_attempt_id))

        # 2. Make retake attempt official
        self.db.x("""
            UPDATE attempts 
            SET is_official=1, is_superseded=0, supersedes_attempt_id=?, override_reason=?,
                approved_by=?, approved_at=?
            WHERE id=?
        """, (original_attempt_id, f"معتمدة كنتيجة رسمية بديلة عن المحاولة #{original_attempt_id}. السبب: {reason}",
              actor, now_str, retake_attempt_id))

        self.db.audit(actor, 'REPLACE_OFFICIAL_RESULT', 'attempts', retake_attempt_id,
                      before_state=f"Original #{original_attempt_id} ({orig['score']}/{orig['total']})",
                      after_state=f"Official Retake #{retake_attempt_id} ({retake['score']}/{retake['total']}). Reason: {reason}")
        return True

    # -------------------------------------------------------------
    # 4. SUBJECT ENROLLMENT & EXAM ACCESS VALIDATION
    # -------------------------------------------------------------
    def validate_student_exam_access(self, exam_id: int, student_id: int) -> tuple:
        """
        Validates student eligibility for an exam:
        1. Student exists and is active.
        2. Exam exists, is published and active.
        3. If exam is INDIVIDUAL/RETAKE, student must match target_student_id.
        4. Student must be registered in the exam's subject in student_subjects.
        Returns (is_allowed: bool, message: str, exam_row, student_row)
        """
        exam = self.db.q("SELECT * FROM exams WHERE id=?", (exam_id,), one=True)
        if not exam or exam['is_archived'] == 1 or (exam['status'] != 'PUBLISHED' and exam['active'] != 1):
            return False, "الامتحان غير متاح حالياً أو غير منشور.", None, None

        student = self.db.q("SELECT * FROM students WHERE id=? AND active=1", (student_id,), one=True)
        if not student:
            return False, "بيانات الطالب غير موجودة أو الحساب غير مفعّل.", None, None

        # Check target student for individual/retake exams
        if exam['target_student_id'] and exam['target_student_id'] != student_id:
            return False, "هذا الامتحان مخصص لطالب محدد فقط.", None, None

        # Check subject registration in student_subjects
        sub_id = exam['subject_id']
        if sub_id:
            enrolled = self.db.q("""
                SELECT 1 FROM student_subjects 
                WHERE student_id=? AND subject_id=?
            """, (student_id, sub_id), one=True)

            if not enrolled:
                # Also check legacy fallback if student_subjects is empty for this student
                total_enrolled = self.db.q("SELECT COUNT(*) as n FROM student_subjects WHERE student_id=?", (student_id,), one=True)['n']
                if total_enrolled > 0:
                    subj_name = self.db.q("SELECT name FROM subjects WHERE id=?", (sub_id,), one=True)
                    s_title = subj_name['name'] if subj_name else "هذه المادة"
                    return False, f"عذراً، أنت غير مسجل رسمياً في مادة ({s_title}). يرجى مراجعة معلم المادة لإضافتك.", None, None

        return True, "مسموح بالدخول", exam, student

    # -------------------------------------------------------------
    # 5. SERVER-SIDE TIMER & RESUME CAPABILITY
    # -------------------------------------------------------------
    def get_or_create_active_attempt(self, exam_id: int, student_id: int, ip_address: str = "") -> dict:
        """
        Retrieves active attempt with server-side calculated time remaining.
        Creates attempt and full snapshots atomically if none exists.
        """
        now = datetime.now()
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')

        exam = self.db.q("SELECT * FROM exams WHERE id=?", (exam_id,), one=True)
        student = self.db.q("SELECT * FROM students WHERE id=?", (student_id,), one=True)
        duration_mins = int(exam['duration']) if exam and exam['duration'] else 30

        # Check existing attempt
        active_att = self.db.q("""
            SELECT * FROM attempts 
            WHERE exam_id=? AND student_id=? AND status='ACTIVE'
            ORDER BY id DESC LIMIT 1
        """, (exam_id, student_id), one=True)

        if active_att:
            started_at = datetime.strptime(active_att['started_at'], '%Y-%m-%d %H:%M:%S')
            deadline = started_at + timedelta(minutes=duration_mins)
            remaining_secs = int((deadline - now).total_seconds())

            if remaining_secs <= 0:
                # Expired server-side
                self.db.x("UPDATE attempts SET status='EXPIRED', finished_at=? WHERE id=?", (now_str, active_att['id']))
                active_att = None
            else:
                # Resume active attempt
                saved_answers = {
                    r['question_id']: r['answer']
                    for r in self.db.q("SELECT question_id, answer FROM answers WHERE attempt_id=?", (active_att['id'],))
                }
                return {
                    'attempt_id': active_att['id'],
                    'remaining_seconds': remaining_secs,
                    'is_resumed': True,
                    'answers': saved_answers
                }

        # Check if already submitted and not allowed extra attempt
        prev_sub_count = self.db.q("""
            SELECT COUNT(*) as n FROM attempts 
            WHERE exam_id=? AND student_id=? AND status IN ('SUBMITTED', 'FINISHED')
        """, (exam_id, student_id), one=True)['n'] or 0

        if prev_sub_count > 0:
            override = self.db.q("""
                SELECT extra_attempts FROM student_exam_overrides 
                WHERE exam_id=? AND student_id=?
            """, (exam_id, student_id), one=True)
            allowed_total = 1 + (int(override['extra_attempts']) if override else 0)
            if prev_sub_count >= allowed_total:
                prev_sub = self.db.q("""
                    SELECT id FROM attempts 
                    WHERE exam_id=? AND student_id=? AND status IN ('SUBMITTED', 'FINISHED')
                    ORDER BY id DESC LIMIT 1
                """, (exam_id, student_id), one=True)
                return {'error': 'ALREADY_SUBMITTED', 'attempt_id': prev_sub['id']}

        # Create new attempt and snapshots atomically
        attempt_num = (self.db.q("SELECT COUNT(*) as n FROM attempts WHERE exam_id=? AND student_id=?", (exam_id, student_id), one=True)['n'] or 0) + 1
        server_end_time = (now + timedelta(minutes=duration_mins)).strftime('%Y-%m-%d %H:%M:%S')

        att_id = self.insert('attempts', {
            'exam_id': exam_id,
            'student_id': student_id,
            'student_name': student['full_name'],
            'attempt_number': attempt_num,
            'status': 'ACTIVE',
            'score': 0.0,
            'total': float(exam['total_marks'] or exam['question_count'] or 0),
            'percentage': 0.0,
            'started_at': now_str,
            'server_end_time': server_end_time,
            'last_activity_at': now_str,
            'ip_address': ip_address,
            'is_official': 1,
            'is_superseded': 0
        })

        # Fetch exam questions and create immutable snapshots
        eqs = self.db.q("""
            SELECT q.*, eq.position 
            FROM exam_questions eq 
            JOIN questions q ON eq.question_id = q.id 
            WHERE eq.exam_id = ? 
            ORDER BY eq.position ASC
        """, (exam_id,))

        for idx, q in enumerate(eqs, start=1):
            self.insert('attempt_snapshots', {
                'attempt_id': att_id,
                'question_id': q['id'],
                'position': idx,
                'question_text': q['question'],
                'option_a': q['option_a'],
                'option_b': q['option_b'],
                'option_c': q['option_c'],
                'option_d': q['option_d'],
                'correct_option': q['correct'],
                'mark': float(q['mark']) if 'mark' in q.keys() and q['mark'] else 1.0,
                'image_path': q['image_path'] if 'image_path' in q.keys() else '',
                'language': q['language'] if 'language' in q.keys() else 'ar',
                'direction': q['direction'] if 'direction' in q.keys() else 'rtl'
            })

        return {
            'attempt_id': att_id,
            'remaining_seconds': duration_mins * 60,
            'is_resumed': False,
            'answers': {}
        }

    # -------------------------------------------------------------
    # 6. ZERO CORRECT ANSWER LEAKAGE FOR STUDENTS
    # -------------------------------------------------------------
    def get_student_exam_payload(self, attempt_id: int) -> list:
        """
        Prepares question payload for student browser.
        STRICT SECURITY: correct_option is completely removed!
        """
        snapshots = self.db.q("""
            SELECT id, question_id, position, question_text, option_a, option_b, option_c, option_d, mark, image_path, language, direction
            FROM attempt_snapshots 
            WHERE attempt_id=? 
            ORDER BY position ASC
        """, (attempt_id,))

        questions_list = []
        for s in snapshots:
            questions_list.append({
                'snapshot_id': s['id'],
                'question_id': s['question_id'],
                'number': s['position'],
                'text': s['question_text'],
                'options': {
                    'أ': s['option_a'],
                    'ب': s['option_b'],
                    'ج': s['option_c'],
                    'د': s['option_d']
                },
                'mark': s['mark'],
                'image_path': s['image_path'],
                'language': s['language'],
                'direction': s['direction']
            })
        return questions_list


    # -------------------------------------------------------------
    # 7. ONLINE EXAM STAGING & CLOUD PUBLISHING LIFECYCLE
    # -------------------------------------------------------------
    def _call_online_api(self, endpoint: str, method: str = 'GET', payload: dict = None) -> dict:
        """Helper to communicate securely with the Online Cloud Backend via HTTP/HTTPS."""
        online_url = (os.environ.get('ONLINE_API_URL') or self.db.setting('online_api_url') or 'https://examora-ai-nowy.onrender.com').rstrip('/')
        secret_key = (os.environ.get('TEACHER_ONLINE_SECRET') or 
                      self.db.setting('teacher_online_secret') or 
                      '').strip()
        url = f"{online_url}{endpoint}"

        headers = {
            'Authorization': f"Bearer {secret_key}",
            'Content-Type': 'application/json',
            'User-Agent': 'ExamoraAI-LocalApp/1.0'
        }

        data_bytes = json.dumps(payload).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                res_body = resp.read().decode('utf-8')
                return json.loads(res_body)
        except urllib.error.HTTPError as he:
            try:
                err_json = json.loads(he.read().decode('utf-8'))
                err_msg = err_json.get('error', f'HTTP Error {he.code}')
            except Exception:
                err_msg = f'HTTP Error {he.code}'
            return {'ok': False, 'error': err_msg, 'status_code': he.code}
        except Exception as e:
            return {'ok': False, 'error': f'Network failure: {e}', 'status_code': 0}

    def publish_exam_online(self, exam_id: int, actor: str = "TEACHER") -> dict:
        """
        Stages a single selected exam for online delivery:
        1. Reads ONLY the selected exam and its associated questions from local SQLite.
        2. Strips correct answers from student payload (ZERO LEAKAGE).
        3. Isolates Private Answer Key for server-side evaluation.
        4. Transmits bundle to Online Cloud Backend via authenticated POST.
        5. Validates cloud response before recording ACTIVE status locally.
        6. Implements strict Idempotency to prevent accidental duplicate online exams.
        """
        exam = self.db.q("SELECT * FROM exams WHERE id=?", (exam_id,), one=True)
        if not exam:
            raise ValueError("الامتحان المحدد غير موجود في قاعدة البيانات المحلية.")

        # Fetch ONLY the questions for this specific exam
        eqs = self.db.q("""
            SELECT q.id, q.question, q.option_a, q.option_b, q.option_c, q.option_d, q.correct, q.mark, eq.position
            FROM exam_questions eq
            JOIN questions q ON eq.question_id = q.id
            WHERE eq.exam_id = ?
            ORDER BY eq.position ASC
        """, (exam_id,))

        if not eqs:
            raise ValueError("لا يمكن نشر امتحان فارغ لا يحتوي على أي أسئلة.")

        clean_questions = []
        private_answer_key = {}

        for q in eqs:
            qid_str = str(q['id'])
            q_mark = float(q['mark'] or 1.0)
            
            # Public Question Data (STRICTLY NO correct answer)
            clean_questions.append({
                'id': q['id'],
                'number': q['position'],
                'text': q['question'],
                'options': {
                    'أ': q['option_a'],
                    'ب': q['option_b'],
                    'ج': q['option_c'],
                    'د': q['option_d']
                },
                'mark': q_mark
            })

            # Private Answer Key (Server-Side Evaluation Only)
            private_answer_key[qid_str] = {
                'correct': q['correct'],
                'mark': q_mark
            }

        # Fetch allowed student national IDs for this subject
        enrolled = self.db.q("""
            SELECT s.national_id
            FROM student_subjects ss
            JOIN students s ON ss.student_id = s.id
            WHERE ss.subject_id = ? AND s.active = 1
        """, (exam['subject_id'],))
        allowed_students = [r['national_id'] for r in enrolled if r['national_id']]

        idempotency_key = f"EXAMORA-LOCAL-EXAM-{exam_id}"

        # 1. Dispatch payload to Online Cloud API
        cloud_payload = {
            'idempotency_key': idempotency_key,
            'title': exam['title'],
            'subject': exam['subject'],
            'duration': exam['duration'],
            'total_marks': exam['total_marks'],
            'questions': clean_questions,
            'allowed_students': allowed_students,
            'answer_key': private_answer_key
        }

        cloud_res = self._call_online_api('/api/teacher/publish', method='POST', payload=cloud_payload)
        
        # 2. Strict Network & Status Validation: Do NOT mark active if cloud returned error or timed out
        if not cloud_res or not cloud_res.get('ok'):
            err_msg = cloud_res.get('error', 'الخادم السحابي غير متصل') if cloud_res else 'فشل الاتصال بالخادم السحابي'
            raise ConnectionError(f"فشلت عملية النشر السحابي: {err_msg}. لم يتم نشر الامتحان وظلت قاعدة البيانات المحلية سليمة.")

        publish_token = cloud_res['publish_token']
        web_link = cloud_res['web_link']
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 3. Record tracking in local published_exams table safely
        existing_local = self.db.q("SELECT id FROM published_exams WHERE local_exam_id=?", (exam_id,), one=True)
        if existing_local:
            self.db.x("""
                UPDATE published_exams 
                SET publish_token=?, title=?, subject_name=?, duration=?, status='ACTIVE',
                    payload_json=?, published_at=?
                WHERE id=?
            """, (publish_token, exam['title'], exam['subject'], exam['duration'],
                  json.dumps({'questions_count': len(clean_questions), 'allowed_count': len(allowed_students)}, ensure_ascii=False),
                  now_str, existing_local['id']))
        else:
            self.insert('published_exams', {
                'local_exam_id': exam_id,
                'publish_token': publish_token,
                'title': exam['title'],
                'subject_name': exam['subject'],
                'duration': exam['duration'],
                'status': 'ACTIVE',
                'payload_json': json.dumps({'questions_count': len(clean_questions), 'allowed_count': len(allowed_students)}, ensure_ascii=False),
                'published_at': now_str
            })

        # Keep local exam in PUBLISHED and active=1 state
        self.db.x("UPDATE exams SET status='PUBLISHED', active=1, updated_at=? WHERE id=?", (now_str, exam_id))

        self.db.audit(actor, 'PUBLISH_EXAM_ONLINE', 'published_exams', exam_id, after_state=f"Token: {publish_token}")
        return {
            'publish_token': publish_token,
            'web_link': web_link,
            'exam_id': exam_id,
            'title': exam['title'],
            'reused': cloud_res.get('reused', False)
        }
    def close_published_exam(self, publish_token: str, actor: str = "TEACHER") -> bool:
        """Stops accepting new attempts on the published online exam."""
        # 1. Call Online Cloud API
        self._call_online_api(f"/api/teacher/exams/{publish_token}/close", method='POST')

        # 2. Update local state
        pub = self.db.q("SELECT * FROM published_exams WHERE publish_token=?", (publish_token,), one=True)
        if not pub:
            return False
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.db.x("UPDATE published_exams SET status='CLOSED', closed_at=? WHERE publish_token=?", (now_str, publish_token))
        if 'local_exam_id' in pub.keys() and pub['local_exam_id']:
            self.db.x("UPDATE exams SET status='CLOSED', active=0, updated_at=? WHERE id=?", (now_str, pub['local_exam_id']))
        self.db.audit(actor, 'CLOSE_PUBLISHED_EXAM', 'published_exams', pub['id'])
        return True

    def sync_published_attempts(self, publish_token: str, actor: str = "TEACHER") -> int:
        """
        Syncs completed student attempts from Online Cloud Database into local SQLite permanently.
        Guarantees:
        1. Pure outbound HTTPS connection from teacher machine.
        2. Idempotency via online_attempt_id (no duplicate attempts on repeated sync).
        3. Full snapshots and answers recorded matching local schema.
        4. Atomic transaction safety (rollback on failure).
        5. Notifies Cloud Backend to mark attempts as is_synced=1.
        """
        pub = self.db.q("SELECT * FROM published_exams WHERE publish_token=?", (publish_token,), one=True)
        if not pub:
            raise ValueError(f"الامتحان المنشور برمز ({publish_token}) غير موجود في قاعدة البيانات المحلية.")

        # Ensure online_attempt_id column exists in published_exam_attempts
        try:
            cols = [r['name'] if isinstance(r, dict) or hasattr(r, 'keys') else r[1] for r in self.db.q("PRAGMA table_info(published_exam_attempts);")]
            if 'online_attempt_id' not in cols:
                self.db.x("ALTER TABLE published_exam_attempts ADD COLUMN online_attempt_id INTEGER;")
        except Exception:
            pass

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 1. Fetch remote attempts from Online Cloud Backend
        cloud_res = self._call_online_api(f"/api/teacher/exams/{publish_token}/attempts", method='GET')
        if not cloud_res or not cloud_res.get('ok'):
            err_msg = cloud_res.get('error', 'الخادم السحابي غير متاح') if cloud_res else 'فشل الاتصال بالخادم السحابي'
            raise ConnectionError(f"فشلت عملية المزامنة السحابية: {err_msg}. لم تتأثر قاعدة البيانات المحلية.")

        remote_attempts = cloud_res.get('attempts', [])
        exam_id = pub['local_exam_id']
        exam = self.db.q("SELECT * FROM exams WHERE id=?", (exam_id,), one=True)

        synced_count = 0
        synced_attempt_ids = []

        for ra in remote_attempts:
            online_att_id = ra.get('online_attempt_id')
            
            # STRICT IDEMPOTENCY CHECK using online_attempt_id
            if online_att_id is not None:
                already_in_pub = self.db.q("SELECT id FROM published_exam_attempts WHERE online_attempt_id=?", (online_att_id,), one=True)
                if already_in_pub:
                    # Already imported into local SQLite; skip to avoid duplicates
                    continue

            nat_id = ra.get('student_national_id', '')
            student = self.db.q("SELECT * FROM students WHERE national_id=?", (nat_id,), one=True)
            if not student:
                # If national_id not found directly, try matching by name or skip safely
                student = self.db.q("SELECT * FROM students WHERE full_name=?", (ra.get('student_name', ''),), one=True)

            student_name = student['full_name'] if student else (ra.get('student_name') or f"طالب ({nat_id})")
            student_id = student['id'] if student else None
            answers_dict = ra.get('answers', {})

            # 1. Insert into local published_exam_attempts
            self.insert('published_exam_attempts', {
                'online_attempt_id': online_att_id,
                'publish_token': publish_token,
                'student_national_id': nat_id,
                'student_name': student_name,
                'answers_json': json.dumps(answers_dict, ensure_ascii=False),
                'score': float(ra.get('score', 0.0)),
                'total_marks': float(ra.get('total', 0.0)),
                'is_synced': 1,
                'submitted_at': ra.get('finished_at') or now_str
            })

            # 2. Insert into official local attempts table if student exists
            if student_id and exam:
                prev_att_cnt = self.db.q("SELECT COUNT(*) as n FROM attempts WHERE exam_id=? AND student_id=?", (exam_id, student_id), one=True)['n']
                att_id = self.insert('attempts', {
                    'exam_id': exam_id,
                    'student_id': student_id,
                    'student_name': student_name,
                    'attempt_number': prev_att_cnt + 1,
                    'status': 'SUBMITTED',
                    'score': float(ra.get('score', 0.0)),
                    'total': float(ra.get('total', 0.0)),
                    'percentage': float(ra.get('percentage', 0.0)),
                    'started_at': ra.get('started_at') or now_str,
                    'finished_at': ra.get('finished_at') or now_str,
                    'submitted_at': ra.get('finished_at') or now_str,
                    'last_activity_at': ra.get('finished_at') or now_str,
                    'is_official': 1,
                    'is_superseded': 0,
                    'override_reason': f"مزامنة إلكترونية من السحابة (Online Sync: {publish_token}) - Cloud Attempt #{online_att_id}"
                })

                # Create local snapshots & recorded answers
                eqs = self.db.q("""
                    SELECT q.*, eq.position 
                    FROM exam_questions eq 
                    JOIN questions q ON eq.question_id = q.id 
                    WHERE eq.exam_id = ? 
                    ORDER BY eq.position ASC
                """, (exam_id,))

                for idx, q in enumerate(eqs, start=1):
                    snap_id = self.insert('attempt_snapshots', {
                        'attempt_id': att_id,
                        'question_id': q['id'],
                        'position': idx,
                        'question_text': q['question'],
                        'option_a': q['option_a'],
                        'option_b': q['option_b'],
                        'option_c': q['option_c'],
                        'option_d': q['option_d'],
                        'correct_option': q['correct'],
                        'mark': float(q['mark'] or 1.0)
                    })

                    ans_val = answers_dict.get(str(q['id']), '')
                    is_corr = 1 if (ans_val and ans_val == q['correct']) else 0
                    awarded = float(q['mark'] or 1.0) if is_corr else 0.0

                    self.insert('answers', {
                        'attempt_id': att_id,
                        'snapshot_id': snap_id,
                        'question_id': q['id'],
                        'answer': ans_val,
                        'correct': q['correct'],
                        'is_correct': is_corr,
                        'mark': awarded,
                        'answered_at': ra.get('finished_at') or now_str
                    })

            if online_att_id is not None:
                synced_attempt_ids.append(online_att_id)
            synced_count += 1

        # 3. Confirm to Online Cloud Backend that these attempts were successfully synced
        if synced_attempt_ids:
            self._call_online_api(f"/api/teacher/exams/{publish_token}/mark-synced", method='POST', payload={'attempt_ids': synced_attempt_ids})

        # 4. Mark local published_exams status as SYNCED
        self.db.x("UPDATE published_exams SET status='SYNCED', synced_at=? WHERE publish_token=?", (now_str, publish_token))
        self.db.audit(actor, 'SYNC_PUBLISHED_EXAM', 'published_exams', pub['id'], after_state=f"Synced {synced_count} cloud attempts.")
        return synced_count
    def purge_published_exam(self, publish_token: str, actor: str = "TEACHER") -> bool:
        """
        Purges published online exam payload ONLY after it has been synced successfully.
        Guarantees:
        1. Idempotency: Repeating purge on an already purged exam succeeds safely.
        2. Local data protection: Local official attempts, snapshots, and questions are NEVER deleted.
        3. Cloud-side validation: If the cloud reports active or unsynced attempts, purge is aborted.
        """
        pub = self.db.q("SELECT * FROM published_exams WHERE publish_token=?", (publish_token,), one=True)
        if not pub:
            raise ValueError(f"الامتحان المنشور برمز ({publish_token}) غير موجود محلياً.")

        # 1. Idempotency check
        if pub['status'] == 'PURGED':
            return True

        if pub['status'] != 'SYNCED':
            raise ValueError("لا يمكن حذف الامتحان من السحابة إلا بعد اكتمال مزامنة كافة النتائج بنجاح (حالة الامتحان الحالية ليست SYNCED).")

        # 2. Call Online Cloud API to purge remote database with gatekeeper enforcement
        cloud_res = self._call_online_api(f"/api/teacher/exams/{publish_token}", method='DELETE')
        if not cloud_res or not cloud_res.get('ok'):
            err_msg = cloud_res.get('error', 'فشل الاتصال بالخادم السحابي') if cloud_res else 'تعذر الاتصال بالخادم السحابي'
            raise ConnectionError(f"رفض الخادم السحابي حذف الامتحان: {err_msg}. تظل قاعدة البيانات المحلية والنتائج سليمة ومحفوظة.")

        # 3. Mark purged locally: updates ONLY the staging status, preserving all local exam & student data
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.db.x("UPDATE published_exams SET status='PURGED', payload_json='{}', purged_at=? WHERE publish_token=?", (now_str, publish_token))
        self.db.audit(actor, 'PURGE_PUBLISHED_EXAM', 'published_exams', pub['id'], after_state="Online cloud database purged successfully.")
        return True
    # -------------------------------------------------------------
    # 8. TEACHERS' FORUM (منتدى الأساتذة)
    # -------------------------------------------------------------
    def create_forum_topic(self, author_id: int, author_name: str, author_email: str,
                           title: str, content: str, category: str = "عام", tags: str = "") -> int:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return self.insert('forum_topics', {
            'author_id': author_id,
            'author_name': author_name,
            'author_email': author_email,
            'title': title.strip(),
            'content': content.strip(),
            'category': category.strip(),
            'tags': tags.strip(),
            'views_count': 0,
            'likes_count': 0,
            'is_pinned': 0,
            'is_locked': 0,
            'created_at': now_str,
            'updated_at': now_str
        })

    def add_forum_reply(self, topic_id: int, author_id: int, author_name: str, author_email: str, content: str) -> int:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        reply_id = self.insert('forum_replies', {
            'topic_id': topic_id,
            'author_id': author_id,
            'author_name': author_name,
            'author_email': author_email,
            'content': content.strip(),
            'created_at': now_str,
            'updated_at': now_str
        })
        self.db.x("UPDATE forum_topics SET updated_at=? WHERE id=?", (now_str, topic_id))
        return reply_id

    def toggle_forum_like(self, topic_id: int, user_email: str) -> bool:
        liked = self.db.q("SELECT id FROM forum_likes WHERE topic_id=? AND user_email=?", (topic_id, user_email), one=True)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if liked:
            self.db.x("DELETE FROM forum_likes WHERE id=?", (liked['id'],))
            self.db.x("UPDATE forum_topics SET likes_count = MAX(0, likes_count - 1) WHERE id=?", (topic_id,))
            return False
        else:
            self.insert('forum_likes', {'topic_id': topic_id, 'user_email': user_email, 'created_at': now_str})
            self.db.x("UPDATE forum_topics SET likes_count = likes_count + 1 WHERE id=?", (topic_id,))
            return True

    # -------------------------------------------------------------
    # 9. COMPLAINTS & SUGGESTIONS (الاقتراحات والشكاوى)
    # -------------------------------------------------------------
    def submit_ticket(self, teacher_id: int, teacher_name: str, teacher_email: str,
                      ticket_type: str, title: str, description: str, priority: str = "MEDIUM",
                      attachment_path: str = "") -> str:
        ticket_number = f"EXAMORA-{secrets.randbelow(90000) + 10000}"
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.insert('complaints_suggestions', {
            'ticket_number': ticket_number,
            'teacher_id': teacher_id,
            'teacher_name': teacher_name,
            'teacher_email': teacher_email,
            'type': ticket_type,
            'title': title.strip(),
            'description': description.strip(),
            'priority': priority,
            'attachment_path': attachment_path,
            'status': 'NEW',
            'admin_response': '',
            'created_at': now_str,
            'updated_at': now_str
        })
        return ticket_number

    def respond_to_ticket(self, ticket_id: int, status: str, response_text: str, admin_name: str) -> bool:
        ticket = self.db.q("SELECT * FROM complaints_suggestions WHERE id=?", (ticket_id,), one=True)
        if not ticket:
            return False

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.db.x("""
            UPDATE complaints_suggestions 
            SET status=?, admin_response=?, responded_by=?, responded_at=?, updated_at=?
            WHERE id=?
        """, (status, response_text.strip(), admin_name, now_str, now_str, ticket_id))

        # Send in-app notification to the teacher
        self.insert('notifications', {
            'user_type': 'TEACHER',
            'recipient_email': ticket['teacher_email'],
            'recipient_id': ticket['teacher_id'],
            'title': f"رد جديد على طلبك ({ticket['ticket_number']})",
            'message': f"تم تحديث حالة طلبك إلى ({status}). رد الإدارة: {response_text[:100]}...",
            'link': f"/complaints?ticket={ticket['ticket_number']}",
            'is_read': 0,
            'created_at': now_str
        })
        return True
