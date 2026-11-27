"""v3 of the KCNT1 AA map: second pass after Angelina's review, the renamed New Data set,
the v2 analysis, the VOS cage-card PDFs and a colony-wide sex check of Lab Ops."""
import os, re, json, csv, datetime, collections, sys
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont

import core
from core import (files, mice_rows, MICE, by_mouse, run_dates, no_files, SRC, NOTES, AADATES, norm,
                  AA_RUN, ABORT, SHORT, REPEAT0, PILOT, SCRAP, HABIT, PACER, TRAIN, TEST, DUP, BROKE, EXTRA,
                  parse_name, cre_call, NOT_RECORDS)

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = r"C:\Users\Z390\Desktop\jeremystats\KCNT1 Active Avoidance"
NEWDATA = os.path.join(BASE, "New Data", "active_avoidance_data")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out3.xlsx")
USABLE = (AA_RUN, SHORT, EXTRA)

# ---------------------------------------------------------------------------------------------
# Inputs new in this pass
# ---------------------------------------------------------------------------------------------
# 1. Angelina's verdicts (column A she added to v2)
VERDICT = {}
wv = openpyxl.load_workbook(os.path.join(BASE, "KCNT1_AA_mouse_map_112326_v2_with_notes.xlsx"))["Mice"]
hv = [c.value for c in wv[1]]
for r in wv.iter_rows(min_row=2, values_only=True):
    if r[0] and r[hv.index("Mouse")]:
        VERDICT[str(r[hv.index("Mouse")])] = str(r[0]).strip()

# 2. Renames she made (content hash old -> new)
ND = json.load(open(os.path.join(HERE, "newdata.json")))
RENAMED = {}   # old basename -> new basename
for olds, news in ND["renames"]:
    RENAMED[os.path.basename(olds[0])] = os.path.basename(news[0])
NEWNAME = {}
for f in files:
    NEWNAME[(f["folder"], f["file"])] = RENAMED.get(f["file"], f["file"]) if f["folder"] == "KCNT1_2026" else f["file"]
    f["now"] = NEWNAME[(f["folder"], f["file"])]

# 3. The v2 analysis (her re-run) and why it stopped
TBL2 = os.path.join(NEWDATA, "KCNT1_2026", "analysis_output_112326_v2", "TBLfiles", "2026_active_avoidance_output_112326_v2.tbl")
IN_V2 = set()
for line in open(TBL2, encoding="latin-1").read().splitlines()[1:]:
    t = line.split("\t")[0].strip()
    if t.lower().endswith(".dat"):
        IN_V2.add(t)
LOG2 = open(os.path.join(NEWDATA, "KCNT1_2026", "analysis_output_112326_v2", "TAreport.log"), encoding="latin-1").read()
first_fail = re.search(r"File (\d+) \.\.\. \S+\\([^\\\s]+\.dat)\s*\nGetTrackSize returned 0 files", LOG2)
FAIL_AT = int(first_fail.group(1)) if first_fail else None

# 4. Eli's AA outputs workbook: which (mouse, session, day) it scored
wbE = openpyxl.load_workbook(os.path.join(BASE, "DATA AND ARCHIVE", "KCNT1_AA_2024_thru_June26_outputs.xlsx"), data_only=True)
IN_ELI = set()
ELI_MICE = set()
for r in wbE["2024 + 2026 data"].iter_rows(min_row=2, values_only=True):
    if r[1]:
        IN_ELI.add((str(r[1]), str(r[5]).strip("?"), str(r[6])))
        ELI_MICE.add(str(r[1]))

