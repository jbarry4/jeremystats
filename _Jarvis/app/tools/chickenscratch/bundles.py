# -*- coding: utf-8 -*-
"""Sort the unstructured sources into reading bundles for the extraction
agents, and boil the huge numeric PTEN tables down to which mouse / session /
condition / date they cover (nobody needs to read 50 MB of theta power to learn
that m13 s17 was a CNO day). Writes <work>/bundles.json and
<work>/text/digest__*.txt."""
import collections
import csv
import json
import os
import re

import openpyxl

W = os.path.expandvars(r"%LOCALAPPDATA%\Jarvis\chickenscratch")
SRC = json.load(open(os.path.join(W, "all_sources.json"), encoding="utf-8"))
ALL = json.load(open(os.path.join(W, "sources.json"), encoding="utf-8"))

ID_COLS = re.compile(r"^(mouse|mouse_?id|animal|subject|rat|id|session|sess|session_?id|cond|"
                     r"condition|grp|group|genotype|subgrp|subgroup|date|rec_?date|file|"
                     r"filename|path|folder|treatment|drug|sex|cohort|batch)$", re.I)


def digest_table(path, label):
    """Distinct values of the identity-looking columns, with counts."""
    combos = collections.Counter()
    cols = None
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
            rd = csv.reader(fh)
            hdr = next(rd)
            cols = [i for i, h in enumerate(hdr) if ID_COLS.match(h.strip())]
            for r in rd:
                combos[tuple(r[i] if i < len(r) else "" for i in cols)] += 1
        names = [hdr[i] for i in cols]
        tabs = {"(csv)": (names, combos)}
    else:
        tabs = {}
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            try:
                hdr = [str(h or "").strip() for h in next(it)]
            except StopIteration:
                continue
            cols = [i for i, h in enumerate(hdr) if ID_COLS.match(h)]
            c = collections.Counter()
            for r in it:
                c[tuple(str(r[i]) if i < len(r) and r[i] is not None else "" for i in cols)] += 1
            tabs[ws.title] = ([hdr[i] for i in cols], c)
    out = ["DIGEST of %s -- distinct identity columns, with row counts" % label]
    for tab, (names, c) in tabs.items():
        out.append("=== %s: columns %s" % (tab, names))
        for k, n in sorted(c.items()):
            out.append("%s  (x%d)" % (" | ".join(k), n))
    return "\n".join(out)


def pick(*pats, kinds=None, exclude=()):
    got = []
    for s in SRC:
        p = s["path"]
        if kinds and s.get("kind") not in kinds:
            continue
        if any(re.search(x, p, re.I) for x in exclude):
            continue
        if any(re.search(x, p, re.I) for x in pats):
            got.append(s)
    return got


def entry(s):
    return {"label": s["path"], "drive_id": s["id"], "text": s.get("text"),
            "chars": s.get("chars"), "modified": s.get("modified"), "owner": s.get("owner"),
            "editor": s.get("editor")}


