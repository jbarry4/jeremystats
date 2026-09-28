/* ui.js -- the controls, built once.

   An audit of the built page found the same control drawn several slightly
   different ways under several names: three shapes of search field, four of
   segmented item, `.btn.small` on eleven buttons with no rule behind it, and
   the magnifier icon copy-pasted verbatim into eight places with the
   attribute order varying each time. None of it was carelessness. It is what
   happens when every call site assembles its own control out of raw `el()`
   and a remembered class string.

   So: one function per control. A caller says what the control is FOR and
   gets the house's answer, rather than typing a class name from memory.

   Nothing here invents a look. Every function emits the classes `app.css`
   already defines, which is why this file can land without touching the
   stylesheet at all -- adopting it is a refactor of the call sites and
   nothing else. GUI-CONSTITUTION.md says which control is for which job;
   this is the same knowledge in a form the code can use.

   Everything is built on `el()` from core.js and returns a real node, so a
   call site can still reach in and change something the way it always
   could. These are shortcuts, not a framework. */
BARRY.ui = (function () {

  /* ---------- buttons ---------- */

  /* The sizes, and the one spelling of each.

     `.btn.small` was applied to eleven buttons and no rule has ever matched
     it, so they rendered at full size next to the eighty-four that wrote
     `.btn.sm` and shrank. Two spellings, one meaning, and the wrong one is
     silent -- which is exactly the kind of thing a function can make
     impossible. `size` takes 'sm' or nothing; anything else is refused
     loudly rather than ignored quietly. */
  const SIZES = { sm: ' sm' };

  /* `primary` is the filled button and it is `.btn` alone -- there is no
     `.primary` class and there never was, though eleven call sites wrote
     `btn primary` as if `btn ghost` had a counterpart. It does not. */
  const KINDS = {
    primary: 'btn',
    ghost:   'btn ghost',
    mini:    'mini',
    link:    'linkish',
  };

  /* One primary action per surface, and it goes last -- see the
     constitution. Not enforced here: a function cannot see the other
     buttons on the page. */
  function button(o) {
    const opt = o || {};
    const kind = opt.kind || 'ghost';
    if (!KINDS[kind]) {
      throw new Error('ui.button: no such kind "' + kind + '". '
                      + 'One of: ' + Object.keys(KINDS).join(', '));
    }
    if (opt.size && !SIZES[opt.size]) {
      throw new Error('ui.button: size is "sm" or nothing, not "'
                      + opt.size + '". `.btn.small` has no rule behind it, '
                      + 'which is how eleven buttons came to render full '
                      + 'size while claiming to be small.');
    }
    /* `.mini` and `.linkish` carry their own size; `sm` is a `.btn`
       modifier and means nothing on them. Silently dropping it would hide
       a caller's mistaken assumption, so say so. */
    if (opt.size && kind !== 'primary' && kind !== 'ghost') {
      throw new Error('ui.button: "' + kind + '" has one size. '
                      + 'Drop `size`, or use kind "ghost" with size "sm".');
    }
    let cls = KINDS[kind] + (opt.size ? SIZES[opt.size] : '');
    if (opt.danger) cls += ' danger';
    if (opt.on) cls += ' on';
    if (opt.extra) cls += ' ' + opt.extra;
    return el('button', {
      class: cls,
      text: opt.text,
      title: opt.title || null,
      id: opt.id || null,
      disabled: opt.disabled ? 'disabled' : null,
      onclick: opt.onclick || null,
    }, opt.children || null);
  }

  /* ---------- the search field ---------- */

  /* One magnifier, drawn once.

     It was inlined in five modules and three places in index.html, each
     time as the same two paths with the attributes in a different order --
     which is how the wrapper ended up with two left-padding rules, 30px
     against 32px, and the field ended up with three measured shapes. */
  function magnifier() {
    return el('svg', {
      class: 'search-icon', viewBox: '0 0 20 20',
      html: '<circle cx="9" cy="9" r="6"/><path d="m14 14 4 4"/>',
    });
  }

  /* The verb a search box opens with.

     Three were in use -- "Search...", "Filter by...", "Find in..." -- for
     one gesture, which asks the reader to work out whether they are three
     different things. They are not. A placeholder describes what you can
     TYPE, not what the box is: "Type a mouse, session or date..." rather
     than "Search sessions".

     Warned about rather than rewritten. The wording is the caller's and
     some of it is deliberate -- "Find in this file" really is a different
     gesture from searching the catalogue -- so this points at the
     constitution and leaves the decision with the person. */
  const VERBS = /^(search|filter|find|jump|type|which|pick|anything)\b/i;

  function searchField(o) {
    const opt = o || {};
    const ph = opt.placeholder || 'Search…';
    if (!VERBS.test(ph.trim())) {
      console.warn('ui.searchField: placeholder "' + ph + '" does not open '
                   + 'with one of the verbs the rest of the application '
                   + 'uses. See GUI-CONSTITUTION.md section 8.');
    }
    const input = el('input', {
      type: 'search',
      value: opt.value === undefined || opt.value === null ? '' : opt.value,
      placeholder: ph,
      title: opt.title || null,
      id: opt.id || null,
      autocomplete: 'off',
      /* Debounced by default. Every call site that repainted a list on
         every keystroke had to remember this, and the ones that forgot
         made a request per character. 140ms is what most of them chose. */
      oninput: opt.oninput
        ? (opt.debounce === false
            ? opt.oninput
            : debounceInput(opt.oninput, opt.debounce || 140))
        : null,
      onkeydown: opt.onkeydown || null,
    });
    const wrap = el('div', {
      class: 'search-wrap' + (opt.inline === false ? '' : ' inline'),
      style: opt.width ? 'max-width:' + opt.width : null,
    }, [magnifier(), input]);
    /* The input, for a caller that wants to focus it or read it later --
       reaching back through the wrapper by tag is how a search box ends up
       coupled to its own markup. */
    wrap.input = input;
    return wrap;
  }

  /* ---------- a row of actions ---------- */

  /* Right-aligned, because that is where this application puts actions:
     `justify-content: flex-end` is already on `.head-actions` and
     `.modal-actions`. Falsey children are dropped, so a caller can write
     `cond ? button(...) : null` inline, which most of them already do. */
  function actions(children, o) {
    const opt = o || {};
    return el('div', {
      class: (opt.inModal ? 'modal-actions' : 'head-actions')
             + (opt.extra ? ' ' + opt.extra : ''),
    }, [].concat(children || []).filter(Boolean));
  }

  /* A modal footer, which is an action row with a rule above it and a
     spacer in the middle: navigational actions to the left of the spacer,
     Cancel and then the primary to the right of it. */
  function modalFoot(left, right) {
    return el('div', { class: 'mf' },
      [].concat(left || []).filter(Boolean)
        .concat([el('div', { class: 'spacer' })])
        .concat([].concat(right || []).filter(Boolean)));
  }

  /* ---------- the segmented control ---------- */

  /* Two primitives existed for this -- `.seg` and `.track-switch`, one mono
     at 11.5px/600 and one sans at 12.5px/550 -- for one job: choosing
     between a handful of mutually exclusive modes.

     `items` is [[value, label, title?], ...]; `onPick` gets the value. */
  function seg(items, current, onPick, o) {
    const opt = o || {};
    return el('div', {
      class: 'seg' + (opt.extra ? ' ' + opt.extra : ''),
    }, (items || []).map(([value, label, title]) => el('button', {
      class: value === current ? 'active' : '',
      text: label,
      title: title || null,
      onclick: () => { if (value !== current) onPick(value); },
    })));
  }

  /* ---------- chips ---------- */

  /* A fact, not a button. `.stat-chip` is the plain one; `.flagchip` is the
     smaller mono one that sits on a session card. `kind` colours it by
     MEANING -- ok, warn, err -- and nothing else, so a chip that is merely
     one of several should carry no kind at all. */
  function chip(text, o) {
    const opt = o || {};
    const base = opt.flag ? 'flagchip' : 'stat-chip';
    return el('span', {
      class: base + (opt.kind ? ' ' + opt.kind : '')
                  + (opt.extra ? ' ' + opt.extra : ''),
      text: text,
      title: opt.title || null,
    });
  }

  /* A row of them. Six modules had independently reached for `.fb-stats`
     for this, which is how a class named after the folder bar came to be
     the generic chip row; it is `.chip-row` now. */
  function chipRow(chips) {
    return el('div', { class: 'chip-row' },
              [].concat(chips || []).filter(Boolean));
  }

  /* ---------- a tool's header ---------- */

  /* The composition the shape audit could not see.

     Two adjacent steps of one bundle had two unrelated headers. Braces built
     `.card.br-intro` › `.section-label` + `p.hint` -- ALL CAPS, boxed in a
     card, the step number buried in the title text as "Braces · step 3 of
     The Dentist". X-ray built `.dp-intro` › `strong` + `.dp-step` pill +
     `.hint` -- mixed case, unboxed, the step in a chip of its own. Both
     measured fine. They just were not the same thing.

     Across the application there were thirteen bespoke tool headers using
     four alignments, seven gaps, three title elements and three subtitle
     classes between them.

     This is X-ray's shape, formalised, because it is the one already closest
     to the house: `.tk-head` and `.view-head` are both a mixed-case title
     with a subtitle beside or under it, and neither is boxed. The step
     belongs in a chip rather than in the title -- a title should say what the
     tool is, and "· step 3 of The Dentist" is a different fact about it.

     `step` is optional: a tool that is not part of a bundle just omits it. */
  /* "step 3 of The Dentist", read out of ToolKit's own bundle list.

     Each tool used to type its own. When Root Canal went in between Braces
     and X-ray, X-ray's header had to be changed from 4 to 5 by hand -- it
     was, that time. Derived, inserting a step renumbers every header after
     it, and a tool that is in no bundle simply gets no chip.

     Called at render time, not load time: ToolKit loads after this file. */
  function stepOf(toolId) {
    const tk = BARRY.views && BARRY.views.toolkit;
    const list = (tk && typeof tk.bundles === 'function') ? tk.bundles() : [];
    for (const b of list) {
      const i = (b.steps || []).findIndex((s) => s.id === toolId);
      if (i >= 0) return 'step ' + (i + 1) + ' of ' + b.name;
    }
    return null;
  }

  function stepHeader(o) {
    const opt = o || {};
    return el('div', { class: 'step-head' }, [
      el('strong', { text: opt.title }),
      opt.step ? el('span', { class: 'step-n', text: opt.step }) : null,
      opt.blurb ? el('p', { class: 'hint', text: opt.blurb }) : null,
    ].filter(Boolean));
  }

  /* ---------- a labelled control ---------- */

  /* Six primitives did this job: `.section-label`, `.field label`,
     `.dp-lab`, `.ctl > label`, `.mini-field` and `.vacc-field`, plus
     `.wiz-grid .field label` un-uppercasing some of them.

     `.section-label` is the one that wins on merit and on usage -- 164 uses
     across 25 files -- so this is that, with the control under it and the
     hint under that. `inline: true` puts the label beside a short control
     instead, which is the one variation that is about the control rather
     than about somebody's taste. */
  function field(o) {
    const opt = o || {};
    return el('div', {
      class: 'ui-field' + (opt.inline ? ' inline' : '')
             + (opt.extra ? ' ' + opt.extra : ''),
    }, [
      el('div', { class: 'section-label', text: opt.label }),
      opt.control,
      opt.hint ? el('p', { class: 'hint', text: opt.hint }) : null,
    ].filter(Boolean));
  }

  /* ---------- a card on a workbench ---------- */

  /* Checkup and StrataScope are the same idea -- things you have open, which
     stay open until you put them down -- and both build a `.cur-set`. They
     did not build the same one.

       owner    Checkup: `button.cur-who`, clickable, reading "unassigned"
                when nobody has it. StrataScope: `span.csr-who`, plain text,
                absent ENTIRELY when nobody has it -- so the fact that a
                sheet is unclaimed was invisible, and `.csr-who` belongs to
                the shelf list rather than to the card anyway.
       when     Checkup: beside the owner. StrataScope: a bare `.hint` on a
                line of its own.
       spacer   both wrote `el('div', { style: 'flex:1' })` next to a
                `.spacer` class that already exists and is used ten lines up.

     One shape now. The owner is always stated, including when there is not
     one, because "nobody has this" is the thing a bench is for saying.

     `owner.onAssign` is what separates them honestly: curation sets can be
     handed to somebody and sheets cannot, so a set's owner is a button and
     a sheet's is text. A control that looks pressable and is not would be a
     worse lie than the one this replaces. */
  function workbenchCard(o) {
    const opt = o || {};
    const own = opt.owner || {};
    const name = own.name || null;
    const ownerNode = own.onAssign
      ? el('button', {
          class: 'cur-who' + (name ? '' : ' none'),
          title: name ? 'Assigned to ' + name + ' — click to change'
                      : 'Nobody has this one. Click to put a name on it.',
          text: name || 'unassigned',
          onclick: own.onAssign,
        })
      : el('span', {
          class: 'cur-who static' + (name ? '' : ' none'),
          title: name ? 'Picked up by ' + name : 'Nobody has this one.',
          text: name || 'unassigned',
        });

    return el('div', {
      class: 'cur-set' + (opt.done ? ' done' : '')
             + (opt.extra ? ' ' + opt.extra : ''),
      'data-gid': opt.gid || null,
    }, [
      el('div', { class: 'cur-set-top' }, [
        typeof opt.title === 'string' ? el('strong', { text: opt.title })
                                      : opt.title,
      ].concat(opt.chips || [])
       .concat([
         el('div', { class: 'spacer' }),
         opt.count ? el('span', { class: 'cur-set-n', text: opt.count }) : null,
       ]).filter(Boolean)),
      el('div', { class: 'cur-set-who' }, [
        ownerNode,
        opt.when ? el('span', { class: 'cur-set-when', text: opt.when }) : null,
      ].filter(Boolean)),
    ].concat(opt.extras || [])
     .concat([
       opt.progress === undefined || opt.progress === null ? null
         : el('div', { class: 'cur-prog small' },
              [el('i', { style: 'width:' + (opt.progress || 0) + '%' })]),
       opt.tally ? el('div', { class: 'cur-set-tally' }, opt.tally) : null,
       opt.actions ? el('div', { class: 'cur-set-acts' }, opt.actions) : null,
     ]).filter(Boolean));
  }

  /* ==================================================================
     Round 2: running, choosing, keeping (constitution §6d, §6e)
     ================================================================== */

  /* ---------- how much time has passed ---------- */

  /* "3d", "5h", "just now". Short because it sits in a row beside a name
     and a count; the full stamp goes in the title. */
  function when(at) {
    const t = Date.parse(at || '');
    if (!isFinite(t)) return '';
    const s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 90) return 'just now';
    if (s < 3600) return Math.round(s / 60) + 'm';
    if (s < 86400) return Math.round(s / 3600) + 'h';
    if (s < 86400 * 60) return Math.round(s / 86400) + 'd';
    return new Date(t).toISOString().slice(0, 10);
  }

  /* ---------- a version's name ---------- */

  /* About thirty places built `'v' + (name || v)` by hand, which is how one
     version came to read as two numbers in two panels. The name is DERIVED
     from lineage (backend/versions.py) and arrives as `label`; the stored
     `v` is only the sync key and is shown when there is nothing else. */
  function versionLabel(v) {
    if (v === null || v === undefined || v === '') return 'v?';
    const raw = typeof v === 'object'
      ? (v.label !== undefined && v.label !== null ? v.label
         : v.name !== undefined && v.name !== null ? v.name : v.v)
      : v;
    return 'v' + String(raw === undefined || raw === null ? '?' : raw)
      .replace(/^v/i, '');
  }

  /* A version name as a sort key: "1.10" after "1.9". For drawing the
     tree. What a NEW version will be called is not worked out here: that
     is BARRY.vers.nextFor (curate.js), the page's one copy of
     versions.label_rows, which simulates the bank naming it. */
  function vkey(label) {
    const out = [];
    for (const part of String(label === undefined || label === null
                              ? '' : label).replace(/^v/i, '').split('.')) {
      if (!part.trim()) continue;
      const n = parseInt(part, 10);
      if (!isFinite(n) || String(n) !== part.trim()) return [1e9];
      out.push(n);
    }
    return out;
  }
  const vfmt = (k) => k.join('.') || '0';
  function vcmp(a, b) {
    for (let i = 0; i < Math.max(a.length, b.length); i++) {
      if (a[i] === undefined) return -1;
      if (b[i] === undefined) return 1;
      if (a[i] !== b[i]) return a[i] - b[i];
    }
    return 0;
  }
  /* What banking after picking up `row` (one of `rows`) would be called,
     and whether that continues its line or branches off it. The bank's own
     rule, simulated -- see BARRY.vers.nextFor. */
  function versionNext(rows, row) {
    const n = BARRY.vers.nextFor(rows || [], row);
    return { from: n.from, name: n.to, branch: !!n.branches };
  }

  /* ---------- the run bar ---------- */

  /* Where it runs and how many, as two questions (§6d). A tool DECLARES
     which of the four modes it supports and this offers only those:

       modes: { local: ['one', 'many'], vacc: ['one', 'many'] }

     An axis with one option is hidden, not shown disabled. VACC is offered
     only while VACC Mode is on and an account is set up -- except for a tool
     that runs nowhere else, which says why it cannot run rather than
     vanishing. `onChange(where, count)` is called on a change; the caller
     re-renders. `action` is the primary, placed last; `cost` is what it will
     spend, said before it is spent. */
  const WHERE = [['local', 'This computer'], ['vacc', 'VACC']];
  const COUNT = [['one', 'One'], ['many', 'Many']];

  function vaccReady() {
    const st = (BARRY.vacc && BARRY.vacc.last) || {};
    return !!(BARRY.state && BARRY.state.vacc && st.configured);
  }

  function runPlan(modes, where, count) {
    const m = modes || { local: ['one'] };
    let wheres = WHERE.map((w) => w[0]).filter((w) => (m[w] || []).length);
    const onlyVacc = wheres.length === 1 && wheres[0] === 'vacc';
    if (!onlyVacc && !vaccReady()) wheres = wheres.filter((w) => w !== 'vacc');
    const w = wheres.includes(where) ? where : wheres[0];
    const counts = COUNT.map((c) => c[0]).filter((c) => (m[w] || []).includes(c));
    const c = counts.includes(count) ? count : counts[0];
    return { wheres, counts, where: w, count: c,
             blocked: w === 'vacc' && !vaccReady()
               ? 'This runs on the VACC, and VACC Mode is off or no account '
                 + 'is set up on this machine. Turn it on from the rail.'
               : null };
  }

  function runBar(o) {
    const opt = o || {};
    const plan = runPlan(opt.modes, opt.where, opt.count);
    const pick = (w, c) => {
      if (typeof opt.onChange === 'function') opt.onChange(w, c);
    };
    const act = opt.action;
    const bar = el('div', { class: 'run-bar' + (opt.extra ? ' ' + opt.extra : '') }, [
      plan.wheres.length > 1 ? field({
        label: 'Where', inline: true,
        control: seg(WHERE.filter((x) => plan.wheres.includes(x[0])),
                     plan.where, (w) => pick(w, plan.count)),
      }) : null,
      plan.counts.length > 1 ? field({
        label: 'How many', inline: true,
        control: seg(COUNT.filter((x) => plan.counts.includes(x[0])),
                     plan.count, (c) => pick(plan.where, c)),
      }) : null,
      (act || opt.cost || plan.blocked) ? el('div', { class: 'run-bar-go' }, [
        plan.blocked ? el('span', { class: 'hint run-bar-why', text: plan.blocked })
          : opt.cost ? (typeof opt.cost === 'string'
                          ? el('span', { class: 'hint run-bar-cost', text: opt.cost })
                          : opt.cost)
          : null,
        el('div', { class: 'spacer' }),
        act ? button({
          kind: 'primary', text: act.text, title: act.title || null,
          disabled: act.disabled || !!plan.blocked,
          onclick: act.onclick,
        }) : null,
      ].filter(Boolean)) : null,
    ].filter(Boolean));
    /* What the bar settled on, which is not always what was asked for: a
       tool asked for VACC on a machine with no account runs here. */
    bar.where = plan.where;
    bar.count = plan.count;
    return bar;
  }

  /* ---------- choosing a recording ---------- */

  /* Braces' rules, shared (§6e). `usable(row)` answers true, or a string
     saying why this tool can do nothing with that recording. The picker
     lists the usable ones; "show all" lists the rest, and picking one of
     those says why it will not work rather than failing later.

     It never picks for you from inside: `openOn(rows, usable, value)` is
     what to open on -- the current choice if it is usable, else the first
     that is -- and the caller sets its state from that BEFORE building, so
     nothing calls back into a render that is still in progress. */
  const usableOf = (usable, r) => {
    if (typeof usable !== 'function') return true;
    const u = usable(r);
    return u === undefined || u === null || u === true;
  };

  function openOn(rows, usable, value) {
    const ok = (rows || []).filter((r) => usableOf(usable, r));
    if (value && ok.some((r) => r.gid === value)) return value;
    return ok.length ? ok[0].gid : (value || null);
  }

  function pickRecording(o) {
    const opt = o || {};
    const rows = opt.rows || [];
    const ok = rows.filter((r) => usableOf(opt.usable, r));
    const rest = rows.length - ok.length;
    let all = !!opt.showAll;
    const slot = el('div', { class: 'pick-rec-slot' });
    const why = el('p', { class: 'hint pick-rec-why hidden' });
    const toggle = rest ? el('button', { class: 'linkish pick-rec-all' }) : null;

    const sayWhy = (r) => {
      const u = r && typeof opt.usable === 'function' ? opt.usable(r) : true;
      const reason = typeof u === 'string' ? u : (u === false
        ? 'This tool has nothing to work on in this recording.' : '');
      why.textContent = reason;
      why.classList.toggle('hidden', !reason);
    };

    function draw() {
      slot.innerHTML = '';
      const list = all ? rows : ok;
      slot.appendChild(BARRY.pickSession({
        rows: list,
        value: opt.value,
        placeholder: opt.placeholder
          || 'Which recording? Type a mouse, session or date…',
        onpick: (r) => {
          sayWhy(r);
          if (typeof opt.onpick === 'function') opt.onpick(r);
        },
      }));
      if (toggle) {
        toggle.textContent = all
          ? 'Only the recordings this tool can use (' + ok.length + ')'
          : 'Show all recordings (' + rest + ' more)';
      }
    }
    if (toggle) {
      toggle.addEventListener('click', () => {
        all = !all; draw();
        if (typeof opt.onShowAll === 'function') opt.onShowAll(all);
      });
    }
    draw();
    sayWhy(rows.find((r) => r.gid === opt.value));

    const node = field({
      label: 'Recording', extra: 'pick-rec',
      control: el('div', {}, [
        slot,
        !ok.length ? el('p', { class: 'hint pick-rec-empty',
          text: opt.emptyText || 'None of the recordings Jarvis knows about '
                + 'has anything this tool can work on yet.' }) : null,
        why,
        toggle,
      ].filter(Boolean)),
    });
    node.pickerValue = () => {
      const p = slot.firstChild;
      return p && p.pickerValue ? p.pickerValue() : null;
    };
    return node;
  }

  /* ---------- the version tree ---------- */

  /* One control for every version choice (§6e): the lineage drawn as
     vertical lanes, newest at the top, the trunk down the left and each
     branch in a lane beside it, joined to the version it came from.

     Rows first, then the graph drawn over them from where the rows actually
     are. The rows are allowed to wrap on a narrow panel -- nothing here is
     ever cut short -- so the node positions are measured, not assumed, and
     re-measured when the panel is resized.

       versions   an entry's versions as the bank sends them
       value      the id (or name) that is chosen
       onpick     called with the version
       disabled   (v) => reason | null; by default a version whose snapshot
                  is not on this machine is shown and cannot be picked
       readonly   a history to read rather than a choice: rows are not
                  buttons and nothing is dimmed
       notes      each version's note on its row, not only in its title */
  const LANE = 14, PAD = 8;

  function versionTree(o) {
    const opt = o || {};
    const vs = (opt.versions || []).map((v) => ({
      v, name: versionLabel(v).slice(1), k: vkey(versionLabel(v).slice(1)),
    }));
    vs.sort((a, b) => vcmp(b.k, a.k));
    const byName = new Map(vs.map((x, i) => [x.name, i]));
    const newest = vs.length ? vs[0].name : null;
    const idOf = (v) => (v && (v.id || v.label || v.v));
    const chosen = opt.value === undefined || opt.value === null ? null
      : String(opt.value).replace(/^v/i, '');

    /* Lines: every version of one line shares its name minus the last
       part. Each line gets a lane; the trunk is lane 0, and a branch takes
       the lowest lane free over the rows from its top to where it forks. */
    const lineOf = (x) => (x.k.length > 1 ? vfmt(x.k.slice(0, -1)) : '');
    const lines = new Map();
    vs.forEach((x, i) => {
      const id = lineOf(x);
      if (!lines.has(id)) lines.set(id, { id, rows: [] });
      lines.get(id).rows.push(i);
    });
    const busy = [];                   // lane -> [[top, bottom], ...]
    const free = (lane, a, b) => !(busy[lane] || [])
      .some(([x, y]) => !(b < x || a > y));
    const order = Array.from(lines.values())
      .sort((a, b) => (a.id === '' ? -1 : b.id === '' ? 1 : a.rows[0] - b.rows[0]));
    for (const ln of order) {
      const top = ln.rows[0];
      const bottom = ln.rows[ln.rows.length - 1];
      ln.origin = ln.id === '' ? null : (byName.has(ln.id) ? byName.get(ln.id) : null);
      const end = ln.origin === null ? bottom : ln.origin - 1;
      let lane = ln.id === '' ? 0 : 1;
      while (!free(lane, top, Math.max(end, bottom))) lane += 1;
      (busy[lane] = busy[lane] || []).push([top, Math.max(end, bottom)]);
      ln.lane = lane;
    }
    const laneOfRow = [];
    lines.forEach((ln) => ln.rows.forEach((i) => { laneOfRow[i] = ln.lane; }));
    const nLanes = Math.max(1, busy.length);
    const gutter = PAD * 2 + (nLanes - 1) * LANE;

    const defaultWhy = (v) => (v.has_snap === false || v.snap_elsewhere
      ? (v.snap_elsewhere
          ? 'Recorded on another machine; its snapshot has not synced here yet.'
          : 'No snapshot was kept for this version, so it cannot be read back.')
      : null);
    const whyOf = opt.readonly ? () => null
      : typeof opt.disabled === 'function' ? opt.disabled : defaultWhy;

    const svg = el('svg', { class: 'vtree-g', 'aria-hidden': 'true' });
    const host = el('div', {
      class: 'vtree' + (opt.readonly ? ' ro' : ''),
      role: opt.readonly ? 'list' : 'radiogroup',
      style: '--vt-gutter:' + gutter + 'px',
    }, [svg]);
    const rowEls = vs.map((x, i) => {
      const v = x.v;
      const why = whyOf(v);
      const states = [];
      if (x.name === newest) states.push('newest');
      if (v.aligned) states.push('aligned');
      if (v.archived) states.push('archived');
      if (v.snap_elsewhere) states.push('not on this machine');
      if (typeof opt.state === 'function') states.push(...(opt.state(v) || []));
      const on = chosen !== null && (String(idOf(v)) === chosen || x.name === chosen);
      return el(opt.readonly ? 'div' : 'button', {
        class: 'vtree-row' + (on ? ' on' : '') + (why ? ' off' : ''),
        role: opt.readonly ? 'listitem' : 'radio',
        'aria-checked': opt.readonly ? null : (on ? 'true' : 'false'),
        'data-v': x.name,
        disabled: why ? 'disabled' : null,
        title: (v.at ? new Date(v.at).toLocaleString() : '')
               + (v.note ? '  ·  ' + v.note : '')
               + (why ? '\n' + why : ''),
        onclick: (why || opt.readonly) ? null : () => {
          rowEls.forEach((r) => {
            r.classList.remove('on'); r.setAttribute('aria-checked', 'false');
          });
          rowEls[i].classList.add('on');
          rowEls[i].setAttribute('aria-checked', 'true');
          draw();
          if (typeof opt.onpick === 'function') opt.onpick(v);
        },
        onkeydown: opt.readonly ? null : (e) => {
          if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
          e.preventDefault();
          const step = e.key === 'ArrowDown' ? 1 : -1;
          for (let j = i + step; j >= 0 && j < rowEls.length; j += step) {
            if (!rowEls[j].disabled) { rowEls[j].focus(); break; }
          }
        },
      }, [
        el('strong', { class: 'vtree-n', text: 'v' + x.name }),
        el('span', { class: 'vtree-who', text: v.by || '' }),
        el('span', { class: 'vtree-when', text: when(v.at) }),
        el('span', { class: 'vtree-count',
                     text: v.n === undefined || v.n === null ? ''
                           : Number(v.n).toLocaleString() }),
        states.length ? el('span', { class: 'vtree-state',
                                     text: states.join(' · ') }) : null,
        why ? el('span', { class: 'vtree-why', text: why }) : null,
        opt.notes && v.note ? el('span', { class: 'vtree-note', text: v.note })
                            : null,
      ].filter(Boolean));
    });
    rowEls.forEach((r) => host.appendChild(r));
    if (!vs.length) {
      host.appendChild(el('p', { class: 'hint', text: 'Nothing banked yet.' }));
    }

    const NS = 'http://www.w3.org/2000/svg';
    const mk = (tag, attrs) => {
      const n = document.createElementNS(NS, tag);
      for (const k in attrs) n.setAttribute(k, attrs[k]);
      return n;
    };
    function draw() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      if (!rowEls.length) return;
      const y = rowEls.map((r) => r.offsetTop + r.offsetHeight / 2);
      const x = (lane) => PAD + lane * LANE;
      svg.setAttribute('width', String(gutter));
      svg.setAttribute('height', String(host.scrollHeight));
      lines.forEach((ln) => {
        const cls = 'vt-l' + (ln.lane % 5);
        const top = ln.rows[0], bottom = ln.rows[ln.rows.length - 1];
        if (bottom > top) {
          svg.appendChild(mk('line', { class: 'vt-edge ' + cls,
            x1: x(ln.lane), y1: y[top], x2: x(ln.lane), y2: y[bottom] }));
        }
        if (ln.origin !== null && ln.origin !== undefined) {
          const ox = x(laneOfRow[ln.origin]), oy = y[ln.origin];
          const bx = x(ln.lane), by = y[bottom];
          const mid = Math.max(by, oy - 12);
          svg.appendChild(mk('path', { class: 'vt-edge ' + cls, fill: 'none',
            d: 'M' + bx + ' ' + by + ' L' + bx + ' ' + mid
               + ' Q' + bx + ' ' + oy + ' ' + ox + ' ' + oy }));
        }
      });
      rowEls.forEach((r, i) => {
        svg.appendChild(mk('circle', {
          class: 'vt-node vt-l' + (laneOfRow[i] % 5)
                 + (r.classList.contains('on') ? ' on' : '')
                 + (r.disabled ? ' off' : ''),
          cx: x(laneOfRow[i]), cy: y[i], r: r.classList.contains('on') ? 5 : 4,
        }));
      });
    }
    /* Drawn once it is on the page and again whenever its width changes,
       because a row that wraps moves every node below it. */
    if (typeof ResizeObserver === 'function') {
      new ResizeObserver(() => draw()).observe(host);
    } else {
      requestAnimationFrame(draw);
    }
    host.redraw = draw;
    host.value = () => {
      const i = rowEls.findIndex((r) => r.classList.contains('on'));
      return i >= 0 ? vs[i].v : null;
    };
    return host;
  }

  /* ---------- the bank dialog ---------- */

  /* One dialog, every time (§6e). Two acts:

       kind 'entry'    a detector's output becomes a new entry. Asks a NAME,
                       pre-filled, never left empty.
       kind 'version'  work done to an entry becomes its next version. The
                       entry's name is shown, not asked; asks a NOTE; and
                       says what will be written -- "continues v5 -> v6" or
                       "branches from v3 -> v3.1".

     Who comes from the profile and is never asked here. Nothing banks
     silently: what is written, and where, is on the dialog. `onBank` does
     the writing and is awaited inside it, so a refusal is shown in the
     dialog rather than after it has gone. Resolves true once banked. */
  function bankDialog(o) {
    const opt = o || {};
    const who = (BARRY.profile && BARRY.profile.who && BARRY.profile.who()) || '';
    const isEntry = opt.kind !== 'version';
    const suggestion = opt.name || '';
    const nameBox = isEntry ? el('input', {
      type: 'text', class: 'bank-dlg-name', value: suggestion,
    }) : null;
    const noteBox = el('textarea', {
      class: 'bank-dlg-note', rows: '2',
      placeholder: isEntry ? 'Anything worth knowing about this set (optional)'
                           : 'What changed in this pass (optional)',
      value: opt.note || '',
    });

    /* Which version the new one is built on, and so what it will be
       called. `from` is an id or a name; `fromV` is the stored number, as a
       curation set records it, and resolves the way the bank does -- the
       last version carrying that number. With neither, the bank takes the
       highest stored number (versions.based_on_default), so this does too:
       the newest thing anybody banked, not the highest name. */
    let line = null, nextName = null;
    if (!isEntry) {
      const vs = (opt.entry || {}).versions || [];
      const byTime = vs.slice().sort((a, b) =>
        String(a.at || '').localeCompare(String(b.at || '')));
      const lastWith = (num) => byTime.filter((v) => v.v === num).pop();
      let hit = null;
      if (opt.from !== undefined && opt.from !== null) {
        const want = String(opt.from).replace(/^v/i, '');
        hit = vs.find((v) => String(v.id) === want
                             || versionLabel(v).slice(1) === want) || null;
      } else if (opt.fromV !== undefined && opt.fromV !== null) {
        hit = lastWith(Number(opt.fromV)) || null;
      }
      if (!hit && vs.length) {
        const top = Math.max(...vs.map((v) => (typeof v.v === 'number' ? v.v : -1)));
        hit = top >= 0 ? lastWith(top)
          : vs.slice().sort((a, b) => vcmp(vkey(versionLabel(b).slice(1)),
                                           vkey(versionLabel(a).slice(1))))[0];
      }
      if (!vs.length) {
        nextName = '1';
        line = 'the first version of this entry, v1';
      } else {
        const from = versionLabel(hit).slice(1);
        const nx = versionNext(vs, hit);
        nextName = nx.name;
        line = nx.branch
          ? 'branches from v' + from + ' → v' + nx.name
          : 'continues v' + from + ' → v' + nx.name;
      }
    }

    const body = el('div', { class: 'bank-dlg' }, [
      !opt.what ? null : typeof opt.what === 'string'
        ? el('p', { class: 'bank-dlg-what', text: opt.what }) : opt.what,
      isEntry
        ? field({ label: 'Name', control: nameBox,
                  hint: 'What the Event Bank lists it under. It can be '
                        + 'changed later.' })
        : field({ label: 'Entry',
                  control: el('div', { class: 'bank-dlg-entry',
                                       text: (opt.entry || {}).name || '' }) }),
      line ? el('p', { class: 'bank-dlg-line', text: line }) : null,
      opt.extra || null,
      field({ label: 'Note', control: noteBox }),
      el('ul', { class: 'fix-steps' }, [
        opt.where ? el('li', { text: opt.where }) : null,
        el('li', { class: who ? '' : 'bank-dlg-nowho',
                   text: who ? 'Banked by ' + who + ', from your profile.'
                             : 'Nobody is set as who you are, so this would '
                               + 'be credited to the machine. Set it from '
                               + 'the name at the top right first.' }),
      ].concat((opt.facts || []).map((f) => el('li', { text: f })))
       .filter(Boolean)),
    ].filter(Boolean));

    /* Where the typing goes, as the dialogs this replaced did. After the
       modal is up, which BARRY.confirm does synchronously. */
    setTimeout(() => {
      try { (nameBox || noteBox).focus(); } catch (e) { /* closed */ }
    }, 30);
    return BARRY.confirm(
      opt.title || (isEntry ? 'Bank this as a new entry'
        : (((opt.entry || {}).versions || []).length
            ? 'Bank this as v' + nextName : 'Bank this set')),
      body,
      opt.okText || (nextName ? 'Bank as v' + nextName : 'Bank it'),
      false,
      async () => {
        if (!who) throw new Error('Set who you are first, from the name at '
                                  + 'the top right.');
        const name = isEntry ? ((nameBox.value || '').trim() || suggestion) : null;
        if (isEntry && !name) throw new Error('A banked entry needs a name.');
        await opt.onBank({ name, note: (noteBox.value || '').trim(), who });
      });
  }

  return {
    when: when,
    versionLabel: versionLabel,
    versionNext: versionNext,
    runBar: runBar,
    runPlan: runPlan,
    openOn: openOn,
    pickRecording: pickRecording,
    versionTree: versionTree,
    bankDialog: bankDialog,
    stepOf: stepOf,
    stepHeader: stepHeader,
    field: field,
    workbenchCard: workbenchCard,
    button: button,
    searchField: searchField,
    magnifier: magnifier,
    actions: actions,
    modalFoot: modalFoot,
    seg: seg,
    chip: chip,
    chipRow: chipRow,
  };
})();
