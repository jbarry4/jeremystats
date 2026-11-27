"""Round 6: the depth range is widened past the analysed band (5 contacts a
side, more while a sink is still above its noise floor at the edge), so a
sink at the band's edge is seen whole. The band's limits are drawn."""
import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_qc5.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


a0 = s.index("def sinks_of(d, ty):")
a1 = s.index("def sink_words(I):")
new = '''MARGIN, MARGIN_MOST = 5, 12


def extent(d, ty):
    """The whole-shank rows to draw: the analysed band and 5 contacts a
    side, widened (to 12) while either type's mean sink is still above its
    noise floor at that end. Bad contacts are skipped over, never an end."""
    F = full[d["gid"]]
    na = F["nums_all"]
    a, b = na.index(d["ns"][0]), na.index(d["ns"][-1])
    tt = F["tt"]
    at0 = F["csd_ev"][:, :, np.abs(tt) <= 3.0].mean(axis=2).astype(float)
    base = np.abs(tt) > 30
    sink, floor = {}, {}
    for c in (1, 2):
        sink[c] = np.maximum(-at0[ty == c].mean(axis=0), 0.0)
        floor[c] = float(np.percentile(np.abs(F["csd_ev"][ty == c][:, a:b + 1, :].astype(float).mean(axis=0)[:, base]), 99))
    n_r = at0.shape[1]
    lo, hi = max(0, a - MARGIN), min(n_r - 1, b + MARGIN)
    while lo > max(0, a - MARGIN_MOST) and any(sink[c][lo] > floor[c] for c in (1, 2)):
        lo -= 1
    while hi < min(n_r - 1, b + MARGIN_MOST) and any(sink[c][hi] > floor[c] for c in (1, 2)):
        hi += 1
    return lo, hi


def sinks_of(d, ty, ext):
    """DS1 and DS2 under any classification `ty`, over the rows `ext`
    (extent): the mean CSD and sink (max(0, -CSD) of the mean) with s.e.m.
    by depth, each mean's noise floor (99th percentile of the mean's |CSD|
    more than 30 ms from the DS, in the analysed band), and per blade DS1's
    peak sink over its floor, each type's sink centroid above its floor
    and the offset (DS1 distal to DS2) where both clear their floors."""
    F = full[d["gid"]]
    na = F["nums_all"]
    a, b = na.index(d["ns"][0]), na.index(d["ns"][-1])
    lo, hi = ext
    rows = np.arange(lo, hi + 1)
    bad = np.array([na[r] in F["bad"] and not (a <= r <= b) for r in rows])
    ev = F["csd_ev"][:, lo:hi + 1, :].astype(float)
    tt = F["tt"]
    at0 = ev[:, :, np.abs(tt) <= 3.0].mean(axis=2)
    at0[:, bad] = np.nan
    base = np.abs(tt) > 30
    mid = (a + b) / 2.0
    cut = a + d["hump_cut"] - lo
    out = {"dep": (rows - mid) * 50.0, "band": ((a - mid) * 50.0 - 25, (b - mid) * 50.0 + 25), "at0": at0, "inband": (rows >= a) & (rows <= b),
           "sink": {}, "se": {}, "floor": {}, "cen": {}, "peak": {}, "mu": {}, "mse": {}}
    for c in (1, 2):
        k = max(int((ty == c).sum()), 1)
        mu = at0[ty == c].mean(axis=0)
        out["mu"][c], out["mse"][c] = mu, at0[ty == c].std(axis=0) / np.sqrt(k)
        out["sink"][c], out["se"][c] = np.maximum(-mu, 0.0), out["mse"][c]
        out["floor"][c] = float(np.percentile(np.abs(ev[ty == c][:, a - lo:b - lo + 1, :].mean(axis=0)[:, base]), 99))
        cs, pk = [], []
        for l_, h_ in ((0, cut), (cut, rows.size)):
            sk = np.nan_to_num(out["sink"][c][l_:h_])
            pk.append(float(sk.max()))
            w = np.maximum(sk - out["floor"][c], 0.0)
            cs.append(float((w * out["dep"][l_:h_]).sum() / w.sum()) if w.sum() > 0 else None)
        out["cen"][c], out["peak"][c] = cs, pk
    out["clear"] = [out["peak"][1][b_] / max(out["floor"][1], 1e-12) for b_ in (0, 1)]
    out["out"] = [None if out["cen"][1][b_] is None or out["cen"][2][b_] is None
                  else round((out["cen"][2][b_] - out["cen"][1][b_]) * (1 if b_ == 0 else -1)) for b_ in (0, 1)]
    return out


def draw_sinks(ax, I):
    top = max(float(np.nanmax(I["sink"][c] + I["se"][c])) for c in (1, 2))
    for c, col in ((2, C_DS2), (1, C_DS1)):
        sk, se = I["sink"][c] / top, I["se"][c] / top
        ax.fill_betweenx(I["dep"], np.maximum(sk - se, 0), sk + se, color=col, alpha=0.25, lw=0)
        ax.plot(sk, I["dep"], color=col, lw=0.9)
        ax.axvline(I["floor"][c] / top, color=col, lw=0.6, ls=(0, (2, 2)))
        for y in I["cen"][c]:
            if y is not None:
                ax.plot([1.0, 1.1], [y, y], color=col, lw=1.4, solid_capstyle="butt", clip_on=False)
    ax.set_xlim(0, 1.05)
    ax.set_xticks([0])
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)


def band_lines(ax, I, word=False):
    for y in I["band"]:
        ax.axhline(y, color=INK, lw=0.5, ls=(0, (4, 2)), alpha=0.7)
    if word:
        ax.text(1.0, I["band"][0], "band ", transform=ax.get_yaxis_transform(), fontsize=FS_S - 0.5, ha="right", va="bottom", color=INK)


'''
s = s[:a0] + new + s[a1:]
rep("def row(fig, y0, d, num, title, sub, colr, ty, order_x, plane, heads):", "def row(fig, y0, d, num, title, sub, colr, ty, order_x, plane, heads, ext):")
rep("    I = sinks_of(d, ty)\n", "    I = sinks_of(d, ty, ext)\n")
rep('''    P = d["prof"][o]
    v = np.percentile(np.abs(d["prof"]), 99)''', '''    P = I["at0"][o]
    v = np.percentile(np.abs(I["at0"][:, I["inband"]]), 99)''')
