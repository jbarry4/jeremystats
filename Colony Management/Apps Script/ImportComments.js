//ImportComments.gs
/**
 * COMMENT MIGRATION — archive sheet -> "KCNT1 Active 2.0"
 * =======================================================
 * Carries the cell comments from the pre-migration sheet across to 2.0,
 * matching on MOUSE ID and ACTIVITY rather than on cell position — because
 * neither the rows nor the columns line up any more.
 *
 * A comment on AV119 of the archive is not a comment on AV119 of 2.0. AV was
 * "Euthanize" in the old layout and is "H10 opto (R)" in the new one, and row
 * 119 is a different mouse. This resolves the source cell to "mouse 314,
 * Euthanize" and then finds where that lives in 2.0 — BC119. Recording
 * comments follow the data into the LEFT hemisphere column, which is where the
 * migration put the v1 values.
 *
 * ---------------------------------------------------------------------------
 * READ THIS FIRST — WHAT CAN AND CANNOT BE COPIED
 *
 * Your comments are THREADED COMMENTS: the ones with an author, a timestamp, a
 * resolve button and @mentions. Apps Script cannot read or create those.
 * SpreadsheetApp only exposes NOTES — the plain yellow hover kind — and the
 * Drive API cannot anchor a new comment to a specific cell in a Sheet.
 *
 * So this writes NOTES, with the author, date and resolved state preserved as
 * the first line of the text:
 *
 *     Angelina Woychosky — 2026-07-28
 *     Right eye good. Left eye all injectate administered, but appeared cloudy.
 *
 * What you keep: the text, who said it, when, whether it was resolved, and the
 * cell it belongs to. What you lose: replies as separate entities, @mention
 * links, and the ability to tick "resolve". If that trade is not worth it,
 * stop here — the archive sheet still holds the originals.
 *
 * ---------------------------------------------------------------------------
 * INPUT
 *
 * Apps Script cannot read the source comments either, so they have to be handed
 * over. Put them on a sheet called "Comment Import" with these headers — the
 * order does not matter and extra columns are ignored:
 *
 *     cell      the ORIGINAL cell on the archive sheet, e.g. AV119   (required)
 *     comment   the comment text                                     (required)
 *     author                                                         (optional)
 *     date                                                           (optional)
 *     state     "resolved" marks it resolved                         (optional)
 *
 * Everything else — which mouse, which activity, which cell in 2.0 — is worked
 * out from the live sheets each run, so it stays correct even if rows move.
 *
 * Several comments on one cell are merged into a single note, oldest first.
 * Re-running is safe: a comment already present in the note is not added twice.
 */

// =============================================================================
// CONFIG
// =============================================================================

const IC_INPUT_SHEET  = 'Comment Import';
const IC_REPORT_SHEET = 'Comment Import Report';

/** The pre-migration sheet, by whatever it is called now. First match wins. */
const IC_ARCHIVE_NAMES = ['KCNT1 Active (Archive)', 'KCNT1 Active (v1 archive)', 'KCNT1 Active'];

/** Trailing qualifiers that belong to the activity block before them. */
const IC_QUALIFIERS = ['Time', 'Lead', 'Sessions', 'Delayed?', 'Double Inj?'];

/** v1's single recording column became two; the old data went into (L). */
const IC_RECORDING_BASES = ['H3 probe', 'H10 probe', 'H10 opto'];

/** Separates merged comments inside one note. */
const IC_SEPARATOR = '\n\n————————\n';

// =============================================================================
// ENTRY POINT
// =============================================================================

