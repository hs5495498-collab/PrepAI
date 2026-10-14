/* ==========================================================
   Minimal SVG line chart (no libraries).
   createChart(container, {
     points:  [{ date: Date, score: 0-100 }],   // sorted by date
     markers: [{ date: Date, kind: 'ach'|'miss', lines: ['text'] }],  // optional
     trend:   true,                              // optional dashed trend line
     height:  320                                // optional
   })  ->  { update(partialOptions) }
   ========================================================== */
(function () {
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function fmt(d, y) { return d.getDate() + ' ' + MONTHS[d.getMonth()] + (y ? ' ' + d.getFullYear() : ''); }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function avg(a) { return a.reduce(function (x, y) { return x + y; }, 0) / a.length; }

  window.createChart = function (container, options) {
    var state = Object.assign({}, options);
    var tip = document.createElement('div');
    tip.className = 'chart-tip';
    tip.hidden = true;
    var lastW = 0;

    function showTip(html, cx, cy, W) {
      tip.innerHTML = html;
      tip.hidden = false;
      var half = tip.offsetWidth / 2;
      tip.style.left = Math.min(Math.max(cx, half + 4), W - half - 4) + 'px';
      tip.style.top = cy + 'px';
    }

    function render() {
      var o = state, pts = o.points || [];
      container.classList.add('chart');
      container.innerHTML = '';
      container.appendChild(tip);
      tip.hidden = true;
      if (!pts.length) {
        container.insertAdjacentHTML('beforeend', '<p class="empty">No completed interviews in this period.</p>');
        return;
      }

      var W = Math.max(container.clientWidth, 280);
      lastW = container.clientWidth;
      var H = o.height || (W < 520 ? 250 : 320);
      var markers = o.markers || [];

      // group markers that fall on the same day and kind
      var groups = {};
      markers.forEach(function (m) {
        var k = m.kind + m.date.getTime();
        if (!groups[k]) groups[k] = { kind: m.kind, date: m.date, lines: [] };
        groups[k].lines = groups[k].lines.concat(m.lines);
      });
      var mk = Object.keys(groups).map(function (k) { return groups[k]; });

      var m = { t: 14, r: 18, b: mk.length ? 66 : 38, l: 34 };
      var iw = W - m.l - m.r, ih = H - m.t - m.b, pad = 14;
      var t0 = pts[0].date.getTime(), t1 = pts[pts.length - 1].date.getTime();
      function x(d) { return t1 === t0 ? m.l + iw / 2 : m.l + pad + (d.getTime() - t0) / (t1 - t0) * (iw - 2 * pad); }
      function y(v) { return m.t + ih - (v / 100) * ih; }

      var s = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' +
        esc(o.ariaLabel || 'Line chart of interview scores over time') + '">';

      [0, 25, 50, 75, 100].forEach(function (v) {
        s += '<line class="grid" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y(v) + '" y2="' + y(v) + '"/>' +
             '<text class="axis-label" x="' + (m.l - 8) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + v + '</text>';
      });

      // x-axis labels: actual attempt dates, skipping any that would overlap
      var lastX = -999, yLabel = m.t + ih + 22;
      pts.forEach(function (p) {
        var px = x(p.date);
        if (px - lastX >= 54) {
          s += '<text class="axis-label" x="' + px + '" y="' + yLabel + '" text-anchor="middle">' + fmt(p.date) + '</text>';
          lastX = px;
        }
      });

      // trend line (simple linear regression over time)
      if (o.trend && pts.length >= 3) {
        var xs = pts.map(function (p) { return (p.date.getTime() - t0) / 864e5; });
        var ys = pts.map(function (p) { return p.score; });
        var mx = avg(xs), my = avg(ys), num = 0, den = 0;
        xs.forEach(function (v, i) { num += (v - mx) * (ys[i] - my); den += (v - mx) * (v - mx); });
        if (den > 0) {
          var slope = num / den, ic = my - slope * mx;
          var clamp = function (v) { return Math.max(0, Math.min(100, v)); };
          s += '<line class="trend" x1="' + x(pts[0].date) + '" y1="' + y(clamp(ic + slope * xs[0])) +
               '" x2="' + x(pts[pts.length - 1].date) + '" y2="' + y(clamp(ic + slope * xs[xs.length - 1])) + '"/>';
        }
      }

      // score line + points
      s += '<polyline class="line" points="' + pts.map(function (p) { return x(p.date) + ',' + y(p.score); }).join(' ') + '"/>';
      pts.forEach(function (p, i) {
        var cx = x(p.date), cy = y(p.score);
        s += '<g class="pt" tabindex="0" data-i="' + i + '" data-cx="' + cx + '" data-cy="' + cy + '" role="img" aria-label="' +
          fmt(p.date, true) + ': score ' + p.score + '">' +
          '<circle class="hit" cx="' + cx + '" cy="' + cy + '" r="16"/><circle class="dot" cx="' + cx + '" cy="' + cy + '" r="4.5"/></g>';
      });

      // timeline markers (below the axis so they never touch the score line)
      var yM = m.t + ih + 50;
      mk.forEach(function (g, i) {
        var cx = x(g.date);
        var shape = g.kind === 'ach'
          ? '<path class="mk-ach" d="M' + cx + ' ' + (yM - 6) + 'L' + (cx + 6) + ' ' + yM + 'L' + cx + ' ' + (yM + 6) + 'L' + (cx - 6) + ' ' + yM + 'Z"/>'
          : '<circle class="mk-miss" cx="' + cx + '" cy="' + yM + '" r="5"/>';
        s += '<g class="mk" tabindex="0" data-m="' + i + '" data-cx="' + cx + '" data-cy="' + yM + '" role="img" aria-label="' +
          esc((g.kind === 'ach' ? 'Achievement' : 'Missed interview') + ' on ' + fmt(g.date, true) + ': ' + g.lines.join(', ')) + '">' +
          '<circle class="hit" cx="' + cx + '" cy="' + yM + '" r="14"/>' + shape + '</g>';
      });
      s += '</svg>';
      container.insertAdjacentHTML('beforeend', s);

      container.querySelectorAll('.pt').forEach(function (g) {
        var p = pts[+g.getAttribute('data-i')];
        function show() {
          showTip('<strong>' + fmt(p.date, true) + '</strong><br>Score: ' + p.score,
            +g.getAttribute('data-cx'), +g.getAttribute('data-cy') - 8, W);
        }
        g.addEventListener('mouseenter', show);
        g.addEventListener('focus', show);
        g.addEventListener('click', show);
        g.addEventListener('mouseleave', function () { tip.hidden = true; });
        g.addEventListener('blur', function () { tip.hidden = true; });
      });
      container.querySelectorAll('.mk').forEach(function (g) {
        var grp = mk[+g.getAttribute('data-m')];
        function show() {
          showTip('<strong>' + (grp.kind === 'ach' ? 'Achievement' : 'Missed interview') + ' · ' + fmt(grp.date, true) + '</strong><br>' +
            grp.lines.map(esc).join('<br>'), +g.getAttribute('data-cx'), +g.getAttribute('data-cy') - 8, W);
        }
        g.addEventListener('mouseenter', show);
        g.addEventListener('focus', show);
        g.addEventListener('click', show);
        g.addEventListener('mouseleave', function () { tip.hidden = true; });
        g.addEventListener('blur', function () { tip.hidden = true; });
      });
    }

    container.addEventListener('click', function (e) {
      if (!e.target.closest || !e.target.closest('.pt, .mk')) tip.hidden = true;
    });
    if ('ResizeObserver' in window) {
      new ResizeObserver(function () {
        if (container.clientWidth !== lastW) render();
      }).observe(container);
    }
    render();
    return { update: function (partial) { Object.assign(state, partial); render(); } };
  };
})();
