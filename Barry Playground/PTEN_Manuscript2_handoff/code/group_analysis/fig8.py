"""Figure 8: hidden-session means by phase and each mouse's change between phases.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import numpy as np, pandas as pd, itertools, warnings
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import stats
from math import comb
warnings.filterwarnings('ignore')
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','axes.titlesize':10.5,'axes.titleweight':'600','axes.titlecolor':'#0b0b0b','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.7,'axes.axisbelow':True,'legend.frameon':False})
COL={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948'}; MK={'CTL':'o','Lo':'^','Hi':'s'}
df=pd.read_pickle('probe.pkl'); d=df[(df.G3!='UNK')&(df.Condition=='H')]; S=pd.read_pickle('slopes.pkl'); IEDP=df.loc[df.IED=='+','MouseID'].unique()
V=[('NumRewards','Rewards','rewards'),('ReRatio','Rewards per entrance','rewards per entrance'),('PGoalTime','Proportion time in goal','proportion'),('MeanTargSpeed','Mean target speed (cm/s)','cm/s')]
def perm(a,b):
    x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean())
    if comb(len(x),n)<=60000:
        c=t=0
        for idx in itertools.combinations(range(len(x)),n):
            m=np.zeros(len(x),bool); m[list(idx)]=True; t+=1; c+=abs(x[m].mean()-x[~m].mean())>=obs-1e-12
        return c/t
    rng=np.random.default_rng(0); c=0
    for _ in range(50000):
        p=rng.permutation(x); c+=abs(p[:n].mean()-p[n:].mean())>=obs-1e-12
    return (c+1)/50001
def perm(a,b,*_a,**_k):  # switched to Mann-Whitney U (two-sided) for all group comparisons
    from scipy.stats import mannwhitneyu as _mw; import numpy as _np
    a=_np.asarray(a,float); b=_np.asarray(b,float); a=a[~_np.isnan(a)]; b=b[~_np.isnan(b)]
    return _mw(a,b,alternative='two-sided').pvalue

fp=lambda p: 'p < 0.001' if p<.001 else (f'p = {p:.3f}' if p<.01 else f'p = {p:.2f}')
def fm(m):
    if abs(m)<5e-5: return '0.00'
    return f"{m:+.2f}" if abs(m)>=0.1 else (f"{m:+.3f}" if abs(m)>=0.01 else f"{m:+.4f}")
fig,axs=plt.subplots(3,4,figsize=(15.5,11.2),gridspec_kw={'height_ratios':[1.1,1,1]}); rng=np.random.default_rng(4)
for j,(v,lab,unit) in enumerate(V):
    ax=axs[0,j]
    for g,off in [('CTL',-.06),('Lo',0),('Hi',.06)]:
        a=d[d.G3==g].groupby('Phase')[v].agg(['mean','sem'])
        ax.errorbar(np.array([7,8,9,10])+off,a['mean'],yerr=a['sem'],color=COL[g],marker='o',ms=7.5,lw=2.2,elinewidth=1.2,capsize=2.5,mec='#fcfcfb',mew=.8,zorder=3,label={'CTL':'WT (n = 19)','Lo':'Pten KO Lo (n = 5)','Hi':'Pten KO Hi (n = 6)'}[g])
    ax.axvspan(7.5,10.5,color='#f0efec',alpha=.6,zorder=0); ax.set_xlim(6.6,10.4); ax.set_xticks([7,8,9,10]); ax.set_xticklabels(['7\ntrained','8','9','10']); ax.grid(axis='x',visible=False)
    ax.set_title(lab,loc='left'); ax.set_xlabel('Hidden probe phase (8–10 = novel locations)')
    for r,(win,wl) in enumerate([('7-10','phases 7–10'),('8-10 (novel only)','novel only (8–10)')]):
        ax=axs[r+1,j]; sl=S[(v,win)]; allv=np.r_[sl['CTL'],sl['Lo'],sl['Hi']]; lo,hi=allv.min(),allv.max(); span=hi-lo
        ax.axhline(0,color='#52514e',lw=1,zorder=1)
        for i,g in enumerate(['CTL','Lo','Hi']):
            y=sl[g]; ids=np.sort(d[d.G3==g].MouseID.unique()); ie=np.isin(ids,IEDP); xj=i-0.14+rng.uniform(-.1,.1,len(y))
            ax.scatter(xj[~ie],y[~ie],s=36,color=COL[g],marker='o',edgecolor='#fcfcfb',linewidth=.9,alpha=.9,zorder=3)
            ax.scatter(xj[ie],y[ie],s=36,color=COL[g],marker='D',edgecolor='#fcfcfb',linewidth=.9,alpha=.9,zorder=3)
            m,se=y.mean(),stats.sem(y); ax.errorbar(i+0.2,m,yerr=se,fmt='_',color='#0b0b0b',ms=15,mew=2,capsize=3.5,elinewidth=1.3,zorder=4)
            p0=stats.ttest_1samp(y,0).pvalue
            ax.text(i,lo-span*.17,fm(m),ha='center',va='top',fontsize=9,color='#0b0b0b',fontweight='600')
            ax.text(i,lo-span*.28,fp(p0)+' vs 0',ha='center',va='top',fontsize=8.5,color='#0b0b0b' if p0<.05 else '#52514e',fontweight='600' if p0<.05 else '400')
        def br(x1,x2,y,t,b):
            ax.plot([x1,x1,x2,x2],[y-span*.02,y,y,y-span*.02],color='#52514e',lw=1); ax.text((x1+x2)/2,y+span*.01,t,ha='center',va='bottom',fontsize=8.5,color='#0b0b0b',fontweight='600' if b else '400')
        p1=perm(sl['Lo'],sl['CTL']); p2=perm(sl['Hi'],sl['CTL']); print(v,win,'Lo vs WT %.4f Hi vs WT %.4f'%(p1,p2), {g:(round(sl[g].mean(),4),round(stats.ttest_1samp(sl[g],0).pvalue,4)) for g in sl})
        br(0,1,hi+span*.08,'Lo vs WT  '+fp(p1),p1<.05); br(0,2,hi+span*.22,'Hi vs WT  '+fp(p2),p2<.05)
        ax.set_ylim(lo-span*.42,hi+span*.36); ax.set_xlim(-.6,2.6); ax.set_xticks([0,1,2]); ax.set_xticklabels(['WT','Lo KO','Hi KO']); ax.grid(axis='x',visible=False)
        ax.set_title(f'Change per phase, {wl}',loc='left'); ax.set_ylabel(f'{unit} per phase')
h,l=axs[0,0].get_legend_handles_labels(); fig.legend(h,l,loc='upper right',ncol=3,fontsize=9.5,bbox_to_anchor=(.995,.972))
fig.suptitle('Does performance decline with each goal rotation? Hidden goal sessions',x=.006,ha='left',fontsize=13,fontweight='600',color='#0b0b0b',y=.995)
fig.text(.006,.004,'Rows 2–3: each point is one mouse\'s linear slope across phases (diamonds: IED+); bars are mean ± SE. Below each group: mean slope and its test against zero. Brackets: each Pten KO group vs WT (Mann-Whitney U test). Uncorrected.',fontsize=8.5,color='#52514e')
fig.tight_layout(rect=(0,.018,1,.95)); fig.savefig('figs/fig8_hi_trend.png',dpi=160); print('ok')
