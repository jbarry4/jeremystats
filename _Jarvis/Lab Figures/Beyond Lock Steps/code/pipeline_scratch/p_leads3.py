import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_leads.py"
s = io.open(P, encoding="utf-8").read()
i0 = s.index("def panel_result(fig, H, x, y, L, P):")
i1 = s.index("def numbers(fig, H, x, y, L, P):")
NEW = '''def outlier_limits(v):
    """y limits that keep the bulk readable: anything beyond 3 IQR past the
    quartiles is drawn at the edge as an arrow with its value."""
    v = v[np.isfinite(v)]
    q1, q3 = np.percentile(v, [25, 75])
    iqr = max(q3 - q1, 1e-12)
    lo_f, hi_f = q1 - 3 * iqr, q3 + 3 * iqr
    inl = v[(v >= lo_f) & (v <= hi_f)]
    a, b = inl.min(), inl.max()
    pad = 0.12 * (b - a if b > a else abs(b) + 1e-9)
    out_hi, out_lo = (v > hi_f).any(), (v < lo_f).any()
    return a - pad * (2.2 if out_lo else 1), b + pad * (2.2 if out_hi else 1), lo_f, hi_f


def draw_points(ax, xs, vals, cols, labs, lims, annotate=True):
    lo, hi, lo_f, hi_f = lims
    for xx, v, c, lb in zip(xs, vals, cols, labs):
        if not np.isfinite(v):
            continue
        if v > hi_f or v < lo_f:
            yv = hi - (hi - lo) * 0.035 if v > hi_f else lo + (hi - lo) * 0.035
            ax.scatter([xx], [yv], s=26, marker="^" if v > hi_f else "v", color=c, edgecolor="white", linewidth=0.4, zorder=5, clip_on=False)
            ax.annotate("%s: %s off scale" % (lb, fmt(v)), (xx, yv), xytext=(4, 0), textcoords="offset points", fontsize=4.2, va="center",
                        color=INK, fontweight="bold")
        else:
            ax.scatter([xx], [v], s=16, color=c, edgecolor="white", linewidth=0.4, zorder=3)
            if annotate:
                ax.annotate(lb, (xx, v), xytext=(3, 0), textcoords="offset points", fontsize=4.0, va="center", color=MUTE)
    ax.set_ylim(lo, hi)
    if np.any(np.asarray(vals)[np.isfinite(vals)] > hi_f):
        ax.plot([-0.02, 0.02], [0.93, 0.95], color=INK, lw=0.6, transform=ax.transAxes, clip_on=False)
        ax.plot([-0.02, 0.02], [0.905, 0.925], color=INK, lw=0.6, transform=ax.transAxes, clip_on=False)
    if np.any(np.asarray(vals)[np.isfinite(vals)] < lo_f):
        ax.plot([-0.02, 0.02], [0.05, 0.07], color=INK, lw=0.6, transform=ax.transAxes, clip_on=False)
        ax.plot([-0.02, 0.02], [0.075, 0.095], color=INK, lw=0.6, transform=ax.transAxes, clip_on=False)


def theil_sen(x, y):
    from scipy import stats as st_
    if np.unique(x).size < 2:
        return np.nan, np.nan
    sl, ic, _, _ = st_.theilslopes(y, x)
    return sl, ic


def fit_band(ax, x, y, col, ls, grid):
    """Theil-Sen line (robust to the odd recording) and a 95% bootstrap
    band over mice (2,000 resamples)."""
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 4 or np.unique(x).size < 2:
        return
    sl, ic = theil_sen(x, y)
    rng = np.random.default_rng(11)
    B = []
    for _ in range(2000):
        i = rng.integers(0, x.size, x.size)
        if np.unique(x[i]).size < 2:
            continue
        b_, a_ = theil_sen(x[i], y[i])
        B.append(a_ + b_ * grid)
    B = np.array(B)
    lo, hi = np.nanpercentile(B, [2.5, 97.5], axis=0)
    ax.fill_between(grid, lo, hi, color=col, alpha=0.13, lw=0, zorder=1)
    ax.plot(grid, ic + sl * grid, color=col, lw=1.0, ls=ls, zorder=2)


def panel_result(fig, H, x, y, L, P):
    m = Mdf.loc[P["id"]]
    recs = RECS["v6"]
    labs = [r.lab for r in recs]
    vals = np.array([m.get(l, np.nan) for l in labs], float)
    sg = np.array([r.subgroup for r in recs])
    ko = np.array([r.ko for r in recs], float)
    cols = [Hs.col_of(r) for r in recs]
    lims = outlier_limits(vals)
    ax = ax_mm(fig, H, x, y, 46, 40)
    rng = np.random.default_rng(3)
    for i, g in enumerate(("CTL", "IED-", "IED+")):
        idx = np.where((sg == g) & np.isfinite(vals))[0]
        xs = i + rng.uniform(-0.17, 0.17, idx.size)
        draw_points(ax, xs, vals[idx], [cols[j] for j in idx], [labs[j] for j in idx], lims)
        if idx.size:
            med = np.median(vals[idx])
            if lims[0] <= med <= lims[1]:
                ax.plot([i - 0.3, i + 0.3], [med] * 2, color=INK, lw=1.0, zorder=4)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["Control\\n(n = %d)" % ((sg == "CTL") & np.isfinite(vals)).sum(), "PTEN IED−\\n(n = %d)" % ((sg == "IED-") & np.isfinite(vals)).sum(),
                        "PTEN IED+\\n(n = %d)" % ((sg == "IED+") & np.isfinite(vals)).sum()], fontsize=FS_S - 0.3)
    ax.set_xlim(-0.6, 2.75)
    ax.set_ylim(lims[0], lims[1])
    ax.set_ylabel(L["ylabel"], fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    # against knockout, with the correlation lines and their 95% bands
    ax2 = ax_mm(fig, H, x + 58, y, 36, 40)
    xs = np.where(sg == "CTL", rng.uniform(-1.8, 1.8, ko.size), ko)
    xfit = np.where(sg == "CTL", 0.0, ko)
    inl = np.isfinite(vals) & (vals >= lims[2]) & (vals <= lims[3])
    grid_all, grid_p = np.linspace(0, 30, 60), np.linspace(3, 30, 60)
    fit_band(ax2, xfit[inl], vals[inl], MUTE, (0, (3, 2)), grid_all)
    pm = inl & (sg != "CTL")
    fit_band(ax2, ko[pm], vals[pm], "#C8591A", "-", grid_p)
    draw_points(ax2, xs, vals, cols, labs, lims, annotate=False)
    rows = T[T["id"] == P["id"]].set_index("contrast")
    words = []
    for c, nm in (("KO_dose_PTEN", "PTEN only"), ("KO_dose_all", "all mice")):
        if c in rows.index:
            words.append("%s: rho %s, P = %.3f" % (nm, ("%+.2f" % rows.loc[c]["effect"]).replace("-", "−"), rows.loc[c]["p"]))
    ax2.set_title("  ·  ".join(words), fontsize=4.4, loc="left", pad=2, color=INK)
    ax2.set_xticks([0, 10, 20, 30])
    ax2.set_xticklabels(["Control", "10", "20", "30"], fontsize=4.8)
    ax2.set_xlim(-3, 31)
    ax2.set_xlabel("PTEN knockout (% of granule cells)", fontsize=FS_S)
    ax2.tick_params(labelsize=4.8)


'''
s = s[:i0] + NEW + s[i1:]
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
