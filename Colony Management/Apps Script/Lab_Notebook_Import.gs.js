//Lab_Notebook_import.gs
/**
 * LAB NOTEBOOK IMPORT — "Lab Notebook Import" -> "KCNT1 Active 2.0"
 * =================================================================
 * The Feb–Jun 2026 hardcopy notebooks, transcribed and cleaned, written into
 * the recording blocks of the master sheet.
 *
 * ---------------------------------------------------------------------------
 * THIS ONE DOES NOT BLINDLY OVERWRITE, AND THAT IS DELIBERATE
 *
 * The recording-binder import could overwrite freely because it was strictly
 * better than what was in the sheet. This source is not. Checked against the
 * live sheet, a blanket overwrite would have done real damage:
 *
 *   306 H10 probe (L)   live "3:00 PM - 5:00 PM", Jeremy   notebook "4:28", no lead
 *   526 H3 probe (L)    live "1:00 PM - 6:00 PM", Mohsen & Jeremy
 *                                                         notebook "2:40 - 3:11", no lead
 *   524 H3 probe (L)    live 4/30, Shahriar, Mohsen, Jeremy
 *                                                         notebook 4/28, no lead
 *
 * The notebook's Initials column is blank on roughly 40% of rows and most of
 * its times are a bare start with no am/pm, so overwriting would trade good
 * data for worse. What it uniquely CONTRIBUTES is the session numbering — the
 * live sheet has almost none for these mice — plus nine blocks that do not
 * exist there at all.
 *
 * So the default policy is:
 *
 *   Sessions   OVERWRITE. The notebook is the session record; that is the
 *              whole point of transcribing it.
 *   Date       FILL BLANKS ONLY. A disagreement is reported, never applied —
 *              see 521, where the sheet says 7/31 and the notebook says 5/5.
 *              Those are probably a scheduled recording and a real one.
 *   Time       FILL BLANKS ONLY. Never replace a full range with a bare start.
 *   Lead       FILL BLANKS ONLY.
 *
 * And underneath all of it, one rule that no policy can override: a blank is
 * never written over a value. Change LN_POLICY below if you disagree, but read
 * the conflict report first.
 *
 * ---------------------------------------------------------------------------
 * INPUT — a sheet named "Lab Notebook Import", from Lab_Notebook_import.csv.
 * Columns, by header name (extra columns ignored):
 *
 *     mouse       cleaned Mouse ID                    (required)
 *     modality    H3 probe | H10 probe | H10 opto     (required)
 *     hemi        L | R                               (required)
 *     session     lowercase s##                       (required)
 *     date                                            (required)
 *     lead                                            (optional)
 *     time        already-formatted Time text         (optional)
 *
 * Rows sharing (mouse, modality, hemisphere) collapse into one activity block,
 * sessions joined in numeric order and de-duplicated — the notebook repeats a
 * session number where a recording continued onto the next page.
 *
 * Run from Lab Tools > Import Lab Notebook, or from the editor.
 */

// =============================================================================
// CONFIG
// =============================================================================

const LN_INPUT_SHEET  = 'Lab Notebook Import';
const LN_REPORT_SHEET = 'Lab Notebook Report';

/** 'fill' = only into an empty cell.  'overwrite' = replace what is there. */
const LN_POLICY = {
  date:     'fill',
  time:     'fill',
  lead:     'fill',
  sessions: 'overwrite'
};

const LN_MODALITIES = ['H3 probe', 'H10 probe', 'H10 opto'];
const LN_QUALIFIERS = ['Time', 'Lead', 'Sessions', 'Delayed?', 'Double Inj?'];
const LN_DATE_FORMAT = 'M/d/yyyy';

// =============================================================================
// ENTRY POINT
// =============================================================================

