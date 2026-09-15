# -*- coding: utf-8 -*-
"""Do Incisor's timestamps agree with Toothy's?

The question is timestamps, not classification. Toothy splits its dentate
spikes into DS1 and DS2; this compares the union, because a spike is a spike
whichever cluster it lands in.

WHAT IS COMPARED, AND ON WHICH CLOCK
------------------------------------
Toothy stamps concatenated time. Any set banked from it is therefore on that
clock unless somebody has applied the correction, in which case the bank's
`time_basis` says so. This reads that stamp rather than assuming either way,
and converts whichever side needs converting, so the comparison is between
two numbers that mean the same thing. Comparing a corrected set with an
uncorrected one -- or either with Incisor -- without looking first is how you
get a disagreement that is entirely your own doing.

MATCHING
--------
Nearest neighbour within a tolerance, greedy from the closest pair outward,
so one Incisor event cannot claim two of Toothy's. The tolerance defaults to
25 ms: half a dentate spike's width, wide enough that the two detectors
landing on opposite shoulders of the same event still counts as agreement,
narrow enough that neighbouring spikes 100 ms apart cannot be confused.

Run: python tools/check_vs_toothy.py [gid-or-path]
"""
import json
import os
import sys
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import continuity, incisor                   # noqa: E402

BASE = "http://127.0.0.1:8791"
MATCH_S = 0.025
TOOTHY_PIPELINES = ("ETS dentate-spike export", "Toothy", "toothy")


def get(url):
    with urllib.request.urlopen(BASE + url, timeout=600) as fh:
        return json.loads(fh.read())


def match(a, b, tol=MATCH_S):
    """Greedy nearest-neighbour pairing. Returns (pairs, only_a, only_b)."""
    a = np.asarray(sorted(a), dtype=np.float64)
    b = np.asarray(sorted(b), dtype=np.float64)
    if not a.size or not b.size:
        return [], list(a), list(b)
    # Every candidate pair inside the tolerance, closest first.
    cand = []
    j = 0
    for i, t in enumerate(a):
        while j < b.size and b[j] < t - tol:
            j += 1
        k = j
        while k < b.size and b[k] <= t + tol:
            cand.append((abs(b[k] - t), i, k))
            k += 1
    cand.sort()
    used_a, used_b, pairs = set(), set(), []
    for d, i, k in cand:
        if i in used_a or k in used_b:
            continue
        used_a.add(i)
        used_b.add(k)
        pairs.append((float(a[i]), float(b[k])))
    only_a = [float(a[i]) for i in range(a.size) if i not in used_a]
    only_b = [float(b[k]) for k in range(b.size) if k not in used_b]
    return pairs, only_a, only_b


def banked_ds(gid):
    """Every banked dentate-spike set for a recording, with its clock."""
    out = []
    for e in (get("/api/bank") or {}).get("entries", []):
        if e.get("gid") != gid:
            continue
        pipe = ((e.get("source") or {}).get("pipeline") or "")
        if not any(p.lower() in pipe.lower() for p in TOOTHY_PIPELINES):
            continue
        out.append(e)
    return out


