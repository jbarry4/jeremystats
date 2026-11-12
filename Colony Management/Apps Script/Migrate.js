//MirgrateSanityCheck.gs
/**
 * MIGRATION SANITY CHECK — "KCNT1 Active" vs "KCNT1 Active 2.0"
 * =============================================================
 * Answers one question about the live spreadsheet: did anything that was in v1
 * fail to make it into 2.0, or change on the way?
 *
 * DIRECTION MATTERS. 2.0 is the live sheet and has been worked on since the
 * migration, so information present in 2.0 but absent from v1 is expected — it
 * is counted and never listed as a problem. The report looks for the other
 * direction: v1 knew something 2.0 does not, or the two disagree.
 *
 * MATCHED BY MOUSE ID, NOT ROW. The migration preserved row order, but VOS
 * imports append rows to 2.0, so comparing row N to row N would produce a
 * mountain of false alarms. Row numbers are still reported, and a mouse that
 * moved rows is noted as information.
 *
 * WHAT IT COMPARES
 *   - Identity fields: Cage ID, Sex, YH, SST, PV, Role, Alive, DOB, Notes.
 *   - Every activity block, as a (date, Time, Lead) triple, discovered from the
 *     header row rather than hard-coded — a block added later needs no edit
 *     here. The v1 recording columns are compared against the LEFT hemisphere
 *     in 2.0, which is where the migration put them; the (R) columns are new
 *     and never compared.
 *
 * DATES ARE COMPARED BY MEANING, NOT BY TYPE. A cell that lost its date number
 * format comes back from getValues() as a raw serial (45828) rather than a Date
 * — the same day, wearing different clothes. Comparing those literally would
 * bury the report in hundreds of differences that are not differences, so both
 * sides are resolved to a calendar day first.
 *
 * That mismatch is still worth knowing about, so it is reported in its own
 * band: DATE NOT FORMATTED. It is not cosmetic. CalendarSync2.0 tests
 * `rawDate instanceof Date`; against a bare serial that test fails, the
 * fallback parse reads 45828 as 45 seconds past the 1970 epoch, and the
 * activity gets scheduled in 1970. Fix those cells with Format > Number > Date.
 *
 * WHAT IT DELIBERATELY DOES NOT COMPARE
 *   - Age and Age (weeks): formulas, and 2.0's still reference the wrong
 *     columns, so comparing them would bury real findings under derived noise.
 *   - Script Sync Data: the calendar sync rewrites it constantly.
 *   - Delayed?: dropped by the migration on purpose. Reported once with a count
 *     of how many cells actually held a value, so you can see the size of what
 *     was discarded instead of 19 columns of noise.
 *
 * Run it from Lab Tools > Compare 2.0 vs v1 (Sanity), or from the editor. It
 * only reads the two sheets; the one thing it writes is its own output tab.
 */

// =============================================================================
// CONFIG
// =============================================================================

const SC2_V1_NAME  = 'KCNT1 Active';
const SC2_V2_NAME  = 'KCNT1 Active 2.0';
const SC2_OUT_NAME = 'Migration Sanity Check';

/**
 * Mirrors V2_RECORDING_BASES in CalendarSync2.0.gs. Deliberately duplicated so
 * this file can be pasted into a scratch copy of the spreadsheet on its own.
 */
const SC2_RECORDING_BASES = ['H3 probe', 'H10 probe', 'H10 opto'];

/** Compared cell by cell, by header name, on both sheets. */
const SC2_SCALAR_FIELDS = ['Cage ID', 'Sex', 'YH', 'SST', 'PV', 'Role', 'Alive', 'DOB', 'Notes'];

/** Never compared — see the header comment for why each one is here. */
const SC2_SKIP_FIELDS = ['Age', 'Age (weeks)', 'Script Sync Data'];

/** Trailing qualifiers that belong to the activity block before them. */
const SC2_QUALIFIERS = ['Time', 'Lead', 'Delayed?', 'Sessions', 'Double Inj?'];

/**
 * "Hom" and "hom" are the same genotype. Leave false unless you are chasing a
 * genuine capitalisation problem.
 */
const SC2_CASE_SENSITIVE = false;

/**
 * Values 2.0 has and v1 does not are the normal result of working on the sheet.
 * Always counted; set true to list them individually as well.
 */
const SC2_LIST_NEW_IN_V2 = false;

