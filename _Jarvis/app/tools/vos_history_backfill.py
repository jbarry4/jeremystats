# -*- coding: utf-8 -*-
"""Give Jarvis's VOS History the censuses from before Jarvis synced them.

Every census pasted by hand lives in the Lab Operations Schedule's "VOS
Imports" as a date-stamped block (Extracted Sorting ID / Cage Card / DOB / Sex
MMDDYY). This reads those blocks out of an .xlsx export of the sheet and
writes one record per census into Colony Management/VOS Exports/Jarvis/syncs,
the same shape backend/vos.py writes for its own syncs, so History can say
what moved between any two of them. A stamp that already has a record (the
ones Jarvis synced itself) is left alone; running it again adds nothing.

--from-status also writes the record for the last sync in status.json if it
has none: the syncs made before the record existed (2026-11-05 10:07).

    python tools/vos_history_backfill.py [--xlsx export.xlsx] [--from-status --by NAME]

Without --xlsx it downloads the export itself (the sheet is link-readable).
"""
import argparse
import csv
import datetime as dt
import json
import os
import platform
import re
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from backend import vos  # noqa: E402

SHEET_ID = "1SDXG1GpRhkjq2aKri3n06nOuR8TGio9QuQsyN656ERo"
STAMPED = re.compile(r"^(Extracted Sorting ID|Cage Card|DOB|Date of Birth|Sex) (\d{6})$")


def _text(v):
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _stamps_on_record():
    have = set()
    if os.path.isdir(vos.HISTORY):
        for name in os.listdir(vos.HISTORY):
            rec = vos._read(os.path.join(vos.HISTORY, name), None)
            if isinstance(rec, dict) and rec.get("stamp"):
                have.add(rec["stamp"])
    return have


def from_sheet(xlsx):
    import openpyxl
    ws = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)["VOS Imports"]
    rows = list(ws.iter_rows(values_only=True))
    blocks = {}
    for j, h in enumerate(rows[0]):
        m = STAMPED.match(str(h or "").strip())
        if m:
            field = {"Date of Birth": "DOB"}.get(m.group(1), m.group(1))
            blocks.setdefault(m.group(2), {})[field] = j
    have = _stamps_on_record()
    wrote = []
    for stamp, col in sorted(blocks.items(), key=lambda kv: kv[0][4:] + kv[0][:4]):
        if stamp in have or "Extracted Sorting ID" not in col:
            continue
        census = []
        for r in rows[1:]:
            get = lambda f: _text(r[col[f]]) if f in col and col[f] < len(r) else ""
            mid = get("Extracted Sorting ID")
            if mid and mid != "0":
                census.append([mid, get("Cage Card"), vos._iso_date(get("DOB")),
                               get("Sex"), ""])
        day = dt.date(2000 + int(stamp[4:]), int(stamp[:2]), int(stamp[2:4]))
        rec = {"v": 1, "date": day.isoformat(), "time": None, "stamp": stamp,
               "source": "VOS Imports", "outcome": "applied", "by": None,
               "machine": None, "sheet": None, "block_at": col["Extracted Sorting ID"] + 1,
               "cages": len({c[1] for c in census if c[1]}), "rows": len(census),
               "issues": [], "skipped": [], "result": None, "pdf": None, "csv": None,
               "census": census}
        vos._write(os.path.join(vos.HISTORY, day.isoformat() + " vos-imports.json"), rec)
        wrote.append((stamp, len(census)))
    return wrote


def from_status():
    """The last sync in status.json, if no record has it."""
    summ = vos._read(vos.STATUS, {}).get("last_sync")
    if not summ or not summ.get("applied") or summ.get("stamp") in _stamps_on_record():
        return None
    skip = {k["cage"] for k in summ.get("skipped") or []}
    census = []
    with open(summ["csv"], encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            s = summ["stamp"]
            mid, cage = r["Extracted Sorting ID " + s].strip(), r["Cage Card " + s].strip()
            if mid and cage not in skip:
                census.append([mid, cage, vos._iso_date(r["DOB " + s]),
                               r["Sex " + s].strip(), r.get("Strain", "").strip()])
    vos._record(summ, "applied", census)
    return summ["stamp"], len(census)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx")
    ap.add_argument("--from-status", action="store_true")
    ap.add_argument("--by", help="who pressed Sync: status.json does not say")
    ap.add_argument("--machine", default=platform.node())
    a = ap.parse_args()
    if a.from_status:
        vos.WHO["fn"] = lambda: (a.by, a.machine)
        print("from status.json:", from_status() or "nothing to add")
    xlsx = a.xlsx
    if not xlsx:
        xlsx = os.path.join(tempfile.mkdtemp(), "lab_ops.xlsx")
        urllib.request.urlretrieve("https://docs.google.com/spreadsheets/d/%s/export?format=xlsx"
                                   % SHEET_ID, xlsx)
    for stamp, n in from_sheet(xlsx):
        print("VOS Imports %s: %d mice" % (stamp, n))
    print(json.dumps([(h["date"], h["source"], h["mice"], h["diff"] and
                       {k: len(v) for k, v in h["diff"].items()}) for h in vos.history()]))


if __name__ == "__main__":
    main()
