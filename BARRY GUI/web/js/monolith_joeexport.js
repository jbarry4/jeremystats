/* ==========================================================================
   monolith_joeexport.js -- the Monolith page's tenth tab: Joe's export
   (Shahriar, 2026-10-26).

   Everything that goes to Joe, in one list: the slides, every tab 9 figure
   with its Prism numbers, tab 8's tables and SPSS files, and the standalone
   script. The list itself is drawn by js/joe_export.js, the same file that
   is Joe's site; above it, the site's card: when it was last assembled,
   how big it is, and a button to assemble it again. Deploying is not a
   button: it is `npx vercel deploy --prod` from the site's folder.
   ========================================================================== */
'use strict';

window.MONO_JOEX = (function () {
  const M = () => window.MONO;
  const P = { data: null, err: null, loading: false, seq: 0, building: false, buildErr: null };
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  const FILE = (name, view) => '/api/arc/monolith/joeexport/file/' + encodeURIComponent(name) + (view ? '?view=1' : '');
  const mb = (b) => (b / 1e6).toFixed(1) + ' MB';
  const when = (s) => { try { return new Date(s).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' }); } catch (e) { return s; } };

  async function load() {
    const seq = ++P.seq;
    P.loading = true;
    render();
    try {
      const got = await M().getJSON('/data/joeexport');
      if (seq !== P.seq) return;
      P.data = got; P.err = null;
    } catch (e) {
      if (seq !== P.seq) return;
      P.data = null; P.err = e.message;
    }
    P.loading = false;
    render();
  }

  async function build() {
    if (P.building) return;
    P.building = true; P.buildErr = null;
    render();
    try {
      const got = await M().postJSON('/joeexport/site', { confirm: true });
      if (P.data) P.data.site = got.site;
    } catch (e) {
      P.buildErr = e.message;
    }
    P.building = false;
    render();
  }

  function siteCard(D) {
    const s = D.site || {};
    const over = D.bytes > D.budget_mb * 1e6;
    return el('div', { class: 'card', id: 'joexsite' }, [
      el('div', { class: 'hrow' }, [el('h2', { text: '10 · Joe export' }), M().qh('joex')]),
      el('p', { text: 'Everything below goes to Joe, and is the site he downloads it from: ' + D.n_figures + ' figures and '
        + D.n_files + ' files, ' + mb(D.bytes) + ' of the ' + D.budget_mb + ' MB a deploy can take.' }),
      over ? el('p', { class: 'warn', text: 'Too big for one deploy: leave something out before assembling.' }) : null,
      el('p', { class: 'small muted', id: 'joexsitesay', text: s.built
        ? 'Joe’s site was last assembled ' + when(s.made) + ' (' + mb(s.bytes) + '), in GUI_logs/.cache/joe_site. '
          + (s.deployed ? 'It is linked to its Vercel project.' : 'It has not been linked to Vercel yet.')
        : 'Joe’s site has not been assembled yet.' }),
      el('div', {}, [
        el('button', { type: 'button', class: 'more-btn', id: 'joexbuild', disabled: P.building || over ? 'disabled' : null,
                       text: P.building ? 'Assembling' : s.built ? 'Assemble the site again' : 'Assemble the site',
                       onclick: build })]),
      P.buildErr ? el('p', { class: 'warn', id: 'joexerr', text: P.buildErr }) : null,
      el('p', { class: 'small muted', text: 'Putting it online is a separate step: from that folder, vercel deploy --prod (project joe-export, '
        + 'password set in Vercel as SITE_PASSWORD and SITE_SECRET).' })]);
  }

  function render() {
    const pane = $('joexpane');
    if (!pane) return;
    if (window.MONO_STATIC) {
      pane.replaceChildren(el('div', { class: 'card', id: 'joexstatic' }, [
        el('div', { class: 'hrow' }, [el('h2', { text: '10 · Joe export' })]),
        el('p', { text: 'Joe’s export is a site of its own. Not in this copy: it opens in Jarvis.' })]));
      return;
    }
    if (P.loading && !P.data) {
      pane.replaceChildren(el('div', { class: 'card' }, el('p', { class: 'muted', text: 'Reading the list.' })));
      return;
    }
    if (!P.data) {
      pane.replaceChildren(el('div', { class: 'card', id: 'joexmissing' }, [
        el('div', { class: 'hrow' }, [el('h2', { text: '10 · Joe export' })]),
        el('p', { text: P.err || 'Nothing to show yet.' })]));
      return;
    }
    const host = el('div', { id: 'joexlist' });
    pane.replaceChildren(host);
    window.JOE_EXPORT.render(host, P.data, { url: (n) => FILE(n), preview: (n) => FILE(n, true), top: siteCard(P.data) });
  }

  function show() {
    if (!P.data && !P.loading) load(); else render();
  }
  return { show, render, load, build, get state() { return { data: P.data, err: P.err, building: P.building }; } };
})();