/**
 * Report cells that hold the right date but lost their date formatting. Worth
 * leaving on — see the header comment for what it breaks.
 */
const SC2_REPORT_DATE_FORMAT = true;

/** Stops a pathological run from trying to write a million-row sheet. */
const SC2_MAX_FINDINGS = 5000;

/**
 * Anything from roughly 1954 to 2119 as a spreadsheet date serial. Outside this
 * band a bare number in a date column is treated as text, not silently read as
 * a date — a cage number should never be reinterpreted as a day.
 */
const SC2_SERIAL_MIN = 20000;
const SC2_SERIAL_MAX = 80000;

// =============================================================================
// ENTRY POINT
// =============================================================================

function runSanityCheckV2() {
  const ui = SpreadsheetApp.getUi();

  try {
    Logger.log('--- MIGRATION SANITY CHECK START ---');
    const ss = SpreadsheetApp.getActiveSpreadsheet();

    const v1Sheet = ss.getSheetByName(SC2_V1_NAME);
    const v2Sheet = ss.getSheetByName(SC2_V2_NAME);

    if (!v1Sheet || !v2Sheet) {
      const have = ss.getSheets().map(function (s) { return '  • ' + s.getName(); }).join('\n');
      throw new Error('This compares "' + SC2_V1_NAME + '" against "' + SC2_V2_NAME +
        '", and ' + (!v1Sheet ? '"' + SC2_V1_NAME + '"' : '"' + SC2_V2_NAME + '"') +
        ' is not here.\n\nSheets in this file:\n' + have +
        '\n\nIf you have already run promoteV2ToActive(), the v1 sheet is called ' +
        '"KCNT1 Active (v1 archive)" — put that name in SC2_V1_NAME.');
    }

    const tz = ss.getSpreadsheetTimeZone();

    const v1Data = v1Sheet.getDataRange().getValues();
    const v2Data = v2Sheet.getDataRange().getValues();
    if (v1Data.length < 2 || v2Data.length < 2) throw new Error('One of the sheets has no data rows.');

    const v1Head = v1Data[0].map(function (h) { return String(h).trim(); });
    const v2Head = v2Data[0].map(function (h) { return String(h).trim(); });

    const v1IdCol = v1Head.indexOf('Mouse ID');
    const v2IdCol = v2Head.indexOf('Mouse ID');
    if (v1IdCol === -1 || v2IdCol === -1) throw new Error('Both sheets need a "Mouse ID" column.');

    const v1Index = sc2IndexById_(v1Data, v1IdCol);
    const v2Index = sc2IndexById_(v2Data, v2IdCol);
    Logger.log('v1 mice: ' + Object.keys(v1Index.rows).length +
               ' | 2.0 mice: ' + Object.keys(v2Index.rows).length);

    const fields = sc2BuildFieldPlan_(v1Head, v2Head);
    Logger.log('Comparable fields: ' + fields.length);

    const findings = [];
    const counts = { missingMouse: 0, conflict: 0, missingValue: 0, dateFormat: 0,
                     newInV2: 0, newMouse: 0, duplicate: 0, moved: 0 };

    // ---- DUPLICATE IDS — they make any comparison ambiguous, so say so first ----
    [['v1', v1Index], ['2.0', v2Index]].forEach(function (pair) {
      const label = pair[0], index = pair[1];
      Object.keys(index.dupes).forEach(function (id) {
        counts.duplicate++;
        findings.push({
          sev: 'DUPLICATE ID', id: id,
          r1: label === 'v1' ? index.dupes[id].join(', ') : '',
          r2: label === '2.0' ? index.dupes[id].join(', ') : '',
          field: '(whole row)', a: '', b: '',
          note: 'Mouse ID appears ' + index.dupes[id].length + ' times in ' + label +
                ' (rows ' + index.dupes[id].join(', ') + '). Only the first was compared.'
        });
      });
    });

    // ---- EVERY MOUSE v1 KNOWS ABOUT ----
    Object.keys(v1Index.rows).forEach(function (id) {
      const r1 = v1Index.rows[id];
      const row1 = v1Data[r1 - 1];

      if (!(id in v2Index.rows)) {
        counts.missingMouse++;
        findings.push({
          sev: 'MISSING MOUSE', id: id, r1: r1, r2: '', field: '(whole row)',
          a: sc2RowSummary_(row1, v1Head, tz), b: '',
          note: 'In ' + SC2_V1_NAME + ' but not in ' + SC2_V2_NAME + '. The migration ' +
                'carried every row across, so check whether this row was deleted later.'
        });
        return;
      }

      const r2 = v2Index.rows[id];
      const row2 = v2Data[r2 - 1];

      if (r1 !== r2) {
        counts.moved++;
        findings.push({
          sev: 'ROW MOVED', id: id, r1: r1, r2: r2, field: '(row position)',
          a: 'row ' + r1, b: 'row ' + r2,
          note: 'Information only. The comparison follows the Mouse ID, not the row.'
        });
      }

      for (let f = 0; f < fields.length; f++) {
        const fld = fields[f];
        const A = sc2Cell_(row1[fld.c1], fld.kind, tz);
        const B = sc2Cell_(row2[fld.c2], fld.kind, tz);

        if (A.text === '' && B.text === '') continue;

        if (A.text !== '' && B.text === '') {
          counts.missingValue++;
          findings.push({
            sev: 'MISSING VALUE', id: id, r1: r1, r2: r2, field: fld.label,
            a: A.text, b: '(blank)',
            note: SC2_V1_NAME + ' has a value here and ' + SC2_V2_NAME + ' does not.'
          });

        } else if (A.text === '' && B.text !== '') {
          counts.newInV2++;
          if (SC2_LIST_NEW_IN_V2) {
            findings.push({
              sev: 'NEW IN 2.0', id: id, r1: r1, r2: r2, field: fld.label,
              a: '(blank)', b: B.text, note: 'Added since the migration. Expected.'
            });
          }

        } else if (!sc2Same_(A.text, B.text)) {
          counts.conflict++;
          findings.push({
            sev: 'CONFLICT', id: id, r1: r1, r2: r2, field: fld.label,
            a: A.text, b: B.text,
            note: 'Both sheets hold a value and they disagree.'
          });

        } else if (SC2_REPORT_DATE_FORMAT && B.serial && !A.serial) {
          // Same day, but 2.0 is storing it as a bare number.
          counts.dateFormat++;
          findings.push({
            sev: 'DATE NOT FORMATTED', id: id, r1: r1, r2: r2, field: fld.label,
            a: A.text, b: B.raw + '  (= ' + B.text + ')',
            note: 'Right date, wrong cell format: ' + SC2_V2_NAME + ' holds a raw serial ' +
                  'number, so getValues() returns a number and not a Date. The calendar ' +
                  'sync misreads that as 1970. Select the column and apply ' +
                  'Format > Number > Date.'
          });
        }
      }
    });

    // ---- MICE ONLY 2.0 KNOWS ABOUT — expected, counted, not listed ----
    Object.keys(v2Index.rows).forEach(function (id) {
      if (!(id in v1Index.rows)) counts.newMouse++;
    });

    // ---- WHAT THE MIGRATION DROPPED ON PURPOSE ----
    const delayed = sc2CountDelayed_(v1Data, v1Head);
    if (delayed.columns > 0) {
      findings.push({
        sev: 'DROPPED BY DESIGN', id: '', r1: '', r2: '', field: 'Delayed?',
        a: delayed.filled + ' cells had a value', b: 'columns removed',
        note: delayed.columns + ' "Delayed?" columns existed in ' + SC2_V1_NAME +
              ' and were removed by the migration. ' + delayed.filled +
              ' of those cells were not blank, across ' + delayed.rows +
              ' mice. Nothing to fix unless you want that history back.'
      });
    }

    // ---- 2.0-ONLY COLUMNS, FOR THE RECORD ----
    const newCols = v2Head.filter(function (h, i) {
      if (h === '' || SC2_QUALIFIERS.indexOf(h) !== -1) return false;
      return v1Head.indexOf(h) === -1 && v2Head.indexOf(h) === i;
    });
    if (newCols.length > 0) {
      findings.push({
        sev: 'NEW COLUMN', id: '', r1: '', r2: '', field: newCols.join(', '),
        a: '', b: '', note: 'Columns that exist only in ' + SC2_V2_NAME + '. Expected.'
      });
    }

    const total = sc2WriteReport_(ss, findings, fields.length,
                                  Object.keys(v1Index.rows).length);

    const summary =
      'Compared ' + Object.keys(v1Index.rows).length + ' mice across ' + fields.length + ' fields.\n\n' +
      'NEEDS ATTENTION\n' +
      '  Mice missing from 2.0:            ' + counts.missingMouse + '\n' +
      '  Conflicting values:               ' + counts.conflict + '\n' +
      '  Values lost (v1 had, 2.0 blank):  ' + counts.missingValue + '\n' +
      '  Duplicate Mouse IDs:              ' + counts.duplicate + '\n\n' +
      'FORMATTING\n' +
      '  Dates stored as raw numbers:      ' + counts.dateFormat + '\n\n' +
      'EXPECTED / INFORMATION\n' +
      '  Values added since migration:     ' + counts.newInV2 + '\n' +
      '  Mice added since migration:       ' + counts.newMouse + '\n' +
      '  Mice that changed row:            ' + counts.moved + '\n' +
      '  "Delayed?" cells discarded:       ' + delayed.filled + '\n\n' +
      total + ' row(s) written to the "' + SC2_OUT_NAME + '" tab.';

    Logger.log(summary);
    Logger.log('--- MIGRATION SANITY CHECK COMPLETE ---');
    ui.alert('Migration Sanity Check', summary, ui.ButtonSet.OK);

  } catch (error) {
    Logger.log('ERROR: ' + error.message + '\n' + error.stack);
    ui.alert('⚠️ Sanity Check Failed',
      error.message + '\n\n(Check the Apps Script Execution Log for details)',
      ui.ButtonSet.OK);
  }
}

