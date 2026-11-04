"""
joestats.py -- each publication figure's statistics, laid out the way SPSS
prints them (Shahriar for Joe, 2026-11-04), one PDF a figure:

  1. the design, e.g. "2 (Session: Early or Late) x 3 (Period) generalized
     estimating equation", with its family, link, working correlation and
     the rats in it;
  2. every main effect and interaction, significant or not: Wald chi-square,
     df, p and, for a test that belongs to a corrected family, the
     Benjamini-Hochberg q;
  3. the follow-ups of every interaction with Session that reaches p < .05
     (the Session effect at each level of the other factor, or the same
     model in each pair or region), Bonferroni-adjusted within each set;
  4. a results paragraph in Joe's register (his conditioning paragraph is
     the template): what the figure shows and how it was averaged, the
     design, the significant effects with their statistics, the rest, the
     post hoc tests, and one sentence of interpretation.

Tables 2 come from tabs 11 and 12's own results, untouched; the effects
(ratios, dB) and the follow-ups are fitted here on the same rows, through
the same GEE. The paragraph reads significance as the dissertation will:
a test in a corrected family by its q, any other by its p; a key test that
passes only before correction is said so in a sentence of its own.

    figure_stats(f, no, D) -> {"analyses", "paragraph", ...}
    write_pdf(doc, path)
"""
from __future__ import annotations

import math
import os

import numpy as np

from . import evenmore as E
from . import finalstage as FS
from . import joepub as JP

ALPHA = E.ALPHA
BAND_RANGE = {"theta": "5–12 Hz", "gamma": "30–90 Hz"}
PERIOD_WORD = {"1 baseline": "baseline", "2 cue 1": "cue 1", "3 cue 2": "cue 2"}
CUE_WORD = {"cue1": "cue 1", "cue2": "cue 2"}
DAY_WORD = {"Precon1": "Early (Precon1)", "Precon4": "Late (Precon4)"}
SESSION = "2 (Session: Early or Late)"
PERIOD = "3 (Period: baseline, cue 1 or cue 2)"
CUE = "2 (Cue: cue 1 or cue 2)"
MODEL = {"gamma": "Gamma family, log link", "normal": "Normal family, identity link"}
ERRORS = ("Tests of up to 2 df use robust standard errors with the Mancl–DeRouen small-sample correction; larger tests use "
          "model-based standard errors, marked in the table.")


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------
def chi(t):
    return "χ²(%d) = %.2f" % (int(t.get("df") or 1), t["chi2"])


def stat(t, q=True):
    """'χ²(2) = 8.62, p = .013, FDR q = .043'."""
    s = "%s, %s" % (chi(t), JP.fp(t["p"]))
    if q and JP.fq(t.get("q")):
        s += ", FDR " + JP.fq(t["q"])
    return s


def est_say(r, short=False):
    """'ratio Late/Early = 1.32, 95% CI [1.04, 1.67]' (or a difference, in
    dB or the measure's own unit); short, for a table under an 'Estimate
    [95% CI]' header: '1.32 [1.04, 1.67]'."""
    if not r or r.get("est") is None:
        return ""
    if r["kind"] == "ratio":
        if short:
            return "%.2f [%.2f, %.2f]" % (r["est"], r["lo"], r["hi"])
        return "%s = %.2f, 95%% CI [%.2f, %.2f]" % (r.get("ratio_say") or "ratio", r["est"], r["lo"], r["hi"])
    sg = lambda v: ("%+.2f" % v).replace("-", "−")      # noqa: E731
    u = r.get("unit", "dB")
    u = (" " + u) if u else ""
    if short:
        return "%s%s [%s, %s]" % (sg(r["est"]), u, sg(r["lo"]), sg(r["hi"]))
    return "%s = %s%s, 95%% CI [%s, %s]" % (r.get("diff_say") or "difference", sg(r["est"]), u, sg(r["lo"]), sg(r["hi"]))


def sig(t):
    """Significant on the paragraph's reading: by q where the test is
    corrected, by p where it is not."""
    if not t or t.get("p") is None:
        return False
    q = t.get("q")
    return q < ALPHA if q is not None else t["p"] < ALPHA


def raw(t):
    return bool(t) and t.get("p") is not None and t["p"] < ALPHA


def _join(xs, last="and", sep=", "):
    """'a, b and c'; items that carry statistics (commas of their own) are
    joined 'a, and b' / 'a; b; and c' so each stays whole."""
    xs = [x for x in xs if x]
    if len(xs) <= 1:
        return "".join(xs)
    if len(xs) == 2:
        return xs[0] + " " + last + " " + xs[1]
    if any("," in x for x in xs):
        return "; ".join(xs[:-1]) + "; " + last + " " + xs[-1]
    return sep.join(xs[:-1]) + (sep if len(xs) > 2 else " ") + last + " " + xs[-1]


def _hz(f):
    return ("%.2f Hz" % f) if f < 20 else ("%g Hz" % f)


# --------------------------------------------------------------------------
# Fits: the same GEE as the tabs, on the same rows
# --------------------------------------------------------------------------
def _coef(res, name, fam, scale=1.0):
    names = list(res.params.index)
    i = names.index(name)
    b = float(res.params.iloc[i]) * scale
    se = float(math.sqrt(np.asarray(res.cov_robust_bc)[i, i])) * abs(scale)
    x = (b / se) ** 2 if se > 0 else float("nan")
    tr = math.exp if fam == "gamma" else (lambda v: v)
    return {"est": tr(b), "lo": tr(b - 1.959964 * se), "hi": tr(b + 1.959964 * se), "chi2": x, "df": 1,
            "p": E._chi2_sf(x, 1) if np.isfinite(x) else None, "kind": "ratio" if fam == "gamma" else "diff",
            "ratio_say": "ratio Late/Early", "diff_say": "Late − Early"}


def late_early(df, fam):
    """Late vs Early on these rows alone: y ~ Session."""
    res = E.gee(df, "y ~ C(day, Treatment('Precon1'))", fam)
    return _coef(res, next(n for n in res.params.index if "Precon4" in n), fam)


def session_in(df, formula, fam):
    """Late - Early averaged over the model's other factors: the Session
    coefficient of a sum-coded model (Precon1 is +1, so the change is -2b)."""
    res = E.gee(df, formula, fam)
    name = next(n for n in res.params.index if n.startswith("C(day, Sum)") and ":" not in n)
    return _coef(res, name, fam, scale=-2.0)


def cue2_cue1(df):
    """Cue 2 vs cue 1 on these rows alone (one session's): y ~ Cue."""
    res = E.gee(df, "y ~ C(cue, Treatment('cue1'))", "gamma")
    return _coef(res, next(n for n in res.params.index if "cue2" in n), "gamma")


def term_of(df, formula, fam, name):
    t = next((t for t in E.terms(E.gee(df, formula, fam)) if t["term"] == name), None)
    return dict(t) if t else None


def _try(fn, *a):
    try:
        return fn(*a), None
    except Exception as exc:                                  # noqa: BLE001
        return None, "%s" % exc


def bonferroni(rows):
    ps = [r for r in rows if r.get("p") is not None]
    for r in ps:
        r["padj"] = min(1.0, r["p"] * len(ps))
    return rows


# --------------------------------------------------------------------------
# The pieces of a statistics page
# --------------------------------------------------------------------------
def term_rows(ts, q_of=None, family=None, est=None):
    """Stored terms -> rows: source, chi2, df, p, q, errors (and an effect
    for Session where one was fitted)."""
    out = []
    for t in ts or []:
        if t.get("p") is None:
            continue
        r = {"source": t["term"], "chi2": t["chi2"], "df": int(t["df"]), "p": t["p"], "q": (q_of or {}).get(t["term"]),
             "errors": "model-based" if t.get("errors") == E.NAIVE else "robust", "family": family if (q_of or {}).get(t["term"]) is not None else None}
        if est and t["term"] == "Session":
            r["effect"] = est
        out.append(r)
    return out


