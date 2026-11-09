# -*- coding: utf-8 -*-
"""rcworkflow.py -- Root Canal's workflows: define a border, apply it, extract.

Asked for 2026-11-05. Three workflows, each its own artifact:

  1. VERIFIED DENTATE SPIKES. A 5%-grace border around DS, drawn from a pool
     whose every event is DS (the controls: "PTEN CTL Baseline Full
     Incisor"); applied to a target pool ("PTEN ALL PTEN Baseline Full
     Incisor"); everything inside it is extracted and banked as one Root
     Canal entry.
  2. VERIFIED P-SPIKES. The same, around P-spikes, drawn from the Bank's
     hand-sorted sets ("IED spikes (hand-sorted)"), measured the way the
     target was; everything inside it is extracted.
  3. AMBIGUOUS. Both borders on the target: what is inside neither, or inside
     both, is shown -- not banked -- for a person to choose from.

THE BORDER is rcborder's envelope (2026-10-19): per axis the range a group's
events span, pulled in at each grace until that share of them is outside.
Inside is solid; outside on any axis is ambiguous. The group is SAID by the
workflow -- every event of the source is that identity -- rather than read
off each event's own call, because "the controls are all dentate spikes" and
"the hand-sorted ones are all P-spikes" are the premises of the question.

INSIDE BOTH (decided 2026-11-05) is ambiguous: an event no box can claim
alone.

Everything here is arithmetic on numbers already measured. Nothing reads a
recording, and nothing is written: app.py does the reading, saving and
banking.
"""
from __future__ import annotations

import numpy as np

from . import rcborder

KINDS = ("ds", "pspike", "ambiguous")
WORDS = {"ds": "Verified dentate spikes", "pspike": "Verified P-spikes",
         "ambiguous": "Ambiguous"}
# Mid-sentence, without lowering the P of P-spike.
WORDS_LC = {"ds": "verified dentate spikes", "pspike": "verified P-spikes",
            "ambiguous": "ambiguous"}
# The stored id of each call ('ied' is the P-spike's, as everywhere).
GROUP = {"ds": "ds", "pspike": "ied"}
# The classes of an event under both borders.
CLASSES = ("ds", "pspike", "both", "neither")
CLASS_WORDS = {"ds": "inside the DS border only",
               "pspike": "inside the P-spike border only",
               "both": "inside both borders",
               "neither": "outside both borders",
               "inside": "inside the border", "outside": "outside the border",
               None: "not measured"}
# The grace sweep's grid: none to 10% in half-percent steps.
SWEEP = tuple(round(0.005 * j, 4) for j in range(0, 21))
AXES = rcborder.AXES


class WorkflowError(ValueError):
    pass


