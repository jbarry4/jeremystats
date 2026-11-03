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
.jx table.jx-tests { border-collapse: collapse; font-size: 13.5px; width: 100%; margin: 6px 0; }
.jx table.jx-tests th, .jx table.jx-tests td { padding: 4px 7px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
.jx table.jx-tests tr.yes td, .jx table.jx-tests tr.yes th { font-weight: 650; }
.jx table.jx-tests th { font-weight: 600; color: var(--ink-2); }
.jx .jx-tablewrap { overflow-x: auto; }
.jx .jx-passlist { margin: 6px 0 4px; padding-left: 20px; font-size: 14px; }
.jx .jx-passlist li { margin-bottom: 3px; }
.jx .jx-msec { margin: 0 0 14px; }
.jx .jx-msec h3 { margin: 18px 0 6px; }
@media (max-width: 640px) {
  .jx .jx-fig { grid-template-columns: minmax(0, 1fr); }
  .jx .jx-thumb { max-width: 320px; }
  .jx .jx-pubfig .jx-thumb { max-width: 100%; }
  .jx .jx-prose { font-size: 15.5px; }
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
    const fig = (fg) => { (fg.views || []).forEach((v) => v.files.forEach(take)); (fg.files || []).forEach(take); take(fg.prism); };
    for (const g of part.groups || []) g.figures.forEach(fig);
    for (const gs of Object.values(part.sets || {})) for (const g of gs) g.figures.forEach(fig);
    (part.figures || []).forEach(fig);
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
  const SW = { mode: 'fdr', figs: [], rs: 'all', setParts: [] };

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

  /* A figure of the publication set: the drawing, its badge, its words. */
  function pubFigure(fg, url, preview, sid) {
    const img = el('img', { alt: fg.name, loading: 'lazy', src: fg.preview ? preview(fg.preview) : '' });
    const badge = el('span', { class: 'jx-badge' });
    const tbox = el('div', {});
    const node = el('div', { class: 'jx-pubfig', id: 'jx-fig-' + sid + '-' + fg.id.replace(/\./g, '_') }, [
      el('div', { class: 'jx-figrow' }, [el('span', { class: 'jx-figname', text: fg.name }), badge]),
      el('a', { class: 'jx-thumb', href: fg.files && fg.files[0] ? url(fg.files[0].name) : (fg.preview ? preview(fg.preview) : '#'), target: '_blank', rel: 'noopener',
                title: 'Open the PDF' }, [img]),
      prose('Caption', fg.caption),
      prose('Results', fg.results),
      prose('Methods note', fg.note),
      tbox,
      el('div', { class: 'jx-files' }, (fg.files || []).map((f) => fileLink(f, url)).concat(fg.prism ? [fileLink(fg.prism, url)] : []))]);
    node.update = () => {
      const s = fg.sig || {};
      const yes = !!s[SW.mode];
      const near = !yes && SW.mode === 'fdr' && !!s.raw;
      badge.className = 'jx-badge' + (yes ? ' yes' : near ? ' near' : '');
      const held = yes ? heldUp(fg) : '';
      badge.textContent = (yes ? (SW.mode === 'fdr' ? 'Significant after FDR' : 'Significant, p < .05 uncorrected')
        : near ? 'p < .05 uncorrected only' : 'Not significant') + (held ? '; ' + held : '');
      if (!(fg.tests || []).some((t) => t.primary)) badge.textContent = (fg.tests || []).some((t) => t.pass && t.pass[SW.mode]) ? 'Some tests significant' : 'No test significant';
      node.hidden = !!(fg.show_in && fg.show_in[SW.mode] === false);
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
      const passing = groups.flatMap((g) => g.figures).filter((fg) => fg.sig && fg.sig[SW.mode] && !(fg.show_in && fg.show_in[SW.mode] === false));
      const kids = [
        el('h3', { text: 'Significant ' + (SW.mode === 'fdr' ? 'after FDR correction' : 'at p < .05, uncorrected') + ' (' + passing.length + ')' }),
        passing.length ? el('ul', { class: 'jx-passlist' }, passing.map((fg) => el('li', {}, [
          el('a', { href: '#jx-fig-' + sid + '-' + fg.id.replace(/\./g, '_'), text: fg.name }), heldUp(fg) ? ': ' + heldUp(fg) : ''])))
          : el('p', { class: 'jx-muted', text: 'Nothing in this part passes on this side of the switch.' }),
        el('div', { class: 'jx-nav' }, groups.map((g) => el('a', { href: '#jx-g-' + sid + '-' + g.key, text: g.title })))];
      for (const g of groups) {
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
    const pass = (t) => (t.pass && typeof t.pass === 'object' ? !!t.pass[SW.mode] : !!t.pass);
    return el('div', { class: 'jx-tests', 'aria-label': fg.tests.length > 1 ? 'Its three tests, FP first' : 'Its test' }, fg.tests.map((t) => el('span', { class: 'jx-test' }, [
      el('span', { class: 'jx-dot' + (pass(t) ? ' on' : ''), 'aria-hidden': 'true' }),
      el('span', { text: t.say + (pass(t) ? ': passes' : ': does not pass') })])));
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
      node.hidden = !!(fg.show_in && fg.show_in[SW.mode] === false);
      show();
    };
    node.update();
    SW.figs.push(node);
    return node;
  }

  function switchNode(M) {
    if (!M.switch) return null;
    const btns = [];
    const set = (m) => {
      SW.mode = m;
      btns.forEach((b) => b.setAttribute('aria-pressed', b.dataset.mode === m ? 'true' : 'false'));
      SW.figs.forEach((n) => n.update());
      SW.setParts.forEach((d) => d());                      // their lists of what passes
    };
    for (const m of ['fdr', 'raw']) {
      const b = el('button', { type: 'button', text: M.switch[m], 'data-mode': m, 'aria-pressed': m === SW.mode ? 'true' : 'false', on: { click: () => set(m) } });
      btns.push(b);
    }
    const rows = [el('div', { class: 'jx-switch' }, [el('span', { class: 'jx-muted', text: M.rat_sets ? 'What counts as significant:' : 'Dickson’s way and Part 2, stars and follow-ups:' }),
      el('div', { class: 'jx-views', role: 'group', 'aria-label': 'Correction for many tests' }, btns)])];
    if (M.rat_sets && M.rat_sets.length > 1) {
      const rb = [];
      const setRs = (k) => {
        SW.rs = k;
        rb.forEach((b) => b.setAttribute('aria-pressed', b.dataset.rs === k ? 'true' : 'false'));
        SW.setParts.forEach((d) => d());
      };
      for (const s of M.rat_sets) {
        rb.push(el('button', { type: 'button', text: s.say, 'data-rs': s.key, 'aria-pressed': s.key === SW.rs ? 'true' : 'false', on: { click: () => setRs(s.key) } }));
      }
      rows.push(el('div', { class: 'jx-switch' }, [el('span', { class: 'jx-muted', text: 'Coherence, power and the follow-ups from:' }),
        el('div', { class: 'jx-views', role: 'group', 'aria-label': 'Which rats' }, rb)]));
      if (M.rat_why) rows.push(el('p', { class: 'jx-muted', text: M.rat_why }));
    }
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
    SW.figs = [];
    SW.setParts = [];
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
        el('li', { text: 'No P value in the figures section is corrected for the number of tests. Read them as leads to test again, not findings.' }),
        M.rat_sets
          ? el('li', { text: 'Methods, for the dissertation: how the data were processed and analysed, from the recordings to the statistics, written to be adapted. Each section has a Copy button; the same text comes as Word and as plain text.' })
          : null,
        M.sections.some((s) => s.id === 'dickson')
          ? el('li', { text: M.rat_sets
            ? 'Coherence between regions, and power, aperiodic activity, directionality and coupling: every figure is drawn without statistics and with its axes shared across pairs, regions and sets of rats, so any two can be compared directly. Under each: its caption, its results as a paragraph, a methods note, and every test behind it. What is significant is marked beside the figure, never in it.'
            : 'Dickson’s way asks the plan’s simpler question: did coherence in each of ten region pairs change from Precon1 to Precon4 (and between cue 1 and cue 2, and against the baseline)? A GEE decides, corrected across the ten pairs. Its coherence comes from pooled spectra: read the warning at the top of that section.' })
          : null,
        M.sections.some((s) => s.id === 'final') && !M.rat_sets
          ? el('li', { text: 'Part 2 is the final stage: power inside each region, the background under it, and, on the coherence results that pass, which region leads and theta–gamma coupling; with the methods written from the run. Every figure here is a PDF.' })
          : null]),
      switchNode(M),
      el('div', { class: 'jx-nav' }, M.sections.map((s) => el('a', { href: '#jx-' + s.id, text: s.title })))]));
    for (const s of M.sections) {
      const sFiles = filesOf(s);
      const card = el('div', { class: 'jx-card', id: 'jx-' + s.id }, [
        el('div', { class: 'jx-head' }, [el('div', {}, [el('h2', { text: s.title }), el('p', { class: 'jx-muted', text: s.say })])]),
        s.flag ? el('div', { class: 'jx-flag', role: 'note' }, [el('b', { text: 'Read first. ' }), s.flag]) : null,
        s.files && s.files.length ? el('div', { class: 'jx-files' }, s.files.map((f) => fileLink(f, url))) : null]);
      if (s.lights) card.appendChild(lights(s.lights));
      if (s.methods && s.methods.length) card.appendChild(el('div', {}, [el('h3', { text: 'Methods' }), methods(s.methods)]));
      if (s.prose && s.prose.length) card.appendChild(methodsProse(s.prose));
      if (s.sets) card.appendChild(setPart(s, url, preview));
      if (s.groups) {
        card.appendChild(el('div', { class: 'jx-nav' }, s.groups.map((g) => el('a', { href: '#jx-g-' + g.key.replace('|', '-'), text: g.title }))));
        for (const g of s.groups) {
          const gb = el('button', { type: 'button', class: 'jx-btn', text: 'Download this group' });
          const gs = el('div', { class: 'jx-status', role: 'status' });
          const gf = filesOf({ figures: g.figures });
          gb.addEventListener('click', () => zipDown(gf, () => '', 'Joe_figures_' + g.key.replace('|', '_') + '.zip', url, (t) => { gs.textContent = t; }, gb));
          card.appendChild(el('div', { id: 'jx-g-' + g.key.replace('|', '-') }, [
            el('div', { class: 'jx-head' }, [el('h3', { text: g.title }), gb]),
            g.say ? el('p', { class: 'jx-gsay', text: g.say })
              : g.key !== 'S' && !g.gated ? el('p', { class: 'jx-gsay', text: 'Tab 8’s light did not pass here, so this group is its ring only.' }) : null,
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
