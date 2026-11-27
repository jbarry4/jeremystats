"""What the user has saved in the room for the new-round sets: splits and
bands, by set and recording."""
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import extraction as EX  # noqa: E402

pr = A.STORE.get_prefs() or {}
for key in (EX.SPLIT_KEY, EX.BAND_KEY):
    got = pr.get(key) or {}
    print(key, len(got))
    for k, v in sorted(got.items()):
        if "xm-500fa6c3c5" in k or "xm-f6c45faefb" in k:
            print("   ", k, json.dumps(v)[:200])
