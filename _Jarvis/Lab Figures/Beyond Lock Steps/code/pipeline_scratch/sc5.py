import sys
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import numpy as np
import dsdata

R = dsdata.by_lab(dsdata.load("v6"))
for lab in ("m33", "m61", "m1", "m26", "m60", "m5"):
    r = R[lab]
    c = r.used
    t = r.types(c)
    a, b = r.band
    P = r.csd_peak
    m1, m2 = P[t == 1].mean(axis=0), P[t == 2].mean(axis=0)
    cut = r.hump_cut_row
    best = None
    for lo, hi in ((a, cut), (cut, b + 1)):
        oo, mk = lo + int(np.argmin(m1[lo:hi])), lo + int(np.argmin(m2[lo:hi]))
        if oo == mk or not (m1[oo] < 0 and m2[mk] < 0):
            continue
        g = (m2[oo] - m1[oo]) + (m1[mk] - m2[mk])
        if best is None or g > best[0]:
            best = (g, oo, mk)
    _, o, mm = best
    so, sm = np.maximum(0, -P[:, o]), np.maximum(0, -P[:, mm])
    tot = so + sm
    null = []
    for c0 in (-40, 40):
        w = np.abs(r.t_ms - c0) <= 3
        null.append(np.maximum(0, -r.csd[:, o][:, w].mean(1)) + np.maximum(0, -r.csd[:, mm][:, w].mean(1)))
    fl = np.percentile(np.concatenate(null), 99)
    sc = np.asarray(r.ds3_score[c], float)
    print(lab, c, "band", r.band, "OML row", o, "MML row", mm, "floor %.3f" % fl,
          "| DS1 events: median outer %.3f middle %.3f tot %.3f, over floor %d/%d | DS2 events: median outer %.3f middle %.3f, over floor %d/%d | stored unscorable DS1 %d" % (
              np.median(so[t == 1]), np.median(sm[t == 1]), np.median(tot[t == 1]), (tot[t == 1] > fl).sum(), (t == 1).sum(),
              np.median(so[t == 2]), np.median(sm[t == 2]), (tot[t == 2] > fl).sum(), (t == 2).sum(), (~np.isfinite(sc[t == 1])).sum()))
    print("   DS1 mean profile in band:", np.round(m1[a:b + 1], 2))
    print("   DS2 mean profile in band:", np.round(m2[a:b + 1], 2))
