# -*- coding: utf-8 -*-
"""Which sessions of m3, m5, m13, m28, m34 the PTEN Baseline v2 pool holds."""
import os, sys, re
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
A = artifacts.Artifacts(LOGS, ST)
for aid in ('105b40acbbb0', '3561fc988afd'):
    rec = A.get(aid)
    pay = A.payload(aid, None) or {}
    labs = sorted({m.get('session_label') for m in pay.get('members') or []})
    want = [l for l in labs if re.search(r'PTEN m(3|5|13|28|34) ', l or '')]
    print(rec.get('nickname'), len(labs), 'members;', want)
