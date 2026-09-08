/**
 * Abla Exam AI - Main Frontend Utilities & State Handlers
 * Clean, lightweight, professional UI logic without external dependencies.
 */

document.addEventListener('DOMContentLoaded', () => {
  initMobileNav();
  initModals();
  initExamCreatorCalculations();
  initSelectAllCheckboxes();
  initColorPickers();
  initStudentExamAutosave();
  initProgressiveFiltering();
  initToastAndAlertSystem();
});

// 1. Mobile Sidebar Navigation Toggle
function initMobileNav() {
  const hamburger = document.getElementById('hamburgerBtn');
  const sidebar = document.getElementById('appSidebar');
  if (hamburger && sidebar) {
    hamburger.addEventListener('click', (e) => {
      e.stopPropagation();
      sidebar.classList.toggle('open');
    });

    document.addEventListener('click', (e) => {
      if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && !hamburger.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });
  }
}

// 2. Modal Window Controls
function initModals() {
  document.querySelectorAll('[data-modal-open]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const modalId = btn.getAttribute('data-modal-open');
      const modal = document.getElementById(modalId);
      if (modal) modal.style.display = 'flex';
    });
  });

  document.querySelectorAll('[data-modal-close]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const modal = btn.closest('.modal-overlay');
      if (modal) modal.style.display = 'none';
    });
  });

  window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
      e.target.style.display = 'none';
    }
  });
}

// 3. Exam Creator Question Selection & Real-Time Counter
function initExamCreatorCalculations() {
  const questionCheckboxes = document.querySelectorAll('.exam-question-checkbox');
  const counterElement = document.getElementById('selectedQuestionCountBadge');
  const hiddenCountInput = document.getElementById('examQuestionCountInput');

  if (questionCheckboxes.length > 0 && counterElement) {
    function updateCount() {
      const selected = document.querySelectorAll('.exam-question-checkbox:checked').length;
      counterElement.textContent = selected;
      if (hiddenCountInput) hiddenCountInput.value = selected;
    }

    questionCheckboxes.forEach(cb => {
      cb.addEventListener('change', updateCount);
    });
    updateCount();
  }
}

// 4. "Select All" with Indeterminate Checkbox Logic
function initSelectAllCheckboxes() {
  const masterCheckboxes = document.querySelectorAll('[data-select-all]');
  masterCheckboxes.forEach(master => {
    const targetGroup = master.getAttribute('data-select-all');
    const childCheckboxes = document.querySelectorAll('[data-group="' + targetGroup + '"]');

    let isBatchUpdating = false;

    function getVisibleChildren() {
      return Array.from(childCheckboxes).filter(cb => {
        const row = cb.closest('tr');
        return !row || row.style.display !== 'none';
      });
    }

    function updateCounter() {
      const counterElement = document.getElementById('selectedQuestionCountBadge');
      const hiddenCountInput = document.getElementById('examQuestionCountInput');
      const checkedTotal = document.querySelectorAll('.exam-question-checkbox:checked').length;
      if (counterElement) counterElement.textContent = checkedTotal;
      if (hiddenCountInput) hiddenCountInput.value = checkedTotal;
    }

    master.addEventListener('change', () => {
      isBatchUpdating = true;
      const isChecked = master.checked;
      const visible = getVisibleChildren();
      visible.forEach(cb => {
        cb.checked = isChecked;
      });
      master.indeterminate = false;
      isBatchUpdating = false;
      updateCounter();
    });

    childCheckboxes.forEach(cb => {
      cb.addEventListener('change', () => {
        if (isBatchUpdating) return;
        const visible = getVisibleChildren();
        const checkedCount = visible.filter(c => c.checked).length;
        if (checkedCount === 0) {
          master.checked = false;
          master.indeterminate = false;
        } else if (checkedCount === visible.length && visible.length > 0) {
          master.checked = true;
          master.indeterminate = false;
        } else {
          master.checked = false;
          master.indeterminate = true;
        }
        updateCounter();
      });
    });
  });
}

function initColorPickers() {
  const primaryPicker = document.getElementById('primaryColorInput');
  const secondaryPicker = document.getElementById('secondaryColorInput');

  if (primaryPicker) {
    primaryPicker.addEventListener('input', (e) => {
      document.documentElement.style.setProperty('--primary', e.target.value);
    });
  }
  if (secondaryPicker) {
    secondaryPicker.addEventListener('input', (e) => {
      document.documentElement.style.setProperty('--secondary', e.target.value);
    });
  }
}

