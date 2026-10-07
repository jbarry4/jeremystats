# -*- coding: utf-8 -*-
"""rcborder.py -- a DS / IED border in three numbers, with grace.

Asked for 2026-10-06 (the meeting with Shahriar, steps 8-9): after the
controls are pooled as all DS and the IED mice pooled at k = 2, and the two
pools pooled together, draw the border between DS and IED as three cut-offs
-- one in µV, one in dB, one in ms -- that anyone can apply to any set
measured the same way, with no k-means.

THE RULE (decided with the user):

  past all three cut-offs      solid IED
  short of all three           solid DS
  anything else                ambiguous

"Past" is towards IED on that axis, and which way that is comes from the
data: on every set looked at so far IEDs are larger, louder in the HF band
and NARROWER, so the half-width cut-off is passed by going under it. An
event missing an axis cannot be past or short of all three, so it is
ambiguous; one with no numbers at all is not classified.

THE STRICT BORDER is the three cut-offs that best separate the events' own
identities (each event's v0: what its own pool called it, in a pool of
pools; its single's call, in a pool). "Best" is Youden's index, once per
solid class: the share of IED events that come out solid IED less the share
of DS events that do, plus the same for solid DS. Shares, so a pool of 900
DS and 300 IED does not draw its border wherever the 900 are happiest; and
less the wrong ones, because the share put right alone is won by a border
that calls nearly everything solid IED (tried on the real pool of 19
singles: 98% of IED events solid IED, no DS solid at all, and half the DS
events called solid IED). The candidates are 40 quantiles of each axis,
every combination of the three tried.

GRACE (decided with the user) is the identity-switch rate allowed: of the
events with an identity, how many may land in the solid class of the OTHER
identity. "None" allows no switch at all. Each cut-off is widened into a
band, the same number of standard deviations on every axis, until the rate
is at most the grace; the events in a band are ambiguous. So the strict
border is the middle of the band, and the band's two edges are where an
event becomes solid IED (one side) and solid DS (the other). Widening only
ever moves events from solid to ambiguous, so the smallest band that meets
the grace is found by stepping out from zero.

A border is in raw units, so it is only the same border under the same
measurement -- filter, mains, HF band, window, search -- which the app
checks before it applies one, as it does for a margin.
"""
from __future__ import annotations

import numpy as np

AXES = (("amp_uV", "max amplitude", "µV"),
        ("hf_db", "HF power", "dB"),
        ("hw_ms", "half-width", "ms"))
GRACES = (0.0, 0.01, 0.05)
N_Q = 40               # candidate cut-offs per axis
S_STEP = 0.02          # band step, in standard deviations
S_MAX = 8.0
MIN_EACH = 5           # complete events of each identity needed


class BorderError(ValueError):
    pass


def _f(v):
    return None if v is None or not np.isfinite(v) else float(v)


def _matrix(events):
    return np.array([[np.nan if e.get(k) is None else float(e[k])
                      for k, _l, _u in AXES] for e in events],
                    dtype=float).reshape(-1, 3)


def identities(events, key="cls_single"):
    """1 for an IED identity, 0 for DS, -1 for none."""
    return np.array([1 if e.get(key) == "ied" else 0 if e.get(key) == "ds"
                     else -1 for e in events], dtype=int)


def _signs(ied_above):
    return np.array([1.0 if ied_above[k] else -1.0 for k, _l, _u in AXES])


def classify(U, ied_at, ds_at):
    """Classes of signed values: past every `ied_at` is solid IED, short of
    every `ds_at` solid DS, anything else ambiguous; no values, None."""
    fin = np.isfinite(U)
    full = fin.all(axis=1)
    with np.errstate(invalid="ignore"):
        ied = full & (U >= ied_at).all(axis=1)
        ds = full & (U < ds_at).all(axis=1)
    out = np.full(U.shape[0], "amb", dtype=object)
    out[ied] = "ied"
    out[ds] = "ds"
    out[~fin.any(axis=1)] = None
    return out


def _counts(cls, y):
    c = {"ds": int(np.sum(cls == "ds")), "ied": int(np.sum(cls == "ied")),
         "amb": int(np.sum(cls == "amb")),
         "none": int(sum(1 for v in cls if v is None))}
    wrong = int(np.sum((cls == "ied") & (y == 0))
                + np.sum((cls == "ds") & (y == 1)))
    n_id = int(np.sum(y >= 0))
    return c, wrong, (wrong / n_id if n_id else None)


