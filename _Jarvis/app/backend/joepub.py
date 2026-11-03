"""
joepub.py -- Joe's publication set (Shahriar, 2026-11-02): every figure of
tabs 11 and 12, for every set of rats, drawn for a dissertation, with the
words to go under each and the methods behind all of it.

  * The figures are tabs 11 and 12's own drawings (evenmore.py and
    finalstage.py) in their publication pass: no title, no statistic and
    no star inside a figure (the site says what is significant), and every
    panel of a kind on one axis across pairs, regions and sets of rats, so
    two figures can be laid side by side and read on the same scale. Drawn
    twice: the first pass only records each panel's limits, the second
    sets their union and saves a PDF and a PNG to preview.
  * For each figure: a caption, a methods note and a results paragraph,
    in the register of a thesis (third person, past tense), with every
    test behind it (effect, Wald chi-square, p, the Benjamini-Hochberg q,
    and, where it passed, leave-one-rat-out and the mixed model).
  * The methods for the whole analysis, from the recordings to the
    statistics, without Jarvis's names for its steps; as sections for the
    site, a .docx and a .txt.

    python -m backend.joepub        -> GUI_logs/.cache/monolith/joepub/
"""
from __future__ import annotations

import json
import os
import re
import time

import numpy as np

from . import evenmore as E
from . import finalstage as FS
from . import joe

SCHEMA = 1
SET_FILE = {"all": "AllRats", "no3": "NoJ3", "no4": "NoJ4", "no34": "NoJ3J4"}
BAND_LONG = {"theta": "theta (5–12 Hz)", "gamma": "gamma (30–90 Hz)"}
BAND_BINS = {"theta": "0.49-Hz bins from 5 to 12 Hz", "gamma": "2-Hz bins from 30 to 90 Hz, excluding 59–61 Hz"}
REGION_LONG = {"RSC": "retrosplenial cortex (RSC)", "DHC": "dorsal hippocampus (dHC)", "ACC": "anterior cingulate cortex (ACC)",
               "OFC": "orbitofrontal cortex (OFC)", "PER": "perirhinal cortex (PER)"}
CONTRAST_SAY = {"cue1-base10": ("cue 1", "baseline"), "cue2-base10": ("cue 2", "baseline"), "cue2-cue1": ("cue 2", "cue 1")}
FAMILY = {"pairs": "the ten region pairs", "regions10": "the ten per-region models (five regions × two bands)",
          "bands": "the two bands", "regions5": "the five regions", "granger": "the Granger tests", "pac": "the coupling tests"}


def _root(*parts):
    from . import monolith as MO
    return MO._path("joepub", *parts)


# --------------------------------------------------------------------------
# Numbers in words
# --------------------------------------------------------------------------
def fp(p):
    if p is None or not np.isfinite(p):
        return "p not estimable"
    if p < 0.001:
        return "p < .001"
    if p > 0.999:
        return "p > .999"
    return "p = " + ("%.3f" % p).lstrip("0")


def fq(q):
    if q is None or not np.isfinite(q):
        return None
    if q < 0.001:
        return "q < .001"
    if q > 0.999:
        return "q > .999"
    return "q = " + ("%.3f" % q).lstrip("0")


def _chi(t):
    return "Wald χ²(%d) = %.2f" % (int(t.get("df", 1)), t["chi2"])


def _stat(t, q=None, eff=None):
    """'ratio = 2.16, Wald χ²(1) = 42.81, p < .001; FDR q < .001'."""
    q = t.get("q") if q is None else q
    parts = ([eff] if eff else []) + [_chi(t), fp(t["p"])]
    s = ", ".join(parts)
    return s + ("; FDR " + fq(q) if fq(q) else "")


def _cls(p, q):
    if q is not None and q < E.ALPHA:
        return "fdr"
    if p is not None and p < E.ALPHA:
        return "raw"
    return "ns"


def _eff(t):
    if t.get("ratio") is not None:
        return "×%.2f" % t["ratio"]
    if t.get("diff") is not None:
        return "%+.2f dB" % t["diff"]
    return ""


def test_row(name, t, q=None, primary=False, robust=None, family=None):
    """A test as the site lists it."""
    if not t or t.get("p") is None:
        return None
    q = t.get("q") if q is None else q
    return {"name": name, "effect": _eff(t), "stat": "%s, %s" % (_chi(t), fp(t["p"])), "p": t["p"], "q": q,
            "pass": {"fdr": bool(q is not None and q < E.ALPHA), "raw": bool(t["p"] < E.ALPHA)}, "corrected": q is not None,
            "family": family, "errors": "robust" if t.get("errors") == E.ROBUST else "model-based", "primary": primary,
            "robust": _robust(robust)}


def _robust(r):
    if not r:
        return None
    lm = r.get("lmm") or {}
    w = r.get("worst") or {}
    ok_l = lm.get("p") is not None and lm["p"] < E.ALPHA
    return {"loo": "holds" if r.get("survives") else "fails", "worst_rat": w.get("rat"), "worst_p": w.get("p"),
            "lmm": ("F(%d, %d) = %.2f, %s" % (lm["df1"], lm["df2"], lm["F"], fp(lm["p"]))) if lm.get("p") is not None else None,
            "lmm_p": lm.get("p"), "verdict": "solid" if (r.get("survives") and ok_l) else "shaky" if (r.get("survives") or ok_l) else "fragile"}


def s_robust(rb):
    """The robustness checks of one test, as a sentence."""
    if not rb:
        return None
    lmm = "a linear mixed model with a random intercept for rat (%s)" % rb["lmm"] if rb.get("lmm") else None
    loo_ok = rb["loo"] == "holds"
    lmm_ok = rb.get("lmm_p") is not None and rb["lmm_p"] < E.ALPHA
    gone = "when J%s was omitted (%s)" % (rb["worst_rat"], fp(rb["worst_p"])) if rb.get("worst_rat") is not None else "when one rat was omitted"
    if loo_ok and lmm_ok:
        return "The effect remained significant when each rat was omitted in turn and in %s." % lmm
    if loo_ok:
        return "The effect remained significant when each rat was omitted in turn, but not in %s." % (lmm or "a linear mixed model")
    if lmm_ok:
        return "The effect was significant in %s, but not %s." % (lmm, gone)
    return "The effect was not robust: it was not significant %s or in %s." % (gone, lmm or "a linear mixed model")


def s_change(subject, t, q, family, what="in Late than in Early sessions", up_dn=("higher", "lower")):
    """A Late-vs-Early ratio test as a sentence."""
    r = t["ratio"]
    word = up_dn[0] if r > 1 else up_dn[1]
    stat = _stat(t, q, "ratio Late/Early = %.2f" % r)
    c = _cls(t["p"], q)
    if c == "fdr":
        return "%s was %s %s (%s)." % (subject, word, what, stat)
    if c == "raw":
        return "%s was nominally %s %s (%s), but this did not survive correction across %s." % (subject, word, what, stat, family)
    return "%s did not differ between Early and Late sessions (%s)." % (subject, stat)


def s_inter(subject, termsay, t, q, family):
    """An interaction (or any term) as a sentence."""
    stat = "%s, %s, %s" % (termsay, _chi(t), fp(t["p"])) + ("; FDR " + fq(q) if fq(q) else "")
    if t.get("errors") != E.ROBUST:
        stat += "; model-based standard errors"
    c = _cls(t["p"], q)
    if c == "fdr" or (c == "raw" and q is None):
        return "%s differed between Early and Late sessions (%s)." % (subject, stat)
    if c == "raw":
        return "%s differed nominally between Early and Late sessions (%s), but not after correction across %s." % (subject, stat, family)
    return "%s did not differ between Early and Late sessions (%s)." % (subject, stat)


def s_contrast(measure, key, t, q, family, db=False):
    """A planned contrast (Session x (a vs b)) as a sentence."""
    a, b = CONTRAST_SAY[key]
    c = _cls(t["p"], q)
    if db:
        d = t["diff"]
        what = "The %s − %s difference in %s" % (a, b, measure)
        moved = "was %.2f dB %s in Late than in Early sessions" % (abs(d), "larger" if d > 0 else "smaller")
        stat = _stat(t, q, "difference = %+.2f dB" % d)
    else:
        r = t["ratio"]
        what = "The %s/%s ratio of %s" % (a, b, measure)
        moved = "was %.2f times as large in Late as in Early sessions" % r
        stat = _stat(t, q, "ratio of ratios = %.2f" % r)
    if c == "fdr":
        return "%s %s (%s)." % (what, moved, stat)
    if c == "raw":
        return "%s %s (%s), but this did not survive correction across %s." % (what, moved.replace("was ", "was nominally ", 1), stat, family)
    return "%s did not change between Early and Late sessions (%s)." % (what, stat)


