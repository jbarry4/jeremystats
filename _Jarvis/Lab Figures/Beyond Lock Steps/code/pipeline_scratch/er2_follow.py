"""Follow one ER2 VACC run home: python er2_follow.py r006"""
import json
import sys
import time
import urllib.request

rid = sys.argv[1]
last = None
while True:
    time.sleep(240)
    try:
        req = urllib.request.Request("http://127.0.0.1:8733/api/er2/run/%s/refresh" % rid, data=b"{}",
                                     headers={"Content-Type": "application/json"}, method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=900).read().decode())
    except Exception as exc:                              # noqa: BLE001
        print(time.strftime("%H:%M"), "retry:", exc, flush=True)
        continue
    run = r.get("run") or {}
    line = "%s/%s answered" % (run.get("answered"), run.get("n"))
    if line != last:
        print(time.strftime("%H:%M"), rid, line, flush=True)
        last = line
    if run.get("n") and run.get("answered") == run.get("n"):
        print("ALL ANSWERED", rid, flush=True)
        break
