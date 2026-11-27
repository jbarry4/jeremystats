import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_qc.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


RED = '"#B5361F"'
rep('    ax.axvline(Q["km_cut"], color=MUTE, lw=0.7, ls=(0, (3, 2)))',
    '    used = m in ("pca", "pca_gmm_line", "pca_gmm_curve")\n'
    '    ax.axvline(Q["km_cut"], color=%s if m == "pca" else MUTE, lw=1.4 if m == "pca" else 0.7, ls=(0, (3, 2)))' % RED)
rep('ax.contour(ft["gx"], ft["gy"], ft["P"], levels=[0.5], colors=[INK], linewidths=0.8, linestyles=[ls])',
    'ax.contour(ft["gx"], ft["gy"], ft["P"], levels=[0.5], colors=[%s if m == key else INK], linewidths=1.4 if m == key else 0.8, linestyles=[ls])' % RED)
rep('''    pca_best = m.startswith("pca")
    ax.set_title("PCA plane" + (": best classifier" if pca_best else ""), fontsize=FS, loc="left", pad=3,
                 color="#B5361F" if pca_best else INK)''',
    '''    ax.set_title("PCA plane", fontsize=FS, loc="left", pad=9)
    if used:
        why = "USED: the red boundary classified these events"
    elif m.startswith("pca"):
        why = "NOT USED: %s works on other axes" % NAMES[base]
    else:
        why = "NOT USED: classified by %s" % NAMES[base]
    ax.text(0.0, 1.015, why, transform=ax.transAxes, fontsize=FS_S, fontweight="bold", ha="left", va="bottom",
            color="#B5361F" if used else MUTE)''')
rep('"g: PC1 and PC2 of the events, coloured by the best classifier. Grey dashed: k-means cut on PC1. Solid: two-Gaussian mixture, straight "\n        "boundary. Dotted: mixture, curved boundary.",',
    '"g: PC1 and PC2 of the events, coloured by the best classifier. Dashed: k-means cut on PC1. Solid: two-Gaussian mixture, straight "\n        "boundary. Dotted: mixture, curved boundary. Red and thick: the boundary used.",')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
