//Code_v2.gs
/**
 * CALENDAR SYNC v2 — for "KCNT1 Active 2.0"
 * =========================================
 * Replaces Code.gs entirely. Delete the old file; do not run both.
 *
 * WHAT CHANGED FROM v1
 *
 * 1. COMPLETENESS GATE. An activity only reaches the calendar when its Date,
 *    Time AND Lead are all filled in and the Time actually parses. A row with a
 *    date but no time creates nothing — there are no all-day events any more.
 *
 * 2. RED / BLACK STATUS COLOURING. The Date, Time and Lead cells of each
 *    activity are coloured to show sync state at a glance:
 *       RED   - started but incomplete. Nothing is on the calendar.
 *       BLACK - either untouched, or complete and successfully synced.
 *    Colouring only ever touches Date/Time/Lead cells, so the grey italic N/A
 *    styling on YH/SST/PV and the Notes formatting are left alone.
 *
 * 3. DUPLICATE PREVENTION. Five separate fixes, see the block comments below:
 *    a document lock, a calendar-scan fallback before any create, per-event
 *    change fingerprints, the completeness gate, and per-row sync writes.
 *
 * 4. QUIET UPDATES. Editing a cell no longer rewrites every calendar event for
 *    that mouse. An event is only touched when its own details changed.
 *
 * 5. SELF-HEALING AFTER A VANISHED EVENT. A sync entry that points at an event
 *    which is no longer on the calendar — deleted by hand, or resurrected by a
 *    CTRL+Z that undid the script's own cleanup — no longer wedges the activity
 *    permanently off the calendar. See FIX 6 in coreProcessV2 and the note on
 *    getEventByIdSafe_: an ID that still resolves is NOT proof the event is
 *    there, because Google keeps deleted events retrievable by ID.
 *
 * SETUP
 *   - Set V2_NOTIFY_EMAILS below.
 *   - Install an EDIT trigger pointing at onEditSync (Triggers > Add Trigger >
 *     onEditSync > From spreadsheet > On edit). A simple trigger will not work,
 *     because CalendarApp needs authorisation.
 *   - Run resyncAllRows() once after deploying to colour the whole sheet.
 */

// =============================================================================
// CONFIG
// =============================================================================

/** Sheets this script is allowed to sync. Anything containing "archive" is ignored. */
const V2_SHEET_NAMES = ['KCNT1 Active 2.0', 'KCNT1 Active'];

/** Who gets invited to newly created events. Blank entries are ignored. */
const V2_NOTIFY_EMAILS = ['', ''];

const V2_CALENDAR_ID = 'primary';

/** The three recording modalities, each split into (L) and (R) columns. */
const V2_RECORDING_BASES = ['H3 probe', 'H10 probe', 'H10 opto'];

/**
 * THE THREE COLOURS.
 *
 *   RED     started but incomplete. Nothing is on the calendar.
 *   ORANGE  an already-synced activity was edited and the update is pending.
 *           Clears itself once the update lands.
 *   (none)  synced, or never started.
 *
 * The synced state CLEARS the font colour rather than forcing black. Forcing an
 * explicit #000000 fought whatever styling the column already had, which is how
 * imported rows ended up looking wrong — and if a column's own styling was light
 * on white, invisible. Removing the colour lets the cell fall back to the
 * sheet's own formatting, whatever that happens to be.
 */
const V2_COLOR_INCOMPLETE = '#cc0000';  // red    - not on the calendar
const V2_COLOR_PENDING    = '#e8710a';  // orange - update queued
const V2_COLOR_SYNCED     = null;       // null   - clear it, inherit the sheet

/**
 * How long to sit on an edit before pushing the update, in milliseconds.
 *
 * Entering an activity means touching three cells — date, then time, then lead —
 * and each one fires the trigger. Without a pause the first keystroke-commit
 * would fire an update, then the second, then the third, emailing every guest
 * three times for one edit.
 *
 * So an edit to an already-synced activity paints the block ORANGE, waits, and
 * only then writes to the calendar. If another edit to the same block arrives
 * during the wait, this run bows out and the newer one takes over — so the timer
 * restarts rather than stacking. Whoever ends up last turns the block black.
 */
const V2_PENDING_DELAY_MS = 7500;

/**
 * A CANCELLATION cannot be shown with a font colour, because clearing an
 * activity leaves three empty cells and there is no text left to colour. So a
 * pending delete gets a background FILL instead, and it sits there until the
 * calendar event is actually gone.
 *
 * IT OVERRIDES WHATEVER WAS THERE, AND PUTS IT BACK. An earlier version simply
 * skipped any cell that already had a fill, so that the culled-mouse row
 * shading could not be destroyed — but that meant precisely the shaded rows
 * showed no indicator at all. Instead the original colour is stashed in the
 * document cache before the orange goes on, and restored when the orange comes
 * off. Nothing is lost and every block gets the indicator.
 *
 * The stash has a TTL comfortably longer than the pending wait. If it ever does
 * expire — the script dying between painting and clearing is the only realistic
 * way — the fallback is to clear the fill, which is the old behaviour: the
 * indicator goes, and a shaded cell would need re-shading by hand. That is the
 * one failure mode, and it costs a colour rather than data.
 */
const V2_FILL_PENDING_DELETE = '#f6b26b';   // orange fill - deletion queued

/** Backgrounds that mean "no fill", so restoring should clear rather than set. */
const V2_FILL_EMPTY = ['#ffffff', '', null];

/** How long the original background is remembered while the orange is showing. */
const V2_BG_STASH_TTL = 600;

/**
 * PRUNING, AND THE ONE THING THAT MUST NOT GO WRONG.
 *
 * This calendar also holds ordinary lab scheduling that has nothing to do with
 * the sheet. Pruning must never touch those, so "is this event ours?" is decided
 * by a single hard gate: the title has to end in "(Mouse ID: something)".
 *
 * Every event this script has ever created is titled
 *     "<activity> - <lead> (Mouse ID: <id>)"
 * because coreProcessV2 appends that suffix unconditionally. Nothing typed by
 * hand for a lab meeting looks like that. An event that fails this test is not
 * examined, not counted, and not deleted — no exceptions and no heuristics.
 *
 * Tightening it further is available: with V2_PRUNE_REQUIRE_MAUVE on, an event
 * must ALSO still carry the colour the script sets. Safer, but it will miss
 * events somebody has recoloured by hand.
 */
const V2_OURS_PATTERN = /\(Mouse ID:\s*[^)]+\)\s*$/;
const V2_PRUNE_REQUIRE_MAUVE = false;

/** How far either side of today to sweep when pruning. */
const V2_PRUNE_BACK_DAYS    = 730;   // two years of history
const V2_PRUNE_FORWARD_DAYS = 365;   // a year ahead

/** Refuse to run rather than mass-delete if the sweep looks implausible. */
const V2_PRUNE_MAX_DELETE = 200;

/**
 * The nag that goes on a red cell. Shows on hover, and as a toast the first time
 * a block goes red in a session.
 */
const V2_RED_NOTE =
  '🚨 THIS CELL IS RED AND IT IS QUIETLY JUDGING YOU 🚨\n\n' +
  'PLEASE give every event a DATE, a TIME and a LEAD, in a format a human or a\n' +
  'computer can read. All three. Every time.\n\n' +
  'ESTIMATES ARE WELCOME. "2:00 PM - 3:00 PM" with a shrug is data.\n' +
  'NEVER LEAVE THEM BLANK. A blank cell is a riddle for future-you to solve at\n' +
  '11pm with no notes and no witnesses.\n\n' +
  '"I will put the time in later" is how this sheet acquired four hundred rows\n' +
  'of UNDOCUMENTED. Nobody went back. Nobody ever goes back.\n\n' +
  'The calendar cannot schedule vibes. 🐭';

/**
 * Events older than this many days are created silently, with no invitation
 * emailed out. Backfilling historical data should not spam anybody.
 */
const V2_SILENT_AFTER_DAYS = 7;

/**
 * When one activity changes, every OTHER event for that mouse has a stale
 * timeline in its description. Setting this true refreshes them all on every
 * edit, which is accurate but chatty — it is the "every tiny edit updates
 * everything" behaviour that caused trouble in v1. Left false, descriptions are
 * refreshed only by resyncAllRows(), and a normal edit touches just the one
 * event you actually changed.
 */
const V2_REFRESH_SIBLING_DESCRIPTIONS = false;

/**
 * Historical backlog control.
 *
 * Most old records have a date but no time — they were logged after the fact,
 * and nobody needs a calendar event for a perfusion that happened last year.
 * With this left null, EVERY incomplete activity goes red, which on the current
 * sheet is roughly 400 cells.
 *
 * Set it to a number of days to leave the backlog alone: any activity dated
 * more than that many days ago is treated as archived — shown black, never
 * red, and never sent to the calendar. Activities from the cutoff forward are
 * held to the full Date+Time+Lead rule. 30 is a sensible starting point.
 *
 * An unreadable DATE is always flagged red regardless, because a cell reading
 * "UNDOCUMENTED" cannot be placed in time at all.
 */
const V2_BACKLOG_GRACE_DAYS = null;

/**
 * Moving a date or swapping a lead makes Google email every guest an "Updated
 * invitation". In a lab where two people are on every event, that is a lot of
 * noise for a routine reschedule.
 *
 * Set this true to route updates through the Advanced Calendar Service with
 * sendUpdates:'none', which changes the event silently. It requires one setup
 * step: in the Apps Script editor, Services > + > Google Calendar API > Add,
 * with the identifier left as "Calendar". If the service is not enabled the
 * code notices and quietly falls back to CalendarApp, so turning this on
 * without doing the setup step is harmless — it just will not take effect.
 *
 * New events always notify, regardless of this setting. It only affects edits.
 */
const V2_USE_ADVANCED_CALENDAR = false;

/**
 * When an activity's Date, Time and Lead are ALL cleared, that is an
 * unambiguous "this is not happening" — so the calendar event is deleted and
 * the sync entry removed. Partially-cleared rows are left alone, because those
 * are usually mid-edit rather than a cancellation.
 */
const V2_DELETE_EVENT_IF_DATE_CLEARED = true;