def followup(title, gate, rows, level_word, unit=False, note=None, sub="Session", measure=None):
    """A set of post hoc tests: why (the interaction that opened it), each
    comparison, Bonferroni within the set. `sub`: what each one tests (the
    Session effect, or a smaller interaction in each pair or region);
    `measure`: what it is measured on, where not the figure's."""
    return {"title": title, "gate": gate, "rows": bonferroni(rows), "level_word": level_word, "unit": unit, "note": note,
            "sub": sub, "measure": measure,
            "correction": "Bonferroni-adjusted across the %d comparisons" % len([r for r in rows if r.get("p") is not None])}


def _levels(df, col, word, fit):
    """The Session effect at each level of `col`: fit(sub) -> effect row."""
    rows = []
    for lv in sorted(df[col].unique()):
        got, err = _try(fit, df[df[col] == lv])
        rows.append(dict(got or {"error": err}, what=word(lv)))
    return rows


def _bins_word(dfb):
    hz = dict(zip(dfb["f"], dfb["hz"]))
    return lambda f: _hz(hz[f])


def analysis(title, design, dv, fam, rats, terms, family=None, planned=None, followups=(), extra=None, units=None, per=None):
    """`units`: each pair's or region's own test that a pooled figure stars
    (their own models, corrected across the pairs or regions). `per`: the
    model is fitted separately for each region pair or region."""
    return {"title": title, "design": design + " generalized estimating equation", "dv": dv, "per": per,
            "model": "%s; exchangeable working correlation; rat as the cluster (n = %d rats). %s" % (MODEL[fam], len(rats), ERRORS),
            "fam": fam, "n": len(rats), "rats": list(rats), "terms": terms, "family": family, "planned": planned,
            "followups": [x for x in followups if x], "extra": extra or [], "units": units or []}


# --------------------------------------------------------------------------
# Each kind of figure
# --------------------------------------------------------------------------
def _rows(D, key, fn):
    c = D.setdefault("_rows", {})
    if key not in c:
        c[key] = fn()
    return c[key]


def _frame(rows, pair=None, finite=False):
    df = E._frame(rows)
    if pair is not None:
        df = df[df["pair"] == "p%02d" % pair]
    if finite:
        df = df[np.isfinite(df["y"]) & (df["y"] > 0)]
    return df.reset_index(drop=True)


def _p1(D, band):
    return _rows(D, ("p1", band), lambda: E.rows_phase1(D["T"], band))


def _p2(D, band):
    return _rows(D, ("p2", band), lambda: E.rows_phase2(D["T"], band))


def _p3(D, band):
    return _rows(D, ("p3", band), lambda: E.rows_phase3(D["T"], band))


def _pow(D, band, region):
    ri = FS.REGIONS.index(region)
    x = next(z for z in D["FN"]["power"][band] if z and z["region"] == region)
    return _rows(D, ("pow", band, region), lambda: FS.power_rows(D["PT"], band, ri, x["rats"]))


def _gate(t, name):
    return {"name": name, "chi2": t["chi2"], "df": t["df"], "p": t["p"], "q": t.get("q")}


def _find(rows, name):
    return next((r for r in rows if r["source"] == name), None)


def coh_pair1(D, band, p):
    B = next(x for x in D["EM"]["bands"] if x["band"] == band)
    st = B["phase1"]["pairs"][p]
    _keep, rows, rows_b = _p1(D, band)
    df, dfb = _frame(rows, p), _frame(rows_b, p, finite=True)
    a2 = st.get("a2") or {}
    eff, _e = _try(late_early, df, "gamma")
    A1 = analysis("Late vs Early on band coherence", SESSION, "band-averaged coherence", "gamma", st["rats"],
                  [{"source": "Session", "chi2": a2.get("chi2"), "df": 1, "p": a2.get("p"), "q": a2.get("q"), "errors": "robust",
                    "family": "pairs", "effect": eff}] if a2.get("p") is not None else [], family="pairs")
    nb = int(dfb["f"].nunique()) if len(dfb) else 0
    t2 = term_rows(st.get("b2"), {"Session × Frequency": st.get("b2_q")}, "pairs")
    fu = []
    sf = _find(t2, "Session × Frequency")
    if raw(sf):
        fu.append(followup("Session × Frequency: Late vs Early in each frequency bin", _gate(sf, "Session × Frequency"),
                           _levels(dfb, "f", _bins_word(dfb), lambda s: late_early(s, "gamma")), "frequency bin"))
    A2 = analysis("Coherence across frequency bins", "%s × %d (Frequency: %s)" % (SESSION, nb, JP.BAND_BINS[band]),
                  "coherence in each frequency bin", "gamma", st["rats"], t2, family="pairs", followups=fu)
    return [A1, A2]


def coh_pool1(D, band):
    B = next(x for x in D["EM"]["bands"] if x["band"] == band)
    P1 = B["phase1"]
    keep, rows, rows_b = _p1(D, band)
    df, dfb = _frame(rows), _frame(rows_b, finite=True)
    rats = sorted({r for x in P1["pairs"] if x for r in x["rats"]})
    n, nb = len(keep), int(dfb["f"].nunique())
    t1 = term_rows(P1.get("a1"))
    fu1 = []
    sp = _find(t1, "Session × Pair")
    if raw(sp):
        fu1.append(followup("Session × Pair: Late vs Early in each pair", _gate(sp, "Session × Pair"),
                            _levels(df, "pair", lambda c: E.PAIR_SAY[int(c[1:])], lambda s: late_early(s, "gamma")), "pair", unit=True))
    units = []
    for p in keep:
        a2 = P1["pairs"][p].get("a2") or {}
        if a2.get("p") is None:
            continue
        got, _e = _try(late_early, _frame(rows, p), "gamma")
        units.append(dict(got or {}, what="%s: Late vs Early" % E.PAIR_SAY[p], chi2=a2["chi2"], df=1, p=a2["p"], q=a2.get("q"), family="pairs",
                          ratio_say="ratio Late/Early"))
    A1 = analysis("All pairs together, band coherence", "%s × %d (Pair)" % (SESSION, n), "band-averaged coherence", "gamma", rats, t1,
                  followups=fu1, units=units)
    t2 = term_rows(P1.get("b1"))
    fu2 = []
    x = _find(t2, "Session × Pair")
    if raw(x):
        rows_ = []
        for p in keep:
            st = P1["pairs"][p]
            s = next((t for t in st.get("b2") or [] if t["term"] == "Session"), None)
            got, _e = _try(session_in, _frame(rows_b, p, finite=True), "y ~ C(day, Sum) * C(f, Sum)", "gamma")
            rows_.append(dict(got or {}, what=E.PAIR_SAY[p], chi2=(s or {}).get("chi2"), df=1, p=(s or {}).get("p")))
        fu2.append(followup("Session × Pair: the Session effect in each pair's model across frequency bins", _gate(x, "Session × Pair"),
                            rows_, "pair", unit=True))
    x = _find(t2, "Session × Frequency")
    if raw(x):
        fu2.append(followup("Session × Frequency: Late vs Early in each frequency bin (all pairs)", _gate(x, "Session × Frequency"),
                            _levels(dfb, "f", _bins_word(dfb), lambda s: session_in(s, "y ~ C(day, Sum) * C(pair, Sum)", "gamma")),
                            "frequency bin"))
    x = _find(t2, "Session × Pair × Frequency")
    if raw(x):
        rows_ = []
        for p in keep:
            st = P1["pairs"][p]
            s = next((t for t in st.get("b2") or [] if t["term"] == "Session × Frequency"), None)
            rows_.append({"what": E.PAIR_SAY[p], "chi2": (s or {}).get("chi2"), "df": (s or {}).get("df"), "p": (s or {}).get("p")})
        fu2.append(followup("Session × Pair × Frequency: Session × Frequency in each pair", _gate(x, "Session × Pair × Frequency"),
                            rows_, "pair", unit=True, sub="Session × Frequency"))
    A2 = analysis("All pairs together, across frequency bins", "%s × %d (Pair) × %d (Frequency: %s)" % (SESSION, n, nb, JP.BAND_BINS[band]),
                  "coherence in each frequency bin", "gamma", rats, t2, followups=fu2)
    return [A1, A2]


