"""Tab 14, Joe Prompt: every request of Joe's run sheet, from the stored
spectra (tab 11's and joeprompt.measure()'s) and tabs 11 and 12's results.

Each request returns one record: what was run, on which rats, its tables
(the estimates with 95% CIs, p, q and the robustness lines Joe's
conventions ask for), its per-rat values (the CSV) and its figures;
joepromptfigs draws the figures and writes the PDF. The conventions, from
the run sheet: a GEE with the rat as the cluster (exchangeable); Gamma with
a log link for coherence, Granger and MI, normal for dB power, FOOOF and
phase measures; robust (Mancl-DeRouen) errors up to 2 df, model-based
above; Benjamini-Hochberg with its family named; every p < .05 on a tested
term gets leave-one-rat-out and a mixed model with a random intercept.
"""
import json
import math
import os

import numpy as np

from . import evenmore as E
from . import finalstage as FS
from . import joe
from . import joeprompt as JP

ALPHA = 0.05
DAYS = E.DAYS
BANDS = [b[0] for b in E.BANDS]
BAND_LIM = {b: (lo, hi) for b, lo, hi in E.BANDS}
PAIR_SAY = E.PAIR_SAY
REGIONS = FS.REGIONS
REGION_SAY = FS.REGION_SAY
CONTRASTS = E.CONTRASTS


# --------------------------------------------------------------------------
# Words for numbers
# --------------------------------------------------------------------------
def fp(p):
    if p is None or not np.isfinite(p):
        return ""
    return "p < .001" if p < 0.001 else "p = %s" % ("%.3f" % p).lstrip("0")


def fq(q):
    if q is None or not np.isfinite(q):
        return ""
    return "q < .001" if q < 0.001 else "q = %s" % ("%.3f" % q).lstrip("0")


def num(v, k=2):
    if v is None or not np.isfinite(v):
        return ""
    return ("%.*f" % (k, v)).replace("-", "−")


def est(x, unit=""):
    """'×0.26 [0.12, 0.55]' for a ratio, '−4.59 [−6.10, −3.08] dB' for a
    difference."""
    if not x or x.get("est") is None:
        return (x or {}).get("error", "")
    k = 3 if x["kind"] == "diff" and abs(x["est"]) < 0.1 else 2
    if x["kind"] == "ratio":
        return "×%s [%s, %s]" % (num(x["est"]), num(x["lo"]), num(x["hi"]))
    return "%s [%s, %s]%s" % (num(x["est"], k), num(x["lo"], k), num(x["hi"], k), (" " + unit) if unit else "")


def chi(x):
    if not x or x.get("chi2") is None or not np.isfinite(x["chi2"]):
        return ""
    return "χ²(%d) = %s" % (x["df"], num(x["chi2"]))


def sig(x, key="p"):
    return bool(x) and x.get(key) is not None and x[key] < ALPHA


def word(x):
    """significant / nominal / n.s., in the run sheet's words."""
    if not x or x.get("p") is None:
        return ""
    if x.get("q") is not None:
        return "significant" if x["q"] < ALPHA else "nominal" if x["p"] < ALPHA else "n.s."
    return "p < .05" if x["p"] < ALPHA else "n.s."


def rob_say(R):
    if not R:
        return ""
    lm = R.get("lmm") or {}
    lm_s = ("LMM F(%d, %d) = %s, %s" % (lm["df1"], lm["df2"], num(lm["F"]), fp(lm["p"]))) if lm.get("F") is not None else "LMM did not fit"
    loo = "leave-one-out holds (largest %s, without J%d)" % (fp(R["worst_p"]), R["worst_rat"]) if R["loo_holds"] else \
        "leave-one-out fails without J%d (%s)" % (R["worst_rat"], fp(R["worst_p"]))
    return "%s: %s; %s" % ("Robust" if R["robust"] else "Not robust", loo, lm_s)


# --------------------------------------------------------------------------
# The models
# --------------------------------------------------------------------------
def _frame(rows):
    return E._frame(rows)


def coef(res, has, fam, exclude=()):
    """One coefficient on the robust errors, back-transformed: a ratio for
    a log link, a difference for the identity."""
    names = list(res.params.index)
    i = next((k for k, n in enumerate(names) if all(h in n for h in has) and not any(x in n for x in exclude)), None)
    if i is None:
        raise JP.PromptError("no coefficient with %s" % has)
    b = float(res.params.iloc[i])
    se = float(np.sqrt(np.asarray(res.cov_robust_bc)[i, i]))
    x = (b / se) ** 2 if se > 0 else float("nan")
    tr = math.exp if fam == "gamma" else (lambda v: v)
    return {"est": tr(b), "lo": tr(b - 1.959964 * se), "hi": tr(b + 1.959964 * se), "chi2": x, "df": 1,
            "p": E._chi2_sf(x, 1) if np.isfinite(x) else None, "errors": E.ROBUST, "kind": "ratio" if fam == "gamma" else "diff"}


SESSION = "y ~ C(day, Treatment('Precon1'))"


def session(df, fam, extra=""):
    """Late against Early (averaged over the other factor's levels when it
    is Sum-coded)."""
    return coef(E.gee(df, SESSION + extra, fam), ["Precon4"], fam, exclude=[":"])


def term(df, formula, fam, name):
    t = next((t for t in E.terms(E.gee(df, formula, fam)) if t["term"] == name), None)
    if t is None:
        raise JP.PromptError("no term %s" % name)
    return dict(t)


def safe(fn):
    try:
        return fn()
    except Exception as exc:                                 # noqa: BLE001
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def robust(df, fitp, lmm_formula, has, log, exclude=()):
    """Leave each rat out (`fitp(df) -> {p}`) and the mixed model beside it."""
    loo = []
    for r in sorted(int(r) for r in df["rat"].unique()):
        g = safe(lambda: fitp(df[df["rat"] != r]))
        loo.append({"rat": r, "p": g.get("p")})
    worst = max(loo, key=lambda x: 2.0 if x["p"] is None else x["p"])
    lm = E.lmm_test(df, lmm_formula, has, log=log, exclude=exclude)
    holds = all(x["p"] is not None and x["p"] < ALPHA for x in loo)
    return {"loo": loo, "worst_rat": worst["rat"], "worst_p": worst["p"], "loo_holds": holds, "lmm": lm,
            "robust": holds and lm.get("p") is not None and lm["p"] < ALPHA}


def bh_put(items, key="p", out="q"):
    qs = E.bh([x.get(key) if x and "error" not in x else None for x in items])
    for x, q in zip(items, qs):
        if x is not None and q is not None:
            x[out] = q


def robust_session(df, fam, extra=""):
    return robust(df, lambda d: session(d, fam, extra), SESSION + extra, ["Precon4"], fam == "gamma", exclude=[":"])


# --------------------------------------------------------------------------
# What every request reads
# --------------------------------------------------------------------------
class Ctx:
    """The stored data, J6-J11 only, read once."""

    def __init__(self, progress=None):
        say = progress or (lambda s: None)
        say("reading tab 11's spectra")
        self.em = {k: v for k, v in E.load_days().items() if k[0] not in JP.DROP}
        self.em_all = E.load_days()
        say("reading the extra pass")
        self.jp = JP.load_days()
        missing = sorted(set(self.em) - set(self.jp))
        if missing:
            raise JP.PromptError("The extra pass is missing %s: measure first." % ", ".join("r%d %s" % k for k in missing), 409)
        self.rats = sorted({r for r, _d in self.em})
        self.T = E.tables(self.em)
        self.PT = FS.power_tables(self.em)
        self.EM = E.result(JP.RS) or {}
        self.F = json.load(open(FS.set_root(JP.RS, "final.json"), encoding="utf-8")) if os.path.isfile(FS.set_root(JP.RS, "final.json")) else {}
        self._ft = None
        self.a2_cache = {}
        self.say = say

    @property
    def FT(self):
        if self._ft is None:
            self.say("fitting FOOOF (the same fits as tab 12)")
            self._ft = FS.fooof_tables(self.PT)
        return self._ft

    def both(self, vals):
        """The rats with a finite value on both days."""
        return [r for r in self.rats if all(vals.get((r, d)) is not None and np.isfinite(vals[(r, d)]) for d in DAYS)]


def rows_of(vals, rats, **extra):
    return [dict({"rat": r, "day": d, "y": float(vals[(r, d)])}, **extra) for r in rats for d in DAYS]


def coh_vals(X, w, band, p):
    return {k: float(v[p]) for k, v in X.T["band"][w][band].items()}


def wire_mean(x, ok):
    """Mean over the valid wire pairs (axis 0), NaN when none."""
    return float(np.mean(x[ok])) if ok.any() else float("nan")


def _bins(lo, hi):
    """The FFT bins in [lo, hi], the notch's never."""
    return joe.band_mask(E.FREQS, lo, hi)


def coh_band_custom(arrs_sab, saa, sbb, n, mask):
    """(P,) region-pair band coherence for a frequency mask, from pooled
    sums (P, C, NF): each wire pair's spectrum, the mean over valid wire
    pairs, then the band's mean (tab 11's order)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        c = np.abs(arrs_sab) ** 2 / (saa * sbb)
    c[n == 0] = np.nan
    spec = E._nanmean(c, axis=1)
    return E._nanmean(spec[..., mask], axis=-1)


def power_custom(psd_sum, pn, mask):
    """(regions,) band dB from summed side spectra (S, NF) and pieces (S,):
    each side's mean linear power over the mask in dB, the mean of the
    region's sides (tab 12's order)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        P = psd_sum / pn[:, None].astype(float) * FS._scale()
    P[pn == 0] = np.nan
    side = FS._db(E._nanmean(P[:, mask], axis=1))
    return np.array([E._nanmean(side[FS.region_sides(r)], axis=0) for r in REGIONS])


def rec(rid, **kw):
    """A request's record, with its run sheet name, priority and part."""
    _i, name, decides, pri = next(x for x in JP.REQUESTS if x[0] == rid)
    r = {"id": rid, "name": name, "decides": decides, "priority": pri, "part": JP.PART_OF[rid], "status": "Done",
         "rats": JP.RATS_SAY, "n": "", "ran": "", "summary": [], "reading": [], "tables": [], "figures": [], "csv": [],
         "robust": [], "source": "", "notes": []}
    r.update(kw)
    return r


def table(title, head, rows, bold=None, note=""):
    return {"title": title, "head": head, "rows": [[("" if c is None else str(c)) for c in r] for r in rows],
            "bold": bold or [False] * len(rows), "note": note}


def n_say(ns):
    ns = sorted(set(ns))
    return ("n = %d rats" % ns[0]) if len(ns) == 1 else ("n = %d–%d rats" % (ns[0], ns[-1]))


# --------------------------------------------------------------------------
# A1. Coherence decomposition
# --------------------------------------------------------------------------
def DAY_SAY(d):
    return JP.DAY_SAY[d]


def _a2_of(X, band, p):
    """Tab 11's own Late vs Early for a pair (its ratio, p and q across the
    ten, J6-J11), with the 95% CI tab 11 does not keep: the same GEE on the
    same rows, fitted again (its ratio must agree)."""
    key = (band, p)
    if key in X.a2_cache:
        return X.a2_cache[key]
    out = {"error": "not tested"}
    for B in X.EM.get("bands") or []:
        if B["band"] == band:
            x = next((z for z in B["phase1"]["pairs"] if z and z["pair"] == p), None)
            a2 = (x or {}).get("a2") or {}
            if a2.get("ratio") is not None:
                vals = coh_vals(X, "pair", band, p)
                g = safe(lambda: session(_frame(rows_of(vals, x["rats"])), "gamma"))
                if "est" in g and abs(g["est"] / a2["ratio"] - 1) > 1e-6:
                    raise JP.PromptError("%s %s: the ratio refitted (%.6f) is not tab 11's (%.6f)" % (PAIR_SAY[p], band, g["est"], a2["ratio"]))
                out = dict(g, q=a2.get("q"), p=a2.get("p"), chi2=a2.get("chi2"))
    X.a2_cache[key] = out
    return out


def a1(X):
    """log|Sxy|^2, log Sxx, log Syy from the cue pair's pooled spectra (each
    per piece), averaged over the band's bins and the valid wire pairs;
    Session on each (normal GEE), BH across the ten pairs within a term."""
    wi = E.WINS.index("pair")
    TERMS = (("lxy", "|Sxy|²"), ("lxx", "Sxx"), ("lyy", "Syy"), ("lcoh", "Coherence (log)"))
    R = rec("A1", ran="Session on log|Sxy|², log Sxx and log Syy of the cue pair's pooled spectra (natural log, per piece, averaged over the "
                      "band's bins and the valid wire pairs), normal GEE, robust errors; BH across the 10 pairs within each term and band.",
            source="Tab 11's pooled spectra (the same sums its coherence is made of).")
    out, ns = {}, []
    for band in BANDS:
        m = _bins(*BAND_LIM[band])
        res = []
        for p in range(len(E.PAIRS)):
            vals = {t: {} for t, _s in TERMS}
            for (r, d), (a, _m) in X.em.items():
                n = a["nseg"][wi, p].astype(float)
                ok = n > 0
                if not ok.any():
                    continue
                with np.errstate(invalid="ignore", divide="ignore"):
                    lxy = np.log(np.abs(a["sab"][wi, p][ok][:, m] / n[ok, None]) ** 2)
                    lxx = np.log(a["saa"][wi, p][ok][:, m] / n[ok, None])
                    lyy = np.log(a["sbb"][wi, p][ok][:, m] / n[ok, None])
                vals["lxy"][(r, d)] = float(lxy.mean())
                vals["lxx"][(r, d)] = float(lxx.mean())
                vals["lyy"][(r, d)] = float(lyy.mean())
                vals["lcoh"][(r, d)] = float((lxy - lxx - lyy).mean())
            rats = X.both(vals["lxy"])
            x = {"pair": p, "band": band, "rats": rats, "coh": _a2_of(X, band, p)}
            if len(rats) < E.MIN_RATS:
                x["error"] = "fewer than %d rats" % E.MIN_RATS
                res.append(x)
                continue
            ns.append(len(rats))
            for t, _s in TERMS:
                df = _frame(rows_of(vals[t], rats))
                g = safe(lambda: session(df, "normal"))
                if "est" in g:
                    g = dict(g, kind="ratio", diff=g["est"], est=math.exp(g["est"]), lo=math.exp(g["lo"]), hi=math.exp(g["hi"]))
                x[t] = g
                for rr in rats:
                    for d in DAYS:
                        R["csv"].append({"request": "A1", "band": band, "pair": PAIR_SAY[p], "term": t, "rat": "J%d" % rr,
                                         "session": DAY_SAY(d), "value": vals[t][(rr, d)]})
            res.append(x)
        for t, _s in TERMS:
            bh_put([x.get(t) for x in res])
        out[band] = res
        rows, bold = [], []
        for x in res:
            if "error" in x:
                continue
            rows.append([PAIR_SAY[x["pair"]], len(x["rats"])] +
                        ["%s, %s%s" % (est(x[t]), fp(x[t].get("p")), (", " + fq(x[t]["q"])) if x[t].get("q") is not None else "") for t, _s in TERMS] +
                        [est(x["coh"])])
            bold.append(any(sig(x[t], "q") for t, _s in TERMS[:3]))
        R["tables"].append(table("%s: Late/Early ratio [95%% CI] of each term" % band.capitalize(),
                                 ["Pair", "n", "|Sxy|²", "Sxx", "Syy", "Coherence from the three", "Coherence (tab 11, Gamma GEE)"], rows, bold,
                                 note="Ratios are exp(Late − Early) of the natural logs. The fourth column is exactly |Sxy|² ÷ (Sxx × Syy) "
                                      "of the first three (the log terms add); the last is tab 11's coherence ratio (mean coherence, "
                                      "Gamma GEE), which averages coherence rather than its log. Bold: a term with q < .05."))
    R["n"] = n_say(ns)
    for band in BANDS:
        for x in out[band]:
            c = x.get("coh") or {}
            if "error" in x or not sig(c, "q"):
                continue
            carry = [s for t, s in (("lxy", "|Sxy|²"), ("lxx", "Sxx"), ("lyy", "Syy")) if sig(x[t], "q")]
            nom = [s for t, s in (("lxy", "|Sxy|²"), ("lxx", "Sxx"), ("lyy", "Syy")) if sig(x[t]) and not sig(x[t], "q")]
            R["summary"].append("%s %s (coherence %s, %s): |Sxy|² %s, Sxx %s, Syy %s; %s." % (
                PAIR_SAY[x["pair"]], band, est(c), fq(c.get("q")), est(x["lxy"]), est(x["lxx"]), est(x["lyy"]),
                ("carried by %s (q < .05)" % " and ".join(carry)) if carry else
                ("no term passes after correction%s" % ("; nominally %s" % " and ".join(nom) if nom else ""))))
    if not R["summary"]:
        R["summary"].append("No pair's coherence changes after correction in J6–J11, so there is no change to decompose.")
    R["reading"] = ["A change carried by |Sxy|² is a change in shared signal (coupling). A change carried by Sxx or Syy with |Sxy|² steady is a power change."]
    R["data"] = out
    return R


# --------------------------------------------------------------------------
# A2. The volume-conduction test
# --------------------------------------------------------------------------
def _icoh(a, w, p, m):
    wi = E.WINS.index(w)
    ok = a["nseg"][wi, p] > 0
    if not ok.any():
        return float("nan")
    with np.errstate(invalid="ignore", divide="ignore"):
        ic = np.abs(np.imag(a["sab"][wi, p])) / np.sqrt(a["saa"][wi, p] * a["sbb"][wi, p])
    return float(np.mean(ic[ok][:, m]))


def _wpli_ppc(j, w, p, m):
    """Debiased wPLI (Vinck 2011) and PPC (Vinck 2010) over every piece of
    every trial, per bin and wire pair; the band's mean; the wire pairs'."""
    wi = JP.WF.index(w)
    n = j["nph"][wi, p].astype(float)
    ok = n > 1
    if not ok.any():
        return float("nan"), float("nan")
    s, a, s2 = j["sim"][wi, p], j["sabs"][wi, p], j["sim2"][wi, p]
    with np.errstate(invalid="ignore", divide="ignore"):
        wpli = (s * s - s2) / (a * a - s2)
        ppc = (np.abs(j["su"][wi, p]) ** 2 - n[:, None]) / (n[:, None] * (n[:, None] - 1))
    return float(np.nanmean(wpli[ok][:, m])), float(np.nanmean(ppc[ok][:, m]))