/**
 * A sync entry can outlive the event it points at, and then nothing brings the
 * event back, because re-typing the same Date, Time and Lead produces the same
 * title and the same times — so the "nothing changed, skip it" shortcut fires
 * and no calendar call is ever made. Two ways to end up there:
 *
 *   - The event is deleted straight from Google Calendar. The sheet never hears
 *     about it and goes on believing the ID is good.
 *
 *   - CTRL+Z. Clearing an activity makes this script delete the event and clear
 *     the sync entry, but that clear is a script write inside your edit, so
 *     undo puts it back. The cells come back, the sync entry comes back, and
 *     the calendar event stays deleted — undo cannot reach Google Calendar.
 *     This is the one that bites, because the restored entry matches the
 *     restored cells perfectly and looks entirely healthy.
 *
 * With this on, the shortcut confirms the event is really on the calendar
 * before taking it, and rebuilds it when it is not.
 *
 * Cost is one or two reads per edited activity, only on the path that would
 * otherwise have done no calendar work at all — so an ordinary edit still
 * touches one or two events rather than nineteen. Turn it off only if that read
 * is genuinely costing you quota; the price is that a vanished event stays
 * vanished until the next resyncAllRows().
 */
const V2_VERIFY_EVENT_ON_SKIP = true;

/**
 * The column this script keeps its event IDs in. Everything depends on it, and
 * looking it up by exact string once meant a single overwritten header cell
 * stopped the whole sync silently — which has happened: a paste landed on it,
 * leaving two "Notes" columns and no sync column, and nothing synced for a day.
 *
 * findSyncColumn_ looks for the name, then the name in any casing, then for the
 * DATA — the JSON blobs are unmistakable — and puts the header back when it
 * finds them. If it genuinely cannot find the column it says so out loud instead
 * of returning quietly.
 */
const V2_SYNC_HEADER = 'Script Sync Data';
const V2_SYNC_SNIFF_ROWS = 400;
const V2_SYNC_SNIFF_MIN = 3;

// =============================================================================
// ENTRY POINTS
// =============================================================================

/**
 * Edit trigger. This is the only thing that normally runs.
 *
 * It works out which activity block the edited cell belongs to and syncs ONLY
 * that block. Editing the Time on a Headplate touches the Headplate event and
 * nothing else — the other eighteen activities for that mouse are not looked
 * at, not re-coloured and never sent to the Calendar API. An edit outside any
 * activity block (Notes, Mouse ID, a genotype) does no calendar work at all.
 */
function onEditSync(e) {
  if (!e || !e.range) return;

  const sheet = e.range.getSheet();
  if (!isSyncableSheet_(sheet)) return;

  const range = e.range;
  const rowStart = range.getRow();
  const rowCount = range.getNumRows();

  // Header-only edit.
  if (rowStart + rowCount - 1 < 2) return;

  const headers = readHeaderRow_(sheet);
  if (findSyncColumn_(sheet, headers) === -1) { reportMissingSyncColumn_(sheet); return; }

  // Stamp Last Edited, but never in response to our own stamp.
  const lastEditedIndex = headers.indexOf('Last Edited');
  const colStart = range.getColumn();
  const colEnd = colStart + range.getNumColumns() - 1;
  if (lastEditedIndex !== -1 &&
      !(colStart <= lastEditedIndex + 1 && colEnd >= lastEditedIndex + 1)) {
    sheet.getRange(rowStart, lastEditedIndex + 1).setValue(new Date());
  }

  // Which columns were touched?
  const editedCols = [];
  for (let c = colStart - 1; c <= colEnd - 1; c++) editedCols.push(c);

  // Which activity blocks do those columns belong to? If none, we are done —
  // this is the early exit that keeps unrelated edits completely free.
  const blocks = collectActivityBlocks_(headers);
  const targetBlocks = blocks.filter(function (blk) {
    return [blk.dateCol, blk.timeCol, blk.leadCol,
            blk.sessionsCol, blk.doubleInjCol]
      .some(function (c) { return c !== -1 && editedCols.indexOf(c) !== -1; });
  });

  if (targetBlocks.length === 0) return;

  const scope = { rowStart: Math.max(rowStart, 2), rowCount: rowCount, blocks: targetBlocks };

  // ---- THE PENDING WINDOW ----
  // Editing an activity that is ALREADY on the calendar means Google will email
  // every guest an "Updated invitation". Entering a change touches three cells,
  // so without a pause that is three emails for one edit.
  //
  // So: paint the block orange, wait, then update. If another edit to the same
  // row lands during the wait, this run stands down and the newer one carries
  // on — the timer restarts instead of stacking, and only the last edit writes.
  //
  // The wait happens HERE, before coreProcessV2 takes the document lock.
  // Sleeping inside the lock would block every other edit trigger for the whole
  // delay and serialise them, which defeats the debounce entirely.
  // EVERY row in the edit, not just the first. This used to be gated on
  // rowCount === 1, which meant selecting two rows and pressing Delete skipped
  // the whole pending window — no orange at all, and the events went straight
  // out. Clearing several mice at once is a completely normal thing to do, so
  // it gets the same treatment as clearing one.
  const firstRow = Math.max(rowStart, 2);
  const lastEditRow = rowStart + rowCount - 1;

  if (V2_PENDING_DELAY_MS > 0 &&
      anyBlockSynced_(sheet, headers, firstRow, lastEditRow, targetBlocks)) {

    // Two kinds of pending, two ways to show it. A block that still has content
    // gets orange TEXT. A block that has just been cleared has no text to
    // colour, so it gets an orange FILL instead — otherwise a cancellation
    // would show nothing at all for the whole wait.
    const font = [], fill = [];
    for (let r = firstRow; r <= lastEditRow; r++) {
      const p = pendingCells_(sheet, r, targetBlocks);
      p.font.forEach(function (x) { font.push(x); });
      p.fill.forEach(function (x) { fill.push(x); });
    }
    if (font.length) sheet.getRangeList(font).setFontColor(V2_COLOR_PENDING);
    if (fill.length) {
      // Remember what each cell looked like, THEN cover it. The orange goes on
      // regardless of what was underneath — a culled row's shading included —
      // and the clear step puts the original back.
      fill.forEach(function (f) { stashBg_(sheet, f.ref, f.bg); });
      sheet.getRangeList(fill.map(function (f) { return f.ref; }))
           .setBackground(V2_FILL_PENDING_DELETE);
    }
    if (font.length || fill.length) SpreadsheetApp.flush();   // show it now

    const token = claimPending_(sheet, firstRow, lastEditRow);
    Utilities.sleep(V2_PENDING_DELAY_MS);

    if (!stillMine_(sheet, firstRow, lastEditRow, token)) {
      // A newer edit to the same rows arrived while we waited. It owns the
      // update and the colour; leave the orange for it to clear.
      Logger.log('Pending window superseded for rows ' + firstRow + '-' + lastEditRow +
                 '; standing down.');
      return;
    }
  }

  coreProcessV2(scope, sheet, false);
}

/**
 * Does any edited block, on any edited row, already have a calendar event? Only
 * then is there anything to wait for — a brand-new activity has nothing on the
 * calendar to update or delete, so it syncs immediately.
 *
 * Reads the sync column for the whole row span in one call rather than once per
 * row, because this runs on every edit.
 */
function anyBlockSynced_(sheet, headers, firstRow, lastRow, blocks) {
  const syncCol = findCol_(headers, [V2_SYNC_HEADER, 'sync data', 'script sync']);
  if (syncCol === -1) return false;

  const n = lastRow - firstRow + 1;
  if (n < 1) return false;

  const cells = sheet.getRange(firstRow, syncCol + 1, n, 1).getValues();
  for (let i = 0; i < cells.length; i++) {
    let blob;
    try { blob = JSON.parse(String(cells[i][0] || '{}')); } catch (err) { continue; }
    for (let b = 0; b < blocks.length; b++) {
      if (normaliseSyncEntry_(blob[blocks[b].activity]).id) return true;
    }
  }
  return false;
}

/**
 * Splits the edited blocks' date/Time/Lead cells into the ones that should get
 * orange TEXT (still has content — an update is pending) and the ones that
 * should get an orange FILL (fully cleared — a delete is pending, and there is
 * no text left to colour).
 *
 * A cell only joins the fill list if it has no background of its own, so the
 * culled-row highlighting survives.
 */
function pendingCells_(sheet, row, blocks) {
  const font = [], fill = [];
  const width = sheet.getLastColumn();
  if (width < 1) return { font: font, fill: fill };

  // One read of the row's values and one of its backgrounds, rather than two
  // per cell per block. This runs on every edit, so it is worth batching.
  const rowRange = sheet.getRange(row, 1, 1, width);
  const vals = rowRange.getValues()[0];
  const bgs = rowRange.getBackgrounds()[0];

  blocks.forEach(function (b) {
    const cols = [b.dateCol, b.timeCol, b.leadCol].filter(function (c) { return c !== -1; });
    if (!cols.length) return;

    // Is the whole block empty? Then this is a cancellation, not an edit.
    const cleared = cols.every(function (c) {
      return String(vals[c] == null ? '' : vals[c]).trim() === '';
    });

    cols.forEach(function (c) {
      const ref = columnLetterV2_(c + 1) + row;
      if (!cleared) { font.push(ref); return; }
      // Carry the colour that is there now so it can be put back afterwards.
      fill.push({ ref: ref, bg: String(bgs[c] || '').toLowerCase() });
    });
  });

  return { font: font, fill: fill };
}

// ---- remembering a background across the pending window ---------------------
// The orange fill covers whatever was there, so the original has to be kept
// somewhere until it is time to put it back. The document cache is shared
// across trigger invocations and expires by itself, so nothing needs cleaning
// up if a run dies partway.
function bgKey_(sheet, ref) { return 'v2bg:' + sheet.getSheetId() + ':' + ref; }

function stashBg_(sheet, ref, bg) {
  // Never stash our own orange as the "original" — on a second pass that would
  // make the orange permanent, restoring orange over orange forever.
  if (String(bg).toLowerCase() === V2_FILL_PENDING_DELETE) return;
  try {
    const c = CacheService.getDocumentCache();
    if (c) c.put(bgKey_(sheet, ref), bg || '', V2_BG_STASH_TTL);
  } catch (err) { /* no cache: the fallback in restoreBg_ handles it */ }
}

/** Puts the original background back and forgets it. */
function restoreBg_(sheet, ref, cell) {
  let orig = null;
  try {
    const c = CacheService.getDocumentCache();
    if (c) { orig = c.get(bgKey_(sheet, ref)); c.remove(bgKey_(sheet, ref)); }
  } catch (err) { orig = null; }

  if (orig && V2_FILL_EMPTY.indexOf(String(orig).toLowerCase()) === -1 &&
      String(orig).toLowerCase() !== V2_FILL_PENDING_DELETE) {
    cell.setBackground(orig);
    return orig;
  }
  cell.setBackground(null);   // was unfilled, or we never got to stash it
  return null;
}

