# -*- coding: utf-8 -*-
"""extraction.py -- The Extraction Room, the sixth and last step of The
Dentist (asked 2026-11-10).

"Create the 6th and last step of The Dentist, The Extraction Room: a
different tab open, like the Monolith. The first tab is the Dentate Spike:
the CSD view and the depth profiles, toggleable between the mean sink and
the mean source -- for the mean sink keep the delta. And the %KO for each
PTEN mouse as a chip next to it, 0% for the controls."

WHAT IS EXTRACTED. The X-ray bundles of one X-ray Many folder, the newest
version of each, taken OUT of Jarvis into a room of their own: every number
the room shows is copied into one artifact version (kind `extraction`,
one per room), so the room keeps showing exactly what was extracted however
the bundles move on afterwards. Extracting again is the room's next
version. Nothing here writes to a bundle, a read or the Event Bank.

PER RECORDING, PER CLASS (DS1, DS2):
  csd       the class's mean CSD over the whole shank and the read's
            surround (5-100 Hz, 60 Hz notched: the picture X-ray draws),
            contacts x time;
  profile   the class's depth profile at the box's time -- the bundle's
            own mean and SEM, the curve X-ray's sinks were measured on;
  sink      its strongest sink in the box (the bundle's) and the DELTA:
            the distance between its two largest sinks, per event, as
            X-ray's delta method measures it -- mean and SEM, in contacts
            and um;
  source    its strongest source in the box: the profile's maximum there,
            with its SEM.
And the recording's %KO, from the lab's sheet (a shared preference, so it is
corrected once for everybody), 0 for a control.

Everything numeric is worked out by `extract_one` from the bundle and its
read; app.py does the loading and the saving.
"""
from __future__ import annotations

import numpy as np

KIND = "extraction"
SCHEMA = "extraction.ds/1"
ROOMS = (("dentate_spike", "Dentate Spike"),)
KO_KEY = "extraction_ko"

# The %KO of each PTEN mouse, "JB % hits" on the lab's sheet (sent
# 2026-11-10). Keyed as Jarvis keys a mouse; a control is 0 by rule, not
# by entry. Seeded into the shared preference on the room's first visit.
KO_SHEET = {
    "PTEN|m7": 24.12, "PTEN|m8": 3.89, "PTEN|m1": 5.18, "PTEN|m10": 9.51,
    "PTEN|m11": 13.50, "PTEN|m33": 4.41, "PTEN|m34": 28.43,
    "PTEN|m13": 18.87, "PTEN|m3": 24.57, "PTEN|m5": 27.64,
    "PTEN|m28": 20.19,
}
# Its other column, kept beside it: which of them have IEDs.
IED_SHEET = {
    "PTEN|m7": False, "PTEN|m8": False, "PTEN|m1": False, "PTEN|m10": False,
    "PTEN|m11": False, "PTEN|m33": False, "PTEN|m34": True,
    "PTEN|m13": True, "PTEN|m3": True, "PTEN|m5": True, "PTEN|m28": True,
}


def _sig(v, n=4):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    if v == 0:
        return 0.0
    return float("%.*g" % (n, v))


