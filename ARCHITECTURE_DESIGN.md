# التصميم المعماري لنظام Examora AI الهجين (ARCHITECTURE DESIGN)
**المشروع:** Examora AI — Hybrid Cloud Architecture  
**المرحلة:** PHASE 2 — ARCHITECTURE DESIGN  
**التاريخ:** 2026-09-08  
**المبدأ الحاكم:** `LOCAL DATABASE ≠ ONLINE DATABASE` (عزل تام لمصدر البيانات المحلي)

---

## 1. حدود النظام المحلي والسحابي (Local / Online Boundaries)

```
+---------------------------------------------------------------------------------------------------------+
|                                    ZONE A: LOCAL TEACHER ENVIRONMENT                                    |
|                                         (Private Machine / LAN)                                         |
|                                                                                                         |
|  +---------------------------+        +--------------------------------------------------------------+  |
|  |   Teacher Desktop UI      |        |             Examora Local Core (Flask/Python)                |  |
|  |  - Dashboard / Settings   | <----> |  - Full Question Bank (166 Questions)                        |  |
|  |  - Student Management     |        |  - Official School & Ministry Identity                       |  |
|  |  - Retake & Overrides     |        |  - Audit Log (464 records) & Forum & Complaints              |  |
|  |  - OSR Image Extraction   |        |  - Master Gradebooks & Historical Snapshots                  |  |
|  +---------------------------+        +------------------------------+-------------------------------+  |
|                                                                      |                                  |
|                                                                      v                                  |
|                                       +--------------------------------------------------------------+  |
|                                       |             exam_data/exam_platform.db (SQLite)              |  |
|                                       |           [Local-only database with outbound HTTPS communication and no inbound public access]                |  |
|                                       |         No inbound ports - No public credentials             |  |
|                                       +--------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------------+
                                                |                     ^
                                (1) Outbound Publish                  | (4) Outbound Sync
                                    (Selected Exam Only)              |     (Attempts & Scores)
                                                v                     |
+---------------------------------------------------------------------------------------------------------+
|                                       ZONE B: ONLINE CLUSTER (DMZ)                                      |
|                                                                                                         |
|   +--------------------------------------------------------------------------------------------------+  |
|   |                        Examora Cloud API (Python/Flask or FastAPI)                               |  |
|   |   - Authenticated Teacher Ingestion Gateway (/api/teacher/*)                                     |  |
|   |   - Public Student Exam Gateway (/api/public/exam/*)                                             |  |
|   |   - Server-Side Timer Engine & Attempt Token Validator                                           |  |
|   |   - Server-Side Grading Engine (Zero-Leak Answer Key Evaluation)                                 |  |
|   +---------------------------------+----------------------------------------------------------------+  |
|                                     |                                                                   |
|                                     v                                                                   |
|   +--------------------------------------------------------------------------------------------------+  |
|   |                           Online Database (Cloud PostgreSQL / Cloud DB)                          |  |
|   |   - online_exams (Staged active exams without client-side answer key)                            |  |
|   |   - online_answer_keys (Isolated server-only table)                                              |  |
|   |   - online_attempts (Temporary student sessions & encrypted attempt_tokens)                      |  |
|   |   - online_answers (Student autosaved answers)                                                   |  |
|   +--------------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------------+
                                                ^
                                                | (2) HTTPS API Requests
                                                |     (Start, Autosave, Submit)
                                                v
+---------------------------------------------------------------------------------------------------------+
|                                      ZONE C: STUDENT PUBLIC ACCESS                                      |
|                                                                                                         |
|   +--------------------------------------------------------------------------------------------------+  |
|   |                    Firebase Hosting Frontend (https://yt-c-c.web.app/#/e/TOKEN)                  |  |
|   |   - Fast Entry Screen (National ID + Token)                                                      |  |
|   |   - Online Examination Room (Timer, Dynamic Questions, Real-time Autosave)                      |  |
|   |   - Instant Feedback & Celebration Screen                                                        |  |
|   +--------------------------------------------------------------------------------------------------+  |
|                                                                                                         |
|                                    Student Mobile / Tablet / PC                                         |
+---------------------------------------------------------------------------------------------------------+
```

### تحديد المسؤوليات والحدود:
* **ما يبقى محلياً حصراً داخل جهاز الأستاذ (Local):**
  1. ملف `exam_platform.db` كاملاً (جميع الجداول الـ 22).
  2. بنك الأسئلة الشامل (الأسئلة غير المنشورة).
  3. سجلات التدقيق الرقابي (`audit_log`).
  4. بيانات الطلاب الكاملة (بيانات أولياء الأمور، كلمات المرور، الشعب غير المعنية).
  5. منتدى المعلمين والشكاوى والمقترحات والرسائل الداخلية.
  6. ملفات الاعتماد السحابي الرئيسية (`serviceAccountKey.json`).