def s_term(prefix, name, t, q, family):
    """One term of a larger model as a sentence ('In tier 1, the Session x
    Period term was significant (...)')."""
    stat = "%s, %s" % (_chi(t), fp(t["p"])) + ("; FDR " + fq(q) if fq(q) else "")
    if t.get("errors") != E.ROBUST:
        stat += "; model-based standard errors"
    c = _cls(t["p"], q)
    if c == "fdr" or (c == "raw" and q is None):
        return "%s, the %s term was significant (%s)." % (prefix, name, stat)
    if c == "raw":
        return "%s, the %s term was significant before but not after correction across %s (%s)." % (prefix, name, family, stat)
    return "%s, the %s term was not significant (%s)." % (prefix, name, stat)


def _pair(p):
    return E.PAIR_SAY[p]


# --------------------------------------------------------------------------
# One set of rats: its data, and its figures drawn
# --------------------------------------------------------------------------
def load_set(rs, every, FT):
    days = {k: v for k, v in every.items() if k[0] not in E.RATSET_DROP[rs]}
    EM, FN = E.result(rs), FS.result(rs)
    if not EM or not FN:
        raise RuntimeError("Tabs 11 and 12 have not been worked out for %s." % E.RATSET_SAY[rs])
    return {"rs": rs, "days": days, "EM": EM, "FN": FN, "T": E.tables(days), "PT": FS.power_tables(days), "FT": FT,
            # outside the publication pass: sig() is never true inside it, and the hits decide these
            "G": FS.granger_models(days, EM), "PM": FS.pac_models(days, EM)}


def draw_set(D):
    """Every figure of one set, in the order the site shows them: tab 11's
    by band and phase, then tab 12's. [{group, id, fid, kind, files, ...}]"""
    T, EM, FN, PT = D["T"], D["EM"], D["FN"], D["PT"]
    nq = [False] * len(E.PAIRS)
    out = []

    def add(group, fid, kind, files, **kw):
        out.append(dict({"group": group, "fid": fid, "kind": kind, "files": files}, **kw))
    for B in EM["bands"]:
        band = B["band"]
        bno = 1 if band == "theta" else 2
        p1, p2, p3 = B["phase1"], B["phase2"], B["phase3"]
        for p, st in enumerate(p1["pairs"]):
            if st:
                fid = "%d_1_%02d" % (bno, p + 1)
                add("C-%s-1" % band, fid, "p1pair", E.fig_pair_phase1(T, band, p, st, p1["deltas"], nq, fid), band=band, pair=p)
        fid = "%d_1_all" % bno
        add("C-%s-1" % band, fid, "p1pool", E.fig_pooled_phase1(T, band, p1, p1["deltas"], nq, fid, "fdr"), band=band)
        for p, st in enumerate(p2["pairs"]):
            if st:
                fid = "%d_2_%02d" % (bno, p + 1)
                add("C-%s-2" % band, fid, "p2pair", E.fig_pair_phase2(T, band, p, st, fid, "fdr"), band=band, pair=p)
        fid = "%d_2_all" % bno
        add("C-%s-2" % band, fid, "p2pool", E.fig_pooled_phase2(T, band, p2, fid, "fdr"), band=band)
        for p, st in enumerate(p3["pairs"]):
            if st:
                fid = "%d_3_%02d" % (bno, p + 1)
                add("C-%s-3" % band, fid, "p3pair", E.fig_pair_phase3(T, band, p, st, fid, "fdr"), band=band, pair=p)
        fid = "%d_3_all" % bno
        add("C-%s-3" % band, fid, "p3pool", E.fig_pooled_phase3(T, band, p3, fid, "fdr"), band=band)
    for band in ("theta", "gamma"):
        bno = 1 if band == "theta" else 2
        per = FN["power"][band]
        for x in per:
            if x:
                fid = "P%d_%d" % (bno, FS.REGIONS.index(x["region"]) + 1)
                add("P-%s" % band, fid, "power", FS.fig_power_region(PT, band, x, fid, "fdr"), band=band, region=x["region"])
        fid = "P%d_all" % bno
        add("P-%s" % band, fid, "powerall", FS.fig_power_all(PT, band, per, fid, "fdr", FN["tiers"][band]), band=band)
    add("F", "F1", "fooof", FS.fig_fooof(FN["fooof"], D["FT"], "F1", "fdr"))
    n = 0
    for x in D["G"]:
        if x.get("error"):
            continue
        n += 1
        add("follow", "G%d" % n, "granger", FS.fig_granger(x, "G%d" % n, "fdr"), band=x["band"], pair=x["pair"], show_in=x["in"])
    n = 0
    for x in D["PM"]:
        if x.get("error"):
            continue
        n += 1
        add("follow", "M%d" % n, "pac", FS.fig_pac(x, "M%d" % n, "fdr"), region=x["region"], show_in=x["in"])
    return out


# --------------------------------------------------------------------------
# The words under each figure
# --------------------------------------------------------------------------
def _robust_index(EM, FN):
    out = {}
    for r in EM.get("robust") or []:
        out[("coh", r["band"], r["pair"], r["label"])] = r
    for r in FN.get("robust") or []:
        nm = r.get("name") or ""
        if r["kind"] == "power":
            m = re.match(r"Power, (.*?)( \(tier 1\))?: ", nm)
            who = "every" if "every region" in nm else (m.group(1) if m else "")
            out[("power", r["band"], who, r["label"])] = r
        elif r["kind"] == "granger":
            out[("granger", r["band"], r["pair"], nm)] = r
        elif r["kind"] == "pac":
            out[("pac", nm.split(", ")[-1])] = r
    return out


def _terms_rows(ts, q_of=None, primary=(), prefix=""):
    rows = []
    for t in ts or []:
        rows.append(test_row(prefix + t["term"], t, q=(q_of or {}).get(t["term"]), primary=t["term"] in primary))
    return [r for r in rows if r]