// A row's pending window is owned by whoever registered last. The token is kept
// in the document cache, which is shared across trigger invocations and expires
// on its own, so nothing has to be cleaned up.
// One token per ROW, so a multi-row delete debounces per row and two people
// editing different rows never cancel each other. A run stands down only if
// every row it was holding has been claimed by something newer.
function pendKey_(sheet, row) { return 'v2pend:' + sheet.getSheetId() + ':' + row; }

function claimPending_(sheet, firstRow, lastRow) {
  const token = String(Date.now()) + ':' + Math.floor(Math.random() * 1e9);
  try {
    const c = CacheService.getDocumentCache();
    if (c) for (let r = firstRow; r <= lastRow; r++) c.put(pendKey_(sheet, r), token, 120);
  } catch (err) { /* no cache: fall through and just do the work */ }
  return token;
}

function stillMine_(sheet, firstRow, lastRow, token) {
  try {
    const c = CacheService.getDocumentCache();
    if (!c) return true;
    for (let r = firstRow; r <= lastRow; r++) {
      const now = c.get(pendKey_(sheet, r));
      if (now === null || now === token) return true;   // at least one row is still ours
    }
    return false;
  } catch (err) { return true; }
}

/**
 * One toast per ten minutes when something is red. Enough to be noticed, not
 * enough to make the sheet unusable.
 */
function nagOnce_(count) {
  try {
    const c = CacheService.getDocumentCache();
    if (c && c.get('v2nag')) return;
    if (c) c.put('v2nag', '1', 600);
    SpreadsheetApp.getActiveSpreadsheet().toast(
      count + ' activity(s) are RED — missing a date, a time or a lead. ' +
      'Estimates are fine. Blanks are not. Hover a red cell for the full lecture. 🐭',
      'Fill in the blanks, please', 8);
  } catch (err) { /* toast is a nicety */ }
}

/**
 * Full-sheet pass. You should not need this day to day — the edit trigger keeps
 * things current on its own. Use it to backfill after first deploying, to
 * refresh every description at once, or to repair the sheet if it and the
 * calendar have drifted apart.
 */
