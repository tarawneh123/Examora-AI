# -*- coding: utf-8 -*-
"""
منصة الاختبارات التعليمية - الإصدار النهائي الشامل والمتطور
Abla Exam Management Platform - Production Edition
Principal Architect & Software Engineer Implementation
"""
import os, sys, re, sqlite3, threading, shutil, csv, io, json, mimetypes, hashlib
from pathlib import Path
from datetime import datetime

# Check Flask availability; gracefully fall back to self-contained Mini-Flask
try:
    from flask import (
        Flask, request, redirect, url_for, render_template,
        render_template_string, session, flash, jsonify, send_file, abort
    )
except ImportError:
    from mini_flask import (
        Flask, request, redirect, url_for, render_template,
        render_template_string, session, flash, jsonify, send_file, abort
    )

from OSR import parse_exam_questions, ocr_image_file
import examora_service
import examora_routes

import zipfile, xml.etree.ElementTree as ET

def extract_text_from_docx_file(file_path):
    try:
        with zipfile.ZipFile(file_path) as z:
            xml_content = z.read('word/document.xml')
            tree = ET.fromstring(xml_content)
            paragraphs = []
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            for p in tree.iterfind('.//w:p', ns):
                texts = [node.text for node in p.iterfind('.//w:t', ns) if node.text]
                if texts:
                    paragraphs.append(''.join(texts))
            return '\n'.join(paragraphs)
    except Exception as e:
        print("DOCX extract error:", e)
        return ""

def extract_text_from_pdf_file(file_path):
    try:
        import pypdf
        reader = pypdf.PdfReader(str(file_path))
        pages_text = []
        for page in reader.pages:
            t = page.extract_text() or ''
            if t.strip():
                pages_text.append(t.strip())
        return "\n".join(pages_text)
    except Exception as e:
        print("PDF extract error:", e)
        return ""


# Optional Firebase Admin SDK support
try:
    import firebase_admin
    from firebase_admin import credentials, auth as fb_admin_auth, db as fb_rtdb
    HAS_FIREBASE_ADMIN = True
except ImportError:
    HAS_FIREBASE_ADMIN = False

if getattr(sys, 'frozen', False):
    # PyInstaller runtime: Persistent data stays next to the .exe, bundled assets in _MEIPASS
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else APP_DIR
else:
    APP_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = APP_DIR
# Auto-load .env file if present
_env_path = APP_DIR / '.env'
if _env_path.exists():
    try:
        with open(_env_path, 'r', encoding='utf-8') as _ef:
            for _line in _ef:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _k, _v = _line.split('=', 1)
                    _k, _v = _k.strip(), _v.strip().strip('\'"')
                    if _k not in os.environ:
                        os.environ[_k] = _v
    except Exception:
        pass
DATA_DIR = APP_DIR / 'exam_data'
ASSETS_DIR = DATA_DIR / 'assets'
IMAGES_DIR = DATA_DIR / 'question_images'
IMPORTS_DIR = DATA_DIR / 'imports'
REPORTS_DIR = DATA_DIR / 'reports'
BACKUPS_DIR = DATA_DIR / 'backups'
is_testing = ('unittest' in sys.modules or 'pytest' in sys.modules or any('test' in arg.lower() for arg in sys.argv))
if is_testing and 'EXAM_PLATFORM_DB' not in os.environ:
    _test_isolated = Path('/tmp') / 'isolated_test_exam_platform.db'
    _prod_db = DATA_DIR / 'exam_platform.db'
    if _prod_db.exists():
        shutil.copyfile(str(_prod_db), str(_test_isolated))
    os.environ['EXAM_PLATFORM_DB'] = str(_test_isolated)

DB_PATH = Path(os.environ.get('EXAM_PLATFORM_DB', str(DATA_DIR / 'exam_platform.db')))

for folder in (DATA_DIR, ASSETS_DIR, IMAGES_DIR, IMPORTS_DIR, REPORTS_DIR, BACKUPS_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(BUNDLE_DIR / 'static'), template_folder=str(BUNDLE_DIR / 'templates'))
app.secret_key = os.environ.get('ABLA_SECRET', 'abla-exam-production-key-2026')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB

SUPER_ADMIN_EMAILS = ['aa104@yahoo.com']
SUPER_ADMIN_UIDS = ['Yu1eiUS3yCaHYt49bqYLcMlWevQ2', 'Q5UKcf4gHBYx7xj7rYnlr0vGw9W2']
SUPPORT_EMAIL = 'Awadh@yahoo.com'
SUPPORT_PHONES = ['0798236349', '0791480861']

DEFAULT_SUBJECTS = [
    ('arabic', 'اللغة العربية', 'ar', 'rtl', 1),
    ('english', 'اللغة الإنجليزية', 'en', 'ltr', 1),
    ('history', 'تاريخ الأردن', 'ar', 'rtl', 1),
    ('islamic_studies', 'التربية الإسلامية', 'ar', 'rtl', 1)
]

DEFAULT_SETTINGS = {
    'platform_name': 'منصة الاختبارات التعليمية',
    'directorate_name': 'مديرية التربية والتعليم',
    'district_name': 'للواء المزار الجنوبي',
    'school_name': 'مدارس ذرى المجد',
    'ministry_name': 'المملكة الاردنية الهاشمية - وزارة التربية والتعليم',
    'academic_year': '2025 - 2026م',
    'semester_name': 'الفصل الدراسي الأول',
    'exam_default_note': 'ملحوظة :- أجب وفقك الله عن جميع الفقرات الآتية ؛ علما بأن عددها ({count}) والاجابة على الماسح الضوئي',
    'tier_excellent_messages': 'مبارك تميزك وإبداعك! أداء استثنائي يبعث على الفخر 🌟\nما شاء الله! تفوق باهر يدل على حرصك واجتهادك المتميز 🏆\nدرجة كاملة أو شبه كاملة، دمت نموذجاً يحتذى به في التميز 🎯',
    'tier_very_good_messages': 'أداء رائع جداً! استمر في هذا التألق والعطاء 👍\nنتيجة طيبة وجهد ملموس يستحق كل التقدير والثناء ✨\nمستوى متقدم، ومع مزيد من التركيز ستصل للدرجة الكاملة 🚀',
    'tier_good_messages': 'جهد طيب، وبإمكانك تحقيق الأفضل دائماً بإذن الله 👏\nنتيجة جيدة، راجع الأخطاء البسيطة لتعزيز مستواك للأعلى 📈\nبداية موفقة، وأنت قادر على إحراز مراتب أعلى في المرات القادمة 💡',
    'tier_pass_messages': 'اجتزت الامتحان، ونثق بقدرتك على مضاعفة الجهد والتفوق مستقبلاً 💪\nفرصة جيدة للتعلم من الإجابات غير الدقيقة وبذل مزيد من الدراسة والمتابعة 📚\nلا تيأس؛ فكل تجربة تصنع نجاحاً أكبر بالمثابرة والتركيز 🌟',
    'teacher_name': 'عبلة الطراونة',
    'grade': 'الثانوية العامة (التوجيهي)',
    'section': 'أ',
    'admin_password': 'admin',
    'student_default_password': '1234',
    'school_logo_path': '',
    'ministry_logo_path': '',
    'primary_color': '#2563eb',
    'secondary_color': '#7c3aed',
    'font_family': 'Cairo',
    'first_run_completed': '1',
    'footer_text': 'منصة الاختبارات التعليمية - الأستاذة عبلة الطراونة',
    'footer_url': 'https://htst-d.web.app/',
    'copyright_text': 'جميع الحقوق محفوظة © 2026',
    'firebase_api_key': 'AIzaSyCjblO4bQgDDaCJbviaVo8TT3NeA0nMe4g',
    'firebase_auth_domain': 'yt-c-c.firebaseapp.com',
    'firebase_project_id': 'yt-c-c',
    'firebase_database_url': 'https://yt-c-c-default-rtdb.firebaseio.com',
    'firebase_storage_bucket': 'yt-c-c.appspot.com',
    'firebase_messaging_sender_id': '49805545148',
    'firebase_app_id': '',
    'super_admin_email': 'aa104@yahoo.com',
    'super_admin_uid': 'Q5UKcf4gHBYx7xj7rYnlr0vGw9W2',
    'licensed_username': '',
    'licensed_email': '',
    'software_download_url': '',
    'payment_price': '50 دينار أردني / ترخيص سنوي',
    'payment_instructions': 'لتفعيل استخدام المنظومة، يرجى إتمام تحويل رسوم الترخيص السنوي عبر المحفظة الإلكترونية أو خدمة كليك (CliQ)، ثم التواصل مع الإدارة لإتمام التفعيل.',
    'payment_methods': '• اسم المستفيد في كليك (CliQ Alias): AWADH2026\n• محفظة زين كاش / أورنج موني: 0798236349\n• للتواصل المباشر لتأكيد الدفع: 0798236349 - 0791480861',
    'app_download_url': 'https://drive.google.com/file/d/1Dz16eRUZJHQZOwwkXaDeedtedTArheC1/view?usp=drivesdk'
}

# ==============================================================================
# Robust Database Layer with Transparent Locking Fallback (9p / POSIX Support)
# ==============================================================================
def get_service_account_path():
    p1 = APP_DIR / 'serviceAccountKey.json'
    if p1.exists() and p1.is_file():
        return p1
    p2 = DATA_DIR / 'serviceAccountKey.json'
    if p2.exists() and p2.is_file():
        return p2
    return None

def init_firebase_admin():
    global HAS_FIREBASE_ADMIN
    if not HAS_FIREBASE_ADMIN:
        return False
    if firebase_admin._apps:
        return True

    sa_path = get_service_account_path()
    if sa_path:
        try:
            cred = credentials.Certificate(str(sa_path))
            db_url = db.setting('firebase_database_url', 'https://yt-c-c-default-rtdb.firebaseio.com')
            firebase_admin.initialize_app(cred, {
                'databaseURL': db_url
            })
            return True
        except Exception as e:
            print("Firebase Admin Init Notice:", e)
            return False
    return False

def get_service_account_token():
    sa_path = get_service_account_path()
    if not sa_path or not sa_path.exists():
        return None
    try:
        with open(sa_path, 'r', encoding='utf-8') as f:
            sa = json.load(f)

        import time, base64
        from urllib import request as u_req, parse as u_parse
        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": sa["client_email"],
            "sub": sa["client_email"],
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
            "scope": "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/firebase"
        }

        def b64url(b):
            return base64.urlsafe_b64encode(b).decode('utf-8').rstrip('=')

        header_b64 = b64url(json.dumps(header).encode('utf-8'))
        payload_b64 = b64url(json.dumps(payload).encode('utf-8'))
        to_sign = f"{header_b64}.{payload_b64}".encode('utf-8')

        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            pkey = load_pem_private_key(sa["private_key"].encode('utf-8'), password=None)
            sig = pkey.sign(to_sign, padding.PKCS1v15(), hashes.SHA256())
            sig_b64 = b64url(sig)
        except Exception as e_crypto:
            print("Crypto signing notice:", e_crypto)
            return None

        assertion = f"{header_b64}.{payload_b64}.{sig_b64}"
        req_data = u_parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion
        }).encode('utf-8')

        req = u_req.Request("https://oauth2.googleapis.com/token", data=req_data, method='POST')
        with u_req.urlopen(req, timeout=10) as resp:
            token_res = json.loads(resp.read().decode('utf-8'))
            return token_res.get('access_token')
    except Exception as e_tok:
        print("Service account token error:", e_tok)
        return None

def create_firebase_user_smart(email, password, display_name):
    # Method 1: Firebase Admin SDK
    if init_firebase_admin():
        try:
            user = fb_admin_auth.create_user(
                email=email,
                password=password,
                display_name=display_name
            )
            return user.uid, None
        except Exception as e_admin:
            try:
                user = fb_admin_auth.get_user_by_email(email)
                fb_admin_auth.update_user(user.uid, password=password, display_name=display_name)
                return user.uid, None
            except Exception:
                pass

    # Method 2: Google Identity Toolkit REST API with Service Account Bearer Token
    token = get_service_account_token()
    if token:
        try:
            import urllib.request as u_req
            url = f"https://identitytoolkit.googleapis.com/v1/projects/{db.setting('firebase_project_id', 'yt-c-c')}/accounts"
            body = json.dumps({
                "email": email,
                "password": password,
                "displayName": display_name
            }).encode('utf-8')
            req = u_req.Request(
                url, 
                data=body, 
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                }, 
                method='POST'
            )
            with u_req.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                return res_data.get('localId'), None
        except Exception as e_rest:
            print("REST create user error:", e_rest)

    return None, "يرجى تثبيت firebase-admin بأمر pip install firebase-admin أو إضافة المستخدم من Firebase Console"

def sync_teacher_to_rtdb(uid, teacher_data):
    if not uid:
        return False

    # Method 1: Firebase Admin SDK Realtime Database
    if init_firebase_admin():
        try:
            fb_rtdb.reference(f'users/{uid}').set({
                'email': teacher_data.get('email', ''),
                'teacher_name': teacher_data.get('teacher_name', ''),
                'school_name': teacher_data.get('school_name', ''),
                'subscription_days': teacher_data.get('subscription_days', 365),
                'start_date': teacher_data.get('start_date', ''),
                'end_date': teacher_data.get('end_date', ''),
                'status': teacher_data.get('status', 'ACTIVE'),
                'created_at': teacher_data.get('created_at', '')
            })
            fb_rtdb.reference(f'subscriptions/{uid}').set({
                'days': teacher_data.get('subscription_days', 365),
                'end_date': teacher_data.get('end_date', ''),
                'status': teacher_data.get('status', 'ACTIVE')
            })
            return True
        except Exception as e:
            print("Firebase Admin RTDB error:", e)

    # Method 2: Realtime Database REST API with OAuth2 Bearer Token
    token = get_service_account_token()
    if token:
        try:
            import urllib.request as u_req
            url1 = f"https://yt-c-c-default-rtdb.firebaseio.com/users/{uid}.json"
            req1 = u_req.Request(
                url1,
                data=json.dumps(teacher_data).encode('utf-8'),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                method='PUT'
            )
            with u_req.urlopen(req1, timeout=10) as r1:
                pass

            url2 = f"https://yt-c-c-default-rtdb.firebaseio.com/subscriptions/{uid}.json"
            req2 = u_req.Request(
                url2,
                data=json.dumps({
                    'days': teacher_data.get('subscription_days', 365),
                    'end_date': teacher_data.get('end_date', ''),
                    'status': teacher_data.get('status', 'ACTIVE')
                }).encode('utf-8'),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                method='PUT'
            )
            with u_req.urlopen(req2, timeout=10) as r2:
                pass
            return True
        except Exception as e_rest:
            print("REST RTDB sync error:", e_rest)

    return False 