def coh_pair2(D, band, p):
    B = next(x for x in D["EM"]["bands"] if x["band"] == band)
    st = B["phase2"]["pairs"][p]
    _keep, rows = _p2(D, band)
    df = _frame(rows, p)
    eff, _e = _try(session_in, df, "y ~ C(day, Sum) * C(cue, Sum)", "gamma")
    t = term_rows(st.get("terms"), {"Session × Cue": st.get("q")}, "pairs", est=eff)
    fu = []
    sc = _find(t, "Session × Cue")
    if raw(sc):
        within = []
        for d in E.DAYS:
            r = (st.get("days") or {}).get(d) or {}
            got, _e = _try(cue2_cue1, df[df["day"] == d])
            within.append(dict(got or {}, what=DAY_WORD[d], chi2=r.get("chi2"), p=r.get("p"), q=r.get("q"), df=1, ratio_say="ratio cue 2/cue 1"))
        fu.append(followup("Session × Cue: cue 2 vs cue 1 within each session", _gate(sc, "Session × Cue"), within, "session"))
        fu.append(followup("Session × Cue: Late vs Early within each cue", _gate(sc, "Session × Cue"),
                           _levels(df, "cue", lambda c: CUE_WORD[c], lambda s: late_early(s, "gamma")), "cue"))
    return [analysis("Session × Cue", "%s × %s" % (SESSION, CUE), "band-averaged coherence in each cue", "gamma", st["rats"], t,
                     family="pairs", followups=fu)]


def coh_pool2(D, band):
    B = next(x for x in D["EM"]["bands"] if x["band"] == band)
    P2 = B["phase2"]
    keep, rows = _p2(D, band)
    df = _frame(rows)
    rats = sorted({r for x in P2["pairs"] if x for r in x["rats"]})
    t = term_rows(P2.get("omnibus"))
    fu = []
    x = _find(t, "Session × Pair")
    if raw(x):
        rows_ = []
        for p in keep:
            s = next((z for z in P2["pairs"][p].get("terms") or [] if z["term"] == "Session"), None)
            got, _e = _try(session_in, _frame(rows, p), "y ~ C(day, Sum) * C(cue, Sum)", "gamma")
            rows_.append(dict(got or {}, what=E.PAIR_SAY[p], chi2=(s or {}).get("chi2"), df=1, p=(s or {}).get("p")))
        fu.append(followup("Session × Pair: the Session effect in each pair's Session × Cue model", _gate(x, "Session × Pair"), rows_,
                           "pair", unit=True))
    x = _find(t, "Session × Cue")
    if raw(x):
        fu.append(followup("Session × Cue: Late vs Early within each cue (all pairs)", _gate(x, "Session × Cue"),
                           _levels(df, "cue", lambda c: CUE_WORD[c], lambda s: session_in(s, "y ~ C(day, Sum) * C(pair, Sum)", "gamma")),
                           "cue"))
    x = _find(t, "Session × Cue × Pair")
    if raw(x):
        rows_ = []
        for p in keep:
            s = next((z for z in P2["pairs"][p].get("terms") or [] if z["term"] == "Session × Cue"), None)
            rows_.append({"what": E.PAIR_SAY[p], "chi2": (s or {}).get("chi2"), "df": 1, "p": (s or {}).get("p")})
        fu.append(followup("Session × Cue × Pair: Session × Cue in each pair", _gate(x, "Session × Cue × Pair"), rows_, "pair", unit=True,
                           sub="Session × Cue"))
    units = []
    for p in keep:
        x = P2["pairs"][p]
        s = next((z for z in x.get("terms") or [] if z["term"] == "Session × Cue"), None)
        if s and s.get("p") is not None:
            units.append({"what": "%s: Session × Cue" % E.PAIR_SAY[p], "chi2": s["chi2"], "df": 1, "p": s["p"], "q": x.get("q"), "family": "pairs"})
    return [analysis("All pairs together", "%s × %s × %d (Pair)" % (SESSION, CUE, len(keep)), "band-averaged coherence in each cue",
                     "gamma", rats, t, followups=fu, units=units)]


def _planned(contrasts, family, db=False):
    """The three planned 1-df contrasts of Session x Period, as stored."""
    out = []
    for ck, (ca, cb) in JP.CONTRAST_SAY.items():
        c = (contrasts or {}).get(ck) or {}
        if c.get("p") is None:
            continue
        r = {"what": "Session × (%s vs %s)" % (ca, cb), "a": ca, "b": cb, "chi2": c["chi2"], "df": 1, "p": c["p"], "q": c.get("q"),
             "family": family}
        if db and c.get("diff") is not None:
            r.update(est=c["diff"], lo=c["lo"], hi=c["hi"], kind="diff", diff_say="difference of differences")
        elif c.get("ratio") is not None:
            r.update(est=c["ratio"], lo=c["lo"], hi=c["hi"], kind="ratio", ratio_say="ratio of ratios")
        out.append(r)
    return out


def _session_period(title, dv, fam, rats, ts, sp, contrasts, family, df, db=False, other=None):
    """A Session x Period model: its terms, its planned contrasts, and, when
    the interaction reaches p < .05, Late vs Early within each period."""
    formula = "y ~ C(day, Sum) * C(period, Sum)" + (" * C(%s, Sum)" % other if other else "")
    eff, _e = _try(session_in, df, formula, fam)
    t = term_rows(ts, {"Session × Period": (sp or {}).get("q")}, family, est=eff)
    fu = []
    x = _find(t, "Session × Period")
    if raw(x):
        fit = (lambda s: session_in(s, "y ~ C(day, Sum) * C(%s, Sum)" % other, fam)) if other else (lambda s: late_early(s, fam))
        fu.append(followup("Session × Period: Late vs Early within each period", _gate(x, "Session × Period"),
                           _levels(df, "period", lambda c: PERIOD_WORD[c], fit), "period"))
    return analysis(title, "%s × %s" % (SESSION, PERIOD), dv, fam, rats, t, family=family,
                    planned=_planned(contrasts, family, db) if contrasts else None, followups=fu)


def coh_pair3(D, band, p):
    B = next(x for x in D["EM"]["bands"] if x["band"] == band)
    st = B["phase3"]["pairs"][p]
    _keep, rows = _p3(D, band)
    return [_session_period("Session × Period", "band-averaged coherence in each 10-s window", "gamma", st["rats"], st.get("terms"),
                            st.get("sp"), st.get("contrasts"), "pairs", _frame(rows, p))]


def coh_pool3(D, band):
    B = next(x for x in D["EM"]["bands"] if x["band"] == band)
    per = [x for x in B["phase3"]["pairs"] if x]
    rats = sorted({r for x in per for r in x["rats"]})
    t = [{"source": E.PAIR_SAY[x["pair"]] + ": Session × Period", "chi2": x["sp"]["chi2"], "df": x["sp"]["df"], "p": x["sp"]["p"],
          "q": x["sp"].get("q"), "errors": "robust", "family": "pairs", "pair": x["pair"]} for x in per if x.get("sp")]
    planned = []
    for x in per:
        for r in _planned(x.get("contrasts"), "pairs"):
            planned.append(dict(r, what="%s: %s" % (E.PAIR_SAY[x["pair"]], r["what"]), pair=x["pair"]))
    return [analysis("Session × Period in each pair", "%s × %s" % (SESSION, PERIOD), "band-averaged coherence in each 10-s window",
                     "gamma", rats, t, family="pairs", planned=planned, per="region pair")]