def main():
    bundles = collections.OrderedDict()
    by_id = {s["id"]: s for s in ALL}

    # --- vision: handwritten recording notes, photos, scans -------------------
    scans = [s for s in ALL if s.get("scan_pages") and re.search(
        r"KCNT1|breeding|bryan ship", s["path"])]
    rec_scans = [s for s in scans if "Recordings/Data Dump" in s["path"]]
    other_scans = [s for s in scans if s not in rec_scans]
    pages = [(s, p) for s in sorted(rec_scans, key=lambda s: s["path"]) for p in s["scan_pages"]]
    third = (len(pages) + 2) // 3
    for i in range(3):
        chunk = pages[i * third:(i + 1) * third]
        bundles["handwritten_recording_notes_%d" % (i + 1)] = [
            {"label": s["path"] + " (page %s)" % re.search(r"_p(\d+)\.png$", p).group(1),
             "drive_id": s["id"], "image": p, "modified": s.get("modified")} for s, p in chunk]
    photos = sorted([s for s in ALL if s.get("photo")], key=lambda s: s["path"])
    rec_photos = [s for s in photos if s["path"].startswith("Rec data 072826")]
    third = (len(rec_photos) + 2) // 3
    for i in range(3):
        bundles["rec_data_072826_photos_%d" % (i + 1)] = [
            {"label": s["path"], "drive_id": s["id"], "image": s["photo"],
             "created": s.get("created")} for s in rec_photos[i * third:(i + 1) * third]]
    bundles["breeding_cagecards_pten_photos"] = (
        [{"label": s["path"] + " (page %s)" % re.search(r"_p(\d+)\.png$", p).group(1),
          "drive_id": s["id"], "image": p} for s in other_scans for p in s["scan_pages"]] +
        [{"label": s["path"], "drive_id": s["id"], "image": s["photo"],
          "created": s.get("created")} for s in photos if s not in rec_photos])

    # --- text: KCNT1 ----------------------------------------------------------
    k_a = pick(r"KCNT1_Dylan_recording_notes", r"notebookFeb-Jun 2026", r"KCNT1_~1\.CSV",
               r"Historical (Recording|Cage Card|Active Avoidance) Archive",
               r"ephys_recording_session", r"KCNT1 Urethane", r"KCNT1_urethane_sessions\.csv",
               r"/Kcnt1 workflow$|^Kcnt1 workflow$", exclude=(r"Data Bank",))
    k_b = pick(r"Colony Notes \(Eli\)", r"KCNT1/colony counts", r"Colony_Count_092426",
               r"KCNT1 AA Ages", r"Genotype List", r"Brain Bank tracking", r"Information for Kathy",
               r"Lab meeting notes", r"Lab Meet Notes", r"Planning Doc",
               r"Shahriar, plz talk to Rain", r"Archive/Untitled document",
               r"To Be Sorted/Untitled", r"^Untitled document", r"Abstract thoughts",
               r"Dylan Poster text", r"Jarvis update notes", r"Archive/Untitled spreadsheet",
               r"Barry ECD Lab Drive/Untitled document", r"SoftMouse\.NET$")
    k_c = pick(r"KCNT1AA \(version 1\)", r"Angelina Age Analysis/KCNT1_AA_2024_thru_June26_outputs",
               r"KCNT1/Breeding/.*\.(xlsx|csv)$", r"Breeding/Colony")
    bundles["kcnt1_recording_records"] = [entry(s) for s in k_a]
    bundles["kcnt1_colony_and_notes"] = [entry(s) for s in k_b]
    bundles["kcnt1_behavior_tables"] = [entry(s) for s in k_c if s not in k_b]

    # --- text: PTEN -----------------------------------------------------------
    p_a = pick(r"PTEN Recordings", r"Data Anylasis/Mice\.xlsx", r"^Pten Blind$", r"^Pten 2KO Unblind$",
               r"^PTEN Collaboration$", r"bryan ship", r"Food Dep SHeet", r"m5 food dep",
               r"Averaged virus graphs", r"IED/01_Session_Inventory/Mouse Recording Sessions",
               r"IED/01_Session_Inventory/batch_input", r"PTEN Toothy Data all bad channels",
               r"IED_session_summary", r"IED_summary\.xlsx", r"CFC Revival Plan",
               r"Toothy_Troubleshooting/Toothy Drive", r"Take 4 Data/Methods",
               r"stakedinnerticket/(README|FIGURE_LEGEN|data/prepped/(data_dict|per_anima))",
               r"Thesis figs", r"Mice Anesthesia", r"Mouse Surgery", r"Surgery Protocol Discussion",
               r"^2nd Meeting$")
    p_b = pick(r"\*Hunter Holoubek Honors Thesis 2026\.pdf", r"Noah Elste Honors Thesis 2024 \(Final\)",
               r"Noah Elste Revised Thesis Proposal\.pdf", r"SURF/SURF proposal\.docx",
               r"Research for Credit Final", r"NBH Poster smal", r"NBH Abstract Noah Elste\.docx",
               r"Figure 6 legend", r"Narrative( Version 2)?\.docx", r"^Thesis Defense$",
               r"^Defence presentation$", r"Award Completion Essay\.docx", r"SURF research goals\.docx")
    p_c = pick(r"Goal Zone anylasis", r"New behvaioral results", r"Learning early phases",
               r"Rewards and Entrences", r"GRAPHS recovery", r"speed anyl", r"testbase", r"testCNO",
               r"Data Anylasis/NOR", r"Thesis Figures\.xlsx", r"Example Feeder Sheet",
               r"1_IEDlevel_IPvsPP_Base\.docx")
    bundles["pten_records"] = [entry(s) for s in p_a]
    bundles["pten_theses_and_writing"] = [entry(s) for s in p_b]
    bundles["pten_behavior_tables"] = [entry(s) for s in p_c]

    # digests of the huge PTEN tables
    digests = []
    for pat in (r"CFCMerged_complete\.csv$", r"CFCMerged_CNO\.csv$", r"MeanTheta_DKO_\d\.xlsx$",
                r"spectral_props_(AllData|2nd-Batch|DKO_\d)\.xlsx$", r"PTEN_DG_StakeDin",
                r"FOOOF Playgroun/event-bank"):
        for s in pick(pat):
            src = by_id.get(s["id"], s).get("local") or s.get("local")
            if not src or not os.path.exists(src):
                continue
            tp = os.path.join(W, "text", "digest__%s.txt" % s["id"])
            if not os.path.exists(tp):
                try:
                    t = digest_table(src, s["path"])
                except Exception as e:                   # noqa: BLE001
                    t = "[digest failed: %s]" % e
                with open(tp, "w", encoding="utf-8") as fh:
                    fh.write(t)
            digests.append({"label": "DIGEST " + s["path"], "drive_id": s["id"], "text": tp,
                            "chars": os.path.getsize(tp)})
    bundles["pten_records"] += digests

    with open(os.path.join(W, "bundles.json"), "w", encoding="utf-8") as fh:
        json.dump(bundles, fh, indent=1)
    for b, items in bundles.items():
        print("%-34s %3d items %8d chars %3d images" % (
            b, len(items), sum(i.get("chars") or 0 for i in items),
            sum(1 for i in items if i.get("image"))))


if __name__ == "__main__":
    main()
