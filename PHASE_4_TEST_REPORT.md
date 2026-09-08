# تقرير اختبارات المرحلة الرابعة: نشر الامتحان أونلاين (PHASE 4 TEST REPORT)
**المشروع:** Examora AI — Publish Online Integration  
**المرحلة:** PHASE 4 — PUBLISH ONLINE  
**التاريخ:** 2026-09-08  
**المبدأ غير القابل للتغيير:** `LOCAL DATABASE ≠ ONLINE DATABASE` (عزل تام لقاعدة بيانات الأستاذ)

---

## 1. ما تم تنفيذه والملفات المعدلة

### أ. ما تم تنفيذه:
1. تفعيل وظيفة نشر امتحان محدد من برنامج الأستاذ المحلي إلى السحابة عبر قناة موثقة ومشفرة.
2. عزل وحذف الإجابات الصحيحة تماماً من حزمة الأسئلة العامة المنشورة للطلاب.
3. حصر قائمة المتقدمين بالطلاب المسجلين رسمياً في المبحث (`student_subjects`).
4. عزل مفتاح الإجابة السري في جدول سحابي خاص بالخادم (`online_answer_keys`) للتصحيح الخادمي الحصري.
5. تطبيق آلية عدم التكرار (Strict Idempotency Key) لمنع إنشاء امتحانات مكررة عند الضغط المتكرر على زر النشر.
6. حماية قاعدة البيانات المحلية من أخطاء وانقطاعات الشبكة (عدم تغيير حالة النشر إلى `ACTIVE` محلياً إلا بعد تأكيد الخادم السحابي بنجاح العملية).
7. إنشاء محرك `wsgi_engine.py` المستقل تماماً للخادم السحابي وفك الارتباط كلياً عن `mini_flask.py` لضمان عزل النطاقات.

### ب. الملفات المعدلة والمضافة:
* **`examora_service.py`:** تحديث دالتي `_call_online_api` و `publish_exam_online` لفرض الأمان الشبكي وآلية عدم التكرار والتحقق من الاستجابة السحابية.
* **`online_backend/app.py`:** تحديث مسار `POST /api/teacher/publish` لدعم مفتاح عدم التكرار `idempotency_key` وإعادة استخدام الرابط إذا كان الامتحان نشطاً.
* **`online_backend/database.py`:** إضافة حقل وفهرس `idempotency_key` إلى جدول `online_exams`.
* **`online_backend/wsgi_engine.py`:** محرك تشغيل مستقل وخفيف ومكتفٍ ذاتياً للخادم السحابي.
* **`online_backend/online_migrations/*.sql`:** تحديث ملفات التهيئة لـ PostgreSQL و SQLite الاختبارية.
* **`tests/test_phase4_publish.py`:** حزمة الاختبارات الشاملة للمرحلة الرابعة (10 اختبارات شاملة للسيناريوهات الأمنية والشبكية).

---

## 2. مخطط تدفق النشر (Publish Flow)

```
[ تطبيق المعلم المحلي ]
        │
        ├──── 1. اختيار الامتحان المراد نشره (local_exam_id)
        ├──── 2. قراءة أسئلة هذا الامتحان فقط (SELECT questions WHERE exam_id = ?)
        ├──── 3. قراءة الأرقام الوطنية للطلاب المقيدين بالمادة فقط
        │
        ├──── 4. بناء الحزمة العامة (Public Bundle):
        │        - عنوان الامتحان، المادة، المدة، العلامة الكلية
        │        - نصوص الأسئلة، الخيارات (أ-د)، العلامات (ZERO correct answers)
        │
        ├──── 5. بناء مفتاح الإجابة السري (Private Answer Key):
        │        - { "qid": {"correct": "أ", "mark": 5.0} }
        │
        ├──── 6. توليد مفتاح عدم التكرار (Idempotency Key):
        │        - "EXAMORA-LOCAL-EXAM-{exam_id}"
        │
        ├──── 7. إرسال الطلب الآمن (POST https://API_DOMAIN/api/teacher/publish):
        │        - الترويسة: Authorization: Bearer <TEACHER_ONLINE_SECRET>
        │
        ▼
[ الخادم السحابي (Online Backend) ]
        │
        ├──── 8. التحقق من مفتاح المعلم في زمن ثابت (hmac.compare_digest)
        ├──── 9. التحقق من سلامة واكتمال الحزمة
        │
        ├─── 10. هل الامتحان منشور مسبقاً بنفس مفتاح عدم التكرار وهو ACTIVE؟
        │        ├── نعم: تحديث الأسئلة والمفتاح وإرجاع نفس الـ publish_token القائم (reused=True).
        │        └── لا: توليد publish_token عشوائي مشفر جديد (secrets.token_urlsafe(24)).
        │
        ├─── 11. إدراج الأسئلة العامة في online_exams
        ├─── 12. إدراج مفتاح الإجابة السري في online_answer_keys (معزول خادمياً)
        │
        ▼
[ استجابة الخادم السحابي إلى التطبيق المحلي ]
        │
        ├─── 13. استلام 200 OK + publish_token + web_link
        │
        ▼
[ التوثيق في قاعدة البيانات المحلية (Local Staging) ]
        │
        ├─── 14. توثيق السجل في جدول published_exams بحالة ACTIVE
        └─── 15. تسجيل العملية في audit_log المحلي وعرض الرابط للمعلم
```