def texts(f, D):
    """caption, note, results and tests for one drawn figure."""
    EM, FN = D["EM"], D["FN"]
    R = D["robust"]
    k = f["kind"]
    band = f.get("band")
    bl = BAND_LONG.get(band, "")
    BW = (band or "").capitalize()
    n_of = lambda rats: "n = %d rats" % len(rats)      # noqa: E731
    n_end = lambda rats: "Data are from %d rats." % len(rats)      # noqa: E731
    pooled = ("Coherence was computed from pooled spectra: for each rat and session, the auto- and cross-spectra of every 1-s segment "
              "(1,024-sample Hann window, 50%% overlap, 2,048-point FFT at 1 kHz) from every trial's %s were summed before "
              "magnitude-squared coherence was taken.")
    regionpair = ("A rat's value for a region pair is the mean over its valid wire pairs, ipsilateral and contralateral weighted equally; "
                  "homotopic pairs were not used.")
    gee_coh = ("Tested with a generalized estimating equation (Gamma family, log link, exchangeable working correlation, rat as the "
               "cluster); tests of up to 2 df used robust standard errors with the Mancl–DeRouen small-sample correction, larger tests "
               "model-based standard errors.")
    out = {"tests": [], "results": []}
    if k in ("p1pair", "p2pair", "p3pair"):
        p = f["pair"]
        a, b = E.STRUCTS[E.PAIRS[p][0]][1], E.STRUCTS[E.PAIRS[p][1]][1]
        B = next(x for x in EM["bands"] if x["band"] == band)
        w = (EM["pairs"][p].get("wires") or {})
    if k == "p1pair":
        st = B["phase1"]["pairs"][p]
        rats = st["rats"]
        no = "D%d.1.%02d" % (1 if band == "theta" else 2, p + 1)
        out["title"] = "%s–%s · %s · Early vs Late" % (a, b, band)
        out["caption"] = (
            "%s coherence between %s and %s during the cue pair in Early (Precon1) and Late (Precon4) sessions. (a) The five recorded "
            "regions; the %s–%s edge is shown in colour (other pairs in grey), its width proportional to the mean Late − Early change in "
            "band coherence on a scale common to all %s figures, and the arrowhead indicating its sign. (b) Coherence in each frequency "
            "bin (%s) for each rat, Early (light) and Late (dark); each point is one rat's value in one bin, and horizontal lines mark the "
            "median and interquartile range. (c) Band-averaged coherence of each rat (grey lines) and the mean ± s.e.m. across rats. "
            "(d) Coherence spectra, mean ± s.e.m. across rats, Early (solid) and Late (dashed); inset, mean Late − Early difference in "
            "each bin. %s" % (BW, a, b, a, b, band, BAND_BINS[band], n_end(rats)))
        out["note"] = " ".join([pooled % "20-s cue-pair window (cue 1 onset to cue 2 offset)", regionpair,
                                "This pair comprised %d ipsilateral and %d contralateral wire pairs across the %d rats." % (w.get("ipsi", 0), w.get("contra", 0), len(rats)),
                                "%s coherence was averaged over %s." % (BW, BAND_BINS[band]),
                                "Late versus Early was tested on band coherence; Session × Frequency on the per-bin values.", gee_coh,
                                "p-values were corrected across the ten region pairs (Benjamini–Hochberg)."])
        a2 = st.get("a2")
        rob = R.get(("coh", band, p, "Late vs Early"))
        if a2:
            out["tests"].append(test_row("Late vs Early", a2, primary=True, robust=rob, family="pairs"))
            out["results"].append(s_change("%s %s–%s coherence" % (BW, a, b), a2, a2.get("q"), FAMILY["pairs"]))
            if rob:
                out["results"].append(s_robust(_robust(rob)))
        sf = next((t for t in st.get("b2") or [] if t["term"] == "Session × Frequency"), None)
        if sf:
            out["tests"].append(test_row("Session × Frequency", sf, q=st.get("b2_q"), family="pairs"))
            out["results"].append(s_term("Across frequency bins", "Session × Frequency", sf, st.get("b2_q"), FAMILY["pairs"]))
    elif k == "p1pool":
        P1 = next(x for x in EM["bands"] if x["band"] == band)["phase1"]
        keep = [x for x in P1["pairs"] if x]
        out["title"] = "All ten pairs · %s · Early vs Late" % band
        out["caption"] = (
            "%s coherence in all ten region pairs during the cue pair, Early (Precon1) and Late (Precon4). (a) The five recorded regions "
            "with one edge per pair, its width proportional to the mean Late − Early change in band coherence and the arrowhead indicating "
            "its sign; the key gives each pair's colour, line style and number of rats. (b) Per-rat coherence in each frequency bin (%s) for "
            "each pair, Early (light) and Late (dark). (c) Band-averaged coherence, mean ± s.e.m. across rats, for each pair. (d, e) "
            "Coherence spectra of each pair (mean across rats), Early (d) and Late (e). (f) Mean Late − Early difference in each frequency "
            "bin for each pair." % (BW, BAND_BINS[band]))
        out["note"] = " ".join([pooled % "20-s cue-pair window", regionpair,
                                "All pairs were entered into one model with Session, Pair and their interaction (band coherence), and one "
                                "with Session, Pair, Frequency and their interactions (per-bin coherence).", gee_coh,
                                "With %d rats, robust standard errors cannot be estimated for terms with many degrees of freedom; those "
                                "terms are reported on model-based errors, which assume the working correlation is correct." % len(EM["rats"])])
        out["tests"] = _terms_rows(P1.get("a1"), prefix="Band: ") + _terms_rows(P1.get("b1"), prefix="Bins: ")
        sp = next((t for t in P1.get("a1") or [] if t["term"] == "Session × Pair"), None)
        ss = next((t for t in P1.get("a1") or [] if t["term"] == "Session"), None)
        for t in P1.get("a1") or []:
            out["results"].append(s_term("In the model of band coherence in all ten pairs", t["term"], t, None, ""))
        for t in P1.get("b1") or []:
            out["results"].append(s_term("In the model of coherence across frequency bins in all ten pairs", t["term"], t, None, ""))
        n_sig = sum(1 for x in keep if x.get("a2") and x["a2"].get("q") is not None and x["a2"]["q"] < E.ALPHA)
        out["results"].append("Tested pair by pair, %d of %d pairs changed between Early and Late after correction across the ten pairs "
                              "(Figures D%d.1.01–D%d.1.10)." % (n_sig, len(keep), 1 if band == "theta" else 2, 1 if band == "theta" else 2))
    elif k == "p2pair":
        st = B["phase2"]["pairs"][p]
        rats = st["rats"]
        out["title"] = "%s–%s · %s · cue 1 vs cue 2" % (a, b, band)
        out["caption"] = (
            "%s coherence between %s and %s during cue 1 and cue 2 in Early (a, Precon1) and Late (b, Precon4) sessions. Grey lines show "
            "individual rats; coloured points show the mean ± s.e.m. across rats (%s)." % (BW, a, b, n_of(rats)))
        out["note"] = " ".join([pooled % "10-s cue 1 window and, separately, its 10-s cue 2 window", regionpair,
                                "Every preconditioning trial is a matched pairing (A→B or C→D); the two pairings were pooled.",
                                "Session × Cue tested whether the cue 2/cue 1 ratio changed between sessions; the cue effect within each "
                                "session (cue 2 versus cue 1) was tested separately.", gee_coh,
                                "Each test was corrected across the ten region pairs (Benjamini–Hochberg)."])
        sc = next((t for t in st.get("terms") or [] if t["term"] == "Session × Cue"), None)
        rob = R.get(("coh", band, p, "Session × Cue"))
        if sc:
            out["tests"].append(test_row("Session × Cue", sc, q=st.get("q"), primary=True, robust=rob, family="pairs"))
            out["results"].append(s_inter("The difference between cue 2 and cue 1 in %s %s–%s coherence" % (band, a, b), "Session × Cue", sc,
                                          st.get("q"), FAMILY["pairs"]))
            if rob:
                out["results"].append(s_robust(_robust(rob)))
        for d in E.DAYS:
            r = (st.get("days") or {}).get(d) or {}
            if r.get("p") is None:
                continue
            out["tests"].append(test_row("Cue 2 vs cue 1, %s" % d, r, family="pairs"))
            out["results"].append(s_change("In %s, %s %s–%s coherence during cue 2" % (d, band, a, b), r, r.get("q"), FAMILY["pairs"],
                                           what="than during cue 1").replace("ratio Late/Early", "ratio cue 2/cue 1")
                                  .replace("did not differ between Early and Late sessions", "did not differ from cue 1"))
    elif k == "p2pool":
        P2 = next(x for x in EM["bands"] if x["band"] == band)["phase2"]
        out["title"] = "All ten pairs · %s · cue 1 vs cue 2" % band
        out["caption"] = ("%s coherence during cue 1 and cue 2 in all ten region pairs, Early (a, Precon1) and Late (b, Precon4). Points show the "
                          "mean ± s.e.m. across rats; the key gives each pair's colour and line style." % BW)
        out["note"] = " ".join([pooled % "cue 1 and cue 2 windows (10 s each)", regionpair,
                                "All pairs were entered into one model with Session, Cue, Pair and their interactions.", gee_coh])
        out["tests"] = _terms_rows(P2.get("omnibus"))
        for t in P2.get("omnibus") or []:
            out["results"].append(s_term("In the model of all ten pairs", t["term"], t, None, ""))
    elif k == "p3pair":
        st = B["phase3"]["pairs"][p]
        rats = st["rats"]
        out["title"] = "%s–%s · %s · baseline, cue 1, cue 2" % (a, b, band)
        out["caption"] = (
            "%s coherence between %s and %s in the baseline, cue 1 and cue 2 windows of Early (Precon1, solid) and Late (Precon4, dashed) "
            "sessions. (a) Band-averaged coherence in each 10-s window, mean ± s.e.m. across rats. (b, c) Change from baseline across "
            "frequency during cue 1 (b) and cue 2 (c), mean (line) ± s.e.m. (shading) across rats. %s" % (BW, a, b, n_end(rats)))
        out["note"] = " ".join([pooled % "10-s baseline (the 10 s preceding cue 1), cue 1 and cue 2 windows, each separately", regionpair,
                                "Session × Period (2 df) tested whether the response to the cues, relative to baseline, changed between "
                                "sessions; three planned 1-df contrasts compared cue 1 with baseline, cue 2 with baseline and cue 2 with "
                                "cue 1. On the log link these are ratios of ratios: (cue/baseline in Late) ÷ (cue/baseline in Early).",
                                gee_coh, "Each test was corrected across the ten region pairs (Benjamini–Hochberg)."])
        sp = st.get("sp") or {}
        rob = R.get(("coh", band, p, "Session × Period"))
        if sp.get("p") is not None:
            out["tests"].append(test_row("Session × Period", sp, primary=True, robust=rob, family="pairs"))
            out["results"].append(s_inter("The response of %s %s–%s coherence to the cues, relative to baseline," % (band, a, b), "Session × Period",
                                          sp, sp.get("q"), FAMILY["pairs"]))
            if rob:
                out["results"].append(s_robust(_robust(rob)))
        for ck, (ca, cb) in CONTRAST_SAY.items():
            c = (st.get("contrasts") or {}).get(ck) or {}
            if c.get("p") is None:
                continue
            say = "Session × (%s vs %s)" % (ca, cb)
            rb = R.get(("coh", band, p, say))
            out["tests"].append(test_row(say, c, robust=rb, family="pairs"))
            out["results"].append(s_contrast("%s %s–%s coherence" % (band, a, b), ck, c, c.get("q"), FAMILY["pairs"]))
            if rb:
                out["results"].append(s_robust(_robust(rb)))
    elif k == "p3pool":
        P3 = next(x for x in EM["bands"] if x["band"] == band)["phase3"]
        out["title"] = "All ten pairs · %s · how the cue effect changed" % band
        out["caption"] = (
            "Change in the cue effect on %s coherence from Early (Precon1) to Late (Precon4) for each region pair. Each point is the "
            "estimated ratio of ratios, (cue/baseline in Late) ÷ (cue/baseline in Early), with its 95%% confidence interval, for cue 1 "
            "relative to baseline (a), cue 2 relative to baseline (b) and cue 2 relative to cue 1 (c); a value of 1 (vertical line) "
            "indicates no change. Logarithmic axis." % band)
        out["note"] = " ".join([pooled % "10-s baseline, cue 1 and cue 2 windows", regionpair,
                                "Each estimate is a planned 1-df contrast of the Session × Period model for that pair.", gee_coh,
                                "Each contrast was corrected across the ten region pairs (Benjamini–Hochberg)."])
        hits_ = []
        for x in P3["pairs"]:
            if not x:
                continue
            for ck, (ca, cb) in CONTRAST_SAY.items():
                c = (x.get("contrasts") or {}).get(ck) or {}
                if c.get("p") is None:
                    continue
                row = test_row("%s: Session × (%s vs %s)" % (_pair(x["pair"]), ca, cb), c, family="pairs")
                out["tests"].append(row)
                if row["pass"]["raw"]:
                    hits_.append(s_contrast("%s %s coherence" % (band, _pair(x["pair"])), ck, c, c.get("q"), FAMILY["pairs"]))
        out["results"] = hits_ or ["No planned contrast reached p < .05 in any pair."]
    elif k == "power":
        r_ = f["region"]
        x = next(z for z in FN["power"][band] if z and z["region"] == r_)
        rs = FS.REGION_SAY[r_]
        out["title"] = "%s · %s power" % (rs, band)
        out["caption"] = (
            "%s power in %s in the baseline, cue 1 and cue 2 windows of Early (Precon1, solid) and Late (Precon4, dashed) sessions. "
            "(a) Band power (dB re 1 µV²/Hz), mean ± s.e.m. across rats. (b, c) Change from baseline across frequency during cue 1 (b) "
            "and cue 2 (c), in dB, mean (line) ± s.e.m. (shading) across rats. %s The y-axis of panel a spans the same range in every "
            "region, centred on that region's power." % (BW, REGION_LONG[r_], n_end(x["rats"])))
        out["note"] = " ".join([
            "Power spectral density (one-sided, µV²/Hz) was estimated from the same 1-s segments as coherence (1,024-sample Hann window, "
            "50% overlap, 2,048-point FFT at 1 kHz) in each 10-s window of every trial, averaged over the session's trials and over the two "
            "hemispheres where both were valid, averaged within the band and expressed in dB (re 1 µV²/Hz). No per-animal normalisation "
            "was applied.",
            "Tier 3a: Session (Precon1, Precon4) × Period (baseline, cue 1, cue 2) on band power, with three planned 1-df contrasts; "
            "tier 3b: Session × Period × Frequency on per-bin power. Generalized estimating equation (normal family, identity link, "
            "exchangeable working correlation, rat as the cluster); tests of up to 2 df on robust standard errors with the Mancl–DeRouen "
            "correction, larger tests on model-based errors. Each test was corrected across the ten per-region models (five regions × two "
            "bands; Benjamini–Hochberg)."])
        sp = x.get("sp") or {}
        rob = R.get(("power", band, rs, "Session × Period"))
        if sp.get("p") is not None:
            out["tests"].append(test_row("Session × Period", sp, primary=True, robust=rob, family="regions10"))
            out["results"].append(s_inter("The response of %s %s power to the cues, relative to baseline," % (rs, band), "Session × Period", sp,
                                          sp.get("q"), FAMILY["regions10"]))
            if rob:
                out["results"].append(s_robust(_robust(rob)))
        for ck, (ca, cb) in CONTRAST_SAY.items():
            c = (x.get("contrasts") or {}).get(ck) or {}
            if c.get("p") is None:
                continue
            say = "Session × (%s vs %s)" % (ca, cb)
            rb = R.get(("power", band, rs, say))
            out["tests"].append(test_row(say, c, robust=rb, family="regions10"))
            out["results"].append(s_contrast("%s %s power" % (rs, band), ck, c, c.get("q"), FAMILY["regions10"], db=True))
            if rb:
                out["results"].append(s_robust(_robust(rb)))
        spf = x.get("spf") or {}
        if spf.get("p") is not None:
            out["tests"].append(test_row("Session × Period × Frequency", spf, family="regions10"))
    elif k == "powerall":
        per = [z for z in FN["power"][band] if z]
        tiers = FN["tiers"][band]
        out["title"] = "Every region · %s power" % band
        out["caption"] = (
            "%s power in every region (rows: %s) in the baseline, cue 1 and cue 2 windows of Early (Precon1, solid) and Late (Precon4, "
            "dashed) sessions. Columns as in the single-region figures: (a) band power (dB re 1 µV²/Hz), (b, c) change from baseline across "
            "frequency during cue 1 and cue 2 (dB); mean ± s.e.m. across rats." % (BW, ", ".join(FS.REGION_SAY[z["region"]] for z in per)))
        out["note"] = ("Power as in the single-region figures. Tier 1: Session × Period × Region (2 × 3 × 5) on band power; tier 2: the same × "
                       "Frequency on per-bin power; generalized estimating equation (normal, identity, exchangeable, rat as the cluster). "
                       "Beside each, a linear mixed model of the same rows with random intercepts for rat, for each rat's region and for each "
                       "region's session (tier 2: and period), with Wald F tests on k and k(n − 1) degrees of freedom. Key terms were "
                       "corrected across the tier's two models (theta and gamma).")
        for t, say in (("t1", "Tier 1"), ("t2", "Tier 2")):
            for name, kk in (tiers.get(t) or {}).get("key", {}).items():
                row = test_row("%s: %s" % (say, name), kk, primary=(name == "Session × Period"), family="bands")
                if row:
                    lm = kk.get("lmm") or {}
                    row["lmm"] = ("F(%d, %d) = %.2f, %s" % (lm["df1"], lm["df2"], lm["F"], fp(lm["p"]))) if lm.get("p") is not None else None
                    row["lmm_p"] = lm.get("p")
                    out["tests"].append(row)
                    s = s_term("In %s %s power" % (say.lower(), band), name, kk, kk.get("q"), FAMILY["bands"])
                    out["results"].append(s + (" The linear mixed model gave %s." % row["lmm"] if row.get("lmm") else ""))
    elif k == "fooof":
        out["title"] = "Aperiodic and periodic components · every region"
        out["caption"] = ("Aperiodic exponent, aperiodic offset, theta peak frequency and theta peak power (rows) in each region (columns) in the "
                          "baseline, cue 1 and cue 2 windows of Early (Precon1, solid) and Late (Precon4, dashed) sessions; mean ± s.e.m. "
                          "across rats with a fit in all six session × window cells. Each row shares one y-axis across regions.")
        out["note"] = ("Power spectra from 2 to 55 Hz were parameterised with FOOOF 1.1 (fixed aperiodic mode, peak widths 1–8 Hz, at most six "
                       "peaks) for each hemisphere, window and session, and the parameters were averaged across hemispheres. Theta peak "
                       "frequency and power (above the aperiodic fit) were taken from the largest peak centred between 5 and 12 Hz. "
                       "Session × Period was tested for each parameter in each region (generalized estimating equation, normal, identity, "
                       "exchangeable, rat as the cluster; robust standard errors with the Mancl–DeRouen correction) and corrected across the "
                       "five regions (Benjamini–Hochberg).")
        for key, say, _u in FS.FOOOF_PARAMS:
            for x in FN["fooof"][key]:
                sp = x.get("sp") or {}
                if sp.get("p") is None:
                    continue
                row = test_row("%s, %s: Session × Period" % (say, FS.REGION_SAY[x["region"]]), sp, family="regions5")
                row["primary"] = row["pass"]["raw"]
                out["tests"].append(row)
                if row["pass"]["raw"]:
                    out["results"].append(s_inter("In %s, the %s across the baseline, cue 1 and cue 2 windows" % (FS.REGION_SAY[x["region"]], say.lower()),
                                                  "Session × Period", sp, sp.get("q"), FAMILY["regions5"]))
        if not out["results"]:
            out["results"].append("No parameter changed between sessions in any region (all p ≥ .05).")
    elif k == "granger":
        x = next(z for z in FN["granger"] if z["pair"] == f["pair"] and z["band"] == band)
        A, Bn = x["a"], x["b"]
        out["title"] = "%s–%s · %s · which region leads" % (A, Bn, band)
        out["caption"] = (
            "Spectral Granger causality between %s and %s in %s, Early (Precon1) and Late (Precon4). (a, b) Band-averaged Granger causality "
            "%s → %s (a) and %s → %s (b) for each rat (grey lines) and the mean ± s.e.m. across rats (%s). (c) Granger causality spectra "
            "(mean across rats) in each direction (solid, %s → %s; dotted, %s → %s), Early (grey) and Late (colour); the shaded band marks "
            "%s." % (A, Bn, BAND_LONG[band], A, Bn, Bn, A, n_of(x["rats"]), A, Bn, Bn, A, BAND_LONG[band]))
        out["note"] = ("Granger causality was computed for region pairs whose coherence changed between Early and Late. Signals were "
                       "down-sampled to 250 Hz, cut into 1-s segments (Hann window, 50% overlap, mean removed, 500-point FFT), and the 2 × 2 "
                       "cross-spectral matrix was pooled over every segment of every cue-pair window of a session and factorised with "
                       "Wilson's algorithm to obtain Geweke's spectral Granger causality in each direction, averaged within the band and over "
                       "the pair's valid wire pairs. Late versus Early in each direction and Session × Direction were tested with a "
                       "generalized estimating equation (Gamma, log link, exchangeable, rat as the cluster, robust standard errors with the "
                       "Mancl–DeRouen correction), corrected across the Granger tests (Benjamini–Hochberg).")
        for key, s1, s2 in (("ab", A, Bn), ("ba", Bn, A)):
            t = x.get(key) or {}
            if t.get("p") is None:
                continue
            rb = R.get(("granger", band, x["pair"], "Granger %s → %s" % (s1, s2)))
            out["tests"].append(test_row("%s → %s, Late vs Early" % (s1, s2), t, primary=True, robust=rb, family="granger"))
            out["results"].append(s_change("%s Granger causality from %s to %s" % (BW, s1, s2), t, t.get("q"), FAMILY["granger"]))
            if rb:
                out["results"].append(s_robust(_robust(rb)))
        sd = x.get("sd") or {}
        if sd.get("p") is not None:
            out["tests"].append(test_row("Session × Direction", sd, family="granger"))
            out["results"].append(s_term("Comparing the two directions", "Session × Direction", sd, sd.get("q"), FAMILY["granger"]))
    elif k == "pac":
        r_ = f["region"]
        x = next(z for z in FN["pac"] if z["region"] == r_)
        rs = FS.REGION_SAY[r_]
        out["title"] = "%s · theta–gamma coupling" % rs
        out["caption"] = ("Theta–gamma phase–amplitude coupling within %s, Early (Precon1) and Late (Precon4). (a) Modulation index of each rat "
                          "(grey lines) and the mean ± s.e.m. across rats (%s). (b) Gamma amplitude in each theta phase bin, as a share of the "
                          "total (mean across rats), Early (solid) and Late (dashed); the horizontal line marks a uniform distribution."
                          % (REGION_LONG[r_], n_of(x["rats"])))
        out["note"] = ("Coupling was measured within regions belonging to pairs whose coherence changed between sessions. Theta (5–12 Hz) phase "
                       "and gamma (30–90 Hz) amplitude of a single wire were obtained by zero-phase band-pass filtering and the Hilbert "
                       "transform (mirrored padding); gamma amplitude was summed in 18 phase bins over every cue-pair window of a session and "
                       "Tort's modulation index computed from the resulting distribution, then averaged across hemispheres. Late versus "
                       "Early was tested with a generalized estimating equation (Gamma, log link, exchangeable, rat as the cluster, robust "
                       "standard errors with the Mancl–DeRouen correction), corrected across the coupling tests (Benjamini–Hochberg).")
        t = x.get("le") or {}
        if t.get("p") is not None:
            rb = R.get(("pac", rs))
            out["tests"].append(test_row("Late vs Early", t, primary=True, robust=rb, family="pac"))
            out["results"].append(s_change("Theta–gamma modulation index in %s" % rs, t, t.get("q"), FAMILY["pac"]))
            if rb:
                out["results"].append(s_robust(_robust(rb)))
    out["tests"] = [t for t in out["tests"] if t]
    prim = [t for t in out["tests"] if t["primary"]]
    out["sig"] = {m: any(t["pass"][m] for t in prim) for m in E.MODES}
    out["results"] = [s for s in out["results"] if s]
    return out


