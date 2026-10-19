# -*- coding: utf-8 -*-
"""Two Results catalogue faults, checked on a throwaway Results folder.

    python tools\\check_results_runlink.py           the checks
    python tools\\check_results_runlink.py --break   and the negative controls

1. Moving a result dropped its run link. `_repoint` rewrote `run["outputs"]`
   while the catalogue read `run["output"]`, so a moved figure lost its
   provenance; and the second and later files a run wrote were never linked
   at all. Every file a run wrote must stay linked after a move.
2. `_from_run` defaulted `kind` to "figure", so a CSV from a run with no kind
   was offered the figure Rebuild. It must default to what the file is.

Nothing here touches the real Results folder or GUI_logs: both live under
the system temp directory and are removed at the end.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import results as R          # noqa: E402
from backend import store as storemod     # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("ok    " if cond else "FAIL  ") + name
          + ("" if cond or not detail else "   [%s]" % detail))


def run():
    del results[:]
    tmp = tempfile.mkdtemp(prefix="jarvis-results-runlink-")
    try:
        logs = os.path.join(tmp, "GUI_logs")
        outdir = os.path.join(tmp, "Results")
        os.makedirs(outdir)
        st = storemod.Store(logs, auto_stage=False)
        res = R.Results(st, outdir, tmp)

        def write(name, body=b"x"):
            p = os.path.join(outdir, name)
            with open(p, "wb") as fh:
                fh.write(body)
            return {"path": p, "rel": name}

        fig, csv1, csv2 = (write("pano.png", b"\x89PNG....."),
                           write("pano_counts.csv", b"a,b\n1,2\n"),
                           write("pano_hist.csv", b"a\n1\n"))
        run1 = st.record_run({"kind": "panorama", "script": "Panorama",
                              "label": "Panorama -- test", "status": "done",
                              "output": fig, "outputs": [fig, csv1, csv2]})
        coupling = write("coupling pair 3.csv", b"r\n0.3\n")
        run2 = st.record_run({"script": "The Arc · Coupling",
                              "label": "coupling pair 3", "status": "ok",
                              "output": coupling})

        cat = {r["name"]: r for r in res.catalog(refresh=True)}
        check("every file a run wrote is linked to it, not only the first",
              all(cat[n].get("run_id") == run1["id"]
                  for n in ("pano.png", "pano_counts.csv", "pano_hist.csv")),
              ", ".join("%s=%s" % (n, cat[n].get("run_id"))
                        for n in ("pano.png", "pano_counts.csv",
                                  "pano_hist.csv")))
        c = cat["coupling pair 3.csv"]
        check("a run with no kind that wrote a CSV is not called a figure",
              c.get("kind") != "figure", str(c.get("kind")))
        check("it is called what the file is", c.get("kind") == "table",
              str(c.get("kind")))
        check("a run that said its kind keeps it",
              cat["pano.png"].get("kind") == "panorama")

        for name in ("pano.png", "pano_counts.csv", "coupling pair 3.csv"):
            res.move(cat[name]["id"], "Filed/Here", store=st)
        cat = {r["name"]: r for r in res.catalog(refresh=True)}
        moved = {n: cat.get(n) for n in ("pano.png", "pano_counts.csv",
                                         "coupling pair 3.csv")}
        check("the moved files are in the folder",
              all(m and m.get("folder") == "Filed/Here"
                  for m in moved.values()),
              str({n: (m or {}).get("folder") for n, m in moved.items()}))
        check("a moved figure keeps its run link (the `output` field)",
              (moved["pano.png"] or {}).get("run_id") == run1["id"],
              str((moved["pano.png"] or {}).get("run_id")))
        check("a moved second file keeps its run link (`outputs`)",
              (moved["pano_counts.csv"] or {}).get("run_id") == run1["id"],
              str((moved["pano_counts.csv"] or {}).get("run_id")))
        check("a moved file whose run had only `output` keeps its link",
              (moved["coupling pair 3.csv"] or {}).get("run_id")
              == run2["id"])
        check("the file left behind is still linked too",
              (cat.get("pano_hist.csv") or {}).get("run_id") == run1["id"])
        rr = next(r for r in st.all_runs() if r["id"] == run1["id"])
        check("the run record itself now points at the new path",
              os.path.abspath(rr["output"]["path"])
              == os.path.abspath(os.path.join(outdir, "Filed", "Here",
                                              "pano.png")),
              rr["output"]["path"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [r for r in results if not r[1]]
    print("\n%d check(s), %d failed" % (len(results), len(bad)))
    return results


def negative_controls():
    """Put each fault back and require the check that names it to fail."""
    ok = True
    real_files = R.Results._run_files

    def only_output(self):
        for rec in self.store.all_runs():
            o = rec.get("output")
            if isinstance(o, dict) and o.get("path"):
                yield rec, o
    R.Results._run_files = only_output
    try:
        got = dict(run())
    finally:
        R.Results._run_files = real_files
    caught = got.get("every file a run wrote is linked to it, not only "
                     "the first") is False
    print(("ok    " if caught else "FAIL  ")
          + "control: reading `output` alone is caught")
    ok = ok and caught

    real_from_run = R.Results._from_run

    def figure_default(self, rec, out):
        got = real_from_run(self, rec, out)
        if not rec.get("kind"):
            got["kind"] = "figure"
        return got
    R.Results._from_run = figure_default
    try:
        got = dict(run())
    finally:
        R.Results._from_run = real_from_run
    caught = got.get("a run with no kind that wrote a CSV is not called a "
                     "figure") is False
    print(("ok    " if caught else "FAIL  ")
          + "control: the old 'figure' default is caught")
    return ok and caught


if __name__ == "__main__":
    ok = all(r[1] for r in run())
    if "--break" in sys.argv:
        ok = negative_controls() and ok
        ok = all(r[1] for r in run()) and ok
    sys.exit(0 if ok else 1)
