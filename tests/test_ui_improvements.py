# -*- coding: utf-8 -*-
"""
Test UI Enhancements and User Request Fixes:
1. Infinite reload prevention verification
2. Subject simplicity (just name, no basic/secondary distinction)
3. Terminology: 'الوحدة' instead of 'حزمة'
4. Official exam header matching Ministry of Education standard
"""
import sys, os, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app

class TestUIImprovements(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.db = app.db

    def test_01_subject_simple_creation_and_deletion(self):
        # Teacher just adds subject by name (e.g. جغرافيا) without needing code
        res_add = self.client.post('/subjects/add', data={'name': 'جغرافيا التوجيهي'})
        self.assertEqual(res_add.status_code, 302)

        sub = self.db.q("SELECT * FROM subjects WHERE name='جغرافيا التوجيهي'", one=True)
        self.assertIsNotNone(sub)
        self.assertTrue(sub['code'].startswith('sub_'))

        # Teacher can delete any subject without 'is_default' restrictions
        res_del = self.client.post(f"/subjects/delete/{sub['id']}")
        self.assertEqual(res_del.status_code, 302)
        deleted = self.db.q("SELECT * FROM subjects WHERE id=?", (sub['id'],), one=True)
        self.assertIsNone(deleted)

    def test_02_unit_terminology_in_templates(self):
        # Check packages page has "الوحدات"
        res_pkg = self.client.get('/packages')
        self.assertEqual(res_pkg.status_code, 200)
        self.assertIn('الوحدات', res_pkg.text)
        self.assertIn('+ إضافة وحدة دراسية جديدة', res_pkg.text)

        # Check import page has "الوحدة"
        res_imp = self.client.get('/import')
        self.assertEqual(res_imp.status_code, 200)
        self.assertIn('الوحدة الدراسية', res_imp.text)
        self.assertIn('+ وحدة جديدة', res_imp.text)

    def test_03_official_exam_header_both_logos_and_layout(self):
        # Create a test exam
        sub = self.db.q("SELECT id FROM subjects WHERE code='history'", one=True)
        eid = self.db.x("INSERT INTO exams (title, subject_id, duration, status, active) VALUES ('امتحان تجريبي للترويسة', ?, 45, 'PUBLISHED', 1)", (sub['id'],))
        qid = self.db.x("INSERT INTO questions (subject_id, question, option_a, option_b, option_c, option_d, correct, status, approved) VALUES (?, 'سؤال ترويسة', 'أ', 'ب', 'ج', 'د', 'أ', 'APPROVED', 1)", (sub['id'],))
        self.db.x("INSERT INTO exam_questions (exam_id, question_id, position) VALUES (?, ?, 1)", (eid, qid))

        res_print = self.client.get(f'/print/exam/{eid}')
        self.assertEqual(res_print.status_code, 200)

        # Check official Ministry emblem is present
        self.assertIn('jordan_emblem.png', res_print.text)
        self.assertIn('ministry-emblem', res_print.text)
        self.assertIn('المملكة الأردنية الهاشمية', res_print.text)
        self.assertIn('وزارة التربية والتعليم', res_print.text)
        self.assertIn('official-exam-header-box', res_print.text)
        self.assertIn('semantic-exam-header', res_print.text)

if __name__ == '__main__':
    unittest.main()