TAB11_KINDS = ("p1pair", "p1pool", "p2pair", "p2pool", "p3pair", "p3pool")
GROUPS = [("C-theta-1", "coh", "Theta coherence · Early against Late"), ("C-theta-2", "coh", "Theta coherence · cue 1 against cue 2"),
          ("C-theta-3", "coh", "Theta coherence · baseline, cue 1 and cue 2"), ("C-gamma-1", "coh", "Gamma coherence · Early against Late"),
          ("C-gamma-2", "coh", "Gamma coherence · cue 1 against cue 2"), ("C-gamma-3", "coh", "Gamma coherence · baseline, cue 1 and cue 2"),
          ("P-theta", "fin", "Theta power within each region"), ("P-gamma", "fin", "Gamma power within each region"),
          ("F", "fin", "Aperiodic and periodic components"), ("follow", "fin", "Directionality and coupling, on the pairs whose coherence changed")]
GROUP_SAY = {
    "C-theta-1": "Each pair alone, then all ten together.", "C-gamma-1": "Each pair alone, then all ten together.",
    "C-theta-2": "Matched trials; cue 1 and cue 2 within each session.", "C-gamma-2": "Matched trials; cue 1 and cue 2 within each session.",
    "C-theta-3": "The response to each cue relative to the 10-s baseline, and how it changed.",
    "C-gamma-3": "The response to each cue relative to the 10-s baseline, and how it changed.",
    "P-theta": "Each region alone (tier 3), then every region together (tiers 1 and 2).",
    "P-gamma": "Each region alone (tier 3), then every region together (tiers 1 and 2).",
    "F": "Five regions, four parameters.",
    "follow": "Run only for the pairs (and their regions) whose coherence changed between Early and Late; the correction setting decides which."}


