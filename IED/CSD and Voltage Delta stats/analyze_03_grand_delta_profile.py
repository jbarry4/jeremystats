#!/usr/bin/env python3
"""
analyze_03_grand_delta_profile.py  --  laminar DELTA profile (CNO - Baseline) down the probe.

For each Channel (even/real channels) x TimeFrame, averages the paired within-mouse delta
(CNO - Baseline) across mice and gives SEM and a paired t-test vs 0. This is the depth
profile of the CNO effect -- the "grand delta" as a function of electrode depth. Because a
given Channel index is the same physical electrode across a mouse's two sessions, the
pairing is valid; whether channel index N is the same ANATOMY across different mice depends
on probe placement (see README pitfalls). Output: results_03_grand_delta_profile.csv.

Reads paired_wide_by_channel.csv (built by build_tables.py).
"""
import csv, os
import paired_stats as ps

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    rows = []
    with open(os.path.join(HERE,'paired_wide_by_channel.csv'), newline='') as f:
        for r in csv.DictReader(f): rows.append(r)

    # group[(tf,channel)] = {'CSD':[deltas], 'Voltage':[deltas], 'regions':set}
    grp = {}
    for r in rows:
        key = (r['TimeFrame'], int(r['Channel']))
        g = grp.setdefault(key, {'CSD':[], 'Voltage':[], 'regions':set()})
        for col, lab in (('Delta_CSD','CSD'), ('Delta_Voltage','Voltage')):
            try: g[lab].append(float(r[col]))
            except ValueError: pass
        g['regions'].add(r['Region'])

    out = []
    print("\nGrand laminar delta profile (CNO - Baseline), averaged across mice")
    print("="*100)
    print(f"{'TF':4} {'Ch':>3} {'n':>3} {'dCSD(mean)':>11} {'SEM':>8} {'p':>7}   {'dV(mean)':>11} {'SEM':>8} {'p':>7}  Region(s)")
    print("-"*100)
    for (tf, ch) in sorted(grp.keys()):
        g = grp[(tf,ch)]
        dcsd, dv = g['CSD'], g['Voltage']
        cs, vs = ps.describe(dcsd), ps.describe(dv)
        _,_,pc = ps.ttest_rel(dcsd); _,_,pv = ps.ttest_rel(dv)
        regs = '/'.join(sorted(g['regions']))
        print(f"{tf:4} {ch:>3} {cs['n']:>3} {cs['mean']:11.2f} {cs['sem']:8.2f} {pc:7.3f}   "
              f"{vs['mean']:11.2f} {vs['sem']:8.2f} {pv:7.3f}  {regs}")
        out.append([tf, ch, cs['n'], cs['mean'], cs['sem'], pc, vs['mean'], vs['sem'], pv, regs])
    print("="*100)
    outp = os.path.join(HERE,'results_03_grand_delta_profile.csv')
    with open(outp,'w',newline='') as f:
        w = csv.writer(f)
        w.writerow(['TimeFrame','Channel','n_mice','MeanDelta_CSD','SEM_CSD','p_CSD',
                    'MeanDelta_Voltage','SEM_Voltage','p_Voltage','Regions'])
        w.writerows(out)
    print(f"Saved -> {outp}")
    print("NOTE: per-channel p-values are UNCORRECTED (many channels x 2 timeframes). Use for the")
    print("depth PROFILE / effect pattern; apply FDR or treat as descriptive before claiming per-channel hits.")

if __name__ == '__main__':
    main()
