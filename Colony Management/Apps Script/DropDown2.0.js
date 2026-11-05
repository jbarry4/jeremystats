//Dropdown2.0.gs
/**
 * FIND MICE 2.0 — for "KCNT1 Active 2.0"
 * ======================================
 * The 2.0 counterpart to Dropdown.gs. Replaces it; do not run both.
 *
 * WHAT CHANGED FROM v1
 *
 * 1. TARGETS A NAMED SHEET. v1 filtered whatever sheet you happened to be
 *    looking at, so running it from "VOS Imports" quietly did nothing useful.
 *    This one resolves "KCNT1 Active 2.0" by name, switches to it if you are
 *    somewhere else, and says so plainly if it cannot find it.
 *
 * 2. HEMISPHERE AWARE. Each recording modality is two columns now, (L) and (R).
 *    A modality counts as finished only when BOTH hemispheres are logged, so a
 *    mouse with H3 probe (L) done and (R) blank is still "ready for H3" — which
 *    is the whole reason the columns were split. The results list names the
 *    outstanding side, so you can see at a glance whether a mouse needs one
 *    more session or two.
 *
 * 3. TELLS YOU WHY. v1 returned an empty list whether nothing matched or the
 *    columns were missing. This reports missing columns by name, which is the
 *    fast way to spot that you are pointed at a pre-migration sheet.
 *
 * 4. OWNS THE MENUS. This file carries the one onOpen for the whole project.
 *
 * INSTALLING
 *   1. Paste this in as a new file.
 *   2. DELETE the onOpen function from Dropdown.gs and from SoftMouse_Import.gs.
 *      Apps Script keeps only one onOpen across the project and silently uses
 *      whichever loads last, so leaving them in place makes the menus a lottery.
 *   3. Ideally delete Dropdown.gs outright once you are happy with this.
 *   4. Reload the spreadsheet to pick up the new menus.
 *
 * The pipeline gate is unchanged from v1: only mice with Alive = "Yes" and
 * Role = "Stock" are considered. Weanlings and breeders never appear.
 */

// =============================================================================
// CONFIG
// =============================================================================

/**
 * Sheets to look for, in order of preference. "KCNT1 Active 2.0" is the name
 * the migration creates; promoteV2ToActive() later renames it to "KCNT1
 * Active", so both names have to work or this breaks the day you promote.
 */
const FM2_SHEET_NAMES = ['KCNT1 Active 2.0', 'KCNT1 Active'];

/** The three modalities, each split into (L) and (R) in 2.0. */
const FM2_RECORDING_BASES = ['H3 probe', 'H10 probe', 'H10 opto'];

/** Document property used to hand the match list from the dialog to the filter. */
const FM2_PROP_KEY = 'filteredMiceV2';

// =============================================================================
// MENUS — the single onOpen for the whole project
// =============================================================================

function onOpen() {
  const ui = SpreadsheetApp.getUi();

  ui.createMenu('Find Mice 2.0')
    .addItem('Select Filters', 'openFilterDialogV2')
    .addSeparator()
    .addItem('Clear All Filters', 'clearSheetFiltersV2')
    .addSeparator()
    .addItem('Diagnose (what will it search?)', 'diagnoseFindMiceV2')
    .addToUi();

  ui.createMenu('Lab Tools')
    .addItem('Sync VOS Census to KCNT1', 'showImportDialog')
    .addItem('Sync SoftMouse to KCNT1', 'showSoftMouseDialog')
    .addSeparator()
    .addItem('Resync All Rows (Calendar)', 'resyncAllRows')
    .addItem('Resync Current Row (Calendar)', 'resyncCurrentRow')
    .addSeparator()
    .addItem('Report Duplicate Events', 'reportDuplicateEvents')
    .addItem('Delete Duplicate Events', 'deleteDuplicateEvents')
    .addItem('Prune Calendar (remove orphaned events)', 'pruneCalendar')
    .addSeparator()
    .addItem('Repair Sheet Formatting', 'repairSheetFormatting')
    .addToUi();
}

// =============================================================================
// DIALOG
// =============================================================================