rep('    ax = ax_mm(62, top, 56, hh)\n    ax.imshow(P.T,', '    ax = ax_mm(62, top, 56, hh)\n    ax.set_facecolor("#DADADA")\n    ax.imshow(np.ma.masked_invalid(P.T),')
rep("    ax.axvline(n1, color=INK, lw=0.6)\n", "    ax.axvline(n1, color=INK, lw=0.6)\n    band_lines(ax, I, True)\n")
rep('    ax.set_ylabel("Depth in band (µm)", fontsize=FS)', '    ax.set_ylabel("Depth from band centre (µm)", fontsize=FS)')
rep('    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)\n    ax.set_ylim(dep[-1] + 25, dep[0] - 25)',
    '    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)\n    band_lines(ax, I)\n    ax.set_ylim(dep[-1] + 25, dep[0] - 25)')
rep("    G.draw_sinks(ax, I, first=False)\n", "    draw_sinks(ax, I)\n    band_lines(ax, I)\n    ax.set_ylim(dep[-1] + 25, dep[0] - 25)\n")
rep("    Q, O = PCA2[d[\"gid\"]], (OPT.get(d[\"gid\"], {}).get(\"fits\") or {})\n", "    Q, O = PCA2[d[\"gid\"]], (OPT.get(d[\"gid\"], {}).get(\"fits\") or {})\n    ext = extent(d, ty)\n")
rep("RED, ty, np.asarray(e[\"x\"], float), plane1, True)", "RED, ty, np.asarray(e[\"x\"], float), plane1, True, ext)")
rep("INK, t2, Q[\"X\"][:, 0], plane2, False)", "INK, t2, Q[\"X\"][:, 0], plane2, False, ext)")
rep("PURPLE, t3, Q[\"X\"][:, 0], plane3, False)", "PURPLE, t3, Q[\"X\"][:, 0], plane3, False, ext)")
rep('''        "Each row is one way of classifying the same events, drawn the same way. Colours: DS1 blue, DS2 orange, named as in row 1.",''',
    '''        "Each row is one way of classifying the same events, drawn the same way. Colours: DS1 blue, DS2 orange, named as in row 1.",
        "Depth.  Dashed lines: the limits of the analysed band (the contacts the classifiers saw). The range is widened 5 contacts past each "
        "limit, and further while a sink is still above its noise floor there; grey: a bad contact outside the band.",''')
rep('"than 30 ms from the DS peak). Ticks at the right: sink centroid above the floor."]',
    '"than 30 ms from the DS peak, in the band). Ticks at the right: sink centroid above the floor, over the widened range."]')
rep("H = 287.0", "H = 290.0")
rep('quality_check_round5"', 'quality_check_round6"')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
