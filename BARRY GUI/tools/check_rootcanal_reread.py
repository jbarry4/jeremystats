# -*- coding: utf-8 -*-
"""Root Canal pools: a member read elsewhere is read again here, on request;
no recording goes in twice; a member's analysis saves as its own single.

    python tools/check_rootcanal_reread.py

Asked for 2026-10-19. A banked member whose read was made on another
machine, asked to be measured the pool's way, stopped the pool with "read
that set on this machine in Single". Now the pool names those members
(`away`), `/api/rootcanal/pool/reread` finds each recording -- a drive here,
or the VACC -- and reads it exactly as it was read (same stamps, so the same
read), and the pool fits.

On this machine's REAL bank and recordings, with the results and their
reads copied into a temp folder first, so "read elsewhere" is real (the
copy has no .npz) and nothing real is written:

  * the pool refuses the member, and names it in `away`;
  * the reread finds the recording here, reads it, and files the read;
  * the pool then fits, measured the pool's way;
  * a recording with a banked result and a read here, both ticked, is
    refused as the same recording twice, naming the second;
  * the member's analysis saves as its own single, in a temp artifact store;
  * a member whose set cannot be found is refused with a reason.
"""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

FAILED = []


def check(name, ok, detail=""):
    print("  %-72s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:700])
    if not ok:
        FAILED.append(name)


def wait(A, job_id, limit_s=900):
    t0 = time.time()
    while time.time() - t0 < limit_s:
        job = A.cfcmod.get(job_id)
        snap = job.snapshot() if job else {"status": "gone"}
        if snap["status"] != "running":
            return snap
        time.sleep(0.5)
    return A.cfcmod.get(job_id).snapshot()


def main():
    from backend import app as A
    from backend import artifacts as artifactsmod
    from backend import rootcanal, toolresults
    tmp = tempfile.mkdtemp(prefix="jarvis-rcreread-")
    logs = os.path.join(tmp, "GUI_logs")
    real = {"ROOTCANAL": A.ROOTCANAL, "ARTIFACTS": A.ARTIFACTS,
            "record_activity": A.STORE.record_activity,
            "record_error": A.STORE.record_error}
    try:
        # The results, without their reads: every banked member is "read
        # elsewhere" in the copy.
        os.makedirs(os.path.join(logs, "rootcanal"), exist_ok=True)
        shutil.copytree(os.path.join(APP, "GUI_logs", "rootcanal", "results"),
                        os.path.join(logs, "rootcanal", "results"))
        A.ROOTCANAL = toolresults.ToolResults(
            logs, "rootcanal", A.STORE,
            keys=tuple(rootcanal.Params.READ_KEYS)
            + tuple(rootcanal.Params.FIT_KEYS))
        A.ARTIFACTS = artifactsmod.Artifacts(logs, A.STORE)
        A.STORE.record_activity = lambda *a, **k: None
        A.STORE.record_error = lambda *a, **k: {"id": "check"}
        A.cfcmod.cache_clear() if hasattr(A.cfcmod, "cache_clear") else None
        c = A.app.test_client()
        cands = (c.get("/api/rootcanal/pool/candidates").get_json()
                 or {}).get("singles") or []
        banked = [x for x in cands if x.get("banked") and not x.get("here")]
        index = A._incisor_registry_index()
        local = [x for x in banked
                 if A._local_path_of(index.get(x.get("gid")) or {})]
        local.sort(key=lambda x: x.get("n") or 0)
        print("\n%d banked result(s), %d with the recording on this computer"
              % (len(banked), len(local)))
        pick = next((x for x in local if (x.get("n") or 0) >= 5), None)
        if not pick:
            check("a banked result whose recording is here", False, banked[:2])
            return
        key = pick["key"]
        rec = A.ROOTCANAL.get(pick["gid"], pick["params_hash"]) or {}
        cross0 = float(((rec.get("params") or {}).get("cross_ms")) or 50)
        other = 100.0 if abs(cross0 - 100.0) > 1e-6 else 75.0
        body = {"members": [{"key": key}], "measure": {"cross_ms": other}}
        print("on %s (%s events), banked with half-width search +/-%g ms, "
              "pooled at +/-%g" % (pick.get("session_label"), pick.get("n"),
                                   cross0, other))

        print("\nread elsewhere, measured another way")
        r = c.post("/api/rootcanal/pool/fit", json=body)
        j = r.get_json() or {}
        check("the pool refuses it", r.status_code == 400 and not j.get("ok"),
              j)
        check("naming the member, so it can be read again", j.get("away")
              == [key], j.get("away"))
        check("and saying it can be read here",
              "Read it here" in (j.get("error") or ""), j.get("error"))

        print("\nread it again, here")
        r = c.post("/api/rootcanal/pool/reread",
                   json={"members": [{"key": key}]}).get_json() or {}
        check("the reread starts as a job, one row for the member",
              r.get("ok") and (r.get("job") or {}).get("id")
              and not r.get("refused"), r)
        snap = wait(A, r["job"]["id"]) if r.get("job") else {}
        row = next((m for m in snap.get("members") or [] if m["id"] == key),
                   {})
        check("it finds the recording on this computer and reads it",
              snap.get("status") == "done" and row.get("status") == "done"
              and row.get("where") == "here", (snap.get("status"), row,
                                               snap.get("error")))
        check("and the read is filed as the very read it was",
              A.ROOTCANAL.has_cached(pick["gid"], pick["read"], ".npz"))
        r = c.post("/api/rootcanal/pool/fit", json=body)
        j = r.get_json() or {}
        check("now the pool fits, measured the pool's way",
              r.status_code == 200 and j.get("ok")
              and (j.get("members") or [{}])[0].get("remeasured"), j.get("error"))
        r = c.post("/api/rootcanal/pool/reread",
                   json={"members": [{"key": key}]}).get_json() or {}
        check("asked again, it is already here and nothing is read",
              r.get("ok") and r.get("job") is None and r.get("here") == [key], r)

        print("\nthe same recording twice")
        cands = (c.get("/api/rootcanal/pool/candidates").get_json()
                 or {}).get("singles") or []
        twin = next((x for x in cands if str(x["key"]).startswith("u:")
                     and x.get("entry_id") == pick.get("entry_id")), None)
        if not twin:
            print("  (no read of the live set here to pair it with; skipped)")
        else:
            r = c.post("/api/rootcanal/pool/fit", json={"members": [
                {"key": key}, {"key": twin["key"]}]})
            j = r.get_json() or {}
            check("banked and read-here of one recording are refused",
                  r.status_code == 400 and "twice" in (j.get("error") or ""),
                  j.get("error"))
            check("naming the second, to take out",
                  j.get("away") == [twin["key"]], j.get("away"))

        print("\nits own analysis, saved as a single")
        r = c.post("/api/rootcanal/pool/singles", json=dict(
            body, keys=[key])).get_json() or {}
        d = (r.get("done") or [{}])[0]
        check("saved as a single version, measured the pool's way",
              r.get("ok") and d.get("key") == key
              and str(d.get("new_key") or "").startswith("s:")
              and not r.get("away"), r)
        arts = A.ARTIFACTS.list(kind="rootcanal_single")
        check("in the (temp) artifact store, as a rootcanal single",
              len(arts) == 1, len(arts))

        if "--vacc" in sys.argv:
            print("\nread on the VACC, as for a recording only the cluster has")
            # The read taken away again, and the recording opened off the
            # cluster rather than off this computer's drive: the path a
            # laptop with no copy takes.
            os.remove(A._rootcanal_npz(pick["gid"], pick["read"]))
            A.cfcmod.cache_clear() if hasattr(A.cfcmod, "cache_clear") else None
            real_sess = A._braces_session

            def off_cluster(rec):
                sess, err = A._session_for("vacc:" + rec["gid"], True)
                if err:
                    raise RuntimeError(err)
                return sess, {}

            A._braces_session = off_cluster
            try:
                r = c.post("/api/rootcanal/pool/reread",
                           json={"members": [{"key": key}]}).get_json() or {}
                snap = wait(A, r["job"]["id"], 1800) if r.get("job") else {}
            finally:
                A._braces_session = real_sess
            row = next((m for m in snap.get("members") or []
                        if m["id"] == key), {})
            check("it is read on a compute node and brought home",
                  snap.get("status") == "done" and row.get("status") == "done"
                  and row.get("where") == "vacc",
                  (snap.get("status"), row, snap.get("error")))
            got = A.ROOTCANAL.get(pick["gid"], pick["read"]) or {}
            check("filed as the same read, saying where it was made",
                  A.ROOTCANAL.has_cached(pick["gid"], pick["read"], ".npz")
                  and (got.get("computed_on") or {}).get("where", "")
                  .startswith("vacc"), got.get("computed_on"))
            r = c.post("/api/rootcanal/pool/fit", json=body)
            check("and the pool fits from it",
                  r.status_code == 200 and (r.get_json() or {}).get("ok"),
                  (r.get_json() or {}).get("error"))

        print("\nwhat cannot be read")
        r = c.post("/api/rootcanal/pool/reread", json={"members": [
            {"key": "u:nosuchentry:abc"}]}).get_json() or {}
        check("a member whose set is not here is refused, with a reason",
              r.get("ok") and r.get("job") is None
              and (r.get("refused") or [{}])[0].get("why"), r)
    finally:
        A.ROOTCANAL = real["ROOTCANAL"]
        A.ARTIFACTS = real["ARTIFACTS"]
        A.STORE.record_activity = real["record_activity"]
        A.STORE.record_error = real["record_error"]
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
    print("\n%s" % ("all passed" if not FAILED else
                    "%d FAILED:\n  " % len(FAILED) + "\n  ".join(FAILED)))
    sys.exit(1 if FAILED else 0)
