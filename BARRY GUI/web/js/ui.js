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
    /* ToolKit's own answer when it has one: a tool in two bundles (Root
       Canal is in The Dentist and The Confluence) is numbered in the one it
       was opened from, which only ToolKit knows. */
    if (tk && typeof tk.stepOf === 'function') return tk.stepOf(toolId);
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
      /* The blurb is also the title's tooltip: Compact hides the line it
         is printed on (app.css), and the words should still be one hover
         away rather than gone. */
      el('strong', { text: opt.title, title: opt.blurb || null }),
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
     worse lie than the one this replaces.

     `sync: { kind, id }` puts the shared-database mark on the owner line
     (js/syncstate.js): whether this set or sheet has reached the shared
     tables, so "is my work up there" is answered on the card rather than in
     the sync panel. */
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
      // Which set, exactly: a recording can hold several (one per bank
      // entry), so the gid alone no longer finds a card.
      'data-kind': opt.kind || null,
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
        opt.sync && BARRY.syncState
          ? BARRY.syncState.mark(opt.sync.kind, opt.sync.id) : null,
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
       notes      each version's note on its row, not only in its title;
                  or (v) => the text to show there instead
       idOf       (v) => what `value` is matched against and what `onpick`'s
                  caller sends back -- a tool's `ref`, say. Default: the id,
                  else the name
       lead       { name, text, title }: a first row that is not a version,
                  "as they are now", chosen when `value` is null; picking
                  it calls onpick(null)
       line       (v) => a sentence under the row: what picking it does
       unit       what the count counts, "stamps" */
  const LANE = 14, PAD = 8;

  function versionTree(o) {
    const opt = o || {};
    const vs = (opt.versions || []).map((v) => ({
      v, name: versionLabel(v).slice(1), k: vkey(versionLabel(v).slice(1)),
    }));
    vs.sort((a, b) => vcmp(b.k, a.k));
    const byName = new Map(vs.map((x, i) => [x.name, i]));
    const newest = vs.length ? vs[0].name : null;
    const idOf = typeof opt.idOf === 'function' ? opt.idOf
      : (v) => (v && (v.id || v.label || v.v));
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
      const on = chosen !== null && (String(idOf(v)).replace(/^v/i, '') === chosen
                                     || x.name === chosen);
      const said = typeof opt.line === 'function' ? opt.line(v) : null;
      const noteOf = (x) => (typeof opt.notes === 'function' ? opt.notes(x)
                             : (opt.notes ? x.note : null));
      // What last worked on this version: "v2 · Checkup" (2026-10-21).
      const madeBy = opt.producer === false ? null
        : versionChip(v, opt.producer, opt.producerType);
      return el(opt.readonly ? 'div' : 'button', {
        class: 'vtree-row' + (on ? ' on' : '') + (why ? ' off' : ''),
        role: opt.readonly ? 'listitem' : 'radio',
        'aria-checked': opt.readonly ? null : (on ? 'true' : 'false'),
        'data-v': x.name,
        'data-ref': String(idOf(v)),
        disabled: why ? 'disabled' : null,
        title: (v.at ? new Date(v.at).toLocaleString() : '')
               + (v.note ? '  ·  ' + v.note : '')
               + (why ? '\n' + why : ''),
        onclick: (why || opt.readonly) ? null : () => {
          mark(rowEls[i]);
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
        madeBy,
        el('span', { class: 'vtree-who', text: v.by || '' }),
        el('span', { class: 'vtree-when', text: when(v.at) }),
        el('span', { class: 'vtree-count',
                     text: v.n === undefined || v.n === null ? ''
                           : Number(v.n).toLocaleString()
                             + (opt.unit ? ' ' + opt.unit : '') }),
        states.length ? el('span', { class: 'vtree-state',
                                     text: states.join(' · ') }) : null,
        why ? el('span', { class: 'vtree-why', text: why }) : null,
        noteOf(v) ? el('span', { class: 'vtree-note', text: noteOf(v) }) : null,
        said ? el('span', { class: 'vtree-line', text: said }) : null,
      ].filter(Boolean));
    });

    /* "As they are now": a choice, but not a version, so it has a row and
       no node -- it is the set before anything more is banked. */
    const lead = (opt.lead && !opt.readonly) ? el('button', {
      class: 'vtree-row vtree-lead' + (chosen === null ? ' on' : ''),
      role: 'radio', 'aria-checked': chosen === null ? 'true' : 'false',
      'data-ref': '',
      title: opt.lead.title || null,
      onclick: () => {
        mark(lead);
        if (typeof opt.onpick === 'function') opt.onpick(null);
      },
    }, [
      el('strong', { class: 'vtree-n', text: opt.lead.name || 'now' }),
      opt.lead.text ? el('span', { class: 'vtree-who', text: opt.lead.text }) : null,
    ].filter(Boolean)) : null;

    function mark(node) {
      [lead].concat(rowEls).filter(Boolean).forEach((r) => {
        const on = r === node;
        r.classList.toggle('on', on);
        r.setAttribute('aria-checked', on ? 'true' : 'false');
      });
      draw();
    }

    if (lead) host.appendChild(lead);
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
    /* Choose one from outside, by what `idOf` answers, without calling
       onpick -- for a caller restoring a choice it already holds. */
    host.choose = (ref) => {
      const i = rowEls.findIndex((r) => r.dataset.ref === String(ref));
      // Nothing matching clears the choice: another tree was chosen.
      if (i >= 0) mark(rowEls[i]); else mark(lead && ref == null ? lead : null);
    };
    /* What produced this family of versions, as a chip above it --
       "Incisor output" (2026-10-20). `producer` is the entry's pipeline
       (or its source); `producerType` its kind, for a curation pass. */
    if (opt.producer && opt.family !== false) {
      const chip = producerChip(opt.producer, opt.producerType);
      if (chip) {
        const fam = el('div', { class: 'vtree-family' }, [
          el('div', { class: 'vtree-made' }, [chip]), host]);
        fam.redraw = host.redraw; fam.value = host.value;
        fam.choose = host.choose;
        return fam;
      }
    }
    return host;
  }

  /* ---------- what made one version ---------- */

  /* What last worked on one version (2026-10-21: "for each version...
     mention what it was last processed by, e.g. v2 = Checkup / Tooth
     Fairy"). Read from what the version itself records, most specific
     first:
       tag            the step that minted it (rootcanal, junction,
                      tooth_fairy)
       aligned        an alignment: Braces, Eye or Lock (`aligned_tool`, or
                      `aligned.tool` on a raw record; else by the kind)
       retimed        moved onto another clock
       the note       a pass that names its tool ("Tooth Fairy", "DS1/DS2")
       imported / v0  the detector's export: the entry's own producer
       otherwise      a person's pass, in the add-on for the entry's kind
     `src` is the entry's pipeline (or source), `type` its kind. */
  const VTAGS = { rootcanal: 'Root Canal', junction: 'Junction',
                  tooth_fairy: 'Tooth Fairy', toothfairy: 'Tooth Fairy',
                  braces: 'Braces', eye: 'Eye', lock: 'Lock',
                  dspca: 'X-ray', xray: 'X-ray' };
  const KIND_PASS = { ds: 'Checkup', ied: 'Spotter', pooled: 'Panning' };
  function versionProducer(v, src, type) {
    if (!v || typeof v !== 'object') return null;
    const kind = kindBase(type || '');
    const tag = String(v.tag || '').toLowerCase();
    if (VTAGS[tag]) return VTAGS[tag];
    const al = v.aligned_tool
      || (v.aligned && typeof v.aligned === 'object' ? v.aligned.tool : null);
    if (al || v.aligned === true) {
      const t = String(al || '');
      if (/eye/i.test(t)) return 'Eye';
      if (/lock/i.test(t)) return 'Lock';
      if (/braces/i.test(t)) return 'Braces';
      return kind === 'ied' ? 'Eye' : kind === 'pooled' ? 'Lock' : 'Braces';
    }
    if (v.retimed && v.retimed !== false) return 'Re-timed';
    const note = String(v.note || '');
    if (/Tooth Fairy/i.test(note)) return 'Tooth Fairy';
    if (/Root Canal/i.test(note)) return 'Root Canal';
    if (/DS1\/DS2|X-ray/i.test(note)) return 'X-ray';
    const name = String(versionLabel(v)).slice(1);
    const first = v.imported || v.v === 0 || name === '0';
    if (!first && KIND_PASS[kind]) return KIND_PASS[kind];
    const pr = producerOf(src, type);
    return pr ? pr.name : null;
  }

  function versionChip(v, src, type) {
    const name = versionProducer(v, src, type);
    if (!name) return null;
    return el('span', {
      class: 'flagchip producer vtree-by',
      'data-producer': name.toLowerCase().replace(/[^a-z]+/g, '-'),
      text: name,
      title: 'Last processed by ' + name,
    });
  }

  /* ---------- a version choice: one button, the whole tree ---------- */

  /* Every version picker (2026-10-21: "the drop down version picker is not
     the way to go... click version should bring the entire git like tree
     as a pop up"). The button says the version chosen, its count and what
     made it; pressing it opens the whole lineage -- every version with who,
     when, what made it and its note -- and picking a row chooses it and
     closes. Takes everything versionTree takes, plus:
       heading    the pop-up's title ("Which version of Incisor (ds)")
       sub        a line under it
       disabled   a reason the choice is closed; the tree still opens, to
                  read
     `button.version()` is the version chosen; `button.choose(ref)` sets it
     without calling onpick. */
  function versionButton(o) {
    const opt = o || {};
    const vs = opt.versions || [];
    const idOf = typeof opt.idOf === 'function' ? opt.idOf
      : (v) => (v && (v.id || v.label || v.v));
    let cur = opt.value === undefined ? null : opt.value;
    const match = (v) => {
      if (cur === null || cur === undefined) return false;
      const want = String(cur).replace(/^v/i, '');
      return String(idOf(v)).replace(/^v/i, '') === want
          || String(versionLabel(v)).slice(1) === want;
    };
    const chosen = () => vs.find(match) || null;
    const btn = el('button', { type: 'button', class: 'vbtn',
                               'aria-haspopup': 'dialog' });
    /* `disabled` closes the whole choice when it is a string (the reason);
       a function is a reason per version, as versionTree takes it, and
       leaves the choice open (2026-10-22, Lock greys Junction's). */
    const closed = typeof opt.disabled === 'string' ? opt.disabled : null;
    function face() {
      const v = chosen();
      btn.innerHTML = '';
      const kids = v
        ? [el('strong', { class: 'vbtn-n', text: versionLabel(v) }),
           v.n !== undefined && v.n !== null
             ? el('span', { class: 'vbtn-c', text: Number(v.n).toLocaleString()
                                                  + (opt.unit ? ' ' + opt.unit : '') })
             : null,
           opt.producer === false ? null
             : versionChip(v, opt.producer, opt.producerType),
           v.archived ? el('span', { class: 'vbtn-c', text: 'archived' }) : null]
        : [el('strong', { class: 'vbtn-n',
                          text: (opt.lead && opt.lead.name) || 'Choose a version' })];
      kids.push(el('span', { class: 'vbtn-more',
        text: vs.length > 1 ? vs.length + ' versions' : 'its only version' }));
      kids.push(el('span', { class: 'vbtn-caret', 'aria-hidden': 'true', text: '▾' }));
      kids.filter(Boolean).forEach((k) => btn.appendChild(k));
      btn.title = (closed ? closed + '\n' : '')
        + 'Every version of this, as a tree: who made each, when, what '
        + 'processed it, and its note. Click to see it'
        + (closed || opt.readonly ? '.' : ' and choose.');
    }
    btn.onclick = () => versionPop(Object.assign({}, opt, {
      value: cur,
      readonly: !!(opt.readonly || closed),
      onpick: (v) => {
        cur = v ? idOf(v) : null;
        face();
        closeModal();
        if (typeof opt.onpick === 'function') opt.onpick(v);
      },
    }));
    face();
    // `version`, not `value`: a <button>'s value is a native string
    // property, and a function assigned to it becomes its source text.
    btn.version = chosen;
    btn.choose = (ref) => { cur = ref; face(); };
    return btn;
  }

  /* The tree on its own, in a pop-up: for a button above, or for a caller
     that wants the whole picture of something it is not choosing. */
  function versionPop(o) {
    const opt = o || {};
    const tree = versionTree(Object.assign({ notes: true }, opt));
    showModal(el('div', { class: 'vpop' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: opt.heading || 'Versions' }),
        el('div', { class: 'spacer' }),
      ]),
      el('div', { class: 'mb' }, [
        opt.sub ? el('p', { class: 'hint', text: opt.sub }) : null,
        typeof opt.disabled === 'string'
          ? el('p', { class: 'hint warn-line', text: opt.disabled }) : null,
        el('p', { class: 'hint vpop-how', text: opt.readonly
          ? 'Newest at the top; a branch sits in a lane of its own, joined to '
            + 'the version it was worked from.'
          : 'Newest at the top; a branch sits in a lane of its own, joined to '
            + 'the version it was worked from. Click a version to use it.' }),
        tree,
      ].filter(Boolean)),
      modalFoot([], [button({ kind: 'ghost', text: 'Close',
                               onclick: () => closeModal() })]),
    ]));
    requestAnimationFrame(() => { if (tree.redraw) tree.redraw(); });
    return tree;
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

  /* ---------- a panel that does not rebuild itself ---------- */

  /* Every tool panel was a `paint()` that emptied its host and built all of
     it again, and every poll called it. On Doppler that was a batch's 1.5 s
     poll rebuilding a 666-row picker, the settings and the landed list: the
     panel visibly reloaded, the scroll jumped, an open <details> shut, the
     cursor left the search box, and a canvas flashed blank (2026-10-13).

     `sections(host, list)` keeps each part of a panel as a node of its own
     and rebuilds a part only when what it shows has changed. `list` is
     [{ key, sig, build, update }] in screen order:

       sig     everything the part shows, as a string or anything JSON can
               write. The SAME sig keeps the node -- its scroll, its focus,
               its open <details>, its canvas -- and build() is not called.
       build   makes the part's node. Called when the part is new or its
               sig changed.
       update  optional; called on every pass with the node, built or kept.
               For a shell whose insides are reconciled by a nested
               `sections` call, or for numbers that tick every second and
               should not cost a rebuild.

     A part that is new ENTERS (`.ui-enter`, staggered); one rebuilt in
     place does not, because it was already there. One no longer listed is
     removed. What survives a rebuild by its own markings: focus and caret
     of an element with `data-fk`, the open state of a <details> with
     `data-keep`, and the scroll of an element with `data-keep-scroll`.
     Returns { key: node } for the parts that were built this pass.

     IT TOUCHES ONLY ITS OWN PARTS. A node in the host without `data-sec`
     belongs to somebody else and is left exactly where it is: ToolKit
     mounts the Activity feed inside the same host, and the first version
     of this removed it on every pass -- ToolKit then mounted a new one,
     "Reading…" and a request each time, once a second while a run was out,
     with the page jumping as its height came and went (2026-10-13). */
  function sections(host, list) {
    const want = (list || []).filter(Boolean);
    const keys = new Set(want.map((s) => s.key));
    for (const n of Array.from(host.children)) {
      if (n.dataset && n.dataset.sec && !keys.has(n.dataset.sec)) n.remove();
    }
    const built = {};
    let prev = null;
    let entering = 0;
    for (const s of want) {
      const sig = typeof s.sig === 'string' ? s.sig : JSON.stringify(s.sig);
      let node = null;
      for (const n of host.children) {
        if (n.dataset && n.dataset.sec === s.key) { node = n; break; }
      }
      if (!node || node.__sig !== sig) {
        const fresh = s.build();
        fresh.dataset.sec = s.key;
        fresh.__sig = sig;
        if (node) {
          const after = carry(node, fresh);
          node.replaceWith(fresh);
          after();
        } else if (s.enter !== false) {
          enter(fresh, entering++);
        }
        node = fresh;
        built[s.key] = fresh;
      }
      const at = prev ? prev.nextSibling : host.firstChild;
      if (at !== node) host.insertBefore(node, at);
      if (s.update) s.update(node);
      prev = node;
    }
    return built;
  }

  /* What a rebuilt part takes over from the one it replaces. Returns what
     has to wait until the new node is in the page: its scroll.

     The part's OWN node counts as well as what is inside it. A part that IS
     its scroll box -- a picker list built as one element -- was skipped by
     `querySelectorAll`, which only looks inside, so a rebuilt list came back
     at the top (2026-10-14). */
  const selfAnd = (node, sel) => (node.matches && node.matches(sel) ? [node] : [])
    .concat(Array.from(node.querySelectorAll(sel)));
  const twinOf = (fresh, sel) => (fresh.matches && fresh.matches(sel)
    ? fresh : fresh.querySelector(sel));
  function carry(old, fresh) {
    const act = document.activeElement;
    if (act && old.contains(act) && act.dataset && act.dataset.fk) {
      const twin = fresh.querySelector('[data-fk="' + act.dataset.fk + '"]');
      if (twin) {
        let at = null;
        try { at = [act.selectionStart, act.selectionEnd]; } catch (e) { /* type */ }
        requestAnimationFrame(() => {
          twin.focus();
          if (at && at[0] != null) {
            try { twin.setSelectionRange(at[0], at[1]); } catch (e) { /* type */ }
          }
        });
      }
    }
    for (const d of old.querySelectorAll('details[data-keep]')) {
      const twin = fresh.querySelector('details[data-keep="' + d.dataset.keep + '"]');
      if (twin) twin.open = d.open;
    }
    const tops = [];
    for (const s of selfAnd(old, '[data-keep-scroll]')) {
      const twin = twinOf(fresh, '[data-keep-scroll="'
                                 + s.dataset.keepScroll + '"]');
      if (twin && s.scrollTop) tops.push([twin, s.scrollTop]);
    }
    return () => {
      // Now, so it never shows at the top; and next frame again, once
      // anything still settling inside it has its height.
      for (const [twin, top] of tops) twin.scrollTop = top;
      if (tops.length) {
        requestAnimationFrame(() => {
          for (const [twin, top] of tops) twin.scrollTop = top;
        });
      }
    };
  }

  /* The entrance: a short rise and fade, each new part a beat after the
     one above it. Ended on a timer as well as on `animationend`, because
     under the harness runner's virtual time `animationend` never fires and
     a part would keep the class -- and its transform -- for ever. */
  function enter(node, i) {
    if (reducedMotion()) return;
    node.classList.add('ui-enter');
    node.style.setProperty('--enter-i', String(Math.min(i, 6)));
    const done = () => {
      node.classList.remove('ui-enter');
      node.style.removeProperty('--enter-i');
    };
    node.addEventListener('animationend', done, { once: true });
    setTimeout(done, 900);
  }

  function reducedMotion() {
    try {
      return !!(window.matchMedia
                && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    } catch (e) { return false; }
  }

  /* A number that arrives, rather than appears: from where it was to where
     it is, over `ms`, easing out. The final text is set by a timer too, for
     the same reason as `enter`. */
  function countUp(node, to, o) {
    const opt = o || {};
    const fmt = opt.fmt || ((v) => Math.round(v).toLocaleString());
    const from = Number(opt.from || 0);
    const ms = opt.ms || 700;
    if (reducedMotion() || !isFinite(to)) { node.textContent = fmt(to); return; }
    const t0 = performance.now();
    let over = false;
    const step = (now) => {
      if (over) return;
      const k = Math.min(1, (now - t0) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      node.textContent = fmt(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
    setTimeout(() => { over = true; node.textContent = fmt(to); }, ms + 60);
  }

  /* ---------- archived things sink ---------- */

  /* The user's rule (2026-10-20), for every list that has archived things
     in it: they go to the bottom, behind one toggle that says how many.
     Never mixed in among what somebody is working from -- an archived pool
     sitting between two live ones was offered as though it were current --
     and never dropped from view either, because archiving is putting away,
     not deleting, and a thing nobody can find again cannot be unarchived.

       key       which list, so its open state survives a repaint
       items     the archived ones (the caller has already split them off)
       render    (items) => a node, or nodes, for them, drawn as the live
                 ones are
       noun      ['entry', 'entries'] -- what the count counts
       onToggle  (open) => the caller repaints
       forceOpen true when what is CHOSEN is archived: a choice is never
                 hidden behind a closed drawer

     Returns null when nothing is archived: no toggle for an empty drawer. */
  const archOpen = Object.create(null);

  function archivedTail(o) {
    const opt = o || {};
    const items = opt.items || [];
    if (!items.length) return null;
    const open = !!archOpen[opt.key] || !!opt.forceOpen;
    const noun = opt.noun || ['item', 'items'];
    const word = items.length === 1 ? noun[0] : noun[1];
    const wrap = el('div', { class: 'arch-tail' + (open ? ' open' : '') });
    wrap.appendChild(el('button', {
      class: 'arch-toggle', type: 'button',
      'aria-expanded': open ? 'true' : 'false',
      title: open ? 'Put the archived ' + noun[1] + ' away again'
                  : 'Archived ' + noun[1] + ' are kept, not deleted. '
                    + 'Show them to look at one or unarchive it.',
      onclick: () => {
        archOpen[opt.key] = !open;
        if (typeof opt.onToggle === 'function') opt.onToggle(!open);
      },
    }, [
      el('span', { class: 'caret', 'aria-hidden': 'true' }),
      el('span', { text: (open ? 'Hide ' : 'Show ') + items.length
                         + ' archived ' + word }),
    ]));
    if (open && typeof opt.render === 'function') {
      const body = el('div', { class: 'arch-body' });
      [].concat(opt.render(items) || []).filter(Boolean)
        .forEach((n) => body.appendChild(n));
      wrap.appendChild(body);
    }
    return wrap;
  }

  /* ---------- one submit per click; a duplicate is followed ---------- */

  /* The VACC rule (2026-10-20): the same job is never submitted twice.
     The server refuses a duplicate (backend/flights.py); this is the page's
     half. `submitOnce(key, send)` runs `send(submitId)` once per key at a
     time -- a second click while the first is still on its way gets the
     SAME promise, not a second POST -- and mints the `submit_id` the
     server remembers, so even a retried request lands on the first job.
     `duplicateOf(err)` reads a refusal: the running job's flight (with
     `job_id` when this computer is following it, or `where` it runs), or
     null for any other error. */
  const sending = Object.create(null);
  let sids = 0;

  function submitOnce(key, send) {
    if (sending[key]) return sending[key];
    sids += 1;
    const sid = Date.now().toString(36) + '-' + sids.toString(36) + '-'
      + Math.floor(Math.random() * 1e9).toString(36);
    const p = Promise.resolve().then(() => send(sid));
    sending[key] = p;
    const done = () => { if (sending[key] === p) delete sending[key]; };
    p.then(done, done);
    return p;
  }

  function isSending(key) { return !!sending[key]; }

  function duplicateOf(err) {
    const d = err && err.data;
    return d && d.kind === 'duplicate' ? (d.duplicate || {}) : null;
  }

  /* The sentence for a refused duplicate, the same in every tool. */
  function duplicateWords(dup) {
    const where = dup.where || 'another computer';
    return 'This exact job is already '
      + (dup.state === 'claimed' ? 'being submitted' : 'running')
      + ' on the VACC' + (where === 'this computer' ? '' : ', from ' + where)
      + (dup.job_id ? ' — following it.' : '. Its answer arrives when it '
         + 'lands there; nothing new was started.');
  }

  /* ---------- one search rule for every list of recordings ---------- */

  /* Whether `query` finds a row whose words are `parts` (2026-10-20).
     People type a recording the way they say it -- "m3 s2", "M3S2",
     "m3s2", "PTEN m3" -- and a list that only matched the spaced form
     could not find M3S2's runs that were plainly there. So the row's mouse
     and session are also offered joined ("m3s2"), case is ignored, and a
     joined word must match a whole token, so "m3s2" does not find m3 s21.
     `parts` may hold strings and numbers; `mouse`/`session` name the
     recording's numbers when the row has them. */
  function searchMatch(parts, query, o) {
    const opt = o || {};
    const q = String(query || '').trim().toLowerCase();
    if (!q) return true;
    const toks = [];
    for (const p of parts || []) {
      if (p === null || p === undefined || p === '') continue;
      toks.push(String(p).toLowerCase());
    }
    if (opt.mouse != null) {
      toks.push('m' + opt.mouse);
      if (opt.session != null) toks.push('m' + opt.mouse + 's' + opt.session);
    }
    if (opt.session != null) toks.push('s' + opt.session);
    const hay = ' ' + toks.join(' ') + ' ';
    const words = ' ' + toks.join(' ').split(/[\s,·()]+/).join(' ') + ' ';
    return q.split(/\s+/).every((w) => (/^m\d+s\d+$/.test(w)
      ? words.indexOf(' ' + w + ' ') >= 0
      : hay.indexOf(w) >= 0));
  }

  /* Split a list into [live, archived] by `isArchived`, keeping order. */
  function splitArchived(list, isArchived) {
    const live = [], gone = [];
    for (const x of list || []) (isArchived(x) ? gone : live).push(x);
    return [live, gone];
  }

  /* ---------- what produced a dataset ---------- */

  /* "Any time the version family is shown, indicate what produced it as a
     little chip -- Incisor output, Checkup output, Doppler output -- and in
     the data bank too" (2026-10-20). Read off the entry's pipeline (and its
     type, for a curation pass); an import says Imported. */
  const PRODUCERS = [
    [/^Incisor/i, 'Incisor'], [/^Doppler/i, 'Doppler'],
    [/curation \(ds/i, 'Checkup'], [/curation \(ied/i, 'Spotter'],
    [/curation \(pooled/i, 'Panning'],
    [/Confluence|Junction/i, 'Junction'], [/Root Canal/i, 'Root Canal'],
    [/Braces/i, 'Braces'], [/^Eye\b/i, 'Eye'], [/^Lock\b/i, 'Lock'],
    [/X-ray|DS1\/DS2/i, 'X-ray'], [/Tooth Fairy/i, 'Tooth Fairy'],
    [/Spark|The Arc/i, 'Spark'],
  ];
  function producerOf(src, type) {
    const p = String((src && typeof src === 'object' ? src.pipeline : src) || '');
    if (/Jarvis curation/i.test(p) && !/\((ds|ied|pooled)/i.test(p)) {
      return { name: type === 'ied' ? 'Spotter' : type === 'pooled' ? 'Panning'
                                                                    : 'Checkup',
               label: (type === 'ied' ? 'Spotter' : type === 'pooled'
                 ? 'Panning' : 'Checkup') + ' output', raw: p };
    }
    for (const [re, name] of PRODUCERS) {
      if (re.test(p)) return { name, label: name + ' output', raw: p };
    }
    if (!p) return null;
    return { name: 'Imported', label: /import|export|hand-sort|ETS|sorted/i.test(p)
      ? 'Imported' : p, raw: p };
  }

  function producerChip(src, type) {
    const pr = producerOf(src, type);
    if (!pr) return null;
    return el('span', {
      class: 'flagchip producer',
      'data-producer': pr.name.toLowerCase().replace(/[^a-z]+/g, '-'),
      text: pr.label,
      title: 'Produced by ' + (pr.raw || pr.name),
    });
  }

  /* ---------- the link to the next step ---------- */

  /* Every bundle step ends the same way (2026-10-20): a row, right-aligned,
     "Next: <Step> — <what it does> →", read off ToolKit's own bundle list,
     so inserting a step renumbers and relinks every page. The last step of
     a bundle has none. A step not in a bundle has none.

       toolId     the step this page is
       ready      true, or a sentence saying why the next step cannot use
                  this yet (the button is shown, disabled, with it)
       note       a short line beside it, what carries over */
  function nextStep(toolId) {
    const tk = BARRY.views && BARRY.views.toolkit;
    if (!tk || typeof tk.bundles !== 'function') return null;
    const via = typeof tk.via === 'function' ? tk.via() : null;
    const list = tk.bundles();
    const order = via ? list.filter((b) => b.id === via).concat(list) : list;
    for (const b of order) {
      const i = (b.steps || []).findIndex((s) => s.id === toolId);
      if (i < 0) continue;
      const nx = b.steps[i + 1];
      return nx ? { id: nx.id, name: nx.name, does: nx.does, soon: nx.soon,
                    bundle: b.id, bundleName: b.name } : null;
    }
    return null;
  }

  function handoff(toolId, o) {
    const opt = o || {};
    const nx = nextStep(toolId);
    if (!nx) return null;
    const why = opt.ready === undefined || opt.ready === true ? null
      : (typeof opt.ready === 'string' ? opt.ready : 'Not ready yet.');
    const soon = nx.soon ? nx.name + ' is not built yet: ' + nx.soon : null;
    /* Only ever the next step's page (2026-10-21: "Next links just take
       you to the next ToolKit page, and not initiate opening any specific
       object or recording"). No caller's onclick: what carries over waits
       there, under Pick up a set or in its picker, for you to choose. */
    const go = () => {
      const tk = BARRY.views.toolkit;
      if (tk && tk.pick) tk.pick(nx.id, nx.bundle);
      if (typeof setView === 'function' && BARRY.state.view !== 'toolkit') {
        setView('toolkit');
      }
    };
    return el('div', { class: 'handoff' }, [
      opt.note ? el('span', { class: 'hint handoff-note', text: opt.note }) : null,
      button({
        kind: 'ghost', size: 'sm', extra: 'handoff-go',
        text: 'Next: ' + nx.name + ' — ' + nx.does + ' →',
        title: why || soon || (nx.bundleName + ': ' + nx.name + ', '
                               + nx.does),
        disabled: !!(why || soon),
        onclick: go,
      }),
    ].filter(Boolean));
  }

  /* ---------- a mode's own end of the one bar ---------- */

  /* Every add-on's bar ends the same way (2026-10-20): its occasional
     controls folded into More, then the next step of its bundle, then Bank
     -- and after those the shell's Simplify, ? and Leave (core.js
     `setMode`), so Leave is always the last thing, far right.

       more   nodes for the More panel (a window length, a light switch,
              List all, Tooth Fairy, Auto-bank...); none, no More
       next   { text, title, onclick }: "Next: Eye — line them up →"
       bank   { text, title, onclick, disabled }: "Bank the results…" */
  function modeEnd(o) {
    const opt = o || {};
    const more = [].concat(opt.more || []).filter(Boolean);
    const bits = [];
    if (more.length) {
      const pop = el('div', { class: 'mode-more-pop' }, more);
      // Open again after a repaint if it was open before it.
      const det = el('details', { class: 'mode-more',
                                  open: modeEnd.open ? 'open' : null }, [
        el('summary', { text: 'More', title: 'Settings and tools for this '
                                             + 'sitting' }),
        pop,
      ]);
      det.addEventListener('toggle', () => { modeEnd.open = det.open; });
      /* Shut when somebody clicks anywhere else -- a <details> stays open.
         One listener for every bar ever drawn, not one per repaint. */
      if (!modeEnd.wired) {
        modeEnd.wired = true;
        document.addEventListener('mousedown', (e) => {
          for (const d of document.querySelectorAll('details.mode-more[open]')) {
            if (!d.contains(e.target)) { d.open = false; modeEnd.open = false; }
          }
        });
      }
      bits.push(det);
    }
    if (opt.next) {
      bits.push(button({ kind: 'ghost', size: 'sm', text: opt.next.text,
                         title: opt.next.title || null,
                         onclick: opt.next.onclick }));
    }
    if (opt.bank) {
      bits.push(button({ kind: 'ghost', size: 'sm',
                         text: opt.bank.text || 'Bank the results…',
                         title: opt.bank.title || null,
                         disabled: !!opt.bank.disabled,
                         onclick: opt.bank.onclick }));
    }
    return el('div', { class: 'mode-own-end' }, bits);
  }

  /* ---------- which working set: a kind names its bank entry ---------- */

  /* A working set belongs to ONE bank entry since 2026-10-20 ("purely bank
     identity based"), and its kind says which: "ied.e3b3111be3118" is the
     set of entry 3b3111be3118. The sets made before stay "ds", "ied",
     "pooled" -- one per recording -- and are matched to the entry they were
     started from. Every route keeps its shape, /api/curation/<gid>/<kind>/..,
     so a caller only has to carry the set's own kind instead of a constant. */
  const kindBase = (k) => String(k || '').split('.')[0];
  function kindEntry(k) {
    const s = String(k || '');
    const i = s.indexOf('.e');
    return i >= 0 ? (s.slice(i + 2) || null) : null;
  }

  function setUrl(gid, kind, what) {
    return '/api/curation/' + encodeURIComponent(gid) + '/'
      + encodeURIComponent(kind) + (what ? '/' + what : '');
  }

  /* The kind of the set that stands for bank entry `entryId` on `gid`, or
     null when there is none: a per-entry set of it, or an older set started
     from it. */
  async function setForEntry(gid, base, entryId) {
    const got = await api('/api/curation/for-recording/'
                          + encodeURIComponent(gid));
    const s = ((got && got.existing) || []).find((x) => kindBase(x.kind) === base
      && (kindEntry(x.kind) === entryId
          || (!kindEntry(x.kind) && (x.source || {}).bank_entry === entryId)));
    return s ? s.kind : null;
  }

  /* ---------- one order for every list of recordings ---------- */

  /* Numbers inside names compare as numbers (2026-10-20): m1, m3, m5, m12
     -- never m1, m12, m3, m34, m5 -- "wherever there are lists of
     recordings displayed". So do sessions (s2 before s10), rats (J2 before
     J10), channels (CSC9 before CSC10) and nicknames. Case is ignored; a
     tie falls back to the plain text, so the order is total. A list that
     is in time order, or ranked by a count, keeps that order: this is the
     order for names. */
  const NAT = (typeof Intl !== 'undefined' && Intl.Collator)
    ? new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
    : null;

  function natCompare(a, b) {
    const x = a == null ? '' : String(a);
    const y = b == null ? '' : String(b);
    const c = NAT ? NAT.compare(x, y) : 0;
    if (c) return c;
    return x < y ? -1 : (x > y ? 1 : 0);
  }

  /* `list` sorted in place by `key(item)` in that order, and returned. A
     key may be an array, compared part by part: [project, label]. */
  function natSort(list, key) {
    const k = key || ((x) => x);
    return (list || []).sort((a, b) => {
      const ka = k(a), kb = k(b);
      if (!Array.isArray(ka) && !Array.isArray(kb)) return natCompare(ka, kb);
      const A = [].concat(ka), B = [].concat(kb);
      for (let i = 0; i < Math.max(A.length, B.length); i++) {
        const c = natCompare(A[i], B[i]);
        if (c) return c;
      }
      return 0;
    });
  }

  /* ---------- numbers right, words left, in every table ---------- */

  /* "All the text results are right aligned" (2026-10-20). Tables are
     built in some eighty places, and many right-align every column but the
     first, so a mouse, a group or a verdict sat on the right like a number.
     Every table now aligns by what its columns hold -- a column of numbers
     (signs, units, ranges and "312 / 1,204" allowed) right, in tabular
     figures; a column of words left -- decided from the cells, so no
     builder has to remember. A cell holding a control (a button, an input)
     or nothing but a dash does not vote, and keeps its own alignment. A
     table that wants its own says data-al="off". Big tables (over 3,000
     rows) are left as built. */
  const NUM_CELL = new RegExp(
    '^[(\\[]?[-+−±~≈<>≤≥]?\\s*[$£€]?'
    + '\\d[\\d,]*(?:\\.\\d+)?(?:[eE][-+]?\\d+)?'
    + '(?:\\s*(?:%|‰|[A-Za-zµ°×]{1,7}))?'
    + '(?:\\s*(?:/|–|-|to|of|±)\\s*[-+−]?\\d[\\d,]*'
    + '(?:\\.\\d+)?(?:\\s*(?:%|[A-Za-zµ°]{1,7}))?)?'
    + '[*†]{0,3}[)\\]]?$');

  function cellVote(cell) {
    if (cell.colSpan > 1) return null;
    if (cell.querySelector('button, input, select, textarea')) return null;
    const t = (cell.textContent || '').replace(/\s+/g, ' ').trim();
    if (!t || /^[-–—·?…]$|^n\/?a$/i.test(t)) return null;
    return NUM_CELL.test(t) ? 'num' : 'text';
  }

  function alignTable(table) {
    if (table.dataset.al === 'off') return;
    const rows = table.rows;
    if (!rows || !rows.length || rows.length > 3000) return;
    const head = [], body = [];
    for (const r of rows) {
      const inHead = r.parentNode && r.parentNode.tagName === 'THEAD';
      const allTh = r.cells.length
        && Array.prototype.every.call(r.cells, (c) => c.tagName === 'TH');
      ((inHead || (allTh && !body.length)) ? head : body).push(r);
    }
    const votes = [];                      // per column: [num, text]
    const cols = (r) => {                  // [cell, column] pairs, colspans counted
      const out = [];
      let i = 0;
      for (const c of r.cells) { out.push([c, i]); i += c.colSpan || 1; }
      return out;
    };
    for (const r of body.slice(0, 400)) {
      for (const [c, i] of cols(r)) {
        const v = cellVote(c);
        if (!v) continue;
        const t = votes[i] || (votes[i] = [0, 0]);
        t[v === 'num' ? 0 : 1] += 1;
      }
    }
    const kind = votes.map((t) => {
      if (!t) return null;
      if (t[0] && t[1] <= Math.floor(t[0] / 10)) return 'num';
      return t[1] ? 'text' : null;
    });
    for (const r of head.concat(body)) {
      for (const [c, i] of cols(r)) {
        const k = c.colSpan > 1 ? null : kind[i];
        if (k && c.dataset.al !== k) c.dataset.al = k;
        else if (!k && c.dataset.al) delete c.dataset.al;
      }
    }
  }

  const alignQ = new Set();
  let alignT = 0;

  function alignSoon(t) {
    if (!t || (t.dataset && t.dataset.al === 'off')) return;
    alignQ.add(t);
    if (!alignT) alignT = setTimeout(alignFlush, 40);
  }

  function alignFlush() {
    alignT = 0;
    const ts = Array.from(alignQ);
    alignQ.clear();
    for (const t of ts) {
      if (!t.isConnected) continue;
      try { alignTable(t); } catch (e) { /* a table it cannot read keeps its look */ }
    }
  }

  function alignWatch() {
    if (alignWatch.on || typeof MutationObserver === 'undefined') return;
    alignWatch.on = true;
    const mo = new MutationObserver((muts) => {
      for (const m of muts) {
        const at = m.target.nodeType === 1 ? m.target : m.target.parentElement;
        const t = at && at.closest ? at.closest('table') : null;
        if (t) { alignSoon(t); continue; }
        for (const n of m.addedNodes) {
          if (n.nodeType !== 1) continue;
          if (n.tagName === 'TABLE') alignSoon(n);
          else for (const x of n.getElementsByTagName('table')) alignSoon(x);
        }
      }
    });
    mo.observe(document.body, { childList: true, subtree: true,
                                characterData: true });
    for (const t of document.getElementsByTagName('table')) alignSoon(t);
  }

  if (typeof document !== 'undefined') {
    if (document.body) alignWatch();
    else document.addEventListener('DOMContentLoaded', alignWatch);
  }

  return {
    archivedTail: archivedTail,
    splitArchived: splitArchived,
    searchMatch: searchMatch,
    natCompare: natCompare,
    natSort: natSort,
    alignTable: alignTable,
    modeEnd: modeEnd,
    handoff: handoff,
    producerOf: producerOf,
    producerChip: producerChip,
    nextStep: nextStep,
    kindBase: kindBase,
    kindEntry: kindEntry,
    setUrl: setUrl,
    setForEntry: setForEntry,
    submitOnce: submitOnce,
    isSending: isSending,
    duplicateOf: duplicateOf,
    duplicateWords: duplicateWords,
    sections: sections,
    countUp: countUp,
    reducedMotion: reducedMotion,
    when: when,
    versionLabel: versionLabel,
    versionNext: versionNext,
    runBar: runBar,
    runPlan: runPlan,
    openOn: openOn,
    pickRecording: pickRecording,
    versionTree: versionTree,
    versionButton: versionButton,
    versionPop: versionPop,
    versionProducer: versionProducer,
    versionChip: versionChip,
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