def _sem(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return None
    return float(np.std(x) / np.sqrt(x.size))


def ko_of(mouse_key, group, ko):
    """(pct, said): a control is 0; a PTEN mouse is its sheet's number, or
    None when the sheet has none for it."""
    if str(group or "").upper() == "CTL":
        return 0.0, "control"
    v = (ko or {}).get(mouse_key)
    if v is None:
        return None, "not on the sheet"
    try:
        return float(v), "sheet"
    except (TypeError, ValueError):
        return None, "not a number on the sheet"


def source_of(profile, box):
    """The class's strongest source inside the box: the profile's maximum
    there, its contact and its SEM. None when the box is unknown."""
    cs = [int(c) for c in profile.get("contacts") or []]
    mu = np.asarray(profile.get("mean") or [], dtype=float)
    se = np.asarray(profile.get("sem") or [np.nan] * len(mu), dtype=float)
    lo, hi = (box or {}).get("sel_lo"), (box or {}).get("sel_hi")
    if not cs or mu.size != len(cs):
        return None
    idx = [j for j, c in enumerate(cs)
           if lo is None or hi is None or lo <= c <= hi]
    idx = [j for j in idx if np.isfinite(mu[j])]
    if not idx:
        return None
    j = max(idx, key=lambda r: mu[r])
    return {"csc": cs[j], "value": _sig(mu[j]),
            "sem": _sig(se[j]) if se.size > j else None}


def extract_one(bundle, subject, res, got, ko):
    """One recording's part of the room, from its bundle's payload and a
    fit of its read made with the bundle's own settings and box (`res`).

    The refit is how the class of each of the read's events is known --
    the bundle keeps the types in its own event order, which is the fit's
    -- and it is checked against the bundle's counts: a refit that does not
    give the same classes is refused, not shown."""
    types = np.asarray(res.get("types"), dtype=int)
    counts = {str(k): int(v) for k, v in (bundle.get("counts") or {}).items()}
    mine = {str(c): int((types == c).sum()) for c in sorted(set(types.tolist()))}
    if counts and mine != counts:
        raise ValueError("refitting its read gave %s, the bundle says %s"
                         % (mine, counts))
    disp = np.asarray(res["disp"], dtype=float)          # ev x ch x t
    nums = [int(n) for n in res.get("nums_all") or got.get("nums") or []]
    sur_ms = float(got.get("surround_ms") or 50.0)
    n_t = disp.shape[2]
    t_ms = np.linspace(-sur_ms, sur_ms, n_t)
    spacing = float(res.get("spacing_um") or got.get("spacing_um") or 0) or None
    gap_c = np.asarray(res.get("gap_contacts") or [], dtype=float)
    box = bundle.get("box") or {}
    profiles = {int(p.get("c")): p for p in bundle.get("profiles") or []}
    sinks = {int(s.get("cls")): s for s in bundle.get("sinks") or []}
    classes = []
    for c in sorted(set(types.tolist())):
        rr = np.where(types == c)[0]
        mat = np.nanmean(disp[rr], axis=0) if rr.size else None
        prof = profiles.get(c) or {}
        g = gap_c[rr] if gap_c.size == types.size else np.array([])
        sk = sinks.get(c) or {}
        classes.append({
            "c": int(c), "name": "DS%d" % c, "n": int(rr.size),
            "csd": ([[_sig(v, 3) for v in row] for row in mat]
                    if mat is not None else None),
            "profile": {"contacts": prof.get("contacts"),
                        "mean": prof.get("mean"), "sem": prof.get("sem"),
                        "band": prof.get("band")},
            "sink": {"csc": sk.get("csc"), "value": sk.get("value"),
                     "sem": sk.get("sem"), "unit": sk.get("unit")},
            "delta": {
                "contacts": _sig(np.mean(g)) if g.size else None,
                "sem": _sig(_sem(g)) if g.size else None,
                "um": (_sig(np.mean(g) * spacing)
                       if g.size and spacing else None),
                "um_sem": (_sig(_sem(g) * spacing)
                           if g.size and spacing and _sem(g) is not None
                           else None),
                "n": int(g.size)},
            "source": source_of(prof, box),
        })
    ko_pct, ko_said = ko_of(subject.get("mouse_key"), subject.get("group"), ko)
    return {
        "gid": subject.get("gid"), "entry_id": subject.get("entry_id"),
        "session_label": subject.get("session_label"),
        "mouse_key": subject.get("mouse_key"), "group": subject.get("group"),
        "ko_pct": ko_pct, "ko_said": ko_said,
        "ied": IED_SHEET.get(subject.get("mouse_key")),
        "n": int(types.size), "counts": counts,
        "separation": {k: (bundle.get("separation") or {}).get(k)
                       for k in ("verdict", "dbic", "min_share", "n", "words")},
        "box": {k: box.get(k) for k in ("sel_lo", "sel_hi", "t_lo_ms",
                                        "t_hi_ms", "auto")},
        "contacts": nums, "t_ms": [_sig(v, 5) for v in t_ms],
        "spacing_um": spacing, "unit": (classes[0]["sink"].get("unit")
                                        if classes else None),
        "bad": bundle.get("bad") or [],
        "classes": classes,
    }


def room_name(room):
    return dict(ROOMS).get(room, room)


# --------------------------------------------------------------------------
# Which is DS1, said by hand (2026-11-10: "let me toggle the label, because
# the math can be a bit off")
# --------------------------------------------------------------------------
FLIP_KEY = "extraction_flip"


def flip_key(room, gid):
    """The key a call had before calls were kept per set (2026-11-11)."""
    return "%s|%s" % (room, gid)


def call_key(room, folder, gid):
    """A call on one recording in one set -- the X-ray Many folder it was
    extracted from -- for the swaps and the separable calls alike."""
    return "%s|%s|%s" % (room, folder, gid)


def classes_shown(rec, flipped):
    """The recording's classes as they are to be called: with its labels
    swapped by hand, X-ray's DS1 is shown and counted as DS2 and the other
    way round. Copies; the extracted numbers are never changed."""
    out = []
    for c in rec.get("classes") or []:
        d = dict(c)
        k = int(c.get("c") or 0)
        d["shown"] = (3 - k) if flipped and k in (1, 2) else k
        d["name"] = "DS%d" % d["shown"]
        out.append(d)
    return sorted(out, key=lambda d: d["shown"])


# --------------------------------------------------------------------------
# Does it differ? (2026-11-10: "a chart / stat to see, after toggling, if
# there is a significant result: PTEN vs CTL, and CTL, Low KO, High KO")
# --------------------------------------------------------------------------
# One number per recording (each recording is one mouse here), so the test
# is across mice, never across events: a mouse with 700 events must not
# outvote one with 60.
MIN_N = 5          # a class with fewer events has no sink worth comparing
KO_SPLIT = 10.0    # % KO: below is Low, at or above is High (adjustable)

METRICS = (
    ("ds1_sink", "DS1 sink strength", "csd",
     "How deep DS1's strongest sink in the box goes (the size of its mean CSD there)."),
    ("ds2_sink", "DS2 sink strength", "csd",
     "How deep DS2's strongest sink in the box goes."),
    ("sink_ratio", "DS2 / DS1 sink", "ratio",
     "DS2's sink strength over DS1's: above 1, DS2's sink is the deeper."),
    ("ds1_delta", "DS1 delta", "um",
     "How far apart DS1's two largest sinks are, the mean over its events."),
    ("ds2_delta", "DS2 delta", "um",
     "How far apart DS2's two largest sinks are, the mean over its events."),
    ("ds1_source", "DS1 source", "csd",
     "How high DS1's strongest source in the box goes."),
    ("ds2_source", "DS2 source", "csd",
     "How high DS2's strongest source in the box goes."),
    ("ds1_share", "Share that are DS1", "share",
     "Of the recording's dentate spikes, the share called DS1."),
)


def metrics_of(rec, flipped, min_n=MIN_N):
    """{metric: value or None} for one recording, with its labels as shown.
    A class with fewer than `min_n` events gives None for its own numbers
    (and the ratio), not a number from three spikes."""
    cs = {d["shown"]: d for d in classes_shown(rec, flipped)}
    a, b = cs.get(1) or {}, cs.get(2) or {}
    ok_a, ok_b = (a.get("n") or 0) >= min_n, (b.get("n") or 0) >= min_n

    def strength(d):
        v = (d.get("sink") or {}).get("value")
        return None if v is None else -float(v)

    def delta(d):
        x = d.get("delta") or {}
        return x.get("um") if x.get("um") is not None else None

    out = {
        "ds1_sink": strength(a) if ok_a else None,
        "ds2_sink": strength(b) if ok_b else None,
        "ds1_delta": delta(a) if ok_a else None,
        "ds2_delta": delta(b) if ok_b else None,
        "ds1_source": (a.get("source") or {}).get("value") if ok_a else None,
        "ds2_source": (b.get("source") or {}).get("value") if ok_b else None,
    }
    s1, s2 = out["ds1_sink"], out["ds2_sink"]
    out["sink_ratio"] = (s2 / s1) if (s1 and s2 is not None and s1 > 0) else None
    n1, n2 = a.get("n") or 0, b.get("n") or 0
    out["ds1_share"] = (n1 / float(n1 + n2)) if (n1 + n2) else None
    return out


def ko_group(rec, ko_now, split=KO_SPLIT):
    if str(rec.get("group") or "").upper() == "CTL":
        return "CTL"
    if ko_now is None:
        return None
    return "Low KO" if float(ko_now) < float(split) else "High KO"


def _summ(x):
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], float)
    if not x.size:
        return {"n": 0, "mean": None, "sem": None, "median": None}
    return {"n": int(x.size), "mean": _sig(np.mean(x)),
            "sem": _sig(np.std(x, ddof=1) / np.sqrt(x.size)) if x.size > 1 else None,
            "median": _sig(np.median(x))}