def _f(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------
def pool_events(pay):
    """A saved pool's events, each with the recording it came from.

    `m` is the member, `i` the event's number in that member's read: what
    the click panel and the averages ask the server for."""
    members = (pay or {}).get("members") or []
    out = []
    for j, e in enumerate((pay or {}).get("events") or []):
        m = members[e.get("m")] if isinstance(e.get("m"), int) and 0 <= e[
            "m"] < len(members) else {}
        out.append({
            "j": j, "m": e.get("m"), "i": e.get("i"),
            "gid": m.get("gid"), "key": m.get("key"),
            "entry_id": m.get("entry_id"),
            "session_label": m.get("session_label"),
            "mouse_key": e.get("mouse_key") or m.get("mouse_key"),
            "mouse_type": e.get("mouse_type") or m.get("mouse_type"),
            "t": _f(e.get("t")),
            "amp_uV": _f(e.get("amp_uV")), "hf_db": _f(e.get("hf_db")),
            "hw_ms": _f(e.get("hw_ms")),
            "cls_pool": e.get("cls_pool"), "cls_single": e.get("cls_single"),
            "partial": bool(e.get("partial")),
        })
    return out


def with_identity(events, group):
    """Every event given the workflow's identity, on a copy."""
    return [dict(e, wf_id=group) for e in events]


# --------------------------------------------------------------------------
# Define
# --------------------------------------------------------------------------
def define(events, group, grace):
    """The envelope around `group`, with a band at the workflow's grace as
    well as none, 1% and 5%."""
    if group not in ("ds", "ied"):
        raise WorkflowError("A workflow draws its border around DS or "
                            "P-spikes; not %r." % (group,))
    g = float(grace)
    b = rcborder.envelope(with_identity(events, group),
                          custom=None if g in rcborder.GRACES else g,
                          identity="wf_id")
    if b.get("group") != group:
        raise WorkflowError("The border came out around the wrong group.")
    rcborder.level_of(b, g)
    return b


def box_of(border, grace):
    """{axis: (lo, hi)} of an envelope at a grace."""
    ed = rcborder.level_of(border, grace)["edges"]
    return {k: (ed[k]["lo"], ed[k]["hi"]) for k, _l, _u in AXES}


# --------------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------------
def inside_of(events, border, grace):
    """True inside the box, False outside it, None with no numbers."""
    cls, _info = rcborder.apply(events, border, grace, identity="wf_none")
    grp = border.get("group")
    return [None if c is None else (c == grp) for c in cls]


def classes_one(events, border, grace):
    return ["inside" if v else (None if v is None else "outside")
            for v in inside_of(events, border, grace)]


def classes_two(events, b_ds, g_ds, b_p, g_p):
    """Each event under both borders: DS only, P-spike only, both, neither."""
    a = inside_of(events, b_ds, g_ds)
    b = inside_of(events, b_p, g_p)
    out = []
    for x, y in zip(a, b):
        if x is None and y is None:
            out.append(None)
        elif x and y:
            out.append("both")
        elif x:
            out.append("ds")
        elif y:
            out.append("pspike")
        else:
            out.append("neither")
    return out


def distances(events, border, grace):
    """How far each event is from the box on each axis, in box widths:
    below 0 inside (how deep), above 0 outside (how far out)."""
    box = box_of(border, grace)
    out = []
    for e in events:
        row = {}
        for k, _l, _u in AXES:
            lo, hi = box[k]
            v = e.get(k)
            if v is None or lo is None or hi is None:
                row[k] = None
                continue
            w = max(1e-9, hi - lo)
            row[k] = round(max(lo - v, v - hi) / w, 4)
        out.append(row)
    return out


# --------------------------------------------------------------------------
# Grace, before it is chosen
# --------------------------------------------------------------------------
def grace_sweep(src_events, tgt_events, group, graces=SWEEP):
    """At each grace: the share of the source's own events left outside,
    and how many of the target's land inside -- so the grace can be chosen
    looking at what it does."""
    X = rcborder._matrix(src_events)
    G = X[np.isfinite(X).all(axis=1)]
    if G.shape[0] < rcborder.MIN_EACH:
        return []
    T = rcborder._matrix(tgt_events)
    tfin = np.isfinite(T).all(axis=1)
    out = []
    for g in graces:
        q = rcborder._trim_for(G, float(g))
        lo, hi = rcborder._box_at(G, q)
        src_out = 1.0 - float(np.mean(rcborder._inside(G, lo, hi)))
        n_in = int(np.sum(rcborder._inside(T, lo, hi)))
        out.append({"grace": float(g), "source_outside": round(src_out, 5),
                    "target_inside": n_in,
                    "target_measured": int(tfin.sum()),
                    "box": {k: [_f(lo[a]), _f(hi[a])]
                            for a, (k, _l, _u) in enumerate(AXES)}})
    return out


# --------------------------------------------------------------------------
# What the run says
# --------------------------------------------------------------------------
def counts(cls):
    c = {}
    for v in cls:
        c[str(v)] = c.get(str(v), 0) + 1
    return c


def breakdown(events, cls, by):
    """{group: {class: n}} for `by` in mouse_key / mouse_type / gid."""
    rows = {}
    for e, c in zip(events, cls):
        k = e.get(by) or "?"
        r = rows.setdefault(k, {"n": 0, "label": (
            e.get("session_label") if by == "gid" else k),
            "mouse_type": e.get("mouse_type")})
        r["n"] += 1
        r[str(c)] = r.get(str(c), 0) + 1
    return [dict(v, key=k) for k, v in sorted(rows.items())]


def columns(events, cls, dist_a=None, dist_b=None):
    """The events of a run, column by column: compact enough to keep every
    one of them with the version that classified them."""
    gids = sorted({e.get("gid") for e in events if e.get("gid")})
    gi = {g: n for n, g in enumerate(gids)}
    col = {"gids": gids,
           "g": [gi.get(e.get("gid"), -1) for e in events],
           "m": [e.get("m") for e in events],
           "i": [e.get("i") for e in events],
           "t": [None if e.get("t") is None else round(e["t"], 6)
                 for e in events],
           "amp": [None if e.get("amp_uV") is None else round(e["amp_uV"], 2)
                   for e in events],
           "hf": [None if e.get("hf_db") is None else round(e["hf_db"], 3)
                  for e in events],
           "hw": [None if e.get("hw_ms") is None else round(e["hw_ms"], 3)
                  for e in events],
           "mouse": [e.get("mouse_key") for e in events],
           "cls": list(cls)}
    for name, d in (("d_a", dist_a), ("d_b", dist_b)):
        if d is not None:
            col[name] = [[r.get(k) for k, _l, _u in AXES] for r in d]
    return col


def event_key(gid, t):
    return "%s|%.6f" % (gid, t)


def diff(prev, cur):
    """What changed class between two runs' columns, by recording and time:
    counts per change, and the first changes themselves."""
    def index(col):
        out = {}
        gids = col.get("gids") or []
        for n, (g, t, c) in enumerate(zip(col.get("g") or [],
                                          col.get("t") or [],
                                          col.get("cls") or [])):
            if t is None or not (0 <= g < len(gids)):
                continue
            out[event_key(gids[g], t)] = c
        return out
    a, b = index(prev or {}), index(cur or {})
    moves, examples = {}, []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k, "absent"), b.get(k, "absent")
        if x == y:
            continue
        w = "%s → %s" % (x, y)
        moves[w] = moves.get(w, 0) + 1
        if len(examples) < 200:
            g, t = k.split("|")
            examples.append({"gid": g, "t": float(t), "was": x, "now": y})
    return {"moves": moves, "n": sum(moves.values()), "examples": examples}


def summary(kind, cls):
    c = counts(cls)
    if kind == "ambiguous":
        keep = c.get("both", 0) + c.get("neither", 0)
    else:
        keep = c.get("inside", 0)
    return {"counts": c, "n": len(cls), "kept": keep}
