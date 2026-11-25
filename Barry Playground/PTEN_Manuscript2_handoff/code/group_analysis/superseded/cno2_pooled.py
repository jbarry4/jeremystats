"""Figure 26: goal-zone time for all Pten KO mice pooled vs WT, baseline and after CNO; prints the pooled statistics with and without M5, and the pooled CSD statistics.

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
import statsmodels.formula.api as smf
warnings.filterwarnings('ignore')
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.6,'axes.axisbelow':True,'legend.frameon':False})
INK='#0b0b0b'; MUT='#52514e'; COL={'WT':'#2a78d6','Lo':'#008300','Hi':'#e34948','KO':'#7a4fa0'}
D=''
df=pd.read_pickle(D+'cno2.pkl'); d=df.dropna(subset=['goal_base','goal_cno']).copy()
d['K']=np.where(d.G=='WT','WT','KO')
W=d[d.K=='WT']; K=d[d.K=='KO']
def report(W,K,tag):
    out={}
    out['base']=(W.goal_base.mean(),K.goal_base.mean(),stats.mannwhitneyu(K.goal_base,W.goal_base).pvalue)
    out['cno']=(W.goal_cno.mean(),K.goal_cno.mean(),stats.mannwhitneyu(K.goal_cno,W.goal_cno).pvalue)
    out['chg']=(W.goal_d.mean(),K.goal_d.mean(),stats.mannwhitneyu(K.goal_d,W.goal_d).pvalue)
    out['pairedW']=stats.ttest_rel(W.goal_cno,W.goal_base).pvalue; out['pairedK']=stats.ttest_rel(K.goal_cno,K.goal_base).pvalue
    m=pd.concat([W,K])[['mouse','K','goal_base','goal_cno']].melt(id_vars=['mouse','K'],var_name='drug',value_name='y'); m['drug']=(m.drug=='goal_cno').astype(int)
    m['Kc']=pd.Categorical(m.K,['WT','KO']); f=smf.mixedlm('y ~ Kc*drug',m,groups=m.mouse).fit(); out['inter']=f.pvalues['Kc[T.KO]:drug']
    # gap to WT mean, per KO mouse
    gb=(K.goal_base-W.goal_base.mean()).abs().mean(); gc=(K.goal_cno-W.goal_cno.mean()).abs().mean()
    print(tag,{k:(tuple(round(float(x),4) for x in v) if isinstance(v,tuple) else round(float(v),4)) for k,v in out.items()},'nW',len(W),'nK',len(K),'KO up',int((K.goal_d>0).sum()),'WT down',int((W.goal_d<0).sum()))
    return out
o=report(W,K,'all'); report(W,K[K.mouse!=5],'no M5')
# figure
fig=plt.figure(figsize=(6.6,3.5))
ax=fig.add_axes([0.08,0.2,0.27,0.62])
for g,off in [('WT',-0.03),('KO',0.03)]:
    x=d[d.K==g]; m=[x.goal_base.mean(),x.goal_cno.mean()]; se=[x.goal_base.sem(),x.goal_cno.sem()]
    ax.errorbar(np.array([0,1])+off,m,yerr=se,color=COL['WT'] if g=='WT' else COL['KO'],marker='o',ms=5.5,lw=2,capsize=2.5,mec='#fcfcfb',label='WT (n=%d)'%len(x) if g=='WT' else 'All Pten KO (n=%d)'%len(x))
ax.set_xticks([0,1]); ax.set_xticklabels(['Baseline','After CNO'],fontsize=8.5); ax.set_xlim(-0.35,1.35); ax.set_ylim(1.4,3.6)
ax.set_ylabel('Time in goal (% of session), P8–9',fontsize=8); ax.legend(fontsize=7.4,loc='upper left')
ax.set_title('Group means ± SE',fontsize=9.5,color=INK,fontweight='semibold',loc='left',pad=16)
ax.text(0,1.015,f"group × CNO p = {o['inter']:.3f}",transform=ax.transAxes,fontsize=7.6,color=MUT,va='bottom')
ax=fig.add_axes([0.42,0.2,0.27,0.62])
for gi,g in enumerate(['WT','KO']):
    x=d[d.K==g]; xs=np.array([gi-0.18,gi+0.18])
    for _,rr in x.iterrows():
        c=COL['WT'] if g=='WT' else COL[rr.G]
        ax.plot(xs,[rr.goal_base,rr.goal_cno],color=c,alpha=0.55,lw=0.9,marker='D' if rr.ied else 'o',ms=3.2,mec='none')
ax.set_xticks([0,1]); ax.set_xticklabels(['WT','All Pten KO'],fontsize=8.5); ax.set_xlim(-0.5,1.5)
ax.set_title('Each mouse, baseline → CNO',fontsize=9.5,color=INK,fontweight='semibold',loc='left',pad=16)
ax.text(0,1.015,'Pten KO: green = Lo, red = Hi, diamond = IED',transform=ax.transAxes,fontsize=7.2,color=MUT,va='bottom')
ax=fig.add_axes([0.77,0.2,0.21,0.62])
for gi,g in enumerate(['WT','KO']):
    x=d[d.K==g]; xs=gi+np.random.default_rng(2).uniform(-0.12,0.12,len(x))
    for xi,(_,rr) in zip(xs,x.iterrows()):
        ax.scatter(xi,rr.goal_d,s=22,color=COL['WT'] if g=='WT' else COL[rr.G],marker='D' if rr.ied else 'o',edgecolor='#fcfcfb',lw=0.6,zorder=3)
    ax.plot([gi-0.25,gi+0.25],[x.goal_d.mean()]*2,color=INK,lw=2,zorder=4)
ax.axhline(0,color='#9a9993',lw=0.8); ax.set_xticks([0,1]); ax.set_xticklabels(['WT','All KO'],fontsize=8.5); ax.set_xlim(-0.6,1.6)
ax.set_ylabel('CNO − baseline (points)',fontsize=8)
ax.set_title('Change with CNO',fontsize=9.5,color=INK,fontweight='semibold',loc='left',pad=16)
ax.text(0,1.015,f"Mann-Whitney p = {o['chg'][2]:.3f}",transform=ax.transAxes,fontsize=7.6,color=MUT,va='bottom')
fig.suptitle('Goal-zone time after CNO: all Pten KO mice vs WT',x=.01,ha='left',fontsize=11.5,fontweight='semibold',color=INK,y=.985)
fig.text(0.5,0.02,'Hidden-goal sessions, phases 8 and 9 averaged. Bars in the right panel are group means.',ha='center',fontsize=7.4,color=MUT)
fig.savefig(D+'figC_goal_pooled.png',dpi=200); plt.close()
# also CSD pooled for completeness
c=df.dropna(subset=['csd_base','csd_cno']).copy(); c['K']=np.where(c.G=='WT','WT','KO')
report_c=lambda: None
m=c[['mouse','K','csd_base','csd_cno']].melt(id_vars=['mouse','K'],var_name='drug',value_name='y'); m['drug']=(m.drug=='csd_cno').astype(int); m['Kc']=pd.Categorical(m.K,['WT','KO'])
f=smf.mixedlm('y ~ Kc*drug',m,groups=m.mouse).fit()
Wc=c[c.K=='WT']; Kc=c[c.K=='KO']
print('CSD pooled: base WT %.4f KO %.4f p=%.4f | cno WT %.4f KO %.4f p=%.4f | chg p=%.4f | inter p=%.5f'%(Wc.csd_base.mean(),Kc.csd_base.mean(),stats.mannwhitneyu(Kc.csd_base,df[df.G=='WT'].csd_base.dropna()).pvalue,Wc.csd_cno.mean(),Kc.csd_cno.mean(),stats.mannwhitneyu(Kc.csd_cno,Wc.csd_cno).pvalue,stats.mannwhitneyu(Kc.csd_d,Wc.csd_d).pvalue,f.pvalues['Kc[T.KO]:drug']))
