"""Figures 1-6: sessions to criterion (1), % KO fit (2), visible and hidden probe bars (3, 4), % KO correlation heatmap (5), phase 10 vs % KO (6). Usage: python figs.py [ROC_heterotopia_Fixed_hilo.sav]

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys, numpy as np, pandas as pd, pyreadstat, warnings
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from scipy import stats
warnings.filterwarnings('ignore')
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','axes.titlesize':10.5,'axes.titleweight':'600','axes.titlecolor':'#0b0b0b','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.7,'axes.axisbelow':True,'legend.frameon':False})
COL={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948','UNK':'#8a8983'}; MK={'CTL':'o','Lo':'^','Hi':'s','UNK':'D'}; LAB={'CTL':'WT','Lo':'Pten KO Lo (<10%)','Hi':'Pten KO Hi (20–28%)','UNK':'Pten KO, no histology'}
pct={1:5.18,3:24.57,5:27.64,7:24.12,8:3.89,10:9.51,28:20.19,29:22.00,30:5.97,33:8.82,34:28.43}
het={8,10,27,29,30}; iedp={3,5,28,34}
cr,_=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else CRIT_SAV)); cr=cr.dropna(subset=['MouseID']); cr=cr[cr.MouseID!=6].rename(columns={'SesstoCriterion':'y'})
cr['g']=cr.GRP2HiLo.map({'CTL':'CTL','PTEN-Lo':'Lo','PTEN-Hi':'Hi','PTEN-?':'UNK'}); cr['pct']=cr.MouseID.map(pct)
rng=np.random.default_rng(3)
# ---------- Fig 1
fig,ax=plt.subplots(figsize=(7.0,4.4))
grp=[('CTL',cr[cr.g=='CTL']),('Lo',cr[cr.g=='Lo']),('Hi',cr[cr.g=='Hi']),('ALL',cr[cr.GRP=='PTEN'])]
for i,(g,d) in zip([0,1,2,3.45],grp):
    d=d.sort_values('y'); xs=[]; seen={}
    for v in d.y:
        k=seen.get(v,0); seen[v]=k+1; xs.append(i+((k+1)//2)*0.07*(1 if k%2 else -1))
    for x_,(_,rr) in zip(xs,d.iterrows()):   # colour = group; shape = IED status (diamond IED+, circle IED- or not recorded)
        ax.scatter(x_,rr.y,s=46 if g!='ALL' else 40,color=COL[rr.g],marker='D' if rr.MouseID in iedp else 'o',edgecolor='#fcfcfb',linewidth=1,alpha=.95,zorder=3)
    m,se=d.y.mean(),d.y.sem(); ax.errorbar(i+0.42,m,yerr=se,fmt='_',color='#0b0b0b',ms=16,mew=2,capsize=4,elinewidth=1.4,zorder=4)
    ax.text(i+0.51,m+(0.9 if g=='CTL' else 0),f"{m:.1f} ± {se:.1f}",va='center',ha='left',fontsize=9.5,color='#0b0b0b')
wm=cr[cr.g=='CTL'].y.mean(); ax.axhline(wm,color='#9a9993',lw=1,ls=(0,(4,3)),zorder=1); ax.text(4.57,wm+.3,'WT mean',ha='right',va='bottom',fontsize=8.5,color='#52514e')
ax.axvline(3.12,color='#d9d8d2',lw=1,zorder=0)
ax.set_xticks([0,1,2,3.45]); ax.set_xticklabels(['WT\nn = 18','Pten KO Lo\nn = 5','Pten KO Hi\nn = 6','All Pten KO\nn = 13']); ax.set_xlim(-.5,4.6); ax.set_ylim(0,37.5)
ax.set_ylabel('Sessions to criterion'); ax.grid(axis='x',visible=False)
def br(x1,x2,y,t):
    ax.plot([x1,x1,x2,x2],[y-.5,y,y,y-.5],color='#52514e',lw=1); ax.text((x1+x2)/2,y+.2,t,ha='center',va='bottom',fontsize=8.5,color='#0b0b0b')
_mwp=lambda a,b: stats.mannwhitneyu(cr[cr.g==a].y,cr[cr.g==b].y,alternative='two-sided').pvalue
_ft=lambda p: 'p < 0.001' if p<.001 else f'p = {p:.2f}'
br(0,0.97,29.6,_ft(_mwp('Lo','CTL'))); br(1.03,2,29.6,_ft(_mwp('Lo','Hi'))); br(0,2,32.2,_ft(_mwp('Hi','CTL')))
br(0,3.45,34.8,_ft(stats.mannwhitneyu(cr[cr.GRP=='PTEN'].y,cr[cr.g=='CTL'].y,alternative='two-sided').pvalue))
from matplotlib.lines import Line2D as _L
ax.legend(handles=[_L([],[],marker='o',ls='',color=COL[g],label={'CTL':'WT','Lo':'Pten KO Lo','Hi':'Pten KO Hi','UNK':'no histology'}[g]) for g in ['CTL','Lo','Hi','UNK']]+
          [_L([],[],marker='D',ls='',color='#9a9993',label='IED+ (diamond)')],loc='lower right',ncol=5,fontsize=8,handletextpad=.2,columnspacing=.9)
ax.set_title('Sessions to criterion by KO level (mean ± SE; M6 excluded)',loc='left')
fig.tight_layout(); fig.savefig('figs/fig1_criterion.png',dpi=200); plt.close()
# ---------- Fig 2
fig,ax=plt.subplots(figsize=(6.8,4.4))
c=cr[cr.g=='CTL']; ax.scatter(rng.uniform(-.9,.9,len(c)),c.y,s=40,color=COL['CTL'],marker='o',edgecolor='#fcfcfb',linewidth=1,label='WT (0%)',zorder=3)
for g in ['Lo','Hi']:
    d=cr[cr.g==g]; ax.scatter(d.pct,d.y,s=62,color=COL[g],marker='o',edgecolor='#fcfcfb',linewidth=1,label=LAB[g],zorder=3)
    e=d[d.MouseID.isin(iedp)]; ax.scatter(e.pct,e.y,s=62,color=COL[g],marker='D',edgecolor='#fcfcfb',linewidth=1,zorder=4)
k=cr[cr.pct.notna()]
for _,r in k.iterrows():
    tag=f"M{int(r.MouseID)}"+(' IED+' if r.MouseID in iedp else '')+(' het' if r.MouseID in het else '')
    off={8:(-8,6,'right'),1:(7,5,'left'),29:(7,-3,'left')}.get(int(r.MouseID),(7,4,'left'))
    ax.annotate(tag,(r.pct,r.y),xytext=off[:2],textcoords='offset points',fontsize=8,color='#52514e',ha=off[2])
dd=cr[cr.g.isin(['CTL','Lo','Hi'])].copy(); dd['p']=dd.pct.fillna(0); co=np.polyfit(dd.p,dd.y,2); xx=np.linspace(0,29,200)
ax.plot(xx,np.polyval(co,xx),color='#52514e',lw=1.5,ls=(0,(5,3)),zorder=2,label='Quadratic fit (WT at 0%)'); ax.scatter([],[],marker='D',color='#9a9993',label='IED+ (diamond)')
ax.axvspan(9.51,20.19,color='#f0efec',zorder=0); ax.text(14.85,1.2,'no mice\n9.5–20.2%',ha='center',va='bottom',fontsize=8.5,color='#52514e')
ax.set_xlabel('% granule cells Pten KO (cell layer)'); ax.set_ylabel('Sessions to criterion'); ax.set_xlim(-2,33); ax.set_ylim(0,31)
fig.legend(loc='lower center',ncol=3,fontsize=8.5,handletextpad=.4,columnspacing=1.2); ax.set_title('Sessions to criterion vs % KO (IED+ and heterotopia mice labelled)',loc='left')
fig.tight_layout(rect=(0,.11,1,1)); fig.savefig('figs/fig2_pctko.png',dpi=200); plt.close()
# ---------- Fig 3/4 probe panels
df=pd.read_pickle('probe.pkl'); df=df[df.G3!='UNK']; R=pd.read_pickle('phase_tab.pkl')
V=[('NumRewards','Rewards'),('PGoalTime','Proportion time in goal'),('ReRatio','Rewards per entrance'),('NumEntrances','Goal entrances'),('MeanSpeed','Mean speed (cm/s)'),('MeanTargSpeed','Mean target speed (cm/s)'),('PTimeCenter','Proportion time in center'),('PTimeAnnulus','Proportion time in annulus')]
for cond,name,fn in [('V','Visible goal','fig3_visible.png'),('H','Hidden goal','fig4_hidden.png')]:
    fig,axs=plt.subplots(2,4,figsize=(12.5,6.0)); 
    for ax,(v,lab) in zip(axs.ravel(),V):
        tops=[]
        for j,g in enumerate(['CTL','Lo','Hi']):
            d=df[(df.Condition==cond)&(df.G3==g)].groupby('Phase')[v].agg(['mean','sem']); x=np.array([7,8,9,10])+(j-1)*0.07
            ax.errorbar(x,d['mean'],yerr=d['sem'],color=COL[g],marker='o',ms=6.5,lw=2,elinewidth=1.2,capsize=2.5,mec='#fcfcfb',mew=.8,label=LAB[g] if g!='CTL' else 'WT (n = 19)',zorder=3)
            tops.append((d['mean']+d['sem']).values)
        tops=np.max(tops,axis=0); lo,hi=ax.get_ylim(); span=hi-lo; ax.set_ylim(lo,hi+span*.16)
        for i,ph in enumerate([7,8,9,10]):
            r=R[(R.cond==cond)&(R['var']==v)&(R.phase==ph)].iloc[0]; s=''
            if r.p_LoCTL<.05: s+='L'
            if r.p_HiCTL<.05: s+='H'
            if r.p_LoHi<.05: s+='×'
            if s: ax.text(ph,tops[i]+span*.04,s,ha='center',va='bottom',fontsize=9,color='#0b0b0b',fontweight='600')
        ax.axvspan(7.5,10.4,color='#f0efec',alpha=.6,zorder=0); ax.set_xlim(6.6,10.4)
        ax.set_xticks([7,8,9,10]); ax.set_xticklabels(['7\ntrained','8','9','10']); ax.set_title(lab,loc='left'); ax.grid(axis='x',visible=False)
    for ax in axs[1]: ax.set_xlabel('Probe phase (8–10 = novel locations)')
    h,l=axs[0,0].get_legend_handles_labels(); l=['WT (n = 19)','Pten KO Lo (n = 5)','Pten KO Hi (n = 6)']
    fig.legend(h,l,loc='upper right',ncol=3,fontsize=9.5,bbox_to_anchor=(.995,1.0))
    fig.suptitle(f'{name} probe sessions by phase (mean ± SE)',x=.008,ha='left',fontsize=12.5,fontweight='600',color='#0b0b0b',y=.995)
    fig.text(.008,.005,'Uncorrected p < 0.05 at that phase:  L = Lo vs WT,  H = Hi vs WT,  × = Lo vs Hi.  Shaded = novel goal locations.',fontsize=8.5,color='#52514e')
    fig.tight_layout(rect=(0,.03,1,.95)); fig.savefig('figs/'+fn,dpi=180); plt.close()
# ---------- Fig 5 heatmap
C=pd.read_pickle('corr.pkl'); C=C[C.phase!='chg']
cmap=LinearSegmentedColormap.from_list('d',['#256abf','#86b6ef','#f0efec','#ef9a99','#d03b3b'])
fig,axs=plt.subplots(1,2,figsize=(9.6,4.3),sharey=True)
for ax,(cond,name) in zip(axs,[('V','Visible goal'),('H','Hidden goal')]):
    M=np.array([[C[(C.cond==cond)&(C['var']==v)&(C.phase==ph)].rho.iloc[0] for ph in [7,8,9,10]] for v,_ in V]); Pm=np.array([[C[(C.cond==cond)&(C['var']==v)&(C.phase==ph)].p_rho.iloc[0] for ph in [7,8,9,10]] for v,_ in V])
    im=ax.imshow(M,cmap=cmap,vmin=-1,vmax=1,aspect='auto'); ax.grid(False)
    for i in range(8):
        for j in range(4):
            ax.text(j,i,f"{M[i,j]:+.2f}"+('*' if Pm[i,j]<.05 else ''),ha='center',va='center',fontsize=9,color='#0b0b0b',fontweight='700' if Pm[i,j]<.05 else '400')
    ax.set_xticks(range(4)); ax.set_xticklabels(['7\ntrained','8','9','10']); ax.set_yticks(range(8)); ax.set_yticklabels([l for _,l in V]); ax.set_title(name,loc='left'); ax.set_xlabel('Probe phase')
    ax.set_xticks(np.arange(-.5,4),minor=True); ax.set_yticks(np.arange(-.5,8),minor=True); ax.grid(which='minor',color='#fcfcfb',linewidth=2); ax.tick_params(which='minor',length=0); 
    for s in ax.spines.values(): s.set_visible(False)
cb=fig.colorbar(im,ax=axs,fraction=.025,pad=.02); cb.set_label('Spearman ρ with % KO'); cb.outline.set_visible(False)
fig.suptitle('Does % KO predict outcome at each phase?  (11 Pten KO mice; * uncorrected p < 0.05)',x=.008,ha='left',fontsize=11.5,fontweight='600',y=.99)
fig.savefig('figs/fig5_heatmap.png',dpi=190,bbox_inches='tight'); plt.close()
# ---------- Fig 6 phase 10 hidden scatters
fig,axs=plt.subplots(1,3,figsize=(11,3.7)); k=df[(df.Condition=='H')&(df.Phase==10)]
for ax,(v,lab) in zip(axs,[('MeanTargSpeed','Mean target speed (cm/s)'),('ReRatio','Rewards per entrance'),('NumRewards','Rewards')]):
    c=k[k.G3=='CTL'][v]; ax.axhspan(c.mean()-c.sem(),c.mean()+c.sem(),color='#cde2fb',zorder=0); ax.axhline(c.mean(),color=COL['CTL'],lw=1.5,zorder=1)
    for g in ['Lo','Hi']:
        d=k[k.G3==g]; i_=d.IED=='+'
        ax.scatter(d.pct[~i_],d[v][~i_],s=58,color=COL[g],marker='o',edgecolor='#fcfcfb',linewidth=1,zorder=3,label=LAB[g])
        ax.scatter(d.pct[i_],d[v][i_],s=58,color=COL[g],marker='D',edgecolor='#fcfcfb',linewidth=1,zorder=3)
    d=k[k.pct.notna()]; s=stats.spearmanr(d.pct,d[v]); co=np.polyfit(d.pct,d[v],1); xx=np.array([3,29]); ax.plot(xx,np.polyval(co,xx),color='#52514e',lw=1.3,ls=(0,(5,3)),zorder=2)
    ax.set_title(f"{lab}\nρ = {s.statistic:+.2f}, p = {s.pvalue:.3f}",loc='left'); ax.set_xlabel('% granule cells Pten KO'); ax.set_xlim(0,31)
    lo,hi=ax.get_ylim(); ax.text(30.6,c.mean()+(hi-lo)*.02,'WT mean ± SE',ha='right',va='bottom',fontsize=8,color='#256abf')
axs[0].scatter([],[],marker='D',color='#9a9993',label='IED+ (diamond)'); axs[0].legend(fontsize=8.5,loc='upper left')
fig.suptitle('Last hidden probe (phase 10, third novel location): outcome vs % KO',x=.008,ha='left',fontsize=11.5,fontweight='600',y=1.0)
fig.tight_layout(rect=(0,0,1,.96)); fig.savefig('figs/fig6_phase10.png',dpi=190); plt.close()
print('ok')
