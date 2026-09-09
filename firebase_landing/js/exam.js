
// ==========================================================================
// Examora AI - Custom Dark Glassmorphism Modal & Toast Engine
// Completely eliminates raw browser alert() and confirm() popups!
// ==========================================================================

function ensureExamoraModals() {
  if (!document.getElementById('examoraAlertModal')) {
    const alertModal = document.createElement('div');
    alertModal.id = 'examoraAlertModal';
    alertModal.style.cssText = 'display:none; position:fixed; inset:0; z-index:999999; background:rgba(7,11,20,0.85); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); align-items:center; justify-content:center; padding:16px; direction:rtl; text-align:right; font-family:Cairo,sans-serif;';
    alertModal.innerHTML = `
      <div style="background:rgba(15,23,42,0.96); border:1px solid rgba(56,189,248,0.35); box-shadow:0 25px 50px -12px rgba(0,0,0,0.85), 0 0 25px rgba(56,189,248,0.25); border-radius:18px; max-width:480px; width:100%; padding:28px 24px; position:relative; overflow:hidden;">
        <div style="position:absolute; top:0; left:0; right:0; height:3.5px; background:linear-gradient(90deg, #38bdf8, #818cf8);"></div>
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px;">
          <span id="examoraAlertIcon" style="font-size:1.8rem; width:44px; height:44px; border-radius:12px; background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.3); display:inline-flex; align-items:center; justify-content:center;">ℹ️</span>
          <h3 id="examoraAlertTitle" style="font-size:1.25rem; font-weight:900; color:#ffffff; margin:0;">تنبيه من المنظومة</h3>
        </div>
        <div id="examoraAlertMessage" style="font-size:0.98rem; color:#cbd5e1; line-height:1.75; margin-bottom:24px; white-space:pre-line;"></div>
        <div style="display:flex; justify-content:flex-end;">
          <button type="button" id="examoraAlertOkBtn" style="background:linear-gradient(135deg, #0284c7, #2563eb); color:#ffffff; border:none; padding:11px 28px; border-radius:10px; font-weight:800; font-size:0.95rem; cursor:pointer; font-family:inherit; box-shadow:0 4px 15px rgba(37,99,235,0.4); transition:all 0.2s;">حسناً، فهمت</button>
        </div>
      </div>
    `;
    document.body.appendChild(alertModal);
  }

  if (!document.getElementById('examoraConfirmModal')) {
    const confirmModal = document.createElement('div');
    confirmModal.id = 'examoraConfirmModal';
    confirmModal.style.cssText = 'display:none; position:fixed; inset:0; z-index:999999; background:rgba(7,11,20,0.85); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); align-items:center; justify-content:center; padding:16px; direction:rtl; text-align:right; font-family:Cairo,sans-serif;';
    confirmModal.innerHTML = `
      <div style="background:rgba(15,23,42,0.96); border:1px solid rgba(56,189,248,0.35); box-shadow:0 25px 50px -12px rgba(0,0,0,0.85), 0 0 25px rgba(56,189,248,0.25); border-radius:18px; max-width:480px; width:100%; padding:28px 24px; position:relative; overflow:hidden;">
        <div id="examoraConfirmTopLine" style="position:absolute; top:0; left:0; right:0; height:3.5px; background:linear-gradient(90deg, #10b981, #38bdf8);"></div>
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px;">
          <span id="examoraConfirmIcon" style="font-size:1.8rem; width:44px; height:44px; border-radius:12px; background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.3); display:inline-flex; align-items:center; justify-content:center;">✅</span>
          <h3 id="examoraConfirmTitle" style="font-size:1.25rem; font-weight:900; color:#ffffff; margin:0;">تأكيد تسليم ورقة الامتحان</h3>
        </div>
        <div id="examoraConfirmMessage" style="font-size:0.98rem; color:#cbd5e1; line-height:1.75; margin-bottom:24px; white-space:pre-line;"></div>
        <div style="display:flex; justify-content:flex-end; gap:12px;">
          <button type="button" id="examoraConfirmCancelBtn" style="background:rgba(30,41,59,0.8); color:#cbd5e1; border:1px solid rgba(255,255,255,0.15); padding:10px 22px; border-radius:10px; font-weight:700; font-size:0.95rem; cursor:pointer; font-family:inherit;">تراجع ومتابعة الحل</button>
          <button type="button" id="examoraConfirmActionBtn" style="background:linear-gradient(135deg, #16a34a, #15803d); color:#ffffff; border:none; padding:10px 26px; border-radius:10px; font-weight:800; font-size:0.95rem; cursor:pointer; font-family:inherit; box-shadow:0 4px 15px rgba(22,163,74,0.4);">نعم، تسليم الورقة الآن ✅</button>
        </div>
      </div>
    `;
    document.body.appendChild(confirmModal);
  }
}