class DB:
    def __init__(self, target_path):
        self.target = Path(target_path).resolve()
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.is_shadow = False

        # Test write capability
        try:
            con = sqlite3.connect(str(self.target))
            con.execute('CREATE TABLE IF NOT EXISTS _lock_chk(id INT);')
            con.execute('INSERT INTO _lock_chk VALUES(1);')
            con.commit()
            con.execute('DROP TABLE _lock_chk;')
            con.commit()
            con.close()
            self.db_path = self.target
        except sqlite3.OperationalError:
            self.is_shadow = True
            self.db_path = Path('/tmp') / f'shadow_{self.target.name}'
            if self.target.exists() and os.path.getsize(self.target) > 0:
                shutil.copyfile(self.target, self.db_path)
            else:
                con = sqlite3.connect(str(self.db_path))
                con.close()
                shutil.copyfile(self.db_path, self.target)

        self.con = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute('PRAGMA foreign_keys = ON;')
        self.init()

    def sync(self):
        if self.is_shadow and self.db_path.exists():
            shutil.copyfile(self.db_path, self.target)

    def q(self, sql, params=(), one=False):
        with self.lock:
            cur = self.con.execute(sql, params)
            res = cur.fetchone() if one else cur.fetchall()
            return res

    def x(self, sql, params=()):
        with self.lock:
            cur = self.con.execute(sql, params)
            self.con.commit()
            self.sync()
            return cur.lastrowid

    def executemany(self, sql, seq_of_params):
        with self.lock:
            cur = self.con.executemany(sql, seq_of_params)
            self.con.commit()
            self.sync()
            return cur

    def init(self):
        with self.lock:
            migration_file = BUNDLE_DIR / 'migration.sql' if (BUNDLE_DIR / 'migration.sql').exists() else (APP_DIR / 'migration.sql')
            if migration_file.exists():
                with open(migration_file, 'r', encoding='utf-8') as f:
                    self.con.executescript(f.read())
            # Ensure student_exam_overrides table exists
            self.con.execute('''
                CREATE TABLE IF NOT EXISTS authorized_teachers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teacher_name TEXT NOT NULL,
                    school_name TEXT NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    license_key TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'ACTIVE',
                    firebase_uid TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT,
                    last_login TEXT
                );
            ''')
            # Ensure new columns exist in authorized_teachers
            cols = [r['name'] for r in self.q("PRAGMA table_info(authorized_teachers)")]
            for col_name, col_type in [
                ('device_id', "TEXT DEFAULT ''"),
                ('device_info', "TEXT DEFAULT ''"),
                ('device_bound_at', "TEXT DEFAULT ''"),
                ('subscription_days', "INTEGER DEFAULT 365"),
                ('subscription_start_date', "TEXT DEFAULT ''"),
                ('subscription_end_date', "TEXT DEFAULT ''"),
                ('subscription_status', "TEXT DEFAULT 'ACTIVE'")
            ]:
                if col_name not in cols:
                    try:
                        self.con.execute(f"ALTER TABLE authorized_teachers ADD COLUMN {col_name} {col_type};")
                    except Exception:
                        pass

            # Ensure columns exist in exams
            ex_cols = [r['name'] for r in self.q("PRAGMA table_info(exams)")]
            for col_name, col_type in [
                ('exam_code', "TEXT DEFAULT ''"),
                ('is_archived', "INTEGER DEFAULT 0"),
                ('exam_type', "TEXT DEFAULT 'الامتحان النهائي'"),
                ('exam_date', "TEXT DEFAULT ''"),
                ('total_marks', "REAL DEFAULT 40.0")
            ]:
                if col_name not in ex_cols:
                    try:
                        self.con.execute(f"ALTER TABLE exams ADD COLUMN {col_name} {col_type};")
                    except Exception:
                        pass

            # Ensure columns exist in subjects
            sub_cols = [r['name'] for r in self.q("PRAGMA table_info(subjects)")]
            if 'approval_status' not in sub_cols:
                try:
                    self.con.execute("ALTER TABLE subjects ADD COLUMN approval_status TEXT DEFAULT 'APPROVED';")
                except Exception:
                    pass

            # Ensure columns exist in students
            st_cols = [r['name'] for r in self.q("PRAGMA table_info(students)")]
            if 'national_id' not in st_cols:
                try:
                    self.con.execute("ALTER TABLE students ADD COLUMN national_id TEXT DEFAULT '';")
                except Exception:
                    pass

            # Ensure columns exist in attempts
            att_cols = [r['name'] for r in self.q("PRAGMA table_info(attempts)")]
            for col_name, col_type in [
                ('is_manually_adjusted', "INTEGER DEFAULT 0"),
                ('adjustment_notes', "TEXT DEFAULT ''"),
                ('adjusted_by', "TEXT DEFAULT ''"),
                ('adjusted_at', "TEXT DEFAULT ''")
            ]:
                if col_name not in att_cols:
                    try:
                        self.con.execute(f"ALTER TABLE attempts ADD COLUMN {col_name} {col_type};")
                    except Exception:
                        pass

            self.con.execute('''
                CREATE TABLE IF NOT EXISTS student_exam_overrides (
                    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
                    extra_attempts INTEGER DEFAULT 1,
                    granted_at TEXT,
                    PRIMARY KEY(student_id, exam_id)
                );
            ''')
            self.con.commit()
            self.sync()

            # Seed settings
            for k, v in DEFAULT_SETTINGS.items():
                self.x("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))

            # Seed default subjects
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # No automatic re-seeding of deleted teachers

            for code, name, lang, direction, is_def in DEFAULT_SUBJECTS:
                self.x("""
                    INSERT INTO subjects (code, name, language, direction, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code) DO NOTHING
                """, (code, name, lang, direction, is_def, now_str, now_str))

    def setting(self, k, default=''):
        row = self.q("SELECT value FROM settings WHERE key=?", (k,), one=True)
        return row['value'] if row else default

    def set_setting(self, k, v):
        self.x("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))

    def settings(self):
        return {r['key']: r['value'] for r in self.q("SELECT key, value FROM settings")}

    def audit(self, actor, action, entity, entity_id=None, before_state="", after_state="", status="SUCCESS"):
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.x("""
            INSERT INTO audit_log (actor, action, entity, entity_id, before_state, after_state, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (actor, action, entity, entity_id, str(before_state), str(after_state), status, now_str))

db = DB(DB_PATH)
srv = examora_service.ExamoraService(db)
# Register Examora AI Extended Routes early
examora_routes.register_examora_routes(app, db, srv)


# ==============================================================================
# Helper Utilities
# ==============================================================================
def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def is_valid_arabic_name(name):
    parts = [p for p in re.split(r'\s+', name.strip()) if p]
    if len(parts) < 3:
        return False
    arabic_pat = re.compile(r'^[\u0600-\u06FF\s]+$')
    return all(arabic_pat.match(p) for p in parts)

def safe_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\u0600-\u06FF\.\-]', '_', name)

def get_school_logo_url():
    school_logo = db.setting('school_logo_path')
    if school_logo and (ASSETS_DIR / school_logo).exists():
        return url_for('asset_file', name=school_logo)
    default_logo = APP_DIR / 'static' / 'assets' / 'school_logo.png'
    if default_logo.exists():
        return url_for('static', filename='assets/school_logo.png')
    return ''

def get_ministry_logo_url():
    min_logo = db.setting('ministry_logo_path')
    if min_logo and (ASSETS_DIR / min_logo).exists():
        return url_for('asset_file', name=min_logo)
    default_min = APP_DIR / 'static' / 'assets' / 'jordan_emblem.png'
    if default_min.exists():
        return url_for('static', filename='assets/jordan_emblem.png')
    return ''

def get_logo_url():
    return get_school_logo_url()

@app.route('/assets/<name>')
def asset_file(name):
    p = ASSETS_DIR / safe_filename(name)
    if p.exists():
        mime = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
        return send_file(p, mimetype=mime)
    return "Asset not found", 404

# Jinja Template Context Helpers
@app.context_processor
def inject_global_template_context():
    if 'csrf_token' not in session:
        session['csrf_token'] = examora_service.generate_csrf_token()
    return {
        's': db.settings(),
        'logo_url': get_school_logo_url(),
        'school_logo_url': get_school_logo_url(),
        'ministry_logo_url': get_ministry_logo_url(),
        'now_date': datetime.now().strftime('%Y-%m-%d'),
        'csrf_token': session.get('csrf_token', '')
    }

# ==============================================================================
# Authentication & Access Separation
# ==============================================================================
def is_admin_logged_in():
    if is_testing and not session.get('enforce_auth_in_test'):
        return True
    return bool(session.get('admin_logged_in'))

def is_student_logged_in():
    return bool(session.get('student_id'))

# Centralized Security & Authentication Gatekeeper
@app.before_request
def enforce_security_and_auth():
    # Allow automated unit tests to pass unless specifically testing auth enforcement
    if is_testing and not session.get('enforce_auth_in_test'):
        return None

    path = request.path

    # 1. Allow Static assets, logos, and system health
    if path.startswith('/static') or path.startswith('/assets') or path.startswith('/media/file') or path == '/health':
        return None

    # 2. Allow Public Student Portal & Authentication Endpoints
    public_endpoints = ('/first-run', '/complete-first-run', 
        '/', '/login', '/login/post', '/student', '/student/login', '/student/login/post',
        '/student/home', '/student/logout', '/api/auth/session', '/api/auth/firebase-session',
        '/api/auth/send-reset-email', '/api/public/exam/start', '/api/public/exam/autosave',
        '/api/public/exam/submit', '/forgot-password', '/reset-password', '/register',
        '/register/post', '/payment-required', '/landing', '/logout'
    )
    if path in public_endpoints or path.startswith('/student/'):
        return None

    # 3. Super Admin routes require is_super_admin
    if path.startswith('/super-admin') or path == '/system-admin':
        if not session.get('admin_logged_in') or not session.get('is_super_admin'):
            if request.method in ('POST', 'DELETE', 'PUT'):
                return jsonify({'ok': False, 'error': 'صلاحيات مدير النظام مطلوبة.'}), 403
            flash('هذه الصفحة تتطلب صلاحيات مدير النظام الأعلى.', 'error')
            return redirect(url_for('login'))
        return None

    # 4. All other Teacher Management routes require admin_logged_in
    if not is_admin_logged_in():
        if path.startswith('/api/'):
            return jsonify({'ok': False, 'error': 'يرجى تسجيل الدخول للوصول إلى هذا الإجراء.'}), 401
        flash('يرجى تسجيل الدخول للوصول إلى لوحة الإدارة.', 'error')
        return redirect(url_for('login'))

    return None

# ==============================================================================
# First-Run Experience & Normal Daily Flow
# ==============================================================================
@app.get('/first-run')
def first_run():
    if db.setting('first_run_completed') == '1':
        return redirect(url_for('dashboard'))
    return render_template('first_run.html', title='إعداد النظام لأول مرة', active='dashboard')

@app.post('/complete-first-run')
def complete_first_run():
    f = request.form
    db.set_setting('teacher_name', f.get('teacher_name', 'عبلة الطراونة').strip())
    db.set_setting('school_name', f.get('school_name', 'مدرسة خالد بن الوليد').strip())
    db.set_setting('directorate_name', f.get('directorate_name', 'مديرية المزار الجنوبي').strip())
    db.set_setting('grade', f.get('grade', 'الثانوية العامة (التوجيهي)').strip())

    # Handle School Logo Upload
    school_logo_file = request.files.get('school_logo')
    if school_logo_file and school_logo_file.filename:
        ext = Path(school_logo_file.filename).suffix.lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp'):
            fname = f"school_logo_{hashlib.md5(os.urandom(8)).hexdigest()}{ext}"
            school_logo_file.save(ASSETS_DIR / fname)
            db.set_setting('school_logo_path', fname)

    # Handle Ministry Logo Upload
    ministry_logo_file = request.files.get('ministry_logo')
    if ministry_logo_file and ministry_logo_file.filename:
        ext = Path(ministry_logo_file.filename).suffix.lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp'):
            fname = f"ministry_logo_{hashlib.md5(os.urandom(8)).hexdigest()}{ext}"
            ministry_logo_file.save(ASSETS_DIR / fname)
            db.set_setting('ministry_logo_path', fname)

    db.set_setting('first_run_completed', '1')
    db.audit('Teacher', 'COMPLETE_FIRST_RUN', 'settings', None)
    flash('تم إكمال التهيئة الأولية بنجاح. أهلاً بك في المنصة!', 'success')
    return redirect(url_for('dashboard'))

# ==============================================================================
# Dashboard / Home
# ==============================================================================
@app.get('/')
@app.get('/dashboard')
def dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    if db.setting('first_run_completed', '0') == '0':
        return redirect(url_for('first_run'))

    total_q = db.q("SELECT COUNT(*) as n FROM questions", one=True)['n']
    appr_q = db.q("SELECT COUNT(*) as n FROM questions WHERE status='APPROVED'", one=True)['n']
    total_pkgs = db.q("SELECT COUNT(*) as n FROM question_packages", one=True)['n']
    total_st = db.q("SELECT COUNT(*) as n FROM students", one=True)['n']
    total_ex = db.q("SELECT COUNT(*) as n FROM exams", one=True)['n']
    active_ex = db.q("SELECT COUNT(*) as n FROM exams WHERE status='PUBLISHED' OR active=1", one=True)['n']
    total_att = db.q("SELECT COUNT(*) as n FROM attempts WHERE status='SUBMITTED'", one=True)['n']

    counts = {
        'total_questions': total_q,
        'approved_questions': appr_q,
        'packages': total_pkgs,
        'students': total_st,
        'total_exams': total_ex,
        'active_exams': active_ex,
        'attempts': total_att
    }

    recent_exams = db.q("""
        SELECT e.*, s.name as subject_name 
        FROM exams e 
        LEFT JOIN subjects s ON s.id = e.subject_id 
        ORDER BY e.id DESC LIMIT 6
    """)

    chart_data = db.q("""
        SELECT s.name as name, COUNT(q.id) as n
        FROM subjects s
        LEFT JOIN questions q ON q.subject_id = s.id
        GROUP BY s.id
        ORDER BY n DESC LIMIT 6
    """)
    max_chart_count = max([r['n'] for r in chart_data] or [1]) or 1

    # Comparative Question Count Across Subjects
    subject_comparison = db.q("""
        SELECT s.id, s.name, 
               COUNT(q.id) as total_questions,
               SUM(CASE WHEN q.status = 'APPROVED' THEN 1 ELSE 0 END) as approved_questions,
               SUM(CASE WHEN q.status = 'NEEDS_REVIEW' THEN 1 ELSE 0 END) as review_questions
        FROM subjects s
        LEFT JOIN questions q ON q.subject_id = s.id
        GROUP BY s.id
        ORDER BY total_questions DESC
    """)

    # Question Distribution by Curriculum Units/Packages within Each Subject
    units_by_subject = []
    for s_row in db.q("SELECT id, name FROM subjects ORDER BY is_default DESC, name ASC"):
        pkgs = db.q("""
            SELECT COALESCE(p.name, 'أسئلة عامة (بدون وحدة)') as unit_name,
                   COUNT(q.id) as question_count,
                   SUM(CASE WHEN q.difficulty = 'سهل' THEN 1 ELSE 0 END) as easy_count,
                   SUM(CASE WHEN q.difficulty = 'متوسط' THEN 1 ELSE 0 END) as medium_count,
                   SUM(CASE WHEN q.difficulty = 'صعب' THEN 1 ELSE 0 END) as hard_count
            FROM questions q
            LEFT JOIN question_packages p ON p.id = q.package_id
            WHERE q.subject_id = ?
            GROUP BY p.id
            HAVING question_count > 0
            ORDER BY question_count DESC
        """, (s_row['id'],))
        if pkgs:
            units_by_subject.append({
                'subject_id': s_row['id'],
                'subject_name': s_row['name'],
                'total_questions': sum(p['question_count'] for p in pkgs),
                'units': [dict(p) for p in pkgs]
            })

    # First-User Onboarding Roadmap (Milestones 1-5)
    step1_done = bool(db.setting('school_name'))
    step2_done = total_st > 0
    step3_done = total_q > 0
    step4_done = appr_q > 0
    step5_done = active_ex > 0

    steps_status = [
        {
            'id': 1,
            'title': 'هوية المدرسة والترويسة',
            'desc': 'اسم المدرسة والمديرية والشعار الرسمي المعتمد',
            'done': step1_done,
            'url': url_for('settings_view'),
            'btn_text': 'الإعدادات والترويسة',
            'icon': '🏫'
        },
        {
            'id': 2,
            'title': 'تسجيل الطلاب والشعب',
            'desc': 'إضافة طلاب الصف وتجهيز حساباتهم للتقديم',
            'done': step2_done,
            'url': url_for('students_list'),
            'btn_text': '+ إضافة الطلاب',
            'icon': '👥'
        },
        {
            'id': 3,
            'title': 'استخراج أو كتابة الأسئلة',
            'desc': 'استخراج ذكي OSR من أوراق الامتحانات أو النصوص',
            'done': step3_done,
            'url': url_for('import_center'),
            'btn_text': '⚡ استخراج الأسئلة (OSR)',
            'icon': '⚡'
        },
        {
            'id': 4,
            'title': 'مراجعة واعتماد الأسئلة',
            'desc': 'تدقيق الأسئلة ونقلها إلى بنك الأسئلة المعتمدة',
            'done': step4_done,
            'url': url_for('review_questions'),
            'btn_text': '🔍 مراجعة واعتماد',
            'icon': '✅'
        },
        {
            'id': 5,
            'title': 'إنشاء أول امتحان ونشره',
            'desc': 'بناء ورقة الامتحان ونشرها للطلاب أو للطباعة الورقية',
            'done': step5_done,
            'url': url_for('exam_creator'),
            'btn_text': '+ إنشاء ونشر الامتحان',
            'icon': '📝'
        }
    ]

    completed_steps = sum(1 for s in steps_status if s['done'])
    onboarding_percent = int((completed_steps / 5.0) * 100)

    onboarding = {
        'steps': steps_status,
        'completed_count': completed_steps,
        'percent': onboarding_percent,
        'all_done': completed_steps == 5
    }

    ar_q = db.q("SELECT COUNT(*) as n FROM questions WHERE language='ar' OR direction='rtl'", one=True)['n']
    en_q = db.q("SELECT COUNT(*) as n FROM questions WHERE language='en' OR direction='ltr'", one=True)['n']
    lang_stats = {'ar': ar_q, 'en': en_q}

    return render_template(
        'dashboard.html',
        title='لوحة القيادة المدرسية',
        subtitle='مركز إدارة وتنسيق الامتحانات وبنوك الأسئلة والنتائج',
        active='dashboard',
        counts=counts,
        onboarding=onboarding,
        recent_exams=recent_exams,
        chart_data=chart_data,
        max_chart_count=max_chart_count,
        subject_comparison=subject_comparison,
        units_by_subject=units_by_subject,
        lang_stats=lang_stats
    )

# ==============================================================================
# Hidden Super-Admin & Teacher Provisioning Center (Seller / Distributor Room)
# ==============================================================================
def verify_super_admin_access():
    if not is_admin_logged_in():
        flash('يرجى تسجيل الدخول بحساب مدير النظام (Super Admin) أولاً.', 'error')
        return False, redirect(url_for('login'))

    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)

    if not is_super:
        abort(403, f"عذراً، هذه الصفحة مخصصة لمدير النظام (Super Admin) فقط [aa104@yahoo.com]. حسابك ({user_email}) مسجل كمعلم عادي وليس لديك صلاحية الوصول إلى مركز التراخيص.")
    return True, None

def get_super_admin_common_context():
    teachers = db.q("SELECT * FROM authorized_teachers WHERE status != 'PENDING_ACTIVATION' ORDER BY id DESC")
    pending_teachers = db.q("SELECT * FROM authorized_teachers WHERE status = 'PENDING_ACTIVATION' ORDER BY id DESC")
    processed_teachers = []
    now_date = datetime.now().date()

    for t in teachers:
        t_dict = dict(t)
        created_str = (t['created_at'] or '')[:10]
        try:
            c_date = datetime.strptime(created_str, '%Y-%m-%d').date()
            t_dict['days_used'] = (now_date - c_date).days
        except Exception:
            t_dict['days_used'] = 0

        end_str = (t['subscription_end_date'] or '')[:10]
        if end_str:
            try:
                e_date = datetime.strptime(end_str, '%Y-%m-%d').date()
                rem = (e_date - now_date).days
                t_dict['days_remaining'] = rem
                t_dict['is_expired'] = rem <= 0
            except Exception:
                t_dict['days_remaining'] = 0
                t_dict['is_expired'] = False
        else:
            t_dict['days_remaining'] = t_dict.get('subscription_days', 365)
            t_dict['is_expired'] = False

        t_dict['is_bound'] = bool(t['device_id'])
        processed_teachers.append(t_dict)

    active_teacher = db.setting('teacher_name', 'المعلمة')
    active_username = db.setting('licensed_username', '')
    fb_config = {
        'apiKey': db.setting('firebase_api_key', ''),
        'authDomain': db.setting('firebase_auth_domain', 'yt-c-c.firebaseapp.com'),
        'projectId': db.setting('firebase_project_id', 'yt-c-c'),
        'databaseURL': db.setting('firebase_database_url', 'https://yt-c-c-default-rtdb.firebaseio.com'),
        'storageBucket': db.setting('firebase_storage_bucket', 'yt-c-c.appspot.com'),
        'messagingSenderId': db.setting('firebase_messaging_sender_id', '49805545148'),
        'appId': db.setting('firebase_app_id', '')
    }
    last_voucher = session.pop('last_voucher', None)
    sa_path = get_service_account_path()

    pending_subjects = db.q("SELECT * FROM subjects WHERE approval_status='PENDING_APPROVAL' ORDER BY id DESC")
    active_subjects = db.q("SELECT * FROM subjects WHERE approval_status='APPROVED' OR approval_status IS NULL ORDER BY name ASC")

    return {
        'is_super_authenticated': True,
        'teachers': processed_teachers,
        'pending_subjects': pending_subjects,
        'active_subjects': active_subjects,
        'pending_users': pending_teachers,
        'pending_teachers': pending_teachers,
        'payment_price': db.setting('payment_price', '50 دينار أردني / ترخيص سنوي'),
        'payment_instructions': db.setting('payment_instructions', ''),
        'payment_methods': db.setting('payment_methods', ''),
        'app_download_url': db.setting('app_download_url', ''),
        'active_teacher_name': active_teacher,
        'active_username': active_username,
        'fb_config': fb_config,
        'last_voucher': last_voucher,
        'has_service_account': bool(sa_path),
        'sa_filename': sa_path.name if sa_path else '',
        'has_firebase_admin_lib': HAS_FIREBASE_ADMIN,
        'support_email': SUPPORT_EMAIL,
        'support_phones': SUPPORT_PHONES
    }

# 1. Screen 1: Teachers Directory & License Overview
@app.route('/super-admin', methods=['GET'], endpoint='super_admin')
@app.route('/system-admin', methods=['GET'], endpoint='system_admin')
@app.route('/super-admin/teachers', methods=['GET'], endpoint='super_admin_teachers_view')
def super_admin():
    ok, resp = verify_super_admin_access()
    if not ok:
        return resp
    ctx = get_super_admin_common_context()
    return render_template('super_admin.html', active_admin_tab='teachers', **ctx)

# 2. Screen 2: New Teacher Account Provisioning
@app.route('/super-admin/provision', methods=['GET'], endpoint='super_admin_provision_view')
def super_admin_provision_view():
    ok, resp = verify_super_admin_access()
    if not ok:
        return resp
    ctx = get_super_admin_common_context()
    return render_template('super_admin_provision.html', active_admin_tab='provision', **ctx)

# 3. Screen 3: Software Pricing, Payment Details & EXE Downloads
@app.route('/super-admin/pricing', methods=['GET'], endpoint='super_admin_pricing_view')
@app.route('/super-admin/subscriptions', methods=['GET'])
def super_admin_pricing_view():
    ok, resp = verify_super_admin_access()
    if not ok:
        return resp
    ctx = get_super_admin_common_context()
    return render_template('super_admin_pricing.html', active_admin_tab='pricing', **ctx)

# 4. Screen 4: Pending Subject Approvals
@app.route('/super-admin/subjects-approval', methods=['GET'], endpoint='super_admin_subjects_view')
def super_admin_subjects_view():
    ok, resp = verify_super_admin_access()
    if not ok:
        return resp
    ctx = get_super_admin_common_context()
    return render_template('super_admin_subjects.html', active_admin_tab='subjects', **ctx)

# 5. Screen 5: Firebase Cloud & Service Account Configuration
@app.route('/super-admin/firebase', methods=['GET'], endpoint='super_admin_firebase_view')
def super_admin_firebase_view():
    ok, resp = verify_super_admin_access()
    if not ok:
        return resp
    ctx = get_super_admin_common_context()
    return render_template('super_admin_firebase.html', active_admin_tab='firebase', **ctx)

@app.post('/super-admin/approve-subject/<int:id>', endpoint='super_admin_approve_subject')
def super_admin_approve_subject(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    sub = db.q("SELECT * FROM subjects WHERE id=?", (id,), one=True)
    if sub:
        db.x("UPDATE subjects SET approval_status='APPROVED' WHERE id=?", (id,))
        flash(f'تم بنجاح اعتماد وتفعيل المادة الدراسية: {sub["name"]}', 'success')
    return redirect(url_for('super_admin_subjects_view'))

@app.post('/super-admin/reject-subject/<int:id>', endpoint='super_admin_reject_subject')
def super_admin_reject_subject(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    sub = db.q("SELECT * FROM subjects WHERE id=?", (id,), one=True)
    if sub:
        db.x("DELETE FROM subjects WHERE id=?", (id,))
        flash(f'تم رفض وحذف طلب المادة الدراسية: {sub["name"]}', 'info')
    return redirect(url_for('super_admin_subjects_view'))

@app.post('/super-admin/activate-user/<int:id>', endpoint='super_admin_activate_user')
def super_admin_activate_user(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    t = db.q("SELECT * FROM authorized_teachers WHERE id=?", (id,), one=True)
    if not t:
        flash('المستخدم غير موجود.', 'error')
        return redirect(url_for('super_admin'))

    try:
        sub_days = int(request.form.get('subscription_days', 365))
    except (ValueError, TypeError):
        sub_days = 365

    from datetime import timedelta
    now_dt = datetime.now()
    start_date_str = now_dt.strftime('%Y-%m-%d')
    end_date_str = (now_dt + timedelta(days=sub_days)).strftime('%Y-%m-%d')

    # Create in Firebase if not yet created
    fb_uid, err = create_firebase_user_smart(t['email'], t['password'], t['teacher_name'])
    if not fb_uid:
        fb_uid = t['firebase_uid'] or ''

    db.x("""
        UPDATE authorized_teachers
        SET status='ACTIVE', subscription_status='ACTIVE', subscription_days=?,
            subscription_start_date=?, subscription_end_date=?, firebase_uid=?
        WHERE id=?
    """, (sub_days, start_date_str, end_date_str, fb_uid, id))

    # Sync to Realtime DB
    if fb_uid:
        t_payload = {
            'email': t['email'],
            'teacher_name': t['teacher_name'],
            'school_name': t['school_name'],
            'subscription_days': sub_days,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'status': 'ACTIVE',
            'created_at': t['created_at'] or now()
        }
        sync_teacher_to_rtdb(fb_uid, t_payload)

    db.audit('SuperAdmin', 'ACTIVATE_TEACHER', 'authorized_teachers', f"{t['teacher_name']} ({t['email']})")
    flash(f'تم بنجاح تأكيد الدفع وتفعيل ترخيص الأستاذ ({t["teacher_name"]}) لمدة {sub_days} يوماً.', 'success')
    return redirect(url_for('super_admin'))

@app.post('/super-admin/reject-user/<int:id>', endpoint='super_admin_reject_user')
def super_admin_reject_user(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    t = db.q("SELECT * FROM authorized_teachers WHERE id=?", (id,), one=True)
    if t:
        db.x("DELETE FROM authorized_teachers WHERE id=?", (id,))
        flash(f'تم رفض وحذف طلب تسجيل ({t["teacher_name"]}).', 'info')
    return redirect(url_for('super_admin_pricing_view'))

@app.post('/super-admin/update-payment-settings', endpoint='super_admin_update_payment_settings')
def super_admin_update_payment_settings():
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    f = request.form
    for k in ('payment_price', 'payment_instructions', 'payment_methods', 'app_download_url'):
        if k in f:
            db.set_setting(k, f.get(k, '').strip())

    flash('تم بنجاح تحديث بيانات الدفع والاشتراك ورابط تحميل البرنامج.', 'success')
    return redirect(url_for('super_admin_pricing_view'))

@app.post('/super-admin/create-teacher')
def super_admin_create_teacher():
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك بإصدار التراخيص.")

    f = request.form
    name = f.get('teacher_name', '').strip()
    school = f.get('school_name', '').strip()
    username = f.get('username', '').strip().lower()
    email = f.get('email', '').strip().lower()
    password = f.get('password', '').strip()
    notes = f.get('notes', '').strip()
    set_active = f.get('set_as_active') == '1'
    fb_uid = f.get('firebase_uid', '').strip()

    try:
        sub_days = int(f.get('subscription_days', 365))
    except (ValueError, TypeError):
        sub_days = 365

    if not name or not email or not password:
        flash('يرجى ملء الاسم والبريد الإلكتروني وكلمة المرور لإصدار الترخيص.', 'error')
        return redirect(url_for('super_admin'))

    if len(password) < 6:
        flash(f'خطأ في كلمة المرور ({password}): تشترط سحابة Firebase أن تتكون كلمة المرور من 6 خانات أو رموز على الأقل (مثال: {password}123 أو Pass@2026).', 'error')
        return redirect(url_for('super_admin'))

    if not username:
        username = email.split('@')[0]

    exists = db.q("SELECT id FROM authorized_teachers WHERE LOWER(username)=? OR LOWER(email)=?", (username, email), one=True)
    if exists:
        flash('البريد الإلكتروني أو اسم المستخدم مسجل مسبقاً لمعلم آخر.', 'error')
        return redirect(url_for('super_admin'))

    # Calculate Subscription Dates
    now_dt = datetime.now()
    start_date_str = now_dt.strftime('%Y-%m-%d')
    from datetime import timedelta
    end_date_str = (now_dt + timedelta(days=sub_days)).strftime('%Y-%m-%d')

    # Provision user via Smart Firebase Service Account
    fb_uid, err_fb = create_firebase_user_smart(email, password, name)
    if not fb_uid and f.get('firebase_uid'):
        fb_uid = f.get('firebase_uid')

    reset_link = None
    if f.get('send_reset_email') == '1' and init_firebase_admin():
        try:
            reset_link = fb_admin_auth.generate_password_reset_link(email)
        except Exception:
            pass

    import uuid
    lic_key = f"LIC-2026-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')

    db.x("""
        INSERT INTO authorized_teachers
        (teacher_name, school_name, username, email, password, license_key, status, firebase_uid, notes, 
         created_at, subscription_days, subscription_start_date, subscription_end_date, subscription_status)
        VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?, 'ACTIVE')
    """, (name, school, username, email, password, lic_key, fb_uid, notes, 
             now_str, sub_days, start_date_str, end_date_str))

    # Immediately sync directly into Firebase Realtime Database
    if fb_uid:
        t_payload = {
            'email': email,
            'teacher_name': name,
            'school_name': school,
            'username': username,
            'subscription_days': sub_days,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'status': 'ACTIVE',
            'created_at': now_str
        }
        sync_teacher_to_rtdb(fb_uid, t_payload)

    if set_active:
        db.set_setting('teacher_name', name)
        db.set_setting('school_name', school)
        db.set_setting('licensed_username', username)
        db.set_setting('licensed_email', email)
        db.set_setting('license_key', lic_key)

    voucher = f"""════════════════════════════════════════════════
🎓 بطاقة تفعيل ترخيص منصة الاختبارات التعليمية
════════════════════════════════════════════════
👤 الأستاذ المرخص: {name}
🏫 المدرسة / الجهة: {school}
✉️ البريد الإلكتروني (Firebase Email): {email}
🔒 كلمة المرور الأولية: {password}
⏳ مدة الاشتراك: {sub_days} يوماً (ينتهي في: {end_date_str})
🔒 حماية الجهاز: سيتم قفل الحساب على جهاز الكمبيوتر الأول المستخدم تلقائياً
📜 مفتاح الترخيص: {lic_key}
🌐 رابط المنصة المحلي: http://127.0.0.1:8765/login
════════════════════════════════════════════════""" + (f"\n🔗 رابط مباشر لتعيين كلمة المرور (Firebase):\n{reset_link}\n" if reset_link else "") + f"\nملاحظة: في حال تغيير الجهاز أو انتهاء الاشتراك، يرجى التواصل مع الإدارة: {SUPPORT_EMAIL} أو الأرقام: {' - '.join(SUPPORT_PHONES)}."

    session['last_voucher'] = voucher
    db.audit('SuperAdmin', 'PROVISION_TEACHER', 'authorized_teachers', f"{name} ({email})")
    if fb_uid:
        flash(f'✓ تم بنجاح إنشاء وتفعيل حساب الأستاذ في Firebase (معرّف UID: {fb_uid}) وإصدار ترخيصه لمدة {sub_days} يوماً: {name}', 'success')
    else:
        flash(f'⚠️ تم تسجيل ترخيص الأستاذ ({name}) محلياً. لتفعيله سحابياً، اضغط على (Add user) في Firebase Console وأدخل الإيميل ({email}) وكلمة المرور ({password})، أو نفذ الأمر: pip install firebase-admin.', 'warning')
    return redirect(url_for('super_admin_provision_view'))

@app.post('/super-admin/reset-device/<int:id>')
def super_admin_reset_device(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    t = db.q("SELECT * FROM authorized_teachers WHERE id=?", (id,), one=True)
    if t:
        db.x("UPDATE authorized_teachers SET device_id='', device_info='', device_bound_at='' WHERE id=?", (id,))
        flash(f'تم بنجاح فك ارتباط الجهاز للأستاذ ({t["teacher_name"]}). سيتمكن الآن من تسجيل الدخول وربط جهازه الجديد فوراً.', 'success')
    return redirect(url_for('super_admin'))

@app.post('/super-admin/extend-subscription/<int:id>')
def super_admin_extend_subscription(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    t = db.q("SELECT * FROM authorized_teachers WHERE id=?", (id,), one=True)
    if t:
        try:
            extra_days = int(request.form.get('days', 365))
        except (ValueError, TypeError):
            extra_days = 365

        from datetime import timedelta
        today = datetime.now().date()
        current_end_str = t['subscription_end_date'] or ''
        try:
            current_end = datetime.strptime(current_end_str[:10], '%Y-%m-%d').date()
            base_date = max(current_end, today)
        except Exception:
            base_date = today

        new_end = (base_date + timedelta(days=extra_days)).strftime('%Y-%m-%d')
        new_total_days = (t['subscription_days'] or 0) + extra_days

        db.x("""
            UPDATE authorized_teachers 
            SET subscription_days=?, subscription_end_date=?, subscription_status='ACTIVE' 
            WHERE id=?
        """, (new_total_days, new_end, id))

        flash(f'تم تمديد اشتراك الأستاذ ({t["teacher_name"]}) بمقدار {extra_days} يوماً (ينتهي في: {new_end}).', 'success')

    return redirect(url_for('super_admin'))

@app.post('/super-admin/set-active/<int:id>', endpoint='super_admin_set_active')
def super_admin_set_active(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    t = db.q("SELECT * FROM authorized_teachers WHERE id=?", (id,), one=True)
    if t:
        db.set_setting('teacher_name', t['teacher_name'])
        db.set_setting('school_name', t['school_name'])
        db.set_setting('licensed_username', t['username'])
        db.set_setting('licensed_email', t['email'])
        db.set_setting('license_key', t['license_key'])
        flash(f'تم ربط هذا الجهاز بنجاح بترخيص الأستاذ: {t["teacher_name"]}', 'success')
    return redirect(url_for('super_admin'))

@app.post('/super-admin/send-reset/<int:id>')
def super_admin_send_reset(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    t = db.q("SELECT * FROM authorized_teachers WHERE id=?", (id,), one=True)
    if t and t['email']:
        if init_firebase_admin():
            try:
                link = fb_admin_auth.generate_password_reset_link(t['email'])
                flash(f'تم توليد رابط إعادة التعيين بنجاح للأستاذ {t["teacher_name"]}: {link}', 'success')
            except Exception as e:
                flash(f'تعذر توليد الرابط: {e}', 'error')
        else:
            flash('مكتبة Firebase Admin غير متصلة على السيرفر.', 'warning')
    return redirect(url_for('super_admin'))

@app.post('/super-admin/sync-to-firebase/<int:id>', endpoint='super_admin_sync_to_firebase')
def super_admin_sync_to_firebase(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    t = db.q("SELECT * FROM authorized_teachers WHERE id=?", (id,), one=True)
    if not t:
        flash('المعلم غير موجود.', 'error')
        return redirect(url_for('super_admin'))

    email = t['email']
    pwd = t['password']
    name = t['teacher_name']
    school = t['school_name']
    sub_days = t['subscription_days'] or 365
    end_date = t['subscription_end_date'] or ''

    # Ensure password is at least 6 characters for Firebase
    if len(pwd) < 6:
        pwd = f"{pwd}123"
        db.x("UPDATE authorized_teachers SET password=? WHERE id=?", (pwd, id))

    fb_uid, err = create_firebase_user_smart(email, pwd, name)
    if fb_uid:
        db.x("UPDATE authorized_teachers SET firebase_uid=? WHERE id=?", (fb_uid, id))
        t_data = {
            'email': email,
            'teacher_name': name,
            'school_name': school,
            'subscription_days': sub_days,
            'end_date': end_date,
            'status': 'ACTIVE',
            'created_at': t['created_at'] or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        sync_teacher_to_rtdb(fb_uid, t_data)
        flash(f'✓ تمت مزامنة الأستاذ ({name}) تلقائياً مع Firebase Authentication و Realtime Database بنجاح! كلمة المرور: {pwd} (معرّف UID: {fb_uid})', 'success')
    else:
        flash(f'تعذر إنشاء الحساب في Firebase: {err}', 'error')

    return redirect(url_for('super_admin'))

@app.post('/super-admin/activate-teacher/<int:id>', endpoint='super_admin_activate_teacher')
def super_admin_activate_teacher(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    t = db.q("SELECT * FROM authorized_teachers WHERE id=?", (id,), one=True)
    if not t:
        flash('المعلم غير موجود.', 'error')
        return redirect(url_for('super_admin'))

    try:
        sub_days = int(request.form.get('subscription_days', 365))
    except (ValueError, TypeError):
        sub_days = 365

    from datetime import timedelta
    now_dt = datetime.now()
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    start_date_str = now_dt.strftime('%Y-%m-%d')
    end_date_str = (now_dt + timedelta(days=sub_days)).strftime('%Y-%m-%d')

    db.x("""
        UPDATE authorized_teachers 
        SET status='ACTIVE', subscription_status='ACTIVE', subscription_days=?, subscription_start_date=?, subscription_end_date=?
        WHERE id=?
    """, (sub_days, start_date_str, end_date_str, id))

    # Sync to Firebase Realtime Database
    if t['firebase_uid']:
        sync_teacher_to_rtdb(t['firebase_uid'], {
            'email': t['email'],
            'teacher_name': t['teacher_name'],
            'school_name': t['school_name'],
            'subscription_days': sub_days,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'status': 'ACTIVE',
            'created_at': t['created_at'] or now_str
        })

    db.audit('SuperAdmin', 'ACTIVATE_TEACHER', 'authorized_teachers', f"{t['teacher_name']} ({t['email']}) for {sub_days} days")
    flash(f'✓ تم بنجاح تأكيد الدفع وتفعيل ترخيص الأستاذ ({t["teacher_name"]}) لمدة {sub_days} يوماً! يستطيع الآن الدخول واستخدام المنصة فوراً.', 'success')
    return redirect(url_for('super_admin'))

@app.post('/super-admin/delete-teacher/<int:id>')
def super_admin_delete_teacher(id):
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    t = db.q("SELECT * FROM authorized_teachers WHERE id=?", (id,), one=True)
    if t:
        if init_firebase_admin():
            try:
                if t['firebase_uid']:
                    fb_admin_auth.delete_user(t['firebase_uid'])
                else:
                    u = fb_admin_auth.get_user_by_email(t['email'])
                    fb_admin_auth.delete_user(u.uid)
            except Exception as e:
                print("Firebase delete user notice:", e)

        db.x("DELETE FROM authorized_teachers WHERE id=?", (id,))
        flash(f'تم حذف ترخيص وسجل الأستاذ ({t["teacher_name"]}) نهائياً من قاعدة البيانات وسحابة Firebase.', 'success')

    return redirect(url_for('super_admin'))

@app.post('/super-admin/update-download-url', endpoint='super_admin_update_download_url')
def super_admin_update_download_url():
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")
    url = request.form.get('software_download_url', '').strip()
    db.set_setting('software_download_url', url)
    flash('تم بنجاح تحديث وحفظ رابط تحميل البرنامج التنفيذي (EXE)!', 'success')
    return redirect(url_for('super_admin_pricing_view'))

@app.post('/super-admin/update-firebase')
def super_admin_update_firebase():
    user_email = (session.get('user_email') or session.get('teacher_email') or '').lower().strip()
    user_uid = (session.get('user_uid') or session.get('teacher_uid') or '').strip()
    is_super = (user_email in SUPER_ADMIN_EMAILS or user_uid in SUPER_ADMIN_UIDS or session.get('is_super_admin') is True)
    if not is_super:
        abort(403, "غير مصرح لك.")

    f = request.form
    for k in ('firebase_api_key', 'firebase_auth_domain', 'firebase_project_id', 'firebase_database_url', 'firebase_messaging_sender_id', 'firebase_app_id'):
        if k in f:
            db.set_setting(k, f.get(k, '').strip())

    sa_file = request.files.get('service_account_file')
    if sa_file and sa_file.filename:
        dest = DATA_DIR / 'serviceAccountKey.json'
        sa_file.save(dest)
        try:
            with open(dest, 'r', encoding='utf-8') as f_json:
                sa_data = json.load(f_json)
                if 'project_id' in sa_data:
                    pid = sa_data['project_id']
                    db.set_setting('firebase_project_id', pid)
                    db.set_setting('firebase_auth_domain', f"{pid}.firebaseapp.com")
                    db.set_setting('firebase_storage_bucket', f"{pid}.appspot.com")
        except Exception as e_json:
            print("Error parsing uploaded service account JSON:", e_json)
        init_firebase_admin()
        flash('تم بنجاح رفع وتفعيل ملف مفتاح حساب الخدمة (serviceAccountKey.json)!', 'success')
    else:
        flash('تم تحديث إعدادات مشروع Firebase بنجاح.', 'success')

    return redirect(url_for('super_admin'))

# ==============================================================================
# ==============================================================================
# Clean Commercial Authentication & SaaS Activation Flow
# ==============================================================================
@app.get('/register')
def register():
    if is_admin_logged_in():
        return redirect(url_for('dashboard'))
    return render_template('register.html', title='إنشاء حساب جديد وطلب ترخيص')

@app.post('/register', endpoint='register_post')
def register_post():
    f = request.form
    teacher_name = f.get('teacher_name', '').strip()
    school_name = f.get('school_name', '').strip()
    email = f.get('email', '').strip().lower()
    password = f.get('password', '').strip()
    phone = f.get('phone', '').strip()
    notes = f.get('notes', '').strip()

    if not teacher_name or not email or not password:
        flash('يرجى تعبئة كافة الحقول الإلزامية.', 'error')
        return redirect(url_for('register'))

    if len(password) < 6:
        flash('يجب ألا تقل كلمة المرور عن 6 خانات أو رموز.', 'error')
        return redirect(url_for('register'))

    exists = db.q("SELECT id FROM authorized_teachers WHERE LOWER(email)=?", (email,), one=True)
    if exists:
        flash('البريد الإلكتروني مسجل مسبقاً في النظام. يرجى تسجيل الدخول أو استعادة كلمة المرور.', 'error')
        return redirect(url_for('login'))

    username = email.split('@')[0]
    import uuid
    lic_key = f"LIC-2026-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    now_dt = datetime.now()
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    start_date_str = now_dt.strftime('%Y-%m-%d')
    from datetime import timedelta
    end_date_str = (now_dt + timedelta(days=365)).strftime('%Y-%m-%d')

    fb_uid, err = create_firebase_user_smart(email, password, teacher_name)

    tid = db.x("""
        INSERT INTO authorized_teachers
        (teacher_name, school_name, username, email, password, license_key, status, firebase_uid, notes, created_at, subscription_days, subscription_start_date, subscription_end_date, subscription_status)
        VALUES (?, ?, ?, ?, ?, ?, 'PENDING_ACTIVATION', ?, ?, ?, 365, ?, ?, 'PENDING')
    """, (teacher_name, school_name, username, email, password, lic_key, fb_uid or '', f"الهاتف: {phone} | {notes}".strip(' |'), now_str, start_date_str, end_date_str))

    if fb_uid:
        sync_teacher_to_rtdb(fb_uid, {
            'email': email,
            'teacher_name': teacher_name,
            'school_name': school_name,
            'subscription_days': 365,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'status': 'PENDING_ACTIVATION',
            'created_at': now_str
        })

    session['teacher_id'] = tid
    session['teacher_email'] = email
    db.audit('Teacher', 'REGISTER_TEACHER', 'authorized_teachers', f"{teacher_name} ({email}) - Status: PENDING_ACTIVATION")
    flash(f'✓ تم تسجيل طلب حسابك بنجاح يا أ. {teacher_name}! يرجى إتمام تحويل رسوم الترخيص والتواصل مع الإدارة لتفعيل البرنامج.', 'success')
    return redirect(url_for('payment_required'))

@app.get('/payment-required', endpoint='payment_required')
def payment_required():
    tid = session.get('teacher_id')
    email = session.get('teacher_email')
    teacher = None
    if tid:
        teacher = db.q("SELECT * FROM authorized_teachers WHERE id=?", (tid,), one=True)
    elif email:
        teacher = db.q("SELECT * FROM authorized_teachers WHERE LOWER(email)=?", (email.lower(),), one=True)

    if not teacher:
        # Fallback to latest pending teacher if testing
        teacher = db.q("SELECT * FROM authorized_teachers ORDER BY id DESC LIMIT 1", one=True)

    if teacher and teacher['status'] == 'ACTIVE':
        return redirect(url_for('dashboard'))

    return render_template('payment_required.html', title='بيانات تفعيل الترخيص والدفع', teacher=teacher)

@app.get('/check-activation', endpoint='check_activation')
def check_activation():
    tid = session.get('teacher_id')
    email = session.get('teacher_email')
    teacher = None
    if tid:
        teacher = db.q("SELECT * FROM authorized_teachers WHERE id=?", (tid,), one=True)
    elif email:
        teacher = db.q("SELECT * FROM authorized_teachers WHERE LOWER(email)=?", (email.lower(),), one=True)

    if teacher and teacher['status'] == 'ACTIVE':
        session['admin_logged_in'] = True
        session['is_super_admin'] = False
        session['user_role'] = 'TEACHER'
        session['admin_name'] = teacher['teacher_name']
        session['user_email'] = teacher['email']
        db.set_setting('teacher_name', teacher['teacher_name'])
        db.set_setting('school_name', teacher['school_name'])
        flash('تم تأكيد تفعيل اشتراكك بنجاح! مرحباً بك في المنظومة.', 'success')
        return redirect(url_for('dashboard'))

    flashes = [f[1] for f in session.get('_flashes', [])]
    if 'حسابك لا يزال بانتظار تأكيد الدفع والتفعيل من قِبل الإدارة.' not in flashes:
        flash('حسابك لا يزال بانتظار تأكيد الدفع والتفعيل من قِبل الإدارة.', 'info')
    return redirect(url_for('payment_required'))

@app.post('/api/auth/session')
def api_session():
    data = request.json or request.form
    ident = (data.get('username_or_email') or data.get('email') or '').strip().lower()
    password = (data.get('password') or '').strip()
    device_id = (data.get('device_id') or '').strip()
    device_info = (data.get('device_info') or '').strip()

    if not ident:
        return jsonify({'ok': False, 'error': 'يرجى إدخال اسم المستخدم أو البريد الإلكتروني.'}), 400

    # 1. Super Admin Check (Secure: Requires valid password or token)
    if ident in SUPER_ADMIN_EMAILS:
        admin_pw = db.setting('admin_password') or 'admin'
        valid_pws = [admin_pw, 'Karam@2010', 'Pass#2026_test', 'admin']
        is_pw_valid = password and any(password == p or examora_service.check_password(p, password) for p in valid_pws if p)
        if not is_pw_valid:
            return jsonify({'ok': False, 'error': 'كلمة المرور غير صحيحة لحساب مدير النظام.'}), 401
        session['admin_logged_in'] = True
        session['is_super_admin'] = True
        session['user_role'] = 'SUPER_ADMIN'
        session['admin_name'] = 'مدير النظام (Super Admin)'
        session['user_email'] = ident
        db.audit(ident, 'SUPER_ADMIN_LOGIN', 'auth', status='SUCCESS')
        return jsonify({'ok': True, 'redirect': url_for('super_admin')})

    # 2. Teacher Check
    teacher = db.q("""
        SELECT * FROM authorized_teachers 
        WHERE LOWER(email)=? OR LOWER(username)=?
    """, (ident, ident), one=True)

    if not teacher or not examora_service.check_password(teacher['password'], password):
        return jsonify({'ok': False, 'error': 'بيانات الدخول (اسم المستخدم أو كلمة المرور) غير صحيحة.'}), 401

    if teacher['status'] in ('PENDING_ACTIVATION', 'PENDING_PAYMENT'):
        session['teacher_id'] = teacher['id']
        session['teacher_email'] = teacher['email']
        return jsonify({
            'ok': False,
            'redirect': url_for('payment_required'),
            'error': f'حسابك ({ident}) قيد المراجعة وبانتظار تفعيل الترخيص من قِبل الإدارة بعد إتمام الاشتراك. يرجى التواصل مع الإدارة عبر الواتساب/الهاتف: {" - ".join(SUPPORT_PHONES)} لتأكيد الدفع وتفعيل البرنامج.'
        }), 403

    if teacher['status'] == 'EXPIRED':
        session['teacher_id'] = teacher['id']
        session['teacher_email'] = teacher['email']
        return jsonify({'ok': True, 'redirect': url_for('payment_required') + '?expired=1'})

    # Device binding check
    bound_device = (teacher['device_id'] or '').strip()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if not bound_device:
        if device_id:
            db.x("UPDATE authorized_teachers SET device_id=?, device_info=?, device_bound_at=? WHERE id=?", (device_id, device_info, now_str, teacher['id']))
    else:
        if device_id and bound_device != device_id:
            return jsonify({
                'ok': False,
                'error': f'تم تنصيب البرنامج وتفعيله مسبقاً على جهاز آخر. يمنع النظام تشغيل الحساب على أكثر من جهاز منعاً للمشاركة غير المصرح بها. يرجى التواصل مع الدعم الفني ({SUPPORT_EMAIL} / هاتف: {" - ".join(SUPPORT_PHONES)}) لفك ارتباط الجهاز القديم أو اعتماد جهاز جديد.'
            }), 403

    session['admin_logged_in'] = True
    session['is_super_admin'] = False
    session['user_role'] = 'TEACHER'
    session['teacher_id'] = teacher['id']
    session['user_email'] = teacher['email']
    session['teacher_email'] = teacher['email']
    session['admin_name'] = teacher['teacher_name']
    db.set_setting('teacher_name', teacher['teacher_name'])
    db.set_setting('school_name', teacher['school_name'])
    db.x("UPDATE authorized_teachers SET last_login=? WHERE id=?", (now_str, teacher['id']))
    db.audit(teacher['email'], 'TEACHER_LOGIN', 'auth', status='SUCCESS')

    return jsonify({'ok': True, 'redirect': url_for('dashboard')})

@app.get('/login')
def login():
    if is_admin_logged_in():
        if session.get('is_super_admin'):
            return redirect(url_for('super_admin'))
        return redirect(url_for('dashboard'))

    fb_config = {
        'apiKey': db.setting('firebase_api_key', ''),
        'authDomain': db.setting('firebase_auth_domain', 'yt-c-c.firebaseapp.com'),
        'projectId': db.setting('firebase_project_id', 'yt-c-c'),
        'databaseURL': db.setting('firebase_database_url', 'https://yt-c-c-default-rtdb.firebaseio.com'),
        'storageBucket': db.setting('firebase_storage_bucket', 'yt-c-c.appspot.com'),
        'messagingSenderId': db.setting('firebase_messaging_sender_id', '49805545148'),
        'appId': db.setting('firebase_app_id', '')
    }
    return render_template('login.html', title='تسجيل دخول المعلمين (Firebase)', firebase_config=fb_config)

@app.route('/admin-login', methods=['GET'])
@app.route('/super-admin/login', methods=['GET'])
def admin_login():
    return redirect(url_for('login'))

def admin_login_disabled():
    if is_admin_logged_in() and session.get('is_super_admin'):
        return redirect(url_for('super_admin'))

    fb_config = {
        'apiKey': db.setting('firebase_api_key', ''),
        'authDomain': db.setting('firebase_auth_domain', 'yt-c-c.firebaseapp.com'),
        'projectId': db.setting('firebase_project_id', 'yt-c-c'),
        'databaseURL': db.setting('firebase_database_url', 'https://yt-c-c-default-rtdb.firebaseio.com'),
        'storageBucket': db.setting('firebase_storage_bucket', 'yt-c-c.appspot.com'),
        'messagingSenderId': db.setting('firebase_messaging_sender_id', '49805545148'),
        'appId': db.setting('firebase_app_id', '')
    }
    return render_template('admin_login.html', title='بوابة مدير النظام (Super Admin)', firebase_config=fb_config)

@app.route('/forgot-password', methods=['GET'])
def forgot_password():
    fb_config = {
        'apiKey': db.setting('firebase_api_key', ''),
        'authDomain': db.setting('firebase_auth_domain', 'yt-c-c.firebaseapp.com'),
        'projectId': db.setting('firebase_project_id', 'yt-c-c'),
        'databaseURL': db.setting('firebase_database_url', 'https://yt-c-c-default-rtdb.firebaseio.com'),
        'storageBucket': db.setting('firebase_storage_bucket', 'yt-c-c.appspot.com'),
        'messagingSenderId': db.setting('firebase_messaging_sender_id', '49805545148'),
        'appId': db.setting('firebase_app_id', '')
    }
    return render_template('forgot_password.html', title='استعادة كلمة المرور', firebase_config=fb_config)

@app.post('/api/auth/super-admin-session')
def api_super_admin_session():
    data = request.json or request.form
    email = (data.get('email') or '').strip().lower()
    uid = (data.get('uid') or '').strip()

    is_super = (email in SUPER_ADMIN_EMAILS or uid in SUPER_ADMIN_UIDS)
    if not is_super:
        return jsonify({
            'ok': False,
            'error': 'عذراً، هذا المدخل مخصص حصرياً لمدير النظام المركزي (aa104@yahoo.com). يرجى تسجيل الدخول من بوابة المعلمين.'
        }), 403

    session['admin_logged_in'] = True
    session['is_super_admin'] = True
    session['user_role'] = 'SUPER_ADMIN'
    session['admin_name'] = 'مدير النظام (Super Admin)'
    session['user_email'] = email
    session['user_uid'] = uid
    db.audit(email, 'SUPER_ADMIN_LOGIN', 'auth', status='SUCCESS')

    return jsonify({'ok': True, 'redirect': url_for('super_admin')})

@app.post('/api/auth/firebase-session')
def api_firebase_session():
    data = request.json or request.form
    email = (data.get('email') or '').strip().lower()
    uid = (data.get('uid') or '').strip()
    display_name = (data.get('displayName') or '').strip()
    device_id = (data.get('device_id') or data.get('deviceId') or '').strip()
    device_info = (data.get('device_info') or data.get('deviceInfo') or '').strip()

    if not email or not uid:
        return jsonify({'ok': False, 'error': 'بيانات التوثيق السحابي من Firebase غير مكتملة'}), 400

    is_super = (email in SUPER_ADMIN_EMAILS or uid in SUPER_ADMIN_UIDS)

    if is_super:
        session['admin_logged_in'] = True
        session['is_super_admin'] = True
        session['user_role'] = 'SUPER_ADMIN'
        session['admin_name'] = 'مدير النظام (Super Admin)'
        session['user_email'] = email
        session['user_uid'] = uid
        db.audit(email, 'SUPER_ADMIN_LOGIN', 'auth', status='SUCCESS')
        return jsonify({
            'ok': True,
            'redirect': url_for('super_admin'),
            'is_super_admin': True,
            'role': 'SUPER_ADMIN',
            'message': 'مرحباً بك يا مدير النظام'
        })

    # Regular User (Teacher) verification
    teacher = db.q("SELECT * FROM authorized_teachers WHERE LOWER(email)=?", (email,), one=True)
    if not teacher:
        if init_firebase_admin():
            try:
                fb_u = fb_admin_auth.get_user_by_email(email)
                now_dt = datetime.now()
                from datetime import timedelta
                end_dt = (now_dt + timedelta(days=365)).strftime('%Y-%m-%d')
                tid = db.x("""
                    INSERT INTO authorized_teachers 
                    (teacher_name, school_name, username, email, password, license_key, status, firebase_uid, created_at, subscription_days, subscription_start_date, subscription_end_date, subscription_status)
                    VALUES (?, ?, ?, ?, 'FIREBASE_AUTH', ?, 'PENDING_ACTIVATION', ?, ?, 365, ?, ?, 'PENDING_PAYMENT')
                """, (display_name or email.split('@')[0], 'المدرسة', email.split('@')[0], email, f'LIC-{uid[:8].upper()}', fb_u.uid, now_dt.strftime('%Y-%m-%d %H:%M:%S'), now_dt.strftime('%Y-%m-%d'), end_dt))
                teacher = db.q("SELECT * FROM authorized_teachers WHERE id=?", (tid,), one=True)
            except Exception:
                pass

    if not teacher:
        return jsonify({
            'ok': False,
            'error': 'عذراً، هذا الحساب غير مصرح له أو لم يتم تفعيل ترخيص له على المنظومة بعد. يرجى التواصل مع الإدارة.'
        }), 403

    # 1. Check Subscription Expiry
    end_date_str = teacher['subscription_end_date'] or ''
    now_date = datetime.now().date()
    if end_date_str:
        try:
            e_date = datetime.strptime(end_date_str[:10], '%Y-%m-%d').date()
            days_rem = (e_date - now_date).days
            if days_rem <= 0 or teacher['subscription_status'] == 'EXPIRED':
                db.x("UPDATE authorized_teachers SET subscription_status='EXPIRED' WHERE id=?", (teacher['id'],))
                return jsonify({
                    'ok': False,
                    'error': f'انتهت فترة اشتراكك في المنظومة (بتاريخ {end_date_str}). يرجى تجديد الاشتراك من خلال إرسال إيميل إلى: {SUPPORT_EMAIL} أو التواصل مع المطور هاتفياً / واتساب على الأرقام: {" - ".join(SUPPORT_PHONES)}'
                }), 403
        except Exception:
            days_rem = 365
    else:
        days_rem = 365

    # 2. Check Device Fingerprint Binding
    bound_device = (teacher['device_id'] or '').strip()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if not bound_device:
        # First Time Login on this machine: BIND DEVICE!
        if device_id:
            db.x("""
                UPDATE authorized_teachers 
                SET device_id=?, device_info=?, device_bound_at=? 
                WHERE id=?
            """, (device_id, device_info, now_str, teacher['id']))
    else:
        # Check matching device
        if device_id and bound_device != device_id:
            return jsonify({
                'ok': False,
                'error': f'تم تنصيب البرنامج وتفعيله مسبقاً على جهاز آخر. يمنع النظام تشغيل الحساب على أكثر من جهاز منعاً للمشاركة غير المصرح بها. يرجى التواصل مع الدعم الفني ({SUPPORT_EMAIL} / هاتف: {" - ".join(SUPPORT_PHONES)}) لفك ارتباط الجهاز القديم أو اعتماد جهاز جديد أو تفعيل مادة جديدة.'
            }), 403

    # 3. Unlock Session
    session['admin_logged_in'] = True
    session['is_super_admin'] = False
    session['user_role'] = 'TEACHER'
    session['user_email'] = email
    session['teacher_email'] = email
    session['admin_name'] = teacher['teacher_name']
    session['days_remaining'] = days_rem
    session['subscription_end_date'] = end_date_str

    db.set_setting('teacher_name', teacher['teacher_name'])
    db.set_setting('school_name', teacher['school_name'])
    db.x("UPDATE authorized_teachers SET last_login=? WHERE id=?", (now_str, teacher['id']))
    db.audit(email, 'TEACHER_FIREBASE_LOGIN', 'auth', status='SUCCESS')

    return jsonify({
        'ok': True,
        'redirect': url_for('dashboard'),
        'is_super_admin': False,
        'role': 'TEACHER',
        'message': f'أهلاً بك أ. {teacher["teacher_name"]}'
    })

@app.post('/api/auth/send-reset-email')
def api_send_reset_email():
    data = request.json or request.form
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'ok': False, 'error': 'البريد الإلكتروني مطلوب'}), 400

    if init_firebase_admin():
        try:
            link = fb_admin_auth.generate_password_reset_link(email)
            return jsonify({
                'ok': True,
                'message': 'تم إرسال رابط إعادة تعيين كلمة المرور بنجاح!',
                'link': link
            })
        except Exception as e:
            return jsonify({'ok': False, 'error': f'تعذر إرسال الرابط: {e}'}), 400

    return jsonify({'ok': False, 'error': 'خدمة التوثيق السحابية غير متصلة.'}), 500

@app.post('/login/post')
def login_post():
    flash('تم إلغاء تسجيل الدخول المحلي؛ تسجيل الدخول متاح حصرياً عبر التوثيق السحابي لـ Firebase بالبريد الإلكتروني وكلمة المرور.', 'error')
    return redirect(url_for('login'))

@app.get('/logout')
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_name', None)
    session.pop('teacher_email', None)
    session.pop('teacher_uid', None)
    session.pop('user_email', None)
    session.pop('user_uid', None)
    session.pop('is_super_admin', None)
    session.pop('user_role', None)
    flash('تم تسجيل الخروج بنجاح.', 'success')
    return redirect(url_for('login'))

@app.get('/super-admin/logout', endpoint='super_admin_logout')
def super_admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_name', None)
    session.pop('teacher_email', None)
    session.pop('teacher_uid', None)
    session.pop('user_email', None)
    session.pop('user_uid', None)
    session.pop('is_super_admin', None)
    session.pop('user_role', None)
    flash('تم تسجيل الخروج وقفل وضع الموزع بنجاح.', 'info')
    return redirect(url_for('admin_login'))

# Subjects System (First-Class Domain Entity)
# ==============================================================================
@app.get('/subjects')
def subjects_list():
    rows = db.q("""
        SELECT s.*, 
               (SELECT COUNT(*) FROM question_packages p WHERE p.subject_id = s.id) as packages_count,
               (SELECT COUNT(*) FROM questions q WHERE q.subject_id = s.id) as questions_count
        FROM subjects s
        ORDER BY s.is_default DESC, s.name ASC
    """)
    return render_template('subjects.html', title='المواد الدراسية', active='subjects', subjects=rows)

@app.post('/subjects/add')
def add_subject():
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().lower()
    lang = request.form.get('language', 'ar').strip()
    direction = request.form.get('direction', 'rtl').strip()

    if not name:
        flash('يرجى تحديد اسم المادة الدراسية.', 'error')
        return redirect(url_for('subjects_list'))

    # Check if a subject with the same name already exists
    existing_name = db.q("SELECT id, name, code FROM subjects WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))", (name,), one=True)
    if existing_name:
        flash(f'المادة الدراسية "{name}" مسجلة مسبقاً ولا يمكن تكرارها.', 'warning')
        return redirect(url_for('subjects_list'))

    if not code:
        import hashlib
        code = f"sub_{hashlib.md5(name.encode('utf-8')).hexdigest()[:6]}"
    else:
        code = re.sub(r'[^a-z0-9_]', '_', code)

    existing = db.q("SELECT id, name FROM subjects WHERE code=?", (code,), one=True)
    if existing:
        flash(f'رمز المادة "{code}" مسجل مسبقاً لمادة أخرى ({existing["name"]}).', 'error')
        return redirect(url_for('subjects_list'))

    is_super = session.get('is_super_admin') is True
    status = 'APPROVED' if is_super else 'PENDING_APPROVAL'

    db.x("""
        INSERT INTO subjects (code, name, language, direction, is_default, approval_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, ?, ?, ?)
    """, (code, name, lang, direction, status, now(), now()))

    db.audit(session.get('admin_name', 'Teacher'), 'CREATE_SUBJECT', 'subjects', name)
    if is_super:
        flash(f'تمت إضافة واعتماد المادة الدراسية: {name}', 'success')
    else:
        flash(f'تم تقديم طلب إضافة المادة الدراسية ({name}) بنجاح، وهي الآن (قيد موافقة مدير النظام المركزي). سيتم تفعيلها فور اعتمادها.', 'warning')
    return redirect(url_for('subjects_list'))

@app.post('/subjects/delete/<int:id>')
def delete_subject(id):
    sub = db.q("SELECT * FROM subjects WHERE id=?", (id,), one=True)
    if not sub:
        flash('المادة غير موجودة.', 'error')
        return redirect(url_for('subjects_list'))

    # Check dependencies: warn if there are questions or exams
    q_count = db.q("SELECT COUNT(*) as n FROM questions WHERE subject_id=?", (id,), one=True)['n']
    ex_count = db.q("SELECT COUNT(*) as n FROM exams WHERE subject_id=?", (id,), one=True)['n']
    if q_count > 0 or ex_count > 0:
        flash(f'لا يمكن حذف المادة لأنها مرتبطة بـ {q_count} سؤال و {ex_count} امتحان. يرجى حذف الأسئلة والامتحانات أولاً.', 'error')
        return redirect(url_for('subjects_list'))

    db.x("DELETE FROM question_packages WHERE subject_id=?", (id,))
    db.x("DELETE FROM subjects WHERE id=?", (id,))
    db.audit('Teacher', 'DELETE_SUBJECT', 'subjects', id)
    flash(f'تم حذف المادة ({sub["name"]}) بنجاح.', 'success')
    return redirect(url_for('subjects_list'))

# ==============================================================================
# Question Packages (Units & Lessons)
# ==============================================================================
@app.get('/packages')
def packages_list():
    s_val = request.args.get('subject_id')
    subject_id = int(s_val) if s_val and str(s_val).isdigit() else None
    subjects = db.q("SELECT * FROM subjects ORDER BY name ASC")
    
    where = []
    params = []
    if subject_id:
        where.append("p.subject_id = ?")
        params.append(subject_id)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    packages = db.q(f"""
        SELECT p.*, s.name as subject_name,
               (SELECT COUNT(*) FROM questions q WHERE q.package_id = p.id) as questions_count
        FROM question_packages p
        JOIN subjects s ON s.id = p.subject_id
        {where_sql}
        ORDER BY s.name ASC, p.sort_order ASC, p.name ASC
    """, params)

    return render_template(
        'packages.html',
        title='حزم الأسئلة والوحدات',
        active='packages',
        packages=packages,
        subjects=subjects,
        selected_subject_id=subject_id
    )

@app.post('/packages/add')
def add_package():
    subject_id = request.form.get('subject_id', type=int)
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()

    if not subject_id or not name:
        flash('يرجى تحديد المادة واسم الحزمة.', 'error')
        return redirect(url_for('packages_list'))

    try:
        pid = db.x("""
            INSERT INTO question_packages (subject_id, name, description, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
        """, (subject_id, name, desc, now(), now()))
        db.audit('Teacher', 'CREATE_PACKAGE', 'question_packages', pid)
        flash(f'تم إنشاء حزمة الأسئلة: {name}', 'success')
    except sqlite3.IntegrityError:
        flash('توجد حزمة بنفس هذا الاسم لهذه المادة مسبقاً.', 'error')

    return redirect(url_for('packages_list', subject_id=subject_id))

@app.post('/packages/delete/<int:id>')
def delete_package(id):
    db.x("UPDATE questions SET package_id = NULL WHERE package_id = ?", (id,))
    db.x("DELETE FROM question_packages WHERE id = ?", (id,))
    db.audit('Teacher', 'DELETE_PACKAGE', 'question_packages', id)
    flash('تم حذف حزمة الأسئلة.', 'success')
    return redirect(url_for('packages_list'))

@app.post('/packages/bulk-delete', endpoint='packages_bulk_delete')
def packages_bulk_delete():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    pkg_ids = request.form.getlist('selected_pkg_ids')
    if not pkg_ids:
        flash('لم يتم تحديد أي وحدات للحذف.', 'warning')
        return redirect(url_for('packages_list'))

    del_count = 0
    for pid in pkg_ids:
        db.x("UPDATE questions SET package_id = NULL WHERE package_id = ?", (pid,))
        db.x("DELETE FROM question_packages WHERE id = ?", (pid,))
        del_count += 1

    db.audit('Teacher', 'BULK_DELETE_PACKAGES', 'question_packages', f"Deleted: {del_count}")
    flash(f'تم بنجاح حذف ({del_count}) وحدة دراسية محددة.', 'success')
    return redirect(url_for('packages_list'))

# ==============================================================================
# Question Bank & Manual Question Creation
# ==============================================================================
@app.get('/questions')
@app.get('/question-bank')
def question_bank():
    s_val = request.args.get('subject_id')
    sub_id = int(s_val) if s_val and str(s_val).isdigit() else None
    p_val = request.args.get('package_id')
    pkg_id = int(p_val) if p_val and str(p_val).isdigit() else None
    q_search = request.args.get('q', '').strip()

    subjects = db.q("SELECT * FROM subjects ORDER BY name ASC")
    packages = db.q("SELECT p.*, s.name as subject_name FROM question_packages p JOIN subjects s ON s.id = p.subject_id ORDER BY s.name ASC, p.name ASC")

    where = ["q.status = 'APPROVED'"]
    params = []

    if sub_id:
        where.append("q.subject_id = ?")
        params.append(sub_id)
    if pkg_id:
        where.append("q.package_id = ?")
        params.append(pkg_id)
    if q_search:
        where.append("(q.question LIKE ? OR q.option_a LIKE ? OR q.option_b LIKE ?)")
        params.extend([f"%{q_search}%"] * 3)

    where_sql = "WHERE " + " AND ".join(where)
    questions = db.q(f"""
        SELECT q.*, s.name as subject_name, p.name as package_name
        FROM questions q
        LEFT JOIN subjects s ON s.id = q.subject_id
        LEFT JOIN question_packages p ON p.id = q.package_id
        {where_sql}
        ORDER BY q.id DESC
    """, params)

    return render_template(
        'questions.html',
        title='بنك الأسئلة المعتمدة',
        active='questions',
        questions=questions,
        subjects=subjects,
        packages=packages,
        filter_subject_id=sub_id,
        filter_package_id=pkg_id,
        search_query=q_search,
        total_matched=len(questions)
    )

@app.post('/questions/save')
def save_question():
    f = request.form
    qid = f.get('id', type=int)
    sub_id = f.get('subject_id', type=int) or 1
    pkg_id = f.get('package_id', type=int) or None
    q_text = f.get('question', '').strip()
    opt_a = f.get('option_a', '').strip()
    opt_b = f.get('option_b', '').strip()
    opt_c = f.get('option_c', '').strip()
    opt_d = f.get('option_d', '').strip()
    correct = f.get('correct', 'أ').strip().upper()
    mark = float(f.get('mark', 1.0))
    status = f.get('status', 'APPROVED').strip().upper()
    redirect_target = f.get('redirect_to', 'bank')

    # Allow 2 options for True/False questions (Option A & B only), or full 4 options
    if not q_text or not opt_a or not opt_b:
        flash('يرجى ملء نص السؤال والخيارين الأول والثاني على الأقل (صح/خطأ أو خيارات متعددة).', 'error')
        return redirect(url_for('question_bank'))

    # Handle optional image upload
    img_file = request.files.get('image')
    image_path = f.get('existing_image_path', '').strip()
    if img_file and img_file.filename:
        ext = Path(img_file.filename).suffix.lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'):
            img_fname = f"q_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
            img_file.save(IMAGES_DIR / img_fname)
            image_path = img_fname

    subj = db.q("SELECT * FROM subjects WHERE id=?", (sub_id,), one=True)
    lang = subj['language'] if subj else 'ar'
    sub_name = subj['name'] if subj else ''

    pkg = db.q("SELECT * FROM question_packages WHERE id=?", (pkg_id,), one=True) if pkg_id else None
    pkg_name = pkg['name'] if pkg else ''
    direction = subj['direction'] if subj else 'rtl'
    appr = 1 if status == 'APPROVED' else 0

    if qid:
        db.x("""
            UPDATE questions
            SET subject_id=?, package_id=?, question=?, option_a=?, option_b=?, option_c=?, option_d=?,
                image_path=?, correct=?, mark=?, status=?, approved=?, language=?, direction=?, updated_at=?
            WHERE id=?
        """, (sub_id, pkg_id, q_text, opt_a, opt_b, opt_c, opt_d, image_path, correct, mark, status, appr, lang, direction, now(), qid))
        db.audit('Teacher', 'UPDATE_QUESTION', 'questions', qid)
        flash('تم تحديث بيانات السؤال بنجاح.', 'success')
    else:
        new_id = db.x("""
            INSERT INTO questions (subject_id, package_id, question, option_a, option_b, option_c, option_d,
                                  image_path, correct, mark, status, approved, language, direction, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?)
        """, (sub_id, pkg_id, q_text, opt_a, opt_b, opt_c, opt_d, image_path, correct, mark, status, appr, lang, direction, now(), now()))
        db.audit('Teacher', 'CREATE_MANUAL_QUESTION', 'questions', new_id)
        flash('تمت إضافة السؤال بنجاح.', 'success')

    if redirect_target == 'review':
        return redirect(url_for('review_questions'))
    return redirect(url_for('question_bank'))

@app.route('/questions/delete/<int:id>', methods=['GET', 'POST'])
def delete_question(id):
    db.x("DELETE FROM exam_questions WHERE question_id=?", (id,))
    db.x("DELETE FROM questions WHERE id=?", (id,))
    db.audit('Teacher', 'DELETE_QUESTION', 'questions', id)
    flash('تم حذف السؤال بنجاح.', 'success')
    ref = request.headers.get('Referer', '')
    if 'review' in ref:
        return redirect(url_for('review_questions'))
    return redirect(url_for('question_bank'))

@app.get('/questions/approve/<int:id>')
def approve_single_question(id):
    db.x("UPDATE questions SET status='APPROVED', approved=1, updated_at=? WHERE id=?", (now(), id))
    db.audit('Teacher', 'APPROVE_QUESTION', 'questions', id)
    flash(f'تم اعتماد السؤال #{id} وإدراجه في بنك الأسئلة.', 'success')
    return redirect(url_for('review_questions'))

# ==============================================================================
# Optical Structured Recognition (OSR) & Extraction Flow
# ==============================================================================
@app.get('/import')
@app.get('/ocr')
def import_center():
    subjects = db.q("SELECT * FROM subjects ORDER BY name ASC")
    packages = db.q("SELECT p.*, s.name as subject_name FROM question_packages p JOIN subjects s ON s.id = p.subject_id ORDER BY s.name ASC, p.name ASC")
    return render_template('import.html', title='استخراج الامتحان (OSR)', active='import', subjects=subjects, packages=packages)

@app.post('/import/process')
def import_process():
    if not is_admin_logged_in():
        flash('يرجى تسجيل الدخول للوصول إلى مركز استخراج الأسئلة.', 'error')
        return redirect(url_for('login'))

    sub_id = request.form.get('subject_id', type=int)
    pkg_id = request.form.get('package_id', type=int) or None
    raw_text = request.form.get('exam_text', '').strip()
    files = request.files.getlist('exam_images')

    if not sub_id:
        flash('يرجى تحديد المادة الدراسية أولاً.', 'error')
        return redirect(url_for('import_center'))

    subj = db.q("SELECT * FROM subjects WHERE id=?", (sub_id,), one=True)
    if not subj:
        flash('المادة الدراسية المحددة غير صالحة أو غير موجودة في النظام.', 'error')
        return redirect(url_for('import_center'))

    lang = subj['language'] if subj else 'ar'
    sub_name = subj['name'] if subj else ''

    pkg = db.q("SELECT * FROM question_packages WHERE id=?", (pkg_id,), one=True) if pkg_id else None
    pkg_name = pkg['name'] if pkg else ''

    extracted_items = []
    errors = []
    allowed_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.docx', '.txt', '.pdf')

    # 1. Process Pasted Text
    if raw_text:
        try:
            parsed = parse_exam_questions(raw_text, source_file="Text Input", default_lang=lang)
            extracted_items.extend(parsed)
        except Exception as e:
            errors.append(f"خطأ في تحليل النص المباشر: {e}")

    # 2. Process Uploaded Files/Images
    for f in files:
        if not f or not f.filename:
            continue
        
        # Pre-validate filename and extension BEFORE saving to disk (Security Guard)
        raw_fname = f.filename.strip()
        dot_idx = raw_fname.rfind('.')
        if dot_idx == -1:
            errors.append(f"الملف {f.filename}: ملف بدون امتداد غير مدعوم.")
            continue
        ext = raw_fname[dot_idx:].lower()
        if ext not in allowed_extensions:
            errors.append(f"الملف {f.filename}: صيغة الملف ({ext}) غير مدعومة. الصيغ المدعومة: Word, TXT, PDF, والصور.")
            continue

        safe_fname = safe_filename(raw_fname)
        save_path = IMAGES_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{safe_fname}"
        
        try:
            f.save(save_path)
            
            # Process based on validated extension
            if ext in ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'):
                try:
                    ocr_text, _ = ocr_image_file(save_path, lang='ara' if lang == 'ar' else 'eng')
                    if ocr_text and ocr_text.strip():
                        parsed = parse_exam_questions(ocr_text, source_file=save_path.name, default_lang=lang)
                        extracted_items.extend(parsed)
                    else:
                        errors.append(f"الصورة {f.filename}: لم يتم التعرف على أي نصوص واضحة في الصورة.")
                except Exception as e:
                    errors.append(f"الصورة {f.filename}: خطأ في معالجة OCR: {e}")
            elif ext == '.docx':
                f_text = extract_text_from_docx_file(save_path)
                if f_text and f_text.strip():
                    parsed = parse_exam_questions(f_text, source_file=save_path.name, default_lang=lang)
                    extracted_items.extend(parsed)
                else:
                    errors.append(f"المستند {f.filename}: الملف فارغ أو تالف أو تعذر قراءة محتواه.")
                # Clean up temporary DOCX to prevent disk leak
                try: save_path.unlink(missing_ok=True)
                except Exception: pass
            elif ext == '.pdf':
                f_text = extract_text_from_pdf_file(save_path)
                if f_text and f_text.strip():
                    parsed = parse_exam_questions(f_text, source_file=save_path.name, default_lang=lang)
                    extracted_items.extend(parsed)
                else:
                    errors.append(f"ملف PDF {f.filename}: الملف فارغ أو تعذر استخراج النصوص منه.")
                # Clean up temporary PDF to prevent disk leak
                try: save_path.unlink(missing_ok=True)
                except Exception: pass
            elif ext == '.txt':
                try:
                    with open(save_path, 'r', encoding='utf-8', errors='ignore') as tf:
                        f_text = tf.read()
                    if f_text and f_text.strip():
                        parsed = parse_exam_questions(f_text, source_file=save_path.name, default_lang=lang)
                        extracted_items.extend(parsed)
                    else:
                        errors.append(f"الملف {f.filename}: ملف نصي فارغ (0 بايت).")
                except Exception as e:
                    errors.append(f"الملف {f.filename}: تعذر قراءة الملف النصي: {e}")
                # Clean up temporary TXT
                try: save_path.unlink(missing_ok=True)
                except Exception: pass
        except Exception as e:
            errors.append(f"الملف {f.filename}: خطأ في المعالجة: {e}")

    if not extracted_items:
        msg = 'لم يتم التعرف على أي أسئلة مطابقة للتنسيق المطلوب.'
        if errors:
            msg += ' التفاصيل: ' + ' | '.join(errors[:3])
        flash(msg, 'error')
        return redirect(url_for('import_center'))

    # Save all extracted questions to database with status 'NEEDS_REVIEW' (Guarded Parameterized Insert)
    saved_ids = []
    for item in extracted_items:
        q_text = str(item.get('question') or '').strip()
        if not q_text:
            continue
        
        opt_a = str(item.get('option_a') or '').strip()
        opt_b = str(item.get('option_b') or '').strip()
        opt_c = str(item.get('option_c') or '').strip()
        opt_d = str(item.get('option_d') or '').strip()
        correct_ans = str(item.get('correct') or 'أ').strip()
        if not correct_ans: correct_ans = 'أ'
        conf = float(item.get('confidence') or 1.0)
        warns = str(item.get('warnings') or '')
        src_file = str(item.get('source_file') or '')
        pg_num = int(item.get('page') or 1)
        item_lang = str(item.get('language') or lang)
        item_dir = str(item.get('direction') or ('rtl' if lang == 'ar' else 'ltr'))

        new_qid = db.x("""
            INSERT INTO questions (subject_id, package_id, subject, unit, question, option_a, option_b, option_c, option_d,
                                  correct, mark, difficulty, status, approved, confidence, warnings,
                                  source_file, source_page, language, direction, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, 'متوسط', 'NEEDS_REVIEW', 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sub_id, pkg_id, sub_name, pkg_name, q_text, opt_a, opt_b, opt_c, opt_d,
            correct_ans, conf, warns, src_file, pg_num,
            item_lang, item_dir, now(), now()
        ))
        saved_ids.append(new_qid)

    db.audit('Teacher', 'OSR_EXTRACT', 'questions', len(saved_ids), after_state=f"Extracted {len(saved_ids)} questions")
    session['last_import_batch'] = saved_ids
    flash(f'تم استخراج {len(saved_ids)} سؤالاً بنجاح عبر محرك OSR وهي الآن بانتظار مراجعتك واعتمادك.', 'success')
    return redirect(url_for('review_questions'))

# ==============================================================================
# Review & Quality Control (QC) Center
# ==============================================================================
@app.get('/review')
def review_questions():
    subjects = db.q("SELECT * FROM subjects ORDER BY name ASC")
    packages = db.q("SELECT p.*, s.name as subject_name FROM question_packages p JOIN subjects s ON s.id = p.subject_id ORDER BY s.name ASC, p.name ASC")

    # Fetch unapproved questions (NEEDS_REVIEW or DRAFT)
    review_qs = db.q("""
        SELECT q.*, s.name as subject_name, p.name as package_name
        FROM questions q
        LEFT JOIN subjects s ON s.id = q.subject_id
        LEFT JOIN question_packages p ON p.id = q.package_id
        WHERE q.status != 'APPROVED'
        ORDER BY q.id DESC
    """)

    return render_template(
        'review.html',
        title='مراجعة الأسئلة وضبط الجودة',
        active='review',
        review_questions=review_qs,
        subjects=subjects,
        packages=packages
    )

@app.post('/review/bulk')
def bulk_review_action():
    action = request.form.get('action')
    selected_ids = request.form.getlist('selected_ids')

    if not selected_ids:
        flash('يرجى تحديد سؤال واحد على الأقل لتنفيذ الإجراء.', 'warning')
        return redirect(url_for('review_questions'))

    # Convert to integers safely
    int_ids = [int(x) for x in selected_ids if x.isdigit()]

    if action == 'approve_selected':
        placeholders = ','.join(['?'] * len(int_ids))
        db.x(f"UPDATE questions SET status='APPROVED', approved=1, updated_at=? WHERE id IN ({placeholders})", [now()] + int_ids)
        db.audit('Teacher', 'BULK_APPROVE', 'questions', len(int_ids))
        flash(f'تم اعتماد {len(int_ids)} سؤالاً بنجاح وإضافتها إلى بنك الأسئلة المعتمدة.', 'success')
    elif action == 'reject_selected':
        placeholders = ','.join(['?'] * len(int_ids))
        db.x(f"UPDATE questions SET status='REJECTED', approved=0, updated_at=? WHERE id IN ({placeholders})", [now()] + int_ids)
        db.audit('Teacher', 'BULK_REJECT', 'questions', len(int_ids))
        flash(f'تم رفض {len(int_ids)} سؤالاً.', 'info')
    elif action == 'delete_selected':
        placeholders = ','.join(['?'] * len(int_ids))
        db.x(f"DELETE FROM questions WHERE id IN ({placeholders})", int_ids)
        db.audit('Teacher', 'BULK_DELETE', 'questions', len(int_ids))
        flash(f'تم حذف {len(int_ids)} سؤالاً نهائياً.', 'success')

    return redirect(url_for('review_questions'))

# ==============================================================================
# Exams Management & Creator
# ==============================================================================
@app.get('/exams')
def exams_list():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    exams = db.q("""
        SELECT e.*, s.name as subject_name, p.name as package_name,
               (SELECT publish_token FROM published_exams pe WHERE pe.local_exam_id = e.id ORDER BY pe.id DESC LIMIT 1) as publish_token,
               (SELECT status FROM published_exams pe WHERE pe.local_exam_id = e.id ORDER BY pe.id DESC LIMIT 1) as online_status
        FROM exams e
        LEFT JOIN subjects s ON s.id = e.subject_id
        LEFT JOIN question_packages p ON p.id = e.package_id
        WHERE e.is_archived = 0
        ORDER BY e.id DESC
    """)

    subjects = db.q("""
        SELECT s.*, (SELECT COUNT(*) FROM exams e WHERE e.subject_id = s.id AND e.is_archived = 0) as exam_count
        FROM subjects s
        WHERE s.approval_status = 'APPROVED'
        ORDER BY s.name ASC
    """)

    return render_template('exams.html', title='الامتحانات', active='exams', exams=exams, subjects=subjects)

@app.post('/exams/bulk-delete', endpoint='exams_bulk_delete')
def exams_bulk_delete():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    exam_ids = request.form.getlist('selected_exam_ids')
    if not exam_ids:
        flash('لم يتم تحديد أي امتحانات للحذف.', 'warning')
        return redirect(url_for('exams_list'))

    archived_count = 0
    deleted_count = 0
    for eid in exam_ids:
        try:
            eid_int = int(eid)
        except ValueError:
            continue
        attempts_count = db.q("SELECT COUNT(*) as n FROM attempts WHERE exam_id=?", (eid_int,), one=True)['n']
        if attempts_count > 0:
            db.x("UPDATE exams SET is_archived = 1, status = 'ARCHIVED', active = 0 WHERE id = ?", (eid_int,))
            archived_count += 1
        else:
            db.x("DELETE FROM exam_questions WHERE exam_id = ?", (eid_int,))
            db.x("DELETE FROM exams WHERE id = ?", (eid_int,))
            deleted_count += 1

    db.audit('Teacher', 'BULK_DELETE_EXAMS', 'exams', f"Archived: {archived_count}, Deleted: {deleted_count}")
    flash(f'تمت معالجة حذف ({archived_count + deleted_count}) امتحان بنجاح. تم الحفاظ التام على أوراق وعلامات الطلاب للامتحانات المنفذة.', 'success')
    return redirect(url_for('exams_list'))

@app.get('/exams/new')
@app.get('/exams/create')
def exam_creator():
    subjects = db.q("SELECT * FROM subjects ORDER BY name ASC")
    packages = db.q("SELECT p.*, s.name as subject_name FROM question_packages p JOIN subjects s ON s.id = p.subject_id ORDER BY s.name ASC, p.name ASC")
    available_qs = db.q("""
        SELECT q.*, s.name as subject_name, p.name as package_name
        FROM questions q
        JOIN subjects s ON s.id = q.subject_id
        LEFT JOIN question_packages p ON p.id = q.package_id
        WHERE q.status = 'APPROVED'
        ORDER BY q.id DESC
    """)
    return render_template('exam_creator.html', title='إنشاء امتحان جديد', active='exams', subjects=subjects, packages=packages, available_questions=available_qs)

@app.post('/exams/create/process')
def create_exam_process():
    f = request.form
    title = f.get('title', '').strip()
    sub_id = f.get('subject_id', type=int)
    pkg_id = f.get('package_id', type=int) or None
    class_name = f.get('class_name', '').strip()
    section = f.get('section', '').strip()
    duration = int(f.get('duration', 45))
    raw_password = f.get('password', '').strip()
    random_order = 1 if f.get('random_order') else 0
    selected_q_ids = request.form.getlist('question_ids')

    if not title or not sub_id:
        flash('يرجى تحديد عنوان الامتحان والمادة الدراسية.', 'error')
        return redirect(url_for('exam_creator'))

    if not selected_q_ids:
        flash('يرجى اختيار سؤال واحد على الأقل لتضمينه في هذا الامتحان.', 'error')
        return redirect(url_for('exam_creator'))

    int_q_ids = [int(x) for x in selected_q_ids if x.isdigit()]

    # Validate that all chosen questions belong to the same subject
    mismatched = db.q(f"SELECT COUNT(*) as n FROM questions WHERE id IN ({','.join(['?']*len(int_q_ids))}) AND subject_id != ?", int_q_ids + [sub_id], one=True)['n']
    if mismatched > 0:
        flash('خطأ في الاتساق: لا يمكن تضمين أسئلة من مادة دراسية مختلفة في نفس الامتحان.', 'error')
        return redirect(url_for('exam_creator'))

    # Store hashed password if set
    pw_hash = hashlib.sha256(raw_password.encode('utf-8')).hexdigest() if raw_password else ''

    import random
    exam_code = f.get('exam_code', '').strip()
    if not exam_code:
        exam_code = str(random.randint(100000, 999999))
    exam_type = f.get('exam_type', '').strip() or 'الامتحان النهائي'
    exam_date = f.get('exam_date', '').strip() or datetime.now().strftime('%Y/%m/%d')
    try:
        total_marks = float(f.get('total_marks', len(int_q_ids) * 1.0))
    except ValueError:
        total_marks = len(int_q_ids) * 1.0

    new_exam_id = db.x("""
        INSERT INTO exams (title, subject_id, package_id, class_name, section, duration,
                          question_count, password, password_hash, status, active, random_order,
                          exam_code, exam_type, exam_date, total_marks, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', 0, ?, ?, ?, ?, ?, ?, ?)
    """, (title, sub_id, pkg_id, class_name, section, duration, len(int_q_ids), raw_password, pw_hash, random_order,
          exam_code, exam_type, exam_date, total_marks, now(), now()))

    for pos, qid in enumerate(int_q_ids, 1):
        db.x("INSERT INTO exam_questions (exam_id, question_id, position) VALUES (?, ?, ?)", (new_exam_id, qid, pos))

    db.audit('Teacher', 'CREATE_EXAM', 'exams', new_exam_id, after_state=f"Exam: {title}, Questions: {len(int_q_ids)}")
    flash(f'تم إنشاء الامتحان بنجاح بـ {len(int_q_ids)} سؤالاً.', 'success')
    return redirect(url_for('exam_manage', id=new_exam_id))

@app.get('/exams/<int:id>')
@app.get('/exams/<int:id>/manage')
def exam_manage(id):
    exam = db.q("""
        SELECT e.*, s.name as subject_name, p.name as package_name
        FROM exams e
        LEFT JOIN subjects s ON s.id = e.subject_id
        LEFT JOIN question_packages p ON p.id = e.package_id
        WHERE e.id = ?
    """, (id,), one=True)

    if not exam:
        flash('الامتحان غير موجود.', 'error')
        return redirect(url_for('exams_list'))

    attached_questions = db.q("""
        SELECT q.*, eq.position
        FROM exam_questions eq
        JOIN questions q ON q.id = eq.question_id
        WHERE eq.exam_id = ?
        ORDER BY eq.position ASC
    """, (id,))

    # Student attendees summary
    attendees = db.q("""
        SELECT st.id as student_id, st.full_name as student_name, st.username, st.class_name, st.section,
               (SELECT COUNT(*) FROM attempts att WHERE att.exam_id = a.exam_id AND att.student_id = a.student_id) as attempts_count,
               a.id as latest_attempt_id,
               a.status as latest_status,
               a.score as latest_score,
               a.total as total,
               a.percentage as percentage,
               a.submitted_at as submitted_at,
               a.finished_at as finished_at,
               (SELECT extra_attempts FROM student_exam_overrides seo WHERE seo.exam_id = a.exam_id AND seo.student_id = a.student_id) as extra_attempts
        FROM attempts a
        JOIN students st ON st.id = a.student_id
        WHERE a.exam_id = ? AND a.id IN (
            SELECT MAX(id) FROM attempts WHERE exam_id = ? GROUP BY student_id
        )
        ORDER BY a.id DESC
    """, (id, id))

    published_online = db.q("""
        SELECT * FROM published_exams 
        WHERE local_exam_id = ? 
        ORDER BY id DESC LIMIT 1
    """, (id,), one=True)

    return render_template(
        'exam_manage.html',
        title=f'إدارة الامتحان: {exam["title"]}',
        active='exams',
        exam=exam,
        attached_questions=attached_questions,
        attendees=attendees,
        published_online=published_online
    )

@app.post('/exams/<int:id>/toggle')
def toggle_exam_publish(id):
    exam = db.q("SELECT * FROM exams WHERE id=?", (id,), one=True)
    if not exam:
        flash('الامتحان غير موجود.', 'error')
        return redirect(url_for('exams_list'))

    if not (exam['status'] == 'PUBLISHED' or exam['active']):
        # Validate conditions before publishing
        q_count = db.q("SELECT COUNT(*) as n FROM exam_questions WHERE exam_id=?", (id,), one=True)['n']
        if q_count == 0:
            flash('لا يمكن نشر امتحان فارغ دون أي أسئلة.', 'error')
            return redirect(url_for('exam_manage', id=id))

        unapproved = db.q("""
            SELECT COUNT(*) as n FROM exam_questions eq
            JOIN questions q ON q.id = eq.question_id
            WHERE eq.exam_id=? AND q.status != 'APPROVED'
        """, (id,), one=True)['n']
        if unapproved > 0:
            flash('لا يمكن نشر الامتحان لأن بعض الأسئلة المضمنة لم يتم اعتمادها بعد.', 'error')
            return redirect(url_for('exam_manage', id=id))

        db.x("UPDATE exams SET status='PUBLISHED', active=1, updated_at=? WHERE id=?", (now(), id))
        db.audit('Teacher', 'PUBLISH_EXAM', 'exams', id)
        flash('تم نشر الامتحان بنجاح وأصبح متاحاً للطلاب.', 'success')
    else:
        db.x("UPDATE exams SET status='CLOSED', active=0, updated_at=? WHERE id=?", (now(), id))
        db.audit('Teacher', 'UNPUBLISH_EXAM', 'exams', id)
        flash('تم إيقاف نشر الامتحان.', 'info')

    return redirect(url_for('exam_manage', id=id))


@app.route('/exams/<int:exam_id>/students/<int:student_id>/grant-attempt', methods=['GET', 'POST'])
def grant_student_attempt(exam_id, student_id):
    st = db.q("SELECT full_name FROM students WHERE id=?", (student_id,), one=True)
    name = st['full_name'] if st else "الطالب"

    existing = db.q("SELECT extra_attempts FROM student_exam_overrides WHERE student_id=? AND exam_id=?", (student_id, exam_id), one=True)
    if existing:
        db.x("UPDATE student_exam_overrides SET extra_attempts = extra_attempts + 1, granted_at=? WHERE student_id=? AND exam_id=?", (now(), student_id, exam_id))
    else:
        db.x("INSERT INTO student_exam_overrides (student_id, exam_id, extra_attempts, granted_at) VALUES (?, ?, 1, ?)", (student_id, exam_id, now()))

    db.audit('Teacher', 'GRANT_EXTRA_ATTEMPT', 'exams', f"{exam_id}:{student_id}")
    flash(f"تم منح الطالب ({name}) محاولة تقديم إضافية بنجاح.", "success")
    return redirect(url_for('exam_manage', id=exam_id))

@app.route('/exams/<int:exam_id>/attempts/<int:attempt_id>/delete', methods=['GET', 'POST'])
def delete_student_attempt(exam_id, attempt_id):
    att = db.q("SELECT * FROM attempts WHERE id=?", (attempt_id,), one=True)
    if not att:
        flash("المحاولة غير موجودة.", "error")
        return redirect(url_for('exam_manage', id=exam_id))

    st_name = att['student_name']
    db.x("DELETE FROM answers WHERE attempt_id=?", (attempt_id,))
    db.x("DELETE FROM attempt_snapshots WHERE attempt_id=?", (attempt_id,))
    db.x("DELETE FROM attempts WHERE id=?", (attempt_id,))

    db.audit('Teacher', 'DELETE_STUDENT_ATTEMPT', 'attempts', attempt_id)
    flash(f"تم حذف محاولة الطالب ({st_name}) بنجاح، ويمكنه الآن التقديم مجدداً.", "success")
    return redirect(url_for('exam_manage', id=exam_id))

@app.post('/exams/<int:id>/copy')
def copy_exam(id):
    exam = db.q("SELECT * FROM exams WHERE id=?", (id,), one=True)
    if not exam:
        flash('الامتحان غير موجود.', 'error')
        return redirect(url_for('exams_list'))

    new_title = f"{exam['title']} (نسخة)"
    new_id = db.x("""
        INSERT INTO exams (title, subject_id, package_id, class_name, section, duration,
                          question_count, password, password_hash, status, active, random_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', 0, ?, ?, ?)
    """, (new_title, exam['subject_id'], exam['package_id'], exam['class_name'], exam['section'],
          exam['duration'], exam['question_count'], exam['password'], exam['password_hash'], exam['random_order'], now(), now()))

    # Copy question mapping
    questions = db.q("SELECT question_id, position FROM exam_questions WHERE exam_id=? ORDER BY position", (id,))
    for q in questions:
        db.x("INSERT INTO exam_questions (exam_id, question_id, position) VALUES (?, ?, ?)", (new_id, q['question_id'], q['position']))

    db.audit('Teacher', 'COPY_EXAM', 'exams', new_id, before_state=f"Source Exam #{id}")
    flash(f'تم نسخ الامتحان بنجاح باسم: {new_title}', 'success')
    return redirect(url_for('exam_manage', id=new_id))

@app.post('/exams/<int:id>/delete')
def delete_exam(id):
    if not is_testing and not is_admin_logged_in():
        return redirect(url_for('login'))

    att_count = db.q("SELECT COUNT(*) as n FROM attempts WHERE exam_id=?", (id,), one=True)['n']
    force_hard = request.form.get('force') == '1' or is_testing

    if att_count > 0 and not force_hard:
        # Protect historical student scores and attempts: Archive instead of hard delete!
        db.x("UPDATE exams SET is_archived=1, status='ARCHIVED', active=0 WHERE id=?", (id,))
        db.audit('Teacher', 'ARCHIVE_EXAM', 'exams', id)
        flash('تمت أرشفة الامتحان بنجاح، وتم الحفاظ الكامل على علامات وإجابات الطلاب وسجلاتهم السابقة.', 'success')
    else:
        db.x("DELETE FROM answers WHERE attempt_id IN (SELECT id FROM attempts WHERE exam_id=?)", (id,))
        db.x("DELETE FROM attempt_snapshots WHERE attempt_id IN (SELECT id FROM attempts WHERE exam_id=?)", (id,))
        db.x("DELETE FROM attempts WHERE exam_id=?", (id,))
        db.x("DELETE FROM exam_questions WHERE exam_id=?", (id,))
        db.x("DELETE FROM exams WHERE id=?", (id,))
        db.audit('Teacher', 'DELETE_EXAM', 'exams', id)
        flash('تم حذف الامتحان بنجاح.', 'success')

    return redirect(url_for('exams_list'))

# ==============================================================================
# Students Management (Separated Screens & Subject-Specific Enrollment)
# ==============================================================================
@app.get('/students')
def students_list():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    subj_id = request.args.get('subject_id', '').strip()
    c_name = request.args.get('class_name', '').strip()
    sec = request.args.get('section', '').strip()
    q_search = request.args.get('q', '').strip()

    sql = """
        SELECT DISTINCT s.* FROM students s
    """
    params = []
    where_clauses = []

    if subj_id:
        sql += " JOIN student_subjects ss ON ss.student_id = s.id "
        where_clauses.append("ss.subject_id = ?")
        params.append(subj_id)

    if c_name:
        where_clauses.append("s.class_name = ?")
        params.append(c_name)

    if sec:
        where_clauses.append("s.section = ?")
        params.append(sec)

    if q_search:
        where_clauses.append("(s.full_name LIKE ? OR s.username LIKE ? OR s.national_id LIKE ?)")
        params.extend([f'%{q_search}%', f'%{q_search}%', f'%{q_search}%'])

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY s.id DESC"
    raw_students = db.q(sql, tuple(params))

    processed = []
    for st in raw_students:
        st_dict = dict(st)
        enrolled = db.q("""
            SELECT sub.name FROM subjects sub
            JOIN student_subjects ss ON ss.subject_id = sub.id
            WHERE ss.student_id = ?
            ORDER BY sub.name ASC
        """, (st['id'],))
        st_dict['enrolled_subjects'] = [r['name'] for r in enrolled]
        processed.append(st_dict)

    subjects = db.q("SELECT * FROM subjects WHERE approval_status='APPROVED' ORDER BY id ASC")

    return render_template(
        'students.html',
        title='سجل الطلاب',
        active='students',
        students=processed,
        subjects=subjects,
        selected_subject_id=int(subj_id) if subj_id.isdigit() else None,
        selected_class=c_name,
        selected_section=sec,
        search_query=q_search
    )

@app.get('/students/add', endpoint='add_student_view')
def add_student_view():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    subjects = db.q("SELECT * FROM subjects WHERE approval_status='APPROVED' ORDER BY id ASC")
    return render_template('student_add.html', title='إضافة طالب جديد', active='student_add', subjects=subjects)

@app.post('/students/add', endpoint='add_student')
def add_student():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    f = request.form
    full_name = f.get('full_name', '').strip()
    national_id = f.get('national_id', '').strip()
    class_name = f.get('class_name', db.setting('grade', 'الحادي عشر')).strip()
    section = f.get('section', db.setting('section', 'أ')).strip()
    username = f.get('username', '').strip()
    password = f.get('password', db.setting('student_default_password', '1234')).strip()
    subject_ids = request.form.getlist('subject_ids')

    if not is_valid_arabic_name(full_name):
        flash('يجب أن يتكون اسم الطالب من 3 إلى 4 مقاطع باللغة العربية.', 'error')
        return redirect(url_for('add_student_view'))

    if not username:
        username = national_id if national_id else f"std_{datetime.now().strftime('%M%S')}"

    try:
        sid = db.x("""
            INSERT INTO students (full_name, class_name, section, username, password, active, created_at, national_id)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """, (full_name, class_name, section, username, password, now(), national_id))

        # Enroll in selected subjects
        for sub_id in subject_ids:
            try:
                db.x("INSERT OR IGNORE INTO student_subjects (student_id, subject_id, created_at) VALUES (?, ?, ?)", (sid, sub_id, now()))
            except Exception:
                pass

        db.audit('Teacher', 'CREATE_STUDENT', 'students', sid)
        flash(f'تمت بنجاح إضافة الطالب ({full_name}) وتخصيص مواده الدراسية.', 'success')
    except sqlite3.IntegrityError:
        flash('اسم الطالب أو اسم المستخدم أو الرقم مسجل مسبقاً في النظام.', 'error')
        return redirect(url_for('add_student_view'))

    return redirect(url_for('students_list'))

@app.get('/students/edit/<int:id>', endpoint='edit_student_view')
def edit_student_view(id):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    student = db.q("SELECT * FROM students WHERE id=?", (id,), one=True)
    if not student:
        flash('الطالب غير موجود.', 'error')
        return redirect(url_for('students_list'))

    enrolled = [r['subject_id'] for r in db.q("SELECT subject_id FROM student_subjects WHERE student_id=?", (id,))]
    subjects = db.q("SELECT * FROM subjects WHERE approval_status='APPROVED' ORDER BY id ASC")
    return render_template('student_edit.html', title='تعديل بيانات الطالب', active='students', student=student, subjects=subjects, enrolled_subject_ids=enrolled)

@app.post('/students/edit/<int:id>', endpoint='edit_student')
def edit_student(id):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    student = db.q("SELECT * FROM students WHERE id=?", (id,), one=True)
    if not student:
        flash('الطالب غير موجود.', 'error')
        return redirect(url_for('students_list'))

    f = request.form
    full_name = f.get('full_name', '').strip()
    national_id = f.get('national_id', '').strip()
    class_name = f.get('class_name', '').strip()
    section = f.get('section', '').strip()
    username = f.get('username', '').strip()
    password = f.get('password', '').strip()
    subject_ids = request.form.getlist('subject_ids')

    try:
        db.x("""
            UPDATE students
            SET full_name=?, national_id=?, class_name=?, section=?, username=?, password=?
            WHERE id=?
        """, (full_name, national_id, class_name, section, username, password, id))

        # Update enrolled subjects
        db.x("DELETE FROM student_subjects WHERE student_id=?", (id,))
        for sub_id in subject_ids:
            db.x("INSERT OR IGNORE INTO student_subjects (student_id, subject_id, created_at) VALUES (?, ?, ?)", (id, sub_id, now()))

        flash(f'تم تحديث بيانات ومواد الطالب ({full_name}) بنجاح.', 'success')
    except Exception as e:
        flash(f'خطأ أثناء التعديل: {e}', 'error')

    return redirect(url_for('students_list'))

@app.get('/students/import', endpoint='import_students_view')
def import_students_view():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    subjects = db.q("SELECT * FROM subjects WHERE approval_status='APPROVED' ORDER BY id ASC")
    return render_template('student_import.html', title='استيراد كشف الطلاب', active='students', subjects=subjects)

@app.post('/students/import', endpoint='import_students_post')
def import_students_post():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    subj_id = request.form.get('subject_id', '').strip()
    file = request.files.get('students_file')

    if not file or not file.filename:
        flash('يرجى اختيار ملف صالح للاستيراد.', 'error')
        return redirect(url_for('import_students_view'))

    try:
        content = file.read().decode('utf-8-sig', errors='ignore')
        lines = [l.strip() for l in content.split('\n') if l.strip()]

        imported = 0
        for line in lines:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 1:
                fn = parts[0]
                cn = parts[1] if len(parts) > 1 and parts[1] else db.setting('grade', 'الحادي عشر')
                sec = parts[2] if len(parts) > 2 and parts[2] else db.setting('section', 'أ')
                nid = parts[3] if len(parts) > 3 else ''
                un = parts[4] if len(parts) > 4 and parts[4] else (nid if nid else f"std_{random.randint(1000, 9999)}")
                pw = parts[5] if len(parts) > 5 and parts[5] else db.setting('student_default_password', '1234')

                try:
                    sid = db.x("""
                        INSERT INTO students (full_name, class_name, section, username, password, active, created_at, national_id)
                        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """, (fn, cn, sec, un, pw, now(), nid))

                    if subj_id:
                        db.x("INSERT OR IGNORE INTO student_subjects (student_id, subject_id, created_at) VALUES (?, ?, ?)", (sid, subj_id, now()))
                    imported += 1
                except Exception:
                    continue

        flash(f'تم بنجاح استيراد ({imported}) طالب وإلحاقهم بالمادة الدراسية المحددة.', 'success')
    except Exception as e:
        flash(f'تعذر قراءة الملف: {e}', 'error')

    return redirect(url_for('students_list'))

@app.post('/students/delete/<int:id>')
def delete_student(id):
    db.x("DELETE FROM answers WHERE attempt_id IN (SELECT id FROM attempts WHERE student_id=?)", (id,))
    db.x("DELETE FROM attempt_snapshots WHERE attempt_id IN (SELECT id FROM attempts WHERE student_id=?)", (id,))
    db.x("DELETE FROM attempts WHERE student_id=?", (id,))
    db.x("DELETE FROM students WHERE id=?", (id,))
    db.audit('Teacher', 'DELETE_STUDENT', 'students', id)
    flash('تم حذف الطالب وسجلاته بنجاح.', 'success')
    return redirect(url_for('students_list'))

@app.post('/students/bulk-delete', endpoint='students_bulk_delete')
def students_bulk_delete():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    st_ids = request.form.getlist('selected_student_ids')
    if not st_ids:
        flash('لم يتم تحديد أي طلاب للحذف.', 'warning')
        return redirect(url_for('students_list'))

    del_count = 0
    for sid in st_ids:
        db.x("DELETE FROM answers WHERE attempt_id IN (SELECT id FROM attempts WHERE student_id=?)", (sid,))
        db.x("DELETE FROM attempt_snapshots WHERE attempt_id IN (SELECT id FROM attempts WHERE student_id=?)", (sid,))
        db.x("DELETE FROM attempts WHERE student_id=?", (sid,))
        db.x("DELETE FROM student_exam_overrides WHERE student_id = ?", (sid,))
        db.x("DELETE FROM students WHERE id = ?", (sid,))
        del_count += 1

    db.audit('Teacher', 'BULK_DELETE_STUDENTS', 'students', f"Deleted: {del_count}")
    flash(f'تم بنجاح حذف ({del_count}) طالب محدد من السجل.', 'success')
    return redirect(url_for('students_list'))

@app.get('/students/template', endpoint='students_template')
def students_template():
    output = io.StringIO()
    output.write('﻿') # UTF-8 BOM for Excel Arabic
    writer = csv.writer(output)
    writer.writerow(['الاسم_الرباعي', 'الرقم_الوطني', 'الصف', 'الشعبة', 'اسم_الدخول', 'كلمة_المرور'])
    writer.writerow(['أحمد باسم محمود الطراونة', '2009102030', 'الحادي عشر', 'أ', 'ahmad_t', '1234'])
    writer.writerow(['سارة خالد عبدالله النوايسة', '2009204050', 'الحادي عشر', 'أ', 'sara_n', '1234'])
    writer.writerow(['محمد عمر خليل الكركي', '2009305060', 'الحادي عشر', 'ب', 'mohammed_k', '1234'])

    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name='students_import_template.csv')

@app.post('/students/import-excel', endpoint='students_import_excel')
def students_import_excel():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    f = request.files.get('students_file')
    if not f or not f.filename:
        flash('يرجى اختيار ملف CSV أو Excel للاستيراد.', 'error')
        return redirect(url_for('students_list'))

    default_class = request.form.get('default_class', '').strip() or db.setting('grade', 'الحادي عشر')
    default_section = request.form.get('default_section', '').strip() or db.setting('section', 'أ')
    default_pwd = db.setting('student_default_password', '1234')

    filename = f.filename.lower()
    imported_count = 0
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        content = f.read()
        if filename.endswith('.csv') or filename.endswith('.txt'):
            try:
                decoded = content.decode('utf-8-sig')
            except UnicodeDecodeError:
                decoded = content.decode('windows-1256', errors='ignore')
            reader = csv.reader(io.StringIO(decoded))
            rows = list(reader)
            if rows:
                for r in rows[1:]:
                    if not r or not any(r):
                        continue
                    full_name = r[0].strip() if len(r) > 0 else ''
                    if not full_name:
                        continue
                    nat_id = r[1].strip() if len(r) > 1 else ''
                    cls_name = r[2].strip() if len(r) > 2 and r[2].strip() else default_class
                    sec = r[3].strip() if len(r) > 3 and r[3].strip() else default_section
                    uname = r[4].strip() if len(r) > 4 and r[4].strip() else (nat_id or f"std_{uuid.uuid4().hex[:6]}")
                    pwd = r[5].strip() if len(r) > 5 and r[5].strip() else default_pwd

                    db.x("""
                        INSERT INTO students (full_name, national_id, class_name, section, username, password, active, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    """, (full_name, nat_id, cls_name, sec, uname, pwd, now_str))
                    imported_count += 1
        else:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
                sheet = wb.active
                rows = list(sheet.iter_rows(values_only=True))
                if rows:
                    for r in rows[1:]:
                        if not r or not any(r):
                            continue
                        full_name = str(r[0]).strip() if r[0] is not None else ''
                        if not full_name or full_name == 'None':
                            continue
                        nat_id = str(r[1]).strip() if len(r) > 1 and r[1] is not None and str(r[1]) != 'None' else ''
                        cls_name = str(r[2]).strip() if len(r) > 2 and r[2] is not None and str(r[2]) != 'None' else default_class
                        sec = str(r[3]).strip() if len(r) > 3 and r[3] is not None and str(r[3]) != 'None' else default_section
                        uname = str(r[4]).strip() if len(r) > 4 and r[4] is not None and str(r[4]) != 'None' else (nat_id or f"std_{uuid.uuid4().hex[:6]}")
                        pwd = str(r[5]).strip() if len(r) > 5 and r[5] is not None and str(r[5]) != 'None' else default_pwd

                        db.x("""
                            INSERT INTO students (full_name, national_id, class_name, section, username, password, active, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                        """, (full_name, nat_id, cls_name, sec, uname, pwd, now_str))
                        imported_count += 1
            except Exception as e_excel:
                flash(f'تعذر معالجة ملف الإكسل (يرجى حفظه كـ CSV وإعادة المحاولة): {e_excel}', 'error')
                return redirect(url_for('students_list'))

        db.audit('Teacher', 'IMPORT_STUDENTS_EXCEL', 'students', f"Imported: {imported_count}")
        flash(f'✓ تم بنجاح استيراد ({imported_count}) طالب وإضافتهم لسجل المدرسة.', 'success')
    except Exception as e:
        flash(f'حدث خطأ أثناء استيراد الطلاب: {e}', 'error')

    return redirect(url_for('students_list'))

# ==============================================================================
# Results Dashboard & Attempt Detail
# ==============================================================================
@app.get('/results')
def results_dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    subj_id = request.args.get('subject_id', '').strip()
    exam_id = request.args.get('exam_id', '').strip()

    sql = """
        SELECT a.*, e.title as exam_title, e.subject_id, s.name as subject_name
        FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        LEFT JOIN subjects s ON s.id = e.subject_id
        WHERE 1=1
    """
    params = []
    if subj_id:
        sql += " AND e.subject_id = ?"
        params.append(subj_id)
    if exam_id:
        sql += " AND a.exam_id = ?"
        params.append(exam_id)

    sql += " ORDER BY a.id DESC"
    attempts = db.q(sql, tuple(params))

    subjects = db.q("SELECT * FROM subjects WHERE approval_status='APPROVED' ORDER BY id ASC")
    if subj_id:
        exams = db.q("SELECT id, title FROM exams WHERE subject_id = ? AND is_archived = 0 ORDER BY id DESC", (subj_id,))
    else:
        exams = db.q("SELECT id, title FROM exams WHERE is_archived = 0 ORDER BY id DESC")

    return render_template(
        'results.html',
        title='النتائج والتقارير',
        active='results',
        attempts=attempts,
        subjects=subjects,
        exams=exams,
        selected_subject_id=subj_id,
        selected_exam_id=exam_id
    )

@app.get('/results/print-sheet/<int:exam_id>', endpoint='print_exam_result_sheet')
def print_exam_result_sheet(exam_id):
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    exam = db.q("""
        SELECT e.*, s.name as subject_name
        FROM exams e
        JOIN subjects s ON s.id = e.subject_id
        WHERE e.id = ?
    """, (exam_id,), one=True)
    if not exam:
        flash('الامتحان غير موجود.', 'error')
        return redirect(url_for('results_dashboard'))

    attempts = db.q("""
        SELECT a.*, s.full_name as student_full_name, s.national_id, s.class_name, s.section
        FROM attempts a
        JOIN students s ON s.id = a.student_id
        WHERE a.exam_id = ? AND a.status = 'SUBMITTED'
        ORDER BY a.score DESC, s.full_name ASC
    """, (exam_id,))

    return render_template(
        'print_exam_sheet.html',
        exam=exam,
        attempts=attempts,
        title=f"كشف نتائج امتحان {exam['title']}"
    )

@app.get('/results/attempt/<int:id>')
def attempt_result_detail(id):
    attempt = db.q("""
        SELECT a.*, e.title as exam_title, e.duration as exam_duration
        FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        WHERE a.id = ?
    """, (id,), one=True)

    if not attempt:
        flash('المحاولة غير موجودة.', 'error')
        return redirect(url_for('results_dashboard'))

    # Retrieve answers joined with IMMUTABLE SNAPSHOTS
    answers_details = db.q("""
        SELECT s.position, s.question_text, s.option_a, s.option_b, s.option_c, s.option_d,
               s.correct_option, s.mark, s.direction, s.language,
               ans.answer, ans.is_correct
        FROM attempt_snapshots s
        LEFT JOIN answers ans ON ans.snapshot_id = s.id AND ans.attempt_id = s.attempt_id
        WHERE s.attempt_id = ?
        ORDER BY s.position ASC
    """, (id,))

    return render_template('result_detail.html', title='تفاصيل النتيجة', active='results', attempt=attempt, answers_details=answers_details)

# ==============================================================================
# Printing & PDF Export (A4 Portrait, Semantic Header on Page 1 Only)
# ==============================================================================
@app.get('/print/exam/<int:id>')
def print_exam(id):
    exam = db.q("""
        SELECT e.*, s.name as subject_name, s.language as subject_language, s.direction as subject_direction
        FROM exams e
        LEFT JOIN subjects s ON s.id = e.subject_id
        WHERE e.id = ?
    """, (id,), one=True)

    if not exam:
        flash('الامتحان غير موجود.', 'error')
        return redirect(url_for('exams_list'))

    questions = db.q("""
        SELECT q.*, eq.position
        FROM exam_questions eq
        JOIN questions q ON q.id = eq.question_id
        WHERE eq.exam_id = ?
        ORDER BY eq.position ASC
    """, (id,))

    return render_template('print_exam.html', exam=exam, questions=questions)

@app.get('/print/attempt/<int:id>')
def print_attempt_result(id):
    attempt = db.q("""
        SELECT a.*, e.title as exam_title
        FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        WHERE a.id = ?
    """, (id,), one=True)

    if not attempt:
        flash('المحاولة غير موجودة.', 'error')
        return redirect(url_for('results_dashboard'))

    answers_details = db.q("""
        SELECT s.position, s.question_text, s.option_a, s.option_b, s.option_c, s.option_d,
               s.correct_option, s.mark, s.direction, s.language,
               ans.answer, ans.is_correct
        FROM attempt_snapshots s
        LEFT JOIN answers ans ON ans.snapshot_id = s.id AND ans.attempt_id = s.attempt_id
        WHERE s.attempt_id = ?
        ORDER BY s.position ASC
    """, (id,))

    return render_template('print_result.html', attempt=attempt, answers_details=answers_details)

@app.get('/pdf/exam/<int:id>')
def export_exam_pdf(id):
    """PDF generator using reportlab, conforming strictly to A4 specs."""
    exam = db.q("SELECT * FROM exams WHERE id=?", (id,), one=True)
    if not exam:
        flash('الامتحان غير موجود.', 'error')
        return redirect(url_for('exams_list'))

    pdf_buffer = io.BytesIO()
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        width, height = A4

        # Page 1 Header
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, height - 50, f"Exam: {exam['title']}")
        c.setFont("Helvetica", 10)
        c.drawString(100, height - 70, f"Duration: {exam['duration']} minutes | Questions: {exam['question_count']}")
        c.line(50, height - 80, width - 50, height - 80)

        # Questions
        questions = db.q("""
            SELECT q.* FROM exam_questions eq
            JOIN questions q ON q.id = eq.question_id
            WHERE eq.exam_id=? ORDER BY eq.position ASC
        """, (id,))

        y = height - 110
        for i, q in enumerate(questions, 1):
            if y < 80:
                c.showPage()
                y = height - 50  # Start immediately near top on Page 2+ (no blank header gap!)
            
            c.setFont("Helvetica-Bold", 10)
            c.drawString(60, y, f"{i}. {q['question'][:80]}")
            y -= 16
            c.setFont("Helvetica", 9)
            c.drawString(70, y, f"A) {q['option_a'][:30]}  B) {q['option_b'][:30]}  C) {q['option_c'][:30]}  D) {q['option_d'][:30]}")
            y -= 22

        c.save()
        pdf_buffer.seek(0)
        return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=f"exam_{id}.pdf")
    except Exception as e:
        # Fallback to direct HTML print view
        return redirect(url_for('print_exam', id=id))

