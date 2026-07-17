#!/usr/bin/env python3
"""
build_tables.py  --  Consolidate the raw CSD / Voltage numbers for CNO-vs-Baseline stats.

Reads the project long-format table (DATA_AND_OUTPUT/Prepped_Merged_Long_Format.csv,
itself derived from Final_Matched_and_Collapsed_Stats.xlsx by prep_SPSS_input.py) and
writes clean, analysis-ready tables into this folder. Pure Python standard library only
(no pandas/numpy needed).

Design (paired, within-subject):
  5 PTEN mice, each recorded at BASELINE and under CNO on the SAME chronic probe, so a
  given Channel index is the SAME physical electrode across both sessions -> pair by
  (Mouse, Channel). Values are per-channel laminar profiles at two timeframes:
     GZ = Ground Zero  (IED peak, t=0)  : CSD=CenterSlice, Voltage=GroundZero
     AS = After Spike  (propagation)    : CSD=TimeSlice,   Voltage=AfterSpike
  Statistics use Data_Type == 'Original' (the 32 real/even channels); 'Interpolated_For_Viz'
  rows are excluded (they are odd channels filled from neighbours for smooth plotting).

Outputs (all CSV, in this folder):
  raw_original_long.csv        Original rows only, tidy long format (stats-ready)
  paired_wide_by_channel.csv   one row per (Mouse,Channel,TimeFrame): Base/CNO/Delta of CSD,Voltage,Theta
  region_means_by_session.csv  one row per (Mouse,Group,Region,TimeFrame): channel-averaged CSD,Voltage
  region_paired_wide.csv       one row per (Mouse,Region,TimeFrame): Base/CNO/Delta region means
  session_summary_metrics.csv  one row per (Mouse,Group,TimeFrame): peak/RMS summary features
"""
import csv, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(HERE, '..', 'DATA_AND_OUTPUT', 'Prepped_Merged_Long_Format.csv')

def fnum(x):
    x = (x or '').strip()
    if x == '' or x.lower() in ('nan','na','none'): return None
    try: return float(x)
    except ValueError: return None

def load_original():
    rows = []
    with open(SRC, newline='') as f:
        for r in csv.DictReader(f):
            if r.get('Data_Type') != 'Original':
                continue
            rows.append({
                'Mouse': r['Mouse'], 'Group': r['Group'], 'Type': r['Type'],
                'Session_ID': r['Session_ID'], 'Channel': int(float(r['Channel'])),
                'Region': r['Region'], 'TimeFrame': r['TimeFrame'],
                'CSD_Val': fnum(r['CSD_Val']), 'Voltage_Val': fnum(r['Voltage_Val']),
                'Theta_Val': fnum(r.get('Theta_Val')),
            })
    return rows

def write_csv(path, header, rows):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(header)
        for r in rows: w.writerow(r)
    print(f"  wrote {os.path.basename(path):32s} {len(rows):5d} rows")