def _phase(a, w, p, m):
    """Each valid wire pair's phase of the band-summed pooled cross-spectrum
    (degrees, -180..180)."""
    wi = E.WINS.index(w)
    ok = a["nseg"][wi, p] > 0
    return [float(np.degrees(np.angle(a["sab"][wi, p, c][m].sum()))) for c in np.flatnonzero(ok)]


def near_zero(ph):
    return float(np.mean([(abs(v) < 10) or (abs(v) > 170) for v in ph])) if ph else float("nan")


def a2(X):
    R = rec("A2", ran="On the cue pair's pieces pooled over every trial: debiased wPLI and PPC (Vinck et al. 2011, 2010), and imaginary "
                      "coherence |Im Sxy| / √(Sxx·Syy) from the same pooled spectra as coherence; each band-averaged, then averaged over "
                      "the valid wire pairs. Session on each (normal GEE, robust errors), BH across the 10 pairs; leave-one-out and an "
                      "LMM for every p < .05. The mean phase of the pooled cross-spectrum per pair, session and band.",
            source="Imaginary coherence and phase from tab 11's pooled spectra; wPLI and PPC from this tab's pass over the recordings.")
    MEAS = (("wpli", "Debiased wPLI"), ("icoh", "Imaginary coherence"), ("ppc", "PPC"))
    out, ns = {}, []
    for band in BANDS:
        m = _bins(*BAND_LIM[band])
        res = []
        for p in range(len(E.PAIRS)):
            vals = {k: {} for k, _s in MEAS}
            phases = {d: [] for d in DAYS}
            for k, (a, _m) in X.em.items():
                vals["icoh"][k] = _icoh(a, "pair", p, m)
                phases[k[1]] += [(k[0], v) for v in _phase(a, "pair", p, m)]
                vals["wpli"][k], vals["ppc"][k] = _wpli_ppc(X.jp[k][0], "pair", p, m)
            rats = X.both(vals["wpli"])
            x = {"pair": p, "band": band, "rats": rats, "phases": phases, "coh": _a2_of(X, band, p), "vals": vals}
            if len(rats) < E.MIN_RATS:
                x["error"] = "fewer than %d rats" % E.MIN_RATS
                res.append(x)
                continue
            ns.append(len(rats))
            for k, _s in MEAS:
                df = _frame(rows_of(vals[k], rats))
                x[k] = safe(lambda: session(df, "normal"))
                x[k + "_df"] = df
                for rr in rats:
                    for d in DAYS:
                        R["csv"].append({"request": "A2", "band": band, "pair": PAIR_SAY[p], "measure": k, "rat": "J%d" % rr,
                                         "session": DAY_SAY(d), "value": vals[k][(rr, d)]})
            res.append(x)
        for k, _s in MEAS:
            bh_put([x.get(k) for x in res])
        for x in res:
            for k, s in MEAS:
                g = x.get(k)
                if g and sig(g):
                    g["robust"] = robust_session(x[k + "_df"], "normal")
                    R["robust"].append("%s %s, %s (%s): %s" % (PAIR_SAY[x["pair"]], band, s, est(g), rob_say(g["robust"])))
            for k, _s in MEAS:
                x.pop(k + "_df", None)
        out[band] = res
        rows, bold = [], []
        for x in res:
            if "error" in x:
                continue
            rows.append([PAIR_SAY[x["pair"]], len(x["rats"]), "%s, %s" % (est(x["coh"]), fq(x["coh"].get("q")))] +
                        ["%s, %s%s" % (est(x[k]), fp(x[k].get("p")), (", " + fq(x[k]["q"])) if x[k].get("q") is not None else "") for k, _s in MEAS])
            bold.append(sig(x.get("wpli"), "q") or sig(x.get("icoh"), "q"))
        R["tables"].append(table("%s: Late − Early [95%% CI]" % band.capitalize(),
                                 ["Pair", "n", "Coherence ratio (tab 11)", "Debiased wPLI", "Imaginary coherence", "PPC"], rows, bold,
                                 note="Coherence as a Late/Early ratio; the phase measures as Late − Early differences (normal GEE). "
                                      "q: BH across the 10 pairs within each measure and band. Bold: wPLI or imaginary coherence with q < .05."))
        prow = []
        for x in res:
            row = [PAIR_SAY[x["pair"]]]
            for d in DAYS:
                ph = [v for _r, v in x["phases"][d] if _r in X.rats]
                if not ph:
                    row += ["", ""]
                    continue
                z = np.mean(np.exp(1j * np.radians(ph)))
                row += ["%s°" % num(float(np.degrees(np.angle(z))), 0), "%d%% of %d" % (round(100 * near_zero(ph)), len(ph))]
            prow.append(row)
        R["tables"].append(table("%s: phase of the pooled cross-spectrum" % band.capitalize(),
                                 ["Pair", "Early: mean phase", "Early: within 10° of 0° or 180°", "Late: mean phase", "Late: within 10° of 0° or 180°"],
                                 prow, note="Each valid wire pair's band-summed pooled cross-spectrum, J6–J11; the phase is their circular "
                                            "mean. Volume conduction and a shared reference sit at 0° or 180°; a conduction delay does not."))
    R["n"] = n_say(ns)
    for band in BANDS:
        for x in out[band]:
            if "error" in x or not sig(x["coh"], "q"):
                continue
            w_ = x["wpli"]
            same = w_.get("est") is not None and ((w_["est"] < 0) == (x["coh"]["est"] < 1))
            ph = [v for _r, v in x["phases"]["Precon1"] + x["phases"]["Precon4"] if _r in X.rats]
            R["summary"].append("%s %s: coherence %s (%s); debiased wPLI %s (%s%s)%s; imaginary coherence %s (%s); %d%% of wire-pair phases within 10° of 0° or 180°." % (
                PAIR_SAY[x["pair"]], band, est(x["coh"]), fq(x["coh"].get("q")), est(w_), fp(w_.get("p")),
                (", " + fq(w_["q"])) if w_.get("q") is not None else "",
                ", the same direction" if same else ", the opposite direction" if w_.get("est") is not None else "",
                est(x["icoh"]), fp(x["icoh"].get("p")), round(100 * near_zero(ph)) if ph else 0))
    R["reading"] = [
        "A coherence change counts as more than volume conduction when debiased wPLI (or imaginary coherence) changes in the same direction "
        "and passes the robustness checks. A coherence change with no lagged change and a phase near 0° is zero-lag, so it can't be called coupling.",
        "Two limits: wPLI also discards genuine zero-lag synchrony, and it's noisier than coherence, so with six rats a null wPLI result is weak "
        "evidence. Read its CI, not only p."]
    R["data"] = out
    return R


# --------------------------------------------------------------------------
# A3. H1 checks
# --------------------------------------------------------------------------
def _incidence():
    B = np.zeros((len(E.PAIRS), len(E.STRUCTS)))
    for p, (i, j) in enumerate(E.PAIRS):
        B[p, i] = B[p, j] = 1.0
    return B


def node_test(beta, V, B):
    """The node model inside the full one: beta (each pair's Session
    effect) = B a (each region's). GLS a and its covariance, the
    residuals, and the Wald chi^2 of what the full model adds."""
    Vi = np.linalg.pinv(V)
    A = np.linalg.pinv(B.T @ Vi @ B)
    a = A @ B.T @ Vi @ beta
    res = beta - B @ a
    _u, s, vt = np.linalg.svd(B.T)
    L = vt[int(np.sum(s > 1e-9)):]
    Lb = L @ beta
    x = float(Lb @ np.linalg.solve(L @ V @ L.T, Lb))
    return a, A, res, x, L.shape[0]


def _lmm_f(fe, cov, idx, n):
    from scipy.stats import f as fdist
    b = fe[idx]
    V = cov[np.ix_(idx, idx)]
    k = len(idx)
    Fv = float(b @ np.linalg.solve(V, b)) / k
    return {"F": Fv, "df1": k, "df2": k * (n - 1), "p": float(fdist.sf(Fv, k, k * (n - 1)))}


def lmm_say(lm):
    return ("F(%d, %d) = %s, %s" % (lm["df1"], lm["df2"], num(lm["F"]), fp(lm["p"]))) if lm and lm.get("F") is not None else (lm or {}).get("error", "")


def a3(X):
    R = rec("A3", ran="Session × Pair on band coherence (cue pair): the GEE (Gamma, log link, model-based; tab 11's), an LMM on log coherence "
                      "with random intercepts for rat and for pair within rat, the GEE again leaving out each rat, BH across theta and gamma, "
                      "and a node model (each pair's Session change the sum of its two regions') tested against the full model (5 df).",
            source="Tab 11's Session × Pair rows (J6–J11); its GEE term is tab 11's.")
    import warnings
    import statsmodels.formula.api as smf
    B = _incidence()
    out, h1 = {}, []
    for band in BANDS:
        _keep, rows, _rb = E.rows_phase1(X.T, band)
        df = _frame(rows)
        Bd = next((z for z in X.EM.get("bands") or [] if z["band"] == band), {})
        sp = next((dict(t) for t in (Bd.get("phase1") or {}).get("a1") or [] if t["term"] == "Session × Pair"), None)
        if sp is None:
            sp = safe(lambda: term(df, "y ~ C(day, Sum) * C(pair, Sum)", "gamma", "Session × Pair"))
        n = int(df["rat"].nunique())
        x = {"band": band, "gee": sp, "n": n}
        d2 = df.copy()
        d2["ly"] = np.log(d2["y"])
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mm = smf.mixedlm("ly ~ C(day, Sum) * C(pair, Sum)", d2, groups="rat", vc_formula={"pair": "0 + C(pair)"}).fit(reml=True)
            names = list(mm.fe_params.index)
            idx = [i for i, nm in enumerate(names) if "C(day" in nm and "C(pair" in nm]
            x["lmm"] = _lmm_f(mm.fe_params.values, np.asarray(mm.cov_params().loc[names, names]), idx, n)
        except Exception as exc:                             # noqa: BLE001
            x["lmm"] = {"error": str(exc)}
        loo = []
        for r in sorted(df["rat"].unique()):
            g = safe(lambda: term(df[df["rat"] != r], "y ~ C(day, Sum) * C(pair, Sum)", "gamma", "Session × Pair"))
            loo.append({"rat": int(r), "chi2": g.get("chi2"), "df": g.get("df"), "p": g.get("p")})
        x["loo"] = loo
        nod = {}
        P_ = sorted(int(s[1:]) for s in df["pair"].unique())
        f = "y ~ 0 + C(pair) + C(pair):C(day, Treatment('Precon1'))"
        for kind in ("gee", "lmm"):
            try:
                if kind == "gee":
                    res = E.gee(df, f, "gamma")
                    names = list(res.params.index)
                    idx = [i for i, nm in enumerate(names) if ":" in nm and "Precon4" in nm]
                    beta = res.params.values[idx]
                    V = np.asarray(res.cov_naive)[np.ix_(idx, idx)]
                else:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        mm2 = smf.mixedlm(f.replace("y ~", "ly ~"), d2, groups="rat", vc_formula={"pair": "0 + C(pair)"}).fit(reml=True)
                    names = list(mm2.fe_params.index)
                    idx = [i for i, nm in enumerate(names) if ":" in nm and "Precon4" in nm]
                    beta = mm2.fe_params.values[idx]
                    V = np.asarray(mm2.cov_params().loc[names, names])[np.ix_(idx, idx)]
                a, A, resid, chi2v, k = node_test(beta, V, B[P_])
                nd = {"chi2": chi2v, "df": k, "p": E._chi2_sf(chi2v, k),
                      "nodes": [{"region": REGION_SAY[REGIONS[i]], "ratio": math.exp(a[i]), "lo": math.exp(a[i] - 1.959964 * math.sqrt(A[i, i])),
                                 "hi": math.exp(a[i] + 1.959964 * math.sqrt(A[i, i]))} for i in range(len(REGIONS))],
                      "resid": [{"pair": PAIR_SAY[pp], "ratio": math.exp(beta[j]), "pred": math.exp(beta[j] - resid[j]), "resid": float(resid[j])}
                                for j, pp in enumerate(P_)]}
                if kind == "lmm":
                    from scipy.stats import f as fdist
                    nd.update({"F": chi2v / k, "df1": k, "df2": k * (n - 1), "p": float(fdist.sf(chi2v / k, k, k * (n - 1)))})
                nod[kind] = nd
            except Exception as exc:                         # noqa: BLE001
                nod[kind] = {"error": "%s: %s" % (type(exc).__name__, exc)}
        x["node"] = nod
        out[band] = x
        h1.append(x)
        for r in rows:
            R["csv"].append({"request": "A3", "band": band, "pair": PAIR_SAY[int(r["pair"][1:])], "rat": "J%d" % r["rat"],
                             "session": DAY_SAY(r["day"]), "value": r["y"]})
    for x, q in zip(h1, E.bh([(x["gee"] or {}).get("p") for x in h1])):
        if q is not None:
            x["gee"]["q"] = q
    rows = []
    for x in h1:
        g, nd, nl = x["gee"] or {}, x["node"].get("gee", {}), x["node"].get("lmm", {})
        w = max(x["loo"], key=lambda z: 2 if z["p"] is None else z["p"])
        rows.append([x["band"].capitalize(), x["n"], "%s, %s (model-based)" % (chi(g), fp(g.get("p"))), fq(g.get("q")), lmm_say(x["lmm"]),
                     "largest %s without J%d" % (fp(w["p"]), w["rat"]),
                     ("%s, %s" % (chi(nd), fp(nd.get("p")))) if "chi2" in nd else nd.get("error", ""), lmm_say(nl)])
    R["tables"].append(table("H1: Session × Pair, four ways",
                             ["Band", "n", "GEE", "q (θ and γ)", "LMM", "Leave-one-out", "Full vs node model (GEE)", "Full vs node model (LMM)"], rows,
                             [sig(x["gee"], "q") for x in h1],
                             note="The LMM's denominator df is k(n − 1), as for every LMM in tabs 11–14. The node model says each "
                                  "pair's Late/Early ratio is the product of its two regions' ratios; the last two columns test whether "
                                  "pair-specific change beyond that is needed (5 df)."))
    for x in h1:
        nd = x["node"].get("gee", {})
        if "nodes" in nd:
            R["tables"].append(table("%s: each region's ratio in the node model (GEE)" % x["band"].capitalize(), ["Region", "Late/Early [95% CI]"],
                                     [[z["region"], "×%s [%s, %s]" % (num(z["ratio"]), num(z["lo"]), num(z["hi"]))] for z in nd["nodes"]],
                                     [z["lo"] > 1 or z["hi"] < 1 for z in nd["nodes"]]))
            R["tables"].append(table("%s: node-model residuals per pair" % x["band"].capitalize(),
                                     ["Pair", "Observed Late/Early", "Node model's", "Residual (log)"],
                                     [[z["pair"], "×%s" % num(z["ratio"]), "×%s" % num(z["pred"]), num(z["resid"], 3)] for z in nd["resid"]]))
    for x in h1:
        g, nd, nl = x["gee"] or {}, x["node"].get("gee", {}), x["node"].get("lmm", {})
        R["summary"].append("%s: GEE %s, %s (%s); LMM %s; leaving out each rat, the largest %s; pair-specific change beyond the node model: GEE %s, LMM %s." % (
            x["band"].capitalize(), chi(g), fp(g.get("p")), fq(g.get("q")), lmm_say(x["lmm"]),
            fp(max((z["p"] if z["p"] is not None else 1.0) for z in x["loo"])), fp(nd.get("p")), fp(nl.get("p"))))
    R["n"] = n_say([x["n"] for x in h1])
    R["reading"] = ["Only pair-specific change beyond the node model supports a network account; node-level change is closer to a focal account or an electrode effect."]
    R["data"] = out
    return R


# --------------------------------------------------------------------------
# A4. Trial-mean coherence and noise floors
# --------------------------------------------------------------------------
def keff(k):
    return k / (1.0 + 2.0 * JP.RHO ** 2)