function openFilterDialogV2() {
  const sheet = findMiceSheetV2_();
  if (!sheet) {
    SpreadsheetApp.getUi().alert('Sheet not found', sheetNotFoundMessageV2_(),
      SpreadsheetApp.getUi().ButtonSet.OK);
    return;
  }

  const sheetName = sheet.getName();

  const htmlContent = `
  <div id="step1" style="font-family: Arial, sans-serif; padding: 15px; margin: 0; overflow: hidden;">
    <p style="margin-bottom: 6px; color: #333; font-size: 16px;"><b>Select pipeline stages to find mice:</b></p>
    <p style="margin-top: 0; margin-bottom: 18px; font-size: 12px; color: #666;">
      Searching <b>${sheetName}</b>. Only mice marked Alive = "Yes" and Role = "Stock" are shown &mdash;
      weanlings, breeders and retired mice are excluded.
    </p>

    <div style="margin-bottom: 25px;">

      <label style="display: block; margin-bottom: 12px; font-size: 15px; cursor: pointer;">
        <input type="checkbox" id="chkInj" style="transform: scale(1.3); margin-right: 10px;"> Ready for Injection
      </label>

      <label style="display: block; margin-bottom: 12px; font-size: 15px; cursor: pointer;">
        <input type="checkbox" id="chkAA" style="transform: scale(1.3); margin-right: 10px;"> Ready for Active Avoidance
      </label>

      <label style="display: block; margin-bottom: 12px; font-size: 15px; cursor: pointer;">
        <input type="checkbox" id="chkHP" style="transform: scale(1.3); margin-right: 10px;"> Ready for Head Plating
      </label>

      <div style="border-top: 1px solid #ccc; margin: 15px 0;"></div>
      <p style="margin: 0 0 10px 0; font-size: 11px; color: #888;">
        A recording counts as done only when both hemispheres are logged.
      </p>

      <label style="display: block; margin-bottom: 12px; font-size: 15px; cursor: pointer;">
        <input type="checkbox" id="chkH3" style="transform: scale(1.3); margin-right: 10px;"> Ready for H3 Recording
      </label>

      <label style="display: block; margin-bottom: 12px; font-size: 15px; cursor: pointer;">
        <input type="checkbox" id="chkH10" style="transform: scale(1.3); margin-right: 10px;"> Ready for H10 Recording
      </label>

      <label style="display: block; margin-bottom: 12px; font-size: 15px; cursor: pointer;">
        <input type="checkbox" id="chkOpto" style="transform: scale(1.3); margin-right: 10px;"> Ready for Opto Recording
      </label>

      <div style="border-top: 1px solid #ccc; margin: 15px 0;"></div>

      <label style="display: block; margin-bottom: 12px; font-size: 15px; cursor: pointer;">
        <input type="checkbox" id="chkPerf" style="transform: scale(1.3); margin-right: 10px;"> Ready for Perfusion
      </label>

    </div>

    <p id="errBox" style="display:none; background:#fdecea; border:1px solid #f5c6cb; color:#a33; padding:10px; border-radius:4px; font-size:13px; margin-bottom:15px;"></p>

    <button style="background-color: #008CBA; color: white; padding: 12px 15px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-weight: bold; font-size: 15px;"
            onclick="findMice(this)">&#128269; Find Mice</button>
  </div>

  <div id="step2" style="display: none; font-family: Arial, sans-serif; padding: 15px; margin: 0; overflow: hidden;">
    <p style="margin-bottom: 10px; color: #333; font-size: 15px;" id="resultText">The following mice meet your criteria:</p>

    <select id="sortOptions" style="width: 100%; padding: 8px; margin-bottom: 15px; border-radius: 4px; border: 1px solid #ccc; font-size: 14px;" onchange="renderMice()">
      <option value="age-oldest">Oldest First</option>
      <option value="age-youngest">Youngest First</option>
      <option value="action-longest">Longest Wait Time (Stagnant First)</option>
      <option value="action-recent">Recently Handled (Active First)</option>
    </select>

    <ul id="mouseList" style="background: #f9f9f9; padding: 15px 15px 15px 35px; border-radius: 5px; margin: 0; list-style-type: square; font-size: 15px; max-height: 220px; overflow-y: auto;">
    </ul>

    <button id="btnFilter" style="background-color: #4CAF50; color: white; padding: 12px 15px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-weight: bold; font-size: 15px; margin-top: 15px; box-sizing: border-box;"
            onclick="applyFilter(this)">&#128187; Computah Filter Accordingly</button>
  </div>

  <script>
    let globalMiceData = [];

    function findMice(btn) {
      btn.innerText = "Searching...";
      document.getElementById('errBox').style.display = 'none';

      const criteria = {
        inj: document.getElementById('chkInj').checked,
        aa: document.getElementById('chkAA').checked,
        hp: document.getElementById('chkHP').checked,
        h3: document.getElementById('chkH3').checked,
        h10: document.getElementById('chkH10').checked,
        opto: document.getElementById('chkOpto').checked,
        perf: document.getElementById('chkPerf').checked
      };

      google.script.run
        .withSuccessHandler(function (res) { showResults(res, btn); })
        .withFailureHandler(function (err) { showError(err.message, btn); })
        .getMatchingMiceV2(criteria);
    }

    function showError(msg, btn) {
      const box = document.getElementById('errBox');
      box.innerText = msg;
      box.style.display = 'block';
      btn.innerHTML = "&#128269; Find Mice";
      google.script.host.setHeight(620);
    }

    function showResults(res, btn) {
      if (!res.ok) { showError(res.error, btn); return; }

      globalMiceData = res.mice;
      document.getElementById('step1').style.display = 'none';
      document.getElementById('step2').style.display = 'block';

      if (globalMiceData.length > 0) {
        document.getElementById('resultText').innerText =
          globalMiceData.length + ' mouse(s) meet your criteria:';
        renderMice();
        const dynamicHeight = Math.min(560, 250 + (globalMiceData.length * 30));
        google.script.host.setHeight(dynamicHeight);
      } else {
        document.getElementById('resultText').innerText = "No alive mice found matching these exact criteria.";
        document.getElementById('sortOptions').style.display = 'none';
        document.getElementById('mouseList').style.display = 'none';
        document.getElementById('btnFilter').style.display = 'none';
        google.script.host.setHeight(100);
      }
    }

    function renderMice() {
      const ul = document.getElementById('mouseList');
      ul.innerHTML = '';

      const sortType = document.getElementById('sortOptions').value;

      globalMiceData.sort((a, b) => {
        if (sortType === 'age-oldest') return a.dob - b.dob;
        if (sortType === 'age-youngest') return b.dob - a.dob;
        if (sortType === 'action-longest') return a.lastAction - b.lastAction;
        if (sortType === 'action-recent') return b.lastAction - a.lastAction;
        return 0;
      });

      globalMiceData.forEach(mouse => {
        const li = document.createElement('li');
        li.style.marginBottom = '8px';
        li.style.color = '#000';

        const idSpan = document.createElement('b');
        idSpan.innerText = mouse.id;
        li.appendChild(idSpan);

        if (mouse.detail) {
          const det = document.createElement('span');
          det.style.color = '#666';
          det.style.fontSize = '13px';
          det.innerText = '  — ' + mouse.detail;
          li.appendChild(det);
        }

        ul.appendChild(li);
      });
    }

    function applyFilter(btn) {
      btn.innerText = "Filtering...";
      google.script.run.withSuccessHandler(google.script.host.close).applyStoredFilterV2();
    }
  </script>
  `;

  const htmlOutput = HtmlService.createHtmlOutput(htmlContent)
      .setWidth(400)
      .setHeight(560);

  SpreadsheetApp.getUi().showModalDialog(htmlOutput, '🐭 Find Mice Pipeline 2.0');
}