def main():
    rows = load_original()
    mice   = sorted({r['Mouse'] for r in rows})
    tfs    = sorted({r['TimeFrame'] for r in rows})
    print(f"Loaded {len(rows)} Original rows | mice={mice} | timeframes={tfs}")

    # ---- raw_original_long.csv ----
    hdr = ['Mouse','Group','Type','Session_ID','Channel','Region','TimeFrame','CSD_Val','Voltage_Val','Theta_Val']
    write_csv(os.path.join(HERE,'raw_original_long.csv'), hdr,
              [[r[c] for c in hdr] for r in
               sorted(rows, key=lambda r:(r['Mouse'],r['Group'],r['TimeFrame'],r['Channel']))])

    # ---- paired_wide_by_channel.csv (pair Base vs CNO by Mouse+Channel+TimeFrame) ----
    idx = {}
    for r in rows:
        idx.setdefault((r['Mouse'],r['Channel'],r['TimeFrame']), {})[r['Group']] = r
    pw = []
    for (mouse,ch,tf), g in sorted(idx.items()):
        b, c = g.get('Base'), g.get('CNO')
        if not (b and c): continue          # need both conditions to pair
        reg = b['Region'] if b['Region']==c['Region'] else f"{b['Region']}|{c['Region']}"
        def d(a,bb): return (a-bb) if (a is not None and bb is not None) else ''
        pw.append([mouse, ch, tf, reg,
                   nz(b['CSD_Val']), nz(c['CSD_Val']), d(c['CSD_Val'],b['CSD_Val']),
                   nz(b['Voltage_Val']), nz(c['Voltage_Val']), d(c['Voltage_Val'],b['Voltage_Val']),
                   nz(b['Theta_Val']), nz(c['Theta_Val']), d(c['Theta_Val'],b['Theta_Val'])])
    write_csv(os.path.join(HERE,'paired_wide_by_channel.csv'),
              ['Mouse','Channel','TimeFrame','Region',
               'Base_CSD','CNO_CSD','Delta_CSD','Base_Voltage','CNO_Voltage','Delta_Voltage',
               'Base_Theta','CNO_Theta','Delta_Theta'], pw)

    # ---- region_means_by_session.csv ----
    reg_idx = {}
    for r in rows:
        reg_idx.setdefault((r['Mouse'],r['Group'],r['Region'],r['TimeFrame']), []).append(r)
    rm = []
    for (mouse,grp,reg,tf), rs in sorted(reg_idx.items()):
        csd = [x['CSD_Val'] for x in rs if x['CSD_Val'] is not None]
        vlt = [x['Voltage_Val'] for x in rs if x['Voltage_Val'] is not None]
        rm.append([mouse,grp,reg,tf,len(rs), mean_or(csd), mean_or(vlt)])
    write_csv(os.path.join(HERE,'region_means_by_session.csv'),
              ['Mouse','Group','Region','TimeFrame','nChannels','Mean_CSD','Mean_Voltage'], rm)

    # ---- region_paired_wide.csv ----
    rmi = {}
    for row in rm:
        mouse,grp,reg,tf,ncnl,mcsd,mv = row
        rmi.setdefault((mouse,reg,tf), {})[grp] = (mcsd,mv)
    rp = []
    for (mouse,reg,tf), g in sorted(rmi.items()):
        if 'Base' not in g or 'CNO' not in g: continue
        (bc,bv),(cc,cv) = g['Base'], g['CNO']
        rp.append([mouse,reg,tf, bc,cc, sub(cc,bc), bv,cv, sub(cv,bv)])
    write_csv(os.path.join(HERE,'region_paired_wide.csv'),
              ['Mouse','Region','TimeFrame','Base_MeanCSD','CNO_MeanCSD','Delta_MeanCSD',
               'Base_MeanVoltage','CNO_MeanVoltage','Delta_MeanVoltage'], rp)

    # ---- session_summary_metrics.csv (per session laminar summary features) ----
    ss_idx = {}
    for r in rows:
        ss_idx.setdefault((r['Mouse'],r['Group'],r['TimeFrame']), []).append(r)
    ss = []
    for (mouse,grp,tf), rs in sorted(ss_idx.items()):
        csd = [x['CSD_Val'] for x in rs if x['CSD_Val'] is not None]
        vlt = [x['Voltage_Val'] for x in rs if x['Voltage_Val'] is not None]
        ss.append([mouse,grp,tf,len(rs),
                   mn(csd), mx(csd), maxabs(csd), rms(csd),
                   mn(vlt), mx(vlt), maxabs(vlt), rms(vlt)])
    write_csv(os.path.join(HERE,'session_summary_metrics.csv'),
              ['Mouse','Group','TimeFrame','nChannels',
               'PeakSink_CSD','PeakSource_CSD','MaxAbs_CSD','RMS_CSD',
               'PeakNeg_Voltage','PeakPos_Voltage','MaxAbs_Voltage','RMS_Voltage'], ss)
    print("Done.")

# small helpers
def nz(x): return '' if x is None else x
def sub(a,b): return (a-b) if (a not in ('',None) and b not in ('',None)) else ''
def mean_or(v): return st.mean(v) if v else ''
def mn(v): return min(v) if v else ''
def mx(v): return max(v) if v else ''
def maxabs(v): return max(abs(x) for x in v) if v else ''
def rms(v): return (sum(x*x for x in v)/len(v))**0.5 if v else ''

if __name__ == '__main__':
    main()