def _p(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else float("%.4g" % v)


def _holm(ps):
    """Holm's step-down adjustment, in the order given."""
    idx = [i for i, p in enumerate(ps) if p is not None]
    out = list(ps)
    order = sorted(idx, key=lambda i: ps[i])
    run = 0.0
    m = len(order)
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i]))
        out[i] = _p(run)
    return out


def two_groups(a, b):
    """CTL vs PTEN: Welch's t, Mann-Whitney U, Hedges' g. Each needs two in
    each group and some spread; short of that, None, and said."""
    from scipy import stats as st
    a = [v for v in a if v is not None and np.isfinite(v)]
    b = [v for v in b if v is not None and np.isfinite(v)]
    out = {"welch_p": None, "mwu_p": None, "g": None,
           "why": None if len(a) >= 2 and len(b) >= 2 else
           "fewer than two recordings in a group"}
    if out["why"]:
        return out
    try:
        out["welch_p"] = _p(st.ttest_ind(b, a, equal_var=False).pvalue)
    except Exception:                                    # noqa: BLE001
        pass
    try:
        out["mwu_p"] = _p(st.mannwhitneyu(b, a, alternative="two-sided").pvalue)
    except Exception:                                    # noqa: BLE001
        pass
    na, nb = len(a), len(b)
    sp = np.sqrt(((na - 1) * np.var(a, ddof=1) + (nb - 1) * np.var(b, ddof=1))
                 / max(na + nb - 2, 1))
    if sp > 0:
        d = (np.mean(b) - np.mean(a)) / sp
        out["g"] = _sig(d * (1 - 3.0 / (4 * (na + nb) - 9)))
    return out


def three_groups(groups):
    """CTL, Low KO, High KO: one-way ANOVA and Kruskal-Wallis across all
    three, every pair by Mann-Whitney (Holm-adjusted over the three pairs),
    and Spearman's rho against %KO itself (controls at 0)."""
    from scipy import stats as st
    names = ("CTL", "Low KO", "High KO")
    xs = [[v for v in groups.get(n) or [] if v is not None and np.isfinite(v)]
          for n in names]
    out = {"anova_p": None, "kw_p": None, "pairs": [],
           "why": None if all(len(x) >= 2 for x in xs) else
           "fewer than two recordings in a group"}
    if not out["why"]:
        try:
            out["anova_p"] = _p(st.f_oneway(*xs).pvalue)
        except Exception:                                # noqa: BLE001
            pass
        try:
            out["kw_p"] = _p(st.kruskal(*xs).pvalue)
        except Exception:                                # noqa: BLE001
            pass
    pairs, raw = [], []
    for i, j in ((0, 1), (0, 2), (1, 2)):
        p = None
        if len(xs[i]) >= 2 and len(xs[j]) >= 2:
            try:
                p = _p(st.mannwhitneyu(xs[j], xs[i],
                                       alternative="two-sided").pvalue)
            except Exception:                            # noqa: BLE001
                p = None
        pairs.append({"a": names[i], "b": names[j], "mwu_p": p})
        raw.append(p)
    for pr, ph in zip(pairs, _holm(raw)):
        pr["holm_p"] = ph
    out["pairs"] = pairs
    return out