def a4(X):
    R = rec("A4", ran="The mean over trials of each trial's own band coherence (cue pair; each trial its own spectra, the mean of its valid wire "
                      "pairs), Session on it for all 10 pairs (Gamma GEE, robust errors, BH across pairs); trials, pieces and the noise "
                      "floor per rat and session; bias-corrected ratios of both.",
            source="Tab 11's per-trial band coherence (the mean of trials it already keeps) and its pooled spectra.")
    wi = E.WINS.index("pair")
    out, ns, cnt = {}, [], []
    for (r, d), (a, _m) in sorted(X.em.items()):
        tn = X.jp[(r, d)][0]["tn"][JP.WF.index("pair")]
        per_trial = tn.max(axis=(1, 2))
        used = per_trial > 0
        K = float(np.median(per_trial[used])) if used.any() else float("nan")
        ok = a["nseg"][wi] > 0
        tot = float(np.median(a["nseg"][wi][ok])) if ok.any() else float("nan")
        cnt.append({"rat": r, "day": d, "trials": int(used.sum()), "pieces_trial": K, "pieces_pooled": tot,
                    "floor_trial": 1.0 / keff(K), "floor_pooled": 1.0 / keff(tot)})
    R["tables"].append(table("Trials, pieces and noise floors", ["Rat", "Session", "Trials", "Pieces per trial (median)",
                                                                 "Pieces pooled (median wire pair)", "Single-trial floor", "Pooled floor"],
                             [["J%d" % c["rat"], DAY_SAY(c["day"]), c["trials"], num(c["pieces_trial"], 0), num(c["pieces_pooled"], 0),
                               num(c["floor_trial"], 3), num(c["floor_pooled"], 4)] for c in cnt],
                             note="Expected coherence with no coupling ≈ 1 ÷ the effective number of pieces, which is the pieces ÷ "
                                  "(1 + 2 × 0.167²) for Hann windows half overlapping."))
    fl = {(c["rat"], c["day"]): c for c in cnt}
    for band in BANDS:
        res = []
        for p in range(len(E.PAIRS)):
            tm = {k: float(v[p]) for k, v in X.T["trialmean"][band].items()}
            po = coh_vals(X, "pair", band, p)
            rats = [r for r in X.both(tm) if r in X.both(po)]
            x = {"pair": p, "band": band, "rats": rats}
            if len(rats) < E.MIN_RATS:
                x["error"] = "fewer than %d rats" % E.MIN_RATS
                res.append(x)
                continue
            ns.append(len(rats))
            bc_t = {k: (v - fl[k]["floor_trial"]) / (1 - fl[k]["floor_trial"]) for k, v in tm.items() if k in fl}
            bc_p = {k: (v - fl[k]["floor_pooled"]) / (1 - fl[k]["floor_pooled"]) for k, v in po.items() if k in fl}
            x["tm"] = safe(lambda: session(_frame(rows_of(tm, rats)), "gamma"))
            x["po"] = _a2_of(X, band, p)
            for key, v in (("tm_bc", bc_t), ("po_bc", bc_p)):
                low = sum(v[(r, d)] <= 0 for r in rats for d in DAYS)
                x[key] = safe(lambda: session(_frame(rows_of(v, rats)), "gamma")) if not low else \
                    {"error": "at or below the floor in %d of %d rat-sessions" % (low, 2 * len(rats))}
            x["below"] = {d: int(sum(po[(r, d)] < fl[(r, d)]["floor_trial"] for r in rats)) for d in DAYS}
            x["mean"] = {d: float(np.mean([po[(r, d)] for r in rats])) for d in DAYS}
            x["mean_tm"] = {d: float(np.mean([tm[(r, d)] for r in rats])) for d in DAYS}
            for rr in rats:
                for d in DAYS:
                    R["csv"].append({"request": "A4", "band": band, "pair": PAIR_SAY[p], "rat": "J%d" % rr, "session": DAY_SAY(d),
                                     "trial_mean": tm[(rr, d)], "pooled": po[(rr, d)], "floor_trial": fl[(rr, d)]["floor_trial"],
                                     "floor_pooled": fl[(rr, d)]["floor_pooled"]})
            res.append(x)
        for k in ("tm", "tm_bc", "po_bc"):
            bh_put([x.get(k) for x in res])
        out[band] = res
        rows, bold = [], []
        for x in res:
            if "error" in x:
                continue
            bc = lambda g: ("%s, %s" % (est(g), fq(g.get("q")))) if "est" in g else g.get("error", "")   # noqa: E731
            rows.append([PAIR_SAY[x["pair"]], len(x["rats"]), "%s, %s" % (est(x["po"]), fq(x["po"].get("q"))),
                         "%s, %s, %s" % (est(x["tm"]), fp(x["tm"].get("p")), fq(x["tm"].get("q"))), bc(x["po_bc"]), bc(x["tm_bc"]),
                         "%s / %s" % (num(x["mean"]["Precon1"], 3), num(x["mean"]["Precon4"], 3)),
                         "%s / %s" % (num(x["mean_tm"]["Precon1"], 3), num(x["mean_tm"]["Precon4"], 3)),
                         "%d / %d" % (x["below"]["Precon1"], x["below"]["Precon4"])])
            bold.append(sig(x["tm"], "q"))
        R["tables"].append(table("%s: pooled against trial-mean coherence, Late/Early" % band.capitalize(),
                                 ["Pair", "n", "Pooled (tab 11)", "Trial mean", "Pooled, bias-corrected", "Trial mean, bias-corrected",
                                  "Pooled mean, Early / Late", "Trial mean, Early / Late", "Rats with pooled below the single-trial floor, Early / Late"],
                                 rows, bold, note="Bias-corrected: (c − floor) ÷ (1 − floor) for each rat and session before the GEE. "
                                                  "Bold: the trial mean changes with q < .05."))
        for x in res:
            if "error" in x or not sig(x["po"], "q"):
                continue
            R["summary"].append("%s %s: pooled %s (%s); trial mean %s (%s, %s). %s" % (
                PAIR_SAY[x["pair"]], band, est(x["po"]), fq(x["po"].get("q")), est(x["tm"]), fp(x["tm"].get("p")), fq(x["tm"].get("q")),
                "Both changed: within-trial coupling changed." if sig(x["tm"], "q") else
                "Pooled only: cross-trial phase consistency changed." if not sig(x["tm"]) else
                "The trial mean moved the same way, but not after correction."))
    R["n"] = n_say(ns)
    R["reading"] = ["A matching trial-mean change means within-trial coupling changed. Pooled-only change means cross-trial phase consistency changed."]
    R["data"] = {"bands": out, "counts": cnt}
    return R


# --------------------------------------------------------------------------
# A5. Per-bin frequency tests
# --------------------------------------------------------------------------
def runs(hz, on):
    """Contiguous runs of True bins, as 'a–b Hz' (one bin: 'a Hz')."""
    out, start = [], None
    for i, v in enumerate(list(on) + [False]):
        if v and start is None:
            start = i
        if not v and start is not None:
            a, b = hz[start], hz[i - 1]
            out.append(("%s Hz" % num(a, 1)) if start == i - 1 else ("%s–%s Hz" % (num(a, 1), num(b, 1))))
            start = None
    return out


SP_SUM = "y ~ C(day, Sum) * C(period, Sum)"


def a5(X, progress=None):
    R = rec("A5", ran="Power: in each region and frequency bin, Session × Period (2 df, robust errors) and its three planned contrasts (1 df "
                      "each), BH across the band's bins within each region and test. Coherence: in each pair and bin, Session (1 df, robust "
                      "errors; Gamma GEE on the cue pair), BH across the band's bins. Theta at the FFT's 0.49-Hz bins, gamma in 2-Hz bins.",
            source="Tab 12's per-bin power and tab 11's per-bin coherence (the rows of their frequency-resolved models).")
    out = {"power": {}, "coh": {}}
    for band in BANDS:
        hz = [f for f, _m in E.bins_of(band)]
        pw = []
        for ri, r in enumerate(REGIONS):
            if progress:
                progress("A5: %s power in %s" % (band, REGION_SAY[r]))
            rats = FS.region_rats(X.PT, ri)
            _rows, rb = FS.power_rows(X.PT, band, ri, rats)
            dfb = _frame(rb)
            per = []
            for fi in range(len(hz)):
                sub = dfb[dfb["f"] == "f%02d" % fi]
                x = {"hz": hz[fi], "sp": safe(lambda: term(sub, SP_SUM, "normal", "Session × Period")),
                     "c": E.period_contrasts(sub, "normal") if len(sub) else {}}
                per.append(x)
            bh_put([x["sp"] for x in per])
            for a, b, _s in CONTRASTS:
                k = E.contrast_key(a, b)
                bh_put([x["c"].get(k) for x in per])
            pw.append({"region": r, "rats": rats, "bins": per})
            for x in per:
                R["csv"].append(dict({"request": "A5", "kind": "power", "band": band, "unit": REGION_SAY[r], "hz": x["hz"],
                                      "sp_chi2": x["sp"].get("chi2"), "sp_p": x["sp"].get("p"), "sp_q": x["sp"].get("q")},
                                     **{"%s_%s" % (E.contrast_key(a, b), k2): x["c"].get(E.contrast_key(a, b), {}).get(k3)
                                        for a, b, _s in CONTRASTS for k2, k3 in (("diff", "diff"), ("p", "p"), ("q", "q"))}))
        co = []
        for p in range(len(E.PAIRS)):
            vals = {k: v[p] for k, v in X.T["bins"]["pair"][band].items()}
            rats = [r for r in X.rats if all(np.all(np.isfinite(vals.get((r, d), [np.nan]))) for d in DAYS)]
            per = []
            for fi in range(len(hz)):
                v = {k: float(a[fi]) for k, a in vals.items()}
                per.append({"hz": hz[fi], "s": safe(lambda: session(_frame(rows_of(v, rats)), "gamma")) if len(rats) >= E.MIN_RATS else {"error": "too few rats"}})
            bh_put([x["s"] for x in per])
            co.append({"pair": p, "rats": rats, "bins": per})
            for x in per:
                R["csv"].append({"request": "A5", "kind": "coherence", "band": band, "unit": PAIR_SAY[p], "hz": x["hz"],
                                 "ratio": x["s"].get("est"), "lo": x["s"].get("lo"), "hi": x["s"].get("hi"), "p": x["s"].get("p"), "q": x["s"].get("q")})
        out["power"][band], out["coh"][band] = pw, co
        rows, bold = [], []
        for x in pw:
            cells = [REGION_SAY[x["region"]], len(x["rats"])]
            any_ = False
            for key, get in [("sp", lambda b: b["sp"])] + [(E.contrast_key(a, b), (lambda b, k=E.contrast_key(a, b): b["c"].get(k) or {})) for a, b, _s in CONTRASTS]:
                on = [sig(get(b), "q") for b in x["bins"]]
                nom = sum(sig(get(b)) for b in x["bins"])
                any_ |= any(on)
                cells.append(", ".join(runs(hz, on)) or ("none (%d nominal)" % nom if nom else "none"))
            rows.append(cells)
            bold.append(any_)
        R["tables"].append(table("%s power: bins with q < .05 (BH across the band's %d bins)" % (band.capitalize(), len(hz)),
                                 ["Region", "n", "Session × Period", "Session × (cue 1 vs baseline)", "Session × (cue 2 vs baseline)", "Session × (cue 2 vs cue 1)"],
                                 rows, bold, note="Contiguous runs of significant bins. Adjacent 0.49-Hz bins are correlated (the true resolution is "
                                                  "about 1.5 Hz); BH stays valid under that positive dependence. Every bin's test is in the CSV."))
        rows, bold = [], []
        for x in co:
            on = [sig(b["s"], "q") for b in x["bins"]]
            nom = sum(sig(b["s"]) for b in x["bins"])
            ests = [b["s"]["est"] for b in x["bins"] if b["s"].get("est") is not None]
            rows.append([PAIR_SAY[x["pair"]], len(x["rats"]), ", ".join(runs(hz, on)) or "none", nom,
                         ("×%s to ×%s" % (num(min(ests)), num(max(ests)))) if ests else ""])
            bold.append(any(on))
        R["tables"].append(table("%s coherence: bins with q < .05 (Session, BH across the band's %d bins)" % (band.capitalize(), len(hz)),
                                 ["Pair", "n", "Significant bins", "Bins with p < .05", "Late/Early range over bins"], rows, bold))
        for x in pw:
            for key, say, get in [("sp", "Session × Period", lambda b: b["sp"])] + [
                    (E.contrast_key(a, b), "Session × (%s)" % s.lower(), (lambda b, k=E.contrast_key(a, b): b["c"].get(k) or {})) for a, b, s in CONTRASTS]:
                on = [sig(get(b), "q") for b in x["bins"]]
                if any(on):
                    R["summary"].append("%s power, %s, %s: %s." % (REGION_SAY[x["region"]], band, say, ", ".join(runs(hz, on))))
        for x in co:
            on = [sig(b["s"], "q") for b in x["bins"]]
            if any(on):
                R["summary"].append("%s coherence, %s: Session at %s." % (PAIR_SAY[x["pair"]], band, ", ".join(runs(hz, on))))
    if not R["summary"]:
        R["summary"].append("No bin passes after correction across its band's bins, in power or coherence.")
    R["n"] = n_say([len(x["rats"]) for b in BANDS for x in out["power"][b]] + [len(x["rats"]) for b in BANDS for x in out["coh"][b]])
    R["reading"] = ["Interpret frequency only through these per-bin tests; they replace every model-based Session × Frequency and Session × Period × Frequency result."]
    R["data"] = out
    return R


# --------------------------------------------------------------------------
# A6. Robustness checks for interpreted effects
# --------------------------------------------------------------------------
def _rob_term(df, formula, fam, name, has, exclude=()):
    log = fam == "gamma"
    return robust(df, lambda d: term(d, formula, fam, name), formula, has, log, exclude)


def _rob_contrast(df, a, b, fam="normal"):
    two = df[df["period"].isin([E.PERIOD_CODE[a], E.PERIOD_CODE[b]])]
    f = "y ~ C(day, Treatment('Precon1')) * C(period, Treatment('%s'))" % E.PERIOD_CODE[b]
    fit = lambda d: E.interaction(d, f, ["Precon4", E.PERIOD_CODE[a]], fam)   # noqa: E731
    g = safe(lambda: fit(two))
    if "ratio" in g or "diff" in g:
        g = dict(g, est=g["ratio"] if fam == "gamma" else g["diff"], kind="ratio" if fam == "gamma" else "diff")
    g["robust"] = robust(two, fit, f, ["Precon4", E.PERIOD_CODE[a]], fam == "gamma")
    return g


def a6(X):
    R = rec("A6", ran="For each effect the text interprets: its estimate again, leave-one-rat-out (the largest p and which rat) and an LMM with a "
                      "random intercept for rat (F, both df, p). Power: band dB, normal GEE, Session averaged over the three periods; FOOOF: "
                      "the same fits as tab 12.",
            source="Tab 12's rows. Tab 12 ran leave-one-out only on its significant results, and none of these was one, so each is run here.")
    PW = lambda band, r: _frame(FS.power_rows(X.PT, band, REGIONS.index(r), FS.region_rats(X.PT, REGIONS.index(r)))[0])   # noqa: E731
    FO = lambda key, r: _frame(FS.fooof_rows(X.FT, key, r))  # noqa: E731
    items = []

    def sess(label, df, unit):
        g = safe(lambda: session(df, "normal", " * C(period, Sum)"))
        if "est" in g:
            g["robust"] = robust_session(df, "normal", " * C(period, Sum)")
        items.append((label, df, g, unit))

    def per(label, df):
        g = safe(lambda: term(df, SP_SUM, "normal", "Period"))
        if "chi2" in g:
            g["robust"] = _rob_term(df, SP_SUM, "normal", "Period", ["C(period"], exclude=["C(day"])
        items.append((label, df, g, ""))

    def sp(label, df):
        g = safe(lambda: term(df, SP_SUM, "normal", "Session × Period"))
        if "chi2" in g:
            g["robust"] = _rob_term(df, SP_SUM, "normal", "Session × Period", ["C(day", "C(period"])
        items.append((label, df, g, ""))
        for a, b, s in CONTRASTS:
            items.append(("%s: Session × (%s)" % (label.split(":")[0], s.lower()), df, _rob_contrast(df, a, b), ""))

    sess("ACC theta power: Session", PW("theta", "ACC"), "dB")
    per("dHC theta power: Period", PW("theta", "DHC"))
    per("OFC theta power: Period", PW("theta", "OFC"))
    sess("PER theta power: Session", PW("theta", "PER"), "dB")
    df = FO("offset", "ACC")
    if len(df):
        sess("FOOOF ACC aperiodic offset: Session", df, "log10 µV²/Hz")
    for r in ("OFC", "DHC"):
        df = FO("theta_cf", r)
        if len(df):
            sess("FOOOF %s theta peak frequency: Session" % REGION_SAY[r], df, "Hz")
    df = FO("exponent", "PER")
    if len(df):
        sp("FOOOF PER aperiodic exponent: Session × Period", df)
    df = FO("theta_pw", "PER")
    if len(df):
        sess("FOOOF PER theta peak power: Session", df, "log10")
    rows, bold = [], []
    for label, df, g, unit in items:
        n = int(df["rat"].nunique()) if len(df) else 0
        rb = g.get("robust") or {}
        w = "%s, without J%d" % (fp(rb.get("worst_p")), rb.get("worst_rat")) if rb.get("worst_rat") is not None else ""
        rows.append([label, n, est(g, unit) if g.get("est") is not None else "", chi(g), fp(g.get("p")), w, lmm_say(rb.get("lmm")),
                     "robust" if rb.get("robust") else "not robust" if rb else g.get("error", "")])
        bold.append(bool(rb.get("robust")))
        R["robust"].append("%s (%s%s, %s): %s" % (label, (est(g, unit) + ", ") if g.get("est") is not None else "", chi(g), fp(g.get("p")), rob_say(rb)))
        for _i, row in df.iterrows():
            R["csv"].append({"request": "A6", "effect": label, "rat": "J%d" % row["rat"], "session": DAY_SAY(row["day"]),
                             "period": row.get("period", ""), "value": row["y"]})
    R["tables"].append(table("Robustness of each interpreted effect", ["Effect", "n", "Estimate [95% CI]", "Wald", "p", "Leave-one-out: largest p",
                                                                     "LMM", "Verdict"], rows, bold,
                             note="Robust: p < .05 without each rat in turn and in the LMM. Estimates: Late − Early averaged over the "
                                  "three periods (Session), or the difference of differences (contrasts); Period has 2 df and no single estimate."))
    R["summary"] = ["%s: %s." % (label, "robust" if (g.get("robust") or {}).get("robust") else "not robust (%s)" % rob_say(g.get("robust") or {}).split(": ", 1)[-1])
                    for label, _df, g, _u in items]
    R["n"] = n_say([int(df["rat"].nunique()) for _l, df, _g, _u in items if len(df)])
    R["reading"] = ["Robust means p < .05 in the GEE, without each rat in turn, and in the LMM; nominal means p < .05 but q ≥ .05."]
    R["data"] = [{"label": label, "test": {k: v for k, v in g.items() if k != "robust"}, "robust": g.get("robust")} for label, _df, g, _u in items]
    return R


# --------------------------------------------------------------------------
# C1. Coherence by cue and by period (tab 11's phase 3, J6-J11)
# --------------------------------------------------------------------------
def _em_robust(X, kind, band, p, label):
    for r in X.EM.get("robust") or []:
        if r.get("kind") == kind and r.get("band") == band and r.get("pair") == p and r.get("label") == label:
            w = r.get("worst") or {}
            lm = r.get("lmm") or {}
            return {"loo": r.get("loo"), "worst_rat": w.get("rat"), "worst_p": w.get("p"), "loo_holds": bool(r.get("survives")), "lmm": lm,
                    "robust": bool(r.get("survives")) and lm.get("p") is not None and lm["p"] < ALPHA}
    return None


