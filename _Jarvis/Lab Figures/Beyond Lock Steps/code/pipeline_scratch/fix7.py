"""Round 2 of the sink comparison: both types on one absolute scale, inside
the analysed band, with s.e.m. and each type's noise floor; an offset only
where DS1's sink clears its floor."""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(HERE, "deep_figs.py")
s = io.open(p, encoding="utf-8").read()
a0 = s.index("    # e  where each family's sink sits")
a1 = s.index("# ───────────────────────── Figure 3")
new = '''    # e  DS1 and DS2 sinks on one scale, in the separable recordings
    letter(fig, H, 66, 68, "e")
    use = [d for d in recs if d["n"] >= DS.MIN_N]
    res = sorted([d for d in use if D2.best_si(d)[1]["si"] >= 0.45], key=lambda d: (d["g"] != "CTL", d["ko"]))
    fig.text(77.0 / W, 1 - 71.5 / H, "DS1 and DS2 sink amplitude by depth in the six separable recordings", fontsize=FS, ha="left", va="center")
    info = {d["lab"]: families(d) for d in use}
    for i, d in enumerate(res):
        ax = ax_mm(fig, H, 78 + i * 11.4, 80, 10.0, 36)
        draw_sinks(ax, info[d["lab"]], first=(i == 0))
        ax.add_patch(Rectangle((0, 1.012), 1, 0.022, transform=ax.transAxes, color=col_of(d), clip_on=False, lw=0))
        ax.text(0.5, 1.05, d["lab"], transform=ax.transAxes, ha="center", va="bottom", fontsize=FS_S)
        ax.text(0.5, -0.02, "DS1 %.0f%%" % info[d["lab"]]["share"], transform=ax.transAxes, ha="center", va="top", fontsize=FS_S, color=C_DS1)
    fig.text(78.0 / W, 1 - 124.0 / H, "DS1", fontsize=FS_S, color=C_DS1, fontweight="bold", ha="left", va="center")
    fig.text(84.0 / W, 1 - 124.0 / H, "DS2", fontsize=FS_S, color=C_DS2, fontweight="bold", ha="left", va="center")
    fig.text(90.5 / W, 1 - 124.0 / H, "mean sink ± s.e.m., one scale per recording;" + chr(10) + "dashed: noise floor of each mean", fontsize=FS_S,
             color=MUTE, ha="left", va="center", linespacing=1.2)
    # f  does DS1's sink clear its noise floor
    letter(fig, H, 149, 68, "f")
    ax = ax_mm(fig, H, 160, 80, 20, 36)
    rng = np.random.default_rng(5)
    grp = [[d for d in use if D2.best_si(d)[1]["si"] >= 0.45], [d for d in use if D2.best_si(d)[1]["si"] < 0.45]]
    vals = []
    ax.axhline(1, color=MUTE, lw=0.5, ls=(0, (3, 2)), zorder=0)
    for k, g in enumerate(grp):
        v = np.array([max(info[d["lab"]]["clear"]) for d in g])
        vals.append(v)
        ax.scatter(k + rng.uniform(-0.16, 0.16, v.size), v, s=13, c=[col_of(d) for d in g], edgecolor="white", linewidth=0.4, zorder=3)
        ax.plot([k - 0.28, k + 0.28], [np.median(v)] * 2, color=INK, lw=1.0, zorder=4)
    ax.set_yscale("log")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Yes" + chr(10) + "(n = %d)" % len(grp[0]), "No" + chr(10) + "(n = %d)" % len(grp[1])], fontsize=FS_S)
    ax.set_xlabel("DS1 and DS2" + chr(10) + "separable", fontsize=FS)
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("DS1 peak sink / noise floor", fontsize=FS)
    save(fig, "Fig2_DS1_DS2_DS3_classification")
    R = [info[d["lab"]] for d in res]
    return {"resolved": [(d["lab"], d["g"], round(I["share"], 1), [round(x, 2) for x in I["clear"]], I["out"], round(I["amp"], 2)) for d, I in zip(res, R)],
            "clear_res": float(np.median(vals[0])), "clear_not": float(np.median(vals[1]))}


def families(d):
    """DS1 and DS2 under the best classifier, in the analysed band, on one
    absolute scale: the mean sink (max(0, -CSD) of the type's mean) and its
    s.e.m. by depth; each mean's noise floor (the 99th percentile of the
    mean's |CSD| more than 30 ms from the DS); per blade, DS1's peak sink
    over its floor, each type's sink centroid above its floor, and the
    offset (DS1 distal to DS2, um) only where both clear their floors."""
    F = full[d["gid"]]
    e = D2.best_si(d)[1]
    ty = e["types"]
    na = F["nums_all"]
    sel = [na.index(x) for x in d["ns"]]
    ev = F["csd_ev"][:, sel, :].astype(float)
    tt = F["tt"]
    at0 = ev[:, :, np.abs(tt) <= 3.0].mean(axis=2)
    base = np.abs(tt) > 30
    nb = len(sel)
    hc = d["hump_cut"]
    out = {"dep": (np.arange(nb) - (nb - 1) / 2.0) * 50.0, "sink": {}, "se": {}, "floor": {}, "cen": {}, "peak": {},
           "share": 100.0 * float((ty == 1).mean()), "n": {c: int((ty == c).sum()) for c in (1, 2)}}
    for c in (1, 2):
        mu = at0[ty == c].mean(axis=0)
        out["sink"][c] = np.maximum(-mu, 0.0)
        out["se"][c] = at0[ty == c].std(axis=0) / np.sqrt(max((ty == c).sum(), 1))
        out["floor"][c] = float(np.percentile(np.abs(ev[ty == c].mean(axis=0)[:, base]), 99))
        cs, pk = [], []
        for lo, hi in ((0, hc), (hc, nb)):
            sk = out["sink"][c][lo:hi]
            pk.append(float(sk.max()))
            w = np.maximum(sk - out["floor"][c], 0.0)
            cs.append(float((w * out["dep"][lo:hi]).sum() / w.sum()) if w.sum() > 0 else None)
        out["cen"][c], out["peak"][c] = cs, pk
    out["clear"] = [out["peak"][1][b] / max(out["floor"][1], 1e-12) for b in (0, 1)]
    out["out"] = [None if out["cen"][1][b] is None or out["cen"][2][b] is None
                  else round((out["cen"][2][b] - out["cen"][1][b]) * (1 if b == 0 else -1)) for b in (0, 1)]
    out["amp"] = max(out["peak"][1]) / max(out["peak"][2])
    return out


def draw_sinks(ax, I, first=True):
    """Both types' mean sink by depth, one scale, with s.e.m. and floors."""
    top = max(float((I["sink"][c] + I["se"][c]).max()) for c in (1, 2))
    for c, col in ((2, C_DS2), (1, C_DS1)):
        sk, se = I["sink"][c] / top, I["se"][c] / top
        ax.fill_betweenx(I["dep"], np.maximum(sk - se, 0), sk + se, color=col, alpha=0.25, lw=0)
        ax.plot(sk, I["dep"], color=col, lw=0.9)
        ax.axvline(I["floor"][c] / top, color=col, lw=0.6, ls=(0, (2, 2)))
        for y in I["cen"][c]:
            if y is not None:
                ax.plot([1.0, 1.1], [y, y], color=col, lw=1.4, solid_capstyle="butt", clip_on=False)
    ax.set_xlim(0, 1.05)
    ax.set_ylim(I["dep"][-1] + 25, I["dep"][0] - 25)
    ax.set_xticks([0])
    if not first:
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
    else:
        ax.set_ylabel("Depth in the analysed band (µm)", fontsize=FS)


'''
s = s[:a0] + new + s[a1:]
io.open(p, "w", encoding="utf-8").write(s)

