# مواصفات واجهات برمجة التطبيقات السحابية (ONLINE API SPECIFICATION)
**الإصدار:** v1.0 — OpenAPI Compliant  
**النطاق السحابي:** `https://api.examora.online` (أو خادم الـ Cloud Run / Render المستضاف)  
**بروتوكول النقل:** HTTPS حصراً  
**صيغة البيانات:** JSON (UTF-8)

---

## القسم الأول: واجهات إدارة المعلم (Teacher Management Gateway)
*تتطلب هذه المسارات توثيقاً إجبارياً عبر ترويسة: `Authorization: Bearer <TEACHER_ONLINE_SECRET>`*

### 1. نشر امتحان جديد (Publish Exam)
* **المسار:** `POST /api/teacher/publish`
* **الوظيفة:** استقبال حزمة الامتحان من تطبيق المعلم المحلي، وإنشاء السجل السحابي، وعزل مفتاح الإجابة.
* **جسم الطلب (Request Body):**
```json
{
  "title": "امتحان التاريخ النصفي - الثاني عشر",
  "subject": "تاريخ الأردن",
  "duration": 45,
  "total_marks": 20.0,
  "allowed_students": ["2009000001", "2009000002", "2009000003"],
  "questions": [
    {
      "id": 101,
      "number": 1,
      "text": "ما هي عاصمة المملكة الأردنية الهاشمية؟",
      "options": {
        "أ": "عمان",
        "ب": "إربد",
        "ج": "الزرقاء",
        "د": "العقبة"
      },
      "mark": 5.0
    }
  ],
  "answer_key": {
    "101": {
      "correct": "أ",
      "mark": 5.0
    }
  }
}
```
* **الاستجابة الناجحة (200 OK):**
```json
{
  "ok": true,
  "publish_token": "T8k9L2mP0qR4sV7xZ1wA3bC5dE7fG9h",
  "web_link": "https://yt-c-c.web.app/#/e/T8k9L2mP0qR4sV7xZ1wA3bC5dE7fG9h",
  "published_at": "2026-09-08 04:00:00"
}
```
* **رموز الخطأ:** `401 Unauthorized` (مفتاح المعلم غير صحيح)، `400 Bad Request` (بيانات ناقصة).

---

### 2. إغلاق الامتحان المنشور (Close Exam)
* **المسار:** `POST /api/teacher/exams/{publish_token}/close`
* **الوظيفة:** تحويل حالة الامتحان إلى `CLOSED` لوقف قبول أي محاولات جديدة.
* **الاستجابة الناجحة (200 OK):**
```json
{
  "ok": true,
  "status": "CLOSED",
  "closed_at": "2026-09-08 05:00:00"
}
```

---

### 3. سحب النتائج للمزامنة المحلية (Fetch Attempts for Sync)
* **المسار:** `GET /api/teacher/exams/{publish_token}/attempts`
* **الوظيفة:** تصدير كافة المحاولات المسلمة `SUBMITTED` لتنزيلها وتوثيقها داخل SQLite المحلي.
* **الاستجابة الناجحة (200 OK):**
```json
{
  "ok": true,
  "publish_token": "T8k9L2mP0qR4sV7xZ1wA3bC5dE7fG9h",
  "total_attempts": 1,
  "attempts": [
    {
      "online_attempt_id": 402,
      "student_national_id": "2009000001",
      "student_name": "طالب (2009000001)",
      "score": 20.0,
      "total": 20.0,
      "percentage": 100.0,
      "tier": "ممتاز",
      "started_at": "2026-09-08 04:05:00",
      "finished_at": "2026-09-08 04:30:00",
      "answers": {
        "101": "أ"
      }
    }
  ]
}
```

---

### 4. الحذف النهائي للنسخة السحابية (Purge Exam)
* **المسار:** `DELETE /api/teacher/exams/{publish_token}`
* **الوظيفة:** حذف الامتحان المنشور ومحاولاته وإجاباته ومفتاح إجابته نهائياً من السحابة.
* **الاستجابة الناجحة (200 OK):**
```json
{
  "ok": true,
  "message": "تم حذف الامتحان وجميع بياناته السحابية المؤقتة بنجاح."
}
```

