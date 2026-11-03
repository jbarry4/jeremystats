"""check_joeexport_race.py -- tab 10's files, asked for several at once.

2026-10-30 12:16: four requests for tab 10's pictures in the same second,
and three failed. Every file request works the manifest out, and making it
writes -- a figure's Prism zip is made again through one fixed `.part` name
whenever its sources are newer -- so the four made the same zip together:
WinError 32 on the rename, and WinError 2 once the first had moved the
`.part` away. `joeexport.manifest` now makes them one at a time.

Ages the Prism zips (a cache, made again from tab 9's files) so each round
has to make them, then has THREADS threads work the manifest out at the
same moment, ROUNDS times. Writes nothing else.

    python tools/check_joeexport_race.py
"""
import os
import sys
import threading
import zipfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from backend import monolith as MO                     # noqa: E402

MO.configure(os.path.join(APP, "GUI_logs"))
from backend import joeexport as JX                    # noqa: E402

THREADS, ROUNDS = 8, 4
ok = bad = 0


def check(name, cond, detail=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    " + name)
    else:
        bad += 1
        print("  FAIL  " + name + ("\n        " + str(detail) if detail else ""))


man, paths = JX.manifest()
if not man.get("ok"):
    print("SKIP  tab 10 has nothing here: " + str(man.get("error")))
    sys.exit(0)
zips = sorted(p for n, p in paths.items() if n.endswith("_prism.zip"))
print("%d Prism zip(s) in tab 10's list" % len(zips))
check("there are Prism zips to make again", bool(zips))

errors = []
for _r in range(ROUNDS):
    for z in zips:
        os.utime(z, (1, 1))
    gate = threading.Barrier(THREADS)

    def ask():
        try:
            gate.wait()
            JX.manifest()
        except Exception as exc:                       # noqa: BLE001
            errors.append("%s: %s" % (type(exc).__name__, exc))

    ts = [threading.Thread(target=ask) for _ in range(THREADS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

check("%d x %d requests at once, and none failed" % (ROUNDS, THREADS),
      not errors, "; ".join(errors[:3]) + (" (+%d)" % (len(errors) - 3)
                                           if len(errors) > 3 else ""))
check("every zip was made again",
      all(os.path.getmtime(z) > 1 for z in zips))
check("and every one opens whole",
      all(zipfile.ZipFile(z).testzip() is None for z in zips))
check("no .part is left behind",
      not [z for z in zips if os.path.exists(z + ".part")])

print("%d ok, %d fail" % (ok, bad))
sys.exit(1 if bad else 0)