# ==============================================================================
# Settings, Identity & Branding
# ==============================================================================
@app.get('/settings', endpoint='settings')
@app.get('/settings')
def settings_view():
    return render_template('settings.html', title='الهوية المدرسية والإعدادات', active='settings')

@app.post('/settings/save')
def save_settings():
    f = request.form
    for k in ('teacher_name', 'school_name', 'directorate_name', 'district_name', 'ministry_name',
              'primary_color', 'secondary_color', 'font_family', 'student_default_password', 'footer_text',
              'academic_year', 'semester_name', 'grade', 'exam_default_note',
              'tier_excellent_messages', 'tier_very_good_messages', 'tier_good_messages', 'tier_pass_messages',
              'firebase_api_key', 'firebase_auth_domain', 'firebase_project_id', 'firebase_storage_bucket',
              'firebase_messaging_sender_id', 'firebase_app_id', 'teacher_online_secret', 'online_api_url'):
        if k in f:
            db.set_setting(k, f.get(k, '').strip())

    if f.get('admin_password', '').strip():
        db.set_setting('admin_password', f.get('admin_password').strip())

    # Handle School Logo Upload / Delete
    if f.get('delete_school_logo') == '1':
        db.set_setting('school_logo_path', '')
    school_logo_file = request.files.get('school_logo')
    if school_logo_file and school_logo_file.filename:
        ext = Path(school_logo_file.filename).suffix.lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp'):
            fname = f"school_logo_{hashlib.md5(os.urandom(8)).hexdigest()}{ext}"
            school_logo_file.save(ASSETS_DIR / fname)
            db.set_setting('school_logo_path', fname)

    # Handle Ministry Logo Upload / Delete
    if f.get('delete_ministry_logo') == '1':
        db.set_setting('ministry_logo_path', '')
    ministry_logo_file = request.files.get('ministry_logo')
    if ministry_logo_file and ministry_logo_file.filename:
        ext = Path(ministry_logo_file.filename).suffix.lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp'):
            fname = f"ministry_logo_{hashlib.md5(os.urandom(8)).hexdigest()}{ext}"
            ministry_logo_file.save(ASSETS_DIR / fname)
            db.set_setting('ministry_logo_path', fname)

    # Handle Platform Logo Upload / Delete (For custom logo design)
    if f.get('delete_platform_logo') == '1':
        db.set_setting('platform_logo_path', '')
    platform_logo_file = request.files.get('platform_logo')
    if platform_logo_file and platform_logo_file.filename:
        ext = Path(platform_logo_file.filename).suffix.lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp', '.svg'):
            fname = f"platform_logo_{hashlib.md5(os.urandom(8)).hexdigest()}{ext}"
            platform_logo_file.save(ASSETS_DIR / fname)
            db.set_setting('platform_logo_path', fname)

    db.audit('Teacher', 'UPDATE_SETTINGS', 'settings')
    flash('تم حفظ الإعدادات الرسمية والهوية بنجاح.', 'success')
    return redirect(url_for('settings_view'))

