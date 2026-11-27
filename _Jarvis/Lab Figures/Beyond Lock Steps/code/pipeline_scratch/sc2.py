import sys
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import numpy as np
import dsdata
import normcurves as N


def tort_main_sink(mu):
    src = int(np.argmax(mu))
    if src < 1:
        return int(np.argmin(mu)), None
    return int(np.argmin(mu[:src])), src


def tort_order(profiles):
    rows = [tort_main_sink(mu)[0] for mu in profiles]
    if len(rows) > 1 and len(set(rows)) == 1:
        n = len(profiles[0])
        return [n - 1 - tort_main_sink(mu[::-1])[0] for mu in profiles], True
    return rows, False


for es in ("v6",):
    for r in dsdata.load(es):
        if not r.ok:
            continue
        c = r.used
        t = r.types(c)
        a, b = r.band
        prof = {k: dsdata.fill_bad(r.csd_peak[t == k].mean(axis=0), r.bad_rows) for k in (1, 2)}
        rows, fl = tort_order([prof[1][a:b + 1], prof[2][a:b + 1]])
        rows = [x + a for x in rows]
        src = [tort_main_sink(prof[k][a:b + 1])[1] for k in (1, 2)]
        k = r.landmarks
        # sink of each type per blade: deepest point within the widened blade rows
        out = []
        for blade in ("upper", "lower"):
            br = r.good(r.blade_rows(blade, 5))
            pos = []
            for kk in (1, 2):
                p = prof[kk][br]
                i = br[int(np.argmin(p))]
                pos.append((i, float(r.v(i, blade)), float(-prof[kk][i])))
            out.append(pos)
        ty = N.typed(r, c)
        print("%-4s %-5s %-16s n1 %3d n2 %3d | tort rows DS1 %d DS2 %d flipped %s src %s | landmarks U %.1f GU %.1f GL %.1f L %.1f | upper: DS1 row %d v %.2f amp %.2f, DS2 row %d v %.2f amp %.2f | lower: DS1 row %d v %.2f amp %.2f, DS2 row %d v %.2f amp %.2f | cen DS1 %s DS2 %s" % (
            r.lab, r.subgroup, c, (t == 1).sum(), (t == 2).sum(), rows[0], rows[1], fl, src, k["U"], k["GU"], k["GL"], k["L"],
            out[0][0][0], out[0][0][1], out[0][0][2], out[0][1][0], out[0][1][1], out[0][1][2],
            out[1][0][0], out[1][0][1], out[1][0][2], out[1][1][0], out[1][1][1], out[1][1][2],
            np.round(ty["cen"].get(1, [np.nan] * 2), 2), np.round(ty["cen"].get(2, [np.nan] * 2), 2)))
