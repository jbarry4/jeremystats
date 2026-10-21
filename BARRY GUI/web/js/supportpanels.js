/* ==========================================================================
   supportpanels.js -- which support panels each add-on pops up, and how
   they are arranged (2026-10-20).

   "In the profile have a section called support panel preferences, where
   people can choose what support panels they'd like to have pop up in what
   arrangement for each Xplorefinder add-on."

   Every add-on that opens a second window of panels -- Checkup, Spotter,
   Panning, StrataScope, Braid -- asks `plan(mode, defaults)` for what to
   open instead of hard-coding it. With nothing chosen, the add-on's own
   defaults stand, exactly as before. A choice is kept in preferences
   (`support_panels`), per add-on: whether the window opens at all, which
   panels in which order, and their arrangement.

     plan(mode, defaults)   { specs, shape } to open, or null (turned off).
                            `defaults` are the add-on's own specs; a chosen
                            panel that is one of them keeps its settings
                            (a spectrogram's channels and band, say).
     section()              the Profile's "Support panel preferences".
   ========================================================================== */
'use strict';

BARRY.supportPanels = (function () {
  const KEY = 'support_panels';

  /* The add-ons with a support window, their defaults as the add-ons
     themselves open them, and the shape those defaults had. */
  const ADDONS = [
    { mode: 'curate', name: 'Checkup', panels: ['csd'], shape: null },
    { mode: 'spotter', name: 'Spotter',
      panels: ['csd', 'voltage', 'spectrogram'], shape: 'cols' },
    { mode: 'panning', name: 'Panning',
      panels: ['csd', 'voltage', 'spectrogram'], shape: 'cols' },
    { mode: 'strata', name: 'StrataScope',
      panels: ['csd', 'theta', 'voltage', 'spectrogram'], shape: 'linked' },
    { mode: 'cfc', name: 'Braid', panels: ['bandpower', 'spectrogram'],
      shape: 'cols' },
  ];

  /* The panels a support window can show: Xplorefinder's own list when it
     has loaded, else the ones the add-ons use. */
  const FALLBACK = [
    { id: 'csd', name: 'CSD' }, { id: 'theta', name: 'Theta' },
    { id: 'voltage', name: 'Voltage raster' },
    { id: 'spectrogram', name: 'Spectrogram' },
    { id: 'bandpower', name: 'Band power' },
    { id: 'traces', name: 'Voltage traces' },
  ];
  function catalog() {
    const xp = BARRY.views && BARRY.views.xplore;
    const defs = (xp && xp.state && xp.state.panelDefs) || [];
    return defs.length ? defs.map((d) => ({ id: d.id, name: d.name }))
                       : FALLBACK;
  }
  const nameOf = (id) => (catalog().find((p) => p.id === id)
                          || FALLBACK.find((p) => p.id === id) || {}).name || id;

  /* How n panes can be arranged (xplore.js layoutOf knows each). */
  function shapesFor(n) {
    if (n === 2) return [['cols', 'Side by side'], ['rows', 'Stacked']];
    if (n === 3) {
      return [['cols', 'Three across'], ['rows', 'Stacked'],
              ['top1', 'One large on top'], ['top2', 'One large below']];
    }
    if (n === 4) {
      return [['linked', 'Two by two'], ['rows', 'Stacked'],
              ['cols', 'Four across']];
    }
    return [];
  }

  function all() {
    try {
      const got = BARRY.prefs.get(KEY, {});
      return (got && typeof got === 'object') ? got : {};
    } catch (e) { return {}; }
  }

  function addon(mode) { return ADDONS.find((a) => a.mode === mode) || null; }

  /* What this person chose for an add-on, filled in from its defaults. */
  function choice(mode) {
    const a = addon(mode) || { panels: [], shape: null };
    const c = all()[mode] || {};
    const panels = Array.isArray(c.panels) && c.panels.length
      ? c.panels.slice(0, 4) : a.panels.slice();
    const shapes = shapesFor(panels.length).map((s) => s[0]);
    return {
      open: c.open !== false,
      panels,
      shape: shapes.includes(c.shape) ? c.shape
        : (shapes.includes(a.shape) ? a.shape : (shapes[0] || null)),
      custom: !!all()[mode],
    };
  }

  function save(mode, c) {
    const every = Object.assign({}, all());
    if (c === null) delete every[mode];
    else every[mode] = { open: c.open, panels: c.panels, shape: c.shape };
    try { BARRY.prefs.set(KEY, every); } catch (e) { /* this session only */ }
  }

  function plan(mode, defaults) {
    const c = choice(mode);
    if (!c.open) return null;
    const byId = {};
    for (const d of defaults || []) if (d && !byId[d.panel]) byId[d.panel] = d;
    const specs = c.panels.map((id) => Object.assign({}, byId[id]
      || (id === 'spectrogram' ? { panel: id, fmin: 1, fmax: 250 }
                               : { panel: id })));
    return specs.length ? { specs, shape: c.shape } : null;
  }

  /* ---------- the Profile's section ---------- */

  function row(a, host) {
    const c = choice(a.mode);
    const set = (patch) => {
      const next = Object.assign({}, c, patch);
      const shapes = shapesFor(next.panels.length).map((s) => s[0]);
      if (!shapes.includes(next.shape)) next.shape = shapes[0] || null;
      save(a.mode, next);
      paint(host);
    };
    const chips = el('div', { class: 'spp-chips' }, c.panels.map((id, i) =>
      el('span', { class: 'spp-chip' }, [
        el('span', { text: (i + 1) + '. ' + nameOf(id) }),
        i > 0 ? el('button', { class: 'mini', text: '↑',
          title: 'Earlier in the window',
          onclick: () => {
            const p = c.panels.slice();
            [p[i - 1], p[i]] = [p[i], p[i - 1]];
            set({ panels: p });
          } }) : null,
        c.panels.length > 1 ? el('button', { class: 'mini', text: '×',
          title: 'Take ' + nameOf(id) + ' out of this window',
          onclick: () => set({ panels: c.panels.filter((x, j) => j !== i) }),
        }) : null,
      ].filter(Boolean))));
    const addable = catalog().filter((p) => !c.panels.includes(p.id));
    const add = c.panels.length < 4 && addable.length ? el('select', {
      class: 'spp-add', title: 'Add a panel to this window (up to four)',
      onchange: (e) => {
        if (e.target.value) set({ panels: c.panels.concat([e.target.value]) });
      },
    }, [el('option', { value: '', text: '+ Add a panel' })]
      .concat(addable.map((p) => el('option', { value: p.id, text: p.name }))))
      : null;
    const shapes = shapesFor(c.panels.length);
    return el('div', { class: 'spp-row' + (c.open ? '' : ' off') }, [
      el('div', { class: 'spp-head' }, [
        el('strong', { text: a.name }),
        BARRY.ui.seg([['on', 'Opens'], ['off', 'Does not open']],
          c.open ? 'on' : 'off', (v) => set({ open: v === 'on' })),
        c.custom ? el('button', { class: 'linkish', text: 'Back to its defaults',
          onclick: () => { save(a.mode, null); paint(host); } }) : null,
      ].filter(Boolean)),
      c.open ? chips : null,
      c.open ? el('div', { class: 'spp-tools' }, [
        add,
        shapes.length > 1 ? BARRY.ui.seg(shapes, c.shape,
          (v) => set({ shape: v }), { extra: 'sm' }) : null,
      ].filter(Boolean)) : null,
    ].filter(Boolean));
  }

  function paint(host) {
    host.innerHTML = '';
    for (const a of ADDONS) host.appendChild(row(a, host));
  }

  function section() {
    const list = el('div', { class: 'spp-list' });
    const wrap = el('details', { class: 'spp' }, [
      el('summary', { class: 'section-label', text: 'Support panel preferences' }),
      el('p', { class: 'hint', text: 'The second window each add-on opens: '
          + 'whether it opens, which panels it holds (up to four), in what '
          + 'order and arrangement. Saved as you change it; it applies the '
          + 'next time the add-on opens.' }),
      list,
    ]);
    paint(list);
    return wrap;
  }

  return { plan, choice, section, ADDONS };
})();