function resyncAllRows() {
  const sheet = getSyncSheet_();
  if (!sheet) {
    SpreadsheetApp.getUi().alert('Could not find a sheet named "' +
      V2_SHEET_NAMES.join('" or "') + '".');
    return;
  }
  const result = coreProcessV2(null, sheet, true);
  SpreadsheetApp.getUi().alert(
    'Resync Complete',
    'Rows scanned: ' + result.rows + '\n' +
    'Activities complete and synced: ' + result.complete + '\n' +
    'Activities incomplete (red): ' + result.incomplete + '\n' +
    'Activities archived backlog: ' + result.archived + '\n' +
    'Events created: ' + result.created + '\n' +
    'Events updated: ' + result.updated + '\n' +
    'Events unchanged (skipped): ' + result.skipped + '\n' +
    'Recovered instead of duplicated: ' + result.adopted + '\n' +
    'Stale copies swept after a move: ' + result.orphansRemoved + '\n' +
    'Cancelled activities removed: ' + result.cancelled,
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

/** Re-checks just the row your cursor is in. Handy for a one-off fix. */
function resyncCurrentRow() {
  const sheet = SpreadsheetApp.getActiveSheet();
  if (!isSyncableSheet_(sheet)) {
    SpreadsheetApp.getUi().alert('This is not the KCNT1 Active sheet.');
    return;
  }
  const row = sheet.getActiveCell().getRow();
  if (row < 2) return;
  const result = coreProcessV2({ rowStart: row, rowCount: 1, blocks: null }, sheet, true);
  SpreadsheetApp.getUi().alert('Row ' + row + ' resynced',
    'Complete: ' + result.complete + '  |  Incomplete: ' + result.incomplete +
    '\nCreated: ' + result.created + '  |  Updated: ' + result.updated +
    '  |  Skipped: ' + result.skipped,
    SpreadsheetApp.getUi().ButtonSet.OK);
}

// =============================================================================
// CORE
// =============================================================================

/**
 * @param scope  null for the whole sheet, or
 *               { rowStart, rowCount, blocks } where `blocks` is the subset of
 *               activity blocks whose calendar events may be written. Pass null
 *               for `blocks` to allow all of them on those rows.
 */
function coreProcessV2(scope, sheet, forceUpdate) {
  const stats = { rows: 0, complete: 0, incomplete: 0, archived: 0,
                  created: 0, updated: 0, skipped: 0, adopted: 0,
                  orphansRemoved: 0, cancelled: 0 };

  // ---------------------------------------------------------------------
  // FIX 1 — THE LOCK.
  // Two edits half a second apart used to start two executions. Both read the
  // same empty syncData, both decided no event existed, and both created one.
  // Serialising removes that race entirely.
  // ---------------------------------------------------------------------
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) {
    Logger.log('Another sync is already running; skipping this pass.');
    return stats;
  }

  try {
    const headers = readHeaderRow_(sheet);
    const syncDataIndex = findSyncColumn_(sheet, headers);
    if (syncDataIndex === -1) { reportMissingSyncColumn_(sheet); stats.noSyncColumn = true; return stats; }
    const mouseIdIndex = headers.indexOf('Mouse ID');
    if (syncDataIndex === -1 || mouseIdIndex === -1) return stats;

    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return stats;

    // Read ONLY the rows in scope. A single-cell edit reads one row, not 220.
    let rowStart = scope ? scope.rowStart : 2;
    let rowCount = scope ? scope.rowCount : (lastRow - 1);
    if (rowStart < 2) { rowCount -= (2 - rowStart); rowStart = 2; }
    if (rowStart + rowCount - 1 > lastRow) rowCount = lastRow - rowStart + 1;
    if (rowCount < 1) return stats;

    const allBlocks = collectActivityBlocks_(headers);

    // Blocks we are allowed to WRITE calendar events for. Every block is still
    // evaluated in memory, because the description needs the whole picture —
    // but evaluation is free and calendar calls are not.
    const writable = (scope && scope.blocks) ? scope.blocks : allBlocks;
    const writableKeys = {};
    writable.forEach(function (b) { writableKeys[b.activity] = true; });

    const calendar = CalendarApp.getCalendarById(V2_CALENDAR_ID);
    const guests = V2_NOTIFY_EMAILS
      .map(function (x) { return String(x).trim(); })
      .filter(function (x) { return x !== ''; })
      .join(',');

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const silentBefore = new Date(today.getTime() - (V2_SILENT_AFTER_DAYS * 86400000));
    const backlogCutoff = (V2_BACKLOG_GRACE_DAYS === null) ? null
      : new Date(today.getTime() - (V2_BACKLOG_GRACE_DAYS * 86400000));

    // One range serves values and font colours, read once and written once.
    const gridRange = sheet.getRange(rowStart, 1, rowCount, headers.length);
    const data = gridRange.getValues();

    // Cells to paint, gathered as A1 refs and applied at the end in three
    // RangeList calls. The synced state CLEARS the colour rather than writing
    // black, and setFontColors() cannot express "no colour" in an array — only
    // setFontColor(null) on a range can — so this collects refs instead of
    // building a colour grid.
    const paintRed = [], paintClear = [], noteRed = [], noteClear = [], clearPendingFill = [];

    for (let i = 0; i < rowCount; i++) {
      const sheetRow = rowStart + i;
      const row = data[i];
      const mouseId = row[mouseIdIndex];
      if (!mouseId) continue;

      stats.rows++;

      let syncData = {};
      try {
        if (row[syncDataIndex]) syncData = JSON.parse(row[syncDataIndex]);
      } catch (err) {
        syncData = {};
      }

      // ---- PASS A: evaluate every block (pure computation, no API calls) ----
      const evaluated = [];

      for (let b = 0; b < allBlocks.length; b++) {
        const blk = allBlocks[b];
        const state = evaluateBlock_(row, blk, backlogCutoff);
        evaluated.push({ blk: blk, state: state });

        // ---- THE COLOUR CONTRACT ----
        // PARTIAL  -> red, and the cell carries the nag note. Not on the
        //             calendar, and the note says why.
        // EMPTY    -> cleared. Nothing started.
        // ARCHIVED -> cleared. Old backlog, deliberately left alone.
        // READY    -> cleared. On the calendar; the sheet's own formatting shows.
        //
        // Only recolour blocks we are responsible for this pass, so an edit to
        // Headplate cannot quietly repaint Perfuse.
        if (writableKeys[blk.activity]) {
          const red = (state.status === 'PARTIAL');

          [blk.dateCol, blk.timeCol, blk.leadCol].forEach(function (c) {
            if (c === -1) return;
            const ref = columnLetterV2_(c + 1) + sheetRow;
            (red ? paintRed : paintClear).push(ref);
          });
          // The note goes on the date cell only — one nag per activity, not three.
          if (blk.dateCol !== -1) {
            (red ? noteRed : noteClear).push(columnLetterV2_(blk.dateCol + 1) + sheetRow);
          }

          // Content is back, so a delete that was pending is off. Retyping
          // during the wait has to take the orange fill away with it.
          if (state.status !== 'EMPTY') {
            [blk.dateCol, blk.timeCol, blk.leadCol].forEach(function (c) {
              if (c !== -1) clearPendingFill.push(columnLetterV2_(c + 1) + sheetRow);
            });
          }

          if (state.status === 'PARTIAL') stats.incomplete++;
          else if (state.status === 'READY') stats.complete++;
          else if (state.status === 'ARCHIVED') stats.archived++;
        }
      }

      let dataChanged = false;

      // ---- CANCELLATION CLEANUP ----
      // An activity whose Date, Time and Lead have all been cleared is being
      // cancelled, not edited. Remove its event and any follow-up it spawned
      // (the Trypsin reminder, the Sucrose swap) so nothing is left stranded
      // on the calendar pointing at work that is no longer happening.
      if (V2_DELETE_EVENT_IF_DATE_CLEARED) {
        for (let k = 0; k < evaluated.length; k++) {
          const ev = evaluated[k];
          if (ev.state.status !== 'EMPTY') continue;
          if (!writableKeys[ev.blk.activity]) continue;

          const activity = ev.blk.activity;

          // ---- TWO-PART ACTIVITIES ----
          // Some activities put TWO events on the calendar: a probe insertion
          // also books "Take probe out of Trypsin (H3 probe (L))" 24h later, and
          // a perfusion books "Replace PFA with Sucrose (Perfuse)". Cancelling
          // the parent has to take the follow-up with it, or the calendar keeps
          // reminding somebody to go and handle a probe that was never placed.
          //
          // The derived keys always end in "(<parent activity>)", so one suffix
          // test catches every one of them however many there are.
          const doomed = Object.keys(syncData).filter(function (key) {
            if (key === activity) return true;
            return key.length > activity.length + 2 &&
                   key.slice(-(activity.length + 2)) === '(' + activity + ')';
          });

          const followUps = doomed.filter(function (k) { return k !== activity; });
          if (followUps.length) {
            Logger.log('Cancelling "' + activity + '" also removes its follow-up(s): ' +
                       followUps.join(', '));
          }

          doomed.forEach(function (key) {
            const e = normaliseSyncEntry_(syncData[key]);
            try {
              let stale = getEventByIdSafe_(calendar, e.id);
              if (!stale && e.t && e.s) stale = findEventOnDay_(calendar, e.t, new Date(e.s));
              if (stale) {
                stale.deleteEvent();
                stats.cancelled++;
              }
            } catch (err) { /* already gone */ }
            delete syncData[key];
            dataChanged = true;
          });

          // The calendar side is settled, so the orange "delete pending" fill
          // has done its job and comes off. Only ours is removed — see the note
          // on V2_FILL_PENDING_DELETE about not eating the culled-row shading.
          [ev.blk.dateCol, ev.blk.timeCol, ev.blk.leadCol].forEach(function (c) {
            if (c !== -1) clearPendingFill.push(columnLetterV2_(c + 1) + sheetRow);
          });
        }
      }

      // Everything below only matters if this mouse has something schedulable.
      if (hasReadyBlock_(evaluated)) {
        // ---- PASS B: the description needs every READY block, not just ours ----
        let allEvents = [];
        for (let k = 0; k < evaluated.length; k++) {
          if (evaluated[k].state.status !== 'READY') continue;
          allEvents = allEvents.concat(
            expandBlockToEvents_(evaluated[k].blk, evaluated[k].state, row));
        }

        const descriptionBase =
          buildDescription_(row, headers, mouseId, evaluated, allEvents);

        // ---- PASS C: but only WRITE the blocks in scope ----
        let mouseEvents = [];
        for (let k = 0; k < evaluated.length; k++) {
          const ev = evaluated[k];
          if (ev.state.status !== 'READY') continue;
          if (!writableKeys[ev.blk.activity]) continue;
          mouseEvents = mouseEvents.concat(
            expandBlockToEvents_(ev.blk, ev.state, row));
        }

        for (let k = 0; k < mouseEvents.length; k++) {
          const ev = mouseEvents[k];

          let eventTitle = ev.activity;
          if (ev.doubleInj) eventTitle += ' [2x]';
          if (ev.lead) eventTitle += ' - ' + ev.lead;
          eventTitle += ' (Mouse ID: ' + mouseId + ')';

          // ---- WHAT WE LAST WROTE ----
          // Storing the title and exact times we last synced (not just a hash of
          // them) means that when something moves we know BOTH where the event
          // is supposed to be and where we left it. That is what makes a date
          // change or a lead change a move/rename instead of a new event.
          const entry = normaliseSyncEntry_(syncData[ev.activity]);
          const descFp = fingerprint_([descriptionBase]);

          const newStartMs = ev.start.getTime();
          const newEndMs = ev.end.getTime();

          const selfChanged = (entry.t !== eventTitle ||
                               entry.s !== newStartMs ||
                               entry.e !== newEndMs);
          const descChanged = (entry.ffp !== descFp);

          // Nothing about this event changed? Then do not call Calendar at all.
          // This is the check that makes per-edit syncing cheap.
          //
          // ---- FIX 6 — A STORED ID IS NOT PROOF THE EVENT STILL EXISTS ----
          // Everything above compares the sheet against what we last WROTE, and
          // says nothing about what is on the calendar now. Delete an event by
          // hand and the sync entry survives it: the title matches, the times
          // match, so this used to skip and the event stayed gone no matter how
          // many times you re-entered the row. Verify before trusting the
          // shortcut, and when the event has vanished drop the dead ID so the
          // resolution ladder below starts from scratch instead of chasing it.
          if (entry.id && !forceUpdate && !selfChanged &&
              (!descChanged || !V2_REFRESH_SIBLING_DESCRIPTIONS)) {
            if (!V2_VERIFY_EVENT_ON_SKIP || getEventByIdSafe_(calendar, entry.id)) {
              stats.skipped++;
              continue;
            }
            Logger.log('Event no longer on the calendar, rebuilding: ' + eventTitle);
            entry.id = null;
          }

          // ---- RESOLUTION LADDER ----
          // Find the one true event before even thinking about creating one.
          const found = resolveEvent_(calendar, entry, eventTitle, ev.start);
          let calEvent = found.event;
          if (found.how === 'previous-location' || found.how === 'new-location') {
            stats.adopted++;
            Logger.log('Recovered event by ' + found.how + ' rather than duplicating: ' + eventTitle);
          }

          if (calEvent) {
            // Move and rename in place. A changed date drags the existing event
            // to its new slot; a changed lead just retitles it. Either way the
            // event keeps its identity, its ID, and its guest list.
            applyEventChanges_(calEvent, eventTitle, ev.start, ev.end, descriptionBase);
            stats.updated++;

            if (selfChanged && entry.s && !sameDay_(new Date(entry.s), ev.start)) {
              // The event changed day. If a stale copy is still sitting at the
              // old date — because the ID lookup had found the new one first —
              // clear it out so the move does not leave a twin behind.
              const swept = sweepOldLocation_(
                calendar, entry.t, new Date(entry.s), calEvent.getId());
              if (swept > 0) {
                stats.orphansRemoved += swept;
                Logger.log('Removed ' + swept + ' stale copy/copies left at the old date.');
              }
            }

          } else {
            // Genuinely new. Only reachable when Date, Time and Lead are all
            // present, so every event created here is timed — never all-day.
            const options = { description: descriptionBase };
            if (guests && ev.start >= silentBefore) {
              options.guests = guests;
              options.sendInvites = true;
            }

            calEvent = calendar.createEvent(eventTitle, ev.start, ev.end, options);
            calEvent.setColor(CalendarApp.EventColor.MAUVE);
            stats.created++;
          }

          syncData[ev.activity] = {
            id: calEvent.getId(),
            t: eventTitle,
            s: newStartMs,
            e: newEndMs,
            ffp: descFp
          };
          dataChanged = true;
        }
      }

      // ---- FIX 5 — WRITE SYNC DATA PER ROW ----
      // v1 accumulated IDs and wrote at the very end. An exception partway
      // through lost every ID created in that pass, and the next run happily
      // recreated all of them. Writing per row bounds the damage to one mouse.
      if (dataChanged) {
        sheet.getRange(sheetRow, syncDataIndex + 1).setValue(JSON.stringify(syncData));
      }
    }

    // ---- APPLY THE PAINT ----
    // Three RangeList calls rather than a write per cell, so a full resync of
    // 220 rows stays fast. setFontColor(null) is the only way to say "no colour,
    // use the sheet's own" — which is the whole point of the synced state.
    if (paintRed.length)   sheet.getRangeList(paintRed).setFontColor(V2_COLOR_INCOMPLETE);
    if (paintClear.length) sheet.getRangeList(paintClear).setFontColor(V2_COLOR_SYNCED);

    // The nag note. Written on red date cells, removed when the block is fixed,
    // and only ever removed if it is OUR note — a note somebody typed by hand
    // must survive.
    noteRed.forEach(function (ref) {
      const cell = sheet.getRange(ref);
      if (cell.getNote() !== V2_RED_NOTE) cell.setNote(V2_RED_NOTE);
    });
    noteClear.forEach(function (ref) {
      const cell = sheet.getRange(ref);
      if (cell.getNote() === V2_RED_NOTE) cell.setNote('');
    });

    // Take the pending-delete fill off and put back whatever it was covering.
    // Only cells still showing OUR orange are touched, so a cell somebody
    // shaded during the wait is left alone.
    if (clearPendingFill.length) {
      const uniq = clearPendingFill.filter(function (v, i, a) { return a.indexOf(v) === i; });
      uniq.forEach(function (ref) {
        const cell = sheet.getRange(ref);
        if (String(cell.getBackground() || '').toLowerCase() !== V2_FILL_PENDING_DELETE) return;
        const back = restoreBg_(sheet, ref, cell);
        if (back) Logger.log('Restored background ' + back + ' on ' + ref + '.');
      });
    }

    if (stats.incomplete > 0) nagOnce_(stats.incomplete);

    Logger.log('Sync pass: ' + JSON.stringify(stats));
    return stats;

  } catch (err) {
    Logger.log('SYNC ERROR: ' + err.message + '\n' + err.stack);
    throw err;
  } finally {
    lock.releaseLock();
  }
}

// =============================================================================
// BLOCK EVALUATION
// =============================================================================

/**
 * Header text to a comparable key: trimmed, inner whitespace collapsed, cased
 * down. Everything that matches a column by name goes through this, so renaming
 * "Double Inj?" to "double inj?" or leaving a trailing space breaks nothing.
 */
function hkey_(h) {
  return String(h == null ? '' : h).replace(/\s+/g, ' ').trim().toLowerCase();
}

/** Find a column by any of several acceptable names. -1 if absent. */
function findCol_(headers, names) {
  const want = names.map(hkey_);
  for (let c = 0; c < headers.length; c++) {
    if (want.indexOf(hkey_(headers[c])) !== -1) return c;
  }
  return -1;
}

/**
 * Columns that trail an activity and belong to it. Matched case-insensitively,
 * so the order of Time / Lead / Sessions inside a block does not matter and
 * adding another trailing attribute needs one entry here, nothing else.
 */
const V2_QUALIFIERS = ['Time', 'Lead', 'Sessions', 'Delayed?', 'Double Inj?',
                       'Initial # of slides', 'Current Slide #'];

/**
 * Scans the header row and returns every activity block: its date column plus
 * whichever qualifiers follow it.
 *
 * WHAT COUNTS AS AN ACTIVITY. A header is an activity only if the very next
 * column is "Time". That one rule replaced a hand-maintained list of columns to
 * ignore, and it is what makes the sheet safe to rearrange.
 *
 * It also fixes the BRAIN BANK section outright. Under the old rule every
 * unrecognised header became a date-only activity with no Time and no Lead,
 * which meant "BRAIN BANK", "Location", "Status" and all four slide-count
 * columns evaluated as PARTIAL the moment you typed in them — six columns that
 * turned red for no reason. None of them is followed by Time, so none of them is
 * an activity now. "Hippocampus Sectioning" and "M2 Sectioning" ARE followed by
 * Time, so they sync like any other activity, and the slide counts ride along as
 * qualifiers of the block they follow.
 */
function collectActivityBlocks_(headers) {
  const isQual = h => V2_QUALIFIERS.map(hkey_).indexOf(hkey_(h)) !== -1;
  const isTime = h => hkey_(h) === 'time';

  const blocks = [];
  for (let i = 0; i < headers.length; i++) {
    if (headers[i] === '' || isQual(headers[i])) continue;
    if (!isTime(headers[i + 1])) continue;        // not an activity — skip it

    const blk = { activity: String(headers[i]).trim(), dateCol: i,
                  timeCol: -1, leadCol: -1, sessionsCol: -1, doubleInjCol: -1,
                  extraCols: [] };

    let k = i + 1;
    while (k < headers.length && isQual(headers[k])) {
      const key = hkey_(headers[k]);
      if (key === 'time' && blk.timeCol === -1) blk.timeCol = k;
      else if (key === 'lead' && blk.leadCol === -1) blk.leadCol = k;
      else if (key === 'sessions' && blk.sessionsCol === -1) blk.sessionsCol = k;
      else if (key === 'double inj?' && blk.doubleInjCol === -1) blk.doubleInjCol = k;
      else blk.extraCols.push({ col: k, label: String(headers[k]).trim() });
      k++;
    }

    blocks.push(blk);
    i = k - 1;
  }

  return blocks;
}

/**
 * The BRAIN BANK block: a banner column with Location and Status beside it.
 * Not an activity — there is nothing to schedule — but it is worth carrying into
 * the event description, because "where is this brain and what state is it in"
 * is exactly what you want on a Sectioning event.
 */
function brainBankCols_(headers) {
  return {
    banner:   findCol_(headers, ['BRAIN BANK', 'Brain Bank']),
    location: findCol_(headers, ['Location']),
    status:   findCol_(headers, ['Status']),
  };
}

/**
 * Decides whether one activity block is EMPTY, PARTIAL or READY.
 *
 * READY requires all three of: a parseable Date, a parseable Time, and a Lead.
 * Anything less than that and the activity never reaches the calendar — which
 * is both the "don't send unless there is a time" rule and the reason a
 * half-entered row can no longer produce a stub event that later gets twinned.
 */
function evaluateBlock_(row, blk, backlogCutoff) {
  const rawDate = blk.dateCol === -1 ? '' : row[blk.dateCol];
  const rawTime = blk.timeCol === -1 ? '' : row[blk.timeCol];
  const rawLead = blk.leadCol === -1 ? '' : row[blk.leadCol];

  const hasDateText = String(rawDate || '').trim() !== '';
  const hasTimeText = String(rawTime || '').trim() !== '';
  const hasLead     = String(rawLead || '').trim() !== '';

  if (!hasDateText && !hasTimeText && !hasLead) {
    return { status: 'EMPTY', missing: [] };
  }

  // Parse the date. Free text like "UNDOCUMENTED" or "yes" fails here, which is
  // deliberate: it goes red so the bad cell is visible.
  let baseDate = null;
  if (rawDate instanceof Date) {
    baseDate = rawDate;
  } else if (hasDateText) {
    const parsed = new Date(rawDate);
    if (!isNaN(parsed.getTime())) baseDate = parsed;
  }

  const times = baseDate ? parseTimeRange(baseDate, rawTime) : null;

  const missing = [];
  if (!baseDate) missing.push(hasDateText ? 'unreadable date' : 'date');
  if (!times)    missing.push(hasTimeText ? 'unreadable time' : 'time');
  if (!hasLead)  missing.push('lead');

  if (missing.length > 0) {
    // Old, dated, and incomplete: this is backlog, not a scheduling gap.
    // Leave it black and off the calendar rather than shouting about it.
    if (backlogCutoff && baseDate && baseDate < backlogCutoff) {
      return { status: 'ARCHIVED', missing: missing, baseDate: baseDate };
    }
    return { status: 'PARTIAL', missing: missing, baseDate: baseDate };
  }

  return {
    status: 'READY',
    missing: [],
    baseDate: baseDate,
    start: times.start,
    end: times.end,
    timeString: rawTime instanceof Date
      ? Utilities.formatDate(rawTime, Session.getScriptTimeZone(), 'h:mm a')
      : String(rawTime).trim(),
    lead: String(rawLead).trim(),
    sessions: blk.sessionsCol === -1 ? '' : String(row[blk.sessionsCol] || '').trim(),
    doubleInj: blk.doubleInjCol !== -1 &&
               (row[blk.doubleInjCol] === true || row[blk.doubleInjCol] === 'TRUE')
  };
}

/** Turns one READY block into its calendar event plus any derived follow-ups. */
function expandBlockToEvents_(blk, state, row) {
  const events = [];
  const tz = Session.getScriptTimeZone();

  // Anything trailing the block that is not Time/Lead/Sessions/Double Inj? —
  // the slide counts on the Sectioning blocks — rides along so it shows on the
  // event rather than being invisible outside the sheet.
  const extras = [];
  (blk.extraCols || []).forEach(function (x) {
    const v = row[x.col];
    if (v === null || v === undefined || String(v).trim() === '') return;
    extras.push(x.label + ': ' + String(v).trim());
  });

  events.push({
    activity: blk.activity,
    start: state.start,
    end: state.end,
    timeString: state.timeString,
    lead: state.lead,
    sessions: state.sessions,
    doubleInj: state.doubleInj,
    extras: extras
  });

  // Trypsin reminder, 24h after any probe insertion. Each hemisphere is its own
  // insertion, so "H3 probe (L)" and "H3 probe (R)" each get one.
  if (isRecordingColumnV2_(blk.activity)) {
    events.push(derivedEvent_(
      'Take probe out of Trypsin (' + blk.activity + ')', state, tz));
  }

  // PFA -> Sucrose swap, 24h after a perfusion.
  if (blk.activity === 'Perfuse') {
    events.push(derivedEvent_(
      'Replace PFA with Sucrose (' + blk.activity + ')', state, tz));
  }

  return events;
}

function derivedEvent_(name, state, tz) {
  const start = new Date(state.start.getTime());
  start.setDate(start.getDate() + 1);
  const end = new Date(start.getTime() + (30 * 60 * 1000));

  return {
    activity: name,
    start: start,
    end: end,
    timeString: Utilities.formatDate(start, tz, 'h:mm a') + ' - ' +
                Utilities.formatDate(end, tz, 'h:mm a'),
    lead: state.lead,
    sessions: '',
    doubleInj: false,
    extras: []
  };
}

// =============================================================================
// DESCRIPTION
// =============================================================================

function buildDescription_(row, headers, mouseId, evaluated, mouseEvents) {
  const idx = function (name) { return headers.indexOf(name); };
  const fmt = function (d) {
    if (!(d instanceof Date)) return d;
    return (d.getMonth() + 1) + '/' + d.getDate() + '/' + d.getFullYear();
  };

  const dobVal = row[idx('DOB')];

  let out = 'Mouse ID: ' + mouseId + '\n' +
            'Cage ID: ' + (row[idx('Cage ID')] || 'N/A') + '\n' +
            'Sex: ' + (row[idx('Sex')] || 'N/A') + '\n' +
            'DOB: ' + (dobVal instanceof Date ? fmt(dobVal) : (dobVal || 'N/A')) + '\n' +
            'Age: ' + (row[idx('Age')] || 'N/A') + '\n' +
            'Genotype (YH/SST/PV): ' + (row[idx('YH')] || '-') + ' / ' +
              (row[idx('SST')] || '-') + ' / ' + (row[idx('PV')] || '-') + '\n' +
            'Role: ' + (row[idx('Role')] || 'N/A') + '\n' +
            'Alive: ' + (row[idx('Alive')] || 'N/A') + '\n\n';

  out += buildRecordingCoverageV2_(row, headers, fmt) + '\n';
  out += buildBrainBankV2_(row, headers, fmt);

  // Timeline of everything that made it onto the calendar.
  const sorted = mouseEvents.slice().sort(function (a, b) {
    return a.start.getTime() - b.start.getTime();
  });

  out += 'Timeline:\n';
  for (let i = 0; i < sorted.length; i++) {
    const ev = sorted[i];
    let line = '- ' + fmt(ev.start) + ': ' + ev.activity;
    if (ev.timeString) line += ' (' + ev.timeString + ')';
    if (ev.lead) line += ' | Lead: ' + ev.lead;
    if (ev.sessions) line += ' | Sessions: ' + ev.sessions;
    if (ev.extras && ev.extras.length) line += ' | ' + ev.extras.join(' | ');
    if (ev.doubleInj) line += ' [DOUBLE INJECTION]';
    out += line + '\n';
  }

  // And a list of what is being held back, so the gap is visible from the
  // calendar rather than only from the red cells in the sheet.
  const held = evaluated.filter(function (e) { return e.state.status === 'PARTIAL'; });
  if (held.length > 0) {
    out += '\nNOT SCHEDULED — incomplete (shown red in the sheet):\n';
    held.forEach(function (e) {
      out += '- ' + e.blk.activity + ' — missing ' + e.state.missing.join(', ') + '\n';
    });
  }

  return out;
}

/**
 * Brain bank state, for the event description.
 *
 * BRAIN BANK is a banner column with Location and Status beside it. None of the
 * three is an activity — there is nothing to schedule — but on a Sectioning
 * event "where is this brain and what state is it in" is the first thing you
 * want to know, so it rides along in the description. The slide counts belong to
 * their Sectioning block and are picked up as block qualifiers.
 *
 * Emits nothing at all when the whole section is empty, so the description does
 * not grow a blank heading on every event.
 */
function buildBrainBankV2_(row, headers, fmt) {
  const bb = brainBankCols_(headers);
  const val = function (c) {
    if (c === -1) return '';
    const v = row[c];
    if (v === null || v === undefined) return '';
    return (v instanceof Date) ? fmt(v) : String(v).trim();
  };

  const banner = val(bb.banner), loc = val(bb.location), st = val(bb.status);
  if (banner === '' && loc === '' && st === '') return '';

  let out = 'Brain bank:\n';
  if (banner !== '') out += '- Entry: ' + banner + '\n';
  if (loc !== '')    out += '- Location: ' + loc + '\n';
  if (st !== '')     out += '- Status: ' + st + '\n';
  return out + '\n';
}

/** Per-modality left/right completion summary. */
function buildRecordingCoverageV2_(row, headers, fmt) {
  let out = 'Recording coverage:\n';

  for (let i = 0; i < V2_RECORDING_BASES.length; i++) {
    const base = V2_RECORDING_BASES[i];
    const parts = [];

    ['L', 'R'].forEach(function (side) {
      const c = headers.indexOf(base + ' (' + side + ')');
      if (c === -1) { parts.push(side + ' n/a'); return; }

      const v = row[c];
      if (!v || String(v).trim() === '') { parts.push(side + ' PENDING'); return; }

      const sIdx = c + 3;
      const sessions = (headers[sIdx] === 'Sessions')
        ? String(row[sIdx] || '').trim() : '';

      parts.push(side + ' ' + (v instanceof Date ? fmt(v) : String(v).trim()) +
                 ' (' + (sessions || 'no sessions logged') + ')');
    });

    out += '- ' + base + ': ' + parts.join('  |  ') + '\n';
  }

  return out;
}

// =============================================================================
// HELPERS
// =============================================================================

function isRecordingColumnV2_(header) {
  const h = String(header).trim();
  for (let i = 0; i < V2_RECORDING_BASES.length; i++) {
    if (h === V2_RECORDING_BASES[i] + ' (L)' ||
        h === V2_RECORDING_BASES[i] + ' (R)') return true;
  }
  return false;
}

function isSyncableSheet_(sheet) {
  const name = sheet.getName();
  if (name.toLowerCase().indexOf('archive') !== -1) return false;
  return V2_SHEET_NAMES.indexOf(name) !== -1;
}

function getSyncSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  for (let i = 0; i < V2_SHEET_NAMES.length; i++) {
    const s = ss.getSheetByName(V2_SHEET_NAMES[i]);
    if (s) return s;
  }
  return null;
}

