/* ==========================================================================
   core.js -- shared state, API helper, routing, log dock, small utilities.
   Everything hangs off the single global `BARRY`.
   ========================================================================== */
'use strict';

const BARRY = {
  state: {
    catalog: null,
    view: 'pipeline',
    job: null,          // currently displayed job id
    jobSeq: 0,          // last log line seen for that job
    poll: null,
    theme: 'dark',
  },
  views: {},
};

/* ==========================================================================
   Uncaught front-end errors
   A JS exception used to fail silently: the interface would simply stop
   halfway through starting up with no indication why. Now anything uncaught
   is shown and written to the error log alongside the backend's own.
   ========================================================================== */
function reportClientError(where, message, detail) {
  const text = String(message || 'Unknown error');
  try {
    const box = document.getElementById('bootError');
    if (box) {
      box.classList.remove('hidden');
      box.textContent = 'Interface error in ' + where + ': ' + text;
    }
    // Mirrored into the title so it is visible even in a headless capture.
    document.title = 'BARRY GUI — error: ' + text.slice(0, 120);
  } catch (e) { /* ignore */ }

  try { toast('Interface error: ' + text, 'err', 12000); } catch (e) { /* early */ }
  try { BARRY.debug.note('error', where + ': ' + text); } catch (e) { /* early */ }

  try {
    fetch('/api/activity', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entries: [{
        action: 'client.error',
        detail: { where, message: text, detail: String(detail || '').slice(0, 4000) },
        view: (BARRY.state && BARRY.state.view) || null,
      }] }),
    });
  } catch (e) { /* ignore */ }
}

window.addEventListener('error', (e) => {
  reportClientError(
    (e.filename || '').split('/').pop() + ':' + (e.lineno || '?'),
    e.message, e.error && e.error.stack);
});
window.addEventListener('unhandledrejection', (e) => {
  const r = e.reason;
  reportClientError('promise', (r && r.message) || String(r), r && r.stack);
});

/* ---------- tiny DOM helpers ---------- */
/* Is the event coming from somewhere the user is typing? Guarded, because
   `matches` only exists on elements and an event can target the document. */
function isTyping(e) {
  const t = e && e.target;
  return !!(t && typeof t.matches === 'function'
            && t.matches('input, textarea, select, [contenteditable]'));
}

const $  = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

/* SVG lives in its own namespace, and document.createElement does not put it
   there -- it produces an HTML element that merely happens to be called
   "svg", which lays out as nothing and renders at 0x0. Every icon, chevron,
   loader and drawn shape built in JS was invisible for exactly that reason.
   The ones written literally in index.html worked because the HTML parser
   knows to switch namespaces, and createElement does not.

   innerHTML has the same problem, so markup destined for an SVG parent is
   parsed as SVG and imported rather than assigned. */
const SVG_NS = 'http://www.w3.org/2000/svg';
const SVG_TAGS = new Set([
  'svg', 'g', 'defs', 'use', 'symbol', 'path', 'rect', 'circle', 'ellipse',
  'line', 'polyline', 'polygon', 'text', 'tspan', 'clipPath', 'mask',
  'linearGradient', 'radialGradient', 'stop', 'marker', 'pattern', 'image',
  'foreignObject', 'title', 'desc',
]);

function svgFragment(markup) {
  const doc = new DOMParser().parseFromString(
    '<svg xmlns="' + SVG_NS + '">' + markup + '</svg>', 'image/svg+xml');
  const frag = document.createDocumentFragment();
  if (doc.querySelector('parsererror')) return frag;
  for (const child of Array.from(doc.documentElement.childNodes)) {
    frag.appendChild(document.importNode(child, true));
  }
  return frag;
}