def figure_record(f, D):
    rs = D["rs"]
    T_ = texts(f, D)
    fid = f["fid"]
    coh = f["kind"] in TAB11_KINDS
    no = ("D" if coh else "") + fid.replace("_", ".")        # D: tab 11's (Joe's site has tab 9's Figure 1.1 too)
    # Prism tables made with tab 11 and 12's own figures for this set
    prism = []
    figs = E.set_root(rs, "figs") if coh else FS.set_root(rs, "figs")
    for ext in ("xlsx", "pzfx"):
        p = os.path.join(figs, "fig_%s_prism.%s" % (fid, ext))
        if os.path.isfile(p):
            prism.append(p)
    return {"id": no, "fid": fid, "kind": f["kind"], "group": f["group"], "band": f.get("band"), "pair": f.get("pair"), "region": f.get("region"),
            "show_in": f.get("show_in"), "title": T_["title"], "name": "Figure %s · %s" % (no, T_["title"]),
            "pdf": f["files"].get("pdf"), "png": f["files"].get("png"), "prism": prism,
            "caption": "Figure %s. %s" % (no, T_["caption"]), "note": T_["note"], "results": T_["results"], "tests": T_["tests"], "sig": T_["sig"]}


# --------------------------------------------------------------------------
# The methods, for the dissertation
# --------------------------------------------------------------------------
def _refs_of_recordings():
    """Each rat-day's acquisition reference and hardware high-pass, from the
    recordings' own headers (None where they cannot be read here)."""
    from . import monolith as MO
    out = {}
    man = MO.manifest() or {}
    for d in man.get("days") or []:
        if d["day"] not in E.DAYS:
            continue
        f = next((x for x in d.get("folders") or [] if x.get("role") == "SPC"), None)
        p = os.path.join(f["local"], "CSC19.ncs") if f and f.get("local") else None
        if not p or not os.path.isfile(p):
            continue
        h = open(p, "rb").read(16384).decode("latin-1")
        ref = re.search(r"-ReferenceChannel\s+\"?([^\r\n\"]*)", h)
        lo = re.search(r"-DspLowCutFrequency\s+([^\r\n]*)", h)
        app = re.search(r"-ApplicationName\s+([^\r\n]*)", h)
        out[(int(d["rat"]), d["day"])] = {"ref": ref.group(1).strip() if ref else None, "lowcut": lo.group(1).strip() if lo else None,
                                          "app": app.group(1).strip().strip('"').replace('"', "") if app else None}
    return out


def _word(n):
    """Small whole numbers in words, as a thesis writes them."""
    w = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
         "fourteen", "fifteen", "sixteen")
    return w[n] if 0 <= n < len(w) else str(n)


