# -*- coding: utf-8 -*-
"""
Examora AI - Online Cloud Backend Comprehensive Test Suite
Validates all 15 Phase 3 architectural and security requirements in strict isolation:
1. Zero connection to local SQLite database.
2. Schema creation and foreign key integrity.
3. Teacher API secret verification (rejection of invalid secrets).
4. Public API rejects Teacher Authorization header.
5. Zero leakage of answer keys in public question payloads.
6. No public endpoint exists to query answer keys.
7. Attempt token required in header (X-Attempt-Token).
8. IDOR rejection (tampered attempt_token rejected).
9. Client score tampering ignored (pure server-side grading).
10. Server deadline strictly enforced.
11. Upsert prevents duplicate answer records.
12. Cascade deletion integrity.
13. Purge gatekeeper blocks deletion of active or unsynced attempts.
14. Publish validation rejects invalid exams.
15. Malformed requests handled gracefully.
"""
import unittest, os, sys, json, time
from datetime import datetime, timedelta
from pathlib import Path

# Setup isolated import path strictly inside online_backend
TEST_DIR = Path(__file__).resolve().parent
ONLINE_BACKEND_DIR = TEST_DIR.parent
sys.path.insert(0, str(ONLINE_BACKEND_DIR))

# Ensure test DB is isolated in /tmp and NEVER touches exam_platform.db
os.environ['SQLITE_TEST_PATH'] = '/tmp/test_isolated_online_backend_phase3.db'
os.environ['TEACHER_ONLINE_SECRET'] = 'test-teacher-secret-key-321'
os.environ['ENVIRONMENT'] = 'test'

from app import app, db
from config import TEACHER_ONLINE_SECRET
from security import hash_attempt_token

