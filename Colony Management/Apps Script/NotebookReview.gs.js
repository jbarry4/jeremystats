//NotebookReview.gs
/**
 * NOTEBOOK REVIEW — decide each disagreement by hand, one mouse at a time
 * =======================================================================
 * Lab_Notebook_import.gs imports what is safe on its own: it fills empty cells
 * and writes the session lists. Where the sheet and the notebook BOTH hold a
 * value and they differ, it refuses to choose and reports the clash.
 *
 * This is where you choose. It opens a dialog grouped by mouse, showing the two
 * values side by side, with three options per disagreement:
 *
 *   KEEP SHEET       leave the cell alone. Nothing is written.
 *   OVERRIDE         replace the cell with the notebook value.
 *   KEEP + COMMENT   leave the value alone and attach a note recording what the
 *                    notebook said, so the disagreement is visible in the sheet
 *                    without changing any data.
 *
 * Nothing is written until you press Apply, and every choice defaults to KEEP
 * SHEET — walking away changes nothing.
 *
 * The blank-cell fills and the session lists are applied at the same time,
 * since those are not in dispute. The dialog states how many there are.
 *
 * NOTES, NOT THREADED COMMENTS. "Keep + comment" writes a cell note. Apps
 * Script cannot create the threaded kind — see ImportComments.gs for the full
 * explanation.
 *
 * Run from Lab Tools > Review Notebook Conflicts.
 */

const NR_MARK = '[from lab notebook]';

// =============================================================================
// ENTRY POINT
// =============================================================================

function openNotebookReview() {
  const ui = SpreadsheetApp.getUi();
  let data;
  try {
    data = nrBuild_();
  } catch (err) {
    ui.alert('⚠️ Could not build the review', err.message, ui.ButtonSet.OK);
    return;
  }

  if (data.items.length === 0) {
    ui.alert('Nothing to review',
      'The sheet and the notebook do not disagree anywhere.\n\n' +
      data.autoFills + ' blank cell(s) and ' + data.autoSessions + ' session list(s) ' +
      'are still waiting to be written — run Lab Tools > Import Lab Notebook for those.',
      ui.ButtonSet.OK);
    return;
  }

  const html = HtmlService.createHtmlOutput(nrHtml_(data))
    .setWidth(900).setHeight(640);
  ui.showModalDialog(html, '📓 Notebook vs Sheet — ' + data.items.length + ' disagreement(s)');
}

/** Called by the dialog when it loads. */
function nrGetData() { return nrBuild_(); }

// =============================================================================
// BUILDING THE REVIEW
// =============================================================================

function nrBuild_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  const src = ss.getSheetByName(LN_INPUT_SHEET);
  if (!src) throw new Error('Could not find a sheet named "' + LN_INPUT_SHEET + '".');

  const target = getSyncSheet_();
  if (!target) throw new Error('Could not find "' + V2_SHEET_NAMES.join('" or "') + '".');

  const read = lnRead_(src);
  const groups = lnGroup_(read.sessions, read.problems);
  const plan = lnPlan_(target, groups, read.problems);

  // Every field where both sides hold a value and they differ.
  const items = plan.kept.map(function (k, i) {
    return {
      id: 'i' + i,
      mouse: k.mouse, row: k.row, col: k.col, column: k.column, field: k.field,
      sheet: k.sheet, notebook: k.notebook, srcRows: k.srcRows,
      isDate: !!k.isDate
    };
  });

  // Group by mouse for display, numerically.
  const byMouse = {};
  items.forEach(function (it) { (byMouse[it.mouse] = byMouse[it.mouse] || []).push(it); });
  const mice = Object.keys(byMouse).sort(function (a, b) { return parseInt(a, 10) - parseInt(b, 10); });

  return {
    items: items,
    mice: mice.map(function (m) { return { mouse: m, rows: byMouse[m] }; }),
    autoFills: plan.counts.filled,
    autoSessions: plan.writes.filter(function (w) { return w.field === 'Sessions'; }).length,
    sheetName: target.getName()
  };
}

// =============================================================================
// APPLYING
// =============================================================================

/**
 * @param choices  { id: 'keep' | 'override' | 'comment' }
 * @param alsoAuto whether to write the undisputed fills and session lists too
 */
