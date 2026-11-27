"""Start (or resume) the 5% meta workflow through the real route, print its
progress as it changes, then kill the process outright after LIMIT seconds:
a crash, as far as the run can tell."""
import os, sys, time
APP = r'C:\Users\Z390\Desktop\jeremystats\_Jarvis\app'
sys.path.insert(0, APP)
os.chdir(APP)


def main():
    limit = float(sys.argv[1])
    from backend import app as A
    c = A.app.test_client()
    aid = "21486d872fcf"
    rows = c.get('/api/rootcanal/meta').get_json()["metas"]
    row = [m for m in rows if m["artifact_id"] == aid][0]
    st0 = row["run"] or {}
    print("BEFORE:", {k: st0.get(k) for k in ("status", "was", "step", "words")}, flush=True)
    r = c.post('/api/rootcanal/meta/%s/run' % aid).get_json()
    print("RUN ->", r["run"]["status"], "resumed:", r["run"].get("resumed"), flush=True)
    t0, last = time.time(), None
    while time.time() - t0 < limit:
        st = A._META_RUNS.get(aid) or {}
        line = (st.get("status"), st.get("step"), st.get("done"), st.get("of"),
                (st.get("item") or "")[:70], st.get("best"))
        if line != last:
            print("%6.1fs %s" % (time.time() - t0, line), flush=True)
            last = line
        if st.get("status") in ("done", "failed"):
            print("ENDED", st.get("status"), st.get("error"), flush=True)
            break
        time.sleep(0.5)
    print("CRASH at %.0fs (os._exit)" % (time.time() - t0), flush=True)
    os._exit(1)


if __name__ == "__main__":
    main()
