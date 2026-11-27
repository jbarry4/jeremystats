"""Quality check round 4: the conventional boundaries (g) beside boundaries
chosen to maximise the separation index (h), and how far the events move."""
import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_qc.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('quality_check_round3"', 'quality_check_round4"')
rep("H = 186.0", "H = 192.0")
rep('         "pca_gmm_line": "PCA, mixture (line)", "pca_gmm_curve": "PCA, mixture (curve)"}',
    '         "pca_gmm_line": "PCA, mixture (line)", "pca_gmm_curve": "PCA, mixture (curve)",\n'
    '         "opt_line": "PCA, index-optimised (line)", "opt_curve": "PCA, index-optimised (curve)"}')
rep('PCA2 = pickle.load(open(os.path.join(HERE, "deep_pca2_v6.pkl"), "rb"))',
    'PCA2 = pickle.load(open(os.path.join(HERE, "deep_pca2_v6.pkl"), "rb"))\nOPT = pickle.load(open(os.path.join(HERE, "deep_opt_v6.pkl"), "rb"))')
rep('G.letter(fig, H, 2, 118, "e")\n    ax = ax_mm(13, 126, 40, 32)', 'G.letter(fig, H, 2, 118, "e")\n    ax = ax_mm(12, 126, 27, 32)')
rep('G.letter(fig, H, 58, 118, "f")\n    ax = ax_mm(88, 126, 38, 32)', 'G.letter(fig, H, 43, 118, "f")\n    ax = ax_mm(79, 126, 27, 32)')
rep('G.letter(fig, H, 131, 118, "g")\n    ax = ax_mm(142, 126, 37, 32)', 'G.letter(fig, H, 109, 118, "g")\n    ax = ax_mm(115, 126, 29, 32)')
rep('''            if suf and b.startswith("pca_gmm"):
                continue
            ee = d["splits"].get(b + suf, {})''',
    '''            if suf and (b.startswith("pca_gmm") or b.startswith("opt_")):
                continue
            ee = d["splits"].get(b + suf, {}) if not b.startswith("opt_") else (OPT.get(d["gid"], {}).get("fits") or {}).get(b, {"err": 1})
            if b.startswith("opt_"):
                mk = "*"''')
rep('ax.set_title("All 17 classifiers", fontsize=FS, loc="left", pad=3)', 'ax.set_title("17 classifiers + 2 optimised", fontsize=FS, loc="left", pad=3)')
rep('ax.set_xlabel("DS1–DS2 separation index", fontsize=FS)', 'ax.set_xlabel("Separation index", fontsize=FS)\n    ax.set_xticks([0, 0.5, 1])')
rep('ax.set_title("PCA plane", fontsize=FS, loc="left", pad=9)', 'ax.set_title("Conventional", fontsize=FS, loc="left", pad=9)')
rep('''        "boundary. Dotted: mixture, curved boundary. Red and thick: the boundary used.",''',
    '''        "boundary. Dotted: mixture, curved boundary. Red and thick: the boundary used.",
        "h: the same plane, coloured by the curve chosen to maximise the separation index (each type 5% of events or more). Solid: optimised "
        "line. Dotted: optimised curve. Black rings: events whose type differs from g.",
        "    ★ in f: the two optimised boundaries; they are shown for comparison and are not eligible as the best classifier. Held out: fitted "
        "on a random half of the events, scored on the other half (mean of 5).",''')
rep('''    for i_, t_ in enumerate(notes):''',
    '''    # h  the other way round: boundaries chosen for the index
    G.letter(fig, H, 147, 118, "h")
    ax = ax_mm(152, 126, 28, 32)
    O = (OPT.get(d["gid"], {}).get("fits") or {})
    oc = O.get("opt_curve") or {}
    PURPLE = "#6A3D9A"
    if "types" in oc:
        to = oc["types"]
        ax.scatter(X[:, 0], X[:, 1], s=2.2, c=np.where(to == 1, C_DS1, C_DS2), linewidth=0, alpha=0.8, rasterized=True)
        diff = to != ty
        if diff.mean() > 0.5:
            diff = ~diff
        ax.scatter(X[diff, 0], X[diff, 1], s=7, facecolor="none", edgecolor=INK, linewidth=0.35, rasterized=True)
        for key, ls in (("opt_line", "-"), ("opt_curve", (0, (1, 1.2)))):
            ft = O.get(key) or {}
            if "F" in ft:
                ax.contour(ft["gx"], ft["gy"], ft["F"], levels=[0.0], colors=[PURPLE], linewidths=1.1, linestyles=[ls])
        ax.set_xlim(X[:, 0].min(), X[:, 0].max())
        ax.set_ylim(X[:, 1].min(), X[:, 1].max())
        ho = "held out %.2f" % oc["heldout"] if oc.get("heldout") is not None else "not held out"
        ax.text(0.0, 1.015, "index %.2f to %.2f (%s)" % (e["si"], oc["si"], ho), transform=ax.transAxes, fontsize=FS_S - 0.3,
                fontweight="bold", ha="left", va="bottom", color=PURPLE)
        ax.set_xlabel("PC1" + chr(10) + "%d events (%.0f%%) change type" % (int(diff.sum()), 100.0 * diff.mean()), fontsize=FS_S)
    else:
        ax.text(0.5, 0.5, "no boundary leaves" + chr(10) + "5% of events a side", transform=ax.transAxes, ha="center", va="center",
                fontsize=FS_S, color=MUTE)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Optimised for the index", fontsize=FS, loc="left", pad=9)
    for i_, t_ in enumerate(notes):''')
rep("fig.text(4 / W, 1 - (169.5 + 3.6 * i_) / H, t_,", "fig.text(4 / W, 1 - (168.5 + 3.4 * i_) / H, t_,")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