def c1(X):
    R = rec("C1", ran="Tab 11's coherence by period, read as it stands (J6–J11): Session × Period (baseline, cue 1, cue 2; 2 df, robust "
                      "errors) and its three planned contrasts as ratios of ratios, Session × Cue (cue 1 vs cue 2), BH across the 10 pairs, "
                      "leave-one-out and an LMM for every p < .05. Added here: the Session effect's q, Late/Early in each period, and the A1 "
                      "decomposition in each period for every pair that changes.",
            source="Tab 11, phases 2 and 3, set 'Without J3 and J4' (the Nov 4 figures D1.2, D1.3, D2.2 and D2.3).")
    out = {}
    wi_of = {w: E.WINS.index(w) for w in E.PERIODS}
    for band in BANDS:
        B = next(z for z in X.EM["bands"] if z["band"] == band)
        p3 = {x["pair"]: x for x in B["phase3"]["pairs"] if x}
        p2 = {x["pair"]: x for x in B["phase2"]["pairs"] if x}
        res = []
        for p in range(len(E.PAIRS)):
            x3, x2 = p3.get(p), p2.get(p)
            if not x3:
                continue
            x = {"pair": p, "rats": x3["rats"], "sp": dict(x3.get("sp") or {}), "contrasts": {}, "cue": E.session_cue(x2) if x2 else None}
            x["session"] = dict(next((t for t in x3.get("terms") or [] if t["term"] == "Session"), {}))
            for a, b, s in CONTRASTS:
                c = dict(x3["contrasts"].get(E.contrast_key(a, b)) or {})
                if c.get("ratio") is not None:
                    c.update(est=c["ratio"], kind="ratio")
                c["robust"] = _em_robust(X, "phase3", band, p, "Session × (%s)" % s.lower()) if sig(c) else None
                x["contrasts"][E.contrast_key(a, b)] = c
            x["sp"]["robust"] = _em_robust(X, "phase3", band, p, "Session × Period") if sig(x["sp"]) else None
            if x["cue"] and sig(x["cue"]):
                x["cue"]["robust"] = _em_robust(X, "phase2", band, p, "Session × Cue")
            # Late/Early within each period
            x["by_period"] = {}
            for w in E.PERIODS:
                vals = coh_vals(X, w, band, p)
                rats = X.both(vals)
                x["by_period"][w] = safe(lambda: session(_frame(rows_of(vals, rats)), "gamma"))
                for rr in rats:
                    for d in DAYS:
                        R["csv"].append({"request": "C1", "band": band, "pair": PAIR_SAY[p], "period": E.PERIOD_SAY[w], "rat": "J%d" % rr,
                                         "session": DAY_SAY(d), "value": vals[(rr, d)]})
            res.append(x)
        bh_put([x["session"] for x in res])
        for w in E.PERIODS:
            bh_put([x["by_period"][w] for x in res])
        # A1 in each period, for the pairs that change
        for x in res:
            changed = sig(x["sp"], "q") or any(sig(c, "q") for c in x["contrasts"].values()) or sig(x["cue"], "q")
            x["changed"] = changed
            if not changed:
                continue
            m = _bins(*BAND_LIM[band])
            dec = {}
            for w in E.PERIODS:
                vals = {"lxy": {}, "lxx": {}, "lyy": {}}
                for k, (a, _m) in X.em.items():
                    n = a["nseg"][wi_of[w], x["pair"]].astype(float)
                    ok = n > 0
                    if not ok.any():
                        continue
                    with np.errstate(invalid="ignore", divide="ignore"):
                        vals["lxy"][k] = float(np.log(np.abs(a["sab"][wi_of[w], x["pair"]][ok][:, m] / n[ok, None]) ** 2).mean())
                        vals["lxx"][k] = float(np.log(a["saa"][wi_of[w], x["pair"]][ok][:, m] / n[ok, None]).mean())
                        vals["lyy"][k] = float(np.log(a["sbb"][wi_of[w], x["pair"]][ok][:, m] / n[ok, None]).mean())
                rats = X.both(vals["lxy"])
                dec[w] = {}
                for t in ("lxy", "lxx", "lyy"):
                    g = safe(lambda: session(_frame(rows_of(vals[t], rats)), "normal"))
                    if "est" in g:
                        g = dict(g, kind="ratio", est=math.exp(g["est"]), lo=math.exp(g["lo"]), hi=math.exp(g["hi"]))
                    dec[w][t] = g
            x["a1"] = dec
        out[band] = res
        rows, bold = [], []
        for x in res:
            c = x["contrasts"]
            cell = lambda g: ("%s, %s, %s" % (est(g), fp(g.get("p")), fq(g.get("q")))) if g and g.get("est") is not None else ""   # noqa: E731
            rows.append([PAIR_SAY[x["pair"]], len(x["rats"]), "%s, %s, %s" % (chi(x["sp"]), fp(x["sp"].get("p")), fq(x["sp"].get("q")))] +
                        [cell(c[E.contrast_key(a, b)]) for a, b, _s in CONTRASTS] +
                        ["%s, %s" % (fp((x["cue"] or {}).get("p")), fq((x["cue"] or {}).get("q"))), "%s, %s" % (fp(x["session"].get("p")), fq(x["session"].get("q")))])
            bold.append(bool(x["changed"]))
        R["tables"].append(table("%s: Session × Period and its contrasts (ratios of ratios)" % band.capitalize(),
                                 ["Pair", "n", "Session × Period", "Session × (cue 1 vs baseline)", "Session × (cue 2 vs baseline)",
                                  "Session × (cue 2 vs cue 1)", "Session × Cue (tab 11 phase 2)", "Session (main effect)"], rows, bold,
                                 note="Ratio of ratios: Late's cue/baseline ratio over Early's. q: BH across the 10 pairs within each test. "
                                      "Bold: a pair with any q < .05."))
        rows = [[PAIR_SAY[x["pair"]]] + ["%s, %s" % (est(x["by_period"][w]), fq(x["by_period"][w].get("q"))) for w in E.PERIODS] for x in res]
        R["tables"].append(table("%s: Late/Early in each period" % band.capitalize(), ["Pair", "Baseline", "Cue 1", "Cue 2"], rows,
                                 [any(sig(x["by_period"][w], "q") for w in E.PERIODS) for x in res],
                                 note="Each period's own Gamma GEE; q across the 10 pairs within a period. Session-within-period comparisons "
                                      "can't localize an interaction; the contrasts above do that."))
        for x in res:
            for t, s in ((x["sp"], "Session × Period"),) + tuple((x["contrasts"][E.contrast_key(a, b)], "Session × (%s)" % s2.lower()) for a, b, s2 in CONTRASTS):
                if t.get("robust"):
                    R["robust"].append("%s %s, %s: %s" % (PAIR_SAY[x["pair"]], band, s, rob_say(t["robust"])))
    for band in BANDS:
        for x in out[band]:
            bp = x["by_period"]
            if x["pair"] in (5,) or x["changed"] or any(sig(bp[w], "q") for w in E.PERIODS):
                R["summary"].append("%s %s: Late/Early at baseline %s, cue 1 %s, cue 2 %s; Session × Period %s, %s (%s)%s." % (
                    PAIR_SAY[x["pair"]], band, est(bp["base10"]), est(bp["cue1"]), est(bp["cue2"]), chi(x["sp"]), fp(x["sp"].get("p")),
                    fq(x["sp"].get("q")), "; it changes in the cue response" if x["changed"] else "; the change is not cue-specific"))
    R["n"] = n_say([len(x["rats"]) for b in BANDS for x in out[b]])
    R["reading"] = ["If dHC–OFC coherence fell equally at baseline, the change is session-wide, like the ACC power drop, and a learning "
                    "interpretation weakens. If it fell only during the cues, it's cue-related."]
    R["data"] = out
    return R


# --------------------------------------------------------------------------
# B1. FOOOF
# --------------------------------------------------------------------------
def b1(X):
    R = rec("B1", ran="Tab 12's FOOOF fits, reported in full: Late − Early (averaged over periods) with 95% CIs for every parameter and region, "
                      "Session q (BH across the 5 regions), the three planned contrasts, n, the settings, and each fit's R².",
            source="Tab 12's fits (the same FOOOF call on the same spectra) and its Session × Period tests.")
    Fo = X.F.get("fooof") or {}
    rows, bold, allsp = [], [], []
    res = {}
    for key, say, unit in FS.FOOOF_PARAMS:
        per = []
        for r in REGIONS:
            df = _frame(FS.fooof_rows(X.FT, key, r))
            t12 = next((z for z in Fo.get(key) or [] if z.get("region") == r), {}) or {}
            x = {"region": r, "n": int(df["rat"].nunique()) if len(df) else 0, "sp": dict(t12.get("sp") or {}),
                 "contrasts": {k: dict(v) for k, v in (t12.get("contrasts") or {}).items()}, "error": t12.get("error")}
            if x["n"] >= E.MIN_RATS:
                x["session"] = safe(lambda: session(df, "normal", " * C(period, Sum)"))
                for _i, row in df.iterrows():
                    R["csv"].append({"request": "B1", "parameter": key, "region": REGION_SAY[r], "rat": "J%d" % row["rat"],
                                     "session": DAY_SAY(row["day"]), "period": row["period"], "value": row["y"]})
            else:
                x["session"] = {"error": "fewer than %d rats with a fit in all six cells" % E.MIN_RATS}
            per.append(x)
            if x["sp"].get("p") is not None:
                allsp.append(x["sp"])
        bh_put([x["session"] for x in per])
        res[key] = per
        for x in per:
            s = x["session"]
            c = x["contrasts"]
            rows.append([say, REGION_SAY[x["region"]], x["n"],
                         (est(s, unit) + ((" (%s dB)" % num(10 * s["est"])) if key == "offset" else "")) if s.get("est") is not None else s.get("error", ""),
                         fp(s.get("p")), fq(s.get("q")),
                         "%s, %s, %s" % (chi(x["sp"]), fp(x["sp"].get("p")), fq(x["sp"].get("q"))) if x["sp"] else ""] +
                        ["%s, %s" % (est(dict(c.get(E.contrast_key(a, b)) or {}, est=(c.get(E.contrast_key(a, b)) or {}).get("diff"), kind="diff")),
                                     fp((c.get(E.contrast_key(a, b)) or {}).get("p"))) if c.get(E.contrast_key(a, b)) else "" for a, b, _s in CONTRASTS])
            bold.append(sig(s, "q") or sig(x["sp"], "q"))
    qall = E.bh([z.get("p") for z in allsp])
    for z, q in zip(allsp, qall):
        z["q_all"] = q
    R["tables"].append(table("Every parameter and region", ["Parameter", "Region", "n", "Late − Early [95% CI]", "p", "q (5 regions)",
                                                            "Session × Period (tab 12)", "Session × (cue 1 vs baseline)", "Session × (cue 2 vs baseline)",
                                                            "Session × (cue 2 vs cue 1)"], rows, bold,
                             note="Aperiodic offset in log10 µV²/Hz, with 10 × Δ in dB beside it (to set against the theta power change). "
                                  "Contrasts: difference of differences (Late's cue − baseline minus Early's)."))
    per_exp = next((x for x in res.get("exponent", []) if x["region"] == "PER"), None)
    if per_exp and per_exp["sp"].get("p") is not None:
        R["summary"].append("PER aperiodic exponent, Session × Period: %s, %s; %s across the 5 regions, %s across all %d Session × Period FOOOF tests." % (
            chi(per_exp["sp"]), fp(per_exp["sp"]["p"]), fq(per_exp["sp"].get("q")), fq(per_exp["sp"].get("q_all")), len(allsp)))
    acc = next((x for x in res.get("offset", []) if x["region"] == "ACC"), None)
    if acc and acc["session"].get("est") is not None:
        R["summary"].append("ACC aperiodic offset: Late − Early %s log10 µV²/Hz, %s dB (%s, %s)." % (
            est(acc["session"]), num(10 * acc["session"]["est"]), fp(acc["session"]["p"]), fq(acc["session"].get("q"))))
    for key in ("theta_cf",):
        for x in res.get(key, []):
            if x["session"].get("est") is not None and sig(x["session"]):
                R["summary"].append("%s theta peak frequency: Late − Early %s (%s, %s)." % (REGION_SAY[x["region"]], est(x["session"], "Hz"),
                                                                                         fp(x["session"]["p"]), fq(x["session"].get("q"))))
    # fit quality and the settings
    r2 = {}
    for (rat, d, w, r), v in X.FT.items():
        r2.setdefault((r, d), []).append(v.get("r2"))
    R["tables"].append(table("Fit quality: mean R² per region and session", ["Region", "Early", "Late", "Fits (sides × periods × rats)"],
                             [[REGION_SAY[r], num(np.nanmean(r2.get((r, "Precon1"), [np.nan])), 3), num(np.nanmean(r2.get((r, "Precon4"), [np.nan])), 3),
                               len(r2.get((r, "Precon1"), [])) + len(r2.get((r, "Precon4"), []))] for r in REGIONS]))
    R["tables"].append(table("Settings", ["Setting", "Value"], [
        ["Frequency range", "%g–%g Hz (below the 59–61 Hz notch)" % FS.FOOOF_RANGE], ["Aperiodic mode", "fixed (no knee)"],
        ["Peak width limits", "1–8 Hz"], ["Maximum number of peaks", "6"], ["Minimum peak height", "0.05 (log10 power)"],
        ["Theta peak", "the strongest peak centred in 5–12 Hz; none when no peak is there"],
        ["Spectra", "each side's pooled Welch spectrum (as power); a region the mean of its sides' parameters"],
        ["Too few fits", "a region and parameter is tested only when at least %d rats have a fit in all six session × period cells" % E.MIN_RATS],
        ["Fit error", "not kept by tab 12; R² is"]]))
    R["n"] = n_say([x["n"] for v in res.values() for x in v if x["n"]])
    R["reading"] = []
    R["data"] = res
    return R


# --------------------------------------------------------------------------
# B2. Power output
# --------------------------------------------------------------------------
def b2(X):
    R = rec("B2", ran="Per region and band, Session (Late − Early averaged over periods, normal GEE, robust errors) with BH across the 10 "
                      "per-region models; the Period term's q across the same 10; and the pairwise period comparisons inside the Period main "
                      "effect for dHC and OFC theta (pooled over sessions), BH across the six.",
            source="Tab 12's per-region rows (tier 3a).")
    ses, prd = [], []
    for band in BANDS:
        for ri, r in enumerate(REGIONS):
            df = _frame(FS.power_rows(X.PT, band, ri, FS.region_rats(X.PT, ri))[0])
            s = safe(lambda: session(df, "normal", " * C(period, Sum)"))
            s.update(region=r, band=band, n=int(df["rat"].nunique()))
            ses.append(s)
            t = safe(lambda: term(df, SP_SUM, "normal", "Period"))
            t.update(region=r, band=band)
            prd.append(t)
    bh_put(ses)
    bh_put(prd)
    R["tables"].append(table("Session, each region and band", ["Band", "Region", "n", "Late − Early [95% CI] (dB)", "p", "q (10 models)", "Period", "Period q"],
                             [[s["band"].capitalize(), REGION_SAY[s["region"]], s["n"], est(s, "dB"), fp(s.get("p")), fq(s.get("q")),
                               "%s, %s" % (chi(t), fp(t.get("p"))), fq(t.get("q"))] for s, t in zip(ses, prd)],
                             [sig(s, "q") for s in ses]))
    pw = []
    for r in ("DHC", "OFC"):
        df = _frame(FS.power_rows(X.PT, "theta", REGIONS.index(r), FS.region_rats(X.PT, REGIONS.index(r)))[0])
        for a, b, s in ((("cue1", "base10", "Cue 1 vs baseline"), ("cue2", "base10", "Cue 2 vs baseline"), ("cue2", "cue1", "Cue 2 vs cue 1"))):
            two = df[df["period"].isin([E.PERIOD_CODE[a], E.PERIOD_CODE[b]])]
            g = safe(lambda: coef(E.gee(two, "y ~ C(day, Sum) + C(period, Treatment('%s'))" % E.PERIOD_CODE[b], "normal"), [E.PERIOD_CODE[a]], "normal"))
            g.update(region=r, what=s)
            pw.append(g)
        for _i, row in df.iterrows():
            R["csv"].append({"request": "B2", "region": REGION_SAY[r], "band": "theta", "rat": "J%d" % row["rat"], "session": DAY_SAY(row["day"]),
                             "period": row["period"], "dB": row["y"]})
    bh_put(pw)
    R["tables"].append(table("Theta power: the Period main effect's pairwise comparisons (pooled over sessions)",
                             ["Region", "Comparison", "Difference [95% CI] (dB)", "p", "q (6)"],
                             [[REGION_SAY[g["region"]], g["what"], est(g, "dB"), fp(g.get("p")), fq(g.get("q"))] for g in pw], [sig(g, "q") for g in pw]))
    for g in pw:
        if sig(g, "q"):
            R["summary"].append("%s theta: %s %s (%s)." % (REGION_SAY[g["region"]], g["what"].lower(), est(g, "dB"), fq(g.get("q"))))
    for s in ses:
        if sig(s):
            R["summary"].append("%s %s power, Session: %s (%s, %s)." % (REGION_SAY[s["region"]], s["band"], est(s, "dB"), fp(s["p"]), fq(s.get("q"))))
    R["n"] = n_say([s["n"] for s in ses])
    R["data"] = {"session": ses, "period": prd, "pairwise": pw}
    return R


# --------------------------------------------------------------------------
# B3. RSC cue 2 (exploratory)
# --------------------------------------------------------------------------
def broadband(X):
    """{(rat, day, period): RSC dB over 2-90 Hz without 59-61}."""
    m = (E.FREQS >= 2.0) & (E.FREQS <= 90.0) & ~((E.FREQS > 59.0) & (E.FREQS < 61.0))
    out = {}
    for w in E.PERIODS:
        for (rat, d), P in X.PT["psd"][w].items():
            side = FS._db(E._nanmean(P[:, m], axis=1))
            out[(rat, d, w)] = float(E._nanmean(side[FS.region_sides("RSC")], axis=0))
    return out


def cue_pairs(X):
    """Each rat's two cue pairs and trials of each per session, from the
    trials themselves."""
    out = {}
    for (r, d), (_a, meta) in sorted(X.jp.items()):
        for t in meta["trials"]:
            out.setdefault(r, {}).setdefault(t["label"], {}).setdefault(d, 0)
            out[r][t["label"]][d] += 1
    return out