function nrApply(choices, alsoAuto) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const target = getSyncSheet_();
  const src = ss.getSheetByName(LN_INPUT_SHEET);

  const read = lnRead_(src);
  const groups = lnGroup_(read.sessions, read.problems);
  const plan = lnPlan_(target, groups, read.problems);

  const done = { kept: 0, overridden: 0, commented: 0, filled: 0 };
  const log = [];

  // Rebuild the same ids nrBuild_ handed out, so a choice lands on the cell it
  // was made about even though this is a fresh pass over the data.
  plan.kept.forEach(function (k, i) {
    const action = choices['i' + i] || 'keep';
    const cell = target.getRange(k.row, k.col);

    if (action === 'override') {
      cell.setValue(k.value);
      if (k.isDate) cell.setNumberFormat(LN_DATE_FORMAT);
      done.overridden++;
      log.push(['OVERRIDDEN', k.mouse, k.row, k.column, k.field, k.sheet, k.notebook,
                'Replaced with the notebook value at your instruction.']);

    } else if (action === 'comment') {
      const existing = cell.getNote() || '';
      const line = NR_MARK + ' ' + k.field + ': ' + k.notebook +
                   '  (sheet says: ' + k.sheet + ')' +
                   (k.srcRows ? '  [notebook rows ' + k.srcRows + ']' : '');
      if (existing.indexOf(line) === -1) {
        cell.setNote(existing.trim() === '' ? line : existing.replace(/\s+$/, '') + '\n' + line);
      }
      done.commented++;
      log.push(['KEPT + COMMENTED', k.mouse, k.row, k.column, k.field, k.sheet, k.notebook,
                'Sheet value kept; the notebook value recorded as a note.']);

    } else {
      done.kept++;
      log.push(['KEPT SHEET', k.mouse, k.row, k.column, k.field, k.sheet, k.notebook,
                'Left as it was.']);
    }
  });

  if (alsoAuto) {
    plan.writes.forEach(function (w) {
      const cell = target.getRange(w.row, w.col);
      cell.setValue(w.value);
      if (w.isDate) cell.setNumberFormat(LN_DATE_FORMAT);
      done.filled++;
      log.push([w.action === 'FILLED' ? 'FILLED' : 'OVERWRITTEN', w.mouse, w.row, w.column,
                w.field, w.before, w.after, 'Undisputed — applied automatically.']);
    });
  }

  // The hemisphere-less sessions: a note on the recording, no value written.
  const unplaced = nrHemisphereNotes_(target, read);
  done.hemiNotes = unplaced.length;
  unplaced.forEach(function (u) {
    log.push(['NOTE ONLY', u.mouse, u.row, u.column, 'Hemisphere', '', '', u.note]);
  });

  SpreadsheetApp.flush();
  nrWriteLog_(ss, log, target.getName(), done);

  return done;
}

/**
 * Sessions the notebook could not place because the Hemisphere box was left
 * blank (marked red in the notebook). No value is invented — the recording gets
 * a note saying the side was never written down.
 */
function nrHemisphereNotes_(target, read) {
  const headers = target.getRange(1, 1, 1, target.getLastColumn()).getValues()[0]
                        .map(function (h) { return String(h).trim(); });
  const data = target.getDataRange().getValues();
  const idCol = headers.indexOf('Mouse ID');

  const rowOf = {};
  for (let r = 1; r < data.length; r++) {
    const id = String(data[r][idCol] || '').trim().replace(/\D/g, '');
    if (id && !(id in rowOf)) rowOf[id] = r + 1;
  }

  // Rows the reader threw out specifically for a missing hemisphere.
  const groupsOf = {};
  read.problems.forEach(function (p) {
    if (p.kind !== 'ROW SKIPPED' || !/hemisphere/i.test(p.note)) return;
    const id = String(p.id || '').replace(/\D/g, '');
    if (!id) return;
    (groupsOf[id] = groupsOf[id] || []).push(p);
  });

  const out = [];
  Object.keys(groupsOf).forEach(function (mouse) {
    const row = rowOf[mouse];
    if (!row) return;

    // Attach to the modality's LEFT column purely as a place to hang the note;
    // the text says the side is unknown, so nothing is being asserted.
    const probs = groupsOf[mouse];
    const col = headers.indexOf('H10 probe (L)') !== -1 ? headers.indexOf('H10 probe (L)') : -1;
    if (col === -1) return;

    const note = 'Hemisphere not recorded in the lab notebook for ' + probs.length +
                 ' session(s) — the notebook cell was blank (flagged red). ' +
                 'Left or right is unknown, so these were not placed:\n' +
                 probs.map(function (p) { return '  • ' + p.note; }).join('\n');

    const cell = target.getRange(row, col + 1);
    const existing = cell.getNote() || '';
    if (existing.indexOf('Hemisphere not recorded') === -1) {
      cell.setNote(existing.trim() === '' ? note : existing.replace(/\s+$/, '') + '\n\n' + note);
    }
    out.push({ mouse: mouse, row: row, column: headers[col], note: note.split('\n')[0] });
  });

  return out;
}

