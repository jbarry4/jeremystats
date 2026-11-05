//SoftMouse_Import.gs
/**
 * The onOpen that used to live here has been removed. Dropdown2.0.gs now owns
 * the single onOpen for the whole project, and its Lab Tools menu already
 * points at showSoftMouseDialog below, so nothing is lost.
 *
 * It had to go: Apps Script keeps only ONE onOpen across all files and silently
 * uses whichever loads last. This one was winning, and it built a "Find Mice"
 * menu wired to openFilterDialog / clearSheetFilters — v1 functions that no
 * longer exist once Dropdown.gs is deleted. Clicking Select Filters then failed
 * with "Script function not found: openFilterDialog".
 */

/**
 * SOFTMOUSE SYNC: Scans "SoftMouse Imports" for date-stamped triplets,
 * sorts them by most recent, and opens an HTML dialogue box.
 */
function showSoftMouseDialog() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const softSheet = ss.getSheetByName('SoftMouse Imports');
  
  if (!softSheet) {
    SpreadsheetApp.getUi().alert('Error: Could not find a sheet named "SoftMouse Imports".');
    return;
  }
  
  const headers = softSheet.getDataRange().getValues()[0];
  const dateMap = new Map();
  
  // Regex to find "Physical Tag ######", "State ######", or "Genotype ######"
  const regex = /(Physical Tag|State|Genotype)\s+(\d{6})/i;
  
  // 1. Identify all 6-digit date suffixes in the headers
  headers.forEach(header => {
    const match = String(header).match(regex);
    if (match) {
      const dateStr = match[2]; // The 6 digit string (MMDDYY)
      if (!dateMap.has(dateStr)) {
        dateMap.set(dateStr, { count: 1, raw: dateStr });
      } else {
        dateMap.get(dateStr).count++;
      }
    }
  });
  
  // 2. Filter only dates that have ALL THREE columns (count === 3)
  let validDates = [];
  dateMap.forEach((data, dateStr) => {
    if (data.count >= 3) {
      const mo = parseInt(dateStr.substring(0, 2), 10) - 1;
      const da = parseInt(dateStr.substring(2, 4), 10);
      const yr = 2000 + parseInt(dateStr.substring(4, 6), 10);
      const realDate = new Date(yr, mo, da);
      
      validDates.push({
        raw: dateStr,
        dateObj: realDate,
        label: `${mo + 1}/${da}/${yr}` 
      });
    }
  });
  
  if (validDates.length === 0) {
    SpreadsheetApp.getUi().alert('No matching Physical Tag, State, and Genotype triplets found in SoftMouse Imports.');
    return;
  }
  
  // 3. Sort by most recent date first
  validDates.sort((a, b) => b.dateObj.getTime() - a.dateObj.getTime());
  
  // 4. Build the HTML Dropdown Options
  let optionsHtml = '';
  validDates.forEach(d => {
    optionsHtml += `<option value="${d.raw}">${d.label} (Raw: ${d.raw})</option>`;
  });
  
  // 5. Create the HTML Dialogue UI
  const htmlStr = `
    <!DOCTYPE html>
    <html>
      <head>
        <base target="_top">
        <style>
          body { font-family: Arial, sans-serif; padding: 15px; color: #333; }
          p { font-size: 14px; margin-bottom: 15px; }
          select, button { width: 100%; padding: 10px; margin-bottom: 15px; font-size: 14px; box-sizing: border-box; }
          button { background-color: #2196F3; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
          button:hover { background-color: #0b7dda; }
          .loader { display: none; text-align: center; color: #666; font-style: italic; }
        </style>
      </head>
      <body>
        <p>Select the SoftMouse Date triplet to sync with the KCNT1 Active sheet:</p>
        <select id="dateSelect">
          ${optionsHtml}
        </select>
        <button id="runBtn" onclick="runSync()">Sync SoftMouse Data</button>
        <div id="loader" class="loader">Syncing genotyping data... Please wait...</div>

        <script>
          function runSync() {
            document.getElementById('runBtn').style.display = 'none';
            document.getElementById('loader').style.display = 'block';
            
            const dateStr = document.getElementById('dateSelect').value;
            
            google.script.run
              .withSuccessHandler(function(msg) {
                google.script.host.close();
              })
              .withFailureHandler(function(err) {
                alert('Error: ' + err.message);
                document.getElementById('runBtn').style.display = 'block';
                document.getElementById('loader').style.display = 'none';
              })
              .processSoftMouseImport(dateStr);
          }
        </script>
      </body>
    </html>
  `;
  
  const htmlOutput = HtmlService.createHtmlOutput(htmlStr)
    .setWidth(320)
    .setHeight(200)
    .setTitle('SoftMouse Importer');
    
  SpreadsheetApp.getUi().showModalDialog(htmlOutput, 'SoftMouse Importer');
}