function readHeaderRow_(sheet) {
  return sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0]
              .map(function (h) { return String(h).trim(); });
}

/**
 * Locates the sync column three ways, hardest to easiest to break:
 *   1. the header, exactly as it should read
 *   2. the header in any casing or spacing
 *   3. the DATA — and then it PUTS THE HEADER BACK, so a stray paste over that
 *      one cell repairs itself on the next edit instead of silently stopping
 *      every calendar event in the spreadsheet.
 */
function findSyncColumn_(sheet, headers) {
  const byName = findCol_(headers, [V2_SYNC_HEADER, 'sync data', 'script sync']);
  if (byName !== -1) return byName;

  const lastRow = sheet.getLastRow();
  if (lastRow < 2 || headers.length === 0) return -1;

  const rows = Math.min(lastRow - 1, V2_SYNC_SNIFF_ROWS);
  const grid = sheet.getRange(2, 1, rows, headers.length).getValues();

  let bestCol = -1, bestHits = 0;
  for (let c = 0; c < headers.length; c++) {
    let hits = 0;
    for (let r = 0; r < grid.length; r++) if (looksLikeSyncBlob_(grid[r][c])) hits++;
    if (hits > bestHits) { bestHits = hits; bestCol = c; }
  }
  if (bestCol === -1 || bestHits < V2_SYNC_SNIFF_MIN) return -1;

  sheet.getRange(1, bestCol + 1).setValue(V2_SYNC_HEADER);
  Logger.log('The "' + V2_SYNC_HEADER + '" header was missing. Found the data in column ' +
             columnLetterV2_(bestCol + 1) + ' (' + bestHits + ' rows) and restored the header.');
  try {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      'The "' + V2_SYNC_HEADER + '" header had been overwritten. Restored to column ' +
      columnLetterV2_(bestCol + 1) + '; syncing has resumed.', 'Calendar sync repaired', 10);
  } catch (err) {}
  return bestCol;
}

