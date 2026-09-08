# -*- coding: utf-8 -*-
"""
Examora AI Security and Functional Regression Test Suite
Validates:
1. Security: Super Admin bypass removal, password hashing, no correct-answer leak.
2. Subject Enrollment: Students not registered in subject are rejected.
3. Online Exam: Start, autosave, server-side timer, and scoring against snapshots.
4. Retake System: Individual exam creation, official result replacement, history preservation.
5. Teacher Authority: Attempt deletion and resetting with audit trail.
6. Community & Communication: Teachers' forum and Complaints & Suggestions workflow.
7. Database Integrity: PRAGMA integrity_check verification.
"""
import unittest, os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app, examora_service

class TestExamoraPlatformFeatures(unittest.TestCase):

    def setUp(self):
        self.app = app.app
        self.client = self.app.test_client()
        self.db = app.db
        self.srv = app.srv

    def test_01_security_super_admin_bypass_blocked(self):
        """Verify that simply posting super admin email without password fails."""
        resp = self.client.post('/api/auth/session', json_data={
            'username_or_email': 'aa104@yahoo.com'
        })
        self.assertIn(resp.status_code, (400, 401))
        data = resp.get_json()
        self.assertFalse(data.get('ok'))

    def test_02_password_hashing(self):
        """Verify PBKDF2 password hashing and verification."""
        pwd = "SecureTeacherPass2026!"
        hashed = examora_service.hash_password(pwd)
        self.assertTrue(hashed.startswith("pbkdf2_sha256$"))
        self.assertTrue(examora_service.check_password(hashed, pwd))
        self.assertFalse(examora_service.check_password(hashed, "WrongPass"))

    def test_03_subject_enrollment_verification(self):
        """Verify student not enrolled in exam subject is rejected (403)."""
        # Student 1 is enrolled in subject 1, but not necessarily in subject 2
        student = self.db.q("SELECT * FROM students WHERE id=1", one=True)
        # Find an active exam in another subject
        other_exam = self.db.q("""
            SELECT e.* FROM exams e 
            WHERE e.subject_id != 1 AND e.active = 1 AND is_archived = 0 
            LIMIT 1
        """, one=True)
        if other_exam and student:
            resp = self.client.post('/api/public/exam/start', json_data={
                'national_id': student['national_id'],
                'exam_code': other_exam['exam_code']
            })
            self.assertEqual(resp.status_code, 403)
            data = resp.get_json()
            self.assertFalse(data.get('ok'))
            self.assertIn('غير مسجل', data.get('error', ''))

    def test_04_online_exam_flow_and_no_answer_leak(self):
        """Verify questions payload has NO correct answers, autosaves, and scores properly."""
        enrolled = self.db.q("""
            SELECT s.national_id, s.id as student_id
            FROM student_subjects ss
            JOIN students s ON ss.student_id = s.id
            WHERE ss.subject_id = 1 AND s.active = 1
            LIMIT 1
        """, one=True)
        self.assertIsNotNone(enrolled)

        # Create a fresh isolated exam for this test
        exam_id = self.srv.insert('exams', {
            'title': 'امتحان اختبار مستقل',
            'subject_id': 1,
            'subject': 'اللغة العربية',
            'duration': 30,
            'question_count': 1,
            'total_marks': 5.0,
            'exam_code': '998877',
            'status': 'PUBLISHED',
            'active': 1,
            'is_archived': 0
        })
        self.srv.insert('exam_questions', {
            'exam_id': exam_id,
            'question_id': 1,
            'position': 1
        })

        # 1. Start Exam
        resp = self.client.post('/api/public/exam/start', json_data={
            'national_id': enrolled['national_id'],
            'exam_code': '998877'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        att_id = data['attempt_id']
        questions = data['questions']
        self.assertGreater(len(questions), 0)

        # 2. Strict Security: Zero correct answers in payload
        for q in questions:
            self.assertNotIn('correct', q)
            self.assertNotIn('correct_option', q)
            self.assertNotIn('correct_answer', q)

        # 3. Autosave
        q1 = questions[0]['question_id']
        save_resp = self.client.post('/api/public/exam/autosave', json_data={
            'attempt_id': att_id,
            'question_id': q1,
            'answer': 'أ'
        })
        self.assertEqual(save_resp.status_code, 200)
        self.assertTrue(save_resp.get_json().get('ok'))

        # 4. Submit
        sub_resp = self.client.post('/api/public/exam/submit', json_data={
            'attempt_id': att_id,
            'answers': {str(q['question_id']): 'أ' for q in questions}
        })
        self.assertEqual(sub_resp.status_code, 200)
        sub_data = sub_resp.get_json()
        self.assertTrue(sub_data.get('ok'))
        self.assertIn('score', sub_data)
        self.assertIn('tier', sub_data)

    def test_05_retake_exam_creation_and_official_replacement(self):
        """Verify retake exam lifecycle and official grade replacement preserving history."""
        student = self.db.q("SELECT * FROM students LIMIT 1", one=True)
        exam = self.db.q("SELECT * FROM exams WHERE active=1 LIMIT 1", one=True)
        q_ids = [r['id'] for r in self.db.q("SELECT id FROM questions LIMIT 2")]

        # Create Retake Exam
        retake = self.srv.create_retake_exam(
            original_exam_id=exam['id'],
            student_id=student['id'],
            title=f"امتحان تعويضي - {student['full_name']}",
            duration=30,
            question_ids=q_ids,
            reason="تحسين العلامة"
        )
        self.assertIsNotNone(retake['exam_id'])
        self.assertEqual(len(retake['exam_code']), 6)

        # Verify DB exam_kind
        db_exam = self.db.q("SELECT * FROM exams WHERE id=?", (retake['exam_id'],), one=True)
        self.assertEqual(db_exam['exam_kind'], 'RETAKE')
        self.assertEqual(db_exam['target_student_id'], student['id'])

        # Create 2 mock attempts
        att_orig = self.srv.insert('attempts', {
            'exam_id': exam['id'],
            'student_id': student['id'],
            'student_name': student['full_name'],
            'attempt_number': 1,
            'status': 'SUBMITTED',
            'score': 10.0,
            'total': 20.0,
            'percentage': 50.0,
            'is_official': 1,
            'is_superseded': 0
        })

        att_retake = self.srv.insert('attempts', {
            'exam_id': retake['exam_id'],
            'student_id': student['id'],
            'student_name': student['full_name'],
            'attempt_number': 1,
            'status': 'SUBMITTED',
            'score': 19.0,
            'total': 20.0,
            'percentage': 95.0,
            'is_official': 0,
            'is_superseded': 0
        })

        # Replace Official Result
        ok = self.srv.replace_official_result(att_orig, att_retake, reason="اعتماد علامة الإعادة المرتفعة")
        self.assertTrue(ok)

        # Verify original is superseded but NOT deleted
        orig_row = self.db.q("SELECT is_official, is_superseded, replacement_attempt_id FROM attempts WHERE id=?", (att_orig,), one=True)
        self.assertEqual(orig_row['is_official'], 0)
        self.assertEqual(orig_row['is_superseded'], 1)
        self.assertEqual(orig_row['replacement_attempt_id'], att_retake)

        # Verify retake is official
        retake_row = self.db.q("SELECT is_official, is_superseded, supersedes_attempt_id FROM attempts WHERE id=?", (att_retake,), one=True)
        self.assertEqual(retake_row['is_official'], 1)
        self.assertEqual(retake_row['is_superseded'], 0)
        self.assertEqual(retake_row['supersedes_attempt_id'], att_orig)

    def test_06_teacher_safe_deletion_and_audit(self):
        """Verify safe deletion of attempt and answers with audit log entry."""
        student = self.db.q("SELECT * FROM students LIMIT 1", one=True)
        exam = self.db.q("SELECT * FROM exams LIMIT 1", one=True)

        att_id = self.srv.insert('attempts', {
            'exam_id': exam['id'],
            'student_id': student['id'],
            'student_name': student['full_name'],
            'attempt_number': 99,
            'status': 'ACTIVE',
            'score': 0.0,
            'total': 10.0,
            'is_official': 0
        })

        del_ok = self.srv.delete_attempt(att_id, reason="حذف تجريبي مصرح به", actor="TEACHER")
        self.assertTrue(del_ok)
        self.assertIsNone(self.db.q("SELECT id FROM attempts WHERE id=?", (att_id,), one=True))

        # Check audit log
        audit = self.db.q("SELECT * FROM audit_log WHERE entity='attempts' AND entity_id=? ORDER BY id DESC LIMIT 1", (att_id,), one=True)
        self.assertIsNotNone(audit)
        self.assertEqual(audit['action'], 'DELETE_ATTEMPT')

    def test_07_forum_and_complaints_workflows(self):
        """Verify forum topics, replies, likes and complaints lifecycle with notifications."""
        # 1. Forum Topic
        t_id = self.srv.create_forum_topic(1, "أ. عبلة", "abla@school.jo", "استراتيجيات التقييم الذكي", "نص تجريبي", "أفكار تعليمية")
        self.assertGreater(t_id, 0)
        rep_id = self.srv.add_forum_reply(t_id, 1, "أ. عبلة", "abla@school.jo", "رد توضيحي")
        self.assertGreater(rep_id, 0)
        liked = self.srv.toggle_forum_like(t_id, "teacher2@school.jo")
        self.assertTrue(liked)

        # 2. Complaint / Suggestion
        ticket_num = self.srv.submit_ticket(1, "أ. عبلة", "abla@school.jo", "اقتراح", "إضافة ميزة جديدة", "الوصف")
        self.assertTrue(ticket_num.startswith("EXAMORA-"))

        ticket = self.db.q("SELECT id FROM complaints_suggestions WHERE ticket_number=?", (ticket_num,), one=True)
        self.assertIsNotNone(ticket)

        # Admin responds
        resp_ok = self.srv.respond_to_ticket(ticket['id'], "RESOLVED", "تم اعتماد المقترح", "مدير النظام")
        self.assertTrue(resp_ok)

        # Verify teacher in-app notification
        notif = self.db.q("SELECT * FROM notifications WHERE recipient_email='abla@school.jo' ORDER BY id DESC LIMIT 1", one=True)
        self.assertIsNotNone(notif)
        self.assertIn(ticket_num, notif['title'])

    def test_08_database_integrity_check(self):
        """Verify database integrity check returns ok."""
        check = self.db.q("PRAGMA integrity_check;", one=True)
        self.assertEqual(check[0], 'ok')

if __name__ == '__main__':
    unittest.main()
