# -*- coding: utf-8 -*-
"""Step 1 -- the hand-sorted PTEN IEDs, out of the Event Bank.

Writes out/ground_truth.json: one record per recording with the folder it is
read from, its bad channels (by CSC number, from the recording's own record),
and every candidate the original detector produced with the label a person
gave it -- solid, sputter, flag, garbage, or None for the ones nobody looked
at.

Which version: the one holding the most events. Several of these entries
also carry a later version that kept only the Solids; that one answers "what
is an IED" but loses the Garbage, and the Garbage is half of this study.

    python step1_ground_truth.py
"""
import collections
import json
import os

import ied_common as C

from backend import app as A          # noqa: E402  (REG, STORE, BANK)

PIPELINE = "IED hand-sort (ETS)"


def main():
    regs = {r["gid"]: r for r in (A.REG.all() or []) if r.get("gid")}
    out = []
    for rec in A.BANK.all():
        if rec.get("type") != "ied" or rec.get("project") != "PTEN":
            continue
        if (rec.get("source") or {}).get("pipeline") != PIPELINE:
            continue
        # The fullest version, and among those the one with the most labels.
        # v0 is the detector's own import and holds every event with NO
        # labels; v1 holds the same events with the sort on them. Taking the
        # first version with the most events took v0 and lost every label.
        def score(v):
            bl = v.get("by_label") or {}
            labelled = sum(c for k, c in bl.items()
                           if str(k).lower() != "unspecified")
            return (v.get("n") or 0, labelled)
        best, best_n = None, -1
        vs = rec.get("versions") or []
        if vs:
            best = max(vs, key=score)
            best_n = best.get("n") or 0
        evs = rec.get("events") or []
        if best is not None and best_n >= len(evs) and best.get("snap"):
            # The snapshot is [[start, label_id], ...] -- the labels the
            # sort gave, which `events_at` does not carry through. Window
            # ends come from whichever stored list has the same start.
            ends = {round(float(e["start"]), 4): e.get("end")
                    for e in (rec.get("events") or [])}
            try:
                for e in (A.BANK.events_at(rec, A.BANK.version_key(best))[0]
                          or []):
                    ends.setdefault(round(float(e["start"]), 4), e.get("end"))
            except Exception:                            # noqa: BLE001
                pass
            evs = [{"start": s, "label_id": lab,
                    "end": ends.get(round(float(s), 4))}
                   for s, lab in best["snap"]]
        gid = rec["gid"]
        row = regs.get(gid) or {}
        folder = next((p for p in (row.get("paths") or [])
                       if os.path.isdir(p)), None)
        stored, _how = A.STORE.get_session({
            "gid": gid, "mouse": rec.get("mouse"),
            "session": rec.get("session"), "key": row.get("key"),
            "loose_key": row.get("loose_key")})
        bad = sorted(int(b) for b in ((stored or {}).get("bad_channels") or []))
        events = []
        for e in evs:
            lab = (e.get("label_id") or e.get("label") or "")
            lab = lab.lower() if lab else None
            if lab not in C.LABELS:
                lab = None
            events.append({"t": float(e["start"]),
                           "end": float(e["end"]) if e.get("end") else None,
                           "label": lab})
        events.sort(key=lambda x: x["t"])
        out.append({
            "key": "m%d_s%d" % (rec["mouse"], rec["session"]),
            "gid": gid, "mouse": rec["mouse"], "session": rec["session"],
            "label": rec.get("session_label"), "entry": rec["id"],
            "folder": folder, "bad": bad,
            "duration_s": rec.get("duration_s"),
            "events": events,
            "counts": dict(collections.Counter(
                e["label"] or "unreviewed" for e in events)),
        })
    # one per recording: the entry with the most events
    by = {}
    for r in out:
        if r["key"] not in by or len(r["events"]) > len(by[r["key"]]["events"]):
            by[r["key"]] = r
    recs = sorted(by.values(), key=lambda r: (r["mouse"], r["session"]))
    with open(os.path.join(C.OUT, "ground_truth.json"), "w",
              encoding="utf-8") as fh:
        json.dump(recs, fh, indent=1)
    tot = collections.Counter()
    for r in recs:
        tot.update(r["counts"])
        C.log("%-8s %-60s bad=%s %s" % (r["key"], r["folder"], r["bad"],
                                        r["counts"]))
    C.log("TOTAL", dict(tot), "across", len(recs), "recordings")


if __name__ == "__main__":
    main()
