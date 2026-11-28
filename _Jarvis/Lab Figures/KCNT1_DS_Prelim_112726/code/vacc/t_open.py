"""Smoke test on a compute node: Jarvis imports, each recording opens, probe and bad channels resolve."""
import time
t0 = time.time()
import vaccpatch as V  # noqa: E402
A = V.A
print("import", round(time.time() - t0, 1), "s", flush=True)
for eid in ["ac407abaa569", "22749a284641", "aa1d581d5f7e", "ef5031882809", "9a12a5c1afaa", "a1eb8aa0f5d1"]:
    rec = A.BANK.get(eid)
    sess, row = A._braces_session(rec)
    chans = A._braces_channels(sess)
    p = A._dspca_params({}, sess)
    print(eid, rec.get("session_label"), "n_ev", len(rec.get("events") or []), "chans", len(chans),
          "bad", [c["number"] for c in chans if c.get("bad")], "probe", p.probe, "spacing", p.spacing,
          "fs", sess.get("fs"), flush=True)