/**
 * SOFTMOUSE SYNC: the menu's import -- the date picked in the dialog, read out
 * of "SoftMouse Imports". The work itself is softMouseSyncCore_, shared with
 * Jarvis (doPost in VOS_Import.gs -> softMouseFromJarvis_ below), so the two
 * ways in can never disagree about what a SoftMouse list means.
 */
function processSoftMouseImport(targetDateStr) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const softSheet = ss.getSheetByName('SoftMouse Imports');

  if (!softSheet) {
    throw new Error('Could not find a sheet named "SoftMouse Imports".');
  }

  // --- 1. BUILD DICTIONARY FROM SOFTMOUSE IMPORTS ---
  const softData = softSheet.getDataRange().getValues();
  const softHeaders = softData[0];

  const tagHeader = "Physical Tag " + targetDateStr;
  const stateHeader = "State " + targetDateStr;
  const genoHeader = "Genotype " + targetDateStr;

  const tagColIdx = softHeaders.indexOf(tagHeader);
  const stateColIdx = softHeaders.indexOf(stateHeader);
  const genoColIdx = softHeaders.indexOf(genoHeader);

  if (tagColIdx === -1 || stateColIdx === -1 || genoColIdx === -1) {
    throw new Error(`Could not find one of the required columns for date ${targetDateStr}.`);
  }

  const importMap = {};
  for (let r = 1; r < softData.length; r++) {
    const rawTag = String(softData[r][tagColIdx]).trim();
    if (!rawTag) continue;
    importMap[softMouseId_(rawTag)] = parseSoftMouseRow_(softData[r][stateColIdx],
                                                          softData[r][genoColIdx]);
  }

  const res = softMouseSyncCore_(importMap, { dryRun: false, label: targetDateStr });

  SpreadsheetApp.getUi().alert(
    `SoftMouse Sync Complete!\n\nSheet: ${res.sheet}\n\n` +
    `Successfully matched and updated ${res.matched} active mice profiles.`);
  return 'Success';
}

/** "M-089" and "M089" both become "089"; "1652" stays "1652". */
function softMouseId_(rawTag) {
  return String(rawTag).trim().replace(/^M-?/i, '').trim();
}

/**
 * The genotype as the master sheet's dropdowns spell it. SoftMouse writes
 * "YH(het)"; the YH / SST / PV dropdowns offer WT, Het, Hom.
 */
function softMouseGeno_(v) {
  const t = String(v || '').trim();
  const canon = { wt: 'WT', het: 'Het', hom: 'Hom' }[t.toLowerCase()];
  return canon || t;
}

/**
 * One SoftMouse mouse: its State and the text inside each gene's brackets,
 * e.g. "YH(WT), SST-Cre(het)" -> yh WT, sst Het, pv "" (written as N/A).
 */
function parseSoftMouseRow_(state, rawGeno) {
  const g = String(rawGeno || '').trim();
  const pick = function (re) { const m = g.match(re); return m ? softMouseGeno_(m[1]) : ''; };
  return {
    state: String(state || '').trim(),
    yh: pick(/YH\s*\(([^)]+)\)/i),
    pv: pick(/PV-Cre\s*\(([^)]+)\)/i),
    sst: pick(/SST-Cre\s*\(([^)]+)\)/i)
  };
}

/**
 * Brings Role, YH, SST and PV in the master sheet in line with one SoftMouse
 * list. Maps M### to ###; a gene SoftMouse does not list is written as N/A.
 *
 * importMap   mouse ID -> { state, yh, pv, sst }
 * opts.dryRun true: change nothing, only say what would change. Jarvis shows
 *             that first, and waits for a person when a genotype the sheet
 *             already knew (WT / Het / Hom) would be replaced or erased.
 *
 * Returns { sheet, matched, changes: [{id, field, from, to}], matingKept: [id],
 *           notInSheet: [id], sheetDuplicates: [{id, rows}] }.
 * Never touches the UI, so it can run from the web app.
 */
