# -*- coding: utf-8 -*-
"""Which recordings' copies disagree about how many channels they hold.

A recording's stored `n_channels` is one fact, written by whichever computer
scanned it last, from whichever copy that computer scanned. So a card could
say 128 channels above a folder of 64 (PTEN m2 s3, 2026-10-20: an archive
copy elsewhere held 128). The registry now keeps what each copy holds on
each computer's sighting (sessreg `copies`), and a card shows the copy it
opens. This lists where the computers' shards disagree, so they can be
looked at, and with --fill counts the channel files of every copy THIS
computer can reach for those recordings and files the counts on this
computer's sighting -- this computer's shard only.

    python tools/check_copy_facts.py           list the disagreements
    python tools/check_copy_facts.py --fill    and count the copies here

Reading needs no server; --fill imports the app so the write carries this
computer's profile, as every write must (memory: scripts must wire the
profile).
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass


def shards_by_record():
    out = {}
    for f in glob.glob(os.path.join(APP, "GUI_logs", "sessions", "*.json")):
        base = os.path.basename(f)
        key, _, machine = base[:-5].partition("@")
        try:
            with open(f, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        out.setdefault(key, []).append((machine, rec))
    return out


def ncs_count(path):
    try:
        return sum(1 for n in os.listdir(path) if n.lower().endswith(".ncs"))
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill", action="store_true")
    a = ap.parse_args()

    found = []
    for key, rows in sorted(shards_by_record().items()):
        vals = {}
        for machine, rec in rows:
            n = rec.get("n_channels")
            if n:
                vals.setdefault(int(n), []).append(machine)
        if len(vals) > 1:
            paths = sorted({p for _, r in rows for p in (r.get("paths") or [])})
            gid = next((r.get("gid") for _, r in rows if r.get("gid")), None)
            found.append((key, gid, vals, paths))

    print("%d recording(s) whose computers disagree about the channel count"
          % len(found))
    for key, gid, vals, paths in found:
        print("\n  %s  (%s)" % (key, gid))
        for n, ms in sorted(vals.items()):
            print("    %4d ch  on %s" % (n, ", ".join(sorted(ms))))
        for p in paths:
            n = ncs_count(p) if os.path.isdir(p) else None
            print("    %s  %s" % (("%4d here" % n) if n is not None
                                  else " not here", p))

    if not a.fill or not found:
        return 0

    from backend import app as A                         # noqa: E402
    filled = 0
    for key, gid, vals, paths in found:
        rec = A.REG.by_gid(gid) if gid else None
        if not rec:
            continue
        for p in paths:
            if not os.path.isdir(p):
                continue
            n = ncs_count(p)
            if n:
                A.REG.note_copy(rec, p, {"n_channels": n})
                rec = A.REG.by_gid(gid) or rec
                filled += 1
    print("\nfiled %d copy count(s) on this computer's sightings" % filled)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
