"""Compare New Data vs DATA AND ARCHIVE: renames by content hash, adds, removes; list the new analysis outputs."""
import os, hashlib, json, collections
BASE = r"C:\Users\Z390\Desktop\jeremystats\KCNT1 Active Avoidance"
OLD = os.path.join(BASE, "DATA AND ARCHIVE", "active_avoidance_data")
NEW = os.path.join(BASE, "New Data", "active_avoidance_data")


def scan(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith(".dat"):
                p = os.path.join(dp, f)
                h = hashlib.md5(open(p, "rb").read()).hexdigest()
                out[os.path.relpath(p, root)] = h
    return out


old, new = scan(OLD), scan(NEW)
by_hash_old = collections.defaultdict(list)
for p, h in old.items():
    by_hash_old[h].append(p)
by_hash_new = collections.defaultdict(list)
for p, h in new.items():
    by_hash_new[h].append(p)
renames, same, added, removed = [], 0, [], []
for h, ps in by_hash_new.items():
    if h not in by_hash_old:
        added += ps
        continue
    o = sorted(by_hash_old[h])
    n = sorted(ps)
    if o == n:
        same += len(n)
    else:
        renames.append((o, n))
for h, ps in by_hash_old.items():
    if h not in by_hash_new:
        removed += ps
print("old", len(old), "new", len(new), "unchanged", same)
print("RENAMED/MOVED:")
for o, n in sorted(renames):
    print("  ", o, "->", n)
print("ADDED (new content):", added)
print("REMOVED:", removed)
json.dump(dict(renames=renames, added=added, removed=removed), open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "newdata.json"), "w"), indent=1)
for dp, dn, fn in os.walk(os.path.join(NEW, "KCNT1_2026")):
    for f in fn:
        if not f.lower().endswith((".ps", ".png", ".dat")):
            p = os.path.join(dp, f)
            print("OUT", os.path.relpath(p, NEW), os.path.getsize(p), os.path.getmtime(p))
