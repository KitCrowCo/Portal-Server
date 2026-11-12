/* graph_view.js - interactive node/edge graph on a canvas, no dependencies. Any module can use it:
     <div class="graph-view" style="height:30rem"><script type="application/json">{"nodes":[{"id":"a","label":"A","type":"person","info":"text"}],"edges":[{"s":"a","t":"b","info":"text"}]}</script></div>
     <script src="/static/js/graph_view.js"></script><script>graphView(theBoxElement, {onOpen: function(node) {...}})</script>
   Layout (opts.layout): "force" (default) - pairwise repulsion, edge springs, gentle pull to the centre, animated until it settles, dragging a node wakes it again;
     "ring" - one circle, grouped by type, most linked first within a type; "rings" - concentric circles, the most linked nodes innermost. Ring layouts stay where they are put: dragging moves only the dragged node.
   Mouse / touch: drag the background to pan, the wheel or two fingers to zoom, drag a node to move it, tap a node to select it (its info and neighbours show), double-tap to call opts.onOpen(node).
   Colours: node types get distinct hues; edges and labels follow the portal theme (--accent, --text, --text_muted). */
window.graphView = window.graphView || function (box, opts) {
  opts = opts || {};
  var data = JSON.parse(box.querySelector('script[type="application/json"]').textContent);
  var cv = document.createElement('canvas'), info = document.createElement('div'), ctx = cv.getContext('2d'), dpr = window.devicePixelRatio || 1;
  cv.style.cssText = 'width:100%;height:100%;display:block;touch-action:none;cursor:grab';
  info.className = 'graph-view-info';
  info.style.cssText = 'position:absolute;top:.3rem;right:.3rem;max-width:min(22rem,60%);max-height:70%;overflow:auto;background:var(--bg_panel);border:var(--border-thick) solid var(--border);border-radius:var(--radius);padding:.3rem .5rem;font-size:.75rem;display:none';
  box.style.position = 'relative'; box.appendChild(cv); box.appendChild(info);
  var css = getComputedStyle(document.documentElement), accent = css.getPropertyValue('--accent').trim() || '#00d4ff', text = css.getPropertyValue('--text').trim() || '#ddd', muted = css.getPropertyValue('--text_muted').trim() || '#888';
  var N = data.nodes || [], idx = {};
  N.forEach(function (n, i) { var a = i * 2.39996, r = 12 * Math.sqrt(i + 1); idx[n.id] = i; n.x = Math.cos(a) * r; n.y = Math.sin(a) * r; n.vx = n.vy = 0; n.deg = 0; n.r = 4; });
  var E = (data.edges || []).filter(function (e) { return e.s in idx && e.t in idx && e.s !== e.t; });
  E.forEach(function (e) { e.a = N[idx[e.s]]; e.b = N[idx[e.t]]; e.a.deg++; e.b.deg++; });
  var hues = {}, view = {x: 0, y: 0, k: 1}, sel = null, near = {}, drag = null, pan = null, moved = 0, alpha = 1, lastTap = 0, pts = {}, dirty = true;   /* dirty: redraw on the next frame (idle graphs cost nothing) */
  var layout = opts.layout || 'force', physics = layout === 'force';
  function place(list, r0, gap) {   /* list onto concentric circles from radius r0, gap apart, about 14 units between neighbours; one circle when r0 already holds them all */
    var i = 0, r = r0;
    while (i < list.length) { var cap = Math.max(6, Math.floor(6.2832 * r / 14)), take = gap ? Math.min(cap, list.length - i) : list.length - i; for (var j = 0; j < take; j++) { var a = 6.2832 * j / take; list[i + j].x = Math.cos(a) * r; list[i + j].y = Math.sin(a) * r; } i += take; r += gap; }
  }
  if (layout === 'ring') place(N.slice().sort(function (a, b) { return String(a.type || '').localeCompare(String(b.type || '')) || b.deg - a.deg; }), Math.max(60, N.length * 14 / 6.2832), 0);
  if (layout === 'rings') place(N.slice().sort(function (a, b) { return b.deg - a.deg; }), 30, 40);
  function hue(t) { if (!(t in hues)) hues[t] = (Object.keys(hues).length * 137 + 190) % 360; return 'hsl(' + hues[t] + ',62%,56%)'; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function resize() { var w = box.clientWidth, h = box.clientHeight; cv.width = w * dpr; cv.height = h * dpr; }
  function step() {
    var i, j, a, b, dx, dy, d2, f, n = N.length;
    for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) {
      a = N[i]; b = N[j]; dx = a.x - b.x; dy = a.y - b.y; d2 = dx * dx + dy * dy + 0.01;
      if (d2 > 90000) continue;
      f = 220 * alpha / d2; a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
    }
    E.forEach(function (e) { var dx = e.b.x - e.a.x, dy = e.b.y - e.a.y, d = Math.sqrt(dx * dx + dy * dy) + 0.01, f = (d - 55) * 0.04 * alpha / d; e.a.vx += dx * f; e.a.vy += dy * f; e.b.vx -= dx * f; e.b.vy -= dy * f; });
    N.forEach(function (n) {
      if (n === drag) { n.vx = n.vy = 0; return; }
      n.vx -= n.x * 0.004 * alpha; n.vy -= n.y * 0.004 * alpha;
      var v = Math.sqrt(n.vx * n.vx + n.vy * n.vy); if (v > 25) { n.vx *= 25 / v; n.vy *= 25 / v; }
      n.x += n.vx; n.y += n.vy; n.vx *= 0.55; n.vy *= 0.55;
    });
    alpha = Math.max(0, alpha * 0.985 - 0.0005);
  }
  function fit() {
    if (!N.length) return;
    var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    N.forEach(function (n) { x0 = Math.min(x0, n.x); x1 = Math.max(x1, n.x); y0 = Math.min(y0, n.y); y1 = Math.max(y1, n.y); });
    view.k = Math.min(3, 0.9 * Math.min(box.clientWidth / (x1 - x0 + 40), box.clientHeight / (y1 - y0 + 40)));
    view.x = -(x0 + x1) / 2 * view.k; view.y = -(y0 + y1) / 2 * view.k;
  }
  function draw() {
    var w = box.clientWidth, h = box.clientHeight, k = view.k;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) resize();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * (w / 2 + view.x), dpr * (h / 2 + view.y));
    ctx.lineWidth = 1 / k; ctx.strokeStyle = muted; ctx.globalAlpha = sel ? 0.18 : 0.4;
    ctx.beginPath(); E.forEach(function (e) { ctx.moveTo(e.a.x, e.a.y); ctx.lineTo(e.b.x, e.b.y); }); ctx.stroke();
    if (sel) { ctx.globalAlpha = 0.9; ctx.strokeStyle = accent; ctx.lineWidth = 1.6 / k; ctx.beginPath(); E.forEach(function (e) { if (e.a === sel || e.b === sel) { ctx.moveTo(e.a.x, e.a.y); ctx.lineTo(e.b.x, e.b.y); } }); ctx.stroke(); }
    N.forEach(function (n) { n.r = 3 + Math.min(8, Math.sqrt(n.deg) * 1.6); ctx.globalAlpha = !sel || n === sel || near[n.id] ? 1 : 0.35; ctx.fillStyle = n === sel ? accent : hue(n.type || ''); ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 6.2832); ctx.fill(); });
    ctx.globalAlpha = 1; ctx.fillStyle = text; ctx.font = (11 / k) + 'px sans-serif';
    var lim = k > 1.6 ? 0 : k > 0.9 ? 3 : 7;
    N.forEach(function (n) { if (n.deg >= lim || n === sel || near[n.id]) ctx.fillText(n.label || n.id, n.x + n.r + 2 / k, n.y + 4 / k); });
  }
  function world(ev) { var b = cv.getBoundingClientRect(); return {x: (ev.clientX - b.left - box.clientWidth / 2 - view.x) / view.k, y: (ev.clientY - b.top - box.clientHeight / 2 - view.y) / view.k}; }
  function hit(p) { for (var i = N.length - 1; i >= 0; i--) { var n = N[i], dx = n.x - p.x, dy = n.y - p.y; if (dx * dx + dy * dy <= Math.pow(n.r + 4 / view.k, 2)) return n; } return null; }
  function select(n) {
    sel = n; near = {}; dirty = true;
    if (!n) { info.style.display = 'none'; return; }
    E.forEach(function (e) { if (e.a === n) near[e.b.id] = e; if (e.b === n) near[e.a.id] = e; });
    var rel = Object.keys(near).slice(0, 40).map(function (id) { var e = near[id]; return '<div><b>' + esc(N[idx[id]].label || id) + '</b>' + (e.info ? ' - ' + esc(e.info) : '') + '</div>'; }).join('');
    info.innerHTML = '<div style="font-weight:600;color:' + accent + '">' + esc(n.label || n.id) + '</div>' + (n.type ? '<div style="color:' + muted + '">' + esc(n.type) + ' - ' + n.deg + ' link(s)</div>' : '') + (n.info ? '<div style="white-space:pre-wrap;margin:.2rem 0">' + esc(n.info) + '</div>' : '') + (rel ? '<details><summary style="cursor:pointer">Linked</summary>' + rel + '</details>' : '') + (opts.onOpen ? '<div style="color:' + muted + ';margin-top:.2rem">Double-tap the node to centre the graph on it.</div>' : '');
    info.style.display = 'block';
  }
  cv.addEventListener('pointerdown', function (ev) {
    cv.setPointerCapture(ev.pointerId); pts[ev.pointerId] = {x: ev.clientX, y: ev.clientY}; moved = 0;
    if (Object.keys(pts).length > 1) { drag = null; pan = null; return; }
    var n = hit(world(ev));
    if (n) { drag = n; if (physics) alpha = Math.max(alpha, 0.25); } else pan = {x: ev.clientX - view.x, y: ev.clientY - view.y};
  });
  cv.addEventListener('pointermove', function (ev) {
    if (!(ev.pointerId in pts)) return;
    var ids = Object.keys(pts);
    if (ids.length === 2) {
      var o = ids[0] == ev.pointerId ? pts[ids[1]] : pts[ids[0]], p = pts[ev.pointerId], d0 = Math.hypot(p.x - o.x, p.y - o.y), d1 = Math.hypot(ev.clientX - o.x, ev.clientY - o.y);
      if (d0 > 10) view.k = Math.max(0.05, Math.min(8, view.k * d1 / d0));
      pts[ev.pointerId] = {x: ev.clientX, y: ev.clientY}; moved = 99; dirty = true; return;
    }
    moved += Math.abs(ev.movementX) + Math.abs(ev.movementY);
    if (drag) { var w = world(ev); drag.x = w.x; drag.y = w.y; if (physics) alpha = Math.max(alpha, 0.25); }
    else if (pan) { view.x = ev.clientX - pan.x; view.y = ev.clientY - pan.y; }
    dirty = true;
  });
  function up(ev) {
    var tapped = moved < 6 && Object.keys(pts).length === 1;
    delete pts[ev.pointerId];
    if (tapped) {
      var n = hit(world(ev)), now = Date.now();
      if (n && n === sel && now - lastTap < 400 && opts.onOpen) opts.onOpen(n);
      else select(n);
      lastTap = now;
    }
    drag = null; pan = null;
  }
  cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  cv.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    var b = cv.getBoundingClientRect(), mx = ev.clientX - b.left - box.clientWidth / 2, my = ev.clientY - b.top - box.clientHeight / 2, f = Math.exp(-ev.deltaY * 0.0015), k = Math.max(0.05, Math.min(8, view.k * f));
    view.x = mx - (mx - view.x) * k / view.k; view.y = my - (my - view.y) * k / view.k; view.k = k; dirty = true;
  }, {passive: false});
  if (physics) for (var i = 0; i < (N.length > 400 ? 60 : 200); i++) step(); else alpha = 0;
  fit();
  window.addEventListener('resize', function () { dirty = true; });
  (function tick() { if (!box.isConnected) return; if (alpha > 0.002) { step(); dirty = true; } if (dirty) { draw(); dirty = false; } requestAnimationFrame(tick); })();
  return {select: select, fit: function () { fit(); dirty = true; }};
};
