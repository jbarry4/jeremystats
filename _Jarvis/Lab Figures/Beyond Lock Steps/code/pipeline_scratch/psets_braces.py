# -*- coding: utf-8 -*-
"""Every Eye/Braces alignment made of the P-spike sets: from which version,
with what settings, reviewed or not, and each row's call."""
import os, sys, json
APP = r'C:\Users\Z390\Desktop\jeremystats\_Jarvis\app'
sys.path.insert(0, APP)
os.chdir(APP)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from backend import store, bracesset as brsetmod
LOGS = os.path.join(APP, 'GUI_logs')
ST = store.Store(LOGS, auto_stage=False)
BR = brsetmod.BracesSets(LOGS, ST)
IDS = {'754a4ab49e03': 'm3 s2', '04b094b59329': 'm3 s7', '51c1d1150100': 'm5 s2',
       'f607183a53d3': 'm5 s7', '964aac87949e': 'm13 s2', 'a2d567582ca0': 'm13 s17',
       '15de830c8b35': 'm28 s2', 'b03a7ae51547': 'm28 s7', '2bcb129a3db5': 'm34 s5',
       'b5a7ed0848ff': 'm34 s8'}
for rec in BR.all():
    if rec.get('entry_id') not in IDS:
        continue
    p = rec.get('params') or {}
    calls = rec.get('calls') or {}
    rows = rec.get('rows') or []
    print(IDS[rec['entry_id']], '| set', rec.get('set_id'), '| from', rec.get('from_version'),
          '| created', (rec.get('created') or {}).get('at') if isinstance(rec.get('created'), dict) else rec.get('created'),
          '| committed', json.dumps(rec.get('committed'), default=str)[:160])
    print('   params', json.dumps({k: p.get(k) for k in ('measure', 'window_ms', 'estimator', 'tool', 'band_kind', 'line_hz', 'smooth_ms', 'depth_band', 'channels', 'n_channels') if p.get(k) is not None}, default=str)[:300])
    print('   summary', json.dumps(rec.get('summary'), default=str)[:300])
    print('   rows', len(rows), '| calls', len(calls), json.dumps(calls, default=str)[:300])
    if rows:
        print('   row0', json.dumps(rows[0], default=str)[:400])