def b3(X):
    R = rec("B3", ran="Exploratory. In RSC: Session × (cue 2 vs cue 1) and Session × (cue 2 vs baseline), 1 df each, robust errors, on FOOOF's "
                      "aperiodic offset and exponent and on broadband power (2–90 Hz without 59–61 Hz); leave-one-out (watch J6) and an LMM.",
            source="Tab 12's FOOOF fits and power spectra.")
    bb = broadband(X)
    rats = [r for r in X.rats if all(np.isfinite(bb.get((r, d, w), np.nan)) for d in DAYS for w in E.PERIODS)]
    dfs = {"Broadband power (dB)": _frame([{"rat": r, "day": d, "period": E.PERIOD_CODE[w], "y": bb[(r, d, w)]} for r in rats for d in DAYS for w in E.PERIODS]),
           "Aperiodic offset": _frame(FS.fooof_rows(X.FT, "offset", "RSC")), "Aperiodic exponent": _frame(FS.fooof_rows(X.FT, "exponent", "RSC"))}
    rows, bold = [], []
    for say, df in dfs.items():
        for a, b, s in (("cue2", "cue1", "Cue 2 vs cue 1"), ("cue2", "base10", "Cue 2 vs baseline")):
            g = _rob_contrast(df, a, b) if len(df) else {"error": "no rows"}
            rb = g.get("robust") or {}
            rows.append([say, s, int(df["rat"].nunique()) if len(df) else 0, est(g), fp(g.get("p")),
                         ("%s, without J%d" % (fp(rb.get("worst_p")), rb["worst_rat"])) if rb.get("worst_rat") is not None else "",
                         "J6 out: %s" % fp(next((z["p"] for z in rb.get("loo") or [] if z["rat"] == 6), None)), lmm_say(rb.get("lmm")),
                         "robust" if rb.get("robust") else "not robust"])
            bold.append(sig(g))
            R["summary"].append("RSC %s, Session × (%s): %s, %s; %s." % (say.lower(), s.lower(), est(g), fp(g.get("p")), rob_say(rb)))
        for _i, row in df.iterrows():
            R["csv"].append({"request": "B3", "measure": say, "rat": "J%d" % row["rat"], "session": DAY_SAY(row["day"]), "period": row["period"], "value": row["y"]})
    R["tables"].append(table("RSC, exploratory (no correction)", ["Measure", "Contrast", "n", "Difference of differences [95% CI]", "p",
                                                                   "Leave-one-out: largest p", "Without J6", "LMM", "Verdict"], rows, bold))
    cp = cue_pairs(X)
    R["tables"].append(table("The cue pairs each rat heard (from its trials)", ["Rat", "Cue pair", "Early trials", "Late trials"],
                             [["J%d" % r, lab, v.get("Precon1", 0), v.get("Precon4", 0)] for r in sorted(cp) for lab, v in sorted(cp[r].items())]))
    first = {}
    for r in cp:
        for lab in cp[r]:
            a = lab.split("→")[0].strip()
            first.setdefault(a, set()).add(r)
    R["tables"].append(table("Which sound opens a pair, across the six rats", ["Sound as cue 1", "Rats"],
                             [[s, ", ".join("J%d" % r for r in sorted(v))] for s, v in sorted(first.items())],
                             note="Each rat hears two pairs; balanced would put every sound first in the same number of rats."))
    R["n"] = n_say([int(df["rat"].nunique()) for df in dfs.values() if len(df)])
    R["reading"] = ["Labelled exploratory. If the six rats aren't balanced across the counterbalanced cue pairs, cue 2 vs. cue 1 partly confounds serial position with the stimulus."]
    R["data"] = {"pairs": {str(k): v for k, v in cp.items()}}
    return R


# --------------------------------------------------------------------------
# B4. Theta vs gamma
# --------------------------------------------------------------------------
def b4(X):
    R = rec("B4", ran="For each pair, Session × Band (theta vs gamma) on cue-pair coherence (Gamma GEE, log link, 1 df, robust errors), BH "
                      "across the 10 pairs; the same on debiased wPLI (normal GEE).",
            source="Tab 11's band coherence; this tab's wPLI.")
    res = []
    for p in range(len(E.PAIRS)):
        vals = {b: coh_vals(X, "pair", b, p) for b in BANDS}
        rats = [r for r in X.both(vals["theta"]) if r in X.both(vals["gamma"])]
        rows = [{"rat": r, "day": d, "band": b, "y": vals[b][(r, d)]} for r in rats for d in DAYS for b in BANDS]
        df = _frame(rows)
        f = "y ~ C(day, Treatment('Precon1')) * C(band, Treatment('theta'))"
        g = safe(lambda: E.interaction(df, f, ["Precon4", "gamma"], "gamma"))
        if "ratio" in g:
            g.update(est=g["ratio"], kind="ratio")
        wv = {b: {k: _wpli_ppc(X.jp[k][0], "pair", p, _bins(*BAND_LIM[b]))[0] for k in X.em} for b in BANDS}
        wr = [r for r in X.both(wv["theta"]) if r in X.both(wv["gamma"])]
        dfw = _frame([{"rat": r, "day": d, "band": b, "y": wv[b][(r, d)]} for r in wr for d in DAYS for b in BANDS])
        gw = safe(lambda: E.interaction(dfw, f, ["Precon4", "gamma"], "normal"))
        if "diff" in gw:
            gw.update(est=gw["diff"], kind="diff")
        res.append({"pair": p, "n": len(rats), "coh": g, "wpli": gw})
        for row in rows:
            R["csv"].append({"request": "B4", "pair": PAIR_SAY[p], "rat": "J%d" % row["rat"], "session": DAY_SAY(row["day"]), "band": row["band"],
                             "coherence": row["y"], "wpli": wv[row["band"]].get((row["rat"], row["day"]))})
    bh_put([x["coh"] for x in res])
    bh_put([x["wpli"] for x in res])
    R["tables"].append(table("Session × Band", ["Pair", "n", "Coherence: gamma's Late/Early over theta's [95% CI]", "p", "q",
                                                "wPLI: gamma's Late − Early minus theta's", "p", "q"],
                             [[PAIR_SAY[x["pair"]], x["n"], est(x["coh"]), fp(x["coh"].get("p")), fq(x["coh"].get("q")), est(x["wpli"]),
                               fp(x["wpli"].get("p")), fq(x["wpli"].get("q"))] for x in res], [sig(x["coh"], "q") for x in res]))
    hit = [x for x in res if sig(x["coh"], "q")]
    R["summary"].append(("Session × Band passes after correction in %s." % ", ".join(PAIR_SAY[x["pair"]] for x in hit)) if hit else
                        "No pair's change differs between theta and gamma after correction (smallest %s): the changes look band-general." %
                        fq(min((x["coh"].get("q") for x in res if x["coh"].get("q") is not None), default=None)))
    R["n"] = n_say([x["n"] for x in res])
    R["data"] = res
    return R


# --------------------------------------------------------------------------
# B5. Technical checks (what is already measured, and 1-4 Hz)
# --------------------------------------------------------------------------
def b5(X):
    from . import monolith as MO
    R = rec("B5", ran="Read from what was already measured: the shared-reference screen for every recording, the bipolar re-referencing "
                      "check, wire-pair and trial counts, and J9 beside the other rats; and from tab 11's pooled spectra, cue-pair "
                      "coherence at 1–4 Hz, Session per pair (Gamma GEE, BH across the 10). Coherence and EMG power at 100–200 Hz were "
                      "not run (Shahriar, 2026-11-06): the stored spectra stop at 95 Hz.",
            source="Tab 11's reference check and pooled spectra; the bipolar check behind the methods (joepub/bipolar.json).")
    rc = X.EM.get("reference_check") or []
    R["tables"].append(table("The shared-reference screen, every recording (10-s baselines)", ["Rat", "Session", "Coherence at 75–90 Hz",
                                                                                               "Rise from 4–8 Hz", "Median |phase|, 30–90 Hz", "Excluded"],
                             [["J%d" % x["rat"], DAY_SAY(x["day"]), num(x["hg"]), "+" + num(x["rise"]), "%s°" % num(x["phase"], 0),
                               "yes" if x["rat"] in JP.DROP else ""] for x in sorted(rc, key=lambda z: (z["rat"], z["day"]))],
                             [x["rat"] in JP.DROP for x in sorted(rc, key=lambda z: (z["rat"], z["day"]))]))
    bip = {}
    try:
        with open(MO._path("joepub", "bipolar.json"), encoding="utf-8") as fh:
            bip = json.load(fh)
    except OSError:
        pass
    if bip:
        rows = []
        for p in range(len(E.PAIRS)):
            cell = []
            for d in DAYS:
                ref = [e["ref"]["gamma"][p] for e in bip.values() if e.get("rat") not in JP.DROP and e.get("day") == d and e["ref"]["gamma"][p] is not None]
                bp = [e["bip"]["gamma"][p] for e in bip.values() if e.get("rat") not in JP.DROP and e.get("day") == d and e["bip"]["gamma"][p] is not None]
                cell += [num(np.mean(ref), 3) if ref else "", num(np.mean(bp), 3) if bp else ""]
            rows.append([PAIR_SAY[p]] + cell)
        R["tables"].append(table("Bipolar re-referencing (a check only): gamma coherence on the 10-s baseline, J6–J11 mean",
                                 ["Pair", "Early, as recorded", "Early, bipolar", "Late, as recorded", "Late, bipolar"], rows,
                                 note="Bipolar (wire minus wire within a region) takes every rat's gamma coherence to about 0.01, which "
                                      "is why it was used as a check only."))
    rows = []
    for (r, d) in sorted(X.em):
        w = X.T["wires"][(r, d)]
        rows.append(["J%d" % r, DAY_SAY(d), (X.EM.get("trials") or {}).get("%s r%d" % (d, r), "")] +
                    ["%d/%d" % (int(w[p, :2].sum()), int(w[p, 2:].sum())) for p in range(len(E.PAIRS))])
    R["tables"].append(table("Trials and valid wire pairs (ipsilateral/contralateral) per rat and session", ["Rat", "Session", "Trials"] +
                             [PAIR_SAY[p] for p in range(len(E.PAIRS))], rows))
    # J9 against the rest, on every nominal coherence effect
    j9 = []
    for band in BANDS:
        for p in range(len(E.PAIRS)):
            c = _a2_of(X, band, p)
            if not sig(c):
                continue
            vals = coh_vals(X, "pair", band, p)
            rats = X.both(vals)
            if 9 not in rats:
                continue
            g = safe(lambda: session(_frame(rows_of(vals, [r for r in rats if r != 9])), "gamma"))
            own = vals[(9, "Precon4")] / vals[(9, "Precon1")]
            others = [vals[(r, "Precon4")] / vals[(r, "Precon1")] for r in rats if r != 9]
            j9.append([PAIR_SAY[p], band, "%s, %s" % (est(c), fq(c.get("q"))), "×%s" % num(own), "×%s to ×%s" % (num(min(others)), num(max(others))),
                       "%s, %s" % (est(g), fp(g.get("p")))])
    R["tables"].append(table("J9 and every nominal coherence effect (cue pair)", ["Pair", "Band", "All six rats", "J9's own Late/Early",
                                                                                  "The other rats' range", "Without J9"], j9))
    w9 = [int(X.T["wires"][(9, d)].sum()) for d in DAYS if (9, d) in X.T["wires"]]
    wo = [int(X.T["wires"][(r, d)].sum()) for r in X.rats if r != 9 for d in DAYS if (r, d) in X.T["wires"]]
    rc9 = [x for x in rc if x["rat"] == 9]
    R["summary"].append("J9 has %s valid wire pairs per session (the others %d–%d); its screen values are %s, the highest of the kept rats and still far below J3 and J4's." % (
        " and ".join(str(v) for v in w9), min(wo), max(wo), "; ".join("%s %s at 75–90 Hz, %s°" % (DAY_SAY(x["day"]), num(x["hg"]), num(x["phase"], 0)) for x in rc9)))
    # 1-4 Hz
    m = _bins(1.0, 4.0)
    res = []
    for p in range(len(E.PAIRS)):
        vals = {k: float(E.band_value(E.rat_spectrum(a, "pair")[p], "theta") * 0 + E._nanmean(E.rat_spectrum(a, "pair")[p][m], axis=-1))
                for k, (a, _m) in X.em.items()}
        rats = X.both(vals)
        g = safe(lambda: session(_frame(rows_of(vals, rats)), "gamma"))
        g["pair"], g["n"] = p, len(rats)
        res.append(g)
        for rr in rats:
            for d in DAYS:
                R["csv"].append({"request": "B5", "measure": "coherence 1-4 Hz", "pair": PAIR_SAY[p], "rat": "J%d" % rr, "session": DAY_SAY(d), "value": vals[(rr, d)]})
    bh_put(res)
    R["tables"].append(table("Outside the bands: cue-pair coherence at 1–4 Hz", ["Pair", "n", "Late/Early [95% CI]", "p", "q",
                                                                                 "Theta's Late/Early", "Gamma's Late/Early"],
                             [[PAIR_SAY[g["pair"]], g["n"], est(g), fp(g.get("p")), fq(g.get("q")), est(_a2_of(X, "theta", g["pair"])),
                               est(_a2_of(X, "gamma", g["pair"]))] for g in res], [sig(g, "q") for g in res],
                             note="The same pairs changing the same way outside theta and gamma would mean a broadband, likely technical, change."))
    same = [g for g in res if sig(g, "q")]
    R["summary"].append(("At 1–4 Hz coherence changes after correction in %s." % ", ".join(PAIR_SAY[g["pair"]] for g in same)) if same else
                        "At 1–4 Hz no pair's coherence changes after correction.")
    R["summary"].append("Reference: J8, J9 and J10's recordings changed from the reference wire to the Subject Ground screw between Early and Late; "
                        "both were in the cerebellum, so this is treated as no change in reference location and is not tested.")
    R["notes"].append("Cue parameters: whether either cue is periodic (a clicker or a pulsed tone), and at what rate, is not in the recordings. "
                      "Needs Joe: the MED-PC program or the sound files say.")
    R["notes"].append("EMG and coherence at 100–200 Hz: not run (Shahriar, 2026-11-06).")
    R["n"] = n_say([g["n"] for g in res])
    R["data"] = {"j9": j9, "low": res}
    return R


# --------------------------------------------------------------------------
# B7. Session x Region LMM for power
# --------------------------------------------------------------------------
def b7(X):
    R = rec("B7", ran="Tier 1's model (2 sessions × 3 periods × 5 regions, band dB) with the mixed model beside it: random intercepts for "
                      "rat, rat × region and rat × region × session (tab 12's structure), Session × Region F with both df; the GEE's "
                      "Session × Region (model-based) and Session (robust) beside it.",
            source="Tab 12's tier 1 rows and its GEE terms.")
    rows = []
    for band in BANDS:
        data = []
        for ri, r in enumerate(REGIONS):
            data += FS.power_rows(X.PT, band, ri, FS.region_rats(X.PT, ri))[0]
        df = _frame(data)
        df["rd"] = df["region"] + " " + df["day"]
        t1 = (((X.F.get("tiers") or {}).get(band) or {}).get("t1") or {}).get("terms")
        if not t1:
            t1 = E.terms(E.gee(df, FS.TIER1, "normal"))
        sr = next((t for t in t1 if t["term"] == "Session × Region"), {})
        s = next((t for t in t1 if t["term"] == "Session"), {})
        lm = FS.lmm_terms(df, FS.TIER1, (("Session × Region", ["C(day", "C(region"], ["C(period"]), ("Session", ["C(day"], ["C(period", "C(region"])),
                          {"region": "0 + C(region)", "rd": "0 + C(rd)"})
        rows.append([band.capitalize(), int(df["rat"].nunique()), "%s, %s (%s)" % (chi(sr), fp(sr.get("p")), sr.get("errors", "")),
                     lmm_say(lm.get("Session × Region")), "%s, %s (%s)" % (chi(s), fp(s.get("p")), s.get("errors", "")), lmm_say(lm.get("Session"))])
        R["summary"].append("%s: Session × Region GEE %s, %s; LMM %s. Session (all regions together): GEE %s; LMM %s." % (
            band.capitalize(), chi(sr), fp(sr.get("p")), lmm_say(lm.get("Session × Region")), fp(s.get("p")), lmm_say(lm.get("Session"))))
        for x in data:
            R["csv"].append({"request": "B7", "band": band, "region": REGION_SAY[x["region"]], "rat": "J%d" % x["rat"], "session": DAY_SAY(x["day"]),
                             "period": x["period"], "dB": x["y"]})
    R["tables"].append(table("Session × Region, both ways", ["Band", "n", "GEE Session × Region", "LMM Session × Region", "GEE Session", "LMM Session"], rows))
    R["n"] = "n = 6 rats (PER 5)"
    R["reading"] = ["A Session × Region interaction with no Session main effect supports the argument that the session shifts aren't implant-wide drift."]
    return R