def spearman(points):
    from scipy import stats as st
    pts = [(k, v) for k, v in points if k is not None and v is not None
           and np.isfinite(v)]
    if len(pts) < 4:
        return {"rho": None, "p": None, "n": len(pts)}
    r = st.spearmanr([k for k, _ in pts], [v for _, v in pts])
    return {"rho": _sig(r.correlation if hasattr(r, "correlation") else r[0], 3),
            "p": _p(r.pvalue if hasattr(r, "pvalue") else r[1]),
            "n": len(pts)}


# --------------------------------------------------------------------------
# THE USUAL TESTS (2026-11-11: "our stats are a bit too strict? use
# something more common and forgiving for a low sample size"). The way most
# papers -- and Prism -- do it: one test per question, picked by whether the
# residuals look normal (Shapiro-Wilk). Two groups: Welch's t, or
# Mann-Whitney. Three: one-way ANOVA with Tukey's pairs, or Kruskal-Wallis
# with Dunn's (Holm). A rate: Boschloo's exact test, never less powerful than
# Fisher's. Nothing corrected across measures. The strict set (both tests
# must agree, Fisher, the false discovery rate) stays beside it.
# --------------------------------------------------------------------------
NORMAL_P = 0.05    # Shapiro-Wilk under this: the residuals are not normal


def _clean(x):
    return [float(v) for v in x if v is not None and np.isfinite(v)]


def normal_resid(groups):
    """Shapiro-Wilk p of the residuals -- each value less its own group's
    mean -- pooled over the groups. None with fewer than three, or none
    spread."""
    from scipy import stats as st
    res = []
    for g in groups:
        if len(g) >= 2:
            m = float(np.mean(g))
            res += [v - m for v in g]
    if len(res) < 3 or float(np.ptp(res)) == 0.0:
        return None
    try:
        return _p(st.shapiro(res).pvalue)
    except Exception:                                    # noqa: BLE001
        return None


def usual_two(a, b, strict):
    """CTL (`a`) vs PTEN (`b`), the usual way: Welch's t when the residuals
    look normal, Mann-Whitney when they do not. `strict` is two_groups'
    answer for the same numbers, so the p is the same one shown there."""
    a, b = _clean(a), _clean(b)
    if len(a) < 2 or len(b) < 2:
        return {"test": None, "p": None, "normal_p": None,
                "why": "fewer than two recordings in a group"}
    norm = normal_resid([a, b])
    if norm is None or norm >= NORMAL_P:
        return {"test": "welch", "p": strict.get("welch_p"), "normal_p": norm}
    return {"test": "mwu", "p": strict.get("mwu_p"), "normal_p": norm}


def dunn(xs):
    """Dunn's test for every pair of `xs` (three groups): each pair's mean
    ranks, from the ranks of all of them together, tie-corrected; raw p."""
    from scipy import stats as st
    allv = [v for x in xs for v in x]
    N = len(allv)
    if N < 3:
        return [None, None, None]
    r = st.rankdata(allv)
    _u, cnt = np.unique(allv, return_counts=True)
    s2 = N * (N + 1) / 12.0 - float(np.sum(cnt ** 3 - cnt)) / (12.0 * (N - 1))
    mr, pos = [], 0
    for x in xs:
        mr.append(float(np.mean(r[pos:pos + len(x)])) if x else None)
        pos += len(x)
    out = []
    for i, j in ((0, 1), (0, 2), (1, 2)):
        if mr[i] is None or mr[j] is None or s2 <= 0:
            out.append(None)
            continue
        z = (mr[j] - mr[i]) / np.sqrt(s2 * (1.0 / len(xs[i]) + 1.0 / len(xs[j])))
        out.append(_p(2 * st.norm.sf(abs(z))))
    return out


def jonckheere(xs):
    """Jonckheere-Terpstra test for a trend in order across the groups `xs`
    (CTL, Low KO, High KO): (p, z), two-sided, by the normal approximation
    with ties (Hollander and Wolfe). z > 0 rises along the order."""
    from scipy import stats as st
    xs = [list(x) for x in xs]
    ns = [len(x) for x in xs]
    N = sum(ns)
    if N < 4 or sum(1 for n in ns if n) < 2:
        return None, None
    J = 0.0
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            for a in xs[i]:
                for b in xs[j]:
                    J += 1.0 if b > a else 0.5 if b == a else 0.0
    _u, t = np.unique([v for x in xs for v in x], return_counts=True)
    t = t.astype(float)
    n = np.asarray(ns, float)
    E = (N * N - float(np.sum(n * n))) / 4.0
    V = ((N * (N - 1) * (2 * N + 5) - float(np.sum(n * (n - 1) * (2 * n + 5)))
          - float(np.sum(t * (t - 1) * (2 * t + 5)))) / 72.0
         + float(np.sum(n * (n - 1) * (n - 2))) * float(np.sum(t * (t - 1) * (t - 2)))
         / (36.0 * N * (N - 1) * (N - 2))
         + float(np.sum(n * (n - 1))) * float(np.sum(t * (t - 1))) / (8.0 * N * (N - 1)))
    if V <= 0:
        return None, None
    z = (J - E) / np.sqrt(V)
    return _p(2 * st.norm.sf(abs(z))), _sig(z, 3)


