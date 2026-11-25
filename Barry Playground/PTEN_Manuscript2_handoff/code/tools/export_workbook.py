"""Build the data workbook: one sheet per analysis, with the per-mouse data and that analysis's tables and statistics.

Per-mouse data come from the intermediate files written by the analysis scripts (WORK) and the inputs.
Tables and key results for each sheet are taken from the matching section of the report (report.md), so the
workbook and the report always agree. Statistics are computed by the analysis scripts named on each sheet and are
stored here as values.
Usage: python tools/export_workbook.py <report.md> <work dir> <out.xlsx>
"""
import sys, re, os, datetime, glob
import numpy as np, pandas as pd, pyreadstat
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

REPORT, W, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PKG)
from config import *

F = 'Arial'
TITLE = Font(name=F, size=14, bold=True); H2 = Font(name=F, size=11, bold=True, color='1F3864')
HDR = Font(name=F, size=10, bold=True); TXT = Font(name=F, size=10); BOLD = Font(name=F, size=10, bold=True)
NOTE = Font(name=F, size=9, italic=True, color='52514E'); CAP = Font(name=F, size=10, italic=True)
FILL = PatternFill('solid', fgColor='E9E8E3'); THIN = Side(style='thin', color='9A9993')
GRP = {'CTL': 'WT', 'WT': 'WT', 'Lo': 'Lo', 'Hi': 'Hi', 'UNK': 'UNK (no histology)'}

rep = open(REPORT).read().split('\n')
def section(start, stop=None):
    """Lines from the heading that starts with `start` up to the next heading at the same or a higher level (or `stop`)."""
    i = next(k for k, l in enumerate(rep) if l.startswith(start)); lvl = len(start) - len(start.lstrip('#'))
    j = len(rep)
    for k in range(i + 1, len(rep)):
        l = rep[k]
        if stop and l.startswith(stop): j = k; break
        if not stop and l.startswith('#') and len(l) - len(l.lstrip('#')) <= lvl: j = k; break
    return rep[i:j]

def clean(s):
    s = s.replace('**', '').replace('`', '').strip()
    return s.strip('*').strip() if s.startswith('*') and s.endswith('*') else s

def num(s):
    t = s.replace('−', '-').replace(',', '')
    try: return float(t) if re.fullmatch(r'-?\d+(\.\d+)?', t) else s
    except ValueError: return s

def blocks(lines):
    """Report tables (with nearby italic caption/notes) and top-level result bullets, in order."""
    out, k = [], 0
    while k < len(lines):
        l = lines[k]
        if l.startswith('|'):
            tab = []
            while k < len(lines) and lines[k].startswith('|'): tab.append(lines[k]); k += 1
            rows = [[c.strip() for c in r.strip().strip('|').split('|')] for r in tab if not re.fullmatch(r'\|[\s\-|:]+\|', r.strip())]
            cap = None
            prev = [x for x in lines[max(0, k - len(tab) - 3):k - len(tab)] if x.strip()]
            if prev and prev[-1].startswith('*') and not prev[-1].startswith('*Figure') and not prev[-1].startswith('**'): cap = clean(prev[-1])
            nb = [j for j in range(k, len(lines)) if lines[j].strip()][:2]
            note = None
            if nb and lines[nb[0]].startswith('*') and not lines[nb[0]].startswith(('*Figure', '**', '*Supplementary')):
                if len(nb) < 2 or not lines[nb[1]].startswith('|'): note = clean(lines[nb[0]])
            out.append(('table', cap, rows, note)); continue
        if l.startswith('- **') or (l.startswith('- ') and not l.startswith('- [')):
            out.append(('bullet', clean(l[2:])));
        elif l.startswith('*Figure') or l.startswith('*Supplementary Figure'):
            out.append(('figure', clean(l)))
        k += 1
    return out

wb = Workbook(); wb.remove(wb.active)

def autosize(ws, maxw=60):
    for col in ws.columns:
        w = 8
        for c in col[:400]:
            if c.value is not None and not (isinstance(c.value, str) and len(c.value) > 90): w = max(w, min(maxw, len(str(c.value)) + 2))
        ws.column_dimensions[get_column_letter(col[0].column)].width = w

def write_df(ws, r, df, title=None, note=None, fmt=None):
    if title: ws.cell(r, 1, title).font = H2; r += 1
    if note: ws.cell(r, 1, note).font = NOTE; r += 1
    for j, c in enumerate(df.columns, 1):
        x = ws.cell(r, j, str(c)); x.font = HDR; x.fill = FILL; x.border = Border(bottom=THIN); x.alignment = Alignment(wrap_text=True, vertical='top')
    for i, row in enumerate(df.itertuples(index=False), r + 1):
        for j, v in enumerate(row, 1):
            if isinstance(v, (np.floating, float)):
                v = None if np.isnan(v) else float(v)
            elif isinstance(v, (np.integer,)): v = int(v)
            elif isinstance(v, (np.bool_, bool)): v = bool(v)
            elif isinstance(v, (pd.Timestamp, datetime.date)): pass
            x = ws.cell(i, j, v); x.font = TXT
            if isinstance(v, float): x.number_format = (fmt or {}).get(df.columns[j - 1], '0.0000')
            if isinstance(v, datetime.date): x.number_format = 'yyyy-mm-dd'
    return r + len(df) + 2

def write_report(ws, r, lines, label='From the report'):
    ws.cell(r, 1, label).font = H2; r += 1
    for b in blocks(lines):
        if b[0] == 'figure':
            ws.cell(r, 1, b[1]).font = NOTE; r += 1
        elif b[0] == 'bullet':
            ws.cell(r, 1, '• ' + b[1]).font = TXT; r += 1
        else:
            _, cap, rows, note = b
            r += 1
            if cap: ws.cell(r, 1, cap).font = CAP; r += 1
            for i, row in enumerate(rows):
                for j, v in enumerate(row, 1):
                    x = ws.cell(r, j, num(clean(v)) if i else clean(v))
                    x.font = HDR if i == 0 else (BOLD if '**' in v else TXT)
                    if i == 0: x.fill = FILL; x.border = Border(bottom=THIN); x.alignment = Alignment(wrap_text=True, vertical='top')
                r += 1
            if note: ws.cell(r, 1, note).font = NOTE; r += 1
            r += 1
    return r + 1

def sheet(name, title, desc, source):
    ws = wb.create_sheet(name)
    ws.cell(1, 1, title).font = TITLE
    ws.cell(2, 1, desc).font = TXT
    ws.cell(3, 1, 'Source: ' + source).font = NOTE
    ws.sheet_view.showGridLines = False
    return ws, 5

# ------------------------------------------------------------------ shared per-mouse info
probe = pd.read_pickle(os.path.join(W, 'probe.pkl'))
mice = probe.drop_duplicates('MouseID')[['MouseID', 'G3', 'pct', 'HBH', 'IED']].copy()
mice['MouseID'] = mice.MouseID.astype(int)
crit, _ = pyreadstat.read_sav(CRIT_SAV); crit = crit.dropna(subset=['MouseID']); crit['MouseID'] = crit.MouseID.astype(int)
dates = pd.read_pickle(os.path.join(W, 'session_dates.pkl'))
dates = dates.rename(columns={'Mouse': 'MouseID', 'File': 'Tracking file', 'date': 'Session date', 'time': 'Session time'})[['MouseID', 'Phase', 'Condition', 'Session date', 'Session time', 'Tracking file']]
csd = pd.read_pickle(os.path.join(PKG, 'work', 'csd3', 'csd3.pkl'))
def grp(g): return GRP.get(g, g)
def add_info(df, key='MouseID'):
    m = mice.rename(columns={'MouseID': key, 'G3': 'Group', 'pct': '% KO', 'HBH': 'Heterotopia', 'IED': 'IED'})
    df = df.merge(m, on=key, how='left'); df['Group'] = df.Group.map(grp)
    return df