function softMouseSyncCore_(importMap, opts) {
  opts = opts || {};
  const dryRun = !!opts.dryRun;
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // Prefers "KCNT1 Active 2.0", falls back to "KCNT1 Active". Shared with the
  // calendar sync so the project has one definition of "the master sheet".
  const kcnt1Sheet = getSyncSheet_();
  if (!kcnt1Sheet) {
    throw new Error('Could not find a sheet named "' + V2_SHEET_NAMES.join('" or "') +
                    '". Sheets in this file: ' +
                    ss.getSheets().map(function (s) { return s.getName(); }).join(', '));
  }

  const targetName = kcnt1Sheet.getName();
  const report = { sheet: targetName, matched: 0, changes: [], matingKept: [],
                   notInSheet: [], sheetDuplicates: [] };

  // --- 2. UPDATE KCNT1 ACTIVE SHEET ---
  const kcnt1Data = kcnt1Sheet.getDataRange().getValues();
  const kcnt1Headers = kcnt1Data[0];

  const getIdx = (name) => kcnt1Headers.indexOf(name);

  const idIdx = getIdx('Mouse ID');
  const roleIdx = getIdx('Role');
  const yhIdx = getIdx('YH');
  const pvIdx = getIdx('PV');
  const sstIdx = getIdx('SST');

  if (idIdx === -1 || roleIdx === -1 || yhIdx === -1 || pvIdx === -1 || sstIdx === -1) {
    const wanted = { 'Mouse ID': idIdx, 'Role': roleIdx, 'YH': yhIdx, 'PV': pvIdx, 'SST': sstIdx };
    const missing = Object.keys(wanted).filter(function (k) { return wanted[k] === -1; });
    throw new Error('Missing column(s) in "' + targetName + '": ' + missing.join(', ') +
                    '. Check the header row for typos or stray spaces.');
  }

  const numRows = kcnt1Data.length;
  if (numRows <= 1) return report;

  // Grab ranges for batch updates
  const roleRange = kcnt1Sheet.getRange(2, roleIdx + 1, numRows - 1, 1);
  const yhRange = kcnt1Sheet.getRange(2, yhIdx + 1, numRows - 1, 1);
  const pvRange = kcnt1Sheet.getRange(2, pvIdx + 1, numRows - 1, 1);
  const sstRange = kcnt1Sheet.getRange(2, sstIdx + 1, numRows - 1, 1);

  let roleVals = roleRange.getValues();
  let yhVals = yhRange.getValues();
  let pvVals = pvRange.getValues();
  let sstVals = sstRange.getValues();

  // Initialize color/style arrays to black/normal rather than reading from the sheet.
  // If we seeded from the sheet, any cell that was previously gray/italic (N/A) and
  // isn't touched in the loop below would carry that stale formatting back on write.
  const blankRow = () => Array(numRows - 1).fill(null).map(() => ['#000000']);
  const blankStyleRow = () => Array(numRows - 1).fill(null).map(() => ['normal']);
  let yhColors   = blankRow();
  let yhStyles   = blankStyleRow();
  let pvColors   = blankRow();
  let pvStyles   = blankStyleRow();
  let sstColors  = blankRow();
  let sstStyles  = blankStyleRow();

  const seen = {};
  const rowsById = {};

  // Helper to cleanly assign a value or write "N/A", saying first what changes.
  function applyGenoData(field, mouseId, valsArray, colorsArray, stylesArray, rowIndex, incomingValue) {
    const next = incomingValue !== "" ? incomingValue : 'N/A';
    const had = String(valsArray[rowIndex][0]).trim();
    if (had !== next) {
      report.changes.push({ id: mouseId, field: field, from: had, to: next });
    }
    if (incomingValue !== "") {
      valsArray[rowIndex][0] = incomingValue;
      colorsArray[rowIndex][0] = '#000000'; // Black text
      stylesArray[rowIndex][0] = 'normal';
    } else {
      valsArray[rowIndex][0] = 'N/A';
      colorsArray[rowIndex][0] = '#a0a0a0'; // Light Gray text
      stylesArray[rowIndex][0] = 'italic';
    }
  }

  for (let r = 1; r < numRows; r++) {
    const dataIndex = r - 1;
    const masterMouseId = String(kcnt1Data[r][idIdx]).trim();

    if (!masterMouseId) continue;
    (rowsById[masterMouseId] = rowsById[masterMouseId] || []).push(r + 1);

    if (importMap.hasOwnProperty(masterMouseId)) {
      const importData = importMap[masterMouseId];
      seen[masterMouseId] = true;

      // Update Role (State) — but NEVER overwrite a manually-set "Mating" status.
      // Mating is hard-coded by hand on the Active sheet and must be preserved.
      const currentRole = String(kcnt1Data[r][roleIdx] || "").trim();
      if (importData.state && currentRole.toLowerCase() !== 'mating') {
        if (currentRole !== importData.state) {
          report.changes.push({ id: masterMouseId, field: 'Role', from: currentRole, to: importData.state });
        }
        roleVals[dataIndex][0] = importData.state;
      } else if (importData.state && importData.state.toLowerCase() !== 'mating') {
        report.matingKept.push(masterMouseId);
      }

      // Update Genotypes dynamically
      applyGenoData('YH', masterMouseId, yhVals, yhColors, yhStyles, dataIndex, importData.yh);
      applyGenoData('PV', masterMouseId, pvVals, pvColors, pvStyles, dataIndex, importData.pv);
      applyGenoData('SST', masterMouseId, sstVals, sstColors, sstStyles, dataIndex, importData.sst);

      report.matched++;
    }
  }

  Object.keys(rowsById).forEach(function (id) {
    if (rowsById[id].length > 1 && importMap.hasOwnProperty(id)) {
      report.sheetDuplicates.push({ id: id, rows: rowsById[id] });
    }
  });
  // SoftMouse knows these and the sheet does not. Nothing is added for them
  // (the VOS census is what adds a mouse), but they are named.
  Object.keys(importMap).forEach(function (id) {
    if (!seen[id]) report.notInSheet.push(id);
  });

  console.log(`--- SOFTMOUSE SYNC ${opts.label || ''}${dryRun ? ' (dry run)' : ''}: ` +
              `${report.matched} matched, ${report.changes.length} change(s) ---`);
  if (dryRun) return report;

  // --- 3. BATCH WRITE TO SPREADSHEET ---
  roleRange.setValues(roleVals);

  yhRange.setValues(yhVals);
  yhRange.setFontColors(yhColors);
  yhRange.setFontStyles(yhStyles);

  pvRange.setValues(pvVals);
  pvRange.setFontColors(pvColors);
  pvRange.setFontStyles(pvStyles);

  sstRange.setValues(sstVals);
  sstRange.setFontColors(sstColors);
  sstRange.setFontStyles(sstStyles);

  return report;
}

