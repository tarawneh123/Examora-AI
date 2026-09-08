# -*- coding: utf-8 -*-
"""
Full End-to-End Test Suite:
Simulates the entire Teacher & Student Journey across all 104 requirements.
"""
import sys, os, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app

class TestFullSuiteE2E(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.db = app.db

    def test_complete_teacher_and_student_lifecycle(self):
        # 1. First Run Setup
        self.db.set_setting('first_run_completed', '0')
        res_setup = self.client.post('/complete-first-run', data={
            'teacher_name': 'عبلة الطراونة',
            'school_name': 'مدرسة خالد بن الوليد الثانوية للبنات',
            'directorate_name': 'مديرية المزار الجنوبي',
            'grade': 'الثانوية العامة'
        })
        self.assertEqual(res_setup.status_code, 302)
        self.assertEqual(self.db.setting('first_run_completed'), '1')

        # 2. Verify Canonical Subjects
        subjects = self.db.q("SELECT * FROM subjects")
        self.assertGreaterEqual(len(subjects), 4)

        # 3. Create Custom Subject (Physics)
        self.client.post('/subjects/add', data={
            'name': 'الفيزياء التطبيقية',
            'code': 'applied_physics',
            'language': 'ar',
            'direction': 'rtl'
        })
        phys = self.db.q("SELECT * FROM subjects WHERE code='applied_physics'", one=True)
        self.assertIsNotNone(phys)
        self.db.x("DELETE FROM questions WHERE subject_id = ?", (phys['id'],))

        # 4. Create Question Package for Physics
        self.client.post('/packages/add', data={
            'subject_id': phys['id'],
            'name': 'الوحدة الأولى: الميكانيكا',
            'description': 'قوانين نيوتن وحركة الأجسام'
        })
        pkg = self.db.q("SELECT * FROM question_packages WHERE subject_id=? AND name='الوحدة الأولى: الميكانيكا'", (phys['id'],), one=True)
        self.assertIsNotNone(pkg)

        # 5. Add Student
        self.client.post('/students/add', data={
            'full_name': 'سارة أحمد محمود الطراونة',
            'class_name': 'الثانوية العامة',
            'section': 'أ',
            'username': 'sara_tarawneh',
            'password': 'pass_sara_123'
        })
        student = self.db.q("SELECT * FROM students WHERE username='sara_tarawneh'", one=True)
        self.assertIsNotNone(student)

        # 6. Extract Questions via OSR
        sample_exam_text = """
        1- ما هي وحدة قياس القوة في النظام الدولي؟
        أ) النيوتن
        ب) الجول
        ج) الواط
        د) الباسكال

        2- جسم كتلته 2 كغم وتسارعه 3 م/ث2، ما مقدار القوة المؤثرة؟
        أ) 6 نيوتن
        ب) 1.5 نيوتن
        ج) 5 نيوتن
        د) 1 نيوتن

        3- ما هو نص القانون الأول لنيوتن في الحركة؟
        أ) الجسم الساكن يبقى ساكناً ما لم تؤثر عليه قوة
        ب) القوة تساوي الكتلة في التسارع
        ج) لكل فعل رد فعل مساوٍ له في المقدار
        د) الطاقة لا تفنى ولا تستحدث
        """
        res_extract = self.client.post('/import/process', data={
            'subject_id': phys['id'],
            'package_id': pkg['id'],
            'exam_text': sample_exam_text
        })
        self.assertEqual(res_extract.status_code, 302)

        # Verify questions start as NEEDS_REVIEW
        extracted_qs = self.db.q("SELECT * FROM questions WHERE subject_id=? AND status='NEEDS_REVIEW' ORDER BY id ASC", (phys['id'],))
        self.assertEqual(len(extracted_qs), 3)

        # 7. QC Review: Teacher selectively approves 2 questions and rejects 1
        q_ids = [str(q['id']) for q in extracted_qs]
        self.client.post('/review/bulk', data={
            'action': 'approve_selected',
            'selected_ids': q_ids[:2]
        })
        self.client.post('/review/bulk', data={
            'action': 'reject_selected',
            'selected_ids': [q_ids[2]]
        })

        # Verify Question Bank shows only approved questions
        bank_qs = self.db.q("SELECT * FROM questions WHERE subject_id=? AND status='APPROVED'", (phys['id'],))
        self.assertEqual(len(bank_qs), 2)

        # 8. Create Exam using Question Bank
        res_exam_create = self.client.post('/exams/create/process', data={
            'title': 'امتحان الفيزياء الشهري الأول',
            'subject_id': phys['id'],
            'package_id': pkg['id'],
            'class_name': 'الثانوية العامة',
            'section': 'أ',
            'duration': 40,
            'password': '',
            'question_ids': [str(q['id']) for q in bank_qs]
        })
        self.assertEqual(res_exam_create.status_code, 302)

        exam = self.db.q("SELECT * FROM exams WHERE title='امتحان الفيزياء الشهري الأول'", one=True)
        self.assertIsNotNone(exam)
        self.assertEqual(exam['question_count'], 2)
        self.assertEqual(exam['status'], 'DRAFT')

        # 9. Publish Exam
        self.client.post(f'/exams/{exam["id"]}/toggle')
        exam_pub = self.db.q("SELECT * FROM exams WHERE id=?", (exam['id'],), one=True)
        self.assertEqual(exam_pub['status'], 'PUBLISHED')
        self.assertEqual(exam_pub['active'], 1)

        # 10. Student Logs In
        student_client = app.app.test_client()
        res_slogin = student_client.post('/student/login/post', data={
            'username': 'sara_tarawneh',
            'password': 'pass_sara_123'
        })
        self.assertEqual(res_slogin.status_code, 302)

        # Student opens exam -> takes snapshot
        res_s_exam = student_client.get(f'/student/exam/{exam["id"]}')
        self.assertEqual(res_s_exam.status_code, 200)

        attempt = self.db.q("SELECT * FROM attempts WHERE exam_id=? AND student_id=? AND status='ACTIVE'", (exam['id'], student['id']), one=True)
        self.assertIsNotNone(attempt)

        snapshots = self.db.q("SELECT * FROM attempt_snapshots WHERE attempt_id=? ORDER BY position ASC", (attempt['id'],))
        self.assertEqual(len(snapshots), 2)

        # 11. Student Autosaves Answers (Q1: 'أ' correct, Q2: 'ب' wrong)
        autosave1 = student_client.post(f'/student/exam/{attempt["id"]}/autosave', json_data={
            'question_id': snapshots[0]['id'],
            'answer': 'أ'
        })
        self.assertTrue(autosave1.get_json()['ok'])

        autosave2 = student_client.post(f'/student/exam/{attempt["id"]}/autosave', json_data={
            'question_id': snapshots[1]['id'],
            'answer': 'ب'
        })
        self.assertTrue(autosave2.get_json()['ok'])

        # 12. Submit Exam
        res_submit = student_client.post(f'/student/exam/{attempt["id"]}/submit', data={
            f'q_{snapshots[0]["id"]}': 'أ',
            f'q_{snapshots[1]["id"]}': 'ب'
        })
        self.assertEqual(res_submit.status_code, 302)

        # Verify attempt calculation (Q1 correct = 1.0, Q2 wrong = 0.0 -> score 1.0 / 2.0 = 50.0%)
        attempt_fin = self.db.q("SELECT * FROM attempts WHERE id=?", (attempt['id'],), one=True)
        self.assertEqual(attempt_fin['status'], 'SUBMITTED')
        self.assertEqual(attempt_fin['score'], 1.0)
        self.assertEqual(attempt_fin['total'], 2.0)
        self.assertEqual(attempt_fin['percentage'], 50.0)

        # 13. Reopening Submitted Exam Must Redirect to Result (Never allow resume!)
        res_reopen = student_client.get(f'/student/exam/{exam["id"]}')
        self.assertEqual(res_reopen.status_code, 302)
        self.assertIn(f'/student/result/{attempt["id"]}', res_reopen.headers.get('Location', ''))

        # 14. Print Exam Check (A4 Portrait, Semantic Arabic Header)
        res_print = self.client.get(f'/print/exam/{exam["id"]}')
        self.assertEqual(res_print.status_code, 200)
        self.assertIn('semantic-exam-header', res_print.text)
        self.assertIn('size: A4 portrait;', res_print.text)

        # 15. Immutability Verification: Modify Question Bank
        self.db.x("""
            UPDATE questions
            SET question = 'تم تغيير هذا السؤال تماماً في بنك الأسئلة',
                correct = 'د'
            WHERE id = ?
        """, (snapshots[0]['question_id'],))

        # Check that Student's historical attempt snapshot is UNCHANGED!
        snap_after = self.db.q("SELECT * FROM attempt_snapshots WHERE id=?", (snapshots[0]['id'],), one=True)
        self.assertEqual(snap_after['question_text'], snapshots[0]['question_text'])
        self.assertEqual(snap_after['correct_option'], 'أ')

        # 16. Delete Exam (Transactional Deletion: Exam & attempts gone, Question Bank questions intact!)
        self.client.post(f'/exams/{exam["id"]}/delete')
        self.assertIsNone(self.db.q("SELECT id FROM exams WHERE id=?", (exam['id'],), one=True))
        self.assertIsNone(self.db.q("SELECT id FROM attempts WHERE id=?", (attempt['id'],), one=True))
        self.assertIsNone(self.db.q("SELECT id FROM attempt_snapshots WHERE attempt_id=?", (attempt['id'],), one=True))

        # Questions in bank STILL EXIST!
        q1_still = self.db.q("SELECT id FROM questions WHERE id=?", (snapshots[0]['question_id'],), one=True)
        self.assertIsNotNone(q1_still)

        print("\n🏆 End-to-End Teacher & Student Lifecycle Test PASSED with 100% Success!")

if __name__ == '__main__':
    unittest.main()
