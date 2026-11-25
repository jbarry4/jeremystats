"""Build the KCNT1 active-avoidance file -> mouse map workbook."""
import os, re, json, datetime, collections, sys
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment

HERE = os.path.dirname(os.path.abspath(__file__))
AA = r"C:\Users\Z390\Desktop\jeremystats\KCNT1 Active Avoidance\DATA AND ARCHIVE"
DATA = os.path.join(AA, "active_avoidance_data")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out.xlsx")

H = json.load(open(os.path.join(HERE, "headers.json")))
S = json.load(open(os.path.join(HERE, "sources.json"), encoding="utf-8"))
SRC, NOTES, AADATES, BOOK = S["src"], S["notes"], S["aa_dates"], S["book_files"]
BOOK_NORM = {k.strip(): v for k, v in BOOK.items()}

TBL = os.path.join(DATA, "KCNT1_2026", "analysis_output_112326", "TBLfiles", "march26_thru_nov2026.tbl")
ANALYZED_1123 = set()
for line in open(TBL, encoding="latin-1").read().splitlines()[1:]:
    t = line.split("\t")[0].strip()
    if t.lower().endswith(".dat"):
        ANALYZED_1123.add(t)


def when(r):
    d, m, y = r["date"].split(".")
    t = datetime.datetime.strptime(r["time"], "%I:%M %p")
    return datetime.datetime(int(y), int(m), int(d), t.hour, t.minute)


# ---------------------------------------------------------------------------------------------
# 1. what each file is
# ---------------------------------------------------------------------------------------------
# kind values
AA_RUN = "AA session"
ABORT = "Aborted start (not usable)"
SHORT = "Short session"
REPEAT0 = "Repeat s0 (day-2 habituation)"
PILOT = "Pilot, Feb 2024 (shocks not working)"
SCRAP = "Scrapped run, Jul 2024 (redone Oct 2024)"
HABIT = "Habituation only (no AA run)"
PACER = "Pacer mouse"
TRAIN = "Training only"
TEST = "Tracker test, no mouse"
DUP = "Duplicate copy"
BROKE = "Incomplete run (apparatus broke)"
EXTRA = "Extra session beyond s16"