def dose(points):
    """DOES IT GET WORSE WITH MORE KNOCKOUT? (2026-11-11: "there's something
    wacky with the stats... we want to show that it gets worse with PTEN
    KO".) Spearman against %KO with the controls at 0% is mostly a test of
    controls against PTEN: every control sits at one end, so any PTEN
    difference reads as a trend. The dose is asked among the PTEN mice
    alone, with a Theil-Sen line to draw. `points` [(ko, value)], PTEN only."""
    from scipy import stats as st
    pts = [(float(k), float(v)) for k, v in points
           if k is not None and v is not None and np.isfinite(v)]
    out = dict(spearman(pts), fit=None)
    if len(pts) >= 3 and len({k for k, _ in pts}) >= 2:
        try:
            ts = st.theilslopes([v for _, v in pts], [k for k, _ in pts])
            out["fit"] = {"slope": _sig(ts[0]), "intercept": _sig(ts[1]),
                          "ko": [min(k for k, _ in pts), max(k for k, _ in pts)]}
        except Exception:                                # noqa: BLE001
            pass
    return out


def usual_three(groups, strict):
    """CTL / Low KO / High KO, the usual way: one-way ANOVA and Tukey's
    pairs when the residuals look normal; Kruskal-Wallis and Dunn's pairs
    (Holm) when they do not."""
    from scipy import stats as st
    names = ("CTL", "Low KO", "High KO")
    xs = [_clean(groups.get(n) or []) for n in names]
    out = {"test": None, "p": None, "normal_p": None, "post": None, "pairs": []}
    if not all(len(x) >= 2 for x in xs):
        out["why"] = "fewer than two recordings in a group"
        return out
    norm = normal_resid(xs)
    out["normal_p"] = norm
    # In order, CTL -> Low KO -> High KO: whether it worsens with the dose.
    out["jt_p"], out["jt_z"] = jonckheere(xs)
    ps = [None, None, None]
    if norm is None or norm >= NORMAL_P:
        out.update(test="anova", p=strict.get("anova_p"), post="tukey")
        try:
            tk = st.tukey_hsd(*xs).pvalue
            ps = [_p(tk[i][j]) for i, j in ((0, 1), (0, 2), (1, 2))]
        except Exception:                                # noqa: BLE001
            pass
    else:
        out.update(test="kw", p=strict.get("kw_p"), post="dunn")
        ps = _holm(dunn(xs))
    out["pairs"] = [{"a": names[i], "b": names[j], "p": p}
                    for (i, j), p in zip(((0, 1), (0, 2), (1, 2)), ps)]
    return out


def _boschloo(y1, n1, y2, n2):
    """Boschloo's exact test of two rates, y1 / n1 against y2 / n2 (each
    column of scipy's table is one group's binomial)."""
    from scipy import stats as st
    if not n1 or not n2:
        return None
    if (y1 + y2) in (0, n1 + n2):
        return 1.0
    try:
        return _p(st.boschloo_exact([[y1, y2], [n1 - y1, n2 - y2]],
                                    alternative="two-sided").pvalue)
    except Exception:                                    # noqa: BLE001
        return None


def usual(ctl, pten, by, strict_two, strict_three):
    """A measure's usual tests, beside its strict ones."""
    return {"two": usual_two(ctl, pten, strict_two),
            "three": usual_three(by, strict_three)}


# --------------------------------------------------------------------------
# Separable or not, said by hand (2026-11-10: "I meant: let me swap
# separable / not separable" -- the two-vs-one test and the 10% rule are a
# rule, and the person looking at the two CSDs is the judge)
# --------------------------------------------------------------------------
SEP_KEY = "extraction_sep"


def sep_shown(rec, override):
    """(verdict, by_hand): the person's call when there is one ('yes' or
    'no'), else X-ray's."""
    if override in ("yes", "no"):
        return override, True
    return (rec.get("separation") or {}).get("verdict"), False


def sep_binary(verdict):
    """Separable (True), not (False), or not counted (None): 'weak' counts
    as not separable; 'too few' is left out of the test, not guessed."""
    if verdict == "yes":
        return True
    if verdict in ("no", "weak"):
        return False
    return None


def _fisher2(a, b, c, d):
    from scipy import stats as st
    try:
        return _p(st.fisher_exact([[a, b], [c, d]]).pvalue)
    except Exception:                                    # noqa: BLE001
        try:
            return _p(st.fisher_exact([[a, b], [c, d]])[1])
        except Exception:                                # noqa: BLE001
            return None