def methods(DA, refs, bip, versions):
    """[{title, paras}]: the whole analysis, from recordings to statistics,
    in a thesis's words. DA is the all-rats set."""
    EM, FN = DA["EM"], DA["FN"]
    rats = EM["rats"]
    tr = sorted((EM.get("trials") or {}).values())
    nreg = {FS.REGION_SAY[x["region"]]: len(x["rats"]) for x in FN["power"]["theta"] if x}
    fl = EM.get("flag") or {}
    ref1 = sorted(k for k, v in refs.items() if v.get("ref") and "Reference" in v["ref"])
    lows = sorted({v.get("lowcut") for v in refs.values() if v.get("lowcut")})
    app = re.sub(r"\s*Development\s*", "", next((v["app"] for v in refs.values() if v.get("app")), "Cheetah")).strip()
    S = []
    S.append(("Overview", [
        "Local field potentials (LFPs) were analysed from %s rats (%s) across sensory preconditioning. Two questions were asked of the "
        "first (Precon1, “Early”) and last (Precon4, “Late”) preconditioning sessions: whether coherence between pairs of regions changed "
        "between sessions, and whether the response to the cues changed within each region (power, its aperiodic and periodic "
        "components) and between regions (direction of influence and theta–gamma coupling). An exploratory analysis across the "
        "spectrum preceded these planned tests and is described separately below." % (_word(len(rats)), ", ".join("J%d" % r for r in rats))]))
    S.append(("Recordings", [
        "[Surgical procedures, electrodes and stereotaxic coordinates to be added.] Each rat carried bilateral electrodes targeting the "
        "retrosplenial cortex (RSC), dorsal hippocampus (dHC), anterior cingulate cortex (ACC), orbitofrontal cortex (OFC), perirhinal "
        "cortex (PER) and postrhinal cortex (POR), with two wires per target per hemisphere (four for PER), 32 channels in all. Signals "
        "were acquired with a Neuralynx system (%s) at 32 kHz with an input range of ±2,000 µV and hardware filtering from %s Hz to "
        "8 kHz (the high-pass setting differed between sessions)." % (app, " or ".join(lows) if lows else "0.1"),
        ("The acquisition reference was the subject ground in most sessions; in %s sessions (%s) channels were referenced to a reference "
         "electrode instead. Signals were analysed as recorded, without re-referencing (see Sensitivity analyses)."
         % (_word(len(ref1)), ", ".join("J%d %s" % k for k in ref1))) if ref1 else
        "Signals were analysed as recorded, without re-referencing."]))
    S.append(("Sessions and trials", [
        "In each preconditioning session, two pairs of neutral auditory cues were presented without reinforcement, 16 presentations in "
        "all (eight of each pairing, A→B and C→D). Each presentation (a trial) consisted of cue 1 (10 s) followed immediately by cue 2 "
        "(10 s). Cue identities were counterbalanced across rats. Recordings without cues were also made before (FP1) and after (FP2) "
        "each session.",
        "Cue times were read from the TTL events recorded with the LFP. Only TTL records were used; each cue code was also emitted on "
        "the adjacent code, and these duplicates were merged, as were repeats of the same code within 150 ms on one port. A trial was "
        "defined as two different cue codes whose onsets were 10.0 ± 0.25 s apart; a separate code marked the end of cue 2. Events "
        "that could not be paired were flagged and inspected rather than discarded. After detection, sessions contributed %d to %d "
        "trials. Windows were cut by timestamp, because acquisition occasionally paused within a recording."
        % (tr[0] if tr else 0, tr[-1] if tr else 0),
        "Four windows were analysed in each trial, defined from that trial's own event times: a 10-s baseline immediately preceding "
        "cue 1; cue 1 (cue 1 onset to cue 2 onset, ≈10 s); cue 2 (cue 2 onset to its offset, ≈10 s); and the cue pair (cue 1 onset to "
        "cue 2 offset, ≈20 s). Windows were analysed in full, so the response to cue onset is included."]))
    S.append(("Electrode placement and channel selection", [
        "Electrode placements were verified histologically, and a region in a hemisphere was analysed only when its electrode lay within "
        "the target. No electrode aimed at POR was located in POR, so POR was not analysed. The numbers of rats contributing to each "
        "region were: %s." % ", ".join("%s %d" % (k, v) for k, v in nreg.items()),
        "Amplifier saturation was assessed for every wire in every window: a wire was excluded from a window when its signal remained "
        "within 0.5% of the digitiser's limit for at least 16 consecutive samples and such samples covered at least 0.5% of the window "
        "or any continuous 50 ms. Wires judged faulty on inspection were excluded throughout. In each window of each trial, one wire was "
        "then used per region and hemisphere: the lowest-numbered wire that was neither excluded nor saturated in that window. A fixed "
        "rule was used, rather than averaging the surviving wires, so that every window represents the same kind of measurement; where "
        "no wire survived, that region and hemisphere was treated as missing for that window."]))
    S.append(("Preprocessing", [
        "Signals were converted to microvolts, corrected for the acquisition system's inverted input, and down-sampled to 1 kHz with an "
        "order-8 Chebyshev type I anti-aliasing filter applied forwards and backwards (zero phase). Line noise was removed with a "
        "second-order Butterworth band-stop filter (59–61 Hz) applied with zero-phase filtering, as in Dickson et al. (2022); the "
        "59–61 Hz bins were excluded from every gamma average."]))
    S.append(("Spectral estimation", [
        "Spectra were estimated with Welch's method using the settings of MATLAB's mscohere as applied by Dickson et al. (2022): "
        "1,024-sample Hann windows, 512 samples of overlap and a 2,048-point FFT, giving a resolution of 0.49 Hz. Rather than computing "
        "a value for each trial and averaging, the auto- and cross-spectra of all segments from all trials of a session were summed "
        "before coherence was computed (pooled spectra). Pooling yields one well-estimated value per rat and session and avoids the "
        "positive bias of coherence estimated from few segments; because it requires the phase relationship between two regions to be "
        "consistent across trials, pooled coherence is lower than the mean of single-trial coherence (cue-pair window, mean across rats "
        "and pairs: %s)." % "; ".join("%s %s, %.3f pooled against %.3f trial-averaged" % (b, d, fl[b][d]["pooled"], fl[b][d]["trialmean"])
                                       for b in ("theta", "gamma") for d in E.DAYS if fl.get(b, {}).get(d)),
        "Theta was defined as 5–12 Hz and gamma as 30–90 Hz (59–61 Hz excluded). For frequency-resolved analyses theta was examined at "
        "the FFT's 0.49-Hz bins and gamma in 2-Hz bins."]))
    S.append(("Coherence", [
        "Magnitude-squared coherence was computed for every wire pair and averaged within each band. Ten region pairs were analysed "
        "(RSC–dHC, RSC–ACC, RSC–OFC, RSC–PER, dHC–ACC, dHC–OFC, dHC–PER, ACC–OFC, ACC–PER and OFC–PER). Within each rat, a region "
        "pair's value was the mean over all of its valid wire pairs, ipsilateral (left–left, right–right) and contralateral "
        "(left–right, right–left), each weighted equally; homotopic pairs (the same structure in the two hemispheres) were not used. A "
        "region pair entered a model only when at least %d rats contributed to it." % E.MIN_RATS,
        "Coherence was compared between Early and Late in the cue-pair window; between cue 1 and cue 2 within each session; and across "
        "the baseline, cue 1 and cue 2 windows (whether the response to the cues, relative to baseline, changed between sessions)."]))
    S.append(("Power and its components", [
        "Power spectral density (one-sided, µV²/Hz) was estimated from the same segments in the baseline, cue 1 and cue 2 windows, "
        "averaged over all segments of a session's trials, averaged over the two hemispheres of a region where both were valid, averaged "
        "within each band and expressed in decibels (dB re 1 µV²/Hz). No per-animal normalisation was applied: between-animal "
        "differences in overall power were absorbed by the model, and the response to the cues was tested as the Session × Period "
        "interaction, which compares each window with the baseline recorded in the same session.",
        "Spectra from 2 to 55 Hz were parameterised with FOOOF %s (Donoghue et al., 2020; fixed aperiodic mode, peak widths 1–8 Hz, at "
        "most six peaks) for each hemisphere, window and session, and the parameters were averaged across hemispheres: the aperiodic "
        "exponent and offset, and the centre frequency and power above the aperiodic fit of the largest peak between 5 and 12 Hz."
        % versions.get("fooof", "1.1")]))
    S.append(("Directionality and phase–amplitude coupling", [
        "For region pairs whose coherence changed between Early and Late, directed interactions were estimated with nonparametric "
        "spectral Granger causality (Dhamala et al., 2008). Signals were down-sampled to 250 Hz and cut into 1-s segments (Hann window, "
        "50% overlap, mean removed, 500-point FFT); the 2 × 2 cross-spectral matrix was pooled over every segment of every cue-pair "
        "window of a session and factorised with Wilson's algorithm, and Geweke's spectral Granger causality was computed in each "
        "direction, averaged within the band and over the pair's valid wire pairs.",
        "Within each region of those pairs, theta–gamma phase–amplitude coupling was quantified with the modulation index of Tort et "
        "al. (2010). Theta (5–12 Hz) phase and gamma (30–90 Hz) amplitude of a single wire were obtained by zero-phase band-pass "
        "filtering and the Hilbert transform with mirrored padding; gamma amplitude was summed in 18 phase bins over every cue-pair "
        "window of a session, and the modulation index was computed from the resulting distribution and averaged across hemispheres."]))
    S.append(("Statistical analysis", [
        "All tests used generalized estimating equations (Liang and Zeger, 1986) with rat as the cluster and an exchangeable working "
        "correlation (statsmodels %s). Coherence, Granger causality and the modulation index were modelled with a Gamma distribution "
        "and log link, so that effects are ratios (for example, Late/Early); power (dB) and the FOOOF parameters with a normal "
        "distribution and identity link, so that effects are differences. Hypotheses were tested with Wald χ² tests. Tests of one or "
        "two degrees of freedom used robust (sandwich) standard errors with the Mancl and DeRouen (2001) small-sample correction. "
        "Robust standard errors cannot be estimated for tests with more degrees of freedom than there are clusters; those tests (for "
        "example, Pair and any term involving Frequency) used model-based standard errors, which assume the working correlation is "
        "correct, and are reported as secondary." % versions.get("statsmodels", ""),
        "Coherence (each region pair): Late versus Early on the band, and Session × Frequency across bins; Session × Cue (cue 1, cue 2), "
        "with the cue effect tested within each session; and Session × Period (baseline, cue 1, cue 2; 2 df) with three planned 1-df "
        "contrasts (cue 1 versus baseline, cue 2 versus baseline, cue 2 versus cue 1). On the log link the contrasts are ratios of "
        "ratios, (cue/baseline in Late) ÷ (cue/baseline in Early).",
        "Power was analysed in four tiers, each separately for theta and gamma. Tier 1: Session (2) × Period (3) × Region (5) on band "
        "power, with Session × Period and Session × Period × Region as the key terms. Tier 2: the same × Frequency on per-bin power. "
        "Tier 3a: Session × Period with the three planned contrasts in each region separately. Tier 3b: Session × Period × Frequency in "
        "each region separately. Because the many-degree-of-freedom terms of tiers 1 and 2 cannot use robust standard errors with %d "
        "rats, each was also fitted as a linear mixed model with random intercepts for rat, for each rat's region and for each region's "
        "session (tier 2: and period), tested with Wald F statistics on k and k(n − 1) degrees of freedom." % len(rats),
        "FOOOF parameters: Session × Period in each region. Granger causality: Late versus Early in each direction, and Session × "
        "Direction. Modulation index: Late versus Early.",
        "p-values were corrected for multiple comparisons with the Benjamini–Hochberg false discovery rate (1995) within each family of "
        "tests: across the ten region pairs for each coherence test; across the two models (theta, gamma) of power tiers 1 and 2; across "
        "the ten per-region models of tiers 3a and 3b (five regions × two bands); across the five regions for each FOOOF parameter; and "
        "within the Granger and coupling families. Results are reported both uncorrected (p < .05) and corrected (q < .05); the region "
        "pairs followed up with Granger causality and coupling are those that changed under the criterion in use.",
        "Every result with p < .05 was checked in two further ways: the model was refitted with each rat omitted in turn (does p remain "
        "below .05 every time, and which rat does the effect depend on), and the same rows were fitted with a linear mixed model with a "
        "random intercept for rat (on the log scale for coherence, Granger causality and the modulation index; on dB for power), tested "
        "with a Wald F on k and k(n − 1) degrees of freedom. With %d rats, the generalized estimating equation's robust p-values can be "
        "markedly smaller than the mixed model's; results that held under both checks are described as robust." % len(rats),
        "Coefficients are reported as SPSS reports them, with the last level of each factor (in ascending order) as the reference "
        "category: Session, Precon4; Period, cue 2; Frequency, the highest bin; Direction, the second. The tests do not depend on this "
        "choice (sum coding)."]))
    rc = sorted(EM.get("reference_check") or [], key=lambda x: -x["hg"])
    flagged = [x for x in rc if x["rat"] in (3, 4) and (x["rat"] == 3 or x["day"] == "Precon1")]
    rest = [x for x in rc if x not in flagged]
    para = [
        "Because coherence assumes that each electrode records its own region, recordings were screened for a signal common to every "
        "channel, the signature of a contaminated reference. Three markers were measured on the 10-s baseline of every rat and session: "
        "coherence between regions at 75–90 Hz (where coherence between distant brain regions is expected to be small), the rise in "
        "coherence from 4–8 Hz to 75–90 Hz (coherence of neural origin typically falls with frequency), and the median absolute phase of "
        "the cross-spectrum at 30–90 Hz (a common signal arrives at every electrode with zero lag)."]
    sg = lambda v: ("%+.2f" % v).replace("-", "−")      # noqa: E731
    if flagged and rest:
        para.append(
            "%s sessions departed from the rest on all three markers: %s. The remaining %s sessions ranged %.2f–%.2f, %s to %s and "
            "%.0f–%.0f°." % (_word(len(flagged)).capitalize(),
                             "; ".join("J%d %s (%.2f, %s, %.0f°)" % (x["rat"], x["day"], x["hg"], sg(x["rise"]), x["phase"]) for x in flagged),
                             _word(len(rest)), min(x["hg"] for x in rest), max(x["hg"] for x in rest), sg(min(x["rise"] for x in rest)),
                             sg(max(x["rise"] for x in rest)), min(x["phase"] for x in rest), max(x["phase"] for x in rest)))
    def gam(rat, kind, day=None):
        return [x for v in (bip or {}).values() if v.get("rat") == rat and (day is None or v.get("day") == day)
                for x in v[kind]["gamma"] if x is not None]
    others = [x for v in (bip or {}).values() if v.get("rat") not in (3, 4) for x in v["bip"]["gamma"] if x is not None]
    others_r = [x for v in (bip or {}).values() if v.get("rat") not in (3, 4) for x in v["ref"]["gamma"] if x is not None]
    if gam(3, "ref") and others:
        para.append(
            "Coherence was then recomputed from the difference between the two wires of each region (a local bipolar derivation), which "
            "cancels anything common to both wires, including a contaminated reference; because it also removes signal shared by "
            "neighbouring wires, it lowers coherence in every rat, so it was compared across rats rather than read on its own. In J3, "
            "gamma coherence fell from a median of %.2f (range %.2f–%.2f) to %.2f (%.2f–%.2f), comparable with rats without the "
            "signature computed the same way (median %.2f, range %.2f–%.2f, from %.2f as recorded). In J3's Precon4 recording, imaginary "
            "coherence and the phase-lag index, which are insensitive to signals arriving at zero lag, were within the range of the "
            "other rats." % (np.median(gam(3, "ref")), min(gam(3, "ref")), max(gam(3, "ref")), np.median(gam(3, "bip")), min(gam(3, "bip")),
                             max(gam(3, "bip")), np.median(others), min(others), max(others), np.median(others_r)))
    if gam(4, "ref", "Precon1") and gam(4, "bip", "Precon1"):
        para.append("In J4's Precon1 recording, where the common signal lay mostly above 60 Hz, the same derivation reduced gamma coherence "
                    "from a median of %.2f (range %.2f–%.2f) to %.2f (%.2f–%.2f)." % (
                        np.median(gam(4, "ref", "Precon1")), min(gam(4, "ref", "Precon1")), max(gam(4, "ref", "Precon1")),
                        np.median(gam(4, "bip", "Precon1")), min(gam(4, "bip", "Precon1")), max(gam(4, "bip", "Precon1"))))
    para.append(
        "Every analysis was therefore repeated without J3, without J4, and without both; each repetition re-estimated every model, the "
        "false discovery rate correction, the pairs followed up and the robustness checks without those rats. Because every test "
        "compares a rat's two sessions, a rat was omitted entirely rather than one of its sessions. The acquisition reference also "
        "differed between Precon1 and Precon4 in three rats (J8, J9, J10); these rats did not show the signature, but the change of "
        "reference is a potential confound of Early versus Late comparisons in them.")
    S.append(("Sensitivity analyses", para))
    S.append(("Exploratory analysis across the spectrum", [
        "Before the planned tests, coupling was surveyed across the spectrum to generate hypotheses; none of its results is used for "
        "inference here. For each trial, connectivity between every pair of the recorded regions was computed in a 10-s baseline before "
        "cue 1, cue 1, cue 2 and a 10-s period after cue 2, and in windows straddling cue 1 onset, the cue 1–cue 2 transition and cue 2 "
        "offset (−3 to +3 s for frequencies up to 12 Hz; −1 to +2 s above). Three measures followed the laboratory's earlier analyses "
        "(Welch coherence with 1,000-sample Hann windows, 500-sample overlap and a 2,000-point FFT; the peak of the cross-correlation "
        "of the band-passed signals within ±0.5 s and its lag; and the same for their amplitude envelopes), extended to fourteen measures "
        "(coherence, imaginary coherence, cross-correlation, envelope correlation with and without lag, orthogonalised envelope "
        "correlation, phase-locking value, pairwise phase consistency, phase-lag index, weighted and debiased weighted phase-lag index, "
        "and spectral Granger causality in each direction), regional power and phase–amplitude coupling, in bands centred on every "
        "integer frequency from 1 to 55 Hz (±15%, at least ±0.5 Hz) and in conventional theta, beta and low-gamma bands. Mains (60 Hz "
        "and harmonics) was notched before any measure was computed.",
        "Each recording's values were organised as a connectivity matrix keeping every trial's value, and regions whose electrode was "
        "not in the target were excluded. Changes from Precon1 to Precon4 were estimated within each rat as the difference of its "
        "session means, with variance from the two sessions' standard errors, and pooled across rats with a DerSimonian–Laird "
        "random-effects meta-analysis, tested with the Hartung–Knapp method on k − 1 degrees of freedom; entries with fewer than four "
        "rats were not tested. The same analysis was run on the cue response relative to the free-period recordings (cue minus "
        "free-period epochs of the same session). With roughly a quarter of a million tests, no entry survives correction, and an entry "
        "selected from this survey and tested again on the same data would be circular; the survey was therefore used only to inform "
        "the planned analyses."]))
    S.append(("Planned comparisons of the proposal", [
        "The comparisons named in the dissertation proposal were analysed separately, with coherence computed for each trial (both the "
        "Welch estimate above and the Dickson et al. (2022) estimate) and averaged over a session's trials: baseline against the cue "
        "pair (20 s), baseline against cue 1 and against cue 2 (10 s), the last 2 s of cue 1 against the first 2 s of cue 2, cue 1 "
        "against cue 2, the trials against randomly drawn free-period segments of the same length (seeded, so the same segments are "
        "used every time), power in each region, and four checks expected to show nothing (cues sorted by sound rather than by their "
        "place in the pair). Each was a linear mixed model of Session × Phase × Pair with a random intercept for rat; follow-up measures "
        "(phase-lag index, imaginary coherence, Granger causality, amplitude cross-correlation lag and phase–amplitude coupling) were "
        "computed only where a comparison changed. A standalone script, using only NumPy and SciPy, reads the recordings independently "
        "and reproduces every value of these comparisons.",
        "In the figures of those comparisons, each network graph was tested against three nulls: within each session, each trial's two "
        "windows were swapped at random 10,000 times; every combination of sign flips of the rats' changes; and fake trials drawn from "
        "the same rats' free-period recordings."]))
    S.append(("Software", [
        "Analyses were carried out in Python %s with NumPy %s, SciPy %s, pandas %s, statsmodels %s, FOOOF %s and matplotlib %s. Figures "
        "were drawn at Nature's dimensions (183 mm wide) with every panel of a kind on a common axis across region pairs, regions and the "
        "sets of rats." % tuple(versions.get(k, "") for k in ("python", "numpy", "scipy", "pandas", "statsmodels", "fooof", "matplotlib"))]))
    S.append(("References", [
        "Benjamini Y, Hochberg Y (1995) Controlling the false discovery rate: a practical and powerful approach to multiple testing. J R Stat Soc B 57:289–300.",
        "DerSimonian R, Laird N (1986) Meta-analysis in clinical trials. Control Clin Trials 7:177–188.",
        "Dhamala M, Rangarajan G, Ding M (2008) Analyzing information flow in brain networks with nonparametric Granger causality. NeuroImage 41:354–362.",
        "Dickson CR, Holmes GL, Barry JM (2022) eNeuro 9(2):ENEURO.0414-21.2022. [Full title to be added.]",
        "Donoghue T, Haller M, Peterson EJ, et al. (2020) Parameterizing neural power spectra into periodic and aperiodic components. Nat Neurosci 23:1655–1665.",
        "Geweke J (1982) Measurement of linear dependence and feedback between multiple time series. J Am Stat Assoc 77:304–313.",
        "Hartung J, Knapp G (2001) A refined method for the meta-analysis of controlled clinical trials with binary outcome. Stat Med 20:3875–3889.",
        "Liang KY, Zeger SL (1986) Longitudinal data analysis using generalized linear models. Biometrika 73:13–22.",
        "Mancl LA, DeRouen TA (2001) A covariance estimator for GEE with improved small-sample properties. Biometrics 57:126–134.",
        "Tort ABL, Komorowski R, Eichenbaum H, Kopell N (2010) Measuring phase-amplitude coupling between neuronal oscillations of different frequencies. J Neurophysiol 104:1195–1210.",
        "Wilson GT (1972) The factorization of matricial spectral densities. SIAM J Appl Math 23:420–426."]))
    return [{"title": t, "paras": ps} for t, ps in S]


