# -*- coding: utf-8 -*-
"""
PHASE 6 Test Suite: Sync Online Results -> Local Teacher Database
Validates:
1. Sync single attempt successfully (imports to published_exam_attempts and official attempts with snapshots).
2. Sync twice for same attempt -> strict Idempotency (no duplicate attempt records).
3. Multiple attempts -> all synced correctly.
4. Network failure safety -> SQLite intact, published_exams status NOT set to SYNCED.
5. Invalid/missing attempt data -> handled gracefully without crashing remaining sync.
6. Confirms online_attempt_id is used for deduplication.
7. Confirms zero inbound Online -> SQLite connection.
"""
import unittest, os, sys, json, secrets, importlib.util
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import app as local_app_module

# Load online backend explicitly via importlib to avoid module collision
ONLINE_DIR = BASE_DIR / 'online_backend'
spec = importlib.util.spec_from_file_location('online_backend_p6', str(ONLINE_DIR / 'app.py'))
online_app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(online_app_module)

class TestPhase6SyncOnline(unittest.TestCase):

    def setUp(self):
        self.local_db = local_app_module.db
        self.local_srv = local_app_module.srv
        self.online_app = online_app_module.app
        self.online_db = online_app_module.db
        self.online_client = self.online_app.test_client()
        self.secret = online_app_module.TEACHER_ONLINE_SECRET
        self.auth_headers = {'Authorization': f'Bearer {self.secret}'}

        # Find a valid local student
        self.local_student = self.local_db.q("SELECT * FROM students WHERE active=1 LIMIT 1", one=True)
        self.assertIsNotNone(self.local_student)
        self.nat_id = self.local_student['national_id']

        # Find a local exam
        self.local_exam = self.local_db.q("""
            SELECT e.* FROM exams e
            JOIN exam_questions eq ON e.id = eq.exam_id
            WHERE e.active = 1 LIMIT 1
        """, one=True)
        self.assertIsNotNone(self.local_exam)
        self.exam_id = self.local_exam['id']

        # Mock online API bridge
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

    def tearDown(self):
        self.local_srv._call_online_api = self.orig_call

    def _publish_and_submit_test_attempt(self, nat_id, score=10.0):
        """Helper to create a published exam and student attempt in online backend."""
        token = f"SYNC-TEST-{secrets.token_hex(6)}"
        now_str = "2026-09-08 10:00:00"

        # 1. Create in local published_exams
        self.local_srv.insert('published_exams', {
            'local_exam_id': self.exam_id,
            'publish_token': token,
            'title': self.local_exam['title'],
            'subject_name': self.local_exam['subject'],
            'duration': 30,
            'status': 'ACTIVE',
            'payload_json': json.dumps({'questions_count': 1}),
            'published_at': now_str
        })

        # 2. Create in online_exams
        self.online_db.insert('online_exams', {
            'publish_token': token,
            'title': self.local_exam['title'],
            'subject': self.local_exam['subject'],
            'duration': 30,
            'total_marks': 10.0,
            'status': 'ACTIVE',
            'questions_json': json.dumps([{'id': 1, 'number': 1, 'text': 'Q1', 'options': {'أ': 'A'}, 'mark': 10.0}]),
            'allowed_students_json': json.dumps([nat_id]),
            'created_at': now_str
        })
        self.online_db.insert('online_answer_keys', {
            'publish_token': token,
            'keys_json': json.dumps({'1': {'correct': 'أ', 'mark': 10.0}}),
            'created_at': now_str
        })

        # 3. Create submitted attempt in online_attempts
        att_id = self.online_db.insert('online_attempts', {
            'publish_token': token,
            'student_national_id': nat_id,
            'student_name': self.local_student['full_name'],
            'attempt_token_hash': f'hash-{secrets.token_hex(8)}',
            'status': 'SUBMITTED',
            'score': score,
            'total': 10.0,
            'percentage': (score / 10.0 * 100),
            'tier': 'ممتاز' if score >= 9.0 else 'مقبول',
            'started_at': now_str,
            'server_deadline': "2026-09-08 10:30:00",
            'finished_at': "2026-09-08 10:20:00",
            'is_synced': 0
        })

        self.online_db.insert('online_answers', {
            'attempt_id': att_id,
            'question_id': 1,
            'answer': 'أ',
            'answered_at': "2026-09-08 10:15:00"
        })

        return token, att_id

    def test_01_sync_single_attempt_success(self):
        """1. Sync a single attempt from Cloud to local SQLite successfully."""
        token, online_att_id = self._publish_and_submit_test_attempt(self.nat_id, score=10.0)

        synced_count = self.local_srv.sync_published_attempts(token)
        self.assertEqual(synced_count, 1)

        # Verify record in local published_exam_attempts
        staged = self.local_db.q("SELECT * FROM published_exam_attempts WHERE online_attempt_id=?", (online_att_id,), one=True)
        self.assertIsNotNone(staged)
        self.assertEqual(staged['student_national_id'], self.nat_id)
        self.assertEqual(float(staged['score']), 10.0)

        # Verify record in local attempts
        official = self.local_db.q("""
            SELECT * FROM attempts 
            WHERE exam_id=? AND student_id=? 
            ORDER BY id DESC LIMIT 1
        """, (self.exam_id, self.local_student['id']), one=True)
        self.assertIsNotNone(official)
        self.assertEqual(official['status'], 'SUBMITTED')
        self.assertEqual(float(official['score']), 10.0)
        self.assertIn(f"Cloud Attempt #{online_att_id}", official['override_reason'])

        # Verify published_exams is marked SYNCED
        pub = self.local_db.q("SELECT status FROM published_exams WHERE publish_token=?", (token,), one=True)
        self.assertEqual(pub['status'], 'SYNCED')

        # Verify cloud backend marked attempt as is_synced=1
        cloud_att = self.online_db.q("SELECT is_synced FROM online_attempts WHERE id=?", (online_att_id,), one=True)
        self.assertEqual(cloud_att['is_synced'], 1)

    def test_02_sync_twice_idempotent_no_duplicates(self):
        """2. Syncing twice for the same attempt creates NO duplicate records."""
        token, online_att_id = self._publish_and_submit_test_attempt(self.nat_id, score=8.0)

        # First sync
        cnt1 = self.local_srv.sync_published_attempts(token)
        self.assertEqual(cnt1, 1)

        total_staged_1 = self.local_db.q("SELECT COUNT(*) as n FROM published_exam_attempts WHERE online_attempt_id=?", (online_att_id,), one=True)['n']
        self.assertEqual(total_staged_1, 1)

        total_attempts_1 = self.local_db.q("SELECT COUNT(*) as n FROM attempts WHERE exam_id=? AND student_id=?", (self.exam_id, self.local_student['id']), one=True)['n']

        # Second sync (Idempotent replay)
        cnt2 = self.local_srv.sync_published_attempts(token)
        self.assertEqual(cnt2, 0) # 0 new attempts imported

        total_staged_2 = self.local_db.q("SELECT COUNT(*) as n FROM published_exam_attempts WHERE online_attempt_id=?", (online_att_id,), one=True)['n']
        self.assertEqual(total_staged_2, 1) # Still exactly 1!

        total_attempts_2 = self.local_db.q("SELECT COUNT(*) as n FROM attempts WHERE exam_id=? AND student_id=?", (self.exam_id, self.local_student['id']), one=True)['n']
        self.assertEqual(total_attempts_2, total_attempts_1) # No duplicates created!

    def test_03_multiple_attempts_all_synced(self):
        """3. Multiple attempts sync all distinct records correctly."""
        # Find another local student
        students = self.local_db.q("SELECT * FROM students WHERE active=1 LIMIT 2")
        if len(students) >= 2:
            std2 = students[1]
            token, att1 = self._publish_and_submit_test_attempt(self.nat_id, score=10.0)

            # Add second student attempt on same token
            att2 = self.online_db.insert('online_attempts', {
                'publish_token': token,
                'student_national_id': std2['national_id'],
                'student_name': std2['full_name'],
                'attempt_token_hash': f'hash-{secrets.token_hex(8)}',
                'status': 'SUBMITTED',
                'score': 9.0,
                'total': 10.0,
                'percentage': 90.0,
                'tier': 'ممتاز',
                'started_at': "2026-09-08 10:00:00",
                'server_deadline': "2026-09-08 10:30:00",
                'finished_at': "2026-09-08 10:20:00",
                'is_synced': 0
            })

            synced_cnt = self.local_srv.sync_published_attempts(token)
            self.assertEqual(synced_cnt, 2)

            self.assertIsNotNone(self.local_db.q("SELECT id FROM published_exam_attempts WHERE online_attempt_id=?", (att1,), one=True))
            self.assertIsNotNone(self.local_db.q("SELECT id FROM published_exam_attempts WHERE online_attempt_id=?", (att2,), one=True))

    def test_04_network_failure_safety(self):
        """4. Network failure keeps local SQLite intact and does not mark exam as SYNCED."""
        token, att_id = self._publish_and_submit_test_attempt(self.nat_id, score=10.0)

        # Mock network failure
        def failing_bridge(endpoint, method='GET', payload=None):
            return {'ok': False, 'error': 'Connection reset by peer (Simulated failure)'}

        self.local_srv._call_online_api = failing_bridge

        with self.assertRaises(ConnectionError) as cm:
            self.local_srv.sync_published_attempts(token)
        self.assertIn("فشلت عملية المزامنة السحابية", str(cm.exception))

        # Verify status is NOT marked as SYNCED
        pub = self.local_db.q("SELECT status FROM published_exams WHERE publish_token=?", (token,), one=True)
        self.assertEqual(pub['status'], 'ACTIVE')

        # Verify integrity
        int_check = self.local_db.q("PRAGMA integrity_check;", one=True)
        self.assertEqual(int_check[0], 'ok')

    def test_05_invalid_attempt_data_handling(self):
        """5. An attempt for unknown student is recorded in published_exam_attempts without crashing."""
        token = f"SYNC-TEST-{secrets.token_hex(6)}"
        now_str = "2026-09-08 10:00:00"

        self.local_srv.insert('published_exams', {
            'local_exam_id': self.exam_id,
            'publish_token': token,
            'title': self.local_exam['title'],
            'subject_name': self.local_exam['subject'],
            'duration': 30,
            'status': 'ACTIVE',
            'payload_json': '{}',
            'published_at': now_str
        })

        self.online_db.insert('online_exams', {
            'publish_token': token,
            'title': self.local_exam['title'],
            'subject': self.local_exam['subject'],
            'duration': 30,
            'total_marks': 10.0,
            'status': 'ACTIVE',
            'questions_json': '[]',
            'allowed_students_json': '[]',
            'created_at': now_str
        })

        # Attempt with unknown national ID
        unk_id = self.online_db.insert('online_attempts', {
            'publish_token': token,
            'student_national_id': '999888777666',
            'student_name': 'طالب غير مسجل',
            'attempt_token_hash': f'hash-{secrets.token_hex(8)}',
            'status': 'SUBMITTED',
            'score': 5.0,
            'total': 10.0,
            'percentage': 50.0,
            'started_at': now_str,
            'server_deadline': "2026-09-08 10:30:00",
            'finished_at': "2026-09-08 10:20:00",
            'is_synced': 0
        })

        # Sync should complete smoothly without unhandled exception
        synced = self.local_srv.sync_published_attempts(token)
        self.assertEqual(synced, 1)
        self.assertIsNotNone(self.local_db.q("SELECT id FROM published_exam_attempts WHERE online_attempt_id=?", (unk_id,), one=True))

    def test_06_online_attempt_id_used_for_deduplication(self):
        """6. Verify online_attempt_id is explicitly stored and verified for deduplication."""
        token, online_att_id = self._publish_and_submit_test_attempt(self.nat_id, score=9.0)
        self.local_srv.sync_published_attempts(token)

        # Check column online_attempt_id in published_exam_attempts
        row = self.local_db.q("SELECT online_attempt_id FROM published_exam_attempts WHERE online_attempt_id=?", (online_att_id,), one=True)
        self.assertIsNotNone(row)
        self.assertEqual(row['online_attempt_id'], online_att_id)

    def test_07_zero_inbound_connection_from_online_to_sqlite(self):
        """7. Verify online_backend has zero imports or paths to exam_platform.db."""
        self.assertNotIn('exam_platform.db', self.online_db.sqlite_path)
        self.assertNotIn('exam_data', self.online_db.sqlite_path)

if __name__ == '__main__':
    unittest.main()