# (folder, file) -> (mouse, session, kind, name_issue, confidence, evidence)
OVR = {
    ("KCNT1_2026", "2645s4_091826.dat"): ("1645", 4, AA_RUN, "Mouse number typed as 2645, no M prefix", "Inferred",
        "Recorded 13:21 in 1645's slot (1637 and 1645 alternated all day); 1645 has no other s4."),
    ("KCNT1_2026", "M1564s7_091826.dat"): ("1645", 7, AA_RUN, "Mouse number typed as 1564 (no such AA mouse)", "Inferred",
        "Recorded 14:46 in 1645's slot between 1637 s7 and 1637 s8; 1645 has no other s7."),
    ("KCNT1_2026", "M2645s9_091926.dat"): ("1645", 9, AA_RUN, "Mouse number typed as 2645", "Inferred",
        "Started 11:12, the same minute as M1645s9_091926.dat, which stopped after 4.9 s; this is the full 10-min 1645 s9."),
    ("KCNT1_2026", "M1645s9_091926.dat"): ("1645", 9, ABORT, "", "Filename",
        "Stopped after 4.9 s and restarted as M2645s9_091926.dat."),
    ("KCNT1_2026", "M1637091926.dat"): ("1637", 13, AA_RUN, "Session number left out of the name", "Inferred",
        "Recorded 12:40 in 1637's slot between 1645 s12 and 1645 s13; 1637 has no other s13."),
    ("KCNT1_2026", "m1637s3_091826.dat"): ("1637", 3, AA_RUN, "Lower-case m", "Filename", ""),
    ("KCNT1_2026", "M1644s_102926.dat"): ("1644", 13, AA_RUN, "Session number left out of the name", "Inferred",
        "Recorded 10:00 in 1644's slot between 1649 s12 and 1649 s13; 1644 has no other s13."),
    ("KCNT1_2026", "31653s13_111326.dat"): ("1653", 13, AA_RUN, "Mouse number typed as 31653, no M prefix", "Inferred",
        "Recorded 13:16 in 1653's slot between 1659 s12 and 1659 s13; 1653 has no other s13."),
    ("KCNT1_2026", "M251s15_032826.dat"): ("521", 15, AA_RUN, "Mouse number typed as 251 (digits swapped)", "Inferred",
        "Recorded 11:57 in 521's slot (521 and 529 alternated); 521 has no other s15. The AA outputs workbook also reads it as 521."),
    ("KCNT1_2026", "M259s15_032826.dat"): ("529", 15, AA_RUN, "Mouse number typed as 259 (digits swapped)", "Inferred",
        "Recorded 12:12 in 529's slot; 529 has no other s15. The AA outputs workbook also reads it as 529."),
    ("KCNT1_2026", "M520s9_031926.dat"): ("520", 8, AA_RUN, "Named s9 but it is s8", "Inferred",
        "Recorded day 1 (3/19) between 527 s7 and 527 s8; 520 has no s8 and a separate s9 on 3/20. The AA outputs workbook also scores it as session 8."),
    ("KCNT1_2026", "M520s5031926.dat"): ("520", 5, AA_RUN, "Underscore missing before the date", "Filename", ""),
    ("KCNT1_2026", "M527s1_032726.dat"): ("529", 1, AA_RUN, "Named 527, but 527 ran a week earlier (3/19-3/20)", "Inferred",
        "Started 08:56, one minute after M529s1_032726.dat stopped at 36 s, and before 521 s2: this is 529's s1 re-run. The AA outputs workbook scores it as 527 session '1????'."),
    ("KCNT1_2026", "M529s1_032726.dat"): ("529", 1, ABORT, "", "Filename",
        "Stopped after 36 s; re-run at 08:56 under the name M527s1_032726.dat."),
    ("KCNT1_2026", "M576s0_041036.dat"): ("576", 0, AA_RUN, "Year typed as 36 (041036)", "Filename", "Header date is 2026-04-10."),
    ("KCNT1_2026", "TRAINING_M560S0_030226.dat"): ("560", 0, TRAIN, "", "Filename", "Behaviour sheet: 03/02/26 s0 (AA Training)."),
    ("KCNT1_2026", "M560s0_031126.dat"): ("560", 0, TRAIN, "", "Filename", "6.2-min s0; no other 560 AA files. Lab Ops has no AA date for 560."),
    ("KCNT1_2026", "RoomTrack_Room.dat"): (None, None, TEST, "Tracker default name, no mouse", "None",
        "31 s on 2026-11-21 09:15, four minutes before 1656 s9; a false start."),
    ("KCNT1_DM_Feb24", "M416H1March13.dat"): ("416", 0, AA_RUN, "Named H1 (habituation) rather than s0", "Filename",
        "Behaviour sheet: 416 s0-s8 on 3/13. The AA outputs workbook calls it M416s0March13."),
    ("KCNT1_DM_Feb24", "M418H1March13.dat"): ("418", 0, ABORT, "Named H1", "Filename", "Stopped after 7.8 s."),
    ("KCNT1_DM_Feb24", "M417H1March13.dat"): ("418", 0, AA_RUN, "Named 417, but 417 ran 3/30-3/31", "Inferred",
        "Recorded 14:50 right after 418's 7.8-s false start; only 416 and 418 ran that day (Behaviour sheet: 418 s0-s8 3/13). Its entries/shocks match the AA outputs workbook's row M418s0March13."),
    ("KCNT1_DM_Feb24", "M417H1March15.dat"): ("419", 0, AA_RUN, "Named 417 H1, but 417's s0 is 3/30", "Inferred",
        "Behaviour sheet: 419 habituation 3/15/24, then 3/30-3/31; no 419 file exists for 3/15 otherwise. Its entries/shocks match the AA outputs workbook's row M419s0March15."),
    ("KCNT1_DM_Feb24", "M419s15March30.dat"): ("419", 15, AA_RUN, "Date in name says March30; recorded March 31", "Filename", "Header date 2024-03-31."),
    ("KCNT1_DM_Feb24", "M415s3April3.dat"): ("415", 3, AA_RUN, "Date in name says April3; recorded April 13", "Filename", "Header date 2024-04-13."),
    ("KCNT1_DM_Feb24", "M811s0March30.dat"): ("811", 0, HABIT, "", "Filename",
        "Behaviour sheet: 811 'habituation 3/30/24'. Lab Ops: headplate practice mouse, no AA."),
    ("KCNT1_DM_Feb24", "M894May13s0.dat"): ("894", 0, AA_RUN, "Session after the date (May13s0)", "Filename", ""),
    ("KCNT1_DM_Feb24", "M457s0July18 - Copy.dat"): ("457", 0, DUP, "Windows copy", "Filename", "Byte-identical to M457s0July18.dat."),
    ("KCNT1_DM_Feb24", "M459s0July19t.dat"): ("459", 0, REPEAT0, "Stray t after the date", "Filename",
        "Behaviour sheet: day 2 began with s0 again for 457-460."),
    ("KCNT1_DM_Feb24", "M462S3July16.dat"): ("462", 3, SCRAP, "", "Filename", "Re-run of s3 after M462s3July16.dat stopped at 2.8 s."),
    ("KCNT1_DM_Feb24", "ArenaTrack_Arena.dat"): (None, None, TEST, "Tracker default name, no mouse", "None", "36 s on 2025-10-06."),
    ("KCNT1_DM_Feb24", "RoomTrack_Room.dat"): (None, None, TEST, "Tracker default name, no mouse", "None", "36 s on 2025-10-06."),
    ("KCNT1_DM_Feb24", "M1S0_ArenaTrack_Arena_20251007_114827.dat"): (None, None, TEST, "'M1' is not a colony mouse", "None",
        "4.5 min on 2025-10-07, no KCNT1 AA scheduled then."),
    ("KCNT1_DM_Feb24", "M1S0_RoomTrack_Room_20251007_114827.dat"): (None, None, TEST, "'M1' is not a colony mouse", "None",
        "4.5 min on 2025-10-07, no KCNT1 AA scheduled then."),
    ("KCNT1_DM_Sep24", "RoomTrack_Room.dat"): (None, None, TEST, "Tracker default name, no mouse", "None",
        "5 s, recorded 2026-10-07 although it sits in the Sep 2024 folder."),
    ("KCNT1_DM_Sep24", "testRoomTrack_Room.dat"): (None, None, TEST, "Test file", "None", "68 s, 2024-09-18, zero path."),
    ("KCNT1_HH_ER_July24", "RoomTrack_Room.dat"): (None, None, TEST, "Tracker default name, no mouse", "None",
        "4 s on 2024-07-16 between 461 s4 and 462 S3."),
}


