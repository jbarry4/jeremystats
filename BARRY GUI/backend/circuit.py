"""Circuit: one recording's connectivity, every cue pair kept.

The Arc's third step. Coupling measures one cue pair at a time; a circuit
takes every cue pair of ONE cue type in ONE recording, for ONE analysis
kind (state or transition), and files them as a matrix whose cells keep
each pair's value next to the n, mean and SD made from them. It is an
artifact, not a figure: Drift reads it, and Drift is where the statistics
live. Nothing here tests anything.

Pure. No Flask, no files: everything arrives as an argument, so the same
function runs in Jarvis and on the VACC and gives the same payload.

The rules, as the user set them (2026-09-25):

- A probe histology marks `relocated`, `missed` or `unscored` is GREY and
  is not computed at all. Stricter than Coupling, which computes a
  relocated probe under its true name -- so a pair result can arrive with
  numbers for a region this refuses, and those numbers are dropped here.
  A region with no histology record at all is treated as unscored: absent
  is not negative, and "nobody scored it" is not "it is where it was aimed".
- Heavy event loss only warns. A cell with a usable value in even one cue
  pair is kept, with `warn` saying how many of how many.
- A cell is ABSENT -- no key, not null, not zero -- when either region is
  grey, or when no cue pair had both regions usable in that window.
- Mixed inputs are refused with a sentence naming what differs: another
  cue type, another kind, another set of windows, other parameters.

The payload is a hard contract with Drift (`arc_contracts.md` section 3).
"""

import math
import re

from . import probes

SCHEMA = "arc.circuit/1"

STATE_WINDOWS = ("pre", "cue1", "cue2", "post")
TRANSITION_WINDOWS = ("onset", "switch", "offset")
KINDS = ("state", "transition")
_CANONICAL_WINDOWS = {"state": STATE_WINDOWS, "transition": TRANSITION_WINDOWS}

DEFAULT_METHODS = ("coherence", "raw_cc", "amp_cc")

# Histology verdicts (histo.py). Spelled out rather than imported so this
# module can be shipped to the VACC without the workbook reader.
INTENDED, UNCERTAIN = "intended", "uncertain"
RELOCATED, MISSED, UNSCORED = "relocated", "missed", "unscored"
GREY_VERDICTS = frozenset((RELOCATED, MISSED, UNSCORED))

#: The four DEWEY cues, as the rig names them. Keys are the cue's
#: CamelCase id; values are how it is written in a label.
CUES = {"Click": "Click", "Noise": "Noise",
        "HighTone": "High tone", "LowTone": "Low Tone"}

#: Cue types. The two the contract names come first and mean exactly what
#: it says. The rest are every other ordered pairing of the four cues,
#: keyed by the same rule ("<opener id>_<closer id>"), because the 2026 rats
#: are counterbalanced: J3 runs Click -> Low Tone and Noise -> High tone,
#: J4/J5/J11 run High tone -> Noise and Low Tone -> Click, and not one
#: banked DEWEY pair is Click -> Noise or High tone -> Low Tone. A table
#: holding only the contract's two would refuse every recording there is.
CUE_TYPES = {"Click_Noise": ("Click", "Noise"),
             "HighTone_LowTone": ("High tone", "Low Tone")}
for _o in CUES:
    for _c in CUES:
        if _o != _c:
            CUE_TYPES.setdefault(_o + "_" + _c, (CUES[_o], CUES[_c]))
del _o, _c

_ARROWS = ("→", "->", "=>")

# The pair-result params that change the numbers, and how to read each.
# `max_lag_s` in a result, `max_lag_ms` in read_params -- both compared in
# seconds so the two spellings cannot disagree by a factor of a thousand.
_NUMBER_PARAMS = ("analysis_fs", "low", "high", "summary_hz", "max_lag_s",
                  "nperseg", "noverlap", "nfft", "pad_s", "before_s",
                  "after_s", "notch_hz", "methods", "kind")


class CircuitError(ValueError):
    """A build that was refused. The message is a sentence for a person."""


# --------------------------------------------------------------------------
# Cue types
# --------------------------------------------------------------------------
def _norm_cue(s):
    return re.sub(r"\s+", "", str(s or "")).lower()


_CUE_BY_NORM = {_norm_cue(v): v for v in CUES.values()}
_TYPE_BY_PAIR = {(_norm_cue(a), _norm_cue(b)): k
                 for k, (a, b) in CUE_TYPES.items()}


