# -*- coding: utf-8 -*-
"""Does the cluster get the same answer as this computer?

Everything else in VACC Mode is plumbing. This is the question: Incisor runs
on a compute node and Incisor runs here, over a recording both can read, and
the two either agree exactly or the feature is worthless. Nothing about a
faster answer matters if it is a different answer.

It is checked on the absolute microsecond stamp rather than on how many
events were found, because a count can match by luck and `abs_us` cannot --
it is, in `incisor.py`'s own words, "the one identity that does not depend on
which tool made the number".

THREE WAYS THIS CHECK LIED BEFORE IT WORKED

Worth writing down, because each produced a confident pass:

  * Four channels were picked without looking, and all four were quiet. Zero
    events here, zero events there, and "0 == 0" reported as agreement. The
    channels are chosen by scanning for events now, and a run that finds none
    fails instead of passing.

  * The local result keys `_rows` by int and the one off the cluster arrives
    through JSON, which has no integer keys. Indexing the remote with an int
    found nothing, `zip` produced no pairs, and a loop that compared NOTHING
    reported a maximum difference of exactly zero.

  * The event's time field is `start`, not `t`. Asking for `t` got None on
    both sides, which compared equal.

So the number of comparisons actually made is printed and asserted. A check
that cannot say how much it checked is a check that can quietly check
nothing.

    python tools/check_vacc_parity.py                 finds a recording itself
    python tools/check_vacc_parity.py <gid>           uses that one

Needs a configured VACC account and a recording readable from both sides.
Skips cleanly, and loudly, when there is not one.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import cfc, continuity, csc, ids, incisor, vacc, vaccrun  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(APP, "GUI_logs")
FAILED = []
N_CHANNELS = 4


def check(name, ok, detail=""):
    print("  %-58s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail))
    if not ok:
        FAILED.append(name)


def rows_of(out):
    """`_rows` with int keys, whichever side it came from."""
    return dict((int(k), v or [])
                for k, v in (out.get("_rows") or {}).items())


def pick_pair(cfg, want_gid=None):
    """A recording the cluster holds AND this machine can open."""
    from backend import sessreg, store as storemod
    reg = sessreg.Registry(storemod.Store(LOGS, auto_stage=False))
    by_key = {}
    for rec in reg.all():
        if not rec.get("gid"):
            continue
        if rec.get("key"):
            by_key.setdefault(str(rec["key"]).lower(), rec)
    for row in vacc.inventory_cached(cfg, cfg.get("scratch_root")):
        ident = ids.identify(row["path"])
        rec = by_key.get(str(ident.get("key") or "").lower())
        if not rec:
            continue
        if want_gid and rec.get("gid") != want_gid:
            continue
        for p in (rec.get("paths") or []):
            if isinstance(p, str) and os.path.isdir(p):
                return rec["gid"], p, row["path"]
    return None, None, None


def main():
    want_gid = sys.argv[1] if len(sys.argv) > 1 else None
    vacc.configure(LOGS)
    cfc.configure(LOGS)
    cfg = vacc.load_config(LOGS)
    if not cfg.get("configured"):
        print("no VACC account on this machine; nothing to compare")
        return 0

    print("\nfinding a recording both sides can read")
    gid, local, remote = pick_pair(cfg, want_gid)
    if not local:
        print("  none found -- the cluster holds nothing this machine can "
              "also open, so there is nothing to compare")
        return 0
    print("  %s" % gid)
    print("  here   : %s" % local)
    print("  cluster: %s" % remote)

    sess = csc.open_session(local, even_only=False, invert=True)
    report = continuity.check(local)

    def spec_for(channels):
        return {"path": local, "channels": list(channels), "invert": True,
                "even_only": False, "band": list(incisor.DS_BAND),
                "height_sd": incisor.DS_HEIGHT_SD,
                "abs_uv": incisor.DS_ABS_THR_UV,
                "dist_ms": incisor.DS_DIST_MS, "prom_uv": incisor.DS_PROM_UV,
                "wlen_ms": incisor.DS_WLEN_MS, "lfp_fs": incisor.LFP_FS}

    print("\nlooking for channels that actually have events")
    allch = [c["index"] for c in (sess.get("channels") or [])]
    probe = allch[::4][:16] or allch[:8]
    spec = spec_for(probe)
    plan = incisor.plan_for(sess, spec, report)
    job = cfc.Job(spec, [("ds read", int(plan["span_s"] * plan["n_channels"])),
                         ("ds detect", plan["n_channels"])],
                  max(0.001, plan["megasamples"]), "d:")
    scout = incisor.run(sess, spec, report, job)
    hot = sorted(((len(v), k) for k, v in rows_of(scout).items() if v),
                 reverse=True)[:N_CHANNELS]
    check("some channel has dentate spikes to compare", bool(hot),
          "every probed channel was silent, so any comparison would be 0==0")
    if not hot:
        return 1
    channels = sorted(c for _, c in hot)
    print("  using %s (%d events between them)"
          % (channels, sum(n for n, _ in hot)))

    # ---- the two runs, one spec ----
    spec = spec_for(channels)
    plan = incisor.plan_for(sess, spec, report)
    steps = [("ds read", int(plan["span_s"] * plan["n_channels"])),
             ("ds detect", plan["n_channels"])]

    print("\nrunning here")
    job = cfc.Job(spec, steps, max(0.001, plan["megasamples"]), "d:")
    t0 = time.time()
    here = incisor.run(sess, spec, report, job)
    t_here = time.time() - t0
    print("  %.1fs" % t_here)

    print("\nrunning on the cluster")
    vacc.push_code(cfg, APP)
    run = vaccrun.VaccRun(cfg, "incisor", spec, remote,
                          plan={"seconds": max(60.0, t_here * 3)},
                          megasamples=plan["megasamples"],
                          tool_steps=steps, report=report)
    job2 = cfc.start({"path": local}, vaccrun.steps() + steps, run.work,
                     max(0.001, plan["megasamples"]), "vacc:scratch")
    t0 = time.time()
    while job2.status == "running" and (time.time() - t0) < 3600:
        time.sleep(2)
    t_there = time.time() - t0
    print("  %.1fs  slurm=%s  status=%s" % (t_there, run.slurm_id, job2.status))
    check("the cluster run finished", job2.status == "done",
          job2.error or job2.status)
    if job2.status != "done":
        return 1
    there = job2.result

    # ---- and do they agree ----
    print("\ncomparing")
    ra, rb = rows_of(here), rows_of(there)
    check("both sides report the same channels", set(ra) == set(rb),
          "%s vs %s" % (sorted(ra), sorted(rb)))
    for ch in sorted(set(ra) & set(rb)):
        check("channel %-3d found the same number of events" % ch,
              len(ra[ch]) == len(rb[ch]),
              "%d here, %d there" % (len(ra[ch]), len(rb[ch])))

    compared, differing = 0, 0
    for ch in sorted(set(ra) & set(rb)):
        for ea, eb in zip(ra[ch], rb[ch]):
            if not (isinstance(ea, dict) and isinstance(eb, dict)):
                continue
            compared += 1
            if ea.get("abs_us") != eb.get("abs_us"):
                differing += 1
    total = sum(len(v) for v in ra.values())
    # The assertion that stops this check passing on an empty comparison.
    check("every event was actually compared", compared == total and compared,
          "compared %d of %d" % (compared, total))
    check("no event is stamped at a different microsecond", differing == 0,
          "%d of %d differ" % (differing, compared))

    for field in ("hilus", "theta", "ripple"):
        check("the %s pick agrees" % field, here.get(field) == there.get(field),
              "%r here, %r there" % (here.get(field), there.get(field)))

    print()
    print("  %d events compared, %.1fs here, %.1fs on the cluster"
          % (compared, t_here, t_there))
    if FAILED:
        print("\nFAILED: " + ", ".join(FAILED))
        return 1
    print("\nALL PASS -- the cluster and this computer agree exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