// =============================================================================
// MATCHING
// =============================================================================

/**
 * Scans the 2.0 sheet and returns the mice that match.
 *
 * Returns { ok, error, mice } rather than a bare array so the dialog can tell
 * "nothing matched" apart from "this sheet is not in the 2.0 layout" — which in
 * v1 looked identical from the outside.
 */
function getMatchingMiceV2(criteria) {
  const sheet = findMiceSheetV2_();
  if (!sheet) {
    return { ok: false, mice: [], error: sheetNotFoundMessageV2_() };
  }

  if (!criteria.inj && !criteria.aa && !criteria.hp &&
      !criteria.h3 && !criteria.h10 && !criteria.opto && !criteria.perf) {
    return { ok: false, mice: [], error: 'Tick at least one pipeline stage first.' };
  }

  const data = sheet.getDataRange().getValues();
  if (data.length < 2) {
    return { ok: false, mice: [], error: '"' + sheet.getName() + '" has no data rows.' };
  }

  // First occurrence wins. Activity headers are unique; the repeated Time /
  // Lead / Sessions qualifiers are never looked up by name here.
  const headers = data[0].map(function (h) { return String(h).trim(); });
  const idx = {};
  for (let c = 0; c < headers.length; c++) {
    if (headers[c] !== '' && !(headers[c] in idx)) idx[headers[c]] = c;
  }

  // Is this actually a 2.0 sheet? The split recording columns are the tell.
  const missingSplit = [];
  FM2_RECORDING_BASES.forEach(function (base) {
    ['L', 'R'].forEach(function (side) {
      const name = base + ' (' + side + ')';
      if (!(name in idx)) missingSplit.push(name);
    });
  });

  if (missingSplit.length === 6) {
    return { ok: false, mice: [], error:
      '"' + sheet.getName() + '" has no split recording columns, so it is still ' +
      'in the v1 layout. Run migrateToKcnt1v2() first, or use the old Find Mice ' +
      'menu for this sheet.' };
  }
  if (missingSplit.length > 0) {
    return { ok: false, mice: [], error:
      'These 2.0 columns are missing: ' + missingSplit.join(', ') +
      '. Check the header row for typos or stray spaces.' };
  }

  if (!('Mouse ID' in idx)) {
    return { ok: false, mice: [], error: 'No "Mouse ID" column in "' + sheet.getName() + '".' };
  }

  const mouseIdIndex = idx['Mouse ID'];
  const aliveIndex   = colIndexV2_(idx, 'Alive');
  const roleIndex    = colIndexV2_(idx, 'Role');
  const dobIndex     = colIndexV2_(idx, 'DOB');
  const injectIndex  = colIndexV2_(idx, 'Inject');
  const aa1Index     = colIndexV2_(idx, 'Active avoidance');
  const aa2Index     = colIndexV2_(idx, 'Active avoidance #2');
  const headplateIdx = colIndexV2_(idx, 'Headplate');
  const perfuseIndex = colIndexV2_(idx, 'Perfuse');

  const matchedMiceData = [];

  for (let r = 1; r < data.length; r++) {
    const row = data[r];
    const mouseId = row[mouseIdIndex];
    if (!mouseId) continue;

    const aliveStatus = aliveIndex === -1 ? '' : row[aliveIndex];
    if (String(aliveStatus).trim().toLowerCase() !== 'yes') continue;

    // Only mice with Role = "Stock" are eligible for the experimental pipeline.
    // Weanling, Mating, Retired, blank, or any other role means the mouse is
    // off-limits and should not show up.
    const roleStatus = roleIndex === -1 ? '' : row[roleIndex];
    if (String(roleStatus).trim().toLowerCase() !== 'stock') continue;

    const filled = function (c) { return isFilledV2_(row, c); };
    const empty  = function (c) { return !isFilledV2_(row, c); };

    // Which hemispheres are outstanding, per modality.
    const pending = {};
    FM2_RECORDING_BASES.forEach(function (base) {
      pending[base] = pendingSidesV2_(row, idx, base);
    });

    const anyRecordingDone = FM2_RECORDING_BASES.some(function (base) {
      return pending[base].length < 2;   // at least one hemisphere logged
    });

    const aaDone = filled(aa1Index) || filled(aa2Index);

    const reasons = [];

    // 1. Ready for Injection: not yet injected.
    if (criteria.inj && empty(injectIndex)) reasons.push('needs injection');

    // 2. Ready for Active Avoidance: injected, but no AA done yet.
    if (criteria.aa && filled(injectIndex) && !aaDone) reasons.push('needs AA');

    // 3. Ready for Head Plating: injected, but not headplated.
    if (criteria.hp && filled(injectIndex) && empty(headplateIdx)) reasons.push('needs headplate');

    // 4-6. Ready for a recording: headplated, and at least one hemisphere of
    // that modality still blank. Naming the side is the point of the split.
    const wants = { 'H3 probe': criteria.h3, 'H10 probe': criteria.h10, 'H10 opto': criteria.opto };
    FM2_RECORDING_BASES.forEach(function (base) {
      if (!wants[base]) return;
      if (!filled(headplateIdx)) return;
      if (pending[base].length === 0) return;
      reasons.push(shortNameV2_(base) + ' (' + pending[base].join('+') + ') pending');
    });

    // 7. Ready for Perfusion: at least one recording done, but not yet perfused.
    if (criteria.perf && anyRecordingDone && empty(perfuseIndex)) reasons.push('ready to perfuse');

    if (reasons.length === 0) continue;

    // Sort key 1: DOB. Smaller number = older. Blank sinks to the bottom.
    let dobVal = 9999999999999;
    if (dobIndex !== -1) {
      const d = toDateV2_(row[dobIndex]);
      if (d) dobVal = d.getTime();
    }

    // Sort key 2: most recent pipeline action. Smaller = waiting longer.
    // Perfusion is terminal and deliberately not counted, same as v1.
    let lastActionVal = 0;
    const stepIndices = [injectIndex, aa1Index, aa2Index, headplateIdx];
    FM2_RECORDING_BASES.forEach(function (base) {
      ['L', 'R'].forEach(function (side) {
        const c = idx[base + ' (' + side + ')'];
        if (c !== undefined) stepIndices.push(c);
      });
    });

    stepIndices.forEach(function (c) {
      if (c === -1 || c === undefined) return;
      const d = toDateV2_(row[c]);
      if (d && d.getTime() > lastActionVal) lastActionVal = d.getTime();
    });

    matchedMiceData.push({
      id: String(mouseId),
      dob: dobVal,
      lastAction: lastActionVal,
      detail: reasons.join(', ')
    });
  }

  // Hand just the IDs to the filter step.
  const finalIds = matchedMiceData.map(function (m) { return m.id; });
  PropertiesService.getDocumentProperties()
    .setProperty(FM2_PROP_KEY, JSON.stringify(finalIds));

  return { ok: true, mice: matchedMiceData, error: '' };
}