// =============================================================================
// PLANNING
// =============================================================================

/**
 * Every field that exists on BOTH sheets and is worth comparing.
 *
 * Activity blocks are found the way the calendar sync finds them — a header
 * followed by "Time" — so a block added later needs no code change. The three
 * recording modalities are the one special case: v1 has a single column, 2.0
 * has (L) and (R), and the migration put the old data in (L).
 */
function sc2BuildFieldPlan_(v1Head, v2Head) {
  const fields = [];

  SC2_SCALAR_FIELDS.forEach(function (name) {
    if (SC2_SKIP_FIELDS.indexOf(name) !== -1) return;
    const c1 = v1Head.indexOf(name);
    const c2 = v2Head.indexOf(name);
    if (c1 === -1 || c2 === -1) return;
    fields.push({ label: name, c1: c1, c2: c2, kind: name === 'DOB' ? 'date' : 'text' });
  });

  for (let i = 0; i < v1Head.length; i++) {
    const h = v1Head[i];
    if (h === '' || SC2_QUALIFIERS.indexOf(h) !== -1) continue;
    if (SC2_SKIP_FIELDS.indexOf(h) !== -1) continue;
    if (SC2_SCALAR_FIELDS.indexOf(h) !== -1) continue;
    if (v1Head[i + 1] !== 'Time') continue;   // not an activity block

    // v1 "H3 probe" became 2.0 "H3 probe (L)".
    const name2 = (SC2_RECORDING_BASES.indexOf(h) !== -1) ? h + ' (L)' : h;
    const c2 = v2Head.indexOf(name2);
    if (c2 === -1) continue;

    const b1 = sc2BlockCols_(v1Head, i);
    const b2 = sc2BlockCols_(v2Head, c2);

    fields.push({ label: h + ' [date]', c1: i, c2: c2, kind: 'date' });
    if (b1.time !== -1 && b2.time !== -1) {
      fields.push({ label: h + ' [Time]', c1: b1.time, c2: b2.time, kind: 'time' });
    }
    if (b1.lead !== -1 && b2.lead !== -1) {
      fields.push({ label: h + ' [Lead]', c1: b1.lead, c2: b2.lead, kind: 'text' });
    }
  }

  return fields;
}