def power_region(D, band, region):
    x = next(z for z in D["FN"]["power"][band] if z and z["region"] == region)
    rows, rb = _pow(D, band, region)
    df, dfb = E._frame(rows), E._frame(rb)
    A1 = _session_period("Tier 3a: Session × Period on band power", "band power (dB) in each 10-s window", "normal", x["rats"], x.get("e1"),
                         x.get("sp"), x.get("contrasts"), "regions10", df, db=True)
    t2 = term_rows(x.get("e2"), {"Session × Period × Frequency": (x.get("spf") or {}).get("q")}, "regions10")
    fu = []
    y = _find(t2, "Session × Frequency")
    if raw(y):
        fu.append(followup("Session × Frequency: Late vs Early in each frequency bin", _gate(y, "Session × Frequency"),
                           _levels(dfb, "f", _bins_word(dfb), lambda s: session_in(s, "y ~ C(day, Sum) * C(period, Sum)", "normal")),
                           "frequency bin"))
    y = _find(t2, "Session × Period × Frequency")
    if raw(y):
        rows_ = []
        word = _bins_word(dfb)
        for f in sorted(dfb["f"].unique()):
            got, err = _try(term_of, dfb[dfb["f"] == f], "y ~ C(day, Sum) * C(period, Sum)", "normal", "Session × Period")
            rows_.append(dict(got or {"error": err}, what=word(f)))
        fu.append(followup("Session × Period × Frequency: Session × Period in each frequency bin", _gate(y, "Session × Period × Frequency"),
                           rows_, "frequency bin", sub="Session × Period"))
    y = _find(t2, "Session × Period")
    if raw(y):
        fu.append(followup("Session × Period: Late vs Early within each period (all bins)", _gate(y, "Session × Period"),
                           _levels(dfb, "period", lambda c: PERIOD_WORD[c], lambda s: session_in(s, "y ~ C(day, Sum) * C(f, Sum)", "normal")),
                           "period"))
    nb = int(dfb["f"].nunique()) if len(dfb) else 0
    A2 = analysis("Tier 3b: Session × Period × Frequency", "%s × %s × %d (Frequency: %s)" % (SESSION, PERIOD, nb, JP.BAND_BINS[band]),
                  "power (dB) in each frequency bin and window", "normal", x["rats"], t2, family="regions10", followups=fu)
    return [A1, A2]


def power_all(D, band):
    per = [z for z in D["FN"]["power"][band] if z]
    T_ = D["FN"]["tiers"][band]
    rows = [r for z in per for r in _pow(D, band, z["region"])[0]]
    rb = [r for z in per for r in _pow(D, band, z["region"])[1]]
    df, dfb = E._frame(rows), E._frame(rb)
    out = []
    for tier, title, data in (("t1", "Tier 1: every region in one model, band power", df), ("t2", "Tier 2: every region, across frequency bins", dfb)):
        X = T_.get(tier) or {}
        key = X.get("key") or {}
        t = term_rows(X.get("terms"), {k: v.get("q") for k, v in key.items()}, "bands")
        extra = []
        for name, k in key.items():
            lm = k.get("lmm") or {}
            if lm.get("p") is not None:
                extra.append("Linear mixed model, %s: F(%d, %d) = %.2f, %s%s." % (name, lm["df1"], lm["df2"], lm["F"], JP.fp(lm["p"]),
                                                                                  (", FDR " + JP.fq(lm["q"])) if JP.fq(lm.get("q")) else ""))
        fu = []
        y = _find(t, "Session × Region")
        if raw(y):
            rows_ = []
            for z in per:
                s = next((u for u in (z.get("e1") if tier == "t1" else z.get("e2")) or [] if u["term"] == "Session"), None)
                got = None
                if tier == "t1":
                    got, _e = _try(session_in, E._frame(_pow(D, band, z["region"])[0]), "y ~ C(day, Sum) * C(period, Sum)", "normal")
                rows_.append(dict(got or {}, what=FS.REGION_SAY[z["region"]], chi2=(s or {}).get("chi2"), df=1, p=(s or {}).get("p")))
            fu.append(followup("Session × Region: the Session effect in each region's own model", _gate(y, "Session × Region"), rows_,
                               "region", unit=True))
        y = _find(t, "Session × Period")
        if raw(y):
            f_ = "y ~ C(day, Sum) * C(region, Sum)" + (" * C(f, Sum)" if tier == "t2" else "")
            fu.append(followup("Session × Period: Late vs Early within each period (all regions)", _gate(y, "Session × Period"),
                               _levels(data, "period", lambda c: PERIOD_WORD[c], lambda s: session_in(s, f_, "normal")), "period"))
        y = _find(t, "Session × Period × Region")
        if raw(y):
            # each region's own Session x Period: tier 3a's for tier 1, the per-bin model's (tier 3b) for tier 2
            rows_ = []
            for z in per:
                s = (z.get("sp") or {}) if tier == "t1" else next((u for u in z.get("e2") or [] if u["term"] == "Session × Period"), None) or {}
                rows_.append({"what": FS.REGION_SAY[z["region"]], "chi2": s.get("chi2"), "df": 2, "p": s.get("p")})
            fu.append(followup("Session × Period × Region: Session × Period in each region", _gate(y, "Session × Period × Region"), rows_,
                               "region", unit=True, sub="Session × Period"))
        if tier == "t2":
            for name, sub in (("Session × Frequency", "Session"), ("Session × Period × Frequency", "Session × Period")):
                y = _find(t, name)
                if raw(y):
                    rows_ = []
                    word = _bins_word(dfb)
                    for f in sorted(dfb["f"].unique()):
                        s_ = dfb[dfb["f"] == f]
                        if sub == "Session":
                            got, err = _try(session_in, s_, "y ~ C(day, Sum) * C(period, Sum) * C(region, Sum)", "normal")
                        else:
                            got, err = _try(term_of, s_, "y ~ C(day, Sum) * C(period, Sum) * C(region, Sum)", "normal", sub)
                        rows_.append(dict(got or {"error": err}, what=word(f)))
                    fu.append(followup("%s: %s in each frequency bin (all regions)" % (name, sub if sub != "Session" else "Late vs Early"),
                                       _gate(y, name), rows_, "frequency bin", sub=sub))
            for name, sub, key_ in (("Session × Region × Frequency", "Session × Frequency", "e2"),
                                    ("Session × Period × Region × Frequency", "Session × Period × Frequency", "e2")):
                y = _find(t, name)
                if raw(y):
                    rows_ = []
                    for z in per:
                        s = next((u for u in z.get(key_) or [] if u["term"] == sub), None)
                        rows_.append({"what": FS.REGION_SAY[z["region"]], "chi2": (s or {}).get("chi2"), "df": (s or {}).get("df"),
                                      "p": (s or {}).get("p")})
                    fu.append(followup("%s: %s in each region" % (name, sub), _gate(y, name), rows_, "region", unit=True, sub=sub))
        nb = int(dfb["f"].nunique()) if len(dfb) else 0
        design = "%s × %s × %d (Region)" % (SESSION, PERIOD, len(per)) + ("" if tier == "t1" else " × %d (Frequency: %s)" % (nb, JP.BAND_BINS[band]))
        units = []
        if tier == "t1":
            for z in per:
                rs_ = FS.REGION_SAY[z["region"]]
                sp = z.get("sp") or {}
                if sp.get("p") is not None:
                    units.append({"what": "%s: Session × Period" % rs_, "chi2": sp["chi2"], "df": 2, "p": sp["p"], "q": sp.get("q"), "family": "regions10"})
                for r in _planned(z.get("contrasts"), "regions10", db=True):
                    units.append(dict(r, what="%s: %s" % (rs_, r["what"])))
        out.append(analysis(title, design, "band power (dB)" if tier == "t1" else "power (dB) in each frequency bin", "normal",
                            X.get("rats") or [], t, family="bands", followups=fu, extra=extra, units=units))
    return out


def fooof_all(D):
    FM = D["FN"]["fooof"]
    out = []
    for key, say, unit in FS.FOOOF_PARAMS:
        t, fu, rats = [], [], set()
        for x in FM.get(key) or []:
            if x.get("error") or not x.get("terms"):
                continue
            rs = FS.REGION_SAY[x["region"]]
            rats |= set(x["rats"])
            for u in term_rows(x["terms"], {"Session × Period": (x.get("sp") or {}).get("q")}, "regions5"):
                t.append(dict(u, source="%s: %s" % (rs, u["source"])))
            sp = dict(x.get("sp") or {}, chi2=(x.get("sp") or {}).get("chi2"))
            if raw(sp):
                # FT holds every rat: the set's own rats only
                df = E._frame([r for r in FS.fooof_rows(D["FT"], key, x["region"]) if r["rat"] in x["rats"]])
                fu.append(followup("%s, Session × Period: Late vs Early within each period" % rs, _gate(dict(sp, df=2), "Session × Period"),
                                   _levels(df, "period", lambda c: PERIOD_WORD[c], lambda s: dict(late_early(s, "normal"), unit=unit)), "period",
                                   measure="the %s in %s" % (say.lower(), rs)))
        out.append(analysis(say, "%s × %s" % (SESSION, PERIOD), "the %s%s" % (say.lower(), " (%s)" % unit if unit else ""),
                            "normal", sorted(rats), t, family="regions5", followups=fu, per="region"))
    return out