def _freeman_halton(yes, n):
    """Exact test of a 2 x k table (k groups, separable or not) with its
    margins fixed: the sum of the probabilities of every table no more
    likely than the one seen. Small enough here to enumerate."""
    from math import comb
    k = len(n)
    R1, N = sum(yes), sum(n)
    if not N or R1 in (0, N):
        return 1.0 if N else None
    denom = comb(N, R1)

    def prob(xs):
        out = 1
        for x, m in zip(xs, n):
            out *= comb(m, x)
        return out / denom

    seen = prob(yes)
    total = 0.0

    def walk(i, left, xs):
        nonlocal total
        if i == k - 1:
            if 0 <= left <= n[i]:
                q = prob(xs + [left])
                if q <= seen * (1 + 1e-9):
                    total += q
            return
        for x in range(0, min(n[i], left) + 1):
            walk(i + 1, left - x, xs + [x])
    walk(0, R1, [])
    return _p(min(1.0, total))


def wilson(k, n, z=1.959964):
    """The Wilson 95% interval of a rate k / n, as [lo, hi]."""
    if not n:
        return None
    p = k / float(n)
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [_sig(max(0.0, c - h)), _sig(min(1.0, c + h))]


def cochran_armitage(yes, n, scores=(0, 1, 2)):
    """(p, z): the Cochran-Armitage test for a trend in a rate across
    ordered groups -- here CTL, Low KO, High KO, scored 0, 1, 2."""
    N, R = float(sum(n)), float(sum(yes))
    if N < 2 or R in (0, N):
        return None, None
    pbar = R / N
    t = sum(s * (y - m * pbar) for s, y, m in zip(scores, yes, n))
    v = pbar * (1 - pbar) * (sum(m * s * s for s, m in zip(scores, n))
                             - sum(m * s for s, m in zip(scores, n)) ** 2 / N)
    if v <= 0:
        return None, None
    z = t / np.sqrt(v)
    from scipy import stats as st
    return _p(2 * st.norm.sf(abs(z))), _sig(z, 3)


def logit_ko(ko, yes):
    """Logistic regression of separable on %KO: the odds ratio per 10% KO
    and its likelihood-ratio p. None when it cannot be fitted (every one
    the same, or perfectly split)."""
    x = np.asarray(ko, float)
    y = np.asarray(yes, float)
    if x.size < 4 or y.min() == y.max():
        return {"or10": None, "p": None, "n": int(x.size)}
    from scipy import optimize, stats as st

    def nll(b):
        eta = b[0] + b[1] * x / 10.0
        return float(np.sum(np.logaddexp(0, eta) - y * eta))
    try:
        fit = optimize.minimize(nll, [0.0, 0.0], method="BFGS")
        p0 = y.mean()
        null = -float(np.sum(y * np.log(p0) + (1 - y) * np.log(1 - p0)))
        lr = 2 * (null - fit.fun)
        b1 = float(fit.x[1])
        if not np.isfinite(b1) or abs(b1) > 20:
            return {"or10": None, "p": _p(st.chi2.sf(max(lr, 0), 1)),
                    "n": int(x.size), "why": "the two are split almost perfectly"}
        return {"or10": _sig(np.exp(b1), 3), "p": _p(st.chi2.sf(max(lr, 0), 1)),
                "n": int(x.size)}
    except Exception:                                    # noqa: BLE001
        return {"or10": None, "p": None, "n": int(x.size)}