// =============================================================================
// FILTERING
// =============================================================================

/**
 * Hides every mouse that did not match. Always acts on the 2.0 sheet, and
 * switches you to it first — v1 applied the filter to whatever was in front of
 * you, which was only ever right by luck.
 */
function applyStoredFilterV2() {
  const sheet = findMiceSheetV2_();
  if (!sheet) return;

  const props = PropertiesService.getDocumentProperties();
  const miceStr = props.getProperty(FM2_PROP_KEY);
  if (!miceStr) return;

  let matchedMice = [];
  try {
    matchedMice = JSON.parse(miceStr).map(String);
  } catch (err) {
    props.deleteProperty(FM2_PROP_KEY);
    return;
  }

  if (SpreadsheetApp.getActiveSheet().getSheetId() !== sheet.getSheetId()) {
    sheet.activate();
  }

  const range = sheet.getDataRange();
  const data = range.getValues();
  const mouseIdIndex = data[0]
    .map(function (h) { return String(h).trim(); })
    .indexOf('Mouse ID');

  if (mouseIdIndex === -1) return;

  const valuesToHide = [];
  for (let r = 1; r < data.length; r++) {
    const id = data[r][mouseIdIndex];
    if (!id) continue;
    const asText = String(id);
    if (matchedMice.indexOf(asText) === -1) valuesToHide.push(asText);
  }

  // Reuse the existing filter if one is already present, otherwise create one.
  // This keeps the dropdown arrows steady across searches and preserves any
  // criteria on other columns.
  let filter = sheet.getFilter();
  if (filter === null) filter = range.createFilter();

  const filterCriteria = SpreadsheetApp.newFilterCriteria()
    .setHiddenValues(valuesToHide)
    .build();

  filter.setColumnFilterCriteria(mouseIdIndex + 1, filterCriteria);
  props.deleteProperty(FM2_PROP_KEY);
}