# the quality-check page: panel d
p = os.path.join(HERE, "deep_qc.py")
s = io.open(p, encoding="utf-8").read()
a0 = s.index("    # d  sink profiles, back to back")
a1 = s.index("    # e  the classifier's axis")
new = '''    # d  both types' sinks on one scale
    G.letter(fig, H, 153, 19, "d")
    I = G.families(d)
    ax = ax_mm(158, 27, 21, 76)
    G.draw_sinks(ax, I, first=False)
    ax.set_title("Sink amplitude", fontsize=FS, loc="left", pad=8)
    lines = []
    for b, nm in ((0, "upper"), (1, "lower")):
        if I["out"][b] is None:
            lines.append("%s: DS1 sink %.1f× its noise floor" % (nm, I["clear"][b]) + chr(10) + "(no offset measured)")
        else:
            lines.append(("%s: DS1 sink %.1f× floor," % (nm, I["clear"][b]) + chr(10) + "centroid %+d µm distal to DS2" % I["out"][b]).replace("-", "−"))
    ax.set_xlabel(chr(10).join(lines), fontsize=FS_S - 0.3)
    fig.text(4 / W, 1 - 107.5 / H, "d: mean sink ± s.e.m. of each type on one scale, same depths as c; dashed lines: noise floor of each mean "
             "(99th percentile of the mean's |CSD| more than 30 ms from the DS peak); ticks at the right: sink centroid above the floor.",
             fontsize=FS_S - 0.3, ha="left", va="center", color=MUTE)
'''
s = s[:a0] + new + s[a1:]
s = s.replace('quality_check"', 'quality_check_round2"')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
