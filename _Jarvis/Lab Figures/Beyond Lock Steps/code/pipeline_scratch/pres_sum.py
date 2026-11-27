import json, os, collections
B = r"C:\Users\Z390\AppData\Local\Jarvis\er2\runs"
def lb(r):
    p = os.path.join(B, r, "leaderboard.json")
    return json.load(open(p)) if os.path.exists(p) else None

for r in ["r016"]:
    L = lb(r)
    if not L:
        print(r, "no leaderboard"); continue
    print("=====", r, len(L["rows"]), "rows")
    g = collections.defaultdict(list)
    for x in L["rows"]:
        g[x["target"]].append(x)
    for t, xs in g.items():
        xs.sort(key=lambda x: -(x["main"] or -9))
        n = sum(1 for x in xs if x["passes"])
        b = xs[0]
        nb = [x for x in xs if x.get("nuisance_baseline") is not None]
        print("  %-18s pass %2d/%3d best %.2f %s/%s top=%s nuis=%s" % (t, n, len(xs), b["main"] or 0, b["view"], b["model"], b["top_feature"], b.get("nuisance_baseline")))
        for x in [x for x in xs if x["passes"]][:6]:
            print("        %.2f %s %s %s" % (x["main"], x["view"], x["model"], x["top_feature"]))

for r in ["r008", "r012"]:
    L = lb(r)
    print("=====", r)
    for x in sorted(L["rows"], key=lambda x: -(x["main"] or 0)):
        print("  %.2f pooled=%s %s %s top=%s" % (x["main"] or 0, round(x["score"].get("pooled", 0) or 0, 2), x["view"], x["model"], x["top_feature"]))
    print(json.dumps(L.get("most_important"), indent=0)[:2500])

# types vs twins
for a, b in [("r010", "r011"), ("r014", "r015")]:
    A, T = lb(a), lb(b)
    print("=====", a, "vs twins", b)
    best = collections.defaultdict(lambda: -9); npass = collections.Counter()
    for X, tag in [(A, "type"), (T, "twin")]:
        for x in X["rows"]:
            v = x["view"]; base, _, sub = v.partition("@")
            k = (x["target"], sub[-1] if sub else "?", tag)
            best[k] = max(best[k], x["main"] or -9)
            npass[k] += bool(x["passes"])
    for t in sorted({k[0] for k in best}):
        for s in "123":
            print("  %-18s DS%s type best %.2f (%d pass)  twin best %.2f (%d pass)" % (t, s, best[(t, s, "type")], npass[(t, s, "type")], best[(t, s, "twin")], npass[(t, s, "twin")]))
    print("  errors:", str(A.get("errors"))[:400])
