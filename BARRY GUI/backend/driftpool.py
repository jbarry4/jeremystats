# -*- coding: utf-8 -*-
"""driftpool.py -- a within-rat Precon1 -> Precon4 drift, both cue pairings
pooled, with the no-cue (FP) recordings subtracted as a second layer.

WHAT IT ANSWERS
---------------
For one band and one window type (state: baseline, cue 1, cue 2, after cue
2; or transition: onset, switch, offset), for every window x method x
region pair -- an ENTRY:

  1. For each rat and day, every cue pair of that day, blind to its type:
     the day's two pairings' circuits are one set of cue pairs (a rat with
     8 + 8 pairs has 16). Their mean, SD and n.
  2. The rat's change: Precon4 mean - Precon1 mean; its variance the two
     days' se^2 added (se^2 = SD^2 / n).
  3. The rats' changes pooled by DerSimonian-Laird (precision-weighted),
     tested by Hartung-Knapp t on k - 1 df -- drift.pool_rats and
     drift.hk_test, the very functions every other within-rat drift uses.
  4. Benjamini-Hochberg across every tested entry of this drift (all its
     windows, methods and region pairs): one band x one window type.

The MINUS-FP layer does the same on (cue - FP) instead of cue: for each rat
and day, the entry's mean over the cue pairs minus the same entry's mean
over that day's FP1 + FP2 rest epochs (the rest circuit, same band, same
method, same region pair), its variance the two se^2 added. So the change
is (P4 cue - P4 FP) - (P1 cue - P1 FP): whatever moved the whole day -- the
electrodes, the rat's state -- is taken out. Its own BH.

WHAT COUNTS
-----------
  - An entry is tested only on at least MIN_RATS rats with it on both days
    (fewer: shown, not tested, and why).
  - Tier 1, "survives": q < .05.
  - Tier 2, "point of interest": q < .25 or p < .01, AND a simple majority
    of the rats' changes in the pooled change's direction. For sifting,
    not for claiming.

The payload is an ordinary drift payload (`cells` is the raw layer), so the
drift renderer draws it as it draws any drift; `layers.minus_fp` holds the
second layer in the same shape, and `tiers` / `min_rats` say the rules.
"""
from __future__ import annotations

import math

from . import drift

SCHEMA = drift.SCHEMA
MIN_RATS = 5
TIER1_Q = 0.05
TIER2_Q = 0.25
TIER2_P = 0.01
DAYS = ("Precon1", "Precon4")
LAYERS = ("raw", "minus_fp")
LAYER_SAY = {
    "raw": "raw change",
    "minus_fp": "minus FP: (cue − that day's FP1 + FP2 rest), then the change",
}


class PoolError(Exception):
    pass


def _cell(payload, w, m, key):
    return ((((payload or {}).get("cells") or {}).get(w) or {}).get(m)
            or {}).get(key)


def _values(cell):
    return [x for x in (cell or {}).get("values") or []
            if isinstance(x, dict) and x.get("v") is not None]


def _stats(vals):
    """mean, sd (None for n < 2), n of plain numbers."""
    n = len(vals)
    if not n:
        return None, None, 0
    mean = sum(vals) / n
    if n < 2:
        return mean, None, n
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1))
    return mean, sd, n


def day_mean(payloads, w, m, key):
    """One rat-day over every cue pair of its circuits, blind to pairing.

    Returns ({mean, sd, n, se2, pair_ids}, None) or (None, why)."""
    vals, ids = [], []
    for P in payloads:
        for x in _values(_cell(P, w, m, key)):
            pid = x.get("pair_id")
            if pid is not None and pid in ids:
                raise PoolError("cue pair %s appears in two circuits of one "
                                "recording" % pid)
            ids.append(pid)
            vals.append(float(x["v"]))
    mean, sd, n = _stats(vals)
    if n == 0:
        return None, "no usable cue pair"
    return {"mean": mean, "sd": sd, "n": n,
            "se2": None if sd is None else sd * sd / n,
            "pair_ids": ids}, None


def rest_mean(payload, m, key):
    vals = [float(x["v"]) for x in _values(_cell(payload, "rest", m, key))]
    mean, sd, n = _stats(vals)
    if n == 0:
        return None, "no usable rest epoch"
    return {"mean": mean, "sd": sd, "n": n,
            "se2": None if sd is None else sd * sd / n}, None


def _add(*se2):
    return None if any(s is None for s in se2) else sum(se2)


