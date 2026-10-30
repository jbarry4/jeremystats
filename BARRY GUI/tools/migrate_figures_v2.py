# -*- coding: utf-8 -*-
"""Bring the figures made before v2 across into the figure store.

    python tools/migrate_figures_v2.py            say what would happen
    python tools/migrate_figures_v2.py --apply    do it

Decided 2026-10-22: convert the real ones, archive the harness ones, delete
nothing.

Every run record of kind "figure" is one of four things:

  harness      made by a harness to prove rendering works. Judged by the
               record itself -- its label says "harness", or its file is in
               the by-product lane (Results/_scratch) -- never by who was at
               the keyboard: the harnesses ran under the user's own name.
               ARCHIVED: a file still in Results is moved to
               Results/_scratch/harness through Results.move(), which repoints
               anything holding it and tombstones the old path. Nothing is
               deleted; no figure record is made for it.
  builder      made by the old builder, with a full recipe (schema 1). Becomes
               a figure whose panels are Xplorefinder panels
               (figkit/legacy.py), with the original file as its version 1.
  rootcanal    filed by Root Canal with its own {tool, params} recipe. Becomes
               a one-panel figure of the Root Canal plot it is ("space" or
               "flat"), with the original file as its version 1.
  no recipe    recorded before recipes. Left exactly as it is.

Run records are never edited (they are write-once): a figure made here
carries `legacy.run`, and /api/figures/for-run/<run> finds it from that.

Already migrated runs are skipped, so running it twice does nothing twice.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import figures as figuresmod                # noqa: E402
from backend import device as devicemod                  # noqa: E402
from backend import profile as profilemod                # noqa: E402
from backend import results as resultsmod                # noqa: E402
from backend import store as storemod                    # noqa: E402
from backend.figkit import legacy                        # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")
RESULTS_DIR = os.path.join(APP, "Results")
SCRATCH = "_scratch"


def rel_of(out):
    """A run output's path inside Results, from its `rel` (which is the same
    on every machine) and only then from its absolute `path`."""
    if not isinstance(out, dict):
        return None
    rel = (out.get("rel") or "").replace("\\", "/")
    if rel:
        return rel
    p = out.get("path") or ""
    if p and os.path.abspath(p).startswith(os.path.abspath(RESULTS_DIR)):
        return os.path.relpath(p, RESULTS_DIR).replace("\\", "/")
    return None


def here(rel):
    return bool(rel) and os.path.isfile(os.path.join(RESULTS_DIR,
                                                     rel.replace("/", os.sep)))


def classify(run):
    rec = run.get("recipe")
    rel = rel_of(run.get("output"))
    label = str(run.get("label") or "")
    if "harness" in label.lower() or (rel or "").lower().startswith(SCRATCH + "/"):
        return "harness"
    if isinstance(rec, dict) and rec.get("schema") == figuresmod.SCHEMA:
        return "v2"
    if isinstance(rec, dict) and rec.get("tool") == "rootcanal":
        return "rootcanal"
    if isinstance(rec, dict) and rec.get("panels") is not None:
        return "builder"
    return "no recipe"


def rootcanal_layout(run):
    rec = run.get("recipe") or {}
    prm = run.get("parameters") or {}
    sess = run.get("session") or {}
    plot = prm.get("panel") or "space"
    params = dict(rec.get("params") or {})
    for k in ("entry_id", "gid", "from_version", "params_hash", "stamps_hash"):
        if rec.get(k) is not None:
            params.setdefault(k, rec[k])
    return {
        "schema": figuresmod.SCHEMA, "profile": "lab",
        "width": "letter_landscape", "height_mm": None, "rows": 1, "cols": 1,
        "title": run.get("label") or "Root Canal",
        "subtitle": "", "footer": {},
        "recording": {"gid": rec.get("gid") or sess.get("gid"),
                      "label": sess.get("label"), "path": sess.get("path"),
                      "invert": True, "identity": sess or None},
        "panels": [{"uid": "p1", "tool": "rootcanal", "plot": plot,
                    "row": 0, "col": 0, "rowspan": 1, "colspan": 1,
                    "title": "", "params": params}],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    store = storemod.Store(LOGS, auto_stage=False)
    # A bare Store stamps writes with the git identity; the profile and the
    # device are what everything else in the app stamps them with.
    prof = profilemod.Profile(LOGS, store)
    store.profile = prof
    dev = devicemod.Device(LOGS, store)
    store.device = dev
    prof.device = dev
    print("writing as:", store.provenance().get("user"), "on",
          store.provenance().get("machine"))
    figs = figuresmod.Figures(LOGS, store, RESULTS_DIR)
    done = {(r.get("legacy") or {}).get("run") for r in figs.book.all()}

    plan = {"harness": [], "builder": [], "rootcanal": [], "no recipe": [],
            "v2": [], "already": []}
    for run in store.all_runs():
        if run.get("kind") != "figure":
            continue
        kind = classify(run)
        if run.get("id") in done:
            plan["already"].append(run)
            continue
        plan[kind].append(run)

    def files_of(run):
        out = {}
        for o in [run.get("output")] + list(run.get("outputs") or []):
            rel = rel_of(o)
            if rel and here(rel):
                ext = os.path.splitext(rel)[1].lower().lstrip(".")
                if ext in ("png", "svg", "pdf"):
                    out.setdefault(ext, rel)
        return out

    sweep = [r for r in plan["harness"]
             if rel_of(r.get("output")) and here(rel_of(r.get("output")))
             and not rel_of(r.get("output")).lower().startswith(SCRATCH + "/")]
    print("figure runs on record:")
    for k in ("builder", "rootcanal", "harness", "no recipe", "v2", "already"):
        print("  %-10s %4d" % (k, len(plan[k])))
    print()
    print("would convert %d builder figure(s) and %d Root Canal figure(s);"
          % (len(plan["builder"]), len(plan["rootcanal"])))
    print("  of those, %d have their file on this machine."
          % sum(1 for r in plan["builder"] + plan["rootcanal"] if files_of(r)))
    print("would archive %d harness figure(s): %d file(s) still in Results "
          "move to Results/_scratch/harness, the rest are already there or "
          "gone." % (len(plan["harness"]), len(sweep)))
    print("would leave %d with no recipe as they are." % len(plan["no recipe"]))
    for r in plan["builder"]:
        print("  builder   %s  %s  %s" % (r["id"], (r.get("provenance") or {})
                                         .get("at", "")[:10], r.get("label")))
    if not args.apply:
        print("\nNothing was written. Run again with --apply.")
        return 0

    made = 0
    for run in plan["builder"] + plan["rootcanal"]:
        prov = run.get("provenance") or {}
        if classify(run) == "builder":
            lay = legacy.from_recipe(run.get("recipe") or {}, run)
        else:
            lay = rootcanal_layout(run)
        lay.pop("legacy", None)
        rec = figs.create(lay, prov, legacy={"run": run["id"],
                                             "script": run.get("script")},
                          created=prov.get("at"))
        figs.add_version(rec["id"], lay, {}, {}, {}, prov,
                         note="Brought across from %s (run %s)"
                              % (run.get("script") or "an earlier figure",
                                 run["id"]),
                         source="migration", files=files_of(run),
                         at=prov.get("at"))
        made += 1
    print("made %d figure(s)." % made)

    if sweep:
        res = resultsmod.Results(store, RESULTS_DIR, os.path.dirname(APP))
        moved = 0
        for run in sweep:
            rel = rel_of(run.get("output"))
            full = os.path.join(RESULTS_DIR, rel.replace("/", os.sep))
            rid = res._result_id(full)
            try:
                res.move(rid, SCRATCH + "/harness", store=store)
                moved += 1
            except Exception as exc:                     # noqa: BLE001
                print("  could not move %s: %s" % (rel, exc))
        print("moved %d harness file(s) into Results/_scratch/harness." % moved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