def granger_pair(D, x):
    df = E._frame(x["rows"])
    out = []
    planned = []
    for k, (s1, s2) in (("ab", (x["a"], x["b"])), ("ba", (x["b"], x["a"]))):
        t = x.get(k) or {}
        if t.get("p") is None:
            continue
        got, _e = _try(late_early, df[df["dir"] == ("a to b" if k == "ab" else "b to a")], "gamma")
        planned.append(dict(got or {}, what="%s → %s: Late vs Early" % (s1, s2), chi2=t["chi2"], df=1, p=t["p"], q=t.get("q"),
                            family="granger", ratio_say="ratio Late/Early"))
    ts, _e = _try(lambda: E.terms(E.gee(df, "y ~ C(day, Sum) * C(dir, Sum)")))
    terms = []
    for u in ts or []:
        terms.append({"source": u["term"], "chi2": u["chi2"], "df": int(u["df"]), "p": u["p"],
                      "q": (x.get("sd") or {}).get("q") if u["term"] == "Session × Direction" else None, "errors": "robust",
                      "family": "granger" if u["term"] == "Session × Direction" and (x.get("sd") or {}).get("q") is not None else None})
    fu = []
    sd = _find(terms, "Session × Direction")
    if raw(sd):
        fu.append(followup("Session × Direction: Late vs Early in each direction", _gate(sd, "Session × Direction"),
                           [dict(r, what=r["what"].split(":")[0]) for r in planned], "direction"))
    A = analysis("Granger causality", "%s × 2 (Direction: %s → %s or %s → %s)" % (SESSION, x["a"], x["b"], x["b"], x["a"]),
                 "band-averaged Granger causality", "gamma", x["rats"], terms, family="granger", planned=planned, followups=fu)
    return [A]


def pac_region(D, x):
    df = E._frame(x["rows"])
    t = x.get("le") or {}
    got, _e = _try(late_early, df, "gamma")
    return [analysis("Late vs Early", SESSION, "the modulation index", "gamma", x["rats"],
                     [{"source": "Session", "chi2": t.get("chi2"), "df": 1, "p": t.get("p"), "q": t.get("q"), "errors": "robust",
                       "family": "pac", "effect": got}] if t.get("p") is not None else [], family="pac")]


# --------------------------------------------------------------------------
# The paragraph, in Joe's register
# --------------------------------------------------------------------------
def _term_say(r):
    s = "%s, %s" % (r["source"], stat(r))
    if r.get("effect") and r["effect"].get("est") is not None:
        s += ", " + est_say(r["effect"])
    return s


def _pa(r):
    """A post hoc test's adjusted p, as SPSS prints it under Sig. (and the
    test's own FDR q, where it has one)."""
    s = "adjusted " + JP.fp(r["padj"])
    return s + (", FDR " + JP.fq(r["q"]) if JP.fq(r.get("q")) else "")


def ph_sig(r):
    """A post hoc test passes: adjusted p < .05, and its own q too where the
    same test is also corrected across pairs or regions."""
    return r.get("padj") is not None and r["padj"] < ALPHA and (r.get("q") is None or r["q"] < ALPHA)


def _higher(r):
    return (r.get("kind") == "ratio" and r["est"] > 1) or (r.get("kind") == "diff" and r["est"] > 0)


def _floor(rs):
    m = min(r["padj"] for r in rs)
    return "all adjusted p > .999" if m > 0.999 else "all adjusted p ≥ " + ("%.3f" % m).lstrip("0")


def _say_followup(F, measure):
    """'Post hoc pairwise comparisons with Bonferroni correction revealed ...'"""
    measure = F.get("measure") or measure
    rows = [r for r in F["rows"] if r.get("padj") is not None]
    if not rows:
        return ""
    hit = [r for r in rows if ph_sig(r)]
    miss = [r for r in rows if not ph_sig(r)]
    why, lw = F["gate"]["name"], F["level_word"]
    if F["unit"] or F.get("sub", "Session") != "Session" or any(r.get("est") is None for r in hit):
        what = "the Session effect" if F.get("sub", "Session") == "Session" else "the %s interaction" % F["sub"]

        def one(r):
            return "%s (%s)" % (r["what"], ", ".join(x for x in (est_say(r), chi(r), _pa(r)) if x))
        head = "Following the %s interaction, %s, tested in each %s with Bonferroni correction," % (why, what, lw)
        if not hit:
            return "%s was not significant in any %s (%s)." % (head, lw, _floor(rows))
        s = "%s was significant in %s" % (head, _join([one(r) for r in hit]))
        if not miss:
            return s + "."
        return s + ", but not in the other %ss (%s)." % (lw, _floor(miss) if len(miss) > 3 else "; ".join("%s: %s" % (r["what"], _pa(r)) for r in miss))
    if lw == "session":
        def one(r):
            return "%s sessions (%s, %s)" % (r["what"].split(" (")[0], est_say(r), _pa(r))
        if hit:
            s = "Post hoc pairwise comparisons with Bonferroni correction revealed that %s differed between cue 2 and cue 1 in %s" % (
                measure, _join([one(r) for r in hit]))
            return s + (", but not in %s sessions (%s)." % (miss[0]["what"].split(" (")[0], _pa(miss[0])) if miss else ".")
        return ("Post hoc pairwise comparisons with Bonferroni correction revealed no difference in %s between cue 2 and cue 1 in either "
                "session (%s)." % (measure, "; ".join("%s: %s" % (r["what"].split(" (")[0], _pa(r)) for r in rows)))
    pre = "during" if lw in ("period", "cue") else "in"

    def loc(r):
        if lw == "frequency bin":
            return "the %s bin" % r["what"]
        return "the baseline" if r["what"] == "baseline" else r["what"]
    if hit:
        parts = []
        for grp, word in (([r for r in hit if _higher(r)], "higher"), ([r for r in hit if not _higher(r)], "lower")):
            if grp:
                parts.append("%s in Late than in Early sessions %s %s" % (word, pre, _join(["%s (%s, %s)" % (loc(r), est_say(r), _pa(r)) for r in grp])))
        s = "Post hoc pairwise comparisons with Bonferroni correction revealed that %s was %s" % (measure, ", and ".join(parts))
        if not miss:
            return s + "."
        if len(miss) > 3:
            return s + ", but did not differ in the other %ss (%s)." % (lw, _floor(miss))
        return s + ", but did not differ %s %s." % (pre, _join(["%s (%s)" % (loc(r), _pa(r)) for r in miss], "or"))
    if len(rows) > 3:
        return ("Post hoc pairwise comparisons with Bonferroni correction revealed no difference in %s between Late and Early sessions in "
                "any %s (%s)." % (measure, lw, _floor(rows)))
    return ("Post hoc pairwise comparisons with Bonferroni correction revealed no difference in %s between Late and Early sessions %s any "
            "%s (%s)." % (measure, pre, lw, "; ".join("%s: %s" % (r["what"].capitalize() if lw == "period" else r["what"], _pa(r)) for r in rows)))


def _say_planned(P, measure, family):
    if not P:
        return ""
    hit = [r for r in P if sig(r)]
    miss = [r for r in P if not sig(r)]

    def one(r):
        return "%s relative to %s (%s, %s)" % (r["a"], r["b"], est_say(r), stat(r))
    if hit:
        s = "Planned contrasts showed that the change in %s from Early to Late sessions differed for %s" % (measure, _join([one(r) for r in hit]))
        return s + (", but not for %s." % _join(["%s relative to %s (%s)" % (r["a"], r["b"], stat(r)) for r in miss], "or") if miss else ".")
    return ("Planned contrasts of the change from Early to Late sessions (%s) were not significant after correction across %s."
            % ("; ".join("%s vs %s, %s" % (r["a"], r["b"], stat(r)) for r in P), family))


