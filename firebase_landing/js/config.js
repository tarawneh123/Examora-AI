// Examora AI - Online Cloud API Configuration (Production Live)
window.EXAMORA_CONFIG = {
  API_BASE_URL: (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://127.0.0.1:8080'
    : 'https://examora-ai-nowy.onrender.com'
};