// 6. Progressive Disclosure: Dynamic Subject & Package Dropdowns (SILENT ON LOAD - NO INFINITE LOOP)
function initProgressiveFiltering() {
  const subjectSelect = document.getElementById('subjectFilterSelect');
  const packageSelect = document.getElementById('packageFilterSelect');

  if (subjectSelect && packageSelect) {
    function filterPackages() {
      const selectedSubjectId = subjectSelect.value;
      const options = packageSelect.querySelectorAll('option');

      options.forEach(opt => {
        if (!opt.value) {
          opt.style.display = 'block'; // "All" or "General" option
          return;
        }
        const optSubjectId = opt.getAttribute('data-subject-id');
        if (!selectedSubjectId || optSubjectId === selectedSubjectId) {
          opt.style.display = 'block';
        } else {
          opt.style.display = 'none';
        }
      });

      // Reset package selection if current selection is now hidden
      const currentSelected = packageSelect.selectedOptions[0];
      if (currentSelected && currentSelected.style.display === 'none') {
        packageSelect.value = '';
      }
    }

    subjectSelect.addEventListener('change', () => {
      filterPackages();
    });

    // Execute filterPackages SILENTLY on load without dispatching synthetic change events!
    filterPackages();
  }
}

// 7. Student Exam Debounced Autosave Engine
function initStudentExamAutosave() {
  const examForm = document.getElementById('studentExamForm');
  if (!examForm) return;

  const attemptId = examForm.getAttribute('data-attempt-id');
  const autosaveIndicator = document.getElementById('autosaveIndicator');
  const answeredCountBadge = document.getElementById('answeredCountBadge');
  const totalQuestions = document.querySelectorAll('.question-card').length;

  let debounceTimer = null;

  function updateAnsweredCount() {
    const answeredCards = new Set();
    document.querySelectorAll('.opt-input:checked').forEach(radio => {
      const qCard = radio.closest('.question-card');
      if (qCard) answeredCards.add(qCard);
    });
    if (answeredCountBadge) {
      answeredCountBadge.textContent = `${answeredCards.size} / ${totalQuestions}`;
    }
  }

  function setAutosaveState(state, text) {
    if (!autosaveIndicator) return;
    autosaveIndicator.className = `autosave-indicator autosave-${state}`;
    autosaveIndicator.textContent = text;
  }

  function performAutosave(questionId, selectedAnswer) {
    setAutosaveState('saving', 'جارِ الحفظ...');

    fetch(`/student/exam/${attemptId}/autosave`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question_id: questionId,
        answer: selectedAnswer
      })
    })
    .then(res => res.json())
    .then(data => {
      if (data.ok) {
        setAutosaveState('saved', 'تم الحفظ ✓');
      } else {
        setAutosaveState('error', 'فشل الحفظ - إعادة المحاولة ⚠️');
      }
    })
    .catch(() => {
      setAutosaveState('error', 'فشل الحفظ - إعادة المحاولة ⚠️');
    });
  }

  document.querySelectorAll('.opt-input').forEach(radio => {
    radio.addEventListener('change', (e) => {
      const qCard = e.target.closest('.question-card');
      if (qCard) {
        qCard.querySelectorAll('.opt-label').forEach(lbl => lbl.classList.remove('selected'));
        e.target.closest('.opt-label').classList.add('selected');
      }
      updateAnsweredCount();

      const questionId = e.target.getAttribute('data-question-id');
      const selectedAnswer = e.target.value;

      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        performAutosave(questionId, selectedAnswer);
      }, 300);
    });
  });

  updateAnsweredCount();
}

