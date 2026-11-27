"""Archive every Root Canal pool, workflow and border outside the current
chain, the way the UI does (shared prefs merged per id; a workflow's bank
entries archived with it). Through the running Jarvis. Dry run unless --apply."""
import datetime
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8733"
APPLY = "--apply" in sys.argv
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
WHO = "Shahriar Tafti"

KEEP_POOLS = {"3561fc988afd", "105b40acbbb0", "07cdcb084c86"}
KEEP_WF = {"4a29af93e601", "6fa7fef7b7a3", "a7eee6a6ca9f", "178daabb125c", "4e5ce690d4b1"}


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


prefs = call("/api/prefs")
prefs = prefs.get("prefs") or prefs
arch = {k: dict(prefs.get(k) or {}) for k in ("rootcanal_pool_archive", "rootcanal_workflow_archive", "rootcanal_border_archive")}

pools = call("/api/rootcanal/pools").get("pools") or []
wfs = call("/api/rootcanal/workflows")["workflows"]
borders = call("/api/rootcanal/borders").get("borders") or []

keep_borders = set()
bank_ids = set()
for w in wfs:
    d = call("/api/rootcanal/workflow/" + w["artifact_id"])
    refs = set()
    for ln in d.get("lines") or []:
        if (ln.get("border_ref") or {}).get("artifact_id"):
            refs.add(ln["border_ref"]["artifact_id"])
        if (ln.get("bank") or {}).get("entry_id") and w["artifact_id"] not in KEEP_WF:
            bank_ids.add(ln["bank"]["entry_id"])
    if (w.get("border_ref") or {}).get("artifact_id"):
        refs.add(w["border_ref"]["artifact_id"])
    if (w.get("bank") or {}).get("entry_id") and w["artifact_id"] not in KEEP_WF:
        bank_ids.add(w["bank"]["entry_id"])
    if w["artifact_id"] in KEEP_WF:
        keep_borders |= refs

merge = {"rootcanal_pool_archive": {}, "rootcanal_workflow_archive": {}, "rootcanal_border_archive": {}}
for p in pools:
    i = p.get("artifact_id") or p.get("id")
    if i not in KEEP_POOLS and i not in arch["rootcanal_pool_archive"]:
        merge["rootcanal_pool_archive"][i] = {"at": NOW, "by": WHO}
for w in wfs:
    i = w["artifact_id"]
    if i not in KEEP_WF and i not in arch["rootcanal_workflow_archive"]:
        merge["rootcanal_workflow_archive"][i] = {"at": NOW}
for b in borders:
    i = b.get("artifact_id") or b.get("id")
    if i not in keep_borders and i not in arch["rootcanal_border_archive"]:
        merge["rootcanal_border_archive"][i] = {"at": NOW}

# Anything kept that is currently archived: put it back on show.
for i in KEEP_POOLS:
    if i in arch["rootcanal_pool_archive"]:
        merge["rootcanal_pool_archive"][i] = None
for i in KEEP_WF:
    if i in arch["rootcanal_workflow_archive"]:
        merge["rootcanal_workflow_archive"][i] = None
for i in keep_borders:
    if i in arch["rootcanal_border_archive"]:
        merge["rootcanal_border_archive"][i] = None

print("kept borders:", sorted(keep_borders))
for k, m in merge.items():
    print(k, "to archive:", len([v for v in m.values() if v]), "| put back:", [i for i, v in m.items() if v is None])
print("bank entries made by archived workflows:", sorted(bank_ids))
if APPLY:
    r = call("/api/prefs", {"merge": merge})
    print("prefs:", r.get("ok"), r.get("error"))
    for b in sorted(bank_ids):
        r = call("/api/bank/%s/archive" % b, {"archived": True})
        print("bank", b, r.get("ok"), r.get("changed"), r.get("error"))
    p2 = call("/api/prefs")
    p2 = p2.get("prefs") or p2
    shown_p = [p.get("nickname") for p in pools if (p.get("artifact_id") or p.get("id")) not in (p2.get("rootcanal_pool_archive") or {})]
    shown_w = [w.get("nickname") for w in wfs if w["artifact_id"] not in (p2.get("rootcanal_workflow_archive") or {})]
    shown_b = [b.get("nickname") or b.get("name") for b in borders
               if (b.get("artifact_id") or b.get("id")) not in (p2.get("rootcanal_border_archive") or {})]
    print("ON SHOW pools:", shown_p)
    print("ON SHOW workflows:", shown_w)
    print("ON SHOW borders:", shown_b)