def parse_name(fn):
    m = re.match(r"^(?:TRAINING_)?[Mm](\d+)[sSH](\d+)", fn)
    if m:
        return m.group(1), int(m.group(2))
    m = re.match(r"^M(\d+)(?:May|March|April|July)\d+s(\d+)", fn)
    if m:
        return m.group(1), int(m.group(2))
    return None, None


files = []
for r in H:
    w = when(r)
    key = (r["folder"], r["file"])
    dur = int(r["elapsed_ms"]) / 1000.0
    if key in OVR:
        mouse, ses, kind, issue, conf, ev = OVR[key]
    else:
        mouse, ses = parse_name(r["file"])
        kind, issue, conf, ev = AA_RUN, "", "Filename", ""
        if r["file"][0] == "m":
            issue = "Lower-case m"
    fn = r["file"]
    if kind == AA_RUN and mouse:
        if w.date() in (datetime.date(2024, 2, 28), datetime.date(2024, 2, 29)):
            kind = PILOT
            ev = ev or "Behaviour sheet: Feb 2024 sessions ran with shocks not working ('more like habituations')."
            if "RoomTrack" in fn:
                issue = issue or "Tracker default name kept after the mouse ID"
            if fn.startswith("M872S1,2"):
                issue = "Two session numbers in one name (S1,2)"
            if fn.startswith("M894S02"):
                issue = "Session written S02"
        elif w.date() == datetime.date(2024, 7, 16):
            if mouse in ("461", "462"):
                kind = SCRAP
                ev = ev or "Behaviour sheet: July runs scrapped (461 s3 overwritten); Mia re-ran both 10/2-10/3/24."
            elif mouse in ("464", "466"):
                kind = HABIT
                ev = "Behaviour sheet: s0 only on 7/16/24; no further AA files."
            elif mouse == "816":
                kind = PACER
                ev = "Lab Ops and Behaviour sheet: 816 was the pacer."
        elif mouse in ("457", "458", "459", "460") and ses == 0 and w.date() == datetime.date(2024, 7, 19):
            kind = REPEAT0
            ev = "Behaviour sheet: s0-s8 normal, next day habituation (s0 again), then s9-16."
        elif mouse in ("1647", "1648"):
            kind = BROKE
            ev = "Lab Ops cell note on 1647: 'Active avoidance apparatus broke! Cannot finish experiment.' No later AA files for 1647 or 1648."
        elif ses is not None and ses > 16:
            kind = EXTRA
            ev = "Day 2 has 9 files (s9-s17) where the protocol has 8 (s9-s16); which one is the extra is not recorded."
        if "OCT" in fn and "RoomTrack" in fn and not issue:
            issue = ""  # the Sep 2024 folder's naming convention, consistent within the folder
    if kind in (AA_RUN, REPEAT0, SCRAP, EXTRA) and dur < 60:
        kind = ABORT
        ev = ev or "Stopped after %.1f s." % dur
    if kind == AA_RUN and dur < 590:
        kind = SHORT
        ev = (ev + " " if ev else "") + "Ran %.1f min of the usual 10." % (dur / 60)
    if kind == PILOT and dur < 590:
        ev += " Ran %.1f min." % (dur / 60)
    book = BOOK_NORM.get(fn)
    files.append(dict(folder=r["folder"], file=fn, when=w, dur=dur, path=float(r["path_m"]), mouse=mouse,
                      session=ses, kind=kind, issue=issue, conf=conf, ev=ev.strip(),
                      in_book=("Yes (as mouse %s, session %s)" % (book["mouse"], book["session"])) if book else "",
                      in_1123=("Yes" if fn in ANALYZED_1123 else ("" if r["folder"] == "KCNT1_2026" else "n/a (2026 folder only)"))))

