"""What each Halo recording's .ncs headers say about the reference. Read only."""
import os, sys, json, warnings, glob
warnings.filterwarnings("ignore")
APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
os.chdir(APP); sys.path.insert(0, APP)
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend.app import app
from backend import app as A

c = app.test_client()
room = A._er_rooms()[os.environ.get("KROOM", "dentate_spike_kcnt1")]
j = c.get(("/api/extraction/%s?version=" + os.environ.get("KV", "1")) % room["id"]).get_json()
out = {}
for r in j["payload"]["recordings"]:
    lab = r["session_label"].split()[1]
    rec = A.DSPCA.get(r["gid"], r["read"])
    ent = A._dspca_entry(rec["entry_id"])
    sess, _ = A._braces_session(ent)
    if lab == "m2":
        print({k: (v if not isinstance(v, (list, dict)) else type(v).__name__) for k, v in sess.items()})
    chans = A._braces_channels(sess)
    info = {}
    for ch in chans[:64]:
        path = ch.get("path") or ch.get("file")
        if not path:
            continue
        try:
            with open(path, "rb") as f:
                h = f.read(16384).decode("latin-1", "replace")
        except Exception as e:
            info[ch["number"]] = "ERR %s" % e
            continue
        keep = [ln.strip() for ln in h.splitlines() if any(k in ln for k in ("Reference", "InputInverted", "DSPLowCut", "DspLowCut", "AcqEnt", "InputRange", "DSPHighCut", "DspHighCut"))]
        info[ch["number"]] = keep
    out[lab] = info
    first = next(iter(info.values()), None)
    refs = sorted({" | ".join(v) for v in info.values() if isinstance(v, list)})
    print(lab, "channels", len(info), "distinct header sets:", len(refs))
    for x in refs[:4]:
        print("    ", x[:400])
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref_headers.json"), "w"), indent=1, default=str)