---

## 3. حصر البيانات المرسلة وغير المرسلة

### أ. البيانات التي يتم إرسالها فقط:
* `title`: عنوان الامتحان المحدد.
* `subject`: المبحث الدراسي.
* `duration`: زمن الامتحان بالدقائق.
* `total_marks`: العلامة الكلية المحسوبة خادمياً.
* `allowed_students`: قائمة الأرقام الوطنية للطلاب المسجلين في المبحث فقط.
* `questions`: نصوص الأسئلة، خياراتها الأربعة، وأرقامها التسلسلية، وعلامة كل سؤال.
* `answer_key`: مفتاح الإجابة السري الموجه لقاعدة البيانات السحابية المعزولة فقط.
* `idempotency_key`: معرف محلي للامتحان لمنع تكرار النشر.

### ب. البيانات التي يُمنع منعاً باتاً إرسالها ولا تغادر جهاز المعلم:
* ❌ ملف قاعدة البيانات `exam_platform.db` كاملاً.
* ❌ بنك الأسئلة الشامل (الأسئلة غير المخصصة لهذا الامتحان).
* ❌ بيانات المعلمين وحساباتهم وكلمات مرورهم.
* ❌ سجل التدقيق الرقابي (`audit_log`).
* ❌ منتدى الأساتذة والشكاوى والمقترحات والرسائل الداخلية.
* ❌ بيانات الطلاب غير المسجلين في المادة، وكلمات مرور الطلاب وأولياء الأمور.
* ❌ مفاتيح الاعتماد الخاصة بـ Firebase Admin.

---

## 4. تدابير الحماية المطبقة

1. **حماية سر المعلم (`TEACHER_ONLINE_SECRET`):**
   * يُقرأ حصراً من متغيرات البيئة (`os.environ`).
   * تم إجراء مسح شامل لملفات المشروع ومستودع Git وأصول الويب (`firebase_landing` و `static`)؛ وأثبت الاختبار انعدام وجود أي أثر للمفتاح في ملفات المتصفح أو الواجهات.
2. **منع التكرار (Duplicate Publish Prevention):**
   * استخدام `idempotency_key` يربط النشر السحابي بهوية الامتحان المحلي.
   * عند إعادة الضغط على زر النشر، يتم تحديث بيانات الامتحان نفسه في السحابة وإعادة استخدام نفس رمز النشر `publish_token` دون إنشاء سجلات سحابية مكررة.
3. **الأمان عند فشل الشبكة (Network Failure Safety):**
   * في حال حدوث أي انقطاع بالإنترنت أو خطأ خادمي (4xx, 5xx, Timeout):
   * يفشل الطلب في مرحلة الإرسال، ويلتقط التطبيق المحلي الخطأ.
   * **لا يتم إنشاء أي سجل فعال بحالة `ACTIVE` في `published_exams` محلياً.**
   * تظل قاعدة بيانات الأستاذ سليمة بنسبة 100% دون أي تلف، مع إشعار المعلم بإمكانية إعادة المحاولة بأمان.

---