def entry(rats, w, m, key, layer):
    """One entry of one layer: the rats' rows, pooled and tested.

    `rats`: {rat: {"Precon1": {"cue": [payloads], "rest": payload|None},
                   "Precon4": {...}}}."""
    rows, dropped = [], []
    for rat in sorted(rats, key=drift._natkey):
        per, why = {}, []
        for day in DAYS:
            slot = rats[rat].get(day) or {}
            c, gone = day_mean(slot.get("cue") or [], w, m, key)
            if c is None:
                why.append("%s: %s" % (day, gone))
                continue
            if layer == "minus_fp":
                if slot.get("rest") is None:
                    why.append("%s: no rest circuit" % day)
                    continue
                r, gone = rest_mean(slot["rest"], m, key)
                if r is None:
                    why.append("%s: %s" % (day, gone))
                    continue
                per[day] = {"x": c["mean"] - r["mean"],
                            "se2": _add(c["se2"], r["se2"]),
                            "n": c["n"] + r["n"], "cue": c["mean"],
                            "rest": r["mean"]}
            else:
                per[day] = {"x": c["mean"], "se2": c["se2"], "n": c["n"],
                            "cue": c["mean"]}
        if why:
            dropped.append({"rat": rat, "why": "; ".join(why)})
            continue
        a, b = per[DAYS[0]], per[DAYS[1]]
        row = {"rat": rat, "delta": b["x"] - a["x"],
               "v": _add(a["se2"], b["se2"]), "n": a["n"] + b["n"],
               "left": a["x"], "right": b["x"]}
        if layer == "minus_fp":
            row.update(left_rest=a["rest"], right_rest=b["rest"],
                       left_cue=a["cue"], right_cue=b["cue"])
        rows.append(row)
    if not rows:
        return None, ("no rat has this entry on both days (%s)"
                      % "; ".join("%s: %s" % (d["rat"], d["why"])
                                  for d in dropped))
    mp = drift.pool_rats(rows)
    t = drift.hk_test(None, None, pooled=mp)
    k = mp["k"]
    warn = list(mp.get("warn") or [])
    if dropped:
        warn.append("pooled over %d of %d rats (%s)" % (
            k, len(rats), "; ".join("%s left out: %s" % (d["rat"], d["why"])
                                    for d in dropped)))
    p = t.get("p")
    why = t.get("why")
    if k < MIN_RATS:
        why = ("%d rat%s ha%s this entry on both days; at least %d are "
               "needed" % (k, "" if k == 1 else "s",
                           "s" if k == 1 else "ve", MIN_RATS))
        p = None
    mean = mp["mean"]
    same = (sum(1 for r in rows if mean is not None and r["delta"] != 0
                and (r["delta"] > 0) == (mean > 0)) if mean else 0)
    side = lambda f: {"mean": sum(r[f] for r in rows) / len(rows),  # noqa: E731
                      "k": len(rows)}
    cell = {"left": side("left"), "right": side("right"),
            "delta": mean, "se": t.get("se") if p is not None else None,
            "t": t.get("stat") if p is not None else None,
            "df": t.get("df"), "hk_factor": t.get("factor"),
            "p": p, "q": None, "testable": p is not None, "why": why,
            "k": k, "n": mp["n"], "tau2": mp["tau2"], "q_het": mp["q_het"],
            "se_dl": mp["se"], "deltas": mp["deltas"], "dropped": dropped,
            "same_direction": same, "majority": same * 2 > k,
            "warn": warn, "z": None}
    return cell, None


def tier_of(c):
    """1 survives, 2 point of interest, 0 neither."""
    if not c or c.get("p") is None:
        return 0
    q = c.get("q")
    if q is not None and q < TIER1_Q:
        return 1
    if ((q is not None and q < TIER2_Q) or c["p"] < TIER2_P) \
            and c.get("majority"):
        return 2
    return 0


