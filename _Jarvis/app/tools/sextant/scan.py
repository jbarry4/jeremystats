"""Read every Sextant recording once with StrataScope's scan.

    python tools/sextant/scan.py            # all 17, skips what is current
    python tools/sextant/scan.py m60 m2     # just these mice

The scan is StrataScope's (backend/stratasteps.py): per channel and second
the band powers, theta coefficients and multiunit power, plus a 1250 Hz copy
of every channel. Sextant's evidence is computed from those. StrataScope
keeps only 3 GB of 1250 Hz copies; this run raises that for itself so all
17 stay until Sextant has read them.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, APP)

from backend import continuity, csc  # noqa: E402
from backend import stratasteps as st  # noqa: E402
from backend.sextant import cohort  # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def main(argv):
    st.configure(LOGS)
    st.LFP_KEEP_BYTES = 12 * 1024 ** 3
    recs = cohort.recordings(LOGS, only=set(argv) or None)
    log("recordings:", len(recs))
    for r in recs:
        gid, path = r["gid"], r["path"]
        if not path or not os.path.isdir(path):
            log(r["mouse"], gid, "NO LOCAL PATH", path)
            continue
        t0 = time.time()
        try:
            sess = csc.open_session(path, invert=True)
            if not sess.get("ok"):
                log(r["mouse"], gid, "open failed", sess.get("error"))
                continue
            nums = [int(c["number"]) for c in sess.get("channels") or []]
            order = [c for c in (r["channels"] or nums) if c in set(nums[:64])]
            order = order or nums[:64]
            stat = st.status(gid, sess, r["bad"])
            lfp_ok = os.path.exists(os.path.join(st._dir(gid), "lfp.npy"))
            if stat.get("scanned") and stat.get("current") and lfp_ok:
                log(r["mouse"], gid, "current, skipped")
                continue
            rep = continuity.check(path)
            if not rep or not rep.get("ok"):
                log(r["mouse"], gid, "could not segment:",
                    (rep or {}).get("error"))
                continue
            meta = st.scan(sess, rep, gid, workers=6, channels=order,
                           skip=r["bad"])
            log(r["mouse"], gid, "scanned %d bins, %d channels in %.0f s" % (
                meta.get("n_bins") or 0, len(meta.get("channels") or []),
                time.time() - t0))
        except Exception as exc:  # keep going; report at the end
            log(r["mouse"], gid, "FAILED:", repr(exc)[:300])
    log("done")


if __name__ == "__main__":
    main(sys.argv[1:])
