"""SUPERSEDED by cno2.py / cno2_fig.py (the earlier version, Pten KO mice only, before the WT rows were added). Theta CSD and goal-zone time before and after CNO (Data4Claude.xlsx): paired tests and regressions on % KO -> cno.pkl.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import numpy as np, pandas as pd, openpyxl, warnings
from scipy import stats
import statsmodels.api as sm
warnings.filterwarnings('ignore'); pd.set_option('display.width',220)
ws=openpyxl.load_workbook(CNO_XLSX,data_only=True)['Sheet1']
rows=list(ws.iter_rows(values_only=True)); df=pd.DataFrame(rows[1:],columns=['grp','mouse','pct','csd_base','csd_cno','b8','b9','goal_base','c8','c9','goal_cno'])
df['ied']=df.grp.str.contains('-IED'); df['goal_base']*=100; df['goal_cno']*=100; df['csd_d']=df.csd_cno-df.csd_base; df['goal_d']=df.goal_cno-df.goal_base
df['csd_pct']=100*df.csd_d/df.csd_base
df.to_pickle('cno.pkl'); print(df[['mouse','ied','pct','csd_base','csd_cno','csd_d','csd_pct','goal_base','goal_cno','goal_d']].sort_values('pct').round(4).to_string(index=False))
def reg(name,x,y):
    m=~(np.isnan(x)|np.isnan(y)); x=x[m]; y=y[m]; r=stats.pearsonr(x,y); ci=r.confidence_interval(); s=stats.spearmanr(x,y); f=sm.OLS(y,sm.add_constant(x)).fit(); b=f.params[1]; bl,bh=f.conf_int()[1]
    loo=[stats.pearsonr(np.delete(x,i),np.delete(y,i)).statistic for i in range(len(x))]
    print(f"{name}: n={len(x)} r={r.statistic:+.2f} [{ci.low:+.2f},{ci.high:+.2f}] p={r.pvalue:.4f} R2={r.statistic**2:.2f} | rho={s.statistic:+.2f} p={s.pvalue:.4f} | slope={b:+.5f} [{bl:+.5f},{bh:+.5f}] intercept={f.params[0]:.5f} | LOO r {min(loo):+.2f}..{max(loo):+.2f}")
x=df.pct.values.astype(float)
for lab,xx in [('%KO as in file',x),('M33 = 8.82 (earlier value)',np.where(df.mouse==33,8.82,x))]:
    print('\n#####',lab)
    reg('CSD baseline',xx,df.csd_base.values.astype(float)); reg('CSD CNO',xx,df.csd_cno.values.astype(float)); reg('CSD change (CNO-base)',xx,df.csd_d.values.astype(float)); reg('CSD % change',xx,df.csd_pct.values.astype(float))
    reg('Goal baseline',xx,df.goal_base.values.astype(float)); reg('Goal CNO',xx,df.goal_cno.values.astype(float)); reg('Goal change',xx,df.goal_d.values.astype(float))
print('\n##### paired baseline vs CNO')
for a,b,l in [('csd_base','csd_cno','CSD'),('goal_base','goal_cno','Goal %')]:
    d=df.dropna(subset=[a,b]); t=stats.ttest_rel(d[b],d[a]); w=stats.wilcoxon(d[b],d[a])
    print(f"{l} all n={len(d)}: {d[a].mean():.4f} -> {d[b].mean():.4f} diff={ (d[b]-d[a]).mean():+.4f} t p={t.pvalue:.4f} wilcoxon p={w.pvalue:.4f} n_down={(d[b]<d[a]).sum()}")
    for nm,sel in [('Lo(<15%)',d.pct<15),('Hi(>15%)',d.pct>15),('IED',d.ied),('NoIED',~d.ied)]:
        s=d[sel]; t=stats.ttest_rel(s[b],s[a]); print(f"   {nm} n={len(s)}: {s[a].mean():.4f} -> {s[b].mean():.4f} diff={(s[b]-s[a]).mean():+.4f} t p={t.pvalue:.4f}")
    dd=d[b]-d[a]; print('   change Hi vs Lo: MWU p=%.4f Welch p=%.4f'%(stats.mannwhitneyu(dd[d.pct>15],dd[d.pct<15]).pvalue, stats.ttest_ind(dd[d.pct>15],dd[d.pct<15],equal_var=False).pvalue))
print('\n##### group diffs Hi vs Lo, IED vs not')
for v in ['csd_base','csd_cno','goal_base','goal_cno']:
    d=df.dropna(subset=[v]); print(v,'Hi %.4f Lo %.4f MWU p=%.4f | IED %.4f NoIED %.4f MWU p=%.4f'%(d[d.pct>15][v].mean(),d[d.pct<15][v].mean(),stats.mannwhitneyu(d[d.pct>15][v],d[d.pct<15][v]).pvalue,d[d.ied][v].mean(),d[~d.ied][v].mean(),stats.mannwhitneyu(d[d.ied][v],d[~d.ied][v]).pvalue))
print('\n##### CSD vs goal time'); d=df.dropna(subset=['goal_base'])
for a,b in [('csd_base','goal_base'),('csd_cno','goal_cno'),('csd_d','goal_d')]:
    r=stats.pearsonr(d[a],d[b]); s=stats.spearmanr(d[a],d[b]); print(a,b,f"r={r.statistic:+.2f} p={r.pvalue:.3f} rho={s.statistic:+.2f} p={s.pvalue:.3f}")