function importComments() {
  const ui = SpreadsheetApp.getUi();

  try {
    Logger.log('--- COMMENT MIGRATION START ---');
    const ss = SpreadsheetApp.getActiveSpreadsheet();

    const src = ss.getSheetByName(IC_INPUT_SHEET);
    if (!src) {
      throw new Error('Could not find a sheet named "' + IC_INPUT_SHEET + '".\n\n' +
        'Create it with columns: cell, comment, author, date, state.\n\n' +
        'Sheets in this file:\n' +
        ss.getSheets().map(function (s) { return '  • ' + s.getName(); }).join('\n'));
    }

    let archive = null;
    for (let i = 0; i < IC_ARCHIVE_NAMES.length && !archive; i++) {
      archive = ss.getSheetByName(IC_ARCHIVE_NAMES[i]);
    }
    if (!archive) {
      throw new Error('Could not find the pre-migration sheet. Looked for: ' +
        IC_ARCHIVE_NAMES.join(', ') + '.\n\nIt is needed to work out which mouse ' +
        'and which activity each original cell belonged to.');
    }

    const target = getSyncSheet_();
    if (!target) throw new Error('Could not find "' + V2_SHEET_NAMES.join('" or "') + '".');

    const plan = icPlan_(src, archive, target);

    if (plan.notes.length === 0) {
      icWriteReport_(ss, plan, archive.getName(), target.getName(), false);
      ui.alert('Comment Migration', 'Nothing to copy.\n\n' + plan.skipped.length +
        ' comment(s) could not be placed. See "' + IC_REPORT_SHEET + '".', ui.ButtonSet.OK);
      return;
    }

    const confirm = ui.alert('Copy ' + plan.mapped + ' comment(s)?',
      'From: ' + archive.getName() + '\n' +
      'To:   ' + target.getName() + '\n\n' +
      'Comments placed:            ' + plan.mapped + '\n' +
      'Cells receiving a note:     ' + plan.notes.length + '\n' +
      '  ...of which already have a note: ' + plan.withExisting + '\n' +
      'Already copied (skipped):   ' + plan.duplicates + '\n' +
      'Could not be placed:        ' + plan.skipped.length + '\n\n' +
      'These are written as NOTES, not threaded comments — Apps Script cannot ' +
      'create those. Author and date are kept in the text.\n\n' +
      'Existing notes are added to, never replaced.\n\nProceed?',
      ui.ButtonSet.YES_NO);

    if (confirm !== ui.Button.YES) {
      icWriteReport_(ss, plan, archive.getName(), target.getName(), false);
      ui.alert('Cancelled', 'Nothing was written. The report shows what would have ' +
        'happened.', ui.ButtonSet.OK);
      return;
    }

    plan.notes.forEach(function (n) {
      target.getRange(n.row, n.col).setNote(n.note);
    });
    SpreadsheetApp.flush();

    icWriteReport_(ss, plan, archive.getName(), target.getName(), true);

    const summary =
      'From: ' + archive.getName() + '\nTo:   ' + target.getName() + '\n\n' +
      'Comments copied:          ' + plan.mapped + '\n' +
      'Cells given a note:       ' + plan.notes.length + '\n' +
      'Already present, skipped: ' + plan.duplicates + '\n' +
      'Could not be placed:      ' + plan.skipped.length + '\n\n' +
      'Detail is in the "' + IC_REPORT_SHEET + '" tab.';

    Logger.log(summary);
    Logger.log('--- COMMENT MIGRATION COMPLETE ---');
    ui.alert('Comments Copied', summary, ui.ButtonSet.OK);

  } catch (err) {
    Logger.log('ERROR: ' + err.message + '\n' + err.stack);
    ui.alert('⚠️ Comment Migration Failed', err.message +
      '\n\n(Check the Apps Script Execution Log for details)', ui.ButtonSet.OK);
  }
}

// =============================================================================
// PLANNING
// =============================================================================

