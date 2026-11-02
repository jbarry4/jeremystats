# -*- coding: utf-8 -*-
"""import_ied.py -- bring a hand-sorted IED tree into the Event Bank.

WHAT THE TREE IS

One folder per recording. A detector wrote a table of events; a person
then looked at rendered pictures of them and dragged each picture into a
folder, and the folder it ended up in IS the decision:

    Take 3/PTEN_M13_pten_m13s2aug1/
        ets.mat                     [N x 2] onsamp, offsamp
        ets_converted_events.xlsx   the same table, exported
        Solid/    Evt010_7ch_align-midpoint_....png   <- the real IEDs
        Sputter/  Evt003_....png
        Flag/     Evt270_7ch.png
        Garbage/  Evt002_6ch.png

Nothing but the directory listing records any of that, which is why this
exists: a decision that lives only in a folder name is one `robocopy`
away from being lost.

FOUR THINGS THIS HAD TO ESTABLISH RATHER THAN ASSUME

  THE SAMPLE RATE. `onsamp` is a sample index and the file does not say
  of what. Measured: the last event of m13 s2 ends at sample 56,101,080,
  the registry has that recording at 1871.97 s, and the quotient is
  29,968 -- 30 kHz, with the last event two seconds before the end. At
  1 kHz it would have been a fifteen-hour recording. Checked per folder
  below, and a folder whose last event lands past the end is refused.

  THE INDEX BASE. `Evt010` is a row of that table, and being off by one
  would mislabel every event while looking perfectly sensible. Measured,
  because both bases land on SOME event: under 1-based the events a
  person called Solid are 1.48x the amplitude of the ones they called
  Garbage; under 0-based, 1.04 -- no separation at all. 1-based. The
  highest `Evt` number in every folder is also <= N, which 0-based would
  not require.

  WHICH FOLDER IS THE SORT. In most recordings the category folders sit
  at the top; in two they sit inside `group_05-10 (N)/`, and the
  top-level `Solid`/`Sputter` there are copies of two of the four. Taken
  as the directory holding the most distinct categories, so the sort is
  read wherever it happens to be and the render folders that also have a
  `Solid` (two files, no Garbage) do not win.

  ONLY THE SORT ROOT'S OWN CHILDREN COUNT. `Garbage/` has sub-folders --
  `Dentate Spike`, `Flag`, `Garbage` -- and they OVERLAP: in m13 s2 the
  same Evt002 sits in three of them at once, so they are not a partition
  and cannot be read as verdicts. Everything under `Garbage/` is garbage
  either way, and the top-level sort is corroborated exactly by the
  pipeline's own Master_Stats.csv (13 SOLID, 18 SPUTTER for m13 s2).

THE THREE FOLDERS MARKED "(Handsorted)" ARE A DIFFERENT SHAPE

In those, `ets_converted_events.xlsx` is NOT the export of `ets.mat`. It
is shorter (18 of 67; 49 of 172; 11 with no .mat at all), every row is
exactly 10 samples wide where a real event window is 750 to 50,000, and
its midpoints do not line up with the long list -- the nearest row is a
median of 492 and 269,210 samples away. It is a separate, later,
SOLID-ONLY run of point markers, and `Solid/` there holds exactly one
blank 289-byte stub per row, numbered 1..N against it.

So those folders hold two incompatible numberings. The solid-only list
is imported, because it is the answer to the question this tree is for;
the long list's Garbage numbering belongs to the other run and is left
where it is rather than merged into times it does not describe.

WHERE THE STAMP GOES

At the MIDPOINT of the on/off pair, which is what the review images are
aligned to -- their names say `align-midpoint`. `end` is the window's
end, so the onset is still exactly recoverable as `2*start - end`.

WHAT IS NOT CARRIED

`Hidden`/`hidden` folders hold pictures withdrawn from a category. A
withdrawal is not a verdict, so nothing under one is labelled, and the
count is in the note. `Take 3/HIDDEN/` holds a whole eleventh recording
set aside the same way; it is reported and not imported.

`Garbage/Dentate Spike` holds events a person decided were dentate
spikes rather than discharges. The IED vocabulary has no label for that
and the bank's per-event whitelist is deliberate, so they are `garbage`
here -- true, within a set about IEDs -- and the count is in the note.

    python tools/import_ied.py                    # dry run; says what it would do
    python tools/import_ied.py --write
    python tools/import_ied.py --write --replace  # re-import, dropping ours
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import eventbank, ids, store              # noqa: E402

PIPELINE = "IED hand-sort (ETS)"
DEFAULT_ROOT = r"C:\Users\Z390\Desktop\IED DATA\Take 3"

# A folder name -> the decision it records. These are the sort's own
# categories; anything else is a render folder or an output folder.
CATEGORIES = {"solid": "solid", "sputter": "sputter",
              "flag": "flag", "garbage": "garbage"}
LABEL_NAME = {"solid": "Solid", "sputter": "Sputter",
              "garbage": "Garbage", "flag": "Flag"}

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11,
          "dec": 12}

EVT = re.compile(r"Evt[_]?(\d+)", re.I)

# A row this narrow is a point marker, not an event window. The real
# detector's narrowest window anywhere in this tree is 750 samples.
POINT_W = 64


def parse_folder(name):
    """(project, mouse, session, month, day) from a folder name, or None."""
    base = re.sub(r"\s*\(.*\)\s*$", "", name).strip()
    bits = base.split("_")
    if len(bits) < 2:
        return None
    m = re.search(r"m(\d+)s(\d+)([a-z]+)(\d+)$", bits[-1], re.I)
    if not m:
        return None
    mon = MONTHS.get(m.group(3).lower())
    if not mon:
        return None
    return (bits[0].strip().upper(), int(m.group(1)), int(m.group(2)),
            mon, int(m.group(4)))


def mat_rows(path):
    try:
        import scipy.io as sio
        arr = sio.loadmat(path).get("ets")
    except Exception:                                    # noqa: BLE001
        return []
    if arr is None or not getattr(arr, "size", 0):
        return []
    return [(int(a), int(b)) for a, b in arr]


def xls_rows(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for row in wb.worksheets[0].iter_rows(values_only=True):
        if not row or row[0] is None:
            continue
        try:
            out.append((int(row[0]), int(row[1])))
        except (TypeError, ValueError):
            continue                                     # the header row
    return out


def tables(folder):
    """The detector's list and the solid-only list, whichever are here.

    They are told apart by shape, not by filename: the short one is all
    ten-sample point markers and is a different run. See the module
    docstring.
    """
    mat = os.path.join(folder, "ets.mat")
    xls = os.path.join(folder, "ets_converted_events.xlsx")
    long_ = mat_rows(mat) if os.path.exists(mat) else []
    short = xls_rows(xls) if os.path.exists(xls) else []
    if long_ and short and len(short) == len(long_):
        return long_, mat, None, None            # the ordinary case: one list
    if short and all((b - a) <= POINT_W for a, b in short):
        return (long_ or None), mat, short, xls  # two runs in one folder
    if not long_ and short:
        return short, xls, None, None            # only the export survives
    return long_, mat, None, None


def sort_root(folder):
    """The directory the category folders actually live in."""
    best, score = None, 0
    for root, dirs, _files in os.walk(folder):
        if any(p.lower() == "hidden"
               for p in os.path.relpath(root, folder).split(os.sep)):
            continue
        cats = {CATEGORIES[d.lower()] for d in dirs if d.lower() in CATEGORIES}
        # Distinct categories decides it, and the shallower wins a tie: a
        # render folder with Solid and Sputter must not beat the real sort.
        if len(cats) > score:
            best, score = root, len(cats)
    return best


def verdicts(root):
    """{event number: label}, from the sort root's own children only."""
    marks, when, moved, hidden, deeper = {}, {}, [], set(), {}
    if not root:
        return marks, moved, hidden, deeper
    for d in sorted(os.listdir(root)):
        lid = CATEGORIES.get(d.lower())
        if not lid or not os.path.isdir(os.path.join(root, d)):
            continue
        cat = os.path.join(root, d)
        for f in os.listdir(cat):
            m = EVT.match(f)
            path = os.path.join(cat, f)
            if not m or not os.path.isfile(path):
                continue
            num, age = int(m.group(1)), os.path.getmtime(path)
            # THE NEWER COPY WINS, and it is worth being explicit about
            # why rather than letting `sorted()` decide by initial. A
            # picture in two categories is somebody changing their mind
            # and leaving the old copy: in m13 s2, Evt035 and Evt040 sit
            # in Solid from September and in Sputter from six weeks
            # later. Alphabetical order happens to agree there and would
            # not next time.
            if num in marks and marks[num] != lid:
                if age <= when.get(num, 0):
                    continue
                moved.append((num, marks[num], lid))
            marks[num], when[num] = lid, age
        # Below a category: a finer sort of the same events, and where it
        # was checked the sub-folders overlap rather than partition.
        # Counted for the note, never read as a verdict.
        for sub, _dirs, files in os.walk(cat):
            if sub == cat:
                continue
            name = os.path.basename(sub)
            nums = {int(EVT.match(f).group(1)) for f in files if EVT.match(f)}
            if not nums:
                continue
            if name.lower() == "hidden":
                hidden |= nums
            else:
                deeper[name] = deeper.get(name, 0) + len(nums)
    return marks, moved, hidden, deeper


