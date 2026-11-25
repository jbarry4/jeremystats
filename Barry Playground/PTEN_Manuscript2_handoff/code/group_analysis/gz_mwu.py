"""Current goal vs trained zone within group and vs WT -> mwu.pkl (used by gz_bars_fig3.py). RECONSTRUCTED: this table was first built interactively; this script reproduces the saved table exactly for every column the figures use.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work/gz) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(os.path.join(WORK,'gz'))
import pandas as pd, numpy as np
from scipy.stats import mannwhitneyu as mw, wilcoxon, ttest_rel
S=pd.read_pickle('gz.pkl'); rows=[]
for cond in ['H','V']:
    for ph in [7,8,9,10]:
        for g in ['CTL','Lo','Hi','PTEN']:
            x=S[(S.Condition==cond)&(S.Phase==ph)&((S.G3==g) if g!='PTEN' else (S.Group=='PTEN'))]
            w=S[(S.Condition==cond)&(S.Phase==ph)&(S.G3=='CTL')]
            cur=x.correct*100; orig=x.trained.fillna(x.correct)*100
            r=dict(cond=cond,phase=ph,group=g,cur=cur.mean(),orig=orig.mean())
            r['mwu_cur_vsWT']=np.nan if g=='CTL' else mw(x.correct,w.correct,method='exact').pvalue
            if ph>7:
                r['wilcoxon_cur_vs_orig']=wilcoxon(cur,orig).pvalue; r['n_cur_gt']=int((cur>orig).sum()); r['n']=len(cur)
                r['p_cur_vs_orig']=ttest_rel(cur,orig).pvalue
                if g!='CTL': r['mwu_pref_vsWT']=mw(x.correct-x.trained,w.correct-w.trained).pvalue
            rows.append(r)
pd.DataFrame(rows).to_pickle('mwu.pkl'); print(pd.DataFrame(rows).round(4).to_string())
