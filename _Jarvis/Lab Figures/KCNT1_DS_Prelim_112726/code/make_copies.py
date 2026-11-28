"""Copy the PTEN pipeline code (Beyond Lock Steps/code) into this KCNT1 folder with its work-PC paths and PTEN room
replaced by settings read from the environment. The PTEN copy is never edited.

  JAPP   Jarvis app folder (on the VACC: /gpfs2/scratch/sakhava1/kcnt1_prelim/app)
  KBAT   the KCNT1 battery folder
  KROOM  Extraction Room id (dentate_spike_kcnt1)
  KV     the room version a deep script reads
  KSCR   where the deep pickles are written and read (the PTEN session scratch folder's role)
"""
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "Beyond Lock Steps", "code")
VACC = "/gpfs2/scratch/sakhava1/kcnt1_prelim"

APP_RE = re.compile(r'r"[cC]:\\Users\\Z390\\Desktop\\jeremystats\\_Jarvis\\app"')
BAT_RE = re.compile(r'r"[cC]:\\Users\\Z390\\Desktop\\DS_PTEN_figures_2026-11-16\\battery"')
SCR_RE = re.compile(r'r"C:\\Users\\Z390\\AppData\\Local\\Temp\\claude\\[0-9a-f]+\\[0-9a-f-]+\\scratchpad"')
RUNS_RE = re.compile(r'r"C:\\Users\\Z390\\AppData\\Local\\Jarvis\\er2\\runs"')
OUT_RE = re.compile(r'r"C:\\Users\\Z390\\Desktop\\jeremystats\\_Jarvis\\Lab Figures\\[^"]+"')

SUBS = [
    (APP_RE, 'os.environ.get("JAPP", "%s/app")' % VACC),
    (BAT_RE, 'os.environ.get("KBAT", "%s/battery")' % VACC),
    (SCR_RE, 'os.environ.get("KSCR", "%s/scr")' % VACC),
    (RUNS_RE, 'os.environ.get("KRUNS", "%s/er2runs")' % VACC),
    (OUT_RE, 'os.environ.get("KOUT", "%s/out")' % VACC),
    (re.compile(r'A\._er_rooms\(\)\["dentate_spike"\]'), 'A._er_rooms()[os.environ.get("KROOM", "dentate_spike_kcnt1")]'),
    (re.compile(r'"%s\?version=6" % room\["id"\]'), '("%s?version=" + os.environ.get("KV", "1")) % room["id"]'),
    (re.compile(r'"deep_(\w+)_v6\.pkl"'), r'"deep_\1_v%s.pkl" % os.environ.get("KV", "1")'),
    (re.compile(r'for V in \(6, 8\):'), 'for V in (int(os.environ.get("KV", "1")),):'),
    (re.compile(r' if V == 6 else None'), ''),
]


def copy_tree(src, dst, names=None):
    os.makedirs(dst, exist_ok=True)
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        for f in files:
            if names and f not in names:
                continue
            s = os.path.join(root, f)
            d = os.path.join(dst, rel, f)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if f.endswith(".py"):
                t = open(s, encoding="utf-8").read()
                for rx, rep in SUBS:
                    t = rx.sub(lambda m: rep, t) if "\\1" not in rep else rx.sub(rep, t)
                if "os.environ" in t and not re.search(r"^import os\b", t, re.M):
                    t = "import os\n" + t
                open(d, "w", encoding="utf-8").write(t)
            else:
                shutil.copy2(s, d)


copy_tree(os.path.join(SRC, "battery"), os.path.join(HERE, "battery"))
copy_tree(os.path.join(SRC, "menus"), os.path.join(HERE, "menus"))
copy_tree(os.path.join(SRC, "pipeline_scratch"), os.path.join(HERE, "deep"),
          names={"deep_extract.py", "deep_extra.py", "deep_pca2.py", "deep_opt.py", "deep_opt2.py", "deep_ds3.py"})
left = []
for root, _d, files in os.walk(HERE):
    for f in files:
        if f.endswith(".py") and f != "make_copies.py":
            for i, line in enumerate(open(os.path.join(root, f), encoding="utf-8"), 1):
                if "Z390" in line:
                    left.append("%s:%d: %s" % (os.path.relpath(os.path.join(root, f), HERE), i, line.strip()[:120]))
print("work-PC paths left:", len(left))
print("\n".join(left[:60]))