function icPlan_(src, archive, target) {
  const data = src.getDataRange().getValues();
  if (data.length < 2) throw new Error('"' + IC_INPUT_SHEET + '" has no rows.');

  const head = data[0].map(function (h) { return String(h).trim().toLowerCase(); });
  const col = function (n) { return head.indexOf(n); };

  const cCell = col('cell');
  const cText = col('comment');
  const cWho  = col('author');
  const cWhen = col('date');
  const cState = col('state');

  if (cCell === -1 || cText === -1) {
    throw new Error('"' + IC_INPUT_SHEET + '" needs at least a "cell" column and a ' +
      '"comment" column.\n\nFound: ' + data[0].filter(String).join(', '));
  }

  const aHead = archive.getRange(1, 1, 1, archive.getLastColumn()).getValues()[0]
                       .map(function (h) { return String(h).trim(); });
  const tHead = target.getRange(1, 1, 1, target.getLastColumn()).getValues()[0]
                       .map(function (h) { return String(h).trim(); });

  const aId = aHead.indexOf('Mouse ID');
  const tId = tHead.indexOf('Mouse ID');
  if (aId === -1 || tId === -1) throw new Error('Both sheets need a "Mouse ID" column.');

  const aIds = archive.getRange(2, aId + 1, Math.max(archive.getLastRow() - 1, 1), 1).getValues();
  const tIds = target.getRange(2, tId + 1, Math.max(target.getLastRow() - 1, 1), 1).getValues();

  const rowOfMouse = {};
  tIds.forEach(function (r, i) {
    const id = String(r[0] || '').trim();
    if (id && !(id in rowOfMouse)) rowOfMouse[id] = i + 2;
  });

  // Gather comments per destination cell so several become one note.
  const buckets = {};
  const skipped = [];
  let mapped = 0;

  for (let r = 1; r < data.length; r++) {
    const ref = String(data[r][cCell] || '').trim().toUpperCase();
    const text = String(data[r][cText] || '').trim();
    if (ref === '' && text === '') continue;

    const who = cWho === -1 ? '' : String(data[r][cWho] || '').trim();
    const when = cWhen === -1 ? '' : icDateText_(data[r][cWhen]);
    const resolved = cState !== -1 && /resolv|done|closed/i.test(String(data[r][cState] || ''));

    const note = { ref: ref, text: text, who: who, when: when, resolved: resolved, row: r + 1 };

    if (text === '') { skipped.push(icSkip_(note, 'no comment text')); continue; }

    const m = /^([A-Z]+)(\d+)$/.exec(ref);
    if (!m) { skipped.push(icSkip_(note, 'cannot read "' + ref + '" as a cell reference')); continue; }

    const aCol = icColNum_(m[1]) - 1;
    const aRow = parseInt(m[2], 10);

    if (aCol >= aHead.length) { skipped.push(icSkip_(note, 'column ' + m[1] + ' is beyond the archive sheet')); continue; }

    // A comment on row 1 documents the COLUMN, not a mouse. Resolve it through
    // the activity block like any other cell: "Time" appears nineteen times, so
    // matching the bare header name would dump a note about Active avoidance's
    // Time onto Tail Snip #1's.
    if (aRow === 1) {
      const hWhat = icDescribe_(aHead, aCol);
      const tc = hWhat.activity ? icTargetCol_(tHead, hWhat.activity, hWhat.part) : -1;
      if (tc === -1) {
        skipped.push(icSkip_(note, 'header note on "' + (aHead[aCol] || '?') +
          '"' + (hWhat.activity ? ' (' + hWhat.activity + ')' : '') + ', which does not exist in 2.0'));
        continue;
      }
      icBucket_(buckets, 1, tc + 1, note, '(column header)',
                hWhat.activity + (hWhat.part === 'date' ? '' : ' / ' + hWhat.part));
      mapped++;
      continue;
    }

    const mouse = String((aIds[aRow - 2] || [''])[0] || '').trim();
    if (!mouse) { skipped.push(icSkip_(note, 'archive row ' + aRow + ' has no Mouse ID')); continue; }

    const tRow = rowOfMouse[mouse];
    if (!tRow) { skipped.push(icSkip_(note, 'mouse ' + mouse + ' is not in the 2.0 sheet')); continue; }

    const what = icDescribe_(aHead, aCol);
    if (!what.activity) { skipped.push(icSkip_(note, 'column ' + m[1] + ' has no header')); continue; }

    const tCol = icTargetCol_(tHead, what.activity, what.part);
    if (tCol === -1) {
      skipped.push(icSkip_(note, 'no "' + what.activity +
        (what.part === 'date' ? '' : ' / ' + what.part) + '" column in 2.0' +
        (what.part === 'Delayed?' ? ' — that column was removed by the migration' : '')));
      continue;
    }

    icBucket_(buckets, tRow, tCol + 1, note, mouse, what.activity + (what.part === 'date' ? '' : ' / ' + what.part));
    mapped++;
  }

  // Build one note per cell, oldest first, skipping anything already there.
  const notes = [];
  let duplicates = 0;
  let withExisting = 0;

  Object.keys(buckets).forEach(function (key) {
    const b = buckets[key];
    const existing = target.getRange(b.row, b.col).getNote() || '';
    if (existing.trim() !== '') withExisting++;

    b.items.sort(function (x, y) { return String(x.when).localeCompare(String(y.when)); });

    const fresh = [];
    b.items.forEach(function (it) {
      // Comparing on the text alone means a re-run cannot double up, even if
      // the author or date column was tidied between runs.
      if (existing.indexOf(it.text) !== -1) { duplicates++; return; }
      fresh.push(icFormat_(it));
    });

    if (fresh.length === 0) return;

    const merged = (existing.trim() === '')
      ? fresh.join(IC_SEPARATOR)
      : existing.replace(/\s+$/, '') + IC_SEPARATOR + fresh.join(IC_SEPARATOR);

    notes.push({ row: b.row, col: b.col, note: merged, mouse: b.mouse,
                 what: b.what, count: fresh.length, hadExisting: existing.trim() !== '' });
  });

  return { notes: notes, skipped: skipped, mapped: mapped,
           duplicates: duplicates, withExisting: withExisting };
}

function icBucket_(buckets, row, col, note, mouse, what) {
  const key = row + ':' + col;
  if (!buckets[key]) buckets[key] = { row: row, col: col, mouse: mouse, what: what, items: [] };
  buckets[key].items.push(note);
}

function icSkip_(note, why) {
  return { ref: note.ref, who: note.who, text: note.text, srcRow: note.row, why: why };
}

