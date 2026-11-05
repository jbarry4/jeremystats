//VOS_Import.gs
/**
 * VOS CENSUS IMPORTER
 * ===================
 * Reads a date-stamped census block out of "VOS Imports" and syncs it into the
 * master mouse sheet: cage cards, DOBs and sexes for mice still in the colony,
 * "RETIRED" for mice that have dropped off the census, and fresh rows for mice
 * that are new.
 *
 * TARGETS 2.0. The master sheet is resolved through getSyncSheet_() in
 * CalendarSync2.0.gs, which prefers "KCNT1 Active 2.0" and falls back to
 * "KCNT1 Active" — so this keeps working after promoteV2ToActive() renames the
 * sheet. Every column is found by header name, never by position, which is why
 * the migration's reshuffling does not affect the sync itself.
 *
 * The one place layout DOES matter is the formulas written into newly appended
 * rows, which have to be built from column letters. See buildAgeFormulasV2_.
 *
 * The menu entry for this lives in Dropdown2.0.gs (Lab Tools > Sync VOS Census).
 *
 * JARVIS. The same sync can arrive without a CSV: Jarvis (Misc > VOS log in)
 * reads VOS itself and POSTs the rows to doPost below, which previews first
 * and writes only when told to. Both ways run syncCensusCore_, so the menu
 * and Jarvis can never disagree about what a census means.
 */

