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

  return {
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
