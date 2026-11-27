"""Why each contact is marked bad on each recording of the room's v4, and
the probe/spacing it was read with."""
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402

room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], 4)
for rec in pay["recordings"]:
    got = A._dspca_load(rec["gid"], rec["read"])
    print(rec["session_label"][:24], got.get("probe"), got.get("spacing_um"),
          {int(k): (v[1] if isinstance(v, (list, tuple)) else v) for k, v in (got.get("bad") or {}).items()})
