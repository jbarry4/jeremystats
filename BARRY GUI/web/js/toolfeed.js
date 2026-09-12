/* ==========================================================================
   toolfeed.js -- what has been happening in this tool, live.

   Every mode already writes to the activity log, and those rows already go
   up to Supabase. This is the half that was missing: being able to READ
   them, per tool, while standing in the tool.

   It is for two things, in this order.

     Reproducibility. The feed is the record of what was done to a
     recording, by whom, on which machine, in what order. Six months later
     it is what a methods section gets written from, and it is the only
     thing that can answer "why does this look different from the version in
     the paper".

     Debugging. When something is wrong, the sequence that produced it is
     right there -- including the actions from the OTHER machine that this
     one only learned about through the sync, which are exactly the ones
     nobody can reconstruct from memory.

   Mounted once, by the ToolKit, for whichever tool is on screen. A tool the
   server has never heard of falls back to its own id as the action prefix,
   so a toolkit added next year gets a feed without anybody registering it.
   ========================================================================== */
'use strict';

BARRY.toolfeed = (function () {
  const EVERY_MS = 9000;        // how often a mounted feed asks for more
  const KEEP = 120;             // rows held in the list before the tail goes

  let live = null;              // the feed currently on screen, if any

  /* One mounted feed. Only ever one: the ToolKit shows one tool at a time,
     and a poller left running for a tool nobody is looking at is a request
     every nine seconds forever. */
  function mount(host, tool, opts) {
    stop();
    if (!host || !tool) return null;
    const o = opts || {};
    const box = el('div', { class: 'tf' });
    const head = el('div', { class: 'tf-head' });
    const list = el('div', { class: 'tf-list' });
    box.appendChild(head);
    box.appendChild(list);
    host.appendChild(box);

    live = {
      tool, box, head, list, rows: [], newest: null, timer: null,
      stopped: false, source: null, note: null,
    };
    paintHead();
    list.appendChild(el('div', { class: 'tf-empty', text: 'Reading…' }));
    pull(true);
    live.timer = setInterval(() => pull(false), o.every || EVERY_MS);
    return box;
  }

  function stop() {
    if (live && live.timer) clearInterval(live.timer);
    if (live) live.stopped = true;
    live = null;
  }

  async function pull(first) {
    const me = live;
    if (!me || me.stopped) return;
    let url = '/api/toolfeed/' + encodeURIComponent(me.tool) + '?limit=60';
    /* Only what is new. A feed left open all afternoon should cost twenty
       rows and then nothing, not the whole history every nine seconds. */
    if (!first && me.newest) url += '&since=' + encodeURIComponent(me.newest);
    let got = null;
    try {
      got = await (await fetch(url)).json();
    } catch (e) {
      if (me === live) { me.note = 'Could not reach the server.'; paintHead(); }
      return;
    }
    if (me !== live || me.stopped) return;      // the tool changed under us
    if (!got || !got.ok) return;

    me.source = got.source;
    me.note = got.note || null;
    const fresh = (got.rows || []).filter((r) => r && r.at);
    if (fresh.length) {
      /* Newest first from the server; the list keeps that order. Ids are
         what stop a row arriving twice when two polls overlap at a
         second boundary. */
      const have = new Set(me.rows.map((r) => r.id));
      const add = fresh.filter((r) => !have.has(r.id));
      me.rows = add.concat(me.rows).slice(0, KEEP);
      me.newest = me.rows.reduce(
        (top, r) => (!top || moment(r.at) > moment(top) ? r.at : top),
        me.newest);
      paintList(add.length && !first ? add.map((r) => r.id) : []);
    } else if (first) {
      paintList([]);
    }
    paintHead();
  }

  /* ---------- painting ---------- */
  function paintHead() {
    const me = live;
    if (!me) return;
    me.head.innerHTML = '';
    const cloud = me.source === 'supabase';
    me.head.appendChild(el('span', {
      class: 'tf-dot' + (cloud ? ' on' : ''),
      title: cloud ? 'Reading the shared table' : 'This machine only',
    }));
    me.head.appendChild(el('strong', { text: 'Activity' }));
    me.head.appendChild(el('span', {
      class: 'tf-src',
      text: cloud ? 'live · everybody' : 'this machine only',
    }));
    me.head.appendChild(el('span', { style: 'flex:1' }));
    me.head.appendChild(el('span', {
      class: 'hint tf-count',
      text: me.rows.length ? me.rows.length + ' recent' : '',
    }));
    if (me.note) {
      me.head.appendChild(el('p', { class: 'hint warn tf-note',
                                    text: me.note }));
    }
  }

  function paintList(flash) {
    const me = live;
    if (!me) return;
    me.list.innerHTML = '';
    if (!me.rows.length) {
      me.list.appendChild(el('div', { class: 'tf-empty',
        text: 'Nothing recorded for this tool yet. Anything anybody does '
            + 'in it will appear here.' }));
      return;
    }
    const hot = new Set(flash || []);
    for (const r of me.rows) {
      const row = el('div', {
        class: 'tf-row' + (hot.has(r.id) ? ' tf-new' : ''),
        title: absolute(r.at) + (r.machine ? '  ·  ' + r.machine : ''),
      }, [
        el('span', { class: 'tf-when', text: ago(r.at) }),
        el('span', { class: 'tf-who', text: shortName(r.git_user) }),
        el('span', { class: 'tf-what', text: words(r.action) }),
        el('span', { class: 'tf-on', text: onWhat(r) }),
        el('span', { class: 'tf-extra', text: extra(r.detail) }),
      ]);
      me.list.appendChild(row);
    }
  }

  /* ---------- saying it in words ---------- */
  /* The action is a dotted id -- `curation.enter`, `bank.add`. Shown as
     something a person reads, and left alone when it is not in the table,
     because an unknown action from a tool added later should still be
     legible rather than blank. */
  const WORDS = {
    'curation.enter': 'opened a set', 'curation.leave': 'closed a set',
    'curation.label': 'labelled', 'curation.taken': 'took a set',
    'curation.review': 'reviewed', 'curation.bank': 'banked a version',
    'curation.import': 'imported curation',
    'curation.collision': 'hit a collision',
    'bank.add': 'banked', 'bank.update': 'edited an entry',
    'bank.delete': 'deleted an entry',
    'events.import': 'imported events',
    'strata.enter': 'opened StrataScope', 'strata.leave': 'left StrataScope',
    'layers.open': 'opened a layer set', 'layers.fill': 'filled layers',
    'layers.assign': 'assigned a sheet', 'layers.archive': 'archived a sheet',
    'layers.snapshot': 'took a layer snapshot',
    'cfc.enter': 'opened Braid', 'cfc.leave': 'left Braid',
    'cfcguide.open': 'opened the explainer',
    'channels.change': 'changed channels',
    'toolkit.bad_channels': 'reviewed bad channels',
    'spikes.detect': 'detected spikes', 'spikes.commit': 'committed spikes',
    'spikes.delete': 'deleted spikes',
    'spikes.to_events': 'turned spikes into events',
    'phy.open': 'opened Phy', 'pipeline.batch': 'ran a batch',
    'dsimport.apply': 'imported sorted snapshots',
  };

  function words(action) {
    const a = String(action || '');
    if (WORDS[a]) return WORDS[a];
    // `thing.did_something` -> "did something"
    const bit = a.split('.').slice(1).join(' ').replace(/_/g, ' ');
    return bit || a || 'did something';
  }

  function onWhat(r) {
    const key = r.session_key || r.gid || '';
    if (!key) return '';
    return String(key).length > 30 ? String(key).slice(0, 29) + '…' : key;
  }

  /* The one or two things from `detail` worth a line. Not the whole object:
     a feed is a list of what happened, and a JSON dump is not a list. */
  function extra(d) {
    if (!d || typeof d !== 'object') return '';
    const bits = [];
    if (d.n != null) bits.push(d.n + ' item(s)');
    if (d.label) bits.push(String(d.label));
    if (d.kind) bits.push(String(d.kind));
    if (d.name) bits.push(String(d.name));
    if (d.v != null) bits.push('v' + d.v);
    return bits.slice(0, 2).join(' · ');
  }

  function shortName(who) {
    const s = String(who || '').trim();
    if (!s) return 'somebody';
    return s.length > 16 ? s.slice(0, 15) + '…' : s;
  }

  /* ---------- time ---------- */
  /* Stamps here come from several machines in several offsets, so they are
     parsed rather than compared as text -- the mistake this codebase has
     made in eleven places. */
  function moment(t) {
    const raw = String(t || '').trim();
    if (!raw) return 0;
    const ms = Date.parse(raw.replace(' ', 'T')
                             .replace(/([+-]\d{2})(\d{2})$/, '$1:$2'));
    return isFinite(ms) ? ms : 0;
  }

  function ago(t) {
    const ms = moment(t);
    if (!ms) return '';
    const s = Math.max(0, (Date.now() - ms) / 1000);
    if (s < 45) return 'just now';
    if (s < 3600) return Math.round(s / 60) + 'm ago';
    if (s < 86400) return Math.round(s / 3600) + 'h ago';
    return Math.round(s / 86400) + 'd ago';
  }

  function absolute(t) {
    const ms = moment(t);
    if (!ms) return String(t || '');
    try {
      return new Date(ms).toLocaleString();
    } catch (e) {
      return String(t);
    }
  }

  return { mount, stop, words };
})();