/** A sync cell is JSON of activity -> event id (or the v1 bare string). */
function looksLikeSyncBlob_(v) {
  if (typeof v !== 'string') return false;
  const s = v.trim();
  if (s.charAt(0) !== '{') return false;
  try {
    const blob = JSON.parse(s);
    const keys = Object.keys(blob);
    if (!keys.length) return false;
    const first = blob[keys[0]];
    return typeof first === 'string' || (first && typeof first.id === 'string');
  } catch (err) { return false; }
}

/** Says out loud that the sync is off. Throttled, because edits are frequent. */
function reportMissingSyncColumn_(sheet) {
  const msg = 'No "' + V2_SYNC_HEADER + '" column on "' + sheet.getName() +
              '", and no column that looks like it. Calendar syncing is OFF.';
  Logger.log(msg);
  try {
    const c = CacheService.getDocumentCache();
    if (c && !c.get('v2MissingSync')) {
      c.put('v2MissingSync', '1', 600);
      SpreadsheetApp.getActiveSpreadsheet().toast(msg, 'Calendar sync is NOT running', 15);
    }
  } catch (err) {}
}

/** 1 -> A, 27 -> AA. */
function columnLetterV2_(n) {
  let s = '';
  while (n > 0) { const t = (n - 1) % 26; s = String.fromCharCode(65 + t) + s; n = (n - t - 1) / 26; }
  return s;
}

// =============================================================================
// PRUNE — events on the calendar that the sheet no longer knows about
// =============================================================================

/**
 * Deletes events this script owns that the sheet can no longer account for:
 * a row was deleted, an activity was cleared while the trigger was off, a
 * calendar was restored from a backup.
 *
 * WHAT IT WILL NOT TOUCH. Anything whose title does not end in
 * "(Mouse ID: …)". Your general lab scheduling is invisible to this function —
 * it is not merely skipped at the delete step, it is filtered out before the
 * comparison even happens, and the report tells you how many were ignored so you
 * can confirm that number looks like your other calendar use.
 *
 * HOW "the sheet no longer knows about it" IS DECIDED. Two independent ways to
 * survive, and an event only dies if it fails BOTH:
 *
 *   1. Its event ID appears in some row's Script Sync Data. Actively tracked.
 *   2. Its title and day match an event the sheet currently expects — rebuilt
 *      from every READY block plus the follow-ups they spawn.
 *
 * Rule 2 exists because rule 1 alone is dangerous: sync data has been wiped
 * before (a paste over the column took 47 rows with it), and pruning on ID
 * alone would then delete a pile of perfectly valid events.
 *
 * IT ALWAYS SHOWS YOU FIRST. Nothing is deleted until you confirm a dialog that
 * states the counts, and the full list is written to a "Calendar Prune" tab
 * whether you go ahead or not.
 */
function pruneCalendar() {
  const ui = SpreadsheetApp.getUi();

  try {
    Logger.log('--- PRUNE CALENDAR START ---');
    const sheet = getSyncSheet_();
    if (!sheet) {
      ui.alert('Could not find a sheet named "' + V2_SHEET_NAMES.join('" or "') + '".');
      return;
    }

    const expected = expectedEventKeys_(sheet);
    if (expected.error) { ui.alert('Cannot prune', expected.error, ui.ButtonSet.OK); return; }

    const calendar = CalendarApp.getCalendarById(V2_CALENDAR_ID);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const from = new Date(today.getTime() - V2_PRUNE_BACK_DAYS * 86400000);
    const to   = new Date(today.getTime() + V2_PRUNE_FORWARD_DAYS * 86400000);

    const events = calendar.getEvents(from, to);

    let ignored = 0, keptById = 0, keptByMatch = 0;
    const doomed = [];

    events.forEach(function (ev) {
      const title = ev.getTitle();

      // THE GATE. Not ours -> not our business.
      if (!V2_OURS_PATTERN.test(title)) { ignored++; return; }
      if (V2_PRUNE_REQUIRE_MAUVE) {
        let col = '';
        try { col = String(ev.getColor() || ''); } catch (e) { col = ''; }
        if (col !== String(CalendarApp.EventColor.MAUVE)) { ignored++; return; }
      }

      const id = String(ev.getId());
      if (expected.ids[id] || expected.ids[id.split('@')[0]]) { keptById++; return; }

      const start = ev.getStartTime();
      if (expected.keys[title + '||' + dayKeyV2_(start)]) { keptByMatch++; return; }

      doomed.push({ event: ev, title: title, when: start });
    });

    Logger.log('Prune scan: ' + events.length + ' events, ' + ignored + ' not ours, ' +
               keptById + ' tracked, ' + keptByMatch + ' matched, ' + doomed.length + ' orphaned.');

    prunePreviewSheet_(doomed, {
      scanned: events.length, ignored: ignored, keptById: keptById,
      keptByMatch: keptByMatch, from: from, to: to, applied: false
    });

    if (doomed.length === 0) {
      ui.alert('Nothing to prune',
        'Scanned ' + events.length + ' event(s) between ' + dayKeyV2_(from) + ' and ' +
        dayKeyV2_(to) + '.\n\n' +
        ignored + ' were not ours and were ignored entirely.\n' +
        keptById + ' are tracked in Script Sync Data.\n' +
        keptByMatch + ' match what the sheet expects.\n\n' +
        'Every event this script owns is accounted for.', ui.ButtonSet.OK);
      return;
    }

    if (doomed.length > V2_PRUNE_MAX_DELETE) {
      ui.alert('Refusing to prune — that is too many',
        doomed.length + ' of our events look orphaned, which is more than the ' +
        V2_PRUNE_MAX_DELETE + ' safety limit.\n\nThat usually means the sheet is not in ' +
        'the state you think it is — a wrong tab, a cleared Script Sync Data column, or ' +
        'a filtered view. Read the "Calendar Prune" tab before doing anything, and raise ' +
        'V2_PRUNE_MAX_DELETE only once the list looks right.', ui.ButtonSet.OK);
      return;
    }

    const sample = doomed.slice(0, 12).map(function (d) {
      return '  • ' + dayKeyV2_(d.when) + '  ' + d.title;
    }).join('\n');

    const go = ui.alert('Delete ' + doomed.length + ' orphaned event(s)?',
      'Scanned ' + events.length + ' event(s) from ' + dayKeyV2_(from) + ' to ' + dayKeyV2_(to) + '.\n\n' +
      'NOT OURS, ignored:            ' + ignored + '\n' +
      'Tracked in Script Sync Data:  ' + keptById + '\n' +
      'Match what the sheet expects: ' + keptByMatch + '\n' +
      'ORPHANED, would be deleted:   ' + doomed.length + '\n\n' +
      sample + (doomed.length > 12 ? '\n  …and ' + (doomed.length - 12) + ' more' : '') + '\n\n' +
      'The full list is on the "Calendar Prune" tab. This cannot be undone.\n\nProceed?',
      ui.ButtonSet.YES_NO);

    if (go !== ui.Button.YES) {
      ui.alert('Cancelled', 'Nothing was deleted. The "Calendar Prune" tab shows what ' +
        'would have gone.', ui.ButtonSet.OK);
      return;
    }

    let killed = 0;
    doomed.forEach(function (d) {
      try { d.event.deleteEvent(); killed++; Utilities.sleep(120); }
      catch (err) { Logger.log('Could not delete "' + d.title + '": ' + err.message); }
    });

    prunePreviewSheet_(doomed, {
      scanned: events.length, ignored: ignored, keptById: keptById,
      keptByMatch: keptByMatch, from: from, to: to, applied: true, killed: killed
    });

    Logger.log('--- PRUNE CALENDAR COMPLETE: ' + killed + ' deleted ---');
    ui.alert('Prune Complete',
      'Deleted ' + killed + ' orphaned event(s).\n\n' +
      ignored + ' unrelated event(s) were never touched.\n\n' +
      'See the "Calendar Prune" tab for the record.', ui.ButtonSet.OK);

  } catch (err) {
    Logger.log('PRUNE ERROR: ' + err.message + '\n' + err.stack);
    ui.alert('⚠️ Prune Failed', err.message +
      '\n\n(Check the Apps Script Execution Log for details)', ui.ButtonSet.OK);
  }
}

