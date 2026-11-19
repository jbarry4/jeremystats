/* ==========================================================================
   strataconsult.js -- StrataScope Beta: Consult (2026-11-19).

   StrataScope's step row gets a two-way switch, [Steps | Beta]. Beta is the
   same StrataScope -- every step, the rail, the strip, Accept -- with one
   thing added: a Consult card at the top of the drawer.

   Consult "primes" a consult. It sends what this window is looking at to
   the server (backend/strataconsult.py): the sheet, the open step, where the
   proposed lines are now (after any dragging), every step's proposal and
   anchors, the depth curves, the checks, ICA if it has run, and pictures of
   the traces, the depth strip and the evidence window. Then you go to
   Claude Code and say "consult". Claude reads it (tools/strata_consult.py
   show), looks, and pushes a reply (tools/strata_consult.py push). The
   reply arrives here over /api/link -- no refresh -- as a list:

     note        something to know or look at
     move        a proposed line to a new channel (a proposal until Accept)
     label       channels relabelled on the sheet (as painting the rail does)
     confidence  a line's sure / likely / guess
     show        which depth curves are on the strip
     step        open a step
     param       a step parameter changed, and the proposals worked out again

   Each item has its reason. Apply one, or "Apply one by one" walks the list
   with a pause between, so every change can be watched landing. Anything
   applied can be undone from the same row. What was applied, skipped or
   undone is kept with the consult, and the next consult carries it.
   ========================================================================== */
'use strict';

