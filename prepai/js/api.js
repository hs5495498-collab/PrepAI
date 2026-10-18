/* ==========================================================
   Thin fetch wrapper for the FastAPI backend (see /backend).
   One place for the base URL so it is never hardcoded per-page.
   Every call resolves (never rejects) to { ok, status, data }:
   status 0 means a network failure or timeout, not a real HTTP
   response, so callers can tell "backend down" apart from a real
   4xx/5xx from the server.
   ========================================================== */
(function () {
  var BASE_URL = 'http://127.0.0.1:8000';
  var TIMEOUT_MS = 5000;

  function request(path, options) {
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = ctrl && setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS);
    var init = Object.assign({}, options || {}, ctrl ? { signal: ctrl.signal } : {});
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

  function postJSON(path, body) {
    return request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  }

  window.PREP_API = {
    baseUrl: BASE_URL,
    health: function () { return request('/health'); },
    createInterview: function (payload) { return postJSON('/api/interviews', payload); },
    getInterview: function (sessionId) { return request('/api/interviews/' + encodeURIComponent(sessionId)); },
    submitAnswer: function (sessionId, payload) { return postJSON('/api/interviews/' + encodeURIComponent(sessionId) + '/answers', payload); },
    completeInterview: function (sessionId) { return postJSON('/api/interviews/' + encodeURIComponent(sessionId) + '/complete', {}); }
  };
})();