def build(folder, name):
    """Everything this folder has to say, or a reason it has nothing."""
    rows, src, solid_rows, solid_src = tables(folder)
    out = {"name": name, "folder": folder, "why": None, "deeper": {},
           "hidden": set(), "solid_only": False, "other_run": 0, "moved": [],
           "rows": [], "marks": {}, "src": src, "root": None, "warn": None}
    if solid_rows:
        # The solid-only run. Every row is an IED somebody confirmed; the
        # long list in the same folder is a different run and stays put.
        out.update(rows=solid_rows, src=solid_src, solid_only=True,
                   marks={i: "solid" for i in range(1, len(solid_rows) + 1)},
                   other_run=len(rows or []))
        return out
    if not rows:
        out["why"] = "no event table"
        return out
    root = sort_root(folder)
    marks, moved, hidden, deeper = verdicts(root)
    out.update(rows=rows, src=src, marks=marks, moved=moved, hidden=hidden,
               deeper=deeper,
               root=os.path.relpath(root, folder) if root else None)
    if marks and max(marks) > len(rows):
        out["why"] = ("Evt%d is past the end of a %d-row table"
                      % (max(marks), len(rows)))
    elif not marks:
        out["why"] = "nothing has been sorted"
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--logs", default=os.path.join(APP, "GUI_logs"))
    ap.add_argument("--fs", type=float, default=30000.0,
                    help="sample rate to assume when the registry has none")
    ap.add_argument("--by", default="import_ied")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                    # noqa: BLE001
        pass
    if not os.path.isdir(args.root):
        print("No such folder: " + args.root)
        return 2

    st = store.Store(args.logs, auto_stage=False)
    bank = eventbank.EventBank(args.logs, st)
    known = st.all_sessions()
    existing = bank.summaries()

    print("Reading  %s" % args.root)
    print("Banking  %s" % os.path.join(args.logs, "event_bank"))
    print("Mode     %s%s" % ("WRITE" if args.write else "dry run",
                             "  (replacing)" if args.replace else ""))
    print()

    rows = []
    for name in sorted(os.listdir(args.root)):
        folder = os.path.join(args.root, name)
        if not os.path.isdir(folder):
            continue
        got = parse_folder(name)
        if not got:
            continue
        project, mouse, session, mon, _day = got
        f = build(folder, name)
        f.update(project=project, mouse=mouse, session=session, month=mon,
                 fs=args.fs)

        # PROJECT FIRST. Mouse and session are not an identity here --
        # the numbering restarts per project, so PTEN m13 s2 and KCNT1
        # m13 s2 are two recordings sharing one loose key.
        pool = [k for k in known
                if str(k.get("project") or k.get("group") or "").upper()
                == project]
        rec, _how = ids.match(
            {"mouse": mouse, "session": session, "key": None, "start": None,
             "loose_key": ids.make_loose_key(mouse, session)}, pool)
        f["rec"] = rec

        if not f["why"]:
            if not rec:
                f["why"] = ("no %s recording registered for m%d s%d"
                            % (project, mouse, session))
            else:
                # The month the folder names against the recording's own
                # date. A loose match that disagrees about WHEN is the
                # wrong recording, and this is the only date the tree has.
                start = str(rec.get("start") or "")
                m = re.match(r"\d{4}-(\d{2})-\d{2}", start)
                if not m:
                    f["why"] = "the recording has no start date to check"
                elif int(m.group(1)) != mon:
                    f["why"] = ("the folder says month %d and %s starts %s"
                                % (mon, rec.get("label"), start[:10]))
        if not f["why"]:
            # The last event against the recording's length, which is
            # what would catch a wrong sample rate: at 1 kHz these
            # indices would put the last event thirty times past the end.
            # So the bar is thirty-fold, not exact. A few seconds over is
            # a differently trimmed copy of the file, not an arithmetic
            # error, and refusing a set over 0.14% would be refusing the
            # wrong thing -- m28 s7 runs 3 s past a 2190 s recording.
            f["fs"] = float(rec.get("fs") or args.fs)
            dur = rec.get("duration_s")
            last = max(b for _a, b in f["rows"]) / f["fs"]
            f["last_s"] = last
            if dur and last > float(dur) * 1.5:
                f["why"] = ("the last event is at %.0f s and the recording "
                            "is %.0f s -- the sample rate is wrong"
                            % (last, float(dur)))
            elif dur and last > float(dur):
                f["warn"] = ("the last event runs %.1f s past the end of a "
                             "%.0f s recording" % (last - float(dur),
                                                   float(dur)))
        rows.append(f)

    hid = os.path.join(args.root, "HIDDEN")
    aside = ([d for d in sorted(os.listdir(hid))
              if os.path.isdir(os.path.join(hid, d))]
             if os.path.isdir(hid) else [])

    # ---- report ---------------------------------------------------------
    print("%-42s %6s %6s %6s  %s"
          % ("folder", "events", "sorted", "solid", "recording"))
    for f in rows:
        n_sol = sum(1 for v in f["marks"].values() if v == "solid")
        print("%-42s %6d %6d %6d  %s"
              % (f["name"][:42], len(f["rows"]), len(f["marks"]), n_sol,
                 f["rec"].get("label") if (f["rec"] and not f["why"])
                 else ("-- " + (f["why"] or "?"))))
        if f["solid_only"]:
            print("      solid-only run of point markers%s"
                  % ("; the %d-row detector list beside it is a different "
                     "run" % f["other_run"] if f["other_run"]
                     else " and no detector list beside it"))
        if f["root"] and f["root"] != ".":
            print("      sorted in %s" % f["root"])
        if f["warn"]:
            print("      note: %s" % f["warn"])
        if f["moved"]:
            print("      in two categories, newer copy taken: %s"
                  % ", ".join("Evt%03d %s over %s" % (n, b, a)
                              for n, a, b in f["moved"][:6]))
        if f["hidden"]:
            print("      %d withdrawn into a Hidden folder, left unlabelled"
                  % len(f["hidden"]))
        if f["deeper"]:
            print("      below a category: %s"
                  % ", ".join("%s %d" % (k, v)
                              for k, v in sorted(f["deeper"].items())))

    good = [f for f in rows if f["rec"] and not f["why"]]
    print()
    print("%d of %d folders resolve: %d events, %d sorted, %d solid"
          % (len(good), len(rows), sum(len(f["rows"]) for f in good),
             sum(len(f["marks"]) for f in good),
             sum(sum(1 for v in f["marks"].values() if v == "solid")
                 for f in good)))
    if aside:
        print("Set aside in HIDDEN/ and not imported: %s" % ", ".join(aside))
    if not args.write:
        print()
        print("Nothing written. Re-run with --write to bank it.")
        return 0

    # ---- write ----------------------------------------------------------
    wrote = 0
    for f in good:
        rec, fs = f["rec"], f["fs"]
        mine = [e for e in existing
                if (e.get("source") or {}).get("pipeline") == PIPELINE
                and e.get("gid") == rec.get("gid")]
        if mine and not args.replace:
            print("skip (already imported): %s" % f["name"])
            continue
        for e in mine:
            bank.delete(e["id"])

        tally, events = {}, []
        for i, (on, off) in enumerate(f["rows"], start=1):   # 1-BASED
            # The MIDPOINT is the stamp -- what the review images are
            # aligned to. `end` keeps the window, so the onset is still
            # exactly `2*start - end`.
            mid = (float(on) + float(off)) / 2.0 / fs
            ev = {"start": mid}
            if float(off) / fs > mid:
                ev["end"] = float(off) / fs
            lid = f["marks"].get(i)
            if lid:
                ev["label_id"] = lid
                ev["label"] = LABEL_NAME[lid]
                tally[lid] = tally.get(lid, 0) + 1
            events.append(ev)

        counts = ", ".join("%d %s" % (v, LABEL_NAME[k])
                           for k, v in sorted(tally.items())) or "nothing"
        if f["solid_only"]:
            note = (
                "Confirmed IEDs, imported from %s. All %d are Solid: this "
                "folder's spreadsheet is a separate, later, solid-only run "
                "of point markers, and its Solid folder holds exactly one "
                "stub per row numbered 1 to %d against it. The %d-row "
                "ets.mat beside it is a DIFFERENT detection run -- every "
                "row there is a 750 to 50,000 sample window and the times "
                "do not line up -- so that run's Garbage sort was not "
                "merged in." % (f["name"], len(f["rows"]), len(f["rows"]),
                                f["other_run"]))
        else:
            note = (
                "Hand-sorted IEDs, imported from %s. %d events from the "
                "detector; %d were rendered and filed by hand and the rest "
                "were never looked at, so they are unspecified rather than "
                "rejected. Filed: %s."
                % (f["name"], len(f["rows"]), len(f["marks"]), counts))
        note += (" Times are the MIDPOINT of the table's on/off pair at "
                 "%g Hz, which is what the review images are aligned to; "
                 "the onset is 2*start - end. `Evt###` is a 1-based row of "
                 "that table. Both established by measurement -- see "
                 "tools/import_ied.py." % fs)
        if f["moved"]:
            note += (" %s in two categories at once; the newer copy was "
                     "taken, which is somebody changing their mind and "
                     "leaving the old one."
                     % ", ".join("Evt%03d (%s over %s)"
                                 % (n, LABEL_NAME[b], LABEL_NAME[a])
                                 for n, a, b in f["moved"]))
        if f["warn"]:
            note += " Worth knowing: %s." % f["warn"]
        if f["hidden"]:
            note += (" %d pictures were withdrawn into a Hidden folder; a "
                     "withdrawal is not a verdict, so those are unlabelled "
                     "here." % len(f["hidden"]))
        if f["deeper"]:
            note += (" Below the categories there is a finer sort (%s) "
                     "whose folders overlap rather than partition, so it "
                     "was not read as verdicts; the folders remain the "
                     "record." % ", ".join(
                         "%s %d" % (k, v)
                         for k, v in sorted(f["deeper"].items())))

        bank.add({
            "project": rec.get("project") or rec.get("group"),
            "mouse": f["mouse"], "session": f["session"],
            "session_key": rec.get("key"),
            "session_loose_key": rec.get("loose_key"),
            "session_label": rec.get("label"),
            "session_path": (rec.get("paths") or [None])[-1],
            "recording_start": rec.get("start"),
            "duration_s": rec.get("duration_s"),
            "gid": rec.get("gid"),
            "type": "ied",
            "type_name": "IED",
            "name": ("IED spikes (confirmed)" if f["solid_only"]
                     else "IED spikes (hand-sorted)"),
            "note": note,
            "events": events,
            "label_names": dict(LABEL_NAME),
            "pipeline": PIPELINE,
            "source_file": f["src"],
            "detector": "ETS",
            "time_basis": "recording",
            "parameters": {"fs": fs, "index_base": 1, "stamp": "midpoint",
                           "solid_only": f["solid_only"],
                           "sorted_in": f["root"],
                           "withdrawn": len(f["hidden"]),
                           "below_categories": f["deeper"]},
            "added_by": args.by,
            "version_note": (
                "The folder sort as it stood, read off %s: %s, and %d the "
                "detector found that nobody rendered."
                % (f["name"], counts, len(f["rows"]) - len(f["marks"]))),
            # Somebody looked at these and said what they are. Not all of
            # them -- `by_label` says how far it got -- but a set with
            # real decisions in it is not a raw detector dump.
            "curated": True,
        })
        wrote += 1
        print("banked %-40s %5d events, %4d sorted"
              % (f["name"][:40], len(events), len(f["marks"])))

    print()
    print("%d entr%s written." % (wrote, "y" if wrote == 1 else "ies"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
