# -*- coding: utf-8 -*-
"""precon_average.py -- the Precon1 -> Precon4 change, averaged.

    python tools\\precon_average.py            # docs/dewey-precon-average.*

WHAT IT ASKS
------------
The drifts test every cell (band x window x method x cue pair) on its own,
and after correction almost none survives. This asks the coarser question:
averaged over everything, did a region pair's coupling change?

  For each RAT and region pair, the mean of that rat's Precon4 - Precon1
  deltas over a set of cells; then those per-rat means tested across rats
  (one-sample t, k - 1 df, two-sided); Benjamini-Hochberg across region
  pairs within each set. The rat is the unit, as in the drifts.

The sets, each a "view":
  all        every cue-session cell: state and transition windows, both cue
             pairs, three bands, three methods
  band       ... one band at a time          method ... one method at a time
  kind       ... state or transition         window ... one window at a time
  role       ... one cue pair at a time
  rest       every rest (FP1 + FP2) cell, and by band
  cue-rest   per rat, the cue-session mean minus the rest mean: a change
             that is in the cue sessions and not the no-cue recordings of
             the same days (and by band)

Only the RAW drifts are read (the change in each window). The cue - baseline
and food - no-food drifts are made from the same numbers; averaging them in
would count every delta twice.

WHAT IT DOES NOT SAY
--------------------
- The methods are on different scales (coherence moves less than a
  correlation), so an average across methods leans on the two correlation
  methods; the method view shows each alone.
- Transition windows overlap state windows in time; `all` counts both, as
  asked; the kind view shows each alone.
- This test was not in the plan. It is one test per region pair per view,
  corrected across pairs, not across views.

Every number names the drift artifacts (id and version, digest-checked)
it was averaged from; the JSON carries every rat's value.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

import precon_drift_report as PR                        # noqa: E402

DOCS = os.path.join(APP, "docs")
RUNLOG = os.path.join(DOCS, "dewey-precon-drift.runlog.json")
OUT = os.path.join(DOCS, "dewey-precon-average")
SCHEMA = "arc.precon-average/1"
Q = 0.05
MIN_K = 3                     # rats needed before a pair is tested at all
CUE_KINDS = ("state", "transition")
BANDS = ("theta", "beta", "gamma_low")
METHODS = ("coherence", "raw_cc", "amp_cc")
WINDOWS = ("pre", "cue1", "cue2", "post", "onset", "switch", "offset")
ROLES = ("food", "no_food")
SAY = {
    "all": "all cue-session cells", "theta": "theta", "beta": "beta",
    "gamma_low": "low gamma", "coherence": "coherence", "raw_cc": "raw cc",
    "amp_cc": "envelope cc", "state": "state windows",
    "transition": "transition windows", "pre": "baseline", "cue1": "cue 1",
    "cue2": "cue 2", "post": "after cue 2", "onset": "cue 1 onset",
    "switch": "cue 1 → cue 2", "offset": "cue 2 offset",
    "food": "food pair", "no_food": "no-food pair", "rest": "rest (FP1+FP2)",
}


def t_sf2(t, df):
    """Two-sided p for Student t, without scipy if it is not there."""
    try:
        from scipy import stats
        return float(2 * stats.t.sf(abs(t), df))
    except ImportError:                                  # pragma: no cover
        x = df / (df + t * t)
        # regularised incomplete beta by continued fraction (NR 6.4)
        a, b = df / 2.0, 0.5

        def cf(x):
            tiny, qab, qap, qam = 1e-300, a + b, a + 1, a - 1
            c, d = 1.0, 1 - qab * x / qap
            d = 1 / (d if abs(d) > tiny else tiny)
            h = d
            for m in range(1, 300):
                m2 = 2 * m
                aa = m * (b - m) * x / ((qam + m2) * (a + m2))
                d = 1 + aa * d
                d = 1 / (d if abs(d) > tiny else tiny)
                c = 1 + aa / c
                c = c if abs(c) > tiny else tiny
                h *= d * c
                aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
                d = 1 + aa * d
                d = 1 / (d if abs(d) > tiny else tiny)
                c = 1 + aa / c
                c = c if abs(c) > tiny else tiny
                h *= d * c
            return h
        lb = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
              + a * math.log(x) + b * math.log(1 - x))
        return float(math.exp(lb) * cf(x) / a)


def bh(ps):
    """Benjamini-Hochberg q for a list of p (None stays None)."""
    idx = [i for i, p in enumerate(ps) if p is not None]
    idx.sort(key=lambda i: ps[i])
    q = [None] * len(ps)
    m, prev = len(idx), 1.0
    for rank in range(m, 0, -1):
        i = idx[rank - 1]
        prev = min(prev, ps[i] * m / rank)
        q[i] = prev
    return q


def test(per_rat):
    """One-sample t across rats of their means."""
    vals = [v for v in per_rat.values() if v is not None]
    k = len(vals)
    out = {"k": k, "mean": None, "sd": None, "se": None, "t": None,
           "df": None, "p": None, "pos": sum(1 for v in vals if v > 0)}
    if k == 0:
        return out
    mean = sum(vals) / k
    out["mean"] = mean
    if k < MIN_K:
        return out
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (k - 1))
    se = sd / math.sqrt(k)
    out.update(sd=sd, se=se, df=k - 1)
    if se > 0:
        out["t"] = mean / se
        out["p"] = t_sf2(out["t"], k - 1)
    return out


def collect(runlog):
    """rat -> pair -> [ (band, kind, window, method, role, delta) ]."""
    rows = defaultdict(lambda: defaultdict(list))
    used, order = [], None
    rdir = os.path.dirname(os.path.abspath(runlog["_path"]))
    for key, d in sorted(runlog["drifts"].items()):
        band, kind, role, contrast = key.split("|")
        if contrast != "raw" or not d.get("artifact_id"):
            continue
        P = PR.payload_of(d, rdir)
        order = order or P.get("region_order")
        used.append({"key": key, "nickname": d.get("nickname"),
                     "artifact_id": d["artifact_id"],
                     "version": d.get("version"),
                     "version_id": d.get("version_id"),
                     "digest": d.get("digest")})
        role = None if role == "-" else role
        for w, byw in (P.get("cells") or {}).items():
            for m, cells in byw.items():
                for pk, c in cells.items():
                    for x in c.get("deltas") or []:
                        if x.get("delta") is None:
                            continue
                        rows[x["rat"]][pk].append(
                            (band, kind, w, m, role, float(x["delta"])))
    return rows, used, order


def mean_of(xs):
    return sum(xs) / len(xs) if xs else None


def views():
    """(view, level, label, predicate over a cell, is_rest)."""
    cue = lambda c: c[1] in CUE_KINDS                     # noqa: E731
    out = [("all", "all", SAY["all"], cue, False)]
    out += [("band", b, SAY[b], (lambda b: lambda c: cue(c) and c[0] == b)(b),
             False) for b in BANDS]
    out += [("method", m, SAY[m],
             (lambda m: lambda c: cue(c) and c[3] == m)(m), False)
            for m in METHODS]
    out += [("kind", k, SAY[k], (lambda k: lambda c: c[1] == k)(k), False)
            for k in CUE_KINDS]
    out += [("window", w, SAY[w],
             (lambda w: lambda c: cue(c) and c[2] == w)(w), False)
            for w in WINDOWS]
    out += [("role", r, SAY[r], (lambda r: lambda c: cue(c) and c[4] == r)(r),
             False) for r in ROLES]
    out += [("rest", "all", "rest, every cell", lambda c: c[1] == "rest",
             True)]
    out += [("rest", b, "rest, " + SAY[b],
             (lambda b: lambda c: c[1] == "rest" and c[0] == b)(b), True)
            for b in BANDS]
    return out


def analyse(rows):
    pairs = sorted({pk for r in rows.values() for pk in r})
    rats = sorted(rows, key=lambda r: int(str(r).lstrip("rm") or 0))
    results = []
    for view, level, label, pred, _rest in views():
        entries = []
        for pk in pairs:
            per = {}
            n_cells = {}
            for rat in rats:
                vals = [c[5] for c in rows[rat].get(pk, []) if pred(c)]
                if vals:
                    per[rat] = mean_of(vals)
                    n_cells[rat] = len(vals)
            st = test(per)
            entries.append(dict(st, pair=pk, per_rat=per, n_cells=n_cells))
        qs = bh([e["p"] for e in entries])
        for e, q in zip(entries, qs):
            e["q"] = q
        results.append({"view": view, "level": level, "label": label,
                        "entries": entries})
    # cue - rest, per rat: overall and per band
    for level, label, band in [("all", "cue sessions − rest", None)] + [
            (b, "cue − rest, " + SAY[b], b) for b in BANDS]:
        entries = []
        for pk in pairs:
            per = {}
            for rat in rats:
                cs = [c[5] for c in rows[rat].get(pk, [])
                      if c[1] in CUE_KINDS and (band is None or c[0] == band)]
                rs = [c[5] for c in rows[rat].get(pk, [])
                      if c[1] == "rest" and (band is None or c[0] == band)]
                if cs and rs:
                    per[rat] = mean_of(cs) - mean_of(rs)
            st = test(per)
            entries.append(dict(st, pair=pk, per_rat=per, n_cells={}))
        qs = bh([e["p"] for e in entries])
        for e, q in zip(entries, qs):
            e["q"] = q
        results.append({"view": "cue-rest", "level": level, "label": label,
                        "entries": entries})
    return results, pairs, rats


def write(results, pairs, rats, used, order, runlog, out=OUT):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    from datetime import datetime, timezone
    doc = {"schema": SCHEMA,
           "made": datetime.now(timezone.utc).astimezone().isoformat(
               timespec="seconds"),
           "question": "Averaged over every cell, did each region pair's "
                       "coupling change from Precon1 to Precon4?",
           "method": "per rat, the mean of its Precon4 − Precon1 deltas "
                     "over the cells of a view; one-sample t across rats "
                     "(k − 1 df, two-sided); Benjamini–Hochberg across "
                     "region pairs within each view; tested only with "
                     "k ≥ %d rats" % MIN_K,
           "rats": rats, "region_order": order, "pairs": pairs,
           "from": used, "runlog": os.path.relpath(runlog["_path"], APP),
           "views": results}
    with open(out + ".json", "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
    with open(out + ".csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["view", "level", "region pair", "k", "mean delta",
                    "sd", "se", "t", "df", "p", "q", "rats up"]
                   + ["rat %s" % r for r in rats])
        for v in results:
            for e in v["entries"]:
                w.writerow([v["view"], v["level"],
                            e["pair"].replace("|", " – "), e["k"],
                            e["mean"], e["sd"], e["se"], e["t"], e["df"],
                            e["p"], e["q"], e["pos"]]
                           + [e["per_rat"].get(r) for r in rats])
    return doc


TEMPLATE = os.path.join(HERE, "precon_average.template.html")


def write_html(doc, path):
    """The page: every view, every region pair, every rat -- one file, the
    data inside it, no network. Opens by double-clicking it."""
    def r5(v):
        return None if v is None else round(v, 5)
    slim = {k: doc[k] for k in ("made", "question", "method", "rats",
                                "region_order", "pairs", "runlog")}
    slim["from"] = [{k: d.get(k) for k in ("key", "nickname", "artifact_id",
                                           "version")} for d in doc["from"]]
    slim["views"] = [{"view": v["view"], "level": v["level"],
                      "entries": [{"pair": e["pair"], "k": e["k"],
                                   "mean": r5(e["mean"]), "se": r5(e["se"]),
                                   "t": r5(e["t"]), "df": e["df"],
                                   "p": e["p"], "q": e["q"], "pos": e["pos"],
                                   "per_rat": {r: r5(x) for r, x in
                                               e["per_rat"].items()}}
                                  for e in v["entries"]]}
                     for v in doc["views"]]
    data = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")          # never closes the script
    with open(TEMPLATE, "r", encoding="utf-8") as fh:
        page = fh.read()
    assert page.count("/*DATA*/") == 1
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page.replace("/*DATA*/", data))
    return path


def summary(doc):
    lines = []
    for v in doc["views"]:
        tested = [e for e in v["entries"] if e["p"] is not None]
        sig = [e for e in tested if e["q"] is not None and e["q"] < Q]
        lines.append("%-10s %-24s %2d pairs tested, %d at q < .05, %d at "
                     "p < .05" % (v["view"], v["label"], len(tested),
                                  len(sig), sum(1 for e in tested
                                                if e["p"] < .05)))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="runlog", default=RUNLOG)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    runlog, _drifts = PR.load_runlog(args.runlog)
    runlog["_path"] = args.runlog
    rows, used, order = collect(runlog)
    results, pairs, rats = analyse(rows)
    doc = write(results, pairs, rats, used, order, runlog, args.out)
    write_html(doc, args.out + ".html")
    print("%d drifts read (raw contrast), %d rats, %d region pairs"
          % (len(used), len(rats), len(pairs)))
    for ln in summary(doc):
        print("  " + ln)
    print("json -> %s.json\ncsv  -> %s.csv\npage -> %s.html"
          % (args.out, args.out, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
