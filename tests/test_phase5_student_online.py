# -*- coding: utf-8 -*-
"""
PHASE 5 Smoke Tests: Student Online Integration
Validates the Student Online Gateway API contract used by firebase_landing/js/exam.js:
1. Start exam flow (Token extraction, attempt initialization, clean questions bundle)
2. Unauthorized student rejection (403)
3. Closed exam rejection (404)
4. Autosave flow with X-Attempt-Token header
5. Server-side submit and grading (pure server evaluation, client score ignored)
6. Zero answer-key leakage across all student API responses
7. Server deadline expiration enforcement
8. In-progress attempt resumption with saved answers
"""
import unittest, os, sys, json, secrets, importlib.util
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ONLINE_DIR = BASE_DIR / 'online_backend'

# Load online backend cleanly
spec = importlib.util.spec_from_file_location('online_backend_p5', str(ONLINE_DIR / 'app.py'))
online_app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(online_app_module)

class TestPhase5StudentOnline(unittest.TestCase):

    def setUp(self):
        self.app = online_app_module.app
        self.db = online_app_module.db
        self.client = self.app.test_client()
        self.teacher_secret = online_app_module.TEACHER_ONLINE_SECRET
        self.auth_headers = {'Authorization': f'Bearer {self.teacher_secret}'}

        # Setup a fresh online exam for testing
        self.exam_payload = {
            'idempotency_key': f'P5-EXAM-{secrets.token_hex(6)}',
            'title': 'امتحان علوم الأرض النهائي',
            'subject': 'علوم الأرض',
            'duration': 25,
            'total_marks': 15.0,
            'allowed_students': ['2009112233', '2009445566'],
            'questions': [
                {'id': 1, 'number': 1, 'text': 'ما هو أصلح صخور القشرة الأرضية؟', 'options': {'أ': 'الجرانيت', 'ب': 'البازلت', 'ج': 'الرخام', 'د': 'الحجر الجيري'}, 'mark': 5.0},
                {'id': 2, 'number': 2, 'text': 'ما هو الغاز الأكثر وفرة في الغلاف الجوي؟', 'options': {'أ': 'الأكسجين', 'ب': 'النيتروجين', 'ج': 'ثاني أكسيد الكربون', 'د': 'الهيدروجين'}, 'mark': 10.0}
            ],
            'answer_key': {
                '1': {'correct': 'أ', 'mark': 5.0},
                '2': {'correct': 'ب', 'mark': 10.0}
            }
        }
        pub_res = self.client.post('/api/teacher/publish', json_data=self.exam_payload, headers=self.auth_headers)
        self.assertEqual(pub_res.status_code, 200)
        self.publish_token = pub_res.get_json()['publish_token']

    def test_01_start_exam_flow(self):
        """1. Verify student starts exam successfully and gets attempt credentials."""
        start_res = self.client.post('/api/public/exam/start', json_data={
            'national_id': '2009112233',
            'publish_token': self.publish_token
        })
        self.assertEqual(start_res.status_code, 200)
        data = start_res.get_json()
        self.assertTrue(data.get('ok'))
        self.assertTrue(data.get('attempt_token'))
        self.assertTrue(data.get('attempt_id'))
        self.assertEqual(data['exam']['title'], 'امتحان علوم الأرض النهائي')
        self.assertEqual(len(data['questions']), 2)
        self.assertEqual(data['remaining_seconds'], 25 * 60)

    def test_02_unauthorized_student_rejected(self):
        """2. Verify student not in allowed list is rejected with 403 Forbidden."""
        res = self.client.post('/api/public/exam/start', json_data={
            'national_id': '9999999999', # Not in allowed list
            'publish_token': self.publish_token
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn('غير مسجل', res.get_json().get('error', ''))

    def test_03_closed_exam_rejected(self):
        """3. Verify student cannot start a closed exam (404 Not Found)."""
        close_res = self.client.post(f'/api/teacher/exams/{self.publish_token}/close', headers=self.auth_headers)
        self.assertEqual(close_res.status_code, 200)

        res = self.client.post('/api/public/exam/start', json_data={
            'national_id': '2009112233',
            'publish_token': self.publish_token
        })
        self.assertEqual(res.status_code, 404)
        self.assertIn('غير متاح', res.get_json().get('error', ''))

    def test_04_autosave_flow(self):
        """4. Verify autosave updates answer with X-Attempt-Token header."""
        start_res = self.client.post('/api/public/exam/start', json_data={
            'national_id': '2009112233',
            'publish_token': self.publish_token
        })
        att_id = start_res.get_json()['attempt_id']
        att_token = start_res.get_json()['attempt_token']

        # Valid autosave
        save_res = self.client.post('/api/public/exam/autosave', json_data={
            'attempt_id': att_id,
            'question_id': 1,
            'answer': 'أ'
        }, headers={'X-Attempt-Token': att_token})
        self.assertEqual(save_res.status_code, 200)
        self.assertTrue(save_res.get_json().get('ok'))

        # Missing token header must be rejected
        bad_save = self.client.post('/api/public/exam/autosave', json_data={
            'attempt_id': att_id,
            'question_id': 1,
            'answer': 'أ'
        })
        self.assertEqual(bad_save.status_code, 400)

    def test_05_submit_flow_and_server_grading(self):
        """5. Verify server-side grading calculates score and locks attempt."""
        start_res = self.client.post('/api/public/exam/start', json_data={
            'national_id': '2009445566',
            'publish_token': self.publish_token
        })
        att_id = start_res.get_json()['attempt_id']
        att_token = start_res.get_json()['attempt_token']

        # Student submits 1 correct answer (Q1: 'أ' = 5.0 marks) and 1 wrong (Q2: 'أ' != 'ب')
        sub_res = self.client.post('/api/public/exam/submit', json_data={
            'attempt_id': att_id,
            'score': 15.0, # Attempted client injection!
            'answers': {'1': 'أ', '2': 'أ'}
        }, headers={'X-Attempt-Token': att_token})

        self.assertEqual(sub_res.status_code, 200)
        data = sub_res.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['score'], 5.0) # Real score calculated by server
        self.assertEqual(data['total'], 15.0)
        self.assertEqual(data['percentage'], round(5.0/15.0*100, 2))

        # Re-submitting same attempt must be blocked
        resub_res = self.client.post('/api/public/exam/submit', json_data={
            'attempt_id': att_id,
            'answers': {'1': 'أ'}
        }, headers={'X-Attempt-Token': att_token})
        self.assertEqual(resub_res.status_code, 403)

    def test_06_no_answer_key_leakage(self):
        """6. Verify no correct answers or answer keys exist in any student API responses."""
        start_res = self.client.post('/api/public/exam/start', json_data={
            'national_id': '2009112233',
            'publish_token': self.publish_token
        })
        resp_text = start_res.text.lower()
        self.assertNotIn('correct', resp_text)
        self.assertNotIn('answer_key', resp_text)
        self.assertNotIn('correct_option', resp_text)

    def test_07_expired_exam_rejected(self):
        """7. Verify autosave/submit past server deadline is rejected."""
        start_res = self.client.post('/api/public/exam/start', json_data={
            'national_id': '2009112233',
            'publish_token': self.publish_token
        })
        att_id = start_res.get_json()['attempt_id']
        att_token = start_res.get_json()['attempt_token']

        # Wind deadline back 10 minutes
        past_str = (datetime.now() - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        self.db.x("UPDATE online_attempts SET server_deadline=? WHERE id=?", (past_str, att_id))

        save_res = self.client.post('/api/public/exam/autosave', json_data={
            'attempt_id': att_id,
            'question_id': 1,
            'answer': 'أ'
        }, headers={'X-Attempt-Token': att_token})
        self.assertEqual(save_res.status_code, 403)
        self.assertIn('انتهى الوقت', save_res.get_json().get('error', ''))

    def test_08_resume_active_attempt(self):
        """8. Verify reloading page resumes active attempt with previously saved answers."""
        start_res = self.client.post('/api/public/exam/start', json_data={
            'national_id': '2009112233',
            'publish_token': self.publish_token
        })
        att_id = start_res.get_json()['attempt_id']
        att_token = start_res.get_json()['attempt_token']

        # Save Q1
        self.client.post('/api/public/exam/autosave', json_data={
            'attempt_id': att_id,
            'question_id': 1,
            'answer': 'أ'
        }, headers={'X-Attempt-Token': att_token})

        # Student reloads page and logs back in
        resume_res = self.client.post('/api/public/exam/start', json_data={
            'national_id': '2009112233',
            'publish_token': self.publish_token
        })
        self.assertEqual(resume_res.status_code, 200)
        resume_data = resume_res.get_json()
        self.assertTrue(resume_data.get('is_resumed'))
        self.assertEqual(resume_data['answers'].get('1'), 'أ')

if __name__ == '__main__':
    unittest.main()