def cue_label(cue_type):
    """"High tone -> Low Tone" (with a real arrow) for a cue type key."""
    got = CUE_TYPES.get(cue_type)
    if not got:
        raise CircuitError("%r is not a cue type. The cue types are %s."
                           % (cue_type, ", ".join(sorted(CUE_TYPES))))
    return got[0] + " → " + got[1]


def cue_type_of(pair):
    """Which cue type one cue pair is, or None when it cannot be told.

    Takes whatever carries a pair: a `pair_connectivity` result, a banked
    event, Coupling's `_coupling_pair`, a bare label string. Reads
    `opener_label`/`closer_label` when both are there, otherwise splits
    `label` on its arrow. Case and spacing are ignored, because the rig
    writes "High tone" and "Low Tone" and a type that depended on the
    capital T would be a type that depended on a typo.
    """
    if pair is None:
        return None
    if isinstance(pair, str):
        pair = {"label": pair}
    o, c = pair.get("opener_label"), pair.get("closer_label")
    if not (o and c):
        label = str(pair.get("label") or "")
        for arrow in _ARROWS:
            if arrow in label:
                parts = label.split(arrow)
                if len(parts) == 2:
                    o, c = parts[0], parts[1]
                break
    if not (o and c):
        return None
    return _TYPE_BY_PAIR.get((_norm_cue(o), _norm_cue(c)))


# --------------------------------------------------------------------------
# Histology
# --------------------------------------------------------------------------
def _probe_by_region(probe):
    return {rec.get("intended"): rec for rec in (probe or [])
            if rec.get("intended")}


def region_records(probe, region_order=None):
    """One record per region in network order: histology, status, why."""
    by = _probe_by_region(probe)
    out = []
    for name in (region_order or probes.DEWEY_NETWORK_ORDER):
        rec = by.get(name)
        if rec is None:
            verdict = UNSCORED
            why = ("There is no histology record for %s, so nobody has "
                   "said where this probe is. It is not computed: absent "
                   "is not the same as where it was aimed." % name)
            out.append({"region": name, "slot": None, "label": name,
                        "histology": verdict, "status": "grey", "why": why})
            continue
        verdict = rec.get("verdict") or UNSCORED
        grey = verdict in GREY_VERDICTS
        why = rec.get("why") or ""
        if grey and verdict == RELOCATED:
            why = (why + " " if why else "") + (
                "A circuit leaves relocated probes out entirely, so this "
                "region is grey even though Coupling computes it.")
        out.append({"region": name, "slot": rec.get("slot"),
                    "label": rec.get("label") or name,
                    "histology": verdict,
                    "status": "grey" if grey else "ok", "why": why})
    return out


def grey_regions(probe, region_order=None):
    """[(region, why)] for every region a circuit will not compute."""
    return [(r["region"], r["why"])
            for r in region_records(probe, region_order)
            if r["status"] == "grey"]


# --------------------------------------------------------------------------
# Reading pair results
# --------------------------------------------------------------------------
def summary_value(got):
    """The number a method result carries, from either of its shapes.

    With curves asked for, a method is {"summary": {value, ...}, "curve":
    ...}; without, the summary IS the method. None when nothing was
    measured. Same rule as `summaryOf` in arc.js and `_coupling_csv`.
    """
    if not isinstance(got, dict):
        return None
    s = got.get("summary") if isinstance(got.get("summary"), dict) else got
    if not isinstance(s, dict):
        return None
    v = s.get("value")
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _result_params(res):
    """The params of one pair result that change its numbers."""
    p = dict(res.get("params") or {})
    notch = res.get("notch") or {}
    out = {}
    for k in _NUMBER_PARAMS:
        if k == "notch_hz":
            v = notch.get("hz") if "hz" in notch else p.get("notch_hz")
        elif k == "methods":
            v = tuple(p.get("methods") or DEFAULT_METHODS)
        elif k == "kind":
            v = res.get("kind") or p.get("kind")
        else:
            v = p.get(k)
        out[k] = v
    return out


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def _say(v):
    if v is None:
        return "not set"
    if isinstance(v, tuple):
        return ", ".join(v)
    return "%g" % v if isinstance(v, (int, float)) else str(v)


def _pair_name(res):
    return "pair %s" % res.get("pair_id")


