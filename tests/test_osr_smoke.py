# -*- coding: utf-8 -*-
"""
Test OSR (Optical Structured Recognition) Smoke & Exact Compliance Tests:
1. Exact Arabic Exam Extraction (RTL, أ-د)
2. Exact English Exam Extraction (LTR, A-D)
3. False Positives Verification (All, Could, About do not become options)
4. Horizontal and Multi-line Option Parsing
5. Exact 21 Import -> Approve 6 -> 6 Approved, 15 Needs_Review
"""
import sys, os, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app
import OSR

class TestOSREngine(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.db = app.db

    def test_01_arabic_ocr_extraction(self):
        text = """
        1- ما هي عاصمة المملكة الأردنية الهاشمية؟
        أ) عمان
        ب) إربد
        ج) الزرقاء
        د) العقبة

        2- متى تم إعلان استقلال المملكة الأردنية الهاشمية؟
        أ) 1921
        ب) 1946
        ج) 1952
        د) 1967
        """
        results = OSR.parse_exam_questions(text, default_lang='ar')
        self.assertEqual(len(results), 2)
        
        q1 = results[0]
        self.assertEqual(q1['question'], 'ما هي عاصمة المملكة الأردنية الهاشمية؟')
        self.assertEqual(q1['option_a'], 'عمان')
        self.assertEqual(q1['option_b'], 'إربد')
        self.assertEqual(q1['option_c'], 'الزرقاء')
        self.assertEqual(q1['option_d'], 'العقبة')
        self.assertEqual(q1['language'], 'ar')
        self.assertEqual(q1['direction'], 'rtl')
        self.assertEqual(q1['status'], 'NEEDS_REVIEW')
        self.assertEqual(q1['approved'], 0)

    def test_02_english_ocr_extraction(self):
        text = """
        1. What is the primary function of mitochondria?
        A) Cellular respiration
        B) Protein synthesis
        C) DNA replication
        D) Lipid storage

        2. Which of the following is a renewable energy source?
        A) Coal
        B) Solar energy
        C) Natural gas
        D) Petroleum
        """
        results = OSR.parse_exam_questions(text, default_lang='en')
        self.assertEqual(len(results), 2)

        q1 = results[0]
        self.assertEqual(q1['language'], 'en')
        self.assertEqual(q1['direction'], 'ltr')
        self.assertEqual(q1['option_a'], 'Cellular respiration')
        self.assertEqual(q1['option_b'], 'Protein synthesis')
        self.assertEqual(q1['status'], 'NEEDS_REVIEW')

    def test_03_false_positives_avoidance(self):
        # Crucial test from Prompt Section 15 & 83:
        # "All...", "Could...", "About..." must NOT be parsed as option markers!
        text = """
        1. Which statement best explains photosynthesis?
        A) Plants absorb light energy
        B) Carbon dioxide is consumed
        C) Could chemical energy be stored in glucose? Yes
        D) All of the above statements are correct
        """
        results = OSR.parse_exam_questions(text, default_lang='en')
        self.assertEqual(len(results), 1)
        q = results[0]
        self.assertEqual(q['option_a'], 'Plants absorb light energy')
        self.assertEqual(q['option_b'], 'Carbon dioxide is consumed')
        self.assertEqual(q['option_c'], 'Could chemical energy be stored in glucose? Yes')
        self.assertEqual(q['option_d'], 'All of the above statements are correct')
        self.assertFalse(q['warnings'])

    def test_04_horizontal_options(self):
        text = """
        1. Identify the capital city:
        (A) Amman (B) Cairo (C) Damascus (D) Baghdad
        """
        results = OSR.parse_exam_questions(text, default_lang='en')
        self.assertEqual(len(results), 1)
        q = results[0]
        self.assertEqual(q['option_a'], 'Amman')
        self.assertEqual(q['option_b'], 'Cairo')
        self.assertEqual(q['option_c'], 'Damascus')
        self.assertEqual(q['option_d'], 'Baghdad')

    def test_05_exact_import_21_approve_6(self):
        # Section 84: Import 21 -> Approve 6 -> Exactly 6 APPROVED, 15 NEEDS_REVIEW
        lines = []
        for i in range(1, 22):
            lines.append(f"{i}- نص السؤال رقم {i}؟\nأ) خيار أ\nب) خيار ب\nج) خيار ج\nد) خيار د")
        batch_text = "\n\n".join(lines)

        hist = self.db.q("SELECT id FROM subjects WHERE code='history'", one=True)
        sub_id = hist['id']

        # Clear prior unapproved questions for clean test
        self.db.x("DELETE FROM questions WHERE status != 'APPROVED'")

        # Process import
        res = self.client.post('/import/process', data={
            'subject_id': sub_id,
            'exam_text': batch_text
        })
        self.assertEqual(res.status_code, 302)

        # Verify 21 questions exist with status NEEDS_REVIEW
        unappr = self.db.q("SELECT id FROM questions WHERE status='NEEDS_REVIEW' ORDER BY id ASC")
        self.assertEqual(len(unappr), 21)

        # Teacher explicitly approves 6 questions only
        to_approve = [str(u['id']) for u in unappr[:6]]
        bulk_res = self.client.post('/review/bulk', data={
            'action': 'approve_selected',
            'selected_ids': to_approve
        })
        self.assertEqual(bulk_res.status_code, 302)

        # Expected counts
        approved_in_batch = self.db.q(f"SELECT COUNT(*) as n FROM questions WHERE id IN ({','.join(to_approve)}) AND status='APPROVED'", one=True)['n']
        self.assertEqual(approved_in_batch, 6)

        remaining_needs_review = self.db.q("SELECT COUNT(*) as n FROM questions WHERE status='NEEDS_REVIEW'", one=True)['n']
        self.assertEqual(remaining_needs_review, 15)

if __name__ == '__main__':
    unittest.main()
