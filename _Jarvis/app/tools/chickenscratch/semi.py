# -*- coding: utf-8 -*-
"""Facts from the lab's other trackers: tables that have a mouse column but
were never the master sheet (Dylan's Kcnt1 workflow, colony counts, the brain
bank list, the PTEN shipment rosters, the transcribed notebook, recording
folder listings, PTEN Recordings' per-mouse blocks...).

Same fact shape as structured.py, written to <work>/facts/semi.jsonl. A
column becomes a fact type by its header (HEADER_TYPES); a few layouts that
are not one-mouse-per-row get their own reader below.
"""
import json
import os
import re
import sys

import openpyxl
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import structured as S  # noqa: E402

W = S.W
SRC = {s["id"]: s for s in json.load(open(os.path.join(W, "sources.json"), encoding="utf-8"))}
LOC = {s["id"]: s for s in json.load(open(os.path.join(W, "local_sources.json"), encoding="utf-8"))}

ID_HEADERS = ("mouse id", "mouse", "mouse #", "mouse_id", "uvm_id", "uvm id", "animal (folder)",
              "🐭id", "mouse_id_#")
HEADER_TYPES = [
    (r"^(dob|born|date of birth)$", "dob"), (r"^sex$", "sex"),
    (r"^(yh|sst|pv|geno|genotype|cre|yh genotype)$", "genotype"),
    (r"int.?cage|animal.?#|ear punch", "identity"), (r"cage", "cage"), (r"^(role|state)$", "role"), (r"^(alive|status)$", "alive"),
    (r"tail snip|genotyped", "tail_snip"), (r"^inject|virus|viral", "injection"),
    (r"active avoidance|^aa date|spatial.?accura|behavio", "behavior"),
    (r"headplat|^surgery", "surgery_headplate"), (r"h3|h10|h1 probe|^opto", "probe_implant"),
    (r"perfus", "perfusion"), (r"euthan|died|dead|dod", "death"),
    (r"slice|stain|image|section|hipp", "histology"),
    (r"skull thin|ultrasound", "surgery_other"), (r"location|brain bank", "brain_bank"),
    (r"note|comment", "note"), (r"record_|baseline|cno|dcz|hemi rec|session", "recording_session"),
    (r"ship", "shipment"), (r"putative|^grp$|^group$|subgrp|dko|^code$", "group"),
    (r"bad chan", "recording_session"), (r"well plate|sample avail|thesis\?", "note"),
]


def htype(h):
    hl = h.lower().strip()
    for pat, t in HEADER_TYPES:
        if re.search(pat, hl):
            return t
    return None


def key_for(raw, project):
    if project == "KCNT1":
        return S.kcnt1_key(raw)
    if project == "PTEN":
        return S.pten_key(raw)
    return None


def table(ws, source, sid, project, hdr_row=1, id_col=None, cohort=None, skip_cols=(),
          tab_note=None):
    """One mouse per row; every non-empty cell becomes a fact typed by its header."""
    rows = list(ws.iter_rows(min_row=hdr_row))
    if not rows:
        return 0
    hdr = [S.txt(c.value) for c in rows[0]]
    if id_col is None:
        id_col = next((i for i, h in enumerate(hdr) if h.lower() in ID_HEADERS), None)
        if id_col is None:
            return 0
    n = 0
    for row in rows[1:]:
        raw = row[id_col].value if id_col < len(row) else None
        key = key_for(raw, project)
        if not key:
            continue
        for j, h in enumerate(hdr):
            if j == id_col or j >= len(row) or j in skip_cols:
                continue
            v = row[j].value
            if v in (None, "", False) or S.txt(v) in ("", "-"):
                continue
            t = htype(h) if h else None
            if not t:
                continue
            if t == "alive" and S.txt(v).lower() not in ("yes", "no", "alive", "dead", "deceased", "y", "n"):
                t = "brain_bank"
            d = S.iso(v)
            loc = "%s!%s%d" % (ws.title, get_column_letter(j + 1), row[0].row)
            f = dict(key=key, project=project, raw=S.txt(raw), type_=t, source=source,
                     source_id=sid, locator=loc, date=d, date_raw=S.txt(v),
                     value=h if d else "%s=%s" % (h, S.txt(v)), conf="medium")
            S.fact(**f)
            if cohort:
                S.OUT[-1]["cohort"] = cohort
            if tab_note:
                S.OUT[-1]["detail"] = tab_note
            n += 1
    return n


def wb_of(sid):
    s = SRC.get(sid) or LOC.get(sid)
    return openpyxl.load_workbook(s["local"], data_only=True), (s.get("path") or s.get("name"))


