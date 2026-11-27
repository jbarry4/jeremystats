"""EXPLORATORY. Statistics for approach_compute.py. Not in the report.
## NOT IN MATLAB.
"""
import os, sys
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [_HERE, os.path.join(_HERE, 'path_analysis')]
from config import DATA_ROOT, WORK, FIGS
import pandas as pd, numpy as np
from scipy.stats import mannwhitneyu as MW, ttest_rel
E=pd.read_pickle(WORK+'/approach/entries.pkl')
p=pd.read_pickle(WORK+'/probe.pkl'); G=p.drop_duplicates('MouseID').set_index('MouseID').G3
E['G3']=E.Mouse.map(G)
def agg(df):
    return pd.Series(dict(heading=df.heading.mean(),straight=df.straight.mean(),n=len(df),
        heading_rew=df[df.rewarded].heading.mean(),straight_rew=df[df.rewarded].straight.mean(),n_rew=df.rewarded.sum(),
        start_dist=df.start_dist.mean()))
M=E.groupby(['G3','Mouse','Phase','Cond']).apply(agg,include_groups=False).reset_index()
M.to_pickle(WORK+'/approach/mouse_phase.pkl')
mw=lambda a,b: MW(a,b,alternative='two-sided').pvalue
out=[]
for v in ['heading','straight','heading_rew','straight_rew']:
    w=M.pivot_table(index=['G3','Mouse'],columns=['Cond','Phase'],values=v)
    for ph in [7,8,9,10,'all']:
        if ph=='all': Vv=w['V'].mean(axis=1); Hh=w['H'].mean(axis=1)
        else: Vv=w[('V',ph)]; Hh=w[('H',ph)]
        D=Vv-Hh
        rec=dict(var=v,phase=ph)
        for g in ['CTL','Lo','Hi']:
            vv,hh=Vv.loc[g],Hh.loc[g]; ok=vv.notna()&hh.notna()
            rec[f'{g}_V']=vv.mean(); rec[f'{g}_H']=hh.mean(); rec[f'{g}_VH_p']=ttest_rel(vv[ok],hh[ok]).pvalue; rec[f'{g}_n']=ok.sum()
        for g in ['Lo','Hi']:
            for nm,ser in [('V',Vv),('H',Hh),('D',D)]:
                rec[f'{g}_{nm}_vsWT']=mw(ser.loc[g].dropna(),ser.loc['CTL'].dropna())
        out.append(rec)
R=pd.DataFrame(out); R.to_pickle(WORK+'/approach/stats.pkl')
pd.set_option('display.width',250)
for v in R['var'].unique():
    print('\n==',v); print(R[R['var']==v].drop(columns='var').round(3).T.to_string())