/**
 * Everything the sheet currently believes should be on the calendar: the event
 * IDs it is tracking, and a title+day key for every event its READY blocks
 * imply — including the Trypsin and Sucrose follow-ups, which are real events
 * and would otherwise look orphaned and be pruned on sight.
 */
function expectedEventKeys_(sheet) {
  const headers = readHeaderRow_(sheet);
  const syncCol = findSyncColumn_(sheet, headers);
  const idCol = findCol_(headers, ['Mouse ID']);
  if (idCol === -1) return { error: 'No "Mouse ID" column on "' + sheet.getName() + '".' };
  if (syncCol === -1) {
    return { error: 'No "' + V2_SYNC_HEADER + '" column on "' + sheet.getName() +
      '". Pruning without it would rely on title matching alone, which is not safe ' +
      'enough to delete on. Restore that column first.' };
  }

  const blocks = collectActivityBlocks_(headers);
  const data = sheet.getDataRange().getValues();
  const ids = {}, keys = {};

  for (let r = 1; r < data.length; r++) {
    const row = data[r];
    const mouseId = row[idCol];
    if (!mouseId) continue;

    // 1. Every ID the sheet is tracking.
    try {
      const blob = JSON.parse(String(row[syncCol] || '{}'));
      Object.keys(blob).forEach(function (k) {
        const e = normaliseSyncEntry_(blob[k]);
        if (e.id) { ids[e.id] = true; ids[String(e.id).split('@')[0]] = true; }
      });
    } catch (err) { /* malformed cell: fall through to title matching */ }

    // 2. Every event the current sheet state implies.
    blocks.forEach(function (blk) {
      const state = evaluateBlock_(row, blk, null);
      if (state.status !== 'READY') return;
      expandBlockToEvents_(blk, state, row).forEach(function (ev) {
        let title = ev.activity;
        if (ev.doubleInj) title += ' [2x]';
        if (ev.lead) title += ' - ' + ev.lead;
        title += ' (Mouse ID: ' + mouseId + ')';
        keys[title + '||' + dayKeyV2_(ev.start)] = true;
      });
    });
  }

  return { ids: ids, keys: keys, error: null };
}

function dayKeyV2_(d) {
  return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
}

function prunePreviewSheet_(doomed, info) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName('Calendar Prune');
  if (!sheet) sheet = ss.insertSheet('Calendar Prune');
  else sheet.clear();

  const rows = [['Status', 'Date', 'Event title', 'Note']];
  const verb = info.applied ? 'DELETED' : 'WOULD DELETE';
  doomed.forEach(function (d) {
    rows.push([verb, dayKeyV2_(d.when), d.title,
      'Ours by title, but neither tracked in Script Sync Data nor matching anything ' +
      'the sheet currently expects.']);
  });
  if (doomed.length === 0) rows.push(['OK', '', '(nothing orphaned)', 'Every event we own is accounted for.']);

  sheet.getRange(1, 1, rows.length, 4).setValues(rows);
  sheet.getRange(1, 1, 1, 4).setFontWeight('bold').setBackground('#f0f0f0');
  sheet.setFrozenRows(1);
  if (doomed.length) {
    sheet.getRange(2, 1, doomed.length, 4)
         .setBackground(info.applied ? '#fce8e6' : '#fef7e0')
         .setFontColor(info.applied ? '#c5221f' : '#b06000');
  }
  [140, 100, 460, 520].forEach(function (w, c) { sheet.setColumnWidth(c + 1, w); });
  sheet.getRange(1, 4, rows.length, 1).setWrap(true);

  const foot = sheet.getRange(rows.length + 2, 1);
  foot.setValue(
    (info.applied ? 'Pruned ' + (info.killed || 0) + ' event(s)' : 'DRY RUN — nothing deleted') +
    '  |  window ' + dayKeyV2_(info.from) + ' to ' + dayKeyV2_(info.to) +
    '  |  scanned ' + info.scanned +
    ', NOT OURS and ignored ' + info.ignored +
    ', tracked ' + info.keptById +
    ', matched the sheet ' + info.keptByMatch +
    ', orphaned ' + doomed.length);
  foot.setFontWeight('bold');
  sheet.activate();
}

// =============================================================================
// FORMATTING REPAIR
// =============================================================================

/**
 * The imports write values without touching formatting, so a cell inherits
 * whatever the row above had — light grey text on white reads as invisible, and
 * an italic date looks like somebody's aside. This puts one rule over the sheet:
 *
 *     "N/A"      grey, italic, left      — deliberately not applicable
 *     anything   default colour, not     — real content, plainly readable
 *     else       italic, left aligned
 *
 * "Default colour" means the colour is CLEARED, not set to black, so a column
 * you have deliberately styled keeps its styling.
 *
 * The sync owns red and orange, so this hands the status colouring back to it
 * on the way out — otherwise a repair would flatten every warning on the sheet.
 */
const V2_NA_COLOR = '#a0a0a0';

function repairSheetFormatting() {
  const ui = SpreadsheetApp.getUi();
  const sheet = getSyncSheet_();
  if (!sheet) {
    ui.alert('Could not find a sheet named "' + V2_SHEET_NAMES.join('" or "') + '".');
    return;
  }

  const lastRow = sheet.getLastRow(), lastCol = sheet.getLastColumn();
  if (lastRow < 2) { ui.alert('Nothing to format.'); return; }

  const values = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();

  const na = [], normal = [];
  for (let r = 0; r < values.length; r++) {
    for (let c = 0; c < lastCol; c++) {
      const v = values[r][c];
      if (v === '' || v === null || v === undefined) continue;
      const ref = columnLetterV2_(c + 1) + (r + 2);
      (String(v).trim().toUpperCase() === 'N/A' ? na : normal).push(ref);
    }
  }

  // RangeList does not like enormous batches, so go in chunks.
  const CHUNK = 400;
  const apply = function (refs, fn) {
    for (let i = 0; i < refs.length; i += CHUNK) fn(sheet.getRangeList(refs.slice(i, i + CHUNK)));
  };

  apply(na, function (rl) {
    rl.setFontColor(V2_NA_COLOR).setFontStyle('italic').setHorizontalAlignment('left');
  });
  apply(normal, function (rl) {
    rl.setFontColor(null).setFontStyle('normal').setHorizontalAlignment('left');
  });
  SpreadsheetApp.flush();

  const res = coreProcessV2(null, sheet, false);

  ui.alert('Formatting Repaired',
    'Sheet: ' + sheet.getName() + '\n\n' +
    'Grey + italic (N/A):        ' + na.length + ' cell(s)\n' +
    'Reset to default + left:    ' + normal.length + ' cell(s)\n\n' +
    'Status colours re-applied: ' + res.incomplete + ' red, ' + res.complete + ' complete.\n\n' +
    'The synced state now CLEARS the font colour rather than forcing black, so ' +
    'your own column styling shows through instead of fighting it.',
    ui.ButtonSet.OK);
}

/** Short stable hash used for change detection. */
function fingerprint_(parts) {
  const bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.MD5, parts.join('||'));
  let hex = '';
  for (let i = 0; i < bytes.length; i++) {
    let b = bytes[i];
    if (b < 0) b += 256;
    hex += (b < 16 ? '0' : '') + b.toString(16);
  }
  return hex.substring(0, 12);
}

/**
 * Normalises whatever is stored against an activity into a predictable shape.
 * Handles the v1 bare-string format and the earlier fingerprint format, so
 * upgrading does not orphan anything already on the calendar.
 */
function normaliseSyncEntry_(sd) {
  if (!sd) return { id: null, t: null, s: null, e: null, ffp: null };
  if (typeof sd === 'string') return { id: sd, t: null, s: null, e: null, ffp: null };
  return {
    id: sd.id || null,
    t: sd.t || null,
    s: sd.s || null,
    e: sd.e || null,
    ffp: sd.ffp || null
  };
}

/**
 * Finds the event this activity refers to, trying hardest before giving up and
 * letting the caller create a new one. Each rung catches a different failure:
 *
 *   1. by stored ID        - the normal path
 *   2. at the OLD location - the ID went stale (event recreated by hand, copied
 *                            calendar, expired ID) but the event is still
 *                            sitting where we last wrote it. This is the rung
 *                            that makes a DATE CHANGE safe: without it, moving
 *                            a date creates a second event and abandons the
 *                            first at the old date.
 *   3. at the NEW location - somebody already made the event by hand, at the
 *                            right time, with the right title. Adopt it rather
 *                            than sitting a duplicate on top of it.
 */
function resolveEvent_(calendar, entry, newTitle, newStart) {
  if (entry.id) {
    const byId = getEventByIdSafe_(calendar, entry.id);
    if (byId) return { event: byId, how: 'id' };
  }

  if (entry.t && entry.s) {
    const atOld = findEventOnDay_(calendar, entry.t, new Date(entry.s));
    if (atOld) return { event: atOld, how: 'previous-location' };
  }

  const atNew = findEventOnDay_(calendar, newTitle, newStart);
  if (atNew) return { event: atNew, how: 'new-location' };

  return { event: null, how: 'none' };
}

