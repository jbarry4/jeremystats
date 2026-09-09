"""FIG 4 — from the 18 numbers to one number.

MI is the Kullback–Leibler divergence of P from the uniform distribution,
divided by log(18) so it lands on [0, 1]:

    H(P) = -sum P_j log P_j
    MI   = (log N - H(P)) / log N  =  KL(P || U) / log N
"""
import numpy as np, matplotlib.pyplot as plt
from scipy.signal import hilbert
import cfc_core as c
from style import *

SR = 1000.0
depths = np.linspace(0, 1, 17)
mis, ents = [], []
for d in depths:
    t, lfp = c.pac_lfp(dur=120, srate=SR, fp=8, fa=80, depth=d,
                       slow_amp=1, fast_amp=0.45, noise=0.45, seed=3)
    ph = np.angle(hilbert(c.eegfilt(lfp, SR, 7.75, 8.25)[0]))
    am = np.abs(hilbert(c.eegfilt(lfp, SR, 75, 85)[0]))
    mi, ma = c.mod_index(ph, am)
    P = ma / ma.sum()
    mis.append(mi); ents.append(-(P * np.log(P)).sum())
mis, ents = np.array(mis), np.array(ents)

fig, (a0, a1) = plt.subplots(1, 2, figsize=(7.8, 3.1))

# (a) the entropy budget
a0.barh([1], [np.log(18)], color="#dde7f5", height=0.45)
a0.barh([0], [ents[-1]], color=C[0], height=0.45)
a0.barh([0], [np.log(18) - ents[-1]], left=[ents[-1]], color=C[1], height=0.45)
a0.set_yticks([0, 1]); a0.set_yticklabels(["observed  H(P)", "uniform  log 18"])
a0.set_xlim(0, np.log(18) * 1.02); a0.set_xlabel("entropy (nats)")
a0.set_title("MI is the missing entropy, as a fraction")
a0.text(ents[-1] / 2, 0, f"H = {ents[-1]:.3f}", va="center", ha="center",
        color="white", fontsize=8, fontweight="600")
a0.text(np.log(18) - 0.005, 0.55, f"KL = {np.log(18)-ents[-1]:.3f} nats\nMI = KL / log 18 = {mis[-1]:.4f}",
        va="bottom", ha="right", color=C[1], fontsize=8.5, fontweight="600")
a0.text(np.log(18) / 2, 1, "log 18 = 2.890", va="center", ha="center",
        color=INK2, fontsize=8)
a0.spines["left"].set_visible(False); a0.tick_params(axis="y", length=0)
tag(a0, "a")

# (b) MI against the thing that actually changed
a1.plot(depths, mis, "-o", color=C[0], ms=4)
for d, lab in [(0.0, "flat"), (0.35, "weak"), (1.0, "strong")]:
    i = int(np.argmin(np.abs(depths - d)))
    a1.plot(depths[i], mis[i], "o", ms=9, mfc="none", mec=C[1], mew=2)
    a1.annotate(f"{lab}\nMI={mis[i]:.4f}", (depths[i], mis[i]),
                textcoords="offset points", xytext=(6, -18 if d else 6),
                fontsize=7.5, color=C[1])
a1.set_xlabel("true modulation depth of the simulated signal")
a1.set_ylabel("MI")
a1.set_title("MI grows with coupling — but not linearly, and not on a fixed scale")
a1.grid(axis="y")
tag(a1, "b")
note(fig, "MI is dimensionless and scale-free: multiply the whole amplitude envelope by 1000 and MI does not move.\n"
          "That also means an MI of 0.04 has no absolute meaning — it is only interpretable against a null "
          "computed on the same recording (Fig 9).", y=-0.02)
plt.tight_layout()
plt.savefig("figures/fig04_entropy_to_mi.png", bbox_inches="tight", dpi=170)
print("fig04 done", mis[-1])
