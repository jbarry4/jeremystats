import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_figs.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (a[:60], s.count(a))
    s = s.replace(a, b)


a0 = s.index('    fig.text(77.0 / W, 1 - 71.5 / H, "Recordings with two families')
a1 = s.index("    # f  how far out DS1's sink sits from DS2's")
new = '''    fig.text(77.0 / W, 1 - 71.5 / H, "Where each family's sink sits, in the six recordings with two families",
             fontsize=FS, ha="left", va="center")
    info = {}
    for d in use:
        info[d["lab"]] = families(d)
    from scipy.interpolate import PchipInterpolator
    for i, d in enumerate(res):
        I = info[d["lab"]]
        ax = ax_mm(fig, H, 78 + i * 11.4, 80, 10.0, 36)
        fine = np.linspace(I["dep"][0], I["dep"][-1], 400)
        for c, col, sgn in ((2, C_DS2, 1.0), (1, C_DS1, -1.0)):
            sink = np.maximum(PchipInterpolator(I["dep"], np.maximum(-I["prof"][c], 0.0))(fine), 0.0)
            ax.fill_betweenx(fine, 0, sgn * sink, color=col, alpha=0.85, lw=0)
            for y in I["cen"][c]:
                if abs(y) <= 690:
                    ax.plot([sgn * 0.04, sgn * 1.08], [y, y], color="white", lw=1.3, solid_capstyle="butt")
                    ax.plot([sgn * 0.04, sgn * 1.08], [y, y], color=INK, lw=0.5, solid_capstyle="butt")
        ax.axvline(0, color=INK, lw=0.5)
        ax.axhline(0, color=MUTE, lw=0.4, ls=(0, (2, 2)), zorder=0)
        ax.set_xlim(-1.12, 1.12)
        ax.set_ylim(700, -700)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_visible(False)
        if i == 0:
            ax.set_yticks([-600, -300, 0, 300, 600])
            ax.spines["left"].set_visible(True)
            ax.spines["left"].set_position(("outward", 3))
            ax.set_ylabel("Depth from the granule-layer\\nsource (µm)", fontsize=FS)
        else:
            ax.set_yticks([])
        ax.add_patch(Rectangle((0, 1.012), 1, 0.022, transform=ax.transAxes, color=col_of(d), clip_on=False, lw=0))
        ax.text(0.5, 1.05, d["lab"], transform=ax.transAxes, ha="center", va="bottom", fontsize=FS_S)
        ax.text(0.5, -0.02, "DS1 %.0f%%" % I["share"], transform=ax.transAxes, ha="center", va="top", fontsize=FS_S, color=C_DS1)
    fig.text(78.0 / W, 1 - 124.0 / H, "DS1", fontsize=FS_S, color=C_DS1, fontweight="bold", ha="left", va="center")
    fig.text(84.0 / W, 1 - 124.0 / H, "DS2", fontsize=FS_S, color=C_DS2, fontweight="bold", ha="left", va="center")
    fig.text(90.5 / W, 1 - 124.0 / H, "sink only, each scaled to its own deepest;\\nline: the centre of each blade's sink", fontsize=FS_S,
             color=MUTE, ha="left", va="center", linespacing=1.2)
'''
s = s[:a0] + new + s[a1:]
rep('letter(fig, H, 147, 68, "f")\n    ax = ax_mm(fig, H, 158, 80, 22, 36)', 'letter(fig, H, 149, 68, "f")\n    ax = ax_mm(fig, H, 160, 80, 20, 36)')
rep('ax.set_ylabel("DS1 sink farther from the granule\\nlayer than DS2 sink (µm, both blades)", fontsize=FS)',
    'ax.set_ylabel("DS1 sink beyond DS2 sink (µm)", fontsize=FS)')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