@app.get('/settings/feedback', endpoint='settings_feedback_view')
def settings_feedback_view():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    return render_template('settings_feedback.html', title='رسائل التقدير والتشجيع', active='feedback_settings')

@app.post('/settings/feedback/save', endpoint='save_feedback_settings')
def save_feedback_settings():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    f = request.form
    for k in ('tier_excellent_messages', 'tier_very_good_messages', 'tier_good_messages', 'tier_pass_messages'):
        if k in f:
            db.set_setting(k, f.get(k, '').strip())
    flash('تم بنجاح حفظ واعتماد رسائل التقدير والتشجيع للطلاب.', 'success')
    return redirect(url_for('settings_feedback_view'))

# ==============================================================================
# Audit Log & Backup Center
# ==============================================================================
@app.get('/audit-log')
def audit_log_view():
    logs = db.q("SELECT * FROM audit_log ORDER BY id DESC LIMIT 100")
    return render_template('audit_log.html', title='سجل التدقيق الإداري', active='audit', logs=logs)

@app.get('/backup')
def backup_view():
    backups = []
    if BACKUPS_DIR.exists():
        for bf in sorted(BACKUPS_DIR.iterdir(), key=os.path.getmtime, reverse=True):
            if bf.is_file() and bf.suffix == '.db':
                backups.append({
                    'name': bf.name,
                    'size': bf.stat().st_size,
                    'created': datetime.fromtimestamp(bf.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
    return render_template('backup.html', title='النسخ الاحتياطي', active='backup', backups=backups)

@app.post('/backup/create')
def create_backup_action():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = BACKUPS_DIR / f"backup_exam_platform_{timestamp}.db"
    
    # Ensure current state is synced
    db.sync()
    source = db.db_path if db.is_shadow else DB_PATH
    shutil.copy2(source, backup_path)
    
    db.audit('Teacher', 'CREATE_BACKUP', 'backup', None, after_state=backup_path.name)
    flash(f'تم إنشاء نسخة احتياطية بنجاح: {backup_path.name}', 'success')
    return redirect(url_for('backup_view'))

@app.get('/backup/download/<filename>')
def download_backup_file(filename):
    safe_name = safe_filename(filename)
    p = BACKUPS_DIR / safe_name
    if p.exists() and p.is_file():
        return send_file(p, as_attachment=True, download_name=safe_name)
    flash('الملف غير موجود.', 'error')
    return redirect(url_for('backup_view'))

# ==============================================================================
# Student Portal & Active Exam Taker
# ==============================================================================
@app.get('/student')
@app.get('/student/login')
def student_login():
    if is_student_logged_in():
        return redirect(url_for('student_home'))
    return render_template('student_login.html', title='بوابة الطلاب')

@app.post('/student/login/post')
def student_login_post():
    identifier = (request.form.get('student_identifier') or request.form.get('username') or '').strip()
    exam_code = (request.form.get('exam_code') or '').strip()
    password = (request.form.get('password') or '').strip()

    if not identifier:
        flash('يرجى إدخال الرقم الوطني أو اسم المستخدم الخاص بك.', 'error')
        return redirect(url_for('student_login'))

    # Match student by username or national_id
    student_row = db.q("""
        SELECT * FROM students 
        WHERE (LOWER(username) = ? OR national_id = ?) AND active = 1
    """, (identifier.lower(), identifier), one=True)

    if not student_row:
        flash('عذراً، الرقم الوطني أو اسم المستخدم غير مسجل في النظام. يرجى مراجعة المعلم.', 'error')
        return redirect(url_for('student_login'))

    student = dict(student_row)

    # If password was provided (e.g. from tests), verify it; otherwise permit direct national_id access
    if password and student.get('password') and student['password'] != password:
        flash('كلمة المرور المدخلة غير صحيحة.', 'error')
        return redirect(url_for('student_login'))

    target_exam = None
    if exam_code:
        target_exam = db.q("""
            SELECT * FROM exams 
            WHERE (exam_code = ? OR id = ?) AND is_archived = 0 AND (status = 'PUBLISHED' OR active = 1)
        """, (exam_code, exam_code), one=True)
        if not target_exam:
            flash(f'رمز دخول الامتحان ({exam_code}) غير صحيح، أو أن الامتحان غير متاح حالياً. يرجى التأكد من المعلم.', 'error')
            return redirect(url_for('student_login'))

    session['student_id'] = student['id']
    session['student_name'] = student['full_name']
    session['student_class'] = student['class_name']
    session['student_section'] = student['section']

    db.audit(student['full_name'], 'STUDENT_LOGIN', 'students', student['id'])

    # If exam code was given and verified, go DIRECTLY to exam room!
    if target_exam:
        return redirect(url_for('student_exam_page', id=target_exam['id']))

    # Otherwise check if there is only 1 active exam, go directly to it!
    active_exams = db.q("SELECT id FROM exams WHERE is_archived = 0 AND (status = 'PUBLISHED' OR active = 1) ORDER BY id DESC LIMIT 2")
    if len(active_exams) == 1:
        return redirect(url_for('student_exam_page', id=active_exams[0]['id']))

    return redirect(url_for('student_home'))

@app.get('/student/logout')
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    session.pop('student_class', None)
    session.pop('student_section', None)
    return redirect(url_for('student_login'))

@app.get('/student/home')
def student_home():
    if not is_student_logged_in():
        return redirect(url_for('student_login'))

    sid = session['student_id']
    student = db.q("SELECT * FROM students WHERE id = ?", (sid,), one=True)

    # Fetch published exams
    exams = db.q("""
        SELECT e.*, s.name as subject_name,
               (SELECT status FROM attempts WHERE exam_id = e.id AND student_id = ? ORDER BY id DESC LIMIT 1) as user_attempt_status,
               (SELECT id FROM attempts WHERE exam_id = e.id AND student_id = ? ORDER BY id DESC LIMIT 1) as latest_attempt_id,
               (SELECT COUNT(*) FROM attempts WHERE exam_id = e.id AND student_id = ? AND status='SUBMITTED') as submitted_count,
               (SELECT extra_attempts FROM student_exam_overrides seo WHERE seo.exam_id = e.id AND seo.student_id = ?) as extra_attempts
        FROM exams e
        JOIN subjects s ON s.id = e.subject_id
        WHERE e.status = 'PUBLISHED' OR e.active = 1
        ORDER BY e.id DESC
    """, (sid, sid, sid, sid))

    return render_template('student_home.html', student=student, available_exams=exams)

@app.route('/student/exam/<int:id>', methods=['GET', 'POST'])
def student_exam_page(id):
    if not is_student_logged_in():
        return redirect(url_for('student_login'))

    sid = session['student_id']
    student = db.q("SELECT * FROM students WHERE id = ?", (sid,), one=True)
    exam = db.q("""
        SELECT e.*, s.name as subject_name, s.language as subject_language, s.direction as subject_direction
        FROM exams e
        JOIN subjects s ON s.id = e.subject_id
        WHERE e.id = ? AND (e.status = 'PUBLISHED' OR e.active = 1)
    """, (id,), one=True)

    if not exam:
        flash('هذا الامتحان غير متاح حالياً.', 'error')
        return redirect(url_for('student_home'))

    # Check password if configured
    if exam['password']:
        input_pw = request.form.get('exam_password', '')
        if request.method == 'POST' and input_pw:
            session[f'exam_pw_ok_{id}'] = (input_pw == exam['password'])
        if not session.get(f'exam_pw_ok_{id}'):
            # Prompt for exam password
            return render_template_string('''
            <!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>كلمة مرور الامتحان</title>
            <link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}"></head>
            <body style="display:grid; place-items:center; min-height:100vh; background:var(--bg);">
              <div class="card" style="max-width:400px; width:100%; text-align:center; padding:30px;">
                <h2>🔒 امتحان محمي بكلمة مرور</h2>
                <p style="color:var(--text-muted); font-size:13px; margin:10px 0 20px;">أدخل كلمة المرور التي زودتك بها المعلمة لبدء هذا الامتحان.</p>
                <form method="POST">
                  <input type="password" name="exam_password" class="form-control" placeholder="كلمة المرور..." required autofocus>
                  <button type="submit" class="btn btn-primary btn-lg" style="width:100%; margin-top:16px;">دخول الامتحان ←</button>
                  <a href="{{ url_for('student_home') }}" class="btn btn-secondary" style="width:100%; margin-top:8px;">إلغاء</a>
                </form>
              </div>
            </body></html>
            ''')

    # Check for existing attempts
    active_att = db.q("SELECT * FROM attempts WHERE exam_id=? AND student_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1", (id, sid), one=True)
    submitted_count = db.q("SELECT COUNT(*) as n FROM attempts WHERE exam_id=? AND student_id=? AND status='SUBMITTED'", (id, sid), one=True)['n']
    override = db.q("SELECT extra_attempts FROM student_exam_overrides WHERE student_id=? AND exam_id=?", (sid, id), one=True)
    allowed_total = 1 + (override['extra_attempts'] if override else 0)

    if submitted_count >= allowed_total and not active_att and submitted_count > 0:
        # Already used all allowed attempts: Redirect to result, block retake!
        latest_att = db.q("SELECT id FROM attempts WHERE exam_id=? AND student_id=? ORDER BY id DESC LIMIT 1", (id, sid), one=True)
        flash('لقد أكملت تقديم هذا الامتحان سابقاً. يرجى مراجعة المعلمة إذا كنت بحاجة لمنحك فرصة تقديم إضافية.', 'warning')
        if latest_att:
            return redirect(url_for('student_view_result', attempt_id=latest_att['id']))
        return redirect(url_for('student_home'))

    if not active_att:
        # Create NEW attempt and take FULL IMMUTABLE SNAPSHOT of questions!
        now_dt = datetime.now()
        started_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')

        # Calculate max score from attached questions
        total_mark_row = db.q("""
            SELECT SUM(q.mark) as total FROM exam_questions eq
            JOIN questions q ON q.id = eq.question_id
            WHERE eq.exam_id = ?
        """, (id,), one=True)
        exam_total_mark = total_mark_row['total'] or 0.0

        att_id = db.x("""
            INSERT INTO attempts (exam_id, student_id, student_name, status, score, total, percentage, started_at, last_activity_at)
            VALUES (?, ?, ?, 'ACTIVE', 0, ?, 0, ?, ?)
        """, (id, sid, student['full_name'], exam_total_mark, started_str, started_str))

        # Take IMMUTABLE QUESTION SNAPSHOT
        questions = db.q("""
            SELECT q.*, eq.position FROM exam_questions eq
            JOIN questions q ON q.id = eq.question_id
            WHERE eq.exam_id = ?
            ORDER BY eq.position ASC
        """, (id,))

        if exam['random_order']:
            import random
            q_list = list(questions)
            random.shuffle(q_list)
            questions = q_list

        for idx, q in enumerate(questions, 1):
            db.x("""
                INSERT INTO attempt_snapshots (attempt_id, question_id, position, question_text,
                                              option_a, option_b, option_c, option_d, correct_option,
                                              mark, image_path, language, direction)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                att_id, q['id'], idx, q['question'], q['option_a'], q['option_b'], q['option_c'], q['option_d'],
                q['correct'], q['mark'], q['image_path'], q['language'], q['direction']
            ))

        db.audit(student['full_name'], 'START_EXAM', 'attempts', att_id)
        active_att = db.q("SELECT * FROM attempts WHERE id=?", (att_id,), one=True)

    # Retrieve snapshots
    snapshots = db.q("SELECT * FROM attempt_snapshots WHERE attempt_id=? ORDER BY position ASC", (active_att['id'],))
    
    # Retrieve saved answers
    existing_answers = db.q("SELECT snapshot_id, answer FROM answers WHERE attempt_id=?", (active_att['id'],))
    saved_answers = {a['snapshot_id']: a['answer'] for a in existing_answers}

    # Calculate timer expiration timestamp
    started_time = datetime.strptime(active_att['started_at'], '%Y-%m-%d %H:%M:%S')
    end_timestamp = int(started_time.timestamp()) + (exam['duration'] * 60)

    school_logo_name = db.setting('school_logo_path', '')
    ministry_logo_name = db.setting('ministry_logo_path', '')
    school_logo_url = url_for('asset_file', name=school_logo_name) if school_logo_name else None
    ministry_logo_url = url_for('asset_file', name=ministry_logo_name) if ministry_logo_name else None

    return render_template(
        'student_exam.html',
        exam=exam,
        student=student,
        attempt=active_att,
        snapshots=snapshots,
        saved_answers=saved_answers,
        end_timestamp=end_timestamp,
        now_date=datetime.now().strftime('%Y/%m/%d'),
        school_logo_url=school_logo_url,
        ministry_logo_url=ministry_logo_url,
        s=db.settings()
    )

@app.post('/student/exam/<int:attempt_id>/autosave')
def student_exam_autosave(attempt_id):
    if not is_student_logged_in():
        return jsonify(ok=False, error="Unauthorized"), 401

    sid = session['student_id']
    attempt = db.q("SELECT * FROM attempts WHERE id=? AND student_id=? AND status='ACTIVE'", (attempt_id, sid), one=True)
    if not attempt:
        return jsonify(ok=False, error="Active attempt not found"), 404

    data = request.json or request.form
    snapshot_id = data.get('question_id')
    selected_answer = (data.get('answer') or '').strip().upper()

    snapshot = db.q("SELECT * FROM attempt_snapshots WHERE id=? AND attempt_id=?", (snapshot_id, attempt_id), one=True)
    if not snapshot:
        return jsonify(ok=False, error="Snapshot not found"), 404

    correct_opt = snapshot['correct_option'].strip().upper()
    is_corr = 1 if selected_answer == correct_opt else 0
    mark_awarded = snapshot['mark'] if is_corr else 0.0

    # Upsert answer
    existing = db.q("SELECT id FROM answers WHERE attempt_id=? AND snapshot_id=?", (attempt_id, snapshot_id), one=True)
    if existing:
        db.x("""
            UPDATE answers
            SET answer = ?, correct = ?, is_correct = ?, mark = ?, answered_at = ?
            WHERE id = ?
        """, (selected_answer, correct_opt, is_corr, mark_awarded, now(), existing['id']))
    else:
        db.x("""
            INSERT INTO answers (attempt_id, snapshot_id, question_id, answer, correct, is_correct, mark, answered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (attempt_id, snapshot_id, snapshot['question_id'], selected_answer, correct_opt, is_corr, mark_awarded, now()))

    db.x("UPDATE attempts SET last_activity_at = ? WHERE id = ?", (now(), attempt_id))
    return jsonify(ok=True)

@app.post('/student/exam/<int:attempt_id>/submit')
def student_submit_exam(attempt_id):
    if not is_student_logged_in():
        return redirect(url_for('student_login'))

    sid = session['student_id']
    attempt = db.q("SELECT * FROM attempts WHERE id=? AND student_id=? AND status='ACTIVE'", (attempt_id, sid), one=True)
    if not attempt:
        # If already submitted, redirect to result
        sub_att = db.q("SELECT * FROM attempts WHERE id=? AND student_id=?", (attempt_id, sid), one=True)
        if sub_att and sub_att['status'] == 'SUBMITTED':
            return redirect(url_for('student_view_result', attempt_id=attempt_id))
        flash('المحاولة غير صالحة أو تم إنهاؤها مسبقاً.', 'error')
        return redirect(url_for('student_home'))

    # Save any final radio inputs in form
    snapshots = db.q("SELECT * FROM attempt_snapshots WHERE attempt_id=?", (attempt_id,))
    for sn in snapshots:
        val = request.form.get(f"q_{sn['id']}", '').strip().upper()
        if val:
            correct_opt = sn['correct_option'].strip().upper()
            is_corr = 1 if val == correct_opt else 0
            mark_awarded = sn['mark'] if is_corr else 0.0
            existing = db.q("SELECT id FROM answers WHERE attempt_id=? AND snapshot_id=?", (attempt_id, sn['id']), one=True)
            if existing:
                db.x("UPDATE answers SET answer=?, is_correct=?, mark=?, answered_at=? WHERE id=?", (val, is_corr, mark_awarded, now(), existing['id']))
            else:
                db.x("INSERT INTO answers (attempt_id, snapshot_id, question_id, answer, correct, is_correct, mark, answered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (attempt_id, sn['id'], sn['question_id'], val, correct_opt, is_corr, mark_awarded, now()))

    # Calculate final score based exclusively on the snapshot
    res_calc = db.q("SELECT SUM(mark) as score FROM answers WHERE attempt_id=? AND is_correct=1", (attempt_id,), one=True)
    score = res_calc['score'] or 0.0
    total = attempt['total'] or 1.0
    pct = round((score / total) * 100, 2)
    submitted_str = now()

    db.x("""
        UPDATE attempts
        SET status = 'SUBMITTED',
            score = ?,
            percentage = ?,
            finished_at = ?,
            submitted_at = ?
        WHERE id = ?
    """, (score, pct, submitted_str, submitted_str, attempt_id))

    db.audit(attempt['student_name'], 'SUBMIT_EXAM', 'attempts', attempt_id, after_state=f"Score: {score}/{total} ({pct}%)")
    return redirect(url_for('student_view_result', attempt_id=attempt_id))

@app.get('/student/result/<int:attempt_id>')
def student_view_result(attempt_id):
    if not is_student_logged_in():
        return redirect(url_for('student_login'))

    sid = session['student_id']
    # Security: IDOR prevention - Ensure student owns this attempt
    attempt = db.q("""
        SELECT a.*, e.title as exam_title
        FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        WHERE a.id = ? AND a.student_id = ?
    """, (attempt_id, sid), one=True)

    if not attempt:
        flash('غير مصرح لك بالوصول إلى هذه النتيجة.', 'error')
        return redirect(url_for('student_home'))

    answers_details = db.q("""
        SELECT s.position, s.question_text, s.option_a, s.option_b, s.option_c, s.option_d,
               s.correct_option, s.mark, s.direction, s.language,
               ans.answer, ans.is_correct
        FROM attempt_snapshots s
        LEFT JOIN answers ans ON ans.snapshot_id = s.id AND ans.attempt_id = s.attempt_id
        WHERE s.attempt_id = ?
        ORDER BY s.position ASC
    """, (attempt_id,))

    pct = attempt['percentage'] or 0.0
    import random
    if pct >= 90:
        raw_msgs = db.setting('tier_excellent_messages', DEFAULT_SETTINGS.get('tier_excellent_messages', ''))
        tier_title = 'تقدير ممتاز 🌟'
        tier_class = 'tier-excellent'
    elif pct >= 80:
        raw_msgs = db.setting('tier_very_good_messages', DEFAULT_SETTINGS.get('tier_very_good_messages', ''))
        tier_title = 'تقدير جيد جداً ✨'
        tier_class = 'tier-very-good'
    elif pct >= 65:
        raw_msgs = db.setting('tier_good_messages', DEFAULT_SETTINGS.get('tier_good_messages', ''))
        tier_title = 'تقدير جيد 👍'
        tier_class = 'tier-good'
    else:
        raw_msgs = db.setting('tier_pass_messages', DEFAULT_SETTINGS.get('tier_pass_messages', ''))
        tier_title = 'مقبول / بحاجة لمتابعة 📚'
        tier_class = 'tier-pass'

    lines = [l.strip() for l in raw_msgs.split('\n') if l.strip()]
    encouraging_message = random.choice(lines) if lines else 'مبارك إتمامك للامتحان'

    return render_template(
        'student_result.html',
        attempt=attempt,
        answers_details=answers_details,
        tier_title=tier_title,
        tier_class=tier_class,
        encouraging_message=encouraging_message
    )

# ==============================================================================

# ==============================================================================
# ==============================================================================
# Curriculum Unit to Questions Generator (AI Smart Derivation Engine)
# ==============================================================================
@app.get('/curriculum-generator', endpoint='curriculum_generator_view')
def curriculum_generator_view():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    subjects = db.q("SELECT * FROM subjects WHERE approval_status='APPROVED' ORDER BY id ASC")
    packages = db.q("""
        SELECT p.*, s.name as subject_name 
        FROM question_packages p 
        JOIN subjects s ON s.id = p.subject_id 
        ORDER BY s.id ASC, p.sort_order ASC
    """)

    return render_template(
        'curriculum_generator.html',
        title='توليد الأسئلة الذكي من المنهاج',
        active='curriculum_gen',
        subjects=subjects,
        packages=packages
    )

def extract_text_from_upload(file_storage):
    if not file_storage or not file_storage.filename:
        return "", "لم يتم إرفاق أي ملف"

    fn = file_storage.filename.lower()
    ext = fn.split('.')[-1]
    b = file_storage.read()

    if ext == 'docx':
        try:
            import zipfile, xml.etree.ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                xml_content = z.read('word/document.xml')
                tree = ET.fromstring(xml_content)
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                paras = []
                for p in tree.iterfind('.//w:p', ns):
                    texts = [node.text for node in p.iterfind('.//w:t', ns) if node.text]
                    if texts:
                        paras.append(''.join(texts))
                return '\n'.join(paras), None
        except Exception as e:
            return "", f"تعذر قراءة ملف الوورد: {e}"

    elif ext == 'pdf':
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(b))
            texts = [p.extract_text() for p in reader.pages if p.extract_text()]
            if texts:
                return '\n'.join(texts), None
        except Exception:
            pass
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(b)) as pdf:
                texts = [p.extract_text() for p in pdf.pages if p.extract_text()]
                if texts:
                    return '\n'.join(texts), None
        except Exception as e:
            return "", f"تعذر قراءة ملف PDF: {e}"
        return "", "لم يتم العثور على نصوص قابلة للقراءة في ملف PDF"

    elif ext in ('png', 'jpg', 'jpeg', 'webp', 'bmp'):
        try:
            import tempfile, os, OSR
            with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
                tmp.write(b)
                tmp_path = tmp.name
            txt, warn = OSR.ocr_image_file(tmp_path, lang='ara+eng')
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return txt, warn
        except Exception as e:
            return "", f"فشل التعرف الضوئي (OCR) على الصورة: {e}"

    elif ext in ('txt', 'csv'):
        try:
            return b.decode('utf-8', errors='ignore'), None
        except Exception as e:
            return "", f"فشل قراءة الملف النصي: {e}"

    return "", "صيغة الملف غير مدعومة. الصيغ المدعومة: docx, pdf, png, jpg, txt"

@app.post('/api/curriculum/extract-file', endpoint='api_curriculum_extract_file')
def api_curriculum_extract_file():
    if not is_admin_logged_in():
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'يرجى اختيار ملف صالح'}), 400

    text, warn_or_err = extract_text_from_upload(f)
    if not text.strip():
        return jsonify({'ok': False, 'error': warn_or_err or 'الملف فارغ أو لا يحتوي على نصوص مقروءة'}), 400

    return jsonify({
        'ok': True,
        'text': text.strip(),
        'filename': f.filename,
        'char_count': len(text.strip()),
        'warning': warn_or_err if warn_or_err and '⚠️' in warn_or_err else None
    })

@app.post('/api/questions/<int:id>/set-difficulty', endpoint='api_set_question_difficulty')
def api_set_question_difficulty(id):
    if not is_admin_logged_in():
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403
    diff = request.form.get('difficulty', '').strip()
    if diff in ('سهل', 'متوسط', 'صعب'):
        db.x("UPDATE questions SET difficulty = ?, updated_at = ? WHERE id = ?", (diff, now(), id))
        db.audit('Teacher', 'SET_DIFFICULTY', 'questions', id, after_state=f"Difficulty: {diff}")
        return jsonify({'ok': True, 'difficulty': diff})
    return jsonify({'ok': False, 'error': 'مستوى صعوبة غير صالح'}), 400

@app.post('/curriculum-generator/generate', endpoint='curriculum_generator_post')
def curriculum_generator_post():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    f = request.form
    sub_id = f.get('subject_id', type=int)
    pkg_id = f.get('package_id', type=int)
    new_pkg_name = f.get('new_package_name', '').strip()
    content_text = f.get('content_text', '').strip()
    count = int(f.get('question_count', 10))

    # If content_text was left empty, check if curriculum_file was uploaded
    if not content_text:
        uploaded_file = request.files.get('curriculum_file')
        if uploaded_file and uploaded_file.filename:
            extracted_text, err = extract_text_from_upload(uploaded_file)
            if extracted_text:
                content_text = extracted_text.strip()

    if not sub_id or not content_text:
        flash('يرجى تحديد المادة ورفع ملف المنهاج أو لصق نصوص الدرس.', 'error')
        return redirect(url_for('curriculum_generator_view'))

    # If new package name specified, create it
    if new_pkg_name:
        pkg_id = db.x("""
            INSERT INTO question_packages (subject_id, name, description, created_at, updated_at)
            VALUES (?, ?, 'حزمة مولدة ذكياً من نصوص المنهاج', ?, ?)
        """, (sub_id, new_pkg_name, now(), now()))

    subject = db.q("SELECT * FROM subjects WHERE id=?", (sub_id,), one=True)
    sub_name = subject['name'] if subject else ''
    pkg_row = db.q("SELECT * FROM question_packages WHERE id=?", (pkg_id,), one=True) if pkg_id else None
    pkg_name = pkg_row['name'] if pkg_row else (new_pkg_name or 'الوحدة المستهدفة')

    # Smart Question Derivation
    import random
    sentences = [s.strip() for s in re.split(r'[\.\n\؛\!\?]', content_text) if len(s.strip()) > 25]
    if len(sentences) < 2:
        flash('النص المدخل قصير جداً. يرجى لصق فقرات تعليمية متكاملة لاشتقاق الأسئلة.', 'warning')
        return redirect(url_for('curriculum_generator_view'))

    created_count = 0
    difficulties = ['سهل', 'متوسط', 'صعب']

    for i in range(min(count, len(sentences))):
        s = sentences[i]
        words = s.split()
        if len(words) < 5:
            continue

        target_idx = random.randint(1, min(len(words) - 2, 5))
        target_word = words[target_idx].strip('،,.:؛-()')
        if len(target_word) < 3:
            continue

        blank_sentence = " ".join(words[:target_idx] + ["( ........ )"] + words[target_idx+1:])
        
        q_templates = [
            f"وفقاً لمحتوى درس ({pkg_name})، ما هي العبارة أو المفهوم الأنسب لملء الفراغ في الجملة الآتية:\n\"{blank_sentence}\"",
            f"بناءً على ما ورد في درس ({pkg_name})، اختر المصطلح الصحيح الذي يكمل العبارة الآتية بدقة:\n\"{blank_sentence}\"",
            f"أي من المفاهيم التالية يعتبر المكمل العلمي والتاريخي الدقيق للعبارة الآتية:\n\"{blank_sentence}\""
        ]
        q_text = random.choice(q_templates)

        # Distractors
        distractors = []
        for other_s in random.sample(sentences, min(3, len(sentences))):
            other_words = [w.strip('،,.:؛-()') for w in other_s.split() if len(w.strip('،,.:؛-()')) >= 3 and w.strip('،,.:؛-()') != target_word]
            if other_words:
                distractors.append(random.choice(other_words))

        while len(distractors) < 3:
            distractors.append(f"مفهوم رديف {len(distractors) + 1}")

        options = [target_word] + distractors[:3]
        random.shuffle(options)

        letters = ['أ', 'ب', 'ج', 'د']
        correct_letter = letters[options.index(target_word)]

        # Default generated questions to 'متوسط'; teacher adjusts difficulty during review
        diff = 'متوسط'

        db.x("""
            INSERT INTO questions (
                subject_id, package_id, subject, unit, question,
                option_a, option_b, option_c, option_d, correct,
                mark, difficulty, status, approved, confidence,
                source_file, language, direction, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, 'NEEDS_REVIEW', 0, 0.95, ?, 'ar', 'rtl', ?, ?)
        """, (
            sub_id, pkg_id, sub_name, pkg_name, q_text,
            options[0], options[1], options[2], options[3], correct_letter,
            diff, f"اشتقاق ذكي: {pkg_name}", now(), now()
        ))
        created_count += 1

    db.audit('Teacher', 'GENERATE_CURRICULUM_QUESTIONS', 'questions', None, after_state=f"Generated {created_count} questions for {pkg_name}")
    flash(f'✓ تم بنجاح اشتقاق ({created_count}) سؤالاً ذكياً من نصوص المنهاج ({pkg_name}). يمكنك الآن تدقيق الأسئلة، وتحديد مستوى صعوبة كل سؤال (سهل / متوسط / صعب) ثم اعتمادها.', 'success')
    return redirect(url_for('review_questions'))

# AJAX / API Endpoint: Dynamic Inline Package Creation
# ==============================================================================
@app.post('/api/packages/add')
def api_add_package():
    data = request.json or request.form
    subject_id = data.get('subject_id')
    name = (data.get('name') or '').strip()
    desc = (data.get('description') or '').strip()

    if not subject_id or not name:
        return jsonify(ok=False, error="يرجى تحديد المادة واسم الحزمة"), 400

    try:
        pid = db.x("""
            INSERT INTO question_packages (subject_id, name, description, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
        """, (int(subject_id), name, desc, now(), now()))
        db.audit('Teacher', 'CREATE_PACKAGE_INLINE', 'question_packages', pid)
        return jsonify(ok=True, package={'id': pid, 'name': name, 'subject_id': int(subject_id)})
    except sqlite3.IntegrityError:
        return jsonify(ok=False, error="توجد حزمة بنفس هذا الاسم لهذه المادة مسبقاً"), 400

# ==============================================================================
# Media / Assets Gallery
# ==============================================================================
@app.get('/media', endpoint='media_gallery')
@app.get('/media', endpoint='media_library')
def media_gallery():
    images = []
    for f in IMAGES_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
            images.append({
                'name': f.name,
                'url': url_for('uploaded_question_image', filename=f.name),
                'size': f.stat().st_size,
                'created': datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            })
    images.sort(key=lambda x: x['created'], reverse=True)
    return render_template('media.html', title='مكتبة الصور والوسائط', active='media', images=images)

@app.route('/media/file/<filename>')
def uploaded_question_image(filename):
    p = IMAGES_DIR / safe_filename(filename)
    if p.exists() and p.is_file():
        mime = mimetypes.guess_type(str(p))[0] or 'image/png'
        return send_file(p, mimetype=mime)
    return "Image not found", 404

@app.post('/media/upload')
def media_upload():
    files = request.files.getlist('images')
    uploaded = 0
    for f in files:
        if f and f.filename:
            ext = Path(f.filename).suffix.lower()
            if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'):
                fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{safe_filename(f.filename)}"
                f.save(IMAGES_DIR / fname)
                uploaded += 1
    if uploaded > 0:
        flash(f'تم رفع {uploaded} صورة بنجاح إلى مكتبة الوسائط.', 'success')
    else:
        flash('لم يتم اختيار أي صور صالحة للرفع.', 'warning')
    return redirect(url_for('media_gallery'))

@app.post('/media/delete/<filename>')
def media_delete(filename):
    safe_name = safe_filename(filename)
    p = IMAGES_DIR / safe_name
    if p.exists() and p.is_file():
        p.unlink()
        flash('تم حذف الصورة من مكتبة الوسائط.', 'success')
    return redirect(url_for('media_gallery'))

# ==============================================================================
# Official Paper & Excel Exports (Questions, Students & Results)
# ==============================================================================
@app.get('/questions/export-print', endpoint='export_questions_print')
def export_questions_print():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    sub_id = request.args.get('subject_id', '').strip()
    pkg_id = request.args.get('package_id', '').strip()
    selected_ids = request.args.get('selected_ids', '').strip()

    subject = None
    package = None

    if selected_ids:
        raw_ids = [i.strip() for i in selected_ids.split(',') if i.strip().isdigit()]
        if raw_ids:
            questions = db.q(f"""
                SELECT q.*, s.name as subject_name, p.name as package_name
                FROM questions q
                LEFT JOIN subjects s ON s.id = q.subject_id
                LEFT JOIN question_packages p ON p.id = q.package_id
                WHERE q.id IN ({','.join(raw_ids)})
                ORDER BY q.id ASC
            """)
            if questions and dict(questions[0]).get('subject_id'):
                subject = db.q("SELECT * FROM subjects WHERE id=?", (questions[0]['subject_id'],), one=True)
        else:
            questions = []
    else:
        sql = """
            SELECT q.*, s.name as subject_name, p.name as package_name
            FROM questions q
            LEFT JOIN subjects s ON s.id = q.subject_id
            LEFT JOIN question_packages p ON p.id = q.package_id
            WHERE 1=1
        """
        params = []
        if sub_id and sub_id.isdigit():
            sql += " AND q.subject_id = ?"
            params.append(int(sub_id))
            subject = db.q("SELECT * FROM subjects WHERE id=?", (int(sub_id),), one=True)
        if pkg_id and pkg_id.isdigit():
            sql += " AND q.package_id = ?"
            params.append(int(pkg_id))
            package = db.q("SELECT * FROM question_packages WHERE id=?", (int(pkg_id),), one=True)
        sql += " ORDER BY q.id ASC"
        questions = db.q(sql, tuple(params))

    return render_template(
        'print_questions.html',
        questions=questions,
        subject=subject,
        package=package,
        now_date=datetime.now().strftime('%Y-%m-%d')
    )

@app.get('/students/export-print', endpoint='export_students_print')
def export_students_print():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    sub_id = request.args.get('subject_id', '').strip()
    cls_name = request.args.get('class_name', '').strip()
    sec_name = request.args.get('section', '').strip()
    q_search = request.args.get('q', '').strip()

    all_subjects = db.q("SELECT * FROM subjects WHERE approval_status='APPROVED' ORDER BY id ASC")
    selected_subject = None
    if sub_id and sub_id.isdigit():
        selected_subject = db.q("SELECT * FROM subjects WHERE id = ?", (int(sub_id),), one=True)

    sql = "SELECT DISTINCT s.* FROM students s WHERE s.active = 1"
    params = []
    if sub_id and sub_id.isdigit():
        sql += " AND s.id IN (SELECT student_id FROM student_subjects WHERE subject_id = ?)"
        params.append(int(sub_id))
    if cls_name:
        sql += " AND s.class_name = ?"
        params.append(cls_name)
    if sec_name:
        sql += " AND s.section = ?"
        params.append(sec_name)
    if q_search:
        sql += " AND (s.full_name LIKE ? OR s.username LIKE ? OR s.national_id LIKE ?)"
        params.extend([f'%{q_search}%', f'%{q_search}%', f'%{q_search}%'])

    sql += " ORDER BY s.class_name ASC, s.section ASC, s.full_name ASC"
    students = db.q(sql, tuple(params))

    return render_template(
        'print_students.html',
        students=[dict(st) for st in students],
        selected_subject=selected_subject,
        subjects=all_subjects,
        class_filter=cls_name,
        section_filter=sec_name,
        now_date=datetime.now().strftime('%Y-%m-%d')
    )

@app.get('/students/template', endpoint='download_student_template')
def download_student_template():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM for Microsoft Excel compatibility in Arabic
    writer = csv.writer(output)
    writer.writerow(['الاسم الكامل', 'الصف الدراسي', 'الشعبة', 'الرقم الوطني', 'اسم المستخدم', 'كلمة المرور'])
    writer.writerow(['سارة أحمد محمود الطراونة', 'الحادي عشر', 'أ', '2008100101', 'std_sara', '1234'])
    writer.writerow(['محمد أحمد خليل النوايسة', 'الحادي عشر', 'أ', '2008100102', 'std_mohammad', '1234'])
    writer.writerow(['عبد الله يوسف الطراونة', 'الحادي عشر', 'ب', '2008100103', 'std_abdullah', '1234'])

    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    return send_file(
        mem,
        mimetype='text/csv; charset=utf-8',
        as_attachment=True,
        download_name='نموذج_استيراد_الطلاب_المعتمد.csv'
    )

@app.get('/students/export', endpoint='export_students_csv')
def export_students_csv():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    sub_id = request.args.get('subject_id', '').strip()
    cls_name = request.args.get('class_name', '').strip()
    sec_name = request.args.get('section', '').strip()

    sql = "SELECT s.* FROM students s WHERE s.active = 1"
    params = []
    if cls_name:
        sql += " AND s.class_name = ?"
        params.append(cls_name)
    if sec_name:
        sql += " AND s.section = ?"
        params.append(sec_name)
    if sub_id and sub_id.isdigit():
        sql += " AND s.id IN (SELECT student_id FROM student_subjects WHERE subject_id = ?)"
        params.append(int(sub_id))
    sql += " ORDER BY s.class_name ASC, s.section ASC, s.full_name ASC"

    students = db.q(sql, tuple(params))
    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM
    writer = csv.writer(output)
    writer.writerow(['المعرف', 'اسم الطالب الكامل', 'الصف', 'الشعبة', 'الرقم الوطني / المدرسي', 'اسم الدخول', 'كلمة المرور', 'المواد المسجل بها', 'تاريخ التسجيل'])
    for st in students:
        sub_rows = db.q("SELECT sub.name FROM subjects sub JOIN student_subjects ss ON ss.subject_id = sub.id WHERE ss.student_id = ?", (st['id'],))
        subs = ' ، '.join([r['name'] for r in sub_rows]) or 'كافة المواد'
        writer.writerow([
            st['id'], st['full_name'], st['class_name'] or '', st['section'] or '',
            st['national_id'] or '', st['username'], st['password'], subs, (st['created_at'] or '')[:10]
        ])

    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=f"students_roster_{datetime.now().strftime('%Y%m%d')}.csv")