# --------------------------------------------------------------------------
# B8. Ipsilateral and contralateral wire pairs
# --------------------------------------------------------------------------
def b8(X):
    R = rec("B8", ran="Only wire pairs valid in both sessions; band coherence (cue pair) for ipsilateral pairs only, contralateral only, both "
                      "with each wire pair weighted equally, and the geometric mean (mean of log coherence); Session on each (Gamma GEE, "
                      "robust errors), BH across the 10 pairs within each kind and band. Granger, each direction, for the six corrected "
                      "pair-bands, ipsilateral and contralateral apart.",
            source="Tab 11's pooled spectra, wire pair by wire pair; tab 12's pooled Granger matrices.")
    wi = E.WINS.index("pair")
    ipsi = np.array([c[2] == "ipsi" for c in E.COMBOS])
    KINDS = (("ipsi", "Ipsilateral"), ("contra", "Contralateral"), ("both", "Both, equal weight"), ("geo", "Geometric mean"))
    out = {}
    for band in BANDS:
        m = _bins(*BAND_LIM[band])
        res = []
        for p in range(len(E.PAIRS)):
            per = {}
            for (r, d), (a, _m) in X.em.items():
                c = E.coherence(a, "pair")[p]            # (C, NF)
                per[(r, d)] = (E._nanmean(c[:, m], axis=-1), a["nseg"][wi, p] > 0)
            vals = {k: {} for k, _s in KINDS}
            cnt = {"ipsi": 0, "contra": 0}
            for r in X.rats:
                if not all((r, d) in per for d in DAYS):
                    continue
                okb = per[(r, DAYS[0])][1] & per[(r, DAYS[1])][1]
                cnt["ipsi"] += int((okb & ipsi).sum())
                cnt["contra"] += int((okb & ~ipsi).sum())
                for d in DAYS:
                    v = per[(r, d)][0]
                    for k, sel in (("ipsi", okb & ipsi), ("contra", okb & ~ipsi), ("both", okb), ("geo", okb)):
                        if sel.any():
                            vals[k][(r, d)] = float(np.exp(np.mean(np.log(v[sel])))) if k == "geo" else float(np.mean(v[sel]))
            x = {"pair": p, "counts": cnt, "coh": _a2_of(X, band, p)}
            for k, _s in KINDS:
                rats = X.both(vals[k])
                g = safe(lambda: session(_frame(rows_of(vals[k], rats)), "gamma")) if len(rats) >= E.MIN_RATS else {"error": "%d rats" % len(rats)}
                g["n"] = len(rats)
                x[k] = g
                for rr in rats:
                    for d in DAYS:
                        R["csv"].append({"request": "B8", "band": band, "pair": PAIR_SAY[p], "kind": k, "rat": "J%d" % rr, "session": DAY_SAY(d),
                                         "value": vals[k][(rr, d)]})
            res.append(x)
        for k, _s in KINDS:
            bh_put([x[k] for x in res])
        out[band] = res
        cell = lambda g: ("%s, %s, n = %d" % (est(g), fq(g.get("q")), g["n"])) if g.get("est") is not None else "%s (n = %d)" % (g.get("error", ""), g.get("n", 0))   # noqa: E731
        R["tables"].append(table("%s: Late/Early by kind of wire pair (both-session wire pairs only)" % band.capitalize(),
                                 ["Pair", "Current (tab 11)", "Ipsilateral", "Contralateral", "Both, equal weight", "Geometric mean", "Wire pairs (ipsi/contra)"],
                                 [[PAIR_SAY[x["pair"]], "%s, %s" % (est(x["coh"]), fq(x["coh"].get("q")))] + [cell(x[k]) for k, _s in KINDS] +
                                  ["%d/%d" % (x["counts"]["ipsi"], x["counts"]["contra"])] for x in res],
                                 [sig(x["contra"], "q") for x in res],
                                 note="Bold: the contralateral pairs alone change with q < .05 (unlikely to be local volume conduction)."))
        for x in res:
            if sig(x["coh"], "q"):
                R["summary"].append("%s %s (now %s): ipsilateral %s, contralateral %s, both-session pairs %s, geometric %s." % (
                    PAIR_SAY[x["pair"]], band, est(x["coh"]), "%s (%s)" % (est(x["ipsi"]), fq(x["ipsi"].get("q"))),
                    "%s (%s)" % (est(x["contra"]), fq(x["contra"].get("q"))), est(x["both"]), est(x["geo"])))
    # Granger, ipsi and contra apart
    from . import sweep
    gr = []
    items = [g for g in X.F.get("granger") or [] if (g.get("in") or {}).get("fdr")]
    for g in items:
        p, band = g["pair"], g["band"]
        lo, hi = BAND_LIM[band]
        mk = joe.band_mask(FS.GC_FREQS, lo, hi) & (FS.GC_FREQS > 0)
        for kind, sel in (("ipsi", ipsi), ("contra", ~ipsi)):
            vals = {"ab": {}, "ba": {}}
            for r in X.rats:
                if not all((r, d) in X.em for d in DAYS):
                    continue
                okb = (X.em[(r, DAYS[0])][0]["gseg"][p] > 0) & (X.em[(r, DAYS[1])][0]["gseg"][p] > 0) & sel
                if not okb.any():
                    continue
                for d in DAYS:
                    a = X.em[(r, d)][0]
                    S = np.stack([a["gS"][p, c] / a["gseg"][p, c] for c in np.flatnonzero(okb)])
                    try:
                        H, sg, _it = sweep.wilson(S)
                        g12, g21 = sweep.granger(H, sg)
                    except np.linalg.LinAlgError:
                        continue
                    vals["ab"][(r, d)] = float(np.mean(np.mean(g12[:, mk], axis=1)))
                    vals["ba"][(r, d)] = float(np.mean(np.mean(g21[:, mk], axis=1)))
            row = {"pair": p, "band": band, "kind": kind, "a": g["a"], "b": g["b"]}
            for k in ("ab", "ba"):
                rats = X.both(vals[k])
                row[k] = safe(lambda: session(_frame(rows_of(vals[k], rats)), "gamma")) if len(rats) >= E.MIN_RATS else {"error": "%d rats" % len(rats)}
                row[k]["n"] = len(rats)
            gr.append(row)
    R["tables"].append(table("Granger by kind of wire pair (the six corrected pair-bands)", ["Pair", "Band", "Wire pairs", "First → second", "Second → first"],
                             [[PAIR_SAY[x["pair"]], x["band"], x["kind"], ("%s, %s, n = %d" % (est(x["ab"]), fp(x["ab"].get("p")), x["ab"]["n"])) if "est" in x["ab"] else x["ab"].get("error", ""),
                               ("%s, %s, n = %d" % (est(x["ba"]), fp(x["ba"].get("p")), x["ba"]["n"])) if "est" in x["ba"] else x["ba"].get("error", "")] for x in gr]))
    R["n"] = "n per test in the tables (a rat with no wire pair of a kind drops out of that test)"
    R["reading"] = ["If a ratio moves when only both-session wire pairs are kept, the change in wire pairs was contributing to it.",
                    "A change that holds in contralateral pairs alone is unlikely to be local volume conduction, which falls off with distance. This "
                    "helps least for midline pairs such as RSC–ACC, and it doesn't address the reference, which affects both kinds of pair equally.",
                    "A change in only one kind of pair limits the claim to that route."]
    R["data"] = {"coh": out, "granger": gr}
    return R


# --------------------------------------------------------------------------
# B9. Time-resolved windows and trial blocks (exploratory)
# --------------------------------------------------------------------------
def _short(X, k):
    """{(rat, day): ((P,) coherence per band, (5,) power per band, pieces)}
    for 2.048-s window k."""
    out = {}
    for key, (j, _m) in X.jp.items():
        coh = {b: coh_band_custom(j["ssab"][k], j["ssaa"][k], j["ssbb"][k], j["sn"][k], _bins(*BAND_LIM[b])) for b in BANDS}
        pw = {b: power_custom(j["spsd"][k], j["spn"][k], _bins(*BAND_LIM[b])) for b in BANDS}
        n = j["sn"][k]
        out[key] = (coh, pw, float(np.median(n[n > 0])) if (n > 0).any() else 0.0)
    return out


def _halves(X):
    """{(rat, day, half): (coh {band: (P,)}, power-response {band: (5,)})}
    from each trial's own sums: the cue pair's coherence, and the cue pair's
    power minus the baseline's (dB)."""
    out = {}
    wp, wb = JP.WF.index("pair"), JP.WF.index("base10")
    for (r, d), (j, meta) in X.jp.items():
        order = np.argsort([t["t"][0] for t in meta["trials"]])
        have = [i for i in order if j["tn"][wp, i].max() > 0]
        h = len(have) // 2
        for half, idx in (("first", have[:h]), ("second", have[h:])):
            if not idx:
                continue
            sab, saa, sbb, n = (j[k][wp][idx].astype(np.complex128 if k == "tsab" else np.float64).sum(axis=0) for k in ("tsab", "tsaa", "tsbb", "tn"))
            coh = {b: coh_band_custom(sab, saa, sbb, n, _bins(*BAND_LIM[b])) for b in BANDS}
            pw = {}
            for b in BANDS:
                mk = _bins(*BAND_LIM[b])
                cue = power_custom(j["tpsd"][wp][idx].astype(float).sum(axis=0), j["tpn"][wp][idx].sum(axis=0), mk)
                base = power_custom(j["tpsd"][wb][idx].astype(float).sum(axis=0), j["tpn"][wb][idx].sum(axis=0), mk)
                pw[b] = cue - base
            out[(r, d, half)] = (coh, pw)
    return out


