/* ==========================================================
   App shell: sidebar navigation, mobile menu, saved display
   settings, then runs the logic for the current page.
   ========================================================== */
(function () {
  var NAV = [
    ['index.html',        'Dashboard',          'dashboard'],
    ['practice.html',     'Practice Interview', 'mic'],
    ['history.html',      'Interview History',  'history'],
    ['analytics.html',    'Progress Analytics', 'chart'],
    ['achievements.html', 'Achievements',       'award'],
    ['plan.html',         'Improvement Plan',   'target'],
    ['settings.html',     'Settings',           'settings']
  ];

  window.PREP_SETTINGS = function () {
    try { return JSON.parse(localStorage.getItem('prepai.settings')) || {}; } catch (e) { return {}; }
  };
  window.applyDisplaySettings = function (s) {
    var sizes = { 'default': '100%', large: '112.5%', larger: '125%' };
    document.documentElement.style.fontSize = sizes[s.textSize] || '100%';
    document.body.classList.toggle('reduce-motion', !!s.reduceMotion);
  };

  document.addEventListener('DOMContentLoaded', function () {
    var body = document.body;
    window.applyDisplaySettings(window.PREP_SETTINGS());

    var current = body.getAttribute('data-nav');
    var side = document.createElement('aside');
    side.className = 'sidebar';
    side.id = 'sidebar';
    side.setAttribute('aria-label', 'Main navigation');
    side.innerHTML = '<a class="brand" href="index.html"><span class="brand-mark">P</span>PrepAI</a><nav class="nav">' +
      NAV.map(function (n) {
        return '<a href="' + n[0] + '"' + (n[0] === current ? ' aria-current="page"' : '') + '>' + icon(n[2], 18) + n[1] + '</a>';
      }).join('') + '</nav>';
    var scrim = document.createElement('div');
    scrim.className = 'scrim';
    body.insertBefore(scrim, body.firstChild);
    body.insertBefore(side, body.firstChild);

    function setNav(open) { body.classList.toggle('nav-open', open); }
    var menu = document.getElementById('menu-btn');
    if (menu) menu.addEventListener('click', function () { setNav(!body.classList.contains('nav-open')); });
    scrim.addEventListener('click', function () { setNav(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setNav(false); });

    window.hydrateIcons();

    // Surface login/registration clearly from every page's topbar, not just
    // buried inside the Settings page's Account section - the settings.html
    // page itself already shows the full account UI, so it skips this.
    var tools = document.querySelector('.topbar-tools');
    if (tools && window.PREP_API && body.getAttribute('data-page') !== 'settings') {
      var accountLink = document.createElement('a');
      accountLink.className = 'btn btn-outline btn-sm';
      accountLink.href = 'settings.html#account-section';
      accountLink.textContent = 'Log In';
      tools.appendChild(accountLink);
      window.PREP_API.me().then(function (res) {
        if (res.ok && res.data && res.data.email) {
          accountLink.textContent = res.data.email;
          accountLink.title = 'Signed in - manage your account';
        } else {
          accountLink.textContent = 'Log In';
          accountLink.title = 'Sign in or create an account';
        }
      });
    }

    var run = window.PREP_PAGES && window.PREP_PAGES[body.getAttribute('data-page')];
    if (run) run();
  });
})();
