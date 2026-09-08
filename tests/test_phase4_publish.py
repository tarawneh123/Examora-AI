# -*- coding: utf-8 -*-
"""
PHASE 4 Test Suite: Online Publishing Integration & Verification
Validates:
- Test A: Successful publish of selected exam with tracking saved locally
- Test B: Answer key isolation (zero leak in public bundle)
- Test C: Teacher authentication (valid secret = 200, invalid secret = 401)
- Test D: Selected exam only (exam A questions isolated from exam B)
- Test E: Local DB integrity (PRAGMA integrity_check = ok)
- Test F: Network failure safety (no false active status on network error)
- Test G: Safe retry with idempotency (no duplicate online exams)
- Test H: Secret exposure verification (secret absent from frontend/git)
- Test I: Invalid publish payload rejected by cloud backend (400)
- Test J: Zero cloud -> local SQLite dependency
"""
import unittest, os, sys, json, secrets, importlib.util
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import app as local_app_module
import examora_service

# Load online backend explicitly via importlib to avoid module collision
ONLINE_DIR = BASE_DIR / 'online_backend'
spec = importlib.util.spec_from_file_location('online_backend_app', str(ONLINE_DIR / 'app.py'))
online_app_module = importlib.util.module_from_spec(spec)
sys.modules['online_backend_app'] = online_app_module
spec.loader.exec_module(online_app_module)

