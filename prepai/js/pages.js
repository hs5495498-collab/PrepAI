/* ==========================================================
   Page logic. Each function below runs on the page whose
   <body data-page="..."> matches its name (see app.js).
   ========================================================== */
(function () {
  var P = window.PREP;
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function signed(n) { return (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n); }
  function metric(label, value, sub, cls) {
    return '<div class="metric"><div class="metric-label">' + label + '</div><div class="metric-value ' + (cls || '') + '">' + value +
      '</div><div class="metric-sub">' + sub + '</div></div>';
  }
  function changeHTML(ch) {
    if (ch == null) return '<span class="row-change muted">—</span>';
    if (ch > 0) return '<span class="row-change pos">' + icon('arrow-up', 14) + ch + '</span>';
    if (ch < 0) return '<span class="row-change neg">' + icon('arrow-down', 14) + Math.abs(ch) + '</span>';
    return '<span class="row-change muted">0</span>';
  }
  function resultHTML(a) { var r = P.result(a); return '<span class="res res-' + r.key + '">' + r.label + '</span>'; }
  function skillByKey(k) { return P.skills.filter(function (s) { return s.key === k; })[0]; }

  var pages = {};

  /* ---------------- 1. Dashboard ---------------- */
  pages.dashboard = function () {
    var c = P.completed(), first = c[0], last = c[c.length - 1], delta = last.score - first.score;
    $('#metrics').innerHTML =
      metric('Latest Score', last.score, 'out of 100') +
      metric('Improvement Since First Attempt', signed(delta), 'points · ' + first.score + ' → ' + last.score, delta >= 0 ? 'pos' : 'neg') +
      metric('Completed Interviews', c.length, 'scored attempts');
    createChart($('#chart'), { points: P.toPoints(c), height: 300, ariaLabel: 'Line chart of your interview scores over time' });

    var weak = P.weakest();
    $('#reco-text').textContent = weak.tip;
    $('#reco-btn').href = 'practice.html?focus=' + weak.key;

    $('#recent').innerHTML = c.slice(-3).reverse().map(function (a) {
      return '<a class="list-row" href="results.html?id=' + a.id + '">' +
        '<div class="row-main"><div class="row-title">' + P.name(a) + '</div><div class="row-sub">' + P.fmt(a.date, true) + '</div></div>' +
        '<span class="row-score">' + a.score + '</span>' + changeHTML(P.changeFor(a)) +
        '<span class="row-arrow">' + icon('chevron', 18) + '</span></a>';
    }).join('');
  };

  /* ---------------- 2. Practice interview ---------------- */
  var CATEGORY_LABEL = { technical: 'Technical', hr: 'HR', behavioral: 'Behavioral' };
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function formatApiError(data) {
    if (!data || data.detail == null) return null;
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map(function (e) { return (e && e.msg) || JSON.stringify(e); }).join('; ');
    }
    return JSON.stringify(data.detail);
  }
  function demoScore(answers) {
    // Non-AI placeholder: a simple word-count heuristic, never shown without a "demo score" label.
    var counts = answers.map(function (a) { return (a || '').trim().split(/\s+/).filter(Boolean).length; });
    var avg = counts.reduce(function (s, n) { return s + n; }, 0) / (counts.length || 1);
    return Math.max(10, Math.min(99, Math.round(avg * 3)));
  }

  pages.practice = function () {
    var params = new URLSearchParams(location.search);
    var settings = window.PREP_SETTINGS();
    var focusParam = params.get('focus');
    if (focusParam === 'weak') focusParam = P.weakest().key;
    var skill = focusParam ? skillByKey(focusParam) : null;

    var setupEl = $('#setup'), sessionEl = $('#session'), introEl = $('#practiceIntro'), recoEl = $('#recommendation');
    var root = $('.practice'), qcount = $('#qcount'), sessionMode = $('#sessionMode'), bar = $('#pbar'),
        question = $('#question'), answer = $('#answer'), hint = $('#hint'), mic = $('#mic'), wave = $('#wave'),
        timer = $('#timer'), pauseBtn = $('#pause'), prevBtn = $('#prev'), nextBtn = $('#submit'),
        endBtn = $('#end');
    var setupRole = $('#setupRole'), setupCategory = $('#setupCategory'),
        setupDifficulty = $('#setupDifficulty'), setupCount = $('#setupCount'),
        setupHint = $('#setupHint'), setupStart = $('#setupStart'), setupOfflineStart = $('#setupOfflineStart');
    var ALL_CATEGORIES = ['technical', 'hr', 'behavioral'];
    var BASELINE_CATEGORY = 'technical', BASELINE_DIFFICULTY = 'easy', QUESTION_COUNT_DEFAULT = 5;

    if (settings.showTimer === false) timer.hidden = true;

    var list = [], meta = null, i = 0, seconds = 0, paused = false, recording = false,
        answers = [], recordedFlags = [], tickHandle = null,
        backendId = null, submittedToBackend = [], creating = false, submitting = false;

    function startTimer() {
      if (tickHandle) return;
      tickHandle = setInterval(function () {
        if (paused) return;
        seconds++;
        var m = Math.floor(seconds / 60), s = seconds % 60;
        timer.textContent = (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
      }, 1000);
    }

    function draw() {
      qcount.textContent = 'Question ' + (i + 1) + ' of ' + list.length +
        (skill ? ' · Focus: ' + skill.name : meta ? ' · ' + CATEGORY_LABEL[meta.category] + ' · ' + cap(meta.difficulty) : '');
      bar.style.width = (i / list.length * 100) + '%';
      question.textContent = list[i].q;
      answer.value = answers[i] || '';
      var locked = !!submittedToBackend[i];
      answer.disabled = locked;
      mic.disabled = locked;
      hint.textContent = locked ? 'This answer was already submitted to the server and can’t be changed.' : '';
      wave.dataset.used = '0';
      setRecording(false);
      prevBtn.disabled = i === 0 || submitting;
      nextBtn.disabled = submitting;
      nextBtn.textContent = i === list.length - 1 ? 'Finish Interview' : 'Next Question';
    }
    function setRecording(on) {
      // NOTE: this is a visual-only prototype. Connect MediaRecorder / speech-to-text here.
      recording = on;
      mic.setAttribute('aria-pressed', on);
      $('.mic-label', mic).textContent = on ? 'Stop recording' : 'Record answer';
      wave.hidden = !on;
      if (!on && wave.dataset.used === '1') recordedFlags[i] = true;
      if (on) wave.dataset.used = '1';
    }
    function saveCurrentAnswer() { if (!submittedToBackend[i]) answers[i] = answer.value; }
    function currentValid() { return !!(answers[i] && answers[i].trim()) || !!recordedFlags[i]; }
    function setBusy(busy, message) {
      submitting = busy;
      nextBtn.disabled = busy;
      prevBtn.disabled = busy || i === 0;
      endBtn.disabled = busy;
      hint.textContent = message || '';
    }
    function advanceOrFinish() {
      if (i >= list.length - 1) { finish(); return; }
      i++;
      draw();
    }

    mic.addEventListener('click', function () { setRecording(!recording); });

    prevBtn.addEventListener('click', function () {
      if (i === 0 || submitting) return;
      if (recording) setRecording(false);
      saveCurrentAnswer();
      i--;
      draw();
    });

    nextBtn.addEventListener('click', function () {
      if (submitting) return;
      if (recording) setRecording(false);
      saveCurrentAnswer();
      if (!currentValid()) {
        hint.textContent = 'Add a written or recorded answer before continuing.';
        return;
      }
      if (!backendId || submittedToBackend[i]) {
        advanceOrFinish();
        return;
      }
      setBusy(true, 'Saving your answer…');
      window.PREP_API.submitAnswer(backendId, { question_id: list[i].id, answer: answers[i] })
        .then(function (res) {
          if (res.ok || res.status === 409) {
            // 409 means the backend already has this answer recorded (e.g. a repeated
            // click) - safe to treat as submitted and continue, not an error.
            submittedToBackend[i] = true;
            setBusy(false);
            advanceOrFinish();
            return;
          }
          if (res.status === 404) {
            // In-memory backend session is gone (e.g. the server restarted). Keep the
            // candidate moving locally instead of losing their progress.
            backendId = null;
            setBusy(false, 'Your interview session expired on the server (sessions are not saved permanently yet). Continuing on this device only.');
            advanceOrFinish();
            return;
          }
          if (res.status === 0) {
            backendId = null;
            setBusy(false, 'Lost connection to the interview server. Continuing on this device only.');
            advanceOrFinish();
            return;
          }
          setBusy(false, formatApiError(res.data) || 'The server rejected this answer. Please try again.');
        });
    });

    pauseBtn.addEventListener('click', function () {
      paused = !paused;
      root.classList.toggle('is-paused', paused);
      pauseBtn.textContent = paused ? 'Resume' : 'Pause';
      if (paused && recording) setRecording(false);
    });

    endBtn.addEventListener('click', function () {
      if (!window.confirm('End this interview? It will be saved as incomplete and will not receive a score.')) return;
      saveCurrentAnswer();
      var answeredCount = 0;
      for (var k = 0; k < list.length; k++) {
        if ((answers[k] && answers[k].trim()) || recordedFlags[k]) answeredCount++;
      }
      P.addDemoAttempt({
        type: meta ? CATEGORY_LABEL[meta.category] : (skill ? skill.name : 'Practice'),
        status: 'incomplete',
        answered: answeredCount,
        total: list.length
      });
      location.href = 'history.html';
    });

    function finishOffline() {
      var qa = list.map(function (item, idx) { return { q: item.q, a: answers[idx] || '' }; });
      var attempt = P.addDemoAttempt({
        type: meta ? CATEGORY_LABEL[meta.category] : (skill ? skill.name : 'Practice'),
        status: 'completed',
        score: demoScore(answers),
        qa: qa,
        source: 'offline'
      });
      location.href = 'results.html?id=' + attempt.id;
    }

    function finishFromBackend(data) {
      var qa = (data.questions || []).map(function (item) { return { id: item.id, q: item.text, a: item.answer || '' }; });
      var attempt = P.addDemoAttempt({
        type: meta ? CATEGORY_LABEL[meta.category] : 'Practice',
        status: 'completed',
        score: demoScore(qa.map(function (x) { return x.a; })),
        qa: qa,
        source: 'backend',
        sessionId: data.session_id
      });
      location.href = 'results.html?id=' + attempt.id;
    }

    function finish() {
      if (!window.confirm('Finish the interview and view your results? You will not be able to change your answers after this.')) return;
      if (!backendId) { finishOffline(); return; }
      setBusy(true, 'Finishing your interview…');
      window.PREP_API.completeInterview(backendId).then(function (res) {
        if (res.ok) { finishFromBackend(res.data); return; }
        // Already completed (a rare double-submit race), expired, or unreachable:
        // fall back to a locally-saved result instead of losing the candidate's answers.
        finishOffline();
      });
    }

    function beginSession(newList, newMeta, backendSessionId) {
      list = newList; meta = newMeta; i = 0; seconds = 0; paused = false;
      answers = []; recordedFlags = []; submittedToBackend = [];
      backendId = backendSessionId || null;
      if (sessionMode) {
        sessionMode.textContent = skill ? '' : (!backendId ? '· Offline demo (not saved to server)' :
          meta && meta.questionSource === 'ai' ? '· Live session · AI-generated questions' : '· Live session · fixed question bank');
        if (meta && meta.bankNote) sessionMode.textContent += ' · ' + meta.bankNote;
      }
      setupEl.hidden = true;
      if (introEl) introEl.hidden = true;
      if (recoEl) recoEl.hidden = true;
      sessionEl.hidden = false;
      root.classList.remove('is-paused');
      pauseBtn.textContent = 'Pause';
      draw();
      startTimer();
    }

    // Mirrors backend/questions.py's pick_questions(): matching-difficulty
    // questions first, then the rest of the category, each used at most
    // once - never cycles back through questions already picked to pad
    // the list up to `count`.
    function pickOfflineQuestions(category, difficulty, count) {
      var all = P.demoQuestions[category] || [];
      var matching = all.filter(function (q) { return q.d === difficulty; });
      var other = all.filter(function (q) { return q.d !== difficulty; });
      var ordered = matching.concat(other);
      return { picked: ordered.slice(0, count), insufficient: count > ordered.length };
    }

    function startOfflineInterview(role, category, difficulty, count) {
      var result = pickOfflineQuestions(category, difficulty, count);
      var picked = result.picked.map(function (q) { return { q: q.q }; });
      beginSession(picked, {
        role: role, category: category, difficulty: difficulty,
        bankNote: result.insufficient
          ? 'Only ' + picked.length + ' distinct fixed sample question(s) are available for this category, fewer than the ' + count + ' requested - showing all of them once instead of repeating any.'
          : null
      }, null);
    }

    function showCreateError(res) {
      var msg;
      if (res.status === 0) msg = 'Could not reach the interview server at ' + window.PREP_API.baseUrl + '. Make sure the backend is running.';
      else if (res.status === 422) msg = 'The server rejected this request: ' + (formatApiError(res.data) || 'invalid input.');
      else if (res.status === 503) msg = formatApiError(res.data) || 'The interview question service is temporarily unavailable.';
      else msg = 'The interview server returned an unexpected error (status ' + res.status + ').';
      setupHint.textContent = msg;
      if (setupOfflineStart) setupOfflineStart.hidden = false;
    }

    if (skill) {
      // Existing quick skill-drill, reached via ?focus=<skill key>. Unchanged question source.
      var skillList = P.bank.filter(function (b) { return b.skill === skill.key; }).slice(0, 3)
        .map(function (b) { return { q: b.q }; });
      beginSession(skillList, null);
    } else {
      setupEl.hidden = false;
      sessionEl.hidden = true;

      // Nice-to-have: prefill from existing Settings, without weakening validation below.
      var savedCategory = { Technical: 'technical', Behavioral: 'behavioral' }[settings.defaultType];
      if (savedCategory) setupCategory.value = savedCategory;
      if (settings.questionCount === '5') setupCount.value = '5';
      var roleOptions = Array.prototype.map.call(setupRole.options, function (o) { return o.value; });
      if (settings.role && roleOptions.indexOf(settings.role) > -1) setupRole.value = settings.role;

      /* ---- Recommended-for-You card (Phase 2A) ----
         Consumes the existing GET /api/recommendations (Phase 9) - no new
         endpoint or response shape invented here. Falls back to a clearly
         labeled, non-personalized starting point when logged out, when
         there's no history yet, or when the request fails - this never
         fabricates a score, a weakness, or a trend that isn't in the real
         data returned by the backend. */
      function minutesEstimate(count) {
        // A simple, generic pacing estimate (~2 min/question) shown to the
        // user as an estimate, not a personalized metric - same spirit as
        // demoScore()'s "(demo)" label elsewhere on this page.
        return Math.max(5, count * 2);
      }
      function recoTag(text) { return '<span class="reco-tag">' + esc(text) + '</span>'; }

      function startFromCard(category, difficulty, btn) {
        if (creating) return;
        btn.disabled = true;
        btn.textContent = 'Starting…';
        if (!setupRole.value) setupRole.value = setupRole.options[1].value;
        setupCategory.value = category;
        setupDifficulty.value = difficulty;
        setupStart.click();
        // Reuses setupStart's own click handler (same CSRF/ownership/error
        // handling as the plain "Start Interview" button, no duplicated
        // network code) - this just mirrors its disabled state back onto
        // this separate button until that attempt finishes either way.
        (function waitForSetupStart(tries) {
          if (!setupStart.disabled || tries > 150) {
            btn.disabled = false;
            btn.textContent = btn.dataset.label;
            return;
          }
          setTimeout(function () { waitForSetupStart(tries + 1); }, 100);
        })(0);
      }

      function renderRecoCard(cfg) {
        var category = cfg.category || BASELINE_CATEGORY;
        var difficulty = cfg.difficulty || BASELINE_DIFFICULTY;
        var count = cfg.count || QUESTION_COUNT_DEFAULT;
        var mins = minutesEstimate(count);
        var tags = recoTag((CATEGORY_LABEL[category] || cap(category))) + recoTag(cap(difficulty) + ' difficulty') +
          recoTag(count + ' question' + (count === 1 ? '' : 's')) + recoTag('~' + mins + ' min (estimate)') +
          recoTag('Written answers');

        var explanationMarkup = cfg.explanationHtml || esc(cfg.explanation || '');
        var reasonHtml = '';
        if (cfg.evidenceLines && cfg.evidenceLines.length) {
          reasonHtml = '<p class="muted" style="margin-top:8px;font-size:.8125rem">' + cfg.evidenceLines.map(esc).join(' · ') + '</p>';
        } else if (cfg.reasonLine) {
          reasonHtml = '<p class="muted" style="margin-top:8px;font-size:.8125rem;font-style:italic">' + esc(cfg.reasonLine) + '</p>';
        }
        var actionHtml = cfg.actionLine ? '<p style="margin-top:8px">Next: ' + esc(cfg.actionLine) + '</p>' : '';
        var kindLine = cfg.isGeneric
          ? '<p class="muted" style="margin-top:4px">General starting point — not yet personalized to your history.</p>'
          : '<p class="muted" style="margin-top:4px">A rule-based suggestion from your own evaluated practice history — not a trained AI model.</p>';

        var others = ALL_CATEGORIES.filter(function (c) { return c !== category; });
        var secondaryHtml = others.map(function (c) {
          var label = 'Try ' + (CATEGORY_LABEL[c] || cap(c)) + ' instead';
          return '<button class="btn btn-outline btn-sm reco-secondary-btn" type="button" data-category="' + c +
            '" data-difficulty="' + difficulty + '" data-label="' + esc(label) + '">' + esc(label) + '</button>';
        }).join('');

        recoEl.innerHTML =
          '<div class="eyebrow">Recommended for You</div>' +
          '<h3 class="reco-text" style="margin-top:6px">' + esc(cfg.title) + '</h3>' +
          '<p class="muted">' + explanationMarkup + '</p>' +
          reasonHtml + actionHtml + kindLine +
          '<div class="reco-tags">' + tags + '</div>' +
          '<div class="reco-actions"><button class="btn btn-primary" type="button" id="recoStartBtn" data-label="Start Recommended Session">Start Recommended Session</button></div>' +
          (others.length ? '<div class="reco-secondary"><span class="muted" style="font-size:.8125rem">Or choose a different interview type:</span>' +
            '<div class="reco-secondary-list">' + secondaryHtml + '</div></div>' : '') +
          '<p class="muted" style="font-size:.8125rem">You can still change the role, category, difficulty, or question count below before starting.</p>';

        var startBtn = $('#recoStartBtn', recoEl);
        startBtn.addEventListener('click', function () { startFromCard(category, difficulty, startBtn); });
        $$('.reco-secondary-btn', recoEl).forEach(function (b) {
          b.addEventListener('click', function () { startFromCard(b.dataset.category, b.dataset.difficulty, b); });
        });
      }

      function showBaseline(explanationHtml) {
        renderRecoCard({
          title: 'Start with a Technical practice interview',
          explanationHtml: explanationHtml || 'This is a general starting point to help you begin practicing right away.',
          isGeneric: true,
          category: BASELINE_CATEGORY,
          difficulty: BASELINE_DIFFICULTY,
          count: QUESTION_COUNT_DEFAULT
        });
      }

      function showRecoError(res) {
        recoEl.innerHTML = '<div class="eyebrow">Recommended for You</div>' +
          '<div class="notice" style="margin-top:8px">Could not load your personalized recommendation' +
          (res.status === 0 ? ' — make sure the backend is running.' : '.') +
          ' <button class="btn btn-secondary btn-sm" type="button" id="recoCardRetry" style="margin-left:8px">Try again</button></div>';
        var retry = $('#recoCardRetry');
        if (retry) retry.addEventListener('click', renderRecommendation);
      }

      function showFromRecommendations(data) {
        var recs = data.recommendations || [];
        if (!recs.length) {
          renderRecoCard({
            title: 'Your results look solid across the board',
            explanation: 'No specific recommendation right now — your evaluated results look solid across the board. Keep practising to build more history.',
            isGeneric: true,
            category: BASELINE_CATEGORY,
            difficulty: BASELINE_DIFFICULTY,
            count: QUESTION_COUNT_DEFAULT
          });
          return;
        }
        var top = recs[0];
        renderRecoCard({
          title: top.title,
          explanation: top.explanation,
          reasonLine: top.reason,
          actionLine: top.action,
          evidenceLines: top.evidence_level === 'generic' ? [] : (top.evidence || []),
          isGeneric: top.evidence_level === 'generic',
          category: top.category,
          difficulty: top.difficulty,
          count: QUESTION_COUNT_DEFAULT
        });
      }

      function renderRecommendation() {
        if (!recoEl) return;
        recoEl.innerHTML = '<div class="eyebrow">Recommended for You</div><p class="muted" style="margin-top:8px">Loading your personalized recommendation…</p>';
        if (!window.PREP_API) { showBaseline(); return; }
        window.PREP_API.getRecommendations().then(function (res) {
          if (res.status === 401) {
            showBaseline('<a class="link" href="settings.html#account-section">Sign in</a> to get a recommendation based on your own practice history. Until then, here’s a sensible starting point.');
            return;
          }
          if (!res.ok || !res.data) { showRecoError(res); return; }
          showFromRecommendations(res.data);
        });
      }

      renderRecommendation();

      setupStart.addEventListener('click', function () {
        if (creating) return;
        var role = setupRole.value, category = setupCategory.value,
            difficulty = setupDifficulty.value, count = parseInt(setupCount.value, 10);
        if (!role || !category) {
          setupHint.textContent = 'Select a job role and an interview category to continue.';
          return;
        }
        setupHint.textContent = '';
        if (setupOfflineStart) setupOfflineStart.hidden = true;
        creating = true;
        setupStart.disabled = true;
        setupStart.textContent = 'Starting interview…';
        window.PREP_API.createInterview({ role: role, category: category, difficulty: difficulty, question_count: count })
          .then(function (res) {
            creating = false;
            setupStart.disabled = false;
            setupStart.textContent = 'Start Interview';
            if (res.ok && res.data && Array.isArray(res.data.questions) && res.data.questions.length) {
              var picked = res.data.questions.map(function (q) { return { q: q.text, id: q.id }; });
              beginSession(picked, {
                role: role, category: category, difficulty: difficulty,
                questionSource: res.data.question_source, bankNote: res.data.question_bank_note || null
              }, res.data.session_id);
              return;
            }
            showCreateError(res);
          });
      });

      if (setupOfflineStart) {
        setupOfflineStart.addEventListener('click', function () {
          var role = setupRole.value, category = setupCategory.value,
              difficulty = setupDifficulty.value, count = parseInt(setupCount.value, 10);
          if (!role || !category) {
            setupHint.textContent = 'Select a job role and an interview category to continue.';
            return;
          }
          startOfflineInterview(role, category, difficulty, count);
        });
      }
    }
  };

  /* ---------------- 3. Interview history ---------------- */
  pages.history = function () {
    var state = { range: 'all', type: 'all', shown: 6 };
    var c = P.completed();
    $('#summary').textContent = 'Latest score ' + c[c.length - 1].score + ' · ' + c.length + ' completed attempts';

    function filtered() {
      var cut = null;
      if (state.range !== 'all') { cut = new Date(P.ref); cut.setDate(cut.getDate() - parseInt(state.range, 10)); }
      return P.attempts.slice().sort(function (a, b) { return b.d - a.d; }).filter(function (a) {
        return (!cut || a.d >= cut) && (state.type === 'all' || a.type === state.type);
      });
    }
    function draw() {
      var all = filtered(), rows = all.slice(0, state.shown);
      $('#rows').innerHTML = rows.length ? rows.map(function (a) {
        var clickable = a.status !== 'missed';
        return '<tr' + (clickable ? ' data-href="results.html?id=' + a.id + '"' : '') + '>' +
          '<td data-label="Date">' + P.fmt(a.date, true) + '</td>' +
          '<td data-label="Type">' + a.type + '</td>' +
          '<td data-label="Score">' + (a.score != null ? a.score : '—') + '</td>' +
          '<td data-label="Result">' + resultHTML(a) + '</td>' +
          '<td data-label="Change">' + changeHTML(P.changeFor(a)) + '</td>' +
          '<td>' + (clickable
            ? '<a class="view-link" href="results.html?id=' + a.id + '">View' + icon('chevron', 16) + '</a>'
            : '<span class="muted">No attempt</span>') + '</td></tr>';
      }).join('') : '<tr><td colspan="6" class="empty">No interviews match these filters.</td></tr>';
      $('#more').hidden = all.length <= state.shown;
    }
    $('#f-range').addEventListener('change', function (e) { state.range = e.target.value; state.shown = 6; draw(); });
    $('#f-type').addEventListener('change', function (e) { state.type = e.target.value; state.shown = 6; draw(); });
    $('#more').addEventListener('click', function () { state.shown += 6; draw(); });
    $('#rows').addEventListener('click', function (e) {
      if (e.target.closest('a')) return;
      var tr = e.target.closest('tr[data-href]');
      if (tr) location.href = tr.getAttribute('data-href');
    });
    draw();
    renderAccountHistory();
  };

  /* Server-persisted account history (Phase 10) - entirely separate from
     the legacy localStorage table above. Never mixes the two: a backend
     interview is only ever shown here, using its real session_id; the
     table above keeps reading only P.attempts/localStorage, unchanged. */
  function renderAccountHistory() {
    var body = $('#account-history-body');
    if (!body) return;
    var limit = 10, offset = 0, accumulated = [];

    function row(item) {
      var scoreCell = item.average_score != null
        ? item.average_score + ' / 100' + (item.evaluated_count < item.question_count ? ' (' + item.evaluated_count + ' of ' + item.question_count + ' evaluated)' : '')
        : (item.evaluated_count === 0 ? '— not evaluated' : '—');
      var statusLabel = item.status === 'completed' ? 'Completed' : 'In Progress';
      return '<tr data-href="results.html?session=' + encodeURIComponent(item.session_id) + '">' +
        '<td data-label="Date">' + P.fmt(new Date(item.created_at), true) + '</td>' +
        '<td data-label="Role">' + esc(item.role) + '</td>' +
        '<td data-label="Category">' + cap(item.category) + ' · ' + cap(item.difficulty) + '</td>' +
        '<td data-label="Status">' + statusLabel + ' (' + item.answered_count + '/' + item.question_count + ' answered)</td>' +
        '<td data-label="Score">' + scoreCell + '</td>' +
        '<td><a class="view-link" href="results.html?session=' + encodeURIComponent(item.session_id) + '">View' + icon('chevron', 16) + '</a></td></tr>';
    }

    function renderList(total) {
      if (!accumulated.length) {
        body.innerHTML = '<p class="muted">You haven’t completed any practice interviews on your account yet. <a class="link" href="practice.html">Start one now</a>.</p>';
        return;
      }
      body.innerHTML = '<table class="table"><thead><tr><th>Date</th><th>Role</th><th>Category</th><th>Status</th><th>Score</th><th><span class="sr-only">View details</span></th></tr></thead>' +
        '<tbody>' + accumulated.map(row).join('') + '</tbody></table>' +
        (accumulated.length < total ? '<div class="table-foot"><button class="btn btn-secondary" id="accountHistoryMore" type="button">Load more</button></div>' : '');
      var moreBtn = $('#accountHistoryMore');
      if (moreBtn) moreBtn.addEventListener('click', function () { offset += limit; load(true); });
      var table = $('table', body);
      table.addEventListener('click', function (e) {
        if (e.target.closest('a')) return;
        var tr = e.target.closest('tr[data-href]');
        if (tr) location.href = tr.getAttribute('data-href');
      });
    }

    function load(append) {
      if (!append) body.innerHTML = '<p class="muted">Loading your account history…</p>';
      window.PREP_API.listInterviews(limit, offset).then(function (res) {
        if (res.status === 401) {
          body.innerHTML = '<div class="notice">Sign in on the <a class="link" href="settings.html">Settings</a> page to see interviews saved to your account.</div>';
          return;
        }
        if (!res.ok || !res.data) {
          body.innerHTML = '<div class="notice">Could not load your account history' +
            (res.status === 0 ? ' — make sure the backend is running.' : '.') +
            ' <button class="btn btn-secondary btn-sm" type="button" id="accountHistoryRetry" style="margin-left:8px">Try again</button></div>';
          var retry = $('#accountHistoryRetry');
          if (retry) retry.addEventListener('click', function () { offset = 0; accumulated = []; load(false); });
          return;
        }
        accumulated = append ? accumulated.concat(res.data.interviews) : res.data.interviews;
        renderList(res.data.total);
      });
    }
    load(false);
  }

  /* ---------------- 4. Progress analytics ---------------- */
  pages.analytics = function () {
    var all = P.completed();
    var unlocked = P.achievementState().filter(function (a) { return a.date; });
    var missed = P.attempts.filter(function (a) { return a.status === 'missed'; });
    var range = 'all';

    function windowed() {
      if (range === 'all') return all;
      var cut = new Date(P.ref); cut.setDate(cut.getDate() - parseInt(range, 10));
      return all.filter(function (a) { return a.d >= cut; });
    }
    function markersFor(list) {
      if (!list.length) return [];
      var lo = list[0].d, hi = list[list.length - 1].d, out = [];
      unlocked.forEach(function (a) {
        var d = P.parse(a.date);
        if (d >= lo && d <= hi) out.push({ date: d, kind: 'ach', lines: [a.title] });
      });
      missed.forEach(function (a) {
        if (a.d >= lo && a.d <= hi) out.push({ date: a.d, kind: 'miss', lines: [P.name(a) + ' · no score recorded'] });
      });
      return out;
    }
    var chart = createChart($('#chart'), { points: [], height: 340, trend: true });

    function draw() {
      var list = windowed(), n = list.length;
      var latest = n ? list[n - 1].score : null;
      var best = n ? Math.max.apply(null, list.map(function (a) { return a.score; })) : null;
      var delta = n > 1 ? list[n - 1].score - list[0].score : null;
      $('#metrics').innerHTML =
        metric('Latest Score', n ? latest : '—', n ? P.fmt(list[n - 1].date, true) : 'No attempts in this period') +
        metric('Highest Score', n ? best : '—', n ? 'out of 100' : '') +
        metric('Improvement Since First Attempt', delta == null ? '—' : signed(delta),
          delta == null ? 'Needs two attempts' : 'points · ' + list[0].score + ' → ' + list[n - 1].score,
          delta == null ? '' : delta >= 0 ? 'pos' : 'neg');
      chart.update({ points: P.toPoints(list), markers: markersFor(list) });

      var suffix = range === 'all' ? '' : ' in this period';
      var text;
      if (delta == null) text = 'Complete at least two interviews in this period to see your progress.';
      else if (delta > 0) text = 'Your score increased by ' + delta + ' points between your first and latest attempts' + suffix + '.';
      else if (delta < 0) text = 'Your score decreased by ' + Math.abs(delta) + ' points between your first and latest attempts' + suffix + '.';
      else text = 'Your score has not changed between your first and latest attempts' + suffix + '.';
      $('#summary').textContent = text;
    }
    $$('#range button').forEach(function (b) {
      b.addEventListener('click', function () {
        range = b.getAttribute('data-range');
        $$('#range button').forEach(function (x) { x.setAttribute('aria-pressed', x === b); });
        draw();
      });
    });

    var improved = P.skills.filter(function (s) { return s.change >= 5; })
      .sort(function (a, b) { return b.change - a.change; }).slice(0, 3);
    $('#improved').innerHTML = improved.map(function (s) {
      return '<li><span>' + s.name + '</span><span class="row-change pos" style="width:auto">' + icon('arrow-up', 14) + s.change + ' pts</span></li>';
    }).join('');
    var focus = P.skills.slice().sort(function (a, b) { return a.score - b.score; }).slice(0, 2);
    $('#focus').innerHTML = focus.map(function (s) {
      return '<li><span><strong>' + s.name + '</strong><br><span class="muted">' + s.tip + '</span></span>' +
        '<a class="link" href="practice.html?focus=' + s.key + '">Practice</a></li>';
    }).join('');
    draw();
    renderRecommendations();
    renderAccountAnalytics();
  };

  /* Account analytics (Phase 10) - calculated server-side from the signed-in
     account's own completed interviews and evaluated answers, entirely
     separate from the sample P.skills-driven metrics/chart/two-col above.
     Free and read-only, so (like recommendations) it loads automatically. */
  function renderAccountAnalytics() {
    var body = $('#account-analytics-body');
    if (!body) return;
    body.innerHTML = '<p class="muted">Loading your analytics…</p>';
    window.PREP_API.getAnalytics().then(function (res) {
      if (res.status === 401) {
        body.innerHTML = '<div class="notice">Sign in on the <a class="link" href="settings.html">Settings</a> page to see analytics calculated from your own account.</div>';
        return;
      }
      if (!res.ok || !res.data) {
        body.innerHTML = '<div class="notice">Could not load your analytics' +
          (res.status === 0 ? ' — make sure the backend is running.' : '.') +
          ' <button class="btn btn-secondary btn-sm" type="button" id="analyticsRetry" style="margin-left:8px">Try again</button></div>';
        var retry = $('#analyticsRetry');
        if (retry) retry.addEventListener('click', renderAccountAnalytics);
        return;
      }
      var d = res.data;
      if (d.evaluated_answers === 0) {
        body.innerHTML = '<p class="muted">' + (d.total_interviews === 0
          ? 'You haven’t completed any practice interviews on your account yet. <a class="link" href="practice.html">Start one now</a>.'
          : 'You have ' + d.total_interviews + ' interview(s) on your account, but none of your answers have been evaluated yet. Open a result and click "Evaluate with AI" to build up your analytics.') + '</p>';
        return;
      }
      var out = '<div class="metrics" style="margin-bottom:24px">' +
        metric('Average Score', d.average_score, 'across ' + d.evaluated_answers + ' evaluated answer' + (d.evaluated_answers === 1 ? '' : 's')) +
        metric('Highest Score', d.highest_score, 'out of 100') +
        metric('Most Recent Score', d.most_recent_score, 'out of 100') +
        metric('Completion Rate', d.completion_rate != null ? Math.round(d.completion_rate * 100) + '%' : '—',
          d.completed_interviews + ' of ' + d.total_interviews + ' interviews completed') +
        '</div>';

      var catEntries = Object.keys(d.by_category);
      if (catEntries.length) {
        out += '<div class="two-col" style="margin-bottom:24px"><div><h4 class="section-title">By Category</h4><ul class="plain-list">' +
          catEntries.map(function (cat) {
            var c = d.by_category[cat];
            return '<li><span>' + cap(cat) + '</span><span>' + c.average_score + ' / 100 <span class="muted">(' + c.count + ' evaluated)</span></span></li>';
          }).join('') + '</ul></div>';
        out += '<div><h4 class="section-title">By Dimension</h4><ul class="plain-list">' +
          Object.keys(d.by_dimension).map(function (field) {
            var dim = d.by_dimension[field];
            var tag = field === d.strongest_dimension ? ' <span class="row-change pos" style="width:auto">strongest</span>'
              : field === d.weakest_dimension ? ' <span class="row-change neg" style="width:auto">weakest</span>' : '';
            return '<li><span>' + esc(dim.label) + tag + '</span><span>' + dim.average + ' / ' + dim.max + '</span></li>';
          }).join('') + '</ul>' +
          (d.strongest_dimension ? '' : '<p class="muted" style="font-size:.8125rem;margin-top:8px">Evaluate a few more answers to see your strongest/weakest area highlighted.</p>') +
          '</div></div>';
      }

      out += '<div><h4 class="section-title" style="margin-bottom:12px">Score Progress</h4>';
      if (!d.progress_sufficient) {
        out += '<p class="muted">Evaluate at least 2 answers (on different occasions) to see a progress chart - right now there' +
          (d.progress.length === 0 ? ' are none yet.' : ' is only 1.') + '</p>';
      } else {
        out += '<div id="account-analytics-chart"></div>';
      }
      out += '</div>';
      body.innerHTML = out;

      if (d.progress_sufficient) {
        createChart($('#account-analytics-chart'), {
          points: d.progress.map(function (p) { return { date: new Date(p.evaluated_at), score: p.score }; }),
          height: 240,
          ariaLabel: 'Line chart of your evaluated-answer scores over time'
        });
      }
    });
  }

  /* Personalized recommendations (Phase 9) - read-only and free (this
     endpoint never calls an AI provider, so there is no cost concern in
     loading it automatically, unlike the per-question "Evaluate with AI"
     action elsewhere in the app). Requires being logged in; anonymous
     visitors get a clear sign-in prompt instead of an error. */
  function renderRecommendations() {
    var body = $('#recommendations-body');
    if (!body) return;
    body.innerHTML = '<p class="muted">Loading recommendations…</p>';
    window.PREP_API.getRecommendations().then(function (res) {
      if (res.status === 401) {
        body.innerHTML = '<div class="notice">Sign in on the <a class="link" href="settings.html">Settings</a> page to see recommendations based on your own evaluated answers.</div>';
        return;
      }
      if (!res.ok || !res.data) {
        body.innerHTML = '<div class="notice">Could not load recommendations' +
          (res.status === 0 ? ' — make sure the backend is running.' : '.') +
          ' <button class="btn btn-secondary btn-sm" type="button" id="recoRetry" style="margin-left:8px">Try again</button></div>';
        var retry = $('#recoRetry');
        if (retry) retry.addEventListener('click', renderRecommendations);
        return;
      }
      var recs = res.data.recommendations || [];
      if (!recs.length) {
        body.innerHTML = '<p class="muted">No specific recommendations right now — your evaluated results look solid across the board. Keep practising to build more history.</p>';
        return;
      }
      body.innerHTML = '<ul class="plain-list">' + recs.map(function (r) {
        var badgeClass = r.priority === 'high' ? 'neg' : r.priority === 'medium' ? '' : 'pos';
        var evidenceLine = r.evidence_level === 'generic'
          ? '<span class="muted" style="font-style:italic">General suggestion — not enough history yet for a specific one.</span>'
          : (r.evidence.length ? '<span class="muted">' + r.evidence.map(esc).join(' · ') + '</span>' : '');
        return '<li style="align-items:flex-start">' +
          '<span><strong>' + esc(r.title) + '</strong><br><span class="muted">' + esc(r.explanation) + '</span><br>' + evidenceLine +
          '<br><span>Next: ' + esc(r.action) + '</span></span>' +
          '<span class="row-change ' + badgeClass + '" style="width:auto">' + esc(r.priority) + '</span></li>';
      }).join('') + '</ul><div class="actions" style="margin-top:16px"><a class="btn btn-primary" href="practice.html">Start a Practice Interview</a></div>';
    });
  }

  /* ---------------- 5. Achievements ---------------- */
  pages.achievements = function () {
    var state = P.achievementState();
    var unlocked = state.filter(function (a) { return a.date; });
    var locked = state.filter(function (a) { return !a.date; });
    var featured = unlocked.slice().sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : 0; }).slice(0, 3);
    var rest = unlocked.filter(function (a) { return featured.indexOf(a) < 0; })
      .sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });

    $('#featured').innerHTML = featured.map(function (a) {
      return '<div class="feat">' + icon(a.icon, 22) + '<div class="row-title">' + a.title + '</div>' +
        '<div class="row-sub">' + a.desc + '</div><div class="row-sub">' + P.fmt(a.date, true) + '</div></div>';
    }).join('');
    function row(a, isLocked) {
      return '<div class="ach-row' + (isLocked ? ' locked' : '') + '">' + icon(isLocked ? 'lock' : a.icon, 20) +
        '<div><div class="row-title">' + a.title + '</div><div class="row-sub">' + a.desc + '</div></div>' +
        '<span class="ach-date">' + (isLocked ? (a.progress || 'Locked') : P.fmt(a.date, true)) + '</span></div>';
    }
    $('#unlocked').innerHTML = rest.map(function (a) { return row(a, false); }).join('');
    $('#locked').innerHTML = locked.map(function (a) { return row(a, true); }).join('');
  };

  /* ---------------- 6. Improvement plan ---------------- */
  pages.plan = function () {
    $('#skills').innerHTML = P.skills.map(function (s) {
      return '<div class="skill"><span class="row-title">' + s.name + '</span>' +
        '<div class="bar" role="progressbar" aria-label="' + s.name + '" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + s.score + '"><span style="width:' + s.score + '%"></span></div>' +
        '<strong>' + s.score + '</strong>' + changeHTML(s.change) + '</div>';
    }).join('');
    $('#actions').innerHTML = P.actions.map(function (a) {
      return '<div class="action"><span class="priority">' + a.priority + '</span><span class="row-title">' + a.title + '</span>' +
        '<span class="muted">' + a.minutes + ' min</span>' +
        '<a class="btn btn-outline btn-sm" href="practice.html?focus=' + a.focus + '">Practice</a></div>';
    }).join('');
    $('#mistakes').innerHTML = P.feedback.mistakes.map(function (m) { return '<li>' + esc(m) + '</li>'; }).join('');
    $('#notes').innerHTML = P.feedback.notes.map(function (n) {
      return '<div><div class="row-title">' + esc(n.skill) + '</div><p class="muted">' + esc(n.text) + '</p></div>';
    }).join('');
  };

  /* ---------------- 7. Detailed results ---------------- */
  pages.results = function () {
    var sessionParam = new URLSearchParams(location.search).get('session');
    if (sessionParam) { renderBackendSession(sessionParam); return; }
    var id = new URLSearchParams(location.search).get('id');
    var a = P.attempts.filter(function (x) { return x.id === id; })[0];
    if (!a) { var c = P.completed(); a = c[c.length - 1]; }
    var out = '<div><div class="eyebrow">Interview Results</div><h2 class="page-heading" style="margin-top:6px">' + P.name(a) +
      '</h2><p class="subtle">' + P.fmt(a.date, true) + '</p></div>';

    if (a.status !== 'completed') {
      out += '<div class="notice">' + (a.status === 'incomplete'
        ? 'You ended this interview after answering ' + a.answered + ' of ' + a.total + ' questions, so it has no score.'
        : 'This interview was missed, so there are no results to show.') + '</div>';
    } else {
      var d = P.details[a.id], prev = P.previousCompleted(a), ch = P.changeFor(a);
      var cmp = prev
        ? '<span class="' + (ch >= 0 ? 'pos' : 'neg') + '">' + (ch === 0 ? 'No change' : signed(ch) + ' points') + '</span> compared with your previous attempt (' + P.fmt(prev.date, true) + ', ' + prev.score + ')'
        : 'This was your first completed attempt.';
      if (d) {
        out += '<div class="score-row"><div class="big-score">' + a.score + '<span>/ 100</span></div>' +
          '<div class="score-meta">' + resultHTML(a) + '<p>' + cmp + '</p></div></div>' +
          '<div class="two-col"><div><h3 class="section-title">Strengths</h3><ul class="bullets">' +
          d.strengths.map(function (t) { return '<li>' + t + '</li>'; }).join('') + '</ul></div>' +
          '<div><h3 class="section-title">Areas to improve</h3><ul class="bullets">' +
          d.improvements.map(function (t) { return '<li>' + t + '</li>'; }).join('') + '</ul></div></div>' +
          '<div><h3 class="section-title">Question-by-question feedback</h3><div class="qa-list">' +
          d.questions.map(function (q, i) {
            return '<details class="qa"><summary><span class="muted">Q' + (i + 1) + '</span><span class="row-title">' + esc(q.q) +
              '</span><strong>' + q.score + '</strong><span class="chev">' + icon('chevron', 16) + '</span></summary>' +
              '<div class="qa-body">' + esc(q.fb) + '</div></details>';
          }).join('') + '</div></div>';
      } else {
        // A Phase 3/4 demo attempt: show the real questions/answers and a clearly labeled, non-AI demo score.
        var sourceNote = a.source === 'backend'
          ? 'This result uses a sample/demo score — a simple word-count heuristic for this prototype phase, not an AI evaluation of your answers. Your answers were submitted to and stored by the local FastAPI backend during this session.'
          : 'This result uses a sample/demo score — a simple word-count heuristic for this prototype phase, not an AI evaluation of your answers. This attempt was kept only in this browser; the backend was not used (or was unavailable) for this session.';
        out += '<div class="notice">' + sourceNote + '</div>' +
          '<div class="score-row"><div class="big-score">' + a.score + '<span>/ 100 (demo)</span></div>' +
          '<div class="score-meta">' + resultHTML(a) + '<p>' + cmp + '</p></div></div>' +
          '<div><h3 class="section-title">Your Answers (Demo Submission)</h3><div class="qa-list">' +
          (a.qa || []).map(function (q, i) {
            var answered = !!(q.a && q.a.trim());
            return '<details class="qa"><summary><span class="muted">Q' + (i + 1) + '</span><span class="row-title">' + esc(q.q) +
              '</span><span></span><span class="chev">' + icon('chevron', 16) + '</span></summary>' +
              '<div class="qa-body">' + (answered ? esc(q.a) : '<em>No answer submitted.</em>') +
              evalBlock(a.sessionId, q, i, answered) + '</div></details>';
          }).join('') + '</div></div>';
      }
    }
    out += '<div class="actions"><a class="btn btn-primary" href="practice.html?focus=weak">Practise Weak Areas</a>' +
      '<a class="btn btn-secondary" href="history.html">Back to Interview History</a></div>';
    $('#result').innerHTML = out;
    wireEvaluateButtons();
  };

  /* Server-persisted interview results (Phase 10), reached via
     results.html?session=<real backend session_id> - used by the new
     "Your Account History" list on history.html. Completely separate
     from the ?id=<localStorage demoId> path above, which is untouched. */
  function renderBackendSession(sessionId) {
    $('#result').innerHTML = '<p class="muted">Loading your interview…</p>';
    window.PREP_API.getInterview(sessionId).then(function (res) {
      if (res.status === 401 || res.status === 404) {
        $('#result').innerHTML = '<div class="notice">This interview could not be found, or you don’t have access to it. <a class="link" href="history.html">Back to Interview History</a></div>';
        return;
      }
      if (!res.ok || !res.data) {
        $('#result').innerHTML = '<div class="notice">Could not load this interview' +
          (res.status === 0 ? ' — make sure the backend is running.' : '.') + ' <a class="link" href="history.html">Back to Interview History</a></div>';
        return;
      }
      var data = res.data;
      var evaluated = data.questions.filter(function (q) { return q.evaluation; });
      var avg = evaluated.length
        ? Math.round(evaluated.reduce(function (s, q) { return s + q.evaluation.total_score; }, 0) / evaluated.length * 10) / 10
        : null;
      var out = '<div><div class="eyebrow">Interview Results</div><h2 class="page-heading" style="margin-top:6px">' +
        cap(data.category) + ' Interview — ' + esc(data.role) + '</h2>' +
        '<p class="subtle">' + cap(data.difficulty) + ' difficulty · ' + (data.status === 'completed' ? 'Completed' : 'In progress') + '</p></div>';
      out += '<div class="notice">Saved to your account on the server. Any score shown is an AI-generated estimate for practice, never an objective evaluation - see each question for the full breakdown.</div>';
      if (avg != null) {
        out += '<div class="score-row"><div class="big-score">' + avg + '<span>/ 100 average</span></div>' +
          '<div class="score-meta"><p class="muted">Average across ' + evaluated.length + ' of ' + data.questions.length + ' evaluated question(s)</p></div></div>';
      }
      out += '<div><h3 class="section-title">Questions &amp; Answers</h3><div class="qa-list">' +
        data.questions.map(function (q, i) {
          var answered = !!(q.answer && q.answer.trim());
          var body = answered ? esc(q.answer) : '<em>No answer submitted.</em>';
          body += q.evaluation ? renderEvaluation(q.evaluation) : evalBlock(sessionId, { id: q.id }, i, answered);
          return '<details class="qa"><summary><span class="muted">Q' + (i + 1) + '</span><span class="row-title">' + esc(q.text) +
            '</span><strong>' + (q.evaluation ? q.evaluation.total_score : '') + '</strong><span class="chev">' + icon('chevron', 16) + '</span></summary>' +
            '<div class="qa-body">' + body + '</div></details>';
        }).join('') + '</div></div>';
      out += '<div class="actions"><a class="btn btn-secondary" href="history.html">Back to Interview History</a></div>';
      $('#result').innerHTML = out;
      wireEvaluateButtons();
    });
  }

  /* AI answer evaluation (Phase 8) - an explicit per-question action, never
     automatic, so viewing results never silently triggers a paid AI call. */
  function evalBlock(sessionId, q, i, answered) {
    if (!sessionId || !q.id || !answered) return '';
    return '<div class="eval-box" style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border)" data-eval-box="' + i + '">' +
      '<button class="btn btn-secondary btn-sm eval-btn" type="button" data-session="' + esc(sessionId) + '" data-question="' + esc(q.id) + '" data-index="' + i + '">Evaluate with AI</button>' +
      '<p class="hint" data-eval-hint="' + i + '"></p>' +
      '<div data-eval-result="' + i + '"></div></div>';
  }
  var DEFAULT_EVAL_NOTE = 'AI-generated estimate for practice purposes - not an objective or official assessment.';
  function renderEvaluation(ev) {
    function list(items) { return '<ul class="bullets">' + items.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul>'; }
    return '<div class="score-row"><div class="big-score" style="font-size:2.5rem">' + ev.total_score + '<span>/ 100</span></div>' +
      '<div class="score-meta"><p class="muted">' + esc(ev.note || DEFAULT_EVAL_NOTE) + '</p></div></div>' +
      '<div class="eval-dims">' +
        '<span><strong>' + ev.relevance_score + '</strong>/30 Relevance</span>' +
        '<span><strong>' + ev.correctness_score + '</strong>/35 Correctness</span>' +
        '<span><strong>' + ev.completeness_score + '</strong>/25 Completeness</span>' +
        '<span><strong>' + ev.clarity_score + '</strong>/10 Clarity</span>' +
      '</div>' +
      '<p>' + esc(ev.relevance_assessment) + '</p><p>' + esc(ev.correctness_assessment) + '</p>' +
      '<p class="muted">' + esc(ev.explanation) + '</p>' +
      '<div class="two-col" style="gap:24px"><div><h4 class="section-title">Strengths</h4>' + list(ev.strengths) + '</div>' +
      '<div><h4 class="section-title">Areas to improve</h4>' + list(ev.weaknesses) + '</div></div>' +
      '<div style="margin-top:16px"><h4 class="section-title">Suggestions</h4>' + list(ev.suggestions) + '</div>' +
      (ev.example_answer ? '<div style="margin-top:16px"><h4 class="section-title">A stronger example answer</h4><p class="muted">' + esc(ev.example_answer) + '</p></div>' : '');
  }
  function wireEvaluateButtons() {
    var result = $('#result');
    if (!result || result.dataset.evalWired) return;
    result.dataset.evalWired = '1';
    result.addEventListener('click', function (e) {
      var btn = e.target.closest('.eval-btn');
      if (!btn || btn.disabled) return;
      var sessionId = btn.getAttribute('data-session'), questionId = btn.getAttribute('data-question'),
          idx = btn.getAttribute('data-index');
      var hint = $('[data-eval-hint="' + idx + '"]'), resultEl = $('[data-eval-result="' + idx + '"]');
      btn.disabled = true;
      btn.textContent = 'Evaluating…';
      hint.textContent = '';
      window.PREP_API.evaluateAnswer(sessionId, questionId).then(function (res) {
        if (res.ok && res.data) {
          btn.hidden = true;
          resultEl.innerHTML = renderEvaluation(res.data);
          return;
        }
        btn.disabled = false;
        btn.textContent = 'Evaluate with AI';
        if (res.status === 0) hint.textContent = 'Could not reach the server. Make sure the backend is running.';
        else if (res.status === 503) hint.textContent = formatApiError(res.data) || 'AI evaluation is not available right now.';
        else if (res.status === 409) hint.textContent = formatApiError(res.data) || 'This question has not been answered.';
        else hint.textContent = formatApiError(res.data) || 'Evaluation failed. Please try again.';
      });
    });
  }

  /* ---------------- 8. Settings ---------------- */
  var DEFAULTS = {
    defaultType: 'Mixed', questionCount: '5', showTimer: true, role: 'Software Engineer', level: 'Mid-level',
    answerMode: 'Text', readAloud: false, remind: true, remindFreq: 'Weekly', weeklySummary: true,
    saveRecordings: false, shareUsage: false, textSize: 'default', reduceMotion: false
  };
  function checkBackendStatus() {
    var box = $('#backend-status'), text = $('#backend-status-text');
    if (!box || !text) return;
    window.PREP_API.health().then(function (res) {
      var ok = res.ok && res.data && res.data.status === 'ok';
      box.className = 'notice ' + (ok ? 'is-ok' : 'is-down');
      text.textContent = ok ? 'Backend connected' : 'Backend unavailable';
    });
  }

  function initAccountSection() {
    var loggedOut = $('#account-loggedout'), loggedIn = $('#account-loggedin'),
        emailInput = $('#authEmail'), passwordInput = $('#authPassword'), hint = $('#authHint'),
        registerBtn = $('#authRegisterBtn'), loginBtn = $('#authLoginBtn'), logoutBtn = $('#authLogoutBtn'),
        emailLabel = $('#accountEmail');
    if (!emailInput) return; // this page has no account section

    function showLoggedIn(email) {
      loggedOut.hidden = true;
      loggedIn.hidden = false;
      emailLabel.textContent = email;
    }
    function showLoggedOut() {
      loggedOut.hidden = false;
      loggedIn.hidden = true;
      passwordInput.value = '';
    }
    function setBusy(busy) {
      registerBtn.disabled = busy;
      loginBtn.disabled = busy;
    }
    function showError(res, fallback) {
      setBusy(false);
      hint.textContent = res.status === 0
        ? 'Could not reach the server. Make sure the backend is running.'
        : (formatApiError(res.data) || fallback);
    }

    registerBtn.addEventListener('click', function () {
      hint.textContent = '';
      setBusy(true);
      window.PREP_API.register(emailInput.value, passwordInput.value).then(function (res) {
        if (res.ok) { setBusy(false); showLoggedIn(res.data.email); }
        else showError(res, 'Could not create an account with those details.');
      });
    });

    loginBtn.addEventListener('click', function () {
      hint.textContent = '';
      setBusy(true);
      window.PREP_API.login(emailInput.value, passwordInput.value).then(function (res) {
        if (res.ok) { setBusy(false); showLoggedIn(res.data.email); }
        else showError(res, 'Could not log in with those details.');
      });
    });

    logoutBtn.addEventListener('click', function () {
      logoutBtn.disabled = true;
      window.PREP_API.logout().then(function () {
        logoutBtn.disabled = false;
        showLoggedOut();
      });
    });

    window.PREP_API.me().then(function (res) {
      if (res.ok && res.data) showLoggedIn(res.data.email);
      else showLoggedOut();
    });
  }

  pages.settings = function () {
    checkBackendStatus();
    initAccountSection();
    var saved = Object.assign({}, DEFAULTS, window.PREP_SETTINGS());
    var form = $('#settings-form');
    Object.keys(DEFAULTS).forEach(function (k) {
      var f = form.elements[k];
      if (!f) return;
      if (f.type === 'checkbox') f.checked = !!saved[k]; else f.value = saved[k];
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var next = {};
      Object.keys(DEFAULTS).forEach(function (k) {
        var f = form.elements[k];
        next[k] = f.type === 'checkbox' ? f.checked : f.value;
      });
      try { localStorage.setItem('prepai.settings', JSON.stringify(next)); } catch (err) { /* storage unavailable */ }
      window.applyDisplaySettings(next);
      var msg = $('#saved');
      msg.hidden = false;
      setTimeout(function () { msg.hidden = true; }, 2500);
    });
  };

  window.PREP_PAGES = pages;
})();
