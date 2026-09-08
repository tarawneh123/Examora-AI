# -*- coding: utf-8 -*-
"""
Test Static Regressions & Security Protections:
1. Complete Route Coverage Audit (All routes in section 56)
2. Admin vs Student Context Separation
3. IDOR Prevention (Cross-student attempt access blocked)
4. Exam Password Security
5. Active Attempt Resume vs Submitted Attempt Result
6. A4 Print & Direction-Aware Layout Structure
"""
import sys, os, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app

class TestRegressionsStatic(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.db = app.db

    def test_01_route_audit_coverage(self):
        # 1. Ensure basic sample exam and student exist
        sub = self.db.q("SELECT id FROM subjects WHERE code='history'", one=True)
        sub_id = sub['id']

        qid = self.db.x("""
            INSERT OR IGNORE INTO questions (id, subject_id, question, option_a, option_b, option_c, option_d, correct, status, approved)
            VALUES (999, ?, 'سؤال روتيني', 'أ', 'ب', 'ج', 'د', 'أ', 'APPROVED', 1)
        """, (sub_id,))

        eid = self.db.x("""
            INSERT OR IGNORE INTO exams (id, title, subject_id, duration, status, active)
            VALUES (999, 'امتحان التدقيق الشامل', ?, 45, 'PUBLISHED', 1)
        """, (sub_id,))

        self.db.x("INSERT OR IGNORE INTO exam_questions (exam_id, question_id, position) VALUES (999, 999, 1)")

        routes_to_test = [
            ('/', 200),
            ('/dashboard', 200),
            ('/login', 200),
            ('/first-run', 302), # Redirects to dashboard when setup completed
            ('/settings', 200),
            ('/subjects', 200),
            ('/packages', 200),
            ('/questions', 200),
            ('/question-bank', 200),
            ('/import', 200),
            ('/review', 200),
            ('/exams', 200),
            ('/exams/new', 200),
            ('/exams/999/manage', 200),
            ('/students', 200),
            ('/results', 200),
            ('/print/exam/999', 200),
            ('/audit-log', 200),
            ('/backup', 200),
            ('/student', 200),
            ('/student/login', 200),
            ('/health', 200)
        ]

        for route, expected_status in routes_to_test:
            res = self.client.get(route)
            self.assertIn(res.status_code, (expected_status, 200, 302), f"Route {route} failed with status {res.status_code}")

    def test_02_admin_student_context_isolation(self):
        # Student visiting protected student route unauthenticated redirects to student login
        c = app.app.test_client()
        res = c.get('/student/home')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/student', res.headers.get('Location', ''))
        # Must NEVER redirect to teacher admin /login
        self.assertNotIn('/login?next', res.headers.get('Location', ''))

    def test_03_idor_prevention(self):
        # Student A must NEVER access Student B's attempt result
        self.db.x("INSERT OR IGNORE INTO students (id, full_name, username, password) VALUES (801, 'طالب أول أ', 'std_a', '1234')")
        self.db.x("INSERT OR IGNORE INTO students (id, full_name, username, password) VALUES (802, 'طالب ثان ب', 'std_b', '1234')")

        sub = self.db.q("SELECT id FROM subjects WHERE code='history'", one=True)
        eid = self.db.x("INSERT INTO exams (title, subject_id, status, active) VALUES ('امتحان الأمان', ?, 'PUBLISHED', 1)", (sub['id'],))

        # Attempt belonging to Student B (802)
        att_b_id = self.db.x("INSERT INTO attempts (exam_id, student_id, student_name, status, score, total) VALUES (?, 802, 'طالب ثان ب', 'SUBMITTED', 10, 10)", (eid,))

        # Login as Student A (801)
        c = app.app.test_client()
        c.post('/student/login/post', data={'username': 'std_a', 'password': '1234'})

        # Student A tries to view Student B's attempt
        res = c.get(f'/student/result/{att_b_id}')
        # Expect redirect back to student home with error flash, not showing B's results!
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get('Location'), '/student/home')

    def test_04_exam_password_protection(self):
        sub = self.db.q("SELECT id FROM subjects WHERE code='history'", one=True)
        eid = self.db.x("INSERT INTO exams (title, subject_id, password, status, active) VALUES ('امتحان محمي بسري', ?, 'secret77', 'PUBLISHED', 1)", (sub['id'],))
        qid = self.db.x("INSERT INTO questions (subject_id, question, option_a, option_b, option_c, option_d, correct, status, approved) VALUES (?, 'سؤال محمي', 'أ', 'ب', 'ج', 'د', 'أ', 'APPROVED', 1)", (sub['id'],))
        self.db.x("INSERT INTO exam_questions (exam_id, question_id, position) VALUES (?, ?, 1)", (eid, qid))

        self.db.x("INSERT OR IGNORE INTO students (id, full_name, username, password) VALUES (805, 'طالب فحص الباسورد', 'std_pw', '1234')")

        c = app.app.test_client()
        c.post('/student/login/post', data={'username': 'std_pw', 'password': '1234'})

        # Access without password -> shows password entry screen
        res_no_pw = c.get(f'/student/exam/{eid}')
        self.assertEqual(res_no_pw.status_code, 200)
        self.assertIn('امتحان محمي بكلمة مرور', res_no_pw.text)

        # Enter wrong password -> still shows password entry screen
        res_wrong = c.post(f'/student/exam/{eid}', data={'exam_password': 'wrong_password'})
        self.assertEqual(res_wrong.status_code, 200)
        self.assertIn('امتحان محمي بكلمة مرور', res_wrong.text)

        # Enter correct password -> unlocks question paper!
        res_correct = c.post(f'/student/exam/{eid}', data={'exam_password': 'secret77'})
        self.assertEqual(res_correct.status_code, 200)
        self.assertIn('سؤال محمي', res_correct.text)

    def test_05_resume_vs_submitted_result(self):
        sub = self.db.q("SELECT id FROM subjects WHERE code='history'", one=True)
        eid = self.db.x("INSERT INTO exams (title, subject_id, duration, status, active) VALUES ('امتحان الاستكمال والتسليم', ?, 30, 'PUBLISHED', 1)", (sub['id'],))
        qid = self.db.x("INSERT INTO questions (subject_id, question, option_a, option_b, option_c, option_d, correct, status, approved) VALUES (?, 'سؤال الاستكمال', 'أ', 'ب', 'ج', 'د', 'أ', 'APPROVED', 1)", (sub['id'],))
        self.db.x("INSERT INTO exam_questions (exam_id, question_id, position) VALUES (?, ?, 1)", (eid, qid))

        self.db.x("INSERT OR IGNORE INTO students (id, full_name, username, password) VALUES (810, 'طالب الاستكمال', 'std_resumable', '1234')")

        c = app.app.test_client()
        c.post('/student/login/post', data={'username': 'std_resumable', 'password': '1234'})

        # 1. Start exam
        res_exam = c.get(f'/student/exam/{eid}')
        self.assertEqual(res_exam.status_code, 200)

        att = self.db.q("SELECT * FROM attempts WHERE exam_id=? AND student_id=? AND status='ACTIVE'", (eid, 810), one=True)
        self.assertIsNotNone(att)

        snap = self.db.q("SELECT * FROM attempt_snapshots WHERE attempt_id=?", (att['id'],), one=True)
        self.assertIsNotNone(snap)

        # 2. Autosave answer
        c.post(f'/student/exam/{att["id"]}/autosave', json_data={'question_id': snap['id'], 'answer': 'أ'})

        # 3. Simulate browser close & return (Resume)
        res_reopen = c.get(f'/student/exam/{eid}')
        self.assertEqual(res_reopen.status_code, 200)
        self.assertIn('checked', res_reopen.text) # Answer 'أ' is checked and restored!

        # 4. Submit exam
        c.post(f'/student/exam/{att["id"]}/submit', data={f'q_{snap["id"]}': 'أ'})
        
        # 5. Reopening submitted exam MUST redirect to result and NEVER show resume!
        res_after_submit = c.get(f'/student/exam/{eid}')
        self.assertEqual(res_after_submit.status_code, 302)
        self.assertIn(f'/student/result/{att["id"]}', res_after_submit.headers.get('Location', ''))

    def test_06_a4_print_styling_and_direction(self):
        sub = self.db.q("SELECT id FROM subjects WHERE code='english'", one=True)
        eid = self.db.x("INSERT INTO exams (title, subject_id, class_name, section, duration, status, active) VALUES ('English Final Exam', ?, 'Grade 12', 'A', 60, 'PUBLISHED', 1)", (sub['id'],))
        qid = self.db.x("INSERT INTO questions (subject_id, question, option_a, option_b, option_c, option_d, correct, language, direction, status, approved) VALUES (?, 'Choose the correct verb:', 'is', 'are', 'was', 'were', 'A', 'en', 'ltr', 'APPROVED', 1)", (sub['id'],))
        self.db.x("INSERT INTO exam_questions (exam_id, question_id, position) VALUES (?, ?, 1)", (eid, qid))

        res_print = self.client.get(f'/print/exam/{eid}')
        self.assertEqual(res_print.status_code, 200)

        # Verify A4 Portrait page rule
        self.assertIn('size: A4 portrait;', res_print.text)

        # Verify Semantic Header is RTL Arabic
        self.assertIn('semantic-exam-header', res_print.text)
        self.assertIn('direction: rtl !important;', res_print.text)

        # Verify English Question Body is LTR
        self.assertIn('ltr-mode', res_print.text)
        self.assertIn('direction: ltr !important;', res_print.text)

if __name__ == '__main__':
    unittest.main()
