# -*- coding: utf-8 -*-
import unittest, os, json
from pathlib import Path
import app as local_app
from examora_service import ExamoraService
from online_backend.scoring import evaluate_exam_submission

class TestImagesAndTrueFalseQuestions(unittest.TestCase):
    def setUp(self):
        self.db = local_app.db
        self.service = ExamoraService(self.db)

    def test_true_false_evaluation(self):
        # 1. Answer key with 2 options (True/False)
        answer_key = {
            "101": {"correct": "أ", "mark": 2.0},  # صح
            "102": {"correct": "ب", "mark": 2.0}   # خطأ
        }

        # Student answered 101 correctly, 102 incorrectly
        student_answers = {
            "101": "أ",
            "102": "أ"
        }

        result = evaluate_exam_submission(student_answers, answer_key)
        self.assertEqual(result['score'], 2.0)
        self.assertEqual(result['total'], 4.0)
        self.assertEqual(result['percentage'], 50.0)

    def test_save_true_false_question_in_db(self):
        # Save question with only option_a and option_b
        qid = self.db.x("""
            INSERT INTO questions (subject_id, question, option_a, option_b, option_c, option_d,
                                  image_path, correct, mark, status, approved, language, direction, confidence, created_at, updated_at)
            VALUES (1, 'الأردن دولة عربية تقع في قارة آسيا.', 'صح', 'خطأ', '', '', 'sample.png', 'أ', 2.0, 'APPROVED', 1, 'ar', 'rtl', 1.0, '2026-09-09 12:00:00', '2026-09-09 12:00:00')
        """)
        self.assertIsNotNone(qid)

        q = self.db.q("SELECT * FROM questions WHERE id=?", (qid,), one=True)
        self.assertEqual(q['option_a'], 'صح')
        self.assertEqual(q['option_b'], 'خطأ')
        self.assertEqual(q['option_c'], '')
        self.assertEqual(q['image_path'], 'sample.png')

        # Clean up test question
        self.db.x("DELETE FROM questions WHERE id=?", (qid,))

if __name__ == '__main__':
    unittest.main()