function showExamoraAlert(message, title = 'تنبيه من المنظومة', icon = 'ℹ️', onOk = null) {
  ensureExamoraModals();
  const modal = document.getElementById('examoraAlertModal');
  document.getElementById('examoraAlertTitle').textContent = title;
  document.getElementById('examoraAlertMessage').textContent = message;
  document.getElementById('examoraAlertIcon').textContent = icon;

  const okBtn = document.getElementById('examoraAlertOkBtn');
  okBtn.onclick = function() {
    modal.style.display = 'none';
    okBtn.onclick = null;
    if (typeof onOk === 'function') onOk();
  };
  modal.style.display = 'flex';
}

function showExamoraConfirm(message, onConfirm, title = 'تأكيد العملية', confirmBtnText = 'نعم، تأكيد', isDanger = false) {
  ensureExamoraModals();
  const modal = document.getElementById('examoraConfirmModal');
  document.getElementById('examoraConfirmTitle').textContent = title;
  document.getElementById('examoraConfirmMessage').textContent = message;

  const iconBox = document.getElementById('examoraConfirmIcon');
  const actionBtn = document.getElementById('examoraConfirmActionBtn');
  const cancelBtn = document.getElementById('examoraConfirmCancelBtn');
  const topLine = document.getElementById('examoraConfirmTopLine');

  if (isDanger) {
    iconBox.textContent = '⚠️';
    iconBox.style.background = 'rgba(239,68,68,0.15)';
    iconBox.style.borderColor = 'rgba(239,68,68,0.3)';
    topLine.style.background = 'linear-gradient(90deg, #ef4444, #dc2626)';
    actionBtn.style.background = 'linear-gradient(135deg, #dc2626, #b91c1c)';
  } else {
    iconBox.textContent = '✅';
    iconBox.style.background = 'rgba(16,185,129,0.15)';
    iconBox.style.borderColor = 'rgba(16,185,129,0.3)';
    topLine.style.background = 'linear-gradient(90deg, #10b981, #38bdf8)';
    actionBtn.style.background = 'linear-gradient(135deg, #16a34a, #15803d)';
  }

  actionBtn.textContent = confirmBtnText;

  function cleanup() {
    modal.style.display = 'none';
    actionBtn.onclick = null;
    cancelBtn.onclick = null;
  }

  actionBtn.onclick = () => {
    cleanup();
    if (typeof onConfirm === 'function') onConfirm();
  };
  cancelBtn.onclick = cleanup;
  modal.style.display = 'flex';
}

// Override native window.alert and window.confirm
window.alert = function(msg) {
  showExamoraAlert(msg);
};
window.confirm = function(msg) {
  showExamoraConfirm(msg, () => {});
  return false;
};

// Examora AI - Online Exam Client Runner (Phase 5 Integrated)
// Securely communicates with the Online Cloud Backend API via HTTPS
let currentExamData = null;
let currentAttemptId = null;
let currentAttemptToken = null;
let timerInterval = null;
let serverDeadlineTimestamp = null;
let remainingSeconds = 0;
let totalQuestionsCount = 0;
let allExamQuestions = [];
const flaggedQuestions = new Set();
let currentBaseFontSize = 16;
let currentExamResultData = null;
let tabSwitchCount = 0;
const studentAnswers = {};

