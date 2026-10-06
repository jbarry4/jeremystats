# -*- coding: utf-8 -*-
"""rootcanalpool.py -- Root Canal across recordings: one cloud or two?

Single (`rootcanal.py`) asks of one recording which events are IEDs. Pooled
asks the question that sits underneath it: do dentate spikes and IEDs form
TWO CLEAR CLUSTERS at all, or one ambiguous spectrum that k-means will cut in
two whatever is there? Asked across recordings, by mouse and by mouse type,
with a focus on any one mouse. Every choice below was made with the user on
2026-10-01 (ROOTCANAL-POOL-SPEC.md) and is not a setting.

WHAT A MEMBER IS
================
A single recording's Root Canal answer, in one of two forms, each marked:

  banked     a classification in the results bank (`ROOTCANAL`, filed by the
             Single commit). It already holds every event's raw numbers and
             its call, so pooling it reads NO recording. Pinned by entry,
             `ds_version` and the record's `params_hash`.
  unbanked   a read cached on this machine, fitted at the settings it is
             added with. Pinned by entry, read hash and fit params, and the
             digest of the rows it produced -- because the rows are only
             rebuildable while that read is on this machine.

Either way a member arrives here as rows: [i, t, amp_uV, hw_ms, hf_db, cls].
Nothing in this module reads a recording or a cache; `app.py` assembles the
members and this does the arithmetic.

THE ARITHMETIC
==============
POOLED RAW UNITS, z-scored ONCE. Every member's raw amplitude (uV),
half-width (ms) and HF power (dB) go into one table and are z-scored across
the whole pool. Not per recording: a per-recording z-score would make every
recording's cloud the same size and centre, and erase exactly the between-
mouse differences -- in event size, impedance and placement included --
that the pooled view exists to show.

ONE K-MEANS, k = 2, on the pooled z-space, with Single's `random_state`,
`n_init` and naming rule (the higher raw-HF centre is IED), and Single's
handling of partial events: fitted on complete 3-axis events only, a 2-axis
event assigned to the nearer centre on the axes it has, nothing imputed.
Each event keeps `cls_single` -- its own recording's call, hand flips
included -- beside `cls_pool`, and `switched` is where they differ.

CLEAR VS BLUR is a Gaussian mixture, one component against two, compared by
BIC (full covariance, fixed seed, n_init 5) on the complete events in the
pooled z-space. dBIC = BIC1 - BIC2, positive favouring two groups, read on
the conventional scale: < 2 no support, 2-6 positive, 6-10 strong, > 10 very
strong. BIC compares GAUSSIAN SHAPES: one skewed cloud can earn two
components, so the verdict says it is evidence and not proof. The same test
runs on the focused mouse (or type) alone when one is focused, in the same
pooled z-space, labelled as that mouse's, beside the pool-wide one.

THE SPLIT AXIS is the line through the two k-means centres, and each
complete event's position along it -- in z units, 0 at the midpoint between
the centres, DS negative and IED positive -- is what the panel histograms.
A partial event has no position on that line (one of its coordinates is
missing), so its value is null rather than a projection of a guess.

ONE BAND. A pool refuses members fitted over different HF bands: the third
axis would be two different measurements under one label, and nothing in
the numbers would say so.

NOTHING HERE DRAWS, and nothing here writes to the Event Bank -- ever.
Banking stays per recording, in Single.
"""
from __future__ import annotations

import hashlib
import json
import re

import numpy as np

from . import rootcanal

try:
    from sklearn.cluster import KMeans
    from sklearn.mixture import GaussianMixture
    HAVE_SKLEARN = True
except Exception:                                        # noqa: BLE001
    KMeans = GaussianMixture = None
    HAVE_SKLEARN = False