def separability(rows):
    """How many are separable, by group, and whether that differs: CTL vs
    PTEN by Fisher's exact test; CTL / Low KO / High KO by the exact
    Freeman-Halton test and each pair by Fisher (Holm); and the %KO of the
    separable against the not separable (Mann-Whitney)."""
    from scipy import stats as st
    counted = [x for x in rows if x["sep"] is not None]

    def tally(pred):
        mine = [x for x in counted if pred(x)]
        return {"n": len(mine), "yes": sum(1 for x in mine if x["sep"]),
                "labels_yes": [x["label"] for x in mine if x["sep"]],
                "labels_no": [x["label"] for x in mine if not x["sep"]]}
    is_ctl = lambda x: str(x["group"]).upper() == "CTL"          # noqa: E731
    two = {"CTL": tally(is_ctl), "PTEN": tally(lambda x: not is_ctl(x))}
    a, b = two["PTEN"]["yes"], two["PTEN"]["n"] - two["PTEN"]["yes"]
    c, d = two["CTL"]["yes"], two["CTL"]["n"] - two["CTL"]["yes"]
    two["fisher_p"] = _fisher2(a, b, c, d) if two["PTEN"]["n"] and two["CTL"]["n"] else None
    two["boschloo_p"] = _boschloo(a, a + b, c, c + d)
    names = ("CTL", "Low KO", "High KO")
    three = {nm: tally(lambda x, nm=nm: x["ko_group"] == nm) for nm in names}
    ns = [three[nm]["n"] for nm in names]
    ys = [three[nm]["yes"] for nm in names]
    three["exact_p"] = _freeman_halton(ys, ns) if all(ns) else None
    pairs, raw = [], []
    for i, j in ((0, 1), (0, 2), (1, 2)):
        A, B = three[names[i]], three[names[j]]
        p = (_fisher2(A["yes"], A["n"] - A["yes"], B["yes"], B["n"] - B["yes"])
             if A["n"] and B["n"] else None)
        pairs.append({"a": names[i], "b": names[j], "fisher_p": p,
                      "boschloo_p": _boschloo(B["yes"], B["n"], A["yes"], A["n"])})
        raw.append(p)
    for pr, ph in zip(pairs, _holm(raw)):
        pr["holm_p"] = ph
    for pr, ph in zip(pairs, _holm([pr["boschloo_p"] for pr in pairs])):
        pr["boschloo_holm_p"] = ph
    three["pairs"] = pairs
    kos = [(0.0 if is_ctl(x) else x["ko"], x["sep"]) for x in counted
           if is_ctl(x) or x["ko"] is not None]
    ky = [k for k, s in kos if s]
    kn = [k for k, s in kos if not s]
    ko = {"yes": _summ(ky), "no": _summ(kn), "mwu_p": None}
    if len(ky) >= 2 and len(kn) >= 2:
        try:
            ko["mwu_p"] = _p(st.mannwhitneyu(ky, kn, alternative="two-sided").pvalue)
        except Exception:                                # noqa: BLE001
            pass
    # THE SEPARATION RATE, with its uncertainty (2026-11-10: "have a stats
    # test for separation rate"): each group's rate with a Wilson 95%
    # interval, and whether the rate falls (or rises) in order CTL -> Low
    # KO -> High KO (Cochran-Armitage), and with %KO itself (logistic).
    for t in list(two.values()) + [three[nm] for nm in names]:
        if isinstance(t, dict) and "n" in t:
            t["rate"] = _sig(t["yes"] / t["n"]) if t["n"] else None
            t["ci"] = wilson(t["yes"], t["n"])
    three["trend_p"], three["trend_z"] = cochran_armitage(ys, ns)
    ko["logit"] = logit_ko([k for k, _s in kos], [bool(s) for _k, s in kos])
    # The dose: among the PTEN mice alone (2026-11-11), the controls left out.
    pk = [(x["ko"], x["sep"]) for x in counted if not is_ctl(x) and x["ko"] is not None]
    ko["logit_pten"] = logit_ko([k for k, _s in pk], [bool(s) for _k, s in pk])
    return {"two": two, "three": three, "ko": ko,
            "not_counted": [x["label"] for x in rows if x["sep"] is None],
            "by_hand": [x["label"] for x in rows if x["sep_by_hand"]],
            "values": [{"gid": x["gid"], "label": x["label"], "group": x["group"],
                        "ko": x["ko"], "ko_group": x["ko_group"], "sep": x["sep"],
                        "verdict": x["verdict"], "by_hand": x["sep_by_hand"]}
                       for x in rows]}


def stats(recs, flips, ko_now, split=KO_SPLIT, min_n=MIN_N, skip=(),
          seps=None, only_sep=False):
    """Every metric, every comparison. `flips` is {gid: bool}; `ko_now`
    {gid: % or None}; `skip` the gids a person has left out; `seps`
    {gid: 'yes' | 'no'} the calls made by hand. `only_sep` takes the
    measures from the recordings called separable only (the separability
    test itself always counts them all)."""
    seps = seps or {}
    rows = []
    for r in recs:
        if r.get("gid") in skip:
            continue
        g = r.get("gid")
        ko = ko_now.get(g)
        verdict, by_hand = sep_shown(r, seps.get(g))
        rows.append({"gid": g, "label": r.get("session_label"),
                     "group": r.get("group"), "ko": ko,
                     "ko_group": ko_group(r, ko, split),
                     "flipped": bool(flips.get(g)),
                     "verdict": verdict, "sep": sep_binary(verdict),
                     "sep_by_hand": by_hand,
                     "m": metrics_of(r, bool(flips.get(g)), min_n)})
    sepb = separability(rows)
    if only_sep:
        rows = [x for x in rows if x["sep"]]
    out = []
    for key, name, unit, words in METRICS:
        vals = [{"gid": x["gid"], "label": x["label"], "group": x["group"],
                 "ko": x["ko"], "ko_group": x["ko_group"],
                 "value": _sig(x["m"].get(key))} for x in rows]
        ctl = [v["value"] for v in vals if str(v["group"]).upper() == "CTL"]
        pten = [v["value"] for v in vals if str(v["group"]).upper() != "CTL"]
        by = {n: [v["value"] for v in vals if v["ko_group"] == n]
              for n in ("CTL", "Low KO", "High KO")}
        two_s, three_s = two_groups(ctl, pten), three_groups(by)
        out.append({
            "key": key, "name": name, "unit": unit, "words": words,
            "values": vals,
            "two": dict(two_s, ctl=_summ(ctl), pten=_summ(pten)),
            "three": dict(three_s,
                          **{n: _summ(by[n]) for n in by}),
            "usual": usual(ctl, pten, by, two_s, three_s),
            "spearman": spearman([(0.0 if str(v["group"]).upper() == "CTL"
                                   else v["ko"], v["value"]) for v in vals]),
            "dose": dose([(v["ko"], v["value"]) for v in vals
                          if str(v["group"]).upper() != "CTL"]),
        })
    return {"metrics": out, "split": float(split), "min_n": int(min_n),
            "n": len(rows),
            "groups": {"CTL": sum(1 for x in rows if x["ko_group"] == "CTL"),
                       "Low KO": sum(1 for x in rows if x["ko_group"] == "Low KO"),
                       "High KO": sum(1 for x in rows if x["ko_group"] == "High KO"),
                       "PTEN": sum(1 for x in rows
                                   if str(x["group"]).upper() != "CTL"),
                       "no KO": [x["label"] for x in rows
                                 if x["ko_group"] is None
                                 and str(x["group"]).upper() != "CTL"]},
            "skipped": sorted(skip),
            "separability": sepb, "only_sep": bool(only_sep)}


