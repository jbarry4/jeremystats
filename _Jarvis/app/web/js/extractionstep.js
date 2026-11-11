/* ==========================================================================
   extractionstep.js -- The Extraction Room's step in the ToolKit: step six,
   the last, of The Dentist (2026-11-10).

   The room itself is a page of its own (web/extraction.html, like the
   Monolith's), so this step is the door to it: what the room holds now,
   which X-ray Many folders could be extracted into it and how many bundles
   each has, and a press that opens the room in its own tab.
   ========================================================================== */
'use strict';

BARRY.extractionStep = (function () {
  const host = () => document.getElementById('tkResult');
  const S = { idx: null, err: null, busy: null, at: 0 };

  function open() {
    const dark = /dark/.test(getComputedStyle(document.documentElement).colorScheme || '');
    const w = window.open('/extraction.html?theme=' + (dark ? 'dark' : 'light'), 'barry-extraction-room');
    if (!w) toast('The room was blocked as a pop-up. Allow pop-ups for this page, then press it again.', 'err', 9000);
    BARRY.activity.log('extraction.open', {});
  }

  async function load() {
    try {
      S.idx = await api('/api/extraction');
      S.err = null;
    } catch (e) {
      S.err = e.message;
    }
    S.at = Date.now();
    render();
  }

  async function extract(fid) {
    if (S.busy) return;
    S.busy = 'Extracting… each recording is refitted from its read, a few seconds each.';
    render();
    try {
      const got = await apiPost('/api/extraction/extract', { room: 'dentate_spike', folder: fid });
      toast('Extracted ' + got.n + ' recordings into the Dentate Spike room as v' + got.version
            + ((got.left || []).length ? '; ' + got.left.length + ' left out (open the room to see why)' : '') + '.',
            'ok', 9000);
      BARRY.activity.log('extraction.extract', { folder: fid, version: got.version });
      // An open room opens it at once (2026-11-11: the 10% set was
      // extracted here while the room's tab sat on the 5% one).
      try {
        const f = ((S.idx || {}).folders || []).find((x) => x.id === fid) || {};
        const bc = new BroadcastChannel('barry-extraction');
        bc.postMessage({ type: 'extracted', room: 'dentate_spike', version: got.version, folder: fid, folder_name: f.name });
        bc.close();
      } catch (e) { /* the room asks again when it is looked at */ }
    } catch (e) {
      toast('Not extracted: ' + e.message, 'err', 12000);
    }
    S.busy = null;
    await load();
  }

  function render() {
    const box = host();
    if (!box) return;
    const feed = box.querySelector('.tf');
    if (feed) box.removeChild(feed);
    box.innerHTML = '';
    box.dataset.tool = 'extraction';
    box.appendChild(BARRY.ui.stepHeader({
      title: 'The Extraction Room',
      step: 'step 6 of The Dentist',
      blurb: 'What X-ray split, taken out of Jarvis into a room of its own: the CSD and depth profiles of DS1 and '
           + 'DS2, their sinks and sources, and each mouse’s %KO. It opens in its own tab, like the Monolith.',
    }));
    const kids = [];
    if (S.err) kids.push(el('p', { class: 'hint', text: 'The room could not be asked: ' + S.err }));
    if (!S.idx && !S.err) kids.push(loader('Asking the room what it holds'));
    if (S.idx) {
      for (const r of S.idx.rooms || []) {
        const sm = r.summary || {};
        kids.push(el('p', {}, [el('strong', { text: r.name + ': ' }),
          el('span', { text: r.artifact_id
            ? 'v' + r.version + ', ' + (sm.recordings || 0) + ' recordings, ' + (sm.events || 0).toLocaleString()
              + ' events, from ‘' + (sm.folder || '?') + '’' + (r.by ? ', extracted by ' + r.by : '')
              + (r.at ? ' on ' + new Date(r.at).toLocaleString() : '') + '.'
            : 'nothing extracted yet.' })]));
      }
      const fs = (S.idx.folders || []).filter((f) => !f.archived);
      kids.push(el('div', { class: 'ui-field' }, [
        el('div', { class: 'section-label', text: 'X-ray Many folders' }),
        el('div', { class: 'er-folders' }, fs.map((f) => el('div', { class: 'er-folder' }, [
          el('span', { text: f.name + ' · ' + f.bundles + ' bundle' + (f.bundles === 1 ? '' : 's') + ' run · '
            + (f.in_room ? 'in the room as v' + f.in_room.v + (f.new ? ', ' + f.new + ' newer since' : '')
                         : f.bundles ? 'not in the room yet' : 'nothing to extract') }),
          BARRY.ui.button({ kind: f.bundles && (!f.in_room || f.new) ? 'primary' : 'ghost', size: 'sm',
            text: f.in_room ? 'Extract again' : 'Extract into the room',
            disabled: !f.bundles || !!S.busy,
            title: f.bundles ? 'The newest bundle of every recording in it, as the room’s next version.'
                             : 'Run its recordings in X-ray Many first.',
            onclick: () => extract(f.id) }),
        ]))),
      ]));
    }
    if (S.busy) kids.push(el('p', { class: 'hint', text: S.busy }));
    kids.push(el('div', { class: 'er-go' }, [BARRY.ui.button({ kind: 'primary', text: 'Open The Extraction Room',
      extra: 'er-open', onclick: open })]));
    box.appendChild(el('div', { class: 'card er-step' }, kids));
    if (feed) box.appendChild(feed);
  }

  function paint() {
    render();
    if (!S.idx || Date.now() - S.at > 20000) load();
  }

  return { paint, _state: () => S, _open: open };
})();