/** "Angelina Woychosky — 2026-07-28 [resolved]" then the text. */
function icFormat_(it) {
  const bits = [];
  if (it.who) bits.push(it.who);
  if (it.when) bits.push(it.when);
  let head = bits.join(' — ');
  if (it.resolved) head += (head ? ' ' : '') + '[resolved]';
  return head ? head + '\n' + it.text : it.text;
}

// =============================================================================
// COLUMN TRANSLATION
// =============================================================================

/** What a column in the OLD layout means: which activity, and which part of it. */
function icDescribe_(headers, c) {
  const h = headers[c];
  if (h === undefined || h === '') return { activity: '', part: '' };
  if (IC_QUALIFIERS.indexOf(h) === -1) return { activity: h, part: 'date' };

  // A qualifier belongs to the nearest activity header to its left.
  let k = c;
  while (k >= 0 && IC_QUALIFIERS.indexOf(headers[k]) !== -1) k--;
  return { activity: k >= 0 ? headers[k] : '', part: h };
}

/** Where that activity and part live in the NEW layout. */
function icTargetCol_(tHead, activity, part) {
  // v1's single recording column became (L) and (R); the data went into (L).
  const name = (IC_RECORDING_BASES.indexOf(activity) !== -1) ? activity + ' (L)' : activity;

  const start = tHead.indexOf(name);
  if (start === -1) return -1;
  if (part === 'date') return start;

  for (let k = start + 1; k < tHead.length && IC_QUALIFIERS.indexOf(tHead[k]) !== -1; k++) {
    if (tHead[k] === part) return k;
  }
  return -1;
}

function icColNum_(letters) {
  let n = 0;
  for (let i = 0; i < letters.length; i++) n = n * 26 + (letters.charCodeAt(i) - 64);
  return n;
}

function icColLetter_(n) {
  let s = '';
  while (n > 0) { const t = (n - 1) % 26; s = String.fromCharCode(65 + t) + s; n = (n - t - 1) / 26; }
  return s;
}

function icDateText_(v) {
  if (v instanceof Date && !isNaN(v.getTime())) {
    return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  }
  return String(v == null ? '' : v).trim();
}

// =============================================================================
// REPORT
// =============================================================================

function icWriteReport_(ss, plan, archiveName, targetName, applied) {
  let sheet = ss.getSheetByName(IC_REPORT_SHEET);
  if (!sheet) sheet = ss.insertSheet(IC_REPORT_SHEET);
  else sheet.clear();

  const header = ['Status', 'Mouse ID', 'Activity', 'Target cell', 'Comments', 'Note preview / reason'];
  const out = [header];
  const verb = applied ? '' : ' (NOT APPLIED)';

  plan.notes.forEach(function (n) {
    out.push([(n.hadExisting ? 'ADDED TO NOTE' : 'NOTE WRITTEN') + verb,
              n.mouse, n.what, icColLetter_(n.col) + n.row, n.count,
              n.note.replace(/\s+/g, ' ').slice(0, 220)]);
  });

  plan.skipped.forEach(function (s) {
    out.push(['NOT PLACED', '', '', s.ref, 1,
              s.why + '  —  ' + String(s.text).replace(/\s+/g, ' ').slice(0, 120)]);
  });

  if (out.length === 1) out.push(['NOTHING TO DO', '', '', '', 0, 'No comments to copy.']);

  sheet.getRange(1, 1, out.length, header.length).setValues(out);
  sheet.getRange(1, 1, 1, header.length).setFontWeight('bold').setBackground('#f0f0f0');
  sheet.setFrozenRows(1);

  const bands = {
    'NOTE WRITTEN':  { bg: '#e6f4ea', fc: '#137333' },
    'ADDED TO NOTE': { bg: '#fef7e0', fc: '#b06000' },
    'NOT PLACED':    { bg: '#fce8e6', fc: '#c5221f' },
    'NOTHING TO DO': { bg: '#f1f3f4', fc: '#5f6368' }
  };
  for (let i = 1; i < out.length; i++) {
    const band = bands[String(out[i][0]).replace(' (NOT APPLIED)', '')];
    if (band) sheet.getRange(i + 1, 1, 1, header.length).setBackground(band.bg).setFontColor(band.fc);
  }

  [170, 80, 190, 90, 80, 620].forEach(function (w, c) { sheet.setColumnWidth(c + 1, w); });
  sheet.getRange(1, 6, out.length, 1).setWrap(true);

  const stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  const foot = sheet.getRange(out.length + 2, 1);
  foot.setValue((applied ? 'Copied' : 'DRY RUN — nothing written') + ' from "' + archiveName +
    '" to "' + targetName + '" on ' + stamp + '  |  placed: ' + plan.mapped +
    ', cells: ' + plan.notes.length + ', already present: ' + plan.duplicates +
    ', not placed: ' + plan.skipped.length);
  foot.setFontWeight('bold');

  sheet.activate();
}