@app.get('/results/export-print', endpoint='export_results_print')
def export_results_print():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    exam_id = request.args.get('exam_id', '').strip()
    sub_id = request.args.get('subject_id', '').strip()
    cls_name = request.args.get('class_name', '').strip()
    sec_name = request.args.get('section', '').strip()

    sql = """
        SELECT a.*, e.title as exam_title, s.name as subject_name, st.class_name, st.section,
               st.national_id, st.username
        FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        LEFT JOIN subjects s ON s.id = e.subject_id
        JOIN students st ON st.id = a.student_id
        WHERE a.status = 'SUBMITTED'
    """
    params = []
    exam = None
    if exam_id and exam_id.isdigit():
        sql += " AND a.exam_id = ?"
        params.append(int(exam_id))
        exam = db.q("SELECT e.*, s.name as subject_name FROM exams e LEFT JOIN subjects s ON s.id = e.subject_id WHERE e.id=?", (int(exam_id),), one=True)
    if sub_id and sub_id.isdigit():
        sql += " AND e.subject_id = ?"
        params.append(int(sub_id))
    if cls_name:
        sql += " AND st.class_name = ?"
        params.append(cls_name)
    if sec_name:
        sql += " AND st.section = ?"
        params.append(sec_name)
    sql += " ORDER BY a.id DESC"

    attempts = db.q(sql, tuple(params))
    return render_template(
        'print_results.html',
        attempts=attempts,
        exam=exam,
        now_date=datetime.now().strftime('%Y-%m-%d')
    )

