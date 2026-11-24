/* ==========================================================================
   curkit.js -- three things every curation tool shares (2026-11-20).

   Asked for by the user, after Rain's report that opening an older step
   banked a new version, that extra copies looked unworked, and that
   colleagues keep asking "does it save? do I just leave it?":

     NOTES      anything that can be flagged can carry a note -- in Panning,
                Checkup, Spotter, and on a row of Lock, Braces or Eye. W
                writes one. The note goes into the bank with the event.

     SAVE       the work was always saved, each decision as it was made,
                and uploaded with the next sync. Save does the upload now
                and reads the shared database back, so the answer to "is it
                saved?" is a sentence somebody can see. Leaving with work
                that has not been confirmed offers Save & leave.

     VIEW ONLY  "only when picked": a View only button beside every Open.
                A set opened that way writes nothing -- no decision, no
                note, no bank, no name put on it -- and says so in the bar.

   Each tool keeps its own state; this is the parts that must look and
   behave the same in all six.
   ========================================================================== */
'use strict';

BARRY.curKit = (function () {
  const clockOf = (iso) => {
    const d = iso ? new Date(String(iso).replace(/([+-]\d\d)(\d\d)$/, '$1:$2'))
                  : new Date();
    return isFinite(d) ? d.toLocaleTimeString([], { hour: 'numeric',
                                                    minute: '2-digit' })
                       : '';
  };
  const num = (n) => Number(n || 0).toLocaleString();

  /* ---------- notes ---------- */

  /* The note dialog. `o`: { title, about, text, onSave(text) -> Promise }.
     Resolves with the note as saved ('' for taken off), or null when
     cancelled. Ctrl+Enter saves, as everywhere a box this size is. */
  function editNote(o) {
    const opt = o || {};
    const had = String(opt.text || '');
    return new Promise((resolve) => {
      let busy = false;
      const ta = el('textarea', {
        class: 'ck-note-ta', rows: '5', maxlength: '2000',
        placeholder: 'What should the next person know about this one? '
                   + 'Why it is flagged, what to look at, what you decided.',
      });
      ta.value = had;
      const why = el('p', { class: 'confirm-err hidden' });
      const finish = (v) => { if (busy) return; closeModal(); resolve(v); };
      const go = async (text) => {
        if (busy) return;
        busy = true;
        why.classList.add('hidden');
        try {
          if (typeof opt.onSave === 'function') await opt.onSave(text);
          busy = false;
          finish(text);
        } catch (e) {
          busy = false;
          why.textContent = (e && e.message) || String(e);
          why.classList.remove('hidden');
        }
      };
      ta.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
          e.preventDefault(); go(ta.value.trim());
        }
        // The tool's own keys must not hear what is typed here.
        e.stopPropagation();
      });
      showModal(el('div', { class: 'ck-note-dlg' }, [
        el('div', { class: 'mh' }, [
          el('h3', { text: opt.title || 'Note' }),
          el('div', { class: 'spacer' }),
          el('button', { class: 'close-x', onclick: () => finish(null),
            html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
        ]),
        el('div', { class: 'mb' }, [
          opt.about ? el('p', { class: 'hint', text: opt.about }) : null,
          ta,
          el('p', { class: 'hint quiet',
            text: 'Saved with the event and carried into the bank when it is '
                + 'banked. Ctrl+Enter saves.' }),
          why,
        ].filter(Boolean)),
        el('div', { class: 'mf' }, [
          had ? el('button', { class: 'btn ghost danger', text: 'Remove note',
                               onclick: () => go('') }) : null,
          el('div', { class: 'spacer' }),
          el('button', { class: 'btn ghost', text: 'Cancel',
                         onclick: () => finish(null) }),
          el('button', { class: 'btn', text: 'Save note',
                         onclick: () => go(ta.value.trim()) }),
        ].filter(Boolean)),
      ]));
      setTimeout(() => { try { ta.focus(); ta.select(); } catch (e) { /* gone */ } }, 30);
    });
  }

  /* The note on the event on screen, for the bar: the words, and whose. */
  function noteLine(text, by, onEdit) {
    if (!text) return null;
    return el('button', {
      class: 'ck-note-line' + (onEdit ? '' : ' ro'), type: 'button',
      title: 'Note' + (by ? ' by ' + by : '') + ': ' + text
             + (onEdit ? '\nClick, or press W, to change it.' : ''),
      onclick: onEdit || null,
    }, [
      el('span', { class: 'ck-note-ico', 'aria-hidden': 'true', text: '✎' }),
      el('span', { class: 'ck-note-txt', text: text }),
      by ? el('span', { class: 'ck-note-by', text: '— ' + by }) : null,
    ].filter(Boolean));
  }

  /* The Note button for a bar: says whether there is one already. */
  function noteButton(has, onclick, disabled) {
    return el('button', {
      class: 'mini ck-note-btn' + (has ? ' has' : ''),
      title: (has ? 'Change the note on this one' : 'Write a note on this one')
             + ' — why it is flagged, what to look at  [W]',
      disabled: disabled ? 'disabled' : null,
      onclick,
    }, [el('span', { text: has ? '✎ Note' : '+ Note' }), el('kbd', { text: 'W' })]);
  }

  /* ---------- save ---------- */

  /* What a save came to, in one sentence. */
  function savedWords(r, noun) {
    const what = noun || 'decided';
    const tail = r.notes ? ', ' + num(r.notes) + ' note'
                           + (r.notes === 1 ? '' : 's') : '';
    if (r.nothing_here) {
      return 'Nothing to upload from this computer: everything in it is '
           + 'already somebody else’s, and theirs to send.';
    }
    const head = r.total != null
      ? num(r.decided) + ' of ' + num(r.total) + ' ' + what + tail
      : (r.calls != null ? num(r.calls) + ' answered' + tail : 'Your work');
    if (r.confirmed) {
      return 'Saved. ' + head + ' — uploaded, and the shared database '
           + 'confirms it (' + clockOf(r.at) + '). Safe to leave.';
    }
    if (r.cloud_total != null) {
      return 'Saved here and uploaded, but the shared database now holds '
           + num(r.cloud_decided) + ' of ' + num(r.cloud_total) + ' decided, '
           + 'not ' + num(r.decided) + ' — a colleague may be working in it '
           + 'too. Your calls are kept on this computer either way.';
    }
    return 'Saved here and uploaded; the shared database did not answer the '
         + 'check. The next sync will check again.';
  }

  /* The Save button, said at once when something changes: the tools count a
     change when the server answers, which is after the bar was drawn. */
  function saveState(dirty) {
    for (const b of document.querySelectorAll('.ck-save')) {
      b.dataset.state = dirty ? 'dirty' : 'clean';
      b.textContent = dirty ? 'Save' : 'Saved';
    }
  }

  /* Save one thing and say what happened. `o`: { url, settle, noun }.
     Resolves with the answer, or null when it failed (said in a toast). */
  async function save(o) {
    const opt = o || {};
    if (typeof opt.settle === 'function') {
      try { await opt.settle(); } catch (e) { /* the save says */ }
    }
    toast('Saving and uploading…', null, 2500);
    let r;
    try {
      r = await apiPost(opt.url, {});
    } catch (e) {
      toast((e && e.message) || 'The save did not go through.', 'err', 10000);
      return null;
    }
    toast(savedWords(r, opt.noun), r.confirmed ? 'ok' : 'warn',
          r.confirmed ? 7000 : 12000);
    return r;
  }

  /* Leaving with work the shared database has not confirmed: Save & leave,
     Leave, or Stay. `o`: { dirty, save, tool }. Resolves true to leave. */
  function leaveAsk(o) {
    const opt = o || {};
    if (!opt.dirty) return Promise.resolve(true);
    return new Promise((resolve) => {
      let busy = false;
      const why = el('p', { class: 'confirm-err hidden' });
      const saveBtn = el('button', { class: 'btn', text: 'Save & leave' });
      const done = (v) => { if (busy) return; closeModal(); resolve(v); };
      saveBtn.addEventListener('click', async () => {
        if (busy) return;
        busy = true;
        saveBtn.disabled = 'disabled';
        saveBtn.textContent = 'Saving…';
        let r = null;
        try { r = await opt.save(); } catch (e) { r = null; }
        busy = false;
        if (r) { done(true); return; }
        saveBtn.disabled = null;
        saveBtn.textContent = 'Try again';
        why.textContent = 'The upload did not go through. Every decision is '
          + 'still saved on this computer and goes up with the next sync, so '
          + 'leaving loses nothing.';
        why.classList.remove('hidden');
      });
      showModal(el('div', {}, [
        el('div', { class: 'mh' }, [
          el('h3', { text: 'Leave ' + (opt.tool || 'this set') + '?' }),
          el('div', { class: 'spacer' }),
        ]),
        el('div', { class: 'mb' }, [
          el('p', { class: 'confirm-msg', text:
            'Everything you did is saved on this computer, and goes up to the '
            + 'shared database with the next sync. Save & leave uploads it now '
            + 'and checks it arrived before you go.' }),
          why,
        ]),
        el('div', { class: 'mf' }, [
          el('button', { class: 'btn ghost', text: 'Stay',
                         onclick: () => done(false) }),
          el('div', { class: 'spacer' }),
          el('button', { class: 'btn ghost', text: 'Leave',
                         title: 'It is saved here; the next sync uploads it',
                         onclick: () => done(true) }),
          saveBtn,
        ]),
      ]));
    });
  }

  /* ---------- view only ---------- */

  /* The bar's first word when a set is open to look at. */
  function viewBadge(onWork) {
    return el('div', { class: 'ck-view' }, [
      el('strong', { text: 'View only' }),
      el('span', { text: 'nothing here is saved, banked or put in your name' }),
      onWork ? el('button', { class: 'btn ghost sm', text: 'Work on it…',
        title: 'Open it again to work on: decisions are saved, and the '
             + 'first one puts your name on the set.',
        onclick: onWork }) : null,
    ].filter(Boolean));
  }

  let lastRefusal = 0;
  /* A key or button that would change something, pressed while viewing. */
  function refuse() {
    const now = Date.now();
    if (now - lastRefusal < 1500) return false;
    lastRefusal = now;
    toast('View only — nothing is changed. Press “Work on it…” in the bar '
          + 'to make changes.', 'warn', 5000);
    return false;
  }

  /* "Work on it": asked once, because the point of View only is that
     nothing happens by accident. */
  function askToWork(name) {
    return BARRY.confirm('Work on ' + (name || 'this set') + '?',
      'From now on what you do here is saved, and your first decision puts '
      + 'your name on it. Somebody else may be meant to be working on it — '
      + 'check before you change their calls.', 'Work on it');
  }

  /* The View only button that sits beside an Open. */
  function viewButton(onclick, opts) {
    const o = opts || {};
    return el('button', {
      class: 'btn ghost sm ck-view-btn', text: o.text || 'View only',
      disabled: o.disabled ? 'disabled' : null,
      title: o.title || 'Open it to look at. Nothing you do is saved, nothing '
             + 'is banked, and your name is not put on it.',
      onclick,
    });
  }

  return { editNote, noteLine, noteButton, save, saveState, savedWords, leaveAsk,
           viewBadge, refuse, askToWork, viewButton };
})();
