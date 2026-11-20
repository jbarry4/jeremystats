"""Checks for the whole-pair window (cue 1 onset to cue 2 offset, 20 s) of
the Monolith's sweep: the node's task kinds `pair`, `pac_pair`, `rest_pair`
and `pac_rest_pair`, on a made-up recording written as real .ncs files
(tools/check_events.make_session: 12 regions, one wire each, 4 kHz).

  * the window is the presentation's cue 1 onset to its cue 2 offset;
  * every measure comes back, for every region pair, in one window;
  * a wire left out of cue 2 is left out of the whole pair (the planner
    joins the two cues' exclusions), and its pairs are empty;
  * PAC over the 20 s window, and the 20 s rest epochs, run the same way;
  * the planner gives the whole pair exactly the union of a presentation's
    Cue 1 and Cue 2 exclusions.

Usage: python tools/check_sweep_pair.py
"""
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

from backend import coupling, sweep                     # noqa: E402
from backend import monolith as MO                      # noqa: E402
import check_events as CE                                # noqa: E402

N = {"ok": 0, "bad": 0}


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print("  %s  %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "   [%s]" % (detail,)))


def main():
    work = tempfile.mkdtemp(prefix="zz-pair-")
    try:
        folder = os.path.join(work, "spc")
        os.makedirs(folder)
        print("Writing a made-up recording (12 regions, %d s, 4 kHz)" % CE.DUR)
        CE.make_session(folder)
        names = sweep.regions()
        acc = coupling.dewey_map()["Right ACC"][0]
        units = [{"id": "p%02d" % (k + 1), "pair": {"opener_t": a, "closer_t": a + 10.0, "offset_t": a + 20.0},
                  "drop": {"pair": [acc] if k == 0 else []}} for k, a in enumerate(CE.OPENERS[:3])]
        spec = {"kind": "pair", "bands": ["f06", "f10", "theta"], "units": units, "folder": folder,
                "regions": names, "blocked": {}, "bad": []}
        print("\nThe whole pair")
        w = sweep._windows_for("pair", units[0])
        check("one window, cue 1 onset to cue 2 offset (20 s)", w == [("pair", 60.0, 80.0)], w)
        arrays, meta = sweep.run_task(spec)
        v, wires = arrays["values"], arrays["wires"]
        P = len(sweep.pairs_of(list(range(len(names)))))
        check("every measure, every pair, one window", v.shape == (3, 1, 3, len(sweep.EDGE_METHODS), P)
              and meta["windows"] == ["pair"], v.shape)
        ai = names.index("Right ACC")
        acc_pairs = [i for i, (a, b) in enumerate(sweep.pairs_of(list(range(len(names))))) if ai in (a, b)]
        other = [i for i in range(P) if i not in acc_pairs]
        check("a wire left out of cue 2 is out of the whole pair, and its pairs are empty",
              wires[0, 0, ai] == -1 and np.isnan(v[0, 0, :, :, acc_pairs]).all()
              and wires[1, 0, ai] == acc and np.isfinite(v[1, 0, :, 0, acc_pairs]).all(), wires[:, 0, ai])
        check("and every other pair is measured", np.isfinite(v[0, 0, :, 0, other]).all())
        pa, pm = sweep.run_task(dict(spec, kind="pac_pair", bands=[]))
        check("PAC over the whole pair: one window of every cell", pa["values"].shape[1] == 1
              and np.isfinite(pa["values"][1]).any(), pa["values"].shape)
        rest = [{"id": "f01", "pair": {"t0": 300.0, "t1": 320.0}, "drop": {"rest": []}}]
        ra, _rm = sweep.run_task(dict(spec, kind="rest_pair", units=rest))
        check("a 20 s rest epoch, measured as the whole pair is", ra["values"].shape == (1, 1, 3, len(sweep.EDGE_METHODS), P)
              and np.isfinite(ra["values"][0, 0, :, 0, other]).all())
        print("\nThe planner")
        man = {"days": [{"rat": 3, "day": "Precon1", "gid": "g", "blocked": {}, "bad": [], "fast_banked": True,
                         "units": [{"id": "p01", "pair": units[0]["pair"], "manual": {"flat": []},
                                    "drop": {"pre": [1], "cue1": [5, 6], "cue2": [6, 21], "post": [9]}}],
                         "rest": [], "rest_pair": [], "folders": []}]}
        chk = {"days": [{"rat": 3, "day": "Precon1", "spc_ready": True, "rest_ready": False,
                         "folders": [{"role": "SPC", "gid": "g", "remote": "/r"}]}], "ready_rats": [3]}
        tasks = [t for t in MO.plan_tasks(man, chk, extra={"pair": True}) if t["kind"] == "pair"]
        check("the whole pair's exclusion is the union of Cue 1's and Cue 2's",
              tasks and all(t["spec"]["units"][0]["drop"] == {"pair": [5, 6, 21]} for t in tasks),
              tasks and tasks[0]["spec"]["units"][0]["drop"])
        check("in %d band chunks, every band once" % MO.PAIR_CHUNKS,
              sorted(b for t in tasks for b in t["spec"]["bands"]) == sorted(sweep.bands_for("pair")))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 1 if N["bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
