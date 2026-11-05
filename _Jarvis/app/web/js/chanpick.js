/* chanpick.js -- choosing channels, one way, everywhere.

   The user (2026-11-04): "standardize channel picking for any sort of
   processing data throughout Jarvis. No ugly basic check boxes." Before
   this, Incisor, Doppler (twice) and Braces each drew their own grid of
   native checkboxes, and Doppler's Many list had no way to reach a
   recording's channels at all while Incisor's did.

   Two pieces:

   BARRY.ui.channelPicker(opts) -- the control. A tile per channel, grouped
   in banks of 32 (the rig records in banks of 32), with the quick picks
   over it and a count beside them. Click toggles one; shift-click toggles
   the run from the last one clicked; drag paints the state the first tile
   took across every tile it passes. Nothing is ever hidden: a bad channel
   is struck through, a channel this run cannot read is dimmed and says
   why, and neither is ever cut short.

     channels   [{ number, label, bad }]
     mode       'bad'  -- on means "not marked bad"; a change writes
                          through to the recording for every tool
                'pick' -- on means "read in this run"; bad channels are
                          shown off and cannot be ticked
     on         Set or array of numbers that are on (mode 'pick' only)
     locked     (c) => reason | null: shown, not changeable
     out        (c) => reason | null: dimmed and said, still changeable --
                a channel this run's pick leaves out without it being bad
     busy       true while a write is in flight
     onToggle   (number, on) -- one channel
     onSet      (numbersOn)  -- a quick pick, a range or a drag, at once
     actions    which quick picks: any of 'all', 'good', 'none', 'evens',
                'odds', 'invert', 'banks'. Default by mode.
     reset      { text, onclick } -- the "put them all back" of mode 'bad'
     title      the words over it

   BARRY.ui.rowChannels(opts) -- the per-recording "Channels…" of a list of
   many recordings (Incisor's and Doppler's Many), so both tools reach a
   recording's channels the same way. It holds which rows are open and what
   each one read, across the host's repaints.

     estimate   (path) => Promise of { channels }: the tool's own estimate
     repaint    () => void: the host redraws
     changed    () => void: after a write, so the host re-plans */
