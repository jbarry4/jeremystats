"""KCNT1 preliminary menu, the numbers: one value per mouse for every measure the eight questions use, and the tests.

Reads (beside this file): jeremy_battery.pkl and _tight.pkl (j1_battery.py), jeremy_freq.pkl and _tight.pkl
(j2_freq.py), rc_events.pkl (m0_data.py), tight_layers.json; battery/data/meta.json. Writes kresults.pkl and
tables/*.csv.

Statistics, as in the PTEN menus: exploratory, one number per mouse, the smallest P of the applicable tests, no
correction.
  dose      gene dose (WT 0, Het 1, Hom 2) over all six mice: Spearman (exact: every one of the 720 orderings),
            Kendall tau-b, Pearson
  WT v Hom  2 against 2: Mann-Whitney (exact; it cannot go below 0.33) and Welch t (when both pairs vary)
  female    every WT and Hom mouse is female and both Het mice are male, so the female-only dose test is WT against
            Hom on the same four mice (Spearman exact over 4)
"""
import itertools
import json
import math
import os
import pickle
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import stats as st

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
BAT = os.environ.get("KBAT", os.path.join(HERE, "..", "battery"))
META = {m["lab"]: m for m in json.load(open(os.path.join(BAT, "data", "meta.json")))}
LABS = ["m1619", "m526", "m1609", "m576", "m1603", "m306"]
GENO = {l: META[l]["group"] for l in LABS}
DOSE = {l: float(META[l]["ko"]) for l in LABS}
SEX = {l: META[l].get("sex") for l in LABS}
WT = [l for l in LABS if GENO[l] == "WT"]
HOM = [l for l in LABS if GENO[l] == "Hom"]
HET = [l for l in LABS if GENO[l] == "Het"]
FBANDS = ["notch", "5-100", "1-100", "1-300", "5-300", "5-50", "10-40"]
BSETS = ["b_none", "b_ds", "b_1_100", "b_1_300", "b_5_300", "b_5_50", "b_10_40"]   # the battery's names for the same bands
LAYKEYS = [("upper", "MML"), ("upper", "OML"), ("lower", "MML"), ("lower", "OML")]
_PERM = {}


def perms(n):
    if n not in _PERM:
        _PERM[n] = np.array(list(itertools.permutations(range(n))))
    return _PERM[n]


