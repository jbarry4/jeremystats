P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_room2_figs.py"
s = open(P, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


# class names capitalized everywhere they are drawn
rep('''def classes(t, ctx):
    d = ctx.data
    mice, y, task, scheme, cls = E.target(d, t)
    return mice, y, task, cls''', '''def classes(t, ctx):
    d = ctx.data
    mice, y, task, scheme, cls = E.target(d, t)
    if cls:
        cls = [c[0].upper() + c[1:] for c in cls]
    return mice, y, task, cls


def stars(p):
    """The significance sign (raw P, uncorrected)."""
    if p is None or not np.isfinite(p):
        return ""
    return "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "n.s."))


def pword(p):
    return "P = %s" % ("%.3f" % p if p >= 0.001 else "%.1e" % p)''')
rep('''    task = r["task"]
    cls = r["classes"]
    calls = per_mouse_calls(r)''', '''    from scipy import stats as st
    task = r["task"]
    cls = [c[0].upper() + c[1:] for c in r["classes"]] if r["classes"] else None
    calls = per_mouse_calls(r)''')
# held-out significance: the held-out calls tested against the truth (raw, uncorrected)
rep('''    txt = "%s\\n%s\\n%s %.2f" % (MODEL[r["model"]], VIEW[r["view"]], SCORE[task], r["score"]["main"])
    text_mm(fig, H, x, y - 6.5, txt, fontsize=T5, va="center", linespacing=1.25)
    return ax''', '''    if task == "binary":
        a_ = [m[0] for lab, (tr, m) in calls.items() if tr == 0]
        b_ = [m[0] for lab, (tr, m) in calls.items() if tr == 1]
        p = st.mannwhitneyu(b_, a_, alternative="greater").pvalue if a_ and b_ else np.nan
        test = "one-sided Mann-Whitney on held-out scores"
    elif task == "regression":
        tr = np.array([v[0] for v in calls.values()])
        pr = np.array([v[1][0] for v in calls.values()])
        p = st.spearmanr(tr, pr).pvalue
        test = "Spearman, held-out guess against truth"
    else:
        tr = np.array([v[0] for v in calls.values()]).astype(int)
        pc = np.array([np.argmax(v[1]) for v in calls.values()])
        k_ = int((tr == pc).sum())
        p = float(st.binomtest(k_, tr.size, 1.0 / 3, alternative="greater").pvalue)
        test = "binomial, calls right against 1 in 3"
    r["_p"], r["_test"] = p, test
    ax.text(0.98, 0.98, stars(p), transform=ax.transAxes, ha="right", va="top", fontsize=T7, fontweight="bold", color=INK)
    text_mm(fig, H, x, y - 7.2, MODEL[r["model"]], fontsize=T6, fontweight="bold")
    text_mm(fig, H, x, y - 4.4, "Inputs: " + VIEW[r["view"]], fontsize=T5, color=MUTE)
    sc = r["score"]["main"]
    text_mm(fig, H, x, y - 1.7, "%s %.2f (bar %.2f; nuisance only %.2f)" % (SCORE[task], sc, E.BAR[task], base), fontsize=T5)
    extra = ("%d%% of calls right" % round(100 * r["score"]["accuracy"])) if "accuracy" in r["score"] else ("mean error %.1f%%" % r["score"]["mae"])
    text_mm(fig, H, x, y + h + (9.5 if task == "multiclass" else 7.5), "%s · %s %s" % (extra, pword(p), stars(p)), fontsize=4.6, color=MUTE)
    return ax''')
# main figure layout
rep('''    H = 150.0
    fig = Hs.page(H)
    models = top_models(ctx, t)''', '''    H = 128.0
    fig = Hs.page(H)
    Hs.stamp(fig, "UNCORRECTED")
    models = top_models(ctx, t)''')
rep('''    letter(fig, H, 3, 10, "a")
    for k, r in enumerate(models):
        draw_model(fig, H, 16 + k * 58, 27, 38, 40, r, t, ctx, base)
    text_mm(fig, H, 16, 75, "Bar: %s %.2f.  Nuisance-only baseline (placement, year, event count; best model): %.2f." % (SCORE[task], E.BAR[task], base),
            fontsize=T5, color=MUTE)
    letter(fig, H, 3, 81, "b")
    ax = ax_mm(fig, H, 84, 85, 70, 52)''', '''    letter(fig, H, 3, 9, "a")
    for k, r in enumerate(models):
        draw_model(fig, H, 16 + k * 58, 19, 40, 36, r, t, ctx, base)
    letter(fig, H, 3, 70, "b")
    text_mm(fig, H, 9, 71.5, "The five parameters that carried these three models most", fontsize=T6, fontweight="bold")
    ax = ax_mm(fig, H, 78, 76, 72, 44)''')
# extended: stamp, mouse label above the where panel, stat marker, outliers, labels
rep('''    H = 236.0
    fig = Hs.page(H)
    mice, yv, task, cls = classes(t, ctx)
    text_mm(fig, H, 3, 4, "Extended Data Fig.''', '''    H = 236.0
    fig = Hs.page(H)
    Hs.stamp(fig, "UNCORRECTED")
    mice, yv, task, cls = classes(t, ctx)
    text_mm(fig, H, 3, 4, "Extended Data Fig.''')
rep('''                where_panel(fig, H, 22, y0 + 12, 22, 24, rec, base)
                text_mm(fig, H, 22, y0 + 39, "%s (%s)" % (rec.lab, ex[-1][2]), fontsize=4.2, color=ex[-1][1])''', '''                where_panel(fig, H, 24, y0 + 13, 24, 24, rec, base)
                text_mm(fig, H, 24, y0 + 11.2, "%s (%s)" % (rec.lab, ex[-1][2]), fontsize=4.4, color=ex[-1][1])''')
rep('''            dist_panel(fig, H, 80, y0 + 3, 36, 26, ctx, item, ex, unit)''', '''            dist_panel(fig, H, 80, y0 + 3, 36, 26, ctx, item, ex, unit, label_of(item).split(" (")[0])''')
rep('''def dist_panel(fig, H, x, y, w, h, ctx, item, examples, unit):''', '''def dist_panel(fig, H, x, y, w, h, ctx, item, examples, unit, short=""):''')
rep('''        if v.size:
            ax.axvline(np.median(v), color=col, lw=0.9, ls=(0, (2.5, 1.5)))
    ax.set_xlabel(unit or "value", fontsize=T5)''', '''    top = ax.get_ylim()[1]
    for k_, ((lab, col, word), v) in enumerate(zip(examples, allv)):
        if not v.size:
            continue
        # mark the statistic the models read, not always the median
        if stat in ("", "median") or stat.endswith("_median"):
            ax.axvline(np.median(v), color=col, lw=0.9, ls=(0, (2.5, 1.5)))
        elif stat in ("mean", "p10", "p90"):
            ax.axvline({"mean": np.mean(v), "p10": np.percentile(v, 10), "p90": np.percentile(v, 90)}[stat], color=col, lw=0.9, ls=(0, (2.5, 1.5)))
        elif stat == "iqr":
            q1, q3 = np.percentile(v, [25, 75])
            ax.plot([q1, q3], [top * (0.95 - 0.07 * k_)] * 2, color=col, lw=1.4)
        elif stat == "sd":
            m_, s_ = np.mean(v), np.std(v)
            ax.plot([max(lo, m_ - s_), min(hi, m_ + s_)], [top * (0.95 - 0.07 * k_)] * 2, color=col, lw=1.4)
    ax.set_ylim(0, top)
    ax.set_xlabel(short + (" (" + unit + ")" if unit else ""), fontsize=T5)''')
rep('''    if vals is None:
        ax.text(0.5, 0.5, "not available", transform=ax.transAxes, ha="center", fontsize=T5)
        return ax, None''', '''    if vals is None:
        ax.text(0.5, 0.5, "not available", transform=ax.transAxes, ha="center", fontsize=T5)
        return ax, None
    import make_leads as ML
    from scipy import stats as st
    lims = ML.outlier_limits(vals)
    shown = np.clip(vals, lims[0], lims[1])
    out = np.isfinite(vals) & ((vals < lims[2]) | (vals > lims[3]))''')
rep('''        ax.scatter(xs, vals, s=8, c=c_, edgecolors="white", linewidths=0.35, zorder=3)''', '''        ok = np.isfinite(vals)
        ax.scatter(xs[ok & ~out], shown[ok & ~out], s=8, c=[c_[i] for i in np.where(ok & ~out)[0]], edgecolors="white", linewidths=0.35, zorder=3)
        for i in np.where(out)[0]:
            ax.scatter([xs[i]], [shown[i]], marker="^" if vals[i] > lims[3] else "v", s=12, color=c_[i], zorder=3)
            ax.text(xs[i] + 0.8, shown[i], "%s %s" % (d.labs[i], ML.fmt(vals[i])), fontsize=3.8, va="center", color=MUTE)
        p = st.spearmanr(ko[ok], vals[ok]).pvalue
        ax.text(0.98, 0.98, "ρ %+.2f %s" % (st.spearmanr(ko[ok], vals[ok]).correlation, stars(p)), transform=ax.transAxes, ha="right", va="top", fontsize=4.8)''')
rep('''            sel = mice[yv == c]
            v = vals[sel]
            v = v[np.isfinite(v)]
            xs = c + rng.uniform(-0.15, 0.15, v.size)
            ax.scatter(xs, v, s=8, color=cols[c], edgecolors="white", linewidths=0.35, zorder=3)
            if v.size:
                ax.plot([c - 0.27, c + 0.27], [np.median(v)] * 2, color=INK, lw=0.9, zorder=4)''', '''            sel = np.array([i for i in mice[yv == c] if np.isfinite(vals[i])], int)
            xs = c + rng.uniform(-0.15, 0.15, sel.size)
            for xx, i in zip(xs, sel):
                if out[i]:
                    ax.scatter([xx], [shown[i]], marker="^" if vals[i] > lims[3] else "v", s=12, color=cols[c], zorder=3)
                    ax.text(xx + 0.12, shown[i], "%s %s" % (d.labs[i], ML.fmt(vals[i])), fontsize=3.8, va="center", color=MUTE)
                else:
                    ax.scatter([xx], [vals[i]], s=8, color=cols[c], edgecolors="white", linewidths=0.35, zorder=3)
            if sel.size:
                med = np.median(vals[sel])
                if lims[0] <= med <= lims[1]:
                    ax.plot([c - 0.27, c + 0.27], [med] * 2, color=INK, lw=0.9, zorder=4)''')
rep('''    ax.set_ylabel("Per mouse" + (" (" + unit + ")" if unit else ""), fontsize=T5)
    return ax, name''', '''    es, band, base, stat = parse(item)
    word = "share" if base.startswith("type_") else (STATW.get(stat, "median") if not stat.endswith("_median") else stat[:-7].upper() + " median")
    ax.set_ylabel(("Each mouse's " + word) + ("\\n(" + unit + ")" if unit else ""), fontsize=T5)
    span = lims[1] - lims[0]
    if task != "regression":
        # significance between the groups (raw P, uncorrected): Mann-Whitney for two, Kruskal-Wallis for three
        grp = [vals[np.array([i for i in mice[yv == c] if np.isfinite(vals[i])], int)] for c in range(len(cls))]
        if all(g.size >= 2 for g in grp):
            p = st.mannwhitneyu(grp[0], grp[1]).pvalue if len(grp) == 2 else st.kruskal(*grp).pvalue
            ytop = lims[1] + span * 0.05
            ax.plot([0, len(cls) - 1], [ytop, ytop], color=INK, lw=0.5)
            ax.text((len(cls) - 1) / 2.0, ytop + span * 0.01, stars(p), ha="center", va="bottom", fontsize=5.6 if stars(p) != "n.s." else 4.6)
            ax.set_ylim(lims[0] - span * 0.04, lims[1] + span * 0.16)
            return ax, name
    ax.set_ylim(lims[0] - span * 0.04, lims[1] + span * 0.06)
    return ax, name''')
s = s.replace('"CSD units"', '"µA/mm³"').replace('"CSD units × ms"', '"µA/mm³ × ms"')
# overview + legends stamp
rep('''    H = 180.0
    fig = Hs.page(H)
    text_mm(fig, H, 3, 4, "Fig. 1''', '''    H = 180.0
    fig = Hs.page(H)
    Hs.stamp(fig, "UNCORRECTED")
    text_mm(fig, H, 3, 4, "Fig. 1''')
rep('''    H = 236.0
    fig = Hs.page(H)
    task = models[0]["task"]''', '''    H = 236.0
    fig = Hs.page(H)
    Hs.stamp(fig, "UNCORRECTED")
    task = models[0]["task"]''')
open(P, "w", encoding="utf-8").write(s)
print("ok")
