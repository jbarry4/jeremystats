/* ==========================================================================
   curate.js -- Going through candidates one at a time.

   The same shape of job whether the candidates are dentate spikes or
   interictal discharges: jump to one, look at it, press a key, move on. So
   this is one mode with a vocabulary handed to it, not two tools.

   Three things it has to get right, all of which the standalone sorters got
   right and are the reason people liked them:

   It has to be fast. A key per category, no confirmation, no dialog. Six
   hundred candidates at two seconds each is twenty minutes; at five seconds
   it is an afternoon.

   It has to be undoable. The hand moves faster than the eye and the wrong
   key gets pressed. Undo goes back a decision AND back a candidate, because
   that is what "undo" means when you have already moved on.

   It must not lose anything. Every keystroke is written through to the
   server, so closing the laptop mid-set costs nothing. The set lives against
   the recording's global id, so it is the same set on the next machine.

   The layout it opens with -- voltage traces large, with a spectrogram, CSD
   and voltage raster beside them -- is the one you would build by hand
   before starting, so it is built for you.
   ========================================================================== */
'use strict';

BARRY.curate = (function () {
  let set_ = null;        // the curation set as the server has it
  let kind = null;        // its vocabulary
  let sess = null;        // the open recording
  let index = 0;          // which candidate
  let span = 1.0;         // seconds of recording shown around it
  let history = [];       // {id, from} so undo means something
  let saving = 0;
  let onlyLeft = true;    // step past the ones already decided

  /* ==================================================================
     Entering and leaving
     ================================================================== */
  async function enter(gid, kindId, opts) {
    let data;
    try {
      data = await api('/api/curation/' + encodeURIComponent(gid) + '/'
                       + encodeURIComponent(kindId));
    } catch (e) {
      toast('Could not open that curation set: ' + e.message, 'err', 8000);
      return false;
    }
    set_ = data.set;
    kind = { id: set_.kind, labels: set_.labels || [] };

    const known = (data.session || {});
    const path = (known.here || [])[0];
    if (!path) {
      toast('None of this recording’s paths are reachable from this '
            + 'machine, so there is nothing to look at.', 'err', 9000);
      return false;
    }

    setView('xplore');
    sess = await BARRY.views.xplore.open(path);
    if (!sess) return false;

    span = (opts && opts.span) || (set_.kind === 'ds' ? 0.6 : 2.0);
    index = 0;
    history = [];
    onlyLeft = true;

    layout();
    // Hand the candidates to the session so the trace can draw them.
    sess.curation = { kind: set_.kind, set: set_, index: 0 };
    goTo(firstUndecided(), true);
    render();

    BARRY.activity.log('curation.enter', {
      gid, kind: set_.kind, n: (set_.events || []).length,
      left: left(),
    }, sess);
    return true;
  }

  function exit() {
    if (!set_) return;
    BARRY.activity.log('curation.leave', {
      gid: set_.gid, kind: set_.kind, left: left(),
    }, sess);
    if (sess) delete sess.curation;
    set_ = null; kind = null; sess = null; history = [];
    const bar = $('#curBar');
    if (bar) bar.remove();
    document.removeEventListener('keydown', keys, true);
    if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
  }

  /* The layout the job wants: the traces big, the aids beside them.

     Rasters and a spectrogram are what tell you whether a deflection is the
     thing you are looking for or an artifact on one wire, so they are up
     from the start rather than something you go and enable. Everything is
     still an ordinary pane, so it can be rearranged like any other. */
  function layout() {
    const every8 = sess.info.channels
      .filter((c, i) => i % 8 === 0).map((c) => c.index);
    BARRY.views.xplore.setPanes([
      { panel: 'traces' },
      { panel: 'spectrogram', tfChannels: every8, tfMode: 'stack',
        fmin: 1, fmax: 250 },
      { panel: 'csd' },
      { panel: 'voltage' },
    // The traces get the bigger share; the rest are for glancing at.
    ], { col: 0.62, row: 0.55 });
  }

  /* ==================================================================
     Moving
     ================================================================== */
  const events = () => (set_ && set_.events) || [];
  const current = () => events()[index] || null;
  const left = () => events().filter((e) => !e.label).length;

  function firstUndecided() {
    const i = events().findIndex((e) => !e.label);
    return i < 0 ? 0 : i;
  }

  function goTo(i, quiet) {
    const n = events().length;
    if (!n) return;
    index = Math.max(0, Math.min(n - 1, i));
    const ev = current();
    if (sess.curation) sess.curation.index = index;
    // Centred, so the thing is where the eye already is.
    BARRY.views.xplore.setWindow(0, Math.max(0, ev.start - span / 2), span);
    if (!quiet) render();
  }

  function step(d) {
    const n = events().length;
    if (!n) return;
    let i = index;
    for (let tries = 0; tries < n; tries++) {
      i += d;
      if (i < 0 || i >= n) {
        toast(d > 0 ? 'That was the last one.' : 'That is the first one.',
              null, 2500);
        return;
      }
      if (!onlyLeft || !events()[i].label) break;
    }
    goTo(i);
  }

  /* ==================================================================
     Deciding
     ================================================================== */
  async function assign(labelId) {
    const ev = current();
    if (!ev) return;
    const was = ev.label || null;

    // Optimistic: the key press has to feel instant. The write follows, and
    // a failure puts it back and says so rather than pretending.
    ev.label = labelId;
    history.push({ id: ev.id, from: was });
    if (history.length > 500) history.shift();
    render();
    // Move on before the round trip, which is the whole point of the mode.
    step(1);

    saving += 1;
    updateSaving();
    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(set_.gid) + '/'
        + encodeURIComponent(set_.kind) + '/label',
        { event: ev.id, label: labelId });
      if (res.progress) set_._progress = res.progress;
    } catch (e) {
      ev.label = was;
      toast('That did not save: ' + e.message, 'err', 8000);
      render();
    } finally {
      saving -= 1;
      updateSaving();
    }
  }

  async function undo() {
    const last = history.pop();
    if (!last) { toast('Nothing to undo.', null, 2000); return; }
    const at = events().findIndex((e) => e.id === last.id);
    if (at < 0) return;
    events()[at].label = last.from;
    // Back to the one that was got wrong, which is what undo has to mean
    // once you have already moved on.
    goTo(at);
    try {
      await apiPost('/api/curation/' + encodeURIComponent(set_.gid) + '/'
                    + encodeURIComponent(set_.kind) + '/label',
                    { event: last.id, label: last.from });
    } catch (e) { toast(e.message, 'err'); }
    render();
  }

  /* ==================================================================
     The bar
     ================================================================== */
  function render() {
    if (!set_) return;
    let bar = $('#curBar');
    if (!bar) {
      bar = el('div', { class: 'cur-bar', id: 'curBar' });
      const body = $('#xfBody');
      if (body) body.appendChild(bar); else document.body.appendChild(bar);
      document.addEventListener('keydown', keys, true);
    }
    bar.innerHTML = '';

    const n = events().length;
    const done = n - left();
    const ev = current();

    bar.appendChild(el('div', { class: 'cur-where' }, [
      el('strong', { text: set_.name || 'Curating' }),
      el('span', { class: 'cur-sub',
        text: (ev ? clock(ev.start) : '—')
            + (ev && ev.channel != null ? '  ·  CSC ' + ev.channel : '') }),
      el('span', { class: 'cur-count',
        text: (index + 1) + ' / ' + n }),
    ]));

    bar.appendChild(el('div', { class: 'cur-prog' }, [
      el('i', { style: 'width:' + (n ? (done / n * 100) : 0) + '%' }),
      el('span', { text: done + ' decided · ' + left() + ' left' }),
    ]));

    const cats = el('div', { class: 'cur-cats' });
    for (const lab of (kind.labels || [])) {
      const on = ev && ev.label === lab.id;
      cats.appendChild(el('button', {
        class: 'cur-cat' + (on ? ' on' : ''),
        style: '--cat:' + lab.color,
        title: lab.name + '   (' + lab.keys.join(' or ') + ')',
        onclick: () => assign(on ? null : lab.id),
      }, [
        el('kbd', { text: lab.keys[0] }),
        el('span', { text: lab.name }),
      ]));
    }
    bar.appendChild(cats);

    bar.appendChild(el('div', { class: 'cur-nav' }, [
      el('button', { class: 'mini', text: '◀', title: 'Previous  (p)',
                     onclick: () => step(-1) }),
      el('button', { class: 'mini', text: '▶', title: 'Next  (n)',
                     onclick: () => step(1) }),
      el('button', { class: 'mini', text: '↶', title: 'Undo  (u)',
                     disabled: history.length ? null : 'disabled',
                     onclick: undo }),
      el('label', { class: 'toggle sm' + (onlyLeft ? ' on' : ''),
                    title: 'Step past the ones already decided' }, [
        el('input', {
          type: 'checkbox', checked: onlyLeft ? 'checked' : null,
          onchange: (e) => { onlyLeft = e.target.checked; render(); },
        }),
        el('span', { text: 'Skip decided' }),
      ]),
      el('div', { class: 'ctl' }, [
        el('label', { text: 'Window s' }),
        el('input', {
          type: 'number', step: '0.1', value: String(span),
          style: 'width:56px',
          onchange: (e) => {
            span = Math.max(0.05, parseFloat(e.target.value) || 1);
            goTo(index);
          },
        }),
      ]),
      el('span', { class: 'cur-saving', id: 'curSaving', text: '' }),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'Bank the results…',
                     onclick: bank }),
      el('button', { class: 'btn ghost sm', text: 'Leave', onclick: exit }),
    ]));

    // Only the overlay changed, so repaint rather than refetch. The window
    // move in goTo() is what asks the server for new samples, and it does
    // that once.
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();
  }

  function updateSaving() {
    const n = $('#curSaving');
    if (n) n.textContent = saving ? 'saving…' : '';
  }

  function keys(e) {
    if (!set_) return;
    if (isTyping(e)) return;
    const k = e.key.toLowerCase();

    /* Navigation is checked first, and wins.

       The server strips reserved keys out of every vocabulary, so this should
       never actually matter -- but "should never" is how `p` ended up meaning
       both "previous" and "sputter", and the key that moves you has to be the
       one thing that always moves you. */
    const map = {
      n: () => step(1), arrowright: () => step(1),
      p: () => step(-1), arrowleft: () => step(-1),
      u: undo, backspace: undo,
      escape: exit,
    };
    if (map[k]) { e.preventDefault(); e.stopPropagation(); map[k](); return; }

    for (const lab of (kind.labels || [])) {
      if ((lab.keys || []).includes(k)) {
        e.preventDefault(); e.stopPropagation();
        assign(lab.id);
        return;
      }
    }
  }

  async function bank() {
    const who = await askPath('Who is banking these?',
                              'your name or email');
    if (!who) return;
    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(set_.gid) + '/'
        + encodeURIComponent(set_.kind) + '/bank',
        { added_by: who });
      toast('Banked ' + res.entries.length + ' entr'
            + (res.entries.length === 1 ? 'y' : 'ies') + ': '
            + res.entries.map((x) => x.label + ' (' + x.n + ')').join(', '),
            'ok', 8000);
      BARRY.refreshSync();
    } catch (e) { toast(e.message, 'err', 8000); }
  }

  /* ==================================================================
     What the trace shows
     ================================================================== */
  function draw(ctx, s, win, x0, plotW, y0, plotH, P) {
    if (!s || !s.curation || !set_) return;
    const evs = events();
    const dur = win.t1 - win.t0;
    const colorOf = (id) => {
      const l = (kind.labels || []).find((x) => x.id === id);
      return l ? l.color : null;
    };

    ctx.save();
    for (let i = 0; i < evs.length; i++) {
      const e = evs[i];
      if (e.start < win.t0 || e.start > win.t1) continue;
      const x = Math.round(x0 + ((e.start - win.t0) / dur) * plotW) + 0.5;
      const isNow = i === index;
      const c = e.label ? colorOf(e.label) : P.text3 || '#7593a2';

      // The one being decided gets a full-height line; the others get a tick,
      // so the candidate in question is never ambiguous.
      ctx.globalAlpha = isNow ? 0.95 : (e.label ? 0.55 : 0.4);
      ctx.strokeStyle = isNow ? (e.label ? c : P.accent) : c;
      ctx.lineWidth = isNow ? 2 : 1;
      if (!isNow && !e.label) ctx.setLineDash([3, 3]); else ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(x, isNow ? y0 : y0 + plotH - 18);
      ctx.lineTo(x, y0 + plotH);
      ctx.stroke();

      if (isNow) {
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
        ctx.fillStyle = e.label ? c : P.accent;
        ctx.beginPath();
        ctx.arc(x, y0 + 7, 4.5, 0, Math.PI * 2);
        ctx.fill();
        const name = e.label
          ? ((kind.labels.find((l) => l.id === e.label) || {}).name || '')
          : 'undecided';
        ctx.font = '10px ' + (P.mono || 'monospace');
        ctx.textAlign = 'center';
        ctx.fillText(name, x, y0 + 24);
      }
    }
    ctx.restore();
  }

  function clock(t) {
    const m = Math.floor(t / 60);
    const s = t - m * 60;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(2);
  }

  return {
    enter, exit, draw,
    get active() { return !!set_; },
    get state() {
      return set_ ? { gid: set_.gid, kind: set_.kind, index,
                      total: events().length, left: left() } : null;
    },
  };
})();