def layer_cells(rats, windows, methods, keys, layer):
    cells, absent, panels = {}, {}, {}
    for w in windows:
        cells[w], absent[w], panels[w] = {}, {}, {}
        for m in methods:
            panel, gone = {}, {}
            for key in keys:
                c, why = entry(rats, w, m, key, layer)
                if c is None:
                    gone[key] = why
                else:
                    panel[key] = c
            cells[w][m], absent[w][m] = panel, gone
    every = [(w, m, k) for w in windows for m in methods for k in cells[w][m]]
    qs = drift._bh([cells[w][m][k]["p"] for w, m, k in every])
    for (w, m, k), q in zip(every, qs):
        cells[w][m][k]["q"] = q
    for (w, m, k) in every:
        cells[w][m][k]["tier"] = tier_of(cells[w][m][k])
    for w in windows:
        for m in methods:
            panel = cells[w][m]
            panels[w][m] = {"tests": sum(1 for c in panel.values()
                                         if c["p"] is not None),
                            "cells": len(panel), "absent": len(absent[w][m]),
                            "tier1": sum(1 for c in panel.values()
                                         if c["tier"] == 1),
                            "tier2": sum(1 for c in panel.values()
                                         if c["tier"] == 2)}
    tested = sum(1 for w, m, k in every if cells[w][m][k]["p"] is not None)
    return {"cells": cells, "absent": absent, "panels": panels,
            "bh_tests": tested}


def build(members, rest, band, kind, labels=None, computed_on=None):
    """members: [{"rat", "day", "cue_type", "payload", "ref"}] -- the cue
    circuits, both pairings, both days, every rat; rest: [{"rat", "day",
    "payload", "ref"}] -- one rest circuit per rat-day, same band."""
    if not members:
        raise PoolError("no circuits to compare")
    # One order whatever order they came in, so the same circuits make the
    # same payload -- and a re-run CONFIRMS its version rather than adding
    # one that differs only in how its member list was sorted.
    order_key = lambda m: (str(m["rat"]), str(m["day"]),  # noqa: E731
                           str((m.get("ref") or {}).get("id")))
    members = sorted(members, key=order_key)
    rest = sorted(rest or [], key=order_key)
    labels = labels or {"left": DAYS[0], "right": DAYS[1]}
    first = members[0]["payload"]
    windows = list(first.get("windows") or [])
    methods = list(first.get("methods") or [])
    order = list(first.get("region_order") or [])
    rats = {}
    for mem in members:
        P = mem["payload"]
        if P.get("kind") != kind or (P.get("band") or
                                     (P.get("params") or {}).get("band")) \
                not in (band, None):
            raise PoolError("%s is a %s %s circuit, not %s %s" % (
                (mem.get("ref") or {}).get("id"), P.get("band"),
                P.get("kind"), band, kind))
        if list(P.get("windows") or []) != windows:
            raise PoolError("the circuits do not share their windows")
        slot = rats.setdefault(mem["rat"], {}).setdefault(
            mem["day"], {"cue": [], "rest": None, "refs": []})
        slot["cue"].append(P)
        slot["refs"].append(mem["ref"])
    for r in rest or []:
        slot = rats.setdefault(r["rat"], {}).setdefault(
            r["day"], {"cue": [], "rest": None, "refs": []})
        if slot["rest"] is not None:
            raise PoolError("r%s %s has two rest circuits" % (r["rat"],
                                                              r["day"]))
        slot["rest"] = r["payload"]
        slot["rest_ref"] = r["ref"]
    one_day = [r for r, d in rats.items() if len([x for x in DAYS
                                                  if (d.get(x) or {}).get(
                                                      "cue")]) < 2]
    keys = set()
    for mem in members:
        for w in windows:
            for m in methods:
                keys.update(((mem["payload"].get("cells") or {}).get(w, {})
                             .get(m) or {}).keys())
    rank = {r: i for i, r in enumerate(order)}
    keys = sorted(keys, key=lambda k: tuple(rank.get(x, 99)
                                            for x in k.split("|")))
    raw = layer_cells(rats, windows, methods, keys, "raw")
    fp = layer_cells(rats, windows, methods, keys, "minus_fp")
    grey_sets = [set(m["payload"].get("grey") or []) for m in members]
    grey = sorted(set.intersection(*grey_sets) if grey_sets else set(),
                  key=lambda r: rank.get(r, 99))
    part = sorted({g for s in grey_sets for g in s} - set(grey),
                  key=lambda r: rank.get(r, 99))
    grey_detail = {g: sorted({str(mem["rat"]) for mem in members
                              if g in (mem["payload"].get("grey") or [])},
                             key=drift._natkey) for g in part}
    types = []
    for mem in members:
        if mem["payload"].get("cue_type") not in types:
            types.append(mem["payload"].get("cue_type"))
    side_members = lambda day: [dict(mem["ref"], rat=mem["rat"],  # noqa
                                     cue_type=mem["payload"].get("cue_type"),
                                     name=mem.get("name"))
                                for mem in members if mem["day"] == day]
    say = ("Within rat, both cue pairings pooled: each rat's %s and %s "
           "averaged over every cue pair of the day, blind to its type; "
           "the rats' changes pooled by DerSimonian–Laird and tested by "
           "Hartung–Knapp t on k − 1 df; Benjamini–Hochberg across every "
           "window, method and region pair of this drift; at least %d rats. "
           "Survives: q < %.2f. Point of interest: q < %.2f or p < %.2f "
           "with most rats moving the same way." % (
               labels["left"], labels["right"], MIN_RATS, TIER1_Q, TIER2_Q,
               TIER2_P))
    out = {
        "schema": SCHEMA, "kind": kind, "band": band,
        "cue_type": "pooled", "cue_label": "both cue pairings, pooled",
        "cue_types": types, "cue_equivalence": [],
        "windows": windows, "methods": methods, "region_order": order,
        "left": {"label": labels["left"], "k": len(side_members(DAYS[0])),
                 "one_recording": False, "cue_types": types,
                 "members": side_members(DAYS[0])},
        "right": {"label": labels["right"],
                  "k": len(side_members(DAYS[1])), "one_recording": False,
                  "cue_types": types, "members": side_members(DAYS[1])},
        "rest": [dict(r["ref"], rat=r["rat"], day=r["day"])
                 for r in rest or []],
        "test": {"name": "hk_test", "label": drift.hk_test.label, "id": "hk"},
        "design": "matched", "bh_scope": "artifact", "contrast": None,
        "pooled_by": "pairings pooled", "rats": len(rats),
        "min_rats": MIN_RATS,
        "tiers": {"survives": {"q": TIER1_Q},
                  "point_of_interest": {"q": TIER2_Q, "p": TIER2_P,
                                        "majority": True}},
        "grey": grey, "grey_detail": grey_detail,
        "cells": raw["cells"], "absent": raw["absent"],
        "panels": raw["panels"], "bh_tests": raw["bh_tests"],
        "layers": {"minus_fp": fp}, "layer_say": LAYER_SAY,
        "params": {"band": band, "kind": kind,
                   "channel_rule": (first.get("params") or {}).get(
                       "channel_rule")},
        "method": ("DerSimonian-Laird over the rats' within-rat changes, both "
                   "cue pairings pooled per rat-day; Hartung-Knapp t; BH "
                   "across all windows, methods and region pairs"),
        "analysis_say": say,
        "notes": [drift.HK_NOTE,
                  "The two cue pairings are pooled per rat and day: every cue "
                  "pair counts once, whatever pairing it belongs to.",
                  "Minus FP subtracts, per rat and day, the entry's mean over "
                  "that day's FP1 + FP2 rest epochs (matched in number to the "
                  "cue pairs) before the change is taken."],
        "warn": (["r%s is on one day only and sits out" % ", r".join(
            str(r) for r in one_day)] if one_day else []),
        "computed_on": dict(computed_on or {"kind": "local"}),
    }
    return out


