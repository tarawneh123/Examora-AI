# -*- coding: utf-8 -*-
"""
OSR: Optical Structured Recognition Engine for Educational Exam Papers.
Enhanced High-Accuracy Version:
- Advanced Image Preprocessing (Upscaling, Contrast, Binarization, Deskew Padding)
- Multi-Pass Tesseract Strategy with Arabic & English Language Optimization
- Smart Question & Option Extraction handling (1), 1-, 1., س1, (أ), أ), أ-, ب (, ج, (د, etc.
- Robust False-Positive Guard (Prevents All, Could, About from becoming options)
- Normalization of common OCR misreadings
- Quality Control Tagging (NEEDS_REVIEW, confidence scoring, warnings)
"""
import os, re, shutil
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image, ImageOps, ImageEnhance
except ImportError:
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

FALSE_POSITIVE_WORDS = {
    'all', 'about', 'also', 'after', 'and', 'any', 'are', 'as', 'at', 'an', 'another', 'although', 'among',
    'between', 'because', 'both', 'before', 'by', 'but', 'below', 'behind',
    'could', 'can', 'choose', 'correct', 'circle', 'count', 'complete', 'contain', 'contains', 'compare',
    'during', 'does', 'did', 'do', 'down', 'different', 'describe', 'define', 'determine', 'due'
}

EXAM_HEADER_PHRASES = [
    r'المملكة\s+ال[اأأإ]ردنية\s+الهاشمية',
    r'وزارة\s+التربية\s+والتعليم',
    r'مديرية\s+التربية\s+والتعليم',
    r'امتحان\s+شهادة\s+الدراسة',
    r'الامتحان\s+النهائي',
    r'الامتحان\s+النصفي',
    r'بسم\s+الله\s+الرحمن\s+الرحيم',
    r'أجب\s+عن\s+(?:جميع\s+)?ال(?:أسئلة|فقرات)',
    r'ضع\s+دائرة\s+حول\s+رمز\s+الإجابة',
    r'اختر\s+رمز\s+الإجابة',
    r'ورقة\s+امتحان\s+رسمية',
    r'الصف\s*:\s*[^\n]+',
    r'المبحث\s*:\s*[^\n]+',
    r'اسم\s+الطالب\s*:\s*[^\n]+',
    r'مدة\s+الامتحان\s*:\s*[^\n]+',
    r'العلامة\s+الكلية\s*:\s*[^\n]+',
    r'اليوم\s+و\s*التاريخ\s*:\s*[^\n]+',
    r'ملحوظة\s*:\s*[^\n]+'
]

APP_DIR = Path(__file__).resolve().parent
PROJECT_TESSDATA = APP_DIR / 'tessdata'

def ensure_arabic_tessdata():
    """Ensures Arabic language pack (ara.traineddata) is available for Tesseract."""
    PROJECT_TESSDATA.mkdir(exist_ok=True)
    ara_file = PROJECT_TESSDATA / 'ara.traineddata'

    if ara_file.exists() and ara_file.stat().st_size > 100000:
        os.environ['TESSDATA_PREFIX'] = str(PROJECT_TESSDATA)
        return True

    std_dirs = [
        Path(r'C:\Program Files\Tesseract-OCR\tessdata'),
        Path(r'C:\Program Files (x86)\Tesseract-OCR\tessdata'),
        Path('/usr/share/tesseract-ocr/5/tessdata'),
        Path('/usr/share/tesseract-ocr/4.00/tessdata'),
        Path('/usr/share/tessdata')
    ]
    for d in std_dirs:
        if d.exists() and (d / 'ara.traineddata').exists() and (d / 'ara.traineddata').stat().st_size > 100000:
            os.environ['TESSDATA_PREFIX'] = str(d)
            return True

    # Try automatic download into project tessdata if internet is available
    try:
        import urllib.request
        url = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/ara.traineddata"
        urllib.request.urlretrieve(url, str(ara_file))
        if ara_file.exists() and ara_file.stat().st_size > 100000:
            # Also copy eng.traineddata if available so ara+eng works together
            for d in std_dirs:
                if (d / 'eng.traineddata').exists() and not (PROJECT_TESSDATA / 'eng.traineddata').exists():
                    try:
                        shutil.copyfile(str(d / 'eng.traineddata'), str(PROJECT_TESSDATA / 'eng.traineddata'))
                    except Exception:
                        pass
            os.environ['TESSDATA_PREFIX'] = str(PROJECT_TESSDATA)
            return True
    except Exception as e:
        print("Auto-download ara.traineddata notice:", e)

    return False

