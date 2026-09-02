#!/usr/bin/env python3
"""
analyze_02_region_paired.py  --  CNO vs Baseline WITHIN each anatomical region.

For each Region x TimeFrame, uses the region-averaged CSD and Voltage per session
(region_paired_wide.csv) and pairs Baseline vs CNO across the mice that have that region
recorded in BOTH sessions. Reports n_pairs, mean paired delta, paired t, exact Wilcoxon,
and Cohen's dz. Regions are only anatomically comparable across mice if labelled
consistently -- and many regions are present in only 1-3 mice, so most rows here are
descriptive/underpowered (n flagged). Output: results_02_region.csv.

Reads region_paired_wide.csv (built by build_tables.py).
"""
import csv, os
import paired_stats as ps

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    rows = []
    with open(os.path.join(HERE,'region_paired_wide.csv'), newline='') as f:
        for r in csv.DictReader(f): rows.append(r)

    # group[(region,tf)] = list of (mouse, deltaCSD, deltaV)
    grp = {}
    for r in rows:
        try: dcsd = float(r['Delta_MeanCSD'])
        except ValueError: dcsd = None
        try: dv = float(r['Delta_MeanVoltage'])
        except ValueError: dv = None
        grp.setdefault((r['Region'], r['TimeFrame']), []).append((r['Mouse'], dcsd, dv))

    out = []
    print("\nCNO vs Baseline within each region (paired region means across mice)")
    print("="*104)
    print(f"{'Region':12} {'TF':4} {'Metric':8} {'n':>3} {'meanDelta':>11} {'SEM':>9} {'t':>7} {'p_t':>7} {'p_wil':>7} {'dz':>6}")
    print("-"*104)
    for (reg, tf), recs in sorted(grp.items()):
        for label, vals in (('CSD',[v[1] for v in recs]), ('Voltage',[v[2] for v in recs])):
            d = [v for v in vals if v is not None]
            if len(d) < 2:
                print(f"{reg:12} {tf:4} {label:8} {len(d):>3}   (n<2, skipped)")
                out.append([reg,tf,label,len(d),'','','','','','']); continue
            de = ps.describe(d); t, df, pt = ps.ttest_rel(d); W, pw = ps.wilcoxon(d); dz = ps.cohen_dz(d)
            flag = '  <-- low n' if len(d) < 4 else ''
            print(f"{reg:12} {tf:4} {label:8} {len(d):>3} {de['mean']:11.2f} {de['sem']:9.2f} "
                  f"{t:7.2f} {pt:7.3f} {pw:7.3f} {dz:6.2f}{flag}")
            out.append([reg,tf,label,len(d),de['mean'],de['sd'],de['sem'],t,pt,pw,dz])
    print("="*104)
    outp = os.path.join(HERE,'results_02_region.csv')
    with open(outp,'w',newline='') as f:
        w = csv.writer(f)
        w.writerow(['Region','TimeFrame','Metric','n_pairs','MeanDelta','SD_Delta','SEM_Delta','t','p_ttest','p_wilcoxon','cohens_dz'])
        w.writerows(out)
    print(f"Saved -> {outp}")
    print("NOTE: region labels must match across mice to be comparable; low-n regions are descriptive only.")

if __name__ == '__main__':
    main()
