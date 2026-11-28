"""Load Jarvis in-process on a VACC compute node, with each KCNT1 recording opened straight off /netfiles.

Jarvis on a desk finds a recording through the registry's `here` (the folders that machine can reach). On a compute
node none of the desk paths exist, so `_braces_session` is pointed at the cluster's mount of the same folder. Every
read below is still Jarvis's own (dspca.read, rootcanal.read, braces.screen); only where the files are is changed.

Nothing here syncs (Jarvis_CLOUD_SYNC is not set and this copy has no key) and nothing is written to netfiles.
"""
import os
import sys

APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402

logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402

NET = "/netfiles/bigdata_jbarry/Jeremy3/KCNT1/"
PATHS = {
    "sdcedca6715fb": NET + "Summer'26/KCNT1_m1619/KCNT1_m1619_s01_081826/2026-08-18_13-11-23",
    "s44851809ecd5": NET + "Spring'26/KCNT1_526/kcnt1_m526_s1_mar26/2026-03-26_14-35-57",
    "se0c7b6ba6d5a": NET + "Summer'26/KCNT1_m1609/KCNT1_m1609_s1_071526/2026-07-15_11-57-58",
    "s6d234609d2c2": NET + "Summer'26/KCNT1_m0576/KCNT1m576_s1_72326/2026-07-23_13-05-13",
    "s655a06b22296": NET + "Summer'26/KCNT1_m1603/KCNT1_m1603_s2_06-24-26/2026-06-24_14-38-31",
    "s9619387fd35c": NET + "Spring'26/KCNT1_hom306/KCNT1_hom306_s1_feb24/2026-02-24_17-46-28",
}

# Read-only copies on GPFS scratch (stage.sbatch): the X-ray reader seeks every channel per event, and over the NFS
# mount that re-read 115 GB for one 11 GB recording in an hour. Same files, so the same recording identity.
STAGED = "/gpfs2/scratch/sakhava1/kcnt1_prelim/rec/"
if os.environ.get("KCNT1_USE_NETFILES") != "1":
    PATHS = {g: STAGED + g for g in PATHS if os.path.isdir(STAGED + g)} or PATHS

_orig = A._braces_session


def _braces_session(rec):
    gid = rec.get("gid")
    path = PATHS.get(gid)
    if not path:
        return _orig(rec)
    sess, err = A._session_for(path, True)
    if err:
        raise ValueError("could not open %s: %s" % (path, (err or {}).get("error")))
    sess["gid"] = gid
    return sess, (A._session_by_gid(gid) or {})


A._braces_session = _braces_session