# ------------------------------------------------------------------ README
ws = wb.create_sheet('README'); ws.sheet_view.showGridLines = False
ws['A1'] = 'Pten KO mosaicism and spatial accuracy: data and statistics by analysis'; ws['A1'].font = TITLE
ws['A2'] = f'Exported {datetime.date.today():%Y-%m-%d} from the analysis code package (ClaudeAnalsysisCode) and the report (Pten_KO_mosaicism_behavior_report).'; ws['A2'].font = TXT
info = [
    ('Groups', 'WT (control); Pten KO Lo (<15% KO granule cells); Pten KO Hi (>=15%). DKO mice are not included. M27 and M31 have no histology (UNK).'),
    ('IED', '+ = clear IEDs; - = no obvious IEDs; NR = not recorded. In the CSD sheets, IED status is IEDBIN from the CSD file; WT count as IED-negative.'),
    ('Exclusions', 'M6 is excluded from sessions to criterion only. M26 (WT) is excluded from theta CSD (problem after implantation surgery) and kept in behaviour.'),
    ('% KO', 'Behaviour sheets use the project % KO list (M33 = 8.82%). CSD/CNO sheets use Data4Claude.xlsx (M33 = 4.41%) plus M29 = 22.00% and M30 = 5.97%. M33 is Lo either way.'),
    ('Session dates', 'Probe-session dates and times are read from the header of each Bio-Signal Tracker .dat file (%Date.0, %Time.0). CNO behaviour and CSD sessions carry no dates in their files.'),
    ('Statistics', 'Between groups: two-sided Mann-Whitney U. Within groups: paired t-test. Other tests are named on each sheet. Statistics are computed by the scripts named on each sheet and stored as values.'),
    ('Layout', 'Each sheet: title and source, then the tables, figure captions and key results from the matching report section, then the per-mouse data.'),
]
r = 4
for k, v in info:
    ws.cell(r, 1, k).font = BOLD; ws.cell(r, 2, v).font = TXT; r += 1
r += 1; ws.cell(r, 1, 'Sheets').font = H2; r += 1
contents_row = r
ws.column_dimensions['A'].width = 22; ws.column_dimensions['B'].width = 70; ws.column_dimensions['C'].width = 40
CONTENTS = []

# ------------------------------------------------------------------ Mice
ws, r = sheet('Mice', 'Mouse list: group, % KO, IED, heterotopia and inclusion', 'One row per mouse in the behaviour or CSD analyses.', 'probe data (AllProbeSessions.sav), sessions to criterion (ROC_heterotopia_Fixed_hilo.sav), CSD_sansM2.sav, AllProbeSessions_CNO.sav')
M = mice.rename(columns={'G3': 'Group', 'pct': '% KO (behaviour list)', 'HBH': 'Heterotopia', 'IED': 'IED'})
M['Group'] = M.Group.map(grp)
M = M.merge(crit[['MouseID', 'SesstoCriterion']].rename(columns={'SesstoCriterion': 'Sessions to criterion'}), on='MouseID', how='left')
c2 = csd[['pct', 'ied', 'AVG4_base', 'AVG4_cno', 'Goal_base', 'Goal_cno']].copy(); c2['MouseID'] = c2.index.astype(int)
c2['In CSD analyses'] = c2.AVG4_base.notna(); c2['CSD after CNO'] = c2.AVG4_cno.notna(); c2['In CNO behaviour'] = c2.Goal_cno.notna()
c2 = c2.rename(columns={'pct': '% KO (CSD/CNO list)', 'ied': 'IED (CSD file)'})[['MouseID', '% KO (CSD/CNO list)', 'IED (CSD file)', 'In CSD analyses', 'CSD after CNO', 'In CNO behaviour']]
M = M.merge(c2, on='MouseID', how='outer')
M['Group'] = M.Group.fillna('WT'); M.loc[M.MouseID == 26, 'In CSD analyses'] = False
notes = {6: 'Excluded from sessions to criterion', 26: 'Excluded from CSD (problem after implantation surgery); kept in behaviour', 27: 'No histology', 31: 'No histology',
         11: 'CSD only', 13: 'CSD only', 24: 'Phase 9 sessions dated after phase 10 (13 vs 10 June 2024)', 33: '% KO 8.82 (behaviour list) vs 4.41 (CNO file)'}
M['Note'] = M.MouseID.map(notes)
for col in ['In CSD analyses', 'CSD after CNO', 'In CNO behaviour']: M[col] = M[col].fillna(False)
M = M.sort_values(['Group', 'MouseID'])
r = write_df(ws, r, M, fmt={'% KO (behaviour list)': '0.00', '% KO (CSD/CNO list)': '0.00', 'Sessions to criterion': '0', 'IED (CSD file)': '0'})
autosize(ws); CONTENTS.append(('Mice', 'Mouse list with group, % KO, IED, heterotopia and inclusion flags', ''))

# ------------------------------------------------------------------ Criterion
ws, r = sheet('Criterion', 'Sessions to criterion (Figures 1–2, ROC table)', 'Sessions needed to reach criterion in training; ROC of sessions to criterion as a classifier; relationship with % KO.', 'ROC_heterotopia_Fixed_hilo.sav; scripts crit2.py, crit3.py, crit4.py, roc.py, roc2.py, figs.py')
r = write_report(ws, r, section('# Sessions to criterion', '# Sessions to criterion and percent KO') + section('# Sessions to criterion and percent KO'))
d = crit.rename(columns={'SesstoCriterion': 'Sessions to criterion', 'BIheterotopia': 'Heterotopia (file)', 'GRP2HiLo': 'Group (file)'})[['MouseID', 'Group (file)', 'Sessions to criterion', 'Heterotopia (file)']]
d = add_info(d); d['Excluded (M6)'] = d.MouseID == 6
r = write_df(ws, r, d.sort_values(['Group', 'MouseID']), 'Per-mouse data', fmt={'Sessions to criterion': '0', '% KO': '0.00', 'Heterotopia (file)': '0'})
autosize(ws); CONTENTS.append(('Criterion', 'Sessions to criterion, ROC, % KO relationship', 'Figures 1, 2'))

# ------------------------------------------------------------------ Probes
MEAS = ['NumRewards', 'PGoalTime', 'NumEntrances', 'ReRatio', 'PTimeCenter', 'PTimeAnnulus', 'MeanSpeed', 'MeanTargSpeed']
pr = probe.copy(); pr['MouseID'] = pr.MouseID.astype(int); pr['Phase'] = pr.Phase.astype(int)
pr = pr.merge(dates, on=['MouseID', 'Phase', 'Condition'], how='left')
pr['Group'] = pr.G3.map(grp)
cols = ['MouseID', 'Group', 'pct', 'IED', 'HBH', 'Phase', 'Condition', 'Session date', 'Session time', 'Tracking file'] + MEAS
pr = pr[cols].rename(columns={'pct': '% KO', 'HBH': 'Heterotopia'})
ptab = pd.read_pickle(os.path.join(W, 'phase_tab.pkl'))
for cond, nm, sec, figs in [('V', 'Probes_visible', '# Probe sessions: visible goal', 'Figure 3'), ('H', 'Probes_hidden', '# Probe sessions: hidden goal', 'Figure 4')]:
    ws, r = sheet(nm, f'Probe sessions, {"visible" if cond == "V" else "hidden"} goal ({figs})', 'Eight PlaceAccuracy measures per probe session (phases 7–10). Group comparisons per phase: Mann-Whitney U; q = Benjamini-Hochberg across the 64 tests.', 'AllProbeSessions.sav; scripts probe.py, report_stats.py')
    r = write_report(ws, r, section(sec))
    t = ptab[ptab.cond == cond].drop(columns='cond').rename(columns={'CTL': 'WT mean', 'CTLse': 'WT SE', 'Lo': 'Lo mean', 'Lose': 'Lo SE', 'Hi': 'Hi mean', 'Hise': 'Hi SE',
                                                                     'p_LoCTL': 'p Lo vs WT', 'p_HiCTL': 'p Hi vs WT', 'p_LoHi': 'p Lo vs Hi', 'q_LoCTL': 'q Lo vs WT', 'q_HiCTL': 'q Hi vs WT', 'q_LoHi': 'q Lo vs Hi', 'var': 'Measure', 'phase': 'Phase'})
    r = write_df(ws, r, t, 'Group means, SE and Mann-Whitney p by phase (all measures)', fmt={'Phase': '0'})
    r = write_df(ws, r, pr[pr.Condition == cond].sort_values(['Group', 'MouseID', 'Phase']), 'Per-mouse data (one row per probe session)', fmt={'Phase': '0', 'NumRewards': '0', 'NumEntrances': '0', '% KO': '0.00'})
    autosize(ws); CONTENTS.append((nm, f'Probe sessions, {"visible" if cond == "V" else "hidden"} goal: 8 measures by phase', figs))

# ------------------------------------------------------------------ Phase effects
ws, r = sheet('Phase_effects', 'Phase effects: trained location vs goal rotations (Figure 8)', 'Trained (phase 7) vs novel (mean of phases 8–10), Friedman and paired tests within group, per-mouse slopes across phases 7–10.', 'probe data; scripts phase.py, hi_trend.py, report_stats.py')
r = write_report(ws, r, section('# Phase effects'))
pe = pd.read_pickle(os.path.join(W, 'phase_eff.pkl')).rename(columns=lambda c: c.replace('CTL', 'WT'))
r = write_df(ws, r, pe, 'Phase-effect statistics by measure (all tests)')
rows = []
for (mid, g, cond), dd in probe.assign(MouseID=probe.MouseID.astype(int)).groupby(['MouseID', 'G3', 'Condition']):
    dd = dd.sort_values('Phase')
    if len(dd) < 4: continue
    rec = {'MouseID': mid, 'Group': grp(g), 'Condition': cond}
    for v in MEAS:
        rec[f'{v} P7'] = dd[dd.Phase == 7][v].iloc[0]; rec[f'{v} novel (P8–10 mean)'] = dd[dd.Phase > 7][v].mean(); rec[f'{v} slope 7–10'] = np.polyfit(dd.Phase, dd[v], 1)[0]
    rows.append(rec)
