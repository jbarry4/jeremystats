"""Round 8: each row also gives the index in each blade; row 3 says what
maximizing the mean of the two blades gives; American spelling."""
import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_qc5.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('quality_check_round7"', 'quality_check_round8"')
rep('OPT = pickle.load(open(os.path.join(HERE, "deep_opt_v6.pkl"), "rb"))',
    '''OPT = pickle.load(open(os.path.join(HERE, "deep_opt_v6.pkl"), "rb"))
OPT2 = pickle.load(open(os.path.join(HERE, "deep_opt2_v6.pkl"), "rb"))


def blade_si(d, ty):
    """The separation index of classification `ty` in each blade (that
    blade's own sink overlap): (upper, lower), or None."""
    Wd = (OPT2.get(d["gid"]) or {}).get("W") or {}
    if "top" not in Wd or "bottom" not in Wd:
        return None
    out = []
    for k in ("top", "bottom"):
        W0 = Wd[k].astype(float).copy()
        np.fill_diagonal(W0, 0.0)
        m = ty == 1
        na, nb = int(m.sum()), int((~m).sum())
        if na < 2 or nb < 2:
            return None
        Wm = W0 @ m
        saa, sab = float(m @ Wm), float((~m) @ Wm)
        sbb = float(W0.sum()) - saa - 2.0 * sab
        out.append(1.0 - (sab / (na * nb)) / ((saa / (na * (na - 1)) + sbb / (nb * (nb - 1))) / 2.0))
    return out''')
rep('''    fig.text(7 / W, 1 - (y0 + 4.6) / H, sub, fontsize=FS_S, ha="left", va="center", color=INK)''',
    '''    bs = blade_si(d, ty)
    if bs is not None:
        sub = sub.replace(".   DS1 ", " (upper blade %.2f, lower blade %.2f, mean %.2f).   DS1 " % (bs[0], bs[1], (bs[0] + bs[1]) / 2.0), 1)
    fig.text(7 / W, 1 - (y0 + 4.6) / H, sub, fontsize=FS_S, ha="left", va="center", color=INK)''')
rep('''        row(fig, y, d, 3, "Optimised for the separation index, on the PCA plane: curve",''',
    '''        f4 = (OPT2.get(d["gid"]) or {}).get("fit")
        if f4 is not None:
            same4 = max(np.mean(f4["types"] == oc["types"]), np.mean(f4["types"] != oc["types"]))
            fig.text(179 / W, 1 - (y + 4.6) / H, "Maximizing the mean of the two blade indices instead: %s (mean %.2f, %.2f held out)." % (
                "the same boundary" if same4 > 0.999 else "%.0f%% of events get the same type" % (100 * same4), f4["mean"],
                f4["heldout"] if f4["heldout"] is not None else float("nan")), fontsize=FS_S, ha="right", va="center", color=PURPLE)
        row(fig, y, d, 3, "Optimised for the separation index, on the PCA plane: curve",''')
for a, b in (("Optimised", "Optimized"), ("optimised", "optimized"), ("normalised", "normalized"), ("coloured", "colored"), ("Colours", "Colors"),
             ("colours", "colors"), ("band centre", "band center"), ("analysed", "analyzed"), ("grey:", "gray:"), ("maximise", "maximize")):
    s = s.replace(a, b)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
