# -*- coding: utf-8 -*-
"""rcdeep.py -- the deep dive (steps 7-10): the events that change identity.

Asked for 2026-10-06 (the meeting with Shahriar): pool the controls as all
DS, pool the IED mice at k = 2, pool those two pools, draw a border with
grace -- and then look hard at the events that do not sit still: the ones
whose identity SWITCHED between their own pool (v0) and the pool of pools,
and the ones a border leaves AMBIGUOUS. Browse them, bank them, export them,
and see where they come from: by mouse, mouse type, group, subgroup and
condition.

Pure functions over a pool's (or a pool of pools') fit; the app supplies the
fit and each recording's facts (the session workbook's group, subgroup and
condition) and does the banking.

THREE CALLS PER EVENT, named for the level they were made at:

  single   its own recording's Root Canal call
  pool     its pool's call (in a pool of pools, v0: its own pool's)
  double   the pool of pools' call (a pool of pools only)

"Switched" is the level's own switch: single against pool in a pool, v0
against the pool of pools in a pool of pools -- what the switch tables
count.
"""
from __future__ import annotations

import csv
import io

GROUPINGS = (("mouse_key", "mouse"), ("mouse_type", "mouse type"),
             ("group", "group"), ("subgroup", "subgroup"),
             ("condition", "condition"))
NOT_RECORDED = "not recorded"


def calls_of(e, level):
    """(single, pool, double) calls of one event at a level."""
    if level == "double":
        return ((e.get("v0") or {}).get("cls_single"), e.get("cls_single"),
                e.get("cls_pool"))
    return e.get("cls_single"), e.get("cls_pool"), None


def switch_of(e, level):
    """'ds_to_ied', 'ied_to_ds' or None: the level's own switch."""
    _s, p, d = calls_of(e, level)
    a, b = (p, d) if level == "double" else (_s, p)
    if a and b and a != b:
        return "%s_to_%s" % (a, b)
    return None


def why_of(e, level):
    """Why an event is in the deep dive, in words; empty if it is not."""
    out = []
    sw = switch_of(e, level)
    if sw:
        a, b = sw.split("_to_")
        out.append("switched %s → %s" % (a.upper(), b.upper()))
    if e.get("border") == "amb":
        out.append("ambiguous under the border")
    return out


def rows(res, level, facts):
    """Every event of the fit that switched or is ambiguous, with where it
    came from. `facts`: gid -> {group, subgroup, condition, ...}. Each row
    keeps `j`, its place in the fit, so a browser can pick its dot."""
    members = res.get("members") or []
    out = []
    for j, e in enumerate(res.get("events") or []):
        why = why_of(e, level)
        if not why:
            continue
        m = members[e["m"]] if e.get("m") is not None and e["m"] < len(
            members) else {}
        f = facts.get(m.get("gid")) or {}
        s, p, d = calls_of(e, level)
        out.append({
            "j": j, "key": m.get("key"), "entry_id": m.get("entry_id"),
            "gid": m.get("gid"), "session_label": m.get("session_label"),
            "project": m.get("project"), "mouse_key": e.get("mouse_key"),
            "mouse_type": e.get("mouse_type"),
            "group": f.get("group"), "subgroup": f.get("subgroup"),
            "condition": f.get("condition"),
            "i": e.get("i"), "t": e.get("t"),
            "amp_uV": e.get("amp_uV"), "hw_ms": e.get("hw_ms"),
            "hf_db": e.get("hf_db"),
            "single": s, "pool": p, "double": d,
            "border": e.get("border"),
            "switch": switch_of(e, level), "why": why,
            "pool_id": (e.get("v0") or {}).get("pool"),
        })
    return out


def summary(res, level, facts):
    """Where the switches and the ambiguous events come from: for each
    mouse, mouse type, group, subgroup and condition, of all its events
    with a call, how many switched each way and how many are ambiguous."""
    members = res.get("members") or []
    has_border = bool(res.get("border_used"))
    tables = {}
    for key, words in GROUPINGS:
        acc = {}
        for e in res.get("events") or []:
            s, p, d = calls_of(e, level)
            if not (d if level == "double" else p):
                continue
            m = members[e["m"]] if e.get("m") is not None and e["m"] < len(
                members) else {}
            if key in ("mouse_key", "mouse_type"):
                val = e.get(key)
            else:
                val = (facts.get(m.get("gid")) or {}).get(key)
            val = str(val) if val not in (None, "") else NOT_RECORDED
            a = acc.setdefault(val, {"value": val, "n": 0, "switched": 0,
                                     "ds_to_ied": 0, "ied_to_ds": 0,
                                     "ambiguous": 0, "recordings": set()})
            a["n"] += 1
            a["recordings"].add(m.get("gid"))
            sw = switch_of(e, level)
            if sw:
                a["switched"] += 1
                a[sw] += 1
            if e.get("border") == "amb":
                a["ambiguous"] += 1
        rows_ = []
        for a in acc.values():
            a["recordings"] = len({g for g in a["recordings"] if g})
            a["switch_rate"] = a["switched"] / a["n"] if a["n"] else None
            a["ambiguous_rate"] = (a["ambiguous"] / a["n"]
                                   if a["n"] and has_border else None)
            rows_.append(a)
        rows_.sort(key=lambda r: (r["value"] == NOT_RECORDED, r["value"]))
        tables[key] = {"label": words, "rows": rows_}
    return tables


COLUMNS = (("session", "session_label"), ("project", "project"),
           ("mouse", "mouse_key"), ("mouse type", "mouse_type"),
           ("group", "group"), ("subgroup", "subgroup"),
           ("condition", "condition"), ("event", "i"), ("time s", "t"),
           ("amplitude uV", "amp_uV"), ("half-width ms", "hw_ms"),
           ("HF dB", "hf_db"), ("single call", "single"),
           ("pool call", "pool"), ("pool of pools call", "double"),
           ("border class", "border"), ("why", "why"), ("gid", "gid"))


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return "%.6g" % v
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    return str(v)


def csv_text(rows_, level):
    """The deep dive as a CSV a spreadsheet opens: one row per event."""
    cols = [c for c in COLUMNS if level == "double" or c[1] != "double"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([h for h, _k in cols])
    for r in rows_:
        w.writerow([_cell(r.get(k)) for _h, k in cols])
    return buf.getvalue()


def counts(rows_, res, level):
    n = sum(1 for e in res.get("events") or []
            if (calls_of(e, level)[2] if level == "double"
                else calls_of(e, level)[1]))
    return {"n": n, "rows": len(rows_),
            "switched": sum(1 for r in rows_ if r["switch"]),
            "ds_to_ied": sum(1 for r in rows_ if r["switch"] == "ds_to_ied"),
            "ied_to_ds": sum(1 for r in rows_ if r["switch"] == "ied_to_ds"),
            "ambiguous": sum(1 for r in rows_ if r["border"] == "amb"),
            "recordings": len({r["gid"] for r in rows_ if r["gid"]})}