## 5. حالة الجداول المحلية (Local Staging State)
* **`published_exams`:** يُستخدم كمرجع محلي لحالة النشر (`ACTIVE` بعد نجاح الاستجابة السحابية).
* **`published_exam_attempts`:** مخصص لاستقبال النتائج أثناء مرحلة المزامنة اللاحقة.
* **`exam_platform.db`:** معزولة ومحمية محلياً (`PRAGMA integrity_check = ok`).

---

## 6. مثال معقم للطلب والاستجابة (Sanitized Request / Response Example)

### الطلب الموجه إلى `POST /api/teacher/publish`:
```http
POST /api/teacher/publish HTTP/1.1
Host: api.examora.online
Authorization: Bearer ************************
Content-Type: application/json

{
  "idempotency_key": "EXAMORA-LOCAL-EXAM-1082",
  "title": "امتحان القواعد الشامل",
  "subject": "اللغة العربية",
  "duration": 30,
  "total_marks": 20.0,
  "allowed_students": ["2009000001", "2009000002"],
  "questions": [
    {
      "id": 1,
      "number": 1,
      "text": "ما هو إعراب الفاعل في الجملة التامة؟",
      "options": {
        "أ": "مرفوع",
        "ب": "منصوب",
        "ج": "مجرور",
        "د": "مجزوم"
      },
      "mark": 5.0
    }
  ],
  "answer_key": {
    "1": {
      "correct": "أ",
      "mark": 5.0
    }
  }
}
```

### الاستجابة الناجحة المستلمة (200 OK):
```json
{
  "ok": true,
  "publish_token": "j8X9qL2mP0qR4sV7xZ1wA3bC",
  "web_link": "https://yt-c-c.web.app/#/e/j8X9qL2mP0qR4sV7xZ1wA3bC",
  "title": "امتحان القواعد الشامل",
  "published_at": "2026-09-08 04:55:00",
  "reused": false
}
```

---

## 7. نتائج الاختبارات الشاملة (Full Test Verification)

```text
=== اختبارات المرحلة الرابعة (PHASE 4: Publish Online Integration) ===
test_A_successful_publish_selected_exam .......................... ok [PASS]
test_B_answer_key_isolation ...................................... ok [PASS]
test_C_teacher_authentication .................................... ok [PASS]
test_D_selected_exam_only_isolation .............................. ok [PASS]
test_E_local_db_integrity ........................................ ok [PASS]
test_F_network_failure_safety .................................... ok [PASS]
test_G_safe_retry_idempotency .................................... ok [PASS]
test_H_secret_exposure_verification .............................. ok [PASS]
test_I_invalid_publish_payload_rejected .......................... ok [PASS]
test_J_zero_cloud_to_local_sqlite_dependency ...................... ok [PASS]
Ran 10 tests | Status: OK (100% Success)

=== اختبارات المرحلة الثالثة (PHASE 3: Online Cloud Backend) ===
Ran 15 tests | Status: OK (100% Success)

=== اختبارات خط الأساس للنظام المحلي (Baseline Tests) ===
test_data_integrity .............................................. ok (5/5 PASS)
test_examora_features ............................................ ok (8/8 PASS)
test_full_suite (E2E Lifecycle) .................................. ok (1/1 PASS)
test_osr_smoke ................................................... ok (5/5 PASS)
test_regressions_static .......................................... ok (6/6 PASS)
test_student_portal_and_exam_controls ............................ ok (3/3 PASS)
test_ui_improvements ............................................. ok (3/3 PASS)
Ran 31 tests | Status: OK (100% Success)

=== فحص سلامة وتكامل قاعدة بيانات الأستاذ المحلية ===
PRAGMA integrity_check; ➔ ok (جميع الجداول الـ 22 سليمة تماماً ومطابقة للأصل)
```

---

## 8. حالة المستودع (Git Status)
```text
On branch master
Changes to be committed:
  modified:   examora_service.py
  modified:   online_backend/app.py
  modified:   online_backend/database.py
  new file:   online_backend/wsgi_engine.py
  modified:   online_backend/online_migrations/001_postgres_schema.sql
  modified:   online_backend/online_migrations/001_sqlite_test_schema.sql
  new file:   tests/test_phase4_publish.py
  new file:   PHASE_4_TEST_REPORT.md
```
