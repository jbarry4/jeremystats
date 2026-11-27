"""Audit step 2: does every event the battery used come from the newest
Lock (Confluence) version of its recording? Event by event. Read only."""
import collections
import json
import os
import pickle
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import rcworkflow  # noqa: E402

AR, BANK = A.ARTIFACTS, A.BANK
BAT = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\data"


def key(t):
    return int(round(float(t) * 1000))          # 1 ms


def order(v):
    try:
        return (int(v.get("v") or 0), str(v.get("at") or ""))
    except (TypeError, ValueError):
        return (0, str(v.get("at") or ""))


def vid(rec, v):
    return v.get("id") or BANK.version_key(v)


def version_rows(rec):
    rows = []
    for v in sorted(rec.get("versions") or [], key=order):
        try:
            st, n_all = A._dspca_stamps(rec, vid(rec, v))
            good = {key(e["t"]) for e in st}
        except Exception as e:                           # noqa: BLE001
            good, n_all = None, None
        al = v.get("aligned") or {}
        rows.append({"v": v.get("v"), "id": vid(rec, v), "at": v.get("at"),
                     "by": v.get("by") if not isinstance(v.get("by"), dict) else v["by"].get("user"),
                     "tool": al.get("tool") if isinstance(al, dict) and al else None,
                     "note": str(v.get("note") or "")[:90], "good": good, "n_all": n_all})
    return rows


def describe_entry(rec):
    rows = version_rows(rec)
    live = {key(e["t"]) for e in A._dspca_stamps(rec, None)[0]}
    lock = [r for r in rows if r["tool"]]
    return rows, live, lock


OUT = {"pools": {}, "pspike": [], "battery": {}, "other_entries": {}}
pool_times = {}
for pid, pv in (("07cdcb084c86", 2), ("3561fc988afd", 2)):
    pay = AR.payload(pid, pv) or {}
    evs = rcworkflow.pool_events(pay)
    by = collections.defaultdict(set)
    for e in evs:
        by[(e["gid"], e["entry_id"])].add(key(e["t"]))
    mem_out = []
    for m in pay.get("members") or []:
        gid, eid = m.get("gid"), m.get("entry_id")
        T = by.get((gid, eid), set())
        pool_times.setdefault(gid, set()).update(T)
        rec = BANK.get(eid) or {}
        rows, live, lock = describe_entry(rec)
        match = [r for r in rows if r["good"] is not None and r["good"] == T]
        newest = rows[-1] if rows else None
        mem_out.append({
            "label": m.get("session_label"), "gid": gid, "entry": eid, "type": rec.get("type"),
            "archived": A.eventbank.entry_archived(rec) if hasattr(A, "eventbank") else None,
            "n_pool": len(T), "n_live": len(live), "pool_eq_live": T == live,
            "pool_minus_live": len(T - live), "live_minus_pool": len(live - T),
            "matched_versions": [(r["v"], r["id"], r["tool"], r["at"]) for r in match],
            "newest": newest and (newest["v"], newest["id"], newest["tool"], newest["at"], newest["by"], newest["note"]),
            "newest_lock": lock and (lock[-1]["v"], lock[-1]["id"], lock[-1]["tool"], lock[-1]["at"]),
            "versions": [(r["v"], r["id"], r["tool"], r["at"], r["by"], None if r["good"] is None else len(r["good"]),
                          r["note"]) for r in rows],
            "read_key": m.get("key"),
        })
    OUT["pools"][pid] = {"version": pv, "members": mem_out}

# Every DS-like entry each pooled recording has, to catch a newer Confluence entry the pool did not use.
gids = set(pool_times)
for rec in BANK.all():
    if rec.get("gid") in gids and (rec.get("type") or "") in ("ds", "pooled"):
        rows = version_rows(rec)
        OUT["other_entries"].setdefault(rec["gid"], []).append({
            "entry": rec["id"], "type": rec.get("type"), "label": rec.get("session_label"),
            "archived": bool(rec.get("archived")) or bool((rec.get("archive") or {})),
            "n_versions": len(rows), "newest": rows and (rows[-1]["v"], rows[-1]["id"], rows[-1]["tool"], rows[-1]["at"]),
            "aligned_tool": (rec.get("aligned") or {}).get("tool") if isinstance(rec.get("aligned"), dict) else None,
            "n_good_live": len(A._dspca_stamps(rec, None)[0])})

# The P-spike border's hand-sorted sets: pinned version against newest.
pay = AR.payload("4e5ce690d4b1", 2) or {}
for s in ((pay.get("definition") or {}).get("source") or {}).get("entries") or []:
    rec = BANK.get(s["entry_id"]) or {}
    rows = version_rows(rec)
    pin = [r for r in rows if r["id"] == s.get("version")]
    later = []
    if pin:
        i = rows.index(pin[0])
        later = [(r["v"], r["id"], r["tool"], r["at"], r["by"], r["note"],
                  None if (r["good"] is None or pin[0]["good"] is None) else (len(r["good"] - pin[0]["good"]), len(pin[0]["good"] - r["good"])))
                 for r in rows[i + 1:]]
    OUT["pspike"].append({"label": s.get("session_label"), "entry": s["entry_id"], "type": rec.get("type"),
                          "pinned": s.get("version"), "pinned_found": bool(pin),
                          "pinned_row": pin and (pin[0]["v"], pin[0]["tool"], pin[0]["at"]),
                          "newest": rows and (rows[-1]["v"], rows[-1]["id"], rows[-1]["tool"], rows[-1]["at"], rows[-1]["note"]),
                          "later": later})

# The battery's own events against the target pool and the newest Lock version.
newest_lock_times = {}
for m in OUT["pools"]["3561fc988afd"]["members"]:
    rec = BANK.get(m["entry"]) or {}
    rows = version_rows(rec)
    lk = [r for r in rows if r["tool"]]
    newest_lock_times[m["gid"]] = (lk[-1]["good"] if lk else None, rows[-1]["good"] if rows else None)
for name in ("ds_v6.pkl", "ds_v8.pkl", "ds_b_none.pkl"):
    with open(os.path.join(BAT, name), "rb") as f:
        recs = pickle.load(f)
    rows = []
    for d in recs:
        T = {key(t) for t in d["times_s"]}
        P = pool_times.get(d["gid"], set())
        L, N = newest_lock_times.get(d["gid"], (None, None))
        rows.append({"lab": d["lab"], "gid": d["gid"], "n": len(T),
                     "not_in_pool": len(T - P),
                     "not_in_newest_lock": None if L is None else len(T - L),
                     "not_in_newest_version": None if N is None else len(T - N)})
    OUT["battery"][name] = rows

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "aud2.json"), "w", encoding="utf-8") as fh:
    json.dump(OUT, fh, indent=1, default=str)
print("ok")
