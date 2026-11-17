/* ==========================================================================
   extraction_blobs.js -- Blob Analysis, the Extraction Room's last sub-tab
   (web/extraction.html; asked 2026-11-12).

   "Then once that's locked in [the Impression] ... move on to Blob
   Analysis. In this part we want a per recording, per group (CTL/PTEN); and
   also per separation/not separable, and also a pick and choose model; for
   any variant that includes more than 2 recordings let us see the averages
   ... separate it out to top blob and bottom blob analysis of DS1 and DS2
   ... how long the sink lasts ... what its activity curve looks like; is it
   fast and strong; or slow and diffused ... For the groups; we also want
   some histogram related data ... since sometimes it seems like the PTEN
   are either weaker DS or high power ones." On the histograms: "include
   figures that would show what averages hide".

   WHAT IS ON SHOW, cast from one Impression version. backend/blobs.py works
   out every number; this page computes none, except where to draw a mark.
     the header      which Impression, the filter note (always), who is in,
                     who was left out and why;
     the controls    Blob (top / bottom / both), Class (all DS / DS1 / DS2 /
                     DS, one kind), Measure, Group by (CTL vs PTEN /
                     separable vs not / picked vs the rest), Pick recordings;
     each recording  its activity curves and the median [middle half] of
                     every number, for the class and blob chosen;
     the groups      for one measure: the mean activity curve, histograms
                     with every recording weighted the same, ECDFs with each
                     recording's own behind (what averages hide), the shift
                     function, the recording medians as dots, the tests in
                     words with p and q, and the two-humps hint;
     the averages    every measure x both blobs, the false discovery rate
                     held across the table: "finding" only on q; "hint" is a
                     lead, never a finding.
   THE TOP BLOB is the shallower of each event's two sink bumps, the BOTTOM
   the deeper. A recording called not separable is one class, "DS, one
   kind", kept out of DS1 vs DS2. Every number is measured per event; the
   recording is the unit.

   Its state (B) lives here so it survives the room's re-renders; each
   Impression is asked for once. Only this tab's element is ever redrawn,
   and inside it only the part that changed.
   ========================================================================== */
'use strict';

