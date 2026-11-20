# -*- coding: utf-8 -*-
"""Chicken Scratch, end to end. Everything lands in %LOCALAPPDATA%\\Jarvis\\
chickenscratch (never the repo: it is public, and some sources are the
Drive's Non-Public folders).

    python tools/chickenscratch/build.py            rebuild from what is here
    python tools/chickenscratch/build.py --fetch    re-read the Drive and this
                                                    machine first (slow)

Order: harvest_drive (Drive -> text), harvest_local (registry, mouse book,
SoftMouse, VOS, repo documents), bundles (reading lists + table digests),
structured (sheets with columns), semi (other trackers), handwritten
(pages read by eye, hw/*.json), merge (dossiers + disagreements), stories
(a draft per Dentate Spike sheet mouse).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(name):
    print("==", name, flush=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, os.path.join(HERE, name)], cwd=HERE, env=env)
    if r.returncode:
        sys.exit("%s failed" % name)


if __name__ == "__main__":
    steps = ["structured.py", "semi.py", "handwritten.py", "merge.py", "stories.py"]
    if "--fetch" in sys.argv:
        steps = ["harvest_drive.py", "harvest_local.py", "bundles.py"] + steps
    for s in steps:
        run(s)
