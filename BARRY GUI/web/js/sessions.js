/* ==========================================================================
   sessions.js -- Scan a data root and browse every recording under it.

   Point it at D:\PTEN\PTEN or a netfiles share; the server walks the tree,
   identifies each recording by mouse/session/start-time, and returns them
   grouped by cohort. Clicking one opens it in Xplorefinder.
   ========================================================================== */
'use strict';

BARRY.views.sessions = (function () {
  let sessions = [];
  let tree = [];
  let scanId = null;
  let poll = null;
  let query = '';
  let groupFilter = '';
  const flags = new Set();

  /* Availability is a choice, not a switch.

     "Everything Jarvis knows" and "only what I can open right now" are two
     different jobs -- one is a catalogue of 473 recordings, the other is a
     work queue of 184 -- and as the ninth checkbox in a row of nine that
     distinction was invisible. */
  let avail = 'all';                      // 'all' | 'open'

  /* What the scan itself is told to do.

     Held here rather than read off two inputs in the toolbar, because the
     inputs are gone: they were the state, and a popover that is rebuilt
     every time it opens cannot be. Defaults are named so the button can say
     when they have been changed -- "why did the scan miss it" is almost
     always Depth. */
  const SCAN_DEFAULTS = { headers: true, depth: 6 };
  const scanOpts = Object.assign({}, SCAN_DEFAULTS);

  /* What each filter is called and where it belongs. One list, so the
     popover, the chips and the count can never disagree about what is on. */
  const FILTERS = [
    { group: 'Recording', id: 'video', name: 'Has video' },
    { group: 'Recording', id: 'converted', name: 'Converted (.mat)',
      note: 'A .mat written by the conversion step' },
    { group: 'Recording', id: 'bad', name: 'Has bad channels' },
    { group: 'Quality', id: 'good', name: 'Marked good',
      note: 'Flagged good for analysis' },
    { group: 'Quality', id: 'exclude', name: 'Hide excluded',
      note: 'Leave out anything flagged exclude' },
    { group: 'Quality', id: 'unhealthy', name: 'Health notes',
      note: 'Only the ones the health check flagged' },
    /* Acquisition gaps, from the kept record of every check rather than by
       re-reading three hundred folders. A recording nobody has checked is
       unknown rather than clean, and is in neither of these. */
    { group: 'Continuity', id: 'concat', name: 'Has acquisition gaps',
      note: 'Multi-segment: Toothy times run early against the raw files' },
    { group: 'Continuity', id: 'unpatched', name: 'Gaps, not corrected',
      note: 'Has gaps, has banked events, and they have not been re-timed' },
    { group: 'Continuity', id: 'unchecked', name: 'Never checked for gaps',
      note: 'Nobody has run the continuity check on this one' },
    /* Which recordings still need StrataScope is a question with sixty-odd
       sheets behind it now, and scrolling four hundred cards looking for
       the gaps is not an answer. */
    { group: 'Layers', id: 'layers', name: 'Layers labelled' },
    { group: 'Layers', id: 'nolayers', name: 'Layers still to do' },
    /* Which of these the cluster could run, which is the question you ask
       before sending anything to it. `notvacc` is deliberately "known not
       to be reachable" rather than "not known to be reachable": a recording
       nobody has established an answer for is in NEITHER, the same way an
       unchecked recording is in neither continuity filter. Reading a
       missing answer as a no is the mistake `canOpen` below is a comment
       about. */
    { group: 'VACC', id: 'onvacc', name: 'VACC can read it',
      note: 'On a share the cluster mounts, or already copied to it' },
    { group: 'VACC', id: 'notvacc', name: 'VACC cannot reach it',
      note: 'Established, and on a disk the cluster has no path to' },
    /* The work list for the flag, because a chip you have to scroll into is
       not much of a flag. Filed by hand is not in here -- somebody already
       looked, and putting their answer back in the queue would mean the
       queue never empties. */
    { group: 'Filing', id: 'projectq', name: 'Project worth a look',
      note: 'A path names a project other than the one it is filed under' },
  ];
  const picked = new Set();   // paths queued for opening
  const health = {};          // path -> report from /api/session/health
  let healthBusy = false;
  /* What every continuity check anybody has run says, keyed on session id.
     Read once when the view opens rather than per card: four hundred cards
     would be four hundred questions and the answer is one table. */
  let continuity = null;
  let continuityAt = 0;

  function continuityOf(s) {
    if (!continuity) return null;
    const gid = s.gid || (s.stored && s.stored.gid);
    return gid ? (continuity[gid] || null) : null;
  }

  async function loadContinuity(force) {
    /* Cheap and it changes when somebody runs a check, so re-read on a
       filter rather than caching for the session. Thirty seconds is long
       enough that switching filters does not re-ask, short enough that a
       check you just ran shows up. */
    if (!force && continuity && Date.now() - continuityAt < 30000) return;
    try {
      const res = await api('/api/health/summary');
      continuity = (res && res.sessions) || {};
      continuityAt = Date.now();
    } catch (e) {
      continuity = continuity || {};
    }
  }

  /* Which of the listed recordings this scan actually found.

     The scan page used to hold its results in memory and nothing else, so a
     refresh emptied it -- a strange thing for a page about what is on your
     drives to do. Everything Jarvis has ever met is in the registry now, so
     the page opens showing all of it faint and a scan brightens what it
     finds. Refreshing costs you the brightening, not the list. */
  const foundNow = new Set();
  let knownLoaded = false;

  const RECENT_KEY = 'barry.roots';
  const LAST_KEY = 'barry.lastSessions';
  /* How big the catalogue was last time. Only ever used to say so while the
     real answer is being read -- see `catalogueScale`. */
  const SIZE_KEY = 'barry.catalogueSize';

  /* What the wait is for, in words, before the answer that would say it
     exactly has arrived.

     A first run on a new machine has nothing to go on and says so rather
     than guessing a number; every run after that can state the scale, which
     is the difference between "it is thinking" and "it is reading six
     hundred and eighty-seven recordings". Approximate on purpose -- the
     stored figure is one run old and the exact one lands with the answer. */
  function catalogueScale() {
    let n = 0;
    try { n = parseInt(localStorage.getItem(SIZE_KEY), 10) || 0; }
    catch (e) { n = 0; }            // private mode
    return n
      ? 'reading about ' + n + ' recordings Jarvis has met'
      : 'reading every recording Jarvis has met';
  }

  function rememberScale(n) {
    if (!n) return;
    try { localStorage.setItem(SIZE_KEY, String(n)); }
    catch (e) { /* private mode */ }
  }

  /* Remember which recordings were last open, so a restart picks up where you
     left off rather than at an empty Xplorefinder. */
  function rememberOpen(paths) {
    try { localStorage.setItem(LAST_KEY, JSON.stringify(paths.slice(0, 4))); }
    catch (e) { /* private mode */ }
  }

  function lastOpen() {
    try { return JSON.parse(localStorage.getItem(LAST_KEY) || '[]'); }
    catch (e) { return []; }
  }

  /* A registry row, wearing the shape the tree already knows how to draw.

     A translation rather than a second renderer, deliberately: one way of
     drawing a session means the remembered ones and the found ones cannot
     drift apart visually, which is the point of showing them together. */
  function fromRegistry(r) {
    const path = (r.here || [])[0] || (r.paths || [])[0] || '';
    return {
      /* Whether THIS computer has met it: true, false, or null for "the
         server did not say". Carried through because the two modes are two
         different questions and this is what separates them.

         Null matters. The demo project is appended to the payload after the
         walk that marks the rows, so those rows carry no answer at all, and
         `!!undefined` made that indistinguishable from "not seen" -- which
         hid the tour session from the scan view. Absent is not no. */
      _seenHere: r.seen_here === undefined ? null : !!r.seen_here,
      path,
      name: r.label || r.key || r.gid,
      gid: r.gid,
      _remembered: true,
      _reachable: !!r.reachable,
      identity: {
        group: r.project || 'Unfiled',
        mouse: r.mouse,
        session: r.session,
        start: r.start,
        label: r.label,
        mouse_folder: '',
        confidence: 'high',
      },
      channels: r.n_channels || 0,
      fs: r.fs || null,
      duration_s: r.duration_s || 0,
      converted: !!r.converted,
      has_video: !!r.has_video,
      has_tracking: false,
      /* What is attached, and where it can be read from.
         Carried through rather than dropped: the filters ask about both,
         and a translation that quietly loses a field makes a filter that
         matches nothing -- which looks like "none of them qualify" rather
         than like a bug. */
      has: r.has || {},
      here: r.here || [],
      hemisphere: r.hemisphere || null,
      hemisphere_source: r.hemisphere_source || null,
      /* The landmarks a CSD is read against, and what the extraction made
         of them. `extraction_note` is the one that matters: "Missing: No
         CA1 SP channel" changes how the recording should be read, and it
         was only ever visible in a spreadsheet. */
      fissure_channel: r.fissure_channel,
      ripple_channel: r.ripple_channel,
      hilus_channel: r.hilus_channel,
      extraction_note: r.extraction_note || null,
      needs_processing: !!r.needs_processing,
      /* Paths whose own text names a different project than this is filed
         under. Carried rather than recomputed: the reading lives in one
         place, `sessreg.project_flags`, and a second copy of the rule here
         is a second copy to get wrong. */
      project_flags: r.project_flags || [],
      /* Which probe, and whether anybody has agreed. Carried rather than
         recomputed: the rule lives in `probes.state_of`, and a second copy
         of it here would be a second copy to get wrong. */
      probe: r.probe || null,
      probe_state: r.probe_state || null,
      stored: (r.bad_channels || []).length
        ? { bad_channels: r.bad_channels } : null,
    };
  }

  /* Everything Jarvis knows, as the starting list.

     `quiet` is for the warm start and nothing else: a re-read that nobody
     asked for must not dim the list or announce itself, because from the
     outside it is indistinguishable from the application deciding to grey
     out what somebody is reading. */
  async function loadKnown(force, quiet) {
    if (knownLoaded && !force) return;
    knownLoaded = true;

    /* The registry read takes about five seconds on a full catalogue, and
       this view opened as an empty box for all of it -- which reads as "no
       sessions" rather than "not yet". Only when there is nothing already on
       screen: refreshing a list that is already there should not blank it.

       `force` is only ever passed by something the person just did -- they
       accepted a held-back folder, or applied a time correction -- and five
       seconds of a tree that still shows the old state, with nothing to say
       so, is the same complaint in a slower view. Dim it for those. */
    const host = $('#sessTree');
    const bones = quiet ? null
      : (sessions.length
          ? (force ? BARRY.skeleton.stale(host) : null)
          : BARRY.skeleton.into(host, 'card', 6));
    const sub = $('#sessSub');
    if (bones && sub) sub.textContent = 'Reading the catalogue\u2026';

    /* The bones say what is COMING. They do not say what is HAPPENING, and
       for six seconds that is the question -- the view looked identical
       whether the registry was being merged, the answer was already warm, or
       the server had stopped answering.

       So a loader above them, on a cold open only. A refresh already has the
       list on screen and does not need a wait announced over the top of it.

       `loader` and not `stepLoader`, deliberately. There is one slow stage
       here and it is the registry read; the merging and grouping after it
       are a few milliseconds on the same data. Naming them as steps would
       have shown two of the three dots for no measurable time, which is a
       progress bar that lies about where the time goes.

       What it says instead is the SIZE of the job, from the last time this
       ran -- because the count is informative when the wait starts and is
       the one thing not known until it ends. */
    const wait = (bones && !sessions.length && host)
      ? loader('The catalogue', catalogueScale()) : null;
    if (wait) host.insertBefore(wait, host.firstChild);
    /* Six seconds is normal and worth sitting through; fifteen is something
       being wrong, and saying so beats letting somebody decide the
       application has hung. */
    const slow = wait ? setTimeout(() => {
      const line = wait.querySelector('.loader-text span');
      if (line) {
        line.textContent = 'still reading — this usually takes about '
                         + 'six seconds';
      }
    }, 15000) : null;
    /* One remover for all of it, so no path can clear the bones and leave a
       loader spinning above an empty tree. */
    const done = () => {
      if (slow) clearTimeout(slow);
      if (wait && wait.parentNode) wait.parentNode.removeChild(wait);
      if (bones) bones();
    };

    let reg;
    try {
      reg = await api('/api/registry');
    } catch (e) {
      // An older server: the page still works, but the bones must not stay.
      done();
      if (sub) sub.textContent = '';
      renderTree();
      return;
    }
    done();
    /* What was actually read, so the next cold open can state the size of
       the job before it starts rather than after it finishes. */
    rememberScale(reg.total);
    /* The lab's projects, whether or not any are on screen right now.
       Without this the project filter's options appear and disappear as
       the list is narrowed by something else, which makes it look broken
       at exactly the moment somebody is using it. */
    BARRY.state.knownProjects = reg.known_projects || [];
    const rows = (reg.tree || []).flatMap(
      (p) => p.mice.flatMap((m) => m.sessions));
    /* A row a scan already put on screen wins, because it carries what the
       scan just read. But the filing flag is the registry's answer and a
       scan has no opinion about it, so it is copied across rather than lost
       -- otherwise the chip appears on the recordings nobody has scanned
       and vanishes from the ones somebody just did. */
    const flagsByGid = {};
    const probeByGid = {};
    for (const r of rows) {
      if (!r.gid) continue;
      if ((r.project_flags || []).length) flagsByGid[r.gid] = r.project_flags;
      if (r.probe_state) probeByGid[r.gid] = r;
    }
    for (const x of sessions) {
      if (!x.gid) continue;
      if (flagsByGid[x.gid]) x.project_flags = flagsByGid[x.gid];
      /* A scan reads a header and knows the channel count, but it does not
         know whether anybody has confirmed what the probe is -- that is the
         registry's answer. Copied across, or the chip appears only on the
         recordings nobody scanned. */
      if (probeByGid[x.gid]) {
        x.probe = probeByGid[x.gid].probe || null;
        x.probe_state = probeByGid[x.gid].probe_state;
      }
    }
    const have = new Set(sessions.map((x) => x.gid).filter(Boolean));
    const seenPath = new Set(sessions.map((x) => x.path).filter(Boolean));
    const extra = rows
      .filter((r) => !have.has(r.gid))
      .map(fromRegistry)
      .filter((x) => !x.path || !seenPath.has(x.path));
    if (!extra.length) { renderTree(); return; }
    sessions = sessions.concat(extra);
    if (!tree.length) {
      // The cohort pills come from the scan; without one, build them from
      // what is known so the filter still works.
      const by = {};
      for (const x of sessions) {
        const g = x.identity.group || 'Ungrouped';
        by[g] = (by[g] || 0) + 1;
      }
      tree = Object.keys(by).sort().map((g) => ({ group: g, n: by[g] }));
      renderGroupFilter();
    }
    const filters = $('#sessFilters');
    if (filters) filters.classList.remove('hidden');
    renderTree();
  }

  /* ---------- recent roots ---------- */
  function recents() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); }
    catch (e) { return []; }
  }
  function remember(root) {
    try {
      const list = [root].concat(recents().filter((r) => r !== root)).slice(0, 6);
      localStorage.setItem(RECENT_KEY, JSON.stringify(list));
    } catch (e) { /* private mode */ }
    renderRecents();
  }
  function renderRecents() {
    const host = $('#rootRecent');
    host.innerHTML = '';
    for (const r of recents()) {
      host.appendChild(el('button', {
        text: r, title: r,
        onclick: () => { $('#rootPath').value = r; start(r); },
      }));
    }
  }

  /* ---------- scanning ---------- */
  async function start(root) {
    root = (root || $('#rootPath').value || '').trim().replace(/^["']|["']$/g, '');
    if (!root) { toast('Enter or browse to a data root first.', 'err'); return; }

    stopPoll();
    $('#scanStatus').classList.remove('hidden');
    $('#scanStatus').innerHTML = '';
    $('#scanStatus').appendChild(el('span', { class: 'spin' }));
    $('#scanStatus').appendChild(el('span', { text: 'Starting…' }));

    try {
      const res = await apiPost('/api/discover/start', {
        root,
        max_depth: scanOpts.depth || SCAN_DEFAULTS.depth,
        read_headers: !!scanOpts.headers,
      });
      scanId = res.job.id;
      remember(root);
      /* Paced by a chained timeout rather than an interval, so the gap can
         grow. See tick(). */
      scanSeen = { scanned: -1, at: Date.now() };
      scanGap = 400;
      schedule();
      tick();
    } catch (e) {
      $('#scanStatus').innerHTML = '';
      $('#scanStatus').appendChild(el('span', { class: 'stat-chip warn', text: e.message }));
    }
  }

  /* How the scan poll paces itself, and how it notices a stall. */
  let scanSeen = null;      // {scanned, at} the last time the count moved
  let scanGap = 400;

  function schedule() {
    if (poll) clearTimeout(poll);
    poll = setTimeout(tick, scanGap);
  }

  function stopPoll() {
    if (poll) clearTimeout(poll);
    poll = null;
    scanSeen = null;
    scanGap = 400;
  }

  /* What the scan is doing, in the terms somebody watching it is asking
     about.

     The old line was a spinner, two counters and an absolute path, and the
     counters are the least informative part: "31 sessions" is true of a
     scan walking the right tree and of a scan walking the wrong one. The
     three questions a person actually has are whether it is moving, whether
     this is the data they meant, and where it has got to -- so the rate
     answers the first, the found-so-far breakdown answers the second, and
     the path answers the third but relative to the root, because the part
     of it they chose is the part they do not need repeated back.

     Nothing here is truncated. The path wraps; a project that does not fit
     goes to the next line. */
  function scanLive(j) {
    const live = j.live || {};
    const wrap = el('div', { class: 'scan-live' });

    const rate = j.elapsed > 0.6 ? Math.round(j.scanned / j.elapsed) : null;
    wrap.appendChild(el('div', { class: 'scan-line' }, [
      el('strong', { text: String(j.found) }),
      el('span', { text: j.found === 1 ? 'recording' : 'recordings' }),
      el('span', { class: 'scan-sep', text: '·' }),
      el('span', { text: j.scanned + ' folders' }),
      rate ? el('span', { class: 'scan-sep', text: '·' }) : null,
      rate ? el('span', { class: 'scan-rate', text: rate + '/s' }) : null,
      el('span', { class: 'scan-sep', text: '·' }),
      el('span', { text: Math.round(j.elapsed) + 's' }),
    ].filter(Boolean)));

    /* What it has found, which is the half that was missing. Projects
       first, because the commonest scan mistake is picking a root one
       level too high or too low and the project names say so
       immediately. */
    const facts = el('div', { class: 'scan-line facts' });
    const projects = live.projects || {};
    const names = Object.keys(projects).sort((a, b) => projects[b] - projects[a]);
    for (const n of names) {
      facts.appendChild(el('span', { class: 'scan-fact',
        title: projects[n] + ' recording(s) filed under ' + n,
        text: n + ' ' + projects[n] }));
    }
    if (live.mice) {
      facts.appendChild(el('span', { class: 'scan-fact quiet',
        title: 'Distinct animals, counted per project — the same number in '
             + 'two projects is two animals.',
        text: live.mice + (live.mice === 1 ? ' mouse' : ' mice') }));
    }
    /* The channel count is the cheapest way to tell which drive this is.
       PTEN is 64 and KCNT1 is 128, so the number alone identifies the
       tree -- and a count that is neither is a recording missing files,
       worth seeing now rather than in an audit later. */
    const ch = live.channels || {};
    const counts = Object.keys(ch).map(Number).sort((a, b) => a - b);
    for (const c of counts) {
      /* Two different ways the number goes wrong, and they mean opposite
         things, so they are not one warning.

         Below a multiple of 32: files are missing. The rig records in banks
         of 32 and a count that is not one of them is an incomplete folder.

         Above 128: files are doubled. The KCNT1 recordings are 128 channels
         and several of them carry a `CSCn_0001.ncs` beside every `CSCn.ncs`
         — what Cheetah writes when acquisition restarts mid-session. This
         count is of CSC files, so the continuation files inflate it, and
         the loader reads only the first of each pair. A 192 here is a
         128-channel recording that is half unread. */
      const short = c % 32 !== 0;
      const doubled = !short && c > 128;
      facts.appendChild(el('span', {
        class: 'scan-fact' + (short || doubled ? ' warn' : ' quiet'),
        title: short
          ? ch[c] + ' recording(s) with ' + c + ' channel files, which is '
            + 'not a multiple of 32. The rig records in banks of 32, so '
            + 'files are probably missing.'
          : doubled
            ? ch[c] + ' recording(s) with ' + c + ' channel files, which is '
              + 'more than the rig has channels. Almost certainly '
              + 'CSCn_0001.ncs continuation files, written when acquisition '
              + 'restarted — the loader reads only the first of each pair, '
              + 'so part of the recording will not be analysed.'
            : ch[c] + ' recording(s) with ' + c + ' channels',
        text: c + ' ch × ' + ch[c] }));
    }
    if (live.unnamed) {
      facts.appendChild(el('span', { class: 'scan-fact warn',
        title: 'Folders that look like recordings but whose mouse and '
             + 'session could not be read from the path. They are still '
             + 'found; they just cannot be identified yet.',
        text: live.unnamed + ' unnamed' }));
    }
    if (facts.children.length) wrap.appendChild(facts);

    /* Where it is, relative to the root somebody typed. The absolute path
       spends its first thirty characters repeating the answer back. */
    const here = relToRoot(j.current || '', j.root || '');
    if (here) {
      wrap.appendChild(el('div', { class: 'scan-line where' }, [
        el('code', { text: here, title: j.current || '' }),
      ]));
    }
    if (live.last) {
      wrap.appendChild(el('div', { class: 'scan-line last' }, [
        el('span', { class: 'scan-sep', text: 'last found' }),
        el('span', { text: live.last }),
      ]));
    }
    return wrap;
  }

  /* The part of a path below the folder that was scanned.

     Kept whole when it is not actually below it -- a resolved root, a
     different spelling of the same drive -- because showing nothing would
     be worse than showing the long form. */
  function relToRoot(path, root) {
    if (!path) return '';
    if (!root) return path;
    const p = path.replace(/\\/g, '/');
    const r = root.replace(/\\/g, '/').replace(/\/+$/, '');
    if (p.toLowerCase().indexOf(r.toLowerCase() + '/') === 0) {
      return path.slice(root.replace(/[\\/]+$/, '').length + 1);
    }
    return path;
  }

  async function tick() {
    if (!scanId) return;
    let data;
    try { data = await api('/api/discover/' + scanId); }
    catch (e) { stopPoll(); return; }
    const j = data.job;

    /* Back off while it runs. Two and a half polls a second for a scan that
       takes minutes is thousands of requests for a number nobody can read
       that fast. */
    if (j.status === 'running') {
      scanGap = Math.min(2000, Math.round(scanGap * 1.25));
      schedule();
    }

    /* Has it actually got anywhere? A network drive that is not reachable
       leaves the walking thread blocked, the job "running" and the counter
       still -- which looks exactly like a slow scan and is not one. */
    let stalledFor = 0;
    if (j.status === 'running') {
      if (!scanSeen || j.scanned !== scanSeen.scanned) {
        scanSeen = { scanned: j.scanned, at: Date.now() };
      } else {
        stalledFor = Math.round((Date.now() - scanSeen.at) / 1000);
      }
    }

    const box = $('#scanStatus');
    box.innerHTML = '';
    if (j.status === 'running') {
      box.appendChild(el('span', { class: 'spin' }));
      box.appendChild(scanLive(j));
      if (stalledFor >= 15) {
        /* Say what it is stuck on. On a mapped drive this is almost always
           the drive being unreachable, and it will not resolve by waiting --
           so the useful thing is the path and a way out. */
        box.appendChild(el('span', { class: 'stat-chip warn',
          title: 'The folder count has not moved. If this is a mapped drive, '
               + 'check it is still connected -- Windows leaves a dead mount '
               + 'looking normal until something reads from it.',
          text: 'no progress for ' + stalledFor + 's' }));
      }
      box.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Stop',
        onclick: () => {
          apiPost('/api/discover/' + scanId + '/cancel').catch(() => {});
          stopPoll();
          box.innerHTML = '';
          box.appendChild(el('span', { class: 'stat-chip',
                                       text: 'Scan stopped.' }));
        },
      }));
      return;
    }

    stopPoll();
    if (j.status === 'failed') {
      box.appendChild(el('span', { class: 'stat-chip warn', text: j.error || 'Scan failed.' }));
      return;
    }

    /* Merge rather than replace: what the scan found is now known first
       hand, and what it did not find is still worth listing -- faint -- so
       "the drive I expected it on does not have it" is visible rather than
       silent. */
    const scanned = j.sessions || [];
    for (const x of scanned) { x._remembered = false; }
    foundNow.clear();
    for (const x of scanned) { if (x.gid) foundNow.add(x.gid); }
    const scannedPaths = new Set(scanned.map((x) => x.path));
    const kept = sessions.filter(
      (x) => x._remembered && !(x.gid && foundNow.has(x.gid))
             && !scannedPaths.has(x.path));
    sessions = scanned.concat(kept);
    tree = j.tree || [];
    box.appendChild(el('span', {
      class: 'stat-chip good',
      text: sessions.length + ' session(s) in ' + j.elapsed + 's',
    }));
    /* How much of that was news.

       The server registers everything a finished scan walked past and says
       how many of them it had never seen, which is the one number that
       tells you whether the scan was worth running. It was already in the
       payload and only ever used to decide whether to re-render. */
    const regd = j.registered || {};
    if (typeof regd.new === 'number') {
      box.appendChild(el('span', {
        class: 'stat-chip' + (regd.new ? ' good' : ''),
        title: regd.new
          ? regd.new + ' of these had never been seen on any machine. The '
            + 'rest were already in the registry and have been updated with '
            + 'what this scan read.'
          : 'Every one of these was already known. The registry has been '
            + 'updated with what this scan read.',
        text: regd.new
          ? regd.new + ' new to Jarvis'
          : 'all already known',
      }));
    }
    const lv = j.live || {};
    if (lv.unnamed) {
      box.appendChild(el('span', {
        class: 'stat-chip warn',
        title: 'Their mouse and session could not be read from the path, so '
             + 'they are filed by folder name until somebody says otherwise.',
        text: lv.unnamed + ' could not be named',
      }));
    }

    /* Folders the scan would not vouch for.

     Kept visible rather than dropped: seven folders on the lab drives are 64
     files of header and nothing else -- an acquisition that was started and
     wrote nothing -- and they had been sitting in the registry looking like
     ordinary recordings. Holding them back is only defensible if it is also
     obvious, and reversible: "this looks wrong" is a judgement about data,
     and whoever made the recording is better placed to make it than a size
     check. */
  function heldChip(held) {
    const chip = el('button', {
      class: 'stat-chip warn',
      title: 'Folders that look like recordings but did not pass the check. '
           + 'Click to see why.',
      text: held.length + ' held back',
      onclick: () => showHeld(held),
    });
    return chip;
  }

  function showHeld(held) {
    const rows = held.map((h) => {
      const q = h.quality || {};
      return el('div', { class: 'held-row' }, [
        el('div', { style: 'min-width:0' }, [
          el('strong', { text: h.label || h.name || h.path }),
          el('code', { class: 'held-path', text: h.path }),
          ...(q.reasons || []).map(
            (r) => el('p', { class: 'hint', text: r })),
        ]),
        el('div', { class: 'held-acts' }, [
          el('span', { class: 'flagchip bad', text: q.verdict || '?' }),
          el('button', {
            class: 'btn sm', text: 'Add anyway',
            title: 'Register it despite the check. Nothing about the '
                 + 'recording changes; Jarvis just stops leaving it out.',
            onclick: async (e) => {
              e.target.disabled = true;
              try {
                await apiPost('/api/discover/accept', { path: h.path });
                toast('Registered ' + (h.label || h.name) + '.', 'ok');
                loadKnown(true);
                e.target.textContent = 'Added';
              } catch (err) {
                toast(err.message, 'err', 8000);
                e.target.disabled = false;
              }
            },
          }),
          el('button', {
            class: 'btn ghost sm', text: 'Open the folder',
            onclick: () => apiPost('/api/reveal',
                                   { path: h.path }).catch(() => {}),
          }),
        ]),
      ]);
    });
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: held.length + ' folder(s) held back' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/>'
              + '</svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'hint',
          text: 'These look like recordings but did not pass the check, so '
              + 'they are not in the registry. Nothing on the drive has been '
              + 'touched \u2014 Jarvis does not delete data it did not write.' }),
        el('div', { class: 'held-list' }, rows),
      ]),
    ]));
  }

  /* A scan is the one moment Jarvis has the whole picture of a drive, so
       everything it walked past is now registered -- not just the handful
       anyone opens. The server did the writing; this tells the registry view
       which ones were actually laid eyes on, so they stop being merely
       remembered. */
    const reg = j.registered || {};
    if (reg.seen) {
      box.appendChild(el('span', {
        class: 'stat-chip',
        title: 'Every recording found is now in Sessions › Everything '
             + 'Jarvis knows, whether or not you open it',
        text: reg.new
          ? reg.new + ' new · ' + reg.seen + ' catalogued'
          : reg.seen + ' catalogued',
      }));
    }
    if (BARRY.views.housekeeping && BARRY.views.housekeeping.confirm) {
      BARRY.views.housekeeping.confirm(Array.from(foundNow), j.root);
    }
    // Anything registered that this scan did not turn up should still be on
    // the page, faint. Forced, because the registry has just grown.
    loadKnown(true);

    box.appendChild(el('code', { text: j.root }));
    box.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Rescan', onclick: () => start(j.root),
    }));
    if ((j.held_back || []).length) box.appendChild(heldChip(j.held_back));

    $('#sessFilters').classList.remove('hidden');
    renderGroupFilter();
    renderTree();
    BARRY.activity.log('sessions.scan',
      { root: j.root, found: sessions.length, elapsed: j.elapsed });
  }

  /* ---------- filtering ---------- */
  function renderGroupFilter() {
    const host = $('#sessGroupFilter');
    host.innerHTML = '';
    host.appendChild(el('button', {
      class: 'pill' + (groupFilter ? '' : ' active'), text: 'All cohorts',
      onclick: () => { groupFilter = ''; renderGroupFilter(); renderTree(); },
    }));
    for (const g of tree) {
      host.appendChild(el('button', {
        class: 'pill' + (groupFilter === g.group ? ' active' : ''),
        text: g.group + ' (' + g.n + ')',
        onclick: () => { groupFilter = g.group; renderGroupFilter(); renderTree(); },
      }));
    }
  }

  /* Is this recording part of what THIS computer has met?

     Its own function because the filter and the count both need it and they
     had it written out twice, differently -- which is how the view came to
     say "188 of 185": the filter passed a row nobody had answered for and
     the count did not count it. */
  function inLocal(s) {
    return !s._remembered || s._seenHere !== false;
  }

  function matches(s) {
    /* "Scan a drive" is this computer's own view: what it has been exposed
       to, read off the registry on disk with no database involved.
       "Everything Jarvis knows" is the shared catalogue -- every recording
       any machine has met, which is what travels through Supabase.

       A recording found by the scan running now counts as met whether or
       not a sighting has been filed yet. */
    if (mode === 'scan' && !inLocal(s)) return false;
    if (groupFilter && (s.identity.group || 'Ungrouped') !== groupFilter) return false;
    if (flags.has('video') && !s.has_video) return false;
    if (flags.has('converted') && !s.converted) return false;
    if (flags.has('bad') && !(s.stored && (s.stored.bad_channels || []).length)) return false;
    if (flags.has('good') && qualityOf(s) !== 'good') return false;
    if (flags.has('exclude') && qualityOf(s) === 'exclude') return false;
    if (flags.has('unhealthy')) {
      const h = health[s.path];
      if (!h || h.level === 'ok') return false;
    }
    /* From the health log, keyed on the session id -- the registry's, which
       is what the log and the bank both file under. */
    const cont = continuityOf(s);
    if (flags.has('concat') && !(cont && cont.concat_issue)) return false;
    /* `unpatched` is computed server-side from what clock each banked set
       is on, so a recording whose sets were detected in house is already
       excluded. Stated here as well because this filter is the thing that
       sends somebody off to correct something. */
    if (flags.has('unpatched')
        && !(cont && cont.unpatched && !cont.all_concat_safe)) return false;
    if (flags.has('unchecked') && cont) return false;
    /* Layer state, from the registry's own count rather than by asking the
       layers store per card: four hundred cards would be four hundred
       questions, and the registry already knows. */
    const nLayers = ((s.has || {}).layers) || 0;
    if (flags.has('layers') && !nLayers) return false;
    if (flags.has('nolayers') && nLayers) return false;
    /* What the cluster makes of it. `BARRY.vacc.of` returns null for a
       recording nobody has established an answer for, so both of these
       exclude it -- neither filter claims an unasked question. */
    if (flags.has('onvacc') || flags.has('notvacc')) {
      const v = (BARRY.vacc && BARRY.vacc.of(s)) || null;
      const st = v && v.state;
      const reachable = st === 'native' || st === 'staged';
      if (flags.has('onvacc') && !reachable) return false;
      if (flags.has('notvacc') && (!st || st === 'unknown' || reachable)) {
        return false;
      }
    }
    if (flags.has('projectq') && !((s.project_flags || []).length)) {
      return false;
    }
    if (projFilter.size && !projFilter.has(projectOf(s))) return false;
    if (!chanMatches(s)) return false;
    /* Can I open this, right now, on this computer.

       Not `here`, which is only whether a folder exists -- a folder can
       outlive its contents. The server answers this one properly: the
       registry asks the loader itself (`can_open`), and a scan already
       counted the CSC and .mat files so it can say `loadable` for free.

       The bug this replaces went the other way from the obvious one. A
       recording a scan had just walked, on this very machine, carried
       neither `here` nor `reachable` -- so the filter read the absence as
       "not on this machine" and hid the only certainly-openable things in
       the list. */
    if (avail === 'open' && !canOpen(s)) return false;
    if (!query) return true;
    const q = query.toLowerCase();
    return (s.identity.label || '').toLowerCase().includes(q)
      || (s.path || '').toLowerCase().includes(q)
      || (s.name || '').toLowerCase().includes(q);
  }

  /* Whether this recording opens on a click.

     Three shapes reach this list and they say it differently: the registry
     sends `can_open` and a `loadable` list, a scan sends `loadable` as a
     boolean, and anything older only has `here`. Taking the first that is
     actually present is the difference between a filter and a guess -- and
     reading a missing field as "no" is what hid every scanned recording. */
  function canOpen(s) {
    if (typeof s.can_open === 'boolean') return s.can_open;
    if (typeof s.loadable === 'boolean') return s.loadable;
    if (Array.isArray(s.loadable)) return s.loadable.length > 0;
    return (s.here || []).length > 0 || !!s._reachable;
  }

  /* ==================================================================
     Two filters that are not yes-or-no
     ==================================================================
     Every other filter is a flag: it is on or it is off, and `FILTERS`
     builds the whole list from one array. These two are not, and forcing
     them into that shape would have meant a checkbox per project and a
     checkbox per channel count -- a list that grows whenever somebody
     scans a new drive.

     Project is a set, because "PTEN and KCNT1 but not the urethane work"
     is an ordinary thing to want. Empty means every project, which is the
     same convention the search box uses: no answer is not an answer of
     "none".

     Channels is a comparison, because the question people actually have is
     "which of these are the dual-implant recordings", and that is `> 64`.
     Asking it as `= 128` gets the ordinary ones and silently misses the
     six whose continuation files inflate the count to 190 or 192 -- which
     are exactly the ones worth finding. */
  const projFilter = new Set();
  let chanFilter = { op: '', n: 64 };

  const CHAN_OPS = [
    ['gt', 'more than'],
    ['lt', 'fewer than'],
    ['eq', 'exactly'],
  ];

  function chanOf(s) {
    const n = s.channels != null ? s.channels : s.n_channels;
    const v = Number(n);
    return Number.isFinite(v) && v > 0 ? v : null;
  }

  function chanMatches(s) {
    if (!chanFilter.op) return true;
    const n = chanOf(s);
    /* A recording nobody has read a header for has no channel count, and a
       missing number is not a small number. It is in neither side of the
       comparison, the same way `notvacc` refuses to claim an unasked
       question. */
    if (n == null) return false;
    const want = Number(chanFilter.n) || 0;
    if (chanFilter.op === 'gt') return n > want;
    if (chanFilter.op === 'lt') return n < want;
    return n === want;
  }

  function projectOf(s) {
    return (s.identity && s.identity.group) || s.project || 'Unfiled';
  }

  /* Every project in the list, plus the ones the lab runs even when none
     are on screen -- so the choice does not appear and disappear as the
     list is filtered down by something else. */
  function projectsAvailable() {
    const seen = new Set(sessions.map(projectOf).filter(Boolean));
    for (const p of (BARRY.state.knownProjects || [])) seen.add(p);
    for (const p of projFilter) seen.add(p);
    return Array.from(seen).sort((a, b) => {
      if (a === 'Unfiled') return 1;
      if (b === 'Unfiled') return -1;
      return a.localeCompare(b);
    });
  }

  function nActive() {
    return flags.size + (avail === 'all' ? 0 : 1)
      + projFilter.size + (chanFilter.op ? 1 : 0);
  }

  function chanLabel() {
    const word = (CHAN_OPS.find((o) => o[0] === chanFilter.op) || [])[1];
    return word ? word + ' ' + chanFilter.n + ' channels' : '';
  }

  /* One button, the chips for whatever is on, and nothing else. */
  function renderFilterBar() {
    const bar = $('#sessFilterBar');
    if (!bar) return;
    bar.innerHTML = '';
    const n = nActive();

    bar.appendChild(el('button', {
      class: 'btn ghost sm filter-open' + (n ? ' on' : ''),
      onclick: (e) => openPopover(e.currentTarget, filterPop),
    }, [
      el('span', { html: '<svg viewBox="0 0 20 20" class="fb-ico">'
        + '<path d="M3 5h14M6 10h8M9 15h2"/></svg>' }),
      el('span', { text: 'Filter' }),
      n ? el('span', { class: 'fb-count', text: String(n) }) : null,
    ].filter(Boolean)));

    /* A chip per active filter. The point of collapsing nine pills into a
       button is compactness; the point of the chips is that compactness
       must not cost you knowing what is on. */
    if (avail === 'open') {
      bar.appendChild(chip('Only what opens here', () => {
        avail = 'all'; renderFilterBar(); renderTree();
      }, 'open'));
    }
    for (const p of projFilter) {
      bar.appendChild(chip(p, () => {
        projFilter.delete(p); renderFilterBar(); renderTree();
      }, 'proj:' + p));
    }
    if (chanFilter.op) {
      bar.appendChild(chip(chanLabel(), () => {
        chanFilter.op = ''; renderFilterBar(); renderTree();
      }, 'chan'));
    }
    for (const f of FILTERS) {
      if (!flags.has(f.id)) continue;
      bar.appendChild(chip(f.name, () => {
        flags.delete(f.id); renderFilterBar(); renderTree();
      }, f.id));
    }
    if (n > 1) {
      bar.appendChild(el('button', {
        class: 'linkish fb-clear', text: 'Clear all',
        onclick: () => {
          flags.clear(); avail = 'all';
          projFilter.clear(); chanFilter.op = '';
          renderFilterBar(); renderTree();
        },
      }));
    }
  }

  /* The scan's settings: one button, and what is not standard on its face.

     Modelled on the filter button beside it, because it is the same
     problem -- controls that matter occasionally and are in the way
     always. */
  function renderScanOpts() {
    const bar = $('#rootOptsBar');
    if (!bar) return;
    bar.innerHTML = '';
    const odd = [];
    if (!scanOpts.headers) odd.push('no headers');
    if (scanOpts.depth !== SCAN_DEFAULTS.depth) {
      odd.push('depth ' + scanOpts.depth);
    }
    bar.appendChild(el('button', {
      class: 'btn ghost sm filter-open' + (odd.length ? ' on' : ''),
      title: 'How this scan reads the drive',
      onclick: (e) => openPopover(e.currentTarget, scanOptsPop),
    }, [
      el('span', { html: '<svg viewBox="0 0 20 20" class="fb-ico">'
        + '<circle cx="10" cy="10" r="3"/><path d="M10 3v3M10 14v3M3 10h3'
        + 'M14 10h3"/></svg>' }),
      el('span', { text: 'Scan options' }),
      /* Named, not counted. "2" would tell you something is different
         without telling you what, and the whole reason to show it is that
         a changed depth explains a scan that found nothing. */
      odd.length ? el('span', { class: 'fb-count', text: odd.join(', ') })
                 : null,
    ].filter(Boolean)));
  }

  function scanOptsPop() {
    const box = el('div', { class: 'ctl-pop-body' });
    box.appendChild(el('div', { class: 'ctl-pop-group' }, [
      el('div', { class: 'ctl-pop-title', text: 'How to read what it finds' }),
      el('label', { class: 'ctl-pop-opt' + (scanOpts.headers ? ' on' : ''),
                    title: 'Opens the first CSC file of each candidate to '
                         + 'read its real header. Slower, and the only way '
                         + 'to get the exact recording id.' }, [
        el('input', { type: 'checkbox',
          checked: scanOpts.headers ? 'checked' : null,
          onchange: () => { scanOpts.headers = !scanOpts.headers; back(); } }),
        el('span', { text: 'Read headers (exact IDs)' }),
      ]),
      el('p', { class: 'hint', text: scanOpts.headers
        ? 'Every folder is opened far enough to read one header. This is '
          + 'what makes two copies of one recording recognisable as the '
          + 'same recording.'
        : 'Folders are identified by name and shape only, which is faster '
          + 'and cannot tell two copies apart.' }),
    ]));
    box.appendChild(el('div', { class: 'ctl-pop-group' }, [
      el('div', { class: 'ctl-pop-title', text: 'How deep to look' }),
      el('label', { class: 'ctl-pop-opt' }, [
        el('input', {
          type: 'number', value: String(scanOpts.depth), min: '1', max: '12',
          class: 'inp sm',
          oninput: (e) => {
            const v = parseInt(e.target.value, 10);
            scanOpts.depth = (v >= 1 && v <= 12) ? v : SCAN_DEFAULTS.depth;
            renderScanOpts();
          },
        }),
        el('span', { text: 'folders below the root' }),
      ]),
      el('p', { class: 'hint',
        text: 'A recording six folders down from a project root is normal '
            + 'here. Lower is faster; too low and the scan finds nothing '
            + 'and looks broken.' }),
    ]));
    if (scanOpts.headers !== SCAN_DEFAULTS.headers
        || scanOpts.depth !== SCAN_DEFAULTS.depth) {
      box.appendChild(el('button', {
        class: 'linkish fb-clear', text: 'Back to the usual',
        onclick: () => {
          Object.assign(scanOpts, SCAN_DEFAULTS);
          renderScanOpts();
          const open = document.querySelector('.ctl-pop');
          if (open && open.firstChild) {
            open.replaceChild(scanOptsPop(), open.firstChild);
          }
        },
      }));
    }

    function back() {
      renderScanOpts();
      const open = document.querySelector('.ctl-pop');
      if (open && open.firstChild) {
        open.replaceChild(scanOptsPop(), open.firstChild);
      }
    }
    return box;
  }

  function chip(label, off, id) {
    /* `data-flag` so anything driving this page -- a harness, a keyboard
       shortcut later -- can name a control rather than matching its
       wording. Nine pills carried it; collapsing them into a popover
       should not have cost it. */
    return el('span', { class: 'fb-chip', 'data-flag': id || null }, [
      el('span', { text: label }),
      el('button', { class: 'fb-chip-x', text: '\u00d7',
        title: 'Turn this one off', onclick: off }),
    ]);
  }

  function filterPop() {
    const box = el('div', { class: 'ctl-pop-body' });

    /* Availability first, because it is the one that changes what the view
       is FOR rather than which subset of it you see. */
    box.appendChild(el('div', { class: 'ctl-pop-group' }, [
      el('div', { class: 'ctl-pop-title', text: 'Which recordings' }),
      radio('Everything Jarvis knows', avail === 'all',
            'Every recording on record, including ones on drives nobody '
            + 'has mounted since.',
            () => { avail = 'all'; refresh(); }, 'all'),
      radio('Only what opens here', avail === 'open',
            'Only the ones this computer can open right now \u2014 the '
            + 'folder is reachable and the CSC or .mat files are in it. '
            + 'This is the work queue.',
            () => { avail = 'open'; refresh(); }, 'open'),
    ]));

    /* Project, as a set rather than one at a time: "PTEN and KCNT1 but not
       the urethane work" is an ordinary thing to want, and the pills above
       the list only do one. Nothing ticked means every project. */
    const projects = projectsAvailable();
    if (projects.length > 1) {
      const pg = el('div', { class: 'ctl-pop-group' }, [
        el('div', { class: 'ctl-pop-title', text: 'Project' }),
      ]);
      for (const p of projects) {
        const n = sessions.filter((s) => projectOf(s) === p).length;
        pg.appendChild(el('label', {
          class: 'ctl-pop-opt' + (projFilter.has(p) ? ' on' : ''),
          'data-project': p,
        }, [
          el('input', { type: 'checkbox',
            checked: projFilter.has(p) ? 'checked' : null,
            onchange: () => {
              if (projFilter.has(p)) projFilter.delete(p);
              else projFilter.add(p);
              refresh();
            } }),
          el('span', { text: p }),
          el('span', { class: 'ctl-pop-n', text: String(n) }),
        ]));
      }
      box.appendChild(pg);
    }

    /* Channels, as a comparison. "More than 64" is the question — it finds
       the dual-implant recordings including the ones whose continuation
       files put the count at 190 or 192, which asking for exactly 128
       would miss. */
    const cg = el('div', { class: 'ctl-pop-group' }, [
      el('div', { class: 'ctl-pop-title', text: 'Channels' }),
    ]);
    const cRow = el('div', { class: 'ctl-pop-row' });
    const sel = el('select', {
      onchange: (e) => { chanFilter.op = e.target.value; refresh(); },
    }, [el('option', { value: '', text: 'any number of' })].concat(
      CHAN_OPS.map(([id, word]) => el('option', {
        value: id, text: word,
        selected: chanFilter.op === id ? 'selected' : null,
      }))));
    cRow.appendChild(sel);
    cRow.appendChild(el('input', {
      type: 'number', min: '1', max: '1024', step: '1',
      value: String(chanFilter.n), class: 'ctl-pop-num',
      disabled: chanFilter.op ? null : 'disabled',
      onchange: (e) => {
        chanFilter.n = Math.max(1, parseInt(e.target.value, 10) || 1);
        refresh();
      },
    }));
    cRow.appendChild(el('span', { class: 'ctl-pop-unit', text: 'channels' }));
    cg.appendChild(cRow);
    cg.appendChild(el('p', { class: 'hint',
      text: 'A recording nobody has read a header for has no channel count, '
          + 'and a missing number is not a small one — those are in '
          + 'neither side of the comparison.' }));
    box.appendChild(cg);

    let last = null;
    let group = null;
    for (const f of FILTERS) {
      if (f.group !== last) {
        last = f.group;
        group = el('div', { class: 'ctl-pop-group' }, [
          el('div', { class: 'ctl-pop-title', text: f.group }),
        ]);
        box.appendChild(group);
      }
      group.appendChild(check(f, () => {
        if (flags.has(f.id)) flags.delete(f.id); else flags.add(f.id);
        refresh();
      }));
    }

    function refresh() {
      renderFilterBar();
      renderTree();
      /* Repainted in place rather than closed: turning three filters on
         should be three clicks, not three clicks and two re-opens. */
      const open = document.querySelector('.ctl-pop');
      if (open && open.firstChild) {
        open.replaceChild(filterPop(), open.firstChild);
      }
    }
    return box;
  }

  function radio(label, on, note, pick, id) {
    return el('label', { class: 'ctl-pop-opt' + (on ? ' on' : ''),
                         title: note || '', 'data-avail': id || null }, [
      el('input', { type: 'radio', name: 'sessAvail',
        checked: on ? 'checked' : null, onchange: pick }),
      el('span', { text: label }),
    ]);
  }

  function check(f, toggle) {
    return el('label', {
      class: 'ctl-pop-opt' + (flags.has(f.id) ? ' on' : ''),
      title: f.note || '',
      'data-flag': f.id,
    }, [
      el('input', { type: 'checkbox',
        checked: flags.has(f.id) ? 'checked' : null, onchange: toggle }),
      el('span', { text: f.name }),
    ]);
  }

  /* ---------- tree ---------- */
  function renderTree() {
    const host = $('#sessTree');
    host.innerHTML = '';
    const visible = sessions.filter(matches);

    const nFound = sessions.filter((x) => !x._remembered).length;
    const nKnown = sessions.length - nFound;
    /* The two modes are two questions, and this line is where the view
       says which one it is answering. It used to fight with `setMode` over
       the same element -- prose from one, counts from the other, last
       writer winning -- so it now says both in the space of one line. */
    $('#sessSub').textContent = visible.length + ' of '
      + (mode === 'scan' ? sessions.filter(inLocal).length : sessions.length)
      + (mode === 'scan'
          ? ' on this computer  ·  read from the registry on this disk'
          : ' in the shared catalogue  ·  every machine, kept in step '
            + 'through Supabase')
      /* In the shared view, how the list divides between what this scan
         just found and what was already on record. Left out of the local
         view, where it said "185 of 185 ... 479 remembered" -- the 479
         being the whole catalogue, most of which this view is
         deliberately not showing. */
      + (mode !== 'scan' && nKnown
          ? '  ·  ' + nFound + ' found by this scan, '
            + nKnown + ' remembered'
          : '')
      + (mode === 'scan' && nFound
          ? '  ·  ' + nFound + ' found by this scan' : '')
      + (query ? '  ·  matching "' + query + '"' : '')
      + (avail === 'open' ? '  ·  only what opens here' : '')
      + (picked.size ? '  ·  ' + picked.size + ' selected' : '');
    renderPickBar();

    if (!visible.length) {
      host.appendChild(el('div', { class: 'tree-empty',
        text: sessions.length
          ? 'Nothing matches those filters.'
          : 'Nothing registered yet. Scan a data root and everything under '
            + 'it will be catalogued, whether or not you open it.' }));
      return;
    }

    const byGroup = new Map();
    for (const s of visible) {
      const g = s.identity.group || 'Ungrouped';
      if (!byGroup.has(g)) byGroup.set(g, new Map());
      const mice = byGroup.get(g);
      const mk = s.identity.mouse != null ? 'm' + s.identity.mouse
        : (s.identity.mouse_folder || 'unknown');
      if (!mice.has(mk)) mice.set(mk, []);
      mice.get(mk).push(s);
    }

    for (const [g, mice] of byGroup) {
      const total = Array.from(mice.values()).reduce((a, b) => a + b.length, 0);
      const grp = el('div', { class: 'grp' }, [
        el('div', { class: 'grp-head' }, [
          el('span', { text: g }),
          el('span', { class: 'count', text: total + ' session(s), ' + mice.size + ' mice' }),
        ]),
      ]);
      const keys = Array.from(mice.keys()).sort((a, b) => {
        const na = parseInt(a.replace(/\D/g, ''), 10);
        const nb = parseInt(b.replace(/\D/g, ''), 10);
        if (isFinite(na) && isFinite(nb)) return na - nb;
        return String(a).localeCompare(String(b));
      });
      for (const mk of keys) {
        const list = mice.get(mk).slice().sort(
          (a, b) => (a.identity.session || 0) - (b.identity.session || 0));
        const row = el('div', { class: 'mouse-row' }, [
          /* In a narrow gutter now, so it has to be short. The folder name
             is the long part and it is the part you rarely need, so it moves
             to the tooltip. */
          el('div', {
            class: 'mouse-label',
            title: (list[0].identity.mouse_folder || mk)
                   + '  ·  ' + list.length + ' session(s)',
          }, [
            el('strong', { text: mk }),
            el('span', { class: 'folder', text: list.length + ' sess' }),
          ]),
        ]);
        const cards = el('div', { class: 'sess-cards' });
        for (const s of list) cards.appendChild(sessionCard(s));
        row.appendChild(cards);
        grp.appendChild(row);
      }
      host.appendChild(grp);
    }
  }

  function sessionCard(s) {
    const i = s.identity;
    const badN = s.stored ? (s.stored.bad_channels || []).length : 0;
    const isPicked = picked.has(s.path);
    const remembered = !!s._remembered;
    return el('div', {
      class: 'sess-card' + (isPicked ? ' picked' : '')
           + (remembered ? ' remembered' : ' found'),
      title: remembered
        ? ((s.path || '(no path on this machine)')
           + '\n\nKnown to Jarvis, but this scan has not found it.')
        : s.path,
      onclick: (e) => {
        if (!s.path) {
          toast('None of this recording\u2019s paths are on this machine.',
                'err', 6000);
          return;
        }
        // Ctrl/Cmd or shift adds to the selection; a plain click opens it.
        if (e.ctrlKey || e.metaKey || e.shiftKey || picked.size) {
          togglePick(s.path);
          return;
        }
        setView('xplore');
        rememberOpen([s.path]);
        BARRY.views.xplore.open(s.path);
      },
    }, [
      el('button', {
        class: 'sc-pick' + (isPicked ? ' on' : ''),
        title: isPicked ? 'Remove from selection' : 'Add to selection',
        text: isPicked ? '\u2713' : '+',
        onclick: (e) => { e.stopPropagation(); togglePick(s.path); },
      }),
      el('div', { class: 'sc-top' }, [
        el('span', { class: 'sc-name', text: 's' + (i.session != null ? i.session : '?') }),
        el('span', { class: 'sc-sub',
                     text: i.start ? BARRY.when(i.start, 'second') : s.name }),
      ]),
      el('div', { class: 'sc-sub', text:
        (s.channels ? s.channels + ' ch · ' : '')
        + (s.fs ? Math.round(s.fs) + ' Hz · ' : '')
        + (s.duration_s ? fmtTime(s.duration_s) : '') }),
      el('div', { class: 'sc-flags' }, [
        /* Which hippocampus. On the card rather than behind a click,
           because pooling a left and a right recording without noticing is
           the kind of mistake that survives into a figure. */
        /* An extraction that did not go cleanly. Only shown when it did
           not: "Success: Clean extraction" on four hundred cards is noise,
           and the three that say "No CA1 SP channel" are the point. */
        (s.extraction_note && !/^success/i.test(s.extraction_note))
          ? el('span', {
              class: 'flagchip bad',
              title: s.extraction_note,
              text: 'extraction',
            }) : null,
        s.needs_processing ? el('span', {
          class: 'flagchip', title: 'The Toothy workbook has this one down '
                                  + 'as still needing processing',
          text: 'to process',
        }) : null,
        s.fissure_channel != null ? el('span', {
          class: 'flagchip hemi',
          title: 'Reference channels — ripple ' + s.ripple_channel
               + ', fissure ' + s.fissure_channel
               + ', hilus ' + s.hilus_channel,
          text: 'fis ' + s.fissure_channel,
        }) : null,
        s.hemisphere ? el('span', {
          class: 'flagchip hemi',
          title: 'Recorded in the ' + (s.hemisphere === 'L' ? 'left' : 'right')
               + ' hippocampus'
               + (s.hemisphere_source ? '\nfrom ' + s.hemisphere_source : ''),
          text: s.hemisphere === 'L' ? 'left' : 'right',
        }) : null,
        s.converted ? el('span', { class: 'flagchip mat', text: '.mat' }) : null,
        s.has_video ? el('span', { class: 'flagchip video', text: 'video' }) : null,
        s.has_tracking ? el('span', { class: 'flagchip', text: 'tracking' }) : null,
        badN ? el('span', { class: 'flagchip bad', text: badN + ' bad' }) : null,
        i.confidence !== 'high' ? el('span', { class: 'flagchip bad',
          text: 'id: ' + i.confidence }) : null,
        remembered ? el('span', {
          class: 'flagchip', title: 'From the registry, not from this scan',
          text: 'remembered',
        }) : null,
        concatChip(s),
        /* What kind of recording this is. On the card because it changes
           what a CSD over it means, and because the only way to work
           through seventy unconfirmed dual implants is to see which they
           are while scanning. */
        BARRY.hk ? BARRY.hk.probeChip(s, {
          small: true,
          onclick: (row, _st, ev) => BARRY.hk.setProbeMenu(
            ev.currentTarget, row, () => { knownLoaded = false;
                                           loadKnown(true); }),
        }) : null,
        projectChip(s),
        vaccChip(s),
        healthPill(s),
        noteChip(s),
      ]),
      flagSet(s),
    ]);
  }

  /* Acquisition gaps, on the card.

     Read from the kept health log rather than by checking the files, so it
     costs nothing per card and says nothing at all about a recording nobody
     has checked -- which is the honest answer for one, and not the same as
     saying it is clean. */
  /* What the cluster makes of this recording, or nothing at all.

     Four states and only two of them draw. `BARRY.vacc.of` returns null for
     a recording nobody has established an answer for -- which is most of a
     fresh scan, because exact ids are minted when headers are read and a
     scanned row often has no gid. Reading that as "the cluster cannot reach
     it" would put an upload badge on four hundred recordings that are
     already sitting on the share it mounts.

     This is the same mistake `canOpen` above documents: a missing field read
     as "no" hid every recording that was certainly openable. Absent is not
     negative, and the only honest thing to draw for it is nothing. */
  /* A path that names a different project than the one this is filed under.

     Raised, never acted on. "Urethane" is the reason this exists and also
     the reason it cannot be a rule: on `D:\KCNT1\urethane\...` it names a
     project, and on `...\M15_s3_baseline_urethane` it names the anaesthetic
     and the recording is PTEN. Both of those are in this lab's data. A rule
     that reads the word gets one of them wrong and says nothing about it.

     So the chip says what the path says and what the record says, and the
     person who can tell the two apart decides. Clicking goes to the project
     picker in Housekeeping; setting it there marks it `manual`, which is
     what clears the flag -- including for the PTEN pair, where the correct
     answer is "leave it, that is the drug". */
  function projectChip(s) {
    const flags = s.project_flags || [];
    if (!flags.length) return null;
    const f = flags[0];
    const others = flags.length > 1 ? ' (+' + (flags.length - 1) + ' more)' : '';
    return el('button', {
      class: 'flagchip warn project-q',
      text: 'project?',
      title: 'A path here says “' + f.word + '”, which usually means '
           + f.suggests + '. This recording is filed under ' + f.filed
           + '.\n\n' + f.path + others
           + '\n\nThat is a hint, not a verdict — the same word names an '
           + 'anaesthetic in the PTEN folders. Click to open the project '
           + 'picker; whatever you set there is kept and the flag goes.',
      onclick: (e) => {
        e.stopPropagation();
        const hk = BARRY.views.housekeeping;
        if (!hk || !hk.inspect || !s.gid) return;
        setMode('housekeeping');
        hk.inspect(s.gid);
      },
    });
  }

  function vaccChip(s) {
    if (!BARRY.vacc) return null;
    const got = BARRY.vacc.of(s);
    if (!got) return null;
    if (got.state !== 'native' && got.state !== 'staged') return null;
    const native = got.state === 'native';
    return el('span', {
      class: 'flagchip vacc ' + got.state,
      text: native ? 'VACC' : 'VACC copy',
      title: native
        ? 'The cluster reads this one where it already is — ' + got.remote
          + '\n\nNothing to upload: it is on a share VACC mounts.'
        : 'A copy of this recording is in cluster scratch.\n\n'
          + 'Scratch is not storage — VACC may clear it without notice, so '
          + 'this is a cache and never the only copy. If it goes, the next '
          + 'run puts it back.',
    });
  }

  function concatChip(s) {
    const c = continuityOf(s);
    if (!c || !c.concat_issue) return null;
    const fixed = !!c.patched;
    /* Three states, not two. A set detected in house was never on the wrong
       clock, so it has nothing to be corrected -- and calling that
       "corrected" would put an event in the history that never happened.
       "Born right" and "repaired" are different things. */
    const safe = !!c.all_concat_safe && c.n_banked > 0;
    const worst = Number(c.max_time_error_ms) || 0;
    const chip = el('button', {
      class: 'flagchip concat' + (fixed ? ' fixed' : '')
             + (safe ? ' safe' : ''),
      title: (safe ? 'The dentate spikes here are safe: detected in house '
                     + 'from the raw .ncs files, so they were never on the '
                     + 'concatenated clock and there is nothing to correct. '
                     + 'The correction is refused for them — applying it '
                     + 'would shift them a second time.\n\n'
                     + 'The recording still has the gaps, though, and '
                     + 'anything else read off it still has to reckon with '
                     + 'them: Kilosort unit times for this session are in '
                     + 'concatenated time.\n\n'
                   : '')
           + c.n_segments + ' segments, ' + (c.n_gaps || 0) + ' gap(s). '
           + 'Times taken from the concatenated file run up to '
           + (worst < 1 ? worst.toFixed(2) : worst.toFixed(1))
           + ' ms early against the raw recording.'
           + (safe
              ? ''
              : fixed
                ? '\n\nThe events banked against it have been moved onto '
                  + 'the recording\u2019s own clock.'
                : (c.n_banked
                   ? '\n\n' + c.n_events + ' banked event(s) have NOT been '
                     + 'corrected.'
                   : '\n\nNothing is banked against it yet.'))
           + '\n\nClick for the gap table.',
      onclick: (e) => { e.stopPropagation(); openContinuity(s); },
    }, [
      /* A break in a line: two strokes with a space where the data is
         missing. It is the thing being reported, at 9 px. */
      el('svg', { class: 'cc-ico', viewBox: '0 0 16 10',
        html: '<path d="M1 5h4M11 5h4M7 2.5v5" />' }),
      /* Always the segment count. The conclusion is the colour and the
         first line of the tooltip; this is the fact, and a list of
         recordings is scanned for facts. */
      el('span', { text: c.n_segments + ' seg' }),
      (fixed || safe) ? el('svg', { class: 'cc-tick', viewBox: '0 0 12 12',
        html: '<path d="m2.5 6.5 2.5 2.5 4.5-5"/>' }) : null,
    ]);
    return chip;
  }

  /* The gap table for one recording.

     The card's chip comes from the health log, which keeps the verdict and
     not the segment map -- so the map is fetched here, when somebody
     actually asks for it, rather than for every card in a list of four
     hundred. */
  async function openContinuity(s) {
    let rep = (health[s.path] || {}).continuity;
    if (!rep || !rep.segments) {
      try {
        rep = await apiPost('/api/session/continuity', { path: s.path });
      } catch (e) {
        toast('Could not read the recording: ' + e.message, 'err');
        return;
      }
    }
    if (!rep || !rep.ok) {
      toast('That recording could not be segmented.', 'err');
      return;
    }
    showContinuity(s, rep);
  }

  /* ======================================================================
     Feature 1 -- Health check
     A truncated channel file, a rig that changed sample rate mid-cohort or a
     recording that is 40 seconds long are all things you would rather learn
     here than three stages into the pipeline.
     ====================================================================== */
  function healthPill(s) {
    const h = health[s.path];
    if (!h) return null;
    const label = h.level === 'ok' ? 'healthy'
      : (h.n_bad ? h.n_bad + ' problem' + (h.n_bad > 1 ? 's' : '')
                 : h.n_warn + ' note' + (h.n_warn > 1 ? 's' : ''));
    return el('span', {
      class: 'health-pill ' + h.level, text: label,
      title: 'Click for the full report',
      onclick: (e) => { e.stopPropagation(); showHealth(s); },
    });
  }

  async function checkHealth(paths, deep) {
    if (healthBusy) { toast('Still checking the last batch.', 'err'); return; }
    healthBusy = true;
    const status = $('#scanStatus');
    status.classList.remove('hidden');
    status.textContent = 'Checking ' + paths.length + ' session(s)'
                       + (deep ? ', reading signal from every channel' : '') + '\u2026';
    try {
      // Chunked so one slow network share does not stall the whole sweep,
      // and so partial results appear as they arrive.
      const size = deep ? 4 : 12;
      for (let i = 0; i < paths.length; i += size) {
        const chunk = paths.slice(i, i + size);
        const res = await apiPost('/api/session/health',
                                  { paths: chunk, deep: !!deep });
        for (const rep of (res.reports || [])) health[rep.path] = rep;
        status.textContent = 'Checked ' + Math.min(i + size, paths.length)
                           + ' of ' + paths.length + '\u2026';
        renderTree();
      }
      const bad = paths.filter((x) => (health[x] || {}).level === 'bad').length;
      const warn = paths.filter((x) => (health[x] || {}).level === 'warn').length;
      status.textContent = 'Health: ' + (paths.length - bad - warn) + ' clean, '
                         + warn + ' with notes, ' + bad + ' with problems.';
      toast('Checked ' + paths.length + ' session(s)', bad ? 'err' : 'ok');
    } catch (e) {
      status.textContent = 'Health check failed: ' + e.message;
    }
    healthBusy = false;
    renderTree();
  }

  function showHealth(s) {
    const h = health[s.path] || {};
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Health \u2014 ' + (s.identity.label || s.name) }),
        el('span', { class: 'sub', text: s.path }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        BARRY.checkList(h.checks || [], {
          extra: (c) => (c.name === 'continuity' && h.continuity
                         && h.continuity.ok && h.continuity.n_segments > 1)
            ? el('button', {
                class: 'btn ghost xs gap-details', text: 'Details',
                title: 'The gap table and the segment map',
                onclick: (e) => {
                  e.stopPropagation();
                  showContinuity(s, h.continuity);
                },
              })
            : null,
        }),
      ]),
      el('div', { class: 'mf' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Deep check (reads every channel)',
          onclick: async () => { closeModal(); await checkHealth([s.path], true);
                                 showHealth(s); },
        }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost sm', text: 'Open folder',
          onclick: () => apiPost('/api/reveal', { path: s.path }).catch(() => {}) }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
  }


  /* ======================================================================
     The gap table behind the continuity row.

     Cheetah closes a record early when acquisition hiccups and the next
     record's timestamp jumps; neo calls that a segment break, and Toothy
     concatenates across it, which closes the gap and labels every later
     sample earlier than it truly is. The check says that happened. This says
     where, and by how much, and on what evidence -- so the claim can be
     checked rather than believed.
     ====================================================================== */
  function showContinuity(s, c) {
    /* The health report carries a capped summary with an n_gaps count; the
       full report from /api/session/continuity carries the gaps themselves
       and no count. Both reach this function -- 'Check every channel'
       swaps the second in for the first -- so the count comes from whichever
       is actually there. Reading only n_gaps made the heading say '0 gap(s)'
       above a table of seven. */
    const nGaps = (c && c.n_gaps != null) ? c.n_gaps : ((c && c.gaps) || []).length;
    const num = (v, dp) => (v == null || !isFinite(v))
      ? '\u2014' : Number(v).toFixed(dp == null ? 3 : dp);
    const ms = (v) => (v == null || !isFinite(v)) ? '\u2014'
      : (Math.abs(v) < 1 ? num(v, 2) + ' ms'
         : (Math.abs(v) < 1000 ? num(v, 1) + ' ms' : num(v / 1e3, 3) + ' s'));

    const table = (head, rows) => el('table', { class: 'gap-table' }, [
      el('thead', {}, [el('tr', {},
        head.map((t) => el('th', { text: t })))]),
      el('tbody', {}, rows.map((r) => el('tr', {},
        r.map((v, i) => el('td', { class: i ? 'n' : '', text: String(v) }))))),
    ]);

    const three = el('div', { class: 'three-clocks' }, [
      el('h4', { text: 'How long is this recording?' }),
      table(['basis', 'seconds', 'who is on it'], [
        ['its own clock', num(c.true_duration_s, 4),
         'the .ncs files, .nev marks, video, and this viewer'],
        ['concatenated', num(c.concat_duration_s, 4),
         'Toothy DS times, lfp_time, CSC_Raw.dat, kilosort units'],
        ['by record index', num(c.record_duration_s, 4),
         'nothing \u2014 it assumes every record is full'],
      ]),
      el('p', { class: 'hint',
        text: 'On a continuous recording these are the same number, which is '
            + 'why the difference went unnoticed. Here they span '
            + ms((Math.max(c.true_duration_s, c.concat_duration_s,
                           c.record_duration_s)
                  - Math.min(c.true_duration_s, c.concat_duration_s,
                             c.record_duration_s)) * 1e3) + '.' }),
    ]);

    /* Where they are, along the recording.

       The table says how much and how far; this says where, which is the
       shape worth seeing -- every gap on this recording falls inside a
       110-second window of an otherwise clean 35 minutes.

       Positions are exact. Widths are not: 50 ms in 2124 s is a fifth of a
       pixel, so each marker has a floor width and the note under the bar
       says so. */
    const span = Number(c.true_duration_s) || 0;
    const allGaps = c.gaps || [];

    /* One track over any window. The whole recording and the stretch the
       gaps are in differ only in where they start and end. */
    const trackOver = (from, to, label) => {
      const width = to - from;
      const at = (t) => Math.max(0, Math.min(100,
        ((Number(t) - from) / width) * 100));
      const track = el('div', { class: 'gap-track' });
      (c.segments || []).forEach((g, i) => {
        const a = at(g.true_t0_s);
        const b = at(Number(g.true_t0_s) + Number(g.duration_s));
        if (b < 0 || a > 100) return;
        const seg = el('div', {
          class: 'gap-seg' + (i % 2 ? ' alt' : ''),
          title: 'segment ' + g.index + ' \u2014 ' + g.n_samples
               + ' samples, ' + num(g.duration_s, 3) + ' s, '
               + (Number(g.error_ms) || 0).toFixed(1)
               + ' ms early in concatenated time',
        });
        seg.style.left = a.toFixed(4) + '%';
        seg.style.width = Math.max(0, b - a).toFixed(4) + '%';
        track.appendChild(seg);
      });
      allGaps.forEach((g, i) => {
        const x = at(g.at_true_time_s);
        if (x < 0 || x > 100) return;
        const mark = el('div', {
          class: 'gap-mark',
          title: 'gap ' + (i + 1) + ' of ' + allGaps.length + ' \u2014 '
               + ms(g.gap_ms) + ' at ' + num(g.at_true_time_s, 3)
               + ' s, after record ' + g.after_record
               + '. Everything past here is '
               + ms(g.cumulative_shift_s * 1e3) + ' early.',
        });
        mark.style.left = x.toFixed(4) + '%';
        track.appendChild(mark);
      });
      return el('div', { class: 'gap-bar' }, [
        label ? el('div', { class: 'gap-label', text: label }) : null,
        track,
        el('div', { class: 'gap-axis' }, [
          el('span', { text: num(from, from < 10 ? 0 : 1) + ' s' }),
          el('span', { class: 'mid', text: label ? '' : nGaps + ' gap(s)' }),
          el('span', { text: num(to, 1) + ' s' }),
        ]),
      ]);
    };

    const first = allGaps.length ? Number(allGaps[0].at_true_time_s) : 0;
    const last = allGaps.length
      ? Number(allGaps[allGaps.length - 1].at_true_time_s) : 0;
    /* One bar.

       A second track zoomed to the gaps was tried, because four of the
       seven share a pixel at full width. It answered that and cost more
       than it was worth: two bars of one recording, where the second is a
       detail of the first, is a picture you have to work out before you can
       read it. The table below gives every boundary to the millisecond, so
       the bar's job is where and how clustered -- which one bar does. */
    const bar = span > 0 ? el('div', {}, [
      trackOver(0, span, ''),
      el('p', { class: 'hint quiet',
        text: 'Positions are to scale. Widths are not \u2014 '
            + ms((c.seconds_lost || 0) * 1e3) + ' in ' + num(span, 0)
            + ' s is far under one pixel, so each marker is drawn at a '
            + 'minimum width to be findable. Hover one for its size.'
            + (allGaps.length > 1
               ? '  They fall between ' + num(first, 1) + ' s and '
                 + num(last, 1) + ' s.'
               : '') }),
    ]) : null;

    const gaps = el('div', {}, [
      el('h4', { text: (nGaps) + ' gap(s) \u2014 data Cheetah never '
                       + 'wrote' }),
      bar,
      table(['after record', 'true time (s)', 'gap', 'shift from here on'],
        (c.gaps || []).map((g) => [
          g.after_record, num(g.at_true_time_s, 3), ms(g.gap_ms),
          ms(g.cumulative_shift_s * 1e3),
        ])),
    ]);

    const segs = el('div', {}, [
      el('h4', { text: c.n_segments + ' segments' }),
      table(['seg', 'samples', 'true start (s)', 'concat start (s)',
             'error'],
        (c.segments || []).map((g) => [
          g.index, g.n_samples, num(g.true_t0_s, 6), num(g.concat_t0_s, 6),
          ms(g.error_ms),
        ])),
      el('p', { class: 'hint',
        text: 'Error is how much earlier the concatenated file calls this '
            + 'stretch than it really is. It is a step, not a drift: '
            + 'constant inside each segment. A dentate spike is 10\u201320 ms '
            + 'wide, so ' + ms(c.max_time_error_ms) + ' is '
            + Math.round(c.max_time_error_ms / 15) + ' event widths.' }),
    ]);

    const how = el('div', { class: 'hint prov' }, [
      el('p', { text: 'Rule: ' + (c.gap_rule || '?') + ', tolerance '
                      + (c.gap_tolerance_us || 0) + ' \u00b5s. This is the '
                      + 'rule spikeinterface uses, so the segmentation here '
                      + 'is the one Toothy saw. neo\u2019s own stricter '
                      + 'default counts clock jitter as a break and finds '
                      + 'thousands.' }),
      el('p', { text: 'Checked ' + ((c.probed || []).length) + ' of '
                      + (c.n_ncs || '?') + ' channels: '
                      + (c.probed || []).join(', ')
                      + ((c.mismatches || []).length
                         ? ' \u2014 ' + c.mismatches.length + ' disagree'
                         : ' \u2014 they agree') + '.' }),
      el('p', { text: 'Clock drift ' + ms((c.clock_drift_s || 0) * 1e3)
                      + ' (implied ' + num(c.implied_fs, 2) + ' Hz against a '
                      + 'nominal rate) is not data loss and is counted '
                      + 'separately.' }),
      el('p', { text: (c.n_short_records || 0) + ' record(s) closed early, '
                      + (c.n_short_inside || 0) + ' of them without making a '
                      + 'break; ' + ms((c.sub_threshold_lost_s || 0) * 1e3)
                      + ' went unrecorded at those. Measured from the '
                      + 'timestamps rather than from the '
                      + (c.unused_record_slots || 0) + ' unused buffer slots '
                      + '\u2014 a record whose next timestamp follows its own '
                      + 'short count is simply short, and lost nothing.' }),
      el('p', { text: 'Segment map ' + (c.gap_map_sha || '?')
                      + (c.truncated ? '  (tables capped here; the whole map '
                                     + 'is on /api/session/continuity)' : '') }),
    ]);

    /* What clock the banked events for this session are on. Filled in
       after the modal is up, because it is a second request and the gap
       table is worth showing without waiting for it. */
    const basisBox = el('div', { class: 'basis-box' }, [
      el('p', { class: 'hint', text: 'Checking what clock the banked events '
                                     + 'are on\u2026' }),
    ]);
    apiPost('/api/session/timebasis',
            { path: s.path, gid: (s.stored && s.stored.gid) || s.gid })
      .then((res) => {
        basisBox.innerHTML = '';
        const rows = (res && res.entries) || [];
        if (!rows.length) {
          basisBox.appendChild(el('p', { class: 'hint',
            text: 'No event set is banked against this recording, so there '
                + 'is nothing carrying these times.' }));
          return;
        }
        basisBox.appendChild(el('h4', { text: 'Banked events' }));
        for (const r of rows) {
          const b = r.basis || {};
          const concat = b.basis === 'toothy_concat';
          basisBox.appendChild(el('div', {
            class: 'basis-row' + (r.correctable ? ' off' : ''),
          }, [
            el('div', { class: 'basis-head' }, [
              el('span', { class: 'basis-name',
                           text: (r.name || r.type || 'events')
                                 + '  \u00b7  ' + (r.n || 0) + ' event(s)' }),
              el('span', { class: 'basis-chip ' + (concat ? 'concat' : 'true'),
                           text: concat ? 'concatenated' : 'raw clock' }),
            ]),
            el('p', { class: 'hint', text: r.reason || '' }),
            b.why ? el('p', { class: 'hint quiet', text: b.why }) : null,
          ]));
        }
        /* What the correction actually does, and a way to look at it.

           "A separate, explicit step" on its own reads like something
           nobody has built. It exists; saying what it does is the
           difference between a warning and a thing you can act on. */
        const can = rows.filter((r) => r.correctable);
        if (can.length) {
          basisBox.appendChild(el('div', { class: 'fix-box' }, [
            el('h4', { text: 'How this gets corrected' }),
            el('ol', { class: 'fix-steps' }, [
              el('li', { text: 'Every event time is moved onto the '
                  + 'recording\u2019s own clock \u2014 the one the .ncs '
                  + 'files, the .nev marks and the video are on. The shift '
                  + 'is zero before the first gap and grows by each gap '
                  + 'after it.' }),
              el('li', { text: 'Times change and nothing else does. Every '
                  + 'labelled event keeps its label and its id; nothing is '
                  + 're-detected, and no candidate is added or removed.' }),
              el('li', { text: 'It lands as a new version of the banked set, '
                  + 'with the old one kept. Reversing it is '
                  + '\u201crestore the previous version\u201d, not a '
                  + 'second pass of arithmetic.' }),
              el('li', { text: 'Kilosort unit times for this session stay in '
                  + 'concatenated time and need the same conversion before '
                  + 'unit/DS comparisons mean anything.' }),
            ]),
            el('div', { class: 'fix-acts' }, [
              el('button', {
                class: 'btn sm', text: 'Preview the correction\u2026',
                title: 'Works out exactly what would change and shows it. '
                     + 'Writes nothing.',
                onclick: (ev) => {
                  ev.stopPropagation();
                  previewRetime(s, c, can[0]);
                },
              }),
              el('span', { class: 'hint quiet',
                text: 'The preview writes nothing. Applying is its own '
                    + 'button, inside it.' }),
            ]),
          ]));
        } else {
          basisBox.appendChild(el('p', { class: 'hint quiet',
            text: 'Nothing here can be corrected automatically, for the '
                + 'reason given against each set above. Correcting a set '
                + 'whose clock cannot be established would introduce the '
                + 'very error this is looking for.' }));
        }
      })
      .catch((e) => {
        basisBox.innerHTML = '';
        basisBox.appendChild(el('p', { class: 'hint',
          text: 'Could not check the banked events: ' + e.message }));
      });

    showModal(el('div', { class: 'continuity-modal' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Continuity \u2014 ' + (s.identity.label || s.name) }),
        el('span', { class: 'sub', text: c.n_segments + ' segments, '
                     + ms((c.seconds_lost || 0) * 1e3) + ' never written' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [three, gaps, segs, basisBox, how]),
      el('div', { class: 'mf' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Check every channel',
          title: 'Parses all ' + (c.n_ncs || '?') + ' files rather than a '
               + 'spot-check. Slower, and the answer to trust before acting '
               + 'on one.',
          onclick: async (ev) => {
            const b = ev.target;
            b.disabled = true;
            b.textContent = 'Reading ' + (c.n_ncs || '?') + ' channels\u2026';
            try {
              const full = await apiPost('/api/session/continuity',
                                         { path: s.path, all_channels: true });
              closeModal();
              if (health[s.path]) health[s.path].continuity = full;
              showContinuity(s, full);
            } catch (err) {
              b.disabled = false;
              b.textContent = 'Check every channel';
              toast('Could not read them all: ' + err.message, 'err');
            }
          },
        }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
  }


  /* ======================================================================
     Re-timing a banked set onto the recording's own clock.

     Preview first, always, and the preview is a server dry run rather than
     a guess made here -- so what it shows is what the write would do,
     produced by the code that would do it.
     ====================================================================== */
  /* "every 2nd", "every 3rd". A bar that quietly drops events without
     saying how many it kept is a bar that lies about density. */
  function wordEnding(n) {
    if (n % 100 >= 11 && n % 100 <= 13) return 'th';
    return { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th';
  }

  async function previewRetime(sess, cont, entry, fromVersion) {
    const num = (v, dp) => (v == null || !isFinite(v))
      ? '\u2014' : Number(v).toFixed(dp == null ? 3 : dp);
    const ms = (v) => (v == null || !isFinite(v)) ? '\u2014'
      : (Math.abs(v) < 1 ? num(v, 2) + ' ms'
         : (Math.abs(v) < 1000 ? num(v, 1) + ' ms' : num(v / 1e3, 3) + ' s'));

    const ask = (v) => apiPost('/api/session/retime', {
      path: sess.path, entry_id: entry.entry_id,
      gid: (sess.stored && sess.stored.gid) || sess.gid || '', kind: 'ds',
      from_version: v == null ? null : v,
    });

    let res;
    try {
      res = await ask(fromVersion);
    } catch (e) {
      toast('Could not work out the correction: ' + e.message, 'err');
      return;
    }
    /* A refusal is not the end of it any more.

       "Already on the recording's clock" used to close the window, which
       was right when the only thing correctable was the live set. Correcting
       again means reading a version that predates the correction, so the
       refusal now offers that instead of only stating itself. */
    if (!res.ok && res.reason) {
      const usable = (((res.versions || {}).versions) || [])
        .filter((v) => v.usable);
      if (!usable.length) {
        toast(res.reason, 'err', 9000);
        return;
      }
      const pick = await pickVersion(res.reason, usable,
                                     (res.versions || {}).drops_fields);
      if (pick == null) return;
      try {
        res = await ask(pick);
      } catch (e) {
        toast('Could not work out the correction: ' + e.message, 'err');
        return;
      }
      if (!res.ok && res.reason) { toast(res.reason, 'err', 9000); return; }
      fromVersion = pick;
    }
    const pv = res.preview || {};
    const ent = res.entry || {};
    const set = res.set || {};
    const vinfo = res.versions || {};
    const vrows = vinfo.versions || [];
    const srcV = res.from_version == null ? vinfo.current_version
                                          : res.from_version;

    /* The version this is reading, and every other one it could.

       Greyed rather than hidden where it cannot be a source: a version
       missing from a list raises the question of why, and the answer --
       "it is already corrected", "its snapshot has not synced here" -- is
       worth more than a shorter list. */
    const versionRow = !vrows.length ? null : el('div', { class: 'fix-box' }, [
      el('h4', { text: 'Which version to correct' }),
      el('p', { class: 'hint quiet',
        text: 'Versions differ in the decisions on them, so this picks the '
            + 'labels as well as the times. Whichever is read, the result '
            + 'lands as a new version and nothing is overwritten.' }),
      el('div', { class: 'ver-pick' }, vrows.map((v) => el('button', {
        class: 'ver-chip' + (v.v === srcV ? ' on' : '')
               + (v.usable ? '' : ' off'),
        disabled: v.usable ? null : 'disabled',
        title: v.usable
          ? ((v.note || '') + (v.by ? '\n\u2014 ' + v.by : '')
             + (v.at ? '\n' + v.at : ''))
          : 'Cannot be corrected from: ' + v.why_not,
        onclick: () => {
          if (v.v === srcV) return;
          closeModal();
          previewRetime(sess, cont, entry, v.v);
        },
      }, [
        el('strong', { text: 'v' + v.v }),
        el('span', { class: 'ver-n', text: (v.n != null ? v.n : '?') + ' ev' }),
        v.current ? el('span', { class: 'ver-tag', text: 'current' }) : null,
        v.retimed ? el('span', { class: 'ver-tag', text: 'corrected' }) : null,
      ].filter(Boolean)))),
      /* Two consequences of reading an older version, both stated where
         the choice is made rather than in a response body. */
      res.set_skipped
        ? el('p', { class: 'warn-line', text: res.set_skipped })
        : null,
      (ent.drops_fields && ent.drops_fields.length)
        ? el('p', { class: 'warn-line',
            text: 'A version snapshot holds a start and a label only, so '
                + ent.drops_fields.join(', ') + ' would not survive being '
                + 'read back from it.' })
        : null,
    ].filter(Boolean));

    const table = (head, rows) => el('table', { class: 'gap-table' }, [
      el('thead', {}, [el('tr', {}, head.map((t) => el('th', { text: t })))]),
      el('tbody', {}, rows.map((r) => el('tr', {},
        r.map((v, i) => el('td', { class: i ? 'n' : '', text: String(v) }))))),
    ]);

    /* The recording, with every event on it.

       The tables say how much and how many; this says where -- which of my
       events are on the wrong side of a gap. Each mark is an event at the
       time it has now, coloured by whether the correction moves it, with
       the gap boundaries over the top. */
    const span = Number((res.continuity || {}).true_duration_s)
              || Number(cont.true_duration_s) || 0;
    const moves = ent.moves || [];
    let eventBar = null;
    if (span > 0 && moves.length) {
      const at = (t) => Math.max(0, Math.min(100, (Number(t) / span) * 100));
      const track = el('div', { class: 'gap-track ev-track' });
      /* Each stretch, shaded by how far it moves, so the steps are visible
         behind the events sitting in them. */
      (pv.shifts || []).forEach((g, i) => {
        const a = at(g.concat_from_s);
        const b = at(g.concat_to_s);
        const seg = el('div', {
          class: 'gap-seg' + (i % 2 ? ' alt' : '')
                 + (Math.abs(g.shift_ms) > 0.0005 ? ' shifts' : ''),
          title: 'everything from ' + num(g.concat_from_s, 3) + ' s to '
               + num(g.concat_to_s, 3) + ' s moves by ' + ms(g.shift_ms),
        });
        seg.style.left = a.toFixed(4) + '%';
        seg.style.width = Math.max(0, b - a).toFixed(4) + '%';
        track.appendChild(seg);
      });
      /* The events. Capped at what a bar can hold: past a few thousand the
         marks overlap into a solid block and say less, not more. */
      const step = Math.max(1, Math.ceil(moves.length / 1800));
      let drawn = 0;
      for (let i = 0; i < moves.length; i += step) {
        const m = moves[i];
        const shifted = Math.abs(m[2]) > 0.0005;
        const tick = el('div', {
          class: 'ev-mark' + (shifted ? ' moved' : ''),
          title: (m[3] || 'event') + ' at ' + num(m[0], 4) + ' s'
               + (shifted ? '  \u2192  ' + num(m[1], 4) + ' s  ('
                            + ms(m[2]) + ' later)'
                          : '  \u2014 does not move'),
        });
        tick.style.left = at(m[0]).toFixed(4) + '%';
        track.appendChild(tick);
        drawn += 1;
      }
      /* And where the data is missing, over the top of both. */
      ((cont && cont.gaps) || []).forEach((g, i) => {
        const mark = el('div', {
          class: 'gap-mark',
          title: 'gap ' + (i + 1) + ' \u2014 ' + ms(g.gap_ms) + ' at '
               + num(g.at_true_time_s, 3) + ' s. Everything past here moves '
               + 'by ' + ms(g.cumulative_shift_s * 1e3) + '.',
        });
        mark.style.left = at(g.at_true_time_s).toFixed(4) + '%';
        track.appendChild(mark);
      });

      eventBar = el('div', { class: 'gap-bar' }, [
        el('div', { class: 'gap-label', text: 'the recording, and where the '
                                              + 'events sit on it' }),
        track,
        el('div', { class: 'gap-axis' }, [
          el('span', { text: '0 s' }),
          el('span', { class: 'mid',
            text: (ent.n_shifted != null ? ent.n_shifted : '?') + ' of '
                + (ent.moved || 0) + ' move' }),
          el('span', { text: num(span, 0) + ' s' }),
        ]),
        el('p', { class: 'hint quiet',
          text: 'Each mark is an event, at the time it has now. Coloured ones '
              + 'move; the rest are before the first gap and stay exactly '
              + 'where they are. The movement itself is not drawn to scale '
              + '\u2014 ' + ms(ent.shift_max_ms) + ' in ' + num(span, 0)
              + ' s is a twentieth of a pixel, so it is shown as colour and '
              + 'said in numbers rather than as a displacement you could not '
              + 'see.'
              + (drawn < moves.length
                 ? '  Showing every ' + step + wordEnding(step) + ' event, '
                   + drawn + ' marks for ' + moves.length + '.'
                 : '') }),
      ]);
    }

    const body = el('div', {}, [
      el('p', { class: 'lead', text: (ent.moved || 0) + ' event(s) move. '
          + 'Every one keeps its label and its id \u2014 nothing is '
          + 're-detected, and no candidate is added or removed.' }),
      eventBar,
      versionRow,
      el('h4', { text: 'How far each stretch of the recording moves' }),
      table(['stretch from (s)', 'to (s)', 'moves by'],
        (pv.shifts || []).map((g) => [
          num(g.concat_from_s, 3), num(g.concat_to_s, 3), ms(g.shift_ms),
        ])),
      el('h4', { text: 'Every event, before and after' }),
      /* Scrolls, one line each, with the ones that actually move picked
         out. Showing the first eight meant eight rows of 0.00 ms, because
         every gap on this recording is at 1762 s and the set starts at
         1.7 s. */
      el('div', { class: 'move-list' },
        (ent.moves || []).map((m) => {
          const shifted = Math.abs(m[2]) > 0.0005;
          return el('div', { class: 'move-row' + (shifted ? ' moved' : '') }, [
            el('span', { class: 'mv-was', text: num(m[0], 4) }),
            el('span', { class: 'mv-arrow', text: shifted ? '\u2192' : '=' }),
            el('span', { class: 'mv-now', text: num(m[1], 4) }),
            el('span', { class: 'mv-shift', text: shifted ? ms(m[2]) : '' }),
            el('span', { class: 'mv-label', text: m[3] || '' }),
          ]);
        })),
      el('p', { class: 'hint quiet',
        text: (ent.n_shifted != null ? ent.n_shifted : '?') + ' of '
            + (ent.moved || 0) + ' move; the rest are before the first gap '
            + 'and stay exactly where they are.'
            + (ent.moves_capped
               ? '  Showing the first ' + (ent.moves || []).length + '.'
               : '') }),
      el('div', { class: 'fix-facts' }, [
        el('p', { text: set.was != null
            ? 'Curation set: ' + set.was + ' candidate(s), '
              + (set.decided != null ? set.decided : 0)
              + ' of them decided. All of the decisions survive \u2014 the '
              + 'edit is keyed on each event\u2019s id, not on its time.'
            : 'The curation set is edited alongside the bank, keyed on each '
              + 'event\u2019s id rather than on its time, so every decision '
              + 'survives.' }),
        el('p', { text: 'Shift runs from ' + ms(ent.shift_min_ms) + ' to '
            + ms(ent.shift_max_ms) + '. Order is preserved: '
            + (ent.order_held ? 'checked and held.' : 'NOT held \u2014 '
               + 'this would be refused.') }),
        (ent.unplaceable
          ? el('p', { class: 'warn-line', text: ent.unplaceable
              + ' event(s) have no time on the other clock, so nothing '
              + 'would be written.' })
          : null),
      ]),
      el('h4', { text: 'Worth knowing first' }),
      el('ul', { class: 'fix-steps' },
        (pv.caveats || []).map((t) => el('li', { text: t }))),
    ]);

    const canApply = res.ok && !ent.error && !set.error && !ent.unplaceable;
    showModal(el('div', { class: 'continuity-modal' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Preview \u2014 correct the event times' }),
        el('span', { class: 'sub', text: (entry.name || 'events') + '  \u00b7  '
            + (entry.n || 0) + ' event(s)  \u00b7  nothing is written yet' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [body]),
      el('div', { class: 'mf' }, [
        el('span', { class: 'hint quiet', text: canApply
          ? 'Applying mints a new version. The current one is kept and can '
            + 'be restored from the version history.'
          : 'This cannot be applied as it stands.' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Close', onclick: closeModal }),
        canApply ? el('button', {
          class: 'btn', text: 'Apply the correction\u2026',
          onclick: async (ev) => {
            const b = ev.target;
            /* Asked, not assumed. This button sits in the corner of a
               modal somebody is scrolling through, and what it does is
               rewrite 1224 timestamps -- so it says what it is about to
               do, names the version it would mint and the one it keeps,
               and writes only after that. */
            const vNow = ent.current_version;
            const vNext = ent.next_version;
            const ok = await BARRY.confirm(
              'Correct ' + (entry.n || 0) + ' event time(s)?',
              el('div', { class: 'fix-facts' }, [
                el('p', { text: 'This writes a new version of the banked '
                    + 'set and of the curation set, with every time moved '
                    + 'onto the recording\u2019s own clock.' }),
                el('ul', { class: 'fix-steps' }, [
                  el('li', { text: (ent.n_shifted != null ? ent.n_shifted
                                    : '?') + ' of ' + (ent.moved || 0)
                      + ' event(s) move, by ' + ms(ent.shift_min_ms)
                      + ' to ' + ms(ent.shift_max_ms) + '.' }),
                  el('li', { text: 'The set becomes v' + vNext
                      + ', read from v' + srcV
                      + '. v' + vNow + ' is kept with its snapshot, and '
                      + 'deleting v' + vNext + ' afterwards puts the times '
                      + 'back and marks the recording unresolved again.' }),
                  res.set_skipped
                    ? el('li', { class: 'warn-line', text: res.set_skipped })
                    : null,
                  /* A number when there is one, and the sentence
                     without it when there is not. */
                  el('li', { text: (set.decided != null
                      ? 'All ' + set.decided + ' decision(s) survive'
                      : 'Every decision on the set survives')
                      + ' \u2014 the edit is keyed on each event\u2019s id, '
                      + 'not on its time. No candidate is added or '
                      + 'removed.' }),
                  el('li', { text: 'This exact correction cannot land twice '
                      + '\u2014 same map, same source version is refused. '
                      + 'Running it again from a different version, or '
                      + 'against a re-checked folder, is allowed.' }),
                ].filter(Boolean)),
              ]),
              'Write v' + vNext);
            if (!ok) return;
            b.disabled = true;
            b.textContent = 'Applying\u2026';
            try {
              const done = await apiPost('/api/session/retime', {
                path: sess.path, entry_id: entry.entry_id,
                gid: (sess.stored && sess.stored.gid) || sess.gid || '',
                kind: 'ds', apply: true,
                from_version: res.from_version,
              });
              if (!done.ok) {
                throw new Error((done.entry || {}).error
                                || (done.set || {}).error
                                || done.reason || done.error || 'refused');
              }
              closeModal();
              const v = (done.entry || {}).version;
              toast('Corrected. The set is now v' + v + ' on the '
                    + 'recording\u2019s own clock, read from v' + srcV
                    + '. Deleting v' + v + ' puts the times back and marks '
                    + 'this recording unresolved again.', 'ok', 11000);
              // The card still says "unpatched" until the cached summary
              // is thrown away, and half a minute of that reads as a
              // correction that did not work.
              refreshHealth();
            } catch (err) {
              b.disabled = false;
              b.textContent = 'Apply the correction\u2026';
              toast('Not applied: ' + err.message, 'err');
            }
          },
        }) : null,
      ]),
    ]));
  }

  /* Which version to read, asked on its own.

     Used when the correction has already been run: there is no preview to
     hang a picker off yet, because the server refused to build one until it
     is told where to read from. */
  function pickVersion(why, rows, drops) {
    return new Promise((resolve) => {
      let picked = null;
      const chips = el('div', { class: 'ver-pick' });
      const draw = () => {
        chips.innerHTML = '';
        rows.forEach((v) => chips.appendChild(el('button', {
          class: 'ver-chip' + (v.v === picked ? ' on' : ''),
          title: (v.note || '') + (v.by ? '\n\u2014 ' + v.by : ''),
          onclick: () => { picked = v.v; draw(); go.disabled = false; },
        }, [
          el('strong', { text: 'v' + v.v }),
          el('span', { class: 'ver-n',
                       text: (v.n != null ? v.n : '?') + ' ev' }),
          v.current ? el('span', { class: 'ver-tag', text: 'current' }) : null,
        ].filter(Boolean))));
      };
      const go = el('button', {
        class: 'btn', text: 'Preview from this version', disabled: 'disabled',
        onclick: () => { closeModal(); resolve(picked); },
      });
      draw();
      showModal(el('div', { class: 'continuity-modal' }, [
        el('div', { class: 'mh' }, [
          el('h3', { text: 'Correct it again, from an earlier version' }),
          el('div', { class: 'spacer' }),
          el('button', { class: 'close-x',
            onclick: () => { closeModal(); resolve(null); },
            html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/>'
                + '</svg>' }),
        ]),
        el('div', { class: 'mb' }, [
          el('p', { class: 'warn-line', text: why }),
          el('p', { text: 'Correcting it again means reading a version from '
              + 'before the correction \u2014 applying the shift to a set '
              + 'that already has it would double every offset. These are '
              + 'the versions that predate it.' }),
          chips,
          (drops && drops.length)
            ? el('p', { class: 'hint quiet',
                text: 'A snapshot holds a start and a label only, so '
                    + drops.join(', ') + ' would not come back with it.' })
            : null,
        ].filter(Boolean)),
        el('div', { class: 'mf' }, [
          el('span', { class: 'hint quiet',
                       text: 'This only builds a preview. Nothing is '
                           + 'written until you apply it.' }),
          el('div', { class: 'spacer' }),
          el('button', { class: 'btn ghost', text: 'Cancel',
            onclick: () => { closeModal(); resolve(null); } }),
          go,
        ]),
      ]));
    });
  }

  /* ======================================================================
     Feature 2 -- Quality flags and notes
     Which recordings are in the analysis and which were thrown out is a
     decision that otherwise lives in someone's notebook. Keyed on session
     identity, so it survives a re-mount or a rename like bad channels do.
     ====================================================================== */
  function qualityOf(s) {
    return (s.stored && s.stored.quality) || '';
  }

  function flagSet(s) {
    const cur = qualityOf(s);
    const mk = (key, label, title) => el('button', {
      class: 'flag-btn ' + key + (cur === key ? ' on' : ''),
      text: label, title,
      onclick: async (e) => {
        e.stopPropagation();
        await setQuality(s, cur === key ? '' : key);
      },
    });
    return el('div', { class: 'flag-set' }, [
      mk('good', 'good', 'Include in analysis'),
      mk('review', 'review', 'Needs a second look'),
      mk('exclude', 'exclude', 'Left out of the analysis'),
      el('button', {
        class: 'flag-btn', text: 'note', title: 'Notes on this recording',
        onclick: (e) => { e.stopPropagation(); editNote(s); },
      }),
    ]);
  }

  function noteChip(s) {
    const n = (s.stored && s.stored.notes) || '';
    if (!n) return null;
    return el('span', { class: 'flagchip', text: 'note', title: n });
  }

  /* The most-clicked write in the app, and it used to wait on the server
     before the chip moved -- so going down a list flagging recordings meant a
     pause after every single one, on the one action people repeat dozens of
     times in a sitting.

     The answer is already known locally: you pressed "review", so the chip
     says review. The write follows, the server's copy of the record replaces
     the guess when it lands, and a failure puts the old flag back and says so
     rather than leaving a mark nobody made. */
  async function setQuality(s, quality) {
    const was = s.stored;
    s.stored = Object.assign({}, s.stored || {}, { quality: quality || null });
    renderTree();
    toast(quality ? 'Marked ' + (s.identity.label || s.name) + ' "' + quality + '"'
                  : 'Cleared the flag', 'ok', 2400);
    try {
      const res = await apiPost('/api/session/note',
                                { identity: s.identity, quality });
      if (res.session) { s.stored = res.session; renderTree(); }
    } catch (e) {
      s.stored = was;
      renderTree();
      toast('That did not save: ' + e.message, 'err', 8000);
    }
  }

  function editNote(s) {
    const box = el('textarea', {
      style: 'width:100%;height:150px;font-size:12.5px;line-height:1.6',
      placeholder: 'Anything the next person should know \u2014 electrode '
                 + 'position, what the animal was doing, why it was excluded\u2026',
      text: (s.stored && s.stored.notes) || '',
    });
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Notes \u2014 ' + (s.identity.label || s.name) }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [box]),
      el('div', { class: 'mf' }, [
        el('span', { class: 'hint', text: 'Saved against the session ID, so it '
                                        + 'follows the recording.' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Save',
          onclick: async () => {
            try {
              const res = await apiPost('/api/session/note',
                                        { identity: s.identity, notes: box.value });
              s.stored = res.session || s.stored;
              closeModal();
              renderTree();
              toast('Note saved', 'ok');
            } catch (e) { toast(e.message, 'err'); }
          },
        }),
      ]),
    ]));
  }

  /* ======================================================================
     Feature 3 -- Compare and export a manifest
     The table that goes into a methods section, built from what is already
     on screen instead of retyped.
     ====================================================================== */
  function manifestRows(list) {
    return list.map((s) => ({
      label: s.identity.label || s.name,
      cohort: s.identity.group || '',
      mouse: s.identity.mouse != null ? s.identity.mouse : '',
      session: s.identity.session != null ? s.identity.session : '',
      start: s.identity.start || '',
      channels: s.channels || '',
      fs_hz: s.fs ? Math.round(s.fs) : '',
      duration_s: s.duration_s ? Math.round(s.duration_s) : '',
      quality: qualityOf(s),
      health: (health[s.path] || {}).level || '',
      bad_channels: (s.stored && s.stored.bad_channels) || [],
      video: s.has_video ? 'yes' : 'no',
      tracking: s.has_tracking ? 'yes' : 'no',
      converted: s.converted ? 'yes' : 'no',
      id_confidence: s.identity.confidence || '',
      notes: (s.stored && s.stored.notes) || '',
      path: s.path,
    }));
  }

  function compare() {
    const list = picked.size
      ? sessions.filter((s) => picked.has(s.path))
      : sessions.filter(matches);
    if (!list.length) { toast('Nothing to compare.', 'err'); return; }
    const rows = manifestRows(list.slice(0, 24));
    const keys = Object.keys(rows[0]).filter((k) => k !== 'path');

    const table = el('table', { class: 'cmp-table' }, [
      el('thead', {}, [el('tr', {}, [el('th', { text: '' })].concat(
        rows.map((r) => el('th', { text: r.label }))))]),
      el('tbody', {}, keys.map((k) => {
        const vals = rows.map((r) => String(
          Array.isArray(r[k]) ? r[k].join(' ') : (r[k] === '' ? '\u2014' : r[k])));
        const differ = new Set(vals).size > 1;
        return el('tr', {}, [el('td', { class: 'k', text: k })].concat(
          vals.map((v) => el('td', {
            class: differ ? 'differ' : '', text: v, title: v,
          }))));
      })),
    ]);

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Compare ' + rows.length + ' session(s)' }),
        el('span', { class: 'sub', text: 'differing rows are highlighted' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [el('div', { class: 'cmp-table-wrap' }, [table])]),
      el('div', { class: 'mf' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Export CSV',
          onclick: () => exportManifest(list),
        }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
  }

  function exportManifest(list) {
    const rows = manifestRows(list || (picked.size
      ? sessions.filter((s) => picked.has(s.path))
      : sessions.filter(matches)));
    if (!rows.length) { toast('Nothing to export.', 'err'); return; }
    BARRY.download('/api/session/manifest',
                    { rows, name: 'sessions.csv' }, 'sessions.csv');
    BARRY.activity.log('sessions.manifest', { n: rows.length });
  }

  function togglePick(path) {
    if (picked.has(path)) picked.delete(path); else picked.add(path);
    renderTree();
  }

  function renderPickBar() {
    let bar = $('#sessPickBar');
    if (!picked.size) { if (bar) bar.remove(); return; }
    if (!bar) {
      bar = el('div', { class: 'pick-bar', id: 'sessPickBar' });
      $('#sessTree').parentNode.insertBefore(bar, $('#sessTree'));
    }
    bar.innerHTML = '';
    bar.appendChild(el('span', { class: 'stat-chip good',
      text: picked.size + ' selected' }));
    bar.appendChild(el('span', { class: 'hint',
      style: 'font-size:11px;color:var(--text-3)',
      text: 'Ctrl/Cmd-click or use + to add more.' }));
    bar.appendChild(el('div', { style: 'flex:1' }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Clear',
      onclick: () => { picked.clear(); renderTree(); },
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Health check',
      onclick: () => checkHealth(Array.from(picked), false),
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Compare',
      onclick: compare,
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Export CSV',
      onclick: () => exportManifest(),
    }));
    bar.appendChild(el('button', {
      class: 'btn sm',
      text: 'Open ' + picked.size + ' in Xplorefinder',
      onclick: openPicked,
    }));
  }

  async function openPicked() {
    const paths = Array.from(picked);
    if (!paths.length) return;
    picked.clear();
    rememberOpen(paths);
    setView('xplore');

    // Opening in series, not in parallel: each open reads headers and the
    // server keeps one session resident at a time, so a burst of concurrent
    // opens just fights itself.
    let opened = 0;
    for (const p of paths) {
      const sess = await BARRY.views.xplore.open(p);
      if (sess) opened += 1;
    }
    // Give every opened recording a pane if the layout can hold them.
    BARRY.views.xplore.fillPanes();
    renderTree();
    toast('Opened ' + opened + ' of ' + paths.length + ' session(s)',
          opened === paths.length ? 'ok' : 'err');
    BARRY.activity.log('sessions.open_multi', { n: opened, requested: paths.length });
  }

  /* Reopen the previous session(s) -- IN THE BACKGROUND, and that is the
     whole of what changed here.

     It used to finish with `setView('xplore')`. A quarter of a second after
     the interface appeared, whatever somebody was looking at was replaced
     by a voltage trace of yesterday's recording, which then took several
     seconds to draw itself. "Opening Jarvis snaps you into places" was
     this line: you were put somewhere you had not asked to go, and if you
     had already started clicking, your click landed there instead of where
     you aimed it.

     The recording still reopens -- that is worth having, and core.js does
     exactly the same thing for `?csc=`. It reopens underneath whatever is
     on screen, and says so once, quietly, so that finding it in
     XploreFinder later is not a surprise.

     Announced rather than done silently, for the same reason it always
     was: a window that springs open with old data and no explanation is
     worse than an empty one. */
  async function restoreLast(paths) {
    const names = paths.map((p) => baseName(p));
    for (const p of paths) {
      const sess = await BARRY.views.xplore.open(p);
      if (!sess) {
        toast('Could not reopen ' + baseName(p) + ' — it may be on a drive '
              + 'that is not mounted.', 'err', 8000);
      }
    }
    if (BARRY.views.xplore.state.order.length > 1) BARRY.views.xplore.fillPanes();
    /* Only if they are not already there. Somebody who walked over to
       XploreFinder while this was loading gets the recording they were
       waiting for; somebody who stayed in the pipeline gets a line of text
       and keeps their place. */
    if (BARRY.state.view === 'xplore') {
      if (BARRY.views.xplore.onShow) BARRY.views.xplore.onShow();
    } else {
      toast('Reopened ' + names.join(', ') + ' in XploreFinder, in the '
            + 'background.', null, 6000);
    }
  }

  /* ---------- init ---------- */
  function init() {
    $$('#sessModeSeg button').forEach((b) =>
      b.addEventListener('click', () => setMode(b.dataset.mode)));

    $('#rootGo').addEventListener('click', () => start());
    $('#rootPath').addEventListener('keydown', (e) => { if (e.key === 'Enter') start(); });
    $('#sessScan').addEventListener('click', () => start());
    $('#rootBrowse').addEventListener('click', async () => {
      const p = await pickPath('folder', '');
      if (p) { $('#rootPath').value = p; start(p); }
    });
    $('#sessReveal').addEventListener('click', () => {
      const p = $('#rootPath').value;
      if (p) apiPost('/api/reveal', { path: p }).catch(() => {});
    });
    $('#sessHealth').addEventListener('click', () => {
      const list = picked.size
        ? Array.from(picked)
        : sessions.filter(matches).map((x) => x.path);
      if (!list.length) { toast('Scan a root first.', 'err'); return; }
      checkHealth(list, false);
    });
    $('#sessCompare').addEventListener('click', compare);

    let deb = null;
    $('#sessSearch').addEventListener('input', (e) => {
      query = e.target.value;
      clearTimeout(deb);
      deb = setTimeout(renderTree, 120);
    });

    renderScanOpts();
    /* The nine pills are gone; the bar builds itself from FILTERS, so
       there is nothing left to wire up one at a time. */
    renderFilterBar();

    renderRecents();

    // ?root=<path> scans straight away, so a data root can be bookmarked.
    const params = new URLSearchParams(location.search);
    const preset = params.get('root');
    if (preset) { $('#rootPath').value = preset; setTimeout(() => start(preset), 60); }
    else if (recents().length) { $('#rootPath').value = recents()[0]; }

    /* Reopen what was last being looked at, unless this window was
       launched with its own target (a pop-out, or a deep link).

       `role` as well as `csc`. A pane pop-out names the recording it is
       showing, so `csc` caught it -- but the comodulogram window is opened
       as `/?role=comod#comod` and names no recording, because it reads the
       window and the channel from its opener. It fell through this test,
       and 250 ms after it opened, `restoreLast` reopened the last recording
       and finished with `setView('xplore')`: the form somebody had just
       been given was replaced by a voltage trace, with "Reopening…" and
       "view restored" as the only clue. Every pop-out sets a role. */
    if (!params.get('csc') && !params.get('role') && !preset) {
      const last = lastOpen();
      /* Later than it was, and deliberately.

         250 ms put the read of a whole recording -- headers for every
         channel, then a first window of samples -- into the middle of the
         page still fetching its own catalogue, and both were slower for
         it. Nothing is waiting on this: it is a convenience that lands
         when it lands, and the two seconds buy a first click that is not
         competing with a disk. */
      if (last.length) setTimeout(() => restoreLast(last), 2000);
    }

    /* The catalogue this view is built from is one of the three the server
       answers out of last boot's cache. If the real one turns out to be
       the same -- which it is on almost every boot -- this never runs. */
    if (BARRY.warm) BARRY.warm.onFresh('registry', warmRegistry);
  }

  /* Two views of the same subject: what is on this drive, and what the lab
     has. Kept in one section because "the sessions" is one idea, and a
     twelfth rail entry for the other half of it would not help anyone. */
  let mode = 'scan';

  function setMode(next) {
    mode = next;
    const scan = $('#sessScanPad'), hk = $('#hkBody'), vc = $('#vaccBody');
    if (scan) scan.classList.toggle('hidden', mode !== 'scan');
    if (hk) hk.classList.toggle('hidden', mode !== 'housekeeping');
    if (vc) vc.classList.toggle('hidden', mode !== 'vacc');
    $$('#sessModeSeg button').forEach(
      (b) => b.classList.toggle('active', b.dataset.mode === mode));
    /* Re-drawn, because the mode is a question about the list and not
       only about the panels under it. This used to toggle two `hidden`
       classes and leave the list exactly as it was, so the local view
       showed the whole catalogue until something else happened to
       re-render.

       The line above the list is written by `renderTree`, which is also
       what counts the cards. */
    if (sessions.length) {
      renderFilterBar();
      renderTree();
    }
    for (const b of $$('#sessHealth, #sessCompare, #sessReveal, #sessScan')) {
      b.classList.toggle('hidden', mode !== 'scan');
    }
    if (mode === 'housekeeping' && BARRY.views.housekeeping) {
      BARRY.views.housekeeping.onShow();
    }
    if (mode === 'vacc') paintVacc();
    BARRY.activity.log('sessions.mode', { mode });
  }

  /* ==================================================================
     Everything VACC knows
     ==================================================================
     A third view of the same catalogue, from the cluster's side. It is not
     a different set of recordings -- it is the same ones, asked a different
     question: which of these can the cluster read, and what else is sitting
     on it that nobody here has met.

     Browsing is how the second half gets answered. Scanning a folder tells
     recordings Jarvis already knows that they also live there, which is
     what makes them selectable in a VACC-marked tool. It never invents a
     recording: a gid is permanent and everything in the lab hangs off it,
     so minting five hundred of them from a directory walk is a decision
     somebody makes on purpose and not a side effect of pressing Scan.
     ================================================================== */
  let vHere = null;          // the cluster listing we are looking at
  let vScan = null;          // what the last dry run said it would do
  let vBusy = false;
  let vCounts = null;
  /* In flight, and it is load-bearing rather than cosmetic.
     `paintVacc` asks `vaccBrowse` to draw, `vaccBrowse` sees no listing and
     asks `vaccGo` to fetch one, and `vaccGo` clears the listing and repaints
     before it awaits anything -- so the paint re-entered the fetch, which
     repainted, which re-entered. Synchronous, unbounded, and it took the
     interface down with "Maximum call stack size exceeded" after stacking
     up several hundred copies of the same card.
     One request at a time, and the draw checks before starting another. */
  let vLoading = false;
  let vCountsLoading = false;
  /* Which half of the cluster view is showing. The catalogue first, because
     it is the one that answers the ordinary question -- the directory walk
     is how a recording gets connected to its copy on the cluster, which is
     a thing you do once. */
  let vaccTab = 'catalogue';

  function vaccShowMode() {
    const btn = $('#sessModeVacc');
    if (!btn) return;
    const st = (BARRY.vacc && BARRY.vacc.last) || {};
    btn.hidden = !st.configured;
  }

  async function vaccGo(path) {
    if (vLoading) return;
    vLoading = true;
    vHere = null; vScan = null;
    paintVacc();
    try {
      vHere = await api('/api/vacc/browse'
                        + (path ? ('?path=' + encodeURIComponent(path)) : ''));
    } catch (e) {
      vHere = { error: e.message, dirs: [], recordings: [] };
    } finally {
      vLoading = false;
    }
    paintVacc();
  }

  async function vaccScan(path, dry) {
    vBusy = true; paintVacc();
    try {
      vScan = await apiPost('/api/vacc/scan', { path, dry: !!dry });
      if (!dry) {
        toast((vScan.added || []).length + ' cluster path(s) added. Those '
              + 'recordings can now be run on VACC.', 'ok', 7000);
        // What the cluster can reach just changed, and the chips on the
        // cards above are drawn from it.
        if (BARRY.vacc) await BARRY.vacc.loadKnows(true);
        vCounts = null;
        render();
      }
    } catch (e) {
      toast(e.message, 'err', 9000);
    } finally {
      vBusy = false; paintVacc();
    }
  }

  function paintVacc() {
    const host = $('#vaccBody');
    if (!host || mode !== 'vacc') return;
    host.innerHTML = '';
    const st = (BARRY.vacc && BARRY.vacc.last) || {};

    host.appendChild(el('div', { class: 'card' }, [
      el('div', { class: 'section-label', style: 'margin-top:0',
                  text: 'What the cluster can reach' }),
      el('p', { class: 'hint', style: 'max-width:78ch',
        text: st.available
          ? ('Connected as ' + (st.netid || '?') + '. These are the same '
             + 'recordings as the other two views — this one says which of '
             + 'them VACC can read, which is what decides whether a '
             + 'VACC-marked tool will offer to run one.')
          : (st.why || 'The cluster is not reachable right now.') }),
      (st.denied_roots || []).length
        ? el('p', { class: 'warn-line',
            text: 'VACC mounts ' + st.denied_roots.join(', ') + ' and this '
                + 'account cannot read it — ask vacchelp@uvm.edu to grant '
                + 'your PI group read and execute on that share.' })
        : null,
      vCounts ? el('div', { class: 'vacc-grid' }, [
        vRow('Reads in place', vCounts['native']),
        vRow('Copied to its scratch', vCounts['staged']),
        vRow('Not reachable from it', vCounts['local-only']),
        vRow('Not established', vCounts['unknown']),
      ]) : el('p', { class: 'hint quiet', text: 'Counting…' }),
    ].filter(Boolean)));

    if (!vCounts && !vCountsLoading) loadVaccCounts();

    /* Two ways of looking at the same cluster, and they answer different
       questions.

       The catalogue is the one you want nearly always: the same
       project → mouse → session tree as Everything Jarvis knows, narrowed
       to what VACC can actually read. Finding a recording by which animal
       it came from is how anybody thinks about it.

       The directory walk answers the other question -- what is physically
       sitting on the cluster, including things Jarvis has never met -- and
       it is how a recording gets connected to its copy there in the first
       place. Kept, because without it the catalogue can only ever show what
       somebody has already scanned. */
    host.appendChild(el('div', { class: 'seg vacc-seg' }, [
      el('button', {
        class: vaccTab === 'catalogue' ? 'active' : '',
        text: 'Catalogue',
        title: 'Every recording the cluster can read, by project and mouse',
        onclick: () => { vaccTab = 'catalogue'; paintVacc(); },
      }),
      el('button', {
        class: vaccTab === 'browse' ? 'active' : '',
        text: 'Directories',
        title: 'Walk the cluster’s filesystem, and scan a folder to '
             + 'connect what is there to what Jarvis knows',
        onclick: () => { vaccTab = 'browse'; paintVacc(); },
      }),
    ]));

    if (vaccTab === 'catalogue') {
      const cat = el('div', { class: 'card' });
      cat.appendChild(el('p', { class: 'hint', style: 'max-width:78ch',
        text: 'The same catalogue as Everything Jarvis knows, narrowed to '
            + 'the recordings VACC can read. A recording nobody has '
            + 'established an answer for is in neither this list nor its '
            + 'opposite — scan a folder under Directories and it will '
            + 'appear here.' }));
      /* The host only. `housekeeping.catalogue` fills it, because the tree,
         the grouping control and the detail panel are one piece of work and
         a second copy of them is a second copy to keep in step. */
      cat.appendChild(el('div', { id: 'vaccCatalogue' }));
      host.appendChild(cat);
      if (BARRY.views.housekeeping) {
        BARRY.views.housekeeping.catalogue('vacc');
      }
      return;
    }

    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: 'Look around it, and scan' }));
    box.appendChild(el('p', { class: 'hint', style: 'max-width:78ch',
      text: 'Scanning a folder walks everything under it and tells the '
          + 'recordings Jarvis already knows that they also live on the '
          + 'cluster. Anything it finds that Jarvis has never met is listed '
          + 'and left alone — a recording is not created by a directory '
          + 'walk.' }));
    box.appendChild(vaccBrowse());
    host.appendChild(box);
  }

  function vRow(k, v) {
    return el('div', { class: 'vacc-row' }, [
      el('span', { class: 'vacc-k', text: k }),
      el('span', { class: 'vacc-v', text: v == null ? '—' : String(v) }),
    ]);
  }

  async function loadVaccCounts() {
    if (vCountsLoading) return;
    vCountsLoading = true;
    try {
      const got = await api('/api/vacc/knows');
      vCounts = got.counts || {};
    } catch (e) { vCounts = {}; } finally { vCountsLoading = false; }
    paintVacc();
  }

  function vaccBrowse() {
    const box = el('div', {});
    if (!vHere) {
      // Only ever start one. Drawing must not be able to start work that
      // draws again -- see `vLoading`.
      if (!vLoading) vaccGo(null);
      box.appendChild(el('p', { class: 'hint quiet', text: 'Looking…' }));
      return box;
    }
    if (vHere.error) {
      box.appendChild(el('p', { class: 'warn-line', text: vHere.error }));
      return box;
    }
    // Breadcrumbs, so "which folder am I about to scan" is readable rather
    // than inferred from the last thing clicked.
    const crumbs = el('div', { class: 'vacc-crumbs' }, [
      el('button', { class: 'vacc-crumb', text: '/',
                     onclick: () => vaccGo('/') }),
    ]);
    let acc = '';
    for (const p of String(vHere.at || '').split('/').filter(Boolean)) {
      acc += '/' + p;
      const t = acc;
      crumbs.appendChild(el('button', { class: 'vacc-crumb', text: p,
                                        onclick: () => vaccGo(t) }));
    }
    box.appendChild(crumbs);

    const list = el('div', { class: 'vacc-ls' });
    const up = String(vHere.at || '').replace(/\/[^/]+$/, '') || '/';
    if (vHere.at && vHere.at !== '/') {
      list.appendChild(el('button', { class: 'vacc-ls-row up', text: '..',
                                      onclick: () => vaccGo(up) }));
    }
    for (const d of (vHere.dirs || [])) {
      list.appendChild(el('button', { class: 'vacc-ls-row dir', text: d.name,
                                      onclick: () => vaccGo(d.path) }));
    }
    for (const r of (vHere.recordings || [])) {
      list.appendChild(el('div', { class: 'vacc-ls-row rec' }, [
        el('span', { text: r.name }),
        el('span', { class: 'vr-n', text: r.n_channels + ' ch' }),
      ]));
    }
    if (!(vHere.dirs || []).length && !(vHere.recordings || []).length) {
      list.appendChild(el('p', { class: 'hint quiet', text: 'Nothing here.' }));
    }
    box.appendChild(list);

    box.appendChild(el('div', { class: 'tk-actions' }, [
      el('button', {
        class: 'btn ghost',
        text: vBusy ? 'Scanning…' : 'Scan this folder',
        disabled: vBusy ? 'disabled' : null,
        onclick: () => vaccScan(vHere.at, true),
      }),
      el('span', { class: 'hint quiet',
        text: 'Says what it would do before it does anything.' }),
    ]));
    if (vScan) box.appendChild(vaccReport(vScan));
    return box;
  }

  function vaccReport(d) {
    const box = el('div', { class: 'vacc-scan' });
    const n = (d.added || []).length;
    box.appendChild(el('div', { class: 'hint',
      text: d.n_found + ' recording(s) under it. '
          + (d.dry ? 'Nothing written yet.' : 'Done.') }));
    const part = (label, rows, cls) => rows.length
      ? el('details', { class: cls || '' }, [
          el('summary', { text: rows.length + ' ' + label }),
          el('div', {}, rows.slice(0, 40).map((r) => el('div', {
            class: 'hint quiet',
            text: (r.label ? r.label + ' — ' : '')
                + String(r.path || '').replace((d.root || '') + '/', '')
                + (r.why ? '  (' + r.why + ')' : '') }))),
        ])
      : null;
    [
      part(d.dry ? 'would gain a cluster path' : 'gained a cluster path',
           d.added || []),
      part('already had it', d.already || []),
      part('not a recording Jarvis knows — left alone', d.unmatched || []),
      part('too ambiguous to match — refused', d.ambiguous || [], 'warn-line'),
    ].filter(Boolean).forEach((x) => box.appendChild(x));

    if (d.dry && n) {
      box.appendChild(el('div', { class: 'tk-actions' }, [
        el('button', { class: 'btn',
          text: 'Add ' + n + ' path(s)',
          disabled: vBusy ? 'disabled' : null,
          onclick: () => vaccScan(d.root, false) }),
        el('span', { class: 'hint quiet',
          text: 'Paths only. Nothing new is created.' }),
      ]));
    } else if (d.dry) {
      box.appendChild(el('p', { class: 'hint quiet',
        text: 'Nothing to add — every recording under here that Jarvis '
            + 'knows already carries its cluster path.' }));
    }
    return box;
  }

  /* Forget the cached health summary and repaint if this view is up.

     Called by anything that changes whether a recording counts as patched:
     applying a correction, undoing one, or deleting the set it was applied
     to. The thirty-second cache is right for scrolling and wrong for the
     instant the answer changes. */
  async function refreshHealth() {
    continuity = null;
    continuityAt = 0;
    await loadContinuity(true);
    if (BARRY.state && BARRY.state.view === 'sessions') render();
  }

  /* Redraw the tree without moving anybody.

     `renderTree` empties its host and rebuilds it, which is right when
     somebody has asked for a different list and wrong when nobody has
     asked for anything -- a background refresh that jumps the scroll back
     to the top is the startup complaint again, arriving eight seconds
     later instead of at boot.

     So: only when this view is the one on screen, never while a menu or a
     modal is open over it, and with the scroll put back exactly where it
     was. `keepScroll` finds the element that is actually scrolling rather
     than being told -- the list itself never scrolls, its pad does, and
     saving `#sessTree.scrollTop` is saving a number that is always zero.
     There is no attempt to preserve a text selection inside the tree; that
     is a rarer case than scrolling and the cure would be worse. */
  function repaintQuietly() {
    if (!BARRY.state || BARRY.state.view !== 'sessions') return;
    if (document.querySelector('.modal-back')) return;
    const back = BARRY.keepScroll($('#sessTree'));
    renderTree();
    back();
  }

  /* The registry came out of the warm cache and the real one differs.

     Two cases, and the difference is whether anybody is looking. On this
     view, re-read and repaint in place. Anywhere else, just forget that it
     has been read -- the next `onShow` picks it up, which costs nothing
     now and cannot move a list somebody is in the middle of. */
  async function warmRegistry() {
    if (BARRY.state && BARRY.state.view === 'sessions' && mode !== 'vacc'
        && mode !== 'housekeeping') {
      const back = BARRY.keepScroll($('#sessTree'));
      await loadKnown(true, true);
      back();
      return;
    }
    knownLoaded = false;
  }

  return {
    init,
    picked: () => Array.from(picked),
    setMode,
    refreshHealth,
    repaintQuietly,
    /* The running-scan line, for web/_dev/scanlive.html.

       Exported because a scan of the test fixture is three folders and is
       over in milliseconds: a harness that waits for the running state to
       assert against it is racing something it cannot win, and would pass
       by never looking. Handed a job snapshot, this renders exactly what
       the poll renders. */
    scanLive,
    relToRoot,
    /* Forget that the registry has been read, so the next onShow reads it
       again. For web/_dev/motion.html, which checks that the skeleton is on
       screen during that read and gone after it -- and there is no way to
       watch a load that only ever happens once per page. */
    _forget: () => { knownLoaded = false; sessions = []; },
    /* What the scan will actually be told to do. For web/_dev/sessfilter.html:
       the settings moved out of two inputs and into module state, and a
       button that merely looks changed is not the same as a scan that is
       changed -- so the harness reads the state the scan reads. */
    _scanOpts: () => Object.assign({}, scanOpts),
    /* Which filters exist. For web/_dev/healthfilter.html: a filter that is
       described in a popover but not wired into the predicate looks
       identical from outside until somebody relies on it. */
    _filterIds: () => FILTERS.map((f) => f.id),
    /* Turn filters on and count what survives. For
       web/_dev/healthfilter.html: a filter listed in the popover but never
       wired into the predicate is invisible from outside until somebody
       relies on it. */
    _tryFilter: async (ids) => {
      await loadContinuity(true);
      flags.clear();
      for (const id of (ids || [])) flags.add(id);
      const kept = sessions.filter(matches).length;
      flags.clear();
      return { kept: kept, total: sessions.length };
    },
    /* The continuity panel, opened directly. For web/_dev/gapbar.html:
       getting to it through a scan and a health sweep is a test of the
       scan, and what wants looking at is the panel. */
    _showContinuity: (sess, report) => showContinuity(sess, report),
    onShow: () => {
      /* The third source appears only when there is a cluster set up. The
         status is already in hand from boot, so this costs nothing; the
         mode is a view of the same catalogue, not a different one. */
      vaccShowMode();
      if (mode === 'vacc') { paintVacc(); return; }
      if (mode === 'housekeeping' && BARRY.views.housekeeping) {
        BARRY.views.housekeeping.onShow();
      } else {
        renderRecents();
        // Open showing what Jarvis already knows rather than an empty page.
        loadKnown();
        /* And what every continuity check has found, so the gap filters
           and the gap chips have something to work from.

           Only repainted if there is something to repaint. This is a small
           local read and the registry is a slow one, so it finishes first --
           and repainting then drew an empty tree over the skeleton that
           says the registry is still being read. When the sessions have not
           arrived yet, `loadKnown` draws them when they do, and by then the
           summary is in hand, so the chips are on that first paint. */
        loadContinuity().then(() => {
          if (continuity && sessions.length) renderTree();
        });
      }
    },
  };
})();
