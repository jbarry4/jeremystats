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
 * The core processing function. Triggered by the HTML Dialogue.
 */
function processImport(targetDateStr) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const vosSheet = ss.getSheetByName('VOS Imports');

  if (!vosSheet) {
    throw new Error('Could not find a sheet named "VOS Imports".');
  }

  // Prefers "KCNT1 Active 2.0", falls back to "KCNT1 Active". Shared with the
  // calendar sync so the project has one definition of "the master sheet".
  const kcnt1Sheet = getSyncSheet_();
  if (!kcnt1Sheet) {
    throw new Error('Could not find a sheet named "' + V2_SHEET_NAMES.join('" or "') +
                    '". Sheets in this file: ' +
                    ss.getSheets().map(function (s) { return s.getName(); }).join(', '));
  }

  const targetName = kcnt1Sheet.getName();

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
  if (numRows <= 1) return 'No data to process.';
  
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
  
  console.log(`--- INITIATING SYNC FOR VOS CENSUS DATE: ${targetDateStr} ---`);
  
  for (let r = 1; r < numRows; r++) {
    const dataIndex = r - 1; 
    const masterMouseId = String(kcnt1Data[r][kcntIdColIdx]).trim();
    
    if (masterMouseId) {
      trueLastRowIndex = r; // Keep pushing the bottom down as long as we find Mouse IDs
    } else {
      continue; // Skip blank rows
    }
    
    if (importMap.hasOwnProperty(masterMouseId)) {
      processedIds.add(masterMouseId); 
      
      const newCage = importMap[masterMouseId].cage;
      const newDob = importMap[masterMouseId].dob;
      const newSex = importMap[masterMouseId].sex;
      
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
      cageValues[dataIndex][0] = 'RETIRED';
      cageColors[dataIndex][0] = '#a0a0a0'; 
      cageStyles[dataIndex][0] = 'italic';  
      
      retiredCount++;
    }
  }
  
  // --- 3. BATCH WRITE UPDATES TO SPREADSHEET ---
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
  
  SpreadsheetApp.getUi().alert(
    `Sync Complete!\n\n` +
    `Sheet: ${targetName}\n\n` +
    `Successfully updated ${matchCount} active cage cards, DOBs & Sexes.\n` +
    `Marked ${retiredCount} mice as RETIRED.\n` +
    `Appended ${addedCount} new mice to the bottom.\n\n` +
    `(View the Apps Script Execution Log for row-by-row changes).`
  );
  return 'Success';
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
