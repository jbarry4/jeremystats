"""The confirmed mouse list and the session list for the AA story menu.

Builds on the v3 map (build3.py): final sex / YH / DOB, the file classification and the New Data names.
Writes mice.json + sessions.json here, and confirmed_mice_112326.xlsx into the KCNT1 Active Avoidance folder.
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AA_SCRATCH = os.path.join(os.path.dirname(HERE), "aa")
sys.path.insert(0, AA_SCRATCH)
sys.argv = [sys.argv[0], os.path.join(AA_SCRATCH, "out3_rebuild.xlsx")]
import build3 as B  # noqa: E402  (rebuilds the v3 map into scratch; gives us final values and the file list)

import openpyxl  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

NEWDATA = os.path.join(B.BASE, "New Data", "active_avoidance_data")
EXCLUDED = {
    "419": "Excluded by Angelina (11-23): s0 ran 15 days before s1-s16; Lab Ops already noted 'excluded from AA data due to extra sessions'.",
    "1647": "Run stopped after s0-s1 when the motor broke (10/21/26); never repeated.",
    "1648": "Run stopped after s0 when the motor broke (10/21/26); never repeated.",
    "473": "Never ran AA; the Lab Ops AA date was copied in error (Angelina, 11-23).",
}

# ---- Lab Ops injection / headplate dates (to flag procedures before AA) -------------------------------
LO = openpyxl.load_workbook(os.path.join(AA_SCRATCH, "labops.xlsx"), data_only=True)["KCNT1 Active 2.0"]
loh = [c.value for c in LO[1]]
PROC = {}
for r in LO.iter_rows(min_row=2, values_only=True):
    mm = re.match(r"^(\d+)", str(r[0] or "").replace(".0", "").strip())
    if not mm:
        continue
    m = str(int(mm.group(1)))

    def d(col):
        v = r[loh.index(col)]
        return v.date() if isinstance(v, datetime.datetime) else None
    PROC.setdefault(m, dict(inject=d("Inject"), headplate=d("Headplate"), double=r[loh.index("Double Inj?")]))

AA_KINDS = (B.AA_RUN, B.SHORT, B.EXTRA, B.REPEAT0)
mice, sessions = [], []
for r in B.mice_rows:
    m = r["mouse"]
    if r["n_usable"] == 0 or m in EXCLUDED:
        continue
    fin = B.final[m]
    fs = [f for f in B.by_mouse[m] if f["kind"] in AA_KINDS]
    s0 = min((f["when"] for f in fs if f["session"] == 0 and f["kind"] != B.REPEAT0), default=None)
    s1 = r["d1"]
    dob = datetime.date.fromisoformat(fin["dob"])
    age = (s1 - dob).days / 7.0
    flags = []
    if m in ("461", "462"):
        flags.append("not naive: a scrapped 10-session July 2024 run with shocks came first")
    if m == "457":
        flags.append("Lab Ops: 'excluded from Dylan's study for behavior'")
    if m in ("812", "813", "894"):
        flags.append("Feb 2024 pilot sessions (shocks not working) before the full run")
    if m in ("416", "418"):
        flags.append("day 2 was two days after day 1")
    if m in ("457", "458", "459", "460"):
        flags.append("day 2 began with a repeat s0")
    if m == "531":
        flags.append("s1 ran 8.6 of 10 min")
    if m == "477":
        flags.append("sex not confirmed (F from the original record; no cage card or SoftMouse entry)")
    if m in ("1653", "1659"):
        flags.append("s17 (an extra day-2 session) dropped")
    p = PROC.get(m, {})
    inj_days = None
    if p.get("inject") and s0 and p["inject"] <= s0.date():
        inj_days = (s0.date() - p["inject"]).days
        flags.append("R/O virus injection %d days before AA" % inj_days)
    if p.get("headplate") and s0 and p["headplate"] <= s0.date():
        flags.append("headplated %d days before AA" % (s0.date() - p["headplate"]).days)
    cohort = s0.strftime("%Y-%m")
    mice.append(dict(mouse=m, sex=fin["sex"], yh=fin["yh"], dob=fin["dob"], s0=s0.strftime("%Y-%m-%d"),
                     s1=s1.isoformat(), day2=r["d2"].isoformat(), age_wk=round(age, 2), age_group="young" if age < 18 else "old",
                     year=s0.year, cohort=cohort, inj_days=inj_days, flags=flags,
                     not_naive=m in ("461", "462"), injected_before=inj_days is not None,
                     injected_7d=inj_days is not None and inj_days <= 7, verdict=B.VERDICT.get(m, "")))
    for f in sorted(fs, key=lambda f: f["when"]):
        use = f["kind"] in (B.AA_RUN, B.SHORT) and 0 <= f["session"] <= 16
        why = ""
        if f["kind"] == B.EXTRA:
            why = "extra day-2 session (s17), dropped (Angelina)"
        elif f["kind"] == B.REPEAT0:
            why = "repeat s0 at the start of day 2; kept out of the curves"
        elif f["kind"] == B.SHORT:
            why = "short session (%.1f min); kept" % (f["dur"] / 60)
        sessions.append(dict(mouse=m, session=int(f["session"]), day=f["day"], folder=f["folder"], file=f["now"],
                             was=f["file"] if f["file"] != f["now"] else "", when=f["when"].strftime("%Y-%m-%d %H:%M"),
                             minutes=round(f["dur"] / 60, 2), use=bool(use), kind=f["kind"], note=why,
                             path=os.path.join(NEWDATA, f["folder"], f["now"])))

json.dump(mice, open(os.path.join(HERE, "mice.json"), "w"), indent=1)
json.dump(sessions, open(os.path.join(HERE, "sessions.json"), "w"), indent=1)
import collections  # noqa: E402
print("mice", len(mice), collections.Counter(m["yh"] for m in mice), collections.Counter((m["yh"], m["age_group"]) for m in mice))
print("sessions used", sum(s["use"] for s in sessions), "of", len(sessions))
missing = [(m["mouse"], k) for m in mice for k in range(17)
           if not any(s["mouse"] == m["mouse"] and s["session"] == k and s["use"] for s in sessions)]
print("missing sessions:", missing)
dup = collections.Counter((s["mouse"], s["session"]) for s in sessions if s["use"])
print("duplicates:", [k for k, v in dup.items() if v > 1])

# ---- the spreadsheet --------------------------------------------------------------------------------------
OUT = os.path.join(B.BASE, "confirmed_mice_112326.xlsx")
F_ = Font(name="Arial", size=10)
FB = Font(name="Arial", size=10, bold=True)
FH = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEAD = PatternFill("solid", fgColor="3B4A5A")
COL = {"WT": "D9EAD3", "Het": "FCE5CD", "Hom": "F4CCCC"}
FLAG = PatternFill("solid", fgColor="FFF2CC")
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Read me"
ws.column_dimensions["A"].width = 22
ws.column_dimensions["B"].width = 110
rows = [
    ("Confirmed AA mice", "The KCNT1 active-avoidance mice whose genotype, sex, DOB and files are settled after the v3 "
                          "map and Angelina's review (2026-11-23). One row per mouse on 'Mice'; every .dat behind them on 'Sessions'."),
    ("Mice", "%d mice: %d WT, %d Het, %d Hom (YH genotype). Sex from the VOS cage cards / SoftMouse where Lab Ops 2.0 "
             "still disagrees. 416 is WT (Transnetyx)." % (len(mice), sum(m["yh"] == "WT" for m in mice),
                                                          sum(m["yh"] == "Het" for m in mice), sum(m["yh"] == "Hom" for m in mice))),
    ("Age", "Age (weeks) = (date of session 1 - DOB) / 7, a live formula. Age group: young under 18 weeks, old 18 and over "
            "(no mouse falls between 16 and 19 weeks)."),
    ("Sessions", "s0 = habituation (the shock voltage is off; the tracker still logs 'shocks' that are not delivered, so s0 "
                 "shock, entrance and zone numbers mean nothing). s1-s8 = day 1, "
                 "s9-s16 = day 2. 'Use' = in the learning analysis. Files are the New Data names; 'Was named' gives the old name."),
    ("Flags", "Kept in every analysis but marked: 461/462 (not naive), 457 (a Lab Ops note), mice injected or headplated "
              "before AA, and small protocol differences. Results are shown with and without them where it matters."),
    ("Excluded", "; ".join("%s: %s" % (k, v) for k, v in EXCLUDED.items()) + " Mice that never ran a full AA run "
                 "(464, 466, 560, 811, 816, 872) are not listed."),
]
for i, (a, b) in enumerate(rows, 1):
    ws.cell(row=i, column=1, value=a).font = FB
    c = ws.cell(row=i, column=2, value=b)
    c.font, c.alignment = F_, WRAP

wm = wb.create_sheet("Mice")
hdr = ["Mouse", "YH genotype", "Sex", "DOB", "s0 date", "s1 date", "Day 2 date", "Age at AA (weeks)", "Age group",
       "Cohort (year-month)", "Sessions used", "Flags", "Angelina's verdict (11-23)"]
wid = [8, 11, 6, 11, 11, 11, 11, 10, 10, 11, 9, 70, 50]
for j, (h, w) in enumerate(zip(hdr, wid), 1):
    c = wm.cell(row=1, column=j, value=h)
    c.font, c.fill, c.alignment = FH, HEAD, Alignment(wrap_text=True, vertical="center")
    wm.column_dimensions[get_column_letter(j)].width = w
wm.freeze_panes = "B2"
order = {"WT": 0, "Het": 1, "Hom": 2}
for i, m in enumerate(sorted(mice, key=lambda m: (order[m["yh"]], m["age_wk"])), 2):
    vals = [int(m["mouse"]), m["yh"], m["sex"], datetime.date.fromisoformat(m["dob"]), datetime.date.fromisoformat(m["s0"]),
            datetime.date.fromisoformat(m["s1"]), datetime.date.fromisoformat(m["day2"]),
            "=ROUND((F%d-D%d)/7,1)" % (i, i), '=IF(H%d<18,"young","old")' % i, m["cohort"],
            sum(1 for s in sessions if s["mouse"] == m["mouse"] and s["use"]), "; ".join(m["flags"]), m["verdict"]]
    for j, v in enumerate(vals, 1):
        c = wm.cell(row=i, column=j, value=v)
        c.font = FB if j == 1 else F_
        c.alignment = WRAP if j in (12, 13) else TOP
        if j in (4, 5, 6, 7):
            c.number_format = "yyyy-mm-dd"
        if j == 8:
            c.number_format = "0.0"
    wm.cell(row=i, column=2).fill = PatternFill("solid", fgColor=COL[m["yh"]])
    if m["flags"]:
        wm.cell(row=i, column=12).fill = FLAG
wm.auto_filter.ref = "A1:M1"

wsx = wb.create_sheet("Sessions")
hdr = ["Mouse", "Session", "Day", "Use", "File (New Data)", "Was named", "Folder", "Recorded", "Minutes", "Note"]
wid = [8, 8, 6, 6, 36, 30, 20, 16, 8, 50]
for j, (h, w) in enumerate(zip(hdr, wid), 1):
    c = wsx.cell(row=1, column=j, value=h)
    c.font, c.fill = FH, HEAD
    wsx.column_dimensions[get_column_letter(j)].width = w
wsx.freeze_panes = "A2"
for i, s in enumerate(sorted(sessions, key=lambda s: (int(s["mouse"]), s["when"])), 2):
    vals = [int(s["mouse"]), s["session"], s["day"] if s["day"] is not None else "", "yes" if s["use"] else "no", s["file"],
            s["was"], s["folder"], datetime.datetime.strptime(s["when"], "%Y-%m-%d %H:%M"), s["minutes"], s["note"]]
    for j, v in enumerate(vals, 1):
        c = wsx.cell(row=i, column=j, value=v)
        c.font = F_
        if j == 8:
            c.number_format = "yyyy-mm-dd hh:mm"
    if not s["use"]:
        for j in range(1, 11):
            wsx.cell(row=i, column=j).fill = PatternFill("solid", fgColor="E8E8E8")
wsx.auto_filter.ref = "A1:J1"

wx = wb.create_sheet("Excluded")
for j, (h, w) in enumerate(zip(["Mouse", "Why"], [8, 110]), 1):
    c = wx.cell(row=1, column=j, value=h)
    c.font, c.fill = FH, HEAD
    wx.column_dimensions[get_column_letter(j)].width = w
for i, (k, v) in enumerate(EXCLUDED.items(), 2):
    wx.cell(row=i, column=1, value=int(k)).font = FB
    c = wx.cell(row=i, column=2, value=v)
    c.font, c.alignment = F_, WRAP
wb.save(OUT)
print("saved", OUT)