r = write_df(ws, r, pd.DataFrame(rows).sort_values(['Condition', 'Group', 'MouseID']), 'Per-mouse data: phase 7, novel mean and slope per phase')
autosize(ws, 28); CONTENTS.append(('Phase_effects', 'Trained vs novel locations and slopes across phases', 'Figure 8'))

# ------------------------------------------------------------------ % KO by phase
ws, r = sheet('PctKO_by_phase', 'Does % KO predict outcome in each phase? (Figures 5–7)', 'Spearman and Pearson correlations of each measure with % KO among Pten KO mice, by phase and condition; q = Benjamini-Hochberg across 64 tests.', 'probe data; scripts pct.py, figs.py, fig7.py')
r = write_report(ws, r, section('# Does percent KO predict'))
cr = pd.read_pickle(os.path.join(W, 'corr.pkl')).rename(columns={'cond': 'Condition', 'var': 'Measure', 'phase': 'Phase', 'rho': 'Spearman rho', 'p_rho': 'p (rho)', 'r': 'Pearson r', 'p_r': 'p (r)', 'q_rho': 'q (rho)'})
r = write_df(ws, r, cr, 'Correlations with % KO (Pten KO mice)', fmt={'Phase': '0'})
k = pr[pr.Group.isin(['Lo', 'Hi'])].sort_values(['Condition', 'MouseID', 'Phase'])
r = write_df(ws, r, k, 'Per-mouse data (Pten KO mice with histology)', fmt={'Phase': '0', '% KO': '0.00'})
autosize(ws); CONTENTS.append(('PctKO_by_phase', 'Correlations of each probe measure with % KO', 'Figures 5, 6, 7'))

# ------------------------------------------------------------------ Zone times
ws, r = sheet('Zone_times', 'Perseveration or failure to update: time in each goal zone (Figures 11–15)', 'Time in the current, previous, trained and never-used zones per probe session; zone-entry measures.', 'AllProbes_ByGZLocation.sav; scripts gz_prep.py, gz_stats.py, gz_bars_stats.py, gz_bars_fig.py, gz_mwu.py, gz_figs.py, gz_entries.py')
r = write_report(ws, r, section('# Perseveration or failure to update'))
for f, t in [('bars.pkl', 'Figure 12: time in each zone by phase and group (Friedman; paired t vs current goal; Mann-Whitney vs WT)'), ('cur_orig.pkl', 'Current vs original (trained) goal zone'), ('mwu.pkl', 'Figure 13: current goal vs WT and vs zone 1')]:
    x = pd.read_pickle(os.path.join(W, 'gz', f)); x['group'] = x['group'].map(grp) if 'group' in x else None
    r = write_df(ws, r, x, t, fmt={'phase': '0', 'n': '0'})
g = pd.read_pickle(os.path.join(W, 'gz', 'gzM.pkl')).drop(columns=['Group']).rename(columns={'Mouse': 'MouseID'})
g['MouseID'] = g.MouseID.astype(int); g['Phase'] = g.Phase.astype(int); g['G3'] = g.G3.map(grp)
g = g.merge(dates, on=['MouseID', 'Phase', 'Condition'], how='left').rename(columns={'G3': 'Group', 'pct': '% KO', 'ied': 'IED'})
r = write_df(ws, r, g.sort_values(['Condition', 'Group', 'MouseID', 'Phase']), 'Per-mouse data (one row per probe session; zone times in s; sh_ = share of zone time; z1–z4 = time in zones 1–4)', fmt={'Phase': '0', '% KO': '0.00'})
autosize(ws, 24); CONTENTS.append(('Zone_times', 'Time in current, previous, trained and other zones', 'Figures 11–15'))

# ------------------------------------------------------------------ Example mice
ws, r = sheet('Example_mice', 'Example mice: M22 (WT), M33 (Lo), M34 (Hi) (Figures 16–19)', 'Paths, dwell and speed maps for one mouse per group.', 'tracking .dat files; scripts traj_compute_preview.py, traj_figs.py')
r = write_report(ws, r, section('# Example mice'))
r = write_df(ws, r, pr[pr.MouseID.isin([22, 33, 34])].sort_values(['MouseID', 'Condition', 'Phase']), 'Probe measures for the example mice', fmt={'Phase': '0', '% KO': '0.00'})
autosize(ws); CONTENTS.append(('Example_mice', 'Probe measures and tables for M22, M33, M34', 'Figures 16–19'))

# ------------------------------------------------------------------ Approach
A = os.path.join(W, 'approach')
ws, r = sheet('Approach', 'How the mice travel to the goal: visible vs hidden (Figures 20–22)', 'Launch distance, straightness and duration of wall-to-goal runs, path per reward. Visible vs hidden: paired t-test within group; groups: Mann-Whitney.', 'tracking .dat files; scripts approach_final.py, approach_figs.py (path_analysis s-scripts in the package)')
r = write_report(ws, r, section('# How the mice travel to the goal', '### Heading toward the goal'))
st = pd.read_pickle(os.path.join(A, 'statsF.pkl')); st['G'] = st.G.map(grp)
r = write_df(ws, r, st.rename(columns={'G': 'Group', 'V': 'Visible', 'H': 'Hidden', 'p_paired': 'p visible vs hidden (paired)', 'p_H': 'p vs WT, hidden', 'p_V': 'p vs WT, visible', 'p_diff': 'p vs WT, difference'}), 'Visible vs hidden by group (mouse means, phases 7–10)')
mf = pd.read_pickle(os.path.join(A, 'mouseF.pkl')).rename(columns={'Mouse': 'MouseID', 'G3': 'Group', 'launch': 'Launch distance (cm)', 'wall_st': 'Wall-to-goal straightness', 'wall_dur': 'Wall-to-goal duration (s)', 'path_per_rew': 'Path per reward (m)'})
mf['Group'] = mf.Group.map(grp); mf['MouseID'] = mf.MouseID.astype(int)
r = write_df(ws, r, mf.sort_values(['Cond', 'Group', 'MouseID']), 'Per-mouse means (phases 7–10)')
sf = pd.read_pickle(os.path.join(A, 'sesF.pkl')).rename(columns={'Mouse': 'MouseID', 'Cond': 'Condition'})
sf['MouseID'] = sf.MouseID.astype(int); sf['Phase'] = sf.Phase.astype(int)
sf = add_info(sf).merge(dates, on=['MouseID', 'Phase', 'Condition'], how='left')
r = write_df(ws, r, sf.sort_values(['Condition', 'Group', 'MouseID', 'Phase']), 'Per-session data (wall_frac = fraction of time at the wall; path per reward in m; n_rew, n_ent = rewards and entrances)', fmt={'Phase': '0', 'n_rew': '0', 'n_ent': '0', '% KO': '0.00'})
autosize(ws, 28); CONTENTS.append(('Approach', 'Launch distance, wall-to-goal runs, path per reward', 'Figures 20–22'))

# ------------------------------------------------------------------ Heading profile
ws, r = sheet('Heading_profile', 'Heading toward the goal by distance, visible vs hidden (Figure 32)',
              'Goal-directedness = mean cosine of the heading error toward the goal centre, running frames (> 5 cm/s) outside the goal zone, not in the 2 s after leaving it, off the wall unless stated; 2.5 cm distance bins; phases 7–10. Reach = distance where goal-directedness falls below 0.1. Visible vs hidden: paired t-test within group; groups: Mann-Whitney.',
              'tracking .dat files; script path_analysis/s15_heading_profile.py (launch distances from s04)')
r = write_report(ws, r, section('### Heading toward the goal', '## Arriving at the goal'))
HD = os.path.join(W, 'heading')
ws.cell(r, 1, 'All statistics (heading_stats.txt, written by s15_heading_profile.py)').font = H2; r += 1
for l in open(os.path.join(HD, 'heading_stats.txt')).read().split('\n'):
    ws.cell(r, 1, l).font = TXT; r += 1
r += 1
hm = pd.read_csv(os.path.join(HD, 'heading_mouse.csv')).rename(columns={'Mouse': 'MouseID'}); hm['MouseID'] = hm.MouseID.astype(int)
hm = add_info(hm.drop(columns=['g', 'IED']))
ren = {'reach_V': 'Reach, visible (cm)', 'reach_H': 'Reach, hidden (cm)', 'gd_V': 'Goal-directedness 10–40 cm, visible', 'gd_H': 'Goal-directedness 10–40 cm, hidden',
       'reach_all_frames_V': 'Reach, all frames incl. wall, visible (cm)', 'reach_all_frames_H': 'Reach, all frames incl. wall, hidden (cm)',
       'gd_all_frames_V': 'Goal-directedness 10–40 cm, all frames, visible', 'gd_all_frames_H': 'Goal-directedness 10–40 cm, all frames, hidden'}
