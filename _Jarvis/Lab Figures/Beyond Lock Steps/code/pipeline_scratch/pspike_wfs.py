# -*- coding: utf-8 -*-
"""Which hand-sorted sets each P-spike workflow is drawn around, at which
version."""
import os, sys, json
APP = r'C:\Users\Z390\Desktop\jeremystats\_Jarvis\app'
sys.path.insert(0, APP)
os.chdir(APP)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from backend import store, artifacts
LOGS = os.path.join(APP, 'GUI_logs')
ST = store.Store(LOGS, auto_stage=False)
A = artifacts.Artifacts(LOGS, ST) if hasattr(artifacts, 'Artifacts') else None
if A is None:
    print([n for n in dir(artifacts) if not n.startswith('_')])
    raise SystemExit
for r in A.list(kind='rootcanal_workflow'):
    pay = A.payload(r['id'], None) or {}
    d = pay.get('definition') or {}
    if d.get('kind') != 'pspike':
        continue
    src = d.get('source') or {}
    print(r['id'], '|', r.get('nickname'), '| v', r.get('version'), '| folder', d.get('folder'), '| grace', d.get('grace'), '| shape', d.get('shape'))
    for e in src.get('entries') or []:
        print('    ', e.get('session_label'), e.get('entry_id'), 'version', e.get('version'), 'n', e.get('n'))
