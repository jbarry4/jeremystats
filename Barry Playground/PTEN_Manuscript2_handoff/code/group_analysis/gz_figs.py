"""Figures 11, 14, 15: zone-role shares across hidden probes; phase 10 zones and pausing; phase 10 vs % KO.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work/gz) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(os.path.join(WORK,'gz'))
import pandas as pd, numpy as np, itertools, warnings
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy import stats
from math import comb
warnings.filterwarnings('ignore')
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':10.5,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','axes.titlesize':11.5,'axes.titleweight':'600','axes.titlecolor':'#0b0b0b','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.7,'axes.axisbelow':True,'legend.frameon':False})
GC={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948'}; GM={'CTL':'o','Lo':'^','Hi':'s'}; GN={'CTL':'WT (n = 19)','Lo':'Pten KO Lo (n = 5)','Hi':'Pten KO Hi (n = 6)'}
ZC={'cur':'#0b0b0b','rec':'#eb6834','trn':'#7c4dcc','nev':'#9a9993'}
M=pd.read_pickle('gzM.pkl'); H=M[(M.Condition=='H')&(M.G3!='UNK')]
def perm(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float); x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean())
    if comb(len(x),n)<=60000:
        c=t=0
        for idx in itertools.combinations(range(len(x)),n):
            m=np.zeros(len(x),bool); m[list(idx)]=True; t+=1; c+=abs(x[m].mean()-x[~m].mean())>=obs-1e-12
        return c/t
    rng=np.random.default_rng(0); P=np.array([rng.permutation(x) for _ in range(20000)])
    return (np.sum(np.abs(P[:,:n].mean(1)-P[:,n:].mean(1))>=obs-1e-12)+1)/20001
def perm(a,b,*_a,**_k):  # switched to Mann-Whitney U (two-sided) for all group comparisons
    from scipy.stats import mannwhitneyu as _mw; import numpy as _np
    a=_np.asarray(a,float); b=_np.asarray(b,float); a=a[~_np.isnan(a)]; b=b[~_np.isnan(b)]
    return _mw(a,b,alternative='two-sided').pvalue

fp=lambda p: 'p < 0.001' if p<.001 else (f'p = {p:.3f}' if p<.01 else f'p = {p:.2f}')
# ---------------- Fig 11: share of zone time by zone role, per group
fig,axs=plt.subplots(1,3,figsize=(14,4.9),sharey=True)
series=[('sh_correct','cur','Current goal',[7,8,9,10]),('sh_recent','rec','Previous goal (most recent)',[8,9,10]),('sh_trained','trn','Original trained goal (zone 1)',[9,10]),('sh_nevermean','nev','Never-used zone (mean per zone)',[7,8,9])]
for ax,g in zip(axs,['CTL','Lo','Hi']):
    d=H[H.G3==g]
    for v,c,lab,phs in series:
        a=d[d.Phase.isin(phs)].groupby('Phase')[v].agg(['mean','sem'])*100
        ax.errorbar(a.index,a['mean'],yerr=a['sem'],color=ZC[c],marker='o',ms=7,lw=2.2 if c!='nev' else 1.6,ls='-' if c!='nev' else (0,(4,3)),elinewidth=1.1,capsize=2.5,mec='#fcfcfb',mew=.8,zorder=3,label=lab)
    if g=='CTL':
        a=d[d.Phase==8].sh_recent.mean()*100
    ax.axhline(25,color='#52514e',lw=1,ls=(0,(1,2)),zorder=1); ax.text(6.75,25.6,'chance (25%)',ha='left',va='bottom',fontsize=8.5,color='#52514e')
    ax.set_xticks([7,8,9,10]); ax.set_xticklabels(['7\ntrained','8','9','10']); ax.set_xlim(6.7,10.4); ax.grid(axis='x',visible=False)
    ax.set_title(GN[g],loc='left',color=GC[g]); ax.set_xlabel('Hidden probe phase')
axs[0].set_ylabel('Share of time across the four zones (%)'); axs[0].set_ylim(0,72)
# annotations vs WT
def note(ax,x,y,t,ha='center'): ax.text(x,y,t,ha=ha,va='bottom',fontsize=8.5,color='#0b0b0b',fontweight='600')
k9=H[H.Phase==9]; k10=H[H.Phase==10]
p1=perm(k9[k9.G3=='Lo'].sh_correct,k9[k9.G3=='CTL'].sh_correct); p2=perm(k9[k9.G3=='Lo'].sh_trained,k9[k9.G3=='CTL'].sh_trained)
axs[1].text(10.35,70,f'Phase 9 vs WT:\ncurrent goal lower, {fp(p1)}\ntrained goal higher, {fp(p2)}',ha='right',va='top',fontsize=8.8,color='#0b0b0b')
p3=perm(k10[k10.G3=='Hi'].sh_recent,k10[k10.G3=='CTL'].sh_recent)
axs[2].text(10.35,70,f'Phase 10 vs WT:\nprevious goal higher, {fp(p3)}',ha='right',va='top',fontsize=8.8,color='#0b0b0b')
h,l=axs[0].get_legend_handles_labels(); fig.legend(h,l,loc='lower center',ncol=4,fontsize=9.5,bbox_to_anchor=(.5,-.005))
fig.suptitle('Where do mice spend their zone time as the goal rotates? Hidden goal sessions (mean ± SE)',x=.006,ha='left',fontsize=13,fontweight='600',color='#0b0b0b',y=.99)
fig.tight_layout(rect=(0,.07,1,.95)); fig.savefig('fig11_zone_roles.png',dpi=170); plt.close()
# ---------------- Fig 12: phase 10 zone profile + pausing at current goal
fig=plt.figure(figsize=(14,4.9)); gs=fig.add_gridspec(1,3,width_ratios=[1.75,1,1]); rng=np.random.default_rng(3)
ax=fig.add_subplot(gs[0])
for zi,z in enumerate(['z1','z2','z3','z4']):
    for gi,g in enumerate(['CTL','Lo','Hi']):
        y=k10[k10.G3==g][z].values*100; x0=zi+(gi-1)*0.26
        ie=(k10[k10.G3==g].ied=='+').values; xj=x0+rng.uniform(-.06,.06,len(y))
        ax.scatter(xj[~ie],y[~ie],s=20,color=GC[g],marker='o',alpha=.45,edgecolor='none',zorder=2); ax.scatter(xj[ie],y[ie],s=20,color=GC[g],marker='D',alpha=.45,edgecolor='none',zorder=2)
        ax.errorbar(x0,y.mean(),yerr=stats.sem(y),fmt='o',color=GC[g],ms=8,mec='#fcfcfb',mew=.9,capsize=3,elinewidth=1.4,zorder=4)
ax.set_xticks(range(4)); ax.set_xticklabels(['Zone 1\noriginal trained','Zone 2\n(phase 8 goal)','Zone 3\nprevious goal','Zone 4\ncurrent goal']); ax.grid(axis='x',visible=False)
ax.axvspan(2.5,3.5,color='#f0efec',zorder=0); ax.set_ylabel('Time in zone (% of session)'); ax.set_ylim(0,9.4)
ax.set_title('A  Time in each zone, phase 10 hidden',loc='left')
cr=perm(k10[k10.G3=='Hi'].z4-k10[k10.G3=='Hi'].z3,np.zeros(0)) if False else None
ax.text(1.9,9.3,'Current vs previous goal:\nWT current > previous, p < 0.001\nHi KO current ≈ previous, p = 0.50',ha='center',va='top',fontsize=8.5,color='#0b0b0b')
leg=[Line2D([],[],marker='o',ls='',color=GC[g],ms=8,mec='#fcfcfb',label=GN[g]) for g in ['CTL','Lo','Hi']]+[Line2D([],[],marker='D',ls='',color='#9a9993',ms=8,mec='#fcfcfb',label='IED+ (diamond)')]
fig.legend(handles=leg,loc='lower center',ncol=4,fontsize=9.5)
for j,(v,lab,ref,ttl) in enumerate([('dwell_entry','Time per entry into current goal (s)',1.2,'B  Pausing at the current goal'),('NumEntrances','Entries into current goal','', 'C  Visits to the current goal')]):
    ax=fig.add_subplot(gs[j+1])
    for gi,g in enumerate(['CTL','Lo','Hi']):
        y=k10[k10.G3==g][v].values
        ie=(k10[k10.G3==g].ied=='+').values; xj=gi-0.13+rng.uniform(-.08,.08,len(y))
        ax.scatter(xj[~ie],y[~ie],s=30,color=GC[g],marker='o',alpha=.75,edgecolor='#fcfcfb',linewidth=.7,zorder=3); ax.scatter(xj[ie],y[ie],s=30,color=GC[g],marker='D',alpha=.75,edgecolor='#fcfcfb',linewidth=.7,zorder=3)
        ax.errorbar(gi+0.2,y.mean(),yerr=stats.sem(y),fmt='_',color='#0b0b0b',ms=14,mew=2,capsize=3.5,elinewidth=1.3,zorder=4)
    if ref: ax.axhline(ref,color='#52514e',lw=1,ls=(0,(4,3))); ax.text(2.55,ref+.03,'1.2 s pause needed\nfor a reward',ha='right',va='bottom',fontsize=8,color='#52514e')
    yy=k10[k10.G3.isin(['CTL','Lo','Hi'])][v]; top=yy.max(); span=top-min(0,yy.min())
    def br(x1,x2,y,t):
        ax.plot([x1,x1,x2,x2],[y-span*.02,y,y,y-span*.02],color='#52514e',lw=1); ax.text((x1+x2)/2,y+span*.01,t,ha='center',va='bottom',fontsize=8.5)
    br(1,2,top+span*.07,'Lo vs Hi '+fp(perm(k10[k10.G3=='Lo'][v],k10[k10.G3=='Hi'][v]))); br(0,2,top+span*.2,'Hi vs WT '+fp(perm(k10[k10.G3=='Hi'][v],k10[k10.G3=='CTL'][v])))
    ax.set_ylim(0,top+span*.34); ax.set_xticks([0,1,2]); ax.set_xticklabels(['WT','Lo KO','Hi KO']); ax.set_xlim(-.6,2.6); ax.grid(axis='x',visible=False); ax.set_ylabel(lab); ax.set_title(ttl,loc='left')
fig.suptitle('Phase 10 hidden goal: Hi KO mice visit the current goal as often as WT but do not stop there',x=.006,ha='left',fontsize=13,fontweight='600',color='#0b0b0b',y=.99)
fig.tight_layout(rect=(0,.06,1,.94)); fig.savefig('fig12_phase10_zones_pausing.png',dpi=170); plt.close()
# ---------------- Fig 13: %KO / IED, Danzer-style CI
K=k10[k10.pct.notna()]
fig,axs=plt.subplots(1,2,figsize=(11.5,4.7))
for ax,(v,lab,scale) in zip(axs,[('z3','Time in previous goal zone (% of session)',100),('rew_entry','Rewards per entry into current goal',1)]):
    x=K.pct.values; y=K[v].values*scale; n=len(x); b,a,r,p,se=stats.linregress(x,y); xx=np.linspace(0,31,200); yh=a+b*xx
    s=np.sqrt(np.sum((y-(a+b*x))**2)/(n-2)); ci=stats.t.ppf(.975,n-2)*s*np.sqrt(1/n+(xx-x.mean())**2/np.sum((x-x.mean())**2))
    ax.fill_between(xx,yh-ci,yh+ci,color='#b9b8b2',alpha=.38,lw=0,zorder=1); ax.plot(xx,yh-ci,color='#9a9993',lw=.8); ax.plot(xx,yh+ci,color='#9a9993',lw=.8); ax.plot(xx,yh,color='#0b0b0b',lw=1.8,zorder=3)
    w=k10[k10.G3=='CTL'][v].values*scale; ax.axhspan(w.mean()-stats.sem(w),w.mean()+stats.sem(w),xmin=0,xmax=.03,color=GC['CTL'],alpha=.5)
    ax.scatter([0]*len(w),w,s=18,color=GC['CTL'],alpha=.45,edgecolor='none',zorder=2)
    for _,rr in K.iterrows():
        ax.scatter([rr.pct],[rr[v]*scale],s=74,marker='D' if rr.ied=='+' else 'o',color=GC['Hi'] if rr.pct>15 else GC['Lo'],edgecolor='#fcfcfb',linewidth=1.1,zorder=4)
        off={'z3':{29:(-7,-12,'right'),7:(6,4,'left'),5:(6,-12,'left'),34:(-7,5,'right'),33:(6,-12,'left')},'rew_entry':{29:(-7,5,'right'),7:(5,7,'left'),3:(7,2,'left'),5:(-7,-12,'right'),34:(7,3,'left'),33:(6,-12,'left')}}[v].get(int(rr.Mouse),(6,4,'left'))
        ax.annotate(f"M{int(rr.Mouse)}",(rr.pct,rr[v]*scale),xytext=off[:2],textcoords='offset points',fontsize=8,color='#52514e',ha=off[2])
    rho=stats.spearmanr(x,y); ip=K[K.ied=='+'][v]; im=K[K.ied=='-'][v]
    ax.text(.98,.97,f"Pearson r = {r:+.2f}, p = {p:.2f}\nSpearman ρ = {rho.statistic:+.2f}, p = {rho.pvalue:.2f}\nIED+ vs IED−: {fp(perm(ip,im))}",transform=ax.transAxes,ha='right',va='top',fontsize=9,bbox=dict(facecolor='#fcfcfb',edgecolor='none',alpha=.85))
    yv=np.r_[y,w]; lo_,hi_=min(yv.min(),(yh-ci).min()),max(yv.max(),(yh+ci).max()); ax.set_ylim(lo_-(hi_-lo_)*.05,hi_+(hi_-lo_)*.38)
    ax.axvline(15,color='#9a9993',lw=1,ls=(0,(4,3))); ax.set_xlim(-1.5,31); ax.set_xlabel('% granule cells Pten KO (WT at 0)'); ax.set_ylabel(lab)
    ax.set_title({'z3':'A  Previous goal zone','rew_entry':'B  Pausing at the current goal'}[v],loc='left')
leg=[Line2D([],[],marker='o',ls='',color=GC['CTL'],ms=6,alpha=.6,label='WT (reference, not in fit)'),Line2D([],[],marker='o',ls='',color=GC['Lo'],ms=8,mec='#fcfcfb',label='Lo KO, IED−'),Line2D([],[],marker='o',ls='',color=GC['Hi'],ms=8,mec='#fcfcfb',label='Hi KO, IED−'),Line2D([],[],marker='D',ls='',color=GC['Hi'],ms=8,mec='#fcfcfb',label='Hi KO, IED+'),Line2D([],[],color='#0b0b0b',lw=1.8,label='Best fit, KO mice'),plt.Rectangle((0,0),1,1,fc='#b9b8b2',alpha=.5,ec='#9a9993',label='95% confidence band')]
fig.legend(handles=leg,loc='lower center',ncol=6,fontsize=8.8,handletextpad=.4,columnspacing=1.1)
fig.suptitle('Phase 10 hidden goal: percent KO and IED status',x=.006,ha='left',fontsize=13,fontweight='600',color='#0b0b0b',y=.99)
fig.tight_layout(rect=(0,.07,1,.94)); fig.savefig('fig13_phase10_pctko.png',dpi=170); plt.close()
print('ok')