def subject_of(members, rest, band, kind, labels=None):
    """The drift's subject: its members pinned, and what makes it this
    analysis (not a default drift of the same circuits)."""
    labels = labels or {"left": DAYS[0], "right": DAYS[1]}
    side = lambda day: sorted(  # noqa: E731
        (dict(m["ref"], gid=m.get("gid"), name=m.get("name"), rat=m["rat"])
         for m in members if m["day"] == day),
        key=lambda r: (str(r.get("id")), str(r.get("version_id"))))
    return {
        "left": side(DAYS[0]), "right": side(DAYS[1]),
        "left_label": labels["left"], "right_label": labels["right"],
        "cue_type": "pooled", "cue_label": "both cue pairings",
        "window_kind": kind, "band": band,
        "band_label": {"theta": "theta 4–12 Hz", "beta": "beta 13–30 Hz",
                       "gamma_low": "low gamma 30–55 Hz"}.get(band, band),
        "cue_equivalence": [],
        "analysis": {"design": "matched", "test": "hk",
                     "bh_scope": "artifact", "contrast": None,
                     "pool": "pairings", "min_rats": MIN_RATS,
                     "layers": list(LAYERS),
                     "rest": sorted("%s@%s" % (r["ref"]["id"],
                                               r["ref"]["version_id"])
                                    for r in rest or [])},
    }