function nrWriteLog_(ss, log, targetName, done) {
  let sheet = ss.getSheetByName('Notebook Review Log');
  if (!sheet) sheet = ss.insertSheet('Notebook Review Log');
  else sheet.clear();

  const header = ['Decision', 'Mouse ID', 'Sheet row', 'Block', 'Field',
                  'Sheet value', 'Notebook value', 'Note'];
  const out = [header].concat(log.length ? log : [['NOTHING', '', '', '', '', '', '', 'No decisions applied.']]);

  sheet.getRange(1, 1, out.length, header.length).setValues(out);
  sheet.getRange(1, 1, 1, header.length).setFontWeight('bold').setBackground('#f0f0f0');
  sheet.setFrozenRows(1);

  const bands = {
    'OVERRIDDEN':       { bg: '#fef7e0', fc: '#b06000' },
    'KEPT + COMMENTED': { bg: '#e8f0fe', fc: '#1967d2' },
    'KEPT SHEET':       { bg: '#f1f3f4', fc: '#5f6368' },
    'FILLED':           { bg: '#e6f4ea', fc: '#137333' },
    'OVERWRITTEN':      { bg: '#fef7e0', fc: '#b06000' },
    'NOTE ONLY':        { bg: '#fff3e0', fc: '#8a5300' }
  };
  for (let i = 1; i < out.length; i++) {
    const b = bands[out[i][0]];
    if (b) sheet.getRange(i + 1, 1, 1, header.length).setBackground(b.bg).setFontColor(b.fc);
  }
  [150, 80, 70, 140, 70, 200, 200, 380].forEach(function (w, c) { sheet.setColumnWidth(c + 1, w); });
  sheet.getRange(1, 8, out.length, 1).setWrap(true);

  const stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  const foot = sheet.getRange(out.length + 2, 1);
  foot.setValue('Reviewed into "' + targetName + '" on ' + stamp +
    '  |  kept: ' + done.kept + ', overridden: ' + done.overridden +
    ', commented: ' + done.commented + ', auto-applied: ' + done.filled +
    ', hemisphere notes: ' + (done.hemiNotes || 0));
  foot.setFontWeight('bold');
}

// =============================================================================
// THE DIALOG
// =============================================================================

