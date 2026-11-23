/* ==========================================================================
   stormregion.js -- a KCNT1 dual recording, one array at a time.

   2026-11-20: "an option to The Storm toolkits (Doppler, Spotter, Eye) so if
   a KCNT1 HIP/M2 recording is received you get to choose to process HIP, M2
   or both and if both is chosen it creates two separate data banks".

   The recording carries two implants -- a line of contacts in hippocampus on
   CSC 1-64, another in M2 on 65-128 -- and everything The Storm does is about
   one line of contacts. So each array is its own question and its own bank
   entry, with its own version tree (backend/stormregion.py).

     Doppler   asks before the run: the array is a channel range, and Both
               is two runs, each banked as its own entry.
     Spotter,  asked when an entry covers both arrays: it is split into one
     Eye       entry per array (decisions kept), and the work goes on in
               the one picked.

   Which array is which comes from the recording's own channel banks -- never
   from a channel count -- so a recording nobody has named is not asked about.
   ========================================================================== */
'use strict';

BARRY.stormRegion = (function () {
  const cache = new Map();         // gid -> {at, regions}
  const TTL = 120000;

  /* [{id, label, short, first, last}] or null. Cached for two minutes per
     recording; `entryId` asks the server about that entry too, uncached. */
  async function look(gid, entryId) {
    if (!gid) return null;
    const hit = cache.get(gid);
    if (!entryId && hit && Date.now() - hit.at < TTL) return hit;
    let got = null;
    try {
      got = await api('/api/storm/regions/' + encodeURIComponent(gid)
                      + (entryId ? '?entry=' + encodeURIComponent(entryId) : ''));
    } catch (e) { return null; }
    const out = { at: Date.now(), regions: got.regions || null,
                  entryRegion: got.entry_region || null,
                  splits: got.splits || {} };
    cache.set(gid, { at: out.at, regions: out.regions });
    return out;
  }

  /* Synchronous, from what has been asked already: Doppler's panel is built
     synchronously and fills in when `look` lands. */
  function known(gid) {
    const hit = cache.get(gid);
    return hit ? hit.regions : undefined;
  }

  const words = (r) => r.label + ' (CSC ' + r.first + '–' + r.last + ')';

  /* The choice itself, as named states (memory: toggles are nouns). */
  /* The same look as BARRY.ui.seg, but it keeps its own pressed state, so
     it can sit in a dialog nothing repaints. */
  function seg(regions, value, onPick) {
    const [hip, m2] = regions;
    const items = [
      ['hip', hip.label, words(hip) + ': only the hippocampal array is read'],
      ['m2', m2.label, words(m2) + ': only the M2 array is read'],
      ['both', 'Both', 'Each array on its own, filed as two bank entries '
                       + 'with their own histories'],
    ];
    let cur = value;
    const box = el('div', { class: 'seg storm-region-seg' });
    for (const [v, label, title] of items) {
      box.appendChild(el('button', {
        class: v === cur ? 'active' : '', text: label, title,
        'data-region': v,
        onclick: () => {
          if (v === cur) return;
          cur = v;
          for (const b of box.children) {
            b.classList.toggle('active', b.dataset.region === v);
          }
          onPick(v);
        },
      }));
    }
    return box;
  }

  /* For Spotter and Eye: `entryId` on a dual recording, covering both
     arrays -- which one(s) to go on with? Returns the entry to work on
     (unchanged when there is nothing to ask), with `others` for the rest of
     a Both, or null when somebody was asked and called it off. */
  async function choose(gid, entryId, tool) {
    const got = await look(gid, entryId);
    if (!got || !got.regions || got.entryRegion) {
      return { entry: entryId, others: [] };
    }
    const regions = got.regions;
    let pick = 'hip';
    const said = el('p', { class: 'hint' });
    const say = () => {
      const s = got.splits || {};
      const parts = (pick === 'both' ? regions : regions.filter((r) => r.id === pick))
        .map((r) => (s[r.id]
          ? r.label + ' already has its own entry, “' + s[r.id].name
            + '”; that is the one opened.'
          : r.label + ' gets a new entry of the events whose peak channel is '
            + 'on its array, with every decision made so far kept.'));
      said.textContent = parts.join(' ');
    };
    say();
    const body = el('div', { class: 'storm-region' }, [
      el('p', { class: 'confirm-msg', text: 'This recording has two arrays, '
          + 'and this set covers both. ' + tool + ' works on one array at a '
          + 'time: a profile down the channel order steps from one implant '
          + 'to the other. The set itself is not changed.' }),
      BARRY.ui.field({ label: 'Which array', inline: true,
        control: seg(regions, pick, (v) => { pick = v; say(); }) }),
      said,
    ]);
    const ok = await BARRY.confirm('Hippocampus, M2 or both', body, 'Go on');
    if (!ok) return null;
    const want = pick === 'both' ? ['hip', 'm2'] : [pick];
    let res;
    try {
      res = await apiPost('/api/storm/split', {
        entry_id: entryId, regions: want,
        added_by: (BARRY.profile && BARRY.profile.who && BARRY.profile.who())
                  || undefined,
      });
    } catch (e) {
      toast('Could not split that set by array: ' + e.message, 'err', 9000);
      return null;
    }
    const made = (res.entries || []).filter((m) => m.id);
    const empty = (res.entries || []).filter((m) => !m.id);
    for (const m of empty) {
      toast('Nothing for ' + (regions.find((r) => r.id === m.region) || {}).label
            + ': ' + (m.why || 'no events') + '.', 'warn', 8000);
    }
    if (!made.length) return null;
    const fresh = made.filter((m) => !m.existed).length;
    if (fresh) {
      toast(made.map((m) => '“' + m.name + '” (' + m.n + ')').join(' and ')
            + (fresh === made.length ? ' filed' : ' ready') + ' in the bank.',
            'ok', 7000);
    }
    if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
      BARRY.views.toolkit.curationChanged();
    }
    return { entry: made[0].id, others: made.slice(1),
             region: made[0].region };
  }

  return { look, known, seg, choose, words };
})();