AXES = rootcanal.AXES
SEED = rootcanal.SEED
N_INIT = rootcanal.N_INIT
GMM_N_INIT = 5
# The fewest complete events a 1-vs-2 comparison is attempted on. Two full-
# covariance Gaussians in three dimensions are 19 free parameters; fewer
# events than this and BIC is comparing noise.
GMM_MIN_N = 20
# The conventional dBIC scale (Kass & Raftery), as the user asked for it.
DBIC_SCALE = ((2.0, "no support for two groups"),
              (6.0, "positive support for two groups"),
              (10.0, "strong support for two groups"),
              (float("inf"), "very strong support for two groups"))


class PoolError(rootcanal.RootCanalError):
    """Something a person can fix, said in a sentence."""


# --------------------------------------------------------------------------
# Mice and their types
# --------------------------------------------------------------------------
def mouse_key(project, mouse, gid=None):
    """`<PROJECT>|m<n>`. Never the number alone.

    Mouse numbering restarts per project -- m13 exists in PTEN and in KCNT1
    and they are different animals -- so a key without the project merges
    two mice into one and every per-mouse number with them. A recording whose
    mouse is not known is its own mouse, keyed on its registry id, rather
    than joining an "unknown" mouse with everything else nobody numbered.
    """
    proj = str(project or "Unfiled").strip() or "Unfiled"
    if mouse in (None, ""):
        return "%s|gid:%s" % (proj, gid or "?")
    try:
        n = int(mouse)
        return "%s|m%d" % (proj, n)
    except (TypeError, ValueError):
        return "%s|m%s" % (proj, str(mouse).strip())


_WT = re.compile(r"(^|[\\/_\- ])wt($|[\\/_\- ])", re.IGNORECASE)


def mouse_type_of(project, cohort=None, paths=()):
    """The registry's filing, as a type: the project plus its cohort.

    `PTEN_DKO` is the cohort sessreg reads off the folders; a cohort that
    already names the project is used as it is, one that does not is
    prefixed with it. Failing a cohort, `wt` where a path says so (the KCNT1
    urethane tree files its wild types under a `wt` folder). Failing both,
    the project alone. A person can override any of it in the pool.
    """
    proj = str(project or "Unfiled").strip() or "Unfiled"
    coh = str(cohort or "").strip()
    if coh:
        return coh if coh.upper().startswith(proj.upper()) \
            else "%s %s" % (proj, coh)
    if any(_WT.search(str(p or "")) for p in (paths or ())):
        return "%s wt" % proj
    return proj


# --------------------------------------------------------------------------
# Members as rows
# --------------------------------------------------------------------------
def rows_from_record(rec):
    """A banked classification's per-event rows, by column NAME.

    By name rather than position because the record's column list grew
    (`axes`, `partial`, `wide` arrived later), and a record filed before that
    must still read back right rather than shifting a column.
    """
    cols = list(rec.get("columns") or [])
    out = []
    for r in rec.get("rows") or []:
        d = dict(zip(cols, r))
        out.append({"i": int(d.get("i")), "t": float(d.get("t")),
                    "amp_uV": _num(d.get("amp_uV")),
                    "hw_ms": _num(d.get("hw_ms")),
                    "hf_db": _num(d.get("hf_db")),
                    "cls": d.get("cls"),
                    "flipped": bool(d.get("flipped")),
                    "wide": bool(d.get("wide"))})
    return out


def rows_from_fit(res):
    """An unbanked member's rows, from `rootcanal.fit` at its settings."""
    # The contact and polarity travel with the numbers: an average over a
    # pool needs each event's own max contact, and asking for them again
    # would mean measuring every member's read again.
    return [{"i": e["i"], "t": e["t"], "amp_uV": e["amp_uV"],
             "hw_ms": e["hw_ms"], "hf_db": e["hf_db"], "cls": e["cls"],
             "flipped": bool(e.get("flipped")), "wide": bool(e.get("wide")),
             "row": e.get("contact_row"), "pol": e.get("polarity")}
            for e in res["events"]]


