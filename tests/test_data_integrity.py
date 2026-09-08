# -*- coding: utf-8 -*-
"""
Test Data Integrity:
1. Subject domain entity (canonical identity, default vs custom)
2. Question packages uniqueness per subject
3. Immutable Attempt Snapshots (Question bank changes do NOT alter historical results)
4. Transactional exam deletion (protects Question Bank)
5. Exam copy isolation (does not copy attempts)
"""
import sys, os, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app

class TestDataIntegrity(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.db = app.db

    def test_01_subjects_domain_entity(self):
        defaults = self.db.q("SELECT code, name, language, direction FROM subjects WHERE is_default=1")
        codes = [d['code'] for d in defaults]
        self.assertIn('arabic', codes)
        self.assertIn('english', codes)
        self.assertIn('history', codes)
        self.assertIn('islamic_studies', codes)

        res = self.client.post('/subjects/add', data={
            'name': 'الفيزياء الحديثة',
            'code': 'physics_modern',
            'language': 'ar',
            'direction': 'rtl'
        })
        self.assertEqual(res.status_code, 302)
        sub = self.db.q("SELECT * FROM subjects WHERE code='physics_modern'", one=True)
        self.assertIsNotNone(sub)
        self.assertEqual(sub['name'], 'الفيزياء الحديثة')

    def test_02_package_uniqueness_per_subject(self):
        eng = self.db.q("SELECT id FROM subjects WHERE code='english'", one=True)
        self.assertIsNotNone(eng)

        self.client.post('/packages/add', data={
            'subject_id': eng['id'],
            'name': 'Unit 1: Grammar',
            'description': 'Grammar and usage'
        })

        pkg1 = self.db.q("SELECT * FROM question_packages WHERE subject_id=? AND name='Unit 1: Grammar'", (eng['id'],), one=True)
        self.assertIsNotNone(pkg1)

        self.client.post('/packages/add', data={
            'subject_id': eng['id'],
            'name': 'Unit 1: Grammar',
            'description': 'Duplicate'
        })
        count = self.db.q("SELECT COUNT(*) as n FROM question_packages WHERE subject_id=? AND name='Unit 1: Grammar'", (eng['id'],), one=True)['n']
        self.assertEqual(count, 1)

    def test_03_attempt_snapshot_immutability(self):
        hist = self.db.q("SELECT id FROM subjects WHERE code='history'", one=True)
        qid = self.db.x("""
            INSERT INTO questions (subject_id, question, option_a, option_b, option_c, option_d, correct, mark, status, approved)
            VALUES (?, 'ما هي عاصمة الأردن؟', 'عمان', 'الكرك', 'الطفيلة', 'معان', 'أ', 5.0, 'APPROVED', 1)
        """, (hist['id'],))

        self.db.x("""
            INSERT OR IGNORE INTO students (full_name, username, password)
            VALUES ('طالب تجريبي للاختبار', 'test_snap_std', '1234')
        """)
        st = self.db.q("SELECT id, full_name FROM students WHERE username='test_snap_std'", one=True)
        sid = st['id']

        eid = self.db.x("""
            INSERT INTO exams (title, subject_id, question_count, duration, status, active)
            VALUES ('امتحان التاريخ النصفي', ?, 1, 30, 'PUBLISHED', 1)
        """, (hist['id'],))
        self.db.x("INSERT INTO exam_questions (exam_id, question_id, position) VALUES (?, ?, 1)", (eid, qid))

        c = self.client
        login_res = c.post('/student/login/post', data={'username': 'test_snap_std', 'password': '1234'})
        self.assertEqual(login_res.status_code, 302)

        exam_res = c.get(f'/student/exam/{eid}')
        self.assertEqual(exam_res.status_code, 200)

        att = self.db.q("SELECT * FROM attempts WHERE exam_id=? AND student_id=? ORDER BY id DESC LIMIT 1", (eid, sid), one=True)
        self.assertIsNotNone(att)
        self.assertEqual(att['status'], 'ACTIVE')

        snap = self.db.q("SELECT * FROM attempt_snapshots WHERE attempt_id=?", (att['id'],), one=True)
        self.assertIsNotNone(snap)
        self.assertEqual(snap['question_text'], 'ما هي عاصمة الأردن؟')
        self.assertEqual(snap['correct_option'], 'أ')

        autosave_res = c.post(f'/student/exam/{att["id"]}/autosave', json_data={
            'question_id': snap['id'],
            'answer': 'أ'
        })
        self.assertTrue(autosave_res.get_json()['ok'])

        sub_res = c.post(f'/student/exam/{att["id"]}/submit', data={f'q_{snap["id"]}': 'أ'})
        self.assertEqual(sub_res.status_code, 302)

        att_sub = self.db.q("SELECT * FROM attempts WHERE id=?", (att['id'],), one=True)
        self.assertEqual(att_sub['status'], 'SUBMITTED')
        self.assertEqual(att_sub['score'], 5.0)

        # Modify original question bank question!
        self.db.x("""
            UPDATE questions
            SET question = 'نص السؤال بعد التعديل الجذري',
                option_a = 'خيار جديد',
                correct = 'د'
            WHERE id = ?
        """, (qid,))

        # Verify old snapshot and result are completely unchanged
        old_snap = self.db.q("SELECT * FROM attempt_snapshots WHERE attempt_id=?", (att['id'],), one=True)
        self.assertEqual(old_snap['question_text'], 'ما هي عاصمة الأردن؟')
        self.assertEqual(old_snap['correct_option'], 'أ')

        old_ans = self.db.q("SELECT * FROM answers WHERE attempt_id=?", (att['id'],), one=True)
        self.assertEqual(old_ans['is_correct'], 1)
        self.assertEqual(old_ans['mark'], 5.0)

    def test_04_delete_exam_protects_question_bank(self):
        hist = self.db.q("SELECT id FROM subjects WHERE code='history'", one=True)
        qid = self.db.x("""
            INSERT INTO questions (subject_id, question, option_a, option_b, option_c, option_d, correct, status, approved)
            VALUES (?, 'سؤال محمي في البنك', 'أ', 'ب', 'ج', 'د', 'أ', 'APPROVED', 1)
        """, (hist['id'],))

        eid = self.db.x("INSERT INTO exams (title, subject_id) VALUES ('امتحان سيتم حذفه', ?)", (hist['id'],))
        self.db.x("INSERT INTO exam_questions (exam_id, question_id, position) VALUES (?, ?, 1)", (eid, qid))

        self.client.post(f'/exams/{eid}/delete')

        ex = self.db.q("SELECT id FROM exams WHERE id=?", (eid,), one=True)
        self.assertIsNone(ex)

        q_still = self.db.q("SELECT id FROM questions WHERE id=?", (qid,), one=True)
        self.assertIsNotNone(q_still)

    def test_05_copy_exam_isolation(self):
        hist = self.db.q("SELECT id FROM subjects WHERE code='history'", one=True)
        eid = self.db.x("INSERT INTO exams (title, subject_id, duration) VALUES ('الامتحان الأصلي', ?, 40)", (hist['id'],))
        self.db.x("INSERT INTO attempts (exam_id, student_id, student_name, score, status) VALUES (?, 1, 'طالب', 10, 'SUBMITTED')", (eid,))

        self.client.post(f'/exams/{eid}/copy')
        copied = self.db.q("SELECT * FROM exams WHERE title='الامتحان الأصلي (نسخة)'", one=True)
        self.assertIsNotNone(copied)

        att_count = self.db.q("SELECT COUNT(*) as n FROM attempts WHERE exam_id=?", (copied['id'],), one=True)['n']
        self.assertEqual(att_count, 0)

if __name__ == '__main__':
    unittest.main()
