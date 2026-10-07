/* ==========================================================================
   monolith_physical.js -- the Monolith's sixth tab: physical cue against
   balanced cue.

   The comparisons are made by seat (A, B, C, D), which the lab's identity
   sheet counterbalances over the four sounds. The sheet does it in a way
   that makes the sounds testable with the Monolith's own numbers: every rat
   opens both its pairs with the same kind of sound -- Click or Noise for
   J3, J6, J7, J8; a tone for J4, J9, J10, J11 -- and every ordered pair of
   sounds is heard by exactly two rats. So each rat's change can be signed
   by sound instead of by seat (backend/monolith.py physical_build):

     tone-first rats against noise-first rats         (between rats, 4 + 4)
     Click-first pair against Noise-first pair         (noise-first rats)
     High-first pair against Low-first pair            (tone-first rats)
     Cue 2 − Cue 1 signed as tone − noise              (all eight)
     AB against CD                                     (the seat counterpart)

   The page says, verdict first: whether the comparisons by sound pass
   p < .05 more often than chance, and more often than an arbitrary
   relabelling of the same rats; then whether each lead holds in both groups
   of four, with an equivalence test at half its own size; then any
   comparison as a circuit, for a view chosen here. Every p is uncorrected.
   Load order: after monolith.js.
   ========================================================================== */
'use strict';