/**
 * Clears every column's filter criteria so all rows reappear, leaving the
 * filter itself in place so the dropdown arrows stay put.
 */
function clearSheetFiltersV2() {
  const sheet = findMiceSheetV2_();
  if (!sheet) {
    SpreadsheetApp.getUi().alert('Sheet not found', sheetNotFoundMessageV2_(),
      SpreadsheetApp.getUi().ButtonSet.OK);
    return;
  }

  const filter = sheet.getFilter();
  if (filter === null) return;

  const lastCol = sheet.getLastColumn();
  for (let col = 1; col <= lastCol; col++) {
    filter.removeColumnFilterCriteria(col);
  }
}

// =============================================================================
// HELPERS
// =============================================================================

/** The 2.0 sheet, by name, wherever the cursor happens to be. */
function findMiceSheetV2_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  for (let i = 0; i < FM2_SHEET_NAMES.length; i++) {
    const s = ss.getSheetByName(FM2_SHEET_NAMES[i]);
    if (s) return s;
  }
  return null;
}

/** Column index for a header, or -1. Keeps the optional lookups readable. */
function colIndexV2_(idx, name) {
  return (name in idx) ? idx[name] : -1;
}

function isFilledV2_(row, c) {
  if (c === -1 || c === undefined) return false;
  const v = row[c];
  return v !== null && v !== undefined && String(v).trim() !== '';
}