---

## القسم الثاني: واجهات الطلاب العامة (Public Student Gateway)
*هذه المسارات متاحة عبر الإنترنت ومحمية بنظام Rate Limiting ورموز المحاولات المشفرة*

### 1. التحقق وبدء الامتحان (Start or Resume Exam)
* **المسار:** `POST /api/public/exam/start`
* **جسم الطلب (Request Body):**
```json
{
  "national_id": "2009000001",
  "publish_token": "T8k9L2mP0qR4sV7xZ1wA3bC5dE7fG9h"
}
```
* **الاستجابة الناجحة (200 OK):**
```json
{
  "ok": true,
  "attempt_id": 402,
  "attempt_token": "k9L2mP0qR4sV7xZ1wA3bC5dE7fG9h8j1a4c7e0f3b6d9",
  "is_resumed": false,
  "remaining_seconds": 2700,
  "exam": {
    "title": "امتحان التاريخ النصفي - الثاني عشر",
    "subject": "تاريخ الأردن",
    "duration": 45,
    "total_marks": 20.0
  },
  "student": {
    "national_id": "2009000001",
    "name": "طالب (2009000001)"
  },
  "questions": [
    {
      "id": 101,
      "number": 1,
      "text": "ما هي عاصمة المملكة الأردنية الهاشمية؟",
      "options": {
        "أ": "عمان",
        "ب": "إربد",
        "ج": "الزرقاء",
        "د": "العقبة"
      },
      "mark": 5.0
    }
  ],
  "answers": {}
}
```
* **ملاحظة أمنية حاسمة:** استجابة الأسئلة لا تحتوي إطلاقاً على أي حقل مثل `correct` أو `correct_answer` أو `answer_key`.
* **رموز الخطأ:** 
  * `403 Forbidden`: الطالب غير مسجل في قائمة المسموح لهم، أو سلم امتحانه مسبقاً.
  * `404 Not Found`: رمز الامتحان غير صحيح أو الامتحان مغلق.
  * `429 Too Many Requests`: تجاوز معدل الطلبات المسموح به.

---

### 2. الحفظ التلقائي اللحظي (Autosave Answer)
* **المسار:** `POST /api/public/exam/autosave`
* **الترويسة المطلوبة:** `X-Attempt-Token: <attempt_token>`
* **جسم الطلب:**
```json
{
  "attempt_id": 402,
  "question_id": 101,
  "answer": "أ"
}
```
* **الاستجابة الناجحة (200 OK):**
```json
{
  "ok": true,
  "saved_at": "2026-09-08 04:12:30"
}
```
* **الحماية من IDOR:** إذا كان `attempt_token` لا يطابق المحاولة `402` خادمياً، يُرفض الطلب فوراً بـ `403 Forbidden`.

---

### 3. التسليم والتصحيح الخادمي (Submit & Server Grading)
* **المسار:** `POST /api/public/exam/submit`
* **الترويسة المطلوبة:** `X-Attempt-Token: <attempt_token>`
* **جسم الطلب:**
```json
{
  "attempt_id": 402,
  "answers": {
    "101": "أ"
  }
}
```
* **الاستجابة الناجحة (200 OK):**
```json
{
  "ok": true,
  "score": 20.0,
  "total": 20.0,
  "percentage": 100.0,
  "tier": "ممتاز",
  "feedback_message": "ما شاء الله! أداء استثنائي ونتيجة متميزة تدعو للفخر."
}
```
* **آلية المعالجة:** يتم حساب العلامة من خلال مقارنة إجابات الطالب المسجلة بمفتاح الإجابة السري في جدول `online_answer_keys`، وتتحول المحاولة إلى `SUBMITTED` ويُقفل التعديل عليها نهائياً.