for ph in [7, 8, 9, 10]:
    ren[f'reach_V_p{ph}'] = f'Reach phase {ph}, visible (cm)'; ren[f'reach_H_p{ph}'] = f'Reach phase {ph}, hidden (cm)'
for t in [20, 30, 40]:
    ren[f'launch_ge{t}_V'] = f'Entries launched >= {t} cm, visible (%)'; ren[f'launch_ge{t}_H'] = f'Entries launched >= {t} cm, hidden (%)'
hm = hm.rename(columns=ren); lead = ['MouseID', 'Group', '% KO', 'IED', 'Heterotopia']
hm = hm[lead + [ren[k] for k in ren if ren[k] in hm.columns]]; hm['Group'] = pd.Categorical(hm.Group, ['WT', 'Lo', 'Hi'], ordered=True)
r = write_df(ws, r, hm.sort_values(['Group', 'MouseID']), 'Per-mouse data (phases 7–10 pooled unless a phase is named; session dates for phases 7–10 are on the Approach sheet)', fmt={'% KO': '0.00'})
hp = pd.read_csv(os.path.join(HD, 'heading_profile.csv')).rename(columns={'g': 'Group', 'Mouse': 'MouseID', 'Cond': 'Condition', 'd': 'Distance from goal centre, bin centre (cm)', 'n': 'Frames',
                                                                          'gd': 'Goal-directedness', 'err': 'Mean heading error (deg)', 'aimed': 'Frames within 45 deg of the goal (%)'})
hp['MouseID'] = hp.MouseID.astype(int); hp['Group'] = pd.Categorical(hp.Group, ['WT', 'Lo', 'Hi'], ordered=True)
r = write_df(ws, r, hp.sort_values(['Group', 'MouseID', 'Condition', 'Distance from goal centre, bin centre (cm)']), 'Per-mouse profile by distance (frames off the wall, phases 7–10; bins with at least 30 frames)', fmt={'Frames': '0'})
autosize(ws, 26); CONTENTS.append(('Heading_profile', 'Heading toward the goal by distance; launch-distance distribution', 'Figure 32'))

# ------------------------------------------------------------------ Arrival
ws, r = sheet('Arrival', 'Arriving at the goal (Figure 23)', 'Entry speed, dwell and reward per directed run on arrival. Groups: Mann-Whitney on mouse means.', 'tracking .dat files; scripts approach_zones.py, approach_arrival.py, approach_fig_arrival.py')
r = write_report(ws, r, section('## Arriving at the goal', '### Does reward per directed run'))
ast = pd.read_pickle(os.path.join(A, 'arrival_stats.pkl')).rename(columns={'p_LoWT': 'p Lo vs WT', 'p_HiWT': 'p Hi vs WT', 'p_LoHi': 'p Lo vs Hi'})
r = write_df(ws, r, ast, 'Arrival measures by phase (hidden), group means and Mann-Whitney p', fmt={'Phase': '0'})
am = pd.read_pickle(os.path.join(A, 'arrival_mouse.pkl')).rename(columns={'Mouse': 'MouseID', 'G3': 'Group', 'Cond': 'Condition', 'fdir': 'Directed runs (% of entries)', 'spd': 'Entry speed (cm/s)', 'dwell': 'Dwell (s)', 'rwdir': 'Directed runs rewarded (%)'})
am['Group'] = am.Group.map(grp); am['MouseID'] = am.MouseID.astype(int); am['Phase'] = am.Phase.astype(int)
am = am.merge(dates, on=['MouseID', 'Phase', 'Condition'], how='left')
r = write_df(ws, r, am.sort_values(['Condition', 'Group', 'MouseID', 'Phase']), 'Per-mouse data by phase', fmt={'Phase': '0'})
autosize(ws, 28); CONTENTS.append(('Arrival', 'Entry speed, dwell and reward per directed run', 'Figure 23'))

# ------------------------------------------------------------------ Reward slope
from scipy.stats import mannwhitneyu, ttest_1samp
ws, r = sheet('Reward_slope', 'Does reward per directed run fall across the rotations? (Figure 24)', 'Per-mouse least-squares slope of % directed runs rewarded across phases 7–10; groups: Mann-Whitney; slope vs 0: one-sample t; per-run logistic GEE in the report table.', 'scripts approach_fig_slope.py, approach_stats.py')
r = write_report(ws, r, section('### Does reward per directed run'))
rows = []
for (g, mid, cond), dd in am.groupby(['Group', 'MouseID', 'Condition']):
    rows.append({'MouseID': mid, 'Group': g, 'Condition': cond, **{f'Phase {int(p)} (%)': v for p, v in zip(dd.Phase, dd['Directed runs rewarded (%)'])},
                 'Slope (points per phase)': np.polyfit(dd.Phase, dd['Directed runs rewarded (%)'], 1)[0]})
sl = pd.DataFrame(rows)
tests = []
for cond in ['H', 'V']:
    s = sl[sl.Condition == cond]; v = {g: s[s.Group == g]['Slope (points per phase)'] for g in ['WT', 'Lo', 'Hi']}
    for g in v: tests.append({'Condition': cond, 'Test': f'{g} slope vs 0 (one-sample t)', 'Mean slope': v[g].mean(), 'n': len(v[g]), 'p': ttest_1samp(v[g], 0).pvalue})
    for a, b in [('Lo', 'WT'), ('Hi', 'WT'), ('Hi', 'Lo')]: tests.append({'Condition': cond, 'Test': f'{a} vs {b} (Mann-Whitney)', 'Mean slope': None, 'n': None, 'p': mannwhitneyu(v[a], v[b]).pvalue})
r = write_df(ws, r, pd.DataFrame(tests), 'Per-mouse slope tests', fmt={'n': '0'})
r = write_df(ws, r, sl.sort_values(['Condition', 'Group', 'MouseID']), 'Per-mouse data')
autosize(ws, 28); CONTENTS.append(('Reward_slope', 'Reward per directed run across phases 7–10', 'Figure 24'))

# ------------------------------------------------------------------ After a miss
ws, r = sheet('After_miss', 'After a miss: coming back and pausing (Figure 25)', 'Hidden phases 8–10. Returns to the current goal within 3 s after an unrewarded exit (other zones as control); pauses (<3 cm/s, 35–300 frames, away from the wall) near the current goal (within 2.5 zone radii). Groups: Mann-Whitney on mouse means.', 'tracking .dat files; scripts turnback.py, turnback_fig.py')
r = write_report(ws, r, section('### After a miss'))
G3 = probe.drop_duplicates('MouseID').set_index('MouseID').G3
E = pd.read_pickle(os.path.join(A, 'exits.pkl')); E['G3'] = E.Mouse.map(G3); E = E[E.G3.isin(['CTL', 'Lo', 'Hi'])]; E['r3'] = E.ret.notna() & (E.ret <= 3)
P = pd.read_pickle(os.path.join(A, 'pauses.pkl')); P['G3'] = P.Mouse.map(G3); P = P[P.G3.isin(['CTL', 'Lo', 'Hi'])]
for z in [1, 2, 3, 4]: P[f'n{z}'] = P[f'd{z}'] < 2.5
P['near_c'] = [rr[f"n{int(rr.cur)}"] for _, rr in P.iterrows()]; P['near_o'] = [np.mean([rr[f"n{z}"] for z in [1, 2, 3, 4] if z != rr.cur]) for _, rr in P.iterrows()]
x = E[(E.Cond == 'H') & E.Phase.isin([8, 9, 10])]
ret = x[(x.role == 'current') & ~x.rewarded].groupby(['G3', 'Mouse']).r3.mean().rename('Return within 3 s after a miss, current goal (%)').to_frame().join(
      x[x.role != 'current'].groupby(['G3', 'Mouse']).r3.mean().rename('Return within 3 s, other zones (%)'))
y = P[(P.Cond == 'H') & P.Phase.isin([8, 9, 10])]
pz = y.groupby(['G3', 'Mouse']).agg(**{'Pauses near current goal (%)': ('near_c', 'mean'), 'Pauses near other zones (%, mean)': ('near_o', 'mean')})
p10 = P[(P.Cond == 'H') & (P.Phase == 10)].groupby(['G3', 'Mouse']).size().rename('Pauses, phase 10 (n)')
e10 = E[(E.Cond == 'H') & (E.Phase == 10) & (E.role == 'current')].groupby(['G3', 'Mouse']).exit_spd.median().rename('Exit speed from current goal, phase 10 (cm/s, median)')
am_ = ret.join(pz).join(p10).join(e10).reset_index().rename(columns={'G3': 'Group', 'Mouse': 'MouseID'})
for c in am_.columns:
    if '(%' in c: am_[c] = am_[c] * 100