function importLabNotebook() {
  const ui = SpreadsheetApp.getUi();

  try {
    Logger.log('--- LAB NOTEBOOK IMPORT START ---');
    const ss = SpreadsheetApp.getActiveSpreadsheet();

    const src = ss.getSheetByName(LN_INPUT_SHEET);
    if (!src) {
      throw new Error('Could not find a sheet named "' + LN_INPUT_SHEET + '".\n\n' +
        'Import Lab_Notebook_import.csv as a tab with that name.\n\nSheets here:\n' +
        ss.getSheets().map(function (s) { return '  • ' + s.getName(); }).join('\n'));
    }

    const target = getSyncSheet_();
    if (!target) throw new Error('Could not find "' + V2_SHEET_NAMES.join('" or "') + '".');

    const read = lnRead_(src);
    Logger.log('Sessions read: ' + read.sessions.length);

    const groups = lnGroup_(read.sessions, read.problems);
    Logger.log('Target blocks: ' + groups.length);

    const plan = lnPlan_(target, groups, read.problems);

    if (plan.writes.length === 0) {
      lnReport_(ss, plan, read, target.getName(), false);
      ui.alert('Lab Notebook Import', 'Nothing to write — every targeted cell already ' +
        'holds a value and the policy is fill-blanks-only.\n\nSee "' + LN_REPORT_SHEET +
        '" for the ' + plan.conflicts.length + ' disagreement(s) found.', ui.ButtonSet.OK);
      return;
    }

    const confirm = ui.alert('Import ' + groups.length + ' notebook block(s)?',
      'Target: ' + target.getName() + '\n\n' +
      'Cells to fill (currently blank): ' + plan.counts.filled + '\n' +
      'Cells to overwrite:              ' + plan.counts.overwritten + '\n' +
      'Left alone (fill-only policy):   ' + plan.counts.kept + '\n' +
      'Already correct:                 ' + plan.counts.same + '\n' +
      'Blocks not matched:              ' + plan.blocked.length + '\n\n' +
      'DISAGREEMENTS FOUND: ' + plan.conflicts.length + '\n' +
      'Those are reported, not applied — the sheet keeps what it has.\n\n' +
      'Policy: sessions=' + LN_POLICY.sessions + ', date=' + LN_POLICY.date +
      ', time=' + LN_POLICY.time + ', lead=' + LN_POLICY.lead + '\n\nProceed?',
      ui.ButtonSet.YES_NO);

    if (confirm !== ui.Button.YES) {
      lnReport_(ss, plan, read, target.getName(), false);
      ui.alert('Cancelled', 'Nothing written. The report shows what would have changed.',
        ui.ButtonSet.OK);
      return;
    }

    plan.writes.forEach(function (w) {
      const cell = target.getRange(w.row, w.col);
      cell.setValue(w.value);
      if (w.isDate) cell.setNumberFormat(LN_DATE_FORMAT);
    });
    SpreadsheetApp.flush();

    lnReport_(ss, plan, read, target.getName(), true);

    const summary =
      'Target: ' + target.getName() + '\n\n' +
      'Blocks imported:        ' + plan.counts.blocks + '\n' +
      'Cells filled:           ' + plan.counts.filled + '\n' +
      'Cells overwritten:      ' + plan.counts.overwritten + '\n' +
      'Left alone by policy:   ' + plan.counts.kept + '\n' +
      'Disagreements reported: ' + plan.conflicts.length + '\n' +
      'Blocks not matched:     ' + plan.blocked.length + '\n' +
      'Notes / warnings:       ' + read.problems.length + '\n\n' +
      'Detail in the "' + LN_REPORT_SHEET + '" tab.';

    Logger.log(summary);
    Logger.log('--- LAB NOTEBOOK IMPORT COMPLETE ---');
    ui.alert('Lab Notebook Imported', summary, ui.ButtonSet.OK);

  } catch (err) {
    Logger.log('ERROR: ' + err.message + '\n' + err.stack);
    ui.alert('⚠️ Import Failed', err.message +
      '\n\n(Check the Apps Script Execution Log for details)', ui.ButtonSet.OK);
  }
}

// =============================================================================
// READING
// =============================================================================

