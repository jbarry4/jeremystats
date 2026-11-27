"""Figure 7: phase 10 hidden session by group.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import numpy as np, pandas as pd, warnings
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
warnings.filterwarnings('ignore')
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','axes.titlesize':10.5,'axes.titleweight':'600','axes.titlecolor':'#0b0b0b','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.7,'axes.axisbelow':True})
COL={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948'}; MK={'CTL':'o','Lo':'^','Hi':'s'}
df=pd.read_pickle('probe.pkl'); R=pd.read_pickle('phase_tab.pkl'); k=df[(df.Condition=='H')&(df.Phase==10)&(df.G3!='UNK')]
V=[('ReRatio','Rewards per entrance'),('NumRewards','Rewards'),('MeanTargSpeed','Mean target speed (cm/s)'),('MeanSpeed','Mean speed (cm/s)')]
fmt=lambda p: 'p < 0.001' if p<.001 else f'p = {p:.3f}' if p<.01 else f'p = {p:.2f}'
fig,axs=plt.subplots(1,4,figsize=(12.5,4.2)); rng=np.random.default_rng(2)
for ax,(v,lab) in zip(axs,V):
    r=R[(R.cond=='H')&(R['var']==v)&(R.phase==10)].iloc[0]; ymax=k[v].max(); ymin=min(0,k[v].min()); span=ymax-ymin
    for i,g in enumerate(['CTL','Lo','Hi']):
        kk=k[k.G3==g]; d=kk[v].values; xj=i-0.12+rng.uniform(-.09,.09,len(d)); ie=(kk.IED=='+').values
        ax.scatter(xj[~ie],d[~ie],s=38,color=COL[g],marker='o',edgecolor='#fcfcfb',linewidth=.9,alpha=.9,zorder=3)
        ax.scatter(xj[ie],d[ie],s=38,color=COL[g],marker='D',edgecolor='#fcfcfb',linewidth=.9,alpha=.9,zorder=3)
        m,se=d.mean(),d.std(ddof=1)/np.sqrt(len(d)); ax.errorbar(i+0.2,m,yerr=se,fmt='_',color='#0b0b0b',ms=15,mew=2,capsize=3.5,elinewidth=1.3,zorder=4)
        ax.text(i+0.31,m,f"{m:.2f}" if m<1 else f"{m:.1f}",va='center',ha='left',fontsize=9,color='#0b0b0b')
    def br(x1,x2,y,t): ax.plot([x1,x1,x2,x2],[y-span*.015,y,y,y-span*.015],color='#52514e',lw=1); ax.text((x1+x2)/2,y+span*.01,t,ha='center',va='bottom',fontsize=8.5,color='#0b0b0b')
    br(1,2,ymax+span*.07,'Lo vs Hi  '+fmt(r.p_LoHi)); br(0,2,ymax+span*.19,'Hi vs WT  '+fmt(r.p_HiCTL)); br(0,1,ymax+span*.31,'Lo vs WT  '+fmt(r.p_LoCTL))
    ax.set_ylim(ymin,ymax+span*.42); ax.set_xlim(-.5,2.75); ax.set_xticks([0,1,2]); ax.set_xticklabels(['WT\nn = 19','Lo KO\nn = 5','Hi KO\nn = 6']); ax.set_title(lab,loc='left'); ax.grid(axis='x',visible=False)
fig.suptitle('Last hidden probe (phase 10): Hi KO mice run faster and earn less; Lo KO mice resemble WT per entrance',x=.008,ha='left',fontsize=12,fontweight='600',color='#0b0b0b',y=.995)
fig.text(.008,.005,'Each point is one mouse (diamonds: IED+); bars are mean ± SE. Mann-Whitney p-values, uncorrected.',fontsize=8.5,color='#52514e')
fig.tight_layout(rect=(0,.03,1,.95)); fig.savefig('figs/fig7_phase10_groups.png',dpi=190)