def _rank(c):
    return (0 if c["tier"] == 1 else 1 if c["tier"] == 2 else 2,
            c["q"] if c.get("q") is not None else 9, c["p"],
            -abs(c.get("delta") or 0))


def top(payloads, layer="raw", n=10):
    """The region pairs that stand out in one layer, across every drift
    handed in (all bands, both window types): ONE entry per region pair,
    listing every band x window x method where it is a tier 1 or 2 entry.
    Ranked by the pair's best entry -- tier, then q, then p, then |change|.
    If fewer than n pairs have a tiered entry, the rest are the next pairs
    by their best p, marked `below_line`: shown, not claimed."""
    by_pair = {}
    for P in payloads:
        L = P if layer == "raw" else (P.get("layers") or {}).get(layer)
        for w, byw in ((L or {}).get("cells") or {}).items():
            for m, panel in byw.items():
                for k, c in panel.items():
                    if c.get("p") is None:
                        continue
                    by_pair.setdefault(k, []).append(dict(
                        c, window=w, method=m, band=P.get("band"),
                        kind=P.get("kind")))
    rows = []
    for k, cs in by_pair.items():
        cs.sort(key=_rank)
        rows.append({"pair": k, "best": cs[0],
                     "where": [c for c in cs if c["tier"] in (1, 2)],
                     "below_line": cs[0]["tier"] == 0,
                     "tested": len(cs)})
    rows.sort(key=lambda r: _rank(r["best"]))
    return rows[:n]


# ==========================================================================
# Pinning and filing -- one path for the tool and the Jarvis route
# ==========================================================================
def file_pooled(host, cue_refs, rest_refs, band, kind, nickname=None,
                by=None, labels=None):
    """Pin every circuit at its exact version, build, file as a drift, and
    cite every input. `cue_refs`: [{id, version_id, rat, day}] -- both
    pairings, both days; `rest_refs`: the same for the rest circuits.
    Returns what driftrun.file_drift returns."""
    from . import driftrun
    labels = labels or {"left": DAYS[0], "right": DAYS[1]}

    def pin(r, side):
        p = driftrun._pin(host, {"id": r["id"],
                                 "version_id": r.get("version_id")}, side)
        return {"rat": str(r["rat"]), "day": r["day"],
                "gid": p.get("gid"), "name": p.get("nickname")
                or p.get("name"), "payload": p["payload"],
                "ref": p["ref"]}
    members = [pin(r, "left" if r["day"] == DAYS[0] else "right")
               for r in cue_refs]
    rest = [pin(r, "reference") for r in rest_refs]
    for r in rest:
        r["ref"] = dict(r["ref"], role="reference")
    payload = build(members, rest, band, kind, labels)
    subject = subject_of(members, rest, band, kind, labels)
    arts = host.artifacts
    inputs = [m["ref"] for m in members] + [r["ref"] for r in rest]
    params = {"band": band, "kind": kind, "design": "matched", "test": "hk",
              "bh_scope": "artifact", "pool": "pairings",
              "min_rats": MIN_RATS, "layers": list(LAYERS),
              "tiers": payload["tiers"]}
    with driftrun._LOCK:
        before = arts.find("drift", subject)
        seen = {v.get("id") for v in ((before or {}).get("versions") or [])}
        rec = arts.put("drift", subject, payload, params=params,
                       inputs=inputs, by=by, nickname=nickname)
        nick = (str(nickname).strip() if nickname else "") or None
        if before and nick and nick != rec.get("nickname"):
            rec = arts.set_nickname(rec["id"], nick, by=by)
        cur = max(rec.get("versions") or [{}],
                  key=lambda v: (v.get("v") or 0, v.get("at") or "",
                                 v.get("id") or ""))
        for ref in inputs:
            arts.cite(ref["id"], ref["version_id"], rec["id"], cur["v"])
    new = cur.get("id") not in seen
    try:
        host.activity([{"action": "arc.drift.file",
                        "detail": {"artifact": rec["id"],
                                   "version": cur.get("v"),
                                   "new_version": new, "pooled": True,
                                   "band": band, "kind": kind,
                                   "circuits": len(members),
                                   "rest": len(rest)}}])
    except Exception:                                    # noqa: BLE001
        pass
    return {"ok": True, "artifact_id": rec["id"], "version": cur.get("v"),
            "version_id": cur.get("id"), "digest": cur.get("digest"),
            "name": rec.get("name"), "nickname": rec.get("nickname"),
            "new_version": new, "payload": payload}