def by_name(pat):
    for s in list(SRC.values()) + list(LOC.values()):
        if re.search(pat, s.get("path") or "") and (s.get("local") or "").lower().endswith((".xlsx", ".csv")):
            return s["id"]
    return None


# --- one-mouse-per-row tables -------------------------------------------------

def trackers():
    jobs = [
        (r"^Kcnt1 workflow$", "KCNT1", {"Current KCNT1": 1, "Available": 3, "Sheet1": 1,
                                        "020625 Colony Overview": 1, "101625 Colony VOS Cross Check": 1,
                                        "Behaviour": 1}, None),
        (r"Colony_Count_092426$", "KCNT1", {"Sheet2": 1, "Sheet3": 1}, None),
        (r"Archive/Brain Bank tracking$", "KCNT1", {"Sheet1": 1}, None),
        (r"KCNT1 AA Ages$", "KCNT1", {"2024 AA": 1, "2026 AA": 1}, None),
        (r"Archive/Genotype List$", "KCNT1", None, None),
        (r"^Pten Blind$", "PTEN", {"ID_July 17, 2024 Shipment": 1},
         "DKO cohort (Pten x Raptor, shipment 2024-07-17)"),
        (r"^Pten 2KO Unblind$", "PTEN", {"Sheet1": 2},
         "DKO cohort (Pten x Raptor, shipment 2024-07-17)"),
        (r"PTEN Toothy Data all bad channels", "PTEN", None, None),
        (r"IED/01_Session_Inventory/Mouse Recording Sessions", "PTEN", None, None),
    ]
    for pat, proj, tabs, cohort in jobs:
        sid = by_name(pat)
        if not sid:
            print("  not found:", pat)
            continue
        wb, label = wb_of(sid)
        for ws in wb.worksheets:
            if tabs is not None and ws.title not in tabs:
                continue
            hr = (tabs or {}).get(ws.title, 1)
            n = table(ws, label + " / " + ws.title, sid, proj, hdr_row=hr, cohort=cohort)
            print("  %4d facts  %s / %s" % (n, label[-50:], ws.title))


def pten_2023_roster():
    """Mice.xlsx: the 2022-2023 'Pten x Td' cohort. Its '#' column is the
    m-number the recordings use (#15 'dead early on / urethane recording' is
    PTEN Recordings' 'M15 ctl - urethane (malocclusion)')."""
    sid = by_name(r"Data Anylasis/Mice\.xlsx$")
    wb, label = wb_of(sid)
    ws = wb.active
    hdr = [S.txt(c.value) for c in ws[1]]
    num = hdr.index("#")
    cohort = "2023 cohort (Pten x Td, arrived 2023-01-10)"
    for row in ws.iter_rows(min_row=2):
        raw = S.txt(row[num].value)
        key = S.pten_key(raw)
        if not key:
            continue
        for j, h in enumerate(hdr):
            v = row[j].value if j < len(row) else None
            if j == num or v in (None, ""):
                continue
            t = {"Genotype": "genotype", "Cage Card": "cage", "DOB": "dob", "Animal #": "identity",
                 "Sex": "sex", "Injected by:": "injection", "Virus": "injection",
                 "Viral Volume": "injection", "Shipment cage": "shipment", "UVM ID": "identity",
                 "Notes upon arrival on 1/10/23": "health", "Experiment": "behavior",
                 "% Infectivity": "histology", "State": "note", "Behavorial Grade": "behavior",
                 "Perfusion Date": "perfusion"}.get(h, "note")
            S.fact(key, "PTEN", raw, t, label, sid, "Sheet1!%s%d" % (get_column_letter(j + 1), row[0].row),
                   date=S.iso(v), date_raw=S.txt(v), value="%s=%s" % (h, S.txt(v)), conf="medium")
            S.OUT[-1]["cohort"] = cohort