function el(tag, attrs, children) {
  const isSvg = SVG_TAGS.has(tag);
  const node = isSvg ? document.createElementNS(SVG_NS, tag)
                     : document.createElement(tag);
  for (const k in (attrs || {})) {
    const v = attrs[k];
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') {
      // An SVG element's className is a read-only SVGAnimatedString.
      if (isSvg) node.setAttribute('class', v); else node.className = v;
    } else if (k === 'text') node.textContent = v;
    // A textarea's content is its child text; the value attribute is only a
    // default and is ignored once the element exists. Assign the property.
    else if (k === 'value' && (tag === 'textarea' || tag === 'input')) node.value = v;
    else if (k === 'html') {
      if (isSvg) node.appendChild(svgFragment(v));
      else node.innerHTML = v;
    } else if (k.startsWith('on') && typeof v === 'function') {
      node.addEventListener(k.slice(2).toLowerCase(), v);
    } else node.setAttribute(k, v);
  }
  for (const c of [].concat(children || [])) {
    if (c === null || c === undefined || c === false) continue;
    node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

/* Read a theme token from CSS. JS had the UVM gold written into it in half a
   dozen places, which meant those spots stayed gold whatever theme was on. */
BARRY.token = function token(name, fallback) {
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim();
  return v || fallback || '#888888';
};

/* The categorical ramp: for things that need telling apart from each other
   rather than meaning something in particular -- session tabs, chart bands.
   It comes from the theme's own --c1..--c5, so it is pink in Horizon and gold
   in UVM Dark, and it is guaranteed internally distinct in a way the semantic
   tokens are not. Past five, it wraps rather than inventing colors that may
   collide with the theme. */
BARRY.hues = function hues(n) {
  const base = ['--c1', '--c2', '--c3', '--c4', '--c5']
    .map((t) => BARRY.token(t));
  // Only the neutral is dropped when a distinct color is what is wanted.
  return n === undefined ? base : base[n % (base.length - 1)];
};


/* ==========================================================================
   Picking one recording out of hundreds.

   A <select> was fine when BARRY knew about six recordings. Scanning a drive
   registers every one it walks past, so the list is now in the hundreds and a
   dropdown is the wrong control entirely -- you cannot type at it, you cannot
   see the project or whether the drive is mounted, and finding m59 s11 means
   scrolling.

   So: a search field that filters as you type, over the label, the mouse and
   session numbers, the project, the cohort, the date and the permanent id.
   Arrow keys move, enter picks, escape closes.
   ========================================================================== */
BARRY.pickSession = function pickSession(opts) {
  const rows = (opts && opts.rows) || [];
  const onpick = (opts && opts.onpick) || function () {};
  let value = (opts && opts.value) || null;
  let cursor = 0;
  let open = false;

  const hayOf = (r) => [
    r.label, r.key, r.gid, r.project, r.cohort,
    'm' + r.mouse, 's' + r.session, r.date,
  ].filter(Boolean).join(' ').toLowerCase();

  const input = el('input', {
    type: 'search', class: 'sp-input',
    placeholder: (opts && opts.placeholder)
      || 'Type a mouse, session, project or date\u2026',
    autocomplete: 'off', spellcheck: 'false',
  });
  const list = el('div', { class: 'sp-list hidden' });
  const box = el('div', { class: 'sp-box' }, [input, list]);

  const current = () => rows.find((r) => r.gid === value) || null;

  function matches() {
    const q = input.value.trim().toLowerCase();
    if (!q) return rows.slice(0, 60);
    const terms = q.split(/\s+/);
    return rows.filter((r) => {
      const hay = hayOf(r);
      return terms.every((t) => hay.includes(t));
    }).slice(0, 60);
  }

  function draw() {
    const found = matches();
    cursor = Math.max(0, Math.min(cursor, found.length - 1));
    list.innerHTML = '';
    if (!found.length) {
      list.appendChild(el('div', { class: 'sp-none',
        text: rows.length ? 'Nothing matches that.'
                          : 'No recordings registered yet.' }));
    }
    found.forEach((r, i) => {
      list.appendChild(el('div', {
        class: 'sp-row' + (i === cursor ? ' on' : '')
             + (r.reachable ? '' : ' away'),
        onmouseenter: () => { cursor = i; paintCursor(); },
        onmousedown: (e) => { e.preventDefault(); choose(r); },
      }, [
        el('span', { class: 'sp-dot' + (r.reachable ? ' on' : ''),
                     title: r.reachable ? 'On a drive this machine can reach'
                                        : 'Not mounted here' }),
        el('span', { class: 'sp-name', text: r.label || r.key || r.gid }),
        r.cohort ? el('span', { class: 'sp-tag', text: r.cohort }) : null,
        el('span', { class: 'sp-proj', text: r.project || '' }),
      ].filter(Boolean)));
    });
    if (rows.length > found.length) {
      list.appendChild(el('div', { class: 'sp-none',
        text: found.length + ' of ' + rows.length + ' shown \u2014 keep '
            + 'typing to narrow it.' }));
    }
  }

  function paintCursor() {
    Array.from(list.querySelectorAll('.sp-row')).forEach(
      (n, i) => n.classList.toggle('on', i === cursor));
  }

  function show() { open = true; list.classList.remove('hidden'); draw(); }
  function hide() { open = false; list.classList.add('hidden'); }

  function choose(r) {
    value = r.gid;
    input.value = r.label || r.key || r.gid;
    hide();
    onpick(r);
  }

  input.addEventListener('focus', () => { input.select(); show(); });
  input.addEventListener('input', () => { cursor = 0; show(); });
  input.addEventListener('blur', () => setTimeout(hide, 140));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) { show(); return; }
      cursor += e.key === 'ArrowDown' ? 1 : -1;
      const n = list.querySelectorAll('.sp-row').length;
      cursor = (cursor + n) % (n || 1);
      paintCursor();
      const on = list.querySelector('.sp-row.on');
      if (on) on.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const found = matches();
      if (found[cursor]) choose(found[cursor]);
    } else if (e.key === 'Escape') {
      if (open) { e.preventDefault(); e.stopPropagation(); hide(); }
    }
  });

  const start = current();
  if (start) input.value = start.label || start.key || start.gid;

  box.pickerValue = () => value;
  box.pickerRow = () => current();
  return box;
};

/* ---------- rate limiting ---------- */
function debounce(fn, ms) {
  let h = null;
  return function () {
    const args = arguments, self = this;
    clearTimeout(h);
    h = setTimeout(() => fn.apply(self, args), ms);
  };
}

/* The same thing for a text input. The event object is recycled by the
   browser, so the value has to be read now and handed on as a plain shape
   the callback can still use when the timer fires. */
function debounceInput(fn, ms) {
  let h = null;
  return function (e) {
    const value = e.target.value;
    clearTimeout(h);
    h = setTimeout(() => fn({ target: { value } }), ms);
  };
}

/* ---------- formatting ---------- */
function fmtBytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + ' ' + u[i];
}

function fmtDur(s) {
  if (!s && s !== 0) return '';
  if (s < 60) return s.toFixed(1) + 's';
  const m = Math.floor(s / 60);
  return m + 'm ' + Math.round(s % 60) + 's';
}

function fmtTime(sec) {
  if (sec === null || sec === undefined || !isFinite(sec)) return '--:--';
  const neg = sec < 0;
  // Work in whole milliseconds so a value like 5.9996 s cannot round its
  // fractional part up to "1000" and overflow the field.
  const total = Math.round(Math.abs(sec) * 1000);
  const h = Math.floor(total / 3600000);
  const m = Math.floor((total % 3600000) / 60000);
  const s = Math.floor((total % 60000) / 1000);
  const ms = total % 1000;
  const pad = (v, n) => String(v).padStart(n, '0');
  const body = (h ? pad(h, 2) + ':' : '') + pad(m, 2) + ':' + pad(s, 2) +
               '.' + pad(ms, 3);
  return (neg ? '-' : '') + body;
}

function baseName(p) {
  if (!p) return '';
  const parts = String(p).replace(/[\\/]+$/, '').split(/[\\/]/);
  return parts[parts.length - 1] || p;
}

/* ==========================================================================
   Debug trace

   The server records the requests it receives, but only the browser knows
   which control was clicked, what its console said, and how a request looked
   from this side -- including the ones that never arrived. Both halves
   together are what explains a bug that raised nothing.

   Rings are bounded and in memory only; nothing is sent anywhere until you
   ask for a report.
   ========================================================================== */
BARRY.debug = (function () {
  const MAX = 400;
  const requests = [];
  const console_ = [];

  const stamp = () => new Date().toTimeString().slice(0, 8);

  function push(ring, rec) {
    ring.push(rec);
    if (ring.length > MAX) ring.splice(0, ring.length - MAX);
  }

  function request(rec) { push(requests, Object.assign({ at: stamp() }, rec)); }
  function note(level, text) {
    push(console_, { at: stamp(), level, text: String(text).slice(0, 1000) });
  }

  /* Console output is captured rather than replaced: the original still runs,
     so devtools behaves exactly as before. */
  for (const level of ['warn', 'error']) {
    const original = console[level].bind(console);
    console[level] = function () {
      try {
        note(level, Array.from(arguments).map((a) =>
          (a && a.stack) ? a.stack : (typeof a === 'object'
            ? JSON.stringify(a).slice(0, 400) : String(a))).join(' '));
      } catch (e) { /* never let logging break logging */ }
      original.apply(console, arguments);
    };
  }

  return {
    request, note,
    requests: () => requests.slice(),
    console: () => console_.slice(),
    clear: () => { requests.length = 0; console_.length = 0; },
  };
})();