// 8. Elegant Toast and Alert Modal System (Replaces browser native alert/confirm)
function initToastAndAlertSystem() {
  // Container for floating toasts
  if (!document.getElementById('customToastContainer')) {
    const toastContainer = document.createElement('div');
    toastContainer.id = 'customToastContainer';
    toastContainer.className = 'custom-toast-container';
    document.body.appendChild(toastContainer);
  }

  // Modal for custom alerts
  if (!document.getElementById('customAlertModal')) {
    const alertModal = document.createElement('div');
    alertModal.id = 'customAlertModal';
    alertModal.className = 'modal-overlay';
    alertModal.style.display = 'none';
    alertModal.style.zIndex = '9999';
    alertModal.innerHTML = `
      <div class="modal-content modal-content-animated" style="max-width: 440px; text-align: center; padding: 30px 24px; border-radius: 16px; border: 1px solid var(--border); box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);">
        <div id="customAlertIconBox" style="width: 56px; height: 56px; border-radius: 16px; background: rgba(37, 99, 235, 0.1); color: var(--primary); display: flex; align-items: center; justify-content: center; font-size: 28px; margin: 0 auto 16px;">
          <span id="customAlertIcon">ℹ️</span>
        </div>
        <h3 id="customAlertTitle" style="font-size: 18px; font-weight: 800; margin: 0 0 8px; color: var(--text);">تنبيه من المنظومة</h3>
        <p id="customAlertMessage" style="color: var(--text-muted); font-size: 14px; margin: 0 0 24px; line-height: 1.6;"></p>
        <button type="button" class="btn btn-primary" id="customAlertOkBtn" style="width: 100%; padding: 11px 20px; font-weight: 700; font-size: 14px;">حسناً، فهمت</button>
      </div>
    `;
    document.body.appendChild(alertModal);
  }

  // Modal for custom confirmations (replaces browser confirm)
  if (!document.getElementById('customConfirmModal')) {
    const confirmModal = document.createElement('div');
    confirmModal.id = 'customConfirmModal';
    confirmModal.className = 'modal-overlay';
    confirmModal.style.display = 'none';
    confirmModal.style.zIndex = '9999';
    confirmModal.innerHTML = `
      <div class="modal-content modal-content-animated" style="max-width: 470px; text-align: right; padding: 26px 24px; border-radius: 16px; border: 1px solid var(--border); box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);">
        <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 16px;">
          <div id="customConfirmIconBox" style="width: 48px; height: 48px; border-radius: 14px; background: rgba(239, 68, 68, 0.12); color: var(--danger); display: flex; align-items: center; justify-content: center; font-size: 24px; flex-shrink: 0;">
            ⚠️
          </div>
          <div>
            <h3 id="customConfirmTitle" style="font-size: 17px; font-weight: 800; margin: 0; color: var(--text);">تأكيد العملية</h3>
            <div id="customConfirmSubtitle" style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">إجراء يتطلب تأكيد الإدارة</div>
          </div>
        </div>
        <div id="customConfirmMessage" style="background: var(--panel-alt); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; font-size: 13.5px; color: var(--text); line-height: 1.6; margin-bottom: 22px;"></div>
        <div style="display: flex; justify-content: flex-end; gap: 10px;">
          <button type="button" class="btn btn-secondary" id="customConfirmCancelBtn" style="padding: 9px 20px; font-weight: 600; font-size: 13.5px;">إلغاء الأمر</button>
          <button type="button" class="btn btn-danger" id="customConfirmActionBtn" style="padding: 9px 22px; font-weight: 700; font-size: 13.5px;">نعم، تأكيد الحذف</button>
        </div>
      </div>
    `;
    document.body.appendChild(confirmModal);
  }

  // Convert legacy onsubmit/onclick confirms to custom modal attributes
  convertLegacyConfirms();

  // Setup Global Form & Click Interceptor
  setupConfirmInterceptors();
}