def _check_inputs(pair_results, kind, cue_type):
    if kind not in KINDS:
        raise CircuitError("The kind has to be one of %s, not %r."
                           % (", ".join(KINDS), kind))
    if cue_type not in CUE_TYPES:
        raise CircuitError("%r is not a cue type. The cue types are %s."
                           % (cue_type, ", ".join(sorted(CUE_TYPES))))
    if not pair_results:
        raise CircuitError("There are no cue pairs to build a circuit from.")

    ids = [r.get("pair_id") for r in pair_results]
    if any(i is None for i in ids):
        raise CircuitError("Every pair result needs its pair_id; %d of %d "
                           "have none." % (sum(i is None for i in ids),
                                           len(ids)))
    dup = sorted({i for i in ids if ids.count(i) > 1}, key=str)
    if dup:
        raise CircuitError("Pair %s is in the input more than once. A "
                           "circuit counts each cue pair once."
                           % ", ".join(str(d) for d in dup))

    # One cue type, and the one asked for.
    wrong = [(r.get("pair_id"), r.get("label"), cue_type_of(r))
             for r in pair_results if cue_type_of(r) != cue_type]
    if wrong:
        raise CircuitError(
            "A %s circuit takes only %s pairs, and %d of the %d given %s "
            "not: %s. Cue types are never pooled; build one circuit per "
            "cue type."
            % (cue_label(cue_type), cue_label(cue_type), len(wrong),
               len(pair_results), "is" if len(wrong) == 1 else "are",
               "; ".join("pair %s is %s" % (
                   pid, ("%s, which is no cue type" % (lab or "unlabelled"))
                   if t is None else cue_label(t))
                   for pid, lab, t in wrong)))

    # One window set.
    first = pair_results[0]
    wins0 = [w.get("window") for w in (first.get("windows") or [])]
    if not wins0 or any(w is None for w in wins0):
        raise CircuitError("%s has no named windows." % _pair_name(first))
    if len(set(wins0)) != len(wins0):
        raise CircuitError("%s names a window twice: %s."
                           % (_pair_name(first), ", ".join(wins0)))
    for r in pair_results[1:]:
        w = [x.get("window") for x in (r.get("windows") or [])]
        if w != wins0:
            raise CircuitError(
                "The pairs were not measured over the same windows: %s has "
                "%s and %s has %s. One circuit is one set of windows."
                % (_pair_name(first), ", ".join(wins0), _pair_name(r),
                   ", ".join(str(x) for x in w) or "none"))

    # The kind. A result that says its kind must say this one; one that
    # does not is judged by its windows only when they are exactly the
    # OTHER kind's names. Otherwise the names are taken as they come.
    other = [k for k in KINDS if k != kind][0]
    for r in pair_results:
        said = r.get("kind") or (r.get("params") or {}).get("kind")
        if said is not None and said != kind:
            raise CircuitError(
                "%s was measured as %s, and this is a %s circuit. A circuit "
                "is one analysis kind." % (_pair_name(r), said, kind))
    if tuple(wins0) == _CANONICAL_WINDOWS[other]:
        raise CircuitError(
            "These pairs carry the %s windows (%s), and this is a %s "
            "circuit." % (other, ", ".join(wins0), kind))

    # One set of parameters.
    p0 = _result_params(first)
    for r in pair_results[1:]:
        p = _result_params(r)
        diff = [k for k in _NUMBER_PARAMS if not _same(p0[k], p[k])]
        if diff:
            raise CircuitError(
                "The pairs were measured with different parameters, so "
                "their numbers are not the same measurement: %s. Re-run "
                "them at one setting." % "; ".join(
                    "%s is %s in %s and %s in %s"
                    % (k, _say(p0[k]), _pair_name(first), _say(p[k]),
                       _pair_name(r)) for k in diff))

    # One set of regions, all of them known.
    known = set(probes.DEWEY_NETWORK_ORDER)
    names0 = set(first.get("region_order") or [])
    for r in pair_results:
        names = set(r.get("region_order") or [])
        stray = sorted(names - known)
        if stray:
            raise CircuitError(
                "%s has regions the DEWEY montage does not: %s."
                % (_pair_name(r), ", ".join(stray)))
        if names != names0:
            raise CircuitError(
                "The pairs were not measured over the same regions: %s has "
                "%d and %s has %d." % (_pair_name(first), len(names0),
                                       _pair_name(r), len(names)))
    return wins0, p0