def configure_tesseract():
    if not pytesseract:
        return False
    candidates = [
        os.environ.get('TESSERACT_CMD', ''),
        shutil.which('tesseract') or '',
        '/usr/bin/tesseract',
        '/usr/local/bin/tesseract',
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
    ]
    for p in candidates:
        if p and Path(p).exists():
            pytesseract.pytesseract.tesseract_cmd = str(p)
            break

    ensure_arabic_tessdata()
    return True

def preprocess_image_advanced(img):
    if not Image:
        return img

    gray = ImageOps.grayscale(img)
    w, h = gray.size
    if w < 1600:
        scale = max(1.5, 1600.0 / w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        gray = gray.resize((new_w, new_h), Image.LANCZOS)

    autocontrasted = ImageOps.autocontrast(gray, cutoff=2)
    contrast_enhancer = ImageEnhance.Contrast(autocontrasted)
    contrasted = contrast_enhancer.enhance(1.9)

    sharp_enhancer = ImageEnhance.Sharpness(contrasted)
    sharpened = sharp_enhancer.enhance(1.8)

    bw = sharpened.point(lambda p: 255 if p > 165 else 0)
    padded = ImageOps.expand(bw, border=30, fill=255)
    return padded

def ocr_image_file(image_path, lang='ara'):
    if not pytesseract or not Image:
        raise RuntimeError("Pytesseract or Pillow is not available.")
    configure_tesseract()

    raw_img = Image.open(image_path)
    prep_img = preprocess_image_advanced(raw_img)

    try:
        available_langs = pytesseract.get_languages()
    except Exception:
        available_langs = ['eng']

    requested_parts = [p.strip() for p in lang.split('+') if p.strip()]
    valid_parts = [p for p in requested_parts if p in available_langs]

    warning_msg = None
    if 'ara' in requested_parts and 'ara' not in available_langs:
        warning_msg = "⚠️ تنبيه: ملف دعم اللغة العربية (ara.traineddata) غير متوفر في Tesseract. تم استخراج النصوص بالحروف الإنجليزية فقط. لدعم قراءة النصوص العربية بالكامل، يرجى وضع ملف ara.traineddata في مجلد tessdata داخل مجلد البرنامج."

    if valid_parts:
        ocr_lang = '+'.join(valid_parts)
    elif 'ara' in available_langs:
        ocr_lang = 'ara'
    elif 'eng' in available_langs:
        ocr_lang = 'eng'
    else:
        ocr_lang = available_langs[0] if available_langs else 'eng'

    configs = ['--oem 1 --psm 4', '--oem 1 --psm 6', '--oem 1 --psm 3']
    best_text = ""
    for cfg in configs:
        try:
            txt = pytesseract.image_to_string(prep_img, lang=ocr_lang, config=cfg)
            if len(txt.strip()) > len(best_text.strip()):
                best_text = txt
                if re.search(r'\d+[\.\-\)]', best_text):
                    break
        except Exception:
            continue

    if not best_text.strip():
        best_text = pytesseract.image_to_string(raw_img, lang=ocr_lang)

    return best_text, warning_msg

def clean_ocr_text(text):
    if not text:
        return ""
    text = text.replace('\r', '\n').replace('\ufeff', '').replace('ـ', '')
    text = re.sub(r'[ \t]+', ' ', text)

    # Normalize Arabic/Indic numerals (١-٩ -> 1-9)
    indic_to_arabic = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    text = text.translate(indic_to_arabic)

    # Normalize common OCR option misrecognitions
    text = re.sub(r'(?:^|[\s\t])(?:©|\(c)\s*[\)\.\-]\s*', ' C) ', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:^|[\s\t])(?:®|\(b)\s*[\)\.\-]\s*', ' B) ', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:^|[\s\t])(?:@|\(a)\s*[\)\.\-]\s*', ' A) ', text, flags=re.IGNORECASE)

    # Filter out top exam header boilerplate lines before questions start
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    cleaned_lines = []
    questions_started = False

    for line in lines:
        if not questions_started:
            # Check if this line starts a question
            if re.match(r'^(?:[\(\[\{]?\s*(?:س|سؤال|Question|Q)?\s*\d{1,3}\s*[\)\]\}\.\-\:\/ـ]?\s*[\)\]\}\.\-\:\/ـ]?)\s*.+$', line, re.IGNORECASE):
                questions_started = True
                cleaned_lines.append(line)
                continue

            # Check if it is a boilerplate header line
            is_header = False
            for hp in EXAM_HEADER_PHRASES:
                if re.search(hp, line, re.IGNORECASE):
                    is_header = True
                    break
            if not is_header:
                cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)

