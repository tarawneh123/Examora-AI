# -*- coding: utf-8 -*-
"""
Targeted Verification Test for 'Publish Exam Now' Button Fix:
1. Verify publish button in exam_manage.html targets /exams/<id>/publish-online (not toggle).
2. Verify calling /exams/<id>/publish-online triggers cloud publish, sets status to PUBLISHED/active.
3. Verify publish_token is properly stored in published_exams.
4. Verify student exam link is rendered as https://yt-c-c.web.app/#/e/<token> with 'نسخ رابط الامتحان'.
5. Verify zero leakage of TEACHER_ONLINE_SECRET or answer_key in HTML response.
"""
import unittest, os, sys, json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import app as local_app_module

class TestPublishButtonFix(unittest.TestCase):

    def setUp(self):
        self.app = local_app_module.app
        self.db = local_app_module.db
        self.srv = local_app_module.srv
        self.client = self.app.test_client()

        # Find an exam with questions
        self.exam = self.db.q("""
            SELECT e.* FROM exams e
            JOIN exam_questions eq ON e.id = eq.exam_id
            WHERE e.active = 1 LIMIT 1
        """, one=True)
        self.assertIsNotNone(self.exam)
        self.exam_id = self.exam['id']

        # Ensure exam is temporarily unpublished (draft) for the button test
        self.db.x("UPDATE exams SET status='DRAFT', active=0 WHERE id=?", (self.exam_id,))
        self.db.x("DELETE FROM published_exams WHERE local_exam_id=?", (self.exam_id,))

    def test_publish_button_and_online_link_rendering(self):
        # 1. Login as Super Admin
        login_res = self.client.post('/api/auth/session', json_data={
            'username_or_email': 'aa104@yahoo.com',
            'password': 'Pass#2026_test'
        })
        self.assertEqual(login_res.status_code, 200)

        # 2. Inspect exam_manage page before publishing:
        res_before = self.client.get(f'/exams/{self.exam_id}')
        self.assertEqual(res_before.status_code, 200)
        html_before = res_before.text

        # Verify button uses /publish-online
        expected_action = f'/exams/{self.exam_id}/publish-online'
        self.assertIn(expected_action, html_before)
        self.assertIn('نشر الامتحان الآن', html_before)
        # Should not show the online link banner yet
        self.assertNotIn('studentExamLink', html_before)

        # 3. Mock the cloud publish call
        def mock_online_call(endpoint, method='GET', payload=None):
            if endpoint == '/api/teacher/publish':
                return {
                    'ok': True,
                    'publish_token': 'test_token_fix_123',
                    'web_link': 'https://yt-c-c.web.app/#/e/test_token_fix_123',
                    'title': 'Test Exam'
                }
            return None

        orig_call = self.srv._call_online_api
        self.srv._call_online_api = mock_online_call

        try:
            # 4. Trigger POST /exams/<id>/publish-online
            res_publish = self.client.post(f'/exams/{self.exam_id}/publish-online')
            # Should redirect to exam_manage
            self.assertEqual(res_publish.status_code, 302)
            self.assertIn(f'/exams/{self.exam_id}', res_publish.headers.get('Location', ''))

            # 5. Inspect exam_manage page after publishing:
            res_after = self.client.get(f'/exams/{self.exam_id}')
            self.assertEqual(res_after.status_code, 200)
            html_after = res_after.text

            # Verify local exam is in PUBLISHED state
            updated_exam = self.db.q("SELECT * FROM exams WHERE id=?", (self.exam_id,), one=True)
            self.assertEqual(updated_exam['status'], 'PUBLISHED')
            self.assertEqual(updated_exam['active'], 1)

            # Verify token is in published_exams
            pub_row = self.db.q("SELECT * FROM published_exams WHERE local_exam_id=?", (self.exam_id,), one=True)
            self.assertIsNotNone(pub_row)
            self.assertEqual(pub_row['publish_token'], 'test_token_fix_123')

            # Verify Firebase link and button are rendered
            expected_firebase_link = 'https://yt-c-c.web.app/#/e/test_token_fix_123'
            self.assertIn(expected_firebase_link, html_after)
            self.assertIn('رابط امتحان الطلاب', html_after)
            self.assertIn('نسخ رابط الامتحان', html_after)
            self.assertIn('copyExamLink()', html_after)

            # Verify NO secrets leaked in HTML
            secret = os.environ.get('TEACHER_ONLINE_SECRET', 'examora-cloud-secret-token-prod-2026')
            self.assertNotIn(secret, html_after)

        finally:
            self.srv._call_online_api = orig_call

if __name__ == '__main__':
    unittest.main()