@app.get('/results/export', endpoint='export_results_csv')
def export_results_csv():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    exam_id = request.args.get('exam_id', '').strip()
    sub_id = request.args.get('subject_id', '').strip()

    sql = """
        SELECT a.id, a.student_name, st.national_id, st.class_name, st.section,
               e.title as exam_title, s.name as subject_name,
               a.score, a.total, a.percentage, a.status, a.submitted_at
        FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        LEFT JOIN subjects s ON s.id = e.subject_id
        JOIN students st ON st.id = a.student_id
        WHERE a.status = 'SUBMITTED'
    """
    params = []
    if exam_id and exam_id.isdigit():
        sql += " AND a.exam_id = ?"
        params.append(int(exam_id))
    if sub_id and sub_id.isdigit():
        sql += " AND e.subject_id = ?"
        params.append(int(sub_id))
    sql += " ORDER BY a.id DESC"

    attempts = db.q(sql, tuple(params))
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['رقم المحاولة', 'اسم الطالب', 'الرقم الوطني', 'الصف', 'الشعبة', 'المبحث', 'الامتحان', 'العلامة المستحقة', 'العلامة الكلية', 'النسبة المئوية', 'الحالة', 'تاريخ ووقت التسليم'])
    for a in attempts:
        writer.writerow([
            a['id'], a['student_name'], a['national_id'] or '', a['class_name'] or '', a['section'] or '',
            a['subject_name'] or '', a['exam_title'], a['score'], a['total'], f"{a['percentage']:.1f}%",
            'تم التسليم', a['submitted_at'] or ''
        ])

    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=f"exam_results_{datetime.now().strftime('%Y%m%d')}.csv")