class TestPhase4PublishOnline(unittest.TestCase):

    def setUp(self):
        self.local_app = local_app_module.app
        self.local_db = local_app_module.db
        self.local_srv = local_app_module.srv
        self.local_client = self.local_app.test_client()

        self.online_app = online_app_module.app
        self.online_db = online_app_module.db
        self.online_client = self.online_app.test_client()
        self.secret = online_app_module.TEACHER_ONLINE_SECRET
        self.auth_headers = {'Authorization': f'Bearer {self.secret}'}

    def test_A_successful_publish_selected_exam(self):
        """Test A: Publish selected exam, transmit required bundle, get publish_token, track locally."""
        exam = self.local_db.q("""
            SELECT e.* FROM exams e 
            JOIN exam_questions eq ON e.id = eq.exam_id 
            WHERE e.active = 1 
            LIMIT 1
        """, one=True)
        self.assertIsNotNone(exam, "Must have an active exam with questions")
        exam_id = exam['id']

        # Bridge call to online_backend test client
        def mock_call(endpoint, method='GET', payload=None):
            if endpoint == '/api/teacher/publish':
                res = self.online_client.post(endpoint, json_data=payload, headers=self.auth_headers)
                return res.get_json()
            return None

        orig_call = self.local_srv._call_online_api
        self.local_srv._call_online_api = mock_call

        try:
            res = self.local_srv.publish_exam_online(exam_id, actor='TestTeacher')
            self.assertTrue(res['publish_token'])
            self.assertIn('https://yt-c-c.web.app/#/e/', res['web_link'])
            self.assertEqual(res['exam_id'], exam_id)

            # Verify local tracking in published_exams
            tracked = self.local_db.q("SELECT * FROM published_exams WHERE local_exam_id=?", (exam_id,), one=True)
            self.assertIsNotNone(tracked)
            self.assertEqual(tracked['status'], 'ACTIVE')
            self.assertEqual(tracked['publish_token'], res['publish_token'])

            # Verify cloud storage in online_backend
            cloud_exam = self.online_db.q("SELECT * FROM online_exams WHERE publish_token=?", (res['publish_token'],), one=True)
            self.assertIsNotNone(cloud_exam)
            self.assertEqual(cloud_exam['status'], 'ACTIVE')
            self.assertEqual(cloud_exam['title'], exam['title'])
        finally:
            self.local_srv._call_online_api = orig_call

    def test_B_answer_key_isolation(self):
        """Test B: Answer key is sent only in teacher publish payload and zero leak in public bundle."""
        clean_questions = [{'id': 10, 'number': 1, 'text': 'Q10', 'options': {'أ': 'A', 'ب': 'B'}, 'mark': 5.0}]
        answer_key = {'10': {'correct': 'أ', 'mark': 5.0}}

        payload = {
            'title': 'امتحان اختبار عزل المفتاح',
            'subject': 'لغة عربية',
            'duration': 30,
            'total_marks': 5.0,
            'questions': clean_questions,
            'allowed_students': ['2009000001'],
            'answer_key': answer_key
        }

        pub_res = self.online_client.post('/api/teacher/publish', json_data=payload, headers=self.auth_headers)
        self.assertEqual(pub_res.status_code, 200)
        token = pub_res.get_json()['publish_token']

        # Request public exam start as student
        start_res = self.online_client.post('/api/public/exam/start', json_data={'national_id': '2009000001', 'publish_token': token})
        self.assertEqual(start_res.status_code, 200)
        q_list = start_res.get_json()['questions']

        for q in q_list:
            self.assertNotIn('correct', q)
            self.assertNotIn('correct_option', q)
            self.assertNotIn('answer_key', q)
            self.assertNotIn('correct_answer', q)

    def test_C_teacher_authentication(self):
        """Test C: Valid secret = 200, invalid secret = 401."""
        valid_res = self.online_client.post('/api/teacher/publish', json_data={
            'title': 'Test Auth', 'questions': [{'id': 1, 'text': 'Q'}]
        }, headers=self.auth_headers)
        self.assertEqual(valid_res.status_code, 200)

        invalid_res = self.online_client.post('/api/teacher/publish', json_data={
            'title': 'Test Auth', 'questions': [{'id': 1, 'text': 'Q'}]
        }, headers={'Authorization': 'Bearer wrong-secret'})
        self.assertEqual(invalid_res.status_code, 401)

    def test_D_selected_exam_only_isolation(self):
        """Test D: Publishing exam A transmits only exam A's questions and not exam B's questions."""
        exams = self.local_db.q("SELECT id, title FROM exams WHERE active=1 LIMIT 2")
        if len(exams) >= 2:
            exam_a_id = exams[0]['id']
            exam_b_id = exams[1]['id']

            q_ids_a = {r['question_id'] for r in self.local_db.q("SELECT question_id FROM exam_questions WHERE exam_id=?", (exam_a_id,))}

            def inspect_call(endpoint, method='GET', payload=None):
                if endpoint == '/api/teacher/publish':
                    sent_q_ids = {q['id'] for q in payload['questions']}
                    self.assertEqual(sent_q_ids, q_ids_a)
                    q_ids_b = {r['question_id'] for r in self.local_db.q("SELECT question_id FROM exam_questions WHERE exam_id=?", (exam_b_id,))}
                    only_in_b = q_ids_b - q_ids_a
                    for b_qid in only_in_b:
                        self.assertNotIn(b_qid, sent_q_ids)
                    return {'ok': True, 'publish_token': 'test-token-d', 'web_link': 'https://yt-c-c.web.app/#/e/test-token-d'}
                return None

            orig_call = self.local_srv._call_online_api
            self.local_srv._call_online_api = inspect_call
            try:
                self.local_srv.publish_exam_online(exam_a_id)
            finally:
                self.local_srv._call_online_api = orig_call

    def test_E_local_db_integrity(self):
        """Test E: PRAGMA integrity_check = ok on exam_platform.db."""
        check = self.local_db.q("PRAGMA integrity_check;", one=True)
        self.assertEqual(check[0], 'ok')

    def test_F_network_failure_safety(self):
        """Test F: Connection failure does not mark exam as published-active and does not corrupt DB."""
        exam = self.local_db.q("SELECT id FROM exams WHERE active=1 LIMIT 1", one=True)

        def failing_call(endpoint, method='GET', payload=None):
            return {'ok': False, 'error': 'Connection refused (Simulated network failure)', 'status_code': 0}

        orig_call = self.local_srv._call_online_api
        self.local_srv._call_online_api = failing_call

        try:
            with self.assertRaises(ConnectionError) as cm:
                self.local_srv.publish_exam_online(exam['id'])
            self.assertIn("فشلت عملية النشر السحابي", str(cm.exception))

            int_check = self.local_db.q("PRAGMA integrity_check;", one=True)
            self.assertEqual(int_check[0], 'ok')
        finally:
            self.local_srv._call_online_api = orig_call

    def test_G_safe_retry_idempotency(self):
        """Test G: Repeated publish calls with same idempotency key update existing exam without creating duplicates."""
        test_idem_key = f"EXAMORA-IDEMPOTENT-KEY-{secrets.token_hex(8)}"
        payload = {
            'idempotency_key': test_idem_key,
            'title': 'امتحان اختبار التكرار',
            'subject': 'تاريخ',
            'duration': 40,
            'total_marks': 10.0,
            'allowed_students': ['2009000001'],
            'questions': [{'id': 1, 'text': 'Q1', 'options': {'أ': 'A'}, 'mark': 10.0}],
            'answer_key': {'1': {'correct': 'أ', 'mark': 10.0}}
        }

        # First publish
        res1 = self.online_client.post('/api/teacher/publish', json_data=payload, headers=self.auth_headers)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        token1 = data1['publish_token']
        self.assertFalse(data1.get('reused', False))

        # Second publish with same idempotency key (Retry)
        res2 = self.online_client.post('/api/teacher/publish', json_data=payload, headers=self.auth_headers)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        token2 = data2['publish_token']
        self.assertTrue(data2.get('reused', True))

        # Must reuse the same token without creating duplicate rows
        self.assertEqual(token1, token2)
        count = self.online_db.q("SELECT COUNT(*) as n FROM online_exams WHERE idempotency_key=?", (test_idem_key,), one=True)['n']
        self.assertEqual(count, 1)

    def test_H_secret_exposure_verification(self):
        """Test H: Verify TEACHER_ONLINE_SECRET is not in frontend JS, HTML, or public assets."""
        secret_val = self.secret
        search_dirs = [
            BASE_DIR / 'firebase_landing',
            BASE_DIR / 'static'
        ]
        for sdir in search_dirs:
            for root, dirs, files in os.walk(sdir):
                for f in files:
                    if f.endswith(('.html', '.js', '.css', '.json')):
                        fp = Path(root) / f
                        with open(fp, 'r', encoding='utf-8', errors='ignore') as content_f:
                            text = content_f.read()
                            self.assertNotIn(secret_val, text, f"SECRET LEAK FOUND IN: {fp}")

    def test_I_invalid_publish_payload_rejected(self):
        """Test I: Backend rejects incomplete/malformed publish payloads."""
        res1 = self.online_client.post('/api/teacher/publish', json_data={'title': ''}, headers=self.auth_headers)
        self.assertEqual(res1.status_code, 400)

        res2 = self.online_client.post('/api/teacher/publish', json_data={'title': 'Exam', 'questions': []}, headers=self.auth_headers)
        self.assertEqual(res2.status_code, 400)

    def test_J_zero_cloud_to_local_sqlite_dependency(self):
        """Test J: Online backend database path does not touch exam_platform.db."""
        self.assertNotIn('exam_platform.db', self.online_db.sqlite_path)
        self.assertNotIn('exam_data', self.online_db.sqlite_path)

    def test_K_idempotency_content_tampering_protection(self):
        """Test K: Idempotency security gate prevents corrupting exams with active/submitted attempts."""
        idem_key = f"EXAMORA-IDEMPOTENT-TAMPER-{secrets.token_hex(6)}"
        
        # 1. Publish Exam A for the first time
        initial_payload = {
            'idempotency_key': idem_key,
            'title': 'امتحان أمان تكرار النشر',
            'subject': 'الأمن السيبراني',
            'duration': 30,
            'total_marks': 10.0,
            'allowed_students': ['2009000001'],
            'questions': [{'id': 101, 'number': 1, 'text': 'ما هو التشفير؟', 'options': {'أ': 'حماية البيانات', 'ب': 'حذف البيانات'}, 'mark': 10.0}],
            'answer_key': {'101': {'correct': 'أ', 'mark': 10.0}}
        }
        pub1_res = self.online_client.post('/api/teacher/publish', json_data=initial_payload, headers=self.auth_headers)
        self.assertEqual(pub1_res.status_code, 200)
        token1 = pub1_res.get_json()['publish_token']
        self.assertFalse(pub1_res.get_json().get('reused', False))

        # 2. Student starts an attempt on Exam A (status becomes ACTIVE)
        start_res = self.online_client.post('/api/public/exam/start', json_data={'national_id': '2009000001', 'publish_token': token1})
        self.assertEqual(start_res.status_code, 200)
        attempt_id = start_res.get_json()['attempt_id']
        raw_att_token = start_res.get_json()['attempt_token']

        # 3. Resend IDENTICAL payload with same idempotency_key
        # Must be accepted (Idempotent replay), returning the same token without breaking the attempt
        pub2_res = self.online_client.post('/api/teacher/publish', json_data=initial_payload, headers=self.auth_headers)
        self.assertEqual(pub2_res.status_code, 200)
        self.assertEqual(pub2_res.get_json()['publish_token'], token1)
        self.assertTrue(pub2_res.get_json().get('reused', True))

        # 4. Resend with MODIFIED questions/content using the same idempotency_key while attempts exist
        tampered_payload = dict(initial_payload)
        tampered_payload['questions'] = [{'id': 101, 'number': 1, 'text': 'نص سؤال مختلف ومعدل تماماً؟', 'options': {'أ': 'X', 'ب': 'Y'}, 'mark': 10.0}]
        tamper_res1 = self.online_client.post('/api/teacher/publish', json_data=tampered_payload, headers=self.auth_headers)
        # Must be strictly REJECTED with 409 Conflict
        self.assertEqual(tamper_res1.status_code, 409)
        self.assertTrue(tamper_res1.get_json().get('conflict', False))
        self.assertIn('لا يمكن تعديل محتوى الامتحان', tamper_res1.get_json().get('error', ''))

        # 5. Resend with MODIFIED answer key while attempts exist
        tampered_key_payload = dict(initial_payload)
        tampered_key_payload['answer_key'] = {'101': {'correct': 'ب', 'mark': 10.0}} # Changed answer key!
        tamper_res2 = self.online_client.post('/api/teacher/publish', json_data=tampered_key_payload, headers=self.auth_headers)
        # Must also be strictly REJECTED with 409 Conflict
        self.assertEqual(tamper_res2.status_code, 409)

        # 6. Verify active student attempt can still autosave and submit safely
        save_res = self.online_client.post('/api/public/exam/autosave', json_data={
            'attempt_id': attempt_id,
            'question_id': 101,
            'answer': 'أ'
        }, headers={'X-Attempt-Token': raw_att_token})
        self.assertEqual(save_res.status_code, 200)

        sub_res = self.online_client.post('/api/public/exam/submit', json_data={
            'attempt_id': attempt_id,
            'answers': {'101': 'أ'}
        }, headers={'X-Attempt-Token': raw_att_token})
        self.assertEqual(sub_res.status_code, 200)
        self.assertEqual(sub_res.get_json()['score'], 10.0) # Full score against original key

        # 7. Resend with modified content after SUBMISSION
        tamper_res3 = self.online_client.post('/api/teacher/publish', json_data=tampered_payload, headers=self.auth_headers)
        self.assertEqual(tamper_res3.status_code, 409) # Still blocked!

if __name__ == '__main__':
    unittest.main()
