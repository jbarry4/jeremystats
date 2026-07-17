#!/usr/bin/env python3
"""
analyze_01_session_summary_paired.py  --  HEADLINE test: CNO vs Baseline on per-session
laminar summary features (n = 5 mice, paired / within-subject).

For each summary metric (peak sink/source CSD, max|CSD|, RMS CSD, and the voltage
equivalents) and each timeframe (GZ = IED peak, AS = after-spike), it pairs each mouse's
Baseline and CNO value, then reports Baseline mean +/- SD, CNO mean +/- SD, the mean
paired change (CNO - Baseline), a paired t-test, an EXACT Wilcoxon signed-rank test, and
Cohen's dz. Output: results_01_session_summary.csv + a printed table.

Reads session_summary_metrics.csv (built by build_tables.py).
"""
import csv, os
import paired_stats as ps

HERE = os.path.dirname(os.path.abspath(__file__))
METRICS = ['PeakSink_CSD','PeakSource_CSD','MaxAbs_CSD','RMS_CSD',
           'PeakNeg_Voltage','PeakPos_Voltage','MaxAbs_Voltage','RMS_Voltage']
TFS = ['GZ','AS']

def load():
    rows = []
    with open(os.path.join(HERE,'session_summary_metrics.csv'), newline='') as f:
        for r in csv.DictReader(f): rows.append(r)
    return rows

def main():
    rows = load()
    # index[(mouse,group,tf)] = row
    idx = {(r['Mouse'],r['Group'],r['TimeFrame']): r for r in rows}
    mice = sorted({r['Mouse'] for r in rows})
    out = []
    print(f"\nPaired CNO vs Baseline on session summary metrics  (mice: {mice}, n={len(mice)})")
    print("="*118)
    print(f"{'TimeFrame':9} {'Metric':16} {'Base(mean+/-SD)':>20} {'CNO(mean+/-SD)':>20} "
          f"{'d(CNO-Base)':>12} {'t':>7} {'p_t':>7} {'p_wilcox':>9} {'dz':>6}")
    print("-"*118)
    for tf in TFS:
        for m in METRICS:
            base, cno, dif, paired_mice = [], [], [], []
            for mouse in mice:
                b = idx.get((mouse,'Base',tf)); c = idx.get((mouse,'CNO',tf))
                if not (b and c): continue
                try: bv = float(b[m]); cv = float(c[m])
                except (ValueError, KeyError): continue
                base.append(bv); cno.append(cv); dif.append(cv-bv); paired_mice.append(mouse)
            if len(dif) < 2: continue
            db, dc, dd = ps.describe(base), ps.describe(cno), ps.describe(dif)
            t, df, pt = ps.ttest_rel(dif); W, pw = ps.wilcoxon(dif); dz = ps.cohen_dz(dif)
            print(f"{tf:9} {m:16} {db['mean']:9.1f}+/-{db['sd']:<7.1f} {dc['mean']:9.1f}+/-{dc['sd']:<7.1f} "
                  f"{dd['mean']:12.1f} {t:7.2f} {pt:7.3f} {pw:9.3f} {dz:6.2f}")
            out.append([tf, m, len(dif), db['mean'], db['sd'], dc['mean'], dc['sd'],
                        dd['mean'], dd['sd'], dd['sem'], t, df, pt, W, pw, dz,
                        ';'.join(paired_mice)])
    print("="*118)
    print("Reading: p_t = paired t-test (two-sided), p_wilcox = exact Wilcoxon signed-rank (two-sided),")
    print("dz = Cohen's dz. With n=5, Wilcoxon's smallest possible two-sided p is 0.0625 -> it can NEVER")
    print("reach p<0.05; treat these as effect sizes + trends, not a hard significance filter (see README).")
    outp = os.path.join(HERE,'results_01_session_summary.csv')
    with open(outp,'w',newline='') as f:
        w = csv.writer(f)
        w.writerow(['TimeFrame','Metric','n_pairs','Base_mean','Base_SD','CNO_mean','CNO_SD',
                    'MeanDelta','SD_Delta','SEM_Delta','t','df','p_ttest','W','p_wilcoxon','cohens_dz','mice'])
        w.writerows(out)
    print(f"\nSaved -> {outp}")

if __name__ == '__main__':
    main()
