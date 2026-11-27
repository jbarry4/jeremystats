import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import style as S
import cells as Ce

OUT = sys.argv[1]
fig = S.figure(9.0, 4.2)
ax = S.ax_at(fig, 0, 0, 9.0, 4.2)
ax.set_xlim(0, 9.0); ax.set_ylim(4.2, 0); ax.set_aspect("equal"); ax.axis("off")
# the three groups, as on a depth axis (y down): somata at the given rows
Ce.group(ax, "pyr", 0.6, 0.35, 2.0)
Ce.group(ax, "gc_up", 0.6, 3.0, 2.15)
Ce.group(ax, "gc_down", 0.6, 3.25, 4.1)
ax.text(1.2, 0.35, "pyr soma", va="center", fontsize=9); ax.text(1.2, 3.0, "gc_up soma", va="center", fontsize=9)
ax.text(1.2, 3.25, "gc_down soma", va="center", fontsize=9)
for y in (0.35, 2.0, 3.0, 2.15, 3.25, 4.1):
    ax.axhline(y, xmin=0.0, xmax=0.16, c="k", lw=0.3)
# bent along a blade
c = (4.0, 2.2)
th = 120
while th < 240:
    _, th1 = Ce.group_arc(ax, "gc_up", c, 0.9, 1.55, th)
    th = th1 + 1
from matplotlib.patches import Circle
ax.add_patch(Circle(c, 0.9, fc="none", ec="k", lw=0.3)); ax.add_patch(Circle(c, 1.55, fc="none", ec="k", lw=0.3))
# SST and PV at two sizes
Ce.sst(ax, Ce.frame((6.4, 1.0), (0, -0.09), (0.09, 0)))
Ce.pv(ax, Ce.frame((8.0, 1.6), (0, -0.09), (0.09, 0)))
Ce.sst(ax, Ce.frame((6.4, 3.3), (0, -0.05), (0.05, 0)), spine_lw=0.35)
Ce.pv(ax, Ce.frame((8.0, 3.6), (0, -0.05), (0.05, 0)))
S.save(fig, OUT)
print("ok", Ce.soma_xs("gc_up"), Ce.extent("sst"), Ce.extent("pv"))
