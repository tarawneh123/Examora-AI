# -*- coding: utf-8 -*-
import sys, os, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app

class TestStudentPortalAndExamControls(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.db = app.db

    def test_01_single_attempt_and_teacher_grant_retry(self):
        import uuid
        unique_uname = f"std_retry_{uuid.uuid4().hex[:6]}"
        sub = self.db.q("SELECT id FROM subjects WHERE code='arabic'", one=True)
        qid = self.db.x("""
            INSERT INTO questions (subject_id, question, option_a, option_b, option_c, option_d, correct, mark, status, approved)
            VALUES (?, 'ما إعراب الفاعل في الجملة؟', 'مرفوع', 'منصوب', 'مجرور', 'مجزوم', 'أ', 2.0, 'APPROVED', 1)
        """, (sub['id'],))

        sid = self.db.x("""
            INSERT INTO students (full_name, username, password)
            VALUES (?, ?, '1234')
        """, (f"طالب {unique_uname}", unique_uname))

        eid = self.db.x("""
            INSERT INTO exams (title, subject_id, duration, status, active)
            VALUES ('امتحان القواعد الشامل', ?, 30, 'PUBLISHED', 1)
        """, (sub['id'],))
        self.db.x("INSERT INTO exam_questions (exam_id, question_id, position) VALUES (?, ?, 1)", (eid, qid))

        c = app.app.test_client()
        login_res = c.post('/student/login/post', data={'username': unique_uname, 'password': '1234'})
        self.assertEqual(login_res.status_code, 302)

        res_start = c.get(f'/student/exam/{eid}')
        self.assertEqual(res_start.status_code, 200)

        att1 = self.db.q("SELECT * FROM attempts WHERE exam_id=? AND student_id=? AND status='ACTIVE'", (eid, sid), one=True)
        self.assertIsNotNone(att1)

        # Submit attempt 1
        res_sub1 = c.post(f'/student/exam/{att1["id"]}/submit', data={})
        self.assertEqual(res_sub1.status_code, 302)

        # Student attempts to take exam again -> MUST BE BLOCKED!
        res_blocked = c.get(f'/student/exam/{eid}')
        self.assertEqual(res_blocked.status_code, 302)
        self.assertIn(f'/student/result/{att1["id"]}', res_blocked.headers.get('Location', ''))

        # Teacher grants extra attempt from Exam Management
        teacher_client = self.client
        res_grant = teacher_client.post(f'/exams/{eid}/students/{sid}/grant-attempt')
        self.assertEqual(res_grant.status_code, 302)

        override = self.db.q("SELECT extra_attempts FROM student_exam_overrides WHERE student_id=? AND exam_id=?", (sid, eid), one=True)
        self.assertIsNotNone(override)
        self.assertGreaterEqual(override['extra_attempts'], 1)

        # Student can now start Attempt 2
        res_start2 = c.get(f'/student/exam/{eid}')
        self.assertEqual(res_start2.status_code, 200)

        att2 = self.db.q("SELECT * FROM attempts WHERE exam_id=? AND student_id=? AND status='ACTIVE'", (eid, sid), one=True)
        self.assertIsNotNone(att2)
        self.assertNotEqual(att1['id'], att2['id'])

        all_atts = self.db.q("SELECT id, status FROM attempts WHERE exam_id=? AND student_id=?", (eid, sid))
        self.assertEqual(len(all_atts), 2)

    def test_02_teacher_deletes_student_attempt(self):
        import uuid
        uname = f"std_del_{uuid.uuid4().hex[:6]}"
        sub = self.db.q("SELECT id FROM subjects WHERE code='arabic'", one=True)
        eid = self.db.x("INSERT INTO exams (title, subject_id, duration, status, active) VALUES ('امتحان تجربة الحذف', ?, 20, 'PUBLISHED', 1)", (sub['id'],))
        
        sid = self.db.x("INSERT INTO students (full_name, username, password) VALUES (?, ?, '1234')", (f"طالب {uname}", uname))
        att_id = self.db.x("INSERT INTO attempts (exam_id, student_id, student_name, status, score, total) VALUES (?, ?, 'طالب الحذف', 'SUBMITTED', 10, 10)", (eid, sid))

        res_del = self.client.post(f'/exams/{eid}/attempts/{att_id}/delete')
        self.assertEqual(res_del.status_code, 302)

        check_att = self.db.q("SELECT * FROM attempts WHERE id=?", (att_id,), one=True)
        self.assertIsNone(check_att)

    def test_03_question_delete_safety_no_405(self):
        sub = self.db.q("SELECT id FROM subjects WHERE code='arabic'", one=True)
        qid = self.db.x("""
            INSERT INTO questions (subject_id, question, option_a, option_b, option_c, option_d, correct, status, approved)
            VALUES (?, 'سؤال حذف بدون 405', 'أ', 'ب', 'ج', 'د', 'أ', 'DRAFT', 0)
        """, (sub['id'],))

        res_get = self.client.get(f'/questions/delete/{qid}')
        self.assertEqual(res_get.status_code, 302)

        q_chk = self.db.q("SELECT * FROM questions WHERE id=?", (qid,), one=True)
        self.assertIsNone(q_chk)

if __name__ == '__main__':
    unittest.main()
