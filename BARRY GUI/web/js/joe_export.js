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
.jx .jx-file span { font-size: 12.5px; color: var(--ink-3); }
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
@media (max-width: 640px) {
  .jx .jx-fig { grid-template-columns: minmax(0, 1fr); }
  .jx .jx-thumb { max-width: 320px; }
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
    for (const g of part.groups || []) for (const fg of g.figures) { fg.views.forEach((v) => v.files.forEach(take)); take(fg.prism); }
    for (const fg of part.figures || []) { fg.views.forEach((v) => v.files.forEach(take)); take(fg.prism); }
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

  function tests(fg) {
    if (!fg.tests || !fg.tests.length) return null;
    return el('div', { class: 'jx-tests', 'aria-label': 'Its three tests, FP first' }, fg.tests.map((t) => el('span', { class: 'jx-test' }, [
      el('span', { class: 'jx-dot' + (t.pass ? ' on' : ''), 'aria-hidden': 'true' }),
      el('span', { text: t.say + (t.pass ? ': passes' : ': does not pass') })])));
  }

  function figure(fg, url, preview) {
    let vi = 0;
    const img = el('img', { alt: fg.name, loading: 'lazy' });
    const thumb = el('a', { class: 'jx-thumb', target: '_blank', rel: 'noopener' }, [img]);
    const legend = el('div', { class: 'jx-legend' });
    const files = el('div', { class: 'jx-files' });
    const vbtns = [];
    function show() {
      const v = fg.views[vi];
      if (v.preview) { img.src = preview(v.preview); thumb.href = preview(v.preview); }
      legend.replaceChildren(el('p', {}, [el('b', { text: v.legend.title || '' }), ' ', v.legend.body || '']));
      files.replaceChildren(...v.files.map((f) => fileLink(f, url)).concat(fg.prism ? [fileLink(fg.prism, url)] : []));
      vbtns.forEach((b, i) => b.setAttribute('aria-pressed', i === vi ? 'true' : 'false'));
    }
    const views = fg.views.length > 1 ? el('div', { class: 'jx-views', role: 'group', 'aria-label': 'Which test the picture shows' },
      fg.views.map((v, i) => { const b = el('button', { type: 'button', text: v.say, on: { click: () => { vi = i; show(); } } }); vbtns.push(b); return b; }))
      : null;
    const node = el('div', { class: 'jx-fig', id: 'jx-fig-' + fg.id.replace('.', '_') }, [
      thumb,
      el('div', {}, [
        el('div', { class: 'jx-figname', text: fg.name }),
        el('div', { text: fg.title || '' }),
        tests(fg),
        views,
        el('details', {}, [el('summary', { text: 'Legend' }), legend]),
        files])]);
    show();
    return node;
  }

  function lights(rows) {
    const cell = (r, b) => {
      const x = r.bands[b];
      return el('td', { class: 'jx-l' }, [el('span', { class: 'jx-light' + (x.lit ? ' on' : '') + (x.lit && r.check ? ' chk' : ''), 'aria-hidden': 'true' }),
        (x.lit ? 'lit, ' : '') + pSay(x.p)]);
    };
    return el('table', { class: 'jx-lights' }, [
      el('thead', {}, el('tr', {}, [el('th', { text: '#' }), el('th', { text: 'Comparison' }), el('th', { text: 'Theta' }), el('th', { text: 'Gamma' })])),
      el('tbody', {}, rows.map((r) => el('tr', {}, [el('td', { text: String(r.no) }), el('td', { text: r.title + (r.check ? ' (check)' : '') }),
        cell(r, 'theta'), cell(r, 'gamma')])))]);
  }

  function render(root, M, opts) {
    style();
    opts = opts || {};
    const url = opts.url || ((n) => 'files/' + encodeURIComponent(n));
    const preview = opts.preview || url;
    root.replaceChildren();
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
    wrap.appendChild(el('div', { class: 'jx-card' }, [
      el('div', { class: 'jx-head' }, [
        el('div', {}, [
          el('div', { class: 'jx-big', text: 'Coherence across preconditioning: figures and data' }),
          el('div', { class: 'jx-muted', text: 'DEWEY, ' + M.rats + ' rats, ' + (M.days || []).join(' and ') + '. Made ' + day(M.made) + ' from the analysis of '
            + day(M.joe_at) + ' and the figures of ' + day(M.figs_at) + '.' })]),
        allBtn]),
      status,
      el('ul', { class: 'jx-read' }, [
        el('li', { text: 'The question, from the proposal: did the cues’ effect on coherence between regions change from Precon1 to Precon4, in theta (5–12 Hz) and gamma (30–90 Hz)?' }),
        el('li', { text: 'A cue effect is the cue window’s coherence minus the baseline’s. Each ring figure has three rows: the Precon1 cue effect, the Precon4 cue effect, and the change in cue effect (Precon4’s minus Precon1’s), which is the question. Supplementary Figure S1 shows it on one pair.' }),
        el('li', { text: 'Every result is held to three tests, FP first: FP (' + (M.fp && M.fp.fake_trials ? M.fp.fake_trials.toLocaleString('en-US') + ' ' : '') + 'fake trials from the same rats’ FP1 and FP2, with no cues), the shuffles (each trial’s baseline and cue swapped at random inside its session) and the rats (every way of flipping the sign of each rat’s change, or a t-test). A filled dot is a test passed (P < 0.05).' }),
        el('li', { text: 'No P value is corrected for the number of tests. Read them as leads to test again, not findings.' })]),
      el('div', { class: 'jx-nav' }, M.sections.map((s) => el('a', { href: '#jx-' + s.id, text: s.title })))]));
    for (const s of M.sections) {
      const sFiles = filesOf(s);
      const card = el('div', { class: 'jx-card', id: 'jx-' + s.id }, [
        el('div', { class: 'jx-head' }, [el('div', {}, [el('h2', { text: s.title }), el('p', { class: 'jx-muted', text: s.say })])]),
        s.files && s.files.length ? el('div', { class: 'jx-files' }, s.files.map((f) => fileLink(f, url))) : null]);
      if (s.lights) card.appendChild(lights(s.lights));
      if (s.groups) {
        card.appendChild(el('div', { class: 'jx-nav' }, s.groups.map((g) => el('a', { href: '#jx-g-' + g.key.replace('|', '-'), text: g.title }))));
        for (const g of s.groups) {
          const gb = el('button', { type: 'button', class: 'jx-btn', text: 'Download this group' });
          const gs = el('div', { class: 'jx-status', role: 'status' });
          const gf = filesOf({ figures: g.figures });
          gb.addEventListener('click', () => zipDown(gf, () => '', 'Joe_figures_' + g.key.replace('|', '_') + '.zip', url, (t) => { gs.textContent = t; }, gb));
          card.appendChild(el('div', { id: 'jx-g-' + g.key.replace('|', '-') }, [
            el('div', { class: 'jx-head' }, [el('h3', { text: g.title }), gb]),
            g.key !== 'S' && !g.gated ? el('p', { class: 'jx-gsay', text: 'Tab 8’s light did not pass here, so this group is its ring only.' }) : null,
            gs]
            .concat(g.figures.map((fg) => figure(fg, url, preview)))));
        }
      }
      if (!s.files.length && !sFiles.length) card.appendChild(el('p', { class: 'jx-muted', text: 'Not made yet.' }));
      wrap.appendChild(card);
    }
  }

  return { render, filesOf };
}());