def _versions():
    import sys
    import importlib
    out = {"python": sys.version.split()[0]}
    for m in ("numpy", "scipy", "pandas", "statsmodels", "matplotlib", "fooof"):
        try:
            out[m] = importlib.import_module(m).__version__
        except Exception:                                    # noqa: BLE001
            pass
    return out


# --------------------------------------------------------------------------
# All of it
# --------------------------------------------------------------------------
def build(progress=None, sets=None, draw=True):
    """Every set's figures and words. draw=False: the words only, over the
    drawings already on disk (their limits are measured again, nothing is
    redrawn)."""
    say = progress or (lambda s: None)
    sets = sets or [k for k, _s, _d in E.RATSETS]
    every = E.load_days()
    say("power spectra and their components (every rat-day)")
    FT = FS.fooof_tables(FS.power_tables(every))
    data = {}
    for rs in sets:
        say("%s: the data" % E.RATSET_SAY[rs])
        data[rs] = load_set(rs, every, FT)
    state = {"record": True, "lims": {}, "spans": {}, "dir": None}
    recorded = {}
    with E.using_pub(state):
        for rs in sets:
            say("%s: measuring every panel" % E.RATSET_SAY[rs])
            recorded[rs] = draw_set(data[rs])
    drawn = {}
    for rs in sets:
        if not draw:
            drawn[rs] = [dict(f, files={e: "fig_%s.%s" % (f["fid"], e) for e in ("pdf", "png")
                                        if os.path.isfile(_root(rs, "fig_%s.%s" % (f["fid"], e)))}) for f in recorded[rs]]
            continue
        say("%s: drawing" % E.RATSET_SAY[rs])
        import shutil
        shutil.rmtree(_root(rs), ignore_errors=True)
        with E.using_pub(dict(state, record=False, dir=_root(rs))):
            drawn[rs] = draw_set(data[rs])
    bip = None
    bp = _root("bipolar.json")
    if os.path.isfile(bp):
        with open(bp, encoding="utf-8") as fh:
            bip = json.load(fh)
    versions = _versions()
    M = methods(data["all"] if "all" in data else data[sets[0]], _refs_of_recordings(), bip, versions)
    by_set = {}
    for rs in sets:
        D = data[rs]
        D["robust"] = _robust_index(D["EM"], D["FN"])
        figs = [figure_record(f, D) for f in drawn[rs]]
        groups = []
        for key, sec, title in GROUPS:
            fs = [f for f in figs if f["group"] == key]
            if fs:
                groups.append({"key": key, "section": sec, "title": title, "say": GROUP_SAY[key], "figures": fs})
        by_set[rs] = {"rats": D["EM"]["rats"], "left_out": (D["EM"].get("ratset") or {}).get("left_out") or [], "groups": groups,
                      "hits": D["FN"].get("hits")}
    os.makedirs(_root(), exist_ok=True)
    txt = FS.methods_txt(M)
    with open(_root("Methods_for_the_dissertation.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(txt)
    FS.methods_docx(M, _root("Methods_for_the_dissertation.docx"))
    out = {"schema": SCHEMA, "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "versions": versions,
           "sets": [{"key": k, "say": s, "drop": list(d), "file": SET_FILE[k]} for k, s, d in E.RATSETS if k in sets],
           "why": E.RATSET_WHY, "methods": M, "by_set": by_set, "lims": len(state["lims"]) + len(state["spans"])}
    joe._write(_root("pub.json"), out)
    return out


def result():
    p = _root("pub.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    import sys
    from . import monolith as MO
    MO.configure(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "GUI_logs"))
    t0 = time.time()
    # joepub [words] [set ...]: "words" writes the words again over the drawings on disk
    args = sys.argv[1:]
    words = args[:1] == ["words"]
    args = args[1:] if words else args
    o = build(progress=lambda s: print("%5.0f s  %s" % (time.time() - t0, s), flush=True), sets=args or None, draw=not words)
    print("%d sets, %d figures, %d shared axes, %.0f s" % (len(o["by_set"]), sum(len(g["figures"]) for v in o["by_set"].values()
                                                                                    for g in v["groups"]), o["lims"], time.time() - t0))
