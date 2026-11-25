"""Theta CSD and goal-zone time, baseline vs CNO, for WT and Pten KO mice (Data4Claude.xlsx, version with WT rows). WT are plotted at 0% KO. Group comparisons (Mann-Whitney), paired baseline vs CNO (t-test), group x drug mixed models (random intercept per mouse), regressions on % KO with and without WT, IED vs no IED. Writes cno2.pkl.

Run from any folder; outputs go to work/cno2. Between groups: Mann-Whitney; within groups: paired t-test.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.makedirs(os.path.join(WORK,'cno2'),exist_ok=True); os.chdir(os.path.join(WORK,'cno2'))
import numpy as np, pandas as pd, warnings
from scipy import stats
import statsmodels.formula.api as smf
warnings.filterwarnings('ignore'); pd.set_option('display.width',250)
raw=pd.read_excel(CNO_XLSX)
raw.columns=['grp','mouse','pct','csd_base','csd_cno','b8','b9','goal_base','c8','c9','goal_cno']
raw['mouse']=raw.mouse.astype(str).str.replace('M','').astype(int)
raw['G']=np.where(raw.grp=='WT','WT',np.where(raw.pct<15,'Lo','Hi'))
raw.loc[raw.G=='WT','pct']=0.0
raw['ied']=raw.grp.eq('PTEN -IED')
for c in ['goal_base','goal_cno','b8','b9','c8','c9']: raw[c]*=100
raw['csd_d']=raw.csd_cno-raw.csd_base; raw['csd_pc']=100*raw.csd_d/raw.csd_base; raw['goal_d']=raw.goal_cno-raw.goal_base
raw.to_pickle('cno2.pkl')
print(raw[['G','mouse','pct','ied','csd_base','csd_cno','csd_pc','goal_base','goal_cno','goal_d']].round(4).to_string(index=False))
# check WT baseline behaviour against probe data (hidden P8/P9 PGoalTime)
p=pd.read_pickle(os.path.join(WORK,'probe.pkl'))
q=p[(p.Condition=='H')&p.Phase.isin([8,9])].groupby('MouseID').PGoalTime.mean()*100
chk=raw.dropna(subset=['goal_base']).set_index('mouse').goal_base
print('baseline goal vs probe hidden P8/9 PGoalTime, max abs diff:', (chk-q.reindex(chk.index)).abs().round(3).to_dict())
G=['WT','Lo','Hi']
def grp(v):
    d=raw.dropna(subset=[v]); g={k:d[d.G==k][v] for k in G}
    s=' '.join(f"{k} {g[k].mean():.4f}±{g[k].sem():.4f} (n={len(g[k])})" for k in G)
    pp=' '.join(f"{a}-{b} {stats.mannwhitneyu(g[a],g[b]).pvalue:.3f}" for a,b in [('Lo','WT'),('Hi','WT'),('Lo','Hi')])
    print(f"{v:10s} {s} | MW {pp}")
print('\n### group comparisons'); [grp(v) for v in ['csd_base','csd_cno','csd_d','csd_pc','goal_base','goal_cno','goal_d']]
print('\n### paired baseline vs CNO within group')
for a,b in [('csd_base','csd_cno'),('goal_base','goal_cno')]:
    for k in G+['KO']:
        d=raw.dropna(subset=[a,b]); d=d[d.G!='WT'] if k=='KO' else d[d.G==k]
        t=stats.ttest_rel(d[b],d[a]); print(f"{a[:4]} {k}: n={len(d)} {d[a].mean():.4f} -> {d[b].mean():.4f} ({100*(d[b].mean()-d[a].mean())/d[a].mean():+.0f}%) paired t p={t.pvalue:.4f} down {(d[b]<d[a]).sum()}/{len(d)}")
print('\n### group x drug (mixed model, mouse random intercept)')
for a,b,nm in [('csd_base','csd_cno','csd'),('goal_base','goal_cno','goal')]:
    d=raw.dropna(subset=[a,b])[['mouse','G',a,b]].melt(id_vars=['mouse','G'],value_vars=[a,b],var_name='drug',value_name='y')
    d['drug']=(d.drug==b).astype(int)
    for ref in ['WT','Lo']:
        d['Gc']=pd.Categorical(d.G,[ref]+[x for x in G if x!=ref])
        f=smf.mixedlm('y ~ Gc*drug',d,groups=d.mouse).fit()
        print(nm,'ref',ref,{k:(round(f.params[k],4),round(f.pvalues[k],4)) for k in f.params.index if 'drug' in k})
print('\n### regression on % KO, WT at 0 (all mice) and KO only')
for v in ['csd_base','csd_cno','csd_d','goal_base','goal_cno','goal_d']:
    for lab,d in [('all',raw),('KO only',raw[raw.G!='WT'])]:
        d=d.dropna(subset=[v]); r=stats.pearsonr(d.pct,d[v]); s=stats.spearmanr(d.pct,d[v]); lr=stats.linregress(d.pct,d[v])
        print(f"{v:10s} {lab:8s} n={len(d)} r={r.statistic:+.2f} p={r.pvalue:.3f} rho={s.statistic:+.2f} p={s.pvalue:.3f} slope={lr.slope:+.5f}")
print('\n### IED vs no IED (KO), and WT')
for v in ['csd_base','csd_cno','csd_d']:
    d=raw.dropna(subset=[v]); a=d[(d.G!='WT')&d.ied][v]; b=d[(d.G!='WT')&~d.ied][v]; w=d[d.G=='WT'][v]
    print(v,f"IED {a.mean():.4f} (n={len(a)}) noIED {b.mean():.4f} (n={len(b)}) WT {w.mean():.4f}: IED-noIED {stats.mannwhitneyu(a,b).pvalue:.3f} IED-WT {stats.mannwhitneyu(a,w).pvalue:.3f} noIED-WT {stats.mannwhitneyu(b,w).pvalue:.3f}")