def _past(M, cands):
    return (M[None, :] >= cands[:, None]).astype(np.float32)


def _count3(A, B, C):
    """For every (a, b, c): how many events pass A[a], B[b] and C[c]."""
    out = np.empty((A.shape[0], B.shape[0], C.shape[0]), dtype=np.float32)
    for i in range(A.shape[0]):
        out[i] = (B * A[i]) @ C.T
    return out


def fit_strict(U, y, n_q=N_Q):
    """The three cut-offs (signed) that best enrich each solid class in its
    own identity: Youden's index for solid IED plus that for solid DS."""
    comp = np.isfinite(U).all(axis=1) & (y >= 0)
    Uc, yc = U[comp], y[comp]
    n_i, n_d = int((yc == 1).sum()), int((yc == 0).sum())
    if n_i < MIN_EACH or n_d < MIN_EACH:
        raise BorderError(
            "A border is drawn between two identities, and this has %d "
            "complete events with an IED identity and %d with a DS one; at "
            "least %d of each are needed." % (n_i, n_d, MIN_EACH))
    qs = np.linspace(0.02, 0.98, n_q)
    cands = [np.unique(np.quantile(Uc[:, a], qs)) for a in range(3)]
    I, D = Uc[yc == 1], Uc[yc == 0]
    PI = [_past(I[:, a], cands[a]) for a in range(3)]
    PD = [_past(D[:, a], cands[a]) for a in range(3)]
    good_i = _count3(*PI)                                # IED, solid IED
    good_d = _count3(*[1 - m for m in PD])               # DS, solid DS
    bad_i = _count3(*PD)                                 # DS, solid IED
    bad_d = _count3(*[1 - m for m in PI])                # IED, solid DS
    score = (good_i / n_i - bad_i / n_d) + (good_d / n_d - bad_d / n_i)
    # Ties to the fewest switches.
    key = score - 1e-6 * (bad_i + bad_d)
    a, b, c = np.unravel_index(int(np.argmax(key)), key.shape)
    t = np.array([cands[0][a], cands[1][b], cands[2][c]])
    return t, {"youden": float(score[a, b, c]),
               "ied_solid": float(good_i[a, b, c] / n_i),
               "ds_solid": float(good_d[a, b, c] / n_d),
               "ds_as_ied": float(bad_i[a, b, c] / n_d),
               "ied_as_ds": float(bad_d[a, b, c] / n_i),
               "n_ied": n_i, "n_ds": n_d}


def _edges_raw(t, s, sd, sign):
    """The band's two edges per axis, back in raw units."""
    out = {}
    for a, (k, _l, _u) in enumerate(AXES):
        ied_at = (t[a] + s * sd[a]) * sign[a]
        ds_at = (t[a] - s * sd[a]) * sign[a]
        out[k] = {"ied_at": _f(ied_at), "ds_at": _f(ds_at),
                  "at": _f(t[a] * sign[a])}
    return out