function lnRead_(src) {
  const data = src.getDataRange().getValues();
  const problems = [];
  if (data.length < 2) return { sessions: [], problems: problems };

  const lower = data[0].map(function (h) { return String(h).trim().toLowerCase(); });
  const col = function (n) { return lower.indexOf(n); };

  const c = { date: col('date'), mouse: col('mouse'), sess: col('session'),
              lead: col('lead'), hemi: col('hemi'), mod: col('modality'),
              time: col('time'), sid: col('session id') };

  const missing = ['date', 'mouse', 'sess', 'hemi', 'mod'].filter(function (k) { return c[k] === -1; });
  if (missing.length) {
    throw new Error('"' + LN_INPUT_SHEET + '" is missing column(s): ' +
      missing.join(', ') + '.\nFound: ' + data[0].filter(String).join(', '));
  }

  const sessions = [];
  for (let r = 1; r < data.length; r++) {
    const row = data[r];
    const mouse = String(row[c.mouse] || '').trim().replace(/\D/g, '');
    const modality = String(row[c.mod] || '').trim();
    const hemi = String(row[c.hemi] || '').trim().toUpperCase();
    const sess = String(row[c.sess] || '').trim().toLowerCase();
    const date = row[c.date];
    const sid = c.sid === -1 ? '' : String(row[c.sid] || '').trim();

    if (!mouse && !modality && !sess) continue;

    const why = [];
    if (!mouse) why.push('no mouse');
    if (LN_MODALITIES.indexOf(modality) === -1) why.push('modality "' + modality + '" not recognised');
    if (hemi !== 'L' && hemi !== 'R') why.push('hemisphere "' + hemi + '" is not L or R');
    if (!sess) why.push('no session');
    if (!(date instanceof Date)) why.push('date is not a real date');

    if (why.length) {
      problems.push({ kind: 'ROW SKIPPED', id: mouse, row: r + 1,
        note: 'Row ' + (r + 1) + (sid ? ' (' + sid + ')' : '') + ' skipped: ' + why.join('; ') });
      continue;
    }

    const time = c.time === -1 ? '' : lnTimeText_(row[c.time]);
    if (time && !/[ap]m/i.test(time)) {
      problems.push({ kind: 'TIME WITHOUT AM/PM', id: mouse, row: r + 1,
        note: 'Row ' + (r + 1) + ' (' + mouse + ' ' + sess + '): "' + time +
              '" has no am/pm. Only written into an empty cell; the calendar sync reads it as AM.' });
    }

    sessions.push({ row: r + 1, sid: sid, mouse: mouse, modality: modality, hemi: hemi,
                    sess: sess, date: date, time: time,
                    lead: c.lead === -1 ? '' : String(row[c.lead] || '').trim() });
  }

  return { sessions: sessions, problems: problems };
}

function lnTimeText_(v) {
  if (v === null || v === undefined || v === '') return '';
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'h:mm a');
  return String(v).trim();
}

// =============================================================================
// GROUPING
// =============================================================================

function lnSessionNum_(s) {
  const m = /^s(\d+)([a-z]?)$/.exec(String(s));
  return m ? parseInt(m[1], 10) * 10 + (m[2] ? m[2].charCodeAt(0) - 96 : 0) : 1e9;
}

function lnGroup_(sessions, problems) {
  const map = {};
  sessions.forEach(function (s) {
    const key = s.mouse + '||' + s.modality + '||' + s.hemi;
    if (!map[key]) map[key] = { mouse: s.mouse, column: s.modality + ' (' + s.hemi + ')', rows: [] };
    map[key].rows.push(s);
  });

  return Object.keys(map).map(function (k) {
    const g = map[k];
    g.rows.sort(function (a, b) { return lnSessionNum_(a) - lnSessionNum_(b) || a.row - b.row; });

    const days = [];
    g.rows.forEach(function (s) {
      const d = lnDayKey_(s.date);
      if (days.indexOf(d) === -1) days.push(d);
    });
    days.sort();
    if (days.length > 1) {
      problems.push({ kind: 'MULTI-DAY BLOCK', id: g.mouse, row: g.rows[0].row,
        note: g.mouse + ' ' + g.column + ' spans ' + days.join(', ') +
              '. One cell holds one date, so the earliest was used.' });
    }

    let earliest = g.rows[0].date;
    g.rows.forEach(function (s) { if (s.date < earliest) earliest = s.date; });

    let time = '';
    for (let i = 0; i < g.rows.length && time === ''; i++) time = g.rows[i].time;

    const leads = [];
    g.rows.forEach(function (s) {
      s.lead.split(',').forEach(function (p) {
        const v = p.trim();
        if (v && leads.indexOf(v) === -1) leads.push(v);
      });
    });

    // A session number repeats where a recording ran onto the next notebook
    // page. One cell, one mention.
    const seen = [];
    g.rows.forEach(function (s) { if (seen.indexOf(s.sess) === -1) seen.push(s.sess); });

    return { mouse: g.mouse, column: g.column, date: earliest, time: time,
             lead: leads.join(', '), sessions: seen.join(', '),
             srcRows: g.rows.map(function (s) { return s.row; }).join(' ') };
  }).sort(function (a, b) {
    return (parseInt(a.mouse, 10) - parseInt(b.mouse, 10)) || a.column.localeCompare(b.column);
  });
}

function lnDayKey_(d) {
  return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
}

// =============================================================================
// PLANNING
// =============================================================================

