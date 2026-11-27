/* ==========================================================================
   seahorse_ui.js -- the Seahorse tab's controls (BARRY.shUI).

   One small kit, so every control in the tab looks and behaves the same:

     icon(name)          a 24-unit line icon in the current text color
     seg(label, opts, cur, on)
                         a named-state switch: the pressed option is what is
                         showing (Shown / Hidden, Story / As traced, ...)
     setSeg(g, v)        press an option from outside, without a rebuild
     range(o)            a slider with its value written beside it
     button(o)           a text button with an optional icon
     menu(anchor, sections, o)
                         a menu that opens from a button: items with a line of
                         explanation, arrow keys, Escape, a click away closes
     sheet(anchor, build, o)
                         a floating panel built by build(box); the View sheet
     closeAll()          close whatever menu or sheet is open

   Nothing here knows about the atlas; seahorse.js owns the state.
   ========================================================================== */
'use strict';

BARRY.shUI = (function () {
  const NS = 'http://www.w3.org/2000/svg';
  /* line icons on a 24 grid, 1.7 stroke; fill="currentColor" marks solid parts */
  const PATHS = {
    play: '<path d="M8.2 5.6v12.8a.6.6 0 0 0 .92.5l10-6.4a.6.6 0 0 0 0-1l-10-6.4a.6.6 0 0 0-.92.5z" fill="currentColor" stroke="none"/>',
    pause: '<rect x="6.6" y="5.4" width="3.8" height="13.2" rx="1.1" fill="currentColor" stroke="none"/><rect x="13.6" y="5.4" width="3.8" height="13.2" rx="1.1" fill="currentColor" stroke="none"/>',
    prev: '<path d="M17.4 6.2v11.6a.5.5 0 0 1-.78.42L8.8 12.4a.5.5 0 0 1 0-.8l7.82-5.82a.5.5 0 0 1 .78.42z" fill="currentColor" stroke="none"/><path d="M6.6 6v12"/>',
    next: '<path d="M6.6 6.2v11.6a.5.5 0 0 0 .78.42l7.82-5.82a.5.5 0 0 0 0-.8L7.38 5.78a.5.5 0 0 0-.78.42z" fill="currentColor" stroke="none"/><path d="M17.4 6v12"/>',
    close: '<path d="M7 7l10 10M17 7L7 17"/>',
    sliders: '<path d="M4 7.5h9M17.5 7.5H20M4 16.5h3M11.5 16.5H20"/><circle cx="15.3" cy="7.5" r="2.2"/><circle cx="9.3" cy="16.5" r="2.2"/>',
    frame: '<path d="M4.5 9V6a1.5 1.5 0 0 1 1.5-1.5h3M15 4.5h3A1.5 1.5 0 0 1 19.5 6v3M19.5 15v3a1.5 1.5 0 0 1-1.5 1.5h-3M9 19.5H6A1.5 1.5 0 0 1 4.5 18v-3"/><circle cx="12" cy="12" r="2.2"/>',
    search: '<circle cx="10.8" cy="10.8" r="6.2"/><path d="M15.4 15.4l4.6 4.6"/>',
    down: '<path d="M7 10l5 5 5-5"/>',
    up: '<path d="M7 14l5-5 5 5"/>',
    left: '<path d="M14.5 6.5L9 12l5.5 5.5"/>',
    right: '<path d="M9.5 6.5L15 12l-5.5 5.5"/>',
    record: '<circle cx="12" cy="12" r="5.6" fill="currentColor" stroke="none"/>',
    share: '<path d="M12 14.5V4.5M8.2 8.2L12 4.4l3.8 3.8"/><path d="M5.5 12v6a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5v-6"/>',
    quiz: '<rect x="4.5" y="7" width="11" height="13" rx="2"/><path d="M8.5 4.5h9a2 2 0 0 1 2 2v10"/><path d="M8.2 12.2a1.9 1.9 0 1 1 2.6 1.8c-.5.2-.8.6-.8 1.1M10 17.2v.1"/>',
    tour: '<path d="M6 20.5V4.5"/><path d="M6 5h11.5l-2.3 3.6 2.3 3.6H6"/>',
    ride: '<path d="M3.5 16.5c3.2 0 3.6-9 7.2-9s3.6 9 9.8 9"/><circle cx="10.7" cy="7.5" r="1.9" fill="currentColor" stroke="none"/>',
    wave: '<path d="M2.8 12.5h3.6l1.9-5.2 3 10.5 2.8-12.6 2.4 7.3h5.7"/>',
    camera: '<path d="M4.5 8.8A1.5 1.5 0 0 1 6 7.3h2.3l1.5-2.1h4.4l1.5 2.1H18a1.5 1.5 0 0 1 1.5 1.5v8.7A1.5 1.5 0 0 1 18 19H6a1.5 1.5 0 0 1-1.5-1.5z"/><circle cx="12" cy="12.9" r="3.3"/>',
    video: '<rect x="3.5" y="6.5" width="12" height="11" rx="2"/><path d="M15.5 10.4l4.6-2.8a.4.4 0 0 1 .6.34v8.12a.4.4 0 0 1-.6.34l-4.6-2.8"/>',
    bookmark: '<path d="M7 4.5h10a.5.5 0 0 1 .5.5v14.6a.4.4 0 0 1-.64.32L12 16.4l-4.86 3.52a.4.4 0 0 1-.64-.32V5a.5.5 0 0 1 .5-.5z"/>',
    views: '<rect x="4" y="5" width="7" height="6" rx="1.4"/><rect x="13" y="5" width="7" height="6" rx="1.4"/><rect x="4" y="13" width="7" height="6" rx="1.4"/><rect x="13" y="13" width="7" height="6" rx="1.4"/>',
    check: '<path d="M5.5 12.5l4 4 9-9.5"/>',
    probe: '<path d="M10.8 3.5h2.4v13l-1.2 4-1.2-4z"/><path d="M10.8 8.5h2.4M10.8 11.5h2.4"/>',
    cube: '<path d="M12 3.6l7.3 4.1v8.6L12 20.4l-7.3-4.1V7.7z"/><path d="M12 12l7.3-4.3M12 12L4.7 7.7M12 12v8.4"/>',
    section: '<rect x="4" y="4.5" width="16" height="15" rx="2.2"/><path d="M4 13.5c3.2-3.6 6.6 2.8 9.8-.6s4.4-1.6 6.2-.4"/>',
    nodes: '<circle cx="6.5" cy="7" r="2.3"/><circle cx="17.5" cy="7" r="2.3"/><circle cx="12" cy="17.5" r="2.3"/><path d="M8.6 8.4l2.4 6.9M15.4 8.4l-2.4 6.9M8.8 7h6.4"/>',
    info: '<circle cx="12" cy="12" r="8.2"/><path d="M12 11v5.2M12 7.8v.1"/>',
    spark: '<path d="M12 3.5l1.9 5.6 5.6 1.9-5.6 1.9-1.9 5.6-1.9-5.6-5.6-1.9 5.6-1.9z"/>',
    plus: '<path d="M12 5.5v13M5.5 12h13"/>',
    note: '<path d="M5.5 5.5h13v9l-4 4h-9z"/><path d="M14.5 18.5v-4h4"/>',
    // a trace that stumbles, bursts and falls quiet: the seizure story
    sextant: '<path d="M4 19.5L12 4.5l8 15"/><path d="M6.4 15.2a9 9 0 0 1 11.2 0"/><circle cx="12" cy="4.5" r="1.2" fill="currentColor" stroke="none"/><path d="M12 4.5l3.2 11.4"/>',
    burst: '<path d="M2.5 13h2.4l1-1.6 1 3 1.2-4.6 1.4 7.2 1.6-10.4 1.6 12.4 1.6-11 1.4 7.6 1.1-3.8.9 1.2h2.3"/>',
  };
  function icon(name, size) {
    const s = document.createElementNS(NS, 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('class', 'sh-ico');
    s.setAttribute('aria-hidden', 'true');
    s.setAttribute('focusable', 'false');
    if (size) { s.setAttribute('width', size); s.setAttribute('height', size); }
    s.innerHTML = PATHS[name] || '';
    return s;
  }

  /* A named-state switch. opts: [[value, words, title?], ...]. The press
     shows at once (the control owns its look); on(value) does the work. */
  function seg(label, opts, cur, on, o) {
    o = o || {};
    const g = el('div', { class: 'seg sh-seg' + (o.small ? ' sm' : ''), role: 'group', 'aria-label': label || o.aria || '' });
    opts.forEach(([v, words, tip]) => {
      const b = el('button', { type: 'button', class: v === cur ? 'active' : '', title: tip || '', 'aria-pressed': String(v === cur) }, [words]);
      b._v = v;
      b.addEventListener('click', () => {
        if (b.classList.contains('active')) return;
        setSeg(g, v);
        on(v);
      });
      g.appendChild(b);
    });
    if (!label) return g;
    return el('div', { class: 'sh-field' + (o.stack ? ' stack' : '') }, [el('span', { class: 'sh-field-k', text: label }), g]);
  }
  function setSeg(g, v) {
    if (!g) return;
    const group = g.classList.contains('seg') ? g : g.querySelector('.seg');
    if (!group) return;
    group.querySelectorAll(':scope > button').forEach((b) => {
      const on = b._v === v;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', String(on));
    });
  }

  /* A slider with its value in words beside it. Moves are coalesced to one
     per frame; o.done(v) fires when the hand lets go. */
  function range(o) {
    const num = el('output', { class: 'sh-range-v', text: o.fmt(o.value) });
    const input = el('input', { type: 'range', min: o.min, max: o.max, step: o.step || 1, value: o.value, 'aria-label': o.aria || o.label || '' });
    let pend = 0;
    input.addEventListener('input', () => {
      const v = +input.value;
      num.textContent = o.fmt(v);
      paint();
      if (pend) cancelAnimationFrame(pend);
      pend = requestAnimationFrame(() => { pend = 0; o.on(v); });
    });
    if (o.done) input.addEventListener('change', () => o.done(+input.value));
    // the filled part of the track, so the slider reads like a gauge
    const paint = () => {
      const f = (+input.value - +o.min) / Math.max(1e-9, +o.max - +o.min);
      input.style.setProperty('--f', (f * 100).toFixed(2) + '%');
    };
    paint();
    const box = el('label', { class: 'sh-range' + (o.wide ? ' wide' : '') }, [
      o.label ? el('span', { class: 'sh-field-k', text: o.label }) : null, input, num]);
    box.set = (v) => { if (document.activeElement === input) return; input.value = v; num.textContent = o.fmt(+v); paint(); };
    box.input = input;
    return box;
  }

  /* A text button, optionally with an icon before the words. */
  function button(o) {
    const b = el('button', { type: 'button', class: 'sh-btn' + (o.kind ? ' ' + o.kind : '') + (o.cls ? ' ' + o.cls : ''), title: o.title || '',
      'aria-label': o.aria || null, 'aria-pressed': o.pressed == null ? null : String(!!o.pressed), disabled: o.disabled ? 'disabled' : null });
    if (o.icon) b.appendChild(icon(o.icon));
    if (o.text) b.appendChild(el('span', { text: o.text }));
    if (o.onclick) b.addEventListener('click', o.onclick);
    return b;
  }

  /* ---------------------------------------------------------- floating */
  let open = null;
  function closeAll() { if (open) { const o = open; open = null; o.close(); } }
  function place(box, anchor, where) {
    const r = anchor.getBoundingClientRect();
    const W = window.innerWidth, H = window.innerHeight;
    const bw = box.offsetWidth, bh = box.offsetHeight;
    let x = where.endsWith('end') ? r.right - bw : where.endsWith('center') ? r.left + r.width / 2 - bw / 2 : r.left;
    let y = where.startsWith('above') ? r.top - bh - 8 : r.bottom + 8;
    if (where.startsWith('above') && y < 8) y = r.bottom + 8;
    if (!where.startsWith('above') && y + bh > H - 8) y = Math.max(8, r.top - bh - 8);
    x = Math.max(8, Math.min(W - bw - 8, x));
    box.style.left = Math.round(x) + 'px';
    box.style.top = Math.round(y) + 'px';
    box.dataset.side = y < r.top ? 'above' : 'below';
  }
  function float(anchor, box, o) {
    closeAll();
    document.body.appendChild(box);
    place(box, anchor, o.where || 'below-start');
    anchor.setAttribute('aria-expanded', 'true');
    anchor.classList.add('open');
    const away = (e) => { if (!box.contains(e.target) && !anchor.contains(e.target)) closeAll(); };
    const key = (e) => { if (e.key === 'Escape') { e.stopPropagation(); closeAll(); anchor.focus(); } };
    const re = () => { if (anchor.isConnected) place(box, anchor, o.where || 'below-start'); else closeAll(); };
    const me = {
      box,
      close() {
        document.removeEventListener('pointerdown', away, true);
        document.removeEventListener('keydown', key, true);
        window.removeEventListener('resize', re);
        anchor.setAttribute('aria-expanded', 'false');
        anchor.classList.remove('open');
        box.classList.add('leaving');
        setTimeout(() => box.remove(), 140);
        if (o.onclose) o.onclose();
      },
      replace: re,
    };
    setTimeout(() => document.addEventListener('pointerdown', away, true), 0);
    document.addEventListener('keydown', key, true);
    window.addEventListener('resize', re);
    open = me;
    return me;
  }
  /* sections: [{title?, items: [{label, sub?, icon?, swatch?, tag?, active?, disabled?, on()}]}] */
  function menu(anchor, sections, o) {
    o = o || {};
    if (open && open.anchor === anchor) { closeAll(); return null; }
    const box = el('div', { class: 'sh-pop sh-menu' + (o.cls ? ' ' + o.cls : ''), role: 'menu' });
    if (o.width) box.style.width = o.width + 'px';
    const items = [];
    sections.forEach((sec) => {
      if (!sec || !sec.items || !sec.items.length) return;
      if (sec.title) box.appendChild(el('div', { class: 'sh-menu-k', text: sec.title }));
      sec.items.forEach((it) => {
        const b = el('button', { type: 'button', class: 'sh-menu-item' + (it.active ? ' active' : ''), role: 'menuitem', tabindex: '-1',
          disabled: it.disabled ? 'disabled' : null, 'aria-current': it.active ? 'true' : null });
        const lead = it.swatch ? el('span', { class: 'sh-sw', style: 'background:' + it.swatch }) : it.icon ? icon(it.icon) : el('span', { class: 'sh-menu-dot' });
        b.appendChild(el('span', { class: 'sh-menu-lead' }, [lead]));
        b.appendChild(el('span', { class: 'sh-menu-words' }, [el('b', { text: it.label }), it.sub ? el('small', { text: it.sub }) : null]));
        if (it.tag) b.appendChild(el('span', { class: 'sh-menu-tag', text: it.tag }));
        b.addEventListener('click', () => { closeAll(); it.on && it.on(); });
        box.appendChild(b);
        items.push(b);
      });
    });
    const me = float(anchor, box, { where: o.where || 'below-start' });
    me.anchor = anchor;
    let at = -1;
    const focusAt = (i) => { at = (i + items.length) % items.length; items[at].focus(); };
    box.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); focusAt(at + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); focusAt(at - 1); }
      else if (e.key === 'Home') { e.preventDefault(); focusAt(0); }
      else if (e.key === 'End') { e.preventDefault(); focusAt(items.length - 1); }
    });
    if (o.keyboard && items.length) focusAt(Math.max(0, items.findIndex((b) => b.classList.contains('active'))));
    return me;
  }
  /* A floating panel; build(box) fills it and may be called again (refresh). */
  function sheet(anchor, build, o) {
    o = o || {};
    if (open && open.anchor === anchor) { closeAll(); return null; }
    const box = el('div', { class: 'sh-pop sh-sheet' + (o.cls ? ' ' + o.cls : ''), role: 'dialog', 'aria-label': o.aria || '' });
    if (o.width) box.style.width = o.width + 'px';
    build(box);
    const me = float(anchor, box, { where: o.where || 'below-end', onclose: o.onclose });
    me.anchor = anchor;
    me.refresh = () => { box.innerHTML = ''; build(box); me.replace(); };
    return me;
  }
  const current = () => open;

  return { icon, seg, setSeg, range, button, menu, sheet, closeAll, current };
})();
