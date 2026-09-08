// Examora AI - Online Exam Client Runner (Phase 5 Integrated)
// Securely communicates with the Online Cloud Backend API via HTTPS
let currentExamData = null;
let currentAttemptId = null;
let currentAttemptToken = null;
let timerInterval = null;
let serverDeadlineTimestamp = null;
let remainingSeconds = 0;
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
  return token;
}

document.addEventListener('DOMContentLoaded', () => {
  const codeParam = extractPublishTokenFromUrl();
  const codeInput = document.getElementById('stdExamCode');
  const nidInput = document.getElementById('stdNationalId');

  if (codeParam && codeInput) {
    codeInput.value = codeParam;
    if (nidInput) nidInput.focus();
  }

  const savedStudentId = localStorage.getItem('examora_student_id');
  if (savedStudentId && nidInput) {
    nidInput.value = savedStudentId;
  }

  // Show login overlay
  const overlay = document.getElementById('loginOverlay');
  if (overlay) overlay.style.display = 'flex';
});

async function handleStudentExamEntry(e) {
  e.preventDefault();
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
    const apiBase = getApiBaseUrl();
    const resp = await fetch(`${apiBase}/api/public/exam/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ national_id: nationalId, publish_token: examCode })
    });

    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      alertBox.textContent = data.error || 'تعذر الدخول إلى الامتحان. يرجى التأكد من البيانات أو مراجعة المعلم.';
      alertBox.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'بدء الامتحان الآن 🚀';
      return;
    }

    // Persist session identifiers securely
    localStorage.setItem('examora_student_id', nationalId);
    sessionStorage.setItem('examora_attempt_id', data.attempt_id);
    sessionStorage.setItem('examora_attempt_token', data.attempt_token);
    sessionStorage.setItem('examora_publish_token', examCode);

    currentExamData = data.exam;
    currentAttemptId = data.attempt_id;
    currentAttemptToken = data.attempt_token;
    remainingSeconds = data.remaining_seconds || (data.exam.duration * 60);
    serverDeadlineTimestamp = Date.now() + (remainingSeconds * 1000);

    // Initialize UI
    document.getElementById('loginOverlay').style.display = 'none';
    document.getElementById('examHeader').style.display = 'flex';
    document.getElementById('examMain').style.display = 'block';
    document.getElementById('examFooter').style.display = 'flex';

    document.getElementById('displayExamTitle').textContent = data.exam.title;
    document.getElementById('displayStudentName').textContent = `الطالب: ${data.student.name || data.student.full_name || ''} (${nationalId})`;

    // Restore previous answers if resumed
    if (data.answers) {
      Object.assign(studentAnswers, data.answers);
    }

    renderQuestions(data.questions);
    startTimer();

  } catch (err) {
    console.error(err);
    alertBox.textContent = 'تعذر الاتصال بخادم الامتحان السحابي. يرجى التحقق من اتصال الإنترنت.';
    alertBox.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'بدء الامتحان الآن 🚀';
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

    card.innerHTML = `
      <div class=\"question-header\">
        <span class=\"q-num-badge\">السؤال (${idx + 1})</span>
        <span class=\"q-mark-badge\">${q.mark || 1} علامات</span>
      </div>
      <div class=\"question-text\">${q.text}</div>
      <div class=\"options-grid\">
        ${renderOption(q.id, 'أ', q.options['أ'], savedAns)}
        ${renderOption(q.id, 'ب', q.options['ب'], savedAns)}
        ${renderOption(q.id, 'ج', q.options['ج'], savedAns)}
        ${renderOption(q.id, 'د', q.options['د'], savedAns)}
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
    <label class=\"option-label ${isSelectedClass}\" id=\"optLabel_${qid}_${char}\">
      <input type=\"radio\" name=\"q_${qid}\" value=\"${char}\" ${isChecked} onchange=\"handleAnswerSelect(${qid}, '${char}')\">
      <span class=\"opt-char\">${char}</span>\n      <span>${text}</span>
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

  // Autosave to server
  autosaveAnswer(qid, char);
}

async function autosaveAnswer(qid, char) {
  const statusTxt = document.getElementById('autosaveText');
  statusTxt.textContent = 'جارٍ الحفظ في السحابة...';

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
      statusTxt.textContent = 'تم حفظ جميع الإجابات سحابياً بنجاح ✅';
    } else {
      statusTxt.textContent = 'حفظ محلي مؤقت في المتصفح ⚠️';
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
  alert('انتهى الوقت المخصص للامتحان رسمياً. سيتم تسليم إجاباتك المحفوظة الآن.');
  submitExamFinal();
}

function openSubmitModal() {
  const total = Object.keys(studentAnswers).length;
  const confirmMsg = `هل أنت متأكد من رغبتك في تسليم الامتحان الآن؟\nلقد قمت بالإجابة عن ${total} سؤالاً.`;
  if (confirm(confirmMsg)) {
    submitExamFinal();
  }
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
        answers: studentAnswers
      })
    });
    const res = await resp.json();
    if (resp.ok && res.ok) {
      // Clean attempt session storage
      sessionStorage.removeItem('examora_attempt_token');
      sessionStorage.removeItem('examora_attempt_id');
      showResultScreen(res);
    } else {
      alert(res.error || 'تعذر اعتماد التسليم. يرجى إبلاغ المعلم.');
    }
  } catch (e) {
    alert('حدث خطأ أثناء التسليم. يرجى التحقق من اتصال الإنترنت أو إبلاغ المعلم.');
  }
}

function showResultScreen(res) {
  document.getElementById('examHeader').style.display = 'none';
  document.getElementById('examMain').style.display = 'none';
  document.getElementById('examFooter').style.display = 'none';

  const screen = document.getElementById('resultScreen');
  screen.style.display = 'block';

  // Strictly display the server-evaluated score without any client computation
  document.getElementById('resScore').textContent = `${res.score} / ${res.total}`;
  document.getElementById('resTier').textContent = res.tier || 'ممتاز';
  document.getElementById('resFeedbackBox').textContent = res.feedback_message || 'أحسنت صنعاً! تم اعتماد نتيجتك بنجاح.';
}