def pten_recordings_blocks():
    """PTEN Recordings.xlsx: one block of columns per mouse; row 2 names the
    mouse, rows 3+ are 'session | date | probe | notes...'."""
    for pat in (r"Data Anylasis/PTEN Recordings\.xlsx$", r"Archive/PTEN/PTEN Recordings \(3\)\.xlsx$"):
        sid = by_name(pat)
        if not sid:
            continue
        wb, label = wb_of(sid)
        for ws in wb.worksheets:
            rows = [[c.value for c in r] for r in ws.iter_rows()]
            if len(rows) < 3:
                continue
            for hdr_i in range(min(4, len(rows))):
                starts = [j for j, v in enumerate(rows[hdr_i]) if re.fullmatch(r"[Mm]\d{1,3}", S.txt(v))]
                if len(starts) >= 2:
                    break
            else:
                continue
            grp_row = rows[hdr_i - 1] if hdr_i else []
            for bi, j0 in enumerate(starts):
                j1 = starts[bi + 1] if bi + 1 < len(starts) else len(rows[hdr_i])
                raw = S.txt(rows[hdr_i][j0])
                key = S.pten_key(raw)
                grp = S.txt(grp_row[j0]) if j0 < len(grp_row) else ""
                head = " ".join(S.txt(v) for v in rows[hdr_i][j0 + 1:j1] if S.txt(v))
                if grp or head:
                    S.fact(key, "PTEN", raw, "note", label + " / " + ws.title, sid,
                           "%s!%s%d" % (ws.title, get_column_letter(j0 + 1), hdr_i + 1),
                           value="block header", detail=("group: %s. " % grp if grp else "") + head)
                for r in range(hdr_i + 1, len(rows)):
                    cells = rows[r][j0:j1]
                    if not any(S.txt(c) for c in cells):
                        continue
                    sess = S.txt(cells[0]) if cells else ""
                    d = next((S.iso(c) for c in cells[:3] if S.iso(c)), None)
                    rest = " | ".join(S.txt(c) for c in cells[1:] if S.txt(c) and not S.iso(c))
                    S.fact(key, "PTEN", raw, "recording_session", label + " / " + ws.title, sid,
                           "%s!%s%d" % (ws.title, get_column_letter(j0 + 1), r + 1),
                           date=d, date_raw=next((S.txt(c) for c in cells[:3] if S.iso(c)), None),
                           session=sess or None, value="session %s" % (sess or "?"), detail=rest,
                           conf="medium")


def eeg_note_blocks():
    """Dylan's EEG Notes / CSD Decoding: blocks of columns per mouse."""
    sid = by_name(r"^Kcnt1 workflow$")
    wb, label = wb_of(sid)
    for tab in ("EEG Notes", "CSD Decoding"):
        if tab not in wb.sheetnames:
            continue
        ws = wb[tab]
        rows = [[c.value for c in r] for r in ws.iter_rows()]
        id_row = 1 if tab == "EEG Notes" else 1
        r0 = rows[id_row]
        if tab == "EEG Notes":
            starts = [j for j, v in enumerate(r0) if S.kcnt1_key(v) and j + 1 < len(r0)]
        else:
            starts = [j + 1 for j, v in enumerate(r0) if S.txt(v) == "Mouse"]
        for bi, j0 in enumerate(starts):
            j1 = starts[bi + 1] if bi + 1 < len(starts) else len(r0)
            raw = S.txt(r0[j0])
            key = S.kcnt1_key(raw)
            if tab == "EEG Notes" and S.txt(r0[j0 + 1]):
                S.fact(key, "KCNT1", raw, "genotype", label + " / " + tab, sid,
                       "%s!%s2" % (tab, get_column_letter(j0 + 2)), value="YH=%s" % S.txt(r0[j0 + 1]),
                       conf="medium")
            for r in range(id_row + 1, len(rows)):
                cells = rows[r][j0 - (1 if tab == "CSD Decoding" else 0):j1]
                txt = " | ".join(S.txt(c) for c in cells if S.txt(c))
                if not txt or txt in ("L/R | Depth | Opto/tones | Notes",):
                    continue
                sess = S.txt(cells[0])
                S.fact(key, "KCNT1", raw, "recording_session", label + " / " + tab, sid,
                       "%s!%s%d" % (tab, get_column_letter(j0 + 1), r + 1), session=sess or None,
                       value="%s note, %s" % (tab, sess or "?"), detail=txt, conf="medium")


def dko_corrections():
    """Pten 2KO Unblind / Corrections: someone re-checked ear punches, sex,
    DOB and DKO status against the cages. Each row is kept whole, on both
    the UVM ID it starts from and the M# it ends at."""
    sid = by_name(r"^Pten 2KO Unblind$")
    wb, label = wb_of(sid)
    if "Corrections" not in wb.sheetnames:
        return
    ws = wb["Corrections"]
    hdr = [S.txt(c.value) for c in ws[2]]
    for row in ws.iter_rows(min_row=3, values_only=True):
        cells = [S.txt(v) for v in row]
        if not any(cells):
            continue
        text = " | ".join("%s: %s" % (h or "(blank)", v) for h, v in zip(hdr, cells) if v)
        keys = {S.pten_key(cells[5]) if len(cells) > 5 else None,
                S.pten_key(cells[18]) if len(cells) > 18 else None}
        for k in keys - {None}:
            S.fact(k, "PTEN", k.split(":")[1], "note", label + " / Corrections", sid, "Corrections",
                   value="DKO roster correction row", detail=text, conf="medium")
            S.OUT[-1]["cohort"] = "DKO cohort (Pten x Raptor, shipment 2024-07-17)"