# --------------------------------------------------------------------------
# Round II (2026-11-10: "try to find something straightforward that is
# significant"): a wide, plain look. Simple per-recording measures, each
# compared the three ways, and the false discovery rate held across all of
# them (Benjamini-Hochberg) -- so a hit is not just the luckiest of many.
# --------------------------------------------------------------------------
ROUND2 = (
    ("events_min", "Events per minute", "/min",
     "Every event Panning kept, per minute of recording."),
    ("ds_min", "Verified DS per minute", "/min",
     "Events inside the DS border, per minute."),
    ("pspike_min", "P-spikes per minute", "/min",
     "Events the one pool calls P-spike, per minute."),
    ("pspike_share", "Share that are P-spikes", "share",
     "Of the recording's events, the share the one pool calls P-spike."),
    ("ds_like", "Share that look like control DS", "share",
     "Of the recording's events, the share inside a DS border drawn from the "
     "controls -- for a control, from the OTHER controls, so its own events "
     "never drew the border they are judged by."),
    ("ds_amp", "Verified DS amplitude", "uV",
     "The mean max amplitude of the recording's verified DS."),
    ("ds_hf", "Verified DS HF power", "dB",
     "The mean 500-1000 Hz power of the recording's verified DS."),
    ("ds_hw", "Verified DS half-width", "ms",
     "The mean half-width of the recording's verified DS."),
    ("all_hf", "HF power of every event", "dB",
     "The mean 500-1000 Hz power of every event Panning kept."),
    ("ds1_min", "DS1 per minute", "/min",
     "X-ray's DS1 (as called now), per minute."),
    ("ds2_min", "DS2 per minute", "/min",
     "X-ray's DS2 (as called now), per minute."),
)


def bh(ps):
    """Benjamini-Hochberg q-values, in the order given (None kept None)."""
    idx = [i for i, p in enumerate(ps) if p is not None]
    m = len(idx)
    out = [None] * len(ps)
    order = sorted(idx, key=lambda i: ps[i], reverse=True)
    run = 1.0
    for r, i in enumerate(order):
        rank = m - r
        run = min(run, ps[i] * m / rank)
        out[i] = _p(min(1.0, run))
    return out


def round2(rows, split=KO_SPLIT):
    """`rows`: [{gid, label, group, ko, m: {measure: value}}]. Every measure
    the three ways, and BH across the measures within each way."""
    for x in rows:
        x["ko_group"] = ko_group(x, x.get("ko"), split)
    out = []
    for key, name, unit, words in ROUND2:
        vals = [{"gid": x["gid"], "label": x["label"], "group": x["group"],
                 "ko": x["ko"], "ko_group": x["ko_group"],
                 "value": _sig((x.get("m") or {}).get(key))} for x in rows]
        ctl = [v["value"] for v in vals if str(v["group"]).upper() == "CTL"]
        pten = [v["value"] for v in vals if str(v["group"]).upper() != "CTL"]
        by = {n: [v["value"] for v in vals if v["ko_group"] == n]
              for n in ("CTL", "Low KO", "High KO")}
        two_s, three_s = two_groups(ctl, pten), three_groups(by)
        out.append({
            "key": key, "name": name, "unit": unit, "words": words,
            "values": vals,
            "two": dict(two_s, ctl=_summ(ctl), pten=_summ(pten)),
            "three": dict(three_s, **{n: _summ(by[n]) for n in by}),
            "usual": usual(ctl, pten, by, two_s, three_s),
            "spearman": spearman([(0.0 if str(v["group"]).upper() == "CTL"
                                   else v["ko"], v["value"]) for v in vals]),
            "dose": dose([(v["ko"], v["value"]) for v in vals
                          if str(v["group"]).upper() != "CTL"]),
        })
    # The false discovery rate, held across the measures, for each way of
    # comparing: its rank test (Mann-Whitney / Kruskal-Wallis / Spearman).
    for way, get in (("two", lambda m: m["two"].get("mwu_p")),
                     ("three", lambda m: m["three"].get("kw_p")),
                     ("ko", lambda m: m["dose"].get("p"))):
        qs = bh([get(m) for m in out])
        for m, q in zip(out, qs):
            m.setdefault("q", {})[way] = q
    # The same rate for the usual tests: shown beside each, not a gate.
    for way, get in (("two", lambda m: m["usual"]["two"].get("p")),
                     ("three", lambda m: m["usual"]["three"].get("p")),
                     ("ko", lambda m: m["dose"].get("p"))):
        qs = bh([get(m) for m in out])
        for m, q in zip(out, qs):
            m.setdefault("q_usual", {})[way] = q
    return {"metrics": out, "split": float(split), "n": len(rows),
            "groups": {"CTL": sum(1 for x in rows if x["ko_group"] == "CTL"),
                       "Low KO": sum(1 for x in rows if x["ko_group"] == "Low KO"),
                       "High KO": sum(1 for x in rows if x["ko_group"] == "High KO"),
                       "PTEN": sum(1 for x in rows
                                   if str(x["group"]).upper() != "CTL")}}
