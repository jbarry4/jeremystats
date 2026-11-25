# -*- coding: utf-8 -*-
"""Build everything the Seahorse tab loads, in order.

    python tools/seahorse/build.py              all stages
    python tools/seahorse/build.py manifest     only the size list

Stages: volume (8 min, derives the laminae), nissl10 (streams the 2.2 GB
Allen 10 um Nissl once), meshes, survey (downloads ~650 registered
tracings once, finds the cells that touch), cells, rides, kb, crosscheck
(asks the Allen API; earlier answers are reused unless --fresh), manifest.
Downloads land in %LOCALAPPDATA%/Jarvis/seahorse_raw; outputs in
web/seahorse/. Needs: numpy scipy scikit-image pynrrd fast-simplification
pillow.
"""
import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import OUT, write_json  # noqa: E402


def manifest():
    files = {}
    for n in sorted(os.listdir(OUT)):
        if n.endswith(('.gz', '.json')) and n != 'manifest.json':
            files[n] = {'bytes': os.path.getsize(os.path.join(OUT, n))}
    write_json(os.path.join(OUT, 'manifest.json'), {'built': datetime.date.today().isoformat(), 'files': files}, compact=False)
    print('manifest:', len(files), 'files')


def main():
    stages = sys.argv[1:] or ['volume', 'nissl10', 'meshes', 'survey', 'cells', 'rides', 'kb', 'crosscheck', 'manifest']
    for s in stages:
        if s == 'manifest':
            manifest()
            continue
        print('==', s, flush=True)
        # volume re-ships after nissl10 so the 20 um copy carries the true stain
        extra = ['--ship'] if s == 'volume' and os.path.exists(os.path.join(OUT, 'fine10.shb.gz')) and '--full' not in sys.argv else []
        subprocess.check_call([sys.executable, '-I', os.path.join(HERE, s + '.py')] + extra)


if __name__ == '__main__':
    main()