def notebook_sessions():
    """The transcribed Feb-Jun 2026 notebook: one session per row, already
    cross-checked against the data folders by whoever made it."""
    sid = by_name(r"notebookFeb-Jun 2026\.xlsx$")
    wb, label = wb_of(sid)
    ws = wb["Sessions"]
    hdr = [S.txt(c.value) for c in ws[1]]
    g = lambda row, h: S.txt(row[hdr.index(h)].value) if h in hdr else ""
    for row in ws.iter_rows(min_row=2):
        raw = g(row, "Mouse ID") or g(row, "Mouse (as written)")
        key = S.kcnt1_key(raw)
        if not key:
            continue
        loc = "Sessions!A%d (%s)" % (row[0].row, g(row, "Session ID"))
        d = S.iso(row[hdr.index("Date")].value) or None
        S.fact(key, "KCNT1", raw, "recording_session", label, sid, loc, date=d,
               date_raw=g(row, "Date (as written)"), who=g(row, "Initials") or None,
               session=g(row, "Session") or None,
               value="%s %s %s" % (g(row, "Session"), g(row, "Hemisphere"), g(row, "Probe")),
               detail="; ".join("%s: %s" % (h, g(row, h)) for h in (
                   "Genotype", "Z0 (probe contact)", "Rec start", "Rec stop", "Channel notes",
                   "Observations", "Data folder", "Folder match", "Notes (verbatim)") if g(row, h)),
               conf="high" if "confirmed" in g(row, "Folder match") else "medium")
        if g(row, "Conflicts"):
            S.fact(key, "KCNT1", raw, "note", label, sid, loc, date=d, session=g(row, "Session") or None,
                   value="notebook vs data conflict", detail=g(row, "Conflicts"), conf="medium")
    ws = wb["Data with no notebook entry"]
    for row in ws.iter_rows(min_row=2, values_only=True):
        m = re.search(r"(\d{3,4})", S.txt(row[0]))
        key = S.kcnt1_key(m.group(1)) if m else None
        S.fact(key, "KCNT1", row[0], "recording_session", label + " / Data with no notebook entry",
               sid, "Data with no notebook entry", date=S.iso(row[1]) or None, date_raw=S.txt(row[1]),
               value="recording folder with no notebook entry", detail=S.txt(row[3]), conf="medium")


def folder_listing():
    """KCNT1_~1.CSV: every Cheetah session folder, with its own timestamp."""
    for sid, s in SRC.items():
        if not s["path"].endswith("KCNT1_~1.CSV") or not (s.get("local") or "").endswith(".csv"):
            continue
        import csv
        with open(s["local"], encoding="utf-8-sig", errors="replace", newline="") as fh:
            for i, r in enumerate(csv.DictReader(fh), 2):
                m = re.search(r"(\d{3,4})", r.get("Animal") or "")
                key = S.kcnt1_key(m.group(1)) if m else None
                folder = r.get("Session") or ""
                ts = re.search(r"(20\d\d)-(\d\d)-(\d\d)_(\d\d)-(\d\d)", folder)
                sm = re.search(r"_s(\d+)", folder, re.I)
                S.fact(key, "KCNT1", r.get("Animal"), "recording_session", s["path"], sid, "row %d" % i,
                       date="%s-%s-%s" % ts.groups()[:3] if ts else None,
                       time="%s:%s" % ts.groups()[3:] if ts else None,
                       session=sm.group(1) if sm else None,
                       value="Cheetah folder (%s, %s)" % (r.get("ProbeModel"), r.get("ProbeLabel")),
                       detail="folder: %s" % folder, conf="high")
        break


if __name__ == "__main__":
    S.OUT.clear()
    trackers()
    pten_2023_roster()
    pten_recordings_blocks()
    dko_corrections()
    eeg_note_blocks()
    notebook_sessions()
    folder_listing()
    with open(os.path.join(W, "facts", "semi.jsonl"), "w", encoding="utf-8") as fh:
        for f in S.OUT:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    from collections import Counter
    print("semi facts:", len(S.OUT))
    print(Counter(f["source"].split(" / ")[0][-40:] for f in S.OUT).most_common(30))
