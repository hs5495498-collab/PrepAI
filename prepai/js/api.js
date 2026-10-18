/* ==========================================================
   Thin fetch wrapper for the FastAPI backend (see /backend).
   One place for the base URL so it is never hardcoded per-page.
   Every call resolves (never rejects) to { ok, status, data }:
   status 0 means a network failure or timeout, not a real HTTP
   response, so callers can tell "backend down" apart from a real
   4xx/5xx from the server.

   Phase 7: every request now sends credentials:'include' so the
   HttpOnly session cookie (set by /api/auth/login or /register) is
   sent back on every call - that cookie is never touched from here,
   only read by the backend. State-changing requests also attach the
   separate, non-HttpOnly CSRF cookie as an X-CSRF-Token header (the
   "double submit cookie" pattern); anonymous requests have neither
   cookie, so nothing changes for the existing offline/demo flow.
   ========================================================== */
(function () {
  var BASE_URL = 'http://127.0.0.1:8000';
  var TIMEOUT_MS = 5000;

  function readCookie(name) {
    var match = document.cookie.match('(?:^|; )' + name.replace(/[.$?*|{}()[\]\\/+^]/g, '\\$&') + '=([^;]*)');
    return match ? decodeURIComponent(match[1]) : null;
  }

  function request(path, options) {
    options = options || {};
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = ctrl && setTimeout(function () { ctrl.abort(); }, options.timeoutMs || TIMEOUT_MS);
    var headers = Object.assign({}, options.headers || {});
    var csrfToken = readCookie('prepai_csrf');
    if (csrfToken && options.method && options.method !== 'GET') headers['X-CSRF-Token'] = csrfToken;
    var init = Object.assign({}, options, { credentials: 'include', headers: headers }, ctrl ? { signal: ctrl.signal } : {});
    delete init.timeoutMs;
    return fetch(BASE_URL + path, init)
      .then(function (res) {
        if (timer) clearTimeout(timer);
        return res.json().catch(function () { return null; }).then(function (data) {
          return { ok: res.ok, status: res.status, data: data };
        });
      })
      .catch(function () {
        if (timer) clearTimeout(timer);
        return { ok: false, status: 0, data: null };
      });
  }

  function postJSON(path, body, timeoutMs) {
    return request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      timeoutMs: timeoutMs
    });
  }

  window.PREP_API = {
    baseUrl: BASE_URL,
    health: function () { return request('/health'); },
    createInterview: function (payload) { return postJSON('/api/interviews', payload); },
    getInterview: function (sessionId) { return request('/api/interviews/' + encodeURIComponent(sessionId)); },
    submitAnswer: function (sessionId, payload) { return postJSON('/api/interviews/' + encodeURIComponent(sessionId) + '/answers', payload); },
    completeInterview: function (sessionId) { return postJSON('/api/interviews/' + encodeURIComponent(sessionId) + '/complete', {}); },
    register: function (email, password) { return postJSON('/api/auth/register', { email: email, password: password }); },
    login: function (email, password) { return postJSON('/api/auth/login', { email: email, password: password }); },
    logout: function () { return postJSON('/api/auth/logout', {}); },
    me: function () { return request('/api/auth/me'); },
    // AI evaluation can genuinely take longer than a normal request - 30s
    // instead of the default 5s, so a real-but-slow response isn't wrongly
    // reported as "backend unreachable".
    evaluateAnswer: function (sessionId, questionId) {
      return postJSON(
        '/api/interviews/' + encodeURIComponent(sessionId) + '/questions/' + encodeURIComponent(questionId) + '/evaluate',
        {}, 30000
      );
    }
  };
})();