/** Positions of Time / Lead within the block that starts at dateCol. */
function sc2BlockCols_(headers, dateCol) {
  const out = { time: -1, lead: -1 };
  let k = dateCol + 1;
  while (k < headers.length && SC2_QUALIFIERS.indexOf(headers[k]) !== -1) {
    if (headers[k] === 'Time' && out.time === -1) out.time = k;
    if (headers[k] === 'Lead' && out.lead === -1) out.lead = k;
    k++;
  }
  return out;
}

// =============================================================================
// VALUE HANDLING
// =============================================================================

/**
 * One cell to one comparable string.
 *
 * Returns { text, serial, raw }. `serial` is true when the value arrived as a
 * bare spreadsheet serial number in a date or time column — the same day or
 * clock time as a proper Date, but a number as far as every other script is
 * concerned. Callers use that to tell "wrong value" from "right value, wrong
 * format".
 */
function sc2Cell_(v, kind, tz) {
  const none = { text: '', serial: false, raw: '' };
  if (v === null || v === undefined || v === '') return none;

  if (v instanceof Date) {
    if (isNaN(v.getTime())) return none;
    return {
      text: Utilities.formatDate(v, tz, kind === 'time' ? 'h:mm a' : 'MM/dd/yyyy'),
      serial: false,
      raw: String(v)
    };
  }

  if (typeof v === 'boolean') return { text: v ? 'TRUE' : 'FALSE', serial: false, raw: String(v) };

  if (typeof v === 'number' && isFinite(v)) {
    if (kind === 'date' && v >= SC2_SERIAL_MIN && v <= SC2_SERIAL_MAX) {
      return { text: sc2SerialToDateText_(v, tz), serial: true, raw: String(v) };
    }
    // A time-only cell is stored as a fraction of a day.
    if (kind === 'time' && v > 0 && v < 1) {
      return { text: sc2FractionToTimeText_(v), serial: true, raw: String(v) };
    }
  }

  return { text: String(v).trim().replace(/\s+/g, ' '), serial: false, raw: String(v) };
}