def _check_params(params, p0):
    """The params the caller says were used must be the ones the results
    carry. A label that disagrees with the numbers under it is refused."""
    if not params:
        return
    want = {k: params[k] for k in ("analysis_fs", "low", "high",
                                   "summary_hz", "pad_s", "notch_hz",
                                   "before_s", "after_s")
            if k in params}
    if params.get("max_lag_ms") is not None:
        want["max_lag_s"] = float(params["max_lag_ms"]) / 1000.0
    elif "max_lag_s" in params:
        want["max_lag_s"] = params["max_lag_s"]
    diff = []
    for k, v in want.items():
        if k in ("before_s", "after_s") and p0.get(k) is None:
            continue          # a state result carries no transition lengths
        if not _same(p0.get(k), v):
            diff.append("%s is %s in the pair results but %s in the "
                        "parameters given" % (k, _say(p0.get(k)), _say(v)))
    if diff:
        raise CircuitError("The parameters given are not the ones the pairs "
                           "were measured with: %s." % "; ".join(diff))


def _opener_t(res, before_s):
    if res.get("opener_t") is not None:
        return float(res["opener_t"])
    by = {w.get("window"): w for w in (res.get("windows") or [])}
    if "cue1" in by and by["cue1"].get("t0") is not None:
        return float(by["cue1"]["t0"])
    if ("onset" in by and by["onset"].get("t0") is not None
            and before_s is not None):
        return round(float(by["onset"]["t0"]) + float(before_s), 6)
    return None


def _cell_key(a, b, order_ix):
    return (a + "|" + b) if order_ix[a] < order_ix[b] else (b + "|" + a)


def _sample_sd(xs):
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _warn(n, of):
    return ("usable in %d of %d pairs" % (n, of)) if n < of / 2.0 else None


# --------------------------------------------------------------------------
# The build
# --------------------------------------------------------------------------
def build(pair_results, probe, kind, cue_type, params, source,
          of=None, computed_on=None):
    """The circuit payload (contract section 3) for one recording.

    `pair_results` are `coupling.pair_connectivity` outputs, one per cue
    pair of `cue_type`, all of `kind`. `probe` is `histo.probe_sanity`
    for the rat. `params` is `coupling.read_params` output (or None to
    take them from the results); `source` is {gid, session_label,
    bank_entry, bank_version}.

    `of` is how many cue pairs of this type the recording has. It defaults
    to the number given; pass it when some pairs could not be run, so the
    warnings count against the recording and not against what survived.
    """
    pair_results = list(pair_results or [])
    wins, p0 = _check_inputs(pair_results, kind, cue_type)
    _check_params(params, p0)
    n_given = len(pair_results)
    if of is None:
        of = n_given
    of = int(of)
    if of < n_given:
        raise CircuitError("%d cue pairs were given, but the recording is "
                           "said to have only %d of this type." % (n_given,
                                                                   of))

    order = list(probes.DEWEY_NETWORK_ORDER)
    order_ix = {n: i for i, n in enumerate(order)}
    regions = region_records(probe, order)
    grey = [r["region"] for r in regions if r["status"] == "grey"]
    grey_set = set(grey)
    methods = list(p0["methods"])

    try:
        results = sorted(pair_results, key=lambda r: r["pair_id"])
    except TypeError:
        results = sorted(pair_results, key=lambda r: str(r["pair_id"]))

    cells, region_usable = {}, {}
    for wname in wins:
        per_method = {m: {} for m in methods}
        usable_count = {n: 0 for n in order}
        for res in results:
            w = next(x for x in res["windows"] if x.get("window") == wname)
            regs = w.get("regions") or {}
            ok = {n for n, r in regs.items()
                  if (r or {}).get("usable") and n not in grey_set}
            for n in ok:
                usable_count[n] += 1
            for row in (w.get("pairs") or []):
                a, b = row.get("a"), row.get("b")
                if a not in ok or b not in ok or a == b:
                    continue
                key = _cell_key(a, b, order_ix)
                for m in methods:
                    v = summary_value(row.get(m))
                    if v is None:
                        continue
                    per_method[m].setdefault(key, []).append(
                        {"pair_id": res["pair_id"], "v": v})
        cells[wname] = {}
        for m in methods:
            out = {}
            for i, a in enumerate(order):
                for b in order[i + 1:]:
                    key = a + "|" + b
                    vals = per_method[m].get(key)
                    if not vals:
                        continue          # ABSENT: not null, not zero
                    xs = [x["v"] for x in vals]
                    n = len(xs)
                    out[key] = {"n": n, "mean": sum(xs) / n,
                                "sd": _sample_sd(xs), "values": vals,
                                "of": of, "warn": _warn(n, of)}
            cells[wname][m] = out
        region_usable[wname] = {}
        for name in order:
            rec = {"usable": 0 if name in grey_set else usable_count[name],
                   "of": of}
            if name in grey_set:
                rec["grey"] = True
            region_usable[wname][name] = rec

    before_s = p0.get("before_s")
    after_s = p0.get("after_s")
    if params:
        before_s = params.get("before_s", before_s)
        after_s = params.get("after_s", after_s)
    pout = dict(params) if params else {
        "analysis_fs": p0["analysis_fs"], "low": p0["low"],
        "high": p0["high"], "summary_hz": p0["summary_hz"],
        "max_lag_ms": (None if p0["max_lag_s"] is None
                       else round(p0["max_lag_s"] * 1000.0, 6)),
        "notch_hz": p0["notch_hz"], "pad_s": p0["pad_s"]}
    pout.update(kind=kind,
                before_s=None if kind == "state" else before_s,
                after_s=None if kind == "state" else after_s)

    src = dict(source or {})
    return {
        "schema": SCHEMA,
        "kind": kind,
        "cue_type": cue_type,
        "cue_label": cue_label(cue_type),
        "windows": list(wins),
        "methods": methods,
        "region_order": order,
        "regions": regions,
        "pairs": [{"pair_id": r["pair_id"], "label": r.get("label"),
                   "opener_t": _opener_t(r, before_s)} for r in results],
        "n_pairs": n_given,
        "cells": cells,
        "region_usable": region_usable,
        "grey": grey,
        "params": pout,
        "source": {"gid": src.get("gid"),
                   "session_label": src.get("session_label"),
                   "bank_entry": src.get("bank_entry"),
                   "bank_version": src.get("bank_version")},
        "computed_on": dict(computed_on or {"kind": "local"}),
    }


