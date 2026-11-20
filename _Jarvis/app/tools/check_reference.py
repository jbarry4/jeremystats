"""check_reference.py -- is a rat's coherence its brain or its reference?

Coherence from one wire minus the other within
each region (a bipolar derivation), beside the referenced single wire tab 11
uses, on the same trials, the same pair window and the same settings
(Dickson's notch, hanning 1024, 512 overlap, FFT 2048, pooled over trials).

Anything the reference electrode adds is identical on both wires of a
region and cancels in their difference (2026-11-02: J3's 0.7 gamma fell to
0.00-0.02 this way). Reads the recordings only; writes
GUI_logs/.cache/monolith/joepub/bipolar.json, which the methods Joe is sent
quote (backend/joepub.py).

    python tools/check_reference.py 3 4 6 11      (rats; both days each)
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from backend import monolith as MO

MO.configure(os.path.join(APP, "GUI_logs"))
from backend import evenmore as E, joe, coupling, spark, nlx

OUT = MO._path("joepub", "bipolar.json")
KINDS = ("ref", "bip")


def one_day(rat, day):
    t0 = time.time()
    man = MO.manifest()
    d = next(x for x in man["days"] if int(x["rat"]) == rat and x["day"] == day)
    folder = next(f["local"] for f in d["folders"] if f.get("role") == "SPC")
    bad = [int(c) for c in d.get("bad") or []]
    blocked = d.get("blocked") or {}
    cm = {k: sorted(int(c) for c in v) for k, v in coupling.dewey_map().items() if k in E.SIDE_NAMES}
    units = list(d.get("units") or [])
    by_pair, _pc = spark.clipping_for(folder, [{"pair_id": u["id"], "opener_t": float(u["pair"]["opener_t"]),
                                                 "closer_t": float(u["pair"]["closer_t"]),
                                                 "offset_t": float(u["pair"]["offset_t"])} for u in units], skip=bad)
    state = {}
    for uid, per in (by_pair or {}).items():
        for c, rec in (per or {}).items():
            for w in rec.get("windows") or []:
                state.setdefault(uid, {}).setdefault(w, set()).add(int(c))
    files = dict(nlx.list_csc_files(folder))
    origin = nlx.recording_start_us(folder)
    WP = E.wire_pairs()
    P, C, NF = len(E.PAIRS), len(E.COMBOS), E.NF
    acc = {k: {"sab": np.zeros((P, C, NF), complex), "saa": np.zeros((P, C, NF)), "sbb": np.zeros((P, C, NF)),
               "n": np.zeros((P, C), int), "psd": np.zeros((len(E.SIDE_NAMES), NF)), "pn": np.zeros(len(E.SIDE_NAMES), int)}
           for k in KINDS}
    used = {k: {} for k in KINDS}
    for u in units:
        o, f = float(u["pair"]["opener_t"]), float(u["pair"]["offset_t"])
        drop = set(joe.trial_drop(u, state.get(u["id"]), (), bad)["pair"])
        sigs = {k: [] for k in KINDS}
        for nm in E.SIDE_NAMES:
            ok = [c for c in cm[nm] if c not in drop and nm not in blocked and c in files]
            tr = []
            for c in ok[:2]:
                got, meta = coupling._channel_windows(files[c], [("pair", o, f)], origin)
                x = got.get("pair")
                if x is None:
                    continue
                y, _fs = coupling.decimate_to(x, meta["fs"], E.FS)
                tr.append((c, y))
            ref = tr[0][1] if tr else None
            bip = (tr[0][1][:min(len(tr[0][1]), len(tr[1][1]))] - tr[1][1][:min(len(tr[0][1]), len(tr[1][1]))]) if len(tr) >= 2 else None
            sigs["ref"].append(ref)
            sigs["bip"].append(bip)
            if tr:
                used["ref"].setdefault(nm, set()).add(tr[0][0])
            if len(tr) >= 2:
                used["bip"].setdefault(nm, set()).add("%d-%d" % (tr[0][0], tr[1][0]))
        for k in KINDS:
            F = dict(zip(E.SIDE_NAMES, E._spectra_of(sigs[k])))
            A = acc[k]
            for si, nm in enumerate(E.SIDE_NAMES):
                if F[nm] is not None:
                    A["psd"][si] += (np.abs(F[nm]) ** 2).sum(0)
                    A["pn"][si] += F[nm].shape[0]
            for p, c, a, b in WP:
                if F[a] is None or F[b] is None:
                    continue
                n = min(F[a].shape[0], F[b].shape[0])
                Fa, Fb = F[a][:n], F[b][:n]
                A["sab"][p, c] += (Fa * np.conj(Fb)).sum(0)
                A["saa"][p, c] += (np.abs(Fa) ** 2).sum(0)
                A["sbb"][p, c] += (np.abs(Fb) ** 2).sum(0)
                A["n"][p, c] += n
    out = {"rat": rat, "day": day, "trials": len(units), "seconds": round(time.time() - t0, 1)}
    for k in KINDS:
        A = acc[k]
        with np.errstate(invalid="ignore", divide="ignore"):
            coh = np.abs(A["sab"]) ** 2 / (A["saa"] * A["sbb"])
        coh[A["n"] == 0] = np.nan
        spec = E._nanmean(coh, axis=1)                                   # (P, NF)
        ph = np.degrees(np.angle(A["sab"]))
        gm = joe.band_mask(E.FREQS, 30, 90)
        out[k] = {
            "gamma": [None if not np.isfinite(v) else float(v) for v in E.band_value(spec, "gamma")],
            "theta": [None if not np.isfinite(v) else float(v) for v in E.band_value(spec, "theta")],
            "by_freq": {"%d-%d" % (a, b): float(np.nanmean(spec[:, (E.FREQS >= a) & (E.FREQS < b)])) if np.isfinite(spec).any() else None
                        for a, b in ((1, 4), (4, 8), (8, 12), (12, 20), (20, 30), (30, 45), (45, 58), (62, 75), (75, 90))},
            "phase_gamma": float(np.nanmedian(np.abs(np.where(A["n"][..., None] > 0, ph, np.nan)[..., gm]))) if (A["n"] > 0).any() else None,
            "gamma_db": [None if A["pn"][i] == 0 else float(10 * np.log10(np.mean((A["psd"][i] / A["pn"][i])[gm]) * 2.0 / (E.FS * np.sum(coupling.matlab_hanning(E.SEG) ** 2))))
                         for i in range(len(E.SIDE_NAMES))],
            "wires": {nm: sorted(str(x) for x in v) for nm, v in used[k].items()},
        }
    return out


def main():
    rats = [int(a) for a in sys.argv[1:]] or [3, 4, 6, 11]
    jobs = [(r, d) for r in rats for d in E.DAYS]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    have = json.load(open(OUT)) if os.path.isfile(OUT) else {}
    with ProcessPoolExecutor(max_workers=min(4, len(jobs))) as ex:
        futs = {ex.submit(one_day, r, d): (r, d) for r, d in jobs}
        for fu in as_completed(futs):
            r, d = futs[fu]
            try:
                res = fu.result()
            except Exception as exc:                                     # noqa: BLE001
                print("r%d %s failed: %r" % (r, d, exc), flush=True)
                continue
            have["%d %s" % (r, d)] = res
            json.dump(have, open(OUT, "w"), indent=1)
            print("done r%d %s in %.0f s" % (r, d, res["seconds"]), flush=True)
    print("\nGamma coherence per pair, referenced single wire  ->  wire minus wire (bipolar)")
    print("%-14s " % "" + " ".join("%13s" % s for s in E.PAIR_SAY))
    for key in sorted(have, key=lambda k: (int(k.split()[0]), k.split()[1])):
        x = have[key]
        for band in ("gamma", "theta"):
            print("J%-2d %-8s %-5s" % (x["rat"], x["day"], band[:5]) + " ".join(
                "%13s" % ("--" if x["ref"][band][p] is None else "%.2f -> %s" % (x["ref"][band][p], "--" if x["bip"][band][p] is None else "%.2f" % x["bip"][band][p]))
                for p in range(len(E.PAIRS))))
    print("\nBy frequency, mean of pairs (ref | bipolar); |gamma phase| median; gamma power dB per side (ref | bip)")
    for key in sorted(have, key=lambda k: (int(k.split()[0]), k.split()[1])):
        x = have[key]
        print("J%-2d %-8s ref %s | phase %.1f" % (x["rat"], x["day"], " ".join("%s:%.2f" % (k, v) for k, v in x["ref"]["by_freq"].items() if v is not None), x["ref"]["phase_gamma"] or -1))
        print("%-12s bip %s | phase %.1f" % ("", " ".join("%s:%.2f" % (k, v) for k, v in x["bip"]["by_freq"].items() if v is not None), x["bip"]["phase_gamma"] or -1))
        print("%-12s dB  %s" % ("", "; ".join("%s %s|%s" % (nm, "--" if a is None else "%.1f" % a, "--" if b is None else "%.1f" % b)
                                             for nm, a, b in zip(E.SIDE_NAMES, x["ref"]["gamma_db"], x["bip"]["gamma_db"]) if a is not None)))
        print("%-12s wires %s" % ("", x["bip"]["wires"]))


if __name__ == "__main__":
    main()