def _say_planned_pairs(P, family):
    """p3pool: the pairs' planned contrasts that pass, the figure's stars."""
    hit = [r for r in P if sig(r)]
    if not hit:
        return "No planned contrast was significant after correction across %s." % family
    return "Planned contrasts were significant after correction across %s for %s." % (family, _join(
        ["%s, %s relative to %s (%s, %s)" % (r["what"].split(":")[0], r["a"], r["b"], est_say(r), stat(r)) for r in hit]))


def _say_directions(P):
    """Granger: Late vs Early in each direction, the figure's own tests."""
    def one(r):
        stats_ = ", ".join(x for x in (est_say(r), stat(r)) if x) + ("" if r.get("q") is not None else ", uncorrected")
        return "from %s (%s)" % (r["what"].split(":")[0].replace(" → ", " to "), stats_)
    hit = [r for r in P if sig(r)]
    miss = [r for r in P if not sig(r)]
    if not hit:
        s = "Granger causality did not differ between Late and Early sessions in either direction: %s." % "; ".join(one(r) for r in P)
    else:
        parts = ["%s in Late than in Early sessions %s" % ("higher" if _higher(r) else "lower", one(r)) if r.get("est") is not None
                 else "different in Late and Early sessions %s" % one(r) for r in hit]
        s = "Granger causality was " + "; and ".join(parts) + ("; it did not differ %s." % one(miss[0]) if miss else ".")
    if any(r.get("q") is None for r in P):
        s += (" These Granger tests are uncorrected: the pair's coherence changed only before correction, so it lies outside the corrected "
              "Granger family.")
    return s


def _uncorrected_only(A, family):
    out = []
    for r in A["terms"]:
        if r.get("q") is None or not raw(r) or sig(r):
            continue
        unit, _c, term = r["source"].rpartition(": ")
        if term == "Session":
            what = "the difference between Late and Early sessions"
        elif "×" in term:
            what = "the %s interaction" % term
        else:
            what = "the effect of %s" % term
        what = ("In %s, %s" % (unit, what)) if unit else what[0].upper() + what[1:]
        out.append("%s reached significance before correction (%s, %s) but not after correction across %s (%s)."
                   % (what, chi(r), JP.fp(r["p"]), family, JP.fq(r["q"])))
    return out


def _effect_phrase(term):
    return ("a %s interaction" % term) if "×" in term else ("a main effect of %s" % term)


def say_analysis(A, measure):
    fam = JP.FAMILY.get(A.get("family") or "", "the family of tests")
    terms = [r for r in A["terms"] if r.get("p") is not None]
    hit = [r for r in terms if sig(r)]
    miss = [r for r in terms if not sig(r)]
    out = []
    if A["title"] == "Granger causality" and A.get("planned"):
        out.append(_say_directions(A["planned"]))
    lead = "A %s on %s" % (A["design"], A["dv"]) + (", fitted separately for each %s," % A["per"] if A.get("per") else "")
    if terms and A.get("per"):
        # one model a pair or region: each effect that reached significance, and where
        if hit:
            by = {}
            for r in hit:
                unit, _c, term = r["source"].rpartition(": ")
                by.setdefault(term, []).append("%s (%s)" % (unit, stat(r)))
            inner = lambda us: us[0] if len(us) == 1 else ", ".join(us[:-1]) + " and " + us[-1]      # noqa: E731
            out.append("%s found %s. No other effect was significant." % (lead, _join(
                ["%s in %s" % (_effect_phrase(term), inner(us)) for term, us in by.items()])))
        else:
            out.append("%s found no significant effect in any %s." % (lead, A["per"]))
    elif len(terms) == 1:
        r = terms[0]
        out.append("%s revealed %s effect of %s (%s)." % (lead, "a significant" if hit else "no significant", r["source"], _term_say(r).split(", ", 1)[1]))
    elif terms:
        mains = [r for r in hit if "×" not in r["source"]]
        inters = [r for r in hit if r not in mains]
        if hit:
            s = lead + " revealed "
            if mains:
                s += "a main effect of " + _join([_term_say(r) for r in mains])
            if inters:
                s += (", as well as " if mains else "") + ("a significant %s interaction, %s" % (inters[0]["source"], stat(inters[0])) if len(inters) == 1
                                                           else "significant interactions of " + _join(["%s, %s" % (r["source"], stat(r)) for r in inters]))
            out.append(s + ".")
            if miss:
                out.append("The analysis found no other significant effects (%s)." % "; ".join(_term_say(r) for r in miss))
        else:
            out.append("%s revealed no significant effects (%s)." % (lead, "; ".join(_term_say(r) for r in miss)))
    out += _uncorrected_only(A, fam)
    if A.get("planned") and A["title"] != "Granger causality":
        out.append(_say_planned_pairs(A["planned"], fam) if A.get("per") else _say_planned(A["planned"], measure, fam))
    for F in A["followups"]:
        if sig(F["gate"]):
            out.append(_say_followup(F, measure))
    if A.get("units"):
        out.append(_say_units(A["units"]))
    return [x for x in out if x]


def _say_units(U):
    """The pairs' or regions' own tests, as the pooled figure stars them."""
    fam = JP.FAMILY.get(U[0].get("family") or "", "the family")
    hit = [r for r in U if sig(r)]
    if not hit:
        return "Tested separately, none of these effects was significant after correction across %s." % fam

    def one(r):
        return "%s (%s)" % (r["what"], ", ".join(x for x in (est_say(r), stat(r)) if x))
    return "Tested separately and corrected across %s, the following were significant: %s." % (fam, _join([one(r) for r in hit]))


def _also(A, names, fam):
    """A same-question effect in a secondary model (no q of its own) that
    passed on p: said beside a key test that did not pass after correction."""
    for A_ in A[1:]:
        for r in A_["terms"]:
            if r["source"] in names and r.get("q") is None and raw(r):
                return ("; the %s in the model across frequency bins (%s, %s) was not corrected for the number of %s" % (
                    _effect_phrase(r["source"])[2:], chi(r), JP.fp(r["p"]),
                    "pairs" if A[0].get("family") == "pairs" else "models"))
    return ""


