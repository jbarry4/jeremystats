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
  const P = { data: null, err: null, loading: false, layer: 'raw', leads: 'monolith', all: false, cmp: 'order', leadView: 'sound',
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
                 what: 'In every rat, the change in its AB less the change in its CD: the same pair-against-pair differences, sorted by A/B/C/D.' },
  };

  // Each sound on its own: its name, its colour, and the comparisons.
  const SOUNDS = ['Click', 'Noise', 'High', 'Low'];
  const SND_SAY = { Click: 'Click', Noise: 'Noise', High: 'High tone', Low: 'Low tone' };
  const sndCol = (x) => css({ Click: '--down', Noise: '--arrow', High: '--up', Low: '--ok' }[x] || '--ink-2');
  const SND_PAIRS = [];
  SOUNDS.forEach((a, i) => SOUNDS.slice(i + 1).forEach((b) => SND_PAIRS.push(a + '-' + b)));
  const pairSay = (id) => id.split('-').map((x) => SND_SAY[x]).join(' − ');
  for (const pid of SND_PAIRS) {
    SAY['snd:' + pid] = { name: pairSay(pid), by: 'sound',
      what: 'In every rat, the change while ' + SND_SAY[pid.split('-')[0]] + ' played less the change while ' + SND_SAY[pid.split('-')[1]]
        + ' played, each in the cue window it had (A, B, C or D), pooled over all eight rats.' };
  }
  SAY['snd:omni'] = { name: 'Do the four sounds differ?', by: 'sound',
    what: 'A repeated-measures ANOVA over each rat’s four sound changes, all eight rats: drawn where the four differ; thicker, the bigger the '
      + 'gap between the sound that changed most and the one that changed least.' };

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
  async function arrayOf(name, nw) {
    if (P.arr.has(name)) return P.arr.get(name);
    const S0 = S();
    const shape = [6, nw || S0.windows.length, S0.bands.length, S0.methods.length, S0.pairs.length];
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
  // The view of the leads: each sound on its own, or the two groups.
  const LEADVIEWS = [['sound', 'Each sound on its own'], ['group', 'Tone-first against noise-first']];
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
    const X = window.MONO_EXPLAIN;
    const sheet = [el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable physseats', id: 'physseats' }, [
        el('thead', {}, [el('tr', {}, ['Rat', 'Group', 'A', 'B', 'C', 'D'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows)])]),
      el('p', { class: 'small muted', text: 'A opens the AB pair and C the CD pair; B and D close them. Noise-first rats hear Click or Noise in '
        + 'Cue 1 and a tone in Cue 2; tone-first rats the other way round. Red: a tone; blue: Click or Noise.' })];
    const sortHost = el('div', { id: 'physsort' });
    const card = section('physintro', 'Physical cue against balanced cue', 'physical', [
      ans ? el('div', { class: 'physanswer ' + (ans.effect === false ? 'ok' : ans.effect ? 'warn' : ''), id: 'physanswer' }, [
        el('p', { class: 'head', text: ans.head }),
        X ? X.more('the details', (body) => { body.appendChild(el('p', { id: 'physanswersay', text: ans.say })); return null; }, { key: 'phys-answer', eager: true })
          : el('p', { id: 'physanswersay', text: ans.say })]) : null,
      el('p', { class: 'takeaway', id: 'physwhat', text: 'The Monolith calls the cues A, B, C and D, and which sound is which changes from rat to rat. '
        + 'This tab sorts the rats by sound instead.' }),
      sortHost,
      X ? X.more('the identity sheet, as a table', (body) => { sheet.forEach((x) => body.appendChild(x)); return null; }, { key: 'phys-sheet', eager: true })
        : el('div', {}, sheet),
    ]);
    if (X) X.playOnce('phys-sort', sortHost, X.soundSort(sortHost, I));
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
    add('Cue 2 − Cue 1', 'seat', (sc.contrast || {}).raw, pt.n ? { rank: pt.balanced_rank, n: pt.n, of: 'shuffles of the rats' } : null, 'contrast');
    add(SAY.seat_abcd.name, 'seat', ((D.counts || {}).seat_abcd || {})[L], null, 'seat_abcd');
    const po = ((perm.order || {})[L]) || {};
    add(SAY.order.name, 'sound', ((D.counts || {}).order || {})[L], po.n ? { rank: po.rank, n: po.n, of: 'splits of the rats into two fours' } : null, 'order');
    for (const cid of ['sound_noise', 'sound_tone']) {
      const ps = ((perm[cid] || {})[L]) || {};
      add(SAY[cid].name, 'sound', ((D.counts || {})[cid] || {})[L], ps.n ? { rank: ps.rank, n: ps.n, of: 'shuffles of its four rats',
        seat: ps.seat_rank } : null, cid);
    }
    add(SAY.tone_noise.name, 'sound', ((D.counts || {}).tone_noise || {}).raw, pt.n ? { rank: pt.rank, n: pt.n, of: 'shuffles of the rats' } : null, 'tone_noise');
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
    const rk = (r) => (r.extra && r.extra.rank ? ', ranking ' + r.extra.rank + ' of ' + r.extra.n : '');
    for (const L of ['raw', 'minus_fp']) {
      for (const r of rowsOf(L).filter((x) => x.by === 'sound' && x.c).concat(L === 'raw' ? soundRows(L).filter((x) => x.test && x.c) : [])) {
        if (r.id === 'tone_noise' && L !== 'raw') continue;
        n++;
        if (!atChance(r)) above.push(r.name + (r.id === 'tone_noise' || r.id.indexOf('snd:') === 0 ? '' : ' (' + LAYER_SAY[L] + ')') + rk(r));
      }
    }
    const omr = soundRows('raw').find((x) => x.id === 'snd:omni');
    const omSay = omr && omr.c && omr.extra ? ' The four sounds taken together are ' + (atChance(omr) ? 'at chance' : 'above chance')
      + ' (ranking ' + omr.extra.rank + ' of ' + omr.extra.n + ' shuffles).' : '';
    const lead = ((D.leads || {}).monolith || {}).raw || [];
    const same = lead.filter((t) => t.both_ways).length;
    const dif = lead.filter((t) => t.diff && t.diff.p != null && t.diff.p < 0.05).length;
    const leadSay = lead.length ? ' Of the Monolith’s ' + lead.length + ' top results, ' + same + ' go the same way in the tone-first and the noise-first '
      + 'rats, and ' + dif + ' differ between them at p < .05, about what chance alone gives (' + (0.05 * lead.length).toFixed(1) + ').' : '';
    if (!n) return { effect: null, head: 'Not answered yet', say: 'Nothing was compared by sound.' };
    if (!above.length) {
      return { effect: false, head: 'The answer: no sign that the physical sound had an effect.',
               say: 'Sorted by sound instead of by A/B/C/D, and sound by sound (each sound’s own change against every other’s, within each '
                 + 'rat), the rats pass no more tests than any other way of sorting the same eight rats, in all ' + n
                 + ' comparisons by sound (Raw and Minus FP).' + leadSay
                 + ' So the Monolith’s results are about the cue’s place in the task (A, B, C, D), not about which sound it was. '
                 + 'With four rats a group, only a large effect of the sound could have been seen: a small one cannot be ruled out.' };
    }
    return { effect: true, head: 'The answer: possibly, in ' + above.length + ' of ' + n + ' comparisons by sound.',
             say: above.join('; ') + (above.length === 1 ? ' sorts' : ' sort') + ' the rats by sound better than nearly every other way of '
               + 'sorting them (the top 5%): there the sound may have left a mark.' + omSay + ' The other ' + (n - above.length)
               + ' comparisons by sound sit at chance. Every p is uncorrected: with ' + n + ' comparisons looked at, chance alone puts about '
               + (0.05 * n).toFixed(1) + ' of them in the top 5%. Check a top result against ' + (above.length === 1 ? 'it' : 'them')
               + ' before reading it as about the cue.' + leadSay };
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
      el('thead', {}, [el('tr', {}, ['Comparison', 'Sorted by', 'Tested', 'p < .05', 'By chance', '× chance', '', 'Against shuffle']
        .map((h) => el('th', { text: h })))]),
      el('tbody', {}, rows.map((r) => el('tr', { 'data-cmp': r.id, class: r.by }, [
        el('th', { text: r.name }), el('td', { class: 'by', 'data-label': 'sorted by', text: r.by === 'seat' ? 'A/B/C/D' : r.by }),
        el('td', { class: 'num', 'data-label': 'tested', text: fmt((r.c || {}).tested) }),
        el('td', { class: 'num', 'data-label': 'p < .05', text: fmt((r.c || {}).p05) }),
        el('td', { class: 'num', 'data-label': 'by chance', text: fmt((r.c || {}).chance_p05) }),
        el('td', { class: 'num', 'data-label': '× chance', text: ratio(r.c) == null ? '—' : ratio(r.c).toFixed(2) }), el('td', { class: 'bar' }, [bar(r)]),
        el('td', { class: 'small rel', text: r.extra && r.extra.rank ? 'ranks ' + r.extra.rank + ' of ' + r.extra.n + ' ' + r.extra.of
          + (r.extra.seat ? ' (by A/B/C/D: ' + r.extra.seat + ')' : '') + (r.by === 'sound' ? (atChance(r) ? ' · at chance' : ' · above chance') : '') : '—' }),
      ]))),
    ]);
    const bySound = rows.filter((r) => r.by === 'sound' && r.c);
    const flat = bySound.filter(atChance);
    const above = bySound.filter((r) => !atChance(r));
    const lead = !bySound.length ? 'Nothing was compared by sound in Minus FP: the tests between sounds are Raw only.'
      : above.length === 0
        ? 'Sorted by group and by pair, every comparison by sound here sits at chance: the rats pass no more stat tests than an ordinary shuffle '
          + 'of the same rats does. (Each sound on its own, below, is the other half of the test.)'
        : above.map((r) => r.name).join('; ') + (above.length === 1 ? ' passes' : ' pass') + ' more stat tests than '
          + (above.length === 1 ? 'nearly every shuffle of its rats: look at it' : 'nearly every shuffle of their rats: look at them')
          + ' before reading a top result as about the cue rather than the sound. '
          + (flat.length ? flat.length + ' of the ' + bySound.length + ' comparisons by sound sit at chance.' : '');
    const X = window.MONO_EXPLAIN;
    const readIt = 'Tested over every window, frequency, measure and region pair the Monolith tests (tone − noise and Cue 2 − Cue 1: '
      + 'the contrast’s own stat tests, raw only). The solid line on each bar is chance; the dashed one is what made-up data with no change at all '
      + 'gave (' + (100 * (D.control_p05 || 0.055)).toFixed(1) + '%, ' + (D.control_say || '') + '). Neighbouring frequencies and measures move '
      + 'together, so a count can stray from chance by luck: the shuffles are the fair yardstick, the same rats sorted every other way. '
      + 'Every p is uncorrected. With four rats a group, “no effect” can only mean none large enough to see.';
    return section('physverdictcard', 'Across the whole Monolith: by A/B/C/D and by sound, against chance', 'physical.verdict', [
      seg([['raw', 'Raw'], ['minus_fp', 'Minus FP']], L, (id) => { P.layer = id; render(); }, 'physlayer'),
      el('p', { class: 'physsay ' + (above.length ? 'warn' : 'ok'), id: 'physsay', text: lead }),
      el('div', { class: 'dtwrap' }, [tbl]),
      X ? X.more('how to read it', (body) => { body.appendChild(el('p', { class: 'small', id: 'physreadit', text: readIt })); return null; },
        { key: 'phys-readit', eager: true }) : el('p', { class: 'small muted', text: readIt }),
      X ? X.more('every shuffle of the same rats, played', (body) => { body.appendChild(relabelFigures()); return null; }, { key: 'phys-shuffles' })
        : relabelFigures(),
    ]);
  }
  // Each sound on its own, one layer: its own change, every pair of sounds,
  // and the four together; the pairs and the four are the tests by sound.
  // Each sound's own change is the layer's; the tests between sounds are
  // raw in both, as Cue 2 − Cue 1 is: within a rat the same rest comes off
  // every cue window of a day, so it cancels from a difference between two
  // sounds, and Minus FP would only add the rest's noise.
  function soundRows(L) {
    const Sd = (P.data || {}).sound || {};
    const Co = (Sd.counts || {})[L] || {};
    const C = (Sd.counts || {}).raw || {};
    const Pm = (Sd.perm || {}).raw || {};
    const rows = SOUNDS.map((x) => ({ id: 'own:' + x, name: SND_SAY[x] + ': its own change', by: 'sound', test: false, c: Co[x], extra: null }));
    for (const pid of SND_PAIRS) {
      const pm = (Pm.pairs || {})[pid] || {};
      rows.push({ id: 'snd:' + pid, name: pairSay(pid), by: 'sound', test: true, c: C[pid],
                  extra: pm.n ? { rank: pm.rank, n: pm.n, of: 'shuffles of the rats' } : null });
    }
    const om = Pm.omni || {};
    rows.push({ id: 'snd:omni', name: 'All four at once (repeated-measures ANOVA)', by: 'sound', test: true, c: C.omni,
                extra: om.n ? { rank: om.rank, n: om.n, of: 'shuffles of the four within each rat' } : null });
    return rows;
  }
  function soundCard() {
    const D = P.data;
    const Sd = D.sound;
    if (!Sd || !Sd.counts || !Object.keys(Sd.counts).length) return null;
    const L = P.layer;
    const rows = soundRows(L);
    const tests = rows.filter((r) => r.test && r.c);
    const above = tests.filter((r) => !atChance(r));
    const say = !tests.length ? 'Not compared in Minus FP: Raw only.'
      : !above.length ? 'Sound by sound, nothing stands out: no pair of sounds, and not the four together, passes more stat tests than an ordinary '
          + 'shuffle of the same rats. The rats’ changes while each sound played are alike.'
        : above.map((r) => r.name).join('; ') + (above.length === 1 ? ' passes' : ' pass') + ' more stat tests than nearly every shuffle of '
          + 'the rats: there the sounds may differ.';
    const tbl = el('table', { class: 'linetable physverdict physsound', id: 'physsound' }, [
      el('thead', {}, [el('tr', {}, ['Comparison', 'Tested', 'p < .05', 'By chance', '× chance', 'Against shuffle'].map((h) => el('th', { text: h })))]),
      el('tbody', {}, rows.map((r) => el('tr', { 'data-cmp': r.id, class: r.test ? 'sound' : 'seat' }, [
        el('th', {}, [el('span', { class: 'nm' }, [r.id.indexOf('own:') === 0 ? el('b', { class: 'sw', style: 'background:' + sndCol(r.id.slice(4)) }) : null,
          r.name])]),
        el('td', { class: 'num', 'data-label': 'tested', text: fmt((r.c || {}).tested) }),
        el('td', { class: 'num', 'data-label': 'p < .05', text: fmt((r.c || {}).p05) }),
        el('td', { class: 'num', 'data-label': 'by chance', text: fmt((r.c || {}).chance_p05) }),
        el('td', { class: 'num', 'data-label': '× chance', text: ratio(r.c) == null ? '—' : ratio(r.c).toFixed(2) }),
        el('td', { class: 'small rel', text: r.extra && r.extra.rank ? 'ranks ' + r.extra.rank + ' of ' + r.extra.n + ' ' + r.extra.of
          + (atChance(r) ? ' · at chance' : ' · above chance') : r.test ? '—' : 'not a test of the sound: the Monolith’s own change, while it played' }),
      ]))),
    ]);
    const om = (((Sd.perm || {})[L] || {}).omni) || {};
    const figs = el('div', { class: 'physhists' });
    const X = window.MONO_EXPLAIN;
    if (X && om.counts && om.counts.length > 1) {
      const h = el('div', { 'data-perm': 'omni' });
      figs.appendChild(h);
      const G = (P.data || {}).groups || { noise: [], tone: [] };
      const p = X.shuffle(h, { counts: om.counts, realIndex: 0, observed: om.observed, rank: om.rank, expected: (((Sd.counts || {})[L] || {}).omni || {}).chance_p05,
                               kind: 'random', rats: (Sd.rats || (G.noise || []).concat(G.tone || [])).map((r) => 'J' + r), realLabel: 'the sounds as named',
                               title: 'The four sounds shuffled within each rat (' + (om.n - 1) + ')',
                               say: 'Each shuffle deals each rat’s four sound changes out again, at random, and counts again.',
                               rankSay: 'The sounds as named rank ' + om.rank + ' of ' + om.n + ': '
                                 + (om.rank > cut(om.n) ? 'an ordinary shuffle.' : 'among the very few shuffles that pass the most stat tests.') });
      X.playOnce('phys-shuf-omni-' + L, h, p);
    } else if (om.counts && om.counts.length > 1) {
      figs.appendChild(el('div', { 'data-perm': 'omni' }, [hist(om.counts.slice(1), [
        { id: 'chance', v: (((Sd.counts || {})[L] || {}).omni || {}).chance_p05, label: 'chance (5%)', color: css('--ink-3'), dash: true },
        { id: 'omni', v: om.observed, label: 'the sounds as named', color: css('--up') }], 'The four sounds shuffled within each rat (' + (om.n - 1) + ')'),
        el('p', { class: 'small muted', text: 'The sounds as named rank ' + om.rank + ' of ' + om.n + ': '
          + (om.rank > cut(om.n) ? 'an ordinary labelling.' : 'among the very few labellings that pass the most stat tests.') })]));
    }
    const how = 'For every rat, the change from Precon1 to Precon4 while each sound played, in the cue window that sound had (A, B, C or D): '
      + 'a different one for different rats (J3’s Noise is its C, J4’s its B). Every rat heard all four, so each pair of sounds is '
      + 'compared within each rat, all eight rats, and the four together by a repeated-measures ANOVA. Uncorrected. Raw or Minus FP chooses '
      + 'each sound’s own change; the comparisons between sounds are raw in both, as Cue 2 − Cue 1 is: the same FP comes off every '
      + 'window of a rat’s day, so it cancels from the difference. Cue windows only: the baselines, the transitions and the whole pair '
      + 'hold no one sound. When two sounds share a pair (A and B, say) their windows come from the same trials, and that covariance is not '
      + 'taken off, which makes those tests a little conservative.';
    return section('physsoundcard', 'Each sound on its own: Precon1 → Precon4 while it plays', 'physical.sound', [
      seg([['raw', 'Raw'], ['minus_fp', 'Minus FP']], L, (id) => { P.layer = id; render(); }, 'physsndlayer'),
      el('p', { class: 'physsay ' + (above.length ? 'warn' : 'ok'), id: 'physsndsay', text: say }),
      el('div', { class: 'swkey' }, SOUNDS.map((x) => el('span', {}, [el('b', { class: 'sw', style: 'background:' + sndCol(x) }), SND_SAY[x]]))),
      el('div', { class: 'dtwrap' }, [tbl]),
      X ? X.more('how each sound is measured', (body) => { body.appendChild(el('p', { class: 'small', id: 'physsndhow', text: how })); return null; },
        { key: 'phys-sndhow', eager: true }) : el('p', { class: 'small muted', text: how }),
      X && figs.childElementCount ? X.more('the four sounds shuffled, played', (body) => { body.appendChild(figs); return null; }, { key: 'phys-omni' }) : figs,
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
    svg.appendChild(sv('text', { x: W / 2, y: H - 3, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'stat tests with p < .05'));
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
  // The rats as the shuffles list them, and where each sorting by sound
  // sits among them: the split into tone-first and noise-first among every
  // split into two fours; a sorting by sound among every way of signing
  // the same rats (the first rat's sign fixed, as backend/monolith.py does).
  function soundSigns(rats, signOf) {
    const s = rats.map(signOf);
    if (!s.length || s.some((x) => !x)) return null;
    let i = 0;
    for (let j = 1; j < s.length; j++) if (s[j] * s[0] < 0) i |= 1 << (j - 1);
    return i;
  }
  function relabelFigures() {
    const D = P.data;
    const L = P.layer;
    const X = window.MONO_EXPLAIN;
    if (X) return shuffleFigures(D, L, X);
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
          + (po.rank > cut(po.n) ? 'an ordinary split.' : 'among the very few splits that pass the most stat tests.') })]));
    }
    for (const cid of ['sound_noise', 'sound_tone']) {
      const ps = ((D.perm || {})[cid] || {})[L] || {};
      if (!ps.counts || !ps.counts.length) continue;
      const who = (ps.rats || []).map((r) => 'J' + r).join(', ');
      box.appendChild(el('div', { 'data-perm': cid }, [hist(ps.counts, [chance(cid, L),
                                                                        { id: 'seat', v: ps.seat, label: 'AB − CD (by A/B/C/D)', color: css('--arrow') },
                                                                        { id: cid, v: ps.observed, label: 'by sound', color: css('--up') }],
        'Every shuffle of ' + who + '’s AB − CD (' + ps.n + ')'),
        el('p', { class: 'small muted', text: SAY[cid].name + ' ranks ' + ps.rank + ' of ' + ps.n + '; the same rats by A/B/C/D, ' + ps.seat_rank
          + ' of ' + ps.n + '. With four rats there are only eight ways, so a rank says little alone; it is one more look.' })]));
    }
    if (pt.counts && pt.counts.length) {
      box.appendChild(el('div', { 'data-perm': 'tone_noise' }, [hist(pt.counts, [chance('tone_noise', 'raw'),
                                                                                  { id: 'balanced', v: pt.balanced, label: 'Cue 2 − Cue 1', color: css('--arrow') },
                                                                                  { id: 'tone_noise', v: pt.observed, label: 'tone − noise', color: css('--up') }],
        'Every shuffle of the rats’ Cue 2 − Cue 1 (' + pt.n + ')'),
        el('p', { class: 'small muted', text: 'Cue 2 − Cue 1 as it stands ranks ' + pt.balanced_rank + ' of ' + pt.n + '; signed as tone − noise, '
          + pt.rank + ' of ' + pt.n + '. Had the sounds driven Cue 2 − Cue 1, tone − noise would rank near the top.' })]));
    }
    return box;
  }
  // The same, played: each shuffle's count dropping in, the real sorting last.
  function shuffleFigures(D, L, X) {
    const ch = (cid, layer) => (((D.counts || {})[cid] || {})[layer] || {}).chance_p05;
    const I = S().identity || { seats: {} };
    const seat = (r) => ((I.seats || {})[r] || {});
    const G = D.groups || { noise: [], tone: [] };
    const all = (D.rats && D.rats.length ? D.rats : (G.noise || []).concat(G.tone || [])).slice().sort((a, b) => a - b);
    const groupOf = (r) => ((G.noise || []).includes(r) ? 'noise' : (G.tone || []).includes(r) ? 'tone' : null);
    const box = el('div', { class: 'physhists physshuffles' });
    const piece = (id, o, say) => {
      const h = el('div', { 'data-perm': id });
      box.appendChild(h);
      X.playOnce('phys-shuf-' + id + '-' + L, h, X.shuffle(h, Object.assign({ rankSay: say }, o)));
    };
    const po = ((D.perm || {}).order || {})[L] || {};
    if (po.counts && po.counts.length) {
      const first = all.map((_r, i) => i).filter((i) => groupOf(all[i]) === groupOf(all[0]));
      const real = X.splits(all.length).findIndex((s) => s.join() === first.join());
      piece('order', { counts: po.counts, realIndex: real >= 0 ? real : null, observed: po.observed, rank: po.rank, expected: ch('order', L),
                       kind: 'split', rats: all.map((r) => 'J' + r), realLabel: 'tone-first vs noise-first',
                       title: 'Every split of the rats into two fours (' + po.n + ')',
                       say: 'Each split puts four rats on one side (red) and four on the other, and counts again.' },
        'Tone-first against noise-first ranks ' + po.rank + ' of ' + po.n + ': ' + (po.rank > cut(po.n) ? 'an ordinary split.' : 'among the very few splits that pass the most stat tests.'));
    }
    for (const cid of ['sound_noise', 'sound_tone']) {
      const ps = ((D.perm || {})[cid] || {})[L] || {};
      if (!ps.counts || !ps.counts.length) continue;
      const rats = ps.rats || [];
      const real = soundSigns(rats, (r) => (['Click', 'High'].includes(seat(r).A) ? 1 : seat(r).A ? -1 : 0));
      piece(cid, { counts: ps.counts, realIndex: real, observed: ps.observed, rank: ps.rank, expected: ch(cid, L), kind: 'sign',
                   rats: rats.map((r) => 'J' + r), realLabel: 'by sound', title: 'Every shuffle of ' + rats.map((r) => 'J' + r).join(', ') + '’s AB − CD (' + ps.n + ')',
                   marks: [{ id: 'seat', v: ps.seat, label: 'AB − CD (by A/B/C/D)', color: css('--arrow') }],
                   say: 'Each shuffle flips some rats’ AB − CD, and counts again.' },
        SAY[cid].name + ' ranks ' + ps.rank + ' of ' + ps.n + '; by A/B/C/D, ' + ps.seat_rank + ' of ' + ps.n + '. Eight ways only: one more look, no more.');
    }
    const pt = ((D.perm || {}).tone_noise || {}).raw || {};
    if (pt.counts && pt.counts.length) {
      const real = soundSigns(all, (r) => (groupOf(r) === 'noise' ? 1 : groupOf(r) === 'tone' ? -1 : 0));
      piece('tone_noise', { counts: pt.counts, realIndex: real, observed: pt.observed, rank: pt.rank, expected: ch('tone_noise', 'raw'), kind: 'sign',
                            rats: all.map((r) => 'J' + r), realLabel: 'tone − noise', title: 'Every shuffle of the rats’ Cue 2 − Cue 1 (' + pt.n + ')',
                            marks: [{ id: 'balanced', v: pt.balanced, label: 'Cue 2 − Cue 1 as it stands', color: css('--arrow') }],
                            say: 'Each shuffle flips some rats’ Cue 2 − Cue 1, and counts again.' },
        'As it stands it ranks ' + pt.balanced_rank + ' of ' + pt.n + '; signed as tone − noise, ' + pt.rank + ' of ' + pt.n
          + '. Had the sounds driven Cue 2 − Cue 1, tone − noise would rank near the top.');
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
    const W = 170;
    // One scale for a lead's two pictures: its groups, and their difference.
    const spanOf = (t) => {
      const eq = t.equivalence;
      const ext = [t.est, t.tone.est, t.noise.est, t.diff.est].filter((v) => v != null && isFinite(v)).map(Math.abs);
      for (const g of [t.tone, t.noise]) if (g.est != null && g.se != null) ext.push(Math.abs(g.est) + 1.96 * g.se);
      if (eq) ext.push(Math.abs(eq.lo), Math.abs(eq.hi), eq.margin);
      return Math.max(1e-9, ...ext);
    };
    // The two groups and all eight: each group's change with its 95%
    // interval, the black line the change in all eight.
    const forest = (t) => {
      const H = 28, span = spanOf(t);
      const X = (v) => W / 2 + (W / 2 - 8) * v / span;
      const g = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, class: 'physforest', role: 'img',
                           'aria-label': 'tone-first ' + sig(t.tone.est) + ', noise-first ' + sig(t.noise.est) + ', all eight ' + sig(t.est) });
      g.appendChild(sv('line', { x1: X(0), x2: X(0), y1: 0, y2: H, stroke: css('--line-2') }));
      g.appendChild(sv('line', { x1: X(t.est).toFixed(1), x2: X(t.est).toFixed(1), y1: 2, y2: H - 2, stroke: css('--ink'), 'stroke-width': 1.5, class: 'g-all' }));
      [['tone', 9, css('--up')], ['noise', 19, css('--down')]].forEach(([gk, y, col]) => {
        const x = t[gk];
        if (x.est == null) return;
        if (x.se != null) g.appendChild(sv('line', { x1: X(x.est - 1.96 * x.se).toFixed(1), x2: X(x.est + 1.96 * x.se).toFixed(1), y1: y, y2: y, stroke: col }));
        g.appendChild(sv('circle', { cx: X(x.est).toFixed(1), cy: y, r: 3.2, fill: col, class: 'g-' + gk }));
      });
      return g;
    };
    // Their difference, on the same scale: the square and its 90% interval,
    // against the box of ±½ the change in all eight, around zero.
    const diffFig = (t) => {
      const H = 16, span = spanOf(t), eq = t.equivalence;
      const X = (v) => W / 2 + (W / 2 - 8) * v / span;
      const g = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, class: 'physdiff', role: 'img',
                           'aria-label': 'difference ' + sig(t.diff.est) + (eq ? ', its 90% interval ' + sig(eq.lo) + ' to ' + sig(eq.hi)
                             + ' against ±' + sig(eq.margin) : '') });
      g.appendChild(sv('line', { x1: X(0), x2: X(0), y1: 0, y2: H, stroke: css('--line-2'), class: 'g-zero' }));
      if (eq) {
        g.appendChild(sv('rect', { x: X(-eq.margin).toFixed(1), y: 2, width: (X(eq.margin) - X(-eq.margin)).toFixed(1), height: 12,
                                   fill: css('--chip'), stroke: css('--line'), class: 'g-band' }));
        g.appendChild(sv('line', { x1: X(eq.lo).toFixed(1), x2: X(eq.hi).toFixed(1), y1: 8, y2: 8, stroke: css('--ink'), 'stroke-width': 1.5, class: 'g-ci' }));
      }
      if (t.diff.est != null && isFinite(t.diff.est)) {
        g.appendChild(sv('rect', { x: (X(t.diff.est) - 3).toFixed(1), y: 5, width: 6, height: 6, fill: css('--ink'), class: 'g-diff' }));
      }
      return g;
    };
    // The four sounds of one lead: each one's change with its 95% interval,
    // a row each, the black line the change in all eight.
    const soundFig = (t) => {
      const sd = (t.sound || {}).sounds || [];
      const H = 8 + 10 * sd.length, Ws = 190;
      const have = sd.filter((x) => x.est != null);
      const mean4 = have.length ? have.reduce((a2, x) => a2 + x.est, 0) / have.length : null;
      const ext = [Math.abs(mean4 || 0)];
      for (const x of sd) if (x.est != null) ext.push(Math.abs(x.est) + 1.96 * (x.se || 0));
      const span = Math.max(1e-9, ...ext);
      const X = (v) => Ws / 2 + (Ws / 2 - 8) * v / span;
      const g = sv('svg', { viewBox: '0 0 ' + Ws + ' ' + H, width: Ws, height: H, class: 'physsndfig', role: 'img',
                           'aria-label': sd.map((x) => SND_SAY[x.sound] + ' ' + sig(x.est)).join(', ') });
      g.appendChild(sv('line', { x1: X(0), x2: X(0), y1: 0, y2: H, stroke: css('--line-2') }));
      if (mean4 != null) g.appendChild(sv('line', { x1: X(mean4).toFixed(1), x2: X(mean4).toFixed(1), y1: 2, y2: H - 2, stroke: css('--ink'),
                                                    'stroke-width': 1.2, class: 's-mean' }));
      sd.forEach((x, i) => {
        if (x.est == null) return;
        const y = 6 + 10 * i, col = sndCol(x.sound);
        if (x.se != null) g.appendChild(sv('line', { x1: X(x.est - 1.96 * x.se).toFixed(1), x2: X(x.est + 1.96 * x.se).toFixed(1), y1: y, y2: y, stroke: col }));
        g.appendChild(sv('circle', { cx: X(x.est).toFixed(1), cy: y, r: 3, fill: col, class: 's-' + x.sound }));
      });
      return g;
    };
    const view = P.leadView === 'group' || !list.some((t) => t.sound) ? 'group' : 'sound';
    // A group's change, ± its standard error, and how many rats when it is
    // fewer than four; nothing to say an interval needs at least three.
    const grpSay = (x) => (x.est == null ? '—' : f3(x.est) + (x.se != null ? ' ± ' + sig(x.se) : ' (' + (x.k || 0) + ' rats: no interval)')
      + (x.se != null && x.k != null && x.k < 4 ? ' · ' + x.k + ' rats' : ''));
    // What the pictures draw, said above the table.
    const keyRow = (items) => el('div', { class: 'swkey figkey' }, items.map(([mark, text]) => el('span', {}, [mark, text])));
    const dot = (col) => el('b', { class: 'sw', style: 'background:' + col });
    const bar = (cls) => el('i', { class: 'kmark ' + cls });
    const sdiff = list.filter((t) => t.sound && t.sound.omni && t.sound.omni.p != null && t.sound.omni.p < 0.05).length;
    const stested = list.filter((t) => t.sound && t.sound.omni && t.sound.omni.p != null).length;
    const top = {};
    for (const t of list) {
      const sd = ((t.sound || {}).sounds || []).filter((x) => x.est != null);
      if (!sd.length) continue;
      const best = sd.reduce((a2, b2) => (Math.abs(b2.est) > Math.abs(a2.est) ? b2 : a2));
      top[best.sound] = (top[best.sound] || 0) + 1;
    }
    const rows = list.slice(0, n).map((t, i) => {
      const head = [
        el('td', { class: 'num rank', text: String(i + 1) }),
        el('td', { class: 'lead-name' }, [el('div', { text: short(t.a) + ' – ' + short(t.b) }),
          el('div', { class: 'small muted', text: win(t.w) + ' · ' + band(t) + ' · ' + meth(t.m) })]),
        el('td', { class: 'num', 'data-label': 'all rats', text: f3(t.est) + ' (p ' + fp(t.p) + ')' })];
      const sd = (t.sound || {}).sounds || [];
      const om = (t.sound || {}).omni || {};
      const tr = el('tr', { class: 'lead', 'data-rank': String(i + 1), tabindex: '0' }, view === 'sound' ? head.concat(
        SOUNDS.map((x) => { const y = sd.find((z) => z.sound === x) || {};
          return el('td', { class: 'num snd', 'data-label': SND_SAY[x], style: 'color:' + sndCol(x),
                            text: y.est == null ? '—' : f3(y.est) + ' ± ' + sig(y.se) }); }),
        [el('td', { class: 'fig' }, [soundFig(t)]),
         el('td', { class: 'num', 'data-label': 'the four differ', text: om.p == null ? '—'
           : (om.p < 0.05 ? 'yes' : 'no') + ' (p ' + fp(om.p) + ', F ' + sig(om.F) + ')' })]) : head.concat([
        el('td', { class: 'num up', 'data-label': 'tone-first', text: grpSay(t.tone) }),
        el('td', { class: 'num down', 'data-label': 'noise-first', text: grpSay(t.noise) }),
        el('td', { class: 'fig' }, [forest(t)]),
        el('td', { class: 'num', 'data-label': 'difference' }, [el('div', { class: t.diff.p == null ? 'muted' : null,
          text: t.diff.p == null ? 'not tested: ' + Math.min(t.tone.k || 0, t.noise.k || 0) + ' rats in a group, 3 needed' : f3(t.diff.est) + ' (p ' + fp(t.diff.p) + ')' }),
          t.diff.p == null ? null : diffFig(t)]),
        el('td', { class: 'yn', 'data-label': 'same way in both', text: t.both_ways ? 'yes' : 'no' }),
        el('td', { class: 'yn', 'data-label': 'equivalent within ±½', text: t.equivalence ? (t.equivalence.within ? 'yes' : 'no')
          + ' · ±' + reach(t).toFixed(2) + '×' : '—' })]));
      const go = () => {
        const w0 = S0.windows.find((w) => w.id === t.w);
        M().showTab(w0 && w0.kind === 'contrast' ? 'c21' : 'main');
        M().go(Object.assign({}, t, { layer: kind === 'monolith_m' ? 'minus_fp' : 'raw', split: 'all' }));
      };
      tr.addEventListener('click', go);
      tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
      return tr;
    });
    const sndSay = 'Of these ' + list.length + ' top results, the four sounds’ changes differ at p < .05 (uncorrected, repeated-measures '
      + 'ANOVA, all eight rats) for ' + sdiff + ' of the ' + stested + ' tested; chance alone would give about ' + (0.05 * stested).toFixed(1) + '. '
      + 'The sound that changed most: ' + SOUNDS.filter((x) => top[x]).map((x) => SND_SAY[x] + ' in ' + top[x]).join(', ')
      + (Object.keys(top).length ? '' : 'none') + '. Each is measured at the top result’s own frequency, measure and region pair, while that sound played.';
    const headSnd = ['#', 'Top result', 'Change, all rats'].concat(SOUNDS.map((x) => SND_SAY[x]), ['', 'Do the four differ?']);
    const headGrp = ['#', 'Top result', 'Change, all rats', 'Tone-first', 'Noise-first', '', 'Difference', 'Same way in both',
      'Equivalent within ±½ · narrowest margin'];
    return section('physleads', 'The top results, sound by sound and in each group of four', 'physical.leads', [
      seg([['monolith', 'The Monolith · Raw'], ['monolith_m', 'The Monolith · Minus FP'], ['contrast', 'Cue 2 − Cue 1']], kind,
        (id) => { P.leads = id; P.all = false; render(); }, 'physleadsel'),
      list.some((t) => t.sound) ? seg(LEADVIEWS, view, (id) => { P.leadView = id; render(); }, 'physleadview') : null,
      view === 'sound'
        ? keyRow(SOUNDS.map((x) => [dot(sndCol(x)), SND_SAY[x]]).concat([[bar('ci'), 'its 95% interval'], [bar('ink'), 'the four sounds’ mean'],
                                                                         [bar('zero'), 'zero']]))
        : keyRow([[dot(css('--up')), 'tone-first rats'], [dot(css('--down')), 'noise-first rats'], [bar('ci'), '95% interval'],
                  [bar('ink'), 'all eight rats'], [bar('zero'), 'zero'], [el('i', { class: 'kmark sq' }), 'the difference (under its number), ± 90%'],
                  [el('i', { class: 'kmark box' }), '±½ of all eight']]),
      view === 'sound' ? el('p', { class: 'small', id: 'physleadsay', text: sndSay }) : el('p', { class: 'small', id: 'physleadsay', text: (list.length === 1 ? 'Of this 1 top result: ' : 'Of these ' + list.length + ' top results: ') + n1(both, 'goes', 'go')
        + ' the same way in the tone-first and the noise-first rats; ' + n1(eq, 'is', 'are') + ' the same in both groups within half its own size '
        + '(equivalence, 90% interval); ' + n1(diff, 'differs', 'differ') + ' between the groups at p < .05 (uncorrected; chance alone would give about '
        + (0.05 * list.length).toFixed(1) + ').'
        + (med != null ? ' Of the ' + split + ' that every rat in both groups has, the median is equivalent within ±' + med.toFixed(2)
          + '× its own change' + (med > 0.5 ? ': with four rats a group, the interval is too wide for ±½.' : '.') : '')
        + (split < list.length ? ' The other ' + (list.length - split) + ' lack a rat in one group, so they are described, not tested.' : '') }),
      el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable physleadtbl', id: 'physleadtbl', 'data-view': view }, [
        el('thead', {}, [el('tr', {}, (view === 'sound' ? headSnd : headGrp).map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows)])]),
      list.length > 10 ? el('button', { type: 'button', class: 'more-btn', id: 'physall', text: P.all ? 'Show the top 10' : 'Show all ' + list.length,
                                        onclick: () => { P.all = !P.all; render(); } }) : null,
      (window.MONO_EXPLAIN ? (txt) => window.MONO_EXPLAIN.more('reading the pictures', (body) => { body.appendChild(el('p', { class: 'small', id: 'physleadread', text: txt })); return null; },
        { key: 'phys-leadread-' + view, eager: true }) : (txt) => el('p', { class: 'small muted', text: txt }))(view === 'sound'
        ? 'Each sound’s change is pooled over all eight rats (± its standard error), each rat measured while that sound played: in its cue '
          + 'window, whatever the top result’s own window. In the picture, a row a sound with its 95% interval, the line their mean, and the thin grey '
          + 'line zero: everything drawn is the cue windows. “Change, all rats” is the top result’s own window (Switch, say, or the pre-baseline, '
          + 'where no one sound plays), so it can sit apart from the four. Click one to open it on the Monolith.'
        : 'Each group’s change is pooled over its own four rats (± its standard error). The picture beside them, on one scale: the thin grey line '
          + 'is zero, red the tone-first rats and blue the noise-first, each with its 95% interval, and the black line the change in all eight. The '
          + 'change in all eight is not the midpoint of the two groups: pooling weights each rat by how steady its numbers are, so the steadier '
          + 'group pulls it. Under the difference, on the same scale: the black square is the difference itself (so it sits near zero, not near '
          + 'the changes), the line its 90% interval, and the grey box ±½ of the change in all eight; the interval must lie inside the box for '
          + 'the two groups to count as the same. A group of four is often a rat short at a top result: its interval and the difference are then '
          + 'worked out from three rats and said (“3 rats”), and with two left there is none. Click one to open it on the Monolith.'),
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
    const sndc = P.cmp.indexOf('snd:') === 0;
    const set = (patch) => { Object.assign(P.view, patch); render(); };
    const hasSnd = !!(((P.data || {}).sound || {}).counts || {}).raw;
    const card = section('physcirc', 'Any comparison as a circuit', 'physical.circuit', [
      seg(['order', 'sound_noise', 'sound_tone', 'tone_noise', 'seat_abcd'].map((c) => [c, SAY[c].name, SAY[c].what]), P.cmp,
        (id) => { P.cmp = id; render(); }, 'physcmp'),
      hasSnd ? seg(SND_PAIRS.map((x) => 'snd:' + x).concat(['snd:omni']).map((c) => [c, SAY[c].name, SAY[c].what]), P.cmp,
        (id) => { P.cmp = id; render(); }, 'physcmpsnd') : null,
      el('p', { class: 'small', id: 'physcmpsay', text: SAY[P.cmp].what }),
      el('div', { class: 'progctl' }, [
        tn ? el('span', { class: 'small muted', text: 'Window: Cue 2 − Cue 1 (raw)' })
          : sndc ? el('span', { class: 'small muted', text: 'Window: each sound’s own cue window (raw)' })
          : pick('Window', 'physw', S0.windows.filter((w) => w.kind !== 'contrast').map((w) => [w.id, w.label]), v.w, (x) => set({ w: x })),
        pick('Frequency', 'physb', S0.bands.map((b) => [b.id, b.named ? b.label : b.hz + ' Hz']), v.b, (x) => set({ b: x })),
        pick('Measure', 'physm', S0.methods.map((m) => [m.id, m.label]), v.m, (x) => set({ m: x })),
        tn || sndc ? null : pick('', 'physl', [['raw', 'Raw'], ['minus_fp', 'Minus FP']], v.layer, (x) => set({ layer: x })),
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
    const sndc = P.cmp.indexOf('snd:') === 0;
    const layer = tn || sndc ? 'raw' : v.layer;
    const name = sndc ? 'phys_snd_' + layer + '__' + P.cmp.slice(4) : 'phys_edges_' + layer + '__' + P.cmp;
    const w = sndc ? 0 : tn ? S0.windows.findIndex((x) => x.id === 'c21') : S0.windows.findIndex((x) => x.id === v.w);
    const b = S0.bands.findIndex((x) => x.id === v.b), m = S0.methods.findIndex((x) => x.id === v.m);
    const seq = ++P.cseq;
    let A;
    try { A = await arrayOf(name, sndc ? 1 : null); } catch (e) {
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
          + 'minutes: every stat test, Raw and Minus FP, with every shuffle of the rats beside it.' }),
        window.MONO_STATIC ? el('p', { class: 'small muted', text: 'Not in this copy: it opens in Jarvis.' })
          : el('button', { type: 'button', class: 'more-btn', id: 'physmake', disabled: P.making ? 'disabled' : null,
                           text: P.making ? 'Comparing: ' + (P.makeNote || 'starting') : 'Compare them now', onclick: make }),
        P.makeErr ? el('p', { class: 'small warn', text: P.makeErr }) : null,
      ]));
      return;
    }
    pane.appendChild(verdict());
    const sc = soundCard();
    if (sc) pane.appendChild(sc);
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
