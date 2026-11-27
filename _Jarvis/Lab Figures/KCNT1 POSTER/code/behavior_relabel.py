"""Re-render the v2 behavior figure WITH outliers (56 mice) for the poster, changing only two axis labels:
panel b 'Change in shocks per turn / from own day-1 mean' -> 'Δ shocks per turn / (vs. day 1)', and panel c's
'Change in shocks per turn' -> 'Δ shocks per turn'. Everything else is poster_fig_v2.py as the user left it.
usage: python -I behavior_relabel.py OUTDIR
"""
import os
import sys

SRC = (r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1 POSTER\Poster Resources\Behavior"
       r"\poster_fig_v2.py")
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
os.environ["LAB_FIGURES"] = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures"
os.environ["POSTER_OUT"] = out
s = open(SRC, encoding="utf-8").read()
reps = [
    (r'ax.set_ylabel("Change in shocks per turn\nfrom own day-1 mean")',
     'ax.set_ylabel("\u0394 shocks per turn\\n(vs. day 1)")'),
    (r'ax.set_ylabel("Change in shocks per turn\n(day 2',
     r'ax.set_ylabel("Δ shocks per turn\n(day 2'),
    ('for TAG, DROP in (("without_outliers", OUTLIERS), ("with_outliers", set())):',
     'for TAG, DROP in (("with_outliers", set()),):'),
]
for a, b in reps:
    assert s.count(a) == 1, a
    s = s.replace(a, b)
g = {"__file__": SRC, "__name__": "__main__"}
exec(compile(s, SRC, "exec"), g)
