"""Figures 9 and 10: theta CSD and goal-zone time vs % KO (WT at 0) at baseline and after CNO, baseline -> CNO by group, and change vs % KO. Best-fit line through all mice with 95% confidence band, in the style of LaSarge et al. (2021).

Run from any folder; outputs go to work/cno2. Between groups: Mann-Whitney; within groups: paired t-test.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.makedirs(os.path.join(WORK,'cno2'),exist_ok=True); os.chdir(os.path.join(WORK,'cno2'))
import numpy as np, pandas as pd, warnings, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy import stats
warnings.filterwarnings('ignore')
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.6,'axes.axisbelow':True,'legend.frameon':False})
INK='#0b0b0b'; MUT='#52514e'
COL={'WT':'#2a78d6','Lo':'#008300','Hi':'#e34948'}
D=''
df=pd.read_pickle(D+'cno2.pkl')
rng=np.random.default_rng(3)
df['xj']=np.where(df.G=='WT',rng.uniform(-0.7,0.7,len(df)),df.pct)
def scatter(ax,v,title,ylab):
    d=df.dropna(subset=[v]); x=d.pct.values; y=d[v].values; n=len(x)
    b,a,r,p,se=stats.linregress(x,y); xx=np.linspace(-1,31,200); yh=a+b*xx
    s=np.sqrt(np.sum((y-(a+b*x))**2)/(n-2)); sxx=np.sum((x-x.mean())**2); t=stats.t.ppf(.975,n-2); ci=t*s*np.sqrt(1/n+(xx-x.mean())**2/sxx)
    ax.fill_between(xx,yh-ci,yh+ci,color='#b9b8b2',alpha=.35,lw=0,zorder=1); ax.plot(xx,yh,color=INK,lw=1.5,zorder=3)
    for _,rr in d.iterrows():
        ax.scatter(rr.xj,rr[v],s=34,marker='D' if rr.ied else 'o',color=COL[rr.G],edgecolor='#fcfcfb',linewidth=0.8,zorder=4)
    ax.axvline(15,color='#9a9993',lw=0.8,ls=(0,(4,3)),zorder=1)
    ax.set_xlim(-2,31); ax.set_xlabel('% granule cells Pten KO (WT = 0)',fontsize=8)
    ax.set_title(title,fontsize=9.5,color=INK,fontweight='semibold',loc='left',pad=16); ax.set_ylabel(ylab,fontsize=8)
    ax.text(0,1.015,f"all mice: r = {r:+.2f}, p = {p:.3f}, n = {n}",transform=ax.transAxes,ha='left',va='bottom',fontsize=7.6,color=MUT)
def paired(ax,a,b,ylab):
    for gi,g in enumerate(['WT','Lo','Hi']):
        d=df[(df.G==g)].dropna(subset=[a,b]); xs=np.array([gi-0.18,gi+0.18])
        for _,rr in d.iterrows(): ax.plot(xs,[rr[a],rr[b]],color=COL[g],alpha=0.35,lw=0.8)
        ax.plot(xs,[d[a].mean(),d[b].mean()],color=COL[g],lw=2.2,marker='o',ms=4.5,mec='#fcfcfb')
        p=stats.ttest_rel(d[b],d[a]).pvalue; lab='**' if p<.01 else '*' if p<.05 else 'ns'
        ax.text(gi,1.0,f"{lab}\nn={len(d)}",transform=ax.get_xaxis_transform(),ha='center',va='bottom',fontsize=7.4,color=INK if lab!='ns' else MUT)
    ax.set_xticks([0,1,2]); ax.set_xticklabels(['WT','Lo KO','Hi KO'],fontsize=8); ax.set_xlim(-0.5,2.5); ax.set_ylabel(ylab,fontsize=8)
    ax.set_title('Baseline → CNO, by group',fontsize=9.5,color=INK,fontweight='semibold',loc='left',pad=22)
leg=[Line2D([],[],marker='o',ls='',color=COL['WT'],ms=6,mec='#fcfcfb',label='WT'),Line2D([],[],marker='o',ls='',color=COL['Lo'],ms=6,mec='#fcfcfb',label='Lo KO (<15%)'),
     Line2D([],[],marker='o',ls='',color=COL['Hi'],ms=6,mec='#fcfcfb',label='Hi KO (>15%), no IED'),Line2D([],[],marker='D',ls='',color=COL['Hi'],ms=6,mec='#fcfcfb',label='Hi KO, IED'),
     Line2D([],[],color=INK,lw=1.5,label='Best fit, all mice'),plt.Rectangle((0,0),1,1,fc='#b9b8b2',alpha=.5,ec='none',label='95% confidence band')]
for fn,(a,b,dv),ylab,sup,dl in [('figA_csd.png',('csd_base','csd_cno','csd_d'),'Theta CSD, MML–GCL','Theta CSD: WT and Pten KO, baseline and after CNO','CNO − baseline'),
                              ('figB_goal.png',('goal_base','goal_cno','goal_d'),'Time in goal (% of session), P8–9','Goal-zone time: WT and Pten KO, baseline and after CNO','CNO − baseline (points)')]:
    fig,axs=plt.subplots(2,2,figsize=(6.6,6.4)); axs=axs.ravel()
    scatter(axs[0],a,'Baseline',ylab); scatter(axs[1],b,'After CNO',ylab)
    lo=min(axs[0].get_ylim()[0],axs[1].get_ylim()[0]); hi=max(axs[0].get_ylim()[1],axs[1].get_ylim()[1])
    for ax in axs[:2]: ax.set_ylim(lo,hi)
    paired(axs[2],a,b,ylab); scatter(axs[3],dv,'Change with CNO',dl); axs[3].axhline(0,color='#9a9993',lw=0.8)
    fig.legend(handles=leg,loc='lower center',ncol=3,fontsize=7.6,handletextpad=.4,columnspacing=1.2)
    fig.suptitle(sup,x=.01,ha='left',fontsize=11.5,fontweight='semibold',color=INK,y=.99)
    fig.tight_layout(rect=(0,.075,1,.96),h_pad=1.6,w_pad=1.4); fig.savefig(D+fn,dpi=200); plt.close()
print('ok')
