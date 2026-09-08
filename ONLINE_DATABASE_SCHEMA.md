# مخطط وتصميم قاعدة البيانات السحابية المستقلة (ONLINE DATABASE SCHEMA)
**المحرك المستهدف:** PostgreSQL 15+ (مع توافق كامل مع SQLite لبيئات التطوير)  
**المبدأ المعماري:** قاعدة بيانات معزولة ومؤقتة؛ لا صلة مباشرة بينها وبين `exam_platform.db`.

---

## 1. مخطط الجداول والعلاقات (Entity Relationship Model)

```
       +-----------------------------------+
       |           online_exams            |
       +-----------------------------------+
       | PK  id             BIGSERIAL      |
       | UQ  publish_token   VARCHAR(64)   |<--------------+
       |     title          VARCHAR(255)   |               |
       |     subject        VARCHAR(128)   |               |
       |     duration       INTEGER        |               |
       |     total_marks    NUMERIC(6,2)   |               |
       |     status         VARCHAR(32)    |               |
       |     questions_json JSONB/TEXT     |               |
       |     allowed_ids    JSONB/TEXT     |               |
       |     created_at     TIMESTAMP      |               |
       |     closed_at      TIMESTAMP      |               |
       +-----------------+-----------------+               |
                         | 1:1                             | 1:N
                         v                                 |
       +-----------------------------------+               |
       |        online_answer_keys         |               |
       |      [PRIVATE - SERVER ONLY]      |               |
       +-----------------------------------+               |
       | PK  id             BIGSERIAL      |               |
       | FK  publish_token   VARCHAR(64)   |               |
       |     keys_json      JSONB/TEXT     |               |
       |     created_at     TIMESTAMP      |               |
       +-----------------------------------+               |
                                                           v
                                           +-----------------------------------+
                                           |          online_attempts          |
                                           +-----------------------------------+
                                           | PK  id             BIGSERIAL      |
                                           | FK  publish_token   VARCHAR(64)   |<----+
                                           |     student_nat_id VARCHAR(64)    |     |
                                           |     student_name   VARCHAR(128)   |     |
                                           | UQ  attempt_token_hash VARCHAR(64)    |     |
                                           |     status         VARCHAR(32)    |     |
                                           |     score          NUMERIC(6,2)   |     |
                                           |     total          NUMERIC(6,2)   |     |
                                           |     percentage     NUMERIC(5,2)   |     |
                                           |     tier           VARCHAR(32)    |     |
                                           |     started_at     TIMESTAMP      |     |
                                           |     deadline       TIMESTAMP      |     |
                                           |     finished_at    TIMESTAMP      |     |
                                           |     is_synced      BOOLEAN/INT    |     |
                                           +-----------------+-----------------+     |
                                                             | 1:N                   |
                                                             v                       |
                                           +-----------------------------------+     |
                                           |          online_answers           |     |
                                           +-----------------------------------+     |
                                           | PK  id             BIGSERIAL      |     |
                                           | FK  attempt_id     BIGINT         |-----+
                                           |     question_id    INTEGER        |
                                           |     answer         VARCHAR(16)    |
                                           |     answered_at    TIMESTAMP      |
                                           | UQ (attempt_id, question_id)      |
                                           +-----------------------------------+
```

---

## 2. كود الـ DDL الرسمي لإنشاء الجداول في PostgreSQL

```sql
-- 1. جدول الامتحانات المنشورة أونلاين
CREATE TABLE IF NOT EXISTS online_exams (
    id BIGSERIAL PRIMARY KEY,
    publish_token VARCHAR(64) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    subject VARCHAR(128) NOT NULL,
    duration INTEGER NOT NULL, -- بالدقائق
    total_marks NUMERIC(6,2) NOT NULL DEFAULT 0.0,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, CLOSED, PURGED
    questions_json JSONB NOT NULL, -- حزمة الأسئلة المجردة بدون إجابات صحيحة
    allowed_students_json JSONB NOT NULL DEFAULT '[]'::jsonb, -- الأرقام الوطنية المصرح لها
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITH TIME ZONE
);

-- 2. جدول مفاتيح الإجابات السرية (معزول خادمياً 100%)
CREATE TABLE IF NOT EXISTS online_answer_keys (
    id BIGSERIAL PRIMARY KEY,
    publish_token VARCHAR(64) NOT NULL REFERENCES online_exams(publish_token) ON DELETE CASCADE,
    keys_json JSONB NOT NULL, -- { "101": {"correct": "أ", "mark": 5.0} }
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. جدول محاولات الطلاب السحابية المؤقتة
CREATE TABLE IF NOT EXISTS online_attempts (
    id BIGSERIAL PRIMARY KEY,
    publish_token VARCHAR(64) NOT NULL REFERENCES online_exams(publish_token) ON DELETE CASCADE,
    student_national_id VARCHAR(64) NOT NULL,
    student_name VARCHAR(128) NOT NULL,
    attempt_token_hash VARCHAR(64) UNIQUE NOT NULL -- Cryptographic SHA-256 hash of raw attempt_token, -- توثيق الجلسة ومنع IDOR
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, SUBMITTED, EXPIRED
    score NUMERIC(6,2) NOT NULL DEFAULT 0.0,
    total NUMERIC(6,2) NOT NULL DEFAULT 0.0,
    percentage NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    tier VARCHAR(32) NOT NULL DEFAULT '',
    feedback_message TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    server_deadline TIMESTAMP WITH TIME ZONE NOT NULL, -- مرجع الوقت الصارم
    finished_at TIMESTAMP WITH TIME ZONE,
    is_synced BOOLEAN NOT NULL DEFAULT FALSE
);

-- 4. جدول إجابات الطلاب المحفوظة لحظياً
CREATE TABLE IF NOT EXISTS online_answers (
    id BIGSERIAL PRIMARY KEY,
    attempt_id BIGINT NOT NULL REFERENCES online_attempts(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL,
    answer VARCHAR(16) NOT NULL,
    answered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_attempt_question UNIQUE (attempt_id, question_id)
);

-- الفهارس لتحقيق استجابة فائقة السرعة
CREATE INDEX IF NOT EXISTS idx_online_exams_status ON online_exams(status);
CREATE INDEX IF NOT EXISTS idx_online_attempts_token ON online_attempts(publish_token);
CREATE INDEX IF NOT EXISTS idx_online_attempts_student ON online_attempts(student_national_id);
CREATE INDEX IF NOT EXISTS idx_online_attempts_auth ON online_attempts(attempt_token_hash);
CREATE INDEX IF NOT EXISTS idx_online_answers_attempt ON online_answers(attempt_id);
```

---

## 3. قواعد عزل وخصوصية البيانات
1. **الاستقلال الكامل:** قاعدة بيانات السحابة تنشأ في خادم سحابي مستقل تماماً، ولا تمتلك أي اتصال أو معرفة بقاعدة بيانات الأستاذ `exam_platform.db`.
2. **الحذف التسلسلي (Cascade Deletion):** عند إتمام المزامنة وتطبيق أمر `Purge`، يؤدي حذف سجل الامتحان من جدول `online_exams` إلى الحذف التلقائي والفوري لكافة المحاولات والإجابات ومفتاح الإجابة السحابي.
3. **انعدام البيانات الحساسة:** لا يوجد في السحابة أي جدول للمعلمين، أو سجلات المدرسة، أو سجلات التدقيق الرقابي، أو كلمات مرور الطلاب.
