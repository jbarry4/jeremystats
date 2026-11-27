import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_averaged2.py"
s = io.open(P, encoding="utf-8").read()


def rep(a, b, cnt=1):
    global s
    assert s.count(a) == cnt, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('''recs = [r for r in dsdata.load("v6") if r.ok]
TU = {r.lab: N.typed_u(r) for r in recs}''', '''import sys
from scipy import stats as st
NOCUT = len(sys.argv) > 1 and sys.argv[1] == "nocut"
TAG = "_no_cutoff" if NOCUT else ""
recs = [r for r in dsdata.load("v6") if r.ok]


def clf_of(r):
    """The classifier drawn: the best eligible one (each type 5%+ of events),
    or with nocut the best by index whatever the type sizes."""
    if not NOCUT:
        return r.used
    conv = [c for c in dsdata.CONVENTIONAL if r.has(c)]
    return max(conv, key=lambda c: r.si(c)) if conv else None


TU = {r.lab: N.typed_u(r, clf_of(r), min_n=1 if NOCUT else 5) for r in recs}''')
rep('''"%s  ·  index %.2f" % (r.lab, r.si(r.used))''', '''"%s  ·  index %.2f" % (r.lab, r.si(clf_of(r)))''')
rep('''"%s; DS1 %d, DS2 %d" % (clf_name(r.used), t["n"][1], t["n"][2])''', '''"%s; DS1 %d, DS2 %d" % (clf_name(clf_of(r)), t["n"][1], t["n"][2])''')
rep('''"Averaged_DS1_DS2_%s.png" % fname''', '''"Averaged_DS1_DS2%s_%s.png" % (TAG, fname)''')
rep('''"Averaged_DS1_DS2_comparison.png"''', '''"Averaged_DS1_DS2%s_comparison.png" % TAG''')
rep('''"Averaged_DS1_DS2.pdf"''', '''"Averaged_DS1_DS2%s.pdf" % TAG''')
rep('''"cluster_tests_ds1_ds2.json"''', '''"cluster_tests_ds1_ds2%s.json" % TAG''')
rep('''def comparison_page(pdf, groups):''', '''def sink_pos(prof, src_u, blade):
    """Centroid (on the depth axis u) of a profile's deepest sink lobe on
    the far side of the cell-layer source of one blade."""
    if prof is None:
        return np.nan
    far = (U < src_u[0]) if blade == "upper" else (U > src_u[-1])
    y = np.where(far & np.isfinite(prof), np.maximum(-prof, 0.0), 0.0)
    if y.max() <= 0:
        return np.nan
    return N._lobe_centroid(y, U, int(np.argmax(y)))


def apart(r):
    """How far apart DS1's and DS2's sinks sit, per blade, outward positive
    (DS1 farther from the cell layer), in u units and in um."""
    t = TU[r.lab]
    out = []
    for blade, sg in (("upper", -1), ("lower", 1)):
        d = sg * (sink_pos(t[1], t["src_u"], blade) - sink_pos(t[2], t["src_u"], blade))
        out.append(d)
    out = np.array(out)
    return out, out * r.landmarks["blade_um"]


def apart_page(pdf, groups):
    """The user's question: in the overlay, IED− DS1 sits farther from DS2
    than in control and IED+. Measured per recording."""
    H = 132.0
    fig = Hs.page(H)
    Hs.stamp(fig)
    text_mm(fig, H, 4, 5, "How far apart DS1's and DS2's sinks sit (DS3 removed)%s" % (", no minimum type size" if NOCUT else ""), fontsize=9, fontweight="bold")
    text_mm(fig, H, 4, 10.5, "Per recording and blade: where DS1's sink is (center of its deepest lobe on the far side of the cell layer) minus where DS2's is, on the normalized depth; "
            "positive = DS1 farther out.", fontsize=FS_S, color=MUTE)
    res = {}
    for j, (unit, k) in enumerate((("normalized depth (blade-to-blade = 1)", 0), ("µm", 1))):
        ax = ax_mm(fig, H, 18 + j * 88, 22, 62, 52)
        rng = np.random.default_rng(2)
        xt = []
        for gi, g in enumerate(("CTL", "IED-", "IED+")):
            for bi, blade in enumerate(("upper", "lower")):
                xx = gi * 2.6 + bi
                xt.append((xx, "%s\\n%s" % ({"CTL": "control", "IED-": "IED−", "IED+": "IED+"}[g], blade)))
                v = np.array([apart(r)[k][bi] for r in groups[g]])
                lb = [r.lab for r in groups[g]]
                ok = np.isfinite(v)
                xs = xx + rng.uniform(-0.2, 0.2, ok.sum())
                ax.scatter(xs, v[ok], s=16, color=[Hs.col_of(r) for r, o in zip(groups[g], ok) if o], edgecolor="white", linewidth=0.4, zorder=3)
                for x_, y_, l_ in zip(xs, v[ok], [l for l, o in zip(lb, ok) if o]):
                    ax.annotate(l_, (x_, y_), xytext=(3, 0), textcoords="offset points", fontsize=3.8, color=MUTE, va="center")
                if ok.any():
                    ax.plot([xx - 0.3, xx + 0.3], [np.median(v[ok])] * 2, color=INK, lw=1.0)
        ax.axhline(0, color=HAIR, lw=0.6)
        ax.set_xticks([x for x, _ in xt])
        ax.set_xticklabels([l for _, l in xt], fontsize=4.6)
        ax.set_ylabel("DS1 sink minus DS2 sink, outward (%s)" % unit, fontsize=FS_S)
        ax.tick_params(labelsize=4.8)
    # tests on the mean of the two blades, in um
    y = 86
    text_mm(fig, H, 4, y, "Mean of the two blades (µm), raw P (UNCORRECTED); Mann–Whitney, exact", fontsize=FS, fontweight="bold")
    vals = {g: np.array([np.nanmean(apart(r)[1]) for r in groups[g]]) for g in ("CTL", "IED-", "IED+", "PTEN")}
    for i, g in enumerate(("CTL", "IED-", "IED+")):
        v = vals[g][np.isfinite(vals[g])]
        text_mm(fig, H, 6, y + 4.5 + 3.4 * i, "%s: median %.0f µm (range %.0f to %.0f, n = %d)" % (Hs.GROUP_NAME[g], np.median(v), v.min(), v.max(), v.size), fontsize=FS_S)
    yy = y + 4.5 + 3.4 * 3 + 1.5
    for i, (a, b) in enumerate((("IED-", "CTL"), ("IED-", "IED+"), ("IED+", "CTL"), ("PTEN", "CTL"))):
        va, vb = vals[a][np.isfinite(vals[a])], vals[b][np.isfinite(vals[b])]
        p = st.mannwhitneyu(va, vb, alternative="two-sided", method="exact").pvalue if va.size and vb.size else np.nan
        res["%s_vs_%s" % (a, b)] = {"p": float(p), "median_a": float(np.median(va)), "median_b": float(np.median(vb))}
        text_mm(fig, H, 6, yy + 3.4 * i, "%s against %s: %.0f against %.0f µm, P = %.3f" % (Hs.GROUP_NAME[a], Hs.GROUP_NAME[b], np.median(va), np.median(vb), p),
                fontsize=FS_S, color=INK if p < 0.05 else MUTE)
    notes = ["DS1 and DS2: each recording's %s, names checked against the anatomy, DS3 events taken out. A type with %s is left out." % (
        "best classifier by index with no minimum type size" if NOCUT else "best eligible classifier (each type 5% of events or more)",
        "no events" if NOCUT else "fewer than 5 events"),
        "µm: the normalized distance times the recording's distance between its two blade sinks. Groups: control m2, m21, m22, m26, m59, m60, m61; IED− m8, m33, m1, m7; IED+ m13, m28, m3, m5, m34."]
    for i, s_ in enumerate(notes):
        text_mm(fig, H, 4, H - 9 + 3.2 * i, s_, fontsize=FS_S - 0.4, color=MUTE)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Averaged_DS1_DS2%s_apart.png" % TAG), dpi=200)
    plt.close(fig)
    return res


def comparison_page(pdf, groups):''')
rep('''        res = comparison_page(pdf, groups)''', '''        res = comparison_page(pdf, groups)
        res["apart"] = apart_page(pdf, groups)''')
rep('''    for k, v in res.items():
        print(k, "%.3f" % v["p"], v["where"])''', '''    for k, v in res.items():
        print(k, v)''')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