function getApiBaseUrl() {
  if (window.EXAMORA_CONFIG && window.EXAMORA_CONFIG.API_BASE_URL) {
    return window.EXAMORA_CONFIG.API_BASE_URL.replace(/\/$/, '');
  }
  return (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://127.0.0.1:8080'
    : '';
}

function extractPublishTokenFromUrl() {
  const urlParams = new URLSearchParams(window.location.search);
  let token = urlParams.get('token') || urlParams.get('code') || '';

  if (!token && window.location.hash) {
    const hash = window.location.hash;
    const match = hash.match(/#\/e\/([^/?#]+)/);
    if (match) {
      token = match[1];
    } else {
      token = hash.replace('#/e/', '').replace('#', '').split('?')[0].trim();
    }
  }

  if (!token && window.location.pathname) {
    const match = window.location.pathname.match(/\/e\/([^/?#]+)/);
    if (match) {
      token = match[1];
    }
  }

  return token;
}

document.addEventListener('DOMContentLoaded', () => {
  ensureExamoraModals();
  const codeParam = extractPublishTokenFromUrl();
  const codeInput = document.getElementById('stdExamCode');
  const nidInput = document.getElementById('stdNationalId');

  if (codeParam && codeInput) {
    codeInput.value = codeParam;
    codeInput.readOnly = true;
    codeInput.style.background = '#f1f5f9';
    codeInput.style.cursor = 'not-allowed';
    codeInput.style.color = '#1e3a8a';
    codeInput.style.fontWeight = '800';
    codeInput.title = 'تم قفل رمز الامتحان تلقائياً من رابط القاعة لمنع مسحه بالخطأ';
    
    const lockBadge = document.getElementById('examCodeLockBadge');
    if (lockBadge) lockBadge.style.display = 'inline-flex';

    if (nidInput) nidInput.focus();
  }

  const savedStudentId = localStorage.getItem('examora_student_id');
  if (savedStudentId && nidInput) {
    nidInput.value = savedStudentId;
  }

  // Smooth Auto-Resume: If student refreshed page while attempt is active
  const activeAttemptToken = sessionStorage.getItem('examora_attempt_token');
  const activePublishToken = sessionStorage.getItem('examora_publish_token') || codeParam;
  if (savedStudentId && activePublishToken && activeAttemptToken) {
    autoResumeStudentExam(savedStudentId, activePublishToken);
    return;
  }

  // Show login overlay
  const overlay = document.getElementById('loginOverlay');
  if (overlay) overlay.style.display = 'flex';
});

// Network status listeners
window.addEventListener('online', () => {
  const banner = document.getElementById('offlineAlertBanner');
  if (banner) banner.style.display = 'none';
  const statusTxt = document.getElementById('autosaveText');
  if (statusTxt) statusTxt.textContent = 'تمت استعادة الاتصال بالإنترنت ✅';
});

window.addEventListener('offline', () => {
  const banner = document.getElementById('offlineAlertBanner');
  if (banner) banner.style.display = 'flex';
  const statusTxt = document.getElementById('autosaveText');
  if (statusTxt) statusTxt.textContent = 'حفظ محلي مؤقت (غير متصل) ⚠️';
});

// Anti-Cheating: Window blur / tab switch detector
document.addEventListener('visibilitychange', () => {
  if (document.hidden && currentAttemptId) {
    tabSwitchCount++;
    const banner = document.getElementById('integrityWarningBanner');
    const countDisplay = document.getElementById('tabSwitchCountDisplay');
    if (banner && countDisplay) {
      countDisplay.textContent = tabSwitchCount;
      banner.style.display = 'flex';
    }
  }
});

async function autoResumeStudentExam(nationalId, examCode) {
  try {
    await performExamEntry(nationalId, examCode, true);
  } catch (err) {
    const overlay = document.getElementById('loginOverlay');
    if (overlay) overlay.style.display = 'flex';
  }
}

async function handleStudentExamEntry(e) {
  if (e) e.preventDefault();
  const alertBox = document.getElementById('loginAlert');
  alertBox.style.display = 'none';

  const nationalId = document.getElementById('stdNationalId').value.trim();
  const examCode = document.getElementById('stdExamCode').value.trim();

  if (!nationalId || !examCode) {
    alertBox.textContent = 'يرجى إدخال الرقم الوطني ورمز الامتحان.';
    alertBox.style.display = 'block';
    return;
  }

  const btn = document.getElementById('btnEnterExam');
  btn.disabled = true;
  btn.textContent = 'جارٍ التحقق من الهوية وبدء الاختبار...';

  try {
    await performExamEntry(nationalId, examCode, false);
  } catch (err) {
    console.error(err);
    alertBox.textContent = err.message || 'تعذر الاتصال بخادم الامتحان السحابي. يرجى التحقق من اتصال الإنترنت.';
    alertBox.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'بدء الامتحان الآن 🚀';
  }
}

async function performExamEntry(nationalId, examCode, isAutoResume) {
  const apiBase = getApiBaseUrl();
  const resp = await fetch(`${apiBase}/api/public/exam/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ national_id: nationalId, publish_token: examCode })
  });

  const data = await resp.json();
  if (!resp.ok || !data.ok) {
    throw new Error(data.error || 'تعذر الدخول إلى الامتحان. يرجى التأكد من البيانات أو مراجعة المعلم.');
  }

  // Persist session identifiers securely
  localStorage.setItem('examora_student_id', nationalId);
  sessionStorage.setItem('examora_attempt_id', data.attempt_id);
  sessionStorage.setItem('examora_attempt_token', data.attempt_token);
  sessionStorage.setItem('examora_publish_token', examCode);

  currentExamData = data.exam;
  currentAttemptId = data.attempt_id;
  currentAttemptToken = data.attempt_token;
  totalQuestionsCount = data.questions ? data.questions.length : 0;
  allExamQuestions = data.questions || [];
  remainingSeconds = data.remaining_seconds || (data.exam.duration * 60);
  serverDeadlineTimestamp = Date.now() + (remainingSeconds * 1000);

  // Initialize UI
  document.getElementById('loginOverlay').style.display = 'none';
  document.getElementById('examHeader').style.display = 'flex';
  document.getElementById('examMain').style.display = 'block';
  document.getElementById('examFooter').style.display = 'flex';

  document.getElementById('displayExamTitle').textContent = data.exam.title;
  document.getElementById('displayStudentName').textContent = `الطالب: ${data.student.name || data.student.full_name || ''} (${nationalId})`;

  // Populate Official Jordanian Header
  const stdName = data.student.name || data.student.full_name || nationalId;
  if (document.getElementById('hdrStudentName')) document.getElementById('hdrStudentName').textContent = stdName;
  if (document.getElementById('hdrSchoolName')) document.getElementById('hdrSchoolName').textContent = data.exam.school_name || 'مدارس ذرى المجد';
  if (document.getElementById('hdrDirectorate')) document.getElementById('hdrDirectorate').textContent = 'مديرية التربية والتعليم / ' + (data.exam.directorate_name || 'لواء المزار الجنوبي');
  if (document.getElementById('hdrGrade')) document.getElementById('hdrGrade').textContent = data.exam.grade || 'الثانوية العامة';
  if (document.getElementById('hdrExamTypeSubject')) document.getElementById('hdrExamTypeSubject').textContent = `${data.exam.exam_type || 'الامتحان الإلكتروني المعتمد'} لمبحث ${data.exam.subject}`;
  if (document.getElementById('hdrSemesterYear')) document.getElementById('hdrSemesterYear').textContent = `${data.exam.semester_name || 'الفصل الدراسي الأول'} ${data.exam.academic_year || '2025 - 2026م'}`;
  if (document.getElementById('hdrDate')) document.getElementById('hdrDate').textContent = new Date().toLocaleDateString('ar-JO');
  if (document.getElementById('hdrTotalMarks')) document.getElementById('hdrTotalMarks').textContent = data.exam.total_marks;
  if (document.getElementById('hdrDuration')) document.getElementById('hdrDuration').textContent = `${data.exam.duration} دقيقة`;
  if (document.getElementById('hdrExamCode')) document.getElementById('hdrExamCode').textContent = examCode;
  if (document.getElementById('hdrNote')) {
    const count = data.questions ? data.questions.length : 0;
    document.getElementById('hdrNote').textContent = `ملحوظة :- أجب وفقك الله عن جميع الفقرات الآتية ؛ علما بأن عددها ( ${count} ) فقرات والاعتماد لحظي إلكترونياً`;
  }

  // Restore previous answers if resumed
  if (data.answers) {
    Object.assign(studentAnswers, data.answers);
  }

  renderQuestionNavigator(data.questions);
  renderQuestions(data.questions);
  updateProgress();
  startTimer();
}

function renderQuestionNavigator(questions) {
  const navGrid = document.getElementById('questionNavGrid');
  if (!navGrid) return;
  navGrid.innerHTML = '';

  questions.forEach((q, idx) => {
    const pill = document.createElement('div');
    pill.className = 'nav-pill';
    pill.id = `navPill_${q.id}`;
    pill.textContent = idx + 1;
    pill.title = `الانتقال إلى السؤال رقم (${idx + 1})`;
    
    if (studentAnswers[q.id]) {
      pill.classList.add('answered');
    }

    pill.onclick = () => {
      const targetCard = document.getElementById(`qCard_${q.id}`);
      if (targetCard) {
        targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
        targetCard.classList.add('active');
        setTimeout(() => targetCard.classList.remove('active'), 1200);
      }
    };
    navGrid.appendChild(pill);
  });
}

function updateProgress() {
  const answeredCount = Object.keys(studentAnswers).length;
  const pct = totalQuestionsCount > 0 ? Math.round((answeredCount / totalQuestionsCount) * 100) : 0;

  const badge = document.getElementById('answeredCounterBadge');
  if (badge) {
    badge.textContent = `${answeredCount} من ${totalQuestionsCount} أسئلة مكتملة (${pct}%)`;
  }

  const fill = document.getElementById('progressBarFill');
  if (fill) {
    fill.style.width = `${pct}%`;
  }
}

function renderQuestions(questions) {
  const container = document.getElementById('questionsContainer');
  container.innerHTML = '';

  questions.forEach((q, idx) => {
    const card = document.createElement('div');
    card.className = 'question-card';
    card.id = `qCard_${q.id}`;

    const savedAns = studentAnswers[q.id] || '';

    // Render image/diagram if attached
    const imgHtml = (q.image || q.image_path) ? `
      <div class="q-image-box" style="margin: 14px 0; text-align: center;">
        <img src="${q.image || q.image_path}" alt="رسم توضيحي للسؤال" style="max-width: 100%; max-height: 380px; border-radius: 8px; border: 1px solid #cbd5e1; box-shadow: 0 2px 6px rgba(0,0,0,0.08); display: inline-block;">
      </div>` : '';

    // Dynamically render options: handles 2 options (True/False) or 4 options
    const optKeys = Object.keys(q.options || {});
    const isTwoOptions = optKeys.length === 2;
    const gridClass = isTwoOptions ? 'options-grid two-col' : 'options-grid';

    let optionsHtml = '';
    ['أ', 'ب', 'ج', 'د'].forEach(char => {
      if (q.options && q.options[char]) {
        optionsHtml += renderOption(q.id, char, q.options[char], savedAns);
      }
    });

    const isFlagged = flaggedQuestions.has(q.id);
    card.onmouseenter = () => { window.currentFocusedQid = q.id; };
    card.innerHTML = `
      <div class="question-header">
        <div style="display: flex; align-items: center; gap: 10px;">
          <span class="q-num-badge">السؤال (${idx + 1})</span>
          <span class="q-mark-badge">${q.mark || 1} علامات</span>
        </div>
        <button type="button" class="btn-flag-q ${isFlagged ? 'active' : ''}" id="btnFlag_${q.id}" onclick="toggleFlagQuestion(${q.id})">
          <span>🔖</span>
          <span>${isFlagged ? 'محدد للمراجعة' : 'مراجعة لاحقاً'}</span>
        </button>
      </div>
      <div class="question-text">${q.text}</div>
      ${imgHtml}
      <div class="${gridClass}">
        ${optionsHtml}
      </div>
    `;
    container.appendChild(card);
  });
}

function renderOption(qid, char, text, selectedVal) {
  if (!text) return '';
  const isChecked = selectedVal === char ? 'checked' : '';
  const isSelectedClass = selectedVal === char ? 'selected' : '';
  return `
    <label class="option-label ${isSelectedClass}" id="optLabel_${qid}_${char}">
      <input type="radio" name="q_${qid}" value="${char}" ${isChecked} onchange="handleAnswerSelect(${qid}, '${char}')">
      <span class="opt-char">${char}</span>
      <span>${text}</span>
    </label>
  `;
}

function handleAnswerSelect(qid, char) {
  studentAnswers[qid] = char;

  // Update UI selection style
  ['أ', 'ب', 'ج', 'د'].forEach(c => {
    const el = document.getElementById(`optLabel_${qid}_${c}`);
    if (el) {
      if (c === char) el.classList.add('selected');
      else el.classList.remove('selected');
    }
  });

  // Update question nav pill
  const pill = document.getElementById(`navPill_${qid}`);
  if (pill) pill.classList.add('answered');

  updateProgress();

  // Autosave to server
  autosaveAnswer(qid, char);
}

async function autosaveAnswer(qid, char) {
  const statusTxt = document.getElementById('autosaveText');
  const pulseDot = document.getElementById('syncPulseDot');
  const pulseTxt = document.getElementById('syncPulseText');
  if (statusTxt) statusTxt.textContent = 'جارٍ الحفظ في السحابة...';
  if (pulseDot) pulseDot.className = 'pulse-dot saving';
  if (pulseTxt) pulseTxt.textContent = 'جارٍ الحفظ...';

  try {
    const apiBase = getApiBaseUrl();
    const resp = await fetch(`${apiBase}/api/public/exam/autosave`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Attempt-Token': currentAttemptToken
      },
      body: JSON.stringify({
        attempt_id: currentAttemptId,
        question_id: qid,
        answer: char
      })
    });

    const res = await resp.json();
    if (resp.ok && res.ok) {
      if (statusTxt) statusTxt.textContent = 'تم حفظ جميع الإجابات سحابياً بنجاح ✅';
      if (pulseDot) pulseDot.className = 'pulse-dot';
      if (pulseTxt) pulseTxt.textContent = 'متصل سحابياً ✓';
    } else {
      if (statusTxt) statusTxt.textContent = 'حفظ محلي مؤقت في المتصفح ⚠️';
      if (pulseDot) pulseDot.className = 'pulse-dot offline';
      if (pulseTxt) pulseTxt.textContent = 'حفظ محلي (أوفلاين)';
    }
  } catch (e) {
    statusTxt.textContent = 'حفظ محلي مؤقت في المتصفح ⚠️';
  }
}

function startTimer() {
  updateTimerDisplay();
  timerInterval = setInterval(() => {
    // Keep timer strictly synchronized with server deadline
    if (serverDeadlineTimestamp) {
      remainingSeconds = Math.max(0, Math.round((serverDeadlineTimestamp - Date.now()) / 1000));
    } else {
      remainingSeconds--;
    }

    if (remainingSeconds <= 0) {
      clearInterval(timerInterval);
      handleTimeExpired();
    } else {
      updateTimerDisplay();
    }
  }, 1000);
}

function updateTimerDisplay() {
  const mins = Math.floor(remainingSeconds / 60);
  const secs = remainingSeconds % 60;
  const disp = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  const el = document.getElementById('timerDisplay');
  if (el) el.textContent = disp;

  const box = document.getElementById('timerBox');
  if (box && remainingSeconds < 300) {
    box.classList.add('urgent');
  }
}

function handleTimeExpired() {
  showExamoraAlert(
    'انتهى الوقت المخصص للامتحان رسمياً!\n\nسيتم الآن تسليم إجاباتك الحالية تلقائياً، واحتساب أي أسئلة متبقية دون إجابة كإجابات غير صحيحة.',
    'انتهاء وقت الامتحان',
    '⏱️',
    () => submitExamFinal()
  );
}

function openSubmitModal() {
  const answeredCount = Object.keys(studentAnswers).length;
  const remainingCount = totalQuestionsCount - answeredCount;

  // Strict Policy: Manual submission is strictly blocked unless ALL questions are answered!
  if (remainingCount > 0) {
    showExamoraAlert(
      `لا يمكن تسليم الامتحان لوجود (${remainingCount}) أسئلة لم تقم بالإجابة عليها بعد!\n\nيجب الإجابة عن جميع الأسئلة لتتمكن من تسليم ورقة الامتحان يدوياً.`,
      'تنبيه استكمال الإجابات',
      '⚠️',
      () => {
        // Automatically scroll to the first missing question
        if (Array.isArray(allExamQuestions)) {
          const firstUnanswered = allExamQuestions.find(q => !studentAnswers[q.id]);
          if (firstUnanswered) {
            const card = document.getElementById(`qCard_${firstUnanswered.id}`);
            if (card) {
              card.scrollIntoView({ behavior: 'smooth', block: 'center' });
              card.classList.add('active');
              setTimeout(() => card.classList.remove('active'), 2000);
            }
          }
        }
      }
    );
    return;
  }

  // All questions are answered: proceed with custom glass confirmation modal
  showExamoraConfirm(
    `لقد قمت بالإجابة عن جميع الأسئلة بالكامل (${totalQuestionsCount} من ${totalQuestionsCount}).\n\nهل أنت متأكد من رغبتك في إنهاء وتسليم ورقة الامتحان الآن؟ لن تتمكن من تعديل إجاباتك بعد التسليم.`,
    () => submitExamFinal(),
    'تأكيد تسليم ورقة الامتحان',
    'نعم، إنهاء وتسليم الامتحان الآن ✅',
    false
  );
}

async function submitExamFinal() {
  clearInterval(timerInterval);
  const apiBase = getApiBaseUrl();

  try {
    const resp = await fetch(`${apiBase}/api/public/exam/submit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Attempt-Token': currentAttemptToken
      },
      body: JSON.stringify({
        attempt_id: currentAttemptId,
        answers: studentAnswers,
        tab_switches: tabSwitchCount
      })
    });
    const res = await resp.json();
    if (resp.ok && res.ok) {
      // Clean attempt session storage
      sessionStorage.removeItem('examora_attempt_token');
      sessionStorage.removeItem('examora_attempt_id');
      sessionStorage.removeItem('examora_publish_token');
      showResultScreen(res);
    } else {
      showExamoraAlert(res.error || 'تعذر اعتماد التسليم. يرجى إبلاغ المعلم.', 'تنبيه التسليم', '⚠️');
    }
  } catch (e) {
    showExamoraAlert('حدث خطأ أثناء التسليم. يرجى التحقق من اتصال الإنترنت أو إبلاغ المعلم.', 'خطأ في الاتصال', '⚠️');
  }
}

function showResultScreen(res) {
  currentExamResultData = res;
  document.getElementById('examHeader').style.display = 'none';
  document.getElementById('examMain').style.display = 'none';
  document.getElementById('examFooter').style.display = 'none';

  const screen = document.getElementById('resultScreen');
  screen.style.display = 'block';

  // Populate score elements
  document.getElementById('resScore').textContent = `${res.score} / ${res.total}`;
  document.getElementById('resTier').textContent = res.tier || 'ممتاز';
  document.getElementById('resFeedbackBox').textContent = res.feedback_message || 'أحسنت صنعاً! تم اعتماد نتيجتك بنجاح.';

  // 3-Minute Result Countdown Logic (180 seconds delay to allow syncing and prevent student anxiety)
  const submitKey = `examora_subtime_${currentAttemptId || 'att'}`;
  let submitTimestamp = localStorage.getItem(submitKey);
  if (!submitTimestamp) {
    submitTimestamp = Date.now();
    localStorage.setItem(submitKey, submitTimestamp);
  } else {
    submitTimestamp = parseInt(submitTimestamp, 10);
  }

  const elapsedSecs = Math.floor((Date.now() - submitTimestamp) / 1000);
  const remainingWait = Math.max(0, 180 - elapsedSecs);

  if (remainingWait <= 0) {
    revealFinalScoreBox(res);
  } else {
    startResultCountdown(remainingWait, res);
  }
}

function startResultCountdown(waitSecs, res) {
  const waitBox = document.getElementById('resultWaitBox');
  const timerDisp = document.getElementById('resultWaitTimer');
  const revealBox = document.getElementById('scoreRevealBox');
  if (waitBox) waitBox.style.display = 'block';
  if (revealBox) revealBox.style.display = 'none';

  function updateDisp(s) {
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    if (timerDisp) timerDisp.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  updateDisp(waitSecs);
  const intv = setInterval(() => {
    waitSecs--;
    updateDisp(waitSecs);
    if (waitSecs <= 0) {
      clearInterval(intv);
      revealFinalScoreBox(res);
    }
  }, 1000);
}

function revealFinalScoreBox(res) {
  const waitBox = document.getElementById('resultWaitBox');
  const revealBox = document.getElementById('scoreRevealBox');
  if (waitBox) waitBox.style.display = 'none';
  if (revealBox) revealBox.style.display = 'block';

  // Show Certificate Button for High Achievers (>= 80%)
  const certBtn = document.getElementById('btnCertModal');
  if (certBtn && res.percentage >= 80) {
    certBtn.style.display = 'inline-flex';
  }

  // Trigger celebration confetti for passing score (>= 60%)
  if (res.percentage >= 60) {
    triggerConfetti();
  }
}


// ==========================================================================
// Flag for Review Logic
// ==========================================================================
function toggleFlagQuestion(qid) {
  const pill = document.getElementById(`navPill_${qid}`);
  const btn = document.getElementById(`btnFlag_${qid}`);
  
  if (flaggedQuestions.has(qid)) {
    flaggedQuestions.delete(qid);
    if (btn) {
      btn.classList.remove('active');
      btn.innerHTML = '<span>🔖</span> <span>مراجعة لاحقاً</span>';
    }
    if (pill) pill.classList.remove('flagged');
  } else {
    flaggedQuestions.add(qid);
    if (btn) {
      btn.classList.add('active');
      btn.innerHTML = '<span>🔖</span> <span>محدد للمراجعة</span>';
    }
    if (pill) pill.classList.add('flagged');
  }
}

// ==========================================================================
// Font Resizer Control
// ==========================================================================
function adjustExamFontSize(delta) {
  currentBaseFontSize = Math.min(22, Math.max(13, currentBaseFontSize + delta));
  const container = document.getElementById('questionsContainer');
  if (container) {
    container.style.fontSize = currentBaseFontSize + 'px';
  }
}

// ==========================================================================
// Dark / Light Theme Toggle
// ==========================================================================
function toggleExamTheme() {
  document.body.classList.toggle('theme-light');
  const isLight = document.body.classList.contains('theme-light');
  localStorage.setItem('examora_exam_theme', isLight ? 'light' : 'dark');
}

// Restore saved theme on load
document.addEventListener('DOMContentLoaded', () => {
  if (localStorage.getItem('examora_exam_theme') === 'light') {
    document.body.classList.add('theme-light');
  }
});

// ==========================================================================
// Keyboard Shortcuts (1-4 or أ-د to select option)
// ==========================================================================
document.addEventListener('keydown', (e) => {
  if (e.target && ['input', 'textarea', 'select'].includes(e.target.tagName.toLowerCase())) return;
  const keyMap = {'1': 'أ', '2': 'ب', '3': 'ج', '4': 'د', 'أ': 'أ', 'ب': 'ب', 'ج': 'ج', 'د': 'د'};
  const optChar = keyMap[e.key];
  if (optChar && window.currentFocusedQid) {
    handleAnswerSelect(window.currentFocusedQid, optChar);
  }
});

// ==========================================================================
// Confetti Animation Engine (Pure Vanilla Canvas)
// ==========================================================================
function triggerConfetti() {
  const canvas = document.getElementById('confettiCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;

  const pieces = [];
  const colors = ['#38bdf8', '#818cf8', '#f59e0b', '#10b981', '#ec4899'];
  for (let i = 0; i < 100; i++) {
    pieces.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height - canvas.height,
      size: Math.random() * 8 + 4,
      color: colors[Math.floor(Math.random() * colors.length)],
      speed: Math.random() * 4 + 2,
      rotation: Math.random() * 360
    });
  }

  let animationFrame;
  let startTime = Date.now();

  function render() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    pieces.forEach(p => {
      p.y += p.speed;
      p.rotation += 2;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rotation * Math.PI / 180);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
      ctx.restore();
    });

    if (Date.now() - startTime < 3500) {
      animationFrame = requestAnimationFrame(render);
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  }
  render();
}

// ==========================================================================
// Digital Certificate Modal Controls
// ==========================================================================
function openDigitalCertificate() {
  const modal = document.getElementById('certificateModal');
  if (!modal || !currentExamResultData) return;

  const res = currentExamResultData;
  const stdName = (currentExamData && (currentExamData.student_name || currentExamData.title)) || localStorage.getItem('examora_student_id') || 'الطالب المتميز';
  const schoolName = (document.getElementById('hdrSchoolName') ? document.getElementById('hdrSchoolName').textContent.trim() : 'مدارس ذرى المجد');
  const examTitle = (document.getElementById('displayExamTitle') ? document.getElementById('displayExamTitle').textContent.trim() : 'الامتحان الإلكتروني');

  document.getElementById('certStudentName').textContent = stdName;
  document.getElementById('certSchoolName').textContent = schoolName;
  document.getElementById('certExamTitle').textContent = examTitle;
  document.getElementById('certScore').textContent = `${res.score} / ${res.total}`;
  document.getElementById('certPercentage').textContent = `${res.percentage}%`;
  document.getElementById('certTier').textContent = res.tier || 'ممتاز';
  document.getElementById('certDate').textContent = new Date().toLocaleDateString('ar-JO');
  document.getElementById('certTokenCode').textContent = (sessionStorage.getItem('examora_publish_token') || 'EXAMORA-CERT-2026').slice(0, 16);

  modal.style.display = 'flex';
}

function closeDigitalCertificate() {
  const modal = document.getElementById('certificateModal');
  if (modal) modal.style.display = 'none';
}