function lnPlan_(target, groups, problems) {
  const headers = target.getRange(1, 1, 1, target.getLastColumn()).getValues()[0]
                        .map(function (h) { return String(h).trim(); });
  const data = target.getDataRange().getValues();

  const idCol = headers.indexOf('Mouse ID');
  if (idCol === -1) throw new Error('No "Mouse ID" column in "' + target.getName() + '".');

  // Exact match first — "302 (breeder)" and "302" are different animals.
  const exact = {}, byDigits = {};
  for (let r = 1; r < data.length; r++) {
    const id = String(data[r][idCol] || '').trim();
    if (!id) continue;
    if (!(id in exact)) exact[id] = r + 1;
    const dg = id.replace(/\D/g, '');
    if (dg) (byDigits[dg] = byDigits[dg] || []).push({ row: r + 1, id: id });
  }
  const lookup = function (m) {
    if (m in exact) return { row: exact[m], how: 'exact' };
    const hits = byDigits[m] || [];
    if (hits.length === 1) return { row: hits[0].row, how: 'digits', matched: hits[0].id };
    if (hits.length > 1) return { row: null, how: 'ambiguous', hits: hits };
    return { row: null, how: 'none' };
  };

  const writes = [], blocked = [], conflicts = [], kept = [];
  const counts = { blocks: 0, filled: 0, overwritten: 0, kept: 0, same: 0 };
  const tz = Session.getScriptTimeZone();

  groups.forEach(function (g) {
    const hit = lookup(g.mouse);
    if (hit.how === 'ambiguous') {
      blocked.push({ mouse: g.mouse, column: g.column, why: 'matches ' + hit.hits.length +
        ' rows (' + hit.hits.map(function (h) { return '"' + h.id + '"'; }).join(', ') + ') — refusing to guess' });
      return;
    }
    if (!hit.row) {
      blocked.push({ mouse: g.mouse, column: g.column,
        why: 'mouse ' + g.mouse + ' is not in "' + target.getName() + '"' });
      return;
    }

    const dateCol = headers.indexOf(g.column);
    if (dateCol === -1) {
      blocked.push({ mouse: g.mouse, column: g.column, why: 'no such column in the target sheet' });
      return;
    }

    const blk = lnBlock_(headers, dateCol);
    counts.blocks++;
    const row = data[hit.row - 1];

    const consider = function (col, field, value, policy) {
      if (col === -1) return;
      const beforeTxt = lnText_(row[col], tz);
      const afterTxt = lnText_(value, tz);

      if (afterTxt === '') return;                       // never write a blank
      if (beforeTxt === afterTxt) { counts.same++; return; }

      if (beforeTxt === '') {
        counts.filled++;
        writes.push({ mouse: g.mouse, row: hit.row, col: col + 1, column: g.column,
                      field: field, before: '(blank)', after: afterTxt, value: value,
                      action: 'FILLED', isDate: field === 'date', srcRows: g.srcRows });
        return;
      }

      // Cell already holds something different.
      if (policy === 'overwrite') {
        counts.overwritten++;
        writes.push({ mouse: g.mouse, row: hit.row, col: col + 1, column: g.column,
                      field: field, before: beforeTxt, after: afterTxt, value: value,
                      action: 'OVERWRITTEN', isDate: field === 'date', srcRows: g.srcRows });
      } else {
        counts.kept++;
        // col/value are carried so the review dialog can act on the decision
        // later without having to redo any of this matching.
        const item = { mouse: g.mouse, row: hit.row, col: col + 1, column: g.column,
                       field: field, sheet: beforeTxt, notebook: afterTxt,
                       value: value, isDate: field === 'date', srcRows: g.srcRows };
        kept.push(item);
        // A date or time disagreement is worth surfacing on its own.
        if (field === 'date' || field === 'Time') conflicts.push(item);
      }
    };

    consider(dateCol,      'date',     g.date,     LN_POLICY.date);
    consider(blk.time,     'Time',     g.time,     LN_POLICY.time);
    consider(blk.lead,     'Lead',     g.lead,     LN_POLICY.lead);
    consider(blk.sessions, 'Sessions', g.sessions, LN_POLICY.sessions);
  });

  return { writes: writes, blocked: blocked, conflicts: conflicts, kept: kept, counts: counts };
}

function lnBlock_(headers, dateCol) {
  const out = { time: -1, lead: -1, sessions: -1 };
  let k = dateCol + 1;
  while (k < headers.length && LN_QUALIFIERS.indexOf(headers[k]) !== -1) {
    if (headers[k] === 'Time' && out.time === -1) out.time = k;
    if (headers[k] === 'Lead' && out.lead === -1) out.lead = k;
    if (headers[k] === 'Sessions' && out.sessions === -1) out.sessions = k;
    k++;
  }
  return out;
}

function lnText_(v, tz) {
  if (v === null || v === undefined) return '';
  if (v instanceof Date) return isNaN(v.getTime()) ? '' : Utilities.formatDate(v, tz, 'MM/dd/yyyy');
  return String(v).trim().replace(/\s+/g, ' ');
}

