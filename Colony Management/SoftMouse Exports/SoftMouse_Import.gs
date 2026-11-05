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
 * SOFTMOUSE SYNC: The core processing function.
 * Maps M### to ###, dynamically extracts Genotype data from inside parentheses, 
 * and updates Role, YH, SST, and PV columns.
 */
function processSoftMouseImport(targetDateStr) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const softSheet = ss.getSheetByName('SoftMouse Imports');

  if (!softSheet) {
    throw new Error('Could not find a sheet named "SoftMouse Imports".');
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
  
  // Loop through SoftMouse rows
  for (let r = 1; r < softData.length; r++) {
    let rawTag = String(softData[r][tagColIdx]).trim();
    if (!rawTag) continue;
    
    // Clean the ID: Removes "M" and any dashes so "M-089" and "M089" both become "089"
    let parsedMouseId = rawTag.replace(/^M-?/i, '').trim();
    
    let state = String(softData[r][stateColIdx]).trim();
    let rawGeno = String(softData[r][genoColIdx]).trim();
    
    // Dynamic Genotype Parsing
    let yhVal = "";
    let pvVal = "";
    let sstVal = "";
    
    if (rawGeno) {
      // These Regex patterns look for the gene name and capture whatever text is inside the parentheses ()
      let yhMatch = rawGeno.match(/YH\s*\(([^)]+)\)/i);
      let pvMatch = rawGeno.match(/PV-Cre\s*\(([^)]+)\)/i);
      let sstMatch = rawGeno.match(/SST-Cre\s*\(([^)]+)\)/i);
      
      // If a match is found, assign the captured text (e.g., "WT", "Het", "Hom"). Otherwise, leave blank.
      if (yhMatch) yhVal = yhMatch[1].trim();
      if (pvMatch) pvVal = pvMatch[1].trim();
      if (sstMatch) sstVal = sstMatch[1].trim();
    }
    
    importMap[parsedMouseId] = {
      state: state,
      yh: yhVal,
      pv: pvVal,
      sst: sstVal
    };
  }
  
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
  if (numRows <= 1) return 'No data to process.';
  
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
  
  let matchCount = 0;
  
  // Helper to cleanly assign a value or write "N/A"
  function applyGenoData(valsArray, colorsArray, stylesArray, rowIndex, incomingValue) {
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
    
    if (importMap.hasOwnProperty(masterMouseId)) {
      const importData = importMap[masterMouseId];
      
      // Update Role (State) — but NEVER overwrite a manually-set "Mating" status.
      // Mating is hard-coded by hand on the Active sheet and must be preserved.
      const currentRole = String(kcnt1Data[r][roleIdx] || "").trim().toLowerCase();
      if (importData.state && currentRole !== 'mating') {
          roleVals[dataIndex][0] = importData.state;
      }
      
      // Update Genotypes dynamically
      applyGenoData(yhVals, yhColors, yhStyles, dataIndex, importData.yh);
      applyGenoData(pvVals, pvColors, pvStyles, dataIndex, importData.pv);
      applyGenoData(sstVals, sstColors, sstStyles, dataIndex, importData.sst);
      
      matchCount++;
    }
  }
  
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
  
  SpreadsheetApp.getUi().alert(
    `SoftMouse Sync Complete!\n\nSheet: ${targetName}\n\n` +
    `Successfully matched and updated ${matchCount} active mice profiles.`);
  return 'Success';
}