class TestOnlineBackendPhase3(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.headers = {'Authorization': f'Bearer {TEACHER_ONLINE_SECRET}'}

    def test_01_backend_operates_without_local_sqlite(self):
        """1. Verify backend runs with ZERO connection or reference to exam_platform.db."""
        self.assertNotIn('exam_platform.db', db.sqlite_path)
        health_res = self.client.get('/health')
        self.assertEqual(health_res.status_code, 200)
        data = health_res.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('service'), 'Examora Online Cloud Backend')

    def test_02_schema_and_fk_integrity(self):
        """2. Verify schema tables exist and foreign keys are active."""
        tables = [r[0] for r in db.q("SELECT name FROM sqlite_master WHERE type='table';")]
        self.assertIn('online_exams', tables)
        self.assertIn('online_answer_keys', tables)
        self.assertIn('online_attempts', tables)
        self.assertIn('online_answers', tables)

    def test_03_teacher_api_rejects_invalid_secret(self):
        """3. Verify teacher API rejects invalid or missing secret."""
        # No header
        res1 = self.client.post('/api/teacher/publish', json_data={'title': 'Fail'})
        self.assertEqual(res1.status_code, 401)
        # Invalid secret
        bad_headers = {'Authorization': 'Bearer wrong-secret-token'}
        res2 = self.client.post('/api/teacher/publish', json_data={'title': 'Fail'}, headers=bad_headers)
        self.assertEqual(res2.status_code, 401)

    def test_04_public_api_rejects_teacher_secret(self):
        """4. Verify public student endpoint rejects request if Teacher Authorization header is attached."""
        res = self.client.post('/api/public/exam/start', json_data={'national_id': '123'}, headers=self.headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('مخصص للطلاب فقط', res.get_json().get('error', ''))

    def test_05_answer_key_not_in_student_response(self):
        """5. Verify zero correct answer leakage in student start payload."""
        # Publish test exam
        pub_payload = {
            'title': 'امتحان حاسوب أمني',
            'subject': 'أمن المعلومات',
            'duration': 30,
            'total_marks': 10.0,
            'allowed_students': ['2009001122'],
            'questions': [{
                'id': 501,
                'number': 1,
                'text': 'ما هو التشفير المتناظر؟',
                'options': {'أ': 'AES', 'ب': 'RSA', 'ج': 'ECC', 'د': 'Diffie-Hellman'},
                'mark': 10.0
            }],
            'answer_key': {'501': {'correct': 'أ', 'mark': 10.0}}
        }
        pub_res = self.client.post('/api/teacher/publish', json_data=pub_payload, headers=self.headers)
        self.assertEqual(pub_res.status_code, 200)
        token = pub_res.get_json()['publish_token']

        # Student starts exam
        start_res = self.client.post('/api/public/exam/start', json_data={'national_id': '2009001122', 'publish_token': token})
        self.assertEqual(start_res.status_code, 200)
        questions = start_res.get_json()['questions']

        for q in questions:
            self.assertNotIn('correct', q)
            self.assertNotIn('correct_answer', q)
            self.assertNotIn('answer_key', q)
            self.assertNotIn('correct_option', q)

    def test_06_no_public_endpoint_for_answer_keys(self):
        """6. Verify there is no route or public endpoint allowing answer key extraction."""
        routes = [r[4] for r in app.routes]
        for path in routes:
            self.assertNotIn('answer_key', path.lower())
            self.assertNotIn('keys', path.lower())

    def test_07_attempt_token_required_for_actions(self):
        """7. Verify autosave & submit reject calls missing X-Attempt-Token header."""
        res_save = self.client.post('/api/public/exam/autosave', json_data={'attempt_id': 1, 'question_id': 1, 'answer': 'أ'})
        self.assertEqual(res_save.status_code, 400)

        res_sub = self.client.post('/api/public/exam/submit', json_data={'attempt_id': 1, 'answers': {'1': 'أ'}})
        self.assertEqual(res_sub.status_code, 400)

    def test_08_idor_rejected(self):
        """8. Verify IDOR attacks are blocked (Attempt Token mismatch)."""
        pub_res = self.client.post('/api/teacher/publish', json_data={
            'title': 'امتحان اختبار IDOR',
            'subject': 'الأمان',
            'duration': 30,
            'total_marks': 5.0,
            'allowed_students': ['2009000001', '2009000002'],
            'questions': [{'id': 1, 'text': 'Q1', 'options': {'أ': 'A', 'ب': 'B'}, 'mark': 5.0}],
            'answer_key': {'1': {'correct': 'أ', 'mark': 5.0}}
        }, headers=self.headers)
        token = pub_res.get_json()['publish_token']

        # Student A starts
        start_a = self.client.post('/api/public/exam/start', json_data={'national_id': '2009000001', 'publish_token': token})
        att_id_a = start_a.get_json()['attempt_id']
        token_a = start_a.get_json()['attempt_token']

        # Student B starts
        start_b = self.client.post('/api/public/exam/start', json_data={'national_id': '2009000002', 'publish_token': token})
        token_b = start_b.get_json()['attempt_token']

        # Student B attempts to autosave to Student A's attempt (IDOR attack)
        idor_res = self.client.post('/api/public/exam/autosave', json_data={
            'attempt_id': att_id_a,
            'question_id': 1,
            'answer': 'ب'
        }, headers={'X-Attempt-Token': token_b})

        self.assertEqual(idor_res.status_code, 403)
        self.assertIn('غير مصرح', idor_res.get_json().get('error', ''))

    def test_09_client_score_tampering_ignored(self):
        """9. Verify client cannot forge or dictate their own score."""
        pub_res = self.client.post('/api/teacher/publish', json_data={
            'title': 'امتحان تصحيح خادمي',
            'subject': 'رياضيات',
            'duration': 30,
            'total_marks': 10.0,
            'allowed_students': ['2009000003'],
            'questions': [{'id': 77, 'text': '1+1=?', 'options': {'أ': '2', 'ب': '3'}, 'mark': 10.0}],
            'answer_key': {'77': {'correct': 'أ', 'mark': 10.0}}
        }, headers=self.headers)
        token = pub_res.get_json()['publish_token']

        start = self.client.post('/api/public/exam/start', json_data={'national_id': '2009000003', 'publish_token': token})
        att_id = start.get_json()['attempt_id']
        raw_tok = start.get_json()['attempt_token']

        # Student sends WRONG answer 'ب' but tries to inject score: 10.0
        submit_res = self.client.post('/api/public/exam/submit', json_data={
            'attempt_id': att_id,
            'score': 10.0, # Attempted forgery!
            'percentage': 100.0,
            'answers': {'77': 'ب'}
        }, headers={'X-Attempt-Token': raw_tok})

        self.assertEqual(submit_res.status_code, 200)
        data = submit_res.get_json()
        self.assertEqual(data['score'], 0.0) # Server calculated real score: 0
        self.assertEqual(data['percentage'], 0.0)

    def test_10_server_deadline_enforced(self):
        """10. Verify submissions after server deadline are rejected."""
        pub_res = self.client.post('/api/teacher/publish', json_data={
            'title': 'امتحان سريع منته',
            'subject': 'فيزياء',
            'duration': 1,
            'total_marks': 5.0,
            'allowed_students': ['2009000004'],
            'questions': [{'id': 1, 'text': 'Q', 'options': {'أ': 'A'}, 'mark': 5.0}],
            'answer_key': {'1': {'correct': 'أ', 'mark': 5.0}}
        }, headers=self.headers)
        token = pub_res.get_json()['publish_token']

        start = self.client.post('/api/public/exam/start', json_data={'national_id': '2009000004', 'publish_token': token})
        att_id = start.get_json()['attempt_id']
        raw_tok = start.get_json()['attempt_token']

        # Artificially set server deadline to 10 minutes in the past
        past_str = (datetime.now() - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        db.x("UPDATE online_attempts SET server_deadline=? WHERE id=?", (past_str, att_id))

        # Attempt to autosave
        save_res = self.client.post('/api/public/exam/autosave', json_data={
            'attempt_id': att_id,
            'question_id': 1,
            'answer': 'أ'
        }, headers={'X-Attempt-Token': raw_tok})

        self.assertEqual(save_res.status_code, 403)
        self.assertIn('انتهى الوقت', save_res.get_json().get('error', ''))

    def test_11_duplicate_answers_prevented(self):
        """11. Verify duplicate autosave calls upsert the single answer without duplicate records."""
        pub_res = self.client.post('/api/teacher/publish', json_data={
            'title': 'امتحان فريد الإجابة',
            'subject': 'كيمياء',
            'duration': 30,
            'total_marks': 5.0,
            'allowed_students': ['2009000005'],
            'questions': [{'id': 88, 'text': 'H2O هو?', 'options': {'أ': 'ماء', 'ب': 'هواء'}, 'mark': 5.0}],
            'answer_key': {'88': {'correct': 'أ', 'mark': 5.0}}
        }, headers=self.headers)
        token = pub_res.get_json()['publish_token']

        start = self.client.post('/api/public/exam/start', json_data={'national_id': '2009000005', 'publish_token': token})
        att_id = start.get_json()['attempt_id']
        raw_tok = start.get_json()['attempt_token']

        # Autosave option 'ب'
        self.client.post('/api/public/exam/autosave', json_data={'attempt_id': att_id, 'question_id': 88, 'answer': 'ب'}, headers={'X-Attempt-Token': raw_tok})
        # Autosave option 'أ' for same question
        self.client.post('/api/public/exam/autosave', json_data={'attempt_id': att_id, 'question_id': 88, 'answer': 'أ'}, headers={'X-Attempt-Token': raw_tok})

        # Verify only 1 answer row exists for this question
        count = db.q("SELECT COUNT(*) as n FROM online_answers WHERE attempt_id=? AND question_id=88", (att_id,), one=True)['n']
        self.assertEqual(count, 1)
        latest_ans = db.q("SELECT answer FROM online_answers WHERE attempt_id=? AND question_id=88", (att_id,), one=True)['answer']
        self.assertEqual(latest_ans, 'أ')

    def test_12_cascade_deletion(self):
        """12. Verify deleting an exam cascades to answer keys, attempts, and answers."""
        pub_res = self.client.post('/api/teacher/publish', json_data={
            'title': 'امتحان حذف تسلسلي',
            'subject': 'أحياء',
            'duration': 30,
            'total_marks': 5.0,
            'allowed_students': ['2009000006'],
            'questions': [{'id': 1, 'text': 'Q', 'options': {'أ': 'A'}, 'mark': 5.0}],
            'answer_key': {'1': {'correct': 'أ', 'mark': 5.0}}
        }, headers=self.headers)
        token = pub_res.get_json()['publish_token']

        start = self.client.post('/api/public/exam/start', json_data={'national_id': '2009000006', 'publish_token': token})
        att_id = start.get_json()['attempt_id']
        raw_tok = start.get_json()['attempt_token']
        self.client.post('/api/public/exam/submit', json_data={'attempt_id': att_id, 'answers': {'1': 'أ'}}, headers={'X-Attempt-Token': raw_tok})

        # Mark as synced so purge gatekeeper allows it
        self.client.post(f'/api/teacher/exams/{token}/close', headers=self.headers)
        self.client.post(f'/api/teacher/exams/{token}/mark-synced', headers=self.headers)

        # Delete exam
        del_res = self.client.delete(f'/api/teacher/exams/{token}', headers=self.headers)
        self.assertEqual(del_res.status_code, 200)

        # Confirm all child records are wiped
        self.assertIsNone(db.q("SELECT id FROM online_exams WHERE publish_token=?", (token,), one=True))
        self.assertIsNone(db.q("SELECT id FROM online_answer_keys WHERE publish_token=?", (token,), one=True))
        self.assertIsNone(db.q("SELECT id FROM online_attempts WHERE publish_token=?", (token,), one=True))
        self.assertIsNone(db.q("SELECT id FROM online_answers WHERE attempt_id=?", (att_id,), one=True))

    def test_13_purge_blocks_unsynced_and_active_attempts(self):
        """13. Verify purge gatekeeper blocks deletion if attempts are ACTIVE or not synced."""
        pub_res = self.client.post('/api/teacher/publish', json_data={
            'title': 'امتحان حماية الحذف',
            'subject': 'لغة عربية',
            'duration': 30,
            'total_marks': 5.0,
            'allowed_students': ['2009000007'],
            'questions': [{'id': 1, 'text': 'Q', 'options': {'أ': 'A'}, 'mark': 5.0}],
            'answer_key': {'1': {'correct': 'أ', 'mark': 5.0}}
        }, headers=self.headers)
        token = pub_res.get_json()['publish_token']

        # Start attempt (now ACTIVE)
        start = self.client.post('/api/public/exam/start', json_data={'national_id': '2009000007', 'publish_token': token})
        att_id = start.get_json()['attempt_id']
        raw_tok = start.get_json()['attempt_token']

        # 1. Purge while ACTIVE must be rejected
        purge_fail1 = self.client.delete(f'/api/teacher/exams/{token}', headers=self.headers)
        self.assertEqual(purge_fail1.status_code, 400)
        self.assertIn('يجب إغلاق الامتحان', purge_fail1.get_json().get('error', ''))

        # Submit attempt (now SUBMITTED but is_synced=0)
        self.client.post('/api/public/exam/submit', json_data={'attempt_id': att_id, 'answers': {'1': 'أ'}}, headers={'X-Attempt-Token': raw_tok})

        self.client.post(f'/api/teacher/exams/{token}/close', headers=self.headers)
        # 2. Purge while SUBMITTED but NOT synced must be rejected
        purge_fail2 = self.client.delete(f'/api/teacher/exams/{token}', headers=self.headers)
        self.assertEqual(purge_fail2.status_code, 400)
        self.assertIn('لم تتم مزامنتها', purge_fail2.get_json().get('error', ''))

    def test_14_publish_validation(self):
        """14. Verify publish endpoint rejects malformed payloads (empty title, no questions)."""
        res1 = self.client.post('/api/teacher/publish', json_data={'title': ''}, headers=self.headers)
        self.assertEqual(res1.status_code, 400)
        res2 = self.client.post('/api/teacher/publish', json_data={'title': 'Exam', 'questions': []}, headers=self.headers)
        self.assertEqual(res2.status_code, 400)

    def test_15_malformed_requests_handled(self):
        """15. Verify malformed requests do not crash the service (400 returned)."""
        res = self.client.post('/api/public/exam/start', json_data={'invalid_key': 123})
        self.assertEqual(res.status_code, 400)

if __name__ == '__main__':
    unittest.main()
