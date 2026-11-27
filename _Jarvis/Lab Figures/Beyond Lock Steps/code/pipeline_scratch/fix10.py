"""Quality check round 3: two Gaussian-mixture classifiers on the PCA plane
join the fifteen; a PC1/PC2 panel with the boundaries; the sink panel says
when a type's sink is under its floor; nothing overlaps."""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(HERE, "deep_qc.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('quality_check_round2"', 'quality_check_round3"')
rep("H = 158.0", "H = 176.0")
rep('NAMES = {"bite": "Bite line", "pca": "PCA", "pca_gap": "PCA + gap", "delta": "Delta", "delta_mid": "Delta middle"}',
    '''NAMES = {"bite": "Bite line", "pca": "PCA, k-means", "pca_gap": "PCA + gap", "delta": "Delta", "delta_mid": "Delta middle",
         "pca_gmm_line": "PCA, mixture (line)", "pca_gmm_curve": "PCA, mixture (curve)"}
import pickle  # noqa: E402
PCA2 = pickle.load(open(os.path.join(HERE, "deep_pca2_v6.pkl"), "rb"))
for d_ in recs:
    for k_, v_ in (PCA2.get(d_["gid"], {}).get("fits") or {}).items():
        if "err" not in v_ and v_.get("si") is not None:
            d_["splits"][k_] = dict(v_, x=PCA2[d_["gid"]]["X"][:, 0], why="not scored for DS3")''')
rep('''        if I["out"][b] is None:
            lines.append("%s: DS1 sink %.1f× its noise floor" % (nm, I["clear"][b]) + chr(10) + "(no offset measured)")''',
    '''        if I["cen"][2][b] is None:
            lines.append("%s: DS2 sink under its" % nm + chr(10) + "noise floor (no centroid)")
        elif I["out"][b] is None:
            lines.append("%s: DS1 sink %.1f× its floor" % (nm, I["clear"][b]) + chr(10) + "(under it: no centroid)")''')
rep("fig.text(4 / W, 1 - 153.5 / H,", "fig.text(4 / W, 1 - 171.5 / H,")
rep('G.letter(fig, H, 2, 116, "e")\n    ax = ax_mm(13, 123, 60, 20)', 'G.letter(fig, H, 2, 118, "e")\n    ax = ax_mm(13, 126, 40, 32)')
rep('G.letter(fig, H, 80, 116, "f")\n    ax = ax_mm(104, 123, 75, 20)', 'G.letter(fig, H, 58, 118, "f")\n    ax = ax_mm(88, 126, 38, 32)')
rep('ax.set_title("Distribution of classifier scores", fontsize=FS, loc="left", pad=3)', 'ax.set_title("Classifier scores", fontsize=FS, loc="left", pad=3)')
rep('ax.set_xlabel("Classifier score (%s, %s)" % (NAMES[base], row), fontsize=FS)',
    'ax.set_xlabel("Score: %s," % NAMES[base] + chr(10) + row, fontsize=FS)')
rep('''        for k, (suf, mk) in enumerate((("", "o"), ("_top", "^"), ("_bottom", "v"))):
            ee = d["splits"].get(b + suf, {})''',
    '''        for k, (suf, mk) in enumerate((("", "o"), ("_top", "^"), ("_bottom", "v"))):
            if suf and b.startswith("pca_gmm"):
                continue
            ee = d["splits"].get(b + suf, {})''')
rep('''    ax.set_title("All 15 classifiers   ●  both sinks   ▲  upper sink   ▼  lower sink   red ring: best   open: a type under 5% of events",
                 fontsize=FS_S, loc="right", pad=3)
    return fig''',
    '''    ax.set_title("All 17 classifiers", fontsize=FS, loc="left", pad=3)
    fig.text(58 / W, 1 - 166.0 / H, "f: ●  both sinks   ▲  upper sink   ▼  lower sink;" + chr(10) + "red ring: best; open: a type under 5% of events",
             fontsize=FS_S - 0.3, ha="left", va="center", color=MUTE, linespacing=1.2)
    # g  the PCA plane
    G.letter(fig, H, 131, 118, "g")
    ax = ax_mm(142, 126, 37, 32)
    Q = PCA2.get(d["gid"])
    X = Q["X"]
    ax.scatter(X[:, 0], X[:, 1], s=2.2, c=np.where(ty == 1, C_DS1, C_DS2), linewidth=0, alpha=0.8, rasterized=True)
    ax.axvline(Q["km_cut"], color=MUTE, lw=0.7, ls=(0, (3, 2)))
    for key, ls in (("pca_gmm_line", "-"), ("pca_gmm_curve", (0, (1, 1.2)))):
        ft = Q["fits"].get(key) or {}
        if "err" not in ft and ft.get("P") is not None:
            ax.contour(ft["gx"], ft["gy"], ft["P"], levels=[0.5], colors=[INK], linewidths=0.8, linestyles=[ls])
    ax.set_xlabel("PC1", fontsize=FS)
    ax.set_ylabel("PC2", fontsize=FS)
    ax.set_xticks([])
    ax.set_yticks([])
    pca_best = m.startswith("pca")
    ax.set_title("PCA plane" + (": best classifier" if pca_best else ""), fontsize=FS, loc="left", pad=3,
                 color="#B5361F" if pca_best else INK)
    st_ = ["%s %.0f%%" % (nm, 100 * Q["fits"][k]["stable"]) for k, nm in (("pca_gmm_line", "line"), ("pca_gmm_curve", "curve"))
           if k in Q["fits"] and "err" not in Q["fits"][k] and Q["fits"][k].get("stable") is not None]
    fig.text(131 / W, 1 - 166.0 / H, "g: dots coloured by the best classifier; grey dashed: k-means cut on PC1;" + chr(10)
             + "solid: mixture, straight boundary; dotted: mixture, curved boundary." + chr(10)
             + ("Events keeping their type on bootstrap refits: " + ", ".join(st_) + "." if st_ else ""),
             fontsize=FS_S - 0.3, ha="left", va="center", color=MUTE, linespacing=1.2)
    return fig''')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