def spearman_exact(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    rx, ry = st.rankdata(x), st.rankdata(y)
    cx, cy = rx - rx.mean(), ry - ry.mean()
    den = math.sqrt(float((cx ** 2).sum() * (cy ** 2).sum()))
    if den == 0:
        return np.nan, np.nan
    rho = float(cx @ cy / den)
    null = (cy[perms(len(y))] @ cx) / den
    return rho, float((np.abs(null) >= abs(rho) - 1e-12).mean())


def tests(values):
    """{lab: v} -> dict of effects and generous P."""
    v = {l: float(values.get(l, np.nan)) for l in LABS}
    fin = [l for l in LABS if np.isfinite(v[l])]
    out = {"values": v, "n": len(fin)}
    if len(fin) >= 4 and np.ptp([v[l] for l in fin]) > 0 and np.ptp([DOSE[l] for l in fin]) > 0:
        x, y = [DOSE[l] for l in fin], [v[l] for l in fin]
        rho, p_s = spearman_exact(x, y)
        kt = st.kendalltau(x, y)
        try:
            p_p = float(st.pearsonr(x, y)[1])
        except Exception:  # noqa: BLE001
            p_p = np.nan
        ps = {"Spearman (exact)": p_s, "Kendall": float(kt.pvalue), "Pearson": p_p}
        k = min((k for k in ps if np.isfinite(ps[k])), key=ps.get)
        out["dose"] = {"rho": rho, "tau": float(kt.correlation), "p": ps[k], "test": k, "p_all": ps}
    a, b = [v[l] for l in WT if np.isfinite(v[l])], [v[l] for l in HOM if np.isfinite(v[l])]
    if len(a) >= 2 and len(b) >= 2 and np.ptp(a + b) > 0:
        ps = {"Mann-Whitney": float(st.mannwhitneyu(b, a, alternative="two-sided", method="exact").pvalue)}
        # Welch t only when both pairs vary: with 2 against 2 a pair of equal values (a frequency on the FFT grid,
        # say) gives a zero variance and a meaningless t. Student t is left out: on 2 against 2 it is the most liberal.
        if np.std(a) > 0 and np.std(b) > 0:
            try:
                ps["Welch t"] = float(st.ttest_ind(b, a, equal_var=False).pvalue)
            except Exception:  # noqa: BLE001
                pass
        ps = {k: p for k, p in ps.items() if np.isfinite(p)}
        k = min(ps, key=ps.get)
        out["wt_hom"] = {"ratio": float(np.mean(b) / np.mean(a)) if np.mean(a) != 0 else np.nan,
                         "diff": float(np.mean(b) - np.mean(a)), "p": ps[k], "test": k, "p_all": ps}
        fem = [l for l in WT + HOM if np.isfinite(v[l])]
        if len(fem) >= 4:
            rho, p = spearman_exact([DOSE[l] for l in fem], [v[l] for l in fem])
            out["female"] = {"rho": rho, "p": p}
    return out


def load(name):
    p = os.path.join(HERE, name)
    return pickle.load(open(p, "rb")) if os.path.exists(p) else None


B = {"old": load("jeremy_battery.pkl"), "tight": load("jeremy_battery_tight.pkl")}
FQ = {"old": load("jeremy_freq.pkl"), "tight": load("jeremy_freq_tight.pkl")}
rc = pd.read_pickle(os.path.join(HERE, "rc_events.pkl"))
FREQS = next(iter(FQ["old"]["mice"].values()))["freqs"]
R = {"labs": LABS, "geno": GENO, "dose": DOSE, "sex": SEX, "meta": META, "m": {}, "t": {}}


def put(key, values, words, unit=""):
    R["m"][key] = {"values": {l: float(values.get(l, np.nan)) for l in LABS}, "words": words, "unit": unit}
    R["t"][key] = tests(values)


def fast_metrics(db, lo=100, hi=500, glo=250):
    fr = FREQS
    m = (fr >= lo) & (fr <= hi)
    ex = np.clip(10 ** (np.asarray(db, float)[m] / 10.0) - 1, 0, None)
    cen = float((ex * fr[m]).sum() / ex.sum()) if ex.sum() > 0 else np.nan
    g = (fr >= glo) & (fr <= hi)
    return cen, float(np.mean(np.asarray(db, float)[g]))


def es_fit(ev, ref, sel=None):
    x = np.log2(ev["sink"] / ref)
    yv = ev["hf"]
    ok = np.isfinite(x) & np.isfinite(yv) & (ev["sink"] > 0)
    if sel is not None:
        ok &= sel
    if ok.sum() < 8:
        return np.nan, np.nan
    sl, ic, _a, _b = st.theilslopes(yv[ok], x[ok])
    return float(ic), float(sl)


# ---------------------------------------------------------------- Root Canal classes per mouse (both workflows)
KIND = {"ds": "DS", "halo_ds": "DS", "both": "BT", "halo_amb": "BT", "pspike": "IED", "halo_pspike": "IED", "neither": "outside"}
cnt = {}
for wf in ("halo", "strict"):
    h = rc[rc.wf == wf]
    for l in LABS:
        k = h[h.lab == l]["cls"].map(KIND).value_counts().to_dict()
        cnt[(wf, l)] = {c: int(k.get(c, 0)) for c in ("DS", "BT", "IED", "outside")}
R["counts"] = cnt
dur = {l: META[l]["dur_min"] for l in LABS}
put("bt_rate", {l: cnt[("halo", l)]["BT"] / dur[l] for l in LABS}, "Borderline transients (BTs) per minute, Halo workflow", "/min")
put("ied_rate", {l: cnt[("halo", l)]["IED"] / dur[l] for l in LABS}, "IED-class events per minute, Halo workflow", "/min")
put("bt_share", {l: cnt[("halo", l)]["BT"] / max(1, sum(cnt[("halo", l)].values())) for l in LABS},
    "BTs as a share of every Root Canal event, Halo workflow", "")
put("ds_rate", {l: cnt[("halo", l)]["DS"] / dur[l] for l in LABS}, "Dentate spikes (Halo set) per minute", "/min")
put("strict_outside_share", {l: cnt[("strict", l)]["outside"] / max(1, sum(cnt[("strict", l)].values())) for l in LABS},
    "Share of events outside both borders, Strict workflow", "")
hds = rc[(rc.wf == "halo") & rc.cls.isin(["ds", "halo_ds"])]
put("rc_hf_ds", {l: float(np.nanmedian(hds[hds.lab == l].hf)) for l in LABS}, "DS fast power (Root Canal, 240-420 Hz), median", "dB")
put("rc_amp_ds", {l: float(np.nanmedian(hds[hds.lab == l].amp)) for l in LABS}, "DS amplitude (Root Canal), median", "uV")
put("rc_hw_ds", {l: float(np.nanmedian(hds[hds.lab == l].hw)) for l in LABS}, "DS half-width (Root Canal), median", "ms")

# ---------------------------------------------------------------- Q1 / Q2 / Q3 / Q5 from the battery
for rule in ("old", "tight"):
    b = B[rule]
    if b is None:
        continue
    for es in b["per"]:
        P, ref = b["per"][es], b["ref"][es]
        tag = "%s|%s" % (rule, es)
        for key, (blade, lay) in zip(("uMML", "uOML", "lMML", "lOML"), LAYKEYS):
            put("q3|%s|%s" % (tag, key), {l: P[l]["all"]["layers"][(blade, lay)] / ref for l in P if l in LABS},
                "%s blade %s sink (WT average deepest sink = 1)" % (blade.capitalize(), lay), "")
        if rule == "old":
            put("q1|sink|%s" % es, {l: P[l]["all"]["sink"] / ref for l in P if l in LABS}, "DS sink at its peak (WT average = 1)")
            put("q1|slope|%s" % es, {l: P[l]["all"]["slope"] / ref for l in P if l in LABS}, "10-90% rise slope of the sink (WT = 1)")
            put("q1|rise|%s" % es, {l: P[l]["all"]["rise"] for l in P if l in LABS}, "10-90% rise time of the sink", "ms")
b = B["old"]
ref = b["ref"]["v6"]
EV = b["events_v6"]
put("q1|out", {l: es_fit(EV[l], ref)[0] for l in LABS if l in EV}, "Fast power for a standard sink (the WT-average sink)", "dB")
put("q1|gain", {l: es_fit(EV[l], ref)[1] for l in LABS if l in EV}, "Fast power gained per doubling of the sink", "dB")
for k in (1, 2):
    put("q1|out_ds%d" % k, {l: es_fit(EV[l], ref, EV[l]["types"] == k)[0] for l in LABS if l in EV},
        "DS%d fast power for a standard sink" % k, "dB")
    put("q1|sink_ds%d" % k, {l: b["per"]["v6"][l]["ds%d" % k]["sink"] / ref for l in LABS if "ds%d" % k in b["per"]["v6"][l]},
        "DS%d sink (WT average DS = 1)" % k)
P6 = b["per"]["v6"]
put("q2|si", {l: P6[l]["si"] for l in LABS}, "Separation index of DS1 and DS2 (the winner classifier)")
put("q2|ds2_share", {l: P6[l]["n2"] / max(1, P6[l]["n1"] + P6[l]["n2"]) for l in LABS}, "DS2 share of typed DS")
put("q2|ds1_rate", {l: P6[l]["n1"] / P6[l]["dur_min"] for l in LABS}, "DS1 per minute", "/min")
put("q2|ds2_rate", {l: P6[l]["n2"] / P6[l]["dur_min"] for l in LABS}, "DS2 per minute", "/min")
R["types"] = {l: {"n1": P6[l]["n1"], "n2": P6[l]["n2"], "n": P6[l]["n"], "si": P6[l]["si"], "winner": P6[l]["winner"],
                  "both": bool(min(P6[l]["n1"], P6[l]["n2"]) >= max(5, 0.05 * P6[l]["n"]))} for l in LABS}
for k in (1, 2):
    put("q2|rise_ds%d" % k, {l: P6[l]["ds%d" % k]["rise"] for l in LABS if "ds%d" % k in P6[l]}, "DS%d sink rise time (own sink)" % k, "ms")

# ---------------------------------------------------------------- Q4 / Q5 / Q7 / Q8 from the 2 kHz reads
for rule in ("old", "tight"):
    fq = FQ[rule]
    if fq is None:
        continue
    for band in FBANDS:
        for blade, lay in LAYKEYS:
            kk = "%s%s" % (blade[0], lay)
            for cls in ("DS", "TZ"):
                vals_dom, vals_cen, vals_gain, vals_sink = {}, {}, {}, {}
                for l in LABS:
                    br = fq["mice"].get(l, {}).get("bands", {}).get(band, {})
                    w = br.get("whole", {}).get((cls, blade, lay, "csd"))
                    if w is not None:
                        vals_dom[l] = w[0]
                    s = br.get("fast_spec", {}).get((cls, blade, lay, "csd"))
                    if s is not None:
                        hi = 500 if band in ("notch",) else 300
                        lo, glo = (100, 250) if hi == 500 else (100, 200)
                        c, g = fast_metrics(s, lo, hi, glo)
                        vals_cen[l], vals_gain[l] = c, g
                    sk = br.get("sink", {}).get((cls, blade, lay))
                    if sk is not None:
                        vals_sink[l] = sk
                tag = "%s|%s|%s|%s" % (rule, band, cls, kk)
                put("q4|dom|" + tag, vals_dom, "%s dominant frequency, %s blade %s" % (cls, blade, lay), "Hz")
                put("q4|cen|" + tag, vals_cen, "%s fast-power center, %s blade %s" % (cls, blade, lay), "Hz")
                put("q4|gain|" + tag, vals_gain, "%s fast-power gain, %s blade %s" % (cls, blade, lay), "dB")
                put("q4|sink|" + tag, vals_sink, "%s sink, %s blade %s (2 kHz read)" % (cls, blade, lay), "")
    R["n_classes"] = {l: fq["mice"][l]["n"] for l in fq["mice"]} if rule == "old" else R.get("n_classes")

# Q7: BTs against the same mouse's DS (paired) and against the WT DS, mice with 5 BTs or more read
fq = FQ["tight"] or FQ["old"]
q7 = {}
for band in FBANDS:
    for blade, lay in LAYKEYS:
        kk = "%s%s" % (blade[0], lay)
        rows = []
        for l in LABS:
            br = fq["mice"].get(l, {}).get("bands", {}).get(band, {})
            n_bt = fq["mice"].get(l, {}).get("n", {}).get("TZ", 0)
            row = {"lab": l, "n_bt": n_bt}
            for cls in ("DS", "TZ"):
                sk = br.get("sink", {}).get((cls, blade, lay))
                s = br.get("fast_spec", {}).get((cls, blade, lay, "csd"))
                row["sink_" + cls] = sk if sk is not None else np.nan
                if s is not None:
                    hi = 500 if band == "notch" else 300
                    row["gain_" + cls] = fast_metrics(s, 100, hi, 250 if hi == 500 else 200)[1]
                else:
                    row["gain_" + cls] = np.nan
            rows.append(row)
        q7[(band, kk)] = rows
R["q7"] = q7
R["ref"] = {"v6": ref}
R["freqs"] = FREQS
with open(os.path.join(HERE, "kresults.pkl"), "wb") as fh:
    pickle.dump(R, fh, protocol=4)

# tables
os.makedirs(os.path.join(HERE, "tables"), exist_ok=True)
rows = []
for key, m in R["m"].items():
    t = R["t"][key]
    r = {"measure": key, "words": m["words"], "unit": m["unit"]}
    r.update({l: m["values"][l] for l in LABS})
    d, w, f = t.get("dose", {}), t.get("wt_hom", {}), t.get("female", {})
    r.update(dose_rho=d.get("rho"), dose_p=d.get("p"), dose_test=d.get("test"), wt_hom_ratio=w.get("ratio"),
             wt_hom_p=w.get("p"), wt_hom_test=w.get("test"), female_rho=f.get("rho"), female_p=f.get("p"))
    rows.append(r)
pd.DataFrame(rows).to_csv(os.path.join(HERE, "tables", "per_mouse_values_and_tests.csv"), index=False)
cr = []
for (wf, l), c in cnt.items():
    cr.append(dict(workflow=wf, mouse=l, genotype=GENO[l], sex=SEX[l], minutes=round(dur[l], 1), **c))
pd.DataFrame(cr).to_csv(os.path.join(HERE, "tables", "root_canal_classes_per_mouse.csv"), index=False)
print("measures", len(rows))
for key in ("q1|sink|v6", "q1|out", "q2|si", "q2|ds2_share", "bt_rate", "ied_rate", "rc_hf_ds"):
    t = R["t"][key]
    print("%-14s" % key, " ".join("%s=%.3g" % (l, t["values"][l]) for l in LABS), "| dose rho %+.2f P %.3g" % (
        t.get("dose", {}).get("rho", np.nan), t.get("dose", {}).get("p", np.nan)),
        "| WT v Hom P %.3g" % t.get("wt_hom", {}).get("p", np.nan))
