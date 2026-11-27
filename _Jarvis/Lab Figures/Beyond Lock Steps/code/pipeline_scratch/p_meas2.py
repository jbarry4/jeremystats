import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\measures.py"
s = io.open(P, encoding="utf-8").read()


def rep(a, b, cnt=1):
    global s
    assert s.count(a) == cnt, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('SETS = ("v6", "v8")', 'SETS = ("v6", "v7", "v8")      # Halo; 10% grace (border around the CTL pool); 10% grace without P-spikes')
rep('''    out = {}
    for clf in dsdata.CLASSIFIERS:
        if not (r.has(clf) and r.eligible(clf)):
            continue
        t = r.types(clf)''', '''    out = {}
    # 2026-11-17: no minimum type size. Every classifier, eligible or not,
    # and the best one by index with no 5% rule ("best_nocut").
    conv = [c for c in dsdata.CONVENTIONAL if r.has(c)]
    best_nc = max(conv, key=lambda c: r.si(c)) if conv else None
    for clf in [c for c in dsdata.CLASSIFIERS if r.has(c)]:
        t = r.types(clf)
        m3 = r.ds3(clf)
        nc = {"ds1n": t == 1, "ds2n": t == 2}
        if m3 is not None:
            nc["ds1nx"], nc["ds2nx"] = (t == 1) & ~m3, (t == 2) & ~m3
        for k, m in nc.items():
            out[(clf, k)] = m
            if clf == best_nc:
                out[("best_nocut", k)] = m
    for clf in dsdata.CLASSIFIERS:
        if not (r.has(clf) and r.eligible(clf)):
            continue
        t = r.types(clf)''')
rep('''def stat_of(x, how):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size < MIN_TYPE:
        return np.nan''', '''def stat_of(x, how, min_n=MIN_TYPE):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size < max(min_n, 2 if how in ("cv", "sd", "mad", "skew", "p90p10") else 1):
        return np.nan''')
rep('''            for r in recs:
                m = masks[r.lab].get((clf, var))
                if m is not None and m.sum() >= MIN_TYPE:
                    vals[r.lab] = stat_of(feats[r.lab][name][m], how)''', '''            mn = 1 if var in NOCUT else MIN_TYPE
            for r in recs:
                m = masks[r.lab].get((clf, var))
                if m is not None and m.sum() >= mn:
                    vals[r.lab] = stat_of(feats[r.lab][name][m], how, mn)''')
rep('''        for v1, v2, tag, extra in (("ds1", "ds2", "ds1_over_ds2", ""), ("ds1x", "ds2x", "ds1x_over_ds2x", " (DS3 events taken out)")):''',
    '''        for v1, v2, tag, extra in (("ds1", "ds2", "ds1_over_ds2", ""), ("ds1x", "ds2x", "ds1x_over_ds2x", " (DS3 events taken out)"),
                                   ("ds1n", "ds2n", "ds1n_over_ds2n", " (no minimum type size)")):''')
