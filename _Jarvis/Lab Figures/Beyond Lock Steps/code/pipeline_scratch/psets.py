# -*- coding: utf-8 -*-
"""The hand-sorted / confirmed P-spike sets the workflow builder offers:
every version, what made it, aligned or not, by whom."""
import os, sys, json
APP = r'C:\Users\Z390\Desktop\jeremystats\_Jarvis\app'
sys.path.insert(0, APP)
os.chdir(APP)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from backend import store, eventbank, versions as versionsmod
LOGS = os.path.join(APP, 'GUI_logs')
ST = store.Store(LOGS, auto_stage=False)
B = eventbank.EventBank(LOGS, ST)
rows = []
for s in B.summaries():
    if s.get('type') != 'ied' or s.get('archived'):
        continue
    pipe = ((s.get('source') or {}).get('pipeline') or s.get('pipeline') or '')
    if pipe not in ('IED hand-sort (ETS)',) and 'hand-sorted' not in (s.get('name') or ''):
        continue
    rows.append(s)
for s in sorted(rows, key=lambda s: s.get('session_label') or ''):
    rec = B.get(s['id'])
    print('==', s.get('session_label'), '|', s.get('name'), '| id', s['id'], '| n', s.get('n'), '| pipe', (rec.get('source') or {}).get('pipeline'))
    named = versionsmod.label_rows(rec.get('versions') or [])
    for ver, nm in named:
        keep = {k: ver.get(k) for k in ('at', 'by', 'machine', 'note', 'tag', 'aligned', 'aligned_tool', 'retimed', 'n', 'parent', 'from') if ver.get(k) not in (None, '', [], {})}
        al = ver.get('aligned')
        if isinstance(al, dict):
            keep['aligned'] = {k: al.get(k) for k in ('tool', 'by', 'at', 'mode', 'how', 'auto', 'method', 'n_moved', 'shift_ms', 'channel') if al.get(k) is not None}
        print('   v' + str(nm), json.dumps(keep, default=str)[:600])
