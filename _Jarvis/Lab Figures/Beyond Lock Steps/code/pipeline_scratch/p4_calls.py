"""What the room itself says each old set's calls are (own keys plus any older
room|gid calls that belong to it), against what p4 copy would carry. Read only."""
import json
import urllib.request

BASE = "http://127.0.0.1:8733"


def call(path):
    with urllib.request.urlopen(BASE + path, timeout=300) as r:
        return json.loads(r.read().decode())


ex = call("/api/extraction")
print([k for k in ex])
rooms = ex.get("rooms")
print(json.dumps(rooms)[:1200])
prefs = call("/api/prefs")
prefs = prefs.get("prefs") or prefs
aid = None
for r in (rooms if isinstance(rooms, list) else (rooms or {}).values()):
    if isinstance(r, dict) and (r.get("room") == "dentate_spike" or r.get("id") == "dentate_spike"):
        aid = r.get("artifact_id") or (r.get("artifact") or {}).get("id")
print("room artifact", aid)
for old, ver in (("xm-f6c45faefb", 6), ("xm-1d6cfcdd3d", 8)):
    d = call("/api/extraction/%s?version=%d" % (aid, ver))
    own = {k: sum(1 for kk in (prefs.get(k) or {}) if str(kk).startswith("dentate_spike|%s|" % old))
           for k in ("extraction_band", "extraction_sep", "extraction_split", "extraction_flip")}
    print(old, "v%d" % ver, "| folder", d["payload"]["source"]["folder"],
          "| room says: seps", len(d.get("seps") or {}), "flips", len(d.get("flips") or {}),
          "splits", len(d.get("splits") or {}), "mode", d.get("mode"), "| own keys", own)