function nrHtml_(data) {
  const json = JSON.stringify(data).replace(/<\//g, '<\\/');

  return `
<style>
  body { font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 0; color: #202124; font-size: 13px; }
  .bar { position: sticky; top: 0; background: #fff; border-bottom: 1px solid #dadce0; padding: 12px 16px; z-index: 5; }
  .bar h2 { margin: 0 0 4px 0; font-size: 16px; }
  .sub { color: #5f6368; font-size: 12px; }
  .wrap { padding: 8px 16px 90px 16px; }
  .mouse { border: 1px solid #dadce0; border-radius: 6px; margin: 12px 0; overflow: hidden; }
  .mouse h3 { margin: 0; padding: 8px 12px; background: #f1f3f4; font-size: 14px; }
  table { border-collapse: collapse; width: 100%; }
  th { text-align: left; font-size: 11px; color: #5f6368; padding: 6px 10px; border-bottom: 1px solid #e8eaed; font-weight: 600; }
  td { padding: 8px 10px; border-bottom: 1px solid #f1f3f4; vertical-align: middle; }
  .blk { font-weight: 600; }
  .fld { color: #5f6368; font-size: 12px; }
  .old { color: #202124; }
  .new { color: #1967d2; }
  .opts { white-space: nowrap; }
  .opts label { margin-right: 10px; cursor: pointer; font-size: 12px; padding: 3px 6px; border-radius: 4px; }
  .opts label:hover { background: #f1f3f4; }
  .foot { position: fixed; bottom: 0; left: 0; right: 0; background: #fff; border-top: 1px solid #dadce0; padding: 10px 16px; display: flex; gap: 10px; align-items: center; }
  button { padding: 9px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 13px; }
  #apply { background: #1a73e8; color: #fff; }
  #apply:disabled { background: #b0c8ec; cursor: default; }
  .quick { background: #f1f3f4; color: #202124; font-weight: normal; }
  .count { margin-left: auto; color: #5f6368; font-size: 12px; }
  .chk { font-size: 12px; color: #202124; }
</style>

<div class="bar">
  <h2>Notebook vs Sheet</h2>
  <div class="sub" id="sub"></div>
</div>

<div class="wrap"><div id="list"></div></div>

<div class="foot">
  <button class="quick" onclick="setAll('keep')">All: keep sheet</button>
  <button class="quick" onclick="setAll('override')">All: override</button>
  <button class="quick" onclick="setAll('comment')">All: keep + comment</button>
  <label class="chk"><input type="checkbox" id="auto" checked> also write the undisputed blanks &amp; sessions</label>
  <span class="count" id="count"></span>
  <button id="apply" onclick="apply()">Apply</button>
</div>

<script>
  var DATA = ${json};

  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function render() {
    document.getElementById('sub').innerHTML =
      esc(DATA.items.length) + ' disagreement(s) across ' + esc(DATA.mice.length) +
      ' mice in <b>' + esc(DATA.sheetName) + '</b>. ' +
      'Every one defaults to <b>keep sheet</b> — nothing changes unless you say so.';

    var html = '';
    DATA.mice.forEach(function (m) {
      html += '<div class="mouse"><h3>Mouse ' + esc(m.mouse) + '</h3><table>' +
        '<tr><th style="width:150px">Block</th><th style="width:60px">Field</th>' +
        '<th>Sheet has</th><th>Notebook says</th><th style="width:330px">Decision</th></tr>';
      m.rows.forEach(function (r) {
        html += '<tr>' +
          '<td class="blk">' + esc(r.column) + '</td>' +
          '<td class="fld">' + esc(r.field) + '</td>' +
          '<td class="old">' + esc(r.sheet) + '</td>' +
          '<td class="new">' + esc(r.notebook) + '</td>' +
          '<td class="opts">' +
            radio(r.id, 'keep', 'Keep sheet', true) +
            radio(r.id, 'override', 'Override', false) +
            radio(r.id, 'comment', 'Keep + comment', false) +
          '</td></tr>';
      });
      html += '</table></div>';
    });
    document.getElementById('list').innerHTML = html;
    tally();
  }

  function radio(id, val, label, checked) {
    return '<label><input type="radio" name="' + id + '" value="' + val + '"' +
           (checked ? ' checked' : '') + ' onchange="tally()"> ' + label + '</label>';
  }

  function choices() {
    var out = {};
    DATA.items.forEach(function (r) {
      var el = document.querySelector('input[name="' + r.id + '"]:checked');
      out[r.id] = el ? el.value : 'keep';
    });
    return out;
  }

  function setAll(v) {
    DATA.items.forEach(function (r) {
      var el = document.querySelector('input[name="' + r.id + '"][value="' + v + '"]');
      if (el) el.checked = true;
    });
    tally();
  }

  function tally() {
    var c = choices(), k = 0, o = 0, m = 0;
    Object.keys(c).forEach(function (id) {
      if (c[id] === 'override') o++; else if (c[id] === 'comment') m++; else k++;
    });
    document.getElementById('count').innerText =
      'keep ' + k + '   ·   override ' + o + '   ·   comment ' + m;
  }

  function apply() {
    var btn = document.getElementById('apply');
    btn.disabled = true;
    btn.innerText = 'Applying…';
    google.script.run
      .withSuccessHandler(function () { google.script.host.close(); })
      .withFailureHandler(function (e) {
        alert('Failed: ' + e.message);
        btn.disabled = false;
        btn.innerText = 'Apply';
      })
      .nrApply(choices(), document.getElementById('auto').checked);
  }

  render();
</script>
`;
}
