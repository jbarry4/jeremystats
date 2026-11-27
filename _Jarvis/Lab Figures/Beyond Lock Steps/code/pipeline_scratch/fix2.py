import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_figs.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (a[:60], s.count(a))
    s = s.replace(a, b)


# ── figure 2, lower row: e = the two families' sinks, f = the outward shift
a0 = s.index("    # e  the relative-sink score where two families are resolved")
a1 = s.index("# ───────────────────────── Figure 3")
new = '''    # e  where each family's sink sits, in the recordings with two families
    letter(fig, H, 66, 68, "e")
    use = [d for d in recs if d["n"] >= DS.MIN_N]
    res = sorted([d for d in use if D2.best_si(d)[1]["si"] >= 0.45], key=lambda d: (d["g"] != "CTL", d["ko"]))
    fig.text(77.0 / W, 1 - 71.5 / H, "Recordings with two families: each family's mean current, from the granule layer outwards",
             fontsize=FS, ha="left", va="center")
    info = {}
    for d in use:
        info[d["lab"]] = families(d)
    for i, d in enumerate(res):
        I = info[d["lab"]]
        ax = ax_mm(fig, H, 77 + i * 11.2, 80, 9.6, 36)
        ax.axvline(0, color=HAIR, lw=0.4, zorder=0)
        ax.axhline(0, color=HAIR, lw=0.4, zorder=0, ls=(0, (2, 2)))
        for c, col in ((2, C_DS2), (1, C_DS1)):
            ax.plot(I["prof"][c], I["dep"], color=col, lw=0.9)
            for y in I["cen"][c]:
                ax.plot([-1.22, -1.06], [y, y], color=col, lw=1.6, solid_capstyle="butt", clip_on=False)
        ax.set_xlim(-1.25, 1.15)
        ax.set_ylim(650, -650)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        if i == 0:
            ax.set_yticks([-600, -300, 0, 300, 600])
            ax.set_ylabel("Depth from the granule-layer source (µm)", fontsize=FS)
        else:
            ax.set_yticks([])
            ax.spines["left"].set_visible(False)
        ax.add_patch(Rectangle((0, 1.012), 1, 0.022, transform=ax.transAxes, color=col_of(d), clip_on=False, lw=0))
        ax.text(0.5, 1.05, d["lab"], transform=ax.transAxes, ha="center", va="bottom", fontsize=FS_S)
        ax.text(0.5, -0.03, "DS1 %.0f%%" % I["share"], transform=ax.transAxes, ha="center", va="top", fontsize=FS_S, color=C_DS1)
    fig.text(77.0 / W, 1 - 123.5 / H, "DS1", fontsize=FS_S, color=C_DS1, fontweight="bold", ha="left", va="center")
    fig.text(83.5 / W, 1 - 123.5 / H, "DS2", fontsize=FS_S, color=C_DS2, fontweight="bold", ha="left", va="center")
    fig.text(90.0 / W, 1 - 123.5 / H, "each scaled to its own deepest sink; ticks at the left mark each sink's centre", fontsize=FS_S, color=MUTE,
             ha="left", va="center")
    # f  how far out DS1's sink sits from DS2's
    letter(fig, H, 147, 68, "f")
    ax = ax_mm(fig, H, 158, 80, 22, 36)
    rng = np.random.default_rng(5)
    grp = [[d for d in use if D2.best_si(d)[1]["si"] >= 0.45], [d for d in use if D2.best_si(d)[1]["si"] < 0.45]]
    vals = []
    ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
    for k, g in enumerate(grp):
        v = np.array([info[d["lab"]]["out"] for d in g])
        vals.append(v)
        ax.scatter(k + rng.uniform(-0.16, 0.16, v.size), v, s=13, c=[col_of(d) for d in g], edgecolor="white", linewidth=0.4, zorder=3)
        ax.plot([k - 0.28, k + 0.28], [np.median(v)] * 2, color=INK, lw=1.0, zorder=4)
    pv = st.mannwhitneyu(vals[0], vals[1]).pvalue
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Two\\nfamilies\\n(n = %d)" % len(grp[0]), "One or\\npartly\\n(n = %d)" % len(grp[1])], fontsize=FS_S)
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("DS1 sink farther from the granule\\nlayer than DS2 sink (µm, both blades)", fontsize=FS)
    ax.text(0.5, 1.02, "P = %.4f" % pv, transform=ax.transAxes, ha="center", va="bottom", fontsize=FS)
    save(fig, "Fig2_families_and_hybrids")
    R = [info[d["lab"]] for d in res]
    return {"resolved": [(d["lab"], d["g"], round(I["share"], 1), round(I["out_u"]), round(I["out_l"]), round(I["amp"], 2)) for d, I in zip(res, R)],
            "p_f": pv, "out_res": float(np.median(vals[0])), "out_not": float(np.median(vals[1])),
            "share_med": float(np.median([I["share"] for I in R])), "amp_med": float(np.median([I["amp"] for I in R]))}


def families(d):
    """The best split's two class means about the granule-layer source: the
    profiles (each over its own deepest sink), each blade's sink centre, and
    how far out DS1's sits from DS2's."""
    F = full[d["gid"]]
    e = D2.best_si(d)[1]
    ty = e["types"]
    ev = F["csd_at0"].astype(float)
    s1, s2, src = D2.geometry(d, F)
    na = F["nums_all"]
    a, b = na.index(d["ns"][0]), na.index(d["ns"][-1])
    cut = a + d["hump_cut"]
    rows = np.arange(max(0, src - 13), min(ev.shape[1], src + 14))
    out = {"dep": (rows - src) * 50.0, "prof": {}, "cen": {}, "share": 100.0 * float((ty == 1).mean())}
    cen, dep_ = {}, {}
    for c in (1, 2):
        mu = ev[ty == c].mean(axis=0)
        out["prof"][c] = mu[rows] / max(np.max(-mu[a:b + 1]), 1e-12)
        cs = []
        for lo, hi in ((a, cut), (cut, b + 1)):
            w = np.maximum(-mu[lo:hi], 0)
            cs.append((w * np.arange(lo, hi)).sum() / max(w.sum(), 1e-12))
        cen[c] = cs
        out["cen"][c] = [(x - src) * 50.0 for x in cs]
        dep_[c] = float(np.max(-mu[a:b + 1]))
    out["out_u"] = (cen[2][0] - cen[1][0]) * 50.0
    out["out_l"] = (cen[1][1] - cen[2][1]) * 50.0
    out["out"] = 0.5 * (out["out_u"] + out["out_l"])
    out["amp"] = dep_[1] / dep_[2]
    return out


'''
s = s[:a0] + new + s[a1:]
rep('ax = ax_mm(fig, H, 13, 78, 50, 38)\n    rng = np.random.default_rng(2)', 'ax = ax_mm(fig, H, 13, 80, 42, 36)\n    rng = np.random.default_rng(2)')
rep('ax.text(ax.get_xlim()[1], 28.5, "about 27% in Tarcsay et al. 2025", fontsize=FS_S, color=MUTE, ha="right", va="bottom")',
    'ax.text(340, 29, "about 27% in\\nTarcsay et al. 2025", fontsize=FS_S, color=MUTE, ha="right", va="bottom", linespacing=1.2)')
