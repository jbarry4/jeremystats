/* ==========================================================================
   joe_export.js -- everything that goes to Joe, as one page: the Monolith's
   tab 10 shows it, and Joe's own site (review/joe_site) is it
   (Shahriar, 2026-10-26).

   JOE_EXPORT.render(root, manifest, opts) draws backend/joeexport.py's
   manifest into root. opts.url(name) is where a file is fetched from (the
   Jarvis route, or files/<name> on the site); opts.top is anything to put
   above the list (tab 10's build card). No dependency on the Monolith's
   own helpers, so the site needs nothing else; "Download everything"
   fetches JSZip from cdnjs only when pressed.
   ========================================================================== */
'use strict';

window.JOE_EXPORT = (function () {
  const JSZIP = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
  const STYLE = `
.jx { --jx-gap: 16px; color: var(--ink); font: 15px/1.55 var(--sans, system-ui, sans-serif); }
.jx h2 { font-size: 19px; margin: 0 0 4px; }
.jx h3 { font-size: 16px; margin: 22px 0 8px; }
.jx p { margin: 0 0 10px; }
.jx .jx-muted { color: var(--ink-3); font-size: 13.5px; }
.jx .jx-card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r, 8px); padding: 16px 18px; margin-bottom: var(--jx-gap); }
.jx .jx-head { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: flex-end; justify-content: space-between; }
.jx .jx-big { font-size: 24px; font-weight: 650; line-height: 1.2; margin: 0 0 6px; }
.jx .jx-btn { font: inherit; font-size: 14px; padding: 7px 14px; border-radius: 6px; border: 1px solid var(--line-2); background: var(--surface);
  color: var(--ink); cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
.jx .jx-btn.jx-main { background: var(--ink); color: var(--surface); border-color: var(--ink); }
.jx .jx-btn:disabled { opacity: .55; cursor: default; }
.jx .jx-btn:focus-visible, .jx a:focus-visible, .jx summary:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.jx ul.jx-read { margin: 6px 0 0; padding-left: 20px; }
.jx ul.jx-read li { margin-bottom: 6px; }
.jx .jx-files { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.jx .jx-file { display: inline-flex; flex-direction: column; padding: 7px 12px; border: 1px solid var(--line-2); border-radius: 6px;
  color: var(--ink); text-decoration: none; background: var(--surface-2, var(--surface)); min-width: 0; }
.jx .jx-file:hover { border-color: var(--ink-3); }
.jx .jx-file b { font-weight: 600; font-size: 14px; overflow-wrap: anywhere; }
.jx .jx-file span { font-size: 12.5px; color: var(--ink-3); overflow-wrap: anywhere; }
.jx .jx-file { max-width: 100%; box-sizing: border-box; }
.jx .jx-nav { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 0; }
.jx .jx-nav a { font-size: 13px; padding: 3px 10px; border-radius: 999px; background: var(--chip); color: var(--ink); text-decoration: none; }
.jx .jx-fig { display: grid; grid-template-columns: minmax(0, 220px) minmax(0, 1fr); gap: 16px; padding: 14px 0; border-top: 1px solid var(--line); }
.jx .jx-fig:first-of-type { border-top: 0; }
.jx .jx-thumb { display: block; background: #fff; border: 1px solid var(--line); border-radius: 6px; padding: 6px; }
.jx .jx-thumb img { display: block; width: 100%; height: auto; }
.jx .jx-figname { font-weight: 650; }
.jx .jx-tests { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 6px 0; font-size: 13.5px; }
.jx .jx-test { display: inline-flex; align-items: center; gap: 6px; }
.jx .jx-dot { width: 11px; height: 11px; border-radius: 50%; border: 1.5px solid var(--ink-3); flex: none; }
.jx .jx-dot.on { background: var(--jlit, #0072B2); border-color: var(--jlit, #0072B2); }
.jx .jx-views { display: inline-flex; border: 1px solid var(--line-2); border-radius: 6px; overflow: hidden; margin: 4px 0 6px; flex-wrap: wrap; }
.jx .jx-views button { font: inherit; font-size: 13px; padding: 4px 10px; border: 0; background: var(--surface); color: var(--ink); cursor: pointer; }
.jx .jx-views button[aria-pressed="true"] { background: var(--ink); color: var(--surface); }
.jx details { margin: 6px 0; }
.jx summary { cursor: pointer; font-size: 14px; color: var(--ink-2); }
.jx .jx-legend { font-size: 13.5px; color: var(--ink-2); margin-top: 6px; }
.jx table.jx-lights { border-collapse: collapse; font-size: 13.5px; width: 100%; margin-top: 8px; }
.jx table.jx-lights th, .jx table.jx-lights td { padding: 5px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
.jx table.jx-lights td.jx-l { white-space: nowrap; }
.jx .jx-light { display: inline-block; width: 12px; height: 12px; border-radius: 50%; border: 1.5px solid var(--ink-3); vertical-align: -1px; margin-right: 6px; }
.jx .jx-light.on { background: var(--jlit, #0072B2); border-color: var(--jlit, #0072B2); }
.jx .jx-light.on.chk { background: var(--jcheck, #D55E00); border-color: var(--jcheck, #D55E00); border-radius: 2px; transform: rotate(45deg) scale(.85); }
.jx .jx-status { font-size: 13.5px; color: var(--ink-2); min-height: 1.3em; margin-top: 6px; }
.jx .jx-gsay { font-size: 13.5px; color: var(--ink-3); margin: -4px 0 6px; }
.jx .jx-switch { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; margin: 10px 0 2px; }
.jx .jx-methods details { border-top: 1px solid var(--line); padding: 6px 0; }
.jx .jx-methods summary { font-weight: 600; color: var(--ink); }
.jx .jx-methods p { font-size: 14px; max-width: 95ch; overflow-wrap: anywhere; margin: 6px 0; }
.jx .jx-flag { border-left: 4px solid var(--jcheck, #D55E00); background: color-mix(in srgb, var(--jcheck, #D55E00) 9%, transparent);
  padding: 8px 12px; border-radius: 0 6px 6px 0; margin: 8px 0 10px; font-size: 14px; overflow-wrap: anywhere; }
.jx .jx-prose { font-family: Charter, "Bitstream Charter", "Sitka Text", Cambria, Georgia, serif; font-size: 16.5px; line-height: 1.62;
  color: var(--ink); max-width: 78ch; }
.jx .jx-prose p { margin: 0 0 10px; }
.jx .jx-block { border: 1px solid var(--line); border-radius: 6px; padding: 10px 14px 4px; margin: 10px 0; background: var(--surface-2, var(--surface)); }
.jx .jx-bhead { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 4px; }
.jx .jx-blabel { font-size: 12.5px; letter-spacing: .04em; text-transform: uppercase; color: var(--ink-3); font-weight: 600; }
.jx .jx-copy { font: inherit; font-size: 12.5px; padding: 2px 10px; border-radius: 5px; border: 1px solid var(--line-2); background: var(--surface);
  color: var(--ink-2); cursor: pointer; }
.jx .jx-pubfig { padding: 18px 0 8px; border-top: 1px solid var(--line); }
.jx .jx-pubfig:first-of-type { border-top: 0; }
.jx .jx-pubfig .jx-thumb { max-width: 920px; }
.jx .jx-figrow { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; margin-bottom: 8px; }
.jx .jx-badge { display: inline-block; font-size: 12.5px; font-weight: 600; padding: 2px 9px; border-radius: 999px; border: 1px solid var(--line-2);
  color: var(--ink-3); }
.jx .jx-badge.yes { background: var(--jlit, #0072B2); border-color: var(--jlit, #0072B2); color: #fff; }
.jx .jx-badge.near { border-color: var(--jcheck, #D55E00); color: var(--jcheck, #D55E00); }
.jx table.jx-tests { display: table; border-collapse: collapse; font-size: 13.5px; width: 100%; margin: 6px 0; }
.jx table.jx-tests th, .jx table.jx-tests td { padding: 4px 7px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
.jx table.jx-tests tr.yes td, .jx table.jx-tests tr.yes th { font-weight: 650; }
.jx table.jx-tests th { font-weight: 600; color: var(--ink-2); }
.jx .jx-tablewrap { overflow-x: auto; }
.jx .jx-passlist { margin: 6px 0 4px; padding-left: 20px; font-size: 14px; }
.jx .jx-passlist li { margin-bottom: 3px; }
.jx .jx-msec { margin: 0 0 14px; }
.jx [hidden] { display: none !important; }
.jx .jx-san-row { display: grid; grid-template-columns: 82px minmax(0, 1fr); gap: 4px 12px; padding: 8px 0; border-top: 1px solid var(--line); }
.jx .jx-san-row .jx-badge { justify-self: start; }
.jx .jx-badge.jx-san-ok { background: var(--jlit, #0072B2); border-color: var(--jlit, #0072B2); color: #fff; }
.jx .jx-badge.jx-san-warn { border-color: var(--jcheck, #D55E00); color: var(--jcheck, #D55E00); }
.jx .jx-badge.jx-san-fail { background: var(--jcheck, #D55E00); border-color: var(--jcheck, #D55E00); color: #fff; }
.jx .jx-flag.jx-san-green { border-left-color: var(--jlit, #0072B2); background: color-mix(in srgb, var(--jlit, #0072B2) 9%, transparent); }
.jx .jx-sanity code { overflow-wrap: anywhere; }
.jx .jx-msec h3 { margin: 18px 0 6px; }
.jx .jx-tabs { display: flex; flex-wrap: wrap; gap: 4px; margin: 14px 0 -17px; border-bottom: 1px solid var(--line); }
.jx .jx-tab { font: inherit; font-size: 15px; font-weight: 600; padding: 8px 16px; border: 1px solid transparent; border-bottom: 0;
  border-radius: 6px 6px 0 0; background: none; color: var(--ink-2); cursor: pointer; margin-bottom: -1px; }
.jx .jx-tab[aria-selected="true"] { background: var(--surface); border-color: var(--line); color: var(--ink); }
.jx .jx-tab:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.jx .jx-cv-step { display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: 2px 12px; padding: 10px 0; border-top: 1px solid var(--line); }
.jx .jx-cv-no { width: 24px; height: 24px; border-radius: 50%; background: var(--chip); font-size: 13px; font-weight: 650;
  display: flex; align-items: center; justify-content: center; }
.jx .jx-conduction table.jx-tests td, .jx .jx-conduction table.jx-tests th { white-space: nowrap; }
.jx .jx-cv-open { margin: 6px 0 0; padding-left: 20px; }
.jx .jx-cv-open li { margin-bottom: 6px; }
.jx .jx-subtabs { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 14px; }
.jx .jx-subtab { font: inherit; font-size: 13.5px; padding: 5px 12px; border-radius: 999px; border: 1px solid var(--line-2); background: var(--surface);
  color: var(--ink); cursor: pointer; }
.jx .jx-subtab[aria-selected="true"] { background: var(--ink); color: var(--surface); border-color: var(--ink); }
.jx .jx-subtab:focus-visible, .jx .jx-chip:focus-visible, .jx .jx-follow:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.jx .jx-chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 6px 0; }
.jx .jx-chip { font: inherit; font-size: 13px; padding: 3px 10px; border-radius: 999px; border: 1px solid var(--line-2); background: var(--surface);
  color: var(--ink-2); cursor: pointer; }
.jx .jx-chip[aria-pressed="true"] { background: var(--chip); color: var(--ink); border-color: var(--ink-3); font-weight: 600; }
.jx table.jx-tracker td, .jx table.jx-tracker th { vertical-align: top; }
.jx table.jx-tracker td.jx-nw { white-space: nowrap; }
.jx table.jx-tracker td.jx-tf a { font-size: 12.5px; overflow-wrap: anywhere; }
.jx table.jx-tracker td.jx-tf { min-width: 150px; max-width: 260px; }
.jx table.jx-tracker a { color: var(--ink); }
.jx .jx-st { display: inline-block; font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--line-2);
  color: var(--ink-3); white-space: nowrap; }
.jx .jx-st.done { background: var(--jlit, #0072B2); border-color: var(--jlit, #0072B2); color: #fff; }
.jx .jx-st.needs { border-color: var(--jcheck, #D55E00); color: var(--jcheck, #D55E00); }
.jx .jx-st.failed { background: var(--jcheck, #D55E00); border-color: var(--jcheck, #D55E00); color: #fff; }
.jx .jx-req { scroll-margin-top: 12px; }
.jx .jx-req h2 { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: baseline; }
.jx .jx-req ul { margin: 4px 0 8px; padding-left: 20px; }
.jx .jx-req li { margin-bottom: 4px; overflow-wrap: anywhere; }
.jx .jx-req .jx-tablewrap { margin: 4px 0 10px; }
.jx .jx-req table.jx-tests td { white-space: normal; min-width: 60px; }
.jx .jx-vc .jx-vc-p { font-size: 15.5px; line-height: 1.6; max-width: 78ch; }
.jx .jx-vc-check { padding: 14px 0 6px; border-top: 1px solid var(--line); margin-top: 12px; }
.jx .jx-vc-check .jx-thumb { max-width: 920px; margin: 6px 0 10px; }
.jx .jx-vc-read { max-width: 78ch; margin: 6px 0; }
.jx .jx-vc-read p { margin: 2px 0 0; font-size: 15px; line-height: 1.55; }
.jx .jx-vc-bottom p { margin: 6px 0 0; font-size: 15px; }
.jx details.jx-vc-numbers > summary { font-size: 15px; font-weight: 600; color: var(--ink); padding: 8px 0; }
.jx .jx-rfig { margin: 12px 0; }
.jx .jx-rfig .jx-thumb { max-width: 920px; }
.jx .jx-follow { font: inherit; font-size: 13.5px; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--line-2); background: var(--surface);
  color: var(--ink); cursor: pointer; display: inline-flex; gap: 8px; align-items: center; }
.jx .jx-follow[aria-pressed="true"] { background: var(--ink); color: var(--surface); border-color: var(--ink); }
.jx .jx-follow .jx-knob { width: 26px; height: 14px; border-radius: 7px; background: var(--line-2); position: relative; flex: none; }
.jx .jx-follow .jx-knob::after { content: ""; position: absolute; top: 2px; left: 2px; width: 10px; height: 10px; border-radius: 50%; background: var(--surface);
  transition: left .15s; }
.jx .jx-follow[aria-pressed="true"] .jx-knob { background: var(--jlit, #0072B2); }
.jx .jx-follow[aria-pressed="true"] .jx-knob::after { left: 14px; }
@media (prefers-reduced-motion: reduce) { .jx .jx-follow .jx-knob::after { transition: none; } }
@media (max-width: 640px) {
  .jx .jx-fig { grid-template-columns: minmax(0, 1fr); }
  .jx .jx-thumb { max-width: 320px; }
  .jx .jx-pubfig .jx-thumb { max-width: 100%; }
  .jx .jx-prose { font-size: 15.5px; }
  .jx .jx-tab { padding: 8px 7px; font-size: 13.5px; }
}`;

  function el(tag, attrs, kids) {
    const n = document.createElement(tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v;
      else if (k === 'on') for (const ev in v) n.addEventListener(ev, v[ev]);
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const c of [].concat(kids || [])) if (c != null) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    return n;
  }
  const mb = (b) => (b >= 1e6 ? (b / 1e6).toFixed(b >= 1e7 ? 0 : 1) + ' MB' : Math.max(1, Math.round(b / 1e3)) + ' kB');
  const pSay = (p) => (p == null ? '' : p < 0.001 ? 'P < 0.001' : 'P = ' + p.toFixed(3));
  const day = (s) => { try { return new Date(s).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }); } catch (e) { return s; } };

  function style() {
    if (document.getElementById('jx-style')) return;
    document.head.appendChild(el('style', { id: 'jx-style', text: STYLE }));
  }

  function fileLink(f, url) {
    if (!f) return null;
    return el('a', { class: 'jx-file', href: url(f.name), download: f.name }, [el('b', { text: f.say || f.name }), el('span', { text: f.name + ' · ' + mb(f.size) })]);
  }

  /* Every file of a part of the manifest, once each. */
  function filesOf(part) {
    const out = new Map();
    const take = (f) => { if (f && !out.has(f.name)) out.set(f.name, f); };
    (part.files || []).forEach(take);
    const fig = (fg) => {
      (fg.views || []).forEach((v) => v.files.forEach(take));
      ['files', 'files_raw', 'files_own', 'files_own_raw'].forEach((k) => (fg[k] || []).forEach(take));
      take(fg.prism);
    };
    for (const g of part.groups || []) g.figures.forEach(fig);
    for (const gs of Object.values(part.sets || {})) for (const g of gs) g.figures.forEach(fig);
    (part.figures || []).forEach(fig);
    ((part.prompt && part.prompt.files_all) || []).forEach(take);
    return Array.from(out.values());
  }

  let zipLib = null;
  function loadZip() {
    if (window.JSZip) return Promise.resolve(window.JSZip);
    if (!zipLib) {
      zipLib = new Promise((res, rej) => {
        const s = el('script', { src: JSZIP, crossorigin: 'anonymous' });
        s.onload = () => res(window.JSZip);
        s.onerror = () => { zipLib = null; rej(new Error('Could not load the zip library (no internet?)')); };
        document.head.appendChild(s);
      });
    }
    return zipLib;
  }

  /* One zip of many files, made in the browser: each file fetched, stored
     as it is (PDFs, PNGs and zips do not shrink further). */
  async function zipDown(files, folderOf, zipName, url, say, btn) {
    btn.disabled = true;
    try {
      const JSZip = await loadZip();
      const z = new JSZip();
      let got = 0;
      const total = files.reduce((s, f) => s + f.size, 0);
      for (const f of files) {
        say('Fetching ' + f.name + ' (' + mb(got) + ' of ' + mb(total) + ')');
        const r = await fetch(url(f.name), { credentials: 'same-origin' });
        if (!r.ok) throw new Error(f.name + ': HTTP ' + r.status);
        z.file((folderOf(f) ? folderOf(f) + '/' : '') + f.name, await r.arrayBuffer());
        got += f.size;
      }
      say('Packing ' + files.length + ' files');
      const blob = await z.generateAsync({ type: 'blob', compression: 'STORE' });
      const a = el('a', { href: URL.createObjectURL(blob), download: zipName });
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
      say('Saved ' + zipName + ' (' + files.length + ' files, ' + mb(blob.size) + ')');
    } catch (e) {
      say('Could not make the zip: ' + e.message);
    } finally {
      btn.disabled = false;
    }
  }

  /* The correction switch (2026-10-30): Dickson's way and Part 2 come drawn
     both ways, and one switch at the top picks which every figure shows. */
  const SW = { mode: 'fdr', figs: [], rs: 'all', setParts: [], only: false, after: [], axes: 'shared' };
  const passOn = (t) => (t.pass && typeof t.pass === 'object' ? !!t.pass[SW.mode] : !!t.pass);

  /* Only what is significant (2026-11-04): a figure of the publication set
     when its main test, or any test of a corrected family it stars (a pair's
     or region's own), passes under the switch; the same set as its part's
     list. One of the figures section's when it passes every one of its tests. */
  const sigPub = (fg) => !!(fg.sig && fg.sig[SW.mode]) || (fg.tests || []).some((t) => t.family && t.pass && t.pass[SW.mode]);
  const sigFig = (fg) => !!(fg.tests && fg.tests.length && fg.tests.every(passOn));
  const offHere = (fg) => !!(fg.show_in && fg.show_in[SW.mode] === false);

  /* Every figure, part, list and row again, after a switch. */
  function refresh() {
    SW.figs.forEach((n) => n.update());
    SW.setParts.forEach((d) => d());
    SW.after.forEach((f) => f());
  }

  /* Text Joe can paste: a labelled block of prose with a Copy button. */
  function prose(label, paras, cls) {
    const list = [].concat(paras || []).filter(Boolean);
    if (!list.length) return null;
    const btn = el('button', { type: 'button', class: 'jx-copy', text: 'Copy' });
    btn.addEventListener('click', async () => {
      const text = list.join('\n\n');
      try { await navigator.clipboard.writeText(text); btn.textContent = 'Copied'; } catch (e) { btn.textContent = 'Select and copy'; }
      setTimeout(() => { btn.textContent = 'Copy'; }, 1800);
    });
    return el('div', { class: 'jx-block' + (cls ? ' ' + cls : '') }, [
      el('div', { class: 'jx-bhead' }, [el('span', { class: 'jx-blabel', text: label }), btn]),
      el('div', { class: 'jx-prose' }, list.map((t) => el('p', { text: t })))]);
  }

  const qSay = (q) => (q == null ? 'not corrected' : q < 0.001 ? 'q < .001' : 'q = ' + q.toFixed(3).replace(/^0/, ''));
  const pAPA = (p) => (p == null ? '' : p < 0.001 ? 'p < .001' : 'p = ' + p.toFixed(3).replace(/^0/, ''));

  /* Every test behind a figure; the ones passing under the switch in bold. */
  function testsTable(fg) {
    const rows = (fg.tests || []).map((t) => {
      const yes = !!(t.pass && t.pass[SW.mode]);
      const verdict = t.pass && t.pass.fdr ? 'significant after FDR' : t.pass && t.pass.raw ? (t.corrected ? 'uncorrected only' : 'p < .05 (not corrected)') : 'not significant';
      const rb = t.robust;
      const rob = rb ? (rb.verdict + ': leave-one-out ' + (rb.loo === 'holds' ? 'holds' : 'fails without J' + rb.worst_rat) + (rb.lmm ? '; mixed model ' + rb.lmm : ''))
        : t.lmm ? 'mixed model ' + t.lmm : '';
      return el('tr', { class: yes ? 'yes' : '' }, [el('th', { text: t.name + (t.primary ? '' : '') }), el('td', { text: t.effect || '' }),
        el('td', { text: t.stat + (t.errors === 'model-based' ? ' (model-based)' : '') }), el('td', { text: qSay(t.q) }),
        el('td', { text: verdict }), el('td', { text: rob })]);
    });
    if (!rows.length) return null;
    return el('details', { class: 'jx-testsd' }, [el('summary', { text: 'Every test behind this figure (' + rows.length + ')' }),
      el('div', { class: 'jx-tablewrap' }, el('table', { class: 'jx-tests' }, [
        el('thead', {}, el('tr', {}, ['Test', 'Effect', 'Statistic', 'FDR', 'Verdict', 'Robustness'].map((h) => el('th', { text: h })))),
        el('tbody', {}, rows)]))]);
  }

  /* How well a figure's passing results held up: the best verdict of its
     primary tests that pass under the switch (solid, shaky, fragile). */
  function heldUp(fg) {
    const v = (fg.tests || []).filter((t) => t.primary && t.pass && t.pass[SW.mode] && t.robust).map((t) => t.robust.verdict);
    return v.includes('solid') ? 'holds without any one rat and in the mixed model' : v.includes('shaky') ? 'holds one of the two checks'
      : v.length ? 'does not hold without one rat or in the mixed model' : '';
  }

  /* A figure of the publication set: the drawing, its badge, its words.
     Since 2026-11-04 its stars follow the switch: the uncorrected drawing
     (and the caption that says so) where it differs from the corrected. */
  function pubFigure(fg, url, preview, sid) {
    const img = el('img', { alt: fg.name, loading: 'lazy' });
    const thumb = el('a', { class: 'jx-thumb', target: '_blank', rel: 'noopener', title: 'Open the PDF' }, [img]);
    const badge = el('span', { class: 'jx-badge' });
    const tbox = el('div', {});
    const cbox = el('div', {});
    const files = el('div', { class: 'jx-files' });
    const node = el('div', { class: 'jx-pubfig', id: 'jx-fig-' + sid + '-' + fg.id.replace(/\./g, '_') }, [
      el('div', { class: 'jx-figrow' }, [el('span', { class: 'jx-figname', text: fg.name }), badge]),
      thumb,
      cbox,
      prose('Results', fg.results),
      prose('Sensitivity analyses', fg.sensitivity),
      prose('Note for Joe', fg.reading),
      prose('Methods note', fg.note),
      tbox,
      files]);
    const draw = () => {
      // the drawing for both switches: axes fitted to it (where that differs), stars corrected or not (where that differs)
      const own = SW.axes === 'own' && !!fg.files_own;
      const raw = SW.mode === 'raw' && !!(own ? fg.files_own_raw : fg.files_raw);
      const fs = own ? (raw ? fg.files_own_raw : fg.files_own) : (raw ? fg.files_raw : (fg.files || []));
      const pv = own ? (raw ? fg.preview_own_raw : fg.preview_own) : (raw && fg.preview_raw ? fg.preview_raw : fg.preview);
      img.src = pv ? preview(pv) : '';
      const pdf = fs.find((f) => !/_statistics\.pdf$/.test(f.name));
      thumb.href = pdf ? url(pdf.name) : (pv ? preview(pv) : '#');
      const cap = SW.mode === 'raw' && fg.caption_raw ? fg.caption_raw : fg.caption;
      const ax = fg.axes_say ? fg.axes_say[SW.axes === 'own' && fg.files_own ? 'own' : 'shared'] : '';
      cbox.replaceChildren(...[prose('Caption', ax ? cap + ' ' + ax : cap)].filter(Boolean));
      files.replaceChildren(...fs.map((f) => fileLink(f, url)).concat(fg.prism ? [fileLink(fg.prism, url)] : []));
    };
    node.update = () => {
      draw();
      const s = fg.sig || {};
      const yes = !!s[SW.mode];
      const near = !yes && SW.mode === 'fdr' && !!s.raw;
      badge.className = 'jx-badge' + (yes ? ' yes' : near ? ' near' : '');
      const held = yes ? heldUp(fg) : '';
      badge.textContent = (yes ? (SW.mode === 'fdr' ? 'Significant after FDR' : 'Significant, p < .05 uncorrected')
        : near ? 'p < .05 uncorrected only' : 'Not significant') + (held ? '; ' + held : '');
      if (!(fg.tests || []).some((t) => t.primary)) badge.textContent = (fg.tests || []).some((t) => t.pass && t.pass[SW.mode]) ? 'Some tests significant' : 'No test significant';
      node.hidden = offHere(fg) || (SW.only && !sigPub(fg));
      tbox.replaceChildren(...[testsTable(fg)].filter(Boolean));
    };
    node.update();
    SW.figs.push(node);
    return node;
  }

  /* A part drawn for every set of rats: redrawn when the set changes. */
  function setPart(s, url, preview) {
    const box = el('div', {});
    const draw = () => {
      SW.figs = SW.figs.filter((n) => box.contains(n) === false);
      const groups = (s.sets || {})[SW.rs] || [];
      const sid = s.id + '-' + SW.rs;
      const passing = groups.flatMap((g) => g.figures).filter((fg) => sigPub(fg) && !offHere(fg));
      // with only what is significant, a group with none of it is not drawn at all
      const shown = SW.only ? groups.filter((g) => g.figures.some((fg) => sigPub(fg) && !offHere(fg))) : groups;
      const kids = [
        el('h3', { text: 'Significant ' + (SW.mode === 'fdr' ? 'after FDR correction' : 'at p < .05, uncorrected') + ' (' + passing.length + ')' }),
        passing.length ? el('ul', { class: 'jx-passlist' }, passing.map((fg) => el('li', {}, [
          el('a', { href: '#jx-fig-' + sid + '-' + fg.id.replace(/\./g, '_'), text: fg.name }), heldUp(fg) ? ': ' + heldUp(fg) : ''])))
          : el('p', { class: 'jx-muted', text: 'Nothing in this part passes on this side of the switch.' }),
        el('div', { class: 'jx-nav' }, shown.map((g) => el('a', { href: '#jx-g-' + sid + '-' + g.key, text: g.title })))];
      // every figure's statistics in this part and set, one zip
      const stats = groups.flatMap((g) => g.figures).map((fg) => fg.stats).filter(Boolean);
      if (stats.length) {
        const sb = el('button', { type: 'button', class: 'jx-btn', text: 'Download every statistics PDF (' + stats.length + ')' });
        const ss = el('div', { class: 'jx-status', role: 'status' });
        sb.addEventListener('click', () => zipDown(stats, () => '', 'Joe_' + s.id + '_' + SW.rs + '_statistics.zip', url, (t) => { ss.textContent = t; }, sb));
        kids.push(el('div', { class: 'jx-files' }, [sb]), ss);
      }
      for (const g of shown) {
        const gb = el('button', { type: 'button', class: 'jx-btn', text: 'Download this group' });
        const gs = el('div', { class: 'jx-status', role: 'status' });
        const gf = filesOf({ figures: g.figures });
        gb.addEventListener('click', () => zipDown(gf, () => '', 'Joe_' + s.id + '_' + SW.rs + '_' + g.key + '.zip', url, (t) => { gs.textContent = t; }, gb));
        kids.push(el('div', { id: 'jx-g-' + sid + '-' + g.key }, [
          el('div', { class: 'jx-head' }, [el('h3', { text: g.title }), gb]),
          g.say ? el('p', { class: 'jx-gsay', text: g.say }) : null, gs].concat(g.figures.map((fg) => pubFigure(fg, url, preview, sid)))));
      }
      box.replaceChildren(...kids);
    };
    draw();
    SW.setParts.push(draw);
    return box;
  }

  function tests(fg) {
    if (!fg.tests || !fg.tests.length) return null;
    return el('div', { class: 'jx-tests', 'aria-label': fg.tests.length > 1 ? 'Its three tests, FP first' : 'Its test' }, fg.tests.map((t) => el('span', { class: 'jx-test' }, [
      el('span', { class: 'jx-dot' + (passOn(t) ? ' on' : ''), 'aria-hidden': 'true' }),
      el('span', { text: t.say + (passOn(t) ? ': passes' : ': does not pass') })])));
  }

  function figure(fg, url, preview) {
    let vi = 0;
    const keyed = fg.views.some((v) => v.key);              // one view each side of the switch: the switch picks
    const img = el('img', { alt: fg.name, loading: 'lazy' });
    const thumb = el('a', { class: 'jx-thumb', target: '_blank', rel: 'noopener' }, [img]);
    const legend = el('div', { class: 'jx-legend' });
    const files = el('div', { class: 'jx-files' });
    const testBox = el('div', {});
    const vbtns = [];
    function show() {
      const v = fg.views[vi];
      if (v.preview) { img.src = preview(v.preview); thumb.href = preview(v.preview); }
      legend.replaceChildren(el('p', {}, [el('b', { text: v.legend.title || '' }), ' ', v.legend.body || '']));
      files.replaceChildren(...v.files.map((f) => fileLink(f, url)).concat(fg.prism ? [fileLink(fg.prism, url)] : []));
      testBox.replaceChildren(...[tests(fg)].filter(Boolean));
      vbtns.forEach((b, i) => b.setAttribute('aria-pressed', i === vi ? 'true' : 'false'));
    }
    const views = !keyed && fg.views.length > 1 ? el('div', { class: 'jx-views', role: 'group', 'aria-label': 'Which test the picture shows' },
      fg.views.map((v, i) => { const b = el('button', { type: 'button', text: v.say, on: { click: () => { vi = i; show(); } } }); vbtns.push(b); return b; }))
      : null;
    const node = el('div', { class: 'jx-fig', id: 'jx-fig-' + fg.id.replace('.', '_') }, [
      thumb,
      el('div', {}, [
        el('div', { class: 'jx-figname', text: fg.name }),
        el('div', { text: fg.title || '' }),
        testBox,
        views,
        el('details', {}, [el('summary', { text: 'Legend' }), legend]),
        files])]);
    node.update = () => {
      if (keyed) vi = Math.max(0, fg.views.findIndex((v) => v.key === SW.mode));
      node.hidden = offHere(fg) || (SW.only && !sigFig(fg));
      show();
    };
    node.update();
    SW.figs.push(node);
    return node;
  }

  function switchNode(M) {
    const rows = [];
    if (M.switch) {
      const btns = [];
      const set = (m) => {
        SW.mode = m;
        btns.forEach((b) => b.setAttribute('aria-pressed', b.dataset.mode === m ? 'true' : 'false'));
        refresh();                                          // every figure, and the lists of what passes
      };
      for (const m of ['fdr', 'raw']) {
        const b = el('button', { type: 'button', text: M.switch[m], 'data-mode': m, 'aria-pressed': m === SW.mode ? 'true' : 'false', on: { click: () => set(m) } });
        btns.push(b);
      }
      rows.push(el('div', { class: 'jx-switch' }, [el('span', { class: 'jx-muted', text: M.rat_sets ? 'What counts as significant:' : 'Dickson’s way and Part 2, stars and follow-ups:' }),
        el('div', { class: 'jx-views', role: 'group', 'aria-label': 'Correction for many tests' }, btns)]));
    }
    if (M.rat_sets && M.rat_sets.length > 1) {
      const rb = [];
      const setRs = (k) => {
        SW.rs = k;
        rb.forEach((b) => b.setAttribute('aria-pressed', b.dataset.rs === k ? 'true' : 'false'));
        refresh();
      };
      for (const s of M.rat_sets) {
        rb.push(el('button', { type: 'button', text: s.say, 'data-rs': s.key, 'aria-pressed': s.key === SW.rs ? 'true' : 'false', on: { click: () => setRs(s.key) } }));
      }
      rows.push(el('div', { class: 'jx-switch' }, [el('span', { class: 'jx-muted', text: 'Coherence, power and the follow-ups from:' }),
        el('div', { class: 'jx-views', role: 'group', 'aria-label': 'Which rats' }, rb)]));
      if (M.rat_why) rows.push(el('p', { class: 'jx-muted', text: M.rat_why }));
    }
    if (M.rat_sets) {
      // the axes (2026-11-04): one per kind of graph in the set of rats, or each graph fitted to itself
      const ab = [];
      const setAxes = (v) => {
        SW.axes = v;
        ab.forEach((b) => b.setAttribute('aria-pressed', b.dataset.axes === v ? 'true' : 'false'));
        refresh();
      };
      for (const [v, say] of [['shared', 'Shared by each kind of graph'], ['own', 'Fitted to each graph']]) {
        ab.push(el('button', { type: 'button', text: say, 'data-axes': v, 'aria-pressed': v === SW.axes ? 'true' : 'false', on: { click: () => setAxes(v) } }));
      }
      rows.push(el('div', { class: 'jx-switch' }, [el('span', { class: 'jx-muted', text: 'Axes:' }),
        el('div', { class: 'jx-views', role: 'group', 'aria-label': 'Axes shared by each kind of graph or fitted to each graph' }, ab)]),
        el('p', { class: 'jx-muted', text: 'Shared: every graph of a kind in this set of rats on one axis, so any two compare directly (an extreme '
          + 'value may be cut off, and its caption says so). Fitted: each graph on its own axis, every value shown.' }));
    }
    const ob = [];
    const why = el('p', { class: 'jx-muted', id: 'jx-onlysay', hidden: true,
      text: 'Showing only what is significant: in each part, the figures whose main test passes under the correction above (their badge says so); '
        + 'in the figures section, those that pass every one of their tests; in the statistics, the lit comparisons. The methods and the files stay.' });
    const setOnly = (v) => {
      SW.only = v;
      ob.forEach((b) => b.setAttribute('aria-pressed', (b.dataset.only === '1') === v ? 'true' : 'false'));
      why.hidden = !v;
      refresh();
    };
    for (const [v, say] of [[false, 'Everything'], [true, 'Only what is significant']]) {
      ob.push(el('button', { type: 'button', text: say, 'data-only': v ? '1' : '0', 'aria-pressed': v === SW.only ? 'true' : 'false', on: { click: () => setOnly(v) } }));
    }
    rows.push(el('div', { class: 'jx-switch' }, [el('span', { class: 'jx-muted', text: 'Show:' }),
      el('div', { class: 'jx-views', role: 'group', 'aria-label': 'Show everything or only what is significant' }, ob)]), why);
    return el('div', {}, rows);
  }

  function methods(list) {
    return el('div', { class: 'jx-methods' }, list.map((s) => el('details', { open: /Read first/.test(s.title) ? true : null }, [
      el('summary', { text: s.title }), ...s.paras.map((t) => el('p', { text: t }))])));
  }

  /* The methods for the dissertation: every section in full, each copyable. */
  function methodsProse(list) {
    const all = el('button', { type: 'button', class: 'jx-btn', text: 'Copy all the methods' });
    all.addEventListener('click', async () => {
      const text = list.map((s) => s.title + '\n\n' + s.paras.join('\n\n')).join('\n\n\n');
      try { await navigator.clipboard.writeText(text); all.textContent = 'Copied'; } catch (e) { all.textContent = 'Use the Word file'; }
      setTimeout(() => { all.textContent = 'Copy all the methods'; }, 1800);
    });
    return el('div', {}, [el('div', { class: 'jx-files' }, [all]),
      el('div', { class: 'jx-nav' }, list.map((s, i) => el('a', { href: '#jx-m-' + i, text: s.title })))]
      .concat(list.map((s, i) => el('div', { class: 'jx-msec', id: 'jx-m-' + i }, [el('h3', { text: s.title }), prose('Copy-ready text', s.paras)]))));
  }

  /* Tab 13's sanity check report (2026-11-04): the verdict, then each
     check with its status in words, what was found, and how it was checked
     behind a More; then how to make it all again. */
  const SAN = { ok: 'OK', warn: 'Check', fail: 'Problem', info: 'Note' };
  const SANV = { green: 'All clear', amber: 'Check these', red: 'Problems found' };
  function sanityPart(R) {
    const c = R.counts || {};
    const kids = [
      el('div', { class: 'jx-flag jx-san-' + (R.verdict || 'amber'), role: 'note' }, [el('b', { text: (SANV[R.verdict] || R.verdict) + '. ' }),
        R.say || '', ' (' + [['ok', 'OK'], ['warn', 'to check'], ['fail', 'problems'], ['info', 'notes']]
          .map(([k, w]) => (c[k] || 0) + ' ' + w).join(', ') + ')'])];
    for (const sec of R.sections || []) {
      kids.push(el('h3', { text: sec.title }));
      if (sec.say) kids.push(el('p', { class: 'jx-muted', text: sec.say }));
      for (const ck of sec.checks || []) {
        const more = [ck.how ? el('p', {}, [el('b', { text: 'How it was checked. ' }), ck.how]) : null]
          .concat((ck.detail || []).map((d) => el('p', { text: d })));
        if (ck.table && ck.table.rows && ck.table.rows.length) {
          more.push(el('div', { class: 'jx-tablewrap' }, el('table', { class: 'jx-tests' }, [
            el('thead', {}, el('tr', {}, ck.table.head.map((h) => el('th', { text: String(h) })))),
            el('tbody', {}, ck.table.rows.map((r) => el('tr', {}, r.map((x) => el('td', { text: String(x) })))))])));
        }
        kids.push(el('div', { class: 'jx-san-row' }, [
          el('span', { class: 'jx-badge jx-san-' + ck.status, text: SAN[ck.status] || ck.status }),
          el('div', {}, [el('div', { class: 'jx-figname', text: ck.title }), el('div', { text: ck.result || '' }),
            el('details', {}, [el('summary', { text: 'More' })].concat(more.filter(Boolean)))])]));
      }
    }
    if ((R.regenerate || []).length) {
      kids.push(el('h3', { text: 'Make it all again' }));
      kids.push(el('ol', { class: 'jx-read' }, R.regenerate.map((g) => el('li', {}, [g.step + ': ', el('code', { text: g.command })]))));
    }
    return el('div', { class: 'jx-sanity' }, kids);
  }

  /* How volume conduction was handled (backend/conduction.py, 2026-11-05):
     the problem in two paragraphs, then each step with what it found in one
     line and the rest behind a More, then what is still open. Tab 11 shows
     the same node through conductionNode. */
  function conductionPart(C) {
    const kids = (C.what || []).map((t) => el('p', { text: t }));
    (C.steps || []).forEach((s, i) => {
      const more = (s.more || []).map((t) => el('p', { text: t }));
      if (s.table && s.table.rows && s.table.rows.length) {
        more.push(el('div', { class: 'jx-tablewrap' }, el('table', { class: 'jx-tests' }, [
          el('thead', {}, el('tr', {}, s.table.head.map((h) => el('th', { text: String(h) })))),
          el('tbody', {}, s.table.rows.map((r) => el('tr', { class: r.some((x) => /marked/.test(String(x))) ? 'yes' : null },
            r.map((x) => el('td', { text: String(x) })))))])));
      }
      kids.push(el('div', { class: 'jx-cv-step', 'data-step': s.key }, [
        el('span', { class: 'jx-cv-no', 'aria-hidden': 'true', text: String(i + 1) }),
        el('div', {}, [el('div', { class: 'jx-figname', text: s.title }), el('div', { text: s.line || '' }),
          more.length ? el('details', {}, [el('summary', { text: 'More' })].concat(more)) : null])]));
    });
    if ((C.open || []).length) {
      kids.push(el('h3', { text: 'Still open' }));
      kids.push(el('ul', { class: 'jx-cv-open' }, C.open.map((t) => el('li', { text: t }))));
    }
    return el('div', { class: 'jx-conduction' }, kids);
  }
  function conductionNode(C) {
    style();
    return el('div', { class: 'jx' }, conductionPart(C));
  }

  /* Joe Prompt (2026-11-06): Joe's run sheet of 23 follow-ups, in parts.
     The overview is his summary table (filters by priority and status, a
     row per request, its files and one line of its result) and the
     Confirmations; each other part holds its requests' cards: what was run,
     what it found, its robustness lines, the run sheet's reading, its
     tables behind a More, its figures and its PDF and CSV. Volume
     conduction opens its part with the explainer the methods use. The
     Monolith's tab 14 draws the same node through promptNode. */
  const ST_CLASS = { 'Done': 'done', 'Needs decision': 'needs', 'Failed': 'failed' };
  const PART_KEY = 'jx.prompt.part';
  function tableNode(t, open) {
    return el('details', { open: open ? true : null }, [el('summary', { text: t.title }),
      el('div', { class: 'jx-tablewrap' }, el('table', { class: 'jx-tests' }, [
        el('thead', {}, el('tr', {}, t.head.map((h) => el('th', { text: String(h) })))),
        el('tbody', {}, t.rows.map((row, i) => el('tr', { class: t.bold && t.bold[i] ? 'yes' : null }, row.map((c) => el('td', { text: String(c) })))))])),
      t.note ? el('p', { class: 'jx-muted', text: t.note }) : null]);
  }
  /* Volume conduction in plain English (2026-11-06): what it is, then each
     check as a figure with how to read it and what it shows, a row per
     coherence change, and the bottom line. Figures are A2's, found by id. */
  function vcStory(S, A2, url, preview) {
    const figs = {};
    ((A2 && A2.figures) || []).forEach((f) => { figs[f.id] = f; });
    const kids = [el('h2', { text: S.title })].concat((S.what || []).map((t) => el('p', { class: 'jx-vc-p', text: t })));
    for (const c of S.checks || []) {
      const f = figs[c.fig];
      kids.push(el('div', { class: 'jx-vc-check', 'data-fig': c.fig || '' }, [
        el('h3', { text: c.title }),
        f ? el('a', { class: 'jx-thumb', href: f.pdf ? url(f.pdf.name) : '#', target: '_blank', rel: 'noopener', title: 'Open the PDF' },
          el('img', { alt: c.title, loading: 'lazy', src: f.preview ? preview(f.preview) : '' })) : null,
        el('div', { class: 'jx-vc-read' }, [el('span', { class: 'jx-blabel', text: 'How to read it' }), el('p', { text: c.read })]),
        el('div', { class: 'jx-vc-read' }, [el('span', { class: 'jx-blabel', text: 'What it shows' }), el('p', { text: c.shows })]),
        f && f.pdf ? el('div', { class: 'jx-files' }, [fileLink(f.pdf, url)]) : null]));
    }
    if (S.table) kids.push(el('h3', { text: S.table.title }), tableNode(S.table, true));
    if ((S.bottom || []).length) {
      kids.push(el('div', { class: 'jx-flag jx-vc-bottom', role: 'note' }, [el('b', { text: 'The bottom line' })]
        .concat(S.bottom.map((t) => el('p', { text: t })))));
    }
    return el('div', { class: 'jx-card jx-vc', id: 'jx-vc-story' }, kids);
  }
  function requestCard(r, url, preview, opts) {
    opts = opts || {};
    const files = [r.files && r.files.pdf, r.files && r.files.csv].filter(Boolean).map((f) => fileLink(f, url));
    const kids = [
      el('h2', {}, [r.id + '. ' + r.name, el('span', { class: 'jx-st ' + (ST_CLASS[r.status] || ''), text: r.status }),
        el('span', { class: 'jx-badge', text: r.priority })]),
      el('p', { class: 'jx-muted', text: [r.rats, r.n, r.date ? 'run ' + day(r.date + 'T12:00:00') : ''].filter(Boolean).join(' · ') }),
      el('p', {}, [el('b', { text: 'Decides. ' }), r.decides || ''])];
    if ((r.summary || []).length) kids.push(el('h3', { text: 'What it found' }), el('ul', {}, r.summary.map((s) => el('li', { text: s }))));
    if ((r.notes || []).length) kids.push(el('div', { class: 'jx-flag', role: 'note' }, r.notes.map((t) => el('p', { text: t }))));
    if ((r.reading || []).length) kids.push(el('p', { class: 'jx-gsay' }, [el('b', { text: 'Reading (from the run sheet). ' }), r.reading.join(' ')]));
    if ((r.robust || []).length) {
      kids.push(el('details', {}, [el('summary', { text: 'Robustness: leave-one-rat-out and the mixed model (' + r.robust.length + ')' }),
        el('ul', {}, r.robust.map((s) => el('li', { text: s })))]));
    }
    if (r.ran) kids.push(el('details', {}, [el('summary', { text: 'What was run' }), el('p', { text: r.ran }), r.source ? el('p', { class: 'jx-muted', text: 'From: ' + r.source }) : null]));
    if ((r.methods || []).length) kids.push(prose('Methods text, ready to use', r.methods));
    for (const f of opts.noFigs ? [] : r.figures || []) {
      const pdf = f.pdf;
      kids.push(el('div', { class: 'jx-rfig' }, [
        el('a', { class: 'jx-thumb', href: pdf ? url(pdf.name) : '#', target: '_blank', rel: 'noopener', title: 'Open the PDF' },
          el('img', { alt: f.caption || f.id, loading: 'lazy', src: f.preview ? preview(f.preview) : '' })),
        f.caption ? el('p', { class: 'jx-legend', text: f.caption }) : null,
        pdf ? el('div', { class: 'jx-files' }, [fileLink(pdf, url)]) : null]));
    }
    (r.tables || []).forEach((t, i) => kids.push(tableNode(t, i === 0 && (r.tables.length < 3))));
    if (files.length) kids.push(el('div', { class: 'jx-files' }, files));
    return el('div', { class: 'jx-card jx-req', id: 'jx-req-' + r.id, 'data-req': r.id }, kids);
  }
  function promptPart(P, url, preview) {
    const box = el('div', { class: 'jx-prompt' });
    const panels = {};
    const btns = [];
    let cur = 'overview';
    const setPart = (k, remember) => {
      if (!panels[k]) k = 'overview';
      cur = k;
      btns.forEach((b) => { const on = b.dataset.part === k; b.setAttribute('aria-selected', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1; });
      for (const p in panels) panels[p].hidden = p !== k;
      if (remember) { try { localStorage.setItem(PART_KEY, k); } catch (e) { /* none */ } }
    };
    const go = (r) => {
      setPart(r.part, true);
      // A2 is told by the volume-conduction walk-through; its numbers are folded under it
      const n = (r.id === 'A2' && box.querySelector('#jx-vc-story')) || box.querySelector('#jx-req-' + r.id);
      const fold = n && n.closest('details');
      if (fold) fold.open = true;
      if (n) n.scrollIntoView({ block: 'start' });
    };
    for (const p of P.parts) {
      panels[p.key] = el('div', { class: 'jx-ppanel', id: 'jx-part-' + p.key, role: 'tabpanel', 'aria-labelledby': 'jx-partbtn-' + p.key });
      btns.push(el('button', { type: 'button', role: 'tab', class: 'jx-subtab', id: 'jx-partbtn-' + p.key, 'data-part': p.key,
                               'aria-controls': 'jx-part-' + p.key, text: p.say, on: { click: () => setPart(p.key, true) } }));
    }
    const bar = el('div', { class: 'jx-subtabs', role: 'tablist', 'aria-label': 'Parts of Joe Prompt' }, btns);
    bar.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const i = P.parts.findIndex((p) => p.key === cur);
      const n = P.parts[(i + (e.key === 'ArrowRight' ? 1 : P.parts.length - 1)) % P.parts.length].key;
      setPart(n, true);
      btns.find((b) => b.dataset.part === n).focus();
    });
    const status = el('div', { class: 'jx-status', role: 'status' });
    const folderBtn = el('button', { type: 'button', class: 'jx-btn', text: 'Download the Aim 2 follow-up folder (' + (P.files_all || []).length + ' files)' });
    folderBtn.addEventListener('click', () => zipDown(P.files_all || [], () => 'Aim 2 follow-up', 'Aim 2 follow-up.zip', url, (t) => { status.textContent = t; }, folderBtn));
    box.appendChild(el('div', { class: 'jx-card' }, [
      el('div', { class: 'jx-head' }, [el('div', {}, [el('h2', { text: P.title }), el('p', { class: 'jx-muted', text: P.say })]), folderBtn]),
      status, bar]));
    for (const k in panels) box.appendChild(panels[k]);
    // the overview: the summary table, its filters, the confirmations
    const F = { pri: 'all', st: 'all' };
    const reqs = P.requests || [];
    const trs = reqs.map((r) => el('tr', { 'data-req': r.id }, [
      el('td', { class: 'jx-nw' }, el('a', { href: '#jx-req-' + r.id, text: r.id, on: { click: (e) => { e.preventDefault(); go(r); } } })),
      el('td', { text: r.name }), el('td', { class: 'jx-nw', text: r.priority }),
      el('td', {}, el('span', { class: 'jx-st ' + (ST_CLASS[r.status] || ''), text: r.status })),
      el('td', { class: 'jx-nw', text: r.date || '' }),
      el('td', { class: 'jx-tf' }, [r.files && r.files.pdf, r.files && r.files.csv].filter(Boolean).map((f) => el('div', {}, el('a', { href: url(f.name), download: f.name, text: f.name })))),
      el('td', { text: r.line || '' })]));
    const shown = el('p', { class: 'jx-muted' });
    const filter = () => {
      let n = 0;
      trs.forEach((tr, i) => {
        const r = reqs[i];
        tr.hidden = (F.pri !== 'all' && r.priority !== F.pri) || (F.st !== 'all' && r.status !== F.st);
        if (!tr.hidden) n += 1;
      });
      shown.textContent = 'Showing ' + n + ' of ' + reqs.length + ' requests.';
    };
    const chips = (label, key, opts) => {
      const bs = [];
      const set = (v) => { F[key] = v; bs.forEach((b) => b.setAttribute('aria-pressed', b.dataset.v === v ? 'true' : 'false')); filter(); };
      for (const [v, say] of [['all', 'All']].concat(opts.map((o) => [o, o]))) {
        bs.push(el('button', { type: 'button', class: 'jx-chip', 'data-v': v, 'aria-pressed': v === F[key] ? 'true' : 'false', text: say, on: { click: () => set(v) } }));
      }
      return el('div', { class: 'jx-chips', role: 'group', 'aria-label': label }, [el('span', { class: 'jx-muted', text: label + ':' })].concat(bs));
    };
    const ov = panels.overview;
    ov.appendChild(el('div', { class: 'jx-card', id: 'jx-prompt-tracker' }, [
      el('h2', { text: 'Summary table' }),
      chips('Priority', 'pri', P.priorities || ['P1', 'P2', 'P3']), chips('Status', 'st', P.statuses || []), shown,
      el('div', { class: 'jx-tablewrap' }, el('table', { class: 'jx-tests jx-tracker' }, [
        el('thead', {}, el('tr', {}, ['ID', 'Request', 'Priority', 'Status', 'Date run', 'Output files', 'Result'].map((h) => el('th', { text: h })))),
        el('tbody', {}, trs)]))]));
    filter();
    if ((P.confirmations || []).length) {
      ov.appendChild(el('div', { class: 'jx-card', id: 'jx-prompt-confirm' }, [el('h2', { text: 'Confirmations' }),
        el('p', { class: 'jx-muted', text: 'The run sheet’s Confirm items, answered from the data and the code before anything ran.' })]
        .concat(P.confirmations.map((c) => el('div', { class: 'jx-san-row' }, [el('span', { class: 'jx-badge', text: c.id }),
          el('div', {}, [el('div', { class: 'jx-figname', text: c.title }), el('div', { text: c.answer }), c.table ? tableNode(c.table, false) : null])])))));
    }
    // volume conduction: the plain-English walk-through first, A2's numbers folded under it
    const A2 = reqs.find((r) => r.id === 'A2');
    if (panels.vc && P.vc_story) panels.vc.appendChild(vcStory(P.vc_story, A2, url, preview));
    else if (panels.vc && P.conduction) {
      panels.vc.appendChild(el('div', { class: 'jx-card', id: 'jx-conduction' }, [el('h2', { text: 'Volume conduction: how it was handled' }),
        el('p', { class: 'jx-muted', text: P.conduction.say || '' }), conductionPart(P.conduction)]));
    }
    for (const r of reqs) {
      if (!panels[r.part]) continue;
      if (r.id === 'A2' && P.vc_story) {
        const card = requestCard(r, url, preview, { noFigs: true });
        panels.vc.appendChild(el('details', { class: 'jx-vc-numbers', id: 'jx-vc-numbers' }, [
          el('summary', { text: 'All the numbers behind this (request A2: every pair, both bands, every measure)' }), card]));
        continue;
      }
      panels[r.part].appendChild(requestCard(r, url, preview));
    }
    let first = 'overview';
    try { first = localStorage.getItem(PART_KEY) || first; } catch (e) { /* none */ }
    const h = /(?:^#|&)part=(\w+)/.exec(location.hash || '');
    setPart(h ? h[1] : first, false);
    return box;
  }
  function promptNode(P, opts) {
    style();
    opts = opts || {};
    const url = opts.url || ((n) => 'files/' + encodeURIComponent(n));
    return el('div', { class: 'jx' }, promptPart(P, url, opts.preview || url));
  }

  function lights(rows) {
    const cell = (r, b) => {
      const x = r.bands[b];
      return el('td', { class: 'jx-l' }, [el('span', { class: 'jx-light' + (x.lit ? ' on' : '') + (x.lit && r.check ? ' chk' : ''), 'aria-hidden': 'true' }),
        (x.lit ? 'lit, ' : '') + pSay(x.p)]);
    };
    const lit = (r) => r.bands.theta.lit || r.bands.gamma.lit;
    const trs = rows.map((r) => el('tr', {}, [el('td', { text: String(r.no) }), el('td', { text: r.title + (r.check ? ' (check)' : '') }),
      cell(r, 'theta'), cell(r, 'gamma')]));
    const none = el('p', { class: 'jx-muted', text: 'No comparison is lit.' });
    const update = () => {
      trs.forEach((tr, i) => { tr.hidden = SW.only && !lit(rows[i]); });
      none.hidden = !(SW.only && !rows.some(lit));
    };
    update();
    SW.after.push(update);
    return el('div', {}, [el('table', { class: 'jx-lights' }, [
      el('thead', {}, el('tr', {}, [el('th', { text: '#' }), el('th', { text: 'Comparison' }), el('th', { text: 'Theta' }), el('th', { text: 'Gamma' })])),
      el('tbody', {}, trs)]), none]);
  }

  const TABS = [['results', 'Results'], ['sanity', 'Sanity check'], ['wrap', 'Wrapping up'], ['prompt', 'Joe Prompt']];
  const TAB_OF = { sanity: 'sanity', conduction: 'wrap', methods: 'wrap', prompt: 'prompt' };
  const TAB_KEY = 'jx.tab';
  const FOLLOW_KEY = 'jx.followup';

  function render(root, M, opts) {
    style();
    opts = opts || {};
    const url = opts.url || ((n) => 'files/' + encodeURIComponent(n));
    const preview = opts.preview || url;
    root.replaceChildren();
    SW.figs = [];
    SW.setParts = [];
    SW.after = [];
    SW.only = false;
    SW.axes = 'shared';
    SW.rs = 'all';
    SW.mode = (M && M.switch && M.switch.default) || 'fdr';
    const wrap = el('div', { class: 'jx' });
    root.appendChild(wrap);
    if (!M || !M.ok) {
      wrap.appendChild(el('div', { class: 'jx-card' }, el('p', { text: (M && M.error) || 'Nothing to show yet.' })));
      return;
    }
    if (opts.top) wrap.appendChild(opts.top);
    const all = filesOf({ files: M.sections.flatMap((s) => filesOf(s)) });
    const status = el('div', { class: 'jx-status', role: 'status' });
    const say = (t) => { status.textContent = t; };
    const allBtn = el('button', { type: 'button', class: 'jx-btn jx-main', text: 'Download everything (' + all.length + ' files, ' + mb(M.bytes) + ')' });
    const folder = new Map();
    for (const s of M.sections) for (const f of filesOf(s)) folder.set(f.name, s.title);
    allBtn.addEventListener('click', () => zipDown(all, (f) => folder.get(f.name), 'Joe_export_' + (M.made || '').slice(0, 10) + '.zip', url, say, allBtn));
    // three tabs (2026-11-05): Results, Sanity check, Wrapping up (volume
    // conduction and the methods for the dissertation)
    const panels = {};
    const tabBtns = [];
    const tabOf = (s) => s.tab || TAB_OF[s.id] || 'results';
    const tabs = TABS.filter(([k]) => k === 'results' || M.sections.some((s) => tabOf(s) === k));
    // Follow-up only (2026-11-06, Joe's prompt 1): shows Joe Prompt alone,
    // off by default, remembered in this browser
    let follow = false;
    try { follow = localStorage.getItem(FOLLOW_KEY) === '1'; } catch (e) { /* none */ }
    const setTab = (k, remember) => {
      if (!panels[k]) k = 'results';
      if (follow && panels.prompt) k = 'prompt';
      SW.tab = k;
      tabBtns.forEach((b) => { const on = b.dataset.tab === k; b.setAttribute('aria-selected', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1; });
      for (const t in panels) panels[t].hidden = t !== k;
      if (remember) { try { localStorage.setItem(TAB_KEY, k); } catch (e) { /* none */ } }
    };
    for (const [k, say] of tabs) {
      panels[k] = el('div', { class: 'jx-panel', id: 'jx-tab-' + k, role: 'tabpanel', 'aria-labelledby': 'jx-tabbtn-' + k });
      tabBtns.push(el('button', { type: 'button', role: 'tab', class: 'jx-tab', id: 'jx-tabbtn-' + k, 'data-tab': k, 'aria-controls': 'jx-tab-' + k,
                                  text: say, on: { click: () => setTab(k, true) } }));
    }
    const tabBar = el('div', { class: 'jx-tabs', role: 'tablist', 'aria-label': 'Parts of this page' }, tabBtns);
    tabBar.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const vis = tabs.filter(([k]) => !follow || k === 'prompt');
      const i = vis.findIndex(([k]) => k === SW.tab);
      const n = vis[(i + (e.key === 'ArrowRight' ? 1 : vis.length - 1)) % vis.length][0];
      setTab(n, true);
      tabBtns.find((b) => b.dataset.tab === n).focus();
    });
    const followBtn = el('button', { type: 'button', class: 'jx-follow', id: 'jx-follow', 'aria-pressed': follow ? 'true' : 'false',
                                     title: 'Show only the Joe Prompt tab (the Aim 2 follow-up)' },
      [el('span', { class: 'jx-knob', 'aria-hidden': 'true' }), 'Follow-up only']);
    const setFollow = (v) => {
      follow = v;
      followBtn.setAttribute('aria-pressed', v ? 'true' : 'false');
      tabBtns.forEach((b) => { b.hidden = v && b.dataset.tab !== 'prompt'; });
      try { localStorage.setItem(FOLLOW_KEY, v ? '1' : '0'); } catch (e) { /* none */ }
      setTab(v ? 'prompt' : SW.tab || 'results', false);
    };
    followBtn.addEventListener('click', () => setFollow(!follow));
    wrap.appendChild(el('div', { class: 'jx-card' }, [
      el('div', { class: 'jx-head' }, [
        el('div', {}, [
          el('div', { class: 'jx-big', text: 'Coherence across preconditioning: figures and data' }),
          el('div', { class: 'jx-muted', text: 'DEWEY, ' + M.rats + ' rats, ' + (M.days || []).join(' and ') + '. Made ' + day(M.made) + ' from the analysis of '
            + day(M.joe_at) + ' and the figures of ' + day(M.figs_at) + '.' })]),
        el('div', { class: 'jx-files' }, [panels.prompt ? followBtn : null, allBtn])]),
      status,
      tabs.length > 1 ? tabBar : null]));
    for (const k in panels) wrap.appendChild(panels[k]);
    const inTab = (k) => M.sections.filter((s) => tabOf(s) === k);
    panels.results.appendChild(el('div', { class: 'jx-card' }, [
      el('ul', { class: 'jx-read' }, [
        el('li', { text: 'The question, from the proposal: did the cues’ effect on coherence between regions change from Precon1 to Precon4, in theta (5–12 Hz) and gamma (30–90 Hz)?' }),
        el('li', { text: 'A cue effect is the cue window’s coherence minus the baseline’s. Each ring figure has three rows: the Precon1 cue effect, the Precon4 cue effect, and the change in cue effect (Precon4’s minus Precon1’s), which is the question. Supplementary Figure S1 shows it on one pair.' }),
        el('li', { text: 'Every result is held to three tests, FP first: FP (' + (M.fp && M.fp.fake_trials ? M.fp.fake_trials.toLocaleString('en-US') + ' ' : '') + 'fake trials from the same rats’ FP1 and FP2, with no cues), the shuffles (each trial’s baseline and cue swapped at random inside its session) and the rats (every way of flipping the sign of each rat’s change, or a t-test). A filled dot is a test passed (P < 0.05).' }),
        el('li', { text: 'No P value in the figures section is corrected for the number of tests. Read them as leads to test again, not findings.' }),
        M.rat_sets && panels.wrap
          ? el('li', { text: 'Wrapping up holds the methods for the dissertation: how the data were processed and analysed, from the recordings to the statistics, written to be adapted, each section with a Copy button and the same text as Word and plain text. Sanity check holds the report on whether the right data and logic went in.' })
          : null,
        panels.prompt
          ? el('li', { text: 'Joe Prompt holds the final round of Aim 2 follow-ups from Joe’s run sheet (J6–J11): the summary table of all 23 requests, the confirmations, and each request’s results, figures, PDF and CSV, in parts, including how volume conduction was handled and how the data were cleaned. “Follow-up only” shows that tab alone.' })
          : null,
        M.sections.some((s) => s.id === 'dickson')
          ? el('li', { text: M.rat_sets
            ? 'Coherence between regions, and power, aperiodic activity, directionality and coupling: every figure has its axes shared across pairs, regions and sets of rats, so any two can be compared directly, and asterisks on its significant tests, corrected or uncorrected as the switch says (the caption says which). Under each: its caption, its results as a paragraph, a methods note, and a statistics PDF laid out as SPSS prints it: the design, every effect and interaction, and the post hoc tests of each significant interaction.'
            : 'Dickson’s way asks the plan’s simpler question: did coherence in each of ten region pairs change from Precon1 to Precon4 (and between cue 1 and cue 2, and against the baseline)? A GEE decides, corrected across the ten pairs. Its coherence comes from pooled spectra: read the warning at the top of that section.' })
          : null,
        M.sections.some((s) => s.id === 'final') && !M.rat_sets
          ? el('li', { text: 'Part 2 is the final stage: power inside each region, the background under it, and, on the coherence results that pass, which region leads and theta–gamma coupling; with the methods written from the run. Every figure here is a PDF.' })
          : null]),
      switchNode(M),
      el('div', { class: 'jx-nav' }, inTab('results').map((s) => el('a', { href: '#jx-' + s.id, text: s.title })))]));
    for (const k in panels) {
      if (k !== 'results' && inTab(k).length > 1) {
        panels[k].appendChild(el('div', { class: 'jx-card' }, el('div', { class: 'jx-nav' }, inTab(k).map((s) => el('a', { href: '#jx-' + s.id, text: s.title })))));
      }
    }
    for (const s of M.sections) {
      if (s.prompt) {
        panels[tabOf(s)].appendChild(promptPart(s.prompt, url, preview));
        continue;
      }
      const sFiles = filesOf(s);
      const card = el('div', { class: 'jx-card', id: 'jx-' + s.id }, [
        el('div', { class: 'jx-head' }, [el('div', {}, [el('h2', { text: s.title }), el('p', { class: 'jx-muted', text: s.say })])]),
        s.flag ? el('div', { class: 'jx-flag', role: 'note' }, [el('b', { text: 'Read first. ' }), s.flag]) : null,
        s.files && s.files.length ? el('div', { class: 'jx-files' }, s.files.map((f) => fileLink(f, url))) : null]);
      if (s.lights) card.appendChild(lights(s.lights));
      if (s.methods && s.methods.length) card.appendChild(el('div', {}, [el('h3', { text: 'Methods' }), methods(s.methods)]));
      if (s.prose && s.prose.length) card.appendChild(methodsProse(s.prose));
      if (s.sanity) card.appendChild(sanityPart(s.sanity));
      if (s.conduction) card.appendChild(conductionPart(s.conduction));
      if (s.sets) card.appendChild(setPart(s, url, preview));
      if (s.groups) {
        const navs = s.groups.map((g) => el('a', { href: '#jx-g-' + g.key.replace('|', '-'), text: g.title }));
        card.appendChild(el('div', { class: 'jx-nav' }, navs));
        const boxes = [];
        s.groups.forEach((g, gi) => {
          const gb = el('button', { type: 'button', class: 'jx-btn', text: 'Download this group' });
          const gs = el('div', { class: 'jx-status', role: 'status' });
          const gf = filesOf({ figures: g.figures });
          gb.addEventListener('click', () => zipDown(gf, () => '', 'Joe_figures_' + g.key.replace('|', '_') + '.zip', url, (t) => { gs.textContent = t; }, gb));
          const fns = g.figures.map((fg) => figure(fg, url, preview));
          const box = el('div', { id: 'jx-g-' + g.key.replace('|', '-') }, [
            el('div', { class: 'jx-head' }, [el('h3', { text: g.title }), gb]),
            g.say ? el('p', { class: 'jx-gsay', text: g.say })
              : g.key !== 'S' && !g.gated ? el('p', { class: 'jx-gsay', text: 'Tab 8’s light did not pass here, so this group is its ring only.' }) : null,
            gs].concat(fns));
          // with only what is significant, a group left with none of its figures goes, and its link with it
          const update = () => { box.hidden = SW.only && fns.every((n) => n.hidden); navs[gi].hidden = box.hidden; };
          update();
          SW.after.push(update);
          boxes.push(box);
          card.appendChild(box);
        });
        const none = el('p', { class: 'jx-muted', hidden: true, text: 'Nothing in this part passes every one of its tests.' });
        SW.after.push(() => { none.hidden = !(SW.only && boxes.every((b) => b.hidden)); });
        card.appendChild(none);
      }
      if (!s.files.length && !sFiles.length && !s.sanity && !s.conduction) card.appendChild(el('p', { class: 'jx-muted', text: 'Not made yet.' }));
      panels[tabOf(s)].appendChild(card);
    }
    // the tab: #tab=<key> in the address, else the last one picked, else Results
    let first = 'results';
    try { first = localStorage.getItem(TAB_KEY) || first; } catch (e) { /* none */ }
    const h = /(?:^#|&)tab=(\w+)/.exec(location.hash || '');
    if (follow && panels.prompt) setFollow(true);
    else setTab(h ? h[1] : first, false);
  }

  return { render, filesOf, conductionNode, promptNode };
}());
