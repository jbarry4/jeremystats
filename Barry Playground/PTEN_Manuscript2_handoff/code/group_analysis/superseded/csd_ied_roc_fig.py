"""Figure 27: theta CSD as a predictor of IEDs, baseline vs after CNO. Run after cno2.py.
WT counted as IED-negative. AUC CIs: bootstrap (5000); baseline vs CNO AUC: paired bootstrap on the 19 mice with both."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from config import *
os.makedirs(os.path.join(WORK,'csdroc'),exist_ok=True)
import numpy as np, pandas as pd, warnings, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy import stats
warnings.filterwarnings('ignore')
plt.rcParams.update({'font.family':'Inter','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.6,'axes.axisbelow':True,'legend.frameon':False})
INK='#0b0b0b'; MUT='#52514e'; COL={'WT':'#2a78d6','Lo':'#008300','Hi':'#e34948'}
d=pd.read_pickle(os.path.join(WORK,'cno2','cno2.pkl')); d=d.dropna(subset=['csd_base']).copy(); d['y']=d.ied.astype(int)
d['drop']=d.csd_base-d.csd_cno
K=lambda a,b:((a[:,None]>b[None,:])+0.5*(a[:,None]==b[None,:])).mean()
def auc(s,c): s=s.dropna(subset=[c]); return K(s[c].values[s.y==1],s[c].values[s.y==0])
def boot(s,c,n=5000):
    s=s.dropna(subset=[c]); P,N=s[c].values[s.y==1],s[c].values[s.y==0]; r=np.random.default_rng(0)
    return np.percentile([K(r.choice(P,len(P)),r.choice(N,len(N))) for _ in range(n)],[2.5,97.5])
def curve(s,c):
    s=s.dropna(subset=[c]); x,y=s[c].values,s.y.values; th=np.r_[np.inf,np.sort(np.unique(x))[::-1]]
    return np.array([(x[y==0]>=t).mean() for t in th]),np.array([(x[y==1]>=t).mean() for t in th])
both=d.dropna(subset=['csd_cno']); ko=d[d.G!='WT']; kob=both[both.G!='WT']
res={}
for lab,s in [('all',both),('ko',kob)]:
    for c in ['csd_base','csd_cno','drop']:
        res[(lab,c)]=(auc(s,c),*boot(s,c),stats.mannwhitneyu(s[c][s.y==1],s[c][s.y==0]).pvalue)
res[('all16','csd_base')]=(auc(d,'csd_base'),*boot(d,'csd_base'),stats.mannwhitneyu(d.csd_base[d.y==1],d.csd_base[d.y==0]).pvalue)
for k,v in res.items(): print(k,np.round(v,3))
# paired bootstrap of AUC(base)-AUC(cno), same mice
def pdiff(s):
    y=s.y.values;a=s.csd_base.values;b=s.csd_cno.values;P,N=np.where(y==1)[0],np.where(y==0)[0]
    f=lambda i:K(a[i][y[i]==1],a[i][y[i]==0])-K(b[i][y[i]==1],b[i][y[i]==0]); r=np.random.default_rng(1)
    bs=np.array([f(np.r_[r.choice(P,len(P)),r.choice(N,len(N))]) for _ in range(5000)])
    return f(np.arange(len(s))),*np.percentile(bs,[2.5,97.5]),min(1,2*min((bs<=0).mean(),(bs>=0).mean()))
pa,pk=pdiff(both),pdiff(kob); print('diff all',np.round(pa,3),'diff ko',np.round(pk,3))
print('LOO AUC diff (all):',{int(m):round(auc(both[both.mouse!=m],'csd_base')-auc(both[both.mouse!=m],'csd_cno'),3) for m in both.mouse})
# IED vs others, mean CSD
for c in ['csd_base','csd_cno']:
    g=both.groupby(np.where(both.y==1,'IED',np.where(both.G=='WT','WT','KO no IED')))[c].mean(); print(c,g.round(4).to_dict())
print('IED vs WT after CNO p=',stats.mannwhitneyu(both.csd_cno[both.y==1],both.csd_cno[both.G=='WT']).pvalue,
      'IED vs KO-noIED after CNO p=',stats.mannwhitneyu(both.csd_cno[both.y==1],both.csd_cno[(both.G!='WT')&(both.y==0)]).pvalue)
CUT=0.042
fig=plt.figure(figsize=(6.8,3.6))
# A ROC curves
ax=fig.add_axes([0.075,0.2,0.25,0.6])
ax.plot([0,1],[0,1],color='#c9c8c2',lw=0.8,ls=':')
for c,col,ls,lab in [('csd_base',INK,'-','Baseline'),('csd_cno','#8a8983','--','After CNO')]:
    fx,ty=curve(both,c); ax.step(fx,ty,where='post',color=col,lw=2,ls=ls,label=f'{lab}  AUC {res[("all",c)][0]:.2f}')
ax.set_xlim(-0.02,1.02); ax.set_ylim(-0.02,1.04); ax.set_aspect('equal')
ax.set_xlabel('False-positive rate',fontsize=8); ax.set_ylabel('True-positive rate (IED mice)',fontsize=8)
ax.legend(fontsize=7.2,loc='lower right',handlelength=1.6)
ax.set_title('A  ROC, all mice',fontsize=9.5,color=INK,fontweight='semibold',loc='left',pad=16)
ax.text(0,1.015,f'5 IED vs 14 others (8 WT, 6 KO)',transform=ax.transAxes,fontsize=7.2,color=MUT,va='bottom')
# B per mouse
ax=fig.add_axes([0.41,0.2,0.27,0.6])
cats=[('WT',both[both.G=='WT']),('KO, no IED',both[(both.G!='WT')&(both.y==0)]),('KO, IED',both[both.y==1])]
for gi,(lab,s) in enumerate(cats):
    xs=np.array([gi-0.17,gi+0.17])
    for _,r in s.iterrows():
        ax.plot(xs,[r.csd_base,r.csd_cno],color=COL[r.G],alpha=0.6,lw=0.9,marker='D' if r.ied else 'o',ms=3.4,mec='none')
    ax.plot(xs,[s.csd_base.mean(),s.csd_cno.mean()],color=INK,lw=2.2,zorder=5)
ax.axhline(CUT,color='#9a9993',lw=0.9,ls='--'); ax.text(-0.45,CUT+0.0008,'best baseline cutoff',fontsize=6.6,color=MUT,va='bottom',ha='left')
ax.set_xticks(range(3)); ax.set_xticklabels([c[0] for c in cats],fontsize=8); ax.set_xlim(-0.5,2.5)
ax.set_ylabel('Theta CSD, MML–GCL',fontsize=8)
ax.set_title('B  Each mouse, baseline → CNO',fontsize=9.5,color=INK,fontweight='semibold',loc='left',pad=16)
ax.text(0,1.015,'Green Lo, red Hi, diamond IED; black = mean',transform=ax.transAxes,fontsize=7.2,color=MUT,va='bottom')
# C AUC summary
ax=fig.add_axes([0.80,0.2,0.18,0.6])
items=[('csd_base','Baseline'),('csd_cno','After\nCNO'),('drop','CNO\ndrop')]
for i,(c,lab) in enumerate(items):
    for lab2,off,mk,fc in [('all',-0.12,'o',INK),('ko',0.12,'o','#fcfcfb')]:
        a,lo,hi,p=res[(lab2,c)]; ax.plot([i+off]*2,[lo,hi],color=INK,lw=1.1); ax.scatter(i+off,a,s=30,marker=mk,facecolor=fc,edgecolor=INK,lw=1.1,zorder=3)
ax.axhline(0.5,color='#9a9993',lw=0.8,ls=':'); ax.set_ylim(0,1.05); ax.set_xlim(-0.5,2.5)
ax.set_xticks(range(3)); ax.set_xticklabels([l for _,l in items],fontsize=7.6); ax.set_ylabel('AUC (95% CI)',fontsize=8)
ax.legend(handles=[Line2D([],[],marker='o',ls='',mfc=INK,mec=INK,label='All mice'),Line2D([],[],marker='o',ls='',mfc='#fcfcfb',mec=INK,label='KO only')],fontsize=7,loc='lower left',handletextpad=0.2)
ax.set_title('C  Prediction of IEDs',fontsize=9.5,color=INK,fontweight='semibold',loc='left',pad=16)
ax.text(0,1.015,f'Drop in AUC {pa[0]:.2f}, p = {pa[3]:.2f}',transform=ax.transAxes,fontsize=7.2,color=MUT,va='bottom')
fig.suptitle('Theta CSD predicts which mice have IEDs at baseline, less so after CNO',x=.01,ha='left',fontsize=11.5,fontweight='semibold',color=INK,y=.985)
fig.text(0.5,0.02,'Mice with CSD at baseline and after CNO (n = 19). WT counted as IED-negative. CIs: bootstrap; baseline − CNO: paired bootstrap.',ha='center',fontsize=7.2,color=MUT)
fig.savefig(os.path.join(FIGS,'figD_csd_ied_roc.png'),dpi=200); plt.close()