rep('ax.set_xlim(0, min(900, gx.max() + 50))', 'ax.set_xlim(0, 350)\n    ax.set_xticks([0, 100, 200, 300])')
rep('"each dot: one recording under one split\\nline: median"', '"dot: one recording, one split\\nline: median"')
rep('ax.set_xlabel("Distance between the two contacts read as\\nouter and middle molecular layer (µm)", fontsize=FS)',
    'ax.set_xlabel("Distance between the contacts read as\\nouter and middle molecular layer (µm)", fontsize=FS)')

# ── figure 3: room for the bottom row, real minus signs, powers of ten
rep("    H = 132.0\n    fig = plt.figure(figsize=(W / 25.4, H / 25.4))\n    rows = FIN[6]", "    H = 140.0\n    fig = plt.figure(figsize=(W / 25.4, H / 25.4))\n    rows = FIN[6]")
rep('letter(fig, H, 2, 76, "b")\n    ax = ax_mm(fig, H, 13, 86, 46, 34)', 'letter(fig, H, 2, 84, "b")\n    ax = ax_mm(fig, H, 13, 97, 44, 32)')
rep('letter(fig, H, 66, 76, "c")\n    ax = ax_mm(fig, H, 78, 86, 40, 34)', 'letter(fig, H, 64, 84, "c")\n    ax = ax_mm(fig, H, 78, 97, 40, 32)')
rep('letter(fig, H, 126, 76, "d")\n    ax = ax_mm(fig, H, 138, 86, 41, 34)', 'letter(fig, H, 126, 84, "d")\n    ax = ax_mm(fig, H, 136, 97, 43, 32)')
rep('ax.legend(fontsize=FS_S, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=1,',
    'ax.legend(fontsize=FS_S, frameon=False, loc="lower left", bbox_to_anchor=(-0.02, 1.0), ncol=1,')
rep('"all mice: ρ = %.2f, P = %.3f\\nPTEN only: ρ = %.2f, P = %.3f\\nuncorrected" % (ra.correlation, ra.pvalue, rp.correlation, rp.pvalue)',
    '("all mice: ρ = %.2f, P = %.3f\\nPTEN only: ρ = %.2f, P = %.3f\\nuncorrected" % (ra.correlation, ra.pvalue, rp.correlation, rp.pvalue)).replace("-", "−")')
rep('ax.set_xticklabels(["10⁻⁵", "10⁻⁴", "10⁻³", "0.01", "0.1"])', 'ax.set_xticklabels(["$10^{-5}$", "$10^{-4}$", "$10^{-3}$", "0.01", "0.1"])')
rep('''    ax.text(ob + 0.1, ax.get_ylim()[1] * 0.98, "this data:\\nP = %.3f\\n\\n%.0f%% of shuffles\\ndo as well" % (fam["best"][1], 100 * fam["fw_p"]),
            fontsize=FS_S, color="#B5361F", ha="left", va="top", linespacing=1.3)''',
    '''    ax.text(ob - 0.12, ax.get_ylim()[1] * 0.98, "best in this data:\\nP = %.3f\\n\\n%.0f%% of shuffles\\ndo as well" % (fam["best"][1], 100 * fam["fw_p"]),
            fontsize=FS_S, color="#B5361F", ha="right", va="top", linespacing=1.3)''')
rep('ax.set_ylabel("Net current between the blades\\n(source +, relative to the sinks)", fontsize=FS)',
    'ax.set_ylabel("Net current between the blades\\n(+ source; 1 = the sinks\' depth)", fontsize=FS)')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
