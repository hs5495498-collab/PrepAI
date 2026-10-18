/* ==========================================================
   Sample data for the prototype.
   Replace these objects with real assessment data from your backend.
   Every number shown in the UI (latest score, improvement, change
   indicators, achievements) is CALCULATED from this data.
   ========================================================== */
(function () {
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function parse(iso) {
    var p = iso.split('-').map(Number);
    return new Date(p[0], p[1] - 1, p[2]);
  }
  function fmt(v, withYear) {
    var d = typeof v === 'string' ? parse(v) : v;
    return d.getDate() + ' ' + MONTHS[d.getMonth()] + (withYear ? ' ' + d.getFullYear() : '');
  }
  function pad2(n) { return n < 10 ? '0' + n : '' + n; }
  function isoToday() {
    var d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }

  var P = { passMark: 60, fmt: fmt, parse: parse };

  /* status: completed | incomplete | missed.  Only completed attempts have a score. */
  P.attempts = [
    { id: 'a1', date: '2026-08-12', type: 'Technical',  status: 'completed',  score: 42 },
    { id: 'a2', date: '2026-08-20', type: 'Behavioral', status: 'completed',  score: 51 },
    { id: 'a3', date: '2026-08-28', type: 'Technical',  status: 'completed',  score: 47 },
    { id: 'a4', date: '2026-08-30', type: 'Behavioral', status: 'missed',     score: null },
    { id: 'a5', date: '2026-09-02', type: 'Technical',  status: 'incomplete', score: null, answered: 2, total: 5 },
    { id: 'a6', date: '2026-09-05', type: 'Behavioral', status: 'completed',  score: 65 },
    { id: 'a7', date: '2026-09-15', type: 'Technical',  status: 'completed',  score: 76 },
    { id: 'a8', date: '2026-09-25', type: 'Mixed',      status: 'completed',  score: 82 }
  ];
  P.attempts.forEach(function (a) { a.d = parse(a.date); });
  P.ref = P.attempts[P.attempts.length - 1].d; // date filters count back from the latest attempt

  /* ---------- Demo attempts created from the Phase 3 practice workflow ----------
     Stored in localStorage under 'prepai.demoAttempts'. These are real attempts the
     candidate just completed in this prototype (real questions, real typed answers),
     but any score shown for them is a simple non-AI heuristic, never fabricated feedback.
     Loading is defensive: anything malformed or missing required fields is dropped
     instead of crashing or corrupting the original sample attempts above. */
  function isValidDemoAttempt(a) {
    if (!a || typeof a !== 'object') return false;
    if (typeof a.id !== 'string' || a.id.indexOf('demo-') !== 0) return false;
    if (typeof a.date !== 'string' || isNaN(parse(a.date).getTime())) return false;
    if (typeof a.type !== 'string' || !a.type) return false;
    if (a.status === 'completed') {
      return typeof a.score === 'number' && a.score >= 0 && a.score <= 100 && Array.isArray(a.qa);
    }
    if (a.status === 'incomplete') {
      return typeof a.answered === 'number' && typeof a.total === 'number';
    }
    return false;
  }
  /* source tells the results page whether a completed attempt's answers were
     actually sent to the FastAPI backend ('backend') or stayed entirely in
     this browser ('offline') - defaults to 'offline' for attempts saved
     before this field existed, so old localStorage data keeps working. */
  function normalizeSource(a) { return a.source === 'backend' ? 'backend' : 'offline'; }
  function loadDemoAttempts() {
    var raw;
    try { raw = JSON.parse(localStorage.getItem('prepai.demoAttempts')); } catch (e) { return; }
    if (!Array.isArray(raw)) return;
    raw.forEach(function (a) {
      if (!isValidDemoAttempt(a)) return; // silently skip corrupted/foreign entries
      var attempt = { id: a.id, date: a.date, d: parse(a.date), type: a.type, status: a.status };
      if (a.status === 'completed') {
        attempt.score = a.score;
        attempt.qa = a.qa;
        attempt.source = normalizeSource(a);
      } else {
        attempt.score = null;
        attempt.answered = a.answered;
        attempt.total = a.total;
      }
      P.attempts.push(attempt);
    });
    if (P.attempts.length) P.ref = P.attempts[P.attempts.length - 1].d;
  }
  function persistDemoAttempts() {
    try {
      var toSave = P.attempts.filter(function (a) { return typeof a.id === 'string' && a.id.indexOf('demo-') === 0; })
        .map(function (a) {
          var out = { id: a.id, date: a.date, type: a.type, status: a.status };
          if (a.status === 'completed') { out.score = a.score; out.qa = a.qa; out.source = normalizeSource(a); }
          else { out.answered = a.answered; out.total = a.total; }
          return out;
        });
      localStorage.setItem('prepai.demoAttempts', JSON.stringify(toSave));
    } catch (e) { /* storage unavailable */ }
  }
  loadDemoAttempts();

  /* Creates and persists one new demo attempt, returns it (with its id) so the
     caller can redirect straight to its own results page. */
  P.addDemoAttempt = function (partial) {
    var attempt = {
      id: 'demo-' + Date.now() + '-' + Math.floor(Math.random() * 1000),
      date: isoToday(),
      type: partial.type || 'Practice',
      status: partial.status
    };
    attempt.d = parse(attempt.date);
    if (attempt.status === 'completed') {
      attempt.score = partial.score;
      attempt.qa = partial.qa || [];
      attempt.source = partial.source === 'backend' ? 'backend' : 'offline';
    } else {
      attempt.score = null;
      attempt.answered = partial.answered || 0;
      attempt.total = partial.total || 0;
    }
    P.attempts.push(attempt);
    P.ref = attempt.d;
    persistDemoAttempts();
    return attempt;
  };

  P.completed = function () {
    return P.attempts.filter(function (a) { return a.status === 'completed'; })
      .sort(function (x, y) { return x.d - y.d; });
  };
  P.name = function (a) { return a.type + ' Interview'; };
  P.result = function (a) {
    if (a.status === 'missed') return { key: 'missed', label: 'Missed' };
    if (a.status === 'incomplete') return { key: 'incomplete', label: 'Incomplete' };
    return a.score >= P.passMark ? { key: 'passed', label: 'Passed' } : { key: 'failed', label: 'Unsuccessful' };
  };
  /* Change versus the previous COMPLETED attempt (null when there is nothing to compare). */
  P.changeFor = function (a) {
    if (a.status !== 'completed') return null;
    var c = P.completed(), i = c.indexOf(a);
    return i > 0 ? a.score - c[i - 1].score : null;
  };
  P.previousCompleted = function (a) {
    var c = P.completed(), i = c.indexOf(a);
    return i > 0 ? c[i - 1] : null;
  };
  P.toPoints = function (list) {
    return list.map(function (a) { return { id: a.id, date: a.d, score: a.score }; });
  };

  /* ---------- Skills ---------- */
  P.skills = [
    { key: 'technical',     name: 'Technical Knowledge', score: 78, change: 12, tip: 'Revisit core concepts and practise explaining them out loud.' },
    { key: 'communication', name: 'Communication',       score: 74, change: 15, tip: 'Keep answers concise and explain ideas in simple terms.' },
    { key: 'problem',       name: 'Problem-Solving',     score: 69, change: 9,  tip: 'Talk through your reasoning step by step while solving problems.' },
    { key: 'structure',     name: 'Answer Structure',    score: 58, change: 22, tip: 'Improve answer structure by practising the STAR method.' },
    { key: 'relevance',     name: 'Answer Relevance',    score: 71, change: 4,  tip: 'Answer the question that was asked before adding extra detail.' }
  ];
  P.weakest = function () {
    return P.skills.slice().sort(function (a, b) { return a.score - b.score; })[0];
  };

  P.actions = [
    { priority: 'High',   title: 'Practise the STAR method',                         minutes: 15, focus: 'structure' },
    { priority: 'Medium', title: 'Explain a technical concept clearly',              minutes: 10, focus: 'communication' },
    { priority: 'Medium', title: 'Solve a problem while explaining your reasoning',  minutes: 20, focus: 'problem' }
  ];
  P.feedback = {
    mistakes: [
      'Answers start with the solution before giving any context.',
      'Examples rarely mention the measurable result.',
      'Longer answers drift away from the original question.'
    ],
    notes: [
      { skill: 'Answer Structure', text: 'Open with the situation in one sentence, describe your action, then close with the result. This was the biggest gain across your last three attempts.' },
      { skill: 'Problem-Solving',  text: 'You reach correct answers, but the reasoning is often unspoken. Say what you are checking and why.' }
    ]
  };

  /* ---------- Achievements ----------
     Each achievement is only "unlocked" when its test returns a date,
     i.e. when the condition is genuinely met by the data above. */
  P.achievements = [
    { id: 'first',  icon: 'flag',   title: 'First interview completed', desc: 'You finished your first practice interview.',
      test: function (c) { return c.length >= 1 ? c[0].date : null; } },
    { id: 'pass',   icon: 'check',  title: 'First passing score', desc: 'Scored 60 or higher for the first time.',
      test: function (c) { var x = c.filter(function (a) { return a.score >= 60; })[0]; return x ? x.date : null; } },
    { id: 'plus20', icon: 'chart',  title: 'Gained 20 points', desc: 'Raised your score by 20 points from your first attempt.',
      test: function (c) { var x = c.filter(function (a) { return a.score - c[0].score >= 20; })[0]; return x ? x.date : null; } },
    { id: 'five',   icon: 'star',   title: 'Five interviews completed', desc: 'Completed five scored interviews.',
      test: function (c) { return c.length >= 5 ? c[4].date : null; } },
    { id: 'e80',    icon: 'trophy', title: 'Scored 80 or higher', desc: 'Reached a score of 80 or more.',
      test: function (c) { var x = c.filter(function (a) { return a.score >= 80; })[0]; return x ? x.date : null; } },
    { id: 'streak', icon: 'zap',    title: 'Three improvements in a row', desc: 'Each of three consecutive attempts beat the one before.',
      test: function (c) {
        for (var i = 3; i < c.length; i++) {
          if (c[i].score > c[i - 1].score && c[i - 1].score > c[i - 2].score && c[i - 2].score > c[i - 3].score) return c[i].date;
        }
        return null;
      } },
    { id: 'ten',    icon: 'award',  title: 'Ten interviews completed', desc: 'Complete ten scored interviews.',
      test: function (c) { return c.length >= 10 ? c[9].date : null; },
      progress: function (c) { return c.length + ' of 10 completed'; } },
    { id: 'e90',    icon: 'trophy', title: 'Scored 90 or higher', desc: 'Reach a score of 90 or more.',
      test: function (c) { var x = c.filter(function (a) { return a.score >= 90; })[0]; return x ? x.date : null; },
      progress: function (c) { return 'Best so far: ' + Math.max.apply(null, c.map(function (a) { return a.score; })); } }
  ];
  P.achievementState = function () {
    var c = P.completed();
    return P.achievements.map(function (a) {
      return { id: a.id, icon: a.icon, title: a.title, desc: a.desc, date: a.test(c), progress: a.progress ? a.progress(c) : '' };
    });
  };

  /* ---------- Detailed results (one entry per completed attempt) ---------- */
  var TIER = {
    low:  { s: ['Calm, steady delivery', 'Correct use of basic terminology'],
            i: ['Explain the reasoning behind each choice', 'Cover the full picture before going into detail'] },
    mid:  { s: ['Clear examples that support your points', 'Good grasp of the core concepts'],
            i: ['Keep answers shorter and closer to the question', 'Quantify the results of your examples'] },
    high: { s: ['Well-structured answers with a clear conclusion', 'Strong, accurate explanations'],
            i: ['Add a short summary to longer answers', 'Mention trade-offs when comparing options'] }
  };
  function tier(score) { return score >= 80 ? TIER.high : score >= 60 ? TIER.mid : TIER.low; }

  var Q = {
    a1: [['Explain the difference between a process and a thread.', 48, 'You named both terms but did not explain memory sharing, which is the key difference.'],
         ['How would you design a URL shortener?', 38, 'You jumped to storage choices before clarifying the requirements.'],
         ['What happens when you type a URL into a browser?', 40, 'You covered DNS and HTTP but skipped the connection and rendering steps.']],
    a2: [['Tell me about a time you faced a tight deadline.', 55, 'Good situation, but the actions you took were not clearly described.'],
         ['Describe a disagreement with a teammate.', 49, 'The answer focused on the conflict and not on how it was resolved.'],
         ['Tell me about a mistake you made.', 49, 'You took ownership, but did not say what you learned or changed.']],
    a3: [['What is the difference between SQL and NoSQL databases?', 50, 'Accurate definitions, but no examples of when to choose each.'],
         ['Explain how a hash map works.', 45, 'You described lookup, but not collisions or resizing.'],
         ['How would you debug a slow web page?', 46, 'A sensible first step, then the answer became unfocused.']],
    a6: [['Tell me about a time you led a project.', 70, 'Clear structure. Add the measurable result to finish strongly.'],
         ['Describe how you handle feedback.', 62, 'Relevant example, but the answer ran long.'],
         ['Tell me about a conflict you resolved.', 63, 'Good action steps; the outcome was left implicit.']],
    a7: [['Explain how indexing speeds up a database query.', 80, 'Accurate and well explained. A short example would make it memorable.'],
         ['How would you find duplicate entries in a large list?', 74, 'Correct approach; you could mention time complexity earlier.'],
         ['What makes an API well designed?', 74, 'Good points. Prioritise the two most important ones.']],
    a8: [['Why do you want this role?', 86, 'Specific, relevant, and well structured.'],
         ['Explain caching to a non-technical colleague.', 80, 'Clear analogy. Close with one sentence of summary.'],
         ['Walk me through how you would investigate a failing service.', 80, 'Logical steps with reasoning. Mention how you would confirm the fix.']]
  };
  P.details = {};
  Object.keys(Q).forEach(function (id) {
    var a = P.attempts.filter(function (x) { return x.id === id; })[0];
    P.details[id] = {
      strengths: tier(a.score).s,
      improvements: tier(a.score).i,
      questions: Q[id].map(function (q) { return { q: q[0], score: q[1], fb: q[2] }; })
    };
  });

  /* ---------- Practice question bank ---------- */
  P.bank = [
    { skill: 'structure',     q: 'Tell me about a time you disagreed with a teammate and how you resolved it.' },
    { skill: 'technical',     q: 'Explain the difference between a process and a thread.' },
    { skill: 'problem',       q: 'How would you find duplicate entries in a very large list? Talk through your reasoning.' },
    { skill: 'communication', q: 'Explain how an API works to someone with no technical background.' },
    { skill: 'relevance',     q: 'Why do you want this role, and what makes you a good fit for it?' },
    { skill: 'structure',     q: 'Describe a project you are proud of, from start to finish.' },
    { skill: 'technical',     q: 'What is the difference between SQL and NoSQL databases?' },
    { skill: 'problem',       q: 'A web page loads slowly. How would you find the cause?' },
    { skill: 'structure',     q: 'Tell me about a time you handled a tight deadline.' },
    { skill: 'communication', q: 'Describe a complex idea you recently explained to a colleague.' },
    { skill: 'relevance',     q: 'Tell me about your most relevant experience for this role.' },
    { skill: 'technical',     q: 'How does caching improve performance, and what are its risks?' },
    { skill: 'problem',       q: 'You inherit code with no tests. How do you start making changes safely?' }
  ];
  P.mixedOrder = [0, 1, 2, 3, 4, 5, 6, 7];

  /* ---------- Phase 3 demo interview question bank ----------
     Deliberately small (6 per category) and clearly sample data. Each category
     gives 2 questions per difficulty; if more questions are requested than exist
     for that difficulty, the practice session cycles through them again rather
     than inventing new ones. */
  P.demoQuestions = {
    technical: [
      { d: 'easy',   q: 'What is the difference between a list/array and a tuple, and when would you use each?' },
      { d: 'easy',   q: 'What does API stand for, and what problem does it solve?' },
      { d: 'medium', q: 'Explain the difference between == and === (or similar value vs strict equality) in a language you know.' },
      { d: 'medium', q: 'What is a database index, and why does it speed up queries?' },
      { d: 'hard',   q: 'How would you design a simple rate limiter for an API?' },
      { d: 'hard',   q: 'Explain how a hash table resolves collisions.' }
    ],
    hr: [
      { d: 'easy',   q: 'Tell me about yourself.' },
      { d: 'easy',   q: 'Why do you want to work here?' },
      { d: 'medium', q: 'What are your greatest strengths and weaknesses?' },
      { d: 'medium', q: 'Where do you see yourself in five years?' },
      { d: 'hard',   q: 'Why should we hire you over other candidates?' },
      { d: 'hard',   q: 'Describe a time you received difficult feedback. How did you respond?' }
    ],
    behavioral: [
      { d: 'easy',   q: 'Describe a time you worked as part of a team.' },
      { d: 'easy',   q: 'Tell me about a goal you set and how you achieved it.' },
      { d: 'medium', q: 'Tell me about a time you disagreed with a teammate and how you resolved it.' },
      { d: 'medium', q: 'Describe a situation where you had to meet a tight deadline.' },
      { d: 'hard',   q: 'Tell me about a time you failed. What did you learn?' },
      { d: 'hard',   q: 'Describe a time you had to persuade someone who disagreed with you.' }
    ]
  };

  window.PREP = P;
})();
