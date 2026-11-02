"""Checks the claims the explainer makes. Run: python3 verify.py"""
import numpy as np
from scipy.signal import hilbert
import cfc_core as c
import make_comodulograms as M

ok = True
def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")

SR = 1000.0
_, lfp = c.pac_lfp(dur=60, srate=SR, fp=8, fa=80, depth=0.8, seed=2)
ph = np.angle(hilbert(c.eegfilt(lfp, SR, 7.75, 8.25)[0]))
am = np.abs(hilbert(c.eegfilt(lfp, SR, 75, 85)[0]))

# 1. mod_index reproduces the literal ModIndex_v2.m loop
nbin = 18; win = 2*np.pi/nbin
pos = -np.pi + np.arange(nbin)*win
ma = np.array([am[(ph < pos[j]+win) & (ph >= pos[j])].mean() for j in range(nbin)])
mi_matlab = (np.log(nbin) - (-np.sum((ma/ma.sum())*np.log(ma/ma.sum()))))/np.log(nbin)
mi_ours, ma_ours = c.mod_index(ph, am)
check("mod_index == literal ModIndex_v2.m loop", abs(mi_ours-mi_matlab) < 1e-12,
      f"{mi_ours:.10f} vs {mi_matlab:.10f}")
check("mean_amp == literal loop", np.allclose(ma, ma_ours), "")

# 2. fast path agrees with the reference path
check("mi_fast == mod_index", abs(c.mi_fast(ph, am)-mi_ours) < 1e-12, f"{c.mi_fast(ph,am):.10f}")

# 3. MI is KL(P||U)/log N
P = ma/ma.sum()
kl = np.sum(P*np.log(P/(1/nbin)))
check("MI == KL(P||U)/log 18", abs(mi_ours - kl/np.log(nbin)) < 1e-12, f"KL={kl:.6f} nats")

# 4. MI is invariant to rescaling the amplitude, and to rotating the phase
check("MI invariant to amplitude scaling", abs(c.mi_fast(ph, am*1000.)-mi_ours) < 1e-9)
rot = np.angle(np.exp(1j*(ph+1.0)))
check("MI invariant to a phase shift (preferred phase is discarded)",
      abs(c.mi_fast(rot, am)-mi_ours) < 5e-4, f"{c.mi_fast(rot,am):.6f}")

# 5. MI bounds
check("0 <= MI <= 1", 0 <= mi_ours <= 1, f"{mi_ours:.5f}")
spike = np.zeros(nbin); spike[3] = 1.0
check("MI == 1 when all amplitude is in one bin",
      abs((np.log(nbin) + np.sum(spike[spike>0]*np.log(spike[spike>0])))/np.log(nbin) - 1) < 1e-12)

# 6. The grid indexing claimed in Notes_ComodAnalysis.m: (4,4) is 2.75 Hz / 40 Hz
px = c.bin_centers(c.PHASE_VEC_LAB, c.PHASE_BW_LAB)
ay = c.bin_centers(c.AMP_VEC_LAB, c.AMP_BW_LAB)
check("Notes_ComodAnalysis.m comment: cell (4,4) = 2.75 Hz phase, 40 Hz amp",
      abs(px[3]-2.75) < 1e-9 and abs(ay[3]-40) < 1e-9, f"{px[3]} Hz / {ay[3]} Hz")
check("grid shape is 51 phase x 37 amp", (len(px), len(ay)) == (51, 37), f"{len(px)} x {len(ay)}")

# 7. R/MATLAB band slices -> the Hz ranges quoted in the write-up
for nm, c1, c2, lo, hi in [("Delta",1,3,1.25,2.25), ("DelTheta",3,9,2.25,5.25),
                           ("Theta",7,23,4.25,12.25), ("Beta",23,40,12.25,20.75)]:
    check(f"band {nm} cols {c1}:{c2}", abs(px[c1-1]-lo)<1e-9 and abs(px[c2-1]-hi)<1e-9,
          f"{px[c1-1]}–{px[c2-1]} Hz")

# 8. eegfilt realised bandwidth is srate-independent and ~0.30 * lower cutoff
from scipy.signal import firls, freqz
def bw(sr, lo, hi):
    o = c.eegfilt_order(sr, lo); o += o % 2
    f, m = c.eegfilt_response(sr, lo, hi)
    b = firls(o+1, list(f), m, fs=sr)
    w, h = freqz(b, worN=60000, fs=sr); H = np.abs(h)**2
    i = np.where(H >= H.max()/2)[0]
    return w[i[-1]]-w[i[0]]
b1, b2 = bw(1000., 80, 90), bw(3255., 80, 90)
check("realised BW independent of srate", abs(b1-b2)/b1 < 0.03, f"{b1:.2f} vs {b2:.2f} Hz")
q = [bw(3255., lo, lo+10)/lo for lo in (80, 120, 200, 280)]
check("realised BW ~ 0.30 x lower cutoff", all(0.27 < x < 0.34 for x in q),
      "ratios " + ", ".join(f"{x:.3f}" for x in q))
check("200 Hz amplitude row is ~60 Hz wide, not 10", bw(3255., 200, 210) > 50,
      f"{bw(3255.,200,210):.1f} Hz")

# 9. the detectability claim
D = c.cached("detectable_region", lambda: None)[0]
FP = np.array([2,4,6,8,10,12,14,17,20,23,26], float)
FA = np.array([30,45,60,80,100,125,150,175,200], float)
i8, i20 = list(FP).index(8), list(FP).index(20)
check("identical coupling, 30 Hz vs 200 Hz amplitude readout differs > 10x",
      D[i8, 0] * 10 < D[i8, -1], f"MI {D[i8,0]:.4f} vs {D[i8,-1]:.4f}")
check("20 Hz phase invisible below ~130 Hz amplitude",
      D[i20, list(FA).index(60)] < 0.002, f"MI {D[i20, list(FA).index(60)]:.5f}")

# 10. spurious MI from transients alone
ied, noi, pac = M.ied(), M.noise_only(), M.pac()
check("sharp transients alone give MI >> the noise floor",
      ied.max() > 10*noi.max(), f"{ied.max():.4f} vs {noi.max():.4f}")
check("but still well below real coupling here", ied.max() < pac.max(),
      f"{ied.max():.4f} vs {pac.max():.4f}")

print("\nALL PASS" if ok else "\nSOMETHING FAILED")