window.MONO_PHYS = (function () {
  const M = () => window.MONO;
  const NS = 'http://www.w3.org/2000/svg';
  const Q = { est: 0, p: 1, k: 2, same: 3, se: 4, why: 5 };
  const P = { data: null, err: null, loading: false, layer: 'raw', leads: 'monolith', all: false, cmp: 'order',
              view: null, arr: new Map(), making: false, makeNote: '', makeErr: null, seq: 0, cseq: 0 };
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  function sv(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const S = () => M().data.S;
  const sig = (v) => M().sig(v), f3 = (v) => M().f3(v), fp = (v) => M().fp(v), short = (r) => M().short(r);
  const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'));
  // At chance, against a relabelling: not among the top 5% of the n ways
  // that pass the most entries (and never the very top).
  const cut = (n) => Math.max(1, Math.floor(0.05 * n));
  const LAYER_SAY = { raw: 'Raw', minus_fp: 'Minus FP' };
  // What each comparison is, for the people reading it.
  const SAY = {
    order: { name: 'Tone-first rats against noise-first rats', by: 'sound',
             what: 'Each group’s own Precon4 − Precon1, pooled over its four rats, one less the other (Welch’s t). In Cue 1 one group hears a tone and the other Click or Noise; in Cue 2 the other way round.' },
    sound_noise: { name: 'Click-first pair against Noise-first pair', by: 'sound',
                   what: 'In each of the four noise-first rats, the change in the pair Click opens less the change in the pair Noise opens, pooled.' },
    sound_tone: { name: 'High-first pair against Low-first pair', by: 'sound',
                  what: 'In each of the four tone-first rats, the change in the pair the high tone opens less the pair the low tone opens, pooled.' },
    tone_noise: { name: 'Cue 2 − Cue 1 signed as tone − noise', by: 'sound',
                  what: 'Cue 2 − Cue 1 is tone − noise for the noise-first rats and noise − tone for the tone-first ones: their sign flipped, it is the same change sorted by sound.' },
    seat_abcd: { name: 'AB against CD', by: 'seat',
                 what: 'In every rat, the change in its AB less the change in its CD: the same pair-against-pair differences, sorted by seat.' },
  };

  /* ---------------- data ---------------- */
  async function load() {
    const seq = ++P.seq;
    P.loading = true;
    render();
    try {
      const got = await M().getJSON('/data/physical');
      if (seq !== P.seq) return;
      P.data = got;
      P.err = null;
    } catch (e) {
      if (seq !== P.seq) return;
      P.data = null;
      P.err = e.message;
    }
    P.loading = false;
    render();
  }
  async function arrayOf(name) {
    if (P.arr.has(name)) return P.arr.get(name);
    const S0 = S();
    const shape = [6, S0.windows.length, S0.bands.length, S0.methods.length, S0.pairs.length];
    const v = M().getArray(name, shape).then((a) => ({ a, shape }));
    P.arr.set(name, v);
    v.catch(() => P.arr.delete(name));
    while (P.arr.size > 6) P.arr.delete(P.arr.keys().next().value);
    return v;
  }
  const at = (v, q, w, b, m, p) => { const sh = v.shape; return v.a[(((q * sh[1] + w) * sh[2] + b) * sh[3] + m) * sh[4] + p]; };
  async function make() {
    if (P.making) return;
    P.making = true; P.makeErr = null; P.makeNote = '';
    render();
    try {
      await M().runHere('/physical', { confirm: true }, (note) => { P.makeNote = note; const b = $('physmake'); if (b) b.textContent = 'Comparing: ' + note; });
      P.arr.clear();
    } catch (e) {
      P.makeErr = /404|not found/i.test(e.message) ? 'Jarvis is running older code without this button: restart it, then press it again.'
        : 'It could not be made: ' + e.message;
    }
    P.making = false;
    load();
  }

  /* ---------------- the page ---------------- */
  // The Monolith's segmented control, with an id to find it by.
  function seg(list, cur, pick, id) {
    const g = M().seg(list, cur, pick, id);
    g.id = id;
    return g;
  }
  const n1 = (n, one, many) => n + ' ' + (n === 1 ? one : many);
  function section(id, title, help, kids) {
    return el('div', { class: 'card', id }, [el('div', { class: 'hrow' }, [el('h2', { text: title }), help ? M().qh(help) : null])].concat(kids));
  }
  function intro() {
    const S0 = S();
    const I = S0.identity || { seats: {}, sound_say: {} };
    const say = (s) => (I.sound_say || {})[s] || s;
    const D = P.data || {};
    const G = D.groups || { noise: [3, 6, 7, 8], tone: [4, 9, 10, 11] };
    const groupOf = (r) => (G.noise.includes(r) ? 'noise' : G.tone.includes(r) ? 'tone' : null);
    const rows = Object.keys(I.seats || {}).map(Number).sort((a, b) => a - b).map((r) => {
      const s = I.seats[r] || {};
      const g = groupOf(r);
      return el('tr', { 'data-rat': String(r), 'data-group': g || '' }, [el('th', { text: 'J' + r }),
        el('td', { text: g === 'noise' ? 'noise-first' : g === 'tone' ? 'tone-first' : '—' })]
        .concat(['A', 'B', 'C', 'D'].map((x) => el('td', { class: 'snd ' + (s[x] === 'High' || s[x] === 'Low' ? 'tone' : 'noisy'), text: say(s[x] || '—') }))));
    });
    const ans = P.data ? answer() : null;
    const card = section('physintro', 'Physical cue against balanced cue', 'physical', [
      ans ? el('div', { class: 'physanswer ' + (ans.effect === false ? 'ok' : ans.effect ? 'warn' : ''), id: 'physanswer' }, [
        el('p', { class: 'head', text: ans.head }), el('p', { text: ans.say })]) : null,
      el('p', { text: 'Every rat heard four sounds: Click, Noise, a high tone and a low tone. The Monolith never uses their names. It calls them '
        + 'A, B, C and D, from the lab’s identity sheet, and which sound is A changes from rat to rat. So a change the Monolith finds could be '
        + 'about the cue’s place in the task, or about the sound itself. This tab checks the sound.' }),
      el('p', { text: 'It can, because of how the sheet seats the sounds: four rats start both their pairs with Click or Noise (noise-first), '
        + 'the other four start both with a tone (tone-first). Splitting the rats that way, and each rat’s two pairs by which sound starts '
        + 'them, tests the sounds with the Monolith’s own numbers. If the sounds did not matter, those splits look like any other split of '
        + 'the same rats.' }),
      el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable physseats', id: 'physseats' }, [
        el('thead', {}, [el('tr', {}, ['Rat', 'Group', 'A', 'B', 'C', 'D'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows)])]),
      el('p', { class: 'small muted', text: 'A opens the AB pair and C the CD pair; B and D close them. Noise-first rats open both their pairs with '
        + 'Click or Noise, so they hear Click or Noise in Cue 1 and a tone in Cue 2; tone-first rats the other way round. Red: a tone; blue: '
        + 'Click or Noise.' }),
    ]);
    // A second ?, with pictures: the sheet, and what each outcome looks like.
    card.querySelector('.hrow').appendChild(el('span', { class: 'qpics small muted', id: 'physhow' }, ['how it works, in pictures', M().qh('physical.how')]));
    return card;
  }
  // The verdict: every comparison, by seat and by sound, against chance.
  // Every comparison of one layer, by seat and by sound, with its counts
  // and its rank among the relabellings of the same rats.
  function rowsOf(L) {
    const D = P.data;
    const rows = [];
    const sc = D.seat_counts || {};
    const add = (name, by, c, extra, id) => rows.push({ name, by, c, extra, id });
    const perm = D.perm || {};
    add('The Monolith: Precon4 − Precon1', 'seat', (sc.monolith || {})[L], null, 'monolith');
    const pt = (perm.tone_noise || {}).raw || {};
    add('Cue 2 − Cue 1', 'seat', (sc.contrast || {}).raw, pt.n ? { rank: pt.balanced_rank, n: pt.n, of: 'ways of signing the rats' } : null, 'contrast');
    add(SAY.seat_abcd.name, 'seat', ((D.counts || {}).seat_abcd || {})[L], null, 'seat_abcd');
    const po = ((perm.order || {})[L]) || {};
    add(SAY.order.name, 'sound', ((D.counts || {}).order || {})[L], po.n ? { rank: po.rank, n: po.n, of: 'splits of the rats into two fours' } : null, 'order');
    for (const cid of ['sound_noise', 'sound_tone']) {
      const ps = ((perm[cid] || {})[L]) || {};
      add(SAY[cid].name, 'sound', ((D.counts || {})[cid] || {})[L], ps.n ? { rank: ps.rank, n: ps.n, of: 'ways of signing its four rats',
        seat: ps.seat_rank } : null, cid);
    }
    add(SAY.tone_noise.name, 'sound', ((D.counts || {}).tone_noise || {}).raw, pt.n ? { rank: pt.rank, n: pt.n, of: 'ways of signing the rats' } : null, 'tone_noise');
    return rows;
  }
  const ratio = (c) => (c && c.chance_p05 ? c.p05 / c.chance_p05 : null);
  // At chance: an ordinary relabelling of the same rats -- not among the
  // top 5% of them that pass the most (never the very top) -- or, with
  // no relabelling to hand, within a quarter of the chance rate.
  const atChance = (r) => !!r.c && (r.extra && r.extra.rank ? r.extra.rank > cut(r.extra.n) : ratio(r.c) <= 1.25);
  /* The bottom line, said first: did the sound have an effect? From the
     same rule as the verdict below, over both layers, and the Monolith's
     leads in each group of four. */
  function answer() {
    const D = P.data;
    const above = [];
    let n = 0;
    for (const L of ['raw', 'minus_fp']) {
      for (const r of rowsOf(L).filter((x) => x.by === 'sound' && x.c)) {
        if (r.id === 'tone_noise' && L !== 'raw') continue;
        n++;
        if (!atChance(r)) above.push(r.name + (r.id === 'tone_noise' ? '' : ' (' + LAYER_SAY[L] + ')'));
      }
    }
    const lead = ((D.leads || {}).monolith || {}).raw || [];
    const same = lead.filter((t) => t.both_ways).length;
    const dif = lead.filter((t) => t.diff && t.diff.p != null && t.diff.p < 0.05).length;
    const leadSay = lead.length ? ' Of the Monolith’s ' + lead.length + ' leads, ' + same + ' go the same way in the tone-first and the noise-first '
      + 'rats, and ' + dif + ' differ between them at p < .05, about what chance alone gives (' + (0.05 * lead.length).toFixed(1) + ').' : '';
    if (!n) return { effect: null, head: 'Not answered yet', say: 'Nothing was compared by sound.' };
    if (!above.length) {
      return { effect: false, head: 'The answer: no sign that the physical sound had an effect.',
               say: 'Sorted by sound instead of by seat, the rats pass no more tests than any other way of sorting the same eight rats, '
                 + 'in all ' + n + ' comparisons by sound (Raw and Minus FP).' + leadSay
                 + ' So the Monolith’s results are about the cue’s place in the task (A, B, C, D), not about which sound it was. '
                 + 'With four rats a group, only a large effect of the sound could have been seen: a small one cannot be ruled out.' };
    }
    return { effect: true, head: 'The answer: possibly, in ' + above.length + ' of ' + n + ' comparisons by sound.',
             say: above.join('; ') + (above.length === 1 ? ' sorts' : ' sort') + ' the rats by sound better than nearly every other way of '
               + 'sorting them: there the sound may have left a mark. Check a lead against them before reading it as about the cue.' + leadSay };
  }
  function verdict() {
    const D = P.data;
    const L = P.layer;
    const rows = rowsOf(L);
    const max = Math.max(2, ...rows.map((r) => ratio(r.c) || 0));
    const bar = (r) => {
      const W = 150, H = 14, x = (v) => 2 + (W - 4) * Math.min(1, v / max);
      const g = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, class: 'physbar', role: 'img',
                           'aria-label': (ratio(r.c) == null ? 'not computed' : ratio(r.c).toFixed(2) + ' times chance') });
      g.appendChild(sv('rect', { x: 2, y: 3, width: W - 4, height: H - 6, fill: css('--surface-2'), stroke: css('--line') }));
      if (ratio(r.c) != null) g.appendChild(sv('rect', { x: 2, y: 3, width: (x(ratio(r.c)) - 2).toFixed(1), height: H - 6,
        fill: r.by === 'seat' ? css('--arrow') : css('--ink-3') }));
      g.appendChild(sv('line', { x1: x(1).toFixed(1), x2: x(1).toFixed(1), y1: 0, y2: H, stroke: css('--ink'), 'stroke-width': 1.2 }));
      g.appendChild(sv('line', { x1: x((D.control_p05 || 0.055) / 0.05).toFixed(1), x2: x((D.control_p05 || 0.055) / 0.05).toFixed(1), y1: 0, y2: H,
        stroke: css('--ink-3'), 'stroke-dasharray': '2 2' }));
      return g;
    };
    const tbl = el('table', { class: 'linetable physverdict', id: 'physverdict' }, [
      el('thead', {}, [el('tr', {}, ['Comparison', 'Sorted by', 'Tested', 'p < .05', 'By chance', '× chance', '', 'Against relabelling']
        .map((h) => el('th', { text: h })))]),
      el('tbody', {}, rows.map((r) => el('tr', { 'data-cmp': r.id, class: r.by }, [
        el('th', { text: r.name }), el('td', { class: 'by', 'data-label': 'sorted by', text: r.by }),
        el('td', { class: 'num', 'data-label': 'tested', text: fmt((r.c || {}).tested) }),
        el('td', { class: 'num', 'data-label': 'p < .05', text: fmt((r.c || {}).p05) }),
        el('td', { class: 'num', 'data-label': 'by chance', text: fmt((r.c || {}).chance_p05) }),
        el('td', { class: 'num', 'data-label': '× chance', text: ratio(r.c) == null ? '—' : ratio(r.c).toFixed(2) }), el('td', { class: 'bar' }, [bar(r)]),
        el('td', { class: 'small rel', text: r.extra && r.extra.rank ? 'ranks ' + r.extra.rank + ' of ' + r.extra.n + ' ' + r.extra.of
          + (r.extra.seat ? ' (by seat: ' + r.extra.seat + ')' : '') + (r.by === 'sound' ? (atChance(r) ? ' · at chance' : ' · above chance') : '') : '—' }),
      ]))),
    ]);
    const bySound = rows.filter((r) => r.by === 'sound' && r.c);
    const flat = bySound.filter(atChance);
    const above = bySound.filter((r) => !atChance(r));
    const lead = !bySound.length ? 'Nothing was compared by sound in this layer.'
      : above.length === 0
        ? 'By sound, every comparison sits at chance: sorted by sound, the rats pass no more entries than an ordinary relabelling of the same '
          + 'rats does. The sounds left no mark the Monolith can see.'
        : above.map((r) => r.name).join('; ') + (above.length === 1 ? ' passes' : ' pass') + ' more entries than '
          + (above.length === 1 ? 'nearly every relabelling of its rats: look at it' : 'nearly every relabelling of their rats: look at them')
          + ' before reading a lead as about the cue rather than the sound. '
          + (flat.length ? flat.length + ' of the ' + bySound.length + ' comparisons by sound sit at chance.' : '');
    return section('physverdictcard', 'Across the whole Monolith: by seat and by sound, against chance', 'physical.verdict', [
      seg([['raw', 'Raw'], ['minus_fp', 'Minus FP']], L, (id) => { P.layer = id; render(); }, 'physlayer'),
      el('p', { class: 'physsay ' + (above.length ? 'warn' : 'ok'), id: 'physsay', text: lead }),
      el('div', { class: 'dtwrap' }, [tbl]),
      el('p', { class: 'small muted', text: 'Tested over every window, frequency, measure and region pair the Monolith tests (tone − noise and Cue 2 − Cue 1: '
        + 'the contrast’s own entries, raw only). The solid line on each bar is chance; the dashed one is what made-up data with no change at all '
        + 'gave (' + (100 * (D.control_p05 || 0.055)).toFixed(1) + '%, ' + (D.control_say || '') + '). Entries are not independent — neighbouring '
        + 'frequencies and measures move together — so a count can stray from chance by luck; the relabellings are the fair yardstick: '
        + 'the same rats, sorted every other way. Every p is uncorrected. With four rats a group, “no effect” can only mean none large enough to see.' }),
      relabelFigures(),
    ]);
  }
  // Where one sorting falls among every relabelling of the same rats: a
  // histogram of their counts, on the counts' own range, with chance and
  // the sortings that matter marked on it.
  function hist(counts, marks, title) {
    const W = 360, H = 112, l = 12, r = 12, t = 20, bo = 26;
    const vals = counts.concat(marks.map((m) => m.v)).filter((v) => v != null && isFinite(v));
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (hi - lo < 1) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.04;
    lo = Math.max(0, lo - pad); hi += pad;
    const nb = Math.min(24, Math.max(6, Math.round(Math.sqrt(counts.length) * 2)));
    const step = (hi - lo) / nb;
    const bins = new Array(nb).fill(0);
    for (const c of counts) bins[Math.max(0, Math.min(nb - 1, Math.floor((c - lo) / step)))]++;
    const top = Math.max(1, ...bins);
    const X = (v) => l + (W - l - r) * ((v - lo) / (hi - lo));
    const svg = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', class: 'mfig physhist', role: 'img', 'aria-label': title,
                            style: 'max-width:' + W + 'px' });
    svg.appendChild(sv('text', { x: 4, y: 12, 'font-size': 10.5, fill: css('--ink-2'), 'font-weight': 600 }, title));
    const y0 = t + 4;
    bins.forEach((n, i) => {
      const h = (H - bo - y0) * n / top;
      svg.appendChild(sv('rect', { x: X(lo + i * step).toFixed(1), y: (H - bo - h).toFixed(1), width: Math.max(1, X(lo + step) - X(lo) - 1).toFixed(1),
                                   height: h.toFixed(1), fill: css('--node-grey'), class: 'hbin', 'data-n': String(n) }));
    });
    svg.appendChild(sv('line', { x1: l, x2: W - r, y1: H - bo, y2: H - bo, stroke: css('--line-2') }));
    [[lo, 'start'], [hi, 'end']].forEach(([v, anchor]) => svg.appendChild(sv('text', { x: X(v).toFixed(1), y: H - bo + 13, 'text-anchor': anchor,
      'font-size': 10, fill: css('--ink-3') }, fmt(Math.round(v)))));
    svg.appendChild(sv('text', { x: W / 2, y: H - 3, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'entries with p < .05'));
    for (const m of marks) {
      if (m.v == null || !isFinite(m.v)) continue;
      const x = X(m.v);
      svg.appendChild(sv('line', { x1: x.toFixed(1), x2: x.toFixed(1), y1: t, y2: H - bo, stroke: m.color, 'stroke-width': m.dash ? 1.2 : 2,
                                   'stroke-dasharray': m.dash ? '3 2' : null, class: 'hmark', 'data-mark': m.id, 'data-v': String(m.v) }));
    }
    const key = el('div', { class: 'hlegend' }, marks.filter((m) => m.v != null && isFinite(m.v)).map((m) =>
      el('span', { 'data-mark': m.id }, [el('i', { class: m.dash ? 'dash' : null, style: 'border-color:' + m.color }), m.label + ' ' + fmt(m.v)])));
    return el('div', { class: 'hfig' }, [svg, key]);
  }
  function relabelFigures() {
    const D = P.data;
    const L = P.layer;
    const chance = (cid, layer) => ({ id: 'chance', v: (((D.counts || {})[cid] || {})[layer] || {}).chance_p05, label: 'chance (5%)',
                                      color: css('--ink-3'), dash: true });
    const po = ((D.perm || {}).order || {})[L] || {};
    const pt = ((D.perm || {}).tone_noise || {}).raw || {};
    const box = el('div', { class: 'physhists' });
    if (po.counts && po.counts.length) {
      box.appendChild(el('div', { 'data-perm': 'order' }, [hist(po.counts, [chance('order', L),
                                                                             { id: 'order', v: po.observed, label: 'tone-first vs noise-first', color: css('--up') }],
        'Every split of the rats into two fours (' + po.n + ')'),
        el('p', { class: 'small muted', text: 'Tone-first against noise-first ranks ' + po.rank + ' of ' + po.n + ': '
          + (po.rank > cut(po.n) ? 'an ordinary split.' : 'among the very few splits that pass the most entries.') })]));
    }
    for (const cid of ['sound_noise', 'sound_tone']) {
      const ps = ((D.perm || {})[cid] || {})[L] || {};
      if (!ps.counts || !ps.counts.length) continue;
      const who = (ps.rats || []).map((r) => 'J' + r).join(', ');
      box.appendChild(el('div', { 'data-perm': cid }, [hist(ps.counts, [chance(cid, L),
                                                                        { id: 'seat', v: ps.seat, label: 'AB − CD (by seat)', color: css('--arrow') },
                                                                        { id: cid, v: ps.observed, label: 'by sound', color: css('--up') }],
        'Every way of signing ' + who + '’s AB − CD (' + ps.n + ')'),
        el('p', { class: 'small muted', text: SAY[cid].name + ' ranks ' + ps.rank + ' of ' + ps.n + '; the same rats by seat, ' + ps.seat_rank
          + ' of ' + ps.n + '. With four rats there are only eight ways, so a rank says little alone; it is one more look.' })]));
    }
    if (pt.counts && pt.counts.length) {
      box.appendChild(el('div', { 'data-perm': 'tone_noise' }, [hist(pt.counts, [chance('tone_noise', 'raw'),
                                                                                  { id: 'balanced', v: pt.balanced, label: 'Cue 2 − Cue 1', color: css('--arrow') },
                                                                                  { id: 'tone_noise', v: pt.observed, label: 'tone − noise', color: css('--up') }],
        'Every way of signing the rats’ Cue 2 − Cue 1 (' + pt.n + ')'),
        el('p', { class: 'small muted', text: 'Cue 2 − Cue 1 as it stands ranks ' + pt.balanced_rank + ' of ' + pt.n + '; signed as tone − noise, '
          + pt.rank + ' of ' + pt.n + '. Had the sounds driven Cue 2 − Cue 1, tone − noise would rank near the top.' })]));
    }
    return box;
  }
  // The leads, split by group.
  function leads() {
    const D = P.data;
    const S0 = S();
    const kind = P.leads;
    const list = kind === 'contrast' ? ((D.leads || {}).contrast || {}).raw || [] : ((D.leads || {}).monolith || {})[kind === 'monolith_m' ? 'minus_fp' : 'raw'] || [];
    const n = P.all ? list.length : Math.min(10, list.length);
    const both = list.filter((x) => x.both_ways).length;
    const eq = list.filter((x) => x.equivalence && x.equivalence.within).length;
    const diff = list.filter((x) => x.diff && x.diff.p != null && x.diff.p < 0.05).length;
    // The narrowest margin each lead is equivalent within, as a multiple
    // of its own change: the far end of its 90% interval. With four rats a
    // group the interval is wide, and ±½ is out of reach for most.
    const reach = (t) => (t.equivalence && t.est ? Math.max(Math.abs(t.equivalence.lo), Math.abs(t.equivalence.hi)) / Math.abs(t.est) : null);
    const reaches = list.map(reach).filter((v) => v != null && isFinite(v)).sort((a, b) => a - b);
    const med = reaches.length ? reaches[Math.floor((reaches.length - 1) / 2)] / 2 + reaches[Math.ceil((reaches.length - 1) / 2)] / 2 : null;
    const split = list.filter((t) => t.equivalence).length;
    const win = (id) => (S0.windows.find((w) => w.id === id) || {}).label || id;
    const meth = (id) => (S0.methods.find((m) => m.id === id) || {}).label || id;
    const band = (t) => (t.hz ? t.hz + ' Hz' : ((S0.bands.find((b) => b.id === t.band) || {}).label || t.band));
    const W = 170, H = 44;
    const forest = (t) => {
      const eq = t.equivalence;
      const ext = [t.est, t.tone.est, t.noise.est, t.diff.est].filter((v) => v != null && isFinite(v)).map(Math.abs);
      for (const g of [t.tone, t.noise]) if (g.est != null && g.se != null) ext.push(Math.abs(g.est) + 1.96 * g.se);
      if (eq) ext.push(Math.abs(eq.lo), Math.abs(eq.hi), eq.margin);
      const span = Math.max(1e-9, ...ext);
      const X = (v) => W / 2 + (W / 2 - 8) * v / span;
      const g = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, class: 'physforest', role: 'img',
                           'aria-label': 'tone-first ' + sig(t.tone.est) + ', noise-first ' + sig(t.noise.est) + ', difference ' + sig(t.diff.est)
                             + (eq ? ', its 90% interval ' + sig(eq.lo) + ' to ' + sig(eq.hi) + ' against ±' + sig(eq.margin) : '') });
      g.appendChild(sv('line', { x1: X(0), x2: X(0), y1: 0, y2: H, stroke: css('--line-2') }));
      // The groups, with the change in all eight between them.
      g.appendChild(sv('line', { x1: X(t.est).toFixed(1), x2: X(t.est).toFixed(1), y1: 2, y2: 24, stroke: css('--ink'), 'stroke-width': 1.5, class: 'g-all' }));
      [['tone', 8, css('--up')], ['noise', 18, css('--down')]].forEach(([gk, y, col]) => {
        const x = t[gk];
        if (x.est == null) return;
        if (x.se != null) g.appendChild(sv('line', { x1: X(x.est - 1.96 * x.se).toFixed(1), x2: X(x.est + 1.96 * x.se).toFixed(1), y1: y, y2: y, stroke: col }));
        g.appendChild(sv('circle', { cx: X(x.est).toFixed(1), cy: y, r: 3.2, fill: col, class: 'g-' + gk }));
      });
      // The difference: inside the band around zero is "the same".
      if (eq) {
        g.appendChild(sv('rect', { x: X(-eq.margin).toFixed(1), y: 29, width: (X(eq.margin) - X(-eq.margin)).toFixed(1), height: 12,
                                   fill: css('--chip'), stroke: css('--line'), class: 'g-band' }));
        g.appendChild(sv('line', { x1: X(eq.lo).toFixed(1), x2: X(eq.hi).toFixed(1), y1: 35, y2: 35, stroke: css('--ink'), 'stroke-width': 1.5, class: 'g-ci' }));
      }
      if (t.diff.est != null && isFinite(t.diff.est)) {
        g.appendChild(sv('rect', { x: (X(t.diff.est) - 3).toFixed(1), y: 32, width: 6, height: 6, fill: css('--ink'), class: 'g-diff' }));
      }
      return g;
    };
    const rows = list.slice(0, n).map((t, i) => {
      const tr = el('tr', { class: 'lead', 'data-rank': String(i + 1), tabindex: '0' }, [
        el('td', { class: 'num rank', text: String(i + 1) }),
        el('td', { class: 'lead-name' }, [el('div', { text: short(t.a) + ' – ' + short(t.b) }),
          el('div', { class: 'small muted', text: win(t.w) + ' · ' + band(t) + ' · ' + meth(t.m) })]),
        el('td', { class: 'num', 'data-label': 'all rats', text: f3(t.est) + ' (p ' + fp(t.p) + ')' }),
        el('td', { class: 'num up', 'data-label': 'tone-first', text: t.tone.est == null ? '—' : f3(t.tone.est) + ' ± ' + sig(t.tone.se) }),
        el('td', { class: 'num down', 'data-label': 'noise-first', text: t.noise.est == null ? '—' : f3(t.noise.est) + ' ± ' + sig(t.noise.se) }),
        el('td', { class: 'fig' }, [forest(t)]),
        el('td', { class: 'num', 'data-label': 'difference', text: t.diff.p == null ? '—' : f3(t.diff.est) + ' (p ' + fp(t.diff.p) + ')' }),
        el('td', { class: 'yn', 'data-label': 'same way in both', text: t.both_ways ? 'yes' : 'no' }),
        el('td', { class: 'yn', 'data-label': 'equivalent within ±½', text: t.equivalence ? (t.equivalence.within ? 'yes' : 'no')
          + ' · ±' + reach(t).toFixed(2) + '×' : '—' }),
      ]);
      const go = () => {
        const w0 = S0.windows.find((w) => w.id === t.w);
        M().showTab(w0 && w0.kind === 'contrast' ? 'c21' : 'main');
        M().go(Object.assign({}, t, { layer: kind === 'monolith_m' ? 'minus_fp' : 'raw', split: 'all' }));
      };
      tr.addEventListener('click', go);
      tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
      return tr;
    });
    return section('physleads', 'The leads, in each group of four', 'physical.leads', [
      seg([['monolith', 'The Monolith · Raw'], ['monolith_m', 'The Monolith · Minus FP'], ['contrast', 'Cue 2 − Cue 1']], kind,
        (id) => { P.leads = id; P.all = false; render(); }, 'physleadsel'),
      el('p', { class: 'small', id: 'physleadsay', text: (list.length === 1 ? 'Of this 1 point of interest: ' : 'Of these ' + list.length + ' points of interest: ') + n1(both, 'goes', 'go')
        + ' the same way in the tone-first and the noise-first rats; ' + n1(eq, 'is', 'are') + ' the same in both groups within half its own size '
        + '(equivalence, 90% interval); ' + n1(diff, 'differs', 'differ') + ' between the groups at p < .05 (uncorrected; chance alone would give about '
        + (0.05 * list.length).toFixed(1) + ').'
        + (med != null ? ' Of the ' + split + ' that every rat in both groups has, the median is equivalent within ±' + med.toFixed(2)
          + '× its own change' + (med > 0.5 ? ': with four rats a group, the interval is too wide for ±½.' : '.') : '')
        + (split < list.length ? ' The other ' + (list.length - split) + ' lack a rat in one group, so they are described, not tested.' : '') }),
      el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable physleadtbl', id: 'physleadtbl' }, [
        el('thead', {}, [el('tr', {}, ['#', 'Lead', 'Change, all rats', 'Tone-first', 'Noise-first', '', 'Difference', 'Same way in both',
          'Equivalent within ±½ · narrowest margin'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows)])]),
      list.length > 10 ? el('button', { type: 'button', class: 'more-btn', id: 'physall', text: P.all ? 'Show the top 10' : 'Show all ' + list.length,
                                        onclick: () => { P.all = !P.all; render(); } }) : null,
      el('p', { class: 'small muted', text: 'Each group’s change is pooled over its own four rats (± its standard error). In the picture, on one '
        + 'scale, the thin grey line is zero. Above: red is the tone-first rats, blue the noise-first, each with its 95% interval, and the black '
        + 'line the change in all eight. Below: the black square is the difference between the groups, the black line its 90% interval, and the '
        + 'grey box ±½ of the change in all eight — the interval must lie inside it for the two groups to count as the same. Click a lead to open '
        + 'it on the Monolith.' }),
    ]);
  }
  // Any comparison as a circuit, for a view chosen here.
  function viewNow() {
    const S0 = S(), st = M().state;
    const v = P.view || {};
    const measured = S0.windows.filter((w) => w.kind !== 'contrast');
    P.view = {
      w: measured.some((w) => w.id === v.w) ? v.w : (measured.some((w) => w.id === st.win) ? st.win : 'cue1'),
      b: S0.bands.some((b) => b.id === v.b) ? v.b : st.band,
      m: S0.methods.some((m) => m.id === v.m) ? v.m : st.method,
      layer: v.layer === 'raw' || v.layer === 'minus_fp' ? v.layer : st.layer,
      level: Number.isInteger(v.level) ? v.level : 1,
    };
    return P.view;
  }
  function circuitCard() {
    const S0 = S(), v = viewNow();
    const pick = (label, id, opts, cur, on) => el('label', { class: 'pctl' }, [el('span', { class: 'lab', text: label }),
      el('select', { id, onchange: (e) => on(e.target.value) }, opts.map(([x, text]) =>
        el('option', { value: x, selected: String(x) === String(cur) ? 'selected' : null, text })))]);
    const tn = P.cmp === 'tone_noise';
    const set = (patch) => { Object.assign(P.view, patch); render(); };
    const card = section('physcirc', 'Any comparison as a circuit', 'physical.circuit', [
      seg(['order', 'sound_noise', 'sound_tone', 'tone_noise', 'seat_abcd'].map((c) => [c, SAY[c].name, SAY[c].what]), P.cmp,
        (id) => { P.cmp = id; render(); }, 'physcmp'),
      el('p', { class: 'small', id: 'physcmpsay', text: SAY[P.cmp].what }),
      el('div', { class: 'progctl' }, [
        tn ? el('span', { class: 'small muted', text: 'Window: Cue 2 − Cue 1 (raw)' })
          : pick('Window', 'physw', S0.windows.filter((w) => w.kind !== 'contrast').map((w) => [w.id, w.label]), v.w, (x) => set({ w: x })),
        pick('Frequency', 'physb', S0.bands.map((b) => [b.id, b.named ? b.label : b.hz + ' Hz']), v.b, (x) => set({ b: x })),
        pick('Measure', 'physm', S0.methods.map((m) => [m.id, m.label]), v.m, (x) => set({ m: x })),
        tn ? null : pick('Layer', 'physl', [['raw', 'Raw'], ['minus_fp', 'Minus FP']], v.layer, (x) => set({ layer: x })),
        pick('Show edges', 'physlv', M().LEVELS.map((L0, i) => [i, L0[0]]), v.level, (x) => set({ level: Number(x) })),
      ]),
      el('div', { id: 'physcircsvg' }),
      el('p', { class: 'small muted', id: 'physcircsay' }),
    ]);
    drawCircuit();
    return card;
  }
  async function drawCircuit() {
    const S0 = S(), v = viewNow();
    const tn = P.cmp === 'tone_noise';
    const layer = tn ? 'raw' : v.layer;
    const name = 'phys_edges_' + layer + '__' + P.cmp;
    const w = tn ? S0.windows.findIndex((x) => x.id === 'c21') : S0.windows.findIndex((x) => x.id === v.w);
    const b = S0.bands.findIndex((x) => x.id === v.b), m = S0.methods.findIndex((x) => x.id === v.m);
    const seq = ++P.cseq;
    let A;
    try { A = await arrayOf(name); } catch (e) {
      const h0 = $('physcircsvg');
      if (h0) h0.textContent = 'Could not read ' + name + ': ' + e.message;
      return;
    }
    if (seq !== P.cseq) return;
    const host = $('physcircsvg');
    if (!host) return;
    host.innerHTML = '';
    const ok = M().LEVELS[v.level][1];
    const Wd = 520, Hd = 470, cx = 260, cy = 236, R = 170;
    const regs = S0.regions;
    const pos = regs.map((_r, i) => { const a = -Math.PI / 2 + (i + 0.5) * (2 * Math.PI / regs.length); return { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a), a }; });
    const edges = S0.pairs.map(([pa, pb], p) => ({ p, pa, pb, est: at(A, Q.est, w, b, m, p), pv: at(A, Q.p, w, b, m, p), k: at(A, Q.k, w, b, m, p) }));
    const tested = edges.filter((e) => isFinite(e.pv));
    const shown = tested.filter((e) => ok(e.pv));
    const max = Math.max(1e-12, ...tested.map((e) => Math.abs(e.est)));
    const svg = sv('svg', { viewBox: '0 0 ' + Wd + ' ' + Hd, width: '100%', class: 'mfig physcircuit', role: 'img', style: 'max-width:' + Wd + 'px',
                            'aria-label': SAY[P.cmp].name + ': ' + shown.length + ' of ' + tested.length + ' region pairs pass' });
    svg.appendChild(sv('circle', { cx, cy, r: R, fill: 'none', stroke: css('--ring') }));
    for (const e of shown.sort((x, y) => Math.abs(x.est) - Math.abs(y.est))) {
      const A0 = pos[e.pa], B0 = pos[e.pb];
      const mx = (A0.x + B0.x) / 2, my = (A0.y + B0.y) / 2;
      const qx = cx + (mx - cx) * 0.35, qy = cy + (my - cy) * 0.35;
      const path = sv('path', { d: 'M' + A0.x.toFixed(1) + ',' + A0.y.toFixed(1) + ' Q' + qx.toFixed(1) + ',' + qy.toFixed(1) + ' ' + B0.x.toFixed(1) + ',' + B0.y.toFixed(1),
        fill: 'none', stroke: css(e.est >= 0 ? '--up' : '--down'), 'stroke-width': (1.2 + 5 * Math.abs(e.est) / max).toFixed(2), 'stroke-opacity': 0.9,
        class: 'pedge', 'data-pair': String(e.p) });
      M().hover(path, [regs[e.pa] + ' – ' + regs[e.pb], SAY[P.cmp].name, 'difference ' + f3(e.est) + ', p ' + fp(e.pv) + ' (uncorrected), ' + e.k + ' rats']);
      svg.appendChild(path);
    }
    regs.forEach((name0, i) => {
      const p0 = pos[i];
      svg.appendChild(sv('circle', { cx: p0.x.toFixed(1), cy: p0.y.toFixed(1), r: 6, fill: css('--node'), stroke: css('--surface'), 'stroke-width': 2 }));
      const lx = cx + (R + 14) * Math.cos(p0.a), ly = cy + (R + 14) * Math.sin(p0.a);
      const anchor = Math.abs(Math.cos(p0.a)) < 0.2 ? 'middle' : (Math.cos(p0.a) > 0 ? 'start' : 'end');
      svg.appendChild(sv('text', { x: lx.toFixed(1), y: (ly + 4).toFixed(1), 'text-anchor': anchor, 'font-size': 12, fill: css('--ink-2') }, short(name0)));
    });
    host.appendChild(svg);
    const expect = (tested.length * 0.05).toFixed(1);
    $('physcircsay').textContent = shown.length + ' of ' + tested.length + ' tested region pairs pass ' + M().LEVELS[v.level][0]
      + (v.level ? ' (uncorrected; at p < .05 chance alone would give about ' + expect + ')' : '') + '. Red: higher in the first named; blue: lower.';
  }

  function render() {
    const pane = $('physpane');
    if (!pane) return;
    pane.innerHTML = '';
    if (P.loading && !P.data) { pane.appendChild(el('p', { class: 'loading', text: 'Reading the comparisons by sound…' })); return; }
    pane.appendChild(intro());
    if (!P.data) {
      pane.appendChild(section('physmissing', 'Not compared yet', null, [
        el('p', { text: 'This build of the Monolith has not been sorted by sound yet. It is worked out here, from the arrays already fetched, in a few '
          + 'minutes: every entry, both layers, with every relabelling of the rats beside it.' }),
        window.MONO_STATIC ? el('p', { class: 'small muted', text: 'Not in this copy: it opens in Jarvis.' })
          : el('button', { type: 'button', class: 'more-btn', id: 'physmake', disabled: P.making ? 'disabled' : null,
                           text: P.making ? 'Comparing: ' + (P.makeNote || 'starting') : 'Compare them now', onclick: make }),
        P.makeErr ? el('p', { class: 'small warn', text: P.makeErr }) : null,
      ]));
      return;
    }
    pane.appendChild(verdict());
    pane.appendChild(leads());
    pane.appendChild(circuitCard());
  }
  function show() {
    if (!P.data && !P.loading) load(); else render();
  }

  return {
    show, render, load, make,
    get state() { return { layer: P.layer, leads: P.leads, all: P.all, cmp: P.cmp, view: P.view ? Object.assign({}, P.view) : null,
                           data: P.data, err: P.err, making: P.making }; },
    set cmp(v) { P.cmp = v; render(); },
  };
})();
