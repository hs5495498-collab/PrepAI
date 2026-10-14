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
  pages.practice = function () {
    var params = new URLSearchParams(location.search);
    var settings = window.PREP_SETTINGS();
    var count = parseInt(settings.questionCount, 10) || 5;
    var focus = params.get('focus');
    if (focus === 'weak') focus = P.weakest().key;
    var skill = focus ? skillByKey(focus) : null;
    var list = skill
      ? P.bank.filter(function (b) { return b.skill === skill.key; }).slice(0, 3)
      : P.mixedOrder.slice(0, count).map(function (i) { return P.bank[i]; });

    var i = 0, seconds = 0, paused = false, recording = false, recorded = false;
    var root = $('.practice'), qcount = $('#qcount'), bar = $('#pbar'), question = $('#question'),
        answer = $('#answer'), hint = $('#hint'), mic = $('#mic'), wave = $('#wave'),
        timer = $('#timer'), pauseBtn = $('#pause');

    if (settings.showTimer === false) timer.hidden = true;

    function draw() {
      qcount.textContent = 'Question ' + (i + 1) + ' of ' + list.length + (skill ? ' · Focus: ' + skill.name : '');
      bar.style.width = (i / list.length * 100) + '%';
      question.textContent = list[i].q;
      answer.value = '';
      hint.textContent = '';
      setRecording(false);
      recorded = false;
    }
    function setRecording(on) {
      // NOTE: this is a visual-only prototype. Connect MediaRecorder / speech-to-text here.
      recording = on;
      mic.setAttribute('aria-pressed', on);
      $('.mic-label', mic).textContent = on ? 'Stop recording' : 'Record answer';
      wave.hidden = !on;
      if (!on && wave.dataset.used === '1') recorded = true;
      if (on) wave.dataset.used = '1';
    }
    function tick() {
      if (paused) return;
      seconds++;
      var m = Math.floor(seconds / 60), s = seconds % 60;
      timer.textContent = (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
    }
    setInterval(tick, 1000);

    mic.addEventListener('click', function () { setRecording(!recording); });
    $('#submit').addEventListener('click', function () {
      if (recording) setRecording(false);
      if (!answer.value.trim() && !recorded) {
        hint.textContent = 'Add a written or recorded answer before submitting.';
        return;
      }
      i++;
      if (i >= list.length) {
        bar.style.width = '100%';
        var c = P.completed();
        location.href = 'results.html?id=' + c[c.length - 1].id; // prototype: opens the latest sample result
        return;
      }
      wave.dataset.used = '0';
      draw();
    });
    pauseBtn.addEventListener('click', function () {
      paused = !paused;
      root.classList.toggle('is-paused', paused);
      pauseBtn.textContent = paused ? 'Resume' : 'Pause';
      if (paused && recording) setRecording(false);
    });
    $('#end').addEventListener('click', function () {
      if (window.confirm('End this interview? It will be saved as incomplete and will not receive a score.')) {
        location.href = 'history.html';
      }
    });
    draw();
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
  };

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
    }
    out += '<div class="actions"><a class="btn btn-primary" href="practice.html?focus=weak">Practise Weak Areas</a>' +
      '<a class="btn btn-secondary" href="history.html">Back to Interview History</a></div>';
    $('#result').innerHTML = out;
  };

  /* ---------------- 8. Settings ---------------- */
  var DEFAULTS = {
    defaultType: 'Mixed', questionCount: '5', showTimer: true, role: 'Software Engineer', level: 'Mid-level',
    answerMode: 'Text', readAloud: false, remind: true, remindFreq: 'Weekly', weeklySummary: true,
    saveRecordings: false, shareUsage: false, textSize: 'default', reduceMotion: false
  };
  pages.settings = function () {
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