def detect_language(text):
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    english_chars = len(re.findall(r'[A-Za-z]', text))
    if english_chars > arabic_chars:
        return 'en', 'ltr'
    return 'ar', 'rtl'

def extract_options_smart(text_line, lang='ar'):
    """
    High-accuracy option extractor handling:
    - (أ), أ), أ-, أ., أ:, أ(, (أ, أ
    - (A), A), A-, A., A:, A(, (A, A
    - Multiple horizontal options on the same line (2 per line or 4 per line)
    - Robust false positive prevention (All, Could, About...)
    """
    if lang == 'en':
        pattern = re.compile(
            r'(?:^|[\s\t]+)(?:[\(\[\{]\s*([A-Da-d])\s*[\)\]\}]?|([A-Da-d])\s*[\)\]\}\.\:\-\/\(]|(?<=^)([A-Da-d])(?=\s+))'
        )
    else:
        pattern = re.compile(
            r'(?:^|[\s\t]+)(?:[\(\[\{]\s*([أ-دإاآ])\s*[\)\]\}]?|([أ-دإاآ])\s*[\)\]\}\.\:\-\/\(]|(?<=^)([أ-دإاآ])(?=\s+))'
        )

    spans = []
    for m in pattern.finditer(text_line):
        g1, g2, g3 = m.group(1), m.group(2), m.group(3)
        key = (g1 or g2 or g3 or '').strip()
        has_punct = bool(g1 or g2)
        if lang == 'en':
            key = key.upper()
        elif key in ('ا', 'إ', 'آ'):
            key = 'أ'
        spans.append((m.start(), m.end(), key, has_punct))

    if not spans:
        return {}

    options = {}
    for idx, (start, end, key, has_punct) in enumerate(spans):
        next_start = spans[idx + 1][0] if idx + 1 < len(spans) else len(text_line)
        val = text_line[end:next_start].strip()
        # Clean leading/trailing brackets & separators
        val = re.sub(r'^[\(\[\{\-\.\:\/\)]+\s*', '', val).strip()
        val = re.sub(r'[\(\[\{\)\]\}\-\.\:\/]+$', '', val).strip()

        if not has_punct:
            first_word = val.split()[0].lower() if val else ''
            if first_word in FALSE_POSITIVE_WORDS or (key.lower() + first_word) in FALSE_POSITIVE_WORDS:
                continue
        if val:
            options[key] = val

    return options