# day numbers + main-run dates per mouse
by_mouse = collections.defaultdict(list)
for f in files:
    if f["mouse"]:
        by_mouse[f["mouse"]].append(f)
run_dates = {}
for m, fs in by_mouse.items():
    main = sorted({f["when"].date() for f in fs if f["kind"] in (AA_RUN, SHORT, REPEAT0, EXTRA, BROKE)})
    s1 = sorted(f["when"].date() for f in fs if f["kind"] in (AA_RUN, SHORT, BROKE) and f["session"] == 1)
    run_dates[m] = dict(dates=main, s1=(s1[0] if s1 else (main[0] if main else None)))
for f in files:
    rd = run_dates.get(f["mouse"], {})
    dates = [d for d in (rd.get("dates") or []) if rd.get("s1") is None or d >= rd["s1"]]
    if f["kind"] in (AA_RUN, SHORT, REPEAT0, EXTRA, BROKE) and f["when"].date() in dates:
        f["day"] = dates.index(f["when"].date()) + 1
    elif f["kind"] in (AA_RUN, SHORT) and rd.get("s1") and f["when"].date() < rd["s1"]:
        f["day"] = "earlier"
    else:
        f["day"] = None

# ---------------------------------------------------------------------------------------------
# 2. what the records say about each mouse
# ---------------------------------------------------------------------------------------------
NOT_RECORDS = ("Sanity Check", "Import Report", "Lab Notebook Report", "Recording Binder", "Notes Sanity")
PRIMARY = ("SoftMouse", "VOS", "Lab Ops: KCNT1 Active 2.0", "AA outputs workbook")
PRIORITY = ["Lab Ops: KCNT1 Active 2.0", "SoftMouse", "VOS", "Lab Ops: KCNT1 Active (Archived)", "Lab Ops: KCNT1 Archive"]


def norm(field, v):
    s = str(v).strip()
    q = "?" in s
    s = s.replace("?", "").strip()
    sl = s.lower()
    if field == "Sex":
        if sl in ("f", "female"):
            return "F"
        if sl in ("m", "male"):
            return "M"
        return None
    if field in ("YH", "SST", "PV"):
        if sl == "wt":
            return "WT"
        if sl == "het":
            return "Het"
        if sl == "hom":
            return "Hom"
        if field != "YH" and sl in ("n/a", "na"):
            return "N/A"
        return None
    if field == "DOB":
        return s if re.fullmatch(r"\d{4}-\d\d-\d\d", s) else None


def call(m, field):
    """-> (value, agreement text, level) level: '' agree, 'minor', 'major', 'missing'"""
    votes = collections.OrderedDict()
    for source, v in SRC.get(m, {}).get(field, []):
        if any(x in source for x in NOT_RECORDS):
            continue
        n = norm(field, v)
        if n is None:
            continue
        votes.setdefault(source, n)
    if not votes:
        return None, "No record in any source", "missing"
    tally = collections.Counter(votes.values())
    top = max(tally.values())
    cands = [v for v, c in tally.items() if c == top]
    best = cands[0]
    if len(cands) > 1:
        for p in PRIORITY:
            if p in votes and votes[p] in cands:
                best = votes[p]
                break
    if len(tally) == 1:
        return best, "%d sources agree" % len(votes), ""
    groups = collections.defaultdict(list)
    for s, v in votes.items():
        groups[v].append(s)
    text = "; ".join("%s: %s" % (v, ", ".join(groups[v])) for v in sorted(groups, key=lambda v: -len(groups[v])))
    prim = {v for s, v in votes.items() if s in PRIMARY}
    level = "major" if len(prim) > 1 or (prim and best not in prim) else "minor"
    return best, text, level