/**
 * Spreadsheet date serial to a calendar day.
 *
 * Built by stepping a LOCAL date forward from the epoch rather than adding
 * milliseconds to a UTC instant: a serial is midnight, and midnight UTC
 * formatted in an American timezone lands on the previous evening, which would
 * report every date one day early.
 */
function sc2SerialToDateText_(serial, tz) {
  const d = new Date(1899, 11, 30);
  d.setDate(d.getDate() + Math.floor(serial));
  return Utilities.formatDate(d, tz, 'MM/dd/yyyy');
}

/** Fraction of a day to a clock time, without going anywhere near a timezone. */
function sc2FractionToTimeText_(frac) {
  let mins = Math.round(frac * 24 * 60);
  let h = Math.floor(mins / 60) % 24;
  const m = mins % 60;
  const ampm = h < 12 ? 'AM' : 'PM';
  h = h % 12; if (h === 0) h = 12;
  return h + ':' + (m < 10 ? '0' : '') + m + ' ' + ampm;
}

function sc2Same_(a, b) {
  return SC2_CASE_SENSITIVE ? (a === b) : (a.toLowerCase() === b.toLowerCase());
}

// =============================================================================
// HELPERS
// =============================================================================

/** Mouse ID -> first row number, plus any IDs that appear more than once. */
function sc2IndexById_(data, idCol) {
  const rows = {};
  const all = {};
  for (let r = 1; r < data.length; r++) {
    const id = String(data[r][idCol] || '').trim();
    if (!id) continue;
    (all[id] = all[id] || []).push(r + 1);
    if (!(id in rows)) rows[id] = r + 1;
  }
  const dupes = {};
  Object.keys(all).forEach(function (id) { if (all[id].length > 1) dupes[id] = all[id]; });
  return { rows: rows, dupes: dupes };
}

/** Enough of a row to recognise the mouse in the report. */
function sc2RowSummary_(row, headers, tz) {
  const parts = [];
  ['Cage ID', 'Sex', 'Role', 'Alive', 'DOB'].forEach(function (name) {
    const c = headers.indexOf(name);
    if (c === -1) return;
    const cell = sc2Cell_(row[c], name === 'DOB' ? 'date' : 'text', tz);
    if (cell.text !== '') parts.push(name + '=' + cell.text);
  });
  return parts.join(', ');
}

/** How much actually lived in the Delayed? columns the migration removed. */
function sc2CountDelayed_(data, headers) {
  const cols = [];
  headers.forEach(function (h, i) { if (h === 'Delayed?') cols.push(i); });

  let filled = 0;
  let rows = 0;
  for (let r = 1; r < data.length; r++) {
    let any = false;
    for (let k = 0; k < cols.length; k++) {
      const v = data[r][cols[k]];
      // An unticked checkbox reads as boolean false and is not information.
      if (v === '' || v === null || v === undefined || v === false) continue;
      filled++;
      any = true;
    }
    if (any) rows++;
  }
  return { columns: cols.length, filled: filled, rows: rows };
}

