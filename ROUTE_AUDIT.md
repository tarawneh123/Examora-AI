# تدقيق مسارات النظام (Route & Endpoint Audit)

يوثق هذا التدقيق كافة المسارات المعرفة في ملف `app.py`، مع تحديد الطريقة المسموحة، والصلاحية، وسياق التنفيذ (إدارة المعلمة مقابل بوابة الطالب)، وحالة الفحص.

---

| المسار (Route) | الطرق المتاحة | السياق (Context) | الوظيفة البرمجية | القالب / نوع الاستجابة | حالة التدقيق |
|:---|:---:|:---:|:---|:---:|:---:|
| `/` | GET | Admin | لوحة القيادة التفاعلية | `dashboard.html` | **PASS** |
| `/dashboard` | GET | Admin | الاسم البديل للوحة القيادة | `dashboard.html` | **PASS** |
| `/first-run` | GET | Admin | معالج التهيئة الأولية للمنصة | `first_run.html` | **PASS** |
| `/complete-first-run` | POST | Admin | إكمال معالج التهيئة وحفظ الهوية | إعادة توجيه `302` | **PASS** |
| `/login` | GET | Admin | شاشة تسجيل دخول الإدارة | `login.html` | **PASS** |
| `/login/post` | POST | Admin | مصادقة كلمة مرور الإدارة | إعادة توجيه `302` | **PASS** |
| `/logout` | GET | Admin | إنهاء جلسة الإدارة | إعادة توجيه `302` | **PASS** |
| `/subjects` | GET | Admin | إدارة المواد الدراسية الأساسية والمخصصة | `subjects.html` | **PASS** |
| `/subjects/add` | POST | Admin | إضافة مادة دراسية جديدة | إعادة توجيه `302` | **PASS** |
| `/subjects/delete/<int:id>` | POST | Admin | حذف مادة دراسية مخصصة بأمان | إعادة توجيه `302` | **PASS** |
| `/packages` | GET | Admin | استعراض حزم الأسئلة والوحدات | `packages.html` | **PASS** |
| `/packages/add` | POST | Admin | إضافة حزمة أسئلة لوحدة دراسية | إعادة توجيه `302` | **PASS** |
| `/packages/delete/<int:id>` | POST | Admin | حذف حزمة أسئلة مع الحفاظ على الأسئلة | إعادة توجيه `302` | **PASS** |
| `/api/packages/add` | POST | Admin API | إضافة حزمة فوريًا عبر AJAX | `JSON (200 OK)` | **PASS** |
| `/questions` | GET | Admin | استعراض بنك الأسئلة المعتمدة والفلترة | `questions.html` | **PASS** |
| `/question-bank` | GET | Admin | مسار بديل لبنك الأسئلة المعتمدة | `questions.html` | **PASS** |
| `/questions/save` | POST | Admin | إضافة أو تعديل سؤال يدوياً | إعادة توجيه `302` | **PASS** |
| `/questions/delete/<int:id>` | POST | Admin | حذف سؤال من البنك والامتحانات | إعادة توجيه `302` | **PASS** |
| `/questions/approve/<int:id>` | GET | Admin | اعتماد سؤال فردي وترقيته للبنك | إعادة توجيه `302` | **PASS** |
| `/questions/export` | GET | Admin | تصدير بنك الأسئلة إلى CSV بترميز عربي | تنزيل ملف CSV | **PASS** |
| `/import` | GET | Admin | مركز استخراج وتحليل الأسئلة | `import.html` | **PASS** |
| `/ocr` | GET | Admin | مسار بديل لمركز استخراج OSR | `import.html` | **PASS** |
| `/import/process` | POST | Admin | استخراج الأسئلة من الصور والملفات | إعادة توجيه `302` | **PASS** |
| `/review` | GET | Admin | مركز مراجعة الأسئلة وضبط الجودة | `review.html` | **PASS** |
| `/review/bulk` | POST | Admin | الإجراءات الجماعية (اعتماد/رفض/حذف) | إعادة توجيه `302` | **PASS** |
| `/exams` | GET | Admin | استعراض قائمة الامتحانات المعدة | `exams.html` | **PASS** |
| `/exams/new` | GET | Admin | منشئ الامتحانات وحساب الأسئلة | `exam_creator.html` | **PASS** |
| `/exams/create` | GET | Admin | مسار بديل لمنشئ الامتحانات | `exam_creator.html` | **PASS** |
| `/exams/create/process` | POST | Admin | حفظ الامتحان الجديد والأسئلة المختارة | إعادة توجيه `302` | **PASS** |
| `/exams/<int:id>` | GET | Admin | مركز إدارة الامتحان الشامل | `exam_manage.html` | **PASS** |
| `/exams/<int:id>/manage` | GET | Admin | مسار بديل لإدارة الامتحان | `exam_manage.html` | **PASS** |
| `/exams/<int:id>/toggle` | POST | Admin | نشر أو إيقاف نشر الامتحان | إعادة توجيه `302` | **PASS** |
| `/exams/<int:id>/copy` | POST | Admin | نسخ الامتحان دون نسخ سجلات الطلاب | إعادة توجيه `302` | **PASS** |
| `/exams/<int:id>/delete` | POST | Admin | حذف ذري للامتحان مع صيانة البنك | إعادة توجيه `302` | **PASS** |
| `/students` | GET | Admin | سجل الطلاب المدرسي | `students.html` | **PASS** |
| `/students/add` | POST | Admin | إضافة طالب والتحقق من الاسم الرباعي | إعادة توجيه `302` | **PASS** |
| `/students/delete/<int:id>` | POST | Admin | حذف طالب وسجلاته ومحاولاته | إعادة توجيه `302` | **PASS** |
| `/results` | GET | Admin | كشف نتائج الامتحانات والمحاولات | `results.html` | **PASS** |
| `/results/export` | GET | Admin | تصدير كشف النتائج كملف CSV | تنزيل ملف CSV | **PASS** |
| `/results/attempt/<int:id>` | GET | Admin | استعراض ورقة إجابة الطالب الموثقة | `result_detail.html` | **PASS** |
| `/print/exam/<int:id>` | GET | Admin | طباعة ورقة الامتحان الرسمية (A4) | `print_exam.html` | **PASS** |
| `/print/attempt/<int:id>` | GET | Admin | طباعة كشف نتيجة الطالب المعتمدة | `print_result.html` | **PASS** |
| `/pdf/exam/<int:id>` | GET | Admin | تصدير ورقة الامتحان كـ PDF | تنزيل PDF | **PASS** |
| `/media` | GET | Admin | مكتبة الوسائط والصور المرفوعة | `media.html` | **PASS** |
| `/media/upload` | POST | Admin | رفع صور إلى مكتبة الوسائط | إعادة توجيه `302` | **PASS** |
| `/media/delete/<name>` | POST | Admin | حذف صورة من مكتبة الوسائط | إعادة توجيه `302` | **PASS** |
| `/settings` | GET | Admin | إعدادات الهوية والتخصيص البصري | `settings.html` | **PASS** |
| `/settings/save` | POST | Admin | حفظ إعدادات الهوية ورفع الشعارات | إعادة توجيه `302` | **PASS** |
| `/audit-log` | GET | Admin | استعراض سجل التدقيق الإداري | `audit_log.html` | **PASS** |
| `/backup` | GET | Admin | شاشة إدارة النسخ الاحتياطي | `backup.html` | **PASS** |
| `/backup/create` | POST | Admin | توليد نسخة احتياطية فورية لقاعدة البيانات | إعادة توجيه `302` | **PASS** |
| `/backup/download/<name>` | GET | Admin | تنزيل ملف النسخة الاحتياطية | تنزيل ملف `.db` | **PASS** |
| `/student` | GET | Student | شاشة دخول بوابة الطلاب | `student_login.html` | **PASS** |
| `/student/login` | GET | Student | مسار بديل لدخول بوابة الطلاب | `student_login.html` | **PASS** |
| `/student/login/post` | POST | Student | التحقق من بيانات الطالب وبدء الجلسة | إعادة توجيه `302` | **PASS** |
| `/student/logout` | GET | Student | إنهاء جلسة الطالب | إعادة توجيه `302` | **PASS** |
| `/student/home` | GET | Student | لوحة امتحانات الطالب النشطة | `student_home.html` | **PASS** |
| `/student/exam/<int:id>` | GET/POST | Student | شاشة تقديم الامتحان وتجميد اللقطة | `student_exam.html` | **PASS** |
| `/student/exam/<id>/autosave` | POST | Student API | الحفظ التلقائي لإجابة السؤال | `JSON (200 OK)` | **PASS** |
| `/student/exam/<id>/submit` | POST | Student | تسليم الامتحان وتصحيحه فوريًا | إعادة توجيه `302` | **PASS** |
| `/student/result/<id>` | GET | Student | استعراض نتيجة الطالب (محمي من IDOR) | `student_result.html` | **PASS** |
| `/health` | GET | Public | فحص صحة النظام وإحصائياته | `JSON (200 OK)` | **PASS** |