/**
 * Jarvis's way in (doPost in VOS_Import.gs, kind "softmouse"). Jarvis reads
 * the live mice out of SoftMouse itself and sends
 *   { stamp: MMDDYY, mode: preview|apply, mice: [{tag, state, genotype}],
 *     block: {headers, rows} }
 * On apply the block goes into "SoftMouse Imports" beside the hand-pasted
 * Physical Tag / State / Genotype ones, then the sync runs.
 */
function softMouseFromJarvis_(body) {
  const stamp = String(body.stamp || '');
  if (!/^\d{6}$/.test(stamp)) throw new Error('stamp must be MMDDYY, got "' + stamp + '"');
  const mice = body.mice || [];
  // A list with almost nobody in it would write N/A over the colony's genotypes.
  if (mice.length < 10) throw new Error('only ' + mice.length + ' mice from SoftMouse; refusing');

  const importMap = {};
  mice.forEach(function (m) {
    const id = softMouseId_(m.tag || '');
    if (id) importMap[id] = parseSoftMouseRow_(m.state, m.genotype);
  });

  const apply = body.mode === 'apply';
  let blockAt = null;
  if (apply && body.block) {
    blockAt = writeJarvisBlock_(stamp, body.block, 'SoftMouse Imports', 'JARVIS_SOFTMOUSE_BLOCKS');
  }
  const res = softMouseSyncCore_(importMap, { dryRun: !apply, label: stamp + ' (Jarvis)' });
  res.ok = true;
  // Jarvis checks this: an older script would read the list as a VOS census.
  res.kind = 'softmouse';
  res.mode = apply ? 'apply' : 'preview';
  res.blockAt = blockAt;
  return res;
}