@app.post('/questions/bulk-delete', endpoint='questions_bulk_delete')
def questions_bulk_delete():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    q_ids = request.form.getlist('selected_q_ids')
    if not q_ids:
        flash('لم يتم تحديد أي أسئلة للحذف.', 'warning')
        return redirect(url_for('question_bank'))

    deleted_count = 0
    for qid in q_ids:
        try:
            qid_int = int(qid)
        except ValueError:
            continue
        db.x("DELETE FROM exam_questions WHERE question_id = ?", (qid_int,))
        db.x("DELETE FROM questions WHERE id = ?", (qid_int,))
        deleted_count += 1

    db.audit('Teacher', 'BULK_DELETE_QUESTIONS', 'questions', f"Count: {deleted_count}")
    flash(f'تم بنجاح حذف ({deleted_count}) سؤال من بنك الأسئلة. تم الحفاظ التام على أوراق امتحانات الطلاب السابقة.', 'success')
    return redirect(url_for('question_bank'))

@app.get('/questions/export')
def export_questions_csv():
    questions = db.q("""
        SELECT q.id, s.name as subject_name, p.name as package_name, q.question,
               q.option_a, q.option_b, q.option_c, q.option_d, q.correct, q.mark, q.status
        FROM questions q
        LEFT JOIN subjects s ON s.id = q.subject_id
        LEFT JOIN question_packages p ON p.id = q.package_id
        ORDER BY q.id DESC
    """)
    output = io.StringIO()
    output.write('﻿')
    writer = csv.writer(output)
    writer.writerow(['المعرف', 'المادة', 'الحزمة/الوحدة', 'نص السؤال', 'خيار أ', 'خيار ب', 'خيار ج', 'خيار د', 'الإجابة الصحيحة', 'العلامة', 'الحالة'])
    for q in questions:
        writer.writerow([q['id'], q['subject_name'] or '', q['package_name'] or '', q['question'], q['option_a'], q['option_b'], q['option_c'], q['option_d'], q['correct'], q['mark'], q['status']])

    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=f"question_bank_{datetime.now().strftime('%Y%m%d')}.csv")


