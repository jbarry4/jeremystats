#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_continuity.py -- which recordings under a root have gaps?

Walks a tree, finds every folder holding .ncs files, and segments each one the
way neo and spikeinterface do. A continuous recording is decided by two
records, so the clean majority costs almost nothing and the slow part is only
the ones that are actually broken.

    python tools/scan_continuity.py D:\\PTEN\\PTEN
    python tools/scan_continuity.py D:\\PTEN\\PTEN --json scan.json --all-channels

Exit code is 0 when everything is continuous, 1 when anything is not, 2 on a
usage error -- so it can gate something later if that is ever wanted.

Why this exists as well as the health check in the GUI: the health check
answers "is this session all right" one session at a time, and the question
this tree raises is "how much of the archive is affected", which wants a
single pass and a table. On 25 PTEN recordings the answer was 8.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import continuity, nlx      # noqa: E402


def recording_folders(root, limit=4000):
    """Every folder under `root` that directly contains .ncs files."""
    out = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "__pycache__", ".cache")]
        if any(f.lower().endswith(".ncs") for f in files):
            out.append(folder)
            dirs[:] = []            # a recording does not nest in a recording
        if len(out) >= limit:
            break
    return sorted(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Find recordings with acquisition gaps under a root.")
    ap.add_argument("root", help="folder to walk")
    ap.add_argument("--all-channels", action="store_true",
                    help="parse every .ncs in each folder, not a spot-check")
    ap.add_argument("--channels", type=int, default=continuity.SPOT_CHANNELS,
                    help="how many channels to cross-check (default %d)"
                         % continuity.SPOT_CHANNELS)
    ap.add_argument("--strict", action="store_true",
                    help="neo's strict tolerance instead of spikeinterface's")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        print("not a directory: %s" % args.root)
        return 2

    folders = recording_folders(args.root)
    if not folders:
        print("no .ncs anywhere under %s" % args.root)
        return 2

    print("%d recording folder(s) under %s" % (len(folders), args.root))
    print("rule: %s" % (nlx.GAP_RULE_STRICT if args.strict
                        else nlx.GAP_RULE_LOOSE))
    print()

    rows, affected, failed = [], [], []
    t_start = time.time()
    for i, folder in enumerate(folders, 1):
        sys.stdout.write("\r  %d/%d  %s"
                         % (i, len(folders), os.path.basename(folder)[:46]))
        sys.stdout.flush()
        try:
            rep = continuity.check(folder, channels=args.channels,
                                   strict=args.strict,
                                   all_channels=args.all_channels,
                                   use_cache=not args.no_cache)
        except Exception as exc:                         # noqa: BLE001
            failed.append((folder, str(exc)))
            continue
        if rep is None:
            continue
        if not rep.get("ok"):
            failed.append((folder, rep.get("error", "unknown")))
            continue
        rows.append(rep)
        if rep["n_segments"] > 1:
            affected.append(rep)
    sys.stdout.write("\r" + " " * 78 + "\r")

    rel = lambda f: os.path.relpath(f, args.root)

    if affected:
        affected.sort(key=lambda r: -r["seconds_lost"])
        print("AFFECTED -- %d of %d" % (len(affected), len(rows)))
        print("  %-52s %4s %4s %10s %11s"
              % ("recording", "seg", "gap", "lost (s)", "worst (ms)"))
        for r in affected:
            print("  %-52s %4d %4d %10.4f %11.1f"
                  % (rel(r["folder"])[:52], r["n_segments"], len(r["gaps"]),
                     r["seconds_lost"], r["max_time_error_ms"]))
    else:
        print("Nothing affected: every recording is a single segment.")

    clean = [r for r in rows if r["n_segments"] == 1]
    print()
    print("CLEAN -- %d of %d" % (len(clean), len(rows)))

    # Time lost below the segment threshold: short records whose next
    # timestamp is later than their own samples account for, but not late
    # enough to make a break. Real, and no segment boundary records it.
    #
    # NOT `n_records * 512 - samples`, which counts unused buffer slots and
    # reports a fifth of a second of "loss" on recordings that lost nothing.
    quiet = [r for r in clean if (r.get("sub_threshold_lost_s") or 0) > 0]
    if quiet:
        print("  %d of them lost time at a short record without making a "
              "break:" % len(quiet))
        for r in sorted(quiet,
                        key=lambda x: -x["sub_threshold_lost_s"])[:8]:
            print("    %-52s %7.2f ms across %d record(s)"
                  % (rel(r["folder"])[:52],
                     r["sub_threshold_lost_s"] * 1e3, r["n_short_inside"]))

    disagree = [r for r in rows if r.get("mismatches")]
    if disagree:
        print()
        print("CHANNELS DISAGREE -- %d folder(s); a mixed or partly copied "
              "folder looks like this, not like a gap" % len(disagree))
        for r in disagree:
            print("  %s" % rel(r["folder"]))
            for m in r["mismatches"][:4]:
                print("    %-12s %s" % (m["channel"], m["why"]))

    if failed:
        print()
        print("UNREADABLE -- %d" % len(failed))
        for folder, why in failed[:10]:
            print("  %-52s %s" % (rel(folder)[:52], why))

    print()
    print("%d folder(s) in %.1f s" % (len(rows), time.time() - t_start))

    if args.json_out:
        payload = {
            "root": args.root,
            "rule": nlx.GAP_RULE_STRICT if args.strict else nlx.GAP_RULE_LOOSE,
            "all_channels": bool(args.all_channels),
            "n_folders": len(rows),
            "n_affected": len(affected),
            "recordings": [{
                "folder": r["folder"],
                "n_segments": r["n_segments"],
                "n_gaps": len(r["gaps"]),
                "seconds_lost": r["seconds_lost"],
                "max_time_error_ms": r["max_time_error_ms"],
                "true_duration_s": r["true_duration_s"],
                "concat_duration_s": r["concat_duration_s"],
                "record_duration_s": r["record_duration_s"],
                "sub_threshold_lost_s": r["sub_threshold_lost_s"],
                "n_short_inside": r["n_short_inside"],
                "unused_record_slots": r["unused_record_slots"],
                "gap_map_sha": r["gap_map_sha"],
                "mismatches": r["mismatches"],
                "gaps": r["gaps"],
                "segments": r["segments"],
            } for r in rows],
            "unreadable": [{"folder": f, "error": w} for f, w in failed],
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print("wrote %s" % args.json_out)

    return 1 if affected else 0


if __name__ == "__main__":
    sys.exit(main())