def single_calls(rows, k=rootcanal.K_DEFAULT):
    """Rows with each event's SINGLE call recomputed: the recording clustered
    on its own, at `k`, by the rule -- no hand calls, no margin. What a
    member's own call means when the pool asks it at settings other than
    the ones it was banked with."""
    X = np.array([[_nan(r["amp_uV"]), _nan(r["hw_ms"]), _nan(r["hf_db"])]
                  for r in rows], dtype=float).reshape(-1, 3)
    if not len(rows):
        return []
    try:
        core = rootcanal.cluster_core(X, k=k, what="events of this member")
    except rootcanal.RootCanalError:
        return [dict(r, cls=None, flipped=False) for r in rows]
    out = []
    for j, r in enumerate(rows):
        lab = int(core["lab"][j])
        out.append(dict(r, cls=(core["calls"][lab] if lab >= 0 else None),
                        flipped=False))
    return out


def rows_digest(rows):
    """What an unbanked member produced, as a name.

    The pin that says "these exact numbers": a read refitted at the same
    settings on another day must give the same digest, and one that does not
    is a different member however its settings read.
    """
    blob = json.dumps([[r["i"], round(r["t"], 6), _r(r["amp_uV"]),
                        _r(r["hw_ms"]), _r(r["hf_db"]), r["cls"]]
                       for r in rows], separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _r(v):
    return None if v is None else round(float(v), 6)


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


# --------------------------------------------------------------------------
# The tests
# --------------------------------------------------------------------------
def verdict(delta):
    for top, words in DBIC_SCALE:
        if delta < top:
            return words
    return DBIC_SCALE[-1][1]


def gmm_test(Zc, mu, sd, seed=SEED, n_init=GMM_N_INIT, label=None,
             calls=None):
    """One Gaussian against two, by BIC, on complete events in z-space.

    Components are reported in raw units and ordered by HF power, so the
    second is always the higher-power one -- the same reading direction as
    the k-means naming rule, and stable from one fit to the next.

    AND WHETHER ITS TWO GROUPS ARE THE DS / IED SPLIT. `calls` is the pooled
    k-means call per row ("ds" / "ied"). Without this the verdict answers a
    different question from the one being asked. Measured on the first real
    pool here (18 PTEN recordings, 2761 events): ΔBIC +881, "very strong
    support for two groups" -- and the GMM's two groups agreed with the
    DS / IED call on 64% of events, adjusted Rand 0.07, with a split axis of
    one hump and a long tail. Two Gaussians fitted a skewed cloud better
    than one; they were not the two kinds of event. A verdict that said
    "very strong" and stopped there would have said the opposite of what
    the data showed, so the agreement is reported beside it and the
    sentence is worded on it.
    """
    Zc = np.asarray(Zc, dtype=float)
    n = int(Zc.shape[0])
    who = ("%s: " % label) if label else ""
    if n < GMM_MIN_N:
        return {"n": n, "bic1": None, "bic2": None, "delta": None,
                "verdict": ("%sToo few complete events (%d) to compare one "
                            "group against two; at least %d are needed."
                            % (who, n, GMM_MIN_N)),
                "weights": None, "means_raw": None, "label": label}
    g1 = GaussianMixture(n_components=1, covariance_type="full",
                         random_state=seed, n_init=n_init).fit(Zc)
    g2 = GaussianMixture(n_components=2, covariance_type="full",
                         random_state=seed, n_init=n_init).fit(Zc)
    bic1, bic2 = float(g1.bic(Zc)), float(g2.bic(Zc))
    delta = bic1 - bic2
    means = g2.means_ * sd + mu
    order = np.argsort(means[:, 2])
    words = verdict(delta)

    agree = None
    tail = ""
    if calls is not None and len(calls) == n:
        from sklearn.metrics import adjusted_rand_score
        comp = g2.predict(Zc)
        # The component ordered second (higher HF) reads as "IED-like".
        ied_like = int(order[1])
        g_ied = comp == ied_like
        k_ied = np.array([c == "ied" for c in calls], dtype=bool)
        ok = np.array([c in ("ds", "ied") for c in calls], dtype=bool)
        if ok.sum() >= GMM_MIN_N:
            ari = float(adjusted_rand_score(k_ied[ok], g_ied[ok]))
            same = float((k_ied[ok] == g_ied[ok]).mean())
            agree = {
                "ari": ari, "same": same, "n": int(ok.sum()),
                "crosstab": {
                    "ds": {"ds_like": int((~k_ied & ~g_ied & ok).sum()),
                           "ied_like": int((~k_ied & g_ied & ok).sum())},
                    "ied": {"ds_like": int((k_ied & ~g_ied & ok).sum()),
                            "ied_like": int((k_ied & g_ied & ok).sum())},
                },
            }
            # Worded on the agreement, because that is what decides what
            # the BIC is evidence OF here.
            if delta >= 2 and ari >= 0.5:
                tail = (" Its two groups match the DS / IED call closely "
                        "(adjusted Rand %.2f, %.0f%% of events the same), so "
                        "this reads as two kinds of event." % (ari, 100 * same))
            elif delta >= 2:
                # Graded on the Rand index, which is corrected for chance.
                # Percent agreement is not: with a 64/36 call against a
                # 50/50 component split, chance alone gives about 50%.
                how = "barely" if ari < 0.2 else "only partly"
                tail = (" But its two groups are %s the DS / IED split "
                        "(adjusted Rand %.2f, where 1 is the same split and "
                        "0 is chance; %.0f%% of events the same): two "
                        "Gaussians fit the cloud's SHAPE better than one, "
                        "which a single skewed spectrum also does. Read the "
                        "split-axis histogram before reading this as two "
                        "populations." % (how, ari, 100 * same))
            else:
                tail = (" Its two groups agree with the DS / IED call on "
                        "%.0f%% of events (adjusted Rand %.2f)."
                        % (100 * same, ari))
    return {
        "n": n, "bic1": bic1, "bic2": bic2, "delta": delta,
        "verdict": ("%sΔBIC = %+.1f (one group %.1f, two groups %.1f): %s. "
                    "BIC compares Gaussian shapes, and a single skewed cloud "
                    "can earn two components, so this is evidence, not "
                    "proof.%s" % (who, delta, bic1, bic2, words, tail)),
        "support": words,
        "agree": agree,
        "weights": [float(g2.weights_[k]) for k in order],
        "means_raw": [[float(v) for v in means[k]] for k in order],
        "label": label,
    }


def _switch_row(evs):
    both = [e for e in evs if e["cls_single"] and e["cls_pool"]]
    sw = [e for e in both if e["switched"]]
    return {"n": len(both), "switched": len(sw),
            "rate": (len(sw) / float(len(both))) if both else None,
            "ds_to_ied": sum(1 for e in sw if e["cls_single"] == "ds"),
            "ied_to_ds": sum(1 for e in sw if e["cls_single"] == "ied")}


def switch_tables(events, members):
    """The identity switch, counted: the crosstab, the rate, and the rate
    per member, per mouse and per mouse type.

    Over events that have BOTH calls. An event its own recording left
    unclassified, or the pool could not place, has nothing to switch from or
    to, and counting it as "unchanged" would flatter the rate.
    """
    ct = {"ds": {"ds": 0, "ied": 0}, "ied": {"ds": 0, "ied": 0}}
    for e in events:
        if e["cls_single"] in ct and e["cls_pool"] in ("ds", "ied"):
            ct[e["cls_single"]][e["cls_pool"]] += 1
    whole = _switch_row(events)
    by_member = []
    for k, m in enumerate(members):
        row = _switch_row([e for e in events if e["m"] == k])
        by_member.append(dict(row, key=m["key"], entry_id=m["entry_id"],
                              session_label=m.get("session_label")))
    by_mouse, by_type = [], []
    for name, field, out in (("mouse_key", "mouse_key", by_mouse),
                             ("mouse_type", "mouse_type", by_type)):
        for val in sorted({e[field] for e in events}):
            row = _switch_row([e for e in events if e[field] == val])
            out.append(dict(row, **{name: val}))
    return {"crosstab": ct, "n": whole["n"], "switched": whole["switched"],
            "rate": whole["rate"], "ds_to_ied": whole["ds_to_ied"],
            "ied_to_ds": whole["ied_to_ds"],
            "by_member": by_member, "by_mouse": by_mouse, "by_type": by_type}


# --------------------------------------------------------------------------
# The pool
# --------------------------------------------------------------------------
def fit_pool(members, mouse_types=None, focus=None, seed=SEED,
             n_init=N_INIT, gmm_n_init=GMM_N_INIT, complete_only=False,
             k=rootcanal.K_DEFAULT, cluster_calls=None, margin=None,
             margin_mode="fixed", drawn=None):
    """Pool the members' rows and answer the three questions.

    `members` is a list of dicts as `app.py` builds them: key, entry_id,
    session_label, gid, project, mouse_key, mouse_type (the registry
    default), banked, pin, band [lo, hi], rows. `mouse_types` overrides any
    mouse's type and wins over the registry. Returns what
    `/api/rootcanal/pool/fit` sends, bar `ok`.
    """
    if not HAVE_SKLEARN:
        raise PoolError(rootcanal.dspca.NO_SKLEARN)
    # Taken now: the member loop below reuses the name `k`, and the number
    # of clusters asked for must not become the last member's index.
    k_want = int(k)
    if not rootcanal.K_MIN <= k_want <= rootcanal.K_MAX:
        raise PoolError("The number of clusters has to be %d to %d, not %d."
                        % (rootcanal.K_MIN, rootcanal.K_MAX, k_want))
    if not members:
        raise PoolError("A pool needs at least one member. Add a recording.")
    keys = [m["key"] for m in members]
    if len(set(keys)) != len(keys):
        raise PoolError("The same member was added twice; take one out.")
    bands = {tuple(float(b) for b in (m.get("band") or rootcanal.BAND))
             for m in members}
    if len(bands) > 1:
        raise PoolError(
            "These members were fitted over different HF bands (%s), so "
            "their third axis is not one measurement. Refit them over one "
            "band before pooling."
            % ", ".join("%s–%s Hz" % (rootcanal._g(a), rootcanal._g(b))
                        for a, b in sorted(bands)))
    band = list(bands.pop())
    # ONE FILTER, for the same reason as one band: amplitude and half-width
    # measured on two different filters are two measurements under one
    # axis label, and a mains-heavy recording measured unfiltered would
    # sit apart from the rest for a reason that has nothing to do with it.
    filts = {m.get("filter") for m in members if m.get("filter")}
    if len(filts) > 1:
        raise PoolError(
            "These members were measured on different filters (%s), so "
            "their amplitude and half-width are not one measurement. Refit "
            "them on one filter before pooling."
            % "; ".join(sorted(filts)))
    over = {str(k): str(v).strip() for k, v in (mouse_types or {}).items()
            if str(v or "").strip()}

    mem_out, ev, X = [], [], []
    for k, m in enumerate(members):
        mtype = over.get(m["mouse_key"]) or m.get("mouse_type") or ""
        rows = m.get("rows") or []
        mem_out.append({"key": m["key"], "entry_id": m["entry_id"],
                        "session_label": m.get("session_label"),
                        "gid": m.get("gid"), "project": m.get("project"),
                        "mouse_key": m["mouse_key"], "mouse_type": mtype,
                        "mouse_type_default": m.get("mouse_type"),
                        "banked": bool(m.get("banked")), "n": len(rows),
                        "here": bool(m.get("here")),
                        "pin": m.get("pin") or {},
                        "event_body": m.get("event_body")})
        for r in rows:
            X.append([_nan(r["amp_uV"]), _nan(r["hw_ms"]), _nan(r["hf_db"])])
            ev.append({"m": k, "i": int(r["i"]), "t": float(r["t"]),
                       "cls_single": r.get("cls"),
                       "wide": bool(r.get("wide")),
                       "mouse_key": m["mouse_key"], "mouse_type": mtype})
    X = np.asarray(X, dtype=float).reshape(-1, 3)

    # COMPLETE EVENTS ONLY, when asked. An event missing an axis -- a
    # half-width that never came back to half amplitude, an HF window too
    # near an edge -- is normally assigned on the two it has and marked.
    # With this on it is left out of the pool altogether: not scaled, not
    # clustered, not in the GMM or the switch tables, and not drawn. The
    # count of what was left out travels with the answer, because a pool
    # that quietly lost its slowest events would read as cleaner than it is.
    n_excluded = 0
    by_member_excluded = {}
    if complete_only and len(ev):
        keep = np.isfinite(X).all(axis=1)
        n_excluded = int((~keep).sum())
        for j in np.where(~keep)[0]:
            k = ev[j]["m"]
            by_member_excluded[k] = by_member_excluded.get(k, 0) + 1
        X = X[keep]
        ev = [e for e, kp in zip(ev, keep) if kp]
        if not len(ev):
            raise PoolError(
                "Every pooled event is missing at least one axis, so "
                "keeping complete events only leaves nothing to pool.")
    n = X.shape[0]
    # Pooled raw, z-scored once (see the module docstring) -- or, with a
    # margin, on the margin's own scale. The clustering is Single's own
    # `cluster_core`, so the two views cannot drift apart.
    # Drawn clusters arrive as (member key, event number) pairs, and are
    # turned here into positions in the pooled list.
    pos = {(mem_out[e["m"]]["key"], int(e["i"])): j for j, e in enumerate(ev)}
    drawn_ix = []
    for grp in (drawn or []):
        ix = [pos[(str(a), int(b))] for a, b in (grp.get("events") or [])
              if (str(a), int(b)) in pos]
        if ix:
            drawn_ix.append((ix, str(grp.get("call") or "ied")))
    try:
        core = rootcanal.cluster_core(
            X, k=k_want, seed=seed, n_init=n_init, cluster_calls=cluster_calls,
            margin=margin, margin_mode=margin_mode, what="pooled events",
            drawn=drawn_ix)
    except rootcanal.RootCanalError as exc:
        raise PoolError(str(exc))
    have, n_axes = core["have"], core["n_axes"]
    use, part, placed = core["use"], core["part"], core["placed"]
    n_used, mu, sd, Z = core["n_used"], core["mu"], core["sd"], core["Z"]
    C, raw_c, lab = core["C"], core["raw_c"], core["lab"]
    cls_of = {r: core["calls"][r]
              for r in range(core["k"] + core["n_drawn"])}

    # THE SPLIT AXIS: from the mean of the DS-called events to the mean of
    # the IED-called ones (complete events, z), 0 at their midpoint, DS
    # negative. At k = 2 by k-means that is the line through the two
    # centres -- a k-means centre IS the mean of its events -- and it means
    # the same thing at any k. With one call only (k = 1, or every cluster
    # relabelled alike) there is no line, and it says so.
    call_of = np.array([cls_of[int(c)] if c >= 0 else "" for c in lab])
    ds_m = use & (call_of == "ds")
    ied_m = use & (call_of == "ied")
    split_ok = bool(ds_m.any() and ied_m.any())
    if split_ok:
        a, b = Z[ds_m].mean(axis=0), Z[ied_m].mean(axis=0)
        u = b - a
        norm = float(np.linalg.norm(u)) or 1.0
        u = u / norm
        mid = (a + b) / 2.0

    counts = {"ds": 0, "ied": 0, "unmeasured": 0, "partial": 0, "wide": 0}
    why_part = {}
    split_vals = []
    for j, e in enumerate(ev):
        e["amp_uV"], e["hw_ms"], e["hf_db"] = (_f(X[j, 0]), _f(X[j, 1]),
                                              _f(X[j, 2]))
        e["z"] = [_f(v) for v in Z[j]]
        e["partial"] = bool(part[j])
        e["axes"] = int(n_axes[j]) if placed[j] else None
        e["missing"] = [AXES[a] for a in range(3) if not have[j, a]]
        e["cluster"] = int(lab[j]) if placed[j] else None
        e["cls_pool"] = cls_of[int(lab[j])] if placed[j] else None
        e["switched"] = bool(e["cls_single"] and e["cls_pool"]
                             and e["cls_single"] != e["cls_pool"])
        if placed[j]:
            counts[e["cls_pool"]] += 1
        else:
            counts["unmeasured"] += 1
        if part[j]:
            counts["partial"] += 1
            why_part[e["missing"][0]] = why_part.get(e["missing"][0], 0) + 1
        if e["wide"]:
            counts["wide"] += 1
        split_vals.append(float(np.dot(Z[j] - mid, u))
                          if (use[j] and split_ok) else None)

    centres = [{"z": [rootcanal._f(v) for v in C[r]],
                "raw": [rootcanal._f(v) for v in raw_c[r]],
                "cls": cls_of[r], "n": int((lab == r).sum()),
                "drawn": r >= core["k"]}
               for r in range(core["k"] + core["n_drawn"])]
    gids = {m.get("gid") for m in members}
    mice = {m["mouse_key"] for m in members}
    band_label = "%s–%s Hz power" % (rootcanal._g(band[0]),
                                     rootcanal._g(band[1]))
    crosses = sorted({float((m.get("pin") or {}).get("params", {})
                            .get("cross_ms") or rootcanal.CROSS_MS)
                      for m in members})
    extra = []
    if counts["unmeasured"]:
        extra.append(", %d not measured" % counts["unmeasured"])
    if counts["partial"]:
        extra.append("; " + rootcanal.partial_sentence(
            counts["partial"], why_part,
            "/".join(rootcanal._g(c) for c in crosses)))
    if counts["wide"]:
        extra.append("; %d resolved only with a half-width search widened "
                     "past 50 ms" % counts["wide"])
    general = rootcanal.k_sentence(core, band_label)
    where = ("Pooled over %d recording%s from %d %s, in %s: "
             % (len(gids), "" if len(gids) == 1 else "s", len(mice),
                "mouse" if len(mice) == 1 else "mice",
                "the margin's own scale" if margin else "pooled raw units"))
    if core["n_drawn"]:
        extra.append("; %d event%s in %d cluster%s drawn by hand" % (
            int(core["held"].sum()), "" if int(core["held"].sum()) == 1 else "s",
            core["n_drawn"], "" if core["n_drawn"] == 1 else "s"))
    if general:
        rule = ("%s%s (%d DS, %d IED%s)."
                % (where, general, counts["ds"], counts["ied"],
                   "".join(extra)))
    else:
        ied_c = int(np.argmax(raw_c[:, 2]))
        rule = ("%sthe cluster whose centre has more %s is called IED: %s "
                "dB against %s dB for the other, which is called DS (%d DS, "
                "%d IED%s)."
                % (where, band_label, rootcanal._db_s(raw_c[ied_c, 2]),
                   rootcanal._db_s(raw_c[1 - ied_c, 2]), counts["ds"],
                   counts["ied"], "".join(extra)))

    calls = [e["cls_pool"] for e in ev]
    gmm = gmm_test(Z[use], mu, sd, seed, gmm_n_init,
                   calls=[calls[j] for j in range(n) if use[j]])
    gmm_focus = None
    fkey, fval = _focus(focus)
    if fkey:
        sel = np.array([use[j] and ev[j][fkey] == fval
                        for j in range(n)], dtype=bool)
        gmm_focus = gmm_test(Z[sel], mu, sd, seed, gmm_n_init,
                             calls=[calls[j] for j in range(n) if sel[j]],
                             label="%s %s" % (
                                 "Mouse" if fkey == "mouse_key"
                                 else "Mouse type", fval))
        gmm_focus["focus"] = {fkey: fval}

    return {
        "n": n, "n_used": n_used, "n_placed": int(placed.sum()),
        "axes": [{"key": "amp_uV", "label": "max amplitude", "unit": "µV"},
                 {"key": "hw_ms", "label": "half-width", "unit": "ms"},
                 {"key": "hf_db", "label": band_label,
                  "unit": "dB re baseline"}],
        "members": mem_out,
        "events": ev,
        "centres": centres,
        "rule": rule,
        "scale": {"mean": [float(v) for v in mu],
                  "sd": [float(v) for v in sd],
                  "why": ("Pooled raw units, z-scored once across the pool: "
                          "differences in size between mice stay visible, "
                          "impedance and placement included.")},
        "gmm": gmm,
        "gmm_focus": gmm_focus,
        "switches": switch_tables(ev, mem_out),
        "split_axis": {"centres_z": ([[float(v) for v in a],
                                      [float(v) for v in b]]
                                     if split_ok else None),
                       "values": split_vals,
                       "unit": "z, 0 at the midpoint, DS negative",
                       "why_none": (None if split_ok else
                                    "every cluster has the same call, so "
                                    "there is no DS-to-IED line")},
        "k": core["k"],
        "clusters": rootcanal.clusters_out(core),
        "counts": dict(counts, excluded=n_excluded),
        "excluded": {"n": n_excluded, "complete_only": bool(complete_only),
                     "by_member": [{"key": mem_out[k]["key"], "n": v}
                                   for k, v in sorted(
                                       by_member_excluded.items())]},
        "params": dict(pool_params(seed, n_init, gmm_n_init, band),
                       complete_only=bool(complete_only), k=core["k"],
                       cluster_calls=dict(cluster_calls or {}),
                       margin_mode=(margin_mode if margin else None)),
    }


def pool_params(seed=SEED, n_init=N_INIT, gmm_n_init=GMM_N_INIT, band=None):
    return {"scale": "pooled raw", "k": 2, "random_state": int(seed),
            "n_init": int(n_init),
            "gmm": {"covariance": "full", "n_init": int(gmm_n_init),
                    "random_state": int(seed), "min_n": GMM_MIN_N,
                    "compare": [1, 2]},
            "dbic_scale": [[t if np.isfinite(t) else None, w]
                           for t, w in DBIC_SCALE],
            "band": list(band or rootcanal.BAND)}


def _focus(focus):
    f = focus or {}
    if f.get("mouse_key"):
        return "mouse_key", str(f["mouse_key"])
    if f.get("mouse_type"):
        return "mouse_type", str(f["mouse_type"])
    return None, None


def _nan(v):
    return np.nan if v is None else float(v)


def _f(v):
    return float(v) if v is not None and np.isfinite(v) else None


# --------------------------------------------------------------------------
# What a saved pool is
# --------------------------------------------------------------------------
def pool_name(members):
    """"Root Canal pool · PTEN + KCNT1 · 12 recordings, 9 mice"."""
    projects = sorted({str(m.get("project") or "Unfiled") for m in members})
    n_rec = len({m.get("gid") for m in members})
    n_mice = len({m["mouse_key"] for m in members})
    return "Root Canal pool · %s · %d recording%s, %d %s" % (
        " + ".join(projects), n_rec, "" if n_rec == 1 else "s", n_mice,
        "mouse" if n_mice == 1 else "mice")


def payload_of(res, pool_key, mouse_types=None, focus=None):
    """Everything a saved pool needs to reopen and be explored with NO
    recording read: the pinned members, the overrides, the parameters, every
    dot, the centres and rule, both tests and the switch tables."""
    out = dict(res)
    out["pool_key"] = pool_key
    out["mouse_types"] = {str(k): str(v) for k, v in
                          sorted((mouse_types or {}).items())
                          if str(v or "").strip()}
    out["focus"] = focus or None
    return out