am_['Group'] = am_.Group.map(grp); am_['MouseID'] = am_.MouseID.astype(int)
tests = []
for c in am_.columns[2:]:
    v = {g: am_[am_.Group == g][c].dropna() for g in ['WT', 'Lo', 'Hi']}
    tests.append({'Measure': c, 'WT': v['WT'].mean(), 'Lo': v['Lo'].mean(), 'Hi': v['Hi'].mean(), 'p Lo vs WT': mannwhitneyu(v['Lo'], v['WT']).pvalue, 'p Hi vs WT': mannwhitneyu(v['Hi'], v['WT']).pvalue, 'p Lo vs Hi': mannwhitneyu(v['Lo'], v['Hi']).pvalue})
r = write_df(ws, r, pd.DataFrame(tests), 'Group means and Mann-Whitney p (mouse means)')
r = write_df(ws, r, am_.sort_values(['Group', 'MouseID']), 'Per-mouse data', fmt={'Pauses, phase 10 (n)': '0'})
autosize(ws, 30); CONTENTS.append(('After_miss', 'Returns after a miss and pauses near the goal', 'Figure 25'))

# ------------------------------------------------------------------ Phase 8 conflicts
ws, r = sheet('Phase8_conflict', 'First goal rotation: place vs cue, and new place vs old place (Figures 30–31)',
              'Directed runs (launch >= 20 cm) to each of the four zones in the phase 8 probes, in the order made. Never-used zones (3, 4) = no-memory baseline. Visible: old-place share vs cue and latent place preference (first 10 runs). Hidden: place pull of new and old place (first 20 runs). Within group: one-sample or paired t; groups: Mann-Whitney; links: Spearman and rank regression with group.',
              'tracking .dat files; scripts path_analysis/s13_phase8_visits.py, path_analysis/s14_phase8_conflict.py')
r = write_report(ws, r, section('# First goal rotation'))
ws.cell(r, 1, 'All statistics (phase8_stats.txt, written by s14_phase8_conflict.py)').font = H2; r += 1
for l in open(os.path.join(W, 'phase8', 'phase8_stats.txt')).read().split('\n'):
    ws.cell(r, 1, l).font = TXT; r += 1
r += 1
pm = pd.read_csv(os.path.join(W, 'phase8', 'phase8_mouse.csv')).rename(columns={'Mouse': 'MouseID'}); pm['MouseID'] = pm.MouseID.astype(int)
pm = pm.drop(columns=['g', 'IED', 'pct'])
d8 = dates[dates.Phase == 8].pivot_table(index='MouseID', columns='Condition', values='Session date', aggfunc='first')
d8 = d8.rename(columns={'V': 'Session date, visible phase 8', 'H': 'Session date, hidden phase 8'}).reset_index(); d8['MouseID'] = d8.MouseID.astype(int)
pm = add_info(pm).merge(d8, on='MouseID', how='left')
lead = ['MouseID', 'Group', '% KO', 'IED', 'Heterotopia', 'Session date, visible phase 8', 'Session date, hidden phase 8']
pm = pm[lead + [c for c in pm.columns if c not in lead]]
pm = pm.rename(columns={'V_old_share': 'Visible: old-place share vs cue, first 10 (%)', 'V_never_share': 'Visible: never-used share vs cue, first 10 (%)',
                        'V_old_pull': 'Visible: latent place preference, old - never, first 10 (%)', 'H_old_pull': 'Hidden: old - never, first 10 (%)',
                        'H_minus_V_old_pull': 'Old-place pull, hidden - visible (%)', 'P10_rewards': 'Rewards, hidden phase 10',
                        'n_directed_V': 'Directed runs, visible', 'n_directed_H': 'Directed runs, hidden'})
pm = pm.rename(columns=lambda c: c.replace('H20_', 'Hidden first 20: ').replace('H10_', 'Hidden first 10: ').replace('Hall_', 'Hidden all runs: ').replace('_pct', ' (% of runs)').replace('never (%', 'one never-used (%').replace('_pull', ' pull (%)'))
pm['Group'] = pd.Categorical(pm.Group, ['WT', 'Lo', 'Hi'], ordered=True)
r = write_df(ws, r, pm.sort_values(['Group', 'MouseID']), 'Per-mouse data (pull = % of directed runs to that place minus % to one never-used zone; place pull = mean of new and old minus never-used)',
             fmt={'% KO': '0.00', 'Directed runs, visible': '0', 'Directed runs, hidden': '0', 'Rewards, hidden phase 10': '0'})
autosize(ws, 26); CONTENTS.append(('Phase8_conflict', 'Phase 8: place vs cue (visible) and new vs old place (hidden)', 'Figures 30, 31'))

# ------------------------------------------------------------------ CSD / CNO / IED
cs = csd.copy(); cs['MouseID'] = cs.index.astype(int)
ws, r = sheet('CSD_CNO_IED', 'Theta CSD by layer, CNO and IED prediction (Figures 9, 27, S1, S2)', 'Theta CSD per layer (mean of the channels in that layer), baseline and after CNO; regressions on % KO (WT at 0); group x drug mixed models; ROC for clear IEDs. M26 excluded.', 'CSD_sansM2.sav, Data4Claude.xlsx (% KO); scripts csd3_data.py, csd3_stats.py, csd3_figs.py')
r = write_report(ws, r, section('# Theta CSD, goal-zone time', '## Layer profile') + section('## Theta CSD as a predictor of IEDs') + section('# Supplementary figures'))
stt = pd.read_csv(os.path.join(PKG, 'work', 'csd3', 'csd3_stats.csv')).set_index('measure').T.reset_index().rename(columns={'index': 'Statistic'})
r = write_df(ws, r, stt, 'All statistics by CSD measure (from csd3_stats.py; mw_ = Mann-Whitney p, x_ = group x drug p, r_ = regression on % KO, roc_ = ROC, loss_ = loss of AUC with CNO)')
cc = ['MouseID', 'G', 'pct', 'ied'] + [f'{k}_{s}' for k in ['AVG4', 'M2G2', 'MML1', 'MML2', 'GCL1', 'GCL2'] for s in ['base', 'cno', 'chg']]
x = cs[cs.AVG4_base.notna()][cc].rename(columns={'G': 'Group', 'pct': '% KO', 'ied': 'IED'})
x = x.rename(columns=lambda c: c.replace('AVG4', '4-layer avg').replace('M2G2', 'MML2+GCL2').replace('_base', ' baseline').replace('_cno', ' CNO').replace('_chg', ' change'))
r = write_df(ws, r, x.sort_values(['Group', 'MouseID']), 'Per-mouse theta CSD (layer means; combined measures pool the channels of their layers)', fmt={'% KO': '0.00', 'IED': '0'})
autosize(ws, 26); CONTENTS.append(('CSD_CNO_IED', 'Theta CSD by layer: regressions, CNO, ROC for IEDs', 'Figures 9, 27, S1, S2'))

# ------------------------------------------------------------------ CSD layer profile
ws, r = sheet('CSD_layer_profile', 'Theta CSD layer profile, baseline and after CNO (Figures 28–29)', 'Mean of the channels in each layer per mouse; GEE (Gaussian, exchangeable, clustered by mouse) vs the WT hilus, Holm within panel. M26 excluded.', 'CSD_sansM2.sav; script csd3_layers.py')
r = write_report(ws, r, section('## Layer profile'))
lg = pd.read_csv(os.path.join(PKG, 'work', 'csd3', 'layers_gee.csv')); lm = pd.read_csv(os.path.join(PKG, 'work', 'csd3', 'layers_means.csv'))
for t in (lg, lm): t['split'] = t.split.map({'LH': 'Lo / Hi', 'IED': 'IED split'})
r = write_df(ws, r, lm, 'Layer means and SE by group (split = grouping)', fmt={'n_base': '0', 'n_cno': '0'})
r = write_df(ws, r, lg.rename(columns={'panel': 'Panel', 'p': 'GEE p vs WT hilus', 'p_holm': 'Holm-adjusted p'}), 'GEE contrasts vs WT hilus (all cells)')
import importlib.util
spec = importlib.util.spec_from_file_location('csd3_layers', os.path.join(PKG, 'group_analysis', 'csd3_layers.py')); mod = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]; spec.loader.exec_module(mod)
lay = mod.m.rename(columns={'mouse': 'MouseID', 'Estimate': 'Layer', 'base': 'Baseline', 'cno': 'After CNO', 'chg': 'Change', 'LH': 'Group (Lo/Hi)', 'IED': 'Group (IED)', 'pct': '% KO', 'ied': 'IED'})
lay = lay[['MouseID', 'Group (Lo/Hi)', 'Group (IED)', '% KO', 'IED', 'Layer', 'Baseline', 'After CNO', 'Change']]
lay['Layer'] = pd.Categorical(lay.Layer, mod.LAY, ordered=True)
r = write_df(ws, r, lay.sort_values(['Group (Lo/Hi)', 'MouseID', 'Layer']), 'Per-mouse data (one row per mouse and layer)', fmt={'% KO': '0.00', 'IED': '0'})
autosize(ws, 26); CONTENTS.append(('CSD_layer_profile', 'Layer profile and GEE vs WT hilus', 'Figures 28, 29'))

