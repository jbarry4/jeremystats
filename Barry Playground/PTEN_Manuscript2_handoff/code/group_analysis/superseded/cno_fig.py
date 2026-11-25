"""SUPERSEDED by cno2.py / cno2_fig.py (the earlier version, Pten KO mice only, before the WT rows were added). Figures 9 and 10: theta CSD and goal-zone time vs % KO, baseline and CNO.

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
from matplotlib.lines import Line2D
from scipy import stats
warnings.filterwarnings('ignore')
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':10.5,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','axes.titlesize':11.5,'axes.titleweight':'600','axes.titlecolor':'#0b0b0b','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.7,'axes.axisbelow':True,'legend.frameon':False})
LO,HI='#008300','#e34948'
df=pd.read_pickle('cno.pkl')
def panel(ax,x,y,ids,ied,title,ylab):
    m=~(np.isnan(x)|np.isnan(y)); x=x[m]; y=y[m]; ids=ids[m]; ied=ied[m]; n=len(x)
    b,a,r,p,se=stats.linregress(x,y); xx=np.linspace(0,31,200); yh=a+b*xx
    s=np.sqrt(np.sum((y-(a+b*x))**2)/(n-2)); sxx=np.sum((x-x.mean())**2); t=stats.t.ppf(.975,n-2); ci=t*s*np.sqrt(1/n+(xx-x.mean())**2/sxx)
    ax.fill_between(xx,yh-ci,yh+ci,color='#b9b8b2',alpha=.38,lw=0,zorder=1); ax.plot(xx,yh-ci,color='#9a9993',lw=.8,zorder=2); ax.plot(xx,yh+ci,color='#9a9993',lw=.8,zorder=2)
    ax.plot(xx,yh,color='#0b0b0b',lw=1.8,zorder=3)
    for xi,yi,i,e in zip(x,y,ids,ied):
        ax.scatter([xi],[yi],s=74,marker='D' if e else 'o',color=HI if xi>15 else LO,edgecolor='#fcfcfb',linewidth=1.1,zorder=4)
        ax.annotate(f"M{int(i)}",(xi,yi),xytext=(6,5),textcoords='offset points',fontsize=8,color='#52514e',zorder=5)
    ax.axvline(15,color='#9a9993',lw=1,ls=(0,(4,3)),zorder=1)
    ax.set_title(title,loc='left'); ax.set_xlabel('% granule cells Pten KO'); ax.set_ylabel(ylab); ax.set_xlim(0,31)
    ax.text(.03,.97,f"r = {r:+.2f},  p = {p:.2f},  n = {n}\nslope = {b:+.2g} per 1% KO",transform=ax.transAxes,ha='left',va='top',fontsize=9.5,color='#0b0b0b',bbox=dict(facecolor='#fcfcfb',edgecolor='none',alpha=.85,pad=2))
    return (yh-ci).min(),(yh+ci).max()
leg=[Line2D([],[],marker='o',ls='',color=LO,ms=8,mec='#fcfcfb',label='Lo KO (<15%), no IED'),Line2D([],[],marker='o',ls='',color=HI,ms=8,mec='#fcfcfb',label='Hi KO (>15%), no IED'),Line2D([],[],marker='D',ls='',color=HI,ms=8,mec='#fcfcfb',label='Hi KO (>15%), IED'),Line2D([],[],color='#0b0b0b',lw=1.8,label='Best-fit line'),plt.Rectangle((0,0),1,1,fc='#b9b8b2',alpha=.5,ec='#9a9993',label='95% confidence band')]
x=df.pct.values.astype(float); ids=df.mouse.values; ied=df.ied.values
for fn,cols,ylab,sup,ylim in [('figA_csd_pctko.png',('csd_base','csd_cno'),'Theta CSD, MML–GCL (as supplied)','Theta CSD vs % KO: baseline and after CNO',None),('figB_goal_pctko.png',('goal_base','goal_cno'),'Time in goal zone (% of session), phases 8–9 mean','Goal-zone time vs % KO: baseline and after CNO',None)]:
    fig,axs=plt.subplots(1,2,figsize=(11.5,5.0),sharey=True); lims=[]
    for ax,c,t in zip(axs,cols,['Baseline','Post-CNO']):
        lims.append(panel(ax,x,df[c].values.astype(float),ids,ied,t,ylab)); ax.tick_params(labelleft=True)
    ally=np.r_[df[cols[0]].dropna().values,df[cols[1]].dropna().values]; lo=min(ally.min(),min(l[0] for l in lims)); hi=max(ally.max(),max(l[1] for l in lims)); pad=(hi-lo)*.06
    axs[0].set_ylim(lo-pad,hi+pad*3.2); axs[1].set_ylabel('')
    axs[1].text(15.3,lo-pad*.6,'15% line',fontsize=8.5,color='#52514e',va='bottom')
    fig.legend(handles=leg,loc='lower center',ncol=5,fontsize=9,handletextpad=.4,columnspacing=1.3)
    fig.suptitle(sup,x=.008,ha='left',fontsize=13,fontweight='600',color='#0b0b0b',y=.99)
    fig.tight_layout(rect=(0,.06,1,.95)); fig.savefig(fn,dpi=180); plt.close()
print('ok')