/**
 * getEventById, but with "the event is not really there any more" reported as a
 * plain null.
 *
 * A dead ID is not the clean null you would hope for. Google keeps a deleted
 * event retrievable by ID long after the fact, so getEventById hands back a
 * cancelled shell: it still reports its old title and times, and it still
 * accepts setTitle() and setTime() without complaint. None of that puts it back
 * on anybody's calendar. Trusting the lookup is what made a deleted event
 * unrecoverable — the sync entry looked healthy, so the event was never rebuilt,
 * and even a forced resync wrote its updates into a shell nobody can see.
 *
 * The one dependable test is whether the event turns up in a listing of the day
 * it claims to be on. Cancelled events do not. Scanning the day the EVENT
 * reports, rather than the day we last wrote, means an event somebody dragged
 * to a different slot by hand is still correctly seen as alive.
 *
 * Cost is one extra read when the event is alive, and none when the ID has
 * already gone.
 */
function getEventByIdSafe_(calendar, id) {
  if (!id) return null;

  let ev = null;
  try {
    ev = calendar.getEventById(id);
  } catch (err) {
    return null;  // malformed ID, or an ID belonging to another calendar
  }
  if (!ev) return null;

  try {
    const when = ev.getStartTime();
    const dayStart = new Date(when.getTime());
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = new Date(dayStart.getTime() + 86400000);

    // CalendarApp IDs carry an "@google.com" suffix that is not always spelled
    // the same way on both sides of the API, so compare the bare id too.
    const bare = String(id).split('@')[0];
    const live = calendar.getEvents(dayStart, dayEnd);

    for (let i = 0; i < live.length; i++) {
      const liveId = String(live[i].getId());
      if (liveId === id || liveId.split('@')[0] === bare) return ev;
    }
  } catch (err) {
    return null;  // could not read it at all — treat it as gone
  }

  Logger.log('Sync entry points at an event that is no longer on the calendar: ' + id);
  return null;
}

/** Looks for an event with this exact title on this day. */
function findEventOnDay_(calendar, title, day) {
  try {
    const dayStart = new Date(day.getTime());
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = new Date(dayStart.getTime() + 86400000);

    const events = calendar.getEvents(dayStart, dayEnd);
    for (let i = 0; i < events.length; i++) {
      if (events[i].getTitle() === title) return events[i];
    }
  } catch (err) {
    Logger.log('Event scan failed (non-fatal): ' + err.message);
  }
  return null;
}

/**
 * Deletes any copy still sitting at the event's previous date, skipping the
 * event we just updated. Runs only when an activity actually changed day.
 */
function sweepOldLocation_(calendar, oldTitle, oldDay, keepId) {
  if (!oldTitle || !oldDay) return 0;
  let removed = 0;
  try {
    const dayStart = new Date(oldDay.getTime());
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = new Date(dayStart.getTime() + 86400000);

    const events = calendar.getEvents(dayStart, dayEnd);
    for (let i = 0; i < events.length; i++) {
      if (events[i].getId() === keepId) continue;
      if (events[i].getTitle() !== oldTitle) continue;
      events[i].deleteEvent();
      removed++;
      Utilities.sleep(150);
    }
  } catch (err) {
    Logger.log('Old-location sweep failed (non-fatal): ' + err.message);
  }
  return removed;
}

/**
 * Writes the new details onto an existing event.
 *
 * With V2_USE_ADVANCED_CALENDAR on, this goes through the Advanced Calendar
 * Service with sendUpdates:'none', so shuffling a date or swapping a lead does
 * not email everybody an "Updated invitation". CalendarApp has no equivalent
 * control, so the fallback path does notify.
 */
function applyEventChanges_(calEvent, title, start, end, description) {
  if (V2_USE_ADVANCED_CALENDAR &&
      typeof Calendar !== 'undefined' && Calendar.Events) {
    try {
      const tz = Session.getScriptTimeZone();
      // CalendarApp IDs look like "abc123@google.com"; the API wants the bare id.
      const bareId = String(calEvent.getId()).split('@')[0];

      Calendar.Events.patch({
        summary: title,
        description: description,
        colorId: '3', // Grape — matches CalendarApp.EventColor.MAUVE
        start: { dateTime: start.toISOString(), timeZone: tz },
        end:   { dateTime: end.toISOString(),   timeZone: tz }
      }, V2_CALENDAR_ID, bareId, { sendUpdates: 'none' });

      return true;
    } catch (err) {
      Logger.log('Advanced Calendar patch failed, using CalendarApp: ' + err.message);
    }
  }

  calEvent.setTime(start, end);
  calEvent.setTitle(title);
  calEvent.setDescription(description);
  calEvent.setColor(CalendarApp.EventColor.MAUVE);
  return false;
}

function sameDay_(a, b) {
  return a.getFullYear() === b.getFullYear() &&
         a.getMonth() === b.getMonth() &&
         a.getDate() === b.getDate();
}

function parseTimeRange(dateObj, timeVal) {
  if (!timeVal) return null;

  let cleanStr = '';
  if (timeVal instanceof Date) {
    cleanStr = Utilities.formatDate(timeVal, Session.getScriptTimeZone(), 'h:mm a');
  } else {
    cleanStr = timeVal.toString().trim();
  }

  if (cleanStr === '') return null;

  const parts = cleanStr.split('-');
  const startStr = parts[0].trim();
  const endStr = parts.length > 1 ? parts[1].trim() : null;

  const start = new Date(dateObj.getTime());
  const end = new Date(dateObj.getTime());

  function applyTime(d, tStr) {
    const match = tStr.match(/(\d+)(?::(\d+))?\s*(AM|PM)?/i);
    if (match) {
      let hr = parseInt(match[1], 10);
      let min = match[2] ? parseInt(match[2], 10) : 0;
      const ampm = match[3] ? match[3].toUpperCase() : null;

      if (ampm === 'PM' && hr < 12) hr += 12;
      if (ampm === 'AM' && hr === 12) hr = 0;

      d.setHours(hr, min, 0, 0);
      return true;
    }
    return false;
  }

  if (applyTime(start, startStr)) {
    if (endStr && applyTime(end, endStr)) {
      return { start: start, end: end };
    }
    end.setTime(start.getTime() + (60 * 60 * 1000));
    return { start: start, end: end };
  }
  return null;
}

// =============================================================================
// DUPLICATE CLEANUP (for the mess v1 already made)
// =============================================================================

/**
 * Reports calendar events that share a title and a day — the signature of a v1
 * duplicate. Reports only; nothing is deleted. Read the log, then run
 * deleteDuplicateEvents() if the list looks right.
 */
function reportDuplicateEvents() {
  const found = scanForDuplicates_();
  let msg = 'Duplicate groups found: ' + found.length + '\n\n';
  found.slice(0, 25).forEach(function (g) {
    msg += g.count + 'x  ' + g.title + '  (' + g.day + ')\n';
  });
  if (found.length > 25) msg += '\n...and ' + (found.length - 25) + ' more. See the log.';
  Logger.log(msg);
  SpreadsheetApp.getUi().alert('Duplicate Report', msg || 'None found.',
    SpreadsheetApp.getUi().ButtonSet.OK);
}

/**
 * Deletes the extra copies, keeping whichever event is referenced in the
 * sheet's Script Sync Data where possible, and otherwise the oldest.
 */
function deleteDuplicateEvents() {
  const ui = SpreadsheetApp.getUi();
  const found = scanForDuplicates_();
  if (found.length === 0) {
    ui.alert('No duplicates found.');
    return;
  }

  const confirm = ui.alert(
    'Delete duplicates?',
    found.length + ' duplicate group(s) found. One event is kept from each ' +
    'group and the rest are deleted. This cannot be undone.\n\nProceed?',
    ui.ButtonSet.YES_NO
  );
  if (confirm !== ui.Button.YES) return;

  // Which event IDs does the sheet consider canonical?
  const keepIds = {};
  const sheet = getSyncSheet_();
  if (sheet) {
    const headers = readHeaderRow_(sheet);
    const sIdx = headers.indexOf('Script Sync Data');
    if (sIdx !== -1 && sheet.getLastRow() > 1) {
      sheet.getRange(2, sIdx + 1, sheet.getLastRow() - 1, 1).getValues()
        .forEach(function (r) {
          if (!r[0]) return;
          try {
            const blob = JSON.parse(r[0]);
            Object.keys(blob).forEach(function (k) {
              const id = typeof blob[k] === 'string' ? blob[k] : blob[k].id;
              if (id) keepIds[id] = true;
            });
          } catch (e) { /* skip malformed */ }
        });
    }
  }

  let deleted = 0;
  found.forEach(function (g) {
    let kept = false;
    // Prefer to keep an event the sheet already points at.
    const ordered = g.events.slice().sort(function (a, b) {
      const ak = keepIds[a.getId()] ? 0 : 1;
      const bk = keepIds[b.getId()] ? 0 : 1;
      return ak - bk;
    });
    ordered.forEach(function (ev) {
      if (!kept) { kept = true; return; }
      try { ev.deleteEvent(); deleted++; } catch (e) { /* already gone */ }
      Utilities.sleep(150); // stay under the Calendar rate limit
    });
  });

  ui.alert('Cleanup complete', 'Deleted ' + deleted + ' duplicate event(s).',
    ui.ButtonSet.OK);
}

function scanForDuplicates_() {
  const calendar = CalendarApp.getCalendarById(V2_CALENDAR_ID);

  const from = new Date();
  from.setFullYear(from.getFullYear() - 2);
  const to = new Date();
  to.setFullYear(to.getFullYear() + 1);

  const events = calendar.getEvents(from, to);
  const groups = {};

  events.forEach(function (ev) {
    const title = ev.getTitle();
    if (title.indexOf('Mouse ID:') === -1) return; // not ours
    const d = ev.getStartTime();
    const day = d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
    const key = title + '||' + day;
    if (!groups[key]) groups[key] = { title: title, day: day, events: [] };
    groups[key].events.push(ev);
  });

  return Object.keys(groups)
    .map(function (k) {
      return { title: groups[k].title, day: groups[k].day,
               count: groups[k].events.length, events: groups[k].events };
    })
    .filter(function (g) { return g.count > 1; });
}

/** True if any block on this row is complete enough to schedule. */
function hasReadyBlock_(evaluated) {
  for (let i = 0; i < evaluated.length; i++) {
    if (evaluated[i].state.status === 'READY') return true;
  }
  return false;
}