function showImportDialog() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const vosSheet = ss.getSheetByName('VOS Imports');
  
  if (!vosSheet) {
    SpreadsheetApp.getUi().alert('Error: Could not find a sheet named "VOS Imports".');
    return;
  }
  
  const headers = vosSheet.getDataRange().getValues()[0];
  const dateMap = new Map();
  
  // Regex to find "Extracted Sorting ID", "Cage Card", "DOB", "Date of Birth", or "Sex"
  const regex = /(Extracted Sorting ID|Cage Card|DOB|Date of Birth|Sex)\s+(\d{6})/i;
  
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
  
  // 2. Filter only dates that have at least the primary columns
  let validDates = [];
  dateMap.forEach((data, dateStr) => {
    if (data.count >= 2) {
      // Parse MMDDYY to a real Date object for sorting
      const mo = parseInt(dateStr.substring(0, 2), 10) - 1;
      const da = parseInt(dateStr.substring(2, 4), 10);
      const yr = 2000 + parseInt(dateStr.substring(4, 6), 10);
      const realDate = new Date(yr, mo, da);
      
      validDates.push({
        raw: dateStr,
        dateObj: realDate,
        label: `${mo + 1}/${da}/${yr}` // Format nicely for the dropdown
      });
    }
  });
  
  if (validDates.length === 0) {
    SpreadsheetApp.getUi().alert('No matching date groups found in VOS Imports.');
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
          button { background-color: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
          button:hover { background-color: #45a049; }
          .loader { display: none; text-align: center; color: #666; font-style: italic; }
        </style>
      </head>
      <body>
        <p>Select the Census Date group to sync with the KCNT1 master sheet:</p>
        <select id="dateSelect">
          ${optionsHtml}
        </select>
        <button id="runBtn" onclick="runSync()">Sync Data</button>
        <div id="loader" class="loader">Syncing colony data... Please wait...</div>

        <script>
          function runSync() {
            document.getElementById('runBtn').style.display = 'none';
            document.getElementById('loader').style.display = 'block';
            
            const dateStr = document.getElementById('dateSelect').value;
            
            // Call the server-side processing function
            google.script.run
              .withSuccessHandler(function(msg) {
                google.script.host.close();
              })
              .withFailureHandler(function(err) {
                alert('Error: ' + err.message);
                document.getElementById('runBtn').style.display = 'block';
                document.getElementById('loader').style.display = 'none';
              })
              .processImport(dateStr);
          }
        </script>
      </body>
    </html>
  `;
  
  const htmlOutput = HtmlService.createHtmlOutput(htmlStr)
    .setWidth(320)
    .setHeight(200)
    .setTitle('VOS Census Importer');
    
  SpreadsheetApp.getUi().showModalDialog(htmlOutput, 'VOS Census Importer');
}

/**
 * Helper function to convert a column index (1-based) to a column letter (e.g. 1 -> A, 2 -> B)
 */
function columnToLetter(column) {
  let temp, letter = '';
  while (column > 0) {
    temp = (column - 1) % 26;
    letter = String.fromCharCode(temp + 65) + letter;
    column = (column - temp - 1) / 26;
  }
  return letter;
}

/**
 * Builds the Alive / Age / Age (weeks) formulas for one newly appended row.
 *
 * These used to be simple "DOB to today" formulas, which meant an imported
 * mouse got a different formula from every other row in the column: no
 * "DOD Unknown" for a retired mouse with no recorded death, and an age that
 * kept climbing after the mouse died. This produces the same formula the rest
 * of the column uses.
 *
 * Age stops at the earliest of Perfuse / Euthanize, or today, whichever comes
 * first — so a perfusion scheduled for next week does not freeze the age now.
 * Both column letters are passed in, resolved from the live header row, since
 * the 2.0 migration moved Perfuse from AR to AZ and Euthanize from AV to BC.
 * If either column is absent the formula degrades to counting to today rather
 * than breaking.
 *
 * @param cols {cage, dob, age, perfuse, euth} column LETTERS; age/perfuse/euth
 *             may be null.
 * @param n    the 1-based sheet row these formulas will live on.
 */
function buildAgeFormulasV2_(cols, n) {
  const dob = cols.dob + n;
  const cage = cols.cage + n;

  const deaths = [];
  if (cols.perfuse) deaths.push(cols.perfuse + n);
  if (cols.euth) deaths.push(cols.euth + n);

  // MIN(TODAY(), earliest death date). FILTER returns #N/A when neither cell
  // holds a real date, and the IFERROR turns that into "still alive".
  let endDate = 'TODAY()';
  if (deaths.length > 0) {
    const arr = '{' + deaths.join(',') + '}';
    endDate = 'MIN(TODAY(), IFERROR(MIN(FILTER(' + arr + ', ISNUMBER(' + arr + '))), TODAY()))';
  }

  // A retired mouse with no death date on file cannot have its age computed —
  // say so rather than silently measuring to today.
  let guardOpen = '', guardClose = '';
  if (deaths.length > 0) {
    guardOpen = 'IF(AND(' + cage + '="RETIRED", NOT(OR(' +
      deaths.map(function (d) { return 'ISNUMBER(' + d + ')'; }).join(', ') +
      '))), "DOD Unknown", ';
    guardClose = ')';
  }

  const age =
    '=IFERROR(IF(ISBLANK(' + dob + '), "", ' + guardOpen +
    'LET(endDate, ' + endDate + ', ' +
    'DATEDIF(' + dob + ', endDate, "M") & "m, " & ' +
    'INT(DATEDIF(' + dob + ', endDate, "MD")/7) & "w, " & ' +
    'MOD(DATEDIF(' + dob + ', endDate, "MD"), 7) & "d")' + guardClose + '),"")';

  // Age (weeks) defers to the Age cell for the blank / DOD Unknown decisions,
  // so the two columns can never disagree about whether an age is knowable.
  const ageWeeks = cols.age
    ? '=IFERROR(IF(' + cols.age + n + '="", "", IF(' + cols.age + n + '="DOD Unknown", ' +
      '"DOD Unknown", (' + endDate + ' - ' + dob + ') / 7)), "")'
    : '=IFERROR((' + endDate + ' - ' + dob + ') / 7, "")';

  return {
    alive: '=IF(' + cage + '="RETIRED","No","Yes")',
    age: age,
    ageWeeks: ageWeeks
  };
}

/**
 * The menu's import: the date picked in the dialog, read out of "VOS Imports".
 * The work itself is syncCensusCore_, shared with doPost (Jarvis).
 */
function processImport(targetDateStr) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const vosSheet = ss.getSheetByName('VOS Imports');

  if (!vosSheet) {
    throw new Error('Could not find a sheet named "VOS Imports".');
  }

  // --- 1. BUILD DICTIONARY FROM VOS IMPORTS ---
  const vosData = vosSheet.getDataRange().getValues();
  const vosHeaders = vosData[0];
  
  const idHeader = "Extracted Sorting ID " + targetDateStr;
  const ccHeader = "Cage Card " + targetDateStr;
  const sexHeader = "Sex " + targetDateStr;
  
  // Account for variations in DOB header formatting
  const dobHeader1 = "DOB " + targetDateStr;
  const dobHeader2 = "Date of Birth " + targetDateStr;
  
  const idColIdx = vosHeaders.indexOf(idHeader);
  const ccColIdx = vosHeaders.indexOf(ccHeader);
  const sexColIdx = vosHeaders.indexOf(sexHeader);
  
  let dobColIdx = vosHeaders.indexOf(dobHeader1);
  if (dobColIdx === -1) dobColIdx = vosHeaders.indexOf(dobHeader2);
  
  if (idColIdx === -1 || ccColIdx === -1) {
    throw new Error(`Could not find columns exactly matching '${idHeader}' and '${ccHeader}'. Check for extra spaces.`);
  }
  if (dobColIdx === -1) {
    throw new Error(`Could not find DOB column for date ${targetDateStr}. Expected 'DOB ${targetDateStr}' or 'Date of Birth ${targetDateStr}'.`);
  }
  
  const importMap = {};
  
  // Loop through VOS rows and map ID -> { Cage Card, DOB, Sex }
  for (let r = 1; r < vosData.length; r++) {
    const mouseId = String(vosData[r][idColIdx]).trim();
    const cageCard = String(vosData[r][ccColIdx]).trim();
    const dobValue = vosData[r][dobColIdx]; // Preserved as a raw date object/string
    
    // Grab and Format the Sex Column (Male -> M, Female -> F)
    let sexValue = sexColIdx !== -1 ? String(vosData[r][sexColIdx]).trim() : ''; 
    if (/^male$/i.test(sexValue)) {
      sexValue = 'M';
    } else if (/^female$/i.test(sexValue)) {
      sexValue = 'F';
    }
    
    if (mouseId && mouseId !== "0" && mouseId !== "") {
      importMap[mouseId] = {
        cage: cageCard,
        dob: dobValue,
        sex: sexValue
      };
    }
  }

  const res = syncCensusCore_(importMap, { dryRun: false, label: targetDateStr });

  SpreadsheetApp.getUi().alert(
    `Sync Complete!\n\n` +
    `Sheet: ${res.sheet}\n\n` +
    `Successfully updated ${res.active} active cage cards, DOBs & Sexes.\n` +
    `Marked ${res.retiredAlready + res.newlyRetired.length} mice as RETIRED.\n` +
    `Appended ${res.added.length} new mice to the bottom.\n\n` +
    `(View the Apps Script Execution Log for row-by-row changes).`
  );
  return 'Success';
}

/**
 * Brings the master sheet in line with one census.
 *
 * importMap   mouse ID -> { cage, dob, sex }, from "VOS Imports" (the menu) or
 *             straight from Jarvis (doPost).
 * opts.dryRun true: change nothing, only say what would change. This is what
 *             Jarvis shows before it applies, and how it decides whether a
 *             person has to look first (anyone newly RETIRED).
 *
 * Returns { sheet, active, retiredAlready, newlyRetired: [{id, cage}],
 *           revived: [id], added: [id], changes: [{id, field, from, to}] }.
 * Never touches the UI, so it can run from a web app, where getUi() throws.
 */
function syncCensusCore_(importMap, opts) {
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
  const report = { sheet: targetName, active: 0, retiredAlready: 0, newlyRetired: [],
                   revived: [], added: [], changes: [], held: [], heldMissing: [],
                   sheetDuplicates: [] };
  const tz = ss.getSpreadsheetTimeZone();
  const dateKey = function (v) {
    // Not `instanceof Date`: a Date made in another context fails it.
    if (Object.prototype.toString.call(v) === '[object Date]' && !isNaN(v.getTime())) {
      return Utilities.formatDate(v, tz, 'yyyy-MM-dd');
    }
    return String(v == null ? '' : v).trim();
  };
  const rowsById = {};

  // --- 2. UPDATE EXISTING KCNT1 DATA ---
  const kcnt1Data = kcnt1Sheet.getDataRange().getValues();
  const kcnt1Headers = kcnt1Data[0];
  
  const kcntIdColIdx = kcnt1Headers.indexOf('Mouse ID');
  const kcntCageColIdx = kcnt1Headers.indexOf('Cage ID'); 
  const kcntDobColIdx = kcnt1Headers.indexOf('DOB'); 
  const kcntSexColIdx = kcnt1Headers.indexOf('Sex');
  const kcntAliveColIdx = kcnt1Headers.indexOf('Alive');
  const kcntAgeColIdx = kcnt1Headers.indexOf('Age');
  const kcntAgeWeeksColIdx = kcnt1Headers.indexOf('Age (weeks)');
  
  if (kcntIdColIdx === -1 || kcntCageColIdx === -1 || kcntDobColIdx === -1) {
    throw new Error('Could not find "Mouse ID", "Cage ID", or "DOB" in "' + targetName +
                    '". Check the header row for typos or stray spaces.');
  }
  
  const numRows = kcnt1Data.length;
  if (numRows <= 1) return report;
  
  // Grab the existing formatting so we can batch-overwrite it instantly
  const cageRange = kcnt1Sheet.getRange(2, kcntCageColIdx + 1, numRows - 1, 1);
  const cageValues = cageRange.getValues();
  const cageColors = cageRange.getFontColors();
  const cageStyles = cageRange.getFontStyles();

  const dobRange = kcnt1Sheet.getRange(2, kcntDobColIdx + 1, numRows - 1, 1);
  const dobValues = dobRange.getValues();
  const dobColors = dobRange.getFontColors();
  const dobStyles = dobRange.getFontStyles();
  
  let sexRange, sexValues, sexColors, sexStyles;
  if (kcntSexColIdx !== -1) {
    sexRange = kcnt1Sheet.getRange(2, kcntSexColIdx + 1, numRows - 1, 1);
    sexValues = sexRange.getValues();
    sexColors = sexRange.getFontColors();
    sexStyles = sexRange.getFontStyles();
  }
  
  let matchCount = 0;
  let retiredCount = 0;
  let addedCount = 0;
  const processedIds = new Set(); 
  
  // Find the TRUE last row by checking the Mouse ID column specifically
  let trueLastRowIndex = 0;
  
  console.log(`--- INITIATING SYNC FOR VOS CENSUS: ${opts.label || ''}${dryRun ? ' (dry run)' : ''} ---`);

  for (let r = 1; r < numRows; r++) {
    const dataIndex = r - 1;
    const masterMouseId = String(kcnt1Data[r][kcntIdColIdx]).trim();

    if (masterMouseId) {
      trueLastRowIndex = r; // Keep pushing the bottom down as long as we find Mouse IDs
    } else {
      continue; // Skip blank rows
    }

    const oldCage = String(cageValues[dataIndex][0]).trim();
    (rowsById[masterMouseId] = rowsById[masterMouseId] || []).push(r + 1);

    // Held by Jarvis: VOS disagrees with itself about this mouse (one tag on
    // two cards). It is in the colony, so it is not retired, and its row is
    // left exactly as it is until somebody fixes VOS.
    if (importMap.hasOwnProperty(masterMouseId) && importMap[masterMouseId].hold) {
      processedIds.add(masterMouseId);
      report.held.push(masterMouseId);
      continue;
    }

    if (importMap.hasOwnProperty(masterMouseId)) {
      processedIds.add(masterMouseId);

      const newCage = importMap[masterMouseId].cage;
      const newDob = importMap[masterMouseId].dob;
      const newSex = importMap[masterMouseId].sex;

      // What is about to change, said before it does (Jarvis's preview).
      if (oldCage === 'RETIRED') report.revived.push(masterMouseId);
      if (oldCage !== String(newCage).trim()) {
        report.changes.push({ id: masterMouseId, field: 'Cage ID', from: oldCage, to: newCage });
      }
      if (dateKey(dobValues[dataIndex][0]) !== dateKey(newDob)) {
        report.changes.push({ id: masterMouseId, field: 'DOB',
                              from: dateKey(dobValues[dataIndex][0]), to: dateKey(newDob) });
      }
      if (kcntSexColIdx !== -1 && newSex !== '' &&
          String(sexValues[dataIndex][0]).trim() !== newSex) {
        report.changes.push({ id: masterMouseId, field: 'Sex',
                              from: String(sexValues[dataIndex][0]).trim(), to: newSex });
      }

      // Update Cage
      cageValues[dataIndex][0] = newCage;
      cageColors[dataIndex][0] = '#000000';
      cageStyles[dataIndex][0] = 'normal'; 

      // Update DOB
      dobValues[dataIndex][0] = newDob;
      dobColors[dataIndex][0] = '#000000';  
      dobStyles[dataIndex][0] = 'normal';  

      // Update Sex (if column exists and data was found)
      if (kcntSexColIdx !== -1 && newSex !== '') {
        sexValues[dataIndex][0] = newSex;
        sexColors[dataIndex][0] = '#000000';
        sexStyles[dataIndex][0] = 'normal';
      }

      matchCount++;
    } else {
      if (oldCage === 'RETIRED') {
        report.retiredAlready++;
      } else {
        report.newlyRetired.push({ id: masterMouseId, cage: oldCage });
      }
      cageValues[dataIndex][0] = 'RETIRED';
      cageColors[dataIndex][0] = '#a0a0a0'; 
      cageStyles[dataIndex][0] = 'italic';  
      
      retiredCount++;
    }
  }
  
  report.active = matchCount;
  Object.keys(rowsById).forEach(function (id) {
    if (rowsById[id].length > 1) report.sheetDuplicates.push({ id: id, rows: rowsById[id] });
  });
  // A held mouse the sheet has never had: nothing is added for it, since
  // which cage it is in is the very thing VOS cannot agree on.
  Object.keys(importMap).forEach(function (id) {
    if (importMap[id].hold && !processedIds.has(id)) {
      report.heldMissing.push(id);
      processedIds.add(id);
    }
  });

  // --- 3. BATCH WRITE UPDATES TO SPREADSHEET ---
  // A dry run stops here, apart from naming the mice that would be added.
  if (dryRun) {
    for (const mouseId of Object.keys(importMap)) {
      if (!processedIds.has(mouseId) && (mouseId.match(/\d/g) || []).length >= 2) {
        report.added.push(mouseId);
      }
    }
    return report;
  }

  cageRange.setValues(cageValues);
  cageRange.setFontColors(cageColors);
  cageRange.setFontStyles(cageStyles);

  dobRange.setValues(dobValues);
  dobRange.setFontColors(dobColors);
  dobRange.setFontStyles(dobStyles);
  
  if (kcntSexColIdx !== -1) {
    sexRange.setValues(sexValues);
    sexRange.setFontColors(sexColors);
    sexRange.setFontStyles(sexStyles);
  }
  
  // --- 4. APPEND UNMATCHED IDS (2+ DIGITS) TO THE TRUE BOTTOM ---
  const newRowsToAppend = [];
  const totalColumns = kcnt1Headers.length; 
  
  // Letters for dynamic formula construction (e.g. 2 -> 'B', 9 -> 'I').
  // Resolved from the live headers every run, because the migration moved
  // Perfuse from AR to AZ and Euthanize from AV to BC — hard-coding any of
  // these is exactly how the Age columns ended up reading the opto dates.
  const kcntPerfuseColIdx = kcnt1Headers.indexOf('Perfuse');
  const kcntEuthColIdx = kcnt1Headers.indexOf('Euthanize');

  const formulaCols = {
    cage: columnToLetter(kcntCageColIdx + 1),
    dob: columnToLetter(kcntDobColIdx + 1),
    age: kcntAgeColIdx === -1 ? null : columnToLetter(kcntAgeColIdx + 1),
    perfuse: kcntPerfuseColIdx === -1 ? null : columnToLetter(kcntPerfuseColIdx + 1),
    euth: kcntEuthColIdx === -1 ? null : columnToLetter(kcntEuthColIdx + 1)
  };

  // Start tracking the row numbers where new mice will be inserted
  let nextAvailableRow = trueLastRowIndex + 2; // +1 for 0-index offset, +1 to drop down to the blank row

  for (const [mouseId, data] of Object.entries(importMap)) {
    if (!processedIds.has(mouseId)) {
      
      const digitCount = (mouseId.match(/\d/g) || []).length;
      
      if (digitCount >= 2) {
        addedCount++;
        report.added.push(mouseId);
        console.log(`[ADDED] New Mouse Found: ${mouseId} at Row ${nextAvailableRow}`);
        
        // Build a fresh blank row that aligns with the Active Sheet's true width
        const newRow = new Array(totalColumns).fill('');
        newRow[kcntIdColIdx] = mouseId;
        newRow[kcntCageColIdx] = data.cage;
        newRow[kcntDobColIdx] = data.dob;
        if (kcntSexColIdx !== -1) newRow[kcntSexColIdx] = data.sex;
        
        // Dynamically create the formulas for this specific row, matching what
        // the rest of the column already does.
        const f = buildAgeFormulasV2_(formulaCols, nextAvailableRow);
        if (kcntAliveColIdx !== -1) newRow[kcntAliveColIdx] = f.alive;
        if (kcntAgeColIdx !== -1) newRow[kcntAgeColIdx] = f.age;
        if (kcntAgeWeeksColIdx !== -1) newRow[kcntAgeWeeksColIdx] = f.ageWeeks;

        newRowsToAppend.push(newRow);
        nextAvailableRow++; // Increment for the next loop
      }
    }
  }

  // Write appended rows safely to the TRUE bottom of the sheet based on Mouse IDs
  if (newRowsToAppend.length > 0) {
    const insertRowStart = trueLastRowIndex + 2;
    const dest = kcnt1Sheet.getRange(insertRowStart, 1, newRowsToAppend.length, totalColumns);

    // ---- FORMAT THE NEW ROWS BEFORE FILLING THEM ----
    // setValues() writes values and nothing else, so an appended mouse landed in
    // virgin cells with none of the sheet's formatting: no column shading, the
    // wrong date format, and — most visibly — no dropdown on Alive, because the
    // data validation range stopped at the old last row. Copying an existing row
    // first gives the new rows the same clothes as every other row.
    stampRowFormatV2_(kcnt1Sheet, insertRowStart, newRowsToAppend.length,
                      totalColumns, trueLastRowIndex + 1, kcntIdColIdx);

    dest.setValues(newRowsToAppend);
  }
  
  console.log(`--- SYNC COMPLETE: ${matchCount} Active | ${retiredCount} Retired | ${addedCount} Added ---`);
  return report;
}

/* ==========================================================================
   JARVIS: the census straight from VOS, no CSV pasted
   ==========================================================================
   Jarvis (Misc > VOS log in) reads the active X6-041 cages out of VOS, prints
   their cards to PDF, runs VOS_report_parser.py on them and POSTs the rows
   here. Same importer as the menu, so the master sheet cannot tell the two
   apart.

   mode "preview"  changes nothing; answers what WOULD change.
   mode "apply"    writes the date-stamped block into "VOS Imports" (so the
                   history is kept the way the hand-made ones are) and runs
                   the sync.

   SET UP ONCE: Deploy > New deployment > Web app, Execute as: Me, Who has
   access: Anyone. Paste the /exec URL into Jarvis. The first call Jarvis
   makes leaves its secret in Script Properties (JARVIS_SECRET); every call
   after that must carry it. To hand the link to a new machine, run
   resetJarvisSecret() and let that machine call first.
*/
function doPost(e) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(120000)) {
    return jarvisJson_({ ok: false, error: 'another sync is running in the sheet; try again in a minute' });
  }
  try {
    const body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    checkJarvisSecret_(body.secret);

    const stamp = String(body.stamp || '');
    if (!/^\d{6}$/.test(stamp)) throw new Error('stamp must be MMDDYY, got "' + stamp + '"');
    const mice = body.mice || [];
    // A census with almost nobody in it would mark the colony RETIRED.
    // Jarvis checks this too; the sheet does not take its word for it.
    if (mice.length < 10) throw new Error('only ' + mice.length + ' mice in the census; refusing');

    const importMap = {};
    mice.forEach(function (m) {
      const id = String(m.id || '').trim();
      if (!id || id === '0') return;
      if (m.hold) { importMap[id] = { hold: true }; return; }
      let sex = String(m.sex || '').trim();
      if (/^(m|male)$/i.test(sex)) sex = 'M';
      else if (/^(f|female)$/i.test(sex)) sex = 'F';
      importMap[id] = { cage: String(m.cage || '').trim(), dob: jarvisDate_(m.dob), sex: sex };
    });

    const apply = body.mode === 'apply';
    let blockAt = null;
    if (apply && body.block) blockAt = writeJarvisBlock_(stamp, body.block);
    const res = syncCensusCore_(importMap, { dryRun: !apply, label: stamp + ' (Jarvis)' });
    res.ok = true;
    res.mode = apply ? 'apply' : 'preview';
    res.blockAt = blockAt;
    return jarvisJson_(res);
  } catch (err) {
    return jarvisJson_({ ok: false, error: err.message });
  } finally {
    lock.releaseLock();
  }
}

function jarvisJson_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function checkJarvisSecret_(secret) {
  const props = PropertiesService.getScriptProperties();
  const known = props.getProperty('JARVIS_SECRET');
  if (!secret) throw new Error('no secret sent');
  if (!known) {
    props.setProperty('JARVIS_SECRET', String(secret));
    return;
  }
  if (known !== String(secret)) throw new Error('wrong secret');
}

/** Run by hand to let a different machine's Jarvis claim the web app. */
function resetJarvisSecret() {
  PropertiesService.getScriptProperties().deleteProperty('JARVIS_SECRET');
}

/** '2025-09-14' -> a Date at local midnight, as a pasted CSV would become. */
function jarvisDate_(text) {
  const m = String(text || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return String(text || '');
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

/**
 * The census as a date-stamped block in "VOS Imports", beside the hand-made
 * ones. A second sync on the same day writes over Jarvis's own block for
 * that day (remembered in Document Properties), never over a pasted one.
 * Returns the 1-based column the block starts at.
 */
function writeJarvisBlock_(stamp, block) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName('VOS Imports');
  if (!sheet) throw new Error('Could not find a sheet named "VOS Imports".');
  const headers = block.headers || [];
  const rows = (block.rows || []).map(function (r) {
    return headers.map(function (_, i) { return r[i] == null ? '' : r[i]; });
  });
  const width = headers.length;
  if (!width) throw new Error('the block has no columns');

  const props = PropertiesService.getDocumentProperties();
  const known = JSON.parse(props.getProperty('JARVIS_VOS_BLOCKS') || '{}');

  let start = known[stamp];
  if (start && String(sheet.getRange(1, start).getValue()) !== headers[0]) start = null;
  if (start) {
    const old = Math.max(sheet.getLastRow(), 1);
    sheet.getRange(1, start, old, width).clearContent();
  } else {
    start = sheet.getLastColumn() + 1;
  }

  const needCols = start + width - 1 - sheet.getMaxColumns();
  if (needCols > 0) sheet.insertColumnsAfter(sheet.getMaxColumns(), needCols);
  const needRows = rows.length + 1 - sheet.getMaxRows();
  if (needRows > 0) sheet.insertRowsAfter(sheet.getMaxRows(), needRows);

  sheet.getRange(1, start, 1, width).setValues([headers]);
  if (rows.length) sheet.getRange(2, start, rows.length, width).setValues(rows);

  known[stamp] = start;
  props.setProperty('JARVIS_VOS_BLOCKS', JSON.stringify(known));
  return start;
}

/**
 * Gives freshly appended rows the same formatting as the rest of the sheet.
 *
 * WHY THIS IS NEEDED. setValues() writes values and touches nothing else, so an
 * appended mouse arrives in cells that have never been styled: white where the
 * column is shaded, the default date format instead of the sheet's, and no
 * dropdown on Alive — the data validation range simply ended at the previous
 * last row. That is what makes imported animals look alien next to the rest.
 *
 * WHICH ROW IS COPIED. The last real data row, walking upwards past any row that
 * carries a background of its own. Culled mice are marked with a full-row
 * highlight, and copying one of those would paint every newly imported mouse as
 * culled — which would be a great deal worse than the formatting being plain.
 *
 * Data validation is applied separately and explicitly. copyTo's formatOnly is
 * about appearance, and the dropdown is the single most visible thing missing;
 * it is not worth leaving to chance.
 */
function stampRowFormatV2_(sheet, startRow, numRows, numCols, lastDataRow, idColIdx) {
  const templateRow = pickFormatTemplateRowV2_(sheet, lastDataRow, idColIdx);
  if (!templateRow) return;

  const template = sheet.getRange(templateRow, 1, 1, numCols);

  // Appearance: fill, borders, font, number formats.
  for (let i = 0; i < numRows; i++) {
    template.copyTo(sheet.getRange(startRow + i, 1, 1, numCols), { formatOnly: true });
  }

  // Dropdowns, explicitly. This is the one that was actually missing.
  try {
    const rules = template.getDataValidations()[0];
    const block = [];
    for (let i = 0; i < numRows; i++) block.push(rules.slice());
    sheet.getRange(startRow, 1, numRows, numCols).setDataValidations(block);
  } catch (err) {
    console.log('Could not copy data validation from row ' + templateRow + ': ' + err.message);
  }

  console.log('Formatted rows ' + startRow + '-' + (startRow + numRows - 1) +
              ' from template row ' + templateRow + '.');
}

/**
 * The nearest row above that is not specially shaded, so an imported mouse never
 * inherits the culled-row highlight. Falls back to the last data row if every
 * candidate is shaded.
 */
function pickFormatTemplateRowV2_(sheet, lastDataRow, idColIdx) {
  if (lastDataRow < 2) return null;
  const floor = Math.max(2, lastDataRow - 60);
  for (let r = lastDataRow; r >= floor; r--) {
    const bg = String(sheet.getRange(r, idColIdx + 1).getBackground() || '').toLowerCase();
    if (bg === '' || bg === '#ffffff') return r;
  }
  return lastDataRow;
}
