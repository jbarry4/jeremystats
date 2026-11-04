# -*- coding: utf-8 -*-
"""Train and test Prospector on the finished PTEN pools (backend/prospector.py).

    python tools/prospector_train.py            everything: build, read,
                                                compare inputs, then the
                                                leave-one-recording-out run
    python tools/prospector_train.py build      just the training set, counted

Three stages, each logged as it goes:

  1. BUILD    every finished PTEN pool rebuilt as a KCNT1-style raw pool and
              answered by Panning and Checkup (`prospector.consolidate`).
  2. READ     Tooth Fairy's two reads of every event, plus the high-pass
              1 Hz CSD and the spectrogram; cached, so a re-run is free.
  3. COMPARE  which inputs, on 5 folds of whole recordings with one set of
              boosted trees: Tooth Fairy's, + Rain's filters, + each of the
              three spectrograms.
  4. FINAL    the best of those, leave one recording out (the user's call),
              the garbage bar set inside the training recordings; its run
              record goes to GUI_logs/prospector/runs, its model to
              GUI_logs/.cache/prospector.

Nothing here writes a label, a curation set or a bank version.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
os.chdir(APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace",
                           line_buffering=True)
except Exception:                                        # noqa: BLE001
    pass

T0 = time.time()
READERS = 6


def log(msg):
    print("[%6.0f s] %s" % (time.time() - T0, msg), flush=True)


from backend import aibeta, continuity, prospector as P  # noqa: E402

# Jarvis itself, for the recordings' openers: loaded by main(), not on
# import, because each read worker process imports this module and must
# not start Jarvis's background threads (the VACC link, the sweeps).
A = STORE = None


def load_jarvis():
    global A, STORE
    log("loading Jarvis (for the recordings' openers)")
    from backend import app
    A = app
    STORE = P.Store(A.LOGS_DIR)


def report_of_factory():
    pools = {r.get("gid"): r for r in A.BANK.all()
             if (r.get("type") or "") == "pooled"}
    cache = {}

    def report_of(gid):
        if gid in cache:
            return cache[gid]
        rep = None
        try:
            sess, _row = A._braces_session(pools[gid])
            rep = continuity.check(sess.get("path"))
        except Exception:                                # noqa: BLE001
            rep = None
        cache[gid] = rep
        return rep
    return report_of


def build():
    log("BUILD: rebuilding every finished PTEN pool")
    ds = P.consolidate(A.BANK, A.CURATE, report_of=report_of_factory())
    ents = ds["entries"]
    tot = {}
    for e in ents:
        for k, v in e["tally"].items():
            tot[k] = tot.get(k, 0) + v
        for o, yv in zip(e["origin"], [x["y"] for x in e["events"]]):
            key = "%s/%s" % (o, "spike" if yv else "garbage")
            tot[key] = tot.get(key, 0) + 1
    log("  %d recordings, %d mice, %d events: %d spike, %d garbage"
        % (len(ents), len({e["mouse_of"] for e in ents}),
           sum(e["n"] for e in ents), sum(e["n_ds"] for e in ents),
           sum(e["n_garbage"] for e in ents)))
    for k in sorted(tot):
        log("    %-44s %s" % (k, tot[k]))
    for s in ds["skipped"]:
        log("  skipped %s -- %s" % (s["label"], s["why"]))
    path = os.path.join(STORE.models, "dataset.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ds, fh)
    return ds, tot


def main(argv):
    load_jarvis()
    ds, tot = build()
    if argv[:1] == ["build"]:
        return 0
    log("READ: both reads of every event (%d processes; cached)" % READERS)
    data, failed = P.read_all(ds["entries"], A._aibeta_open, A.AIBETA,
                              want_filt={"notch", "10_40", "5_100", "hp1"},
                              want_spec=True, log=log, processes=READERS,
                              logs_dir=A.LOGS_DIR)
    for k, v in failed.items():
        log("  could not read %s: %s" % (k, v))
    log("  %d recordings read" % len(data))

    base = P.TF_FAMILIES + ["origin"]
    variants = [
        ("Tooth Fairy's inputs", base),
        ("+ Rain's filters", base + P.RAIN_FAMILIES),
        ("+ Rain's filters + spectrogram 1-800 Hz",
         base + P.RAIN_FAMILIES + ["spec800"]),
        ("+ Rain's filters + spectrogram 1-1000 Hz",
         base + P.RAIN_FAMILIES + ["spec1000"]),
        ("+ Rain's filters + spectrogram 1-2000 Hz",
         base + P.RAIN_FAMILIES + ["spec2000"]),
    ]
    log("COMPARE: 5 folds of whole recordings, one set of boosted trees")
    compare = []
    for name, fams in variants:
        out = P.train(data, fams, "hgb", folds=5, inner=2)
        r = out["results"]
        b1, b9 = r["bars"]["1.0"], r["bars"]["0.995"]
        row = {"name": name, "families": fams, "auc": r["pooled"].get("auc"),
               "seconds": out["seconds"], "n_features": r["n_features"],
               "bar_1.0": {k: b1[k] for k in ("spike_recall",
                                              "garbage_into_spike",
                                              "spike_called")},
               "bar_0.995": {k: b9[k] for k in ("spike_recall",
                                                "garbage_into_spike",
                                                "spike_called")}}
        compare.append(row)
        log("  %-44s AUC %s | zero-garbage bar: %5.1f%% of spikes, %d garbage"
            " through | 99.5%%: %5.1f%%, %d through | %d inputs, %.0f s"
            % (name, row["auc"], 100 * b1["spike_recall"],
               b1["garbage_into_spike"], 100 * b9["spike_recall"],
               b9["garbage_into_spike"], r["n_features"], out["seconds"]))

    best = max(compare, key=lambda r: (r["bar_1.0"]["spike_recall"]
                                       - 0.02 * r["bar_1.0"]["garbage_into_spike"],
                                       r["auc"] or 0))
    # The blend is five sets of trees: about five times the cost. A
    # leave-one-recording-out run is (recordings x 3 + 1) fits; past eight
    # hours one set of trees is used instead, and said.
    n_rec = len(data)
    per_fit = best["seconds"] / (5 * 3 + 1)
    est_blend_h = per_fit * 5 * (n_rec * 3 + 1) / 3600.0
    model_id = "blend" if est_blend_h <= 8.0 else "hgb"
    log("FINAL: %s, leave one recording out (%d folds), model %s "
        "(the blend was estimated at %.1f h)"
        % (best["name"], n_rec, model_id, est_blend_h))
    out = P.train(data, best["families"], model_id, folds=None, inner=2)
    r = out["results"]
    rid = STORE.new_id()
    rec = {
        "schema": P.SCHEMA, "id": rid, "at": aibeta._now(),
        "computed": A.STORE.provenance(),
        "rules": "prospector.consolidate as of 2026-11-03: Panning wins, "
                 "Checkup otherwise, Tooth Fairy-accepted calls count, "
                 "Toothy-era garbage counts, no Spotter garbage, no KCNT1",
        "data": {"n_recordings": n_rec,
                 "n_mice": len({e["mouse_of"] for e, _f in data}),
                 "n_events": int(r["pooled"]["n"]),
                 "n_spike": int(r["pooled"]["n_ds"]),
                 "n_garbage": int(r["pooled"]["n_garbage"]),
                 "tally": tot,
                 "entries": [{k: e[k] for k in (
                     "entry_id", "label", "mouse_of", "version",
                     "version_name", "n", "n_ds", "n_garbage", "tally")}
                     for e, _f in data],
                 "failed": failed, "skipped": ds["skipped"]},
        "compare": compare,
        "final": {"name": best["name"], "families": out["families"],
                  "model": model_id, "folds": out["folds"],
                  "inner": out["inner"], "seconds": out["seconds"],
                  "results": r},
    }
    path = STORE.save(rec, {"model": out["model"], "feature_names": out["names"],
                            "families": out["families"], "run_id": rid,
                            "channels": "even"})
    log("  saved %s" % path)
    if out.get("held_out"):
        hpath = os.path.join(STORE.models, rid + "_held_out.json")
        with open(hpath, "w", encoding="utf-8") as fh:
            json.dump(out["held_out"], fh)
        log("  every event's held-out score: %s" % hpath)
    for c_ in ("1.0", "0.999", "0.998", "0.995", "0.99"):
        b = r["bars"][c_]
        log("  bar %-6s  Spike: %5d called, %5.1f%% of spikes, %3d garbage "
            "through | lean spike %5d (%d spikes) | lean garbage %5d "
            "(%d garbage)" % (c_, b["spike_called"], 100 * b["spike_recall"],
                              b["garbage_into_spike"], b["lean_spike"],
                              b["lean_spike_true"], b["lean_garbage"],
                              b["lean_garbage_true"]))
    log("done in %.1f h" % ((time.time() - T0) / 3600.0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