def summary(payload):
    """The artifact version's `n_summary`: counts a list can show without
    opening the payload."""
    order = payload.get("region_order") or []
    grey = set(payload.get("grey") or [])
    live = [n for n in order if n not in grey]
    possible = len(live) * (len(live) - 1) // 2
    per = {}
    n_cells = n_warn = n_absent = 0
    for w in payload.get("windows") or []:
        per[w] = {}
        for m in payload.get("methods") or []:
            got = ((payload.get("cells") or {}).get(w) or {}).get(m) or {}
            warn = sum(1 for c in got.values() if c.get("warn"))
            per[w][m] = {"cells": len(got), "warn": warn,
                         "absent": possible - len(got)}
            n_cells += len(got)
            n_warn += warn
            n_absent += possible - len(got)
    return {
        "kind": payload.get("kind"),
        "cue_type": payload.get("cue_type"),
        "n_pairs": payload.get("n_pairs"),
        "of": next((c.get("of") for w in (payload.get("cells") or {}).values()
                    for m in w.values() for c in m.values()),
                   payload.get("n_pairs")),
        "n_regions": len(order),
        "n_grey": len(grey),
        "grey": [n for n in order if n in grey],
        "cells_possible": possible,
        "n_cells": n_cells, "n_warn": n_warn, "n_absent": n_absent,
        "by_window": per,
    }


# --------------------------------------------------------------------------
# Naming (contract section 2)
# --------------------------------------------------------------------------
def subject_key(gid, cue_type, kind):
    return "circuit|%s|%s|%s" % (gid, cue_type, kind)


def name_for(subject):
    """"DEWEY r4 s1 Precon1 SPC · High tone → Low Tone ·
    state" from a circuit subject. Parts that are not known are left out
    rather than written as None."""
    s = subject or {}
    head = []
    if s.get("project"):
        head.append(str(s["project"]))
    if s.get("mouse") is not None:
        head.append("r%s" % s["mouse"])
    if s.get("session") is not None:
        head.append("s%s" % s["session"])
    if s.get("phase"):
        head.append("%s%s" % (s["phase"], "" if s.get("phase_n") is None
                              else s["phase_n"]))
    if s.get("run"):
        head.append(str(s["run"]))
    if not head and s.get("session_label"):
        head.append(str(s["session_label"]))
    parts = [" ".join(head)] if head else []
    ct = s.get("cue_type")
    if ct in CUE_TYPES:
        parts.append(cue_label(ct))
    elif ct:
        parts.append(str(ct))
    if s.get("window_kind"):
        parts.append(str(s["window_kind"]))
    return " · ".join(parts)
