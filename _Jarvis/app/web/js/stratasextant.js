/* ==========================================================================
   stratasextant.js -- StrataScope x Sextant: a placement offered as a proposal.

   Sextant (Seahorse > Place a probe) estimates where a recording's probe sat
   in the atlas from the recording's own signals, and so which layer each
   contact was in. When it has placed the open recording, StrataScope's step
   row gets a [Sextant] switch. On, every lane is hatched in the layer Sextant
   puts there -- a proposal, drawn exactly like a step's, never a label --
   and "Accept Sextant's layers" writes them in one click (the sheet keeps
   its history, as for any step).

   The layers come from the placement somebody kept in Seahorse (Accept) when
   there is one, else from Sextant's own answer; the switch says which.
   ========================================================================== */
'use strict';

BARRY.strataSextant = (function () {
  let gid = null;
  let prop = null;          // {from: 'accepted'|'sextant', strata: [64 region ids or null], ...}
  let showing = false;
  let busy = false;

  const C = () => BARRY.strataSteps && BARRY.strataSteps._consult;
  const host = () => { const c = C(); return c && c.host ? c.host() : null; };
  const url = (what) => '/api/sextant/' + encodeURIComponent(gid) + '/' + what;

  async function enter(g) {
    gid = g; prop = null; showing = false; busy = false;
    try {
      const res = await apiPost(url('proposal'), {});
      if (gid !== g) return;
      prop = res && res.proposal && res.proposal.strata ? res.proposal : null;
      if (prop) { const H = host(); if (H) H.render(); }
    } catch (e) { /* no Sextant route on this server: nothing to offer */ }
  }
  function leave() { gid = null; prop = null; showing = false; }

  function rowBits() {
    if (!prop || !gid) return [];
    const kept = prop.from === 'accepted';
    const out = [BARRY.ui.seg([
      ['off', 'Sextant', 'Sextant’s layers are not drawn.'],
      ['on', 'Shown', 'Hatch every lane in the layer Sextant puts there: ' + (kept
        ? 'the placement kept in Seahorse' + (prop.by ? ' by ' + prop.by : '') + '.'
        : 'Sextant’s own answer, from this recording’s signals (Seahorse › Place a probe).') + ' A proposal until you accept it.'],
    ], showing ? 'on' : 'off', (v) => { showing = v === 'on'; const H = host(); if (H) { H.render(); if (H.redraw) H.redraw(); } },
    { extra: 'ss-sextant-seg' })];
    if (showing) {
      out.push(el('button', {
        class: 'btn sm' + (busy ? ' busy' : ''), text: busy ? 'Writing…' : 'Accept Sextant’s layers',
        disabled: busy ? 'disabled' : null,
        title: 'Write the hatched layers as this sheet’s labels (every contact Sextant names; CA2 and CA3 contacts are left as they are).',
        onclick: accept,
      }));
    }
    return out;
  }

  /* channel number -> region id, while shown (contact k is CSC k) */
  function proposedLabels() {
    if (!showing || !prop) return null;
    const m = new Map();
    prop.strata.forEach((r, k) => { if (r) m.set(k + 1, r); });
    return m;
  }

  async function accept() {
    if (!gid || busy) return;
    busy = true;
    const H0 = host(); if (H0) H0.render();
    try {
      const res = await apiPost(url('to_strata'), {});
      const H = host();
      if (H && res.sheet) H.adoptSheet(res.sheet);
      showing = false;
      toast('Sextant’s layers written: ' + res.n + ' channels labelled.', 'ok', 6000);
    } catch (e) {
      toast('Not written: ' + e.message, 'err', 9000);
    } finally {
      busy = false;
      const H = host(); if (H) H.render();
    }
  }

  return { enter, leave, rowBits, proposedLabels, showing: () => showing };
})();