def interpretation(kind, A, measure):
    """One sentence, on the corrected reading."""
    fam = JP.FAMILY.get(A[0].get("family") or "", "the family")
    if kind in ("p1pair", "pac"):
        r = _find(A[0]["terms"], "Session")
        if sig(r):
            e = r.get("effect") or {}
            if e.get("est") is None:
                return "These results indicate that %s differed between Early and Late sessions." % measure
            return "These results indicate that %s was %s in Late than in Early sessions." % (measure, "higher" if _higher(e) else "lower")
        also = _also(A, ("Session",), fam)
        if also:
            return "These results provide no evidence, after correction across %s, that %s differed between Early and Late sessions%s." % (fam, measure, also)
        return "These results provide no evidence that %s differed between Early and Late sessions." % measure
    if kind == "p2pair":
        r = _find(A[0]["terms"], "Session × Cue")
        if sig(r):
            return "These results indicate that the difference between cue 1 and cue 2 in %s changed from Early to Late sessions." % measure
        return "These results provide no evidence that the difference between cue 1 and cue 2 in %s changed from Early to Late sessions." % measure
    if kind in ("p3pair", "power"):
        r = _find(A[0]["terms"], "Session × Period")
        con = [c for c in A[0].get("planned") or [] if sig(c)]
        if con and sig(r):
            return "These results indicate that the response of %s to the cues, relative to baseline, changed from Early to Late sessions." % measure
        if con:
            return ("These results indicate that the change in %s from Early to Late sessions differed for %s, although the Session × Period "
                    "interaction was not significant after correction." % (measure, _join(["%s relative to %s" % (c["a"], c["b"]) for c in con])))
        if sig(r):
            return ("These results indicate that the response of %s to the cues, relative to baseline, differed between Early and Late sessions, "
                    "although no single planned contrast reached significance." % measure)
        s = _find(A[0]["terms"], "Session")
        if sig(s) and (s.get("effect") or {}).get("est") is not None:
            return ("These results indicate that %s was %s in Late than in Early sessions across the baseline and both cues, with no evidence "
                    "that its response to the cues changed." % (measure, "higher" if _higher(s["effect"]) else "lower"))
        also = _also(A, ("Session × Period",), fam)
        if also:
            return ("These results provide no evidence, after correction across %s, that the response of %s to the cues changed from Early to "
                    "Late sessions%s." % (fam, measure, also))
        return "These results provide no evidence that %s, or its response to the cues, changed from Early to Late sessions." % measure
    if kind in ("p1pool", "p2pool"):
        r = _find(A[0]["terms"], "Session × Pair")
        if sig(r):
            return "These results indicate that the change in %s from Early to Late sessions differed between region pairs." % measure
        r2 = _find(A[1]["terms"], "Session × Pair") if len(A) > 1 else None
        if sig(r2):
            return ("These results indicate that the change in %s from Early to Late sessions differed between region pairs in the model "
                    "across frequency bins (on model-based standard errors), but not in the band-averaged model." % measure)
        return "These results provide no evidence that %s changed from Early to Late sessions across the ten region pairs as a whole." % measure
    if kind == "p3pool":
        hit = [r for r in A[0]["terms"] if sig(r)]
        if hit:
            return ("These results indicate that the response of %s to the cues changed from Early to Late sessions in %s."
                    % (measure, _join([r["source"].split(":")[0] for r in hit])))
        return "These results provide no evidence that the response of %s to the cues changed from Early to Late sessions in any pair." % measure
    if kind == "powerall":
        t = A[0]["terms"]
        if sig(_find(t, "Session × Period × Region")):
            return "These results indicate that the change in the response of %s to the cues from Early to Late sessions differed between regions." % measure
        if sig(_find(t, "Session × Period")):
            return "These results indicate that the response of %s to the cues changed from Early to Late sessions." % measure
        return ("These results provide no evidence that the response of %s to the cues changed from Early to Late sessions when the five "
                "regions were analysed together." % measure)
    if kind == "fooof":
        hit = [(A_["title"], r["source"].split(":")[0]) for A_ in A for r in A_["terms"] if r["source"].endswith("Session × Period") and sig(r)]
        if hit:
            return ("These results indicate that the response to the cues changed from Early to Late sessions in the %s."
                    % _join(["%s of %s" % (p.lower(), r) for p, r in hit]))
        return "These results provide no evidence that the aperiodic or theta-peak parameters responded differently to the cues in Late than in Early sessions."
    if kind == "granger":
        if any(sig(r) for r in A[0].get("planned") or []):
            return "These results indicate that directed interaction between these regions changed from Early to Late sessions."
        return "These results provide no evidence that Granger causality between these regions changed from Early to Late sessions."
    return ""


# --------------------------------------------------------------------------
# One figure
# --------------------------------------------------------------------------
def figure_stats(f, no, D, title):
    """Everything the statistics PDF of one figure says."""
    k, band = f["kind"], f.get("band")
    bw = band or ""
    if k in ("p1pair", "p2pair", "p3pair"):
        a, b = E.STRUCTS[E.PAIRS[f["pair"]][0]][1], E.STRUCTS[E.PAIRS[f["pair"]][1]][1]
        measure = "%s coherence between %s and %s" % (bw, a, b)
    elif k in ("p1pool", "p2pool", "p3pool"):
        measure = "%s coherence" % bw
    elif k == "power":
        measure = "%s power in %s" % (bw, FS.REGION_SAY[f["region"]])
    elif k == "powerall":
        measure = "%s power" % bw
    elif k == "pac":
        measure = "theta–gamma coupling in %s" % FS.REGION_SAY[f["region"]]
    elif k == "granger":
        measure = "%s Granger causality" % bw
    else:
        measure = "the spectral parameters"
    if k == "p1pair":
        A = coh_pair1(D, band, f["pair"])
        open_ = ("%s is displayed in Figure %s. Coherence was computed for the 20-s cue pair from spectra pooled over every trial of each "
                 "session and averaged over each rat's valid wire pairs." % (measure[0].upper() + measure[1:], no))
    elif k == "p1pool":
        A = coh_pool1(D, band)
        open_ = ("%s coherence in all ten region pairs is displayed in Figure %s. Coherence was computed for the 20-s cue pair from spectra "
                 "pooled over every trial of each session and averaged over each rat's valid wire pairs." % (bw.capitalize(), no))
    elif k == "p2pair":
        A = coh_pair2(D, band, f["pair"])
        open_ = ("%s during cue 1 and cue 2 is displayed in Figure %s. Coherence was computed separately in each 10-s cue window from spectra "
                 "pooled over every trial of each session." % (measure[0].upper() + measure[1:], no))
    elif k == "p2pool":
        A = coh_pool2(D, band)
        open_ = ("%s coherence during cue 1 and cue 2 in all ten region pairs is displayed in Figure %s. Coherence was computed separately in "
                 "each 10-s cue window from spectra pooled over every trial of each session." % (bw.capitalize(), no))
    elif k == "p3pair":
        A = coh_pair3(D, band, f["pair"])
        open_ = ("%s in the baseline, cue 1 and cue 2 windows is displayed in Figure %s. Coherence was computed separately in each 10-s "
                 "window from spectra pooled over every trial of each session." % (measure[0].upper() + measure[1:], no))
    elif k == "p3pool":
        A = coh_pool3(D, band)
        open_ = ("The change in the cue effect on %s coherence from Early to Late sessions in each region pair is displayed in Figure %s. "
                 "Each estimate is a planned contrast of that pair's Session × Period model." % (bw, no))
    elif k == "power":
        A = power_region(D, band, f["region"])
        open_ = ("%s power in %s in the baseline, cue 1 and cue 2 windows is displayed in Figure %s. Power was averaged over every trial "
                 "of each session and over the two hemispheres, and expressed in dB." % (bw.capitalize(), JP.REGION_LONG[f["region"]], no))
    elif k == "powerall":
        A = power_all(D, band)
        open_ = ("%s power in all five regions in the baseline, cue 1 and cue 2 windows is displayed in Figure %s. Power was averaged over "
                 "every trial of each session and over the two hemispheres, and expressed in dB." % (bw.capitalize(), no))
    elif k == "fooof":
        A = fooof_all(D)
        open_ = ("The aperiodic and periodic components of the power spectrum in each region are displayed in Figure %s. Each spectrum "
                 "(2–55 Hz) was parameterised with FOOOF, and the parameters were averaged over the two hemispheres." % no)
    elif k == "granger":
        x = next(z for z in D["G"] if z["pair"] == f["pair"] and z["band"] == band and not z.get("error"))
        A = granger_pair(D, x)
        measure = "%s Granger causality between %s and %s" % (bw, x["a"], x["b"])
        open_ = ("%s during the cue pair is displayed in Figure %s. Granger causality was computed from the pooled cross-spectral matrix "
                 "of each session by spectral factorisation and averaged within the band." % (measure[0].upper() + measure[1:], no))
    elif k == "pac":
        x = next(z for z in D["PM"] if z["region"] == f["region"] and not z.get("error"))
        A = pac_region(D, x)
        open_ = ("Theta–gamma phase–amplitude coupling within %s is displayed in Figure %s. The modulation index was computed from the gamma "
                 "amplitude in each theta phase bin, summed over every cue-pair window of a session." % (JP.REGION_LONG[f["region"]], no))
    else:
        return None
    rats = sorted({r for a_ in A for r in a_["rats"]})
    paras = [open_ + (" Data are from %d rats." % len(rats) if rats else "")]
    body = []
    for a_ in A:
        body += say_analysis(a_, measure)
    if any(r["errors"] == "model-based" and sig(r) for a_ in A for r in a_["terms"]):
        body.append("Effects with more than 2 df were tested on model-based standard errors, which assume the working correlation is correct.")
    if body:
        paras.append(" ".join(body))
    it = interpretation(k, A, measure)
    if it:
        paras[-1] = paras[-1] + " " + it
    return {"id": no, "title": title, "kind": k, "measure": measure, "analyses": A, "paragraph": paras, "rats": rats}


