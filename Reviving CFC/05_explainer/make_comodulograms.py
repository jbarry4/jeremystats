"""Builds the comodulograms the later figures reuse, on the lab's own grid
(Phase 1:0.5:26 BW 0.5, Amp 20:5:200 BW 10 — step04_newFCSE.m).
Results are cached in ./_cache so the figure scripts are cheap to re-run.
"""
import numpy as np, time
import cfc_core as c

SR = 1000.0
DUR = 120.0
PV, PBW, AV, ABW = c.PHASE_VEC_LAB, c.PHASE_BW_LAB, c.AMP_VEC_LAB, c.AMP_BW_LAB


def _run(lfp):
    ph, am = c.filter_banks(lfp, SR, PV, PBW, AV, ABW)
    return (c.comodulogram_fast(ph, am),)


def pac():
    """Real theta(8 Hz)–gamma(80 Hz) coupling on a pink-noise background."""
    def f():
        _, lfp = c.pac_lfp(dur=DUR, srate=SR, fp=8, fa=80, depth=0.9,
                           slow_amp=1.0, fast_amp=0.45, noise=0.6, seed=3)
        return _run(lfp)
    return c.cached("comod_pac", f)[0]


def noise_only():
    """No coupling at all: pink noise. Shows the MI floor across the grid."""
    def f():
        lfp = c.pink_noise(int(DUR * SR), SR, seed=11)
        return _run(lfp)
    return c.cached("comod_noise", f)[0]


def ied():
    """Sharp interictal-like transients, no true coupling anywhere."""
    def f():
        _, lfp, _ = c.ied_lfp(dur=DUR, srate=SR, rate=1.5, seed=1, amp=6.0)
        return _run(lfp)
    return c.cached("comod_ied", f)[0]


if __name__ == "__main__":
    for name, fn in [("pac", pac), ("noise", noise_only), ("ied", ied)]:
        t0 = time.time(); m = fn()
        print(f"{name:6s} {m.shape}  max MI={m.max():.4f}  {time.time()-t0:.1f}s")