function convertLegacyConfirms() {
  document.querySelectorAll('form[onsubmit*="confirm("], [onclick*="confirm("]').forEach(el => {
    const isForm = el.tagName === 'FORM';
    const attr = isForm ? 'onsubmit' : 'onclick';
    const val = el.getAttribute(attr) || '';
    const m = val.match(/confirm\(['"](.*?)['"]\)/);
    if (m) {
      el.setAttribute('data-confirm', m[1]);
      el.removeAttribute(attr);
    }
  });
}

function setupConfirmInterceptors() {
  // 1. Intercept form submissions with data-confirm
  document.addEventListener('submit', function(e) {
    const form = e.target;
    if (form.dataset.confirmed === 'true') {
      form.dataset.confirmed = '';
      return;
    }

    let msg = form.getAttribute('data-confirm');
    if (!msg && form.getAttribute('onsubmit') && form.getAttribute('onsubmit').includes('confirm(')) {
      const match = form.getAttribute('onsubmit').match(/confirm\(['"](.*?)['"]\)/);
      if (match) msg = match[1];
      form.removeAttribute('onsubmit');
    }

    if (msg) {
      e.preventDefault();
      e.stopImmediatePropagation();
      const title = form.getAttribute('data-confirm-title') || 'تأكيد العملية';
      const btnText = form.getAttribute('data-confirm-btn') || 'نعم، تأكيد الحذف';
      const isDanger = form.getAttribute('data-confirm-danger') !== 'false';

      window.showConfirmModal(msg, function() {
        form.dataset.confirmed = 'true';
        form.submit();
      }, title, btnText, isDanger);
      return false;
    }
  }, true);

  // 2. Intercept button/link clicks with data-confirm
  document.addEventListener('click', function(e) {
    const target = e.target.closest('[data-confirm], [onclick*="confirm("]');
    if (!target) return;

    let msg = target.getAttribute('data-confirm');
    if (!msg && target.getAttribute('onclick') && target.getAttribute('onclick').includes('confirm(')) {
      const match = target.getAttribute('onclick').match(/confirm\(['"](.*?)['"]\)/);
      if (match) msg = match[1];
      target.removeAttribute('onclick');
    }

    if (!msg) return;

    const title = target.getAttribute('data-confirm-title') || 'تأكيد العملية';
    const btnText = target.getAttribute('data-confirm-btn') || 'نعم، تأكيد الحذف';
    const isDanger = target.getAttribute('data-confirm-danger') !== 'false';

    // If inside a form as submit button
    if (target.form && (target.type === 'submit' || target.tagName === 'BUTTON')) {
      if (target.form.dataset.confirmed === 'true') return;
      e.preventDefault();
      e.stopImmediatePropagation();

      window.showConfirmModal(msg, function() {
        target.form.dataset.confirmed = 'true';
        if (target.name && target.value) {
          const hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.name = target.name;
          hidden.value = target.value;
          target.form.appendChild(hidden);
        }
        target.form.submit();
      }, title, btnText, isDanger);
      return false;
    }

    // If a standalone link
    if (target.tagName === 'A' && target.href) {
      e.preventDefault();
      e.stopImmediatePropagation();
      window.showConfirmModal(msg, function() {
        window.location.href = target.href;
      }, title, btnText, isDanger);
      return false;
    }
  }, true);
}

// Global helper for showing beautiful floating toasts
window.showToast = function(message, type = 'info', duration = 4000) {
  const container = document.getElementById('customToastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `custom-toast toast-${type}`;
  
  const icon = type === 'success' ? '✓' : (type === 'error' ? '✕' : 'ℹ️');
  toast.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-message">${message}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('show');
  }, 10);

  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, duration);
};

// Global helper for replacing alert(...)
window.showAlertModal = function(message, title = 'تنبيه من المنظومة', icon = 'ℹ️', onOk = null) {
  const modal = document.getElementById('customAlertModal');
  if (!modal) {
    alert(message);
    if (typeof onOk === 'function') onOk();
    return;
  }
  document.getElementById('customAlertTitle').textContent = title;
  document.getElementById('customAlertMessage').textContent = message;
  document.getElementById('customAlertIcon').textContent = icon;

  const okBtn = document.getElementById('customAlertOkBtn');
  okBtn.onclick = function() {
    modal.style.display = 'none';
    okBtn.onclick = null;
    if (typeof onOk === 'function') onOk();
  };

  modal.style.display = 'flex';
};

// Global helper for replacing confirm(...)
window.showConfirmModal = function(message, onConfirm, title = 'تأكيد العملية', confirmBtnText = 'نعم، تأكيد الحذف', isDanger = true) {
  const modal = document.getElementById('customConfirmModal');
  if (!modal) {
    if (confirm(message)) onConfirm();
    return;
  }

  document.getElementById('customConfirmTitle').textContent = title;
  document.getElementById('customConfirmMessage').textContent = message;
  
  const iconBox = document.getElementById('customConfirmIconBox');
  const actionBtn = document.getElementById('customConfirmActionBtn');
  const cancelBtn = document.getElementById('customConfirmCancelBtn');

  if (isDanger) {
    iconBox.textContent = '🗑️';
    iconBox.style.background = 'rgba(239, 68, 68, 0.12)';
    iconBox.style.color = 'var(--danger)';
    actionBtn.className = 'btn btn-danger';
  } else {
    iconBox.textContent = '❓';
    iconBox.style.background = 'rgba(37, 99, 235, 0.12)';
    iconBox.style.color = 'var(--primary)';
    actionBtn.className = 'btn btn-primary';
  }

  actionBtn.textContent = confirmBtnText;

  function cleanup() {
    modal.style.display = 'none';
    actionBtn.onclick = null;
    cancelBtn.onclick = null;
    document.removeEventListener('keydown', handleKey);
    modal.onclick = null;
  }

  function handleKey(e) {
    if (e.key === 'Escape') cleanup();
  }

  actionBtn.onclick = () => {
    cleanup();
    if (typeof onConfirm === 'function') onConfirm();
  };

  cancelBtn.onclick = () => {
    cleanup();
  };

  modal.onclick = (e) => {
    if (e.target === modal) cleanup();
  };

  document.addEventListener('keydown', handleKey);
  modal.style.display = 'flex';
};

// Override native confirm & alert to prevent ugly browser popups completely
window.confirm = function(msg) {
  window.showConfirmModal(msg, () => {});
  return false;
};

window.alert = function(msg) {
  window.showAlertModal(msg);
};

// Accordion Sidebar Navigation
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.nav-accordion-header').forEach(header => {
    header.addEventListener('click', function(e) {
      e.preventDefault();
      const parent = this.closest('.nav-accordion-group');
      const wasOpen = parent.classList.contains('open');

      // Close all other groups (Accordion effect)
      document.querySelectorAll('.nav-accordion-group').forEach(group => {
        group.classList.remove('open');
      });

      // Toggle current group
      if (!wasOpen) {
        parent.classList.add('open');
      }
    });
  });
});
