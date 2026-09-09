# -*- coding: utf-8 -*-
"""
PHASE 8 Production E2E Verification
Validates the complete end-to-end lifecycle in a single deterministic test:
Teacher Publish
→ Firebase Student Start
→ Answer/Autosave
→ Submit (Server Grading)
→ Teacher Close & Sync
→ Local Result in SQLite
→ Safe Cloud Purge
"""
import unittest, os, sys, json, secrets, importlib.util
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import app as local_app_module

ONLINE_DIR = BASE_DIR / 'online_backend'
spec = importlib.util.spec_from_file_location('online_backend_p8', str(ONLINE_DIR / 'app.py'))
online_app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(online_app_module)

class TestPhase8ProductionE2E(unittest.TestCase):

    def setUp(self):
        self.local_db = local_app_module.db
        self.local_srv = local_app_module.srv
        self.online_app = online_app_module.app
        self.online_db = online_app_module.db
        self.online_client = self.online_app.test_client()
        self.secret = online_app_module.TEACHER_ONLINE_SECRET
        self.auth_headers = {'Authorization': f'Bearer {self.secret}'}

        # Bridge call
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

        self.local_exam = self.local_db.q("SELECT e.* FROM exams e JOIN exam_questions eq ON e.id = eq.exam_id WHERE e.active = 1 LIMIT 1", one=True)
        self.local_student = self.local_db.q('''
            SELECT s.* FROM students s
            JOIN student_subjects ss ON s.id = ss.student_id
            WHERE ss.subject_id = ? AND s.active = 1
            LIMIT 1
        ''', (self.local_exam['subject_id'],), one=True)
        if self.local_student:
            self.online_db.x('DELETE FROM online_attempts WHERE student_national_id=?', (self.local_student['national_id'],))
        # Clear prior staging for this exam to ensure fresh single cycle
        self.local_db.x('DELETE FROM published_exams WHERE local_exam_id=?', (self.local_exam['id'],))
        self.online_db.x('DELETE FROM online_exams WHERE idempotency_key=?', (f"EXAMORA-LOCAL-EXAM-{self.local_exam['id']}",))

    def tearDown(self):
        self.local_srv._call_online_api = self.orig_call

    def test_complete_production_e2e_cycle(self):
        """Single comprehensive test validating entire teacher-student-cloud lifecycle."""
        # STEP 1: Teacher Publish
        pub_res = self.local_srv.publish_exam_online(self.local_exam['id'], actor='TeacherAwadh')
        self.assertTrue(pub_res['publish_token'])
        token = pub_res['publish_token']
        self.assertIn('https://yt-c-c.web.app/#/e/', pub_res['web_link'])

        # Verify local status
        pub_tracked = self.local_db.q("SELECT * FROM published_exams WHERE publish_token=?", (token,), one=True)
        self.assertEqual(pub_tracked['status'], 'ACTIVE')

        # STEP 2: Firebase Student Start
        start_res = self.online_client.post('/api/public/exam/start', json_data={
            'national_id': self.local_student['national_id'],
            'publish_token': token
        })
        self.assertEqual(start_res.status_code, 200)
        start_data = start_res.get_json()
        att_id = start_data['attempt_id']
        raw_att_token = start_data['attempt_token']
        self.assertTrue(raw_att_token)
        # Verify ZERO leak of correct answers
        for q in start_data['questions']:
            self.assertNotIn('correct', q)
            self.assertNotIn('correct_option', q)
            self.assertNotIn('answer_key', q)

        # STEP 3: Autosave
        q1_id = start_data['questions'][0]['id']
        save_res = self.online_client.post('/api/public/exam/autosave', json_data={
            'attempt_id': att_id,
            'question_id': q1_id,
            'answer': 'أ'
        }, headers={'X-Attempt-Token': raw_att_token})
        self.assertEqual(save_res.status_code, 200)
        self.assertTrue(save_res.get_json()['ok'])

        # STEP 4: Submit (Server-Side Grading)
        sub_res = self.online_client.post('/api/public/exam/submit', json_data={
            'attempt_id': att_id,
            'answers': {str(q1_id): 'أ'}
        }, headers={'X-Attempt-Token': raw_att_token})
        self.assertEqual(sub_res.status_code, 200)
        sub_data = sub_res.get_json()
        self.assertTrue(sub_data['ok'])
        self.assertIn('score', sub_data)
        self.assertIn('tier', sub_data)

        # STEP 5: Teacher Close & Sync
        closed = self.local_srv.close_published_exam(token, actor='TeacherAwadh')
        self.assertTrue(closed)

        synced_count = self.local_srv.sync_published_attempts(token, actor='TeacherAwadh')
        self.assertEqual(synced_count, 1)

        # STEP 6: Local Result in SQLite
        staged_att = self.local_db.q("SELECT * FROM published_exam_attempts WHERE online_attempt_id=?", (att_id,), one=True)
        self.assertIsNotNone(staged_att)
        self.assertEqual(staged_att['student_national_id'], self.local_student['national_id'])

        official_att = self.local_db.q("SELECT * FROM attempts WHERE exam_id=? AND student_id=? ORDER BY id DESC LIMIT 1", (self.local_exam['id'], self.local_student['id']), one=True)
        self.assertIsNotNone(official_att)
        self.assertEqual(official_att['status'], 'SUBMITTED')

        # STEP 7: Safe Cloud Purge
        purged = self.local_srv.purge_published_exam(token, actor='TeacherAwadh')
        self.assertTrue(purged)

        # Confirm wiped on cloud
        self.assertIsNone(self.online_db.q("SELECT id FROM online_exams WHERE publish_token=?", (token,), one=True))
        # Confirm preserved on local SQLite
        preserved = self.local_db.q("SELECT * FROM attempts WHERE id=?", (official_att['id'],), one=True)
        self.assertIsNotNone(preserved)
        self.assertEqual(preserved['id'], official_att['id'])

if __name__ == '__main__':
    unittest.main()
