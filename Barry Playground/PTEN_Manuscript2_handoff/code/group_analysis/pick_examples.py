"""Ranks mice within each group to suggest example mice (first round of example selection).

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import pandas as pd, numpy as np
g=pd.read_pickle('gz/gz.pkl'); g=g[(g.Condition=='H')&g.G3.isin(['CTL','Lo','Hi'])]
p=pd.read_pickle('probe.pkl'); p=p[(p.Condition=='H')&p.G3.isin(['CTL','Lo','Hi'])]
g['cur']=g.correct*100; g['z1p']=g.z1*100
W=g.pivot_table(index=['G3','Mouse'],columns='Phase',values=['cur','z1p'])
R=p.pivot_table(index=['G3','MouseID'],columns='Phase',values='NumRewards'); R.index.names=['G3','Mouse']
W=W.join(pd.concat({'rew':R},axis=1))
W.columns=[f'{a}{int(b)}' for a,b in W.columns]
feat=[c for c in W.columns]
sd=W[feat].std()
pc=g.drop_duplicates('Mouse').set_index('Mouse').pct
for grp in ['CTL','Lo','Hi']:
    X=W.loc[grp]; m=X.mean()
    d=(((X-m)/sd)**2).mean(axis=1)**.5
    X=X.assign(dist=d, pct=pc.reindex(X.index).values).sort_values('dist')
    print('\n',grp,'group mean:'); print(m.round(1).to_string())
    print(X[['pct','cur7','cur8','z1p8','cur9','z1p9','cur10','z1p10','rew7','rew9','rew10','dist']].round(1).to_string())
