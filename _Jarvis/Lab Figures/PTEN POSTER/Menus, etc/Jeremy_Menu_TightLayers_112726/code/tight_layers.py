"""Layer check (2026-11-25): tight MML / OML contacts per recording, from each DS type's own sink.

Rules (the user's answers, 2026-11-25):
  anchors     per blade, MML is centered on the DS2 sink and OML on the DS1 sink (the battery's winner split; its
              names are positional: DS1 is the type whose sink sits farther from the cell layer, checked and swapped by
              the battery), each sink found on that type's own mean CSD at the DS peak (+-3 ms), on the molecular-layer
              side of the blade's cell-layer source, as the centroid of the sink lobe above half its depth
  fallback    a mouse whose types do not separate (question 2's rule: separation index >= 0.45 and each type >= 5% and
              >= 5 events), or a blade where DS1's sink is not farther out than DS2's, uses the all-DS sink as the MML
              and puts the OML the median DS1-to-DS2 distance (from the separating blades) farther out
  width       +-2 contacts (+-40 um at 20 um per contact); where the two anchors are under 4 contacts apart, every
              contact goes to the nearer anchor only (split at the midpoint), so no contact is in both layers
  contacts    good contacts only, never the probe's first or last (no CSD there), and only on the molecular-layer side
              of that blade's cell-layer source
The old rule is kept beside it for the figures: v = 0 at the cell-layer source, 1 at the all-DS sink, MML v 0.7-1.3,
OML v 1.3-2.0. Writes tight_layers.json.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import dsdata  # noqa: E402

LABS = ["m2", "m21", "m22", "m26", "m59", "m60", "m61", "m8", "m33", "m1", "m7", "m13", "m28", "m3", "m5", "m34"]
UM = 20.0
HALF = 2.0
OLD = {"MML": (0.7, 1.3), "OML": (1.3, 2.0)}


def type_sink(r, prof, blade, good):
    """(row, depth) of a mean profile's sink on one blade's molecular-layer side; row is the lobe centroid."""
    far = r.far_rows(blade)
    far = far[good[far]] if far.size else far
    if far.size < 2:
        return np.nan, np.nan
    i0 = int(far[np.argmin(prof[far])])
    if prof[i0] >= 0:
        return np.nan, np.nan
    return dsdata._centroid(-prof, i0, 0.5), float(-prof[i0])


def main():
    recs = {r.lab: r for r in dsdata.load("v6") if r.lab in LABS}
    info = {}
    for lab in LABS:
        r = recs[lab]
        k = r.landmarks
        n = r.csd_peak.shape[1]
        good = np.array([i not in r.bad_rows for i in range(n)])
        good[[0, n - 1]] = False
        t = np.asarray(r.labels["winner"]["types"]) if (r.winner and "winner" in r.labels) else np.zeros(r.n, int)
        n1, n2 = int((t == 1).sum()), int((t == 2).sum())
        si = r.winner_si
        separable = bool(si is not None and min(n1, n2) >= max(5, 0.05 * r.n) and si >= 0.45)
        prof = {c: dsdata.fill_bad(np.nanmean(r.csd_peak[t == c], axis=0), r.bad_rows) for c in (1, 2) if (t == c).sum() >= 3}
        d = {"lab": lab, "n": int(r.n), "n1": n1, "n2": n2, "si": si, "separable": separable,
             "landmarks": {kk: float(k[kk]) for kk in ("U", "L", "GU", "GL")}, "blades": {}}
        for blade in ("upper", "lower"):
            src = k["GU"] if blade == "upper" else k["GL"]
            out = -1.0 if blade == "upper" else 1.0          # the direction away from the cell layer, in rows
            b = {"source_row": float(src), "all_sink_row": float(k["U"] if blade == "upper" else k["L"])}
            for c in (1, 2):
                if c in prof:
                    row, depth = type_sink(r, prof[c], blade, good)
                    b["ds%d_sink_row" % c], b["ds%d_sink_depth" % c] = row, depth
            ok = separable and np.isfinite(b.get("ds1_sink_row", np.nan)) and np.isfinite(b.get("ds2_sink_row", np.nan))
            if ok:
                d1 = (b["ds1_sink_row"] - src) * out
                d2 = (b["ds2_sink_row"] - src) * out
                ok = d1 > d2
            b["method"] = "own types" if ok else "median gap"
            b["out"] = out
            d["blades"][blade] = b
        info[lab] = d
    # the median DS1-to-DS2 distance (contacts) per blade, from the blades that use their own types
    gap = {}
    for blade in ("upper", "lower"):
        g = [abs(info[l]["blades"][blade]["ds1_sink_row"] - info[l]["blades"][blade]["ds2_sink_row"]) for l in LABS
             if info[l]["blades"][blade]["method"] == "own types"]
        gap[blade] = float(np.median(g))
    for lab in LABS:
        d = info[lab]
        n = len(recs[lab].contacts)
        good = np.array([i not in recs[lab].bad_rows for i in range(n)])
        good[[0, n - 1]] = False
        rows = np.arange(n)
        d["rows"], d["rows_old"] = {}, {}
        for blade in ("upper", "lower"):
            b = d["blades"][blade]
            if b["method"] == "own types":
                mml, oml = b["ds2_sink_row"], b["ds1_sink_row"]
            else:
                mml = b["all_sink_row"]
                oml = mml + b["out"] * gap[blade]
            b["mml_row"], b["oml_row"] = float(mml), float(oml)
            b["anchor_gap_um"] = float(abs(oml - mml) * UM)
            b["mml_um_from_source"] = float((mml - b["source_row"]) * b["out"] * UM)
            b["oml_um_from_source"] = float((oml - b["source_row"]) * b["out"] * UM)
            side = (rows - b["source_row"]) * b["out"] > 0.5
            dm, do = np.abs(rows - mml), np.abs(rows - oml)
            in_m = good & side & (dm <= HALF) & (dm < do)
            in_o = good & side & (do <= HALF) & (do < dm)
            d["rows"][blade] = {"MML": rows[in_m].tolist(), "OML": rows[in_o].tolist()}
            # the old rule, for the figures
            r = recs[lab]
            v = r.v(rows, blade)
            d["rows_old"][blade] = {nm: rows[good & (v >= lo) & (v < hi)].tolist() for nm, (lo, hi) in OLD.items()}
    out = {"made": "2026-11-25", "um_per_contact": UM, "half_width_contacts": HALF, "median_gap_contacts": gap,
           "rule": __doc__, "mice": info}
    with open(os.path.join(HERE, "tight_layers.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=float)
    print("median DS1-DS2 gap (contacts):", {b: round(g, 2) for b, g in gap.items()})
    for lab in LABS:
        d = info[lab]
        s = []
        for blade in ("upper", "lower"):
            b = d["blades"][blade]
            s.append("%s %-10s MML %3.0f um (%s) OML %3.0f um (%s) gap %3.0f" % (
                blade[:2], b["method"], b["mml_um_from_source"], ",".join(map(str, d["rows"][blade]["MML"])),
                b["oml_um_from_source"], ",".join(map(str, d["rows"][blade]["OML"])), b["anchor_gap_um"]))
        print("%-4s sep %-5s | %s | %s" % (lab, d["separable"], s[0], s[1]), flush=True)


if __name__ == "__main__":
    main()
