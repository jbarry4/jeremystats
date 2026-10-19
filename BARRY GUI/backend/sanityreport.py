# -*- coding: utf-8 -*-
"""Channel sanity over every banked DEWEY recording, saved: v2.

The Arc's "Probe sanity" and "Channel sanity" are worked out live, one
recording at a time, from the histology (`histo.py`) and the bank. When the
histology was rescored (v2, 2026-10-05), the lab asked for it to be run
over everything and kept, so there is a record that v2 has been applied
and of what it decided (the user, 2026-10-05).

One run, one record in `GUI_logs/runs/` (`STORE.record_run`, kind
`sanity`), which travels with the repository like every other run.

For each banked recording of a DEWEY rat:
  - each probe's verdict under the histology in force, its raw cell, and
    whether Coupling uses it (`histo.USABLE`) and whether the Monolith does
    (`monolith.histology_blocked`: only "y", plus Left POR-SUB);
  - over its banked cue pairs, for each region and window, on how many a
    wire is usable -- `coupling.channel_sanity`, exactly what the overview
    shows -- and, where none is, why (histology, bad, clipped).

It reads the bank, the registry and the histology only; no recording is
opened, so it takes seconds. Nothing in it decides anything: it is the
record. The decisions live in histo.py and monolith.py.
"""
from __future__ import annotations

import time

from . import coupling, histo, probes

SCRIPT = "Channel sanity"
KIND = "sanity"
#: The windows, in the order every count list uses.
STATE = tuple(coupling.CLIP_WINDOW_NAMES)
TRANSITION = tuple(coupling.TRANSITION_WINDOW_NAMES)


def _regions():
    return probes.regions_for("dewey32", [{"number": n} for n in range(1, 33)])


def one(host, row, monolith_blocked=None):
    """One recording's sanity, compact."""
    gid = row.get("gid")
    entry = host.entry(gid) if gid else None
    if not entry:
        return None
    sm = host.summary(gid) or {}
    bad = sorted(int(c) for c in (sm.get("bad_channels") or []))
    rat, probe = host.probe(sm)
    regions = _regions()
    tm = host.measured_transition(entry)[0]
    windows = STATE + (TRANSITION if tm else ())
    events = entry.get("events") or []
    keep = {r["region"]: [0] * len(windows) for r in regions}
    why = {r["region"]: {} for r in regions}
    for ev in events:
        san = coupling.channel_sanity(
            regions, bad=bad, clipped_by_window=coupling.excluded_for(ev),
            windows=windows, probe=probe)
        for r in san:
            for wi, w in enumerate(windows):
                v = r["windows"].get(w) or {}
                if v.get("channel") is not None:
                    keep[r["region"]][wi] += 1
                else:
                    b = v.get("blocked") or "unread"
                    why[r["region"]][b] = why[r["region"]].get(b, 0) + 1
    mono = monolith_blocked(rat) if (monolith_blocked and rat is not None) \
        else {}
    return {
        "gid": gid, "label": row.get("label") or sm.get("label"),
        "rat": rat, "phase": row.get("phase"), "phase_n": row.get("phase_n"),
        "run": row.get("run"), "n_pairs": len(events), "bad": bad,
        "windows": list(windows),
        "probes": [{"region": p["intended"], "verdict": p["verdict"],
                    "raw": p.get("raw"), "coupling": bool(p.get("usable")),
                    "monolith": p["intended"] not in mono}
                   for p in (probe or [])],
        "kept": keep,
        "why": {k: v for k, v in why.items() if v},
    }


def run(host, store, monolith_blocked=None, progress=None):
    """Every banked DEWEY recording, saved as one run record. Returns it."""
    t0 = time.time()
    rows = host.recordings(True) or []
    out, skipped = [], 0
    for i, row in enumerate(rows):
        if progress:
            progress(i, len(rows), row.get("label"))
        got = one(host, row, monolith_blocked)
        if got is None:
            skipped += 1
            continue
        out.append(got)
    n_rw = sum(len(r["kept"]) * len(r["windows"]) * r["n_pairs"] for r in out)
    n_kept = sum(sum(v) for r in out for v in r["kept"].values())
    rats = sorted({r["rat"] for r in out if r["rat"] is not None})
    rec = {
        "kind": KIND, "script": SCRIPT, "status": "done",
        "label": "Channel sanity v%d over every banked DEWEY recording"
                 % histo.HISTO_VERSION,
        "histology": {"version": histo.HISTO_VERSION,
                      "date": histo.HISTO_DATE, "say": histo.version_say(),
                      "file": histo.SHEET_FILE},
        "parameters": {"histology_version": histo.HISTO_VERSION},
        "totals": {"recordings": len(out), "not_banked": skipped,
                   "rats": rats,
                   "cue_pairs": sum(r["n_pairs"] for r in out),
                   "region_windows": n_rw, "kept": n_kept,
                   "seconds": round(time.time() - t0, 1)},
        "by_rat": {str(rat): {p["region"]: {"raw": p["raw"],
                                            "verdict": p["verdict"],
                                            "coupling": p["coupling"],
                                            "monolith": p["monolith"]}
                              for p in next(r for r in out
                                            if r["rat"] == rat)["probes"]}
                   for rat in rats},
        "recordings": out,
    }
    return store.record_run(rec)


def latest(store):
    """The newest saved channel sanity run, briefly, or None."""
    for rec in store.all_runs():
        if rec.get("kind") == KIND and rec.get("script") == SCRIPT:
            return {"id": rec.get("id"),
                    "at": (rec.get("provenance") or {}).get("at"),
                    "by": (rec.get("provenance") or {}).get("user"),
                    "version": (rec.get("histology") or {}).get("version"),
                    "totals": rec.get("totals")}
    return None


def badge(store):
    """What every probe-sanity surface says about the histology in force
    and whether channel sanity has been run under it."""
    last = latest(store)
    ran = bool(last and last.get("version") == histo.HISTO_VERSION)
    return {"version": histo.HISTO_VERSION, "date": histo.HISTO_DATE,
            "say": histo.version_say(), "run": last if ran else None,
            "older_run": last if (last and not ran) else None}
