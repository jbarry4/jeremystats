/* ==========================================================================
   monolith_joeprompt.js -- the Monolith page's fourteenth tab: Joe Prompt
   (Shahriar, 2026-11-06).

   Joe's final round of Aim 2 follow-ups (his run sheet, 23 requests),
   J6-J11 only: the summary table, the confirmations, and every request's
   results, figures, PDF and CSV, in parts. The page is js/joe_export.js's
   promptNode, the same node Joe's site shows in its Joe Prompt tab, read
   from tab 10's list (/data/joeexport) so its files come through the same
   route. Made by `python -m backend.joepromptfigs` (after
   `python -m backend.joeprompt measure`).
   ========================================================================== */
'use strict';

window.MONO_PROMPT = (function () {
  const M = () => window.MONO;
  const P = { data: null, err: null, loading: false, seq: 0 };
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  const FILE = (name, view) => '/api/arc/monolith/joeexport/file/' + encodeURIComponent(name) + (view ? '?view=1' : '');

  async function load() {
    const seq = ++P.seq;
    P.loading = true;
    render();
    try {
      const got = await M().getJSON('/data/joeexport');
      if (seq !== P.seq) return;
      const s = (got.sections || []).find((x) => x.id === 'prompt');
      P.data = s ? s.prompt : null;
      P.err = s ? null : 'Joe Prompt has not been made yet: python -m backend.joepromptfigs makes it.';
    } catch (e) {
      if (seq !== P.seq) return;
      P.data = null; P.err = e.message;
    }
    P.loading = false;
    render();
  }

  function render() {
    const pane = $('promptpane');
    if (!pane) return;
    if (window.MONO_STATIC) {
      pane.replaceChildren(el('div', { class: 'card', id: 'promptstatic' }, [
        el('div', { class: 'hrow' }, [el('h2', { text: '14 · Joe Prompt' })]),
        el('p', { text: 'Joe Prompt is on Joe’s own site. Not in this copy: it opens in Jarvis.' })]));
      return;
    }
    if (P.loading && !P.data) {
      pane.replaceChildren(el('div', { class: 'card' }, el('p', { class: 'muted', text: 'Reading the follow-ups.' })));
      return;
    }
    if (!P.data) {
      pane.replaceChildren(el('div', { class: 'card', id: 'promptmissing' }, [
        el('div', { class: 'hrow' }, [el('h2', { text: '14 · Joe Prompt' })]),
        el('p', { text: P.err || 'Nothing to show yet.' })]));
      return;
    }
    pane.replaceChildren(window.JOE_EXPORT.promptNode(P.data, { url: (n) => FILE(n), preview: (n) => FILE(n, true) }));
  }

  function show() {
    if (!P.data && !P.loading) load(); else render();
  }
  return { show, render, load, get state() { return { data: P.data, err: P.err }; } };
})();