BARRY.strataConsult = (function () {
  const KEY = 'barry.strataBeta';
  const S = () => BARRY.strataSteps && BARRY.strataSteps._consult;

  let gid = null;
  let cur = null;            // {id, at, note, step, images, reply, decisions}
  let note = '';             // the question typed for the next consult
  let busy = '';             // 'priming' while a consult is being sent
  let undo = {};             // "rev:i" -> how to put it back
  let walking = false;       // Apply one by one is running
  let walkNow = null;        // the index it is on
  let stopWalk = false;
  let seenRev = 0;
  let pollTimer = null;
  let fresh = false;         // a reply just arrived: the card says so

  /* ---------- Beta on or off ---------- */
  function beta() {
    try { return localStorage.getItem(KEY) === 'on'; } catch (e) { return false; }
  }
  function setBeta(on) {
    try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch (e) { /* this view only */ }
    toast(on ? 'Showing StrataScope BETA: the same steps, plus a Consult card '
             + 'at the top of the drawer.'
             : 'Showing StrataScope STEPS: the Consult card is put away. Your '
             + 'consults are kept.', 'ok', 5000);
    const s = S();
    if (s && s.host()) s.host().render();
    if (on && gid) refresh(true);
  }

  function rowBits() {
    const out = [BARRY.ui.seg([
      ['steps', 'Steps', 'StrataScope as it is.'],
      ['beta', 'Beta', 'The same steps, plus Consult: send what you are '
                     + 'looking at to Claude Code and get suggestions back '
                     + 'here, to apply one at a time.'],
    ], beta() ? 'beta' : 'steps', (v) => setBeta(v === 'beta'),
    { extra: 'ss-beta-seg' })];
    if (beta()) {
      out.push(el('button', {
        class: 'btn sm ss-consult-btn' + (busy ? ' busy' : ''),
        text: busy ? 'Priming…' : 'Consult',
        disabled: busy ? 'disabled' : null,
        title: 'Send what this window shows -- the sheet, the open step, the '
             + 'lines where they are now, the curves, and pictures -- for '
             + 'Claude Code to look at. Then say "consult" in Claude Code.',
        onclick: prime,
      }));
    }
    return out;
  }

  const wantsDrawer = () => beta() && !!gid;

  /* ---------- in and out ---------- */
  function enter(g) {
    gid = g;
    cur = null; undo = {}; seenRev = 0; walking = false; fresh = false;
    if (beta()) refresh(true);
  }
  function leave() {
    gid = null; cur = null; stopWalk = true;
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  }

  const url = (what) => '/api/strata/' + encodeURIComponent(gid) + '/consult'
    + (what ? '/' + what : '');

  /* `quiet` on the way in: a reply that was already there is not news. */
  async function refresh(quiet) {
    if (!gid) return;
    const mine = gid;
    let got;
    try { got = (await api(url())).consult; } catch (e) { return; }
    if (mine !== gid) return;
    const rev = got && got.reply ? got.reply.rev || 0 : 0;
    const news = !quiet && rev > seenRev;
    // A newer reply replaces the list: what was kept to undo was for the old one.
    if (rev !== seenRev || !cur || !got || cur.id !== got.id) undo = {};
    cur = got;
    seenRev = rev;
    if (news) {
      const n = (got.reply.items || []).length;
      toast('Claude replied to the consult: ' + n + ' suggestion'
            + (n === 1 ? '' : 's') + '. They are in the Consult card.',
            'ok', 7000);
      fresh = true;
      setTimeout(() => { fresh = false; rerender(); }, 2600);
      // Doppler's one soft bell (jarvisfx.js), so the one mute silences it too.
      try {
        const fx = BARRY.jarvisfx || window.JarvisFX;
        if (fx && !fx.muted && fx.land) fx.land();
      } catch (e) { /* a decoration never stops a reply */ }
    }
    rerender();
    schedulePoll();
  }

  /* The reply comes over /api/link; this is the fallback for a window that
     missed the nudge (another tab held the poll, the server restarted). */
  function schedulePoll() {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    if (!gid || !beta() || !cur || cur.reply) return;
    pollTimer = setTimeout(() => { pollTimer = null; refresh(false); }, 8000);
  }

  let linkSeen = 0;
  function fromLink(channels, g) {
    const slot = channels && channels['strata-consult:' + g];
    const v = slot && slot.value;
    if (!v || !v.at || v.at <= linkSeen) return;
    linkSeen = v.at;
    if (g !== gid) return;
    refresh(false);
  }

  function rerender() {
    const s = S();
    if (s && s.host()) s.host().render();
  }

  /* ==================================================================
     Priming a consult
     ================================================================== */
  async function prime() {
    const s = S();
    if (!s || !s.host() || busy) return;
    busy = 'priming';
    rerender();
    try {
      const req = gather();
      const images = await photographs();
      const res = await apiPost(url(), { request: req, images });
      cur = res.consult || { id: res.id };
      seenRev = 0; fresh = false; undo = {};
      note = '';
      let copied = false;
      try { await navigator.clipboard.writeText('consult'); copied = true; } catch (e) { /* not allowed here */ }
      toast('Consult ready. In Claude Code, say "consult"'
            + (copied ? ' (it is on the clipboard).' : '.')
            + ' The reply will appear in the Consult card.', 'ok', 9000);
      schedulePoll();
    } catch (e) {
      toast('Could not prime the consult: ' + e.message, 'err', 9000);
    } finally {
      busy = '';
      rerender();
    }
  }

  /* What a consult needs to know, in the page's own words. */
  function gather() {
    const s = S();
    const H = s.host();
    const sheet = H.sheet() || {};
    const sug = s.sug() || {};
    const gh = s.ghost();
    const st = s.strata();
    const walk = ((st.states || {}).theta_walk) || [];
    const sec = walk.reduce((a, b) => a + Math.max(0, (b[1] || 0) - (b[0] || 0)), 0);
    const aid = H.aidWindow && H.aidWindow();
    let evidenceText = null;
    try {
      const b = aid && aid.document.getElementById('saBody');
      if (b && aid.document.body.classList.contains('steps')) {
        evidenceText = b.innerText.slice(0, 20000);
      }
    } catch (e) { /* closed or elsewhere */ }
    const prof = sug.profile || null;
    return {
      version: 1,
      gid,
      label: sheet.session_label || null,
      path: H.path(),
      who: (BARRY.profile && BARRY.profile.who && BARRY.profile.who()) || null,
      note: note.trim() || null,
      open_step: s.open(),
      step_states: s.stepStates(),
      steps_saved: st.steps || {},
      channels: sug.channels || H.allChannels().map((c) => c.number),
      bad: sug.bad || [],
      regions: (H.regions() || []).map((r) => ({
        id: r.id, name: r.name, retired: !!r.retired, note: r.note || null })),
      labels: sheet.labels || {},
      lines: gh ? { step: gh.step, lines: gh.lines } : null,
      proposals: sug.steps || null,
      profile: prof,
      curves: s.curves(),
      shown: s.shown(),
      ref_channel: sug.ref_channel,
      params: sug.params || null,
      masks: sug.masks || null,
      ripples_n: Array.isArray(sug.ripples) ? sug.ripples.length
        : (sug.ripples && sug.ripples.n) || null,
      ripple_tr: sug.ripple_tr || null,
      theta_tr: sug.theta_tr || null,
      ica_ready: !!sug.ica_ready,
      ica: s.ica(),
      checks: s.checks(),
      overrides: s.overrides(),
      confidence: st.confidence || {},
      anchors: st.anchors || {},
      theta_walk: { bouts: walk.length, seconds: Math.round(sec) },
      evidence_text: evidenceText,
      scanned: !!(s.status() && s.status().scanned),
    };
  }

  /* Pictures, from the canvases themselves: the traces window, the depth
     strip on its own (it is narrow, and in the composite it is small), and
     the evidence window -- the whole scroll of it, not just what is in view. */
  async function photographs() {
    const s = S();
    const H = s.host();
    const out = {};
    const body = document.getElementById('xfBody');
    try { if (body) out.screen = shoot(document, body, false, ['.ss-drawer']); } catch (e) { /* skip */ }
    try {
      const sc = s.stripCanvas();
      if (sc) out.strip = sc.toDataURL('image/png');
    } catch (e) { /* skip */ }
    try {
      const aid = H.aidWindow && H.aidWindow();
      if (aid) {
        const d = aid.document;
        const steps = d.body.classList.contains('steps');
        const root = steps ? d.getElementById('saBody') : d.body;
        if (root) out.evidence = shoot(d, root, steps, []);
      }
    } catch (e) { /* closed, or not ours */ }
    return out;
  }

  function shoot(doc, root, full, skip) {
    const win = doc.defaultView;
    const r = root.getBoundingClientRect();
    const sTop = full ? root.scrollTop : 0;
    const W = Math.max(1, Math.round(r.width));
    const Ht = Math.max(1, Math.round(full ? Math.min(root.scrollHeight, 7000)
                                           : r.height));
    const k = Math.min(2, Math.max(1, win.devicePixelRatio || 1));
    const cv = document.createElement('canvas');
    cv.width = Math.round(W * k); cv.height = Math.round(Ht * k);
    const ctx = cv.getContext('2d');
    ctx.fillStyle = win.getComputedStyle(doc.body).backgroundColor || '#111';
    ctx.fillRect(0, 0, cv.width, cv.height);
    const skipped = (node) => skip.some((q) => node.closest && node.closest(q));
    // What was drawn, so the picture can be cut down to it.
    const box = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
    const grow = (x, y, w, h) => {
      box.x0 = Math.min(box.x0, x); box.y0 = Math.min(box.y0, y);
      box.x1 = Math.max(box.x1, x + w); box.y1 = Math.max(box.y1, y + h);
    };
    const add = (scope, ox, oy) => {
      for (const c of scope.querySelectorAll('canvas')) {
        if (skipped(c) || !c.width || !c.height) continue;
        const cs = c.ownerDocument.defaultView.getComputedStyle(c);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const b = c.getBoundingClientRect();
        if (!b.width || !b.height) continue;
        const x = b.left + ox - r.left;
        const y = b.top + oy - r.top + sTop;
        if (x > W || y > Ht || x + b.width < 0 || y + b.height < 0) continue;
        try {
          ctx.drawImage(c, x * k, y * k, b.width * k, b.height * k);
          grow(x, y, b.width, b.height);
        } catch (e) { /* tainted */ }
      }
      for (const f of scope.querySelectorAll('iframe')) {
        if (skipped(f)) continue;
        const fs = f.ownerDocument.defaultView.getComputedStyle(f);
        if (fs.display === 'none' || fs.visibility === 'hidden') continue;
        let fd = null;
        try { fd = f.contentDocument; } catch (e) { /* another origin */ }
        const fb = f.getBoundingClientRect();
        if (fd && fd.body && fb.width) add(fd.body, ox + fb.left, oy + fb.top);
      }
    };
    add(root, 0, 0);
    /* The rail is not a canvas: drawn here from its rows, the layer's colour
       and the channel's number and name, so the picture says which lane is
       which. */
    const rows = root.querySelectorAll('.strata-row');
    for (const row of rows) {
      const b = row.getBoundingClientRect();
      if (!b.height) continue;
      const x = b.left - r.left, y = b.top - r.top + sTop;
      grow(x, y, b.width, b.height);
      const cat = row.style.getPropertyValue('--cat').trim();
      if (cat) {
        ctx.globalAlpha = 0.35;
        ctx.fillStyle = cat;
        ctx.fillRect(x * k, y * k, b.width * k, b.height * k);
        ctx.globalAlpha = 1;
        ctx.fillRect(x * k, y * k, 5 * k, b.height * k);
      }
      if (b.height >= 7) {
        const num = (row.querySelector('.strata-num') || {}).textContent || '';
        const nm = (row.querySelector('.strata-name') || {}).textContent || '';
        ctx.fillStyle = win.getComputedStyle(row).color || '#ccc';
        ctx.font = Math.round(Math.min(11, b.height - 1) * k) + 'px sans-serif';
        ctx.textBaseline = 'middle';
        ctx.fillText(num + '  ' + nm, (x + 8) * k, (y + b.height / 2) * k);
      }
    }
    if (!(box.x1 > box.x0 && box.y1 > box.y0)) return cv.toDataURL('image/png');
    const x0 = Math.max(0, Math.floor(box.x0) - 4), y0 = Math.max(0, Math.floor(box.y0) - 4);
    const x1 = Math.min(W, Math.ceil(box.x1) + 4), y1 = Math.min(Ht, Math.ceil(box.y1) + 4);
    const cut = document.createElement('canvas');
    cut.width = Math.round((x1 - x0) * k); cut.height = Math.round((y1 - y0) * k);
    cut.getContext('2d').drawImage(cv, x0 * k, y0 * k, cut.width, cut.height,
                                   0, 0, cut.width, cut.height);
    return cut.toDataURL('image/png');
  }

  /* ==================================================================
     Applying a reply
     ================================================================== */
  const itemKey = (i) => (cur && cur.reply ? cur.reply.rev : 0) + ':' + i;
  const stateOf = (i) => {
    const d = (cur && cur.decisions) || {};
    return (d[itemKey(i)] || {}).state || 'pending';
  };

  async function decide(i, state, detail) {
    if (!cur) return;
    cur.decisions = cur.decisions || {};
    cur.decisions[itemKey(i)] = { state, detail: detail || null };
    try {
      const res = await apiPost(url('decide'), {
        id: cur.id, rev: cur.reply.rev, index: i, state, detail: detail || null });
      if (res.decisions) cur.decisions = res.decisions;
    } catch (e) { /* kept here; the server copy is a record, not the state */ }
  }

  function findLine(it) {
    const s = S();
    const gh = s.ghost();
    if (!gh) return null;
    return gh.lines.find((l) => (it.line && l.id === it.line)
      || (!it.line && (it.above === undefined || l.above === it.above)
          && (it.below === undefined || l.below === it.below))) || null;
  }

  function rowOfCh(ch) {
    const sug = S().sug();
    if (!sug || !sug.channels) return -1;
    if (ch === 'bottom' || ch === null) return sug.channels.length;
    return sug.channels.indexOf(Number(ch));
  }

  async function ensureStep(it) {
    if (it.step == null) return;
    await S().openStep(String(it.step));
  }

  async function apply(i) {
    const s = S();
    const it = cur.reply.items[i];
    const H = s.host();
    if (!H) return false;
    try {
      if (it.kind === 'note') {
        await decide(i, 'read');
      } else if (it.kind === 'step') {
        await ensureStep(it);
        await decide(i, 'applied');
      } else if (it.kind === 'move') {
        await ensureStep(it);
        const ln = findLine(it);
        if (!ln) throw new Error('that line is not among the open step’s lines');
        const to = it.to_row != null ? Number(it.to_row) : rowOfCh(it.to_ch);
        if (to < 0) throw new Error('ch ' + it.to_ch + ' is not on this probe');
        const from = ln.at;   // setLine moves `ln` itself, so read it first
        undo[itemKey(i)] = { kind: 'move', ln, at: from };
        s.setLine(ln, to);
        if (it.confidence) s.setConfidence(ln, it.confidence);
        await decide(i, 'applied', { from, to });
      } else if (it.kind === 'confidence') {
        await ensureStep(it);
        const ln = findLine(it);
        if (!ln) throw new Error('that line is not among the open step’s lines');
        undo[itemKey(i)] = { kind: 'confidence', ln, was: ln.confidence };
        s.setConfidence(ln, it.value);
        await decide(i, 'applied');
      } else if (it.kind === 'label') {
        const labels = (H.sheet() || {}).labels || {};
        const map = {}, was = {};
        for (const c of it.channels) {
          map[c] = it.region || null;
          was[c] = labels[String(c)] || null;
        }
        undo[itemKey(i)] = { kind: 'label', was };
        await H.setLabels(map);
        await decide(i, 'applied', { was });
      } else if (it.kind === 'show') {
        await ensureStep(it);
        undo[itemKey(i)] = { kind: 'show', was: s.shown() };
        s.setShown(it.curves || []);
        await decide(i, 'applied');
      } else if (it.kind === 'param') {
        const p = (s.sug() || {}).params || {};
        undo[itemKey(i)] = { kind: 'param', key: it.key, was: p[it.key] == null ? null : p[it.key] };
        await s.saveParams({ [it.key]: it.value });
        await decide(i, 'applied', { was: p[it.key] == null ? null : p[it.key] });
      }
      return true;
    } catch (e) {
      toast('Could not apply item ' + (i + 1) + ': ' + e.message, 'err', 8000);
      return false;
    } finally {
      rerender();
    }
  }

  async function revert(i) {
    const s = S();
    const u = undo[itemKey(i)];
    const it = cur.reply.items[i];
    try {
      if (u && u.kind === 'move') s.setLine(u.ln, u.at);
      else if (u && u.kind === 'confidence') s.setConfidence(u.ln, u.was);
      else if (u && u.kind === 'show') s.setShown(u.was);
      else if (u && u.kind === 'param') await s.saveParams({ [u.key]: u.was });
      else if (u && u.kind === 'label') await s.host().setLabels(u.was);
      else if (it.kind === 'label') {
        // After a reload: the decision kept what the channels said before.
        const d = ((cur.decisions || {})[itemKey(i)] || {}).detail || {};
        if (d.was) await s.host().setLabels(d.was);
        else throw new Error('nothing kept to put back');
      } else throw new Error('nothing kept to put back after a reload');
      delete undo[itemKey(i)];
      await decide(i, 'undone');
    } catch (e) {
      toast('Could not undo item ' + (i + 1) + ': ' + e.message, 'err', 8000);
    }
    rerender();
  }

  async function walk() {
    if (walking || !cur || !cur.reply) return;
    walking = true; stopWalk = false;
    const items = cur.reply.items || [];
    const pause = (ms) => new Promise((r) => setTimeout(r, ms));
    for (let i = 0; i < items.length; i++) {
      if (stopWalk || !gid) break;
      if (stateOf(i) !== 'pending') continue;
      walkNow = i; rerender();
      scrollToItem(i);
      await pause(700);
      if (stopWalk || !gid) break;
      await apply(i);
      await pause(items[i].kind === 'note' ? 600 : 1100);
    }
    walking = false; walkNow = null;
    rerender();
  }

  function scrollToItem(i) {
    const node = document.querySelector('.ssc-item[data-i="' + i + '"]');
    if (node && node.scrollIntoView) node.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  /* ==================================================================
     The card
     ================================================================== */
  function when(iso) {
    const t = Date.parse(iso || '');
    return isFinite(t) ? new Date(t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '';
  }

  const KIND_NAME = { note: 'Note', move: 'Move line', label: 'Relabel',
                      confidence: 'Confidence', show: 'Curves', step: 'Open step',
                      param: 'Parameter' };

  function chRun(chs) {
    const a = chs.slice().map(Number);
    if (!a.length) return '';
    const sug = S().sug();
    const order = sug && sug.channels ? sug.channels : null;
    if (order) a.sort((x, y) => order.indexOf(x) - order.indexOf(y));
    const runs = [];
    for (const c of a) {
      const last = runs[runs.length - 1];
      if (last && order && order.indexOf(c) === order.indexOf(last[1]) + 1) last[1] = c;
      else runs.push([c, c]);
    }
    return 'ch ' + runs.map((r) => (r[0] === r[1] ? r[0] : r[0] + '–' + r[1])).join(', ');
  }

  function what(it) {
    const s = S();
    const nm = (id) => (id ? s.regionName(id) : 'unlabelled');
    if (it.kind === 'move') {
      const ln = findLine(it);
      const name = ln ? s.regionName(ln.above) + ' | ' + s.regionName(ln.below)
        : [it.above, it.below].map(nm).join(' | ');
      const now = ln && ln.at != null ? ' (now above ' + s.chName(ln.at) + ')' : '';
      const to = it.to_row != null ? s.chName(Number(it.to_row)) : 'ch ' + it.to_ch;
      return name + ' → above ' + to + now;
    }
    if (it.kind === 'label') return chRun(it.channels) + ' → ' + nm(it.region);
    if (it.kind === 'confidence') {
      const ln = findLine(it);
      return (ln ? s.regionName(ln.above) + ' | ' + s.regionName(ln.below) : 'line')
        + ': ' + (ln ? ln.confidence || '—' : '?') + ' → ' + it.value;
    }
    if (it.kind === 'show') {
      const names = Object.fromEntries(s.curves().map((c) => [c.id, c.name]));
      return 'Strip shows: ' + (it.curves || []).map((c) => names[c] || c).join(', ');
    }
    if (it.kind === 'step') return 'Open Step ' + it.step;
    if (it.kind === 'param') {
      const p = (s.sug() || {}).params || {};
      return it.key.replace(/_/g, ' ') + ': ' + (p[it.key] == null ? 'default' : p[it.key])
        + ' → ' + (it.value == null ? 'default' : it.value);
    }
    return '';
  }

  function itemRow(it, i) {
    const st = stateOf(i);
    const btns = [];
    if (st === 'pending' || st === 'undone' || st === 'skipped') {
      btns.push(el('button', {
        class: 'btn sm', text: it.kind === 'note' ? 'Got it' : 'Apply',
        disabled: walking ? 'disabled' : null,
        onclick: () => apply(i),
      }));
      if (st !== 'skipped') {
        btns.push(el('button', {
          class: 'btn ghost sm', text: 'Skip', disabled: walking ? 'disabled' : null,
          onclick: async () => { await decide(i, 'skipped'); rerender(); },
        }));
      }
    } else if (st === 'applied' && it.kind !== 'note' && it.kind !== 'step') {
      btns.push(el('button', {
        class: 'btn ghost sm', text: 'Undo', disabled: walking ? 'disabled' : null,
        onclick: () => revert(i),
      }));
    }
    const tag = { pending: '', applied: '✓ applied', read: '✓ read',
                  skipped: 'skipped', undone: 'undone' }[st] || st;
    return el('div', {
      class: 'ssc-item ' + it.kind + ' ' + st + (walkNow === i ? ' now' : ''),
      'data-i': String(i),
    }, [
      el('div', { class: 'ssc-item-head' }, [
        el('span', { class: 'ssc-n', text: String(i + 1) }),
        el('span', { class: 'ssc-kind', text: KIND_NAME[it.kind] || it.kind }),
        it.step != null && it.kind !== 'step'
          ? el('span', { class: 'ssc-step', text: 'Step ' + it.step }) : null,
        tag ? el('span', { class: 'ssc-tag', text: tag }) : null,
      ].filter(Boolean)),
      it.title ? el('div', { class: 'ssc-title', text: it.title }) : null,
      what(it) ? el('div', { class: 'ssc-what', text: what(it) }) : null,
      it.why ? el('div', { class: 'ssc-why', text: it.why }) : null,
      it.look ? el('div', { class: 'ssc-look' }, [el('b', { text: 'Look: ' }), it.look]) : null,
      (it.refs && it.refs.length) ? el('div', { class: 'ssc-refs',
        text: it.refs.join(' · ') }) : null,
      btns.length ? el('div', { class: 'ssc-btns' }, btns) : null,
    ].filter(Boolean));
  }

  function card() {
    const box = el('section', { class: 'ssc' + (fresh ? ' fresh' : '') });
    box.appendChild(el('div', { class: 'ssc-head' }, [
      el('strong', { text: 'Consult' }),
      el('span', { class: 'sa-beta ssc-beta', text: 'Beta' }),
      el('span', { style: 'flex:1' }),
      el('button', {
        class: 'btn sm', text: busy ? 'Priming…' : 'Consult',
        disabled: busy ? 'disabled' : null, onclick: prime,
        title: 'Send what this window shows to Claude Code.',
      }),
    ]));
    box.appendChild(el('textarea', {
      class: 'ssc-note', rows: '2', value: note,
      placeholder: 'What should Claude look at? (optional, goes with the next Consult)',
      oninput: (e) => { note = e.target.value; },
    }));

    if (!cur) {
      box.appendChild(el('p', { class: 'ss-say', text: 'Label as usual. When you '
        + 'want a second opinion, press Consult, then say "consult" in Claude '
        + 'Code. Suggestions come back here, one per row, to apply or skip.' }));
      return box;
    }
    const reply = cur.reply;
    if (!reply) {
      box.appendChild(el('div', { class: 'ssc-wait' }, [
        el('span', { class: 'ssc-radar' }),
        el('span', { text: 'Primed at ' + when(cur.at) + (cur.step ? ', Step ' + cur.step
          + ' open' : '') + '. In Claude Code, say "consult". Waiting for the reply.' }),
      ]));
      return box;
    }
    const items = reply.items || [];
    const left = items.filter((_, i) => stateOf(i) === 'pending').length;
    box.appendChild(el('div', { class: 'ssc-meta', text: 'Reply ' + (reply.rev > 1
      ? reply.rev + ' ' : '') + 'at ' + when(reply.at) + ' to the consult from '
      + when(cur.at) + ' · ' + items.length + ' item' + (items.length === 1 ? '' : 's')
      + (left ? ', ' + left + ' to go' : ', all handled') }));
    if (reply.summary) box.appendChild(el('p', { class: 'ssc-summary', text: reply.summary }));
    if (left && items.length > 1) {
      box.appendChild(el('div', { class: 'ssc-walk' }, [
        walking
          ? el('button', { class: 'btn ghost sm', text: 'Stop', onclick: () => { stopWalk = true; } })
          : el('button', { class: 'btn sm', text: 'Apply one by one',
            title: 'Apply every item still to go, in order, with a pause between, '
                 + 'so you can watch each one land. Stop at any time; every '
                 + 'change can be undone from its row.',
            onclick: walk }),
        el('span', { class: 'ss-say', text: 'Moved lines are proposals until you '
          + 'Accept the step; relabels save at once, like painting the rail.' }),
      ]));
    }
    const list = el('div', { class: 'ssc-items' });
    items.forEach((it, i) => list.appendChild(itemRow(it, i)));
    box.appendChild(list);
    return box;
  }

  return { rowBits, wantsDrawer, card, enter, leave, fromLink,
           get beta() { return beta(); },
           _state: () => ({ gid, cur, busy, walking, undo }) };
})();