def b9(X):
    R = rec("B9", ran="Exploratory. The power and pooled-coherence pipelines on 2.048-s windows (three 1.024-s pieces, half overlapping, cut "
                      "from the notched 10-s window): the last 2 s of baseline, the first and last 2 s of cue 1 and the first 2 s of cue 2 "
                      "(the cues are back to back, so there is no gap window). Power: Session × (window vs baseline), 1 df, robust, BH across "
                      "the 10 per-region models within each window. Coherence: Session in each window, BH across the 10 pairs. Trial blocks: "
                      "each session's trials split into halves by time; Early first half vs Early second half, and Early second half vs Late, "
                      "on the cue response in power (cue pair minus baseline, dB) and on cue-pair coherence (1 df each, robust, BH across "
                      "regions or pairs).",
            source="This tab's pass over the recordings (each trial's sums, and the 2-s windows).")
    K = {key: i for i, (key, _s, _e, _say) in enumerate(JP.SHORT)}
    S = {key: _short(X, i) for key, i in K.items()}
    # pieces and floors
    R["tables"].append(table("Pieces per 2-s window (median wire pair) and the pooled noise floor", ["Rat", "Session"] + [s for _k, _s, _e, s in JP.SHORT],
                             [["J%d" % r, DAY_SAY(d)] + ["%d (floor %s)" % (S[k][(r, d)][2], num(1.0 / keff(S[k][(r, d)][2]), 3)) if S[k][(r, d)][2] else ""
                                                       for k, _s, _e, _say in JP.SHORT] for (r, d) in sorted(X.jp)]))
    # power: window against the last 2 s of baseline
    pres = []
    for key, _src, _e, say in JP.SHORT[1:]:
        fam = []
        for band in BANDS:
            for ri, r in enumerate(REGIONS):
                rows = []
                for rat in X.rats:
                    for d in DAYS:
                        for w in ("b_last", key):
                            v = S[w].get((rat, d))
                            if v is not None and np.isfinite(v[1][band][ri]):
                                rows.append({"rat": rat, "day": d, "period": w, "y": float(v[1][band][ri])})
                df = _frame(rows)
                ok = df.groupby("rat").size() == 4 if len(df) else []
                df = df[df["rat"].isin(list(ok[ok].index))] if len(df) else df
                f = "y ~ C(day, Treatment('Precon1')) * C(period, Treatment('b_last'))"
                g = safe(lambda: E.interaction(df, f, ["Precon4", key], "normal")) if len(df) else {"error": "no rows"}
                if "diff" in g:
                    g.update(est=g["diff"], kind="diff")
                g.update(region=r, band=band, window=say, n=int(df["rat"].nunique()) if len(df) else 0)
                fam.append(g)
                for row in rows:
                    R["csv"].append({"request": "B9", "kind": "power", "window": row["period"], "band": band, "unit": REGION_SAY[r],
                                     "rat": "J%d" % row["rat"], "session": DAY_SAY(row["day"]), "value": row["y"]})
        bh_put(fam)
        pres += fam
    R["tables"].append(table("Power: Session × (2-s window vs last 2 s of baseline), dB", ["Window", "Band", "Region", "n", "Difference of differences [95% CI]", "p", "q"],
                             [[g["window"], g["band"], REGION_SAY[g["region"]], g["n"], est(g, "dB"), fp(g.get("p")), fq(g.get("q"))] for g in pres],
                             [sig(g, "q") for g in pres]))
    cres = []
    for key, _src, _e, say in JP.SHORT:
        for band in BANDS:
            fam = []
            for p in range(len(E.PAIRS)):
                vals = {k: float(v[0][band][p]) for k, v in S[key].items()}
                rats = X.both(vals)
                g = safe(lambda: session(_frame(rows_of(vals, rats)), "gamma")) if len(rats) >= E.MIN_RATS else {"error": "too few rats"}
                g.update(pair=p, band=band, window=say, n=len(rats))
                fam.append(g)
                for rr in rats:
                    for d in DAYS:
                        R["csv"].append({"request": "B9", "kind": "coherence", "window": key, "band": band, "unit": PAIR_SAY[p], "rat": "J%d" % rr,
                                         "session": DAY_SAY(d), "value": vals[(rr, d)]})
            bh_put(fam)
            cres += fam
    R["tables"].append(table("Coherence: Late/Early in each 2-s window", ["Window", "Band", "Pair", "n", "Late/Early [95% CI]", "p", "q"],
                             [[g["window"], g["band"], PAIR_SAY[g["pair"]], g["n"], est(g), fp(g.get("p")), fq(g.get("q"))] for g in cres],
                             [sig(g, "q") for g in cres]))
    # trial blocks
    H = _halves(X)
    bres = []
    for test, (ga, gb), say in (("halves", (("Precon1", "first"), ("Precon1", "second")), "Early 2nd half vs Early 1st half"),
                                ("on", (("Precon1", "second"), ("Precon4", "all")), "Late (all trials) vs Early 2nd half")):
        for band in BANDS:
            for kind, units in (("power", REGIONS), ("coherence", list(range(len(E.PAIRS))))):
                fam = []
                for ui, u in enumerate(units):
                    rows = []
                    for rat in X.rats:
                        cells = []
                        for (d, h) in (ga, gb):
                            if h == "all":
                                v = X.PT["band"]["cue1"][band].get((rat, d)) if kind == "power" else X.T["band"]["pair"][band].get((rat, d))
                                if kind == "power":
                                    # the whole session's cue response, as the halves are: the cue pair minus the baseline
                                    j = X.jp.get((rat, d))
                                    if j is None:
                                        v = None
                                    else:
                                        jj = j[0]
                                        mk = _bins(*BAND_LIM[band])
                                        v = power_custom(jj["tpsd"][JP.WF.index("pair")].astype(float).sum(axis=0), jj["tpn"][JP.WF.index("pair")].sum(axis=0), mk) - \
                                            power_custom(jj["tpsd"][JP.WF.index("base10")].astype(float).sum(axis=0), jj["tpn"][JP.WF.index("base10")].sum(axis=0), mk)
                            else:
                                hv = H.get((rat, d, h))
                                v = None if hv is None else (hv[1][band] if kind == "power" else hv[0][band])
                            cells.append(None if v is None or not np.isfinite(v[ui]) else float(v[ui]))
                        if all(c is not None for c in cells):
                            rows += [{"rat": rat, "grp": "a", "y": cells[0]}, {"rat": rat, "grp": "b", "y": cells[1]}]
                    df = _frame(rows)
                    fam_ = "normal" if kind == "power" else "gamma"
                    g = safe(lambda: coef(E.gee(df, "y ~ C(grp, Treatment('a'))", fam_), ["T.b"], fam_)) if len(rows) >= 2 * E.MIN_RATS else {"error": "too few rats"}
                    g.update(test=say, band=band, kind=kind, unit=REGION_SAY[u] if kind == "power" else PAIR_SAY[u], n=len(rows) // 2)
                    fam.append(g)
                    for row in rows:
                        R["csv"].append({"request": "B9", "kind": "block " + kind, "test": test, "band": band, "unit": g["unit"], "rat": "J%d" % row["rat"],
                                         "group": say.split(" vs ")[0] if row["grp"] == "b" else say.split(" vs ")[1], "value": row["y"]})
                bh_put(fam)
                bres += fam
    R["tables"].append(table("Trial blocks", ["Test", "Band", "Measure", "Region or pair", "n", "Estimate [95% CI]", "p", "q"],
                             [[g["test"], g["band"], g["kind"], g["unit"], g["n"], est(g, "dB" if g["kind"] == "power" else ""), fp(g.get("p")), fq(g.get("q"))]
                              for g in bres], [sig(g, "q") for g in bres],
                             note="Power: the cue response (cue pair minus baseline, dB), the difference between the two groups of trials. "
                                  "Coherence: the ratio. q across the 5 regions or 10 pairs within a test and band."))
    hits = [g for g in pres + cres + bres if sig(g, "q")]
    for g in hits:
        R["summary"].append("%s: %s %s %s, %s, %s." % (g.get("window") or g.get("test"), g["band"], g.get("unit") or (REGION_SAY[g["region"]] if "region" in g else PAIR_SAY[g["pair"]]),
                                                       est(g, "dB" if (g.get("kind") == "power" or "region" in g) else ""), fp(g.get("p")), fq(g.get("q"))))
    if not hits:
        R["summary"].append("Nothing passes after correction in the 2-s windows or the trial blocks.")
    if hits:
        R["notes"].append("Granger and the modulation index in the windows or blocks that change were not run: tab 12's Granger matrices "
                          "cover only the whole cue pair. Needs a decision if they are wanted.")
    R["n"] = "n per test in the tables"
    R["reading"] = ["A change confined to one window that the full periods miss means the full-period nulls understate the effect. A change at "
                    "the end of cue 1 is the most direct sign of an anticipatory, S–S change. A difference between the halves of Precon 1 means "
                    "learning was already under way within Precon 1. Labelled exploratory: it adds many tests."]
    R["data"] = {"power": pres, "coh": cres, "blocks": bres}
    return R


# --------------------------------------------------------------------------
# B10. Sub-band splits
# --------------------------------------------------------------------------
def b10(X):
    R = rec("B10", ran="Gamma split into low (30–56 Hz) and high (64–90 Hz), which also leaves out 59–61 Hz. In each: the per-region power "
                       "model (Session × Period and its three contrasts, normal GEE; BH across the 5 regions) and cue-pair coherence "
                       "(Session, Gamma GEE, BH across the 10 pairs). Theta is not split: A5 ran.",
            source="Tab 11's pooled spectra and tab 12's power spectra, averaged over the sub-band's bins.")
    out = {}
    for key, lo, hi, say in JP.SUB:
        mk = _bins(lo, hi)
        pw = []
        for ri, r in enumerate(REGIONS):
            rows = []
            for rat in X.rats:
                cells = {}
                for d in DAYS:
                    for w in E.PERIODS:
                        P = X.PT["psd"][w].get((rat, d))
                        if P is None:
                            continue
                        side = FS._db(E._nanmean(P[:, mk], axis=1))
                        cells[(d, w)] = float(E._nanmean(side[FS.region_sides(r)], axis=0))
                if len(cells) == 6 and all(np.isfinite(v) for v in cells.values()):
                    rows += [{"rat": rat, "day": d, "period": E.PERIOD_CODE[w], "y": v} for (d, w), v in cells.items()]
            df = _frame(rows)
            x = {"region": r, "n": int(df["rat"].nunique()) if len(df) else 0,
                 "sp": safe(lambda: term(df, SP_SUM, "normal", "Session × Period")) if len(df) else {"error": "no rows"},
                 "c": {k: (dict(v, est=v.get("diff"), kind="diff") if "diff" in v else v) for k, v in (E.period_contrasts(df, "normal") if len(df) else {}).items()}}
            pw.append(x)
            for row in rows:
                R["csv"].append({"request": "B10", "kind": "power", "sub_band": key, "unit": REGION_SAY[r], "rat": "J%d" % row["rat"],
                                 "session": DAY_SAY(row["day"]), "period": row["period"], "value": row["y"]})
        bh_put([x["sp"] for x in pw])
        for a, b, _s in CONTRASTS:
            bh_put([x["c"].get(E.contrast_key(a, b)) for x in pw])
        co = []
        for p in range(len(E.PAIRS)):
            vals = {k: float(E._nanmean(E.rat_spectrum(a, "pair")[p][mk], axis=-1)) for k, (a, _m) in X.em.items()}
            rats = X.both(vals)
            g = safe(lambda: session(_frame(rows_of(vals, rats)), "gamma"))
            g.update(pair=p, n=len(rats))
            co.append(g)
            for rr in rats:
                for d in DAYS:
                    R["csv"].append({"request": "B10", "kind": "coherence", "sub_band": key, "unit": PAIR_SAY[p], "rat": "J%d" % rr,
                                     "session": DAY_SAY(d), "value": vals[(rr, d)]})
        bh_put(co)
        out[key] = {"power": pw, "coh": co}
        R["tables"].append(table("%s: power, Session × Period and contrasts (dB)" % say, ["Region", "n", "Session × Period", "Session × (cue 1 vs baseline)",
                                                                                         "Session × (cue 2 vs baseline)", "Session × (cue 2 vs cue 1)"],
                                 [[REGION_SAY[x["region"]], x["n"], "%s, %s, %s" % (chi(x["sp"]), fp(x["sp"].get("p")), fq(x["sp"].get("q")))] +
                                  ["%s, %s, %s" % (est(x["c"].get(E.contrast_key(a, b)) or {}, "dB"), fp((x["c"].get(E.contrast_key(a, b)) or {}).get("p")),
                                                   fq((x["c"].get(E.contrast_key(a, b)) or {}).get("q"))) for a, b, _s in CONTRASTS] for x in pw],
                                 [sig(x["sp"], "q") or any(sig(v, "q") for v in x["c"].values()) for x in pw]))
        R["tables"].append(table("%s: coherence, Late/Early" % say, ["Pair", "n", "Late/Early [95% CI]", "p", "q", "Full gamma (tab 11)"],
                                 [[PAIR_SAY[g["pair"]], g["n"], est(g), fp(g.get("p")), fq(g.get("q")), est(_a2_of(X, "gamma", g["pair"]))] for g in co],
                                 [sig(g, "q") for g in co]))
    for p in range(len(E.PAIRS)):
        lo_, hi_ = out["low"]["coh"][p], out["high"]["coh"][p]
        if sig(lo_, "q") or sig(hi_, "q"):
            R["summary"].append("%s coherence: low gamma %s (%s), high gamma %s (%s); full band %s." % (
                PAIR_SAY[p], est(lo_), fq(lo_.get("q")), est(hi_), fq(hi_.get("q")), est(_a2_of(X, "gamma", p))))
    for key, _lo, _hi, say in JP.SUB:
        for x in out[key]["power"]:
            if sig(x["sp"], "q") or any(sig(v, "q") for v in x["c"].values()):
                R["summary"].append("%s power in %s changes in %s." % (REGION_SAY[x["region"]], say.lower(), ", ".join(
                    ([("Session × Period") if sig(x["sp"], "q") else ""] + ["Session × (%s)" % s.lower() for a, b, s in CONTRASTS if sig(x["c"].get(E.contrast_key(a, b)), "q")])).strip(", ")))
    if not R["summary"]:
        R["summary"].append("Nothing changes after correction in either sub-band.")
    R["n"] = n_say([g["n"] for k in out for g in out[k]["coh"]])
    R["reading"] = ["A change in one sub-band only, or opposite changes in the two, means the full-band null understates change. A high-gamma "
                    "coherence change that tracks 100–200 Hz power is likely EMG (not measured here), and low gamma is then the cleaner measure."]
    R["data"] = out
    return R


# --------------------------------------------------------------------------
# C2. Granger follow-ups (the cheap ones)
# --------------------------------------------------------------------------
def _gc(a, p, mk, reverse=False):
    """(a->b, b->a, zero-lag, total, zero-lag in time) over the valid wire
    pairs: Geweke's decomposition of the pooled matrix, every term from the
    factorisation's own spectra (H Sigma H^H) so that total = a->b + b->a +
    zero-lag at every frequency (band means); and the time-domain zero-lag
    term ln(Sigma11 Sigma22 / |Sigma|), never negative. reverse = the
    time-reversed signals (the conjugate matrix)."""
    from . import sweep
    n = a["gseg"][p]
    valid = [c for c in range(len(E.COMBOS)) if n[c] > 0]
    if not valid:
        return None
    S = np.stack([a["gS"][p, c] / n[c] for c in valid])
    if reverse:
        S = np.conj(S)
    H, sg, _it = sweep.wilson(S)
    g12, g21 = sweep.granger(H, sg)
    Sf = H @ sg[:, None] @ np.conj(np.swapaxes(H, -1, -2))
    s11, s22, s12 = np.real(Sf[..., 0, 0]), np.real(Sf[..., 1, 1]), Sf[..., 0, 1]
    det = s11 * s22 - np.abs(s12) ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        tot = np.log(s11 * s22 / det)
    inst = tot - g12 - g21
    sd = np.real(sg)
    tinst = np.log(sd[:, 0, 0] * sd[:, 1, 1] / (sd[:, 0, 0] * sd[:, 1, 1] - sd[:, 0, 1] * sd[:, 1, 0]))
    f = lambda z: float(np.mean(np.mean(z[:, mk], axis=1)))   # noqa: E731
    return f(g12), f(g21), f(inst), f(tot), float(np.mean(tinst))


def c2(X):
    R = rec("C2", ran="On the six corrected pair-bands (tab 12's main run, reused): the instantaneous (zero-lag) term of the same Geweke "
                      "decomposition, Session on it (Gamma GEE, BH across the six); time-reversed Granger (the conjugate spectral matrix) "
                      "for the Direction effects; and q for one family of 12 tests (both directions × six pair-bands) beside tab 12's "
                      "per-direction q. Conditional Granger was not run (Shahriar, 2026-11-06).",
            source="Tab 12's Granger results and its pooled cross-spectral matrices (250 Hz).")
    items = [g for g in X.F.get("granger") or [] if (g.get("in") or {}).get("fdr") and "error" not in g]
    fam12 = []
    for g in items:
        for k in ("ab", "ba"):
            fam12.append(g[k])
    q12 = E.bh([x.get("p") for x in fam12])
    rows, res = [], []
    for g in items:
        p, band = g["pair"], g["band"]
        lo, hi = BAND_LIM[band]
        mk = joe.band_mask(FS.GC_FREQS, lo, hi) & (FS.GC_FREQS > 0)
        vals = {"inst": {}, "tot": {}, "ab": {}, "ba": {}, "rab": {}, "rba": {}, "tinst": {}}
        for k, (a, _m) in X.em.items():
            try:
                o = _gc(a, p, mk)
                rv = _gc(a, p, mk, reverse=True)
            except np.linalg.LinAlgError:
                continue
            if o is None:
                continue
            vals["ab"][k], vals["ba"][k], vals["inst"][k], vals["tot"][k], vals["tinst"][k] = o
            vals["rab"][k], vals["rba"][k] = rv[0], rv[1]
        rats = X.both(vals["tinst"])
        x = {"pair": p, "band": band, "a": g["a"], "b": g["b"], "n": len(rats), "ab": g["ab"], "ba": g["ba"], "sd": g.get("sd")}
        # the zero-lag term tested is the time-domain one (never negative, so a Gamma GEE fits it); the band's share is descriptive
        x["inst"] = safe(lambda: session(_frame(rows_of(vals["tinst"], rats)), "gamma"))
        for tag, ka, kb in (("dir", "ab", "ba"), ("rdir", "rab", "rba")):
            rows_ = [{"rat": r, "day": d, "dir": "a to b", "y": vals[ka][(r, d)]} for r in rats for d in DAYS] + \
                    [{"rat": r, "day": d, "dir": "b to a", "y": vals[kb][(r, d)]} for r in rats for d in DAYS]
            x[tag] = safe(lambda: coef(E.gee(_frame(rows_), "y ~ C(day, Sum) + C(dir, Treatment('b to a'))", "gamma"), ["a to b"], "gamma"))
        x["share"] = float(np.mean([vals["inst"][(r, d)] / vals["tot"][(r, d)] for r in rats for d in DAYS if vals["tot"][(r, d)] > 0]))
        res.append(x)
        for r in rats:
            for d in DAYS:
                R["csv"].append(dict({"request": "C2", "pair": PAIR_SAY[p], "band": band, "rat": "J%d" % r, "session": DAY_SAY(d)},
                                     **{k: vals[k][(r, d)] for k in vals}))
    bh_put([x["inst"] for x in res])
    i = 0
    for x in res:
        x["ab"] = dict(x["ab"], q12=q12[i])
        x["ba"] = dict(x["ba"], q12=q12[i + 1])
        i += 2
    lab = lambda x, k: ("%s → %s" % (x["a"], x["b"])) if k == "ab" else ("%s → %s" % (x["b"], x["a"]))   # noqa: E731
    R["tables"].append(table("Late/Early each way, with q in one family of 12", ["Pair (band)", "Direction", "Late/Early", "p", "q (6, tab 12)", "q (12)"],
                             [["%s (%s)" % (PAIR_SAY[x["pair"]], x["band"]), lab(x, k), "×%s" % num(x[k].get("ratio")), fp(x[k].get("p")),
                               fq(x[k].get("q")), fq(x[k].get("q12"))] for x in res for k in ("ab", "ba")],
                             [sig({"p": x[k].get("p"), "q": x[k].get("q12")}, "q") for x in res for k in ("ab", "ba")]))
    R["tables"].append(table("The zero-lag (instantaneous) term", ["Pair (band)", "n", "Its share of the band's total interdependence",
                                                                   "Zero-lag term (time domain), Late/Early [95% CI]", "p", "q (6)"],
                             [["%s (%s)" % (PAIR_SAY[x["pair"]], x["band"]), x["n"], "%d%%" % round(100 * x["share"]), est(x["inst"]),
                               fp(x["inst"].get("p")), fq(x["inst"].get("q"))] for x in res], [sig(x["inst"], "q") for x in res],
                             note="Total interdependence = first → second + second → first + the instantaneous term (Geweke 1982), each "
                                  "from the factorised spectra; the share is the band's mean over rats and sessions (descriptive; in "
                                  "the frequency domain the zero-lag part can dip below zero at some frequencies). Tested: the time-domain "
                                  "zero-lag term ln(Σ11·Σ22 / |Σ|), which never does. A large zero-lag share is what volume conduction "
                                  "or a shared reference would leave."))
    R["tables"].append(table("Direction, forwards and time-reversed (sessions pooled)", ["Pair (band)", "First → second over second → first",
                                                                                        "p", "Time-reversed", "p", "Reading"],
                             [["%s (%s)" % (PAIR_SAY[x["pair"]], x["band"]), est(x["dir"]), fp(x["dir"].get("p")), est(x["rdir"]), fp(x["rdir"].get("p")),
                               ("flips: consistent with a real lead" if (x["dir"].get("est", 1) > 1) != (x["rdir"].get("est", 1) > 1) and sig(x["dir"]) else
                                "does not flip: the asymmetry survives reversal, so it is likely the cleaner signal looking like the leader" if sig(x["dir"]) else
                                "no direction effect")] for x in res]))
    for x in res:
        R["summary"].append("%s %s: zero-lag share %d%%, Late/Early %s (%s); direction %s, time-reversed %s." % (
            PAIR_SAY[x["pair"]], x["band"], round(100 * x["share"]), est(x["inst"]), fq(x["inst"].get("q")), est(x["dir"]), est(x["rdir"])))
    R["notes"].append("Name the effect in each sensitivity paragraph: done in every robustness line of this tab.")
    R["notes"].append("Conditional (multivariate) Granger: not run (Shahriar, 2026-11-06).")
    R["n"] = n_say([x["n"] for x in res])
    R["reading"] = ["Granger comes from the same cross-spectral matrix as coherence, so it inherits every coherence caveat. A Direction effect "
                    "that keeps its sign after time reversal is more likely a signal-to-noise difference than a lead."]
    R["data"] = res
    return R


# --------------------------------------------------------------------------
# C3. Modulation index (tab 12's, as it stands)
# --------------------------------------------------------------------------
def c3(X):
    R = rec("C3", ran="Tab 12's theta–gamma modulation index (Tort et al. 2010) within each region of the pairs whose coherence changed, as it "
                      "stands: theta phase 5–12 Hz, gamma amplitude 30–90 Hz, pooled over trials, Late vs Early (Gamma GEE). Not rebuilt "
                      "with low and high gamma apart or against shuffled surrogates (Shahriar, 2026-11-06).",
            source="Tab 12, set 'Without J3 and J4'.")
    rows = []
    for x in X.F.get("pac") or []:
        le = x.get("le") or {}
        rb = next((r for r in X.F.get("robust") or [] if r.get("kind") == "pac" and REGION_SAY[x["region"]] in (r.get("name") or "")), None)
        rows.append([REGION_SAY[x["region"]], len(x.get("rats") or []), "×%s" % num(le.get("ratio")), fp(le.get("p")), fq(le.get("q")),
                     ("%s; LMM %s" % ("leave-one-out holds" if rb.get("survives") else "leave-one-out fails without J%s" % (rb.get("worst") or {}).get("rat"),
                                      lmm_say(rb.get("lmm")))) if rb else ""])
        R["summary"].append("%s: MI Late/Early ×%s, %s%s." % (REGION_SAY[x["region"]], num(le.get("ratio")), fp(le.get("p")), (", " + fq(le["q"])) if le.get("q") is not None else ""))
    R["tables"].append(table("Theta–gamma MI, Late/Early", ["Region", "n", "Late/Early", "p", "q", "Robustness (tab 12)"], rows))
    R["notes"].append("Low/high gamma and shuffle-normalised MI: not run (Shahriar, 2026-11-06).")
    R["n"] = n_say([len(x.get("rats") or []) for x in X.F.get("pac") or []] or [0])
    return R


# --------------------------------------------------------------------------
# C4. H2: paired vs unpaired cues
# --------------------------------------------------------------------------
def c4(X):
    R = rec("C4", ran="For each rat, session and region pair: the coherence spectrum in each cue of each of the rat's two cue pairs (pooled "
                      "over that pair's trials); similarity = Pearson r across the band's bins, Fisher z. Paired: cue 1 and cue 2 of the "
                      "same pair; unpaired: cue 1 of one pair against cue 2 of the other (matched in serial position and exposure). "
                      "Session × Pairing (normal GEE, 1 df, robust), BH across the 10 pairs; leave-one-out and an LMM for p < .05.",
            source="This tab's pass over the recordings (each trial's sums, with its cue pair).")
    w1, w2 = JP.WF.index("cue1"), JP.WF.index("cue2")
    out = {}
    for band in BANDS:
        bins = E.bins_of(band)
        res = []
        for p in range(len(E.PAIRS)):
            vals = {}
            for (r, d), (j, meta) in X.jp.items():
                labs = sorted({t["label"] for t in meta["trials"]})
                if len(labs) != 2:
                    continue
                spec = {}
                for li, lab in enumerate(labs):
                    idx = [i for i, t in enumerate(meta["trials"]) if t["label"] == lab]
                    for wn, w in (("c1", w1), ("c2", w2)):
                        sab = j["tsab"][w, idx, p].astype(np.complex128).sum(axis=0)
                        saa = j["tsaa"][w, idx, p].astype(float).sum(axis=0)
                        sbb = j["tsbb"][w, idx, p].astype(float).sum(axis=0)
                        n = j["tn"][w, idx, p].sum(axis=0)
                        with np.errstate(invalid="ignore", divide="ignore"):
                            c = np.abs(sab) ** 2 / (saa * sbb)
                        c[n == 0] = np.nan
                        sp = E._nanmean(c, axis=0)
                        spec[(li, wn)] = np.array([E._nanmean(sp[mm], axis=-1) for _f, mm in bins])
                z = lambda a, b: float(np.arctanh(np.clip(np.corrcoef(a, b)[0, 1], -0.999999, 0.999999)))   # noqa: E731
                if any(not np.all(np.isfinite(v)) for v in spec.values()):
                    continue
                vals[(r, d, "paired")] = (z(spec[(0, "c1")], spec[(0, "c2")]) + z(spec[(1, "c1")], spec[(1, "c2")])) / 2
                vals[(r, d, "unpaired")] = (z(spec[(0, "c1")], spec[(1, "c2")]) + z(spec[(1, "c1")], spec[(0, "c2")])) / 2
            rats = [r for r in X.rats if all((r, d, k) in vals for d in DAYS for k in ("paired", "unpaired"))]
            rows = [{"rat": r, "day": d, "pairing": k, "y": vals[(r, d, k)]} for r in rats for d in DAYS for k in ("paired", "unpaired")]
            df = _frame(rows)
            f = "y ~ C(day, Treatment('Precon1')) * C(pairing, Treatment('unpaired'))"
            fit = lambda d_: E.interaction(d_, f, ["Precon4", "paired"], "normal")   # noqa: E731
            g = safe(lambda: fit(df)) if len(rats) >= E.MIN_RATS else {"error": "too few rats"}
            if "diff" in g:
                g.update(est=g["diff"], kind="diff")
            g.update(pair=p, n=len(rats), mean={d: {k: float(np.mean([vals[(r, d, k)] for r in rats])) if rats else float("nan")
                                                   for k in ("paired", "unpaired")} for d in DAYS})
            g["_df"] = df
            res.append(g)
            for row in rows:
                R["csv"].append({"request": "C4", "band": band, "pair": PAIR_SAY[p], "rat": "J%d" % row["rat"], "session": DAY_SAY(row["day"]),
                                 "pairing": row["pairing"], "fisher_z": row["y"]})
        bh_put(res)
        for g in res:
            if sig(g):
                g["robust"] = robust(g["_df"], lambda d_: E.interaction(d_, "y ~ C(day, Treatment('Precon1')) * C(pairing, Treatment('unpaired'))",
                                                                       ["Precon4", "paired"], "normal"),
                                     "y ~ C(day, Treatment('Precon1')) * C(pairing, Treatment('unpaired'))", ["Precon4", "paired"], False)
                R["robust"].append("%s %s, Session × Pairing: %s" % (PAIR_SAY[g["pair"]], band, rob_say(g["robust"])))
            g.pop("_df", None)
        out[band] = res
        R["tables"].append(table("%s: Session × Pairing (Fisher z of the similarity)" % band.capitalize(),
                                 ["Pair", "n", "Early: paired / unpaired", "Late: paired / unpaired", "Session × Pairing [95% CI]", "p", "q"],
                                 [[PAIR_SAY[g["pair"]], g["n"], "%s / %s" % (num(g["mean"]["Precon1"]["paired"]), num(g["mean"]["Precon1"]["unpaired"])),
                                   "%s / %s" % (num(g["mean"]["Precon4"]["paired"]), num(g["mean"]["Precon4"]["unpaired"])), est(g), fp(g.get("p")),
                                   fq(g.get("q"))] for g in res], [sig(g, "q") for g in res],
                                 note="Session × Pairing: (Late paired − Late unpaired) − (Early paired − Early unpaired), in Fisher z. H2 predicts "
                                      "a positive value: the two cues of a pair grow more alike than cues from different pairs."))
    hits = [(b, g) for b in BANDS for g in out[b] if sig(g, "q")]
    nom = [(b, g) for b in BANDS for g in out[b] if sig(g) and not sig(g, "q")]
    R["summary"].append(("Session × Pairing passes after correction in %s." % "; ".join("%s %s (%s)" % (PAIR_SAY[g["pair"]], b, est(g)) for b, g in hits)) if hits else
                        "No pair passes after correction%s." % ((" (nominal: %s)" % "; ".join("%s %s, %s, %s" % (PAIR_SAY[g["pair"]], b, est(g), fp(g["p"])) for b, g in nom)) if nom else ""))
    R["n"] = n_say([g["n"] for b in BANDS for g in out[b]])
    R["reading"] = ["Every rat heard both cue pairs in every session (Confirmations), so the unpaired comparison exists for every rat."]
    R["data"] = out
    return R


# --------------------------------------------------------------------------
# C5. SPC test behavior (the SPSS results as they stand)
# --------------------------------------------------------------------------
def c5(X):
    from . import paths
    R = rec("C5", ran="The cohort's SPC behavior as already analysed in SPSS (repeated-measures ANOVAs on elevation ratios), copied in as it "
                      "stands, from 'Ephys behavior ANOVA results.docx'. Not recomputed.",
            source="Ephys behavior ANOVA results.docx (repo root): the five .spv files it names.")
    path = os.path.join(paths.repo_root(), "Ephys behavior ANOVA results.docx") if hasattr(paths, "repo_root") else ""
    if not path or not os.path.isfile(path):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "Ephys behavior ANOVA results.docx")
    lines = []
    try:
        import docx
        D = docx.Document(path)
        lines = [p.text.strip() for p in D.paragraphs if p.text.strip()]
    except Exception as exc:                                 # noqa: BLE001
        R["status"] = "Failed"
        R["summary"].append("The behavior document could not be read (%s)." % exc)
        return R
    blocks, cur = [], None
    for t in lines[1:]:
        if t[:2].rstrip(".").isdigit() and t[1:3].startswith("."):
            cur = {"title": t, "lines": []}
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append(t)
        else:
            R["notes"].append(t)
    for b in blocks:
        R["tables"].append(table(b["title"], ["Result"], [[t] for t in b["lines"]]))
    test = next((b for b in blocks if b["title"].startswith("5.")), None)
    if test:
        R["summary"].append("Test, A vs C (the preconditioning test): %s" % next((t for t in test["lines"] if t.startswith("A vs C, t(")), ""))
    R["summary"].append("The per-rat elevation ratios (the .sav files) are not on this machine, so each rat's test responding could not be set "
                        "beside its dHC–OFC change. Needs the .sav files.")
    R["status"] = "Needs decision"
    R["n"] = "n = 5 at test (J9 has no complete test session); n = 6 in preconditioning and conditioning"
    R["reading"] = ["With 6 rats, relating each rat's dHC–OFC change to its test responding is descriptive only."]
    return R


