"""Round 7: the row with the highest separation index is marked; a sink
under its noise floor gets a faint tick at its peak; DS1 and DS2 ticks sit
side by side, never on top of each other."""
import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_qc5.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


GREEN = "#1B7F4B"
rep('quality_check_round6"', 'quality_check_round7"')
rep("            pk.append(float(sk.max()))\n", "            pk.append(float(sk.max()))\n            pd_.append(float(out[\"dep\"][l_:h_][int(np.argmax(sk))]))\n")
rep("        cs, pk = [], []\n        for l_, h_ in ((0, cut), (cut, rows.size)):", "        cs, pk, pd_ = [], [], []\n        for l_, h_ in ((0, cut), (cut, rows.size)):")
rep('        out["cen"][c], out["peak"][c] = cs, pk\n    out["clear"] = [out["peak"][1][b_]',
    '        out["cen"][c], out["peak"][c] = cs, pk\n        out.setdefault("pkdep", {})[c] = pd_\n    out["clear"] = [out["peak"][1][b_]')
rep('''        for y in I["cen"][c]:
            if y is not None:
                ax.plot([1.0, 1.1], [y, y], color=col, lw=1.4, solid_capstyle="butt", clip_on=False)
    ax.set_xlim(0, 1.05)
    ax.set_xticks([0])''',
    '''        x0 = 1.0 if c == 2 else 1.13
        for b_, y in enumerate(I["cen"][c]):
            if y is not None:
                ax.plot([x0, x0 + 0.1], [y, y], color=col, lw=1.4, solid_capstyle="butt", clip_on=False)
            else:
                ax.plot([x0, x0 + 0.1], [I["pkdep"][c][b_]] * 2, color=col, lw=1.4, alpha=0.3, solid_capstyle="butt", clip_on=False)
    ax.set_xlim(0, 1.05)
    ax.set_xticks([0])''')
rep("def row(fig, y0, d, num, title, sub, colr, ty, order_x, plane, heads, ext):", "def row(fig, y0, d, num, title, sub, colr, ty, order_x, plane, heads, ext, badge=None):")
rep('''    fig.text(7 / W, 1 - (y0 + 1.6) / H, "%d   %s" % (num, title), fontsize=7.5, fontweight="bold", ha="left", va="center", color=colr)''',
    '''    fig.text(7 / W, 1 - (y0 + 1.6) / H, "%d   %s" % (num, title), fontsize=7.5, fontweight="bold", ha="left", va="center", color=colr)
    if badge:
        fig.text(179 / W, 1 - (y0 + 1.6) / H, badge, fontsize=6.5, fontweight="bold", ha="right", va="center", color="white",
                 bbox=dict(boxstyle="round,pad=0.35", fc="GREENCOL", ec="none"))
        fig.add_artist(Rectangle((2.2 / W, 1 - (y0 + 62.0) / H), 0.8 / W, 62.0 / H, color="GREENCOL", lw=0, transform=fig.transFigure))'''.replace("GREENCOL", GREEN))
rep('''    ext = extent(d, ty)\n''', '''    ext = extent(d, ty)
    # which of the three has the highest index (a row must be eligible: each type 5%% of events or more)
    cand_ = [(k, d["splits"][k]) for k in ON_PLANE if k in d["splits"] and "err" not in d["splits"][k] and d["splits"][k].get("si") is not None]
    ok_ = [c for c in cand_ if eligible(c[1], d["n"])]
    e2_ = max(ok_ or cand_, key=lambda c: c[1]["si"])[1]
    oc_ = O.get("opt_curve") or {}
    sis = {1: e["si"], 2: e2_["si"] if eligible(e2_, d["n"]) else None, 3: oc_.get("si")}
    top_ = max(v for v in sis.values() if v is not None)
    win = [k for k, v in sis.items() if v is not None and v >= top_ - 0.005]
    badge = lambda k: None if k not in win else ("HIGHEST SEPARATION INDEX" if len(win) == 1 else "HIGHEST SEPARATION INDEX (TIE: ROWS %%s)" %% " AND ".join(str(x) for x in win))
    bits = ["row %%d: %%s" %% (k, "not eligible" if v is None else "%%.2f" %% v) for k, v in sis.items()]
    if oc_.get("heldout") is not None:
        bits[2] += " (%%.2f held out)" %% oc_["heldout"]
    fig.text(179 / W, 1 - 5 / H, "Separation index   " + "     ".join(bits), fontsize=FS, ha="right", va="center", color=INK)
    if sis[2] is not None and sis[3] is not None and sis[2] > sis[3] + 0.005:
        fig.text(179 / W, 1 - 12.5 / H, "Row 2 scores above row 3: its boundary is a shape the search in row 3 does not cover.", fontsize=FS_S,
                 ha="right", va="center", color="%s")
''' % "#B5361F")
rep("RED, ty, np.asarray(e[\"x\"], float), plane1, True, ext)", "RED, ty, np.asarray(e[\"x\"], float), plane1, True, ext, badge(1))")
rep("INK, t2, Q[\"X\"][:, 0], plane2, False, ext)", "INK, t2, Q[\"X\"][:, 0], plane2, False, ext, badge(2))")
rep("PURPLE, t3, Q[\"X\"][:, 0], plane3, False, ext)", "PURPLE, t3, Q[\"X\"][:, 0], plane3, False, ext, badge(3))")
rep('"    Ticks at the right: sink centroid above the floor, over the widened range."]',
    '"    Ticks at the right: sink centroid above the floor, over the widened range (DS2 inner column, DS1 outer). A faint tick: that sink is '
    'under its noise floor; the tick marks its peak.",\n'
    '        "Green label and bar: the row with the highest separation index among eligible rows. Row 3 was fitted to maximise that index, so its '
    'held-out value is the fair one to set against rows 1 and 2."]')
rep("H = 293.0", "H = 297.0")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
