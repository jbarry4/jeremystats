/**
 * AuditFixes_112326.js -- the Lab Ops fixes from the KCNT1 active-avoidance
 * audit (KCNT1_AA_mouse_map_112326_v3.xlsx, 2026-11-23).
 *
 * RUN previewAuditFixes112326 FIRST. It changes nothing and lists, in the
 * execution log, every cell it would change and every one it would leave.
 * Then applyAuditFixes112326 makes the changes and writes the same list to a
 * tab called "Audit fixes 112326".
 *
 * Safe by construction:
 *   - Only the "KCNT1 Active 2.0" tab is touched.
 *   - A cell is changed only if it still holds the value the audit found
 *     there. Anything somebody has already corrected, or changed to something
 *     else, is left alone and listed as such.
 *   - Every changed cell gets a note with its old value and what settled the
 *     new one, so any of them can be put back by hand.
 *   - A script's own edits do not fire the calendar's on-edit trigger, so no
 *     calendar event is created or removed by this.
 *
 * Left out on purpose:
 *   - 477's sex: still an open conflict (Lab Ops 2.0 says M, the original
 *     Archive record says F, nothing else exists). The perfusion record or the
 *     Oct 2024 notebook should settle it first.
 *   - The old "KCNT1 Active (Archived)" tab: kept as it was, as the record of
 *     what the tab held.
 */

const AUDIT112326 = {
  tab: 'KCNT1 Active 2.0',
  source: 'KCNT1 AA audit v3 (2026-11-23)',
  // [mouse, Lab Ops 2.0 says, set to, settled by, confidence]
  sex: [
    [292, 'M', 'F', 'Lab Ops KCNT1 Archive (original record)', 'Medium'],
    [301, 'M', 'F', 'VOS cage card CC-21436-5', 'High'],
    [306, 'F', 'M', 'VOS cage card CC-26315-1', 'High'],
    [314, 'M', 'F', 'VOS cage card CC-22038-3', 'High'],
    [318, 'F', 'M', 'VOS cage card CC-27875-1', 'High'],
    [320, 'M', 'F', 'VOS cage card CC-25084-2', 'High'],
    [323, 'F', 'M', 'VOS cage card CC-22537-1', 'High'],
    [402, 'M', 'F', 'SoftMouse', 'High'],
    [414, 'M', 'F', 'VOS cage card CC-8069-6', 'High'],
    [416, 'F', 'M', 'VOS cage card CC-11563-1', 'High'],
    [439, 'M', 'F', 'VOS cage card CC-17573-6', 'High'],
    [445, 'M', 'F', 'VOS cage card CC-17573-6', 'High'],
    [448, 'F', 'M', 'VOS cage card CC-12583-4', 'High'],
    [449, 'F', 'M', 'SoftMouse', 'High'],
    [464, 'F', 'M', 'VOS cage card CC-11617-4', 'High'],
    [470, 'M', 'F', 'SoftMouse', 'High'],
    [471, 'M', 'F', 'VOS cage card CC-22858-1', 'High'],
    [474, 'M', 'F', 'VOS cage card CC-23613-1', 'High'],
    [475, 'M', 'F', 'VOS cage card CC-12302-7', 'High'],
    [479, 'M', 'F', 'VOS cage card CC-13107-2', 'High'],
    [482, 'F', 'M', 'VOS cage card CC-22256-1', 'High'],
    [483, 'F', 'M', 'VOS cage card CC-13109-2', 'High'],
    [486, 'M', 'F', 'VOS cage card CC-22376-3', 'High'],
    [499, 'F', 'M', 'VOS cage card CC-17572-6', 'High'],
    [500, 'M', 'F', 'Lab Ops KCNT1 Archive (original record)', 'Medium'],
    [503, 'M', 'F', 'VOS cage card CC-21024-1', 'High'],
    [505, 'M', 'F', 'VOS cage card CC-21026-1', 'High'],
    [507, 'F', 'M', 'VOS cage card CC-21024-1', 'High'],
    [508, 'F', 'M', 'VOS cage card CC-21026-1', 'High'],
    [526, 'F', 'M', 'VOS cage card CC-23547-1', 'High'],
    [527, 'M', 'F', 'VOS cage card CC-27242-1', 'High'],
    [532, 'F', 'M', 'VOS cage card CC-25086-2', 'High'],
    [552, 'F', 'M', 'Lab Ops KCNT1 Archive (original record)', 'Medium'],
    [557, 'M', 'F', 'VOS census', 'High'],
    [814, 'F', 'M', 'VOS cage card CC-13952-1', 'High'],
    [828, 'M', 'F', 'SoftMouse', 'High'],
    [834, 'F', 'M', 'SoftMouse', 'High'],
    [879, 'F', 'M', 'Lab Ops KCNT1 Archive (original record)', 'Medium'],
    [892, 'F', 'M', 'VOS cage card CC-17244-2', 'High'],
    [893, 'F', 'M', 'SoftMouse', 'High'],
    [894, 'F', 'M', 'SoftMouse', 'High'],
  ],
  // Active avoidance dates the tracker stamped into the files (and the
  // Behaviour sheet): [mouse, day 1, day 2]. Lab Ops has 3/24/2024.
  aa: [
    [416, [2024, 3, 13], [2024, 3, 15]],
    [418, [2024, 3, 13], [2024, 3, 15]],
  ],
  aaWrong: [2024, 3, 24],
  // 473 never ran AA: its date was copied in error (Angelina, 11-23).
  clearAA: [473],
  // DOB nobody had, from the old VOS cage card CC-11420-1.
  dob: [[872, [2023, 3, 24], 'VOS cage card CC-11420-1']],
};

