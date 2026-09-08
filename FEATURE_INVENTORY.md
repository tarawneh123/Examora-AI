# فهرس الميزات الشامل (Feature Inventory)

يوثق هذا المستند كافة الوظائف والمكونات البرمجية المعتمدة في المنصة، والمسارات المرتبطة بها، والجداول المرجعية، وحالة كل ميزة لضمان عدم فقدان أي وظيفة سابقة.

---

| # | الميزة (Feature) | التنفيذ البرمجي | المسارات (Routes) | جداول قاعدة البيانات | القوالب المرتبطة | حالة الميزة |
|---|---|---|---|---|---|---|
| 1 | **إدارة هوية المدرسة والمعلمة** | حفظ الترويسة الرسمية، الوزارة، المديرية، اللواء، المدرسة | `/settings`, `/settings/save` | `settings` | `settings.html`, `base.html` | **ENHANCED** |
| 2 | **تخصيص الألوان والخطوط** | منتقي ألوان حقيقي (Color Picker) وقائمة خطوط عربية ولاتينية | `/settings`, `/settings/save` | `settings` | `settings.html` | **ENHANCED** |
| 3 | **إدارة الشعارات الرسمية** | رفع شعار المدرسة والوزارة مع التحقق الآمن وعرض المعاينة والحذف | `/settings`, `/settings/save`, `/assets/<name>` | `settings` | `settings.html` | **ENHANCED** |
| 4 | **لوحة القيادة التفاعلية** | إحصائيات سريعة، مخطط توزيع الأسئلة، المرشد التفاعلي للخطوة التالية | `/`, `/dashboard` | `questions`, `exams`, `students`, `attempts` | `dashboard.html` | **ENHANCED** |
| 5 | **كيان المواد الدراسية** | إدارة المواد الأساسية والمخصصة مع تحديد اللغة والاتجاه | `/subjects`, `/subjects/add`, `/subjects/delete/<id>` | `subjects` | `subjects.html` | **NEW & PRESERVED** |
| 6 | **حزم الأسئلة والوحدات** | تقسيم المنهاج إلى حزم ووحدات تتبع المادة مع منع تكرار الأسماء | `/packages`, `/packages/add`, `/packages/delete/<id>`, `/api/packages/add` | `question_packages` | `packages.html`, `import.html` | **ENHANCED** |
| 7 | **إضافة حزمة أثناء الاستخراج** | زر "+ إضافة حزمة" داخل مسار الاستخراج دون إعادة تحميل الصفحة | `/api/packages/add` | `question_packages` | `import.html` | **NEW & ENHANCED** |
| 8 | **محرك الاستخراج الذكي (OSR)** | تحليل صور ونصوص الامتحانات باللغتين مع منع الإيجابيات الكاذبة | `/import`, `/ocr`, `/import/process` | `questions` | `import.html` | **ENHANCED (OSR Official)** |
| 9 | **السؤال اليدوي في سياق الحزمة** | إضافة سؤال يدوي يرث المادة والحزمة الحالية مباشرة بنقرة زر | `/questions/save` | `questions` | `import.html` | **NEW & ENHANCED** |
| 10 | **السؤال اليدوي المستقل** | إضافة سؤال يدوي باختيار المادة والحزمة والعلامة من بنك الأسئلة | `/questions/save` | `questions` | `questions.html` | **PRESERVED** |
| 11 | **مركز مراجعة الأسئلة (QC)** | فحص الأسئلة المستخرجة وتعديلها واعتمادها الفردي أو الجماعي | `/review`, `/review/bulk`, `/questions/approve/<id>` | `questions` | `review.html` | **ENHANCED** |
| 12 | **بنك الأسئلة المعتمدة** | تصفية حسب المادة، الحزمة، الحالة، البحث، والتعديل بالنقر المزدوج | `/questions`, `/question-bank`, `/questions/export` | `questions`, `subjects`, `question_packages` | `questions.html` | **ENHANCED** |
| 13 | **تصدير بنك الأسئلة كـ CSV** | تنزيل ملف Excel بترميز UTF-8 BOM الداعم للأحرف العربية | `/questions/export` | `questions` | `questions.html` | **NEW & PRESERVED** |
| 14 | **مكتبة الوسائط والصور** | استعراض وحفظ وحذف الرسوم التوضيحية لأسئلة الامتحانات | `/media`, `/media/upload`, `/media/delete/<filename>` | نظام الملفات | `media.html` | **RESTORED & ENHANCED** |
| 15 | **منشئ الامتحانات الذكي** | احتساب تلقائي لعدد الأسئلة مع فلترة تدريجية حسب المادة والحزمة | `/exams/new`, `/exams/create`, `/exams/create/process` | `exams`, `exam_questions`, `questions` | `exam_creator.html` | **ENHANCED** |
| 16 | **حماية الامتحان بكلمة مرور** | تعيين رمز سري للامتحان لمنع بدء المحاولة إلا بإدخاله | `/exams/create/process`, `/student/exam/<id>` | `exams` | `exam_creator.html`, `student_exam.html` | **ENHANCED** |
| 17 | **مركز إدارة الامتحان** | مركز متكامل: البيانات، الأسئلة، النشر، الحذف الذري، والنسخ | `/exams/<id>`, `/exams/<id>/manage`, `/exams/<id>/toggle`, `/exams/<id>/copy`, `/exams/<id>/delete` | `exams`, `exam_questions`, `attempts` | `exam_manage.html` | **ENHANCED** |
| 18 | **جدول الطلاب المتقدمين** | عرض المتقدمين للامتحان وعدد المحاولات والعلامة وتاريخ التسليم | `/exams/<id>/manage` | `attempts`, `students` | `exam_manage.html` | **ENHANCED** |
| 19 | **سجل الطلاب المدرسي** | إدارة أسماء الطلاب، الصفوف، الشعب، وبيانات الدخول | `/students`, `/students/add`, `/students/delete/<id>` | `students` | `students.html` | **PRESERVED** |
| 20 | **بوابة الطلاب المنفصلة** | تسجيل دخول الطالب واستعراض الامتحانات النشطة فقط | `/student`, `/student/login`, `/student/home`, `/student/logout` | `students`, `exams`, `attempts` | `student_login.html`, `student_home.html` | **ENHANCED** |
| 21 | **شاشة تقديم الامتحان الرقمي** | ترويسة عربية ثابتة، مؤقت تنازلي، مؤشر حفظ تلقائي، وخيارات مرنة | `/student/exam/<id>` | `exams`, `attempts`, `attempt_snapshots` | `student_exam.html` | **ENHANCED** |
| 22 | **اللقطات المجمدة للمحاولات** | تجميد الأسئلة عند بدء المحاولة لمنع تغير النتائج عند تعديل البنك | `/student/exam/<id>` | `attempt_snapshots` | `student_exam.html` | **NEW & CRITICAL** |
| 23 | **الحفظ التلقائي الموزون** | حفظ إجابات الطالب فورياً في الخادم مع فاصل زمني (Debounce 300ms) | `/student/exam/<id>/autosave` | `answers`, `attempts` | `student_exam.html` | **ENHANCED** |
| 24 | **استكمال المحاولة (Resume)** | العودة للامتحان النشط مع استرجاع كافة الإجابات السابقة | `/student/exam/<id>` | `attempts`, `answers` | `student_exam.html` | **ENHANCED** |
| 25 | **تسليم الامتحان واحتساب العلامة** | إغلاق المحاولة، تصحيح آلي فوري، ومنع إعادة التقديم | `/student/exam/<id>/submit` | `attempts`, `answers` | `student_exam.html` | **ENHANCED** |
| 26 | **كشف نتيجة الطالب الفوري** | عرض العلامة المستحقة والنسبة والتقرير التفصيلي لكل سؤال | `/student/result/<attempt_id>` | `attempts`, `attempt_snapshots`, `answers` | `student_result.html` | **ENHANCED** |
| 27 | **طباعة ورقة الامتحان (A4)** | ترويسة رسمية في الصفحة الأولى فقط، مع تدفق طبيعي في الصفحة الثانية | `/print/exam/<id>` | `exams`, `questions` | `print_exam.html` | **ENHANCED** |
| 28 | **طباعة كشف نتيجة الطالب** | كشف رسمي A4 يوثق نتيجة المحاولة بالاعتماد على اللقطة التاريخية | `/print/attempt/<id>` | `attempts`, `attempt_snapshots`, `answers` | `print_result.html` | **ENHANCED** |
| 29 | **تصدير الامتحان كـ PDF** | توليد ملف PDF رسمي للطباعة الورقية | `/pdf/exam/<id>` | `exams`, `questions` | مولد PDF | **ENHANCED** |
| 30 | **سجل التدقيق الإداري** | تسجيل العمليات الحساسة (إنشاء، نشر، حذف، دخول) | `/audit-log` | `audit_log` | `audit_log.html` | **ENHANCED** |
| 31 | **النسخ الاحتياطي لقاعدة البيانات** | نسخ فوري وتنزيل ملفات `.db` مشفرة بختم زمني | `/backup`, `/backup/create`, `/backup/download/<name>` | نظام الملفات | `backup.html` | **ENHANCED** |
