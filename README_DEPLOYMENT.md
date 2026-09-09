# دليل النشر والتشغيل الشامل لمنظومة Examora AI
**الإصدار:** v34 Master Production Release  
**الهوية:** منظومة Examora AI للتقييم والاختبارات الذكية  
**تصميم وتطوير:** [HT STUDIO DESIGN](https://htst-d.web.app/)  

---

## 1. محتويات المنظومة المتكاملة
* **تطبيق المعلم المحلي (Examora Local App):**
  * `app.py`، `examora_service.py`، `examora_routes.py`، `mini_flask.py`.
  * قوالب الواجهات المحلية (`templates/`) وملفات التنسيق والوسائط (`static/`).
  * قاعدة البيانات المحلية (`exam_data/exam_platform.db`) مفصولة ذاتياً لضمان الخصوصية.
* **الخادم السحابي المستقل (Online Cloud Backend):**
  * مجلد `online_backend/` مع `Dockerfile` وملف البناء التلقائي لـ Render (`render.yaml`).
* **بوابة الطلاب والاستضافة السحابية (Firebase Hosting):**
  * مجلد `firebase_landing/` (الواجهة المظلمة الزجاجية، قاعة الاختبار بالترويسة الرسمية المعتمدة، وخريطة الأسئلة، وشهادات التميز).
  * ملف التكوين `firebase.json` وقواعد الأمان `database.rules.json`.
* **سير العمل وأتمتة النشر على GitHub:**
  * مجلد `.github/workflows/` (فحص CI/CD واختبارات الجودة ونشر Firebase Hosting تلقائياً).
* **حزمة التعرف الضوئي للغة العربية (OSR / OCR):**
  * مجلد `tessdata/` لدعم قراءة الأسئلة من الصور باللغتين العربية والإنجليزية دون تثبيت برامج خارجية.

---

## 2. كيفية رفع المشروع وتحديثه على GitHub
داخل مجلد المشروع، نفذ الأوامر التالية لرفع التحديثات إلى مستودع GitHub:

```bash
# 1. التحقق من حالة الملفات
git status

# 2. إضافة كافة التعديلات الجديدة
git add .

# 3. تثبيت التعديلات برسالة واضحة
git commit -m "Release: Examora AI v34 Master Production"

# 4. رفع الكود إلى المستودع
git push origin main
```

*(بمجرد تنفيذ `git push`، سيقوم GitHub Actions تلقائياً بفحص الكود ونشر واجهة `firebase_landing` إلى استضافة Firebase Hosting عبر ملف `.github/workflows/firebase-deploy.yml`)*.

---

## 3. كيفية نشر بوابة الطلاب على Firebase Hosting يدوياً
إذا كنت ترغب في نشر واجهة الطلاب مباشرة عبر أداة Firebase CLI:

```bash
# تسجيل الدخول إلى حساب فيربيز
firebase login

# التأكد من اختيار المشروع
firebase use yt-c-c

# نشر الواجهة السحابية وقواعد الحماية
firebase deploy --only hosting,database
```

الرابط المباشر للطلاب: `https://yt-c-c.web.app`

---

## 4. كيفية ربط ونشر الخادم السحابي على Render
تم تجهيز ملف `render.yaml` مسبقاً في جذر المشروع. لربطه بنقرة واحدة:
1. ادخل إلى لوحة تحكم [Render Dashboard](https://dashboard.render.com/).
2. اختر **New +** ثم **Blueprint**.
3. اربط مستودع GitHub الخاص بمشروع Examora AI.
4. سيقرأ Render ملف `render.yaml` تلقائياً ويبني الحاوية باستخدام `online_backend/Dockerfile` ويطلق السيرفر على الرابط:  
   `https://examora-ai-nowy.onrender.com`.

---

## 5. كيفية تصدير البرنامج إلى نسخة تنفيذية (Examora_AI.exe) دون دمج قاعدة البيانات
لتحويل التطبيق إلى ملف `.exe` نظيف وخفيف ومستقل، مع ترك قاعدة البيانات منفصلة وخاصة بكل أستاذ:

```bash
pyinstaller --noconfirm --onedir --windowed \
  --name "Examora_AI" \
  --add-data "templates;templates" \
  --add-data "static;static" \
  --add-data "firebase_landing;firebase_landing" \
  --add-data "tessdata;tessdata" \
  --add-data "migration.sql;." \
  --add-data "serviceAccountKey.json;." \
  --hidden-import "jinja2" \
  --hidden-import "cryptography" \
  --icon="static/assets/school_logo.png" \
  app.py
```

* **النتيجة:** سينتج مجلد في المسار `dist/Examora_AI` يحتوي على ملف `Examora_AI.exe`.
* عند تشغيل البرنامج على أي جهاز، يُنشئ بجانبه مجلد `exam_data/` تلقائياً مع قاعدة بيانات نظيفة وجديدة تماماً وخاصة بالأستاذ دون أي تداخل مع بياناتك السابقة.

---
© 2026 جميع الحقوق محفوظة — منظومة Examora AI للتقييم والاختبارات الذكية  
تصميم وتطوير: **HT STUDIO DESIGN** (https://htst-d.web.app/)