function previewAuditFixes112326() { return runAudit112326_(false); }
function applyAuditFixes112326() { return runAudit112326_(true); }

function runAudit112326_(apply) {
  const A = AUDIT112326;
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName(A.tab);
  if (!sh) throw new Error('No tab called ' + A.tab);
  const tz = ss.getSpreadsheetTimeZone();
  const values = sh.getDataRange().getValues();
  const head = values[0].map((h) => String(h || '').trim());
  const col = (name) => {
    const i = head.indexOf(name);
    if (i < 0) throw new Error('No column "' + name + '" in ' + A.tab);
    return i;
  };
  const cId = col('Mouse ID'), cSex = col('Sex'), cDob = col('DOB');
  const cAA1 = col('Active avoidance'), cAA2 = col('Active avoidance #2');

  // Mouse number -> its rows ("0292 (Breeder 2)" is 292).
  const rows = {};
  for (let r = 1; r < values.length; r++) {
    const m = String(values[r][cId] || '').match(/^\s*0*(\d+)/);
    if (!m) continue;
    (rows[m[1]] = rows[m[1]] || []).push(r);
  }
  const ymd = (v) => (v instanceof Date
    ? Utilities.formatDate(v, tz, 'yyyy-MM-dd') : String(v == null ? '' : v).trim());
  const iso = (p) => p[0] + '-' + String(p[1]).padStart(2, '0') + '-'
                     + String(p[2]).padStart(2, '0');
  const mkDate = (p) => new Date(p[0], p[1] - 1, p[2]);
  const stamp = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');
  const report = [];
  const changes = [];     // [row, col, newValue, note]

  const one = (mouse, field) => {
    const rs = rows[String(mouse)] || [];
    if (rs.length !== 1) {
      report.push([mouse, field, '', '', rs.length ? 'SKIPPED: ' + rs.length
                   + ' rows for this mouse' : 'SKIPPED: mouse not on the tab', '']);
      return null;
    }
    return rs[0];
  };
  const noteFor = (was, now, why) => 'Audit ' + stamp + ' (' + A.source + '): was "'
    + (was === '' ? '(blank)' : was) + '", set to "' + (now === '' ? '(blank)' : now)
    + '". ' + why;

  // ---- sex ----
  for (const [mouse, wrong, right, why, conf] of A.sex) {
    const r = one(mouse, 'Sex');
    if (r == null) continue;
    const cur = String(values[r][cSex] || '').trim();
    if (cur.toUpperCase() === right) {
      report.push([mouse, 'Sex', cur, right, 'already correct', why]);
    } else if (cur.toUpperCase() === wrong) {
      changes.push([r, cSex, right, noteFor(cur, right, 'Settled by ' + why
                    + ' (' + conf + ' confidence).')]);
      report.push([mouse, 'Sex', cur, right, apply ? 'CHANGED' : 'would change',
                   why + ', ' + conf]);
    } else {
      report.push([mouse, 'Sex', cur, right, 'SKIPPED: holds "' + cur
                   + '", not the "' + wrong + '" the audit found', why]);
    }
  }

  // ---- 416 / 418 active avoidance dates ----
  const wrongAA = iso(A.aaWrong);
  for (const [mouse, d1, d2] of A.aa) {
    const r = one(mouse, 'Active avoidance');
    if (r == null) continue;
    for (const [c, want, label] of [[cAA1, d1, 'Active avoidance'],
                                    [cAA2, d2, 'Active avoidance #2']]) {
      const cur = ymd(values[r][c]);
      if (cur === iso(want)) {
        report.push([mouse, label, cur, iso(want), 'already correct', 'file headers']);
      } else if (cur === wrongAA || cur === '') {
        changes.push([r, c, mkDate(want), noteFor(cur, iso(want),
          'The tracker stamps the date into each file, and the Behaviour sheet '
          + 'agrees: day 1 3/13/2024, day 2 3/15/2024.')]);
        report.push([mouse, label, cur, iso(want), apply ? 'CHANGED' : 'would change',
                     'file headers + Behaviour sheet']);
      } else {
        report.push([mouse, label, cur, iso(want), 'SKIPPED: holds "' + cur
                     + '", not ' + wrongAA, 'file headers']);
      }
    }
  }

  // ---- 473: never ran AA ----
  for (const mouse of A.clearAA) {
    const r = one(mouse, 'Active avoidance');
    if (r == null) continue;
    for (const [c, label] of [[cAA1, 'Active avoidance'], [cAA2, 'Active avoidance #2']]) {
      const cur = ymd(values[r][c]);
      if (cur === '') {
        report.push([mouse, label, '', '', 'already blank', 'Angelina, 11-23']);
        continue;
      }
      changes.push([r, c, '', noteFor(cur, '', '473 did not run active avoidance: '
        + 'the date was copied in error (Angelina, 11-23). No Behaviour-log row '
        + 'and no free slot on 10/23-24.')]);
      report.push([mouse, label, cur, '', apply ? 'CLEARED' : 'would clear',
                   'copied in error (Angelina)']);
    }
  }

  // ---- 872's DOB ----
  for (const [mouse, d, why] of A.dob) {
    const r = one(mouse, 'DOB');
    if (r == null) continue;
    const cur = ymd(values[r][cDob]);
    if (cur === iso(d)) {
      report.push([mouse, 'DOB', cur, iso(d), 'already correct', why]);
    } else if (cur === '' || cur === '?' || /unknown/i.test(cur)) {
      changes.push([r, cDob, mkDate(d), noteFor(cur, iso(d), 'From ' + why + '.')]);
      report.push([mouse, 'DOB', cur, iso(d), apply ? 'CHANGED' : 'would change', why]);
    } else {
      report.push([mouse, 'DOB', cur, iso(d), 'SKIPPED: already holds "' + cur + '"', why]);
    }
  }

  if (apply) {
    for (const [r, c, v, note] of changes) {
      const cell = sh.getRange(r + 1, c + 1);
      const had = cell.getNote();
      cell.setValue(v);
      cell.setNote(had ? had + '\n\n' + note : note);
    }
    let rep = ss.getSheetByName('Audit fixes 112326');
    if (!rep) rep = ss.insertSheet('Audit fixes 112326');
    rep.clear();
    const out = [['Mouse', 'Field', 'Was', 'Now', 'Result', 'Settled by']].concat(report);
    rep.getRange(1, 1, out.length, 6).setValues(out.map((x) => x.map(String)));
    rep.setFrozenRows(1);
  }
  const lines = report.map((x) => x.join(' | '));
  console.log((apply ? 'APPLIED ' : 'PREVIEW (nothing changed) ') + changes.length
              + ' change(s):\n' + lines.join('\n'));
  return { changed: apply ? changes.length : 0, planned: changes.length, report };
}
