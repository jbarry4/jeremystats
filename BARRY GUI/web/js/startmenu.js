/* ==========================================================================
   startmenu.js -- a title screen and a menu, the way a game starts.

   The user's ask (2026-10-20): "a cooler start up animation ... like a
   videogame start up menu", chosen as a title screen plus a menu. The boot
   overlay already covers the seconds the catalogue takes to read; when it
   is done, instead of fading away it becomes the title -- the mark, the
   name, the scope still sweeping behind them -- and a menu:

       Continue           where you left off (Enter, or any key)
       Open a recording   Sessions
       ToolKit            the bundles and tools
       Settings           theme, density, motion
       Patch notes        what changed

   Arrows (or W / S) move, Enter or Space chooses, Escape or any other key
   is Continue. Each choice is one soft note through jarvisfx, under the
   same mute switch as every other sound. "Show at start" turns it off for
   this browser.

   It never stands in anybody's way:
     * not in an iframe (every harness drives the app in one), not under
       automation, not in a pop-out or aid window, not with ?menu=0;
     * not when the address asks for somewhere specific (a deep link);
     * reduced motion shows it all at once, with nothing moving.
   ========================================================================== */
'use strict';

BARRY.startMenu = (function () {
  const PREF = 'barry.startmenu';          // 'off' to skip it
  let open = null;                         // { box, items, at, finish }

  const fx = () => BARRY.jarvisfx || window.JarvisFX || null;
  const sfx = (name, a) => {
    try { const f = fx(); if (f && !f.muted && f[name]) f[name](a); }
    catch (e) { /* a sound never stops anything */ }
  };
  const reduced = () => !!(BARRY.ui && BARRY.ui.reducedMotion
                           && BARRY.ui.reducedMotion());

  function wanted() {
    try {
      if (window.top !== window) return false;
    } catch (e) { return false; }
    if (navigator.webdriver) return false;
    const b = document.body;
    if (b && (b.classList.contains('solo-window')
              || b.classList.contains('aid-window'))) return false;
    const q = new URLSearchParams(location.search);
    if (q.get('menu') === '0') return false;
    for (const k of ['view', 'session', 'path', 'gid', 'tool', 'open']) {
      if (q.get(k)) return false;
    }
    try { if (localStorage.getItem(PREF) === 'off') return false; }
    catch (e) { /* private mode: show it */ }
    return true;
  }

  const ITEMS = [
    ['continue', 'Continue', 'Where you left off'],
    ['sessions', 'Open a recording', 'Every recording Jarvis knows'],
    ['toolkit', 'ToolKit', 'The bundles and every tool'],
    ['settings', 'Settings', 'Theme, density and motion'],
    ['notes', 'Patch notes', 'What changed, and when'],
  ];

  function act(id) {
    try {
      if (id === 'sessions' && typeof setView === 'function') setView('sessions');
      else if (id === 'toolkit' && typeof setView === 'function') setView('toolkit');
      else if (id === 'settings' && typeof showThemePicker === 'function') {
        setTimeout(() => showThemePicker(), 420);
      } else if (id === 'notes' && BARRY.notes && BARRY.notes.open) {
        setTimeout(() => BARRY.notes.open(), 420);
      }
    } catch (e) {
      reportClientError('startmenu.act', e.message, e.stack);
    }
  }

  function choose(id) {
    if (!open) return;
    sfx('select');
    const o = open;
    open = null;
    window.removeEventListener('keydown', onKey, true);
    act(id);
    o.finish();
  }

  function moveTo(i) {
    if (!open) return;
    const n = open.items.length;
    open.at = (i + n) % n;
    open.items.forEach((b, k) => {
      b.classList.toggle('on', k === open.at);
      b.setAttribute('aria-selected', k === open.at ? 'true' : 'false');
    });
    const b = open.items[open.at];
    if (b && document.activeElement !== b) b.focus({ preventScroll: true });
  }

  function onKey(e) {
    if (!open) return;
    const k = e.key;
    if (k === 'ArrowDown' || k === 'ArrowRight' || k === 's' || k === 'S'
        || (k === 'Tab' && !e.shiftKey)) {
      e.preventDefault(); sfx('hover'); moveTo(open.at + 1); return;
    }
    if (k === 'ArrowUp' || k === 'ArrowLeft' || k === 'w' || k === 'W'
        || (k === 'Tab' && e.shiftKey)) {
      e.preventDefault(); sfx('hover'); moveTo(open.at - 1); return;
    }
    if (k === 'Enter' || k === ' ') {
      e.preventDefault(); choose(ITEMS[open.at][0]); return;
    }
    // Escape, or any other key: straight in, where you left off.
    if (k.length === 1 || k === 'Escape') {
      e.preventDefault(); choose('continue');
    }
  }

  function versionText() {
    try {
      const n = BARRY.notes && BARRY.notes.get && BARRY.notes.get();
      return n && n.version ? 'v' + n.version : '';
    } catch (e) { return ''; }
  }

  /* Take over the boot overlay: the title, then the menu. `finish` is what
     the boot screen does to go away; it is called with the choice made. */
  function take(box, finish) {
    if (open) return;
    const still = reduced();
    box.classList.add('boot-menu');
    if (still) box.classList.add('still');

    const mark = el('div', { class: 'sm-mark', 'aria-hidden': 'true' });
    try {
      if (BARRY.jarvis && BARRY.jarvis.markSvg) {
        mark.innerHTML = BARRY.jarvis.markSvg(null, 'full');
      }
    } catch (e) { /* a title without its mark is still a title */ }

    /* The name, one letter at a time -- the reveal's own gesture. Kept in
       the DOM as one word for anybody reading it; the letters are spans. */
    const word = document.documentElement.dataset.jarvis === 'off'
      ? 'Workbench' : 'Jarvis';
    const name = el('h1', { class: 'sm-name', 'aria-label': word },
      word.split('').map((ch, i) => el('span', {
        class: 'sm-letter', text: ch, style: '--i:' + i,
      })));
    if (!still) {
      word.split('').forEach((_, i) => setTimeout(() => sfx('tick', i),
                                                  140 + i * 70));
    }

    const items = ITEMS.map(([id, label, sub], i) => el('button', {
      class: 'sm-item' + (i === 0 ? ' on' : ''), type: 'button',
      role: 'option', 'aria-selected': i === 0 ? 'true' : 'false',
      style: '--i:' + i,
      onclick: () => choose(id),
      onmouseenter: () => { if (open && open.at !== i) { sfx('hover'); moveTo(i); } },
    }, [
      el('span', { class: 'sm-caret', 'aria-hidden': 'true' }),
      el('span', { class: 'sm-label', text: label }),
      el('span', { class: 'sm-sub', text: sub }),
    ]));

    let showAtStart = true;
    try { showAtStart = localStorage.getItem(PREF) !== 'off'; } catch (e) { /* on */ }
    const keep = el('label', { class: 'sm-keep' }, [
      el('input', { type: 'checkbox', checked: showAtStart ? 'checked' : null,
        onchange: (e) => {
          try { localStorage.setItem(PREF, e.target.checked ? 'on' : 'off'); }
          catch (err) { /* private mode */ }
        } }),
      el('span', { text: 'Show this at start' }),
    ]);

    const panel = el('div', { class: 'sm-panel', role: 'dialog',
                              'aria-label': 'Start' }, [
      el('div', { class: 'sm-title' }, [
        mark,
        name,
        el('div', { class: 'sm-tag', text: 'Neural data workbench'
                                           + (versionText() ? '  ·  '
                                              + versionText() : '') }),
      ]),
      el('div', { class: 'sm-menu', role: 'listbox' }, items),
      el('div', { class: 'sm-foot' }, [
        el('span', { class: 'sm-keys' }, [
          el('kbd', { text: '↑' }), el('kbd', { text: '↓' }),
          el('span', { text: 'choose' }),
          el('kbd', { text: 'Enter' }), el('span', { text: 'start' }),
          el('kbd', { text: 'Esc' }), el('span', { text: 'skip' }),
        ]),
        keep,
      ]),
    ]);
    box.appendChild(panel);

    open = { box, items, at: 0, finish: () => finish() };
    window.addEventListener('keydown', onKey, true);
    // After the letters have landed, so the first key press is not lost to
    // the animation, and focus is on Continue for Enter.
    setTimeout(() => moveTo(0), still ? 0 : 380);
  }

  return { wanted, take, get open() { return !!open; } };
})();