def compare(path, gid, label):
    rep = continuity.check(path)
    if not rep.get("ok"):
        print("  could not segment: %s" % rep.get("error"))
        return None

    sets = banked_ds(gid)
    if not sets:
        print("  nothing banked from Toothy for this recording")
        return None

    from backend import app as appmod
    sess, err = appmod._session_for(path, False, True)
    if err:
        print("  could not open: %s" % err)
        return None

    # Every channel, because the hilus channel is what Toothy detected on and
    # this has to find the same one before the times can be compared.
    chans = [c["index"] for c in sess["channels"]]
    spec = {"path": path, "channels": chans, "invert": True,
            "even_only": False}
    out = incisor.run(sess, spec, rep)
    hil = out["picked"]["hilus"]
    print("  Incisor picked %s (margin %.0f%%), %d events"
          % (hil["label"], 100 * hil["margin"], out["n"]))
    print("  recording: %d segment(s), %.1f s lost, residual sd %.0f us"
          % (rep["n_segments"], rep["seconds_lost"],
             rep.get("map_residual_sd_us") or 0))

    mine = [e["start"] for e in out["events"]]
    # The same events, timed the OLD way: segment-linear at the header's
    # nominal rate, which is what `concat_to_true` does and therefore what
    # every already-corrected set in the bank carries. Computed from the
    # sample index each event already holds, so it is the same detection
    # with a different clock -- which is the only way to show that a ramp in
    # the offset is the clock and not the detector.
    fs_nom = float(rep.get("fs") or 30000.0)
    seg_at, seg_start = {}, 0
    for sg in rep.get("segments") or []:
        seg_at[int(sg["index"])] = (seg_start, float(sg["true_t0_s"]))
        seg_start += int(sg["n_samples"])
    mine_old = []
    for e in out["events"]:
        got = seg_at.get(int(e["segment"]))
        if got is None:
            continue
        base_i, base_t = got
        mine_old.append(base_t + (int(e["idx"]) - base_i) / fs_nom)
    best = None
    for entry in sets:
        full = get("/api/bank/" + entry["id"])
        rec = full.get("entry") or full
        evs = rec.get("events") or []
        basis = (rec.get("time_basis") or {}).get("kind")
        times = [float(e["start"]) for e in evs if e.get("start") is not None]

        # Onto the recording's own clock, whichever clock it is on now.
        note = "already on the true clock"
        if basis != "neuralynx_true":
            conv = [continuity.concat_to_true(rep, t)[0] for t in times]
            times = [t for t in conv if t is not None]
            note = "converted from concatenated time"

        pairs, only_mine, only_theirs = match(mine, times)
        d = np.array([p[0] - p[1] for p in pairs]) if pairs else np.array([])

        # Separate the clock from the detector.
        #
        # An offset that grows linearly with time is a RATE difference: the
        # two sides disagree about how long a second is, not about where a
        # dentate spike is. Incisor fits the rate off the file's own record
        # timestamps; a set corrected by the older `concat_to_true` carries
        # the header's nominal rate instead. Regressing the offset on time
        # tells the two apart, and what is left after removing the ramp is
        # the honest measure of whether the detectors agree.
        when = np.array([p[0] for p in pairs]) if pairs else np.array([])
        ppm = resid = None
        if d.size > 32 and np.ptp(when) > 60:
            slope, icept = np.polyfit(when, d, 1)
            ppm = slope * 1e6
            resid = d - (slope * when + icept)
        row = {
            "entry": rec.get("name") or entry["id"],
            "pipeline": (rec.get("source") or {}).get("pipeline"),
            "basis": basis, "note": note,
            "theirs": len(times), "mine": len(mine),
            "matched": len(pairs),
            "only_mine": len(only_mine), "only_theirs": len(only_theirs),
            "median_ms": float(np.median(d) * 1e3) if d.size else 0.0,
            "p95_ms": float(np.percentile(np.abs(d), 95) * 1e3)
            if d.size else 0.0,
            "max_ms": float(np.max(np.abs(d)) * 1e3) if d.size else 0.0,
        }
        # WHICH CHANNEL did Toothy use?
        #
        # A channel mismatch and a timing error look identical from the
        # summary -- both are "the times do not agree" -- and they need
        # opposite fixes. Every channel's events are already in hand, so ask
        # which one Toothy's set actually matches. If that is not the one
        # picked, the disagreement is about anatomy, not about clocks.
        best_ch, best_n = None, -1
        for idx, evs in (out.get("by_channel") or {}).items():
            if not evs:
                continue
            p_ch, _, _ = match([e["start"] for e in evs], times)
            if len(p_ch) > best_n:
                best_n, best_ch = len(p_ch), int(idx)
        row["best_channel"] = best_ch
        row["best_matched"] = best_n

        print()
        print("  against %s  (%s)" % (row["entry"], row["pipeline"]))
        if best_ch is not None and best_ch != out["chosen"]:
            lab = next((c["label"] for c in out["channels"]
                        if c["index"] == best_ch), str(best_ch))
            mine_lab = next((c["label"] for c in out["channels"]
                             if c["index"] == out["chosen"]), "?")
            print("    CHANNEL MISMATCH: Toothy's set matches %s (%d of %d), "
                  "Incisor picked %s" % (lab, best_n, len(times), mine_lab))
        print("    its clock: %s -- %s" % (basis or "unstamped", note))
        print("    %d Toothy, %d Incisor, %d matched within %.0f ms"
              % (row["theirs"], row["mine"], row["matched"], MATCH_S * 1e3))
        print("    %d only Incisor, %d only Toothy  (recall %.1f%%, "
              "precision %.1f%%)"
              % (row["only_mine"], row["only_theirs"],
                 100.0 * row["matched"] / max(1, row["theirs"]),
                 100.0 * row["matched"] / max(1, row["mine"])))
        if d.size:
            print("    offset: median %+.2f ms, p95 %.2f ms, worst %.2f ms"
                  % (row["median_ms"], row["p95_ms"], row["max_ms"]))
        # And the same comparison on the old clock.
        if mine_old:
            p2, _, _ = match(mine_old, times)
            if len(p2) > 32:
                d2 = np.array([a - b for a, b in p2])
                w2 = np.array([a for a, _ in p2])
                if np.ptp(w2) > 60:
                    sl2, _ic2 = np.polyfit(w2, d2, 1)
                    print("    timing the SAME events the old way "
                          "(segment-linear, nominal rate): %+.2f ppm"
                          % (sl2 * 1e6))
        if best_ch is not None and best_ch != out["chosen"] and best_n > 0:
            alt = [e["start"] for e in (out["by_channel"] or {}).get(
                str(best_ch), [])]
            pa, oa, ob = match(alt, times)
            if pa:
                da = np.array([a - b for a, b in pa])
                print("    on THAT channel: %d of %d matched, offset "
                      "median %+.2f ms, p95 %.2f ms"
                      % (len(pa), len(times), float(np.median(da) * 1e3),
                         float(np.percentile(np.abs(da), 95) * 1e3)))
        if resid is not None:
            row["ppm"] = float(ppm)
            row["resid_sd_ms"] = float(np.std(resid) * 1e3)
            row["resid_p95_ms"] = float(np.percentile(np.abs(resid), 95) * 1e3)
            print("    of which a clock difference of %+.2f ppm "
                  "(%.2f ms across the recording)"
                  % (ppm, abs(ppm) * np.ptp(when) / 1e6 * 1e3))
            print("    with that removed: sd %.2f ms, p95 %.2f ms, "
                  "worst %.2f ms"
                  % (row["resid_sd_ms"], row["resid_p95_ms"],
                     float(np.max(np.abs(resid)) * 1e3)))
        if best is None or row["matched"] > best["matched"]:
            best = row
    return best