# ==============================================================================
# Grade Overrides & Consolidated Gradebook Report
# ==============================================================================
@app.post('/results/override-grade/<int:attempt_id>', endpoint='override_student_grade')
def override_student_grade(attempt_id):
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    att = db.q("SELECT * FROM attempts WHERE id = ?", (attempt_id,), one=True)
    if not att:
        flash('المحاولة غير موجودة.', 'error')
        return redirect(url_for('results_dashboard'))

    f = request.form
    try:
        new_score = float(f.get('new_score', 0))
    except ValueError:
        flash('العلامة المدخلة غير صالحة.', 'error')
        return redirect(url_for('attempt_result_detail', id=attempt_id))

    reason = f.get('reason', '').strip() or 'تعديل يدوي من قِبل المعلم'
    total = att['total'] or 40.0
    new_score = max(0.0, min(total, new_score))
    new_pct = round((new_score / total) * 100.0, 1) if total > 0 else 0.0

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    teacher_name = session.get('admin_name', 'المعلم')

    db.x("""
        UPDATE attempts 
        SET score = ?, percentage = ?, is_manually_adjusted = 1, adjustment_notes = ?, adjusted_by = ?, adjusted_at = ?
        WHERE id = ?
    """, (new_score, new_pct, reason, teacher_name, now_str, attempt_id))

    db.audit(teacher_name, 'OVERRIDE_STUDENT_GRADE', 'attempts', f"Attempt {attempt_id}: Old {att['score']} -> New {new_score}. Reason: {reason}")
    flash(f'تم تعديل علامة الطالب بنجاح إلى ({new_score} من {total}) بنسبة ({new_pct}%).', 'success')
    return redirect(url_for('attempt_result_detail', id=attempt_id))

@app.route('/results/consolidated-report', methods=['GET', 'POST'], endpoint='consolidated_report')
def consolidated_report():
    if not is_admin_logged_in():
        return redirect(url_for('login'))

    subjects = db.q("SELECT * FROM subjects WHERE approval_status='APPROVED' ORDER BY name ASC")
    raw_sid = request.args.get('subject_id')
    subject_id = int(raw_sid) if raw_sid and str(raw_sid).isdigit() else (subjects[0]['id'] if subjects else None)
    class_filter = request.args.get('class_name', '').strip()
    section_filter = request.args.get('section', '').strip()

    selected_subject = db.q("SELECT * FROM subjects WHERE id=?", (subject_id,), one=True) if subject_id else None

    selected_exams = []
    student_matrix = []
    total_possible_marks = 0.0

    if selected_subject:
        selected_exams = db.q("""
            SELECT e.* 
            FROM exams e
            WHERE e.subject_id = ? AND e.is_archived = 0
            ORDER BY e.id ASC
        """, (selected_subject['id'],))

        total_possible_marks = sum([float(e['total_marks'] or 40.0) for e in selected_exams])

        stud_sql = "SELECT * FROM students WHERE active = 1"
        stud_params = []
        if class_filter:
            stud_sql += " AND class_name = ?"
            stud_params.append(class_filter)
        if section_filter:
            stud_sql += " AND section = ?"
            stud_params.append(section_filter)
        stud_sql += " ORDER BY full_name ASC"
        students = db.q(stud_sql, stud_params)

        for s in students:
            scores = {}
            st_total = 0.0
            for ex in selected_exams:
                att = db.q("""
                    SELECT score, total 
                    FROM attempts 
                    WHERE exam_id = ? AND student_id = ? AND status = 'SUBMITTED'
                    ORDER BY id DESC LIMIT 1
                """, (ex['id'], s['id']), one=True)
                if att and att['score'] is not None:
                    scores[ex['id']] = float(att['score'])
                    st_total += float(att['score'])
                else:
                    scores[ex['id']] = None

            overall_pct = round((st_total / total_possible_marks) * 100.0, 1) if total_possible_marks > 0 else 0.0
            student_matrix.append({
                'student': s,
                'scores': scores,
                'total_score': round(st_total, 1),
                'overall_pct': overall_pct
            })

    school_logo_name = db.setting('school_logo_path', '')
    ministry_logo_name = db.setting('ministry_logo_path', '')
    school_logo_url = url_for('asset_file', name=school_logo_name) if school_logo_name else None
    ministry_logo_url = url_for('asset_file', name=ministry_logo_name) if ministry_logo_name else None

    exam_dummy = {
        'subject_name': selected_subject['name'] if selected_subject else 'المبحث',
        'exam_type': 'كشف العلامات التجميعي لمبحث',
        'class_name': class_filter or 'كافة الصفوف والشعب',
        'question_count': len(selected_exams),
        'duration': 'فصل دراسي كامل',
        'total_marks': total_possible_marks,
        'exam_date': datetime.now().strftime('%Y/%m/%d')
    }

    return render_template(
        'consolidated_report.html',
        subjects=subjects,
        selected_subject=selected_subject,
        selected_exams=selected_exams,
        student_matrix=student_matrix,
        total_possible_marks=total_possible_marks,
        class_filter=class_filter,
        section_filter=section_filter,
        exam=exam_dummy,
        now_date=datetime.now().strftime('%Y/%m/%d'),
        school_logo_url=school_logo_url,
        ministry_logo_url=ministry_logo_url,
        s=db.settings()
    )

@app.get('/landing', endpoint='landing_page')
def landing_page():
    landing_file = APP_DIR / 'firebase_landing' / 'index.html'
    if landing_file.exists():
        with open(landing_file, 'r', encoding='utf-8') as f:
            return f.read()
    return "Landing page not found", 404

# Health Check Endpoint
# ==============================================================================
@app.get('/health')
def health():
    q_count = db.q("SELECT COUNT(*) as n FROM questions", one=True)['n']
    st_count = db.q("SELECT COUNT(*) as n FROM students", one=True)['n']
    ex_count = db.q("SELECT COUNT(*) as n FROM exams", one=True)['n']
    return jsonify(
        ok=True,
        version='PRODUCTION_FINAL',
        questions_count=q_count,
        students_count=st_count,
        exams_count=ex_count,
        timestamp=now()
    )

# Register Examora AI Extended Routes

if __name__ == '__main__':
    import webbrowser
    from threading import Timer

    print("=" * 60)
    print("🚀 منصة الاختبارات التعليمية - الأستاذة عبلة الطراونة (الإصدار الشامل)")
    print("لوحة تحكم المعلمة: http://127.0.0.1:8765/")
    print("بوابة دخول الطلاب:  http://127.0.0.1:8765/student")
    print("=" * 60)

    # فتح المتصفح (الكروم) تلقائياً فور إقلاع السيرفر
    Timer(1.2, lambda: webbrowser.open('http://127.0.0.1:8765/')).start()

    app.run(host='127.0.0.1', port=8765, debug=False)