// =============================================================================
// REPORT
// =============================================================================

function lnReport_(ss, plan, read, targetName, applied) {
  let sheet = ss.getSheetByName(LN_REPORT_SHEET);
  if (!sheet) sheet = ss.insertSheet(LN_REPORT_SHEET);
  else sheet.clear();

  const header = ['Status', 'Mouse ID', 'Sheet row', 'Block', 'Field',
                  'Sheet had', 'Notebook says', 'Notebook rows', 'Note'];
  const out = [header];
  const verb = applied ? '' : ' (NOT APPLIED)';

  // Disagreements first — the only rows that need a human.
  plan.conflicts.forEach(function (c) {
    out.push(['DISAGREEMENT', c.mouse, c.row, c.column, c.field, c.sheet, c.notebook, c.srcRows,
      'Both sources have a value and they differ. The sheet was left as it is. ' +
      'Decide which is right; if the notebook wins, change it by hand.']);
  });

  plan.writes.filter(function (w) { return w.action === 'OVERWRITTEN'; }).forEach(function (w) {
    out.push(['OVERWRITTEN' + verb, w.mouse, w.row, w.column, w.field, w.before, w.after, w.srcRows,
      'Replaced under the "' + LN_POLICY[w.field === 'date' ? 'date' : w.field.toLowerCase()] + '" policy.']);
  });

  plan.writes.filter(function (w) { return w.action === 'FILLED'; }).forEach(function (w) {
    out.push(['FILLED' + verb, w.mouse, w.row, w.column, w.field, '(blank)', w.after, w.srcRows,
      'Cell was empty.']);
  });

  plan.kept.filter(function (k) { return k.field !== 'date' && k.field !== 'Time'; })
    .forEach(function (k) {
      out.push(['KEPT SHEET VALUE', k.mouse, k.row, k.column, k.field, k.sheet, k.notebook, k.srcRows,
        'Policy for ' + k.field + ' is fill-blanks-only, so the sheet value stands.']);
    });

  plan.blocked.forEach(function (b) {
    out.push(['NOT IMPORTED', b.mouse, '', b.column, '', '', '', '', b.why]);
  });

  read.problems.forEach(function (p) {
    out.push([p.kind, p.id || '', p.row || '', '', '', '', '', '', p.note]);
  });

  if (out.length === 1) out.push(['NOTHING TO DO', '', '', '', '', '', '', '', 'No changes needed.']);

  sheet.getRange(1, 1, out.length, header.length).setValues(out);
  sheet.getRange(1, 1, 1, header.length).setFontWeight('bold').setBackground('#f0f0f0');
  sheet.setFrozenRows(1);

  const bands = {
    'DISAGREEMENT':     { bg: '#f4c7c3', fc: '#a50e0e' },
    'OVERWRITTEN':      { bg: '#fef7e0', fc: '#b06000' },
    'FILLED':           { bg: '#e6f4ea', fc: '#137333' },
    'KEPT SHEET VALUE': { bg: '#f1f3f4', fc: '#5f6368' },
    'NOT IMPORTED':     { bg: '#fce8e6', fc: '#c5221f' },
    'ROW SKIPPED':      { bg: '#fce8e6', fc: '#c5221f' },
    'MULTI-DAY BLOCK':  { bg: '#fff3e0', fc: '#8a5300' },
    'TIME WITHOUT AM/PM': { bg: '#fff3e0', fc: '#8a5300' },
    'NOTHING TO DO':    { bg: '#f1f3f4', fc: '#5f6368' }
  };
  for (let i = 1; i < out.length; i++) {
    const band = bands[String(out[i][0]).replace(' (NOT APPLIED)', '')];
    if (band) sheet.getRange(i + 1, 1, 1, header.length).setBackground(band.bg).setFontColor(band.fc);
  }

  [150, 80, 70, 140, 70, 190, 190, 100, 400].forEach(function (w, c) { sheet.setColumnWidth(c + 1, w); });
  sheet.getRange(1, 9, out.length, 1).setWrap(true);

  const stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  const foot = sheet.getRange(out.length + 2, 1);
  foot.setValue((applied ? 'Imported' : 'DRY RUN — nothing written') + ' into "' + targetName +
    '" on ' + stamp + '  |  filled: ' + plan.counts.filled +
    ', overwritten: ' + plan.counts.overwritten + ', kept: ' + plan.counts.kept +
    ', disagreements: ' + plan.conflicts.length + ', not matched: ' + plan.blocked.length);
  foot.setFontWeight('bold');

  sheet.activate();
}