# 5. VOS cage-card PDFs (parsed with VOS_report_parser.py; kept outside the repo)
CARDS = {}
for fn, label in (("vos_old.csv", "VOS cage card (old archive)"), ("vos_current.csv", "VOS cage card (current)")):
    for r in csv.DictReader(open(os.path.join(HERE, fn), encoding="utf-8-sig")):
        i = str(r.get("Extracted Sorting ID", "")).strip()
        if not i.isdigit():
            continue
        m = str(int(i))
        s = (r.get("Sex") or "").strip().upper()[:1]
        dob = None
        for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                dob = datetime.datetime.strptime((r.get("DOB") or "").strip(), fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass
        CARDS.setdefault(m, []).append(dict(src=label, sex=s if s in ("M", "F") else None, dob=dob,
                                            card=r.get("Cage Card"), strain=(r.get("Strain") or "").strip()))
        if s in ("M", "F"):
            SRC.setdefault(m, {}).setdefault("Sex", []).append((label, s))
        if dob:
            SRC.setdefault(m, {}).setdefault("DOB", []).append((label, dob))

# 6. Colony-wide sex sources (from sexcheck.py)
SX = json.load(open(os.path.join(HERE, "sexsrc.json")))
LO = openpyxl.load_workbook(os.path.join(HERE, "labops.xlsx"), data_only=True)["KCNT1 Active 2.0"]
loh = [c.value for c in LO[1]]
LO_ROW = {}
for r in LO.iter_rows(min_row=2, values_only=True):
    mm = re.match(r"^(\d+)", str(r[0] or "").replace(".0", "").strip())
    if mm:
        LO_ROW.setdefault(str(int(mm.group(1))), r)


def short(s):
    s = s.replace("Drive: Lab Documentation frfr/KCNT1/Breeding/", "Drive ").replace("Drive: Archive/", "Drive ")
    s = s.replace("AA outputs workbook", "Eli's AA outputs workbook")
    return s.replace("Lab Ops: ", "Lab Ops ").replace("Kcnt1 workflow / ", "Kcnt1 workflow: ")


def votes(m, field):
    v = collections.OrderedDict()
    for s, x in SRC.get(m, {}).get(field, []):
        if any(k in s for k in NOT_RECORDS):
            continue
        n = norm(field, x)
        if n is not None:
            v.setdefault(s, n)
    return v


def grouped(v):
    g = collections.defaultdict(list)
    for s, x in v.items():
        g[x].append(short(s))
    return g


# ---------------------------------------------------------------------------------------------
# Conflict model. level: Open / Fix / Todo / Check / Resolved / Note
# ---------------------------------------------------------------------------------------------
LV = {"Open": 0, "Fix": 1, "Todo": 2, "Check": 3, "Resolved": 4, "Note": 5}
C_ = lambda type_, subject, options, why, conf, todo, level, **kw: dict(
    type=type_, subject=subject, options=options, why=why, confidence=conf, todo=todo, level=level, **kw)
conf_by_mouse = collections.defaultdict(list)
final = {}
all_mice = [r["mouse"] for r in mice_rows] + [m for m, _ in no_files]

for m in all_mice:
    r = MICE.get(m)
    side = bool(r) and r["n_usable"] == 0 and not r["kinds"].get(BROKE)
    verdict = VERDICT.get(m, "")
    fin = {}
    # ---- sex ---------------------------------------------------------------------------------
    v = votes(m, "Sex")
    g = grouped(v)
    cards = {c["sex"] for c in CARDS.get(m, []) if c["sex"]}
    sm = v.get("SoftMouse")
    if len(cards) == 1:
        pick, basis, conf = next(iter(cards)), "the VOS cage card", "High"
    elif sm:
        pick, basis, conf = sm, "SoftMouse", "High" if v.get("Lab Ops: KCNT1 Archive") in (None, sm) else "Medium"
    elif v.get("Lab Ops: KCNT1 Archive"):
        pick, basis, conf = v["Lab Ops: KCNT1 Archive"], "the original record (Lab Ops 'KCNT1 Archive', copied from the Kcnt1 workflow sheet)", "Medium"
    elif g:
        pick, basis, conf = collections.Counter(v.values()).most_common(1)[0][0], "most sources", "Low"
    else:
        pick = None
    fin["sex"] = pick
    if len(g) > 1 and pick:
        wrong = [s for s, x in v.items() if x != pick]
        lab_wrong = [s for s in wrong if s in ("Lab Ops: KCNT1 Active 2.0",)]
        eli_wrong = [s for s in wrong if s == "AA outputs workbook"]
        sm_wrong = [s for s in wrong if s == "SoftMouse"]
        why = "Settled by %s." % basis
        if len(cards) == 1:
            cc = CARDS[m][0]
            why = "The VOS cage card (%s, %s) says %s; " % (cc["card"], cc["src"].split("(")[1].rstrip(")"), pick)
            why += "SoftMouse agrees. " if sm == pick else ("SoftMouse says %s. " % sm if sm else "SoftMouse has no record. ")
        why += (" Lab Ops 2.0 has the other sex, like every sheet built from the Lab Ops 'KCNT1 Active' tab "
                "(Active (Archived), Colony_Count_092426, Brain Bank tracking, Dentate Spike Data, Eli's workbook)."
                if lab_wrong else "")
        todo = []
        if lab_wrong:
            todo.append("Set Lab Ops KCNT1 Active 2.0 Sex to %s." % pick)
        if sm_wrong:
            todo.append("Set SoftMouse sex to %s." % pick)
        if eli_wrong:
            todo.append("Change Eli's AA outputs workbook to %s before any by-sex plot." % pick)
        if not todo:
            todo.append("Only an older sheet is wrong; no live record to fix.")
        if not cards and not sm:
            todo = ["No cage card or SoftMouse record exists. Check the perfusion / brain-bank record or the "
                    "Oct 2024 AA notebook; if it confirms %s, set Lab Ops KCNT1 Active 2.0 to %s." % (pick, pick)]
        level = "Open" if conf in ("Medium", "Low") and not cards and not sm else ("Fix" if (lab_wrong or sm_wrong or eli_wrong) else "Note")
        if side and level != "Note":
            level = "Fix" if lab_wrong else "Note"
        opts = [("%s: %s" % ({"F": "Female", "M": "Male"}[x], "; ".join(g[x])), x == pick) for x in sorted(g, key=lambda x: x != pick)]
        conf_by_mouse[m].append(C_("Sex", m, opts, why, conf, " ".join(todo), level, verdict=verdict))
    elif not g and not side:
        conf_by_mouse[m].append(C_("Sex", m, [("No source records the sex", True)], "", "", "Check the perfusion record.", "Open"))
    # ---- genotype ----------------------------------------------------------------------------
    v = votes(m, "YH")
    g = grouped(v)
    if m == "416":
        fin["yh"] = "WT"
        conf_by_mouse[m].append(C_("Genotype", m,
            [("WT (confirmed: Transnetyx genotyping result): " + "; ".join(g.get("WT", [])), True),
             ("Het: " + "; ".join(g.get("Het", [])), False)],
            "Angelina checked the Transnetyx result on 11-23: WT. My v2 pick (Het) was wrong; the Het sources "
            "(SoftMouse, two old workflow tabs, Eli's workbook) are the ones to correct.", "Confirmed",
            "Set SoftMouse genotype to YH(WT). Move 416 to WT in Eli's AA outputs workbook and re-plot.", "Fix",
            verdict=verdict))
    elif len(g) > 1:
        fin["yh"] = collections.Counter(v.values()).most_common(1)[0][0]
        opts = [("%s: %s" % (x, "; ".join(g[x])), x == fin["yh"]) for x in sorted(g, key=lambda x: x != fin["yh"])]
        conf_by_mouse[m].append(C_("Genotype", m, opts, "Most sources agree.", "Low", "Find the genotyping result.",
                                   "Note" if side else "Open"))
    elif not g:
        fin["yh"] = None
        conf_by_mouse[m].append(C_("Genotype", m, [("No source records the YH genotype", True)],
                                   "Not an AA mouse; does not affect the analysis.", "", "", "Note"))
    else:
        fin["yh"] = next(iter(g))
    # ---- DOB ---------------------------------------------------------------------------------
    v = votes(m, "DOB")
    g = grouped(v)
    cdob = {c["dob"] for c in CARDS.get(m, []) if c["dob"]}
    if len(g) > 1:
        pick = next(iter(cdob)) if len(cdob) == 1 else collections.Counter(v.values()).most_common(1)[0][0]
        others = [x for x in g if x != pick]
        old_only = all(set(g[x]) <= {"Kcnt1 workflow", "Kcnt1 workflow: 020625 Colony Overview"} for x in others)
        shift = ", ".join("%+.1f wk" % ((datetime.date.fromisoformat(x) - datetime.date.fromisoformat(pick)).days / 7) for x in others)
        why = ("The VOS cage card, SoftMouse and Lab Ops agree. " if cdob == {pick} and "SoftMouse" in g[pick] else "Most sources agree. ")
        if old_only:
            why += "Only the old Kcnt1 workflow tabs differ (%s)." % shift
        opts = [("%s: %s" % (x, "; ".join(g[x])), x == pick) for x in sorted(g, key=lambda x: x != pick)]
        conf_by_mouse[m].append(C_("DOB", m, opts, why, "High", "Nothing to fix for the analysis." if old_only else "Check the litter record.",
                                   "Note" if old_only or side else "Open"))
        fin["dob"] = pick
    elif not g:
        fin["dob"] = None
        conf_by_mouse[m].append(C_("DOB", m, [("No source records a DOB", True)], "", "", "", "Note" if side else "Open"))
    else:
        fin["dob"] = next(iter(g))
        if m == "872" and cdob:
            conf_by_mouse[m].append(C_("DOB", m, [("2023-03-24 (VOS cage card %s)" % CARDS[m][0]["card"], True)],
                "Every Lab Ops tab has '?' or Unknown; the old VOS cage card has it. Pilot mouse only, so no age is used.",
                "High", "Optionally fill Lab Ops DOB = 3/24/2023.", "Note"))
    final[m] = fin

# ---- file names -----------------------------------------------------------------------------------
file_items = {}
for f in files:
    key = (f["folder"], f["file"])
    renamed = f["now"] != f["file"]
    named, nses = parse_name(f["file"])
    if f["kind"] == TEST:
        file_items[key] = C_("File names", f["now"], [("Not an animal: tracker test or false start", True)],
                             f["ev"], "High", "Leave out of every analysis.", "Note")
        continue
    if f["kind"] == ABORT and renamed:
        file_items[key] = C_("File names", f["now"], [("Was %s; now marked do-not-use" % f["file"], True)],
                             f["ev"], "High", "", "Resolved")
        continue
    if f["conf"] == "Inferred" or (f["issue"] and f["mouse"] and f["kind"] not in (PILOT,)):
        want = "M%ss%d_%s.dat" % (f["mouse"], f["session"], f["when"].strftime("%m%d%y"))
        usable = f["kind"] in (AA_RUN, SHORT, EXTRA, REPEAT0)
        if renamed:
            file_items[key] = C_("File names", f["now"], [("Renamed 11-23 from %s to %s" % (f["file"], f["now"]), True)],
                                 "Angelina renamed it in New Data; the name now matches mouse %s s%d." % (f["mouse"], f["session"]),
                                 "Confirmed", "", "Resolved")
        elif f["conf"] == "Inferred":
            lvl = "Todo" if f["folder"] == "KCNT1_2026" else "Check"
            todo = ("Rename to %s and re-run the analysis; the v2 table scored it under the wrong name." % want
                    if f["folder"] == "KCNT1_2026" else
                    "Optional: rename to %s. Eli's workbook already scores it as mouse %s s%d." % (want, f["mouse"], f["session"]))
            file_items[key] = C_("File names", f["now"],
                                 [("As named: %s" % (("mouse %s" % named) if named else "no readable mouse"), False),
                                  ("Mouse %s s%d" % (f["mouse"], f["session"]), True)],
                                 f["ev"], "High", todo, lvl)
        elif usable:
            file_items[key] = C_("File names", f["now"], [("Name as written", False), ("Mouse %s s%s, recorded %s" % (f["mouse"], f["session"], f["when"].strftime("%Y-%m-%d")), True)],
                                 f["issue"] + ". The header date and the run order agree on the mouse.", "High",
                                 "Optional rename to %s; Angelina notes Dylan's 2024 convention was M[id]s[n][Month][day]." % want
                                 if f["folder"] != "KCNT1_2026" else "Optional rename to %s." % want, "Note")
for key, c in file_items.items():
    f = next(x for x in files if (x["folder"], x["file"]) == key)
    f["conflict"] = c
    if f["mouse"] and c["level"] in ("Todo", "Check", "Resolved"):
        conf_by_mouse[f["mouse"]].append(dict(c, subject=f["now"]))
        named, _ = parse_name(f["file"])
        if named and named != f["mouse"] and named in MICE and c["level"] != "Resolved":
            conf_by_mouse[named].append(dict(c, subject=f["now"], why="Named for %s, but it belongs to %s. %s" % (named, f["mouse"], c["why"])))

# ---- runs (with Angelina's verdicts) ---------------------------------------------------------------
for m, r in MICE.items():
    fs = by_mouse[m]
    v = VERDICT.get(m, "")
    if r["kinds"].get(BROKE):
        conf_by_mouse[m].append(C_("Sessions / run", m, [("Exclude: run stopped when the motor broke on 10/21", True)],
            "Angelina: 'exclude (stopped due to motor breaking)'. Lab Ops note on 1647 says the apparatus broke.",
            "Confirmed", "Leave out of the AA analysis.", "Resolved", verdict=v))
    if any(f["kind"] == EXTRA for f in fs):
        conf_by_mouse[m].append(C_("Sessions / run", m, [("Drop s17: a 9th day-2 session was run by mistake", True)],
            "Angelina: the first time a newly trained undergrad ran AA on their own, they ran one extra day-2 session. "
            "This matches the v2 reading of the clock (9 clean alternating slots).", "Confirmed",
            "Drop %s from the analysis table (the v2 run scored it)." % ", ".join(f["now"] for f in fs if f["kind"] == EXTRA),
            "Todo" if any(f["now"] in IN_V2 for f in fs if f["kind"] == EXTRA) else "Resolved", verdict=v))
    if m == "419":
        conf_by_mouse[m].append(C_("Sessions / run", m, [("Exclude 419", True)],
            "Angelina: 'exclude 419'. s0 was run 15 days before s1-s16; Lab Ops: 'excluded from AA data due to extra sessions'. "
            "Eli's workbook still includes 419.", "Confirmed", "Remove 419 from Eli's AA outputs workbook / plots.", "Fix", verdict=v))
for m, real in no_files:
    conf_by_mouse[m].append(C_("Sessions / run", m, [("473 did not run AA; the AA date was copied in error", True)],
        "Angelina: 'for sure copied in error'. No Behaviour-log row, no free slot on 10/23-24, and the Lab Ops cell "
        "carries a note that belongs to 461/462.", "Confirmed",
        "Clear 473's Active avoidance dates in Lab Ops KCNT1 Active 2.0 (and the KCNT1 AA Ages sheet / Current KCNT1).",
        "Fix", verdict=VERDICT.get(m, "")))

# ---- AA date / age -------------------------------------------------------------------------------
for m, r in MICE.items():
    if r["lo_flag"]:
        age = (r["d1"] - datetime.date.fromisoformat(final[m]["dob"])).days / 7
        conf_by_mouse[m].append(C_("AA date / age", m,
            [("Lab Ops and the KCNT1 AA Ages sheet: 2024-03-24", False),
             ("File headers and the Behaviour sheet: 2024-03-13 and 2024-03-15, age %.1f wk" % age, True)],
            "The tracker stamps the date into each file. Eli's workbook gives %s wk, which is what 3/24 gives." % r["book_age"],
            "High", "Set Lab Ops AA dates to 3/13/2024 and 3/15/2024; change Eli's age to %.1f wk." % age, "Fix"))

# ---- analysis coverage ---------------------------------------------------------------------------
for m, r in MICE.items():
    fs = [f for f in by_mouse[m] if f["kind"] in USABLE and f["kind"] != EXTRA]
    if not fs:
        continue
    if fs[0]["folder"] == "KCNT1_2026":
        miss = [f for f in fs if f["now"] not in IN_V2]
        if miss:
            sess = sorted(f["session"] for f in miss)
            conf_by_mouse[m].append(C_("Analysis", m,
                [("Not in the v2 table: s%s" % ", s".join(str(s) for s in sess), True)],
                "The TA program stopped reading files after file %d of 518 in BOTH runs ('GetTrackSize returned 0 files' "
                "for every file from #%d on). The first run reached 1667 s7, the v2 run only s5, because the two "
                "do-not-use files and the renamed ones moved 1667 later in the list. It is a batch-size limit, not bad data."
                % (FAIL_AT - 1, FAIL_AT), "High",
                "Re-run 1667 (or the whole set split into two batches of under ~500 files).", "Todo"))
    else:
        days = {(m, str(f["session"]), str(f["day"])) for f in fs}
        if m not in ELI_MICE:
            why = ("Eli's workbook (2024 + 2026 thru June) has no rows for this mouse. " +
                   ("All of the KCNT1_DM_Sep24 folder (448, 461, 462, 476-482) is missing from it, so that folder was probably never run through the TA analysis. "
                    if fs[0]["folder"] == "KCNT1_DM_Sep24" else
                    "894 is the only Feb24-folder mouse missing; its s0 is named M894May13s0.dat and its Feb 2024 pilot files share the number, which may be why it was left out. "))
            if m == "448":
                why += "Lab Ops Archive: 'Excluded due to weird CSD' (Dylan's study)."
            conf_by_mouse[m].append(C_("Analysis", m, [("Not analyzed: no rows in Eli's AA outputs workbook", True)], why,
                                       "High", "Run the TA analysis on this mouse's files (or record why it is excluded).", "Todo",
                                       verdict=VERDICT.get(m, "")))

# ---- the two do-not-use files that the v2 run scored ----------------------------------------------
for f in files:
    if f["now"].endswith("_do_not_use.dat") and f["now"] in IN_V2:
        conf_by_mouse[f["mouse"]].append(C_("Analysis", f["mouse"], [("%s was scored in the v2 table" % f["now"], True)],
            "Renamed do-not-use, but still in the folder the analysis read, so it has a row in the output.", "High",
            "Delete its row from the v2 output (or move the file out of the folder and re-run).", "Todo"))


# ---------------------------------------------------------------------------------------------
# Colony-wide Lab Ops sex worklist
# ---------------------------------------------------------------------------------------------
work = []
for m, lo_sex in SX["V2"].items():
    card = {c["sex"] for c in CARDS.get(m, []) if c["sex"]}
    vos = SX["VOS"].get(m)
    sm = SX["SM"].get(m)
    arc = SX["ARC"].get(m)
    if len(card) == 1:
        ans, basis, conf = next(iter(card)), "VOS cage card", "High"
    elif vos:
        ans, basis, conf = vos, "VOS census", "High"
    elif sm:
        ans, basis, conf = sm, "SoftMouse", "High" if arc in (None, sm) else "Medium"
    elif arc:
        ans, basis, conf = arc, "Lab Ops KCNT1 Archive (original record)", "Medium"
    else:
        continue
    if ans != lo_sex:
        row = LO_ROW.get(m)
        alive = row[loh.index("Alive")] if row else ""
        cage = row[loh.index("Cage ID")] if row else ""
        work.append(dict(mouse=m, now=lo_sex, to=ans, basis=basis, conf=conf,
                         card="; ".join("%s %s" % (c["card"], c["sex"]) for c in CARDS.get(m, []) if c["sex"]),
                         sm=sm or "", vos=vos or "", arc=arc or "", alive=alive, cage=cage,
                         aa="Yes" if m in MICE and MICE[m]["n_usable"] else ""))
work.sort(key=lambda w: int(w["mouse"]))


# ---------------------------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------------------------
def status(m):
    cs = conf_by_mouse.get(m, [])
    r = MICE.get(m)
    if r is not None and r["n_usable"] == 0 and not r["kinds"].get(BROKE) and not any(c["level"] == "Fix" for c in cs):
        return "Not an AA mouse"
    lv = min((LV[c["level"]] for c in cs), default=9)
    return {0: "Open conflict", 1: "Fix records", 2: "Analysis to-do", 3: "Check", 4: "Resolved"}.get(lv, "Good")


# ---------------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------------
FONT = "Arial"
F_BASE = Font(name=FONT, size=10)
F_BOLD = Font(name=FONT, size=10, bold=True)
F_HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_SEC = Font(name=FONT, size=11, bold=True, color="FFFFFF")
F_TITLE = Font(name=FONT, size=14, bold=True)
IF_B = InlineFont(rFont=FONT, sz=10, b=True)
IF_N = InlineFont(rFont=FONT, sz=10)
IF_I = InlineFont(rFont=FONT, sz=10, i=True, color="555555")
fill = lambda c: PatternFill("solid", fgColor=c)
HEADFILL, SECFILL = fill("3B4A5A"), fill("5B6B7B")
LVFILL = {"Open": fill("F4C7C3"), "Fix": fill("F9CB9C"), "Todo": fill("FFF2CC"), "Check": fill("FFF8DC"),
          "Resolved": fill("D9EAD3"), "Note": None}
STFILL = {"Open conflict": fill("F4C7C3"), "Fix records": fill("F9CB9C"), "Analysis to-do": fill("FFF2CC"),
          "Check": fill("FFF8DC"), "Resolved": fill("D9EAD3"), "Good": fill("B6D7A8"), "Not an AA mouse": fill("E8E8E8"),
          "Renamed": fill("D9EAD3"), "Do not use": fill("E8E8E8"), "No mouse": fill("E8E8E8"),
          "Still misnamed": fill("FFF2CC"), "Not analyzed": fill("FFF2CC"), "Remove from table": fill("FFF2CC")}
GREY = fill("E8E8E8")
VFILL = fill("EAD1DC")
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")


def put(ws, r, c, v, f=None, fmt=None, wrap=False, bold=False):
    cell = ws.cell(row=r, column=c, value=v)
    cell.font = F_BOLD if bold else F_BASE
    cell.alignment = WRAP if wrap else TOP
    if f:
        cell.fill = f
    if fmt:
        cell.number_format = fmt
    return cell


def rich(c, with_why=True, label=None):
    parts = []
    if label:
        parts.append(TextBlock(IF_N, label + "\n"))
    many = len(c["options"]) > 1
    for i, (txt, likely) in enumerate(c["options"]):
        if i:
            parts.append(TextBlock(IF_N, "\n"))
        tag = ("   <- confirmed" if c["confidence"] == "Confirmed" else "   <- most likely") if (likely and many) else ""
        parts.append(TextBlock(IF_B if (likely or not many) else IF_N, txt + tag))
    if with_why and c["why"]:
        parts.append(TextBlock(IF_I, "\nWhy: " + c["why"] + (("  Confidence: " + c["confidence"]) if c["confidence"] else "")))
    return CellRichText(*parts)


def head(ws, headers, widths, row=1, freeze_col=4):
    for i, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font, c.fill, c.alignment = F_HEAD, HEADFILL, Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 32
    ws.freeze_panes = ws.cell(row=row + 1, column=freeze_col)
    ws.auto_filter.ref = "A%d:%s%d" % (row, get_column_letter(len(headers)), row)


def note_for(m):
    bits = []
    for c in sorted(conf_by_mouse.get(m, []), key=lambda c: LV[c["level"]]):
        if c["level"] == "Note":
            continue
        likely = next((t for t, l in c["options"] if l), "")
        likely = re.split(r"[:(]", likely)[0].strip() if c["type"] in ("Sex", "Genotype") else likely
        prefix = {"Open": "OPEN", "Fix": "FIX", "Todo": "TO DO", "Check": "CHECK", "Resolved": "DONE"}[c["level"]]
        bits.append("%s - %s: %s" % (prefix, c["type"], likely))
    return "\n".join(bits) if bits else "All sources agree; every session present and analyzed."


def todo_for(m):
    out = []
    for c in sorted(conf_by_mouse.get(m, []), key=lambda c: LV[c["level"]]):
        if c["level"] in ("Open", "Fix", "Todo", "Check") and c["todo"] and c["todo"] not in out:
            out.append(c["todo"])
    return "\n".join("%d. %s" % (i, t) for i, t in enumerate(out, 1))


wb = openpyxl.Workbook()

# ---- Read me ----------------------------------------------------------------------------------------
ws = wb.active
ws.title = "Read me"
ws.column_dimensions["A"].width = 26
ws.column_dimensions["B"].width = 118
put(ws, 1, 1, "KCNT1 active avoidance map, v3 (second pass, 2026-11-23 evening)").font = F_TITLE
cnt = collections.Counter(status(m) for m in all_mice)
n_open = sum(1 for m in all_mice for c in conf_by_mouse[m] if c["level"] == "Open")
readme = [
    ("What is new in v3", "Angelina's verdicts (purple column, Mice tab) are folded in. Files are now read from New Data "
     "(her renamed set) and checked against her v2 analysis run. Two new sources: the VOS cage-card PDFs (old archive "
     "and current). New tab 'Lab Ops sex fixes': every mouse in KCNT1 Active 2.0 whose sex disagrees with the cage "
     "card, VOS or SoftMouse, not only AA mice."),
    ("Mice now", ", ".join("%s %d" % (k, v) for k, v in sorted(cnt.items(), key=lambda kv: -kv[1]))),
    ("Status", ""),
    ("   Open conflict", "Sources disagree and nothing settles it yet."),
    ("   Fix records", "The answer is known (confirmed or settled by the cage card); a live record still holds the wrong value."),
    ("   Analysis to-do", "Data are fine; an analysis output is missing rows or has rows it should not."),
    ("   Check", "Minor: a file still carries an old or odd name."),
    ("   Resolved", "Settled and nothing left to change (renamed, excluded by decision, confirmed)."),
    ("   Good", "All sources agree; every session present and analyzed."),
    ("Bold", "The answer I think is right. '<- confirmed' means a person or a primary record settled it; "
             "'<- most likely' means it is still my inference."),
    ("Sex: what went wrong", "The VOS cage cards, SoftMouse (now and its May 2026 exports) and the original Kcnt1 workflow "
     "sheet all agree with each other. The wrong sexes live only in Lab Ops 'KCNT1 Active' (now 'Active (Archived)'), "
     "were carried into Active 2.0 by the migration (which copied v1 faithfully), and from there into every later export "
     "(Colony_Count_092426, Brain Bank tracking, Dentate Spike Data, Eli's workbook). Live mice look right only because "
     "each VOS import rewrites Sex for mice still on a cage card; retired mice never get rewritten, so their wrong sex "
     "stays. The error is not a row shift (checked offsets -6..+6 against every older sheet) and did not come from "
     "SoftMouse. It entered when the v1 tab was built, between the workflow sheet's last edit (2026-05-12) and the first "
     "copy that shows it (Brain Bank tracking, 2026-09-04). The Drive API only returns versions from 2026-10-26 on, so the "
     "exact edit cannot be pulled from here."),
    ("Ages", "Age (weeks) = (date of AA session 1 - DOB) / 7, as an Excel formula."),
]
for i, (a, b) in enumerate(readme, 3):
    put(ws, i, 1, a, bold=True)
    put(ws, i, 2, b, wrap=True)
    if a.strip() in STFILL:
        ws.cell(row=i, column=1).fill = STFILL[a.strip()]

# ---- Mice ---------------------------------------------------------------------------------------------
wm = wb.create_sheet("Mice")
TYPES = ["Genotype", "Sex", "DOB", "File names", "Sessions / run", "AA date / age", "Analysis"]
mh = (["Angelina's verdict (11-23)", "Status", "Conflict note", "What to do", "Mouse", "Sex", "YH genotype", "Cre", "DOB",
       "AA day 1 (s1)", "AA day 2", "Age at AA (weeks)"] + ["Conflict: " + t for t in TYPES] +
      ["Files", "AA sessions", "Session status", "Lab Ops AA date(s)", "VOS cage card", "SoftMouse genotype text",
       "End (SoftMouse)", "AA notes from the records"])
mw = [30, 14, 44, 46, 8, 6, 10, 16, 11, 11, 11, 10] + [44, 50, 40, 46, 46, 40, 44] + [7, 8, 22, 22, 26, 26, 22, 60]
head(wm, mh, mw, freeze_col=6)
mouse_row = {}
for i, m in enumerate(sorted(all_mice, key=int), 2):
    mouse_row[m] = i
    r = MICE.get(m)
    fin = final[m]
    st = status(m)
    by_type = collections.defaultdict(list)
    for c in conf_by_mouse[m]:
        by_type[c["type"]].append(c)
    worst = lambda t: min((LV[c["level"]] for c in by_type[t]), default=9)
    vf = lambda t: {0: LVFILL["Open"], 1: LVFILL["Fix"]}.get(worst(t))
    put(wm, i, 1, VERDICT.get(m, ""), f=VFILL if VERDICT.get(m) else None, wrap=True)
    put(wm, i, 2, st, f=STFILL[st], bold=True)
    put(wm, i, 3, note_for(m), wrap=True)
    put(wm, i, 4, todo_for(m), wrap=True)
    put(wm, i, 5, int(m), bold=True)
    put(wm, i, 6, fin["sex"] or "unknown", f=vf("Sex"), bold=bool(by_type["Sex"]))
    put(wm, i, 7, fin["yh"] or "unknown", f=vf("Genotype"), bold=bool(by_type["Genotype"]))
    put(wm, i, 8, cre_call(m)[0])
    put(wm, i, 9, datetime.date.fromisoformat(fin["dob"]) if fin["dob"] else "unknown", fmt="yyyy-mm-dd", f=vf("DOB"))
    if r and r["d1"]:
        put(wm, i, 10, r["d1"], fmt="yyyy-mm-dd")
        put(wm, i, 11, r["d2"], fmt="yyyy-mm-dd")
        put(wm, i, 12, '=IF(AND(ISNUMBER(I%d),ISNUMBER(J%d)),ROUND((J%d-I%d)/7,1),"unknown")' % (i, i, i, i), fmt="0.0")
    else:
        put(wm, i, 12, "no AA run" if r else "no files", f=GREY)
    for j, t in enumerate(TYPES, 13):
        cs = sorted(by_type[t], key=lambda c: LV[c["level"]])
        if not cs:
            continue
        blocks = []
        for k, c in enumerate(cs):
            if k:
                blocks.append(TextBlock(IF_N, "\n\n"))
            blocks.extend(rich(c, label=c["subject"] if t == "File names" else None))
        cell = wm.cell(row=i, column=j, value=CellRichText(*blocks))
        cell.alignment = WRAP
        if LVFILL[cs[0]["level"]]:
            cell.fill = LVFILL[cs[0]["level"]]
    put(wm, i, 24, "; ".join("%s %s %s %s" % (c["card"], c["sex"] or "", c["dob"] or "", c["strain"]) for c in CARDS.get(m, [])) or "", wrap=True)
    if r:
        put(wm, i, 20, r["n_files"])
        put(wm, i, 21, r["n_usable"])
        put(wm, i, 22, r["status"], wrap=True)
        put(wm, i, 23, r["labops"] or "none", wrap=True)
        put(wm, i, 25, r["sm_geno"] or "not in SoftMouse", wrap=True)
        put(wm, i, 26, r["end"], wrap=True)
        put(wm, i, 27, "\n".join(r["notes"]), wrap=True)

# ---- Conflicts ------------------------------------------------------------------------------------------
wc = wb.create_sheet("Conflicts")
for col, w in zip("ABCDEFGH", [12, 9, 30, 60, 70, 11, 50, 30]):
    wc.column_dimensions[col].width = w
put(wc, 1, 1, "What is still in conflict (v3). Bold = answer.").font = F_TITLE
pool = [(m, c) for m in all_mice for c in conf_by_mouse[m] if c["type"] != "File names"]
pool += [(f["mouse"] or "", f["conflict"]) for f in files if f.get("conflict")]
SECTIONS = [
    ("Still open: nothing settles these yet", lambda c: c["level"] == "Open"),
    ("Answer known: Lab Ops sex is wrong (full colony list on the 'Lab Ops sex fixes' tab)", lambda c: c["level"] == "Fix" and c["type"] == "Sex"),
    ("Answer known: other records to fix (genotype, dates, Eli's workbook)", lambda c: c["level"] == "Fix" and c["type"] != "Sex"),
    ("Analysis to-dos", lambda c: c["level"] == "Todo" and c["type"] != "File names"),
    ("File names: still to rename", lambda c: c["type"] == "File names" and c["level"] in ("Todo", "Check")),
    ("Resolved today", lambda c: c["level"] == "Resolved"),
    ("Notes (no action needed)", lambda c: c["level"] == "Note"),
]
row = 3
used = set()
for n, (title, test) in enumerate(SECTIONS, 1):
    items = [(m, c) for m, c in pool if id(c) not in used and test(c)]
    for m, c in items:
        used.add(id(c))
    for col in range(1, 9):
        wc.cell(row=row, column=col).fill = SECFILL
    s = wc.cell(row=row, column=1, value="%d. %s  (%d)" % (n, title, len(items)))
    s.font = F_SEC
    row += 1
    if not items:
        put(wc, row, 1, "None.")
        row += 2
        continue
    for col, h in enumerate(["Status", "Mouse", "File / subject", "Answers (bold = answer)", "Why", "Confidence",
                             "What to do", "Angelina's verdict"], 1):
        cc = wc.cell(row=row, column=col, value=h)
        cc.font, cc.fill = F_HEAD, HEADFILL
    row += 1
    items.sort(key=lambda mc: (LV[mc[1]["level"]], mc[1]["type"], int(mc[0]) if str(mc[0]).isdigit() else 0, mc[1]["subject"]))
    for m, c in items:
        put(wc, row, 1, {"Open": "Open", "Fix": "Fix", "Todo": "To do", "Check": "Check", "Resolved": "Resolved", "Note": "Note"}[c["level"]],
            bold=True, f=LVFILL[c["level"]])
        put(wc, row, 2, int(m) if str(m).isdigit() else "")
        put(wc, row, 3, c["subject"] if c["subject"] != m else c["type"], wrap=True)
        cell = wc.cell(row=row, column=4, value=rich(c, with_why=False))
        cell.alignment = WRAP
        put(wc, row, 5, c["why"], wrap=True)
        put(wc, row, 6, c["confidence"])
        put(wc, row, 7, c["todo"], wrap=True)
        put(wc, row, 8, c.get("verdict", "") or VERDICT.get(str(m), "") if c["type"] not in ("File names",) else "", wrap=True,
            f=VFILL if (c.get("verdict") or (VERDICT.get(str(m)) and c["type"] not in ("File names",))) else None)
        row += 1
    row += 1
wc.freeze_panes = "A3"

# ---- Lab Ops sex fixes ------------------------------------------------------------------------------------
wl = wb.create_sheet("Lab Ops sex fixes")
head(wl, ["Mouse", "Lab Ops 2.0 says", "Set to", "Settled by", "Confidence", "VOS cage card", "VOS census", "SoftMouse",
          "Lab Ops KCNT1 Archive", "Alive (Lab Ops)", "Cage ID", "AA mouse?"],
     [8, 10, 8, 30, 11, 26, 10, 10, 12, 10, 14, 9], freeze_col=2)
for i, w in enumerate(work, 2):
    put(wl, i, 1, int(w["mouse"]), bold=True)
    put(wl, i, 2, w["now"], f=LVFILL["Open"])
    put(wl, i, 3, w["to"], bold=True, f=fill("D9EAD3"))
    put(wl, i, 4, w["basis"])
    put(wl, i, 5, w["conf"], f=None if w["conf"] == "High" else LVFILL["Check"])
    put(wl, i, 6, w["card"])
    put(wl, i, 7, w["vos"])
    put(wl, i, 8, w["sm"])
    put(wl, i, 9, w["arc"])
    put(wl, i, 10, w["alive"])
    put(wl, i, 11, w["cage"])
    put(wl, i, 12, w["aa"])
n = len(work) + 3
put(wl, n, 1, "How each row was settled: VOS cage card first (the physical card), then the VOS census Jarvis keeps, then "
             "SoftMouse, then the original Lab Ops 'KCNT1 Archive' tab. 'Medium' rows rest on one record only.", wrap=False)

# ---- Files ----------------------------------------------------------------------------------------------
wf = wb.create_sheet("Files")
fh = ["Status", "Note (bold = answer)", "What to do", "Folder", "File now (New Data)", "Was named", "Recorded (header)",
      "Length (min)", "Mouse", "Session", "Day", "What it is", "Sex", "YH genotype", "DOB", "Age at this file (weeks)",
      "In Eli's AA workbook", "In v2 analysis (11-23)"]
fw = [15, 58, 40, 16, 34, 30, 16, 8, 8, 8, 7, 26, 6, 10, 11, 10, 12, 12]
head(wf, fh, fw, freeze_col=6)
NOTUSE = (ABORT, PILOT, SCRAP, HABIT, PACER, TRAIN, DUP, BROKE, TEST)
for i, f in enumerate(sorted(files, key=lambda f: (f["when"], f["now"])), 2):
    c = f.get("conflict")
    in_v2 = f["now"] in IN_V2 if f["folder"] == "KCNT1_2026" else None
    in_eli = (f["mouse"], str(f["session"]), str(f["day"])) in IN_ELI if f["folder"] != "KCNT1_2026" or f["when"] < datetime.datetime(2026, 7, 1) else None
    if f["kind"] == TEST or not f["mouse"]:
        st = "No mouse"
    elif f["now"].endswith("_do_not_use.dat") and in_v2:
        st = "Remove from table"
    elif f["kind"] == EXTRA:
        st = "Remove from table" if in_v2 else "Do not use"
    elif f["kind"] in NOTUSE:
        st = "Do not use"
    elif c and c["level"] in ("Todo", "Check"):
        st = "Still misnamed"
    elif f["folder"] == "KCNT1_2026" and not in_v2:
        st = "Not analyzed"
    elif f["folder"] != "KCNT1_2026" and f["mouse"] not in ELI_MICE:
        st = "Not analyzed"
    elif c and c["level"] == "Resolved":
        st = "Renamed"
    else:
        st = "Good"
    put(wf, i, 1, st, f=STFILL[st], bold=True)
    if c:
        cell = wf.cell(row=i, column=2, value=rich(c))
        cell.alignment = WRAP
        todo = c["todo"]
    else:
        note = f["kind"] + (". " + f["ev"] if f["ev"] else "") if f["kind"] not in USABLE else ""
        if st == "Not analyzed" and f["folder"] == "KCNT1_2026":
            note = "Not in the v2 table: the TA program stopped reading after file %d of the batch." % (FAIL_AT - 1)
        elif st == "Not analyzed":
            note = "Mouse has no rows in Eli's AA outputs workbook."
        put(wf, i, 2, note, wrap=True)
        todo = {"Not analyzed": "Run the TA analysis on it.", "Remove from table": "Delete its row from the v2 output.",
                "Do not use": "Leave out."}.get(st, "")
    if f["kind"] == EXTRA:
        todo = "Drop (extra s17; Angelina)." + (" Delete its row from the v2 output." if in_v2 else "")
    put(wf, i, 3, todo, wrap=True)
    put(wf, i, 4, f["folder"])
    put(wf, i, 5, f["now"], bold=True)
    put(wf, i, 6, f["file"] if f["file"] != f["now"] else "")
    put(wf, i, 7, f["when"], fmt="yyyy-mm-dd hh:mm")
    put(wf, i, 8, round(f["dur"] / 60, 2), fmt="0.0")
    put(wf, i, 9, int(f["mouse"]) if f["mouse"] else "none", bold=True)
    put(wf, i, 10, f["session"])
    put(wf, i, 11, f["day"])
    put(wf, i, 12, f["kind"], f=GREY if f["kind"] in NOTUSE else None)
    if f["mouse"] in mouse_row:
        mr = mouse_row[f["mouse"]]
        put(wf, i, 13, "=Mice!F%d" % mr)
        put(wf, i, 14, "=Mice!G%d" % mr)
        put(wf, i, 15, "=Mice!I%d" % mr, fmt="yyyy-mm-dd")
        put(wf, i, 16, '=IF(AND(ISNUMBER(O%d),ISNUMBER(G%d)),ROUND((INT(G%d)-O%d)/7,1),"unknown")' % (i, i, i, i), fmt="0.0")
    put(wf, i, 17, "" if in_eli is None else ("Yes" if in_eli else "No"))
    put(wf, i, 18, "" if in_v2 is None else ("Yes" if in_v2 else "No"))

# ---- Sources ---------------------------------------------------------------------------------------------
wsrc = wb.create_sheet("Sources")
head(wsrc, ["Source", "How it was read", "Used for"], [36, 96, 40], freeze_col=1)
srcs = [
    ("Angelina's review", "KCNT1_AA_mouse_map_112326_v2_with_notes.xlsx, column A of Mice (17 verdicts).", "Confirmations, exclusions, 416 genotype"),
    ("New Data", "KCNT1 Active Avoidance/New Data/active_avoidance_data: 1026 .dat, 10 renamed (matched to the old files by content hash).", "Current file names"),
    ("v2 analysis", "New Data/.../KCNT1_2026/analysis_output_112326_v2 (TBL + TAreport.log).", "Which 2026 files were scored; where the run stopped"),
    ("VOS cage-card PDFs", "Downloads/OLD CAGE CARD INFO.pdf and CURRENT FULL CAGE CARD INFO.pdf, parsed with VOS_report_parser.py (output kept out of the repo).", "Sex and DOB from the physical cards"),
    ("Lab Operations Schedule", "Live xlsx export at 16:23 on 2026-11-23 (KCNT1 Active 2.0, Active (Archived), Archive, sanity tabs) and Drive revision list (oldest available 2026-10-26).", "Current Lab Ops values; history"),
    ("Apps Script (clasp)", "Clone in Colony Management/Apps Script matches the live project (status: nothing to push). Migrate.js is only the v1-vs-2.0 sanity check; VOS_Import.js is the only script that writes Sex, and only for mice on a live cage card.", "How sexes get written"),
    ("SoftMouse.NET", "Live Mouse List (2026-11-23) plus the May-Nov 2026 exports in Colony Management/SoftMouse Exports.", "Sex, DOB, genotype"),
    ("VOS census", "Every census Jarvis kept (to 2026-11-05).", "Sex, DOB"),
    ("Eli's AA outputs workbook", "DATA AND ARCHIVE/KCNT1_AA_2024_thru_June26_outputs.xlsx.", "Which mice/sessions were scored; its sex/genotype/age"),
    ("Chicken Scratch", "Drive sheets and notebooks harvested 2026-11-09 (Kcnt1 workflow, Colony_Count_092426, Brain Bank tracking, KCNT1 AA Ages, Dentate Spike Data).", "Older votes; the Behaviour log"),
]
for i, s in enumerate(srcs, 2):
    for j, v in enumerate(s, 1):
        put(wsrc, i, j, v, wrap=True, bold=(j == 1))

wb.move_sheet("Conflicts", offset=-(len(wb.sheetnames) - 2))
wb.save(OUT)
print("saved", OUT)
print("mouse status:", dict(cnt))
print("open:", [(m, c["type"]) for m in all_mice for c in conf_by_mouse[m] if c["level"] == "Open"])
print("fix:", [(m, c["type"]) for m in all_mice for c in conf_by_mouse[m] if c["level"] == "Fix"])
print("todo:", [(m, c["type"]) for m in all_mice for c in conf_by_mouse[m] if c["level"] == "Todo"])
print("worklist:", len(work), [(w["mouse"], w["now"], w["to"], w["basis"][:12], w["conf"]) for w in work])
print("fail at", FAIL_AT)