def extract(events, custom=None, identity="cls_single"):
    """The strict border and the band at each grace, from events carrying
    raw numbers and an identity."""
    X = _matrix(events)
    y = identities(events, identity)
    comp = np.isfinite(X).all(axis=1)
    ied_above = {}
    for a, (k, _l, _u) in enumerate(AXES):
        mi = X[comp & (y == 1), a]
        md = X[comp & (y == 0), a]
        ied_above[k] = bool(mi.size and md.size
                            and np.median(mi) >= np.median(md))
    sign = _signs(ied_above)
    U = X * sign
    t, how = fit_strict(U, y)
    sd = np.nanstd(U[comp], axis=0)
    sd[~np.isfinite(sd) | (sd <= 0)] = 1.0
    graces = list(GRACES)
    if custom is not None and all(abs(custom - g) > 1e-9 for g in graces):
        graces.append(float(custom))
    graces.sort()
    # Every band on the grid at once: [steps, events].
    steps = np.arange(0.0, S_MAX + 1e-9, S_STEP)
    fin = np.isfinite(U).all(axis=1)
    with np.errstate(invalid="ignore"):
        past = [(U[None, :, a] >= (t[a] + steps[:, None] * sd[a]))
                for a in range(3)]
        short = [(U[None, :, a] < (t[a] - steps[:, None] * sd[a]))
                 for a in range(3)]
    ied = fin[None] & past[0] & past[1] & past[2]
    ds = fin[None] & short[0] & short[1] & short[2]
    wrong = (ied & (y == 0)[None]).sum(axis=1) + (ds & (y == 1)[None]).sum(
        axis=1)
    n_id = int(np.sum(y >= 0))
    rate = wrong / max(1, n_id)
    levels = []
    for g in graces:
        hit = np.nonzero(rate <= g + 1e-12)[0]
        j = int(hit[0]) if hit.size else len(steps) - 1
        s = float(steps[j])
        cls = classify(U, t + s * sd, t - s * sd)
        c, w, r = _counts(cls, y)
        levels.append({"grace": float(g), "s_sd": round(s, 4),
                       "reached": bool(hit.size),
                       "edges": _edges_raw(t, s, sd, sign),
                       "counts": c, "wrong": w, "switch_rate": r})
    cls0 = classify(U, t, t)
    c0, w0, r0 = _counts(cls0, y)
    return {
        "schema": 1,
        "axes": [{"key": k, "label": lab, "unit": u} for k, lab, u in AXES],
        "ied_above": ied_above,
        "strict": {k: _f(t[a] * sign[a]) for a, (k, _l, _u) in
                   enumerate(AXES)},
        "strict_counts": c0, "strict_wrong": w0, "strict_rate": r0,
        "fit": how,
        "sd": {k: _f(sd[a]) for a, (k, _l, _u) in enumerate(AXES)},
        "levels": levels,
        "n": len(events), "n_identity": n_id,
        "n_complete": int(comp.sum()),
        "identity": identity,
    }


def level_of(border, grace):
    """The saved band at a grace."""
    g = float(grace)
    for lv in border.get("levels") or []:
        if abs(float(lv["grace"]) - g) < 1e-9:
            return lv
    have = ", ".join(grace_words(lv["grace"])
                     for lv in border.get("levels") or [])
    raise BorderError("This border was saved with grace %s; it has no %s "
                      "band." % (have or "none", grace_words(g)))


def grace_words(g):
    g = float(g)
    return "none" if g == 0 else ("%g%%" % round(100 * g, 3))


def apply(events, border, grace, identity="cls_single"):
    """Each event's class under a saved border at one of its graces, with
    the counts -- and, where the events carry an identity, how many of
    them land in the other identity's solid class."""
    lv = level_of(border, grace)
    ab = border.get("ied_above") or {}
    sign = _signs({k: ab.get(k, True) for k, _l, _u in AXES})
    X = _matrix(events)
    ed = lv["edges"]
    ied_at = np.array([ed[k]["ied_at"] for k, _l, _u in AXES]) * sign
    ds_at = np.array([ed[k]["ds_at"] for k, _l, _u in AXES]) * sign
    cls = classify(X * sign, ied_at, ds_at)
    y = identities(events, identity)
    c, w, r = _counts(cls, y)
    return list(cls), {"counts": c, "wrong": w, "switch_rate": r,
                       "n_identity": int(np.sum(y >= 0))}


def rule_words(border, grace):
    """The rule in a sentence, at a grace."""
    lv = level_of(border, grace)
    ab = border.get("ied_above") or {}
    ed = lv["edges"]

    def side(k, which):
        unit = dict((a, u) for a, _l, u in AXES)[k]
        lab = dict((a, lab) for a, lab, _u in AXES)[k]
        v = ed[k][which + "_at"]
        up = ab.get(k, True)
        op = (("≥" if up else "≤") if which == "ied"
              else ("<" if up else ">"))
        return "%s %s %s %s" % (lab, op, _num(v), unit)

    return ("Solid IED: %s. Solid DS: %s. Anything else is ambiguous "
            "(grace %s)." % (", ".join(side(k, "ied") for k, _l, _u in AXES),
                             ", ".join(side(k, "ds") for k, _l, _u in AXES),
                             grace_words(lv["grace"])))


def _num(v):
    if v is None:
        return "?"
    return ("%.0f" % v) if abs(v) >= 100 else ("%.1f" % v)


def name(border):
    s = border.get("strict") or {}
    return "Border · %s µV · %s dB · %s ms" % (
        _num(s.get("amp_uV")), _num(s.get("hf_db")), _num(s.get("hw_ms")))