# ------------------------------------------------------------------ IEDs
ws, r = sheet('IEDs', 'IEDs: laminar structure, rate with CNO, and the link to theta and behaviour (Figures 33–35, S3, S4)',
              'IEDs from the lab recording pipeline: 5 Pten KO mice, one baseline and one CNO recording each. Grand-average voltage by layer in the initiation (-1 to 0 ms) and propagation (2 to 15 ms) windows; IED rate and timing; per-mouse link to theta CSD and hidden-goal behaviour (n = 4, descriptive). The pipeline statistics are reported as given.',
              'inputs/ied (GrandAvg_SOLID_*.csv, IED_session_summary.csv, IED_onsets_solid.csv, stats_*.csv); script group_analysis/ied_figs.py')
r = write_report(ws, r, section('## IEDs: their laminar structure'))
ID = os.path.join(PKG, 'work', 'ied')
ws.cell(r, 1, 'All statistics (ied_stats.txt, written by ied_figs.py; includes the pipeline statistics)').font = H2; r += 1
for l in open(os.path.join(ID, 'ied_stats.txt')).read().split('\n'):
    ws.cell(r, 1, l).font = TXT; r += 1
r += 1
im = pd.read_csv(os.path.join(ID, 'ied_mouse.csv')).rename(columns={'Mouse': 'MouseID'})
im = im.rename(columns=lambda c: c.replace('IED_per_min_first20', 'IEDs per min, first 20 min').replace('IED_per_min', 'IEDs per min').replace('theta_', 'theta CSD ').replace('_change_pct', ' change (%)')
                                  .replace('_base', ', baseline').replace('_CNO', ', CNO').replace('hidden_goal_time', 'hidden goal-zone time (%)').replace('visible_goal_time', 'visible goal-zone time (%)'))
r = write_df(ws, r, im, 'Per mouse: IED rate, theta CSD and goal-zone time, baseline and CNO (theta and behaviour from the CSD/CNO data)')
ss = pd.read_csv(os.path.join(ID, 'ied_sessions.csv')).drop(columns=['m'], errors='ignore')
r = write_df(ws, r, ss, 'Per session: recording length and solid IEDs', fmt={'N_solid_IEDs': '0', 'Sampling_rate_Hz': '0'})
il = pd.read_csv(os.path.join(ID, 'ied_layers.csv'))
r = write_df(ws, r, il, 'Per layer: grand-average voltage (uV) and approximate CSD (a.u.) in each window, and baseline theta CSD of WT and IED+ mice')
on = pd.read_csv(os.path.join(IED_DIR, 'IED_onsets_solid.csv'))
r = write_df(ws, r, on, 'Every solid IED: onset time in its recording')
autosize(ws, 24); CONTENTS.append(('IEDs', 'IED laminar structure, rate with CNO, link to theta and behaviour', 'Figures 33–35, S3, S4'))

# ------------------------------------------------------------------ Arrival: slowing and pausing
ws, r = sheet('Arrival_slowing', 'Slowing at the goal and total pausing (Figure 37)',
              'Slowing ratio = mean speed over the 1.2 s after entering the goal divided by mean speed over the 1.5 s to 0.5 s before it, on directed runs (launch >= 20 cm), per session. 1 means the mouse did not slow at all; it is a within-run ratio, so it controls for approach speed. Pause measures are per probe session; distances are in goal-zone radii, so a pause inside the zone is < 1. Mann-Whitney between groups.',
              'script path_analysis/s16_arrival_directed.py (profiles) and s17_arrival_paths.py (figure); pauses from s11')
r = write_report(ws, r, section('## What arrival looks like'))
GM = probe.drop_duplicates('MouseID').set_index('MouseID').G3
AD = pd.read_pickle(os.path.join(W, 'approach', 'arrival_dir.pkl'))
AD['G3'] = AD.Mouse.map(GM)
AD = AD[AD.G3.isin(['CTL', 'Lo', 'Hi'])]
bnd = lambda q, lo, hi: np.nanmean(q[int((lo + 3) * 30):int((hi + 3) * 30) + 1])
AD['slowing_ratio'] = AD.prof.apply(lambda q: bnd(q, 0, 1.2)) / AD.prof.apply(lambda q: bnd(q, -1.5, -0.5))
AD['speed_in_zone'] = AD.prof.apply(lambda q: bnd(q, 0, 1.2))
AD['speed_before'] = AD.prof.apply(lambda q: bnd(q, -1.5, -0.5))
t = AD[['G3', 'Mouse', 'Phase', 'Cond', 'directed', 'n', 'speed_before', 'speed_in_zone', 'slowing_ratio']].copy()
t.columns = ['Group', 'Mouse', 'Phase', 'Condition', 'Directed run', 'Entries', 'Speed before (cm/s)',
             'Speed in reward window (cm/s)', 'Slowing ratio']
r = write_df(ws, r, t.round(3), 'Per session: speed before and after entering the goal, directed runs and chance crossings separately')
g = (AD[AD.directed].groupby(['Cond', 'Phase', 'G3']).apply(
        lambda x: pd.Series({'Mice': x.Mouse.nunique(), 'Slowing ratio': x.groupby('Mouse').slowing_ratio.mean().mean()}))
     .reset_index().rename(columns={'Cond': 'Condition', 'G3': 'Group'}))
r = write_df(ws, r, g.round(3), 'Slowing ratio by phase and condition, directed runs (mean of mouse means)')
PP = pd.read_pickle(os.path.join(W, 'approach', 'pauses_d.pkl'))
PP['G3'] = PP.Mouse.map(GM); PP = PP[PP.G3.isin(['CTL', 'Lo', 'Hi'])]
pt = (PP.groupby(['Cond', 'Phase', 'G3', 'Mouse'])
        .apply(lambda x: pd.Series({'Pauses': len(x), 'Pause time (s)': x.dur.sum(),
                                    'Mean pause duration (s)': x.dur.mean(),
                                    'Pause time in zone, <1 r (s)': x.loc[x.dcur < 1, 'dur'].sum(),
                                    'Pause time around goal, 1-2.5 r (s)': x.loc[(x.dcur >= 1) & (x.dcur < 2.5), 'dur'].sum(),
                                    'Pause time open interior, >2.5 r (s)': x.loc[x.dcur >= 2.5, 'dur'].sum(),
                                    'In-zone pauses': (x.dcur < 1).sum(),
                                    'Median dist of near-goal pauses (radii)': x.loc[x.dcur < 2.5, 'dcur'].median()}))
        .reset_index().rename(columns={'Cond': 'Condition', 'G3': 'Group'}))
r = write_df(ws, r, pt.round(3), 'Pausing per probe session, per mouse, split by where the pause happened (distance in goal-zone radii). A pause is 1.2-10 s below 3 cm/s; pauses in the wall annulus (radius > 0.8 of the fitted arena radius) are excluded by the pause definition, so none of these columns contain wall or resting behaviour.')
autosize(ws, 26); CONTENTS.append(('Arrival_slowing', 'Slowing at the goal and total pausing per session', 'Figure 37'))

# ------------------------------------------------------------------ What the mice search
ws, r = sheet('Search_sets', 'Pause time by the kind of place the pause was at (Figure 38)',
              'Zone k was the goal of phase k + 6, so at each hidden phase the four zones divide into the current goal, the former goals and the zones not yet used; the number of former goals grows 0, 1, 2, 3 across phases 7 to 10. Each pause is assigned to the nearest kind of zone within 2.5 zone radii (current first, then former, then never-used), and pauses near none of them are counted as away from every zone. Pauses at the wall (beyond 0.8 of the fitted arena radius) are excluded by the pause definition, so none of these columns contain thigmotaxis. Hidden sessions only.',
              'script path_analysis/s18_search_sets.py; pauses from s11')
r = write_report(ws, r, section('## What the mice search'))
SS = pd.read_csv(os.path.join(W, 'approach', 'search_sets.csv'))
SS['Place'] = SS.Place.map({'current': 'Current goal', 'former': 'Former goals',
                            'never': 'Never used', 'open': 'Away from every zone'})