rep('''MIN_TYPE = 5
''', '''MIN_TYPE = 5
NOCUT = ("ds1n", "ds2n", "ds1nx", "ds2nx")     # variants with no minimum type size (2026-11-17)
FILTER_FEATS = ("sink_amp", "sink_upper", "sink_lower", "blade_balance", "source_amp", "source_over_sink", "net_between", "cen_um",
                "sink_width_um", "sink_fwhm", "source_fwhm", "lat_source_minus_sink")
''')
rep('''# -------------------------------------------------------------------- main
def main(which):''', '''# ------------------------------------------------------------------ filter
def match(ta, tb, tol=0.005):
    """For each time in ta: is there a time in tb within tol seconds?"""
    tb = np.sort(np.asarray(tb, float))
    j = np.clip(np.searchsorted(tb, ta), 1, max(tb.size - 1, 1))
    if tb.size == 0:
        return np.zeros(len(ta), bool)
    d = np.minimum(np.abs(ta - tb[j - 1]), np.abs(ta - tb[np.minimum(j, tb.size - 1)]))
    return d <= tol


def run_filter(B):
    """What the stricter event filters remove, per mouse (2026-11-17).
    Halo set (v6) = the loosest border; 10% grace (v7) = a border drawn
    around the control pool, 10% grace; No P-spikes (v8) = v7 less the
    events inside the P-spike border. Events are matched by time (5 ms)."""
    R = {es: {r.lab: r for r in dsdata.load(es) if r.ok} for es in SETS}
    labs = sorted(R["v6"])
    kept, extra, ps, drop_n = {}, {}, {}, {}
    part = {}
    for lab in labs:
        a, b, c = R["v6"][lab], R["v7"].get(lab), R["v8"].get(lab)
        if b is None or a.times_s is None or b.times_s is None:
            continue
        ink = match(a.times_s, b.times_s)
        kept[lab] = float(ink.mean())
        extra[lab] = float((~match(b.times_s, a.times_s)).mean())
        if c is not None and c.times_s is not None:
            ps[lab] = float((~match(b.times_s, c.times_s)).mean())
        drop_n[lab] = float((~ink).sum())
        part[lab] = ink
    B.add("filter", "halo_kept_by_grace_share", kept, "Share of the Halo set's events that the 10% grace border keeps", "share", "v6", "", "filter")
    B.add("filter", "grace_not_in_halo_share", extra, "Share of the 10% grace set's events that are not in the Halo set", "share", "v6", "", "filter")
    B.add("filter", "pspike_removed_share", ps, "Share of the 10% grace set's events removed as P-spikes (No P-spikes set)", "share", "v6", "", "filter")
    B.add("filter", "halo_dropped_count", drop_n, "Number of Halo events outside the 10% grace border", "events", "v6", "", "filter")
    feats = {lab: event_features(R["v6"][lab]) for lab in part}
    for f in FILTER_FEATS:
        dm, km, dd = {}, {}, {}
        for lab, ink in part.items():
            x = feats[lab][f]
            if (~ink).sum() >= MIN_TYPE and ink.sum() >= MIN_TYPE:
                a_, b_ = stat_of(x[~ink], "median"), stat_of(x[ink], "median")
                dm[lab], km[lab], dd[lab] = a_, b_, a_ - b_
        desc = EVENT_FEATURES[f][1]
        B.add("filter", "%s_dropped_median" % f, dm, "%s; median over the Halo events the 10%% grace border drops" % desc, EVENT_FEATURES[f][2], "v6", "", "dropped")
        B.add("filter", "%s_kept_median" % f, km, "%s; median over the Halo events the 10%% grace border keeps" % desc, EVENT_FEATURES[f][2], "v6", "", "kept")
        B.add("filter", "%s_dropped_minus_kept" % f, dd, "%s; dropped minus kept (median of each)" % desc, EVENT_FEATURES[f][2], "v6", "", "dropped_minus_kept")
    # which types the filter drops, under the recording's best classifier
    for nm, fn in (("ds1", lambda r, clf: r.types(clf) == 1), ("ds2", lambda r, clf: r.types(clf) == 2),
                   ("ds3", lambda r, clf: r.ds3(clf) if r.ds3(clf) is not None else None)):
        d_, k_, dd = {}, {}, {}
        for lab, ink in part.items():
            r = R["v6"][lab]
            if not r.used:
                continue
            m = fn(r, r.used)
            if m is None or (~ink).sum() < MIN_TYPE:
                continue
            d_[lab], k_[lab] = float(m[~ink].mean()), float(m[ink].mean())
            dd[lab] = d_[lab] - k_[lab]
        B.add("filter", "%s_share_dropped" % nm, d_, "Share of %s among the Halo events the 10%% grace border drops (best classifier)" % nm.upper(), "share", "v6", "used", "dropped")
        B.add("filter", "%s_share_dropped_minus_kept" % nm, dd, "Share of %s among dropped minus among kept Halo events (best classifier)" % nm.upper(), "share", "v6", "used", "dropped_minus_kept")


# -------------------------------------------------------------------- main
def main(which):''')
rep('''    for es in SETS:
        recs = [r for r in dsdata.load(es) if r.ok]''', '''    if "filter" in which:
        run_filter(BATS["filter"])
        BATS["filter"].save()
        print("filter measures %d, tests %d" % BATS["filter"].count(), flush=True)
    which = [f for f in which if f != "filter"]
    for es in SETS:
        recs = [r for r in dsdata.load(es) if r.ok]''')
rep('''    fams = [a for a in sys.argv[1:]] or ["timing", "waveform", "laminar", "structure"]''', '''    fams = [a for a in sys.argv[1:]] or ["filter", "timing", "waveform", "laminar", "structure"]''')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
