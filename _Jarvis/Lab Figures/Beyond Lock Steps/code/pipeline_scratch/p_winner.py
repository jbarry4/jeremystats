P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\measures.py"
s = open(P, encoding="utf-8").read()


def rep(a, b, n=1):
    global s
    assert s.count(a) >= 1, a[:90]
    s = s.replace(a, b, n)


rep('''OUTDIR = os.environ.get("BATTERY_OUT")''', '''# ONE CLASSIFIER (2026-11-18: "We had the winner. Keep those winners and vary
# everything else"): every type-specific measure uses each recording's winner
# (dsdata.Rec.winner, the quality check's FINAL OPTIMIZED SEPARATION), and the
# measures that compare classifiers are not made. BATTERY_ALL_CLASSIFIERS=1
# brings back run 3's behavior.
WINNER_ONLY = not os.environ.get("BATTERY_ALL_CLASSIFIERS")
CLFS = ["winner"] if WINNER_ONLY else None
OUTDIR = os.environ.get("BATTERY_OUT")''')
# masks
rep('''    conv = [c for c in dsdata.CONVENTIONAL if r.has(c)]
    best_nc = max(conv, key=lambda c: r.si(c)) if conv else None
    for clf in [c for c in dsdata.CLASSIFIERS if r.has(c)]:''', '''    conv = [c for c in dsdata.CONVENTIONAL if r.has(c)] if not WINNER_ONLY else []
    best_nc = max(conv, key=lambda c: r.si(c)) if conv else None
    for clf in ([c for c in dsdata.CLASSIFIERS if r.has(c)] if not WINNER_ONLY else []):''')
rep('''    for clf in dsdata.CLASSIFIERS:
        if not (r.has(clf) and r.eligible(clf)):
            continue
        t = r.types(clf)''', '''    for clf in (CLFS or dsdata.CLASSIFIERS):
        if not (r.has(clf) and r.eligible(clf)):
            continue
        t = r.types(clf)''')
rep('''            if clf == r.used:
                out[("used", k)] = m''', '''            if clf == r.used and not WINNER_ONLY:
                out[("used", k)] = m''')
rep('''    clfs = [c for c in dsdata.CLASSIFIERS] + ["used"]''', '''    clfs = CLFS or ([c for c in dsdata.CLASSIFIERS] + ["used"])''')
rep('''    for clf in dsdata.CLASSIFIERS:
        B.add("structure", "separation_index",''', '''    for clf in (CLFS or dsdata.CLASSIFIERS):
        B.add("structure", "separation_index",''')
# gate the over-classifier blocks
rep('''    # over classifiers
    conv = dsdata.CONVENTIONAL''', '''    if WINNER_ONLY:
        run_structure_rest(B, es, recs, Wz)
        return
    # over classifiers
    conv = dsdata.CONVENTIONAL''')
rep('''    # one cloud or two, on the PCA plane
    cloud = {''', '''    run_structure_rest(B, es, recs, Wz)


def run_structure_rest(B, es, recs, Wz):
    """The structure measures that do not depend on a classifier."""
    # one cloud or two, on the PCA plane
    cloud = {''')
rep('''    # stability on random halves
    mean_h, sd_h = {}, {}
    for r in recs:
        if not r.used:''', '''    # stability on random halves
    mean_h, sd_h = {}, {}
    for r in recs:
        if WINNER_ONLY or not r.used:''')
open(P, "w", encoding="utf-8").write(s)
print("ok")