# --------------------------------------------------------------------------
# The PDF
# --------------------------------------------------------------------------
CSS = """
* { font-family: sans-serif; font-size: 9.5pt; line-height: 1.32; color: #111; }
h1 { font-size: 13pt; margin: 0 0 2pt 0; }
h2 { font-size: 11pt; margin: 14pt 0 3pt 0; }
h3 { font-size: 10pt; margin: 10pt 0 2pt 0; }
p { margin: 0 0 4pt 0; }
.src { color: #555; font-size: 8.5pt; }
.design { font-weight: bold; margin-top: 2pt; }
.model { color: #333; font-size: 8.5pt; }
.res { margin: 0 0 1pt 10pt; }
table { border-collapse: collapse; margin: 4pt 0 2pt 0; }
th { font-weight: bold; text-align: left; border-bottom: 0.8px solid #000; padding: 1.5pt 7pt 1.5pt 0; font-size: 8.5pt; white-space: nowrap; }
td { border-bottom: 0.4px solid #bbb; padding: 1.5pt 7pt 1.5pt 0; font-size: 8.5pt; }
td.n { text-align: right; white-space: nowrap; }
tr.s td { font-weight: bold; }
.foot { color: #444; font-size: 8pt; }
.para { font-size: 10pt; line-height: 1.45; }
"""


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pcell(p):
    s = JP.fp(p)
    return s[4:] if s.startswith("p = ") else s[2:] if s.startswith("p ") else s


def _qcell(q):
    s = JP.fq(q)
    return "" if not s else s[4:] if s.startswith("q = ") else s[2:]


def _table(head, rows, bold, num=()):
    h = "<tr>%s</tr>" % "".join("<th>%s</th>" % _esc(x) for x in head)
    b = "".join("<tr%s>%s</tr>" % (' class="s"' if bold[i] else "", "".join('<td%s>%s</td>' % (' class="n"' if j in num else "", _esc(c))
                                                                              for j, c in enumerate(r))) for i, r in enumerate(rows))
    return "<table>%s%s</table>" % (h, b)


def html(doc, set_say):
    out = ["<h1>%s</h1>" % _esc(doc["title"]),
           '<p class="src">%s · %d rats · statistics from Jarvis tabs 11 and 12</p>' % (_esc(set_say), len(doc["rats"]))]
    for i, A in enumerate(doc["analyses"], 1):
        out.append("<h2>%d. %s</h2>" % (i, _esc(A["title"])))
        out.append('<p class="design">%s</p>' % _esc(A["design"]))
        out.append('<p class="model">Dependent variable: %s. %s</p>' % (_esc(A["dv"]), _esc(A["model"])))
        if A["terms"]:
            for r in A["terms"]:
                out.append('<p class="res">%s</p>' % _esc(_term_say(r) + (" (model-based)" if r["errors"] == "model-based" else "")))
            out.append(_table(["Source", "Wald χ²", "df", "p", "FDR q", "Standard errors"],
                              [[r["source"], "%.2f" % r["chi2"], str(r["df"]), _pcell(r["p"]), _qcell(r.get("q")), r["errors"]] for r in A["terms"]],
                              [sig(r) for r in A["terms"]], num=(1, 2, 3, 4)))
            if any(r.get("q") is not None for r in A["terms"]):
                out.append('<p class="foot">FDR q: Benjamini–Hochberg across %s. Bold: significant (q &lt; .05 where corrected, otherwise p &lt; .05).</p>'
                           % _esc(JP.FAMILY.get(A.get("family") or "", "the family")))
            else:
                out.append('<p class="foot">Bold: p &lt; .05. These terms are not part of a corrected family.</p>')
        for e in A.get("extra") or []:
            out.append('<p class="foot">%s</p>' % _esc(e))
        if A.get("planned"):
            P = A["planned"]
            out.append("<h3>Planned comparisons</h3>")
            ratio = any(r.get("kind") == "ratio" for r in P)
            out.append(_table(["Comparison", "Estimate [95% CI]" + (" (ratio)" if ratio else " (dB)"), "Wald χ²(1)", "p", "FDR q"],
                              [[r["what"], est_say(r, short=True) or "", "%.2f" % r["chi2"], _pcell(r["p"]), _qcell(r.get("q"))] for r in P],
                              [sig(r) for r in P], num=(2, 3, 4)))
        if A.get("units"):
            U = A["units"]
            out.append("<h3>Each %s's own test</h3>" % ("pair" if U[0].get("family") == "pairs" else "region"))
            out.append('<p class="foot">Each from its own model, corrected across %s (Benjamini–Hochberg). These are the tests the figure\'s '
                       "asterisks mark.</p>" % _esc(JP.FAMILY.get(U[0].get("family") or "", "the family")))
            est_ = any(r.get("est") is not None for r in U)
            out.append(_table(["Test"] + (["Estimate [95% CI]"] if est_ else []) + ["Wald χ²", "df", "p", "FDR q"],
                              [[r["what"]] + ([est_say(r, short=True)] if est_ else []) + ["%.2f" % r["chi2"], str(r["df"]),
                                _pcell(r["p"]), _qcell(r.get("q"))] for r in U], [sig(r) for r in U],
                              num=tuple(range(2 if est_ else 1, 6 if est_ else 5))))
        for F in A["followups"]:
            g = F["gate"]
            out.append("<h3>Post hoc: %s</h3>" % _esc(F["title"]))
            out.append('<p class="foot">Followed up because %s, %s%s. %s.%s</p>' % (
                _esc(g["name"]), _esc(stat(g)), "" if sig(g) or g.get("q") is None else " (significant before correction only)",
                _esc(F["correction"]), (" " + _esc(F["note"])) if F.get("note") else ""))
            rows = F["rows"]
            est_ = any(r.get("est") is not None for r in rows)
            q_ = any(r.get("q") is not None for r in rows)
            head = [F["level_word"].capitalize()] + (["Estimate [95% CI]"] if est_ else []) + ["Wald χ²", "df", "p", "p (Bonferroni)"] + (["FDR q"] if q_ else [])
            body = []
            for r in rows:
                body.append([r["what"]] + ([est_say(r, short=True)] if est_ else [])
                            + ["%.2f" % r["chi2"] if r.get("chi2") is not None else "", str(r.get("df") or ""),
                               _pcell(r.get("p")) if r.get("p") is not None else (r.get("error") or ""),
                               _pcell(r["padj"]) if r.get("padj") is not None else ""] + ([_qcell(r.get("q"))] if q_ else []))
            k0 = 2 if est_ else 1
            out.append(_table(head, body, [ph_sig(r) for r in rows], num=tuple(range(k0, len(head)))))
            if q_:
                out.append('<p class="foot">Each of these tests is also corrected across the ten region pairs (FDR q); it is counted as '
                           "significant only when both its Bonferroni-adjusted p and its q are below .05.</p>")
    out.append("<h2>Results</h2>")
    for p in doc["paragraph"]:
        out.append('<p class="para">%s</p>' % _esc(p))
    if doc.get("sensitivity"):
        out.append("<h3>Sensitivity analyses</h3>")
        for p in doc["sensitivity"]:
            out.append('<p class="para">%s</p>' % _esc(p))
    if doc.get("reading"):
        out.append("<h3>Note for Joe: reading this result</h3>")
        for p in doc["reading"]:
            out.append('<p class="para">%s</p>' % _esc(p))
    out.append('<p class="foot">Estimates: ratios Late/Early (or of ratios) for coherence, Granger causality and the modulation index, '
               "modelled on a log link; differences in dB for power, and in each parameter's own units for the FOOOF parameters. Terms with "
               "more than 1 df have no single estimate; their post hoc comparisons give them.</p>")
    return "".join(out)


def write_pdf(doc, path, set_say):
    import io
    import fitz
    story = fitz.Story(html=html(doc, set_say), user_css=CSS)
    buf = io.BytesIO()
    w = fitz.DocumentWriter(buf)
    page = fitz.paper_rect("letter")
    where = page + (54, 50, -54, -50)
    more = 1
    while more:
        dev = w.begin_page(page)
        more, _ = story.place(where)
        story.draw(dev)
        w.end_page()
    w.close()
    d = fitz.open("pdf", buf.getvalue())
    d.set_metadata({"title": doc["title"], "author": "Jarvis (tabs 11 and 12)", "subject": "Statistics for %s" % doc["id"]})
    d.subset_fonts()
    d.save(path + ".tmp", garbage=4, deflate=True)
    d.close()
    os.replace(path + ".tmp", path)
    return path