def main():
    reg = get("/api/registry")
    rows = []
    for p in reg.get("tree", []):
        for m in p.get("mice", []):
            for s in m.get("sessions", []):
                if (s.get("here") or []):
                    rows.append(s)
    want = sys.argv[1] if len(sys.argv) > 1 else None
    if want:
        rows = [r for r in rows
                if r.get("gid") == want or want in (r.get("here") or [])
                or want.lower() in (r.get("label") or "").lower()]

    seen = []
    for r in rows:
        gid = r.get("gid")
        path = (r.get("here") or [None])[0]
        if not gid or not path:
            continue
        if not banked_ds(gid):
            continue
        print()
        print("=" * 72)
        print(r.get("label") or gid)
        got = compare(path, gid, r.get("label"))
        if got:
            seen.append((r.get("label") or gid, got))
        if len(seen) >= 10 and not want:
            break

    print()
    print("=" * 72)
    print("%-24s %7s %7s %7s %8s %9s %9s"
          % ("session", "Toothy", "Incisor", "matched", "clock", "resid sd",
             "resid p95"))
    for label, row in seen:
        print("%-24s %7d %7d %7d %7s %8s %9s"
              % (label[:24], row["theirs"], row["mine"], row["matched"],
                 ("%+.1fppm" % row["ppm"]) if row.get("ppm") else "-",
                 ("%.2fms" % row["resid_sd_ms"])
                 if row.get("resid_sd_ms") is not None else "-",
                 ("%.2fms" % row["resid_p95_ms"])
                 if row.get("resid_p95_ms") is not None else "-"))


main()