r = write_df(ws, r, SS.round(3), 'Pause time per probe session, per mouse, by kind of place; Condition H = hidden, V = cued')
pv = (SS.pivot_table(index=['Condition', 'Place', 'Group'], columns='Phase', values='Pause time (s)', aggfunc='mean')
        .round(2).reset_index())
r = write_df(ws, r, pv, 'Group means by phase (s per session), hidden and cued')
sl = []
for (cd, pl, g), d2 in SS.groupby(['Condition', 'Place', 'Group']):
    v = [np.polyfit(x.index.values.astype(float), x.values, 1)[0]
         for m, gg in d2.groupby('Mouse') for x in [gg.set_index('Phase')['Pause time (s)']] if len(x) >= 3]
    sl.append({'Condition': cd, 'Place': pl, 'Group': g, 'Mice': len(v), 'Mean slope (s per phase)': round(np.mean(v), 2)})
r = write_df(ws, r, pd.DataFrame(sl), 'Per-mouse slope across phases 7-10; Hi vs WT compared by Mann-Whitney in the report')
autosize(ws, 26); CONTENTS.append(('Search_sets', 'Pause time by kind of place: current, former and never-used goals', 'Figure 38'))

# ------------------------------------------------------------------ Load slopes and speed mode
ws, r = sheet('Load_and_speed', 'Per-rotation slopes, and what the mice do instead of searching (v2 Figures 24 and 29)',
              'Every measure in the report that has a slope across the hidden rotations, fitted the same way: per-mouse least squares across phases 7 to 10. Groups are compared on the unstandardised slopes with a two-sided Mann-Whitney, which is the group x phase test used throughout. The speed table is the within-mouse comparison of the hidden session against the cued session at the same phase: negative means the mouse slows down when the marker is removed.',
              'scripts path_analysis/s19_load_slopes.py and s20_speed_mode.py')
LS = pd.read_csv(os.path.join(W, 'approach', 'load_slopes.csv'))
r = write_df(ws, r, LS, 'Per-mouse slope across hidden phases 7-10, by measure')
g = (LS.groupby(['Measure', 'Unit', 'Group']).Slope.agg(['count', 'mean'])
       .round(3).reset_index().rename(columns={'count': 'Mice', 'mean': 'Mean slope'}))
r = write_df(ws, r, g, 'Mean slope by measure and group')
SM = pd.read_csv(os.path.join(W, 'approach', 'speed_mode.csv'))
SM = SM.rename(columns={'G3': 'Group', 'H': 'Speed hidden (cm/s)', 'V': 'Speed cued (cm/s)',
                        'd': 'Hidden minus cued (cm/s)'})
r = write_df(ws, r, SM.round(3), 'Mean speed per probe session, cued and hidden, per mouse and phase')
pr = pd.read_pickle(os.path.join(W, 'probe.pkl')).rename(columns={'MouseID': 'Mouse'})
pr = pr[(pr.Condition == 'H') & (pr.Phase == 10) & pr.G3.isin(['CTL', 'Lo', 'Hi'])]
tr = pr[['G3', 'Mouse', 'NumEntrances', 'NumRewards', 'PGoalTime', 'MeanSpeed', 'PTimeAnnulus']].copy()
tr.columns = ['Group', 'Mouse', 'Goal-zone entries', 'Rewards', 'Fraction of time in goal zone',
              'Mean speed (cm/s)', 'Fraction of time in wall annulus']
r = write_df(ws, r, tr.round(3), 'Hidden phase 10: entries against rewards, per mouse')
autosize(ws, 26); CONTENTS.append(('Load_and_speed', 'Per-rotation slopes and the shift from searching to running', 'v2 Figures 24, 29'))

# ------------------------------------------------------------------ Braking
ws, r = sheet('Braking', 'Deceleration on approach: rate by place, and braking distance',
              "Whishaw, Cassel and Jarrard (1995, J Neurosci 15:5779) take deceleration on approach as the sign that an animal expects the goal at a place. A braking event here is a fall from a local speed maximum of at least 12 cm/s to below half that speed within 1 s, off the wall, placed where the mouse ended up slow and assigned to the nearest zone kind within 2.5 zone radii. Rates are per metre of off-wall path, because Hi mice cover about 29 per cent more ground and a raw count would reward that. Braking distance is measured on directed runs (launch >= 20 cm) as the distance from the goal at which speed first falls below 70 per cent of that run's approach maximum; runs with no such fall are recorded as not braking, so the censoring is explicit.",
              'script path_analysis/s21_braking.py')
GM2 = probe.drop_duplicates('MouseID').set_index('MouseID').G3
EV = pd.read_csv(os.path.join(W, 'approach', 'braking_events.csv'))
EV['Group'] = EV.Mouse.map(GM2)
mt = EV[EV.cat == '__metres__'].groupby(['Group', 'Mouse', 'Phase', 'Cond']).d_goal.sum().rename('Off-wall path (m)').reset_index()
cn = EV[EV.cat != '__metres__'].groupby(['Group', 'Mouse', 'Phase', 'Cond', 'cat']).size().rename('Braking events').reset_index()
bt = mt.merge(cn, on=['Group', 'Mouse', 'Phase', 'Cond'], how='left')
bt['Events per 10 m'] = (bt['Braking events'] / bt['Off-wall path (m)'] * 10).round(3)
bt = bt.rename(columns={'Cond': 'Condition', 'cat': 'Place'})
r = write_df(ws, r, bt.round(3), 'Braking events per session by place (current goal, former goal, never used, elsewhere)')
RB = pd.read_csv(os.path.join(W, 'approach', 'braking_runs.csv'))
RB['Group'] = RB.Mouse.map(GM2)
g2 = (RB.groupby(['Group', 'Mouse', 'Phase', 'Cond'])
        .apply(lambda x: pd.Series({'Directed runs': len(x), 'Runs with braking (%)': 100 * x.braked.mean(),
                                    'Mean braking distance (cm)': x.brake_dist.mean(),
                                    'Mean approach peak speed (cm/s)': x.v_max.mean()}))
        .reset_index().rename(columns={'Cond': 'Condition'}))
r = write_df(ws, r, g2.round(3), 'Braking on directed runs to the current goal, per mouse and phase')
autosize(ws, 26); CONTENTS.append(('Braking', 'Deceleration on approach, by place and as braking distance', 'Section 5'))

# ------------------------------------------------------------------ CNO patch clamp
ws, r = sheet('CNO_patch', 'Whole-cell validation: CNO silences hM4D-expressing Pten KO granule neurons (Figure 36)',
              'Current-clamp recordings from the lab patch rig. Pten KO granule neurons expressing hM4D(Gi) from pRubi-HM4D-T2A-Cre, before and during 10 uM CNO, against uninfected wild-type granule neurons recorded with the same current steps and no drug (time control). Per-cell values were recovered from the vector coordinates of the lab summary figure and reproduce its published means and SEMs exactly. The Pten;Raptor dKO cells of that figure are kept here for the record but are not plotted in Figure 36. p values are the two-tailed paired t tests of the source methods.',
              'inputs/patch (cno_patch_cells.csv, cno_patch_fi.csv, cno_patch_traces.json); script patch/cno_patch_fig.py')
r = write_report(ws, r, section('## The DREADD works'))
PD = os.path.join(PKG, 'inputs', 'patch')
pc = pd.read_csv(os.path.join(PD, 'cno_patch_cells.csv'))
pc = pc.rename(columns={'measure': 'Measure', 'group': 'Group', 'cell': 'Cell', 'baseline': 'Baseline',
                        'post': 'CNO or later', 'post_censored': 'Note'})
pc['Group'] = pc['Group'].map({'WT': 'WT (no drug)', 'KO': 'Pten KO + hM4D', 'DKO': 'Pten;Raptor dKO + hM4D'})
r = write_df(ws, r, pc, 'Per cell: baseline and CNO (or 10 min later, for the wild-type time control)')
mm = []
for meas, md in pc.groupby('Measure', sort=False):
    for grp, gd in md.groupby('Group', sort=False):
        post = gd[gd['CNO or later'].notna() & gd['Note'].isna()]['CNO or later']
        for lab, v in (('Baseline', gd['Baseline']), ('CNO / later', post)):
            mm.append({'Measure': meas, 'Group': grp, 'Series': lab, 'n': len(v),
                       'Mean': round(v.mean(), 3), 'SEM': round(v.std(ddof=1) / np.sqrt(len(v)), 3)})
r = write_df(ws, r, pd.DataFrame(mm), 'Mean and SEM per column (silenced cells are excluded from the CNO mean, as in the paired test)')
pf = pd.read_csv(os.path.join(PD, 'cno_patch_fi.csv'))
pf = pf.rename(columns={'series': 'Series', 'current_rel_rheobase_pA': 'Current from baseline rheobase (pA)',
                        'rate_norm': 'Firing rate / peak rate', 'lo': 'Mean - SE', 'hi': 'Mean + SE', 'n_cells': 'Cells'})
