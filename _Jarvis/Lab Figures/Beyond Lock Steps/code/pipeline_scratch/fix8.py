import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def patch(name, pairs):
    p = os.path.join(HERE, name)
    s = io.open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert s.count(a) == 1, (name, a[:70], s.count(a))
        s = s.replace(a, b)
    io.open(p, "w", encoding="utf-8").write(s)


patch("deep_figs.py", [
    ('        draw_sinks(ax, info[d["lab"]], first=(i == 0))\n',
     '        draw_sinks(ax, info[d["lab"]], first=(i == 0))\n        ax.set_ylim(525, -525)\n        ax.set_xticks([])\n        ax.spines["bottom"].set_visible(False)\n'),
    ('    ax.set_yscale("log")\n    ax.set_xticks([0, 1])',
     '    ax.set_yscale("log")\n    ax.set_yticks([1, 2, 4, 8])\n    ax.set_yticklabels(["1", "2", "4", "8"])\n    ax.minorticks_off()\n    ax.set_ylim(0.4, 9)\n    ax.set_xticks([0, 1])'),
])
patch("deep_qc.py", [
    ("H = 150.0", "H = 158.0"),
    ("fig.text(4 / W, 1 - 107.5 / H,", "fig.text(4 / W, 1 - 153.5 / H,"),
    ('ax = ax_mm(158, 27, 21, 76)\n    G.draw_sinks', 'ax = ax_mm(156, 27, 19, 76)\n    G.draw_sinks'),
    ('"(99th percentile of the mean\'s |CSD| more than 30 ms from the DS peak); ticks at the right: sink centroid above the floor.",',
     '"(99th percentile of the" + chr(10) + "mean\'s |CSD| more than 30 ms from the DS peak); ticks at the right: sink centroid above the floor.",'),
    ("G.letter(fig, H, 2, 112, \"e\")\n    ax = ax_mm(13, 119, 60, 22)", "G.letter(fig, H, 2, 116, \"e\")\n    ax = ax_mm(13, 123, 60, 20)"),
    ("G.letter(fig, H, 80, 112, \"f\")\n    ax = ax_mm(104, 119, 75, 22)", "G.letter(fig, H, 80, 116, \"f\")\n    ax = ax_mm(104, 123, 75, 20)"),
])
print("ok")