/** Which of (L) / (R) are still blank for one modality. */
function pendingSidesV2_(row, idx, base) {
  const out = [];
  ['L', 'R'].forEach(function (side) {
    const c = idx[base + ' (' + side + ')'];
    if (c === undefined) return;
    if (!isFilledV2_(row, c)) out.push(side);
  });
  return out;
}

/** "H10 opto" -> "Opto", "H3 probe" -> "H3". Keeps the results list narrow. */
function shortNameV2_(base) {
  if (base === 'H10 opto') return 'Opto';
  return base.replace(' probe', '');
}

/** Anything date-like to a Date, or null. Free text like "UNDOCUMENTED" fails. */
function toDateV2_(v) {
  if (!v) return null;
  if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
  const d = new Date(v);
  return isNaN(d.getTime()) ? null : d;
}

/** Names every sheet in the file, so "not found" says what IS there. */
function sheetNotFoundMessageV2_() {
  let names = [];
  try {
    names = SpreadsheetApp.getActiveSpreadsheet().getSheets()
      .map(function (s) { return '  • ' + s.getName(); });
  } catch (err) {
    names = ['  (could not list sheets: ' + err.message + ')'];
  }

  return 'Find Mice 2.0 looks for a sheet named "' +
         FM2_SHEET_NAMES.join('" or "') + '", and this spreadsheet has neither.\n\n' +
         'Sheets in this file:\n' + names.join('\n') + '\n\n' +
         'If your 2.0 sheet is called something else, add that name to the front ' +
         'of FM2_SHEET_NAMES at the top of Dropdown2.0.gs. Watch for trailing ' +
         'spaces in the tab name — they count.';
}

// =============================================================================
// STALE-MENU ALIASES
// =============================================================================

/**
 * Google Sheets builds the menu bar once, when the document loads, and keeps it
 * until the document is reloaded. So after swapping onOpen the OLD menu is
 * still on screen, still wired to the v1 function names — and clicking it gets
 * you Google's own "Script function not found: openFilterDialog", thrown before
 * any of our code runs, where we cannot intercept it or explain it.
 *
 * These two aliases simply are those names. A stale menu now lands in the 2.0
 * dialog instead of failing, and drops a toast explaining why the menu still
 * says "Find Mice". Reloading the spreadsheet retires them; leaving them costs
 * nothing.
 *
 * If Dropdown.gs is still in your project, DELETE IT. It defines these same two
 * names, and Apps Script keeps only one of each — with both files present you
 * get whichever loaded last, which is exactly the coin toss this is meant to
 * end.
 */