/* ---------- API ---------- */
async function api(path, opts) {
  const t0 = performance.now();
  const method = (opts && opts.method) || 'GET';
  const record = (status, error) => BARRY.debug.request({
    method, path: path.split('?')[0], query: path.split('?')[1] || '',
    status, ms: Math.round(performance.now() - t0), error,
  });

  let res;
  try {
    res = await fetch(path, Object.assign({
      headers: { 'Content-Type': 'application/json' },
    }, opts || {}));
  } catch (e) {
    // The request never completed -- server gone, or the tab went offline.
    record(0, e.message);
    throw new Error('Could not reach the server: ' + e.message);
  }

  /* A 404 on an /api/ route means the route is not there -- which almost
     always means the server is running older code than the page that just
     asked for it. That happens whenever BARRY is left running while the repo
     is updated, and the only symptom is a feature quietly doing nothing.
     Say it once, plainly, rather than letting it look like a bug. */
  if (res.status === 404 && path.startsWith('/api/')) {
    staleServer(path);
  }

  let data;
  try { data = await res.json(); }
  catch (e) {
    record(res.status, 'non-JSON response');
    throw new Error('Server returned a non-JSON response (' + res.status + ').');
  }
  if (!res.ok || data.ok === false) {
    const msg = data.error || ('Request failed (' + res.status + ')');
    record(res.status, msg);
    throw new Error(msg);
  }
  record(res.status);
  return data;
}

const apiPost = (path, body) =>
  api(path, { method: 'POST', body: JSON.stringify(body || {}) });

/* Told once per session, not once per request: a stale server produces a
   burst of these, and twenty identical toasts is worse than none. */
let staleTold = false;
function staleServer(path) {
  BARRY.debug.note('warn', 'stale server: no route ' + path);
  if (staleTold) return;
  staleTold = true;
  toast('This page asked the server for ' + path.split('?')[0]
        + ' and it does not have it — BARRY is running older code than '
        + 'the files on disk. Restart it (close the window and run '
        + '"Start BARRY GUI" again) to pick up the new version.',
        'err', 20000);
}

/* ---------- loading state ----------
   A themed placeholder, used everywhere something is being fetched or
   rendered. The browser's own broken-image glyph used to show through while a
   panel image had no src yet, which looked like a failure rather than a wait. */
/* A loader that says which step it is on.

   "Reading…" for three seconds tells you nothing, and every ToolKit pane
   waits on two or three requests -- the recording registry is over a second
   on its own. Naming the step is both more use and more interesting to look
   at than a spinner, and when it stalls you know what it stalled on.

   The trace is a dentate spike sweeping past, which is what this whole
   application is for. Returns a node with a .step(text) on it so the caller
   can tick it along. */
function stepLoader(label, steps) {
  const line = el('span', { class: 'sl-step' });
  const dots = el('div', { class: 'sl-dots' },
    (steps || []).map(() => el('i')));
  const node = el('div', { class: 'loader step-loader' }, [
    el('svg', {
      class: 'loader-wave sl-wave', viewBox: '0 0 120 28',
      preserveAspectRatio: 'none',
      html: '<path class="sl-base" d="M0 14 H120"/>'
          + '<path class="sl-spike" d="M0 14 L36 14 L44 5 L50 25 L57 10'
          + ' L63 15 L70 14 L120 14"/>',
    }),
    el('div', { class: 'loader-text' }, [
      el('strong', { text: label || 'Working' }),
      line,
    ]),
    dots,
  ]);
  let at = -1;
  node.step = (text) => {
    at += 1;
    line.textContent = text || '';
    Array.from(dots.children).forEach((d, i) => {
      d.className = i < at ? 'done' : (i === at ? 'now' : '');
    });
  };
  if ((steps || []).length) node.step(steps[0]);
  return node;
}

function loader(label, sub) {
  return el('div', { class: 'loader' }, [
    el('svg', {
      class: 'loader-wave', viewBox: '0 0 120 28', preserveAspectRatio: 'none',
      html: '<path d="M0 14 L14 14 L19 4 L25 24 L31 9 L37 18 L43 14 L58 14'
          + ' L63 6 L69 22 L75 11 L81 16 L87 14 L102 14 L107 8 L113 20 L120 14"/>',
    }),
    el('div', { class: 'loader-text' }, [
      el('strong', { text: label || 'Loading' }),
      sub ? el('span', { text: sub }) : null,
    ]),
  ]);
}

/* ---------- toasts ---------- */
function toast(msg, kind, ms) {
  const node = el('div', { class: 'toast' + (kind ? ' ' + kind : ''), text: msg });
  $('#toasts').appendChild(node);
  setTimeout(() => {
    node.style.opacity = '0';
    node.style.transition = 'opacity .2s';
    setTimeout(() => node.remove(), 220);
  }, ms || (kind === 'err' ? 6000 : 3200));
}

