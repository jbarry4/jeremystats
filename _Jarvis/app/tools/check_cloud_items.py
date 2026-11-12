# -*- coding: utf-8 -*-
"""`Sync.item_states` gives the same answer with its curation stamps kept.

    python tools/check_cloud_items.py

The newest stamp of every curation set is kept until the curation store's
signature moves (cloudsync.Sync._curation_newest, 2026-10-22). This works
the curation part out the way it was worked out before -- every stamp
parsed on every call -- on this machine's own GUI_logs, and checks the two
agree record for record, for a cursor before everything, one after
everything, and one in the middle. Then it times both.

Reads only. The app is imported for its stores, so its background threads
start as they do for any harness run.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
os.chdir(APP)

from backend import app as A          # noqa: E402
from backend import cloud, cloudsync  # noqa: E402


def old_curation(sync, last_push, known_gids):
    """The loop as it stood before the stamps were kept."""
    def judge(stamp):
        if not last_push:
            return "waiting"
        if not stamp:
            return "synced"
        return "waiting" if cloudsync._after(stamp, last_push) else "synced"

    def orphan(gid):
        return bool(known_gids is not None and gid and gid not in known_gids)

    d = {}
    for rec in (sync.curate.all() if sync.curate else []):
        gid, kind = rec.get("gid"), rec.get("kind")
        if not gid or not kind:
            continue
        sid = "%s__%s" % (gid, kind)
        if sync._is_demo(rec):
            d[sid] = {"state": "local", "why": "demo"}
            continue
        if orphan(gid):
            d[sid] = {"state": "local", "why": "no recording"}
            continue
        stamps = [cloud.ts(cloudsync._prov(rec, "updated").get("at"))]
        for ev in (rec.get("events") or []):
            stamps.append(cloud.ts(ev.get("at")) or cloud.ts(ev.get("cleared_at")))
            for r in (ev.get("reviews") or []):
                stamps.append(cloud.ts(r.get("at")))
        stamps = [s for s in stamps if s]
        t = max(stamps, key=cloudsync._ts_key) if stamps else None
        d[sid] = {"state": judge(t), "at": t}
    return d


def main():
    sync = A.CLOUD
    known = {r.get("gid") for r in (A.REG.all() or []) if r.get("gid")}
    stamps = sorted((v[2] for v in sync._curation_newest().values() if v[2]),
                    key=cloudsync._ts_key)
    middle = stamps[len(stamps) // 2] if stamps else None
    fails = 0
    for label, cursor in (("no push yet", None),
                          ("a push before everything", "2000-01-01T00:00:00+00:00"),
                          ("a push in the middle", middle),
                          ("a push after everything", "2100-01-01T00:00:00+00:00")):
        for kg_label, kg in (("with the registry", known), ("without", None)):
            new = sync.item_states(["curation"], last_push=cursor,
                                   known_gids=kg)["curation"]
            old = old_curation(sync, cursor, kg)
            same = new == old and list(new) == list(old)
            waiting = sum(1 for v in new.values() if v.get("state") == "waiting")
            print("%-4s %-26s %-18s %d sets, %d waiting"
                  % ("ok" if same else "FAIL", label, kg_label, len(new), waiting))
            fails += 0 if same else 1

    t = time.perf_counter()
    for _ in range(3):
        old_curation(sync, middle, known)
    t_old = (time.perf_counter() - t) / 3
    t = time.perf_counter()
    for _ in range(3):
        sync.item_states(["curation"], last_push=middle, known_gids=known)
    t_new = (time.perf_counter() - t) / 3
    print("curation part: %.0f ms worked out every time, %.0f ms kept"
          % (t_old * 1000, t_new * 1000))
    t = time.perf_counter()
    sync.item_states(last_push=middle, known_gids=known)
    print("every kind, kept: %.0f ms" % ((time.perf_counter() - t) * 1000))
    print("nothing failing" if not fails else "%d FAILED" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