def parse_exam_questions(text, source_file="", default_lang='ar', page=1):
    """
    Core Optical Structured Recognition (OSR) parser.
    Supports single/multi-column questions, horizontal options, and mixed formatting.
    """
    text = clean_ocr_text(text)
    if not text:
        return []

    lines = [x.strip() for x in text.split('\n') if x.strip()]
    if not lines:
        return []

    detected_lang, direction = detect_language(text)
    lang = default_lang if default_lang in ('ar', 'en') else detected_lang

    # Robust Question Start Regex:
    # Matches: 1-, 1., 1), (1), (1 ), 1/, س1:, سؤال 1-, Question 1., Q1.
    q_start_pattern = re.compile(
        r'^(?:[\(\[\{]?\s*(?:س\s*|سؤال\s*|Question\s*|Q\s*)?(\d{1,3})\s*[\)\]\}\.\-\:\/ـ]?\s*[\)\]\}\.\-\:\/ـ]?)\s*(.+)$',
        re.IGNORECASE
    )

    starts = []
    for idx, line in enumerate(lines):
        m = q_start_pattern.match(line)
        if m:
            q_num = int(m.group(1))
            q_initial_text = m.group(2).strip()
            starts.append((idx, q_num, q_initial_text))

    if not starts:
        starts = [(0, 1, lines[0])]

    mapping = {'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd', 'أ': 'a', 'ب': 'b', 'ج': 'c', 'د': 'd'}

    extracted = []
    for i, (start_idx, q_num, initial_text) in enumerate(starts):
        end_idx = starts[i + 1][0] if i + 1 < len(starts) else len(lines)
        block_lines = lines[start_idx:end_idx]

        q_text_lines = [initial_text]
        options_dict = {}

        # Scan block lines for options
        for line in block_lines[1:]:
            line_opts = extract_options_smart(line, lang=lang)
            if line_opts:
                options_dict.update(line_opts)
            else:
                # If no options found yet, it is continuation of the question statement
                if not options_dict:
                    q_text_lines.append(line)

        question_text = ' '.join(q_text_lines).strip()

        # Check for answer key embedded in text (e.g. الإجابة: أ or الجواب: ب or Answer: C)
        correct_answer = 'A' if lang == 'en' else 'أ'
        ans_match = re.search(r'(?:الإجابة|الجواب|حل|Answer)\s*[\:\-\=]\s*([أ-دABCDa-d])', question_text, re.IGNORECASE)
        if ans_match:
            correct_answer = ans_match.group(1).upper()
            if lang == 'ar' and correct_answer in ('A', 'B', 'C', 'D'):
                inv_map = {'A': 'أ', 'B': 'ب', 'C': 'ج', 'D': 'د'}
                correct_answer = inv_map.get(correct_answer, 'أ')
            question_text = re.sub(r'(?:الإجابة|الجواب|حل|Answer)\s*[\:\-\=]\s*([أ-دABCDa-d])', '', question_text, flags=re.IGNORECASE).strip()

        opts = {'option_a': '', 'option_b': '', 'option_c': '', 'option_d': ''}
        warnings = []

        for raw_k, raw_v in options_dict.items():
            norm_k = mapping.get(raw_k.upper() if lang == 'en' else raw_k)
            if norm_k:
                opts[f'option_{norm_k}'] = raw_v

        missing = [k for k, v in opts.items() if not v]
        if missing:
            warnings.append(f"خيارات غير مكتملة: {', '.join(missing)}")
        if len(question_text) < 5:
            warnings.append("نص السؤال قصير جداً.")

        confidence = 1.0
        if missing:
            confidence -= (len(missing) * 0.15)
        if len(question_text) < 10:
            confidence -= 0.2
        confidence = max(0.1, min(1.0, round(confidence, 2)))

        extracted.append({
            'number': q_num,
            'question': question_text,
            'option_a': opts['option_a'],
            'option_b': opts['option_b'],
            'option_c': opts['option_c'],
            'option_d': opts['option_d'],
            'correct': correct_answer,
            'confidence': confidence,
            'warnings': '; '.join(warnings),
            'status': 'NEEDS_REVIEW',
            'approved': 0,
            'language': lang,
            'direction': 'ltr' if lang == 'en' else 'rtl',
            'page': page,
            'source_file': str(source_file)
        })

    return extracted