/* ---------- path prompt modal ---------- */
function askPath(title, placeholder) {
  return new Promise((resolve) => {
    const back = $('#pathModal');
    const input = $('#pathModalInput');
    $('#pathModalTitle').textContent = title || 'Paste a path';
    input.placeholder = placeholder || '';
    input.value = '';
    back.classList.remove('hidden');
    setTimeout(() => input.focus(), 30);

    const close = (val) => {
      back.classList.add('hidden');
      $('#pathModalOk').removeEventListener('click', ok);
      $('#pathModalCancel').removeEventListener('click', cancel);
      input.removeEventListener('keydown', key);
      resolve(val);
    };
    const clean = (v) => (v || '').trim().replace(/^["']|["']$/g, '');
    const ok = () => close(clean(input.value) || null);
    const cancel = () => close(null);
    const key = (e) => {
      if (e.key === 'Enter') ok();
      if (e.key === 'Escape') cancel();
    };
    $('#pathModalOk').addEventListener('click', ok);
    $('#pathModalCancel').addEventListener('click', cancel);
    input.addEventListener('keydown', key);
  });
}

/* ---------- drag & drop ----------
   Browsers hand us a File, not a path. On Windows a dropped folder or file
   still exposes enough for us to ask the user to confirm, but the reliable
   route is the native picker -- so we take what we can get and fall back. */
function wireDropzone(node, onPath) {
  const stop = (e) => { e.preventDefault(); e.stopPropagation(); };

  ['dragenter', 'dragover'].forEach((ev) =>
    node.addEventListener(ev, (e) => { stop(e); node.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach((ev) =>
    node.addEventListener(ev, (e) => { stop(e); node.classList.remove('drag'); }));

  node.addEventListener('drop', async (e) => {
    const dt = e.dataTransfer;

    // A path dragged from a terminal / text field arrives as plain text.
    const text = (dt.getData('text/plain') || '').trim().replace(/^["']|["']$/g, '');
    if (text && /[\\/]/.test(text)) { onPath(text); return; }

    const items = dt.items ? Array.from(dt.items) : [];
    const entry = items.length && items[0].webkitGetAsEntry
      ? items[0].webkitGetAsEntry() : null;
    const file = dt.files && dt.files.length ? dt.files[0] : null;
    const name = (entry && entry.name) || (file && file.name) || '';

    if (!name) { toast('Could not read that drop. Use Browse instead.', 'err'); return; }

    // Chromium never exposes the real path for security reasons, so confirm it.
    const guess = await askPath(
      'Confirm the full path for "' + name + '"',
      'Paste the full path -- browsers hide it from drops');
    if (guess) onPath(guess);
  });
}

/* ---------- native picker ---------- */
async function pickPath(kind, start) {
  try {
    const res = await apiPost('/api/pick', { kind: kind || 'folder', start: start || '' });
    return res.path || null;
  } catch (e) {
    toast('Picker failed: ' + e.message, 'err');
    return null;
  }
}

/* ==========================================================================
   Log dock -- polls the active job and streams its output.
   ========================================================================== */
const LOG = {
  attach(jobId, label) {
    BARRY.state.job = jobId;
    BARRY.state.jobSeq = 0;
    $('#logBody').textContent = '';
    $('#jobPill').textContent = label || 'running';
    $('#jobPill').className = 'job-pill running';
    LOG.expand();
    LOG.startPolling();
    LOG.refreshJobList();
  },

  expand() { $('#logDock').classList.remove('collapsed'); },
  collapse() { $('#logDock').classList.add('collapsed'); },

  startPolling() {
    if (BARRY.state.poll) clearInterval(BARRY.state.poll);
    BARRY.state.poll = setInterval(LOG.tick, 500);
    LOG.tick();
  },

  stopPolling() {
    if (BARRY.state.poll) clearInterval(BARRY.state.poll);
    BARRY.state.poll = null;
  },

  async tick() {
    const id = BARRY.state.job;
    if (!id) { LOG.stopPolling(); return; }
    let data;
    try {
      data = await api('/api/job/' + id + '?since=' + BARRY.state.jobSeq);
    } catch (e) {
      LOG.stopPolling();
      return;
    }
    const job = data.job;
    LOG.appendLines(job.lines);
    BARRY.state.jobSeq = job.seq;

    const pill = $('#jobPill');
    pill.className = 'job-pill ' + job.status;
    const dur = job.started ? ((job.ended || Date.now() / 1000) - job.started) : 0;
    pill.textContent = job.label + ' · ' + job.status +
      (dur ? ' · ' + fmtDur(dur) : '');

    $('#jobCancel').disabled = job.status !== 'running';

    // 'cancelled' appears in runs recorded before the spelling was made
    // consistent, and those records are not rewritten.
    if (['done', 'failed', 'canceled', 'cancelled'].includes(job.status)) {
      LOG.stopPolling();
      LOG.refreshJobList();
      if (BARRY.views.pipeline && BARRY.views.pipeline.onJobEnd) {
        BARRY.views.pipeline.onJobEnd(job);
      }
      if (job.status === 'done') toast(job.label + ' finished', 'ok');
      else if (job.status === 'failed') toast(job.label + ' failed — see Output', 'err');
    }
  },

  appendLines(lines) {
    if (!lines || !lines.length) return;
    const body = $('#logBody');
    const stuck = body.scrollTop + body.clientHeight >= body.scrollHeight - 40;
    const frag = document.createDocumentFragment();
    for (const ln of lines) {
      const cls = ln.s === 'meta' ? 'meta' : (ln.s === 'err' ? 'err' : '');
      frag.appendChild(el('span', { class: cls, text: ln.text + '\n' }));
    }
    body.appendChild(frag);
    // Keep the DOM bounded on very chatty jobs.
    while (body.childNodes.length > 6000) body.removeChild(body.firstChild);
    if (stuck) body.scrollTop = body.scrollHeight;
  },

  async refreshJobList() {
    let data;
    try { data = await api('/api/jobs'); } catch (e) { return; }
    const sel = $('#jobSelect');
    const cur = BARRY.state.job;
    sel.innerHTML = '';
    if (!data.jobs.length) {
      sel.appendChild(el('option', { text: 'no runs yet', value: '' }));
      return;
    }
    for (const j of data.jobs) {
      const when = j.started
        ? new Date(j.started * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : '';
      sel.appendChild(el('option', {
        value: j.id,
        text: when + '  ' + j.label + '  (' + j.status + ')',
        selected: j.id === cur ? 'selected' : null,
      }));
    }
  },

  async show(jobId) {
    if (!jobId) return;
    BARRY.state.job = jobId;
    BARRY.state.jobSeq = 0;
    $('#logBody').textContent = '';
    LOG.expand();
    LOG.startPolling();
  },
};

/* ==========================================================================
   GUI_logs sync status
   ========================================================================== */
BARRY.sync = { git: null, root: null, index: null };

BARRY.refreshSync = async function refreshSync() {
  let data;
  try { data = await api('/api/sync/status'); } catch (e) { return; }
  BARRY.sync = data;
  const git = data.git || {};
  const btn = $('#syncBtn');
  const label = $('#syncLabel');
  if (!git.ok) {
    label.textContent = 'Logs';
    btn.classList.remove('dirty');
    btn.title = 'GUI_logs at ' + (data.root || '');
  } else if (git.dirty) {
    label.textContent = git.dirty + ' to commit';
    btn.classList.add('dirty');
    btn.title = git.dirty + ' uncommitted file(s) in GUI_logs — click for details';
  } else {
    label.textContent = 'Logs synced';
    btn.classList.remove('dirty');
    btn.title = 'GUI_logs has no uncommitted changes';
  }
};

/* Whether anything in the logs could ever conflict on a pull.

   Worth a line in the sync panel rather than only a script, because this is
   the one property of the store that quietly stops being true: somebody adds
   a new kind of record next year, writes it to one shared file, and nobody
   finds out until two people push in the same afternoon. */
/* Where the shared copy stands.

   Rendered empty and filled in when the answer arrives, because the sync
   panel should open instantly whether or not the network is up -- the whole
   point of writing locally first is that nothing waits on Supabase. */
/* The one thing a clone cannot carry.

   The repo says which project to sync to; the key deliberately is not in it,
   so each machine has to be told once. BARRY asks on startup in the terminal
   and here, because whichever one somebody is looking at should be enough. */
function askForKey(c) {
  const input = el('input', {
    type: 'password', class: 'cloud-key',
    placeholder: 'sb_secret_\u2026',
    autocomplete: 'off', spellcheck: 'false',
  });
  const msg = el('div', { class: 'hint' });
  const save = async () => {
    msg.className = 'hint';
    msg.textContent = 'Checking\u2026';
    try {
      const r = await apiPost('/api/cloud/key', { key: input.value });
      if (r.ok) {
        toast('Connected to ' + (c.project || 'Supabase') + '.', 'ok');
        showSync();
      } else {
        msg.className = 'hint bad';
        msg.textContent = r.error || 'That did not work.';
      }
    } catch (e) {
      msg.className = 'hint bad';
      msg.textContent = e.message;
    }
  };
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); });

  return el('div', { class: 'cloud-ask' }, [
    el('strong', { text: 'Connect this machine to ' + (c.project || 'Supabase') }),
    el('p', { class: 'hint',
      text: 'The repo knows which project to sync to. It does not carry the '
          + 'key \u2014 that would put it in git \u2014 so this machine '
          + 'needs it once. Project Settings \u2192 API Keys \u2192 the '
          + 'secret / service_role key.' }),
    el('div', { class: 'row' }, [
      input,
      el('button', { class: 'btn', text: 'Connect', onclick: save }),
    ]),
    msg,
    el('p', { class: 'hint',
      text: 'Kept in GUI_logs/.cloud.json, which git ignores. BARRY works '
          + 'perfectly well without it \u2014 the sync is an addition, not a '
          + 'requirement.' }),
  ]);
}


function cloudNote() {
  const box = el('div', { class: 'cloud-note' }, [
    el('div', { class: 'hint', text: 'Checking the shared copy…' }),
  ]);
  api('/api/cloud/status').then((c) => {
    box.innerHTML = '';
    if (c.key_in_repo) {
      box.appendChild(el('div', { class: 'cloud-err',
        text: 'cloud.json in the repo contains a key. That file is tracked '
            + 'by git, so treat the key as public: rotate it in the Supabase '
            + 'dashboard and paste the new one below. BARRY is ignoring the '
            + 'one in the file.' }));
    }
    if (c.needs_key) { box.appendChild(askForKey(c)); return; }
    if (!c.configured) {
      box.appendChild(el('p', { class: 'hint' }, [
        el('span', { text: 'Not syncing to Supabase. Set it up with ' }),
        el('code', { text: 'python tools/cloud_setup.py --url <project>' }),
      ]));
      return;
    }
    const last = c.last || {};
    const when = last.at ? new Date(last.at).toLocaleTimeString() : 'not yet';
    box.appendChild(el('div', { class: 'cloud-line' }, [
      el('span', { class: 'dot' + (last.ok === false ? ' bad'
                                   : (last.ok ? ' ok' : '')) }),
      el('strong', { text: c.project || 'Supabase' }),
      el('span', { class: 'hint',
        text: c.auto ? 'syncing every ' + c.interval + 's' : 'automatic sync '
            + 'is off' }),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn ghost sm', text: last.running ? 'Syncing…' : 'Sync now',
        disabled: last.running ? 'disabled' : null,
        onclick: async (e) => {
          e.target.disabled = true;
          e.target.textContent = 'Syncing…';
          try {
            const r = await apiPost('/api/cloud/sync', {});
            const l = r.last || {};
            toast('Sent ' + (l.pushed || 0) + ', brought back '
                  + (l.pulled || 0)
                  + (l.downloaded ? ', downloaded ' + l.downloaded + ' file(s)'
                     : '') + '.', l.ok === false ? 'err' : 'ok', 7000);
          } catch (err) { toast(err.message, 'err', 8000); }
          showSync();
        },
      }),
    ]));
    box.appendChild(el('p', { class: 'hint',
      text: 'Last sync ' + when
          + (last.ok === false ? '  —  failed' : '')
          + (last.pushed != null ? '  ·  sent ' + last.pushed : '')
          + (last.pulled ? '  ·  brought back ' + last.pulled : '')
          + (last.downloaded ? '  ·  ' + last.downloaded + ' file(s) down'
             : '') }));
    if (last.error) {
      box.appendChild(el('pre', { class: 'cloud-err', text: last.error }));
    }
    box.appendChild(el('p', { class: 'hint',
      text: 'BARRY writes here first and syncs in the background, so none of '
          + 'this is in the way if the network is down.' }));
  }).catch(() => {
    box.innerHTML = '';
    box.appendChild(el('p', { class: 'hint',
      text: 'This BARRY does not have the Supabase sync — restart it to '
          + 'pick up the new version.' }));
  });
  return box;
}


function conflictNote(c) {
  if (!c) return null;
  if (c.ok) {
    return el('p', {
      class: 'hint sync-ok',
      title: c.files + ' files checked. This machine writes as ' + c.mine
           + (c.machines.length > 1
              ? '. Also seen here: ' + c.machines.filter((m) => m !== c.mine)
                  .join(', ')
              : '.'),
      text: 'Nothing here can conflict on a pull \u2014 every record that '
          + 'can be edited is kept per machine and compiled when it is read. '
          + (c.machines.length > 1
             ? c.machines.length + ' machines have written here.'
             : ''),
    });
  }
  return el('div', { class: 'sync-warn' }, [
    el('p', { text: c.shared.length + ' file(s) here are shared between '
                  + 'machines, so two people editing the same thing would '
                  + 'collide on a pull:' }),
    el('pre', { text: c.shared.join('\n') }),
    el('p', { class: 'hint',
      text: 'Route whatever writes them through a shards.Book, or add them '
          + 'to .gitignore if they are derived. tools/conflict_check.py says '
          + 'the same thing from the command line.' }),
  ]);
}


function showSync() {
  const d = BARRY.sync || {};
  const git = d.git || {};
  const counts = (d.index && d.index.counts) || {};
  const files = (git.files || []).slice(0, 40);

  showModal(el('div', {}, [
    el('div', { class: 'mh' }, [
      el('h3', { text: 'GUI_logs' }),
      el('span', { class: 'sub', text: d.root || '' }),
      el('div', { class: 'spacer' }),
      el('button', { class: 'close-x', html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
                     onclick: closeModal }),
    ]),
    el('div', { class: 'mb' }, [
      el('div', { class: 'fb-stats' }, [
        el('span', { class: 'stat-chip', text: (counts.runs || 0) + ' runs' }),
        el('span', { class: 'stat-chip', text: (counts.sessions || 0) + ' sessions' }),
        el('span', { class: 'stat-chip', text: (counts.errors || 0) + ' errors' }),
        git.ok
          ? el('span', { class: 'stat-chip ' + (git.dirty ? 'warn' : 'good'),
                         text: git.dirty ? git.dirty + ' uncommitted' : 'clean' })
          : el('span', { class: 'stat-chip warn', text: git.error || 'not a git repo' }),
      ]),
      el('div', { class: 'section-label', text: 'How syncing works' }),
      el('p', { style: 'font-size:12.5px;line-height:1.7;color:var(--text-2)' , text:
        'BARRY writes every run, bad-channel mark, preset and error into GUI_logs as '
        + 'plain JSON — one file per run and per session, so git merges them without '
        + 'conflict. It never commits or pushes on its own.' }),
      el('div', { class: 'source-box' }, [
        cloudNote(),
        conflictNote(d.conflicts),
        el('pre', { text: 'git add "BARRY GUI/GUI_logs"\ngit commit -m "session logs"\ngit push\n\n'
                          + '# to pick up everyone else\'s work:\ngit pull' }),
      ]),
      files.length ? el('div', { class: 'section-label', text: 'Uncommitted files' }) : null,
      files.length ? el('div', { class: 'source-box' }, [el('pre', { text: files.join('\n') })]) : null,
    ]),
    el('div', { class: 'mf' }, [
      el('button', { class: 'btn ghost sm', text: 'Open folder',
                     onclick: () => apiPost('/api/reveal', { path: d.root }).catch(() => {}) }),
      el('button', { class: 'btn ghost sm', text: 'Rebuild index',
                     onclick: async () => {
                       try { await apiPost('/api/sync/reindex'); await BARRY.refreshSync();
                             toast('Index rebuilt', 'ok'); showSync(); }
                       catch (e) { toast(e.message, 'err'); }
                     } }),
      el('div', { class: 'spacer' }),
      el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
    ]),
  ]));
}

BARRY.setErrorCount = function setErrorCount(n) {
  const b = $('#errBadge');
  if (!b) return;
  b.textContent = String(n);
  b.classList.toggle('hidden', !n);
};

/* ==========================================================================
   Routing + boot
   ========================================================================== */
const VIEWS = ['pipeline', 'explorer', 'xplore', 'sessions', 'history',
               'errors', 'results', 'storyboard', 'misc', 'eventbank',
               'toolkit'];

/* ==========================================================================
   The rail: full, icons, away
   ==========================================================================
   Cycled by one button rather than configured in a settings panel, because
   this is a thing people do twenty times a day and once a year respectively.
   Remembered per machine -- it describes the monitor, not the project.
   ========================================================================== */
const RAIL_STATES = ['full', 'icons', 'away'];

function railState() {
  try {
    const v = localStorage.getItem('barry.rail');
    return RAIL_STATES.includes(v) ? v : 'full';
  } catch (e) { return 'full'; }
}

function setRail(state, remember) {
  const app = document.getElementById('app');
  if (!app) return;
  const s = RAIL_STATES.includes(state) ? state : 'full';
  app.classList.toggle('rail-icons', s === 'icons');
  app.classList.toggle('rail-away', s === 'away');
  const btn = document.getElementById('railToggle');
  if (btn) {
    btn.title = s === 'full' ? 'Collapse the menu to icons'
      : s === 'icons' ? 'Hide the menu' : 'Show the menu';
  }
  if (remember !== false) {
    try { localStorage.setItem('barry.rail', s); } catch (e) { /* ignore */ }
  }
  // Every canvas in the workspace just changed width.
  window.dispatchEvent(new Event('resize'));
}

function cycleRail() {
  const at = RAIL_STATES.indexOf(railState());
  setRail(RAIL_STATES[(at + 1) % RAIL_STATES.length]);
}

function wireRail() {
  const btn = document.getElementById('railToggle');
  if (btn) btn.addEventListener('click', cycleRail);

  // The handle that brings it back. Built here rather than in the markup so
  // it cannot exist without the code that makes it work.
  const peek = el('button', {
    id: 'railPeek', title: 'Show the menu',
    onclick: () => setRail('full'),
    html: '<svg viewBox="0 0 20 20" style="width:12px;height:12px;fill:none;'
        + 'stroke:currentColor;stroke-width:2"><path d="M7 4l6 6-6 6"/></svg>',
  });
  // Inside #app, because that is where the rail-away class lands and the
  // rule that shows this is a descendant selector. On body it was styled by
  // nothing and stayed invisible -- a way back that cannot be seen is not
  // one.
  (document.getElementById('app') || document.body).appendChild(peek);
  setRail(railState(), false);
}


/* ==========================================================================
   Modes
   ==========================================================================
   StrataScope and DS curation take over the window: different panes,
   different keys, dragging means something else. Announced here rather than
   in each mode, so the two cannot drift apart, and so leaving is always the
   same button in the same place.
   ========================================================================== */
const MODES = {
  strata: {
    name: 'StrataScope',
    what: 'Labelling layers · drag on the rail to set a boundary '
        + '· the aids are in the second window',
  },
  curate: {
    name: 'DS curation',
    what: 'Judging candidates · Y keeps, N rejects, ←/→ move '
        + '· the aids are in the second window',
  },
};

let modeLeaveFn = null;

/* Turn a mode on or off. `leave` is what the Leave button calls; without one
   the button is hidden, because a way out that does nothing is worse than
   none. */
function setMode(kind, leave) {
  const app = document.getElementById('app');
  if (!app) return;
  for (const k of Object.keys(MODES)) app.classList.toggle('mode-' + k, k === kind);
  modeLeaveFn = kind ? (leave || null) : null;
  const m = MODES[kind];
  const name = document.getElementById('modeName');
  const what = document.getElementById('modeWhat');
  const out = document.getElementById('modeLeave');
  if (name) name.textContent = m ? m.name : '';
  if (what) what.textContent = m ? m.what : '';
  if (out) out.style.display = (m && modeLeaveFn) ? '' : 'none';
  // Every canvas just changed height by the banner's worth.
  window.dispatchEvent(new Event('resize'));
}

function wireMode() {
  const out = document.getElementById('modeLeave');
  if (out) out.addEventListener('click', () => {
    const fn = modeLeaveFn;
    if (fn) fn();
  });
}


function setView(name) {
  if (!VIEWS.includes(name)) name = 'pipeline';
  BARRY.state.view = name;
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + name));
  if (location.hash.slice(1) !== name) {
    history.replaceState(null, '', '#' + name);
  }
  const v = BARRY.views[name];
  if (v && v.onShow) v.onShow();
}

/* ==========================================================================
   Themes

   The swatch colors here are only for the picker; the real palettes live in
   app.css, where every theme redefines the same token set.
   ========================================================================== */
const THEMES = [
  { id: 'dark',  name: 'UVM Dark',      swatch: ['#0f1e18', '#154734', '#FFB81C'] },
  { id: 'light', name: 'UVM Light',     swatch: ['#ffffff', '#e7efea', '#154734'] },
  { id: 'slate', name: 'Slate',         swatch: ['#151a21', '#2a323d', '#6aa9ff'] },
  { id: 'parchment', name: 'Parchment', swatch: ['#faf6ef', '#e0d5c0', '#8a5a14'] },
  { id: 'phosphor', name: 'Phosphor',   swatch: ['#060a07', '#111b14', '#46f08c'] },
  { id: 'horizon', name: 'Horizon',     swatch: ['#5bcefa', '#f5a9b8', '#ffffff'] },
  { id: 'horizon-night', name: 'Horizon Night',
    swatch: ['#0b1220', '#5bcefa', '#f5a9b8'] },
];

const themeById = (id) => THEMES.find((t) => t.id === id) || THEMES[0];

function applyTheme(theme, remember) {
  if (!THEMES.some((t) => t.id === theme)) theme = 'dark';
  BARRY.state.theme = theme;
  document.documentElement.dataset.theme = theme;
  const label = $('#themeToggle span');
  if (label) label.textContent = themeById(theme).name;

  if (remember !== false) {
    // The theme belongs to the machine, not the person's whole account: the
    // same repo is used on a bright rig-room screen and a dark office one.
    // localStorage applies it with no flash; preferences keyed by hostname
    // survive a browser reset without pushing your choice onto anyone else
    // through the shared log.
    try { localStorage.setItem('barry.theme', theme); } catch (e) { /* private */ }
    const host = ((BARRY.state.catalog || {}).system || {}).hostname;
    if (host) {
      const all = Object.assign({}, BARRY.prefs.get('themes', {}) || {});
      all[host] = theme;
      BARRY.prefs.set('themes', all);
    }
  }
  paintFavicon();
  // The canvas paints from CSS tokens, so it has to be repainted by hand.
  if (BARRY.views.xplore && BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
}

/* The tab icon is the same trace mark as the brand, drawn in the theme's own
   colors -- a gold-on-green favicon over a pink interface looks like a
   different application. */
/* Offer the tour once, on a machine that has never run one.

   Once, and only once: a nudge that reappears every morning is not a nudge,
   it is a nag. The Guide chip is in the rail either way, and the command
   palette knows the word "tour". */
function offerTour() {
  const KEY = 'barry.tour.offered';
  try {
    if (localStorage.getItem(KEY)) return;
    if (BARRY.tour.doneSet().size) return;
    localStorage.setItem(KEY, '1');
  } catch (e) { return; }        // private window: skip it rather than nag
  setTimeout(() => {
    toast('First time here? "Guide" at the bottom of the rail walks you '
          + 'through it — four minutes, and it points at the real '
          + 'thing rather than describing it.', null, 14000);
  }, 1800);
}

function paintFavicon() {
  const cs = getComputedStyle(document.documentElement);
  const tok = (n, f) => (cs.getPropertyValue(n) || f).trim();
  const bg = tok('--accent', '#154734');
  const ink = tok('--on-accent', '#FFB81C');
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    + '<rect width="32" height="32" rx="7" fill="' + bg + '"/>'
    + '<path d="M4 18h3l3-9 4 15 4-12 3 7 2-3h5" fill="none" stroke="' + ink
    + '" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
    + '</svg>';
  let link = document.querySelector('link[rel="icon"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  link.type = 'image/svg+xml';
  link.href = 'data:image/svg+xml,' + encodeURIComponent(svg);
}

function themeForThisMachine() {
  const host = ((BARRY.state.catalog || {}).system || {}).hostname;
  const byHost = BARRY.prefs.get('themes', {}) || {};
  if (host && byHost[host]) return byHost[host];
  try {
    const saved = localStorage.getItem('barry.theme');
    if (saved) return saved;
  } catch (e) { /* private mode */ }
  return null;
}

function showThemePicker() {
  const existing = $('#themePop');
  if (existing) { existing.remove(); return; }

  const pop = el('div', { class: 'theme-pop', id: 'themePop' },
    THEMES.map((t) => el('button', {
      class: 'theme-opt' + (BARRY.state.theme === t.id ? ' on' : ''),
      onclick: () => {
        applyTheme(t.id);
        pop.remove();
        BARRY.activity.log('theme.change', { theme: t.id });
      },
    }, [
      el('span', { class: 'theme-swatch' },
         t.swatch.map((c) => el('i', { style: 'background:' + c }))),
      el('span', { text: t.name }),
    ])).concat([
      el('div', { class: 'theme-note',
                  text: 'Remembered for this computer only.' }),
    ]));

  $('#themeToggle').parentNode.appendChild(pop);
  // Close on the next click anywhere else.
  setTimeout(() => {
    const away = (e) => {
      if (!pop.contains(e.target) && !e.target.closest('#themeToggle')) {
        pop.remove();
        document.removeEventListener('mousedown', away);
      }
    };
    document.addEventListener('mousedown', away);
  }, 0);
}

window.addEventListener('beforeunload', () => {
  try { BARRY.prefs.flush(); } catch (e) { /* nothing to do about it now */ }
});

BARRY.init = async function init() {
  // Applied before anything is fetched, so the first paint is already right.
  // A ?theme= in the URL wins but is not remembered -- it is for a link, not
  // a preference.
  const urlTheme = new URLSearchParams(location.search).get('theme');
  let saved = null;
  try { saved = localStorage.getItem('barry.theme'); } catch (e) { /* ignore */ }
  applyTheme(urlTheme || saved || 'dark', !urlTheme);

  $$('.nav-item').forEach((b) =>
    b.addEventListener('click', () => setView(b.dataset.view)));

  // The rail's own collapse, and the handle that brings it back.
  wireRail();
  wireMode();

  $('#themeToggle').addEventListener('click', showThemePicker);

  $('#syncBtn').addEventListener('click', showSync);

  $('#logToggle').addEventListener('click', () =>
    $('#logDock').classList.toggle('collapsed'));
  $('#logHead').addEventListener('click', (e) => {
    if (e.target.closest('button, select')) return;
    $('#logDock').classList.toggle('collapsed');
  });
  $('#logClear').addEventListener('click', (e) => {
    e.stopPropagation(); $('#logBody').textContent = '';
  });
  $('#logCopy').addEventListener('click', async (e) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText($('#logBody').textContent);
      toast('Output copied', 'ok');
    } catch (err) { toast('Could not copy', 'err'); }
  });
  $('#jobCancel').addEventListener('click', async (e) => {
    e.stopPropagation();
    if (!BARRY.state.job) return;
    try {
      await apiPost('/api/job/' + BARRY.state.job + '/cancel');
      toast('Stopping…');
    } catch (err) { toast(err.message, 'err'); }
  });
  $('#jobSelect').addEventListener('change', (e) => LOG.show(e.target.value));

  // Keyboard: 1-4 switch views when not typing.
  document.addEventListener('keydown', (e) => {
    if (isTyping(e)) return;
    // In rail order, top to bottom, so the number on the button is the key
    // that gets you there.
    const map = { '1': 'pipeline', '2': 'explorer', '3': 'xplore',
                  '4': 'sessions', '5': 'history', '6': 'errors',
                  '7': 'results', '8': 'eventbank', '9': 'storyboard',
                  '0': 'misc',
                  // Eleven sections, ten digits. The letter goes to the one
                  // that was added last rather than renumbering the ten that
                  // people have already learned.
                  't': 'toolkit', 'T': 'toolkit' };
    if (map[e.key]) setView(map[e.key]);
  });

  // Load the catalog, then hand off to each view.
  try {
    const cat = await api('/api/catalog');
    BARRY.state.catalog = cat;
    $('#repoName').textContent = cat.repo_name;
    $('#repoName').title = cat.repo;
    const env = $('#envInfo');
    env.textContent = '';
    env.appendChild(el('div', {}, [
      el('span', { class: 'dot ' + (cat.matlab ? 'on' : 'off') }),
      'MATLAB ' + (cat.matlab ? (cat.matlab.match(/R\d{4}[ab]/) || [''])[0] : 'missing'),
    ]));
    env.appendChild(el('div', {}, [
      el('span', { class: 'dot on' }),
      'Python ' + (cat.python_version || ''),
    ]));
    env.appendChild(el('div', { text: cat.items.length + ' scripts indexed' }));
    $('#envInfo').title = 'MATLAB: ' + (cat.matlab || 'not found') +
                          '\nPython: ' + cat.python;
  } catch (e) {
    toast('Could not load the repo index: ' + e.message, 'err', 9000);
  }

  // Preferences gate the views (favourites, smart collections, last
  // session), so they must be in hand before any view renders.
  await BARRY.prefs.load();

  // Preferences and the catalog are both in hand now, so the per-machine
  // choice can be honored -- it may differ from what localStorage had.
  const mine = themeForThisMachine();
  if (mine && mine !== BARRY.state.theme) applyTheme(mine);
  else applyTheme(BARRY.state.theme, true);   // records it for this machine

  BARRY.activity.init();
  // Housekeeping lives inside the Sessions view rather than owning a rail
  // slot, so it is wired here rather than by the view loop.
  if (BARRY.views.housekeeping) BARRY.views.housekeeping.init();
  if (BARRY.tour) {
    BARRY.tour.init();
    offerTour();
  }

  // One view failing to start must not take the rest of the interface with it.
  for (const key of Object.keys(BARRY.views)) {
    try {
      if (BARRY.views[key].init) BARRY.views[key].init();
    } catch (err) {
      reportClientError('init:' + key, err.message, err.stack);
    }
  }
  // Deep links: ?csc=<path> opens a session straight away (handy for a desktop
  // shortcut per recording), ?folder=<path> preloads the pipeline.
  const params = new URLSearchParams(location.search);
  const cscPath = params.get('csc');
  const pipeFolder = params.get('folder');

  // One call gives both the sync state and the error count for the badge.
  BARRY.refreshSync().then(() => {
    const n = ((BARRY.sync.index || {}).counts || {}).errors || 0;
    BARRY.setErrorCount(n);
  });

  setView(location.hash.slice(1) || (cscPath ? 'xplore' : 'pipeline'));
  window.addEventListener('hashchange', () => setView(location.hash.slice(1)));
  LOG.refreshJobList();

  if (cscPath && BARRY.views.xplore) {
    BARRY.views.xplore.open(cscPath).then((sess) => {
      if (!sess) return;
      const t0 = parseFloat(params.get('t0'));
      const span = parseFloat(params.get('span'));
      if (isFinite(t0)) sess.t0 = t0;
      if (isFinite(span) && span > 0) sess.span = span;
      const hp = parseFloat(params.get('hp'));
      const lp = parseFloat(params.get('lp'));
      const nt = parseFloat(params.get('notch'));
      if (isFinite(hp)) sess.hp = hp;
      if (isFinite(lp)) sess.lp = lp;
      if (isFinite(nt)) sess.notch = nt;
      const panel = params.get('panel');
      if (panel && BARRY.views.xplore.state.panes[0]) {
        BARRY.views.xplore.state.panes[0].panel = panel;
      }
      BARRY.views.xplore.onShow();
      // ?figure=1 opens the builder straight onto this session.
      if (params.get('figure')) {
        setTimeout(() => BARRY.figure.open(BARRY.views.xplore.state, sess), 400);
      }
    });
  }
  if (pipeFolder && BARRY.views.pipeline.setFolder) {
    BARRY.views.pipeline.setFolder(pipeFolder);
  }
};