function openFilterDialog() {
  staleMenuNoticeV2_('Select Filters');
  openFilterDialogV2();
}

function clearSheetFilters() {
  staleMenuNoticeV2_('Clear All Filters');
  clearSheetFiltersV2();
}

function staleMenuNoticeV2_(item) {
  try {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      'You used the old "Find Mice" menu (' + item + '). It still works, but ' +
      'reload this spreadsheet to get the "Find Mice 2.0" menu.',
      'Old menu — running 2.0 anyway', 8);
  } catch (err) { /* toast is a nicety, never a blocker */ }
}

// =============================================================================
// DIAGNOSTIC
// =============================================================================

/**
 * Answers "what would Find Mice actually search, and is it in the right shape?"
 * — the questions you want answered when the menu misbehaves or a search comes
 * back empty and you cannot tell whether that is real.
 */
function diagnoseFindMiceV2() {
  const ui = SpreadsheetApp.getUi();
  const sheet = findMiceSheetV2_();

  if (!sheet) {
    ui.alert('Find Mice 2.0 — Diagnosis', sheetNotFoundMessageV2_(), ui.ButtonSet.OK);
    return;
  }

  const lines = [];
  lines.push('Target sheet:   ' + sheet.getName());
  lines.push('Active sheet:   ' + SpreadsheetApp.getActiveSheet().getName());
  lines.push('Data rows:      ' + Math.max(0, sheet.getLastRow() - 1));
  lines.push('');

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0]
                       .map(function (h) { return String(h).trim(); });
  const present = {};
  headers.forEach(function (h) { if (h !== '') present[h] = true; });

  const needed = ['Mouse ID', 'Alive', 'Role', 'DOB', 'Inject',
                  'Active avoidance', 'Active avoidance #2', 'Headplate', 'Perfuse'];
  FM2_RECORDING_BASES.forEach(function (base) {
    needed.push(base + ' (L)');
    needed.push(base + ' (R)');
  });

  const missing = needed.filter(function (n) { return !present[n]; });

  if (missing.length === 0) {
    lines.push('Columns:        all ' + needed.length + ' expected 2.0 columns found.');
  } else {
    lines.push('MISSING COLUMNS (' + missing.length + ' of ' + needed.length + '):');
    missing.forEach(function (m) { lines.push('  • ' + m); });
    lines.push('');
    lines.push(missing.length >= 6
      ? 'Six missing (L)/(R) columns means this is still the v1 layout — run migrateToKcnt1v2().'
      : 'Check the header row for typos or stray spaces.');
  }

  // How many rows survive the Alive / Role gate? An empty result is usually
  // this, not a broken filter.
  if (sheet.getLastRow() > 1 && present['Mouse ID']) {
    const data = sheet.getDataRange().getValues();
    const cId = headers.indexOf('Mouse ID');
    const cAlive = headers.indexOf('Alive');
    const cRole = headers.indexOf('Role');
    let withId = 0, alive = 0, eligible = 0;

    for (let r = 1; r < data.length; r++) {
      if (!data[r][cId]) continue;
      withId++;
      if (cAlive !== -1 && String(data[r][cAlive]).trim().toLowerCase() !== 'yes') continue;
      alive++;
      if (cRole !== -1 && String(data[r][cRole]).trim().toLowerCase() !== 'stock') continue;
      eligible++;
    }

    lines.push('');
    lines.push('Rows with a Mouse ID:       ' + withId);
    lines.push('  ...of those, Alive = Yes: ' + alive);
    lines.push('  ...of those, Role = Stock: ' + eligible + '   <- the search pool');
    if (eligible === 0) {
      lines.push('');
      lines.push('Nothing passes the gate, so every search returns empty. Check the ' +
                 'Alive and Role columns — the values must read exactly "Yes" and "Stock".');
    }
  }

  ui.alert('Find Mice 2.0 — Diagnosis', lines.join('\n'), ui.ButtonSet.OK);
}