r = write_df(ws, r, pf, 'Normalised F-I curves (Figure 36b), mean +/- SE of per-cell curves')
ws.cell(r, 1, 'Paired t-test p values reported in the source methods (within group, so unchanged by dropping the dKO group)').font = H2; r += 1
for line in ['Spikes per sweep at matched current: WT p < 0.001 (n = 5); Pten KO p = 0.051 (n = 5)',
             'Spike threshold: WT p = 0.555 (n = 5); Pten KO p = 0.477 (n = 3 measurable)',
             'Rheobase: WT p = 1.000 (n = 5); Pten KO p = 0.254 (n = 3 measurable)',
             'Resting potential: WT p = 0.724 (n = 5); Pten KO p = 0.490 (n = 5)']:
    ws.cell(r, 1, line).font = TXT; r += 1
autosize(ws, 26); CONTENTS.append(('CNO_patch', 'Whole-cell validation of CNO silencing in Pten KO granule neurons', 'Figure 36'))

# ------------------------------------------------------------------ Goal time with CNO
ws, r = sheet('Goal_time_CNO', 'Goal-zone time before and after CNO, visible and hidden (Figures 10, 26)', 'Mean goal-zone time of probe phases 8–9 (% of session). Group x drug mixed models; regressions on % KO (WT at 0). M26 included.', 'AllProbeSessions_CNO.sav; scripts csd3_data.py, csd3_stats.py, csd3_figs.py')
r = write_report(ws, r, section('## Goal-zone time, visible and hidden'))
x = cs[cs.Goal_base.notna() | cs.Vis_base.notna()][['MouseID', 'G', 'pct', 'ied', 'Vis_base', 'Vis_cno', 'Vis_chg', 'Goal_base', 'Goal_cno', 'Goal_chg']]
x = x.rename(columns={'G': 'Group', 'pct': '% KO', 'ied': 'IED', 'Vis_base': 'Visible baseline', 'Vis_cno': 'Visible CNO', 'Vis_chg': 'Visible change',
                      'Goal_base': 'Hidden baseline', 'Goal_cno': 'Hidden CNO', 'Goal_chg': 'Hidden change'})
r = write_df(ws, r, x.sort_values(['Group', 'MouseID']), 'Per-mouse goal-zone time (% of session, phases 8–9 mean)', fmt={'% KO': '0.00', 'IED': '0'})
autosize(ws); CONTENTS.append(('Goal_time_CNO', 'Goal-zone time before and after CNO', 'Figures 10, 26'))

# ------------------------------------------------------------------ Standalone summary: example mice
ws, r = sheet('Summary_examples', 'Per-mouse values behind the standalone summary (summary Figures 1-4)',
              'Everything the standalone summary quotes, one row per mouse. The three followed mice (M9 WT, M8 Lo, M5 Hi) are each the mouse closest to its group median across sessions to criterion, pause time at former goals, total pause time, hidden-minus-cued speed and braking rate at the goal, scored in units of each measure\'s median absolute deviation. Phase 10 throughout; V = cue present, H = cue removed.',
              'scripts summary_figs/nf1-nf4; search_sets.csv, braking_events.csv, braking_runs.csv, speed_mode.csv, phase8_mouse.csv')
_t = pd.read_csv(W + '/phase8/phase8_mouse.csv').drop_duplicates('Mouse').set_index('Mouse')
_ss = pd.read_csv(W + '/approach/search_sets.csv'); _h = _ss[_ss.Phase == 10]
_pk = _h.pivot_table(index='Mouse', columns=['Condition', 'Place'], values='Pause time (s)', aggfunc='first')
_tot = _h.groupby(['Mouse', 'Condition'])['Pause time (s)'].sum().unstack()
_ev = pd.read_csv(W + '/approach/braking_events.csv'); _rb = pd.read_csv(W + '/approach/braking_runs.csv')
_sm = pd.read_csv(W + '/approach/speed_mode.csv'); _sm = _sm[_sm.Phase == 10].drop_duplicates('Mouse').set_index('Mouse')
_rows = []
for m in sorted(_t.index):
    g = _t.g.get(m)
    if g not in ('WT', 'Lo', 'Hi'): continue
    d = {'MouseID': m, 'Group': g, '% KO': _t.pct.get(m), 'IED': int(bool(_t.IED.get(m, False))),
         'Sessions to criterion': crit.set_index('MouseID').SesstoCriterion.to_dict().get(int(m), np.nan),
         'Place preference, cue present': _t.V_old_pull.get(m),
         'Rewards, hidden phase 10': _t.P10_rewards.get(m)}
    for cond, lab in [('V', 'cue present'), ('H', 'cue removed')]:
        d['Pause time, ' + lab + ' (s)'] = _tot.get(cond, pd.Series(dtype=float)).get(m)
        for pl in ['current', 'former', 'open']:
            d['Pause at %s goal, %s (s)' % (pl, lab) if pl != 'open' else 'Pause in open interior, ' + lab + ' (s)'] = \
                _pk[(cond, pl)].get(m) if (cond, pl) in _pk.columns else np.nan
        e = _ev[(_ev.Phase == 10) & (_ev.Cond == cond)]
        met = e[(e.cat == '__metres__') & (e.Mouse == m)].d_goal
        cnt = len(e[(e.cat == 'current') & (e.Mouse == m)])
        d['Braking at the goal per 10 m, ' + lab] = cnt / float(met.iloc[0]) * 10 if len(met) and met.iloc[0] > 0 else np.nan
        q = _rb[(_rb.Phase == 10) & (_rb.Cond == cond) & (_rb.Mouse == m)]
        d['Directed runs with braking, ' + lab + ' (%)'] = 100 * q.braked.mean() if len(q) else np.nan
        d['Braking distance, ' + lab + ' (cm)'] = q[q.braked].brake_dist.mean() if q.braked.any() else np.nan
    d['Speed, cue present (cm/s)'] = _sm.V.get(m); d['Speed, cue removed (cm/s)'] = _sm.H.get(m)
    d['Speed, hidden minus cued'] = _sm.d.get(m)
    _rows.append(d)
_ex = pd.DataFrame(_rows)
_ex['Followed in the summary'] = _ex.MouseID.map({9.0: 'WT example', 8.0: 'Lo example', 5.0: 'Hi example'}).fillna('')
for _c in _ex.columns:
    if _c not in ('MouseID', 'Group', 'IED', 'Followed in the summary') and pd.api.types.is_numeric_dtype(_ex[_c]):
        _ex[_c] = _ex[_c].round(2)
r = write_df(ws, r, _ex, 'Per-mouse values, phase 10', fmt={'% KO': '0.00', 'IED': '0'})
autosize(ws, 22); CONTENTS.append(('Summary_examples', 'Per-mouse values behind the standalone summary', 'Summary Figures 1-4'))

# ------------------------------------------------------------------ Patch: per-sweep data
ws, r = sheet('CNO_patch_KO', 'Whole-cell recordings: the five Pten KO neurons, per sweep',
              'Computed from the raw AxoGraph recordings, not from the published figure. One row per sweep at each injected current shared by a neuron\'s baseline and CNO series. Spikes are peaks above -10 mV preceded within 2 ms by dV/dt > 100 mV/ms, accepted when the peak exceeds threshold by 20 mV.',
              'summary: patch/ko_patch_fig.py; identities in patch_cell_identities.csv')
_ps = pd.read_csv(W + '/patch/patch_per_sweep.csv')
_ps = _ps[_ps.group == 'KO'].drop(columns=['group'])
r = write_df(ws, r, _ps, 'Spikes per sweep at matched injected current')
_id = pd.read_csv(W + '/patch/patch_cell_identities.csv')
r = write_df(ws, r, _id[_id.group == 'KO'].drop(columns=['group']), 'Which raw recording each figure label is')
autosize(ws, 20); CONTENTS.append(('CNO_patch_KO', 'Pten KO whole-cell recordings, per sweep', 'Figure 21'))

# ------------------------------------------------------------------ README contents
ws = wb['README']; r = contents_row
for j, h in enumerate(['Sheet', 'Contents', 'Figures'], 1):
    c = ws.cell(r, j, h); c.font = HDR; c.fill = FILL
for nm, desc, figs in CONTENTS:
    r += 1; ws.cell(r, 1, nm).font = TXT; ws.cell(r, 1).hyperlink = f"#'{nm}'!A1"; ws.cell(r, 2, desc).font = TXT; ws.cell(r, 3, figs).font = TXT
for wsx in wb.worksheets:
    for row in wsx.iter_rows():
        for c in row:
            if c.value is not None and c.font.name != F: c.font = Font(name=F, size=c.font.size or 10, bold=c.font.bold, italic=c.font.italic, color=c.font.color)
wb.save(OUT); print('saved', OUT, [s.title for s in wb.worksheets])