// =============================================================================
// OUTPUT
// =============================================================================

function sc2WriteReport_(ss, findings, fieldCount, mouseCount) {
  let sheet = ss.getSheetByName(SC2_OUT_NAME);
  if (!sheet) sheet = ss.insertSheet(SC2_OUT_NAME);
  else sheet.clear();

  // Worst first, so the top of the sheet is the part that matters.
  const order = { 'MISSING MOUSE': 0, 'CONFLICT': 1, 'MISSING VALUE': 2,
                  'DUPLICATE ID': 3, 'DATE NOT FORMATTED': 4, 'NEW IN 2.0': 5,
                  'ROW MOVED': 6, 'DROPPED BY DESIGN': 7, 'NEW COLUMN': 8 };
  const rank = function (s) { return order[s] === undefined ? 99 : order[s]; };

  findings.sort(function (a, b) {
    const d = rank(a.sev) - rank(b.sev);
    if (d !== 0) return d;
    if (a.id !== b.id) return String(a.id).localeCompare(String(b.id));
    return String(a.field).localeCompare(String(b.field));
  });

  let truncated = 0;
  if (findings.length > SC2_MAX_FINDINGS) {
    truncated = findings.length - SC2_MAX_FINDINGS;
    findings = findings.slice(0, SC2_MAX_FINDINGS);
  }

  const header = ['Severity', 'Mouse ID', 'v1 Row', '2.0 Row', 'Field',
                  SC2_V1_NAME, SC2_V2_NAME, 'What it means'];

  const out = [header];
  findings.forEach(function (f) {
    out.push([f.sev, f.id, f.r1, f.r2, f.field, f.a, f.b, f.note]);
  });

  if (findings.length === 0) {
    out.push(['OK', '', '', '', '(nothing)', '', '',
      'No missing or conflicting information found across ' + fieldCount +
      ' fields and ' + mouseCount + ' mice.']);
  }

  sheet.getRange(1, 1, out.length, header.length).setValues(out);
  sheet.getRange(1, 1, 1, header.length).setFontWeight('bold').setBackground('#f0f0f0');
  sheet.setFrozenRows(1);

  const bands = {
    'MISSING MOUSE':      { bg: '#f4c7c3', fc: '#a50e0e' },
    'CONFLICT':           { bg: '#fce8e6', fc: '#c5221f' },
    'MISSING VALUE':      { bg: '#fef7e0', fc: '#b06000' },
    'DUPLICATE ID':       { bg: '#fef7e0', fc: '#b06000' },
    'DATE NOT FORMATTED': { bg: '#fff3e0', fc: '#8a5300' },
    'NEW IN 2.0':         { bg: '#e6f4ea', fc: '#137333' },
    'ROW MOVED':          { bg: '#f1f3f4', fc: '#5f6368' },
    'DROPPED BY DESIGN':  { bg: '#e8f0fe', fc: '#1967d2' },
    'NEW COLUMN':         { bg: '#e8f0fe', fc: '#1967d2' }
  };

  // Findings are already sorted by severity, so every band is contiguous.
  // Walk by index and colour each run in a single call.
  let i = 0;
  while (i < findings.length) {
    const sev = findings[i].sev;
    let j = i;
    while (j < findings.length && findings[j].sev === sev) j++;

    const band = bands[sev];
    if (band) {
      // findings[i] lives on sheet row i + 2 (row 1 is the header).
      sheet.getRange(i + 2, 1, j - i, header.length)
           .setBackground(band.bg).setFontColor(band.fc);
    }
    i = j;
  }

  [140, 90, 60, 60, 170, 200, 230, 430].forEach(function (w, c) {
    sheet.setColumnWidth(c + 1, w);
  });
  sheet.getRange(1, 8, out.length, 1).setWrap(true);

  if (truncated > 0) {
    const cell = sheet.getRange(out.length + 2, 1);
    cell.setValue('Stopped after ' + SC2_MAX_FINDINGS + ' findings — ' + truncated +
      ' more were not written. Raise SC2_MAX_FINDINGS, or clear the top band first.');
    cell.setFontWeight('bold').setFontColor('#a50e0e');
  }

  sheet.activate();
  return findings.length;
}
