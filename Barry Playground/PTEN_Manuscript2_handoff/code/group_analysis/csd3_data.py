"""Per-mouse table for the theta CSD / CNO / IED section (current data, replaces cno2.py).

Inputs (config.py)
    CSD_SAV        channel-level theta CSD (one row per channel), 'Estimate' = layer label, 'Condition' ZZBa (baseline) or CNO
    CNO_BEHAV_SAV  probe sessions with CNOvsBase = Base / CNO, Condition V (visible) / H (hidden)
    CNO_XLSX       used only for % KO of the KO mice (column 'JB % hits'); PCT_EXTRA adds M29 and M30

Choices
    * CSD per layer = mean of all channels with that layer label in the session.
      Combined measures pool the channels of their layers (as the Data4Claude values did):
      AVG4 = MML1 + MML2 + GCL1 + GCL2, M2G2 = MML2 + GCL2.
    * M26 (WT) is excluded from CSD (EPHYS_EXCLUDE) and kept in behaviour. DKO mice are excluded.
    * M59 baseline CSD = session s4 (M59_BASELINE); its second baseline session (s11) is not used.
    * The M33 CNO session has one channel row with a blank MouseID; mice are identified from SESSID.
    * Goal-zone time = mean PGoalTime of phases 8 and 9, x 100 (percent of session), separately for
      hidden (Goal_*) and visible (Vis_*) sessions. M2 has two visible CNO sessions at phase 9; all are averaged.
    * WT = 0% KO. Lo < 15% KO <= Hi. Mice without % KO (M27, M31: no histology) are dropped.
    * IED status: IEDBIN in the CSD file; for mice with behaviour only, SubGroup == 'IED+'. WT = IED-negative.
Output: work/csd3/csd3.pkl
"""
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, _ROOT)
from config import *
import numpy as np, pandas as pd, pyreadstat

LAYERS = {'AVG4': ['DG MML1', 'DG MML2', 'DG GCL1', 'DG GCL2'], 'M2G2': ['DG MML2', 'DG GCL2'],
          'MML1': ['DG MML1'], 'MML2': ['DG MML2'], 'GCL1': ['DG GCL1'], 'GCL2': ['DG GCL2']}

c, _ = pyreadstat.read_sav(CSD_SAV)
c['mouse'] = c.SESSID.str.extract(r'M(\d+)s')[0].astype(int)
c['Estimate'] = c.Estimate.str.strip()
c = c[(c.Group != 'DKO') & ~c.mouse.isin(EPHYS_EXCLUDE)]
c = c[~((c.mouse == 59) & (c.Condition != 'CNO') & (c.SESSID != M59_BASELINE))]
c['cond'] = np.where(c.Condition == 'CNO', 'cno', 'base')
csd = pd.DataFrame({f'{k}_{cd}': c[(c.cond == cd) & c.Estimate.isin(ls)].groupby('mouse').CSD.mean()
                    for k, ls in LAYERS.items() for cd in ['base', 'cno']})
cinfo = c.groupby('mouse').agg(csd_grp=('Group', 'first'), ied_csd=('IEDBIN', 'max'))

b, _ = pyreadstat.read_sav(CNO_BEHAV_SAV)
b = b[(b.Group != '') & b.Phase.isin([8, 9])]
beh = []
for cond, lab in [('H', 'Goal'), ('V', 'Vis')]:
    g = b[b.Condition == cond].groupby(['MouseID', 'CNOvsBase']).PGoalTime.mean().unstack() * 100
    g.columns = [f'{lab}_{"base" if x == "Base" else "cno"}' for x in g.columns]; beh.append(g)
beh = pd.concat(beh, axis=1); beh.index = beh.index.astype(int)
binfo = b.groupby('MouseID').agg(beh_grp=('Group', 'first'), sub=('SubGroup', 'first')); binfo.index = binfo.index.astype(int)

x4 = pd.read_excel(CNO_XLSX); x4['mouse'] = x4['UVM #'].astype(str).str.replace('M', '').astype(int)
pct = x4.set_index('mouse')['JB % hits'].dropna().to_dict(); pct.update(PCT_EXTRA)

d = csd.join(cinfo, how='outer').join(beh, how='outer').join(binfo, how='left')
d['isWT'] = (d.csd_grp == 'ZCTL') | (d.beh_grp == 'CTL')
d['pct'] = [0.0 if w else pct.get(i, np.nan) for i, w in zip(d.index, d.isWT)]
d = d[d.pct.notna()].copy()
d['ied'] = np.where(d.ied_csd.notna(), d.ied_csd, np.where(d['sub'] == 'IED+', 1, 0)).astype(int)
d['G'] = np.where(d.isWT, 'WT', np.where(d.pct < 15, 'Lo', 'Hi'))
d['K'] = np.where(d.G == 'WT', 'WT', 'KO')
d['mouse'] = d.index
for k in list(LAYERS) + ['Goal', 'Vis']:
    d[f'{k}_chg'] = d[f'{k}_cno'] - d[f'{k}_base']
    d[f'{k}_drop'] = -d[f'{k}_chg']
d.to_pickle(os.path.join(WORK, 'csd3', 'csd3.pkl'))
if __name__ == '__main__':
    pd.set_option('display.width', 250)
    print('CSD, baseline:', {g: sorted(d[(d.G == g) & d.AVG4_base.notna()].index) for g in ['WT', 'Lo', 'Hi']})
    print('CSD, both sessions:', {g: sorted(d[(d.G == g) & d.AVG4_base.notna() & d.AVG4_cno.notna()].index) for g in ['WT', 'Lo', 'Hi']})
    print('Behaviour, baseline and CNO:', {g: sorted(d[(d.G == g) & d.Goal_cno.notna()].index) for g in ['WT', 'Lo', 'Hi']})
    print('IED mice:', sorted(d[d.ied == 1].index))
    print(d[['G', 'pct', 'ied', 'AVG4_base', 'AVG4_cno', 'M2G2_base', 'M2G2_cno', 'Goal_base', 'Goal_cno', 'Vis_base', 'Vis_cno']].round(4).to_string())
