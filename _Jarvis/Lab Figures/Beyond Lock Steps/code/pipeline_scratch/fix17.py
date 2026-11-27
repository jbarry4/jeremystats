"""Round 9: DS3 in every row. Two more panels a row -- DS3's sink with its
ticks, and DS1 and DS2 again without the DS3 events -- and the green label
becomes FINAL OPTIMIZED SEPARATION, given to the row whose DS1 and DS2 are
best separated once DS3 is out."""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(HERE, "deep_qc5.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


def cut(a, b, new):
    global s
    i0 = s.index(a)
    i1 = s.index(b, i0)
    s = s[:i0] + new + s[i1:]


rep('quality_check_round8"', 'quality_check_round9"')
rep("H = 297.0", "H = 318.0")
rep("from deep_figs import D2, plt, recs, full, W, INK, MUTE, HAIR, C_DS1, C_DS2, CSD_CMAP, FS, FS_S  # noqa: E402",
    "from deep_figs import D2, plt, recs, full, W, INK, MUTE, HAIR, C_DS1, C_DS2, C_DS3, CSD_CMAP, FS, FS_S  # noqa: E402\nCOLS = {1: C_DS1, 2: C_DS2, 3: C_DS3}")
rep('OPT2 = pickle.load(open(os.path.join(HERE, "deep_opt2_v6.pkl"), "rb"))',
    '''OPT2 = pickle.load(open(os.path.join(HERE, "deep_opt2_v6.pkl"), "rb"))
DS3 = pickle.load(open(os.path.join(HERE, "deep_ds3_v6.pkl"), "rb"))
DS3_CUT = 0.5


def si_sub(d, t3):
    """The whole-band separation index of DS1 against DS2 among the events
    that are still DS1 or DS2 in `t3`."""
    Wd = (OPT2.get(d["gid"]) or {}).get("W") or {}
    if "both" not in Wd:
        return None
    keep = np.where((t3 == 1) | (t3 == 2))[0]
    W0 = Wd["both"][np.ix_(keep, keep)].astype(float).copy()
    np.fill_diagonal(W0, 0.0)
    m = t3[keep] == 1
    na, nb = int(m.sum()), int((~m).sum())
    if na < 2 or nb < 2:
        return None
    Wm = W0 @ m
    saa, sab = float(m @ Wm), float((~m) @ Wm)
    sbb = float(W0.sum()) - saa - 2.0 * sab
    return 1.0 - (sab / (na * nb)) / ((saa / (na * (na - 1)) + sbb / (nb * (nb - 1))) / 2.0)


def ds3_info(d, key, ty, si0):
    """DS3 under one classification: which events score within +-0.5 on
    the relative sink (Tarcsay et al. 2025), and how well DS1 and DS2
    separate without them. `final` is None when a type is left with under
    5 events."""
    src = (DS3.get(d["gid"]) or {}).get(key)
    if src is None:
        e_ = d["splits"].get(key) or {}
        src = e_ if ("score" in e_ or e_.get("why")) and e_.get("why") != "not scored for DS3" else None
    n = ty.size
    if src is None or src.get("why") or "score" not in src:
        return {"ok": False, "mask": np.zeros(n, bool), "t3": ty.copy(), "final": si0, "n1": int((ty == 1).sum()), "n2": int((ty == 2).sum())}
    sc = np.asarray(src["score"], float)
    mask = np.isfinite(sc) & (np.abs(sc) <= DS3_CUT)
    t3 = np.where(mask, 3, ty)
    n1, n2 = int((t3 == 1).sum()), int((t3 == 2).sum())
    return {"ok": True, "mask": mask, "t3": t3, "unsc": int((~np.isfinite(sc)).sum()), "gap": abs(src["oml"] - src["mml"]) * 50,
            "n1": n1, "n2": n2, "final": si_sub(d, t3) if min(n1, n2) >= 5 else None}''')

# sinks_of: any set of types
rep('def sinks_of(d, ty, ext):', 'def sinks_of(d, ty, ext, classes=(1, 2)):')
rep('''    for c in (1, 2):
        k = max(int((ty == c).sum()), 1)
        mu = at0[ty == c].mean(axis=0)''', '''    classes = tuple(c for c in classes if (ty == c).any())
    out["classes"] = classes
    for c in classes:
        k = max(int((ty == c).sum()), 1)
        mu = at0[ty == c].mean(axis=0)''')
rep('''    out["clear"] = [out["peak"][1][b_] / max(out["floor"][1], 1e-12) for b_ in (0, 1)]
    out["out"] = [None if out["cen"][1][b_] is None or out["cen"][2][b_] is None
                  else round((out["cen"][2][b_] - out["cen"][1][b_]) * (1 if b_ == 0 else -1)) for b_ in (0, 1)]
    return out''', '''    if 1 in classes and 2 in classes:
        out["clear"] = [out["peak"][1][b_] / max(out["floor"][1], 1e-12) for b_ in (0, 1)]
        out["out"] = [None if out["cen"][1][b_] is None or out["cen"][2][b_] is None
                      else round((out["cen"][2][b_] - out["cen"][1][b_]) * (1 if b_ == 0 else -1)) for b_ in (0, 1)]
    return out''')
cut("def draw_sinks(ax, I):", "def band_lines(ax, I, word=False):", '''def top_of(I):
    return max([float(np.nanmax(I["sink"][c] + I["se"][c])) for c in I["classes"]] or [0.0])


def draw_sinks(ax, I, top=None):
    top = top or top_of(I) or 1.0
    for c in sorted(I["classes"], reverse=True):
        col = COLS[c]
        sk, se = I["sink"][c] / top, I["se"][c] / top
        ax.fill_betweenx(I["dep"], np.maximum(sk - se, 0), sk + se, color=col, alpha=0.25, lw=0)
        ax.plot(sk, I["dep"], color=col, lw=0.9)
        ax.axvline(I["floor"][c] / top, color=col, lw=0.6, ls=(0, (2, 2)))
        x0 = 1.16 if c == 1 else 1.0
        for b_, y in enumerate(I["cen"][c]):
            if y is not None:
                ax.plot([x0, x0 + 0.12], [y, y], color=col, lw=1.4, solid_capstyle="butt", clip_on=False)
            else:
                ax.plot([x0, x0 + 0.12], [I["pkdep"][c][b_]] * 2, color=col, lw=1.4, alpha=0.3, solid_capstyle="butt", clip_on=False)
    ax.set_xlim(0, 1.05)
    ax.set_xticks([0])
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)


''')

# the row: six columns
cut("def row(fig, y0, d, num, title, sub, colr, ty, order_x, plane, heads, ext, badge=None):", "def contour(ax, ft, key, col, lw, ls):",
    '''def row(fig, y0, d, num, title, sub, colr, ty, order_x, plane, heads, ext, badge=None, D3=None, extra=None):
    """One classification, in six columns. y0: the top of the row (mm)."""
    ax_mm = lambda x, y, w, h: G.ax_mm(fig, H, x, y, w, h)
    fig.add_artist(Rectangle((4 / W, 1 - (y0 + 5.4) / H), 1.2 / W, 5.4 / H, color=colr, lw=0, transform=fig.transFigure))
    fig.text(7 / W, 1 - (y0 + 1.6) / H, "%d   %s" % (num, title), fontsize=7.5, fontweight="bold", ha="left", va="center", color=colr)
    if badge:
        fig.text(179 / W, 1 - (y0 + 1.6) / H, badge, fontsize=6.5, fontweight="bold", ha="right", va="center", color="white",
                 bbox=dict(boxstyle="round,pad=0.35", fc="#1B7F4B", ec="none"))
        fig.add_artist(Rectangle((2.2 / W, 1 - (y0 + 66.0) / H), 0.8 / W, 66.0 / H, color="#1B7F4B", lw=0, transform=fig.transFigure))
    bs = blade_si(d, ty)
    if bs is not None:
        sub = sub.replace(".   DS1 ", " (upper blade %.2f, lower blade %.2f, mean %.2f).   DS1 " % (bs[0], bs[1], (bs[0] + bs[1]) / 2.0), 1)
    fig.text(7 / W, 1 - (y0 + 4.6) / H, sub, fontsize=FS_S, ha="left", va="center", color=INK)
    I = sinks_of(d, ty, ext)
    fig.text(7 / W, 1 - (y0 + 7.4) / H, sink_words(I), fontsize=FS_S, ha="left", va="center", color=MUTE)
    n = ty.size
    if not D3["ok"]:
        w3 = "DS3.  Not measurable under this classification: DS1's and DS2's mean sinks do not give separate outer and middle layer contacts."
    else:
        k3 = int(D3["mask"].sum())
        w3 = "DS3.  %d events (%.0f%%) score within ±0.5 (layer contacts %d µm apart); %d unscorable events keep their type.   Without DS3: %s; DS1 %d, DS2 %d." % (
            k3, 100.0 * k3 / n, D3["gap"], D3["unsc"],
            "a type is left with under 5 events, no index" if D3["final"] is None else "separation index %.2f" % D3["final"], D3["n1"], D3["n2"])
    fig.text(7 / W, 1 - (y0 + 10.2) / H, w3, fontsize=FS_S, ha="left", va="center", color=C_DS3)
    if extra:
        fig.text(7 / W, 1 - (y0 + 13.0) / H, extra, fontsize=FS_S, ha="left", va="center", color=colr)
    top, hh = y0 + 23.5, 34.0
    X = PCA2[d["gid"]]["X"]
    t3 = D3["t3"]
    # 1 the PCA plane
    ax = ax_mm(10, top, 28, hh)
    ax.scatter(X[:, 0], X[:, 1], s=2.0, c=np.where(ty == 1, C_DS1, C_DS2), linewidth=0, alpha=0.8, rasterized=True)
    ax.set_xlim(X[:, 0].min(), X[:, 0].max())
    ax.set_ylim(X[:, 1].min(), X[:, 1].max())
    plane(ax, X)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("PC1", fontsize=FS)
    ax.set_ylabel("PC2", fontsize=FS)
    # 2 every event: DS1, DS3, DS2
    rank = np.where(t3 == 1, 0, np.where(t3 == 3, 1, 2))
    o = np.lexsort((np.where(np.isfinite(order_x), order_x, np.nanmax(order_x)), rank))
    P = I["at0"][o]
    v = np.percentile(np.abs(I["at0"][:, I["inband"]]), 99)
    dep = I["dep"]
    ax = ax_mm(51, top, 38, hh)
    ax.set_facecolor("#DADADA")
    ax.imshow(np.ma.masked_invalid(P.T), aspect="auto", cmap=CSD_CMAP, vmin=-v, vmax=v, interpolation="nearest", extent=[0, P.shape[0], dep[-1] + 25, dep[0] - 25])
    n1, n3 = int((t3 == 1).sum()), int((t3 == 3).sum())
    for x_ in (n1, n1 + n3):
        if 0 < x_ < n:
            ax.axvline(x_, color=INK, lw=0.6)
    band_lines(ax, I, True)
    span = dep[-1] - dep[0] + 50
    for a, b, c in ((0, n1, C_DS1), (n1, n1 + n3, C_DS3), (n1 + n3, n, C_DS2)):
        if b > a:
            ax.add_patch(Rectangle((a, dep[0] - 25 - 0.045 * span), b - a, 0.03 * span, color=c, clip_on=False, lw=0))
    ax.set_xticks([0, n])
    ax.set_ylabel("Depth from band center (µm)", fontsize=FS)
    ax.set_xlabel("Events: DS1, DS3, DS2", fontsize=FS_S)
    # 3 the means
    ax = ax_mm(93, top, 17, hh)
    for c in (2, 1):
        ax.fill_betweenx(dep, I["mu"][c] - I["mse"][c], I["mu"][c] + I["mse"][c], color=COLS[c], alpha=0.25, lw=0)
        ax.plot(I["mu"][c], dep, color=COLS[c], lw=0.9)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    band_lines(ax, I)
    ax.set_ylim(dep[-1] + 25, dep[0] - 25)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xticks([0])
    ax.set_xlabel("sink − 0 + source", fontsize=FS_S - 0.5)
    # 4-6 the sinks: as classified, DS3 alone, DS1 and DS2 without DS3
    I3 = sinks_of(d, t3, ext, (3,)) if D3["mask"].any() else None
    In = sinks_of(d, t3, ext, (1, 2)) if D3["mask"].any() else None
    tp = max([top_of(I)] + [top_of(k) for k in (I3, In) if k is not None]) or 1.0
    for x_, Ik, lab, none in ((114, I, "DS1 and DS2", None), (137, I3, "DS3", "no DS3 events" if D3["ok"] else "DS3 not measurable"),
                              (160, In, "DS1, DS2 without DS3", "same as the first" if D3["ok"] else "DS3 not measurable")):
        ax = ax_mm(x_, top, 15, hh)
        if Ik is None:
            ax.text(0.5, 0.5, none.replace(" ", chr(10), 1), transform=ax.transAxes, ha="center", va="center", fontsize=FS_S, color=MUTE)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.spines["left"].set_visible(False)
        else:
            draw_sinks(ax, Ik, tp)
            band_lines(ax, I)
        ax.set_ylim(dep[-1] + 25, dep[0] - 25)
        ax.set_xlabel(lab, fontsize=FS_S - 0.5, color=C_DS3 if lab == "DS3" else INK)
    if heads:
        for x, s_ in ((10, "PCA plane"), (51, "CSD at the DS peak, every event"), (93, "Mean CSD"), (114, "Mean sink ± s.e.m., one scale across the three")):
            fig.text(x / W, 1 - (top - 5.8) / H, s_, fontsize=FS, ha="left", va="center", color=INK)
        for x, s_, c in ((93, "DS1", C_DS1), (99.5, "DS2", C_DS2), (106, "DS3", C_DS3)):
            fig.text(x / W, 1 - (top - 2.3) / H, s_, fontsize=FS_S, fontweight="bold", color=c, ha="left", va="center")
    return I


''')

# the page: who wins is decided without DS3
cut("    # which of the three has the highest index", "    # row 1  the classifier used", '''    # each row's classification, its DS3, and DS1 against DS2 without DS3
    cand_ = [(k, d["splits"][k]) for k in ON_PLANE if k in d["splits"] and "err" not in d["splits"][k] and d["splits"][k].get("si") is not None]
    ok_ = [c for c in cand_ if eligible(c[1], d["n"])]
    k2_, e2_ = max(ok_ or cand_, key=lambda c: c[1]["si"])
    oc_ = O.get("opt_curve") or {}
    D3s = {1: ds3_info(d, m, ty, e["si"]), 2: ds3_info(d, k2_, align(e2_["types"], ty)[0], e2_["si"] if eligible(e2_, d["n"]) else None)}
    if "types" in oc_:
        D3s[3] = ds3_info(d, "opt_curve", align(oc_["types"], ty)[0], oc_["si"])
    before = {1: e["si"], 2: e2_["si"] if eligible(e2_, d["n"]) else None, 3: oc_.get("si")}
    fin = {k: v["final"] for k, v in D3s.items()}
    live = [v for v in fin.values() if v is not None]
    win = [k for k, v in fin.items() if v is not None and v >= max(live) - 0.005] if live else []
    badge = lambda k: None if k not in win else ("FINAL OPTIMIZED SEPARATION" if len(win) == 1 else "FINAL OPTIMIZED SEPARATION (TIE: ROWS %s)" % " AND ".join(str(x) for x in win))
    f2 = lambda v: "none" if v is None else "%.2f" % v
    bits = ["row %d: %s to %s" % (k, f2(before[k]), f2(fin.get(k))) for k in (1, 2, 3)]
    fig.text(179 / W, 1 - 5 / H, "Separation index, as classified to without DS3     " + "     ".join(bits), fontsize=FS_S, ha="right", va="center", color=INK)
''')
rep('RED, ty, np.asarray(e["x"], float), plane1, True, ext, badge(1))', 'RED, ty, np.asarray(e["x"], float), plane1, True, ext, badge(1), D3s[1])')
rep('INK, t2, Q["X"][:, 0], plane2, False, ext, badge(2))', 'INK, t2, Q["X"][:, 0], plane2, False, ext, badge(2), D3s[2])')
rep('PURPLE, t3, Q["X"][:, 0], plane3, False, ext, badge(3))', 'PURPLE, t3, Q["X"][:, 0], plane3, False, ext, badge(3), D3s[3], extra4)')
cut('            fig.text(7 / W, 1 - (y + 10.4) / H, "Maximizing the mean of the upper-blade', '        row(fig, y, d, 3,',
    '''            extra4 = "Maximizing the mean of the upper-blade and lower-blade indices instead gives %s (mean %.2f, %.2f held out)." % (
                "the same boundary" if same4 > 0.999 else "nearly the same boundary, %.0f%% of events keeping their type" % (100 * same4), f4["mean"],
                f4["heldout"] if f4["heldout"] is not None else float("nan"))
''')
rep("        f4 = (OPT2.get(d[\"gid\"]) or {}).get(\"fit\")\n", "        extra4 = None\n        f4 = (OPT2.get(d[\"gid\"]) or {}).get(\"fit\")\n")
assert s.count("    y += 64.0\n") == 2
s = s.replace("    y += 64.0\n", "    y += 68.0\n")
rep('''        "Green label and bar: the row with the highest separation index among eligible rows. Row 3 was fitted to maximize that index, so its held-out value is the fair one to set against rows 1 and 2."]''',
    '''        "DS3.  An event whose relative sink, (outer − middle) / (outer + middle), is within ±0.5 (Tarcsay et al. 2025); the outer and middle "
        "molecular layer contacts are where DS1's and DS2's mean sinks peak in this row's classification.",
        "    Sink panels: DS1 and DS2 as classified; DS3 alone; DS1 and DS2 with the DS3 events taken out. One scale across the three.",
        "Green label and bar, FINAL OPTIMIZED SEPARATION: the row whose DS1 and DS2 have the highest separation index once DS3 is taken out "
        "(each type keeping 5 events or more). Where DS3 is not measurable the row keeps its index as classified."]''')
rep("(272.0 + 3.3 * i_)", "(287.0 + 3.3 * i_)")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