(function () {
  'use strict';

  const BANK = 32;

  function numbersOf(list) {
    return new Set((list || []).map(Number));
  }

  function channelPicker(o) {
    const opt = o || {};
    const mode = opt.mode === 'pick' ? 'pick' : 'bad';
    // Every field the caller sent is kept: `locked` and `out` read the
    // caller's own (Incisor's `picked`, say).
    const all = (opt.channels || []).map((c) => Object.assign({}, c, {
      number: Number(c.number),
      label: c.label || ('CSC' + c.number),
      bad: !!c.bad,
    }));
    const lockedWhy = typeof opt.locked === 'function' ? opt.locked : () => null;
    const outWhy = typeof opt.out === 'function' ? opt.out : () => null;
    const isOn = mode === 'bad'
      ? (c) => !c.bad
      : (() => { const s = numbersOf(opt.on); return (c) => s.has(c.number); })();
    // What the tiles say now. Changed in place by a click or a drag, so the
    // grid answers before the write comes back.
    const state = new Map(all.map((c) => [c.number, isOn(c)]));
    const canChange = (c) => !opt.busy && !lockedWhy(c)
                             && !(mode === 'pick' && c.bad);

    const wrap = el('div', { class: 'chp' + (opt.busy ? ' busy' : ''),
                             'data-mode': mode });
    const count = el('span', { class: 'chp-count' });
    const sayCount = () => {
      const on = all.filter((c) => state.get(c.number)).length;
      const nBad = all.filter((c) => c.bad).length;
      count.textContent = mode === 'bad'
        ? on + ' of ' + all.length + ' read'
          + (nBad ? ' · ' + nBad + ' marked bad' : '')
        : on + ' of ' + all.length + ' in this run'
          + (nBad ? ' · ' + nBad + ' marked bad, left out' : '');
    };

    const commit = (nums) => {
      if (typeof opt.onSet === 'function') {
        opt.onSet(nums.slice().sort((a, b) => a - b));
      }
    };
    const onNow = () => all.filter((c) => state.get(c.number))
      .map((c) => c.number);
    const setAll = (want) => {
      // Locked and (in 'pick') bad channels keep what they are.
      // Shown at once, in place; the write follows.
      const out = [];
      for (const c of all) {
        const keep = !canChange(c);
        const v = keep ? state.get(c.number) : !!want(c);
        state.set(c.number, v);
        paintTile(c);
        if (v) out.push(c.number);
      }
      sayCount();
      commit(out);
    };

    const acts = opt.actions || (mode === 'bad'
      ? ['all', 'evens', 'odds', 'banks']
      : ['all', 'good', 'none', 'evens', 'odds', 'invert', 'banks']);
    const banks = [];
    for (let i = 0; i < all.length; i += BANK) banks.push(all.slice(i, i + BANK));
    const quick = el('div', { class: 'chp-quick', role: 'group',
                              'aria-label': 'Quick picks' });
    const q = (text, title, fn) => el('button', {
      type: 'button', class: 'chp-q', text, title,
      disabled: opt.busy ? 'disabled' : null, onclick: fn,
    });
    for (const a of acts) {
      if (a === 'all') {
        quick.appendChild(q(mode === 'bad' ? 'Read all' : 'All',
          mode === 'bad' ? 'Mark none of them bad'
                         : 'Every channel that is not marked bad',
          () => setAll(() => true)));
      } else if (a === 'good' && mode === 'pick') {
        quick.appendChild(q('Good ones', 'Every channel not marked bad',
          () => setAll((c) => !c.bad)));
      } else if (a === 'none' && mode === 'pick') {
        quick.appendChild(q('None', 'Clear the run', () => setAll(() => false)));
      } else if (a === 'evens') {
        quick.appendChild(q('Evens', mode === 'bad'
          ? 'Read the even channels; mark the odd ones bad'
          : 'Only the even channels', () => setAll((c) => c.number % 2 === 0)));
      } else if (a === 'odds') {
        quick.appendChild(q('Odds', mode === 'bad'
          ? 'Read the odd channels; mark the even ones bad'
          : 'Only the odd channels', () => setAll((c) => c.number % 2 === 1)));
      } else if (a === 'invert' && mode === 'pick') {
        quick.appendChild(q('Invert', 'Swap what is in and what is out',
          () => setAll((c) => !state.get(c.number))));
      } else if (a === 'banks' && banks.length > 1) {
        banks.forEach((b) => {
          const lo = b[0].number, hi = b[b.length - 1].number;
          quick.appendChild(q(lo + '–' + hi, 'Only CSC' + lo + ' to CSC' + hi,
            () => setAll((c) => c.number >= lo && c.number <= hi)));
        });
      }
    }
    if (opt.reset) {
      quick.appendChild(q(opt.reset.text || 'Put them all back',
        opt.reset.title || '', opt.reset.onclick));
    }
    const head = el('div', { class: 'chp-head' }, [
      opt.title ? el('span', { class: 'chp-title', text: opt.title }) : null,
      count,
      opt.busy ? el('span', { class: 'chp-busy', text: 'Saving…' }) : null,
      quick,
    ].filter(Boolean));
    wrap.appendChild(head);

    /* The tiles. Drag paints: the first tile pressed decides whether the
       drag turns tiles on or off, and every tile it then passes takes that
       state; one write when the pointer lets go. */
    const tiles = new Map();
    let drag = null;          // { to, touched:Set }
    let lastClicked = null;
    const paintTile = (c) => {
      const t = tiles.get(c.number);
      if (!t) return;
      const on = !!state.get(c.number);
      t.classList.toggle('on', on);
      t.setAttribute('aria-checked', on ? 'true' : 'false');
    };
    const why = (c) => {
      const lk = lockedWhy(c);
      if (lk) return c.label + ': ' + lk;
      const ow = !c.bad && outWhy(c);
      if (ow) return c.label + ': ' + ow;
      if (c.bad) {
        return mode === 'bad'
          ? c.label + ' is marked bad and is not read. Click to read it again.'
          : c.label + ' is marked bad on this recording, so no run reads it.';
      }
      return mode === 'bad'
        ? c.label + ' is read. Click to mark it bad for this recording, '
          + 'everywhere.'
        : c.label + (state.get(c.number) ? ' is in this run' : ' is left out of '
          + 'this run only');
    };
    const finishDrag = () => {
      if (!drag) return;
      const d = drag;
      drag = null;
      document.removeEventListener('pointerup', finishDrag);
      document.removeEventListener('pointercancel', finishDrag);
      if (d.touched.size === 1 && typeof opt.onToggle === 'function') {
        const n = d.touched.values().next().value;
        opt.onToggle(n, d.to);
      } else if (d.touched.size) {
        commit(onNow());
      }
      sayCount();
    };
    const touch = (c) => {
      if (!drag || !canChange(c) || drag.touched.has(c.number)) return;
      drag.touched.add(c.number);
      state.set(c.number, drag.to);
      paintTile(c);
    };

    banks.forEach((b) => {
      const g = el('div', { class: 'chp-bank' });
      if (banks.length > 1) {
        g.appendChild(el('div', { class: 'chp-bank-h',
          text: 'CSC ' + b[0].number + '–' + b[b.length - 1].number }));
      }
      const grid = el('div', { class: 'chp-grid', role: 'group',
        'aria-label': 'CSC ' + b[0].number + ' to ' + b[b.length - 1].number });
      for (const c of b) {
        const lk = lockedWhy(c);
        const t = el('button', {
          type: 'button',
          class: 'chp-t' + (c.bad ? ' bad' : '') + (lk ? ' locked' : '')
                 + (!c.bad && outWhy(c) ? ' out' : ''),
          role: 'checkbox', 'aria-checked': state.get(c.number) ? 'true' : 'false',
          'aria-label': c.label, title: why(c), 'data-ch': String(c.number),
          disabled: canChange(c) ? null : 'disabled',
          onpointerdown: (e) => {
            if (!canChange(c) || e.button !== 0) return;
            e.preventDefault();
            if (e.shiftKey && lastClicked != null) {
              // A run: everything between the last one clicked and this,
              // set to what this one becomes.
              const to = !state.get(c.number);
              const lo = Math.min(lastClicked, c.number);
              const hi = Math.max(lastClicked, c.number);
              for (const x of all) {
                if (x.number >= lo && x.number <= hi && canChange(x)) {
                  state.set(x.number, to);
                  paintTile(x);
                }
              }
              lastClicked = c.number;
              commit(onNow());
              sayCount();
              return;
            }
            lastClicked = c.number;
            drag = { to: !state.get(c.number), touched: new Set() };
            touch(c);
            document.addEventListener('pointerup', finishDrag);
            document.addEventListener('pointercancel', finishDrag);
          },
          onpointerenter: () => touch(c),
          /* A click with no pointer behind it -- assistive technology, or a
             script's .click() -- toggles one. A real press was already
             handled on pointerdown, and a key on keydown. */
          onclick: (e) => {
            if (e.detail !== 0 || !canChange(c)) return;
            const to = !state.get(c.number);
            state.set(c.number, to);
            paintTile(c);
            sayCount();
            lastClicked = c.number;
            if (typeof opt.onToggle === 'function') opt.onToggle(c.number, to);
          },
          onkeydown: (e) => {
            if (e.key === ' ' || e.key === 'Enter') {
              e.preventDefault();
              if (!canChange(c)) return;
              const to = !state.get(c.number);
              state.set(c.number, to);
              paintTile(c);
              sayCount();
              lastClicked = c.number;
              if (typeof opt.onToggle === 'function') opt.onToggle(c.number, to);
              return;
            }
            const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 8,
                           ArrowUp: -8 }[e.key];
            if (!step) return;
            e.preventDefault();
            const i = all.findIndex((x) => x.number === c.number) + step;
            const next = all[Math.max(0, Math.min(all.length - 1, i))];
            const tn = next && tiles.get(next.number);
            if (tn) tn.focus();
          },
        }, [
          el('span', { class: 'chp-n', text: String(c.number) }),
        ]);
        tiles.set(c.number, t);
        grid.appendChild(t);
      }
      g.appendChild(grid);
      wrap.appendChild(g);
    });
    for (const c of all) paintTile(c);
    sayCount();
    return wrap;
  }

  /* One recording's channels inside a list of many, by the same record the
     single panels write (`/api/session/bad-for-path`, by CSC number),
     reached by the recording's own path here or by `vacc:<gid>`. */
  function rowChannels(o) {
    const opt = o || {};
    const open = {};             // gid -> { busy, est, error, path }
    const repaint = () => { if (typeof opt.repaint === 'function') opt.repaint(); };
    const pathOf = (r) => r.here || ('vacc:' + r.gid);

    async function read(r, path) {
      try {
        const got = await opt.estimate(path);
        open[r.gid] = { est: got, path };
      } catch (e) {
        open[r.gid] = { error: e.message, path };
      }
      repaint();
    }

    async function write(r, numbers, change) {
      const st = open[r.gid];
      if (!st || st.busy) return;
      st.busy = true;
      repaint();
      try {
        await apiPost('/api/session/bad-for-path', Object.assign({
          path: st.path,
          bad_channels: numbers.map(Number).sort((a, b) => a - b),
        }, change || {}));
      } catch (e) {
        st.busy = false;
        toast(e.message, 'err', 9000);
        repaint();
        return;
      }
      await read(r, st.path);
      if (typeof opt.changed === 'function') opt.changed(r);
    }

    const api = {
      isOpen: (r) => !!open[r.gid],
      toggle(r) {
        if (open[r.gid]) { delete open[r.gid]; repaint(); return; }
        open[r.gid] = { busy: true, path: pathOf(r) };
        repaint();
        read(r, pathOf(r));
      },
      button(r) {
        const on = !!open[r.gid];
        return el('button', {
          type: 'button', class: 'mini', text: on ? 'Done' : 'Channels…',
          'aria-expanded': on ? 'true' : 'false',
          title: 'Which of this recording’s channels are read. Taking one out '
               + 'marks it bad for this recording everywhere.',
          onclick: (e) => { e.preventDefault(); e.stopPropagation(); api.toggle(r); },
        });
      },
      editor(r) {
        const st = open[r.gid] || {};
        if (st.error) {
          return el('p', { class: 'warn-line row-chans', text: st.error });
        }
        if (!st.est) {
          return el('p', { class: 'hint quiet row-chans',
            text: r.here ? 'Reading its channel list…'
              : 'Reading its channel list off the cluster: the header only, '
                + 'a few seconds.' });
        }
        const all = st.est.channels || [];
        const bad = all.filter((c) => c.bad).map((c) => Number(c.number));
        return el('div', { class: 'row-chans' }, [
          channelPicker({
            mode: 'bad', channels: all, busy: !!st.busy,
            // One channel is sent as a change, not as a list with one
            // channel different: the list was read when the row opened.
            onToggle: (n, on) => {
              const now = new Set(bad);
              if (on) now.delete(n); else now.add(n);
              write(r, Array.from(now), on ? { remove: [n] } : { add: [n] });
            },
            onSet: (onNums) => {
              const keep = new Set(onNums);
              write(r, all.map((c) => Number(c.number))
                          .filter((n) => !keep.has(n)));
            },
            reset: bad.length ? { text: 'Put them all back',
                                  onclick: () => write(r, []) } : null,
          }),
        ]);
      },
    };
    return api;
  }

  /* The words of a Many list, said the same way in every tool that sends
     many recordings to the cluster (Incisor's and Doppler's, 2026-11-04:
     "streamline both ... to be in sync with each other UI-wise"). `verb`
     is what the tool does to one: 'scanned', 'run'. */
  function manySentence(todo, verb) {
    const n = (todo || []).length;
    const nNative = (todo || []).filter((r) => r.state === 'native').length;
    return n.toLocaleString() + ' recordings are VACC loaded: '
      + nNative.toLocaleString() + ' on the lab’s netfiles share, read in '
      + 'place, and ' + (n - nNative).toLocaleString() + ' as copies in '
      + 'scratch. Whether this computer has them does not matter: the work '
      + 'happens where the data is and comes back here. Ones already '
      + verb + ' with these settings are marked.';
  }

  /* One row's facts: where it is read, its folder, its channels and length,
     which are marked bad (named), and whether this computer has it too. */
  function manyRowSub(r) {
    const bad = r.bad_channels || [];
    // The folder itself, because a recording's id can hold several: a DEWEY
    // day is one id across FP1, SPC and FP2, and this is the one that runs.
    const folder = String(r.remote || '').split('/').filter(Boolean)
      .slice(-2).join('/');
    return (r.state === 'native' ? 'netfiles, read in place'
                                 : 'a copy in VACC scratch')
      + (folder ? ' · ' + folder : '')
      + ' · ' + (r.n_channels ? r.n_channels + ' channels'
                              : 'channels read on the cluster')
      + (r.duration_s ? ' · ' + Math.round(r.duration_s / 60) + ' min' : '')
      + (bad.length ? ' · ' + bad.length + ' marked bad ('
                      + bad.map((n) => 'CSC' + n).join(', ') + ')'
                    : ' · none marked bad')
      + (r.here ? ' · also on this computer' : '');
  }

  BARRY.ui.channelPicker = channelPicker;
  BARRY.ui.rowChannels = rowChannels;
  BARRY.ui.manySentence = manySentence;
  BARRY.ui.manyRowSub = manyRowSub;
})();