(function () {
  const ROOM = (window.erRoom = window.erRoom || {});
  ROOM.ext = ROOM.ext || {};
  const K = () => (window.erRoom || {}).kit;

  /* ---------- words ---------- */
  const FILTER_NOTE = 'The blob timing (duration, rise and decay) is measured on the 5-100 Hz CSD, which rounds off '
    + 'slow sinks: it might be worth redoing with other filters.';
  const NONE_YET = 'Lock in a set first: Take the impression on the Recordings tab.';
  const FEW = 'averages need at least 3 recordings';
  const MIN_EVENTS = 5;
  const BLOBS = [['top', 'Top', 'The shallower of each event’s two sink bumps.'],
                 ['bottom', 'Bottom', 'The deeper of each event’s two sink bumps.'],
                 ['both', 'Both', 'The top and the bottom blob side by side.']];
  const BLOB_NAME = { top: 'Top blob', bottom: 'Bottom blob' };
  const CLASSES = [['all', 'All DS', 'Every event of every recording: DS1 and DS2 together where a recording separates, '
                      + 'its one kind where it does not.'],
                   ['1', 'DS1', 'DS1 of the separable recordings only.'],
                   ['2', 'DS2', 'DS2 of the separable recordings only.'],
                   ['3', 'DS3', 'DS3, the hybrid (Tarcsay et al. 2025), where the Impression was taken with DS3 on.'],
                   ['0', 'DS, one kind', 'The recordings called not separable: all their events are one class, kept '
                      + 'out of DS1 vs DS2.']];
  const CLS_NAME = { all: 'all DS', 1: 'DS1', 2: 'DS2', 0: 'DS, one kind', 3: 'DS3 (hybrid)', 4: 'unsure' };
  const BY = [['group', 'CTL vs PTEN'], ['sep', 'Separable vs not'], ['pick', 'Picked vs the rest',
              'The recordings you tick on their cards against every other one.']];
  const BY_WORDS = { group: 'CTL vs PTEN', sep: 'separable vs not separable', pick: 'picked vs the rest' };
  /* Group colours. Separable / not and picked / the rest share a teal and an
     ochre of their own (checked for colour-blind separation in both themes). */
  const GC = { CTL: ['--g-ctl', '#4f8a6a'], PTEN: ['--g-pten', '#8a4fbf'],
               Separable: ['--erb-a', '#008a9e'], 'Not separable': ['--erb-b', '#9a6a00'],
               Picked: ['--erb-a', '#008a9e'], 'The rest': ['--erb-b', '#9a6a00'] };
  const KIND_ORDER = ['two', 'one', 'merged', 'unplaced', 'none'];
  const KIND_WORDS = { two: 'two sinks', one: 'one sink, placed by its depth', merged: 'both blades run together in '
    + 'one sink', unplaced: 'one sink that could not be placed', none: 'no sink at all' };
  const TESTS = [['location', 'Where the recordings sit'], ['spread', 'How varied the mice are'],
                 ['shape', 'The whole shape of the distribution']];
  const WORD = { finding: ['finding', 'erb-w-find'], hint: ['a lead, not a finding', 'erb-w-lead'],
                 'no sign': ['no sign', 'erb-w-none'], untested: ['not tested', 'erb-w-none'] };
  // In case an answer comes without them: backend/blobs.py's MEASURES.
  const MEASURES0 = [
    { id: 'peak', words: 'Peak sink', unit: 'CSD', higher: 'a stronger sink' },
    { id: 'latency_ms', words: 'When the sink peaks, after the stamp', unit: 'ms', higher: 'a later peak (below zero: before the stamp)' },
    { id: 'fwhm_ms', words: 'How long the sink lasts (time above half its peak)', unit: 'ms', higher: 'a longer sink' },
    { id: 'rise_ms', words: 'Rise time, 10% to 90% of the peak', unit: 'ms', higher: 'a slower build' },
    { id: 'decay_ms', words: 'Decay time, 90% to 10% of the peak', unit: 'ms', higher: 'a slower fade' },
    { id: 'sharpness', words: 'Sharpness: peak over the sink’s area in time', unit: '1/ms', higher: 'fast and strong; lower is slow and diffuse' },
    { id: 'area_t', words: 'Sink over time, at the blob’s depth', unit: 'CSD·ms', higher: 'more sink at that depth' },
    { id: 'area', words: 'Total sink, over time and depth', unit: 'CSD·ms·µm', higher: 'more sink in all' },
    { id: 'spread_um', words: 'Depth spread (depth above half its peak)', unit: 'µm', higher: 'a sink spread over more depth' },
  ];

  /* ---------- state: survives every render of the room ---------- */
  const B = {
    root: null, secs: {}, building: null,
    list: null, listErr: null, listBusy: false,
    choice: null, impSeen: null,
    dataKey: null, data: null, dataErr: null, dataBusy: false, dataT0: 0, dataGen: 0, timer: null,
    byLabel: new Map(), byGid: new Map(),
    blob: 'top', cls: 'all', measure: 'peak', by: 'group', scale: 'same',
    picking: false, picks: new Set(), picksFor: null, pickT: null, moreOpen: new Set(),
    cmp: new Map(), cmpErr: new Map(), cmpBusy: new Set(),
    all: new Map(), allErr: new Map(), allBusy: new Set(),
  };

  /* ---------- small things ---------- */
  const el = (t, a, k) => K().el(t, a, k);
  const tx = (s) => document.createTextNode(String(s));
  const tok = (n, fb) => K().tok(n, fb);
  const S = () => K().S;
  const keyOf = (x) => (x && x.artifact_id ? x.artifact_id + '@' + x.version : '');
  const pl = (n, w, many) => n + ' ' + (n === 1 ? w : (many || w + 's'));
  const minus = (s) => String(s).replace(/^-/, '−');
  const ok = (v) => v != null && isFinite(v);
  const grp = (r) => (String((r && r.group) || '').toUpperCase() === 'CTL' ? 'CTL' : 'PTEN');
  const gcol = (lab) => tok((GC[lab] || ['--ink-2'])[0], (GC[lab] || [0, '#464b53'])[1]);
  const gvar = (lab) => 'var(' + (GC[lab] || ['--ink-2'])[0] + ')';
  const hash = (s) => { let x = 7; for (const ch of String(s)) x = (x * 31 + ch.charCodeAt(0)) % 1000; return x / 1000; };
  const pw = (p) => (p == null ? '—' : p < 0.001 ? '< 0.001' : '= ' + String(Number((+p).toPrecision(2))));
  const pct = (v) => (ok(v) ? (v * 100 < 10 ? (v * 100).toFixed(1) : String(Math.round(v * 100))) + '%' : '—');
  function nf(v, unit) {
    if (!ok(v)) return '—';
    const a = Math.abs(v);
    let s;
    if (unit === 'ms') s = a >= 100 ? v.toFixed(0) : v.toFixed(1);
    else if ((unit === 'µm' || unit === 'um') && a >= 10) s = v.toFixed(0);
    else if (a === 0) s = '0';
    else if (a >= 1000) s = Number(v.toPrecision(3)).toLocaleString('en-US');
    else s = String(Number(v.toPrecision(3)));
    if (Number(s.replace(/,/g, '')) === 0) s = s.replace('-', '');
    return minus(s);
  }
  // "p = 0.034 · q = 0.21", kept on one line each.
  const pq = (t) => 'p ' + pw(t.p).replace(' ', ' ') + ' · q ' + (t.q == null ? '—' : pw(t.q).replace(' ', ' '));
  const sgnf = (v, unit) => (ok(v) ? (v > 0 ? '+' : '') + nf(v, unit) : '—');
  function when(at) {
    if (!at) return '';
    const d = new Date(at);
    if (isNaN(d)) return String(at);
    try { return d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }); } catch (e) { return d.toLocaleString(); }
  }
  const measures = () => ((B.data && B.data.measures) || MEASURES0);
  const meas = (id) => measures().find((m) => m.id === id) || measures()[0];
  const short = (m) => String(m.words).split(/[(:,]/)[0].trim();
  const clsKey = () => (B.cls === 'all' ? 'all' : B.cls);
  const clsArg = () => (B.cls === 'all' ? 'all' : Number(B.cls));
  const blobsShown = () => (B.blob === 'both' ? ['top', 'bottom'] : [B.blob]);
  const minRecs = () => (B.data && B.data.min_recs) || 3;
  const recs = () => (B.data && B.data.recordings) || [];

  /* ---------- picks: remembered in this browser, per Impression ---------- */
  function loadPicks(aid) {
    if (B.picksFor === aid) return;
    B.picksFor = aid;
    B.picks = new Set();
    try {
      const s = window.localStorage.getItem('erBlobs.picks.' + aid);
      const a = s ? JSON.parse(s) : [];
      if (Array.isArray(a)) for (const g of a) B.picks.add(String(g));
    } catch (e) { /* no storage: the picks last as long as the page */ }
  }
  function savePicks() {
    try { window.localStorage.setItem('erBlobs.picks.' + B.picksFor, JSON.stringify(Array.from(B.picks))); }
    catch (e) { /* no storage */ }
  }
  const picksHere = () => recs().filter((r) => B.picks.has(r.gid)).map((r) => r.gid).sort();
  const picksArg = () => (B.by === 'pick' ? picksHere() : []);
  function pickWords() {
    const n = picksHere().length;
    if (!n) return B.picking ? 'Tick the recordings on their cards.' : 'None picked.';
    return pl(n, 'recording') + ' picked' + (B.by === 'pick' ? '.' : ': group by ‘Picked vs the rest’ to compare them.');
  }

  /* ---------- painting: the tab, or one part of it ---------- */
  const SECS = ['head', 'ctl', 'recs', 'group', 'table'];
  const BUILD = {};
  function fill() {
    dropLive(null);
    B.secs = {};
    const kids = SECS.map((name) => (B.secs[name] = el('div', { class: 'erb-sec', 'data-sec': name })));
    B.root.replaceChildren(...kids);
    for (const name of SECS) build(name);
    later();
  }
  function build(name) {
    const box = B.secs[name];
    if (!box) return;
    dropLive(name);
    B.building = name;
    let got;
    try { got = BUILD[name](); } catch (e) {
      got = el('p', { class: 'err', text: 'This part of Blob Analysis could not be shown: ' + e.message });
    }
    B.building = null;
    box.replaceChildren(...[].concat(got || []).filter(Boolean));
  }
  const live = () => (B.root && B.root.isConnected);
  function paint(...names) {
    if (!live()) return;
    for (const n of names) build(n);
    later();
  }
  function refill() { if (live()) fill(); }
  function later() { requestAnimationFrame(drawMine); setTimeout(drawMine, 60); }
  function drawMine() {
    const kit = K();
    if (!kit) return;
    for (const f of kit.live.slice()) if (f.blobs) { try { f(); } catch (e) { /* a canvas that left */ } }
  }
  function dropLive(sec) {
    const L = K().live;
    for (let i = L.length - 1; i >= 0; i--) if (L[i].blobs && (sec == null || L[i].erbSec === sec)) L.splice(i, 1);
  }
  function canvas(cls, draw, label) {
    const cv = el('canvas', { class: cls, role: 'img', 'aria-label': label || null });
    const f = () => draw(cv);
    f.blobs = true;
    f.erbSec = B.building;
    K().live.push(f);
    return cv;
  }
  const errLine = (words, again) => el('p', { class: 'err' }, [tx(words + ' '),
    el('button', { class: 'btn small', text: 'Try again', onclick: again })]);

  /* ---------- loading ---------- */
  async function ensureList(force) {
    if (B.listBusy || (!force && (B.list || B.listErr))) return;
    B.listBusy = true;
    B.listErr = null;
    try {
      const got = await K().api('/api/extraction/impressions');
      B.list = got.impressions || [];
    } catch (e) {
      B.listErr = e.message;
    }
    B.listBusy = false;
    refill();
  }

  /* The one on show: the one picked here; else the one just taken; else the
     newest of the set on show; else the newest. */
  function current() {
    const list = B.list || [];
    const has = (x) => x && list.some((i) => i.artifact_id === x.artifact_id
      && (i.version === x.version || (i.versions || []).some((v) => v.v === x.version)));
    if (has(B.choice)) return B.choice;
    const imp = S().impression;
    if (imp && imp.artifact_id) return { artifact_id: imp.artifact_id, version: imp.version };
    const mine = list.filter((i) => (i.subject || {}).folder === S().folder);
    const it = mine[0] || list[0];
    return it ? { artifact_id: it.artifact_id, version: it.version } : null;
  }

  function ensureData(cur) {
    const key = keyOf(cur);
    if (B.dataKey === key && (B.data || B.dataBusy || B.dataErr)) return;
    B.dataKey = key;
    B.data = null;
    B.dataErr = null;
    B.dataBusy = true;
    B.dataT0 = Date.now();
    const gen = ++B.dataGen;
    startTimer();
    K().post('/api/extraction/blobs', { artifact_id: cur.artifact_id, version: cur.version }).then((got) => {
      if (gen !== B.dataGen) return;
      B.data = got;
      B.byLabel = new Map();
      B.byGid = new Map();
      for (const r of got.recordings || []) {
        if (!B.byLabel.has(r.session_label)) B.byLabel.set(r.session_label, r);
        B.byGid.set(r.gid, r);
      }
      if (!measures().some((m) => m.id === B.measure)) B.measure = measures()[0].id;
      loadPicks(cur.artifact_id);
    }, (e) => {
      if (gen === B.dataGen) B.dataErr = e.message;
    }).catch((e) => {
      if (gen === B.dataGen) { B.data = null; B.dataErr = e.message; }
    }).then(() => {
      if (gen !== B.dataGen) return;
      B.dataBusy = false;
      stopTimer();
      refill();
    });
  }
  function startTimer() {
    stopTimer();
    B.timer = setInterval(() => {
      if (!B.root) return;
      const s = Math.round((Date.now() - B.dataT0) / 1000);
      for (const n of B.root.querySelectorAll('.erb-secs')) n.textContent = pl(s, 'second') + ' so far.';
    }, 1000);
  }
  function stopTimer() { if (B.timer) clearInterval(B.timer); B.timer = null; }

  const cmpKey = (blob) => [B.dataKey, B.measure, blob, B.cls, B.by, picksArg().join(',')].join('|');
  const allKey = () => [B.dataKey, B.cls, B.by, picksArg().join(',')].join('|');
  function trim(m) { while (m.size > 48) m.delete(m.keys().next().value); }
  function ensureCmp(blob) {
    const key = cmpKey(blob);
    if (B.cmp.has(key) || B.cmpErr.has(key) || B.cmpBusy.has(key)) return;
    const cur = current();
    if (!cur) return;
    B.cmpBusy.add(key);
    K().post('/api/extraction/blobs/compare', { artifact_id: cur.artifact_id, version: cur.version,
      measure: B.measure, blob, cls: clsArg(), by: B.by, picks: picksArg() })
      .then((got) => { B.cmp.set(key, got); trim(B.cmp); }, (e) => { B.cmpErr.set(key, e.message); })
      .then(() => {
        B.cmpBusy.delete(key);
        if (blobsShown().some((b) => cmpKey(b) === key)) paint('group');
      });
  }
  function ensureAll() {
    const key = allKey();
    if (B.all.has(key) || B.allErr.has(key) || B.allBusy.has(key)) return;
    const cur = current();
    if (!cur) return;
    B.allBusy.add(key);
    K().post('/api/extraction/blobs/all', { artifact_id: cur.artifact_id, version: cur.version,
      cls: clsArg(), by: B.by, picks: picksArg() })
      .then((got) => { B.all.set(key, got); trim(B.all); }, (e) => { B.allErr.set(key, e.message); })
      .then(() => {
        B.allBusy.delete(key);
        if (key !== allKey()) return;
        paint('table');
        putTests();
      });
  }
  /* The /all row for this measure and blob: it carries q. */
  function allRow(blob) {
    const got = B.all.get(allKey());
    return got ? (got.rows || []).find((r) => r.measure === B.measure && r.blob === blob) || null : null;
  }

  /* ---------- the header ---------- */
  BUILD.head = function () {
    ensureList();
    const kids = [el('div', { class: 'bar' }, [el('h2', { text: 'Blob Analysis' }),
      el('span', { class: 'muted small', text: 'The top and the bottom sink of every dentate spike, timed and sized, '
        + 'one recording at a time.' })])];
    let cur = null;
    if (B.listErr) kids.push(errLine('The Impressions could not be listed: ' + B.listErr, () => ensureList(true)));
    else if (!B.list) kids.push(el('p', { class: 'muted', text: 'Looking for Impressions…' }));
    else if (!B.list.length) {
      kids.push(el('p', { class: 'empty erb-none', text: NONE_YET }));
      kids.push(el('div', { class: 'acts' }, [
        el('button', { class: 'btn small', text: 'Go to Recordings', onclick: () => {
          const b = document.querySelector('#erSubs button[data-sub="recordings"]');
          if (b) b.click();
        } }),
        el('button', { class: 'btn small', text: 'Look again', onclick: () => ensureList(true) })]));
    } else {
      cur = current();
      kids.push(picker(cur));
      kids.push(impLine(cur));
      ensureData(cur);
    }
    const d = B.data;
    kids.push(el('p', { class: 'erb-filter', id: 'erbFilter' }, [el('b', { text: 'Filter: ' }),
      tx(((d && d.filter) || '5–100 Hz, 60 Hz notched.') + ' ' + ((d && d.filter_note) || FILTER_NOTE))]));
    if (cur && B.dataBusy) {
      kids.push(el('p', { class: 'erb-wait', id: 'erbWait' }, [
        tx('Measuring every recording of this Impression. The first time, each recording is fitted again in its band, '
           + 'so this can take a minute. '),
        el('span', { class: 'erb-secs', text: pl(Math.round((Date.now() - B.dataT0) / 1000), 'second') + ' so far.' })]));
    }
    if (cur && B.dataErr) {
      kids.push(errLine('Not measured: ' + B.dataErr, () => { B.dataKey = null; B.dataErr = null; refill(); }));
    }
    if (d) kids.push(...whoIsIn(d));
    return el('div', { class: 'card erb-head', id: 'erbHead' }, kids);
  };

  function picker(cur) {
    const opts = B.list.map((i) => {
      const name = (i.subject || {}).folder_name || (i.subject || {}).folder || i.artifact_id;
      const vs = (i.versions || []).length ? i.versions.slice().sort((a, b) => b.v - a.v)
        : [{ v: i.version, at: i.at, by: i.by, summary: i.summary }];
      return el('optgroup', { label: '‘' + name + '’' }, vs.map((v) => el('option', {
        value: i.artifact_id + '|' + v.v,
        selected: (cur && i.artifact_id === cur.artifact_id && v.v === cur.version) || null,
        text: '‘' + name + '’ v' + v.v + (v.nickname ? ' “' + v.nickname + '”' : '') + (v.at ? ' · ' + day(v.at) : '')
          + (v.here === false ? ' · not here yet' : '') })));
    });
    return el('div', { class: 'ctl erb-imp' }, [el('span', { class: 'lab', text: 'Impression' }),
      el('select', { id: 'erbImp', onchange: (e) => {
        const at = e.target.value.lastIndexOf('|');
        B.choice = { artifact_id: e.target.value.slice(0, at), version: Number(e.target.value.slice(at + 1)) };
        refill();
      } }, opts),
      el('button', { class: 'btn small', text: 'Look again', title: 'Ask again for the Impressions taken, here and elsewhere.',
        onclick: () => ensureList(true) })]);
  }
  // The option's own words are short, so a phone's select shows them whole;
  // the line under it says the rest.
  function day(at) {
    const d = new Date(at);
    if (isNaN(d)) return String(at);
    try { return d.toLocaleDateString([], { day: 'numeric', month: 'short' }); } catch (e) { return d.toDateString(); }
  }
  function sumWords(s) {
    if (!s || s.recordings == null) return '';
    return ' Locked in: ' + pl(s.recordings, 'recording') + (s.separable != null ? ', ' + s.separable + ' separable' : '')
      + (s.events != null ? ', ' + pl(s.events, 'event') : '') + '.';
  }
  function impLine(cur) {
    const i = (B.list || []).find((x) => x.artifact_id === cur.artifact_id) || {};
    const v = (i.versions || []).find((x) => x.v === cur.version) || (i.version === cur.version ? i : {});
    const name = (i.subject || {}).folder_name || (B.data && B.data.folder_name) || '';
    return el('p', { class: 'erb-impl', id: 'erbImpLine' }, [
      el('b', { text: 'Impression of ‘' + name + '’ · v' + cur.version + (v.nickname ? ' “' + v.nickname + '”' : '') }),
      tx((v.at ? ' · taken ' + when(v.at) : '') + (v.by ? ' by ' + v.by : '') + '.' + sumWords(v.summary || i.summary)),
      v.note ? el('span', { class: 'muted', text: ' Its note: ' + v.note }) : null,
      v.here === false ? el('span', { class: 'muted', text: ' It was taken on another computer.' }) : null]);
  }
  function whoIsIn(d) {
    const rs = d.recordings || [];
    const yes = rs.filter((r) => r.call === 'yes').length;
    const no = rs.filter((r) => r.call === 'no').length;
    const nods1 = rs.filter((r) => r.call === 'no_ds1').length;
    const ctl = rs.filter((r) => grp(r) === 'CTL').length;
    const ev = rs.reduce((a, r) => a + (((r.summary || {}).n) || 0), 0);
    const out = [el('p', { class: 'erb-in', id: 'erbIn' }, [el('b', { text: pl(rs.length, 'recording') + ' in' }),
      tx(': ' + yes + ' separable (DS1 and DS2), ' + no + ' not separable (DS, one kind)'
        + (nods1 ? ', ' + nods1 + ' no DS1 (all DS2)' : '') + ' · CTL ' + ctl + ', PTEN '
        + (rs.length - ctl) + ' · ' + pl(ev, 'event') + '.')])];
    const left = d.left_out || [];
    out.push(el('p', { class: 'small erb-left', id: 'erbLeft', text: left.length
      ? 'Left out: ' + left.map((x) => (x.session_label || x.gid) + ' (' + x.why + ')').join('; ') + '.'
      : 'Nobody was left out.' }));
    out.push(el('p', { class: 'muted small', text: 'Every number is measured on each event, and the recording is the '
      + 'unit: a recording’s median counts once in its group, whether it has 700 events or 60. Averages and tests need '
      + 'at least ' + minRecs() + ' recordings a group.' }));
    return out;
  }

  /* ---------- the controls ---------- */
  BUILD.ctl = function () {
    if (!B.data) return null;
    const kit = K();
    // "No DS1" (2026-11-13): all its events DS2, so it is in DS2 and All DS.
    const nOf = (k) => recs().filter((r) => (k === 'all' ? true : k === '0' ? r.call === 'no'
      : r.call === 'yes' || (k === '2' && r.call === 'no_ds1'))).length;
    const ctl = (lab, kids) => el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: lab })].concat(kids));
    return el('div', { class: 'card erb-ctl', id: 'erbCtl' }, [el('div', { class: 'bar' }, [
      ctl('Blob', [kit.seg(BLOBS, B.blob, (v) => { B.blob = v; paint('ctl', 'recs', 'group', 'table'); }, 'erbBlob')]),
      ctl('Class', [kit.seg(CLASSES.map(([v, w, t]) => [v, w, t + ' ' + pl(nOf(v), 'recording') + '.']), B.cls,
        (v) => { B.cls = v; paint('ctl', 'recs', 'group', 'table'); }, 'erbCls')]),
      ctl('Measure', [el('select', { id: 'erbMeasure', onchange: (e) => {
        B.measure = e.target.value;
        markMeasure();                 // each recording's card, in place
        paint('group', 'table');
      } },
        measures().map((m) => el('option', { value: m.id, selected: m.id === B.measure || null,
          text: m.words + ' (' + m.unit + ')' })))]),
      ctl('Group by', [kit.seg(BY, B.by, (v) => { B.by = v; paint('ctl', 'group', 'table'); }, 'erbBy')]),
      ctl('Curves', [kit.seg([['same', 'one scale for every card', 'Every card’s curves on one scale, so they compare by eye.'],
                              ['own', 'each its own', 'Each card scaled to itself: its shape is easier to read.']],
        B.scale, (v) => { B.scale = v; paint('ctl'); drawMine(); }, 'erbScale')]),
    ]), el('div', { class: 'bar erb-pickbar' }, [
      el('button', { class: 'btn small' + (B.picking ? ' primary' : ''), id: 'erbPicking', 'aria-pressed': String(B.picking),
        text: B.picking ? 'Done picking' : 'Pick recordings',
        title: 'Tick recordings on their cards; then group by ‘Picked vs the rest’. Remembered in this browser.',
        onclick: () => { B.picking = !B.picking; paint('ctl', 'recs'); } }),
      el('span', { class: 'small', id: 'erbPickN', text: pickWords() }),
      picksHere().length ? el('button', { class: 'btn small', id: 'erbPickNone', text: 'Pick none', onclick: () => {
        B.picks.clear(); savePicks(); paint('ctl', 'recs'); if (B.by === 'pick') paint('group', 'table');
      } }) : null,
    ])]);
  };
  function togglePick(gid, on) {
    if (on) B.picks.add(gid); else B.picks.delete(gid);
    savePicks();
    const card = B.root.querySelector('.erb-rec[data-gid="' + cssq(gid) + '"]');
    if (card) card.classList.toggle('erb-picked', on);
    paint('ctl');
    if (B.by === 'pick') {
      clearTimeout(B.pickT);
      B.pickT = setTimeout(() => paint('group', 'table'), 450);
    }
  }
  const cssq = (s) => (window.CSS && CSS.escape ? CSS.escape(String(s)) : String(s).replace(/["\\]/g, '\\$&'));

  /* ---------- each recording ---------- */
  /* The classes a card draws: under All DS, the ones the recording has (DS1
     and DS2 where it separates, its one kind where not); else the one chosen,
     where the recording has it. */
  function cardKeys(r) {
    const c = ((r.summary || {}).cls) || {};
    if (B.cls === 'all') {
      const ks = r.call === 'yes' ? ['1', '2', '3'] : r.call === 'no_ds1' ? ['2'] : ['0'];
      const got = ks.filter((k) => c[k]);
      return got.length ? got : (c.all ? ['all'] : []);
    }
    if ((B.cls === '0') !== (r.call === 'no')) return [];
    if (B.cls === '1' && r.call === 'no_ds1') return [];
    return c[B.cls] ? [B.cls] : [];
  }
  const CCOL = { 1: ['--ds1', '#2d6cdf'], 2: ['--ds2', '#d9791a'], 0: ['--ink-2', '#464b53'], all: ['--ink', '#17181b'],
                 3: ['--ds3', '#1f9d5c'], 4: ['--unsure', '#8a8f98'] };

  BUILD.recs = function () {
    if (!B.data) return null;
    const rs = recs().slice().sort((a, b) => (grp(a) === 'CTL' ? 0 : 1) - (grp(b) === 'CTL' ? 0 : 1)
      || String(a.session_label).localeCompare(String(b.session_label), undefined, { numeric: true }));
    const sw = (v, cls, w) => el('span', {}, [el('span', { class: 'erb-sw' + (cls ? ' ' + cls : ''), style: '--sw: var(' + v + ')' }), tx(w)]);
    const kids = [
      el('div', { class: 'bar' }, [el('h2', { text: 'Each recording' }),
        el('span', { class: 'muted small', text: CLS_NAME[B.cls] + ' · ' + blobsShown().map((b) => BLOB_NAME[b].toLowerCase()).join(' and ') })]),
      el('p', { class: 'erb-cap', text: 'Each card: the blob’s activity curve, its sink over time at its own depth (up is sink, '
        + '0 ms is the stamp), the mean over the recording’s events ± SEM; and the median [middle half, 25th to 75th '
        + 'percentile] of every number over its events' + (B.cls === 'all' ? ', all its DS together' : '')
        + '. “Cut off” counts events whose number the −50 to +50 ms window cut short.' }),
      el('div', { class: 'erb-legend' }, [sw('--ds1', '', 'DS1'), sw('--ds2', '', 'DS2'), sw('--ink-2', '', 'DS, one kind'),
        sw('--ink-3', '', 'solid: top blob'), sw('--ink-3', 'dash', 'dashed: bottom blob')]),
    ];
    if (!rs.length) {
      kids.push(el('p', { class: 'empty', text: 'No recording of this Impression could be measured.' }));
    } else {
      kids.push(el('div', { class: 'erb-recs', id: 'erbRecs' }, rs.map(recCard)));
    }
    return el('div', { class: 'card', id: 'erbRecsCard' }, kids);
  };

  function recCard(r) {
    const sm = r.summary || {};
    const keys = cardKeys(r);
    const picked = B.picks.has(r.gid);
    const g = grp(r);
    const head = el('div', { class: 'erb-rh' }, [
      el('b', { text: r.session_label || r.gid }),
      el('span', { class: 'chip erb-g', style: '--erb-gc: ' + gvar(g), text: g }),
      el('span', { class: 'chip ' + (r.call === 'yes' ? 'yes' : 'no'),
        text: r.call === 'yes' ? 'separable' : r.call === 'no_ds1' ? 'no DS1 · every event DS2' : 'not separable · one kind' }),
      el('span', { class: 'chip', text: pl(sm.n || 0, 'event') + (r.call === 'yes'
        ? ' · DS1 ' + (((sm.cls || {})['1'] || {}).n || 0) + ' · DS2 ' + (((sm.cls || {})['2'] || {}).n || 0) : '') }),
      g === 'PTEN' && ok(r.ko_pct) ? el('span', { class: 'chip', text: Math.round(r.ko_pct) + '% KO' }) : null,
      r.flip ? el('span', { class: 'chip swapped', text: 'DS1 and DS2 swapped by hand' }) : null,
      !B.picking && picked ? el('span', { class: 'chip erb-pk', text: 'picked' }) : null,
      B.picking ? el('label', { class: 'erb-pick' }, [
        el('input', { type: 'checkbox', checked: picked || null, 'data-gid': r.gid,
          onchange: (e) => togglePick(r.gid, e.target.checked) }), el('span', { text: 'pick' })]) : null,
    ]);
    const kids = [head];
    if (!keys.length) {
      kids.push(el('p', { class: 'small erb-off-why', text: B.cls === '0'
        ? 'Separable, so its events are DS1 and DS2, not one kind.'
        : r.call === 'no_ds1' ? 'Called no DS1: every event here is DS2.'
        : r.call !== 'yes' ? 'Not separable, so no ' + CLS_NAME[B.cls] + ': its events are one class (DS, one kind).'
          : 'No ' + CLS_NAME[B.cls] + ' events here.' }));
    } else {
      kids.push(el('p', { class: 'erb-mline', 'data-gid': r.gid, text: mlineWords(r) }));
      kids.push(canvas('erb-rc', (cv) => drawRec(cv, r), 'Activity curves of ' + (r.session_label || r.gid)));
      kids.push(recTable(r));
      const sm = r.summary || {};
      if (sm.third_big && sm.n && sm.third_big / sm.n >= 0.1) {
        kids.push(el('p', { class: 'erb-note erb-warn', text: sm.third_big + ' of ' + sm.n + ' events have a third sink at least '
          + 'half the second’s: top and bottom may swap bands here.' }));
      }
      const notes = recNotes(r);
      if (notes) {
        kids.push(el('details', { class: 'erb-more', open: B.moreOpen.has(r.gid) || null,
          ontoggle: (e) => { if (e.target.open) B.moreOpen.add(r.gid); else B.moreOpen.delete(r.gid); } }, [
          el('summary', { text: 'More about its events' }), el('p', { class: 'erb-note', text: notes })]));
      }
    }
    return el('div', { class: 'erb-rec' + (keys.length ? '' : ' erb-off') + (picked ? ' erb-picked' : ''), 'data-gid': r.gid }, kids);
  }

  function recTable(r) {
    const e = ((r.summary || {}).cls || {})[clsKey()] || {};
    const bl = blobsShown();
    const headRow = el('tr', {}, [el('th', { text: 'Median [middle half]' })].concat(bl.map((b) => el('th', {}, [
      tx(BLOB_NAME[b]), el('span', { class: 'erb-open muted', text: 'in ' + ((e[b] || {}).n || 0) + ' of ' + (e.n || 0) + ' events' })]))));
    const rows = measures().map((m) => el('tr', { 'data-m': m.id, class: m.id === B.measure ? 'erb-cur' : null }, [
      el('td', { title: m.words }, [tx(short(m) + ' '), el('span', { class: 'muted', text: '(' + m.unit + ')' })])].concat(bl.map((b) => {
        const st = (((e[b] || {}).stats) || {})[m.id] || {};
        return el('td', { class: 'v' }, [
          tx(ok(st.median) ? nf(st.median, m.unit) + ' [' + nf(st.q25, m.unit) + ' – ' + nf(st.q75, m.unit) + ']' : '—'),
          st.open ? el('span', { class: 'erb-open', text: st.open + ' cut off by the window' }) : null]);
      }))));
    return el('table', { class: 'erb-mt' }, [el('thead', {}, [headRow]), el('tbody', {}, rows)]);
  }

  function recNotes(r) {
    const sm = r.summary || {};
    const e = (sm.cls || {})[clsKey()] || {};
    const out = [];
    const humps = sm.sink === 'humps';
    for (const b of blobsShown()) {
      const x = e[b] || {};
      const bits = [];
      if (x.from_one) bits.push(x.from_one + (humps ? ' from events with sink in this hump only' : ' from a single sink placed by its depth'));
      if (x.edge_peak) bits.push(x.edge_peak + ' peaked at the edge of the search window');
      if (bits.length) out.push(BLOB_NAME[b] + ': ' + bits.join(', ') + '.');
    }
    const kinds = sm.kinds || {};
    const ks = KIND_ORDER.filter((k) => kinds[k]).concat(Object.keys(kinds).filter((k) => !KIND_ORDER.includes(k) && kinds[k]));
    if (ks.length) {
      const kw = humps ? Object.assign({}, KIND_WORDS, { two: 'sink in both humps', one: 'sink in one hump only' }) : KIND_WORDS;
      out.push('Of its ' + pl(sm.n || 0, 'event') + ', all its DS: ' + ks.map((k) => kinds[k] + ' with ' + (kw[k] || k))
        .join(' · ') + '.');
    }
    if (humps) {
      out.push('Top and bottom are the recording’s two humps, each event’s sink taken whole in each'
        + (sm.camel ? '; ' + pl(sm.camel, 'event') + ' had a notch inside a hump, kept inside its blob.' : '.'));
    }
    if (sm.third_big) out.push(sm.third_big + ' have a third sink at least half the second’s.');
    return out.join(' ');
  }

  /* The curves a card draws, and the scale they share. */
  function pairsOf(r) {
    const out = [];
    for (const k of cardKeys(r)) for (const b of blobsShown()) {
      const c = ((((r.summary || {}).cls || {})[k] || {})[b] || {}).curve;
      if (c && c.mean) out.push({ k, b, c });
    }
    return out;
  }
  function rangeOf(rs) {
    let lo = 0, hi = 0;
    for (const r of rs) for (const p of pairsOf(r)) {
      p.c.mean.forEach((m, i) => {
        if (!ok(m)) return;
        const s = p.c.sem && ok(p.c.sem[i]) ? p.c.sem[i] : 0;
        lo = Math.min(lo, m - s); hi = Math.max(hi, m + s);
      });
    }
    if (!(hi > lo)) hi = lo + 1;
    const pad = (hi - lo) * 0.06;
    return [lo < 0 ? lo - pad : lo, hi + pad];
  }
  /* One scale for every card: worked out once per selection, not per card. */
  function sharedRange() {
    const k = [B.dataKey, B.cls, B.blob].join('|');
    if (B.rangeK !== k) { B.rangeK = k; B.range = rangeOf(recs()); }
    return B.range;
  }
  function drawRec(cv, r) {
    const t = (r.summary || {}).t_ms || [];
    if (t.length < 2) return;
    const [y0, y1] = B.scale === 'same' ? sharedRange() : rangeOf([r]);
    const P = plot(cv, { x0: t[0], x1: t[t.length - 1], y0, y1, L: 42, B: 28, T: 16, yUnit: 'CSD, up is sink', xUnit: 'ms' });
    if (!P) return;
    marks(P);
    const pairs = pairsOf(r);
    P.clip();
    for (const p of pairs) {
      if (!p.c.sem) continue;
      P.g.fillStyle = col(p.k);
      P.g.globalAlpha = 0.16;
      band(P, t, p.c.mean, p.c.sem);
      P.g.globalAlpha = 1;
    }
    for (const p of pairs) {
      P.g.strokeStyle = col(p.k);
      P.g.lineWidth = 2;
      P.g.setLineDash(p.b === 'bottom' ? [5, 3] : []);
      line(P, t, p.c.mean);
    }
    P.g.setLineDash([]);
    for (const p of pairs) markOn(P, r, p);
    P.unclip();
  }

  /* THE MEASURE ON EACH CARD (2026-11-13: the measure picked "isn't
     changing" anything under it -- the cards drew the same curve and table
     whatever it was). Each card now says the measure's median, marks its
     row, and draws it on the curve where it lives in time: from the
     per-event medians, so the mark is the number, not the mean curve's own
     geometry. Peak: a level. When it peaks: a line. How long it lasts: a
     bar at half the peak, centred on when it peaks. Rise and decay: a bar
     before and after the peak. The rest are not times: the line says them. */
  function statOf(r, k, b, id) {
    return ((((((r.summary || {}).cls || {})[k] || {})[b] || {}).stats) || {})[id] || {};
  }
  function markOn(P, r, p) {
    const id = B.measure;
    const med = (x) => { const v = statOf(r, p.k, p.b, x).median; return ok(v) ? +v : null; };
    const pk = med('peak'), lat = med('latency_ms');
    const g = P.g;
    g.save();
    g.strokeStyle = col(p.k);
    g.fillStyle = col(p.k);
    g.lineWidth = 2.5;
    g.globalAlpha = 0.9;
    g.setLineDash(p.b === 'bottom' ? [5, 3] : []);
    const hbar = (a, z, y) => {
      if (a == null || z == null || y == null) return;
      const ya = P.Y(y);
      g.beginPath(); g.moveTo(P.X(a), ya); g.lineTo(P.X(z), ya); g.stroke();
      g.setLineDash([]);
      for (const x of [a, z]) { g.beginPath(); g.moveTo(P.X(x), ya - 4); g.lineTo(P.X(x), ya + 4); g.stroke(); }
    };
    if (id === 'peak' && pk != null) {
      g.setLineDash([2, 3]);
      g.beginPath(); g.moveTo(P.L, P.Y(pk)); g.lineTo(P.L + P.pw, P.Y(pk)); g.stroke();
    } else if (id === 'latency_ms' && lat != null) {
      g.setLineDash([2, 3]);
      g.beginPath(); g.moveTo(P.X(lat), P.T); g.lineTo(P.X(lat), P.T + P.ph); g.stroke();
    } else if (id === 'fwhm_ms' && med('fwhm_ms') != null && lat != null && pk != null) {
      const w = med('fwhm_ms');
      hbar(lat - w / 2, lat + w / 2, pk / 2);
    } else if (id === 'rise_ms' && med('rise_ms') != null && lat != null && pk != null) {
      hbar(lat - med('rise_ms'), lat, pk / 2);
    } else if (id === 'decay_ms' && med('decay_ms') != null && lat != null && pk != null) {
      hbar(lat, lat + med('decay_ms'), pk / 2);
    }
    g.restore();
  }
  /* The measure, said on the card: its median [middle half] for each class
     and blob drawn. */
  function mlineWords(r) {
    const m = meas(B.measure);
    if (!m) return '';
    const parts = pairsOf(r).map((p) => {
      const st = statOf(r, p.k, p.b, m.id);
      const who = (p.k === 'all' ? '' : CLS_NAME[p.k] + ', ') + BLOB_NAME[p.b].toLowerCase();
      return who + ' ' + (ok(st.median) ? nf(st.median, m.unit) + ' [' + nf(st.q25, m.unit) + ' – ' + nf(st.q75, m.unit) + ']'
        : '—');
    });
    return short(m) + ' (' + m.unit + '): ' + (parts.length ? parts.join(' · ') : '—');
  }
  /* A new measure picked: every card's line, row and mark, in place. */
  function markMeasure() {
    if (!live()) return;
    for (const card of B.root.querySelectorAll('.erb-rec')) {
      const r = B.byGid && B.byGid.get(card.dataset.gid);
      const ln = card.querySelector('.erb-mline');
      if (r && ln) ln.textContent = mlineWords(r);
      for (const tr of card.querySelectorAll('table.erb-mt tr[data-m]')) {
        tr.classList.toggle('erb-cur', tr.dataset.m === B.measure);
      }
    }
    later();
  }
  const col = (k) => tok((CCOL[k] || CCOL.all)[0], (CCOL[k] || CCOL.all)[1]);

  /* ---------- drawing ---------- */
  function ticks(lo, hi, n) {
    if (!ok(lo) || !ok(hi) || !(hi > lo)) return { vals: ok(lo) ? [lo] : [], step: 1 };
    const raw = (hi - lo) / Math.max(1, n);
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    const m = raw / p;
    const step = (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
    const vals = [];
    for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-9 && vals.length < 40; v += step) {
      vals.push(Math.abs(v) < step * 1e-9 ? 0 : v);
    }
    return { vals, step };
  }
  function tickText(v, step) {
    const d = Math.max(0, Math.min(6, -Math.floor(Math.log10(step) + 1e-9)));
    if (Math.abs(v) >= 10000 && d === 0) return minus(Number(v.toPrecision(3)).toLocaleString('en-US'));
    return minus(v.toFixed(d));
  }
  /* A plot's frame: grid, ticks and units, and the scales. */
  function plot(cv, o) {
    const s = K().sized(cv);
    if (!s) return null;
    const { g, w, h } = s;
    const L = o.L != null ? o.L : 50, R = o.R != null ? o.R : 12, T = o.T != null ? o.T : 18, Bm = o.B != null ? o.B : 32;
    const pw_ = Math.max(20, w - L - R), ph = Math.max(20, h - T - Bm);
    let { x0, x1, y0, y1 } = o;
    if (!(x1 > x0)) { x0 -= 1; x1 += 1; }
    if (!(y1 > y0)) { y0 -= 1; y1 += 1; }
    const X = (v) => L + ((v - x0) / (x1 - x0)) * pw_;
    const Y = (v) => T + ph - ((v - y0) / (y1 - y0)) * ph;
    g.font = '10px ' + tok('--sans', 'sans-serif');
    g.lineWidth = 1;
    g.setLineDash([]);
    g.globalAlpha = 1;
    const yt = ticks(y0, y1, Math.max(2, Math.floor(ph / 34)));
    g.strokeStyle = tok('--line', '#e3e1db');
    g.fillStyle = tok('--ink-3', '#70757e');
    g.textAlign = 'right';
    for (const v of yt.vals) {
      const y = Math.round(Y(v)) + 0.5;
      g.beginPath(); g.moveTo(L, y); g.lineTo(L + pw_, y); g.stroke();
      g.fillText(o.yFmt ? o.yFmt(v, yt.step) : tickText(v, yt.step), L - 5, y + 3, L - 6);
    }
    const xt = o.xTicks ? { vals: o.xTicks, step: o.xStep || 1 } : ticks(x0, x1, Math.max(2, Math.floor(pw_ / 62)));
    g.strokeStyle = tok('--line-2', '#cfcdc6');
    g.beginPath(); g.moveTo(L, T + ph + 0.5); g.lineTo(L + pw_, T + ph + 0.5); g.stroke();
    g.textAlign = 'center';
    for (const v of xt.vals) {
      const x = Math.round(X(v)) + 0.5;
      g.beginPath(); g.moveTo(x, T + ph); g.lineTo(x, T + ph + 4); g.stroke();
      g.fillText(o.xFmt ? o.xFmt(v, xt.step) : tickText(v, xt.step), x, T + ph + 14);
    }
    g.fillStyle = tok('--ink-2', '#464b53');
    if (o.yUnit) { g.textAlign = 'left'; g.fillText(o.yUnit, 4, 11, w - 8); }
    if (o.xUnit) { g.textAlign = 'right'; g.fillText(o.xUnit, L + pw_, h - 3, pw_); }
    g.textAlign = 'left';
    return { g, w, h, L, T, pw: pw_, ph, X, Y, x0, x1, y0, y1,
      clip() { g.save(); g.beginPath(); g.rect(L, T, pw_, ph); g.clip(); },
      unclip() { g.restore(); } };
  }
  /* The stamp (0 ms) and the zero line. */
  function marks(P) {
    const g = P.g;
    g.strokeStyle = tok('--ink-3', '#70757e');
    g.lineWidth = 1;
    if (P.y0 < 0 && P.y1 > 0) { const y = Math.round(P.Y(0)) + 0.5; g.beginPath(); g.moveTo(P.L, y); g.lineTo(P.L + P.pw, y); g.stroke(); }
    if (P.x0 < 0 && P.x1 > 0) {
      g.setLineDash([3, 3]);
      const x = Math.round(P.X(0)) + 0.5;
      g.beginPath(); g.moveTo(x, P.T); g.lineTo(x, P.T + P.ph); g.stroke();
      g.setLineDash([]);
    }
  }
  function runs(n, good) {
    const out = [];
    let s = -1;
    for (let i = 0; i <= n; i++) {
      const gd = i < n && good(i);
      if (gd && s < 0) s = i;
      if (!gd && s >= 0) { out.push([s, i - 1]); s = -1; }
    }
    return out;
  }
  function line(P, xs, ys) {
    const n = Math.min(xs.length, ys.length);
    for (const [a, b] of runs(n, (i) => ok(xs[i]) && ok(ys[i]))) {
      P.g.beginPath();
      for (let i = a; i <= b; i++) { const x = P.X(xs[i]), y = P.Y(ys[i]); if (i === a) P.g.moveTo(x, y); else P.g.lineTo(x, y); }
      P.g.stroke();
    }
  }
  function band(P, xs, mid, sem) {
    const n = Math.min(xs.length, mid.length, sem.length);
    for (const [a, b] of runs(n, (i) => ok(xs[i]) && ok(mid[i]) && ok(sem[i]))) {
      P.g.beginPath();
      for (let i = a; i <= b; i++) { const x = P.X(xs[i]), y = P.Y(mid[i] + sem[i]); if (i === a) P.g.moveTo(x, y); else P.g.lineTo(x, y); }
      for (let i = b; i >= a; i--) P.g.lineTo(P.X(xs[i]), P.Y(mid[i] - sem[i]));
      P.g.closePath();
      P.g.fill();
    }
  }
  function bandLoHi(P, xs, lo, hi) {
    const n = Math.min(xs.length, lo.length, hi.length);
    for (const [a, b] of runs(n, (i) => ok(xs[i]) && ok(lo[i]) && ok(hi[i]))) {
      P.g.beginPath();
      for (let i = a; i <= b; i++) { const x = P.X(xs[i]), y = P.Y(hi[i]); if (i === a) P.g.moveTo(x, y); else P.g.lineTo(x, y); }
      for (let i = b; i >= a; i--) P.g.lineTo(P.X(xs[i]), P.Y(lo[i]));
      P.g.closePath();
      P.g.fill();
    }
  }

  /* ---------- the groups ---------- */
  BUILD.group = function () {
    if (!B.data || !recs().length) return null;
    if (B.by === 'pick' && !picksHere().length) {
      return el('div', { class: 'card erb-group', id: 'erbGroup' }, [el('h2', { text: 'Picked vs the rest' }),
        el('p', { class: 'empty', text: 'Pick recordings first: press Pick recordings and tick them on their cards.' })]);
    }
    const m = meas(B.measure);
    return blobsShown().map((b) => groupCard(b, m));
  };

  function classOut() {
    const rs = recs();
    const yes = rs.filter((r) => r.call === 'yes').length, no = rs.filter((r) => r.call === 'no').length;
    const nods1 = rs.filter((r) => r.call === 'no_ds1').length;
    if (B.cls === '1' || B.cls === '2') {
      const w = [];
      if (no) w.push('DS1 and DS2 are the separable recordings’ own: the ' + pl(no, 'not separable one', 'not separable ones')
        + ' ' + (no === 1 ? 'is' : 'are') + ' out of this.');
      if (nods1) w.push(B.cls === '2' ? 'The ' + pl(nods1, 'recording', 'recordings') + ' called no DS1 '
        + (nods1 === 1 ? 'is' : 'are') + ' in, every event DS2.' : 'The ' + pl(nods1, 'recording', 'recordings')
        + ' called no DS1 ' + (nods1 === 1 ? 'is' : 'are') + ' out of this.');
      return w.length ? w.join(' ') : null;
    }
    if (B.cls === '0') {
      return yes ? 'DS, one kind is the not separable recordings’ class: the ' + pl(yes, 'separable one', 'separable ones')
        + ' ' + (yes === 1 ? 'is' : 'are') + ' out of this.' : null;
    }
    return 'All DS: every event of every recording, DS1 and DS2 together where a recording separates.';
  }

  function groupCard(blob, m) {
    const key = cmpKey(blob);
    const got = B.cmp.get(key), err = B.cmpErr.get(key);
    if (!got && !err) ensureCmp(blob);
    ensureAll();
    const kids = [
      el('h2', { text: BLOB_NAME[blob] + ' · ' + m.words + ' · ' + CLS_NAME[B.cls] + ' · ' + BY_WORDS[B.by] }),
      el('p', { class: 'erb-cap' }, [tx('In ' + m.unit + '. Higher means ' + m.higher + '. '),
        el('span', { class: 'muted', text: classOut() || '' })]),
    ];
    if (err) kids.push(errLine('Not compared: ' + err, () => { B.cmpErr.delete(key); paint('group'); }));
    else if (!got) {
      kids.push(el('p', { class: 'muted erb-busy', text: 'Comparing the groups: the intervals resample the recordings and the '
        + 'tests shuffle their labels, so this takes a few seconds.' }));
    } else kids.push(...groupBody(got, blob, m));
    return el('div', { class: 'card erb-group', 'data-blob': blob }, kids);
  }

  function groupBody(got, blob, m) {
    const gs = got.groups || [];
    const unit = got.unit || m.unit;
    if (!gs.length) {
      return [el('p', { class: 'empty', text: 'No recording has ' + CLS_NAME[B.cls] + ' with at least ' + MIN_EVENTS
        + ' events that give this number, so there is nothing to compare.' })];
    }
    const out = [];
    out.push(el('p', { class: 'small erb-gn' }, gs.map((g, i) => el('span', {}, [
      tx(i ? ' · ' : ''), el('b', { text: g.label }),
      tx(': ' + pl(g.n_rec, 'recording') + ', ' + pl(g.n_events, 'event') + (g.stats ? '' : ' (' + FEW + ')'))]))));
    if ((got.left_out || []).length) {
      out.push(el('p', { class: 'small', text: 'Left out of this comparison, fewer than ' + MIN_EVENTS + ' events with this number: '
        + got.left_out.map((x) => x.rec + ' (' + x.why + ')').join('; ') + '.' }));
    }
    if (gs.length < 2) {
      out.push(el('p', { class: 'notice small', text: B.by === 'sep' && B.cls !== 'all'
        ? (B.cls === '0' ? 'Only the not separable recordings have DS, one kind: there is no separable side to compare.'
          : 'DS1 and DS2 are the separable recordings’ own: there is no not separable side to compare.')
        : 'Only one group has recordings here, so nothing is compared.' }));
    } else if (!got.compare) {
      out.push(el('p', { class: 'notice small', text: 'No comparison: it needs two groups with at least ' + minRecs()
        + ' recordings each. What each recording shows is below.' }));
    }
    out.push(el('div', { class: 'erb-legend' }, gs.map((g) => el('span', {}, [
      el('span', { class: 'erb-sw dot', style: '--sw: ' + gvar(g.label) }), tx(g.label + ' · ' + pl(g.n_rec, 'recording'))]))
      .concat([el('span', { class: 'muted', text: 'faint: each recording · bold: its group' })])));
    out.push(el('div', { class: 'erb-panels' }, [
      pCurve(got, blob), pHist(got, unit), pEcdf(got, unit), pShift(got, unit, m), pStrip(got, unit),
      el('div', { class: 'erb-panel' }, [el('h3', { text: 'The tests, in words' }),
        el('div', { class: 'erb-tests', 'data-blob': blob }, testsBody(got, blob))]),
    ]));
    return out;
  }
  const panel = (title, cv, cap, extra) => el('div', { class: 'erb-panel' },
    [el('h3', { text: title }), el('p', { class: 'erb-cap', text: cap }), cv].concat(extra || []));
  const fewOf = (got) => (got.groups || []).filter((g) => !g.stats).map((g) => g.label);
  const fewWords = (got, what) => { const f = fewOf(got);
    return f.length ? ' ' + f.join(' and ') + ': ' + FEW + ', so only ' + (f.length === 1 ? 'its' : 'their') + ' recordings’ own ' + what + '.' : ''; };

  /* (a) The mean activity curve per group, each recording's faint behind. */
  function pCurve(got, blob) {
    const cap = 'The blob’s sink over time at its own depth (up is sink, 0 ms is the stamp): bold, each group’s mean of its '
      + 'recordings’ mean curves ± SEM across recordings; faint, each recording’s own.' + fewWords(got, 'curves are drawn');
    return panel('The activity curve', canvas('erb-cv', (cv) => drawGCurve(cv, got, blob), cap), cap);
  }
  function drawGCurve(cv, got, blob) {
    const ck = clsKey();
    const faint = [], bold = [];
    let t = null;
    for (const g of got.groups || []) {
      for (const lab of g.recs || []) {
        const r = B.byLabel.get(lab);
        const c = r && ((((r.summary || {}).cls || {})[ck] || {})[blob] || {}).curve;
        if (c && c.mean) { faint.push({ lab: g.label, mean: c.mean, a: g.curve ? 0.28 : 0.6 }); t = t || r.summary.t_ms; }
      }
      if (g.curve && g.curve.mean) bold.push({ lab: g.label, mean: g.curve.mean, sem: g.curve.sem });
    }
    if (!t) t = ((recs()[0] || {}).summary || {}).t_ms;
    if (!t || t.length < 2) return;
    let lo = 0, hi = 0;
    for (const s of faint.concat(bold)) s.mean.forEach((v, i) => {
      if (!ok(v)) return;
      const e = s.sem && ok(s.sem[i]) ? s.sem[i] : 0;
      lo = Math.min(lo, v - e); hi = Math.max(hi, v + e);
    });
    const pad = (hi - lo) * 0.06 || 1;
    const P = plot(cv, { x0: t[0], x1: t[t.length - 1], y0: lo < 0 ? lo - pad : 0, y1: hi + pad,
      yUnit: 'CSD, up is sink', xUnit: 'ms from the stamp' });
    if (!P) return;
    marks(P);
    P.clip();
    for (const s of faint) {
      P.g.strokeStyle = gcol(s.lab); P.g.globalAlpha = s.a; P.g.lineWidth = 1;
      line(P, t, s.mean);
    }
    P.g.globalAlpha = 1;
    for (const s of bold) {
      if (!s.sem) continue;
      P.g.fillStyle = gcol(s.lab); P.g.globalAlpha = 0.18;
      band(P, t, s.mean, s.sem);
    }
    P.g.globalAlpha = 1;
    for (const s of bold) {
      P.g.strokeStyle = tok('--surface', '#fff'); P.g.lineWidth = 4.5;
      line(P, t, s.mean);
      P.g.strokeStyle = gcol(s.lab); P.g.lineWidth = 2.25;
      line(P, t, s.mean);
    }
    P.unclip();
  }

  /* (b) Overlaid histograms, every recording weighted the same. */
  function pHist(got, unit) {
    const parts = [];
    for (const g of got.groups || []) {
      if (g.hist) {
        if (g.under || g.over) parts.push(g.label + ' ' + pct(g.under) + ' below, ' + pct(g.over) + ' above');
      } else {
        (g.recs || []).forEach((lab, i) => {
          const u = (g.rec_under || [])[i], o = (g.rec_over || [])[i];
          if (u || o) parts.push(lab + ' ' + pct(u) + ' below, ' + pct(o) + ' above');
        });
      }
    }
    const cap = 'Where the events fall: the share of each group’s events in each bin, every recording weighted the same '
      + '(one with 700 events counts as much as one with 60).' + fewWords(got, 'histograms are drawn');
    return panel('Histograms', canvas('erb-cv', (cv) => drawHist(cv, got, unit), cap), cap,
      [el('p', { class: 'erb-note', text: parts.length ? 'Past the bins’ ends (they span the middle 99%): ' + parts.join(' · ') + '.'
        : 'Every event falls inside the bins.' })]);
  }
  function drawHist(cv, got, unit) {
    const e = got.bins || [];
    const nb = e.length - 1;
    if (nb < 1) return;
    const ser = [];
    for (const g of got.groups || []) {
      if (g.hist) ser.push({ lab: g.label, v: g.hist, bold: true });
      else for (const rh of g.rec_hist || []) ser.push({ lab: g.label, v: rh, bold: false });
    }
    let ymax = 0;
    for (const s of ser) for (const v of s.v) if (ok(v)) ymax = Math.max(ymax, v);
    const P = plot(cv, { x0: e[0], x1: e[nb], y0: 0, y1: Math.max(0.01, ymax * 1.1),
      yFmt: (v, st) => (v * 100).toFixed(st * 100 < 1 ? 1 : 0) + '%', yUnit: 'share of events', xUnit: unit });
    if (!P) return;
    const step = (s) => {
      P.g.beginPath();
      P.g.moveTo(P.X(e[0]), P.Y(0));
      for (let i = 0; i < nb; i++) {
        const v = ok(s.v[i]) ? s.v[i] : 0;
        P.g.lineTo(P.X(e[i]), P.Y(v)); P.g.lineTo(P.X(e[i + 1]), P.Y(v));
      }
      P.g.lineTo(P.X(e[nb]), P.Y(0));
    };
    P.clip();
    for (const s of ser.filter((x) => x.bold)) {
      step(s); P.g.closePath(); P.g.fillStyle = gcol(s.lab); P.g.globalAlpha = 0.15; P.g.fill();
    }
    for (const s of ser) {
      step(s); P.g.strokeStyle = gcol(s.lab);
      P.g.globalAlpha = s.bold ? 1 : 0.6; P.g.lineWidth = s.bold ? 2 : 1;
      P.g.stroke();
    }
    P.g.globalAlpha = 1;
    P.unclip();
  }

  /* (c) The ECDFs: what averages hide. */
  function pEcdf(got, unit) {
    const cap = 'What averages hide: each faint line is one recording’s events, the bold line its group’s, every recording '
      + 'weighted the same. Faint lines that fan out are recordings that disagree; two bundles are two kinds of mouse.'
      + fewWords(got, 'lines are drawn');
    return panel('Each recording’s spread (ECDF)', canvas('erb-cv', (cv) => drawEcdf(cv, got, unit), cap), cap);
  }
  function drawEcdf(cv, got, unit) {
    const x = got.ecdf_x || [];
    if (x.length < 2) return;
    const P = plot(cv, { x0: x[0], x1: x[x.length - 1], y0: 0, y1: 1, yFmt: (v) => Math.round(v * 100) + '%',
      yUnit: 'share of events at or below', xUnit: unit });
    if (!P) return;
    const g = P.g;
    g.strokeStyle = tok('--ink-3', '#70757e'); g.setLineDash([3, 3]); g.lineWidth = 1;
    const y5 = Math.round(P.Y(0.5)) + 0.5;
    g.beginPath(); g.moveTo(P.L, y5); g.lineTo(P.L + P.pw, y5); g.stroke(); g.setLineDash([]);
    P.clip();
    for (const gr of got.groups || []) {
      g.strokeStyle = gcol(gr.label); g.globalAlpha = gr.ecdf ? 0.3 : 0.65; g.lineWidth = 1;
      for (const f of gr.rec_ecdf || []) line(P, x, f);
    }
    g.globalAlpha = 1;
    for (const gr of got.groups || []) {
      if (!gr.ecdf) continue;
      g.strokeStyle = tok('--surface', '#fff'); g.lineWidth = 4.5; line(P, x, gr.ecdf);
      g.strokeStyle = gcol(gr.label); g.lineWidth = 2.25; line(P, x, gr.ecdf);
    }
    P.unclip();
  }

  /* (d) The shift function. */
  function deciles(list) {
    const w = list.map((q) => Math.round(q * 100) + '%');
    return w.length < 2 ? w.join('') : w.slice(0, -1).join(', ') + ' and ' + w[w.length - 1];
  }
  function pShift(got, unit, m) {
    const c = got.compare;
    if (!c) {
      return el('div', { class: 'erb-panel' }, [el('h3', { text: 'The shift function' }),
        el('p', { class: 'erb-cap', text: 'It needs two groups with at least ' + minRecs() + ' recordings each.' })]);
    }
    const s = c.shift || {};
    const up = [], down = [];
    (s.q || []).forEach((q, i) => {
      if (ok((s.lo || [])[i]) && s.lo[i] > 0) up.push(q);
      else if (ok((s.hi || [])[i]) && s.hi[i] < 0) down.push(q);
    });
    let read;
    if (!up.length && !down.length) read = 'The interval covers zero at every decile: no part of the distribution clearly moves.';
    else {
      read = (up.length ? c.b + ' sits higher than ' + c.a + ' at the ' + deciles(up) + ' deciles' : '')
        + (up.length && down.length ? ', and lower at the ' + deciles(down) : down.length ? c.b + ' sits lower than ' + c.a
          + ' at the ' + deciles(down) + ' deciles' : '') + '.'
        + (up.length && down.length ? ' Not one shift: the two ends move apart, a different spread.' : '')
        + ' One interval per decile, not corrected for looking at nine: a lead, not a finding.';
    }
    const cap = c.b + ' minus ' + c.a + ' at each tenth of the distribution, with its 95% interval (recordings resampled '
      + (c.n_boot || 2000) + ' times). Above the zero line, ' + c.b + ' is higher there; higher means ' + m.higher + '.';
    return panel('The shift function', canvas('erb-cv', (cv) => drawShift(cv, got, unit), cap), cap,
      [el('p', { class: 'erb-note erb-shift-read', text: read })]);
  }
  function drawShift(cv, got, unit) {
    const c = got.compare;
    const s = (c || {}).shift || {};
    const q = s.q || [];
    if (!q.length) return;
    const vals = [0].concat(s.diff || [], s.lo || [], s.hi || []).filter(ok);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.08 || 1;
    const P = plot(cv, { x0: 0.05, x1: 0.95, y0: lo - pad, y1: hi + pad, xTicks: q, xStep: 0.1,
      xFmt: (v) => Math.round(v * 100) + '%', yUnit: c.b + ' − ' + c.a + ', ' + unit, xUnit: 'decile' });
    if (!P) return;
    const g = P.g;
    g.strokeStyle = tok('--ink-3', '#70757e'); g.setLineDash([4, 3]); g.lineWidth = 1.25;
    const y0 = Math.round(P.Y(0)) + 0.5;
    g.beginPath(); g.moveTo(P.L, y0); g.lineTo(P.L + P.pw, y0); g.stroke(); g.setLineDash([]);
    g.fillStyle = tok('--ink-3', '#70757e'); g.textAlign = 'right';
    g.fillText('no difference', P.L + P.pw - 2, y0 - 4);
    g.textAlign = 'left';
    const colB = gcol(c.b);
    P.clip();
    g.fillStyle = colB; g.globalAlpha = 0.18;
    bandLoHi(P, q, s.lo || [], s.hi || []);
    g.globalAlpha = 1;
    g.strokeStyle = colB; g.lineWidth = 2;
    line(P, q, s.diff || []);
    q.forEach((x, i) => {
      const v = (s.diff || [])[i];
      if (!ok(v)) return;
      g.beginPath(); g.arc(P.X(x), P.Y(v), 4, 0, 6.2832);
      g.fillStyle = colB; g.fill();
      g.strokeStyle = tok('--surface', '#fff'); g.lineWidth = 1.5; g.stroke();
    });
    P.unclip();
  }

  /* (e) The recording medians, a dot each, with the group's median. */
  function pStrip(got, unit) {
    const cap = 'Each dot is one recording’s median; the bar is its group’s median of the medians and the shaded band their '
      + 'middle half. Click a dot to find its card.' + fewWords(got, 'dots are drawn, without a bar');
    const cv = canvas('erb-cv erb-strip', (c) => drawStrip(c, got, unit), cap);
    cv.addEventListener('mousemove', (e) => {
      const p = nearest(cv, e);
      cv.title = p ? p.lab + ': median ' + nf(p.v, unit) + ' ' + unit : '';
    });
    cv.addEventListener('click', (e) => { const p = nearest(cv, e); if (p) findCard(p.gid); });
    return panel('Each recording’s median', cv, cap);
  }
  function nearest(cv, e) {
    const b = cv.getBoundingClientRect();
    const x = e.clientX - b.left, y = e.clientY - b.top;
    let best = null, bd = 144;
    for (const p of cv.__pts || []) { const d = (p.x - x) ** 2 + (p.y - y) ** 2; if (d < bd) { bd = d; best = p; } }
    return best;
  }
  function findCard(gid) {
    if (!gid || !B.root) return;
    const card = B.root.querySelector('.erb-rec[data-gid="' + cssq(gid) + '"]');
    if (!card) return;
    card.scrollIntoView({ block: 'center', behavior: 'smooth' });
    card.classList.add('erb-flash');
    setTimeout(() => card.classList.remove('erb-flash'), 1600);
  }
  function drawStrip(cv, got, unit) {
    const gs = got.groups || [];
    const vals = [];
    for (const g of gs) {
      for (const v of g.medians || []) if (ok(v)) vals.push(v);
      if (g.stats) for (const v of [g.stats.q25, g.stats.q75, g.stats.median]) if (ok(v)) vals.push(v);
    }
    if (!vals.length) { cv.__pts = []; return; }
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (!(hi > lo)) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.1;
    const P = plot(cv, { x0: 0, x1: gs.length, y0: lo - pad, y1: hi + pad, xTicks: [], yUnit: unit, B: 24 });
    if (!P) return;
    const g = P.g;
    const colw = P.pw / gs.length;
    const pts = [];
    gs.forEach((gr, i) => {
      const cx = P.X(i + 0.5);
      const c = gcol(gr.label);
      g.fillStyle = tok('--ink-2', '#464b53'); g.textAlign = 'center';
      g.fillText(gr.label + ' · ' + pl(gr.n_rec, 'recording'), cx, P.T + P.ph + 15, colw - 4);
      g.textAlign = 'left';
      const half = Math.min(46, colw * 0.32);
      if (gr.stats && ok(gr.stats.q25) && ok(gr.stats.q75)) {
        g.fillStyle = c; g.globalAlpha = 0.14;
        g.fillRect(cx - half, P.Y(gr.stats.q75), half * 2, P.Y(gr.stats.q25) - P.Y(gr.stats.q75));
        g.globalAlpha = 1;
      }
      (gr.medians || []).forEach((v, j) => {
        if (!ok(v)) return;
        const lab = (gr.recs || [])[j];
        const r = B.byLabel.get(lab);
        const x = cx + (hash((r && r.gid) || lab) - 0.5) * half * 1.5, y = P.Y(v);
        g.beginPath(); g.arc(x, y, 4.5, 0, 6.2832);
        g.fillStyle = c; g.globalAlpha = 0.9; g.fill(); g.globalAlpha = 1;
        g.strokeStyle = tok('--surface', '#fff'); g.lineWidth = 1.5; g.stroke();
        pts.push({ x, y, v, lab, gid: r && r.gid });
      });
      if (gr.stats && ok(gr.stats.median)) {
        const y = Math.round(P.Y(gr.stats.median)) + 0.5;
        g.strokeStyle = tok('--ink', '#17181b'); g.lineWidth = 2.5;
        g.beginPath(); g.moveTo(cx - half - 6, y); g.lineTo(cx + half + 6, y); g.stroke();
        g.lineWidth = 1;
      }
    });
    cv.__pts = pts;
  }

  /* (f) The tests in words, with p and q (q once the table's answer is in). */
  function wordChip(w) {
    const [t, c] = WORD[w] || [w || '—', 'erb-w-none'];
    return el('span', { class: 'chip erb-w ' + c, 'data-word': w || '', text: t });
  }
  function permWords(t) {
    if (!t || !t.perms) return '';
    return t.exact ? ' · p from all ' + t.perms + ' ways to split the recordings' : ' · p from ' + t.perms + ' random splits of the recordings';
  }
  function testsBody(got, blob) {
    const kids = [];
    const c = got.compare;
    const row = allRow(blob);
    const fam = ((B.all.get(allKey()) || {}).family) || {};
    const unit = got.unit || '';
    if (!c) {
      kids.push(el('p', { class: 'erb-cap', text: 'No tests: they need two groups with at least ' + minRecs() + ' recordings each.' }));
    } else {
      const fromAll = !!(row && row.compare && row.compare.tests);
      const T = fromAll ? row.compare.tests : (c.tests || {});
      const e = c.effect || {};
      const sp = (T.spread || (c.tests || {}).spread || {});
      const say = {
        location: c.b + ' − ' + c.a + ', median of the recording medians: ' + sgnf(e.diff, unit) + ' ' + unit
          + ' (95% interval ' + nf(e.lo, unit) + ' to ' + nf(e.hi, unit) + ', recordings resampled).',
        spread: 'How far apart the recording medians are, SD: ' + c.a + ' ' + nf(sp.sd_a, unit) + ', ' + c.b + ' ' + nf(sp.sd_b, unit)
          + '. “Are the ' + c.b + ' recordings more varied?”',
        shape: 'The whole distribution, every recording weighted the same: a split into weak and strong shows here even when '
          + 'the medians agree.',
      };
      for (const [k, name] of TESTS) {
        const t = T[k] || {};
        kids.push(el('div', { class: 'erb-test', 'data-test': k }, [
          el('div', { class: 'erb-test-h' }, [el('b', { text: name }), wordChip(t.word)]),
          el('span', { class: 'small', text: say[k] }),
          el('span', { class: 'muted small num', text: (t.name || '') + ' · ' + pq(t) + permWords(t) })]));
      }
      kids.push(el('p', { class: 'muted small erb-qsay', text: fromAll
        ? 'q: Benjamini–Hochberg, each kind of test across the averages table below (' + (fam.location || 0) + ' location, '
          + (fam.spread || 0) + ' spread and ' + (fam.shape || 0) + ' shape tests corrected together). A finding needs q '
          + 'under 0.05 (and, for where they sit, an interval clear of zero); p under 0.05 alone is a lead.'
        : 'q comes with the averages table below, which corrects across every number; until it comes nothing here can be '
          + 'a finding, and p under 0.05 alone is a lead.' }));
    }
    kids.push(el('b', { class: 'erb-bm-h', text: 'Two kinds of mouse, some weak and some strong?' }));
    for (const g of got.groups || []) kids.push(bimodalLine(g, row));
    return kids;
  }
  function bimodalLine(g, row) {
    const ag = row ? (row.groups || []).find((x) => x.label === g.label) : null;
    const bm = (ag && ag.bimodal) || g.bimodal;
    if (!bm) return el('div', { class: 'erb-test small' }, [el('span', { text: g.label + ': ' + FEW + ' to ask.' })]);
    const m = bm.medians || {}, e = bm.events || {};
    const med = m.p != null
      ? 'Among the recording medians, Hartigan’s dip p ' + pw(m.p) + (m.q != null ? ', q ' + pw(m.q) : '')
      : 'Among the ' + pl(m.n || 0, 'recording median') + ': too few for the dip’s p (it needs 10); bimodality coefficient '
        + nf(m.bc) + (m.hint ? ', over 0.56, which leans two-humped' : '');
    const ev = 'Pooled events: bimodality coefficient ' + nf(e.bc) + (e.hint
      ? ', leans two-humped (over 0.56; a lead only: events are not independent, and skew raises it too).' : ', one hump.');
    return el('div', { class: 'erb-test', 'data-group': g.label }, [
      el('div', { class: 'erb-test-h' }, [el('span', { class: 'erb-sw dot', style: '--sw: ' + gvar(g.label) }),
        el('b', { text: g.label }), bmChip(m)]),
      el('span', { class: 'muted small', text: med + '. ' + ev })]);
  }
  /* Two humps among the recording medians: a test word when there is a dip
     p (10 or more recordings); under that only the coefficient leans it,
     which is said as a lean, not as a lead. */
  function bmChip(m) {
    if (!m) return el('span', { class: 'muted', text: FEW });
    if (m.p == null) {
      return el('span', { class: 'chip erb-w erb-w-none', 'data-word': m.hint ? 'leans' : 'one',
        text: m.hint ? 'leans two-humped (coefficient only)' : 'one hump' });
    }
    return wordChip(m.word || (m.p < 0.05 ? 'hint' : 'no sign'));
  }
  /* The table's answer, into the tests panels already drawn: no canvas redrawn. */
  function putTests() {
    if (!live()) return;
    for (const box of B.root.querySelectorAll('.erb-tests')) {
      const blob = box.getAttribute('data-blob');
      const got = B.cmp.get(cmpKey(blob));
      if (got) box.replaceChildren(...testsBody(got, blob));
    }
  }

  /* ---------- the averages: every number, both blobs ---------- */
  BUILD.table = function () {
    if (!B.data || !recs().length) return null;
    if (B.by === 'pick' && !picksHere().length) return null;
    const key = allKey();
    const got = B.all.get(key), err = B.allErr.get(key);
    if (!got && !err) ensureAll();
    const kids = [el('div', { class: 'bar' }, [el('h2', { text: 'The averages, every number' }),
      el('span', { class: 'muted small', text: CLS_NAME[B.cls] + ' · ' + BY_WORDS[B.by] })]),
      el('p', { class: 'erb-cap', text: 'Every number of both blobs: each group’s median of its recordings’ medians [their middle '
        + 'half] and how many recordings; the difference with its 95% interval; and the three tests, with q held across the '
        + 'whole table. Click a row to show it above.' })];
    if (err) kids.push(errLine('Not worked out: ' + err, () => { B.allErr.delete(key); paint('table'); }));
    else if (!got) {
      kids.push(el('p', { class: 'muted erb-busy', text: 'Working out every number of both blobs, with the false discovery '
        + 'rate held across them: a little while the first time.' }));
    } else kids.push(...allTable(got));
    return el('div', { class: 'card', id: 'erbTable' }, kids);
  };

  function allTable(got) {
    const rows = got.rows || [];
    const withCmp = rows.find((r) => r.compare);
    let labels = withCmp ? [withCmp.compare.a, withCmp.compare.b] : [];
    if (!labels.length) for (const r of rows) for (const g of r.groups || []) if (!labels.includes(g.label)) labels.push(g.label);
    const a = labels[0], b = labels[1];
    const fam = got.family || {};
    let nFind = 0, nLead = 0;
    const words = (r) => {
      const ws = r.compare ? Object.values(r.compare.tests || {}).map((t) => t.word) : [];
      for (const g of r.groups || []) if (g.bimodal && g.bimodal.medians && g.bimodal.medians.word) ws.push(g.bimodal.medians.word);
      return ws;
    };
    for (const r of rows) for (const w of words(r)) { if (w === 'finding') nFind++; else if (w === 'hint') nLead++; }
    const out = [];
    out.push(el('p', { class: 'erb-sum', id: 'erbSum', text: pl(nFind, 'finding') + ' (q under 0.05) and ' + pl(nLead, 'lead')
      + ' (p under 0.05 alone: not findings).' }));
    out.push(el('p', { class: 'muted small', id: 'erbFamily', text: 'Corrected together (Benjamini–Hochberg, each kind of test '
      + 'across this table): ' + (fam.location || 0) + ' location, ' + (fam.spread || 0) + ' spread and ' + (fam.shape || 0)
      + ' shape tests' + (fam.bimodal != null ? ', and ' + fam.bimodal + ' two-kinds-of-mouse tests' : '') + '.' }));
    if (labels.length < 2) {
      out.push(el('p', { class: 'notice small', text: 'Only one group has recordings here, so the table has no comparisons.' }));
    } else if (!withCmp) {
      out.push(el('p', { class: 'notice small', text: 'No comparisons: they need two groups with at least ' + minRecs()
        + ' recordings each.' }));
    }
    const groupH = (lab) => el('th', {}, [el('span', { class: 'erb-sw dot', style: '--sw: ' + gvar(lab) }),
      tx(lab + ': median of medians [middle half] · recordings')]);
    const head = el('tr', {}, [el('th', { text: 'Number' })].concat(labels.map(groupH), b ? [
      el('th', { text: 'Difference, ' + b + ' − ' + a + ' [95% interval]' }),
      el('th', { text: 'Where they sit' }), el('th', { text: 'How varied' }), el('th', { text: 'The whole shape' })] : [],
      [el('th', { text: 'Two kinds of mouse?' })]));
    const body = [];
    let lastBlob = null;
    const span = 1 + labels.length + (b ? 4 : 0) + 1;
    for (const r of rows) {
      if (r.blob !== lastBlob) {
        lastBlob = r.blob;
        body.push(el('tr', { class: 'erb-blobrow' }, [el('td', { colspan: String(span),
          text: BLOB_NAME[r.blob] + (r.blob === 'top' ? ', the shallower sink' : ', the deeper sink') })]));
      }
      const ws = words(r);
      const cur = r.measure === B.measure && blobsShown().includes(r.blob);
      const cls = 'erb-row' + (ws.includes('finding') ? ' erb-find' : ws.includes('hint') ? ' erb-lead' : '') + (cur ? ' erb-cur' : '');
      const pick = () => {
        B.measure = r.measure;
        if (B.blob !== 'both') B.blob = r.blob;
        paint('ctl', 'recs', 'group', 'table');
        const card = B.root.querySelector('.erb-group[data-blob="' + r.blob + '"]');
        if (card) card.scrollIntoView({ block: 'start', behavior: 'smooth' });
      };
      const cells = [el('td', { 'data-l': 'Number' }, [el('b', { text: r.words }), el('span', { class: 'muted', text: ' (' + r.unit + ')' }),
        el('span', { class: 'muted small erb-tb', text: ' · ' + BLOB_NAME[r.blob].toLowerCase() })])];
      for (const lab of labels) {
        const g = (r.groups || []).find((x) => x.label === lab);
        const st = g && g.stats;
        cells.push(el('td', { class: 'num', 'data-l': lab }, !g ? [tx('—')] : st ? [
          tx(nf(st.median, r.unit) + ' [' + nf(st.q25, r.unit) + ' – ' + nf(st.q75, r.unit) + ']'),
          el('span', { class: 'muted', text: ' · ' + g.n_rec })] : [
          el('span', { class: 'muted', text: FEW + ' (' + g.n_rec + ')' })]));
      }
      if (b) {
        const c = r.compare;
        const e = (c && c.effect) || {};
        cells.push(el('td', { class: 'num', 'data-l': 'Difference' }, [tx(c ? sgnf(e.diff, r.unit) + ' [' + nf(e.lo, r.unit) + ' to '
          + nf(e.hi, r.unit) + ']' : '—')]));
        for (const [k, name] of TESTS) {
          const t = c && (c.tests || {})[k];
          cells.push(el('td', { 'data-l': name, 'data-test': k }, t ? [wordChip(t.word),
            el('span', { class: 'muted small num erb-pq', text: pq(t) })] : [tx('—')]));
        }
      }
      cells.push(el('td', { 'data-l': 'Two kinds of mouse?' }, (r.groups || []).map((g) => {
        const m = (g.bimodal || {}).medians;
        return el('span', { class: 'erb-bm' }, [tx(g.label + ' '), bmChip(m),
          m && m.p != null ? el('span', { class: 'muted small num', text: pq(m) }) : null]);
      })));
      body.push(el('tr', { class: cls, tabindex: '0', 'data-measure': r.measure, 'data-blob': r.blob,
        onclick: pick, onkeydown: (ev) => { if (ev.key === 'Enter') pick(); } }, cells));
    }
    out.push(el('div', { class: 'tablewrap' }, [el('table', { class: 'erb-tab', id: 'erbAll' },
      [el('thead', {}, [head]), el('tbody', {}, body)])]));
    out.push(el('p', { class: 'muted small', text: 'Where they sit: Mann–Whitney U on the recording medians. How varied: '
      + 'Brown–Forsythe on the recording medians, recording labels shuffled. The whole shape: Anderson–Darling between the '
      + 'equal-weight distributions, labels shuffled. Two kinds of mouse: Hartigan’s dip on the recording medians (a p from 10 '
      + 'recordings; under that, the bimodality coefficient leans it, a lead only). A finding is q under 0.05, and for where '
      + 'they sit an interval clear of zero too.' }));
    return out;
  }

  /* ---------- the style, once ---------- */
  const CSS_TEXT = `
:root { --erb-a: #008a9e; --erb-b: #9a6a00; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --erb-a: #22a3b5; --erb-b: #b88619; } }
:root[data-theme="dark"] { --erb-a: #22a3b5; --erb-b: #b88619; }
.erb { min-width: 0; }
.erb .chip { white-space: normal; }
.erb h2 { margin-bottom: 4px; }
.erb-imp { margin: 8px 0 4px; }
.erb-imp select { min-width: 0; flex: 1 1 260px; }
.erb-impl { margin: 4px 0 8px; overflow-wrap: anywhere; }
.erb-filter { margin: 8px 0; padding: 8px 10px; border-radius: 6px; background: var(--surface-2); border: 1px solid var(--line);
  border-left: 3px solid var(--ink-3); font-size: 13px; color: var(--ink-2); }
.erb-wait { color: var(--ink-2); }
.erb-in, .erb-left { margin: 4px 0; overflow-wrap: anywhere; }
.erb-ctl { display: flex; flex-direction: column; gap: 10px; }
.erb-ctl select { max-width: 100%; }
.erb-pickbar { gap: 8px 12px; }
.erb-cap { font-size: 12.5px; color: var(--ink-2); margin: 0; max-width: 110ch; overflow-wrap: anywhere; }
.erb-note { font-size: 12px; color: var(--ink-3); margin: 0; overflow-wrap: anywhere; }
.erb-legend { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 12.5px; color: var(--ink-2); margin: 8px 0 10px; }
.erb-sw { display: inline-block; width: 18px; height: 0; border-top: 2.5px solid var(--sw); vertical-align: middle; margin-right: 5px; }
.erb-sw.dash { border-top-style: dashed; }
.erb-sw.dot { width: 10px; height: 10px; border: 0; border-radius: 50%; background: var(--sw); margin-right: 4px; }
.erb-recs { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(310px, 100%), 1fr)); gap: 12px; }
.erb-rec { display: flex; flex-direction: column; gap: 6px; min-width: 0; padding: 10px 12px; border: 1px solid var(--line);
  border-radius: var(--r); background: var(--surface); }
.erb-rec.erb-off { background: var(--surface-2); }
.erb-off-why { color: var(--ink-3); margin: 0; }
.erb-rec.erb-picked { border-color: color-mix(in srgb, var(--erb-a) 50%, var(--line)); box-shadow: inset 4px 0 0 var(--erb-a); }
.erb-rec.erb-flash { outline: 2px solid var(--focus); outline-offset: 2px; }
.erb-rh { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.erb-rh b { overflow-wrap: anywhere; margin-right: 2px; }
.chip.erb-g::before { content: ''; flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--erb-gc, var(--ink-3)); }
.chip.erb-pk { color: var(--erb-a); border-color: var(--erb-a); }
.erb-pick { display: inline-flex; align-items: center; gap: 4px; font-size: 12.5px; margin-left: auto; cursor: pointer;
  padding: 2px 8px; border: 1px solid var(--line-2); border-radius: 999px; }
.erb-pick input { margin: 0; }
canvas.erb-rc { height: 140px; border-radius: 6px; background: var(--surface-2); }
canvas.erb-cv { height: 220px; border-radius: 6px; background: var(--surface-2); }
canvas.erb-strip { cursor: pointer; }
table.erb-mt { font-size: 12px; }
table.erb-mt th, table.erb-mt td { padding: 3px 6px; }
table.erb-mt td.v { font-variant-numeric: tabular-nums; }
table.erb-mt tr.erb-cur td { background: color-mix(in srgb, var(--accent, #2f6fdf) 12%, transparent); font-weight: 600; }
.erb-mline { margin: 2px 0 0; font-size: 12.5px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.erb-open { display: block; color: var(--warn); font-size: 11.5px; font-weight: 400; }
.erb-open.muted { color: var(--ink-3); }
.erb-panels { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(340px, 100%), 1fr)); gap: 12px; margin-top: 4px; }
.erb-panel { display: flex; flex-direction: column; gap: 6px; min-width: 0; padding: 10px 12px; border: 1px solid var(--line);
  border-radius: var(--r); }
.erb-panel h3 { font-size: 13.5px; margin: 0; }
.erb-tests { display: flex; flex-direction: column; gap: 8px; }
.erb-test { display: flex; flex-direction: column; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
.erb-test-h { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
.erb-bm-h { font-size: 13px; margin-top: 4px; }
.erb-bm { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 6px; margin: 0 0 3px; }
.erb-pq { display: block; margin-top: 2px; }
.erb-warn { color: var(--warn); }
.erb-more > summary { cursor: pointer; font-size: 12px; color: var(--ink-2); }
.erb-more[open] > summary { margin-bottom: 4px; }
.chip.erb-w { font-weight: 600; }
.chip.erb-w-find { color: var(--ok); border-color: var(--ok); }
.chip.erb-w-lead { color: var(--warn); border-color: var(--warn); border-style: dashed; }
.chip.erb-w-none { font-weight: 500; }
.erb-sum { font-weight: 600; margin: 8px 0 2px; }
table.erb-tab tr.erb-row { cursor: pointer; }
table.erb-tab tr.erb-row:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
table.erb-tab tr.erb-find td { background: color-mix(in srgb, var(--ok) 9%, transparent); }
table.erb-tab tr.erb-find td:first-child { box-shadow: inset 3px 0 0 var(--ok); }
table.erb-tab tr.erb-lead td:first-child { box-shadow: inset 3px 0 0 var(--warn); }
table.erb-tab tr.erb-cur td { background-image: linear-gradient(color-mix(in srgb, var(--focus) 10%, transparent),
  color-mix(in srgb, var(--focus) 10%, transparent)); }
table.erb-tab tr.erb-blobrow td { background: var(--surface-2); font-weight: 600; color: var(--ink-2); }
@media (max-width: 760px) {
  table.erb-tab thead { display: none; }
  table.erb-tab, table.erb-tab tbody, table.erb-tab tr, table.erb-tab td { display: block; width: 100%; }
  table.erb-tab tr { border-bottom: 1px solid var(--line-2); padding: 6px 0; }
  table.erb-tab td { border: 0; padding: 2px 8px; }
  table.erb-tab td[data-l]::before { content: attr(data-l) ': '; color: var(--ink-3); font-weight: 600; }
  table.erb-tab td[data-l="Number"]::before { content: none; }
}
@media (max-width: 520px) { .erb-pick { margin-left: 0; } }
`;
  function injectCss() {
    if (document.getElementById('erbStyle')) return;
    const st = document.createElement('style');
    st.id = 'erbStyle';
    st.textContent = CSS_TEXT;
    document.head.appendChild(st);
  }

  /* ---------- the tab ---------- */
  function render() {
    if (!K()) return document.createTextNode('');
    injectCss();
    if (!B.root) B.root = el('div', { class: 'erb', id: 'erBlobs' });
    // An Impression just taken on the Recordings tab is the one shown, and
    // the list is asked again if it is not in it yet.
    const imp = S().impression;
    if (imp && imp.artifact_id && keyOf(imp) !== B.impSeen) {
      B.impSeen = keyOf(imp);
      B.choice = null;
      if (B.list && !B.list.some((i) => i.artifact_id === imp.artifact_id
          && (i.version === imp.version || (i.versions || []).some((v) => v.v === imp.version)))) {
        B.list = null;
        B.listErr = null;
      }
    }
    fill();
    return B.root;
  }

  ROOM.ext.blobs = {
    render,
    state: () => B,
    _drawAll: drawMine,
  };
})();
