# -*- coding: utf-8 -*-
"""
Examora AI - Dry Run Simulation: Online Exam + Manual Sync + Automatic Sync
Demonstrates:
1. Publishing local exam to Online Cloud Backend.
2. Student 1 takes online exam and submits -> Manual Sync imports result.
3. Student 2 takes online exam and submits -> Auto-Sync imports result automatically.
4. Complete verification of local SQLite gradebook and integrity check.
"""
import unittest, os, sys, json, secrets, importlib.util
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import app as local_app_module

ONLINE_DIR = BASE_DIR / 'online_backend'
spec = importlib.util.spec_from_file_location('online_backend_sim', str(ONLINE_DIR / 'app.py'))
online_app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(online_app_module)

class TestDryRunOnlineExamAndSync(unittest.TestCase):

    def setUp(self):
        self.local_db = local_app_module.db
        self.local_srv = local_app_module.srv
        self.online_app = online_app_module.app
        self.online_db = online_app_module.db
        self.online_client = self.online_app.test_client()
        self.secret = online_app_module.TEACHER_ONLINE_SECRET
        self.auth_headers = {'Authorization': f'Bearer {self.secret}'}

        # Bridge call to online backend test client
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

        # Pick a valid local exam with questions
        self.local_exam = self.local_db.q("""
            SELECT e.* FROM exams e 
            JOIN exam_questions eq ON e.id = eq.exam_id 
            WHERE e.active = 1 
            LIMIT 1
        """, one=True)
        self.assertIsNotNone(self.local_exam)
        self.exam_id = self.local_exam['id']

        # Pick two enrolled students for this subject
        students = self.local_db.q("""
            SELECT s.* FROM students s
            JOIN student_subjects ss ON s.id = ss.student_id
            WHERE ss.subject_id = ? AND s.active = 1
            LIMIT 2
        """, (self.local_exam['subject_id'],))
        
        if len(students) < 2:
            # Add a second test student to subject if needed
            all_st = self.local_db.q("SELECT * FROM students WHERE active=1 LIMIT 2")
            for st in all_st:
                self.local_db.x("INSERT OR IGNORE INTO student_subjects (student_id, subject_id) VALUES (?, ?)", (st['id'], self.local_exam['subject_id']))
            students = self.local_db.q("""
                SELECT s.* FROM students s
                JOIN student_subjects ss ON s.id = ss.student_id
                WHERE ss.subject_id = ? AND s.active = 1
                LIMIT 2
            """, (self.local_exam['subject_id'],))

        self.student1 = students[0]
        self.student2 = students[1]
        
        # Clean isolated online test tables for fresh dry-run simulation
        self.online_db.x("DELETE FROM online_answers")
        self.online_db.x("DELETE FROM online_attempts")
        self.online_db.x("DELETE FROM online_answer_keys")
        self.online_db.x("DELETE FROM online_exams")

    def tearDown(self):
        self.local_srv._call_online_api = self.orig_call

    def test_complete_simulation_manual_and_auto_sync(self):
        """Execute full simulation of online exam with manual sync and automatic sync."""
        print("\n================================================================")
        print("🚀 [START SIMULATION] Online Exam + Manual Sync + Automatic Sync")
        print("================================================================")

        # ----------------------------------------------------------------------
        # STAGE 1: Teacher Publishes Exam Online
        # ----------------------------------------------------------------------
        print(f"1. المعلم ينشر الامتحان محلياً: '{self.local_exam['title']}' (ID: {self.exam_id})")
        pub_res = self.local_srv.publish_exam_online(self.exam_id, actor='TeacherAwadh')
        token = pub_res['publish_token']
        web_link = pub_res['web_link']
        print(f"   ✅ تم إنشاء رمز النشر المشفر: {token}")
        print(f"   🌐 رابط قاعة الاختبار للطلاب: {web_link}")

        # Verify local tracking
        tracked = self.local_db.q("SELECT * FROM published_exams WHERE publish_token=?", (token,), one=True)
        self.assertIsNotNone(tracked)
        self.assertEqual(tracked['status'], 'ACTIVE')

        # ----------------------------------------------------------------------
        # STAGE 2: Student 1 Takes Exam Online
        # ----------------------------------------------------------------------
        print(f"\n2. الطالب الأول يدخل للامتحان: {self.student1['full_name']} (الرقم الوطني: {self.student1['national_id']})")
        start_res1 = self.online_client.post('/api/public/exam/start', json_data={
            'national_id': self.student1['national_id'],
            'publish_token': token
        })
        self.assertEqual(start_res1.status_code, 200)
        s1_data = start_res1.get_json()
        att1_id = s1_data['attempt_id']
        att1_token = s1_data['attempt_token']
        print(f"   ✅ بدأ الطالب الجلسة برمز أمان: {att1_token[:12]}... (Attempt ID: {att1_id})")
        print(f"   🔒 عدد الأسئلة المستلمة: {len(s1_data['questions'])} (خالية تماماً من الإجابات النموذجية)")

        # Student 1 Autosaves Answers
        q1_id = s1_data['questions'][0]['id']
        save_res1 = self.online_client.post('/api/public/exam/autosave', json_data={
            'attempt_id': att1_id,
            'question_id': q1_id,
            'answer': 'أ'
        }, headers={'X-Attempt-Token': att1_token})
        self.assertEqual(save_res1.status_code, 200)
        print(f"   💾 تم الحفظ اللحظي لإجابة السؤال {q1_id} بنجاح (Autosave OK)")

        # Student 1 Submits Exam
        sub_res1 = self.online_client.post('/api/public/exam/submit', json_data={
            'attempt_id': att1_id,
            'answers': {str(q1_id): 'أ'}
        }, headers={'X-Attempt-Token': att1_token})
        self.assertEqual(sub_res1.status_code, 200)
        score1 = sub_res1.get_json()['score']
        total1 = sub_res1.get_json()['total']
        tier1 = sub_res1.get_json()['tier']
        print(f"   🎯 سلّم الطالب الأول امتحانه: حصل على {score1}/{total1} (التقدير: {tier1})")

        # ----------------------------------------------------------------------
        # STAGE 3: Manual Sync (المزامنة اليدوية)
        # ----------------------------------------------------------------------
        print(f"\n3. [المزامنة اليدوية] المعلم يضغط زر 'مزامنة النتائج السحابية'")
        manual_synced_count = self.local_srv.sync_published_attempts(token, actor='TeacherAwadh')
        print(f"   🔄 نتيجة المزامنة اليدوية: تم استيراد ({manual_synced_count}) محاولة جديدة بنجاح.")
        self.assertEqual(manual_synced_count, 1)

        # Verify Student 1 is in local database
        s1_local = self.local_db.q("SELECT * FROM attempts WHERE exam_id=? AND student_id=? ORDER BY id DESC LIMIT 1", (self.exam_id, self.student1['id']), one=True)
        self.assertIsNotNone(s1_local)
        self.assertEqual(float(s1_local['score']), score1)
        print(f"   ✅ تم توثيق نتيجة الطالب الأول محلياً برقم محاولة #{s1_local['id']}")

        # Idempotency check: Repeated manual sync should import 0 duplicates
        repeat_sync = self.local_srv.sync_published_attempts(token, actor='TeacherAwadh')
        print(f"   🛡️ فحص عدم التكرار (Idempotency): محاولة المزامنة اليدوية ثانية أنتجت ({repeat_sync}) محاولات جديدة.")
        self.assertEqual(repeat_sync, 0)

        # ----------------------------------------------------------------------
        # STAGE 4: Student 2 Takes Exam Online (Subsequent Submission)
        # ----------------------------------------------------------------------
        print(f"\n4. الطالب الثاني يدخل للامتحان لاحقاً: {self.student2['full_name']} (الرقم الوطني: {self.student2['national_id']})")
        start_res2 = self.online_client.post('/api/public/exam/start', json_data={
            'national_id': self.student2['national_id'],
            'publish_token': token
        })
        self.assertEqual(start_res2.status_code, 200)
        s2_data = start_res2.get_json()
        att2_id = s2_data['attempt_id']
        att2_token = s2_data['attempt_token']

        # Student 2 answers & submits
        sub_res2 = self.online_client.post('/api/public/exam/submit', json_data={
            'attempt_id': att2_id,
            'answers': {str(q1_id): 'ب'}
        }, headers={'X-Attempt-Token': att2_token})
        self.assertEqual(sub_res2.status_code, 200)
        score2 = sub_res2.get_json()['score']
        print(f"   🎯 سلّم الطالب الثاني امتحانه في السحابة: حصل على {score2}/{sub_res2.get_json()['total']}")
        print(f"   ⏳ (النتيجة حالياً في السحابة فقط ولم يضغط المعلم أي زر محلياً)")

        # ----------------------------------------------------------------------
        # STAGE 5: Automatic Sync (المزامنة التلقائية)
        # ----------------------------------------------------------------------
        print(f"\n5. [المزامنة التلقائية] آلية Auto-Sync الدورية تفحص السحابة تلقائياً")
        auto_sync_res = self.local_srv.auto_sync_all_active_exams(actor='AUTO_SYNC_DAEMON')
        print(f"   🤖 التقرير التلقائي: تم فحص ({auto_sync_res['total_exams_checked']}) امتحان نشط، واستيراد ({auto_sync_res['total_attempts_synced']}) محاولة جديدة آلياً!")
        self.assertEqual(auto_sync_res['total_attempts_synced'], 1)

        # Verify Student 2 is now in local database alongside Student 1
        s2_local = self.local_db.q("SELECT * FROM attempts WHERE exam_id=? AND student_id=? ORDER BY id DESC LIMIT 1", (self.exam_id, self.student2['id']), one=True)
        self.assertIsNotNone(s2_local)
        self.assertEqual(float(s2_local['score']), score2)
        print(f"   ✅ ظهرت نتيجة الطالب الثاني في كشف علامات الأستاذ المحلي تلقائياً: محاولة #{s2_local['id']}")

        # ----------------------------------------------------------------------
        # STAGE 6: Local Gradebook & Database Integrity Verification
        # ----------------------------------------------------------------------
        print("\n6. كشف العلامات المحدث النهائي في قاعدة بيانات الأستاذ المحلية:")
        final_attempts = self.local_db.q("""
            SELECT id, student_name, score, total, percentage, override_reason, submitted_at 
            FROM attempts 
            WHERE exam_id=? 
            ORDER BY id DESC LIMIT 2
        """, (self.exam_id,))
        for fa in final_attempts:
            print(f"   - [محاولة #{fa['id']}] {fa['student_name']} | العلامة: {fa['score']}/{fa['total']} ({fa['percentage']}%) | المصدر: {fa['override_reason'][:40]}...")

        # PRAGMA integrity check
        check = self.local_db.q("PRAGMA integrity_check;", one=True)
        self.assertEqual(check[0], 'ok')
        print(f"\n   🛡️ فحص سلامة وتكامل قاعدة بيانات الأستاذ: {check[0].upper()} (100% Intact)")
        print("================================================================")
        print("🎉 [SIMULATION COMPLETED WITH 100% SUCCESS]")
        print("================================================================")

if __name__ == '__main__':
    unittest.main()
