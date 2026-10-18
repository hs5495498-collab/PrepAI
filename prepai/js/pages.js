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

    var setupEl = $('#setup'), sessionEl = $('#session');
    var root = $('.practice'), qcount = $('#qcount'), sessionMode = $('#sessionMode'), bar = $('#pbar'),
        question = $('#question'), answer = $('#answer'), hint = $('#hint'), mic = $('#mic'), wave = $('#wave'),
        timer = $('#timer'), pauseBtn = $('#pause'), prevBtn = $('#prev'), nextBtn = $('#submit'),
        endBtn = $('#end');
    var setupRole = $('#setupRole'), setupCategory = $('#setupCategory'),
        setupDifficulty = $('#setupDifficulty'), setupCount = $('#setupCount'),
        setupHint = $('#setupHint'), setupStart = $('#setupStart'), setupOfflineStart = $('#setupOfflineStart');

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
      }
      setupEl.hidden = true;
      sessionEl.hidden = false;
      root.classList.remove('is-paused');
      pauseBtn.textContent = 'Pause';
      draw();
      startTimer();
    }

    function startOfflineInterview(role, category, difficulty, count) {
      var pool = (P.demoQuestions[category] || []).filter(function (q) { return q.d === difficulty; });
      if (!pool.length) pool = P.demoQuestions[category] || [];
      var picked = [];
      for (var k = 0; k < count && pool.length; k++) picked.push({ q: pool[k % pool.length].q });
      beginSession(picked, { role: role, category: category, difficulty: difficulty }, null);
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
              beginSession(picked, { role: role, category: category, difficulty: difficulty, questionSource: res.data.question_source }, res.data.session_id);
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
  };

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
  };

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

  /* AI answer evaluation (Phase 8) - an explicit per-question action, never
     automatic, so viewing results never silently triggers a paid AI call. */
  function evalBlock(sessionId, q, i, answered) {
    if (!sessionId || !q.id || !answered) return '';
    return '<div class="eval-box" style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border)" data-eval-box="' + i + '">' +
      '<button class="btn btn-secondary btn-sm eval-btn" type="button" data-session="' + esc(sessionId) + '" data-question="' + esc(q.id) + '" data-index="' + i + '">Evaluate with AI</button>' +
      '<p class="hint" data-eval-hint="' + i + '"></p>' +
      '<div data-eval-result="' + i + '"></div></div>';
  }
  function renderEvaluation(ev) {
    function list(items) { return '<ul class="bullets">' + items.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul>'; }
    return '<div class="score-row"><div class="big-score" style="font-size:2.5rem">' + ev.total_score + '<span>/ 100</span></div>' +
      '<div class="score-meta"><p class="muted">' + esc(ev.note) + '</p></div></div>' +
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