* **ما يذهب إلى السحابة مؤقتاً (Online Staged Data):**
  1. الامتحان المنشور فقط (`title`, `subject`, `duration`, `total_marks`).
  2. أسئلة الامتحان المحددة فقط **بعد تجريدها بالكامل من الإجابات الصحيحة**.
  3. قائمة الأرقام الوطنية للطلاب المسجلين في مبحث الامتحان فقط (`allowed_students`).
  4. مفتاح الإجابة السري الخادمي في جدول معزول لا يمكن الوصول إليه عبر الـ Public API.
  5. محاولات وإجابات الطلاب أثناء فترة فتح الامتحان، وتُحذف نهائياً بعد إتمام المزامنة المحلية.

---

## 2. بنية الخادم السحابي المستقل (Online Backend Architecture)

* **التقنية المختارة:** Python Micro-framework (Flask / WSGI) خفيف ومكتفٍ ذاتياً، مماثل للـ Stack الحالي لضمان عدم وجود تناقض في سلوك تشغيل المترجم والمكتبات.
* **قاعدة البيانات:** PostgreSQL (على خدمة Managed Cloud Database مجانية/اقتصادية مثل Neon أو Supabase أو Render PostgreSQL) مع دعم تشغيل بيئة اختبارية بـ SQLite منفصل.
* **هيكل الملفات المقترح للمجلد المستقل (`online_backend/`):**
  ```text
  online_backend/
  ├── app.py                 # نقطة الدخول الرئيسية وتوجيه الطلبات
  ├── config.py              # إدارة متغيرات البيئة والأسرار
  ├── database.py            # محرك الاتصال بـ PostgreSQL / Schema init
  ├── security.py            # التحقق من الرموز، Rate Limiting، وفحص الصلاحيات
  ├── scoring.py             # محرك التصحيح الخادمي الحصري
  ├── requirements.txt       # الاعتماديات الخادمة (psycopg2-binary, etc.)
  ├── Dockerfile             # حاوية التشغيل القياسية لأي سحابة
  └── migrations/            # ملفات تهيئة قاعدة البيانات السحابية المستقلة
      └── 001_online_schema.sql
  ```

---

## 3. سيناريوهات الأعطال والانقطاعات (Failure Scenarios & Resilience)

1. **انقطاع الإنترنت أثناء تقديم الامتحان:**
   * الواجهة في `exam.js` تحتفظ بالإجابات محلياً في `IndexedDB/Memory` وتضع علامة تحذيرية برتقالية للطالب `حفظ مؤقت في المتصفح`.
   * يتم تفعيل آلية إعادة محاولة تلقائية دورية (Exponential Backoff: كل 3، 6، 12 ثانية) فور عودة الاتصال.
2. **إغلاق المتصفح أو انقطاع التيار (Crash / Refresh):**
   * عند عودة الطالب وإدخال رقمه الوطني ورمز الامتحان:
   * يتحقق الخادم من وجود محاولة نشطة (`ACTIVE`).
   * يحسب الخادم الوقت المتبقي الفعلي بدقة: `server_deadline - current_server_time`.
   * إذا كان الوقت المتبقي > 0، يُعاد إرسال الامتحان ومعه مصفوفة الإجابات المحفوظة مسبقاً ليستأنف الطالب من حيث توقف.
3. **محاولة التلاعب بالوقت بتعديل ساعة جهاز الطالب:**
   * الخادم هو المرجع الوحيد للزمن. إذا أرسل المتصفح تسليماً أو حفظاً بعد `server_deadline + 15s grace period`، يرفض الخادم الطلب ويُقفل المحاولة بـ `EXPIRED`.
4. **فشل الاتصال أثناء المزامنة المحلية (Sync Failure):**
   * عملية المزامنة `Idempotent`: يطلب التطبيق المحلي المحاولات ذات الحالة `SUBMITTED`.
   * بعد إدخالها بنجاح في SQLite داخل Transaction محلية محكمة، يُرسل التطبيق تأكيد الاستلام للسحابة لتحديث `is_synced = 1`.
   * إذا انقطع الاتصال أثناء النقل، تظل البيانات في السحابة محفوظة لإعادة المزامنة في أي وقت.

---

## 4. معمارية النشر والتشغيل المقترحة (Deployment Architecture)

* **الواجهة الأمامية (Frontend):** Firebase Hosting على `https://yt-c-c.web.app/` (مجانية بالكامل، موزعة عالمياً عبر CDN، تدعم HTTPS تلقائياً).
* **الخادم السحابي (Online API):** خدمة حاويات سحابية مدارة (Serverless Container) مثل:
  * **Google Cloud Run** أو **Render** أو **Railway** (تتميز بتكلفة تبدأ من $0 / Free Tier، تدعم تشغيل حاوية Docker واحدة، وتدير شهادات SSL تلقائياً).
* **متغيرات البيئة السحابية الأساسية (Environment Variables):**
  * `DATABASE_URL`: رابط اتصال PostgreSQL السحابي.
  * `TEACHER_ONLINE_SECRET`: مفتاح التوثيق السري بين جهاز المعلم والخادم السحابي.
  * `ALLOWED_ORIGIN`: `https://yt-c-c.web.app` (لحصر CORS ومنع الاستدعاءات العشوائية).
  * `ENVIRONMENT`: `production`.