def cre_call(m):
    sst, _, _ = call(m, "SST")
    pv, _, _ = call(m, "PV")
    parts = []
    if sst and sst not in ("N/A", "WT"):
        parts.append("SST-Cre " + sst.lower())
    if pv and pv not in ("N/A", "WT"):
        parts.append("PV-Cre " + pv.lower())
    sm = "; ".join(v for _, v in SRC.get(m, {}).get("_softmouse_genotype", []))
    if parts:
        return ", ".join(parts), sm
    if sst or pv:
        return "no Cre", sm
    return "none recorded", sm


EXPECTED = list(range(0, 17))
mice_rows = []
for m in sorted(set(by_mouse) | set(), key=int):
    fs = by_mouse[m]
    sex, sex_t, sex_l = call(m, "Sex")
    yh, yh_t, yh_l = call(m, "YH")
    dob, dob_t, dob_l = call(m, "DOB")
    cre, sm_geno = cre_call(m)
    usable = [f for f in fs if f["kind"] in (AA_RUN, SHORT, EXTRA)]
    have = sorted({f["session"] for f in usable})
    kinds = collections.Counter(f["kind"] for f in fs)
    if usable:
        missing = [s for s in EXPECTED if s not in have]
        status = "Complete s0-s16" if not missing else "Missing " + ", ".join("s%d" % s for s in missing)
        if any(s > 16 for s in have):
            status += "; extra " + ", ".join("s%d" % s for s in have if s > 16)
    else:
        missing = []
        status = "No AA run: " + ", ".join(sorted(kinds))
    rd = run_dates[m]
    d1 = rd["s1"]
    d2 = rd["dates"][-1] if rd["dates"] else None
    labops = [v for s, v in AADATES.get(m, []) if s == "Lab Ops: KCNT1 Active 2.0 / Active avoidance"]
    labops2 = [v for s, v in AADATES.get(m, []) if s == "Lab Ops: KCNT1 Active 2.0 / Active avoidance #2"]
    lo_text = " / ".join(x for x in [labops[0] if labops else "", labops2[0] if labops2 else ""] if x)
    lo_flag = ""
    if usable and labops:
        lo = re.match(r"\d{4}-\d\d-\d\d", labops[0])
        file_days = {d.strftime("%Y-%m-%d") for d in rd["dates"]}
        if lo and lo.group(0) not in file_days:
            lo_flag = "Lab Ops date %s is not a day any file was recorded (%s)" % (
                lo.group(0), ", ".join(sorted(file_days)))
    book_age = sorted({v for _, v in SRC.get(m, {}).get("_book_age", [])})
    book_yh = sorted({norm("YH", v) for s, v in SRC.get(m, {}).get("YH", []) if s == "AA outputs workbook"} - {None})
    book_sex = sorted({norm("Sex", v) for s, v in SRC.get(m, {}).get("Sex", []) if s == "AA outputs workbook"} - {None})
    nts = []
    seen = set()
    for s, t in NOTES.get(m, []):
        t = re.sub(r"\s+", " ", t).strip()
        if t and t not in seen:
            seen.add(t)
            nts.append("%s: %s" % (s, t))
    end = "; ".join(v for _, v in SRC.get(m, {}).get("_end", []))
    mice_rows.append(dict(mouse=m, sex=sex, sex_t=sex_t, sex_l=sex_l, yh=yh, yh_t=yh_t, yh_l=yh_l,
                          cre=cre, sm_geno=sm_geno, dob=dob, dob_t=dob_t, dob_l=dob_l, d1=d1, d2=d2,
                          n_files=len(fs), n_usable=len(usable), status=status, missing=missing,
                          kinds=kinds, labops=lo_text, lo_flag=lo_flag, book_age=", ".join(book_age),
                          book_yh=", ".join(book_yh), book_sex=", ".join(book_sex), notes=nts, end=end,
                          inferred=[f["file"] for f in fs if f["conf"] == "Inferred"]))
MICE = {r["mouse"]: r for r in mice_rows}

# mice the records say did AA, but with no file here
no_files = []
for m, lst in AADATES.items():
    if m in by_mouse:
        continue
    real = [(s, v) for s, v in lst if re.search(r"\d{4}-\d\d-\d\d|\d+/\d+/\d+", v)
            and not any(x in s for x in NOT_RECORDS)]
    if real:
        no_files.append((m, real))
no_files.sort(key=lambda x: int(x[0]))

