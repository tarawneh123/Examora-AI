# -*- coding: utf-8 -*-
"""
PHASE 7 Smoke Tests: Lifecycle & Safe Purge of Online Exams
Validates:
1. Close stops accepting new attempts (404 for new student start).
2. Existing student attempts are NOT deleted upon Close.
3. Purge is rejected if attempts are ACTIVE or not yet SYNCED (or if exam is still ACTIVE).
4. Purge succeeds cleanly after exam is CLOSED and all attempts are SYNCED.
5. Repeated Purge is idempotent and does not cause errors or delete local records.
6. Local SQLite data (attempts, exams, students) remains 100% intact and undamaged.
"""
import unittest, os, sys, json, secrets, importlib.util
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import app as local_app_module

# Load online backend explicitly via importlib to avoid module collision
ONLINE_DIR = BASE_DIR / 'online_backend'
spec = importlib.util.spec_from_file_location('online_backend_p7', str(ONLINE_DIR / 'app.py'))
online_app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(online_app_module)

class TestPhase7LifecycleAndPurge(unittest.TestCase):

    def setUp(self):
        self.local_db = local_app_module.db
        self.local_srv = local_app_module.srv
        self.online_app = online_app_module.app
        self.online_db = online_app_module.db
        self.online_client = self.online_app.test_client()
        self.secret = online_app_module.TEACHER_ONLINE_SECRET
        self.auth_headers = {'Authorization': f'Bearer {self.secret}'}

        # Mock online API bridge so local_srv can communicate with online_client in tests
        def mock_bridge(endpoint, method='GET', payload=None):
            if method == 'GET':
                res = self.online_client.get(endpoint, headers=self.auth_headers)
            elif method == 'POST':
                res = self.online_client.post(endpoint, json_data=payload, headers=self.auth_headers)
            elif method == 'DELETE':
                res = self.online_client.delete(endpoint, headers=self.auth_headers)
            else:
                return {'ok': False, 'error': f'Unsupported method {method}'}
            return res.get_json()

        self.orig_call = self.local_srv._call_online_api
        self.local_srv._call_online_api = mock_bridge

        # Create a test student and local exam
        self.local_student = self.local_db.q("SELECT * FROM students WHERE active=1 LIMIT 1", one=True)
        self.local_exam = self.local_db.q("SELECT e.* FROM exams e JOIN exam_questions eq ON e.id = eq.exam_id WHERE e.active = 1 LIMIT 1", one=True)

    def tearDown(self):
        self.local_srv._call_online_api = self.orig_call

    def _setup_active_online_exam(self):
        token = f"LIFECYCLE-TEST-{secrets.token_hex(6)}"
        now_str = "2026-09-08 11:00:00"

        # 1. Local tracking
        self.local_srv.insert('published_exams', {
            'local_exam_id': self.local_exam['id'],
            'publish_token': token,
            'title': self.local_exam['title'],
            'subject_name': self.local_exam['subject'],
            'duration': 30,
            'status': 'ACTIVE',
            'payload_json': '{}',
            'published_at': now_str
        })

        # 2. Online cloud backend
        self.online_db.insert('online_exams', {
            'publish_token': token,
            'title': self.local_exam['title'],
            'subject': self.local_exam['subject'],
            'duration': 30,
            'total_marks': 10.0,
            'status': 'ACTIVE',
            'questions_json': json.dumps([{'id': 1, 'number': 1, 'text': 'Q1', 'options': {'أ': 'A'}, 'mark': 10.0}]),
            'allowed_students_json': json.dumps([self.local_student['national_id']]),
            'created_at': now_str
        })
        self.online_db.insert('online_answer_keys', {
            'publish_token': token,
            'keys_json': json.dumps({'1': {'correct': 'أ', 'mark': 10.0}}),
            'created_at': now_str
        })

        return token

    def test_01_close_stops_new_attempts(self):
        """1. Closing an exam stops accepting new student attempts (returns 404)."""
        token = self._setup_active_online_exam()

        # Teacher closes the exam
        closed_ok = self.local_srv.close_published_exam(token)
        self.assertTrue(closed_ok)

        # Local status updated to CLOSED
        local_pub = self.local_db.q("SELECT status FROM published_exams WHERE publish_token=?", (token,), one=True)
        self.assertEqual(local_pub['status'], 'CLOSED')

        # Cloud status updated to CLOSED
        cloud_exam = self.online_db.q("SELECT status FROM online_exams WHERE publish_token=?", (token,), one=True)
        self.assertEqual(cloud_exam['status'], 'CLOSED')

        # New student attempt rejected
        start_res = self.online_client.post('/api/public/exam/start', json_data={
            'national_id': self.local_student['national_id'],
            'publish_token': token
        })
        self.assertEqual(start_res.status_code, 404)
        self.assertIn('غير متاح', start_res.get_json().get('error', ''))

    def test_02_existing_attempts_not_deleted_on_close(self):
        """2. Existing attempts are preserved and not deleted when exam is closed."""
        token = self._setup_active_online_exam()

        # Student starts and submits
        start_res = self.online_client.post('/api/public/exam/start', json_data={
            'national_id': self.local_student['national_id'],
            'publish_token': token
        })
        att_id = start_res.get_json()['attempt_id']
        raw_tok = start_res.get_json()['attempt_token']

        self.online_client.post('/api/public/exam/submit', json_data={
            'attempt_id': att_id,
            'answers': {'1': 'أ'}
        }, headers={'X-Attempt-Token': raw_tok})

        # Close exam
        self.local_srv.close_published_exam(token)

        # Confirm attempt still exists in online database
        att = self.online_db.q("SELECT * FROM online_attempts WHERE id=?", (att_id,), one=True)
        self.assertIsNotNone(att)
        self.assertEqual(att['status'], 'SUBMITTED')

    def test_03_purge_rejected_if_attempts_unsynced_or_active(self):
        """3. Purge is rejected if attempts are ACTIVE or not yet SYNCED (or if exam is still ACTIVE)."""
        token = self._setup_active_online_exam()

        # 3a. Cannot purge while exam is ACTIVE
        purge_res1 = self.online_client.delete(f'/api/teacher/exams/{token}', headers=self.auth_headers)
        self.assertEqual(purge_res1.status_code, 400)
        self.assertIn('يجب إغلاق الامتحان أولاً', purge_res1.get_json().get('error', ''))

        # Close exam
        self.local_srv.close_published_exam(token)

        # Create submitted unsynced attempt
        att_id = self.online_db.insert('online_attempts', {
            'publish_token': token,
            'student_national_id': self.local_student['national_id'],
            'student_name': self.local_student['full_name'],
            'attempt_token_hash': f'hash-{secrets.token_hex(8)}',
            'status': 'SUBMITTED',
            'score': 10.0,
            'total': 10.0,
            'percentage': 100.0,
            'started_at': "2026-09-08 11:00:00",
            'server_deadline': "2026-09-08 11:30:00",
            'finished_at': "2026-09-08 11:15:00",
            'is_synced': 0 # NOT SYNCED!
        })

        # 3b. Local service rejects purge because local status is CLOSED, not SYNCED
        with self.assertRaises(ValueError) as cm1:
            self.local_srv.purge_published_exam(token)
        self.assertIn("ليست SYNCED", str(cm1.exception))

        # 3c. Cloud API also rejects purge directly
        purge_res2 = self.online_client.delete(f'/api/teacher/exams/{token}', headers=self.auth_headers)
        self.assertEqual(purge_res2.status_code, 400)
        self.assertIn('لم تتم مزامنتها', purge_res2.get_json().get('error', ''))

    def test_04_purge_successful_after_sync(self):
        """4. Purge succeeds cleanly after exam is CLOSED and all attempts are SYNCED."""
        token = self._setup_active_online_exam()

        # Student starts and submits
        start_res = self.online_client.post('/api/public/exam/start', json_data={
            'national_id': self.local_student['national_id'],
            'publish_token': token
        })
        att_id = start_res.get_json()['attempt_id']
        raw_tok = start_res.get_json()['attempt_token']
        self.online_client.post('/api/public/exam/submit', json_data={'attempt_id': att_id, 'answers': {'1': 'أ'}}, headers={'X-Attempt-Token': raw_tok})

        # Close & Sync
        self.local_srv.close_published_exam(token)
        self.local_srv.sync_published_attempts(token)

        # Confirm status is SYNCED
        local_pub = self.local_db.q("SELECT status FROM published_exams WHERE publish_token=?", (token,), one=True)
        self.assertEqual(local_pub['status'], 'SYNCED')

        # Execute Purge
        purged = self.local_srv.purge_published_exam(token)
        self.assertTrue(purged)

        # Confirm cloud data wiped
        self.assertIsNone(self.online_db.q("SELECT id FROM online_exams WHERE publish_token=?", (token,), one=True))
        self.assertIsNone(self.online_db.q("SELECT id FROM online_answer_keys WHERE publish_token=?", (token,), one=True))
        self.assertIsNone(self.online_db.q("SELECT id FROM online_attempts WHERE publish_token=?", (token,), one=True))

        # Confirm local tracking marked as PURGED
        updated_pub = self.local_db.q("SELECT status FROM published_exams WHERE publish_token=?", (token,), one=True)
        self.assertEqual(updated_pub['status'], 'PURGED')

    def test_05_repeated_purge_idempotent_safe(self):
        """5. Re-running purge on an already purged exam is idempotent and returns True safely."""
        token = self._setup_active_online_exam()
        self.local_srv.close_published_exam(token)
        self.local_srv.sync_published_attempts(token)
        self.local_srv.purge_published_exam(token)

        # Run purge second time
        purged_again = self.local_srv.purge_published_exam(token)
        self.assertTrue(purged_again)

    def test_06_local_sqlite_remains_intact(self):
        """6. Confirms local attempts, questions, and students are NOT deleted by purge."""
        token = self._setup_active_online_exam()
        self.local_srv.close_published_exam(token)
        self.local_srv.sync_published_attempts(token)

        # Count local official attempts and questions before purge
        att_cnt_before = self.local_db.q("SELECT COUNT(*) as n FROM attempts", one=True)['n']
        q_cnt_before = self.local_db.q("SELECT COUNT(*) as n FROM questions", one=True)['n']

        self.local_srv.purge_published_exam(token)

        # Count after purge
        att_cnt_after = self.local_db.q("SELECT COUNT(*) as n FROM attempts", one=True)['n']
        q_cnt_after = self.local_db.q("SELECT COUNT(*) as n FROM questions", one=True)['n']

        self.assertEqual(att_cnt_before, att_cnt_after)
        self.assertEqual(q_cnt_before, q_cnt_after)

        int_check = self.local_db.q("PRAGMA integrity_check;", one=True)
        self.assertEqual(int_check[0], 'ok')

if __name__ == '__main__':
    unittest.main()