# --------------------------------------------------------------------------
# B6, B12: not run (Shahriar, 2026-11-06)
# --------------------------------------------------------------------------
def b6(X):
    return rec("B6", status="Skipped", ran="Not run (Shahriar, 2026-11-06).",
               summary=["Skipped on purpose. Tracking exists: a Neuralynx video-tracking file (VT1.nvt) for every J6–J11 Early and Late SPC "
                        "session, so speed per period could be measured if wanted."])


def b12(X):
    cp = cue_pairs(X)
    return rec("B12", status="Skipped", ran="Not run (Shahriar, 2026-11-06). Its Confirm items are answered in the Confirmations.",
               summary=["Skipped on purpose. Every rat heard both of its cue pairs in every session (Confirmations), so the split could run."],
               tables=[table("The cue pairs each rat heard", ["Rat", "Cue pair", "Early trials", "Late trials"],
                             [["J%d" % r, lab, v.get("Precon1", 0), v.get("Precon4", 0)] for r in sorted(cp) for lab, v in sorted(cp[r].items())])])


# --------------------------------------------------------------------------
# B11: how the data were cleaned (Shahriar: "our criteria is enough")
# --------------------------------------------------------------------------
def b11(X):
    from . import joepub
    rows = [x for x in joepub.saturation_counts() if x["rat"] not in JP.DROP]
    R = rec("B11", ran="No second automatic screen (Shahriar, 2026-11-06: the lab's criteria are enough). Instead, what the cleaning did to "
                       "J6–J11, counted from the trials' hand exclusions and the wire each window used, with methods text to use as it is.",
            source="Tab 8's day files (the wire each window used) and the curators' hand exclusions; joepub's head-bump counts.")
    pc = lambda a, b: "%.1f%%" % (100.0 * a / b) if b else "0%"   # noqa: E731
    R["tables"].append(table("What the cleaning removed, per rat and session", ["Rat", "Session", "Trials", "Region-windows", "Hand exclusion reached it",
                                                                                 "Used a second wire", "Omitted", "1-s segments omitted"],
                             [["J%d" % x["rat"], DAY_SAY(x["day"]), x["trials"], x["windows"], x["hand"], x["replaced"], x["omitted"],
                               "%d of %d (%s)" % (x["segments_lost"], x["segments"], pc(x["segments_lost"], x["segments"]))] for x in rows],
                             note="A region-window is one region and hemisphere in one 10-s window (baseline, cue 1 or cue 2) of one trial."))
    tw, ts = sum(x["windows"] for x in rows), sum(x["segments"] for x in rows)
    om, sl = sum(x["omitted"] for x in rows), sum(x["segments_lost"] for x in rows)
    by = {d: [x for x in rows if x["day"] == d] for d in DAYS}
    R["summary"].append("Across J6–J11, %s of region-windows were omitted (%s of 1-s segments); Early lost %s and Late %s of their segments." % (
        pc(om, tw), pc(sl, ts), pc(sum(x["segments_lost"] for x in by["Precon1"]), sum(x["segments"] for x in by["Precon1"])),
        pc(sum(x["segments_lost"] for x in by["Precon4"]), sum(x["segments"] for x in by["Precon4"]))))
    R["summary"].append("No segment was rejected by amplitude; nothing was cut out of a window. Hemispheres are averaged in dB (each side's band "
                        "power in dB, then the mean of the sides); coherence averages the valid wire pairs on its own scale, each weighted equally.")
    methods = joepub.saturation_paragraphs(rows) + [
        "Power was computed for each hemisphere separately, converted to decibels, and the two hemispheres of a region were then averaged, so "
        "that a louder hemisphere could not dominate the region's value. Coherence was computed for every valid wire pair and averaged across "
        "wire pairs with equal weight. No further amplitude-based rejection of segments was applied: once wires carrying an artifact had been "
        "excluded by hand or by the saturation rule, every remaining segment of every trial entered the pooled spectra.",
        "Because the number of segments differed between sessions, coherence was always estimated from the segments that remained (pooled "
        "spectra), and the analyses of each session used only that session's own segments; no segment was interpolated or replaced by data "
        "from another window."]
    R["methods"] = methods
    R["n"] = "n = 6 rats, 12 sessions"
    R["data"] = rows
    for x in rows:
        R["csv"].append(dict({"request": "B11", "rat": "J%d" % x["rat"], "session": DAY_SAY(x["day"])}, **{k: v for k, v in x.items() if k not in ("rat", "day")}))
    return R


# --------------------------------------------------------------------------
# The Confirm items, answered from the data and the code
# --------------------------------------------------------------------------
def confirmations(X):
    cp = cue_pairs(X)
    both = all(len(v) == 2 and all(c.get(d, 0) > 0 for c in v.values() for d in DAYS) for v in cp.values())
    gaps, c1, c2 = [], [], []
    for (_r, _d), (_j, meta) in X.jp.items():
        for t in meta["trials"]:
            o, c, f = t["t"]
            c1.append(c - o)
            c2.append(f - c)
    rc = sorted(X.EM.get("reference_check") or [], key=lambda z: (z["rat"], z["day"]))
    return [
        {"id": "B12", "title": "Cue-pair design and counterbalancing for J6–J11",
         "answer": "Every rat heard its two cue pairs in every session%s, and every measure pools both pairs." % (
             ", 8 trials of each (fewer where a trial was lost)" if both else " except where the table shows otherwise"),
         "table": table("Each rat's pairs", ["Rat", "Cue pair", "Early trials", "Late trials"],
                        [["J%d" % r, lab, v.get("Precon1", 0), v.get("Precon4", 0)] for r in sorted(cp) for lab, v in sorted(cp[r].items())])},
        {"id": "B11", "title": "Segment or trial rejection, and hemisphere averaging",
         "answer": "Wires are excluded per 10-s window, by hand (head bumps) and by the saturation rule (0.5% of the digitiser's limit for ≥ 16 "
                   "samples, covering ≥ 0.5% of the window or 50 ms); an excluded wire is replaced by the region's next usable wire, and a "
                   "region with none left is omitted from that window. No segment is rejected by amplitude. Power: each hemisphere in dB, then "
                   "the mean of the two (after the dB conversion). See Data cleaning."},
        {"id": "B8", "title": "The wire pairs and weighting Granger uses",
         "answer": "The same valid wire pairs as coherence (checked: the same pairs in all 16 rat-days), each wire pair's pooled matrix factorised "
                   "on its own, then a plain mean over the valid wire pairs, ipsilateral and contralateral weighted equally."},
        {"id": "B5", "title": "Trial and wire-pair counts, and the cue stimuli",
         "answer": "Counts per rat and session are in B5. The stimuli are four sounds (High tone, Low Tone, Click, Noise), two pairs per rat. "
                   "Whether the click is a train, and its rate, is not in the recordings: needs Joe."},
        {"id": "B9", "title": "Cue timing, and any gap between the cues",
         "answer": "Cue 1 lasted %s–%s s and cue 2 %s–%s s (measured from the rig's own marks in every trial); cue 2 starts as cue 1 ends, so "
                   "there is no gap." % (num(min(c1), 3), num(max(c1), 3), num(min(c2), 3), num(max(c2), 3))},
        {"id": "C2", "title": "The J3/J4 screen", "answer": "Yes: this is the screen that excluded them. Its three values per rat and session:",
         "table": table("The screen (10-s baselines)", ["Rat", "Session", "Coherence at 75–90 Hz", "Rise from 4–8 Hz", "Median |phase| 30–90 Hz"],
                        [["J%d" % x["rat"], DAY_SAY(x["day"]), num(x["hg"]), "+" + num(x["rise"]), "%s°" % num(x["phase"], 0)] for x in rc],
                        [x["rat"] in JP.DROP for x in rc])},
    ]


ORDER = ("A1", "A2", "A3", "C1", "A6", "B1", "B9", "A4", "A5", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B10", "B11", "B12", "C2", "C3", "C4", "C5")
RUN = {"A1": a1, "A2": a2, "A3": a3, "A4": a4, "A5": a5, "A6": a6, "C1": c1, "B1": b1, "B2": b2, "B3": b3, "B4": b4, "B5": b5, "B6": b6,
       "B7": b7, "B8": b8, "B9": b9, "B10": b10, "B11": b11, "B12": b12, "C2": c2, "C3": c3, "C4": c4, "C5": c5}


# --------------------------------------------------------------------------
# One line per request, for the summary table (Joe's tracker)
# --------------------------------------------------------------------------
def _changed(X):
    """The (band, pair) whose cue-pair coherence changes after correction."""
    return [(b, p) for b in BANDS for p in range(len(E.PAIRS)) if sig(_a2_of(X, b, p), "q")]


def _names(xs):
    return ", ".join(xs) if xs else "none"


def line(rid, r, X):
    D = r.get("data")
    ch = _changed(X)
    say = lambda bp: "%s %s" % (PAIR_SAY[bp[1]], bp[0])   # noqa: E731
    try:
        if rid == "A1":
            carried = [say((b, x["pair"])) for b in BANDS for x in D[b] if (b, x["pair"]) in ch and "error" not in x
                       and any(sig(x[t], "q") for t in ("lxy", "lxx", "lyy"))]
            return "%d coherence changes; %s carried by one term after correction (%s)." % (len(ch), len(carried) or "none", _names(carried)) \
                if carried else "%d coherence changes; none is carried by |Sxy|², Sxx or Syy alone after correction." % len(ch)
        if rid == "A2":
            ok = [say((b, x["pair"])) for b in BANDS for x in D[b] if (b, x["pair"]) in ch and "error" not in x and sig(x.get("wpli"), "q")
                  and ((x["wpli"]["est"] < 0) == (x["coh"]["est"] < 1)) and (x["wpli"].get("robust") or {}).get("robust")]
            return "Debiased wPLI confirms %d of %d coherence changes robustly (%s); in the other %d it does not change after correction." % (
                len(ok), len(ch), _names(ok), len(ch) - len(ok))
        if rid == "A3":
            t, g = D["theta"], D["gamma"]
            return "Session × Pair: GEE θ %s, γ %s; LMM θ %s, γ %s; not robust to leaving out a rat; no pair-specific change beyond the node model (θ %s, γ %s)." % (
                fq(t["gee"].get("q")), fq(g["gee"].get("q")), fp(t["lmm"].get("p")), fp(g["lmm"].get("p")),
                fp(t["node"]["gee"].get("p")), fp(g["node"]["gee"].get("p")))
        if rid == "A4":
            B = D["bands"]
            xs = [x for b in BANDS for x in B[b] if (b, x["pair"]) in ch and "error" not in x]
            same = sum((x["tm"].get("est", 1) < 1) == (x["po"]["est"] < 1) for x in xs)
            sq = sum(sig(x["tm"], "q") for x in xs)
            return "Trial-mean coherence moves the same way in %d of %d changed pairs; %d after correction." % (same, len(xs), sq)
        if rid == "A5":
            pw = sum(any(sig(b_["sp"], "q") for b_ in x["bins"]) for b in BANDS for x in D["power"][b])
            co = sum(any(sig(b_["s"], "q") for b_ in x["bins"]) for b in BANDS for x in D["coh"][b])
            return "Per-bin tests: %d region-bands with a significant Session × Period bin; %d pair-bands with significant coherence bins." % (pw, co)
        if rid == "A6":
            rob = [x["label"].split(":")[0] for x in D if (x.get("robust") or {}).get("robust")]
            return "Robust: %s; the other %d are not." % (_names(rob), len(D) - len(rob))
        if rid == "C1":
            cs = [say((b, x["pair"])) for b in BANDS for x in D[b] if x.get("changed")]
            return "Session × Period (or a contrast) passes after correction only in %s; in the other pairs the change does not differ between baseline and the cues." % _names(cs)
        if rid == "B1":
            return " ".join(r["summary"][:1]) if r["summary"] else ""
        if rid == "B2":
            s = [x for x in D["session"] if sig(x, "q")]
            return "Session q < .05 in %s; %d period comparisons pass." % (_names(["%s %s (%s)" % (REGION_SAY[x["region"]], x["band"], est(x, "dB")) for x in s]),
                                                                       sum(sig(g, "q") for g in D["pairwise"]))
        if rid == "B3":
            return "Exploratory: nothing in RSC holds leaving out a rat and in the LMM."
        if rid == "B4":
            return r["summary"][0]
        if rid == "B5":
            return "1–4 Hz: %s; J9 is the kept rat nearest the screen's cut; cue rate needs Joe." % _names([PAIR_SAY[g["pair"]] for g in D["low"] if sig(g, "q")])
        if rid == "B7":
            return " ".join(s.split(" Session (all")[0] for s in r["summary"]) + " No Session main effect in either band."
        if rid == "B8":
            co = [say((b, x["pair"])) for b in BANDS for x in D["coh"][b] if (b, x["pair"]) in ch and sig(x["contra"], "q")]
            return "Contralateral wire pairs alone keep %d of %d changes (%s)." % (len(co), len(ch), _names(co))
        if rid == "B9":
            n = sum(sig(g, "q") for k in ("power", "coh", "blocks") for g in D[k])
            nb = sum(sig(g, "q") for g in D["coh"] if g["window"] == JP.SHORT[0][3])
            return "Exploratory: %d tests pass, %d of them coherence drops already in the last 2 s of baseline." % (n, nb)
        if rid == "B10":
            lo_ = [PAIR_SAY[g["pair"]] for g in D["low"]["coh"] if sig(g, "q")]
            hi_ = [PAIR_SAY[g["pair"]] for g in D["high"]["coh"] if sig(g, "q")]
            return "Low gamma: %s. High gamma: %s." % (_names(lo_), _names(hi_))
        if rid == "C2":
            fl = [say((x["band"], x["pair"])) for x in D if sig(x["dir"]) and (x["dir"]["est"] > 1) != (x["rdir"].get("est", 1) > 1)]
            big = sorted(D, key=lambda x: -x["share"])[:2]
            return "Largest zero-lag shares: %s; the direction effect flips under time reversal in %s." % (
                ", ".join("%s %s %d%%" % (PAIR_SAY[x["pair"]], x["band"], round(100 * x["share"])) for x in big), _names(fl))
        if rid == "C3":
            return "Tab 12's MI as it stands: %d regions, ACC lowest q (%s)." % (len(X.F.get("pac") or []),
                                                                                fq(next((x["le"].get("q") for x in X.F.get("pac") or [] if x["region"] == "ACC"), None)))
        if rid == "C4":
            return r["summary"][0]
        if rid == "C5":
            return "Test A vs C: t(4) = 2.90, p = .044 (SPSS, n = 5); per-rat values not on this machine."
        if rid == "B11":
            return r["summary"][0]
        if rid in ("B6", "B12"):
            return "Skipped on purpose (Shahriar, 2026-11-06)."
    except Exception as exc:                                 # noqa: BLE001
        return "%s" % (r["summary"][0] if r.get("summary") else exc)
    return r["summary"][0] if r.get("summary") else ""
