"""Step 9. Reward per directed run across the hidden rotations (report Figure 24 and its table).

## NOT IN MATLAB: TargetTrajectories.m has no equivalent of this analysis; it was designed here.
Per mouse: linear slope (np.polyfit) of % directed runs rewarded across phases 7-10 (and 8-10); one-sample
t-test against zero within group; Mann-Whitney between groups. Per run: logistic GEE (statsmodels), outcome =
rewarded, predictors group x phase, exchangeable correlation within mouse. With 5-6 mice per KO group the
GEE's clustered standard errors are approximate.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu as mw, ttest_1samp
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':9,'figure.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb'})
INK='#0b0b0b'; MUT='#52514e'; GRID='#e4e3de'
COL={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948'}; LAB={'CTL':'WT','Lo':'Pten KO Lo','Hi':'Pten KO Hi'}
D=WORK+'/approach/'
M=pd.read_pickle(D+'arrival_mouse.pkl')
def style(ax):
    for s in ['top','right']: ax.spines[s].set_visible(False)
    for s in ['left','bottom']: ax.spines[s].set_color('#9a9993')
    ax.tick_params(colors=MUT,labelsize=7.8); ax.grid(axis='y',color=GRID,lw=0.6); ax.set_axisbelow(True)
fig=plt.figure(figsize=(6.6,3.0))
H=M[M.Cond=='H']
for j,g in enumerate(['CTL','Lo','Hi']):
    ax=fig.add_axes([0.095+j*0.195,0.2,0.165,0.62])
    x=H[H.G3==g].pivot(index='Mouse',columns='Phase',values='rwdir')
    for _,r in x.iterrows(): ax.plot(r.index,r.values,color=COL[g],alpha=0.3,lw=0.8)
    ax.plot(x.columns,x.mean(),color=COL[g],lw=2.4,marker='o',ms=4.5,mec='#fcfcfb')
    ax.set_ylim(0,85); ax.set_xticks([7,8,9,10]); ax.set_xlabel('Hidden phase',fontsize=8,color=MUT)
    ax.set_title(LAB[g],fontsize=9.2,color=COL[g],fontweight='semibold'); style(ax)
    if j==0: ax.set_ylabel('Directed runs that end\nin a reward (%)',fontsize=8,color=MUT)
    else: ax.set_yticklabels([])
ax=fig.add_axes([0.735,0.2,0.255,0.62])
rows=[]
for c,off,alpha in [('H',-0.17,1.0),('V',0.17,0.45)]:
    x=M[M.Cond==c]
    s=x.groupby(['G3','Mouse']).apply(lambda d: np.polyfit(d.Phase,d.rwdir,1)[0])
    for gi,g in enumerate(['CTL','Lo','Hi']):
        v=s.loc[g].values; xs=gi+off+np.random.default_rng(1).uniform(-0.06,0.06,len(v))
        ax.scatter(xs,v,s=13,color=COL[g],alpha=alpha*0.8,lw=0,marker='o' if c=='H' else 's')
        ax.plot([gi+off-0.1,gi+off+0.1],[v.mean()]*2,color=COL[g] if c=='H' else '#9a9993',lw=2.2)
ax.axhline(0,color='#9a9993',lw=0.8); ax.set_xticks([0,1,2]); ax.set_xticklabels(['WT','Lo','Hi'],fontsize=8.5)
ax.set_title('Slope across phases 7–10',fontsize=9.2,color=INK,fontweight='semibold')
ax.set_ylabel('Change per phase (% points)',fontsize=8,color=MUT); style(ax)
ax.text(0.98,0.02,'● hidden   ■ visible',transform=ax.transAxes,ha='right',va='bottom',fontsize=7.4,color=MUT)
fig.suptitle('Reward per directed run across the hidden probes',fontsize=11,y=0.985,color=INK,fontweight='semibold')
fig.text(0.5,0.015,'Thin lines: mice; thick lines: group means. Right: each mouse\'s linear slope (hidden: circles; visible: squares), bars = group means.',ha='center',fontsize=7.4,color=MUT)
fig.savefig(FIGS+'/ap5_slope.png',dpi=200); plt.close()

# ---------- per-mouse slope statistics
for c in ['H','V']:
    for phs in [[7,8,9,10],[8,9,10]]:
        x=M[(M.Cond==c)&M.Phase.isin(phs)]
        s=x.groupby(['G3','Mouse']).apply(lambda d: np.polyfit(d.Phase,d.rwdir,1)[0])
        cc,l,h=s.loc['CTL'],s.loc['Lo'],s.loc['Hi']
        print(c,phs,' '.join(f"{g} {v.mean():.2f}±{v.sem():.2f} (vs 0 p={ttest_1samp(v,0).pvalue:.4f}, {int((v<0).sum())}/{len(v)} falling)" for g,v in [('WT',cc),('Lo',l),('Hi',h)]),
              '| MW Hi-WT %.3f Lo-WT %.3f Lo-Hi %.3f'%(mw(h,cc).pvalue,mw(l,cc).pvalue,mw(l,h).pvalue))

# ---------- per-run logistic GEE, group x phase, clustered by mouse
import statsmodels.api as sm, statsmodels.formula.api as smf
p=pd.read_pickle(WORK+'/probe.pkl'); G=p.drop_duplicates('MouseID').set_index('MouseID').G3
Vv=pd.read_pickle(D+'visits.pkl'); Vv['G3']=Vv.Mouse.map(G)
Vv=Vv[Vv.G3.isin(['CTL','Lo','Hi'])&(Vv.role=='current')&(Vv.launch>=20)].copy(); Vv['y']=Vv.rewarded.astype(int)
for c in ['H','V']:
    for phs in [[7,8,9,10],[8,9,10]]:
        d=Vv[(Vv.Cond==c)&Vv.Phase.isin(phs)].copy(); d['Ph']=d.Phase-min(phs)
        for ref in ['CTL','Lo']:
            d['G']=pd.Categorical(d.G3,[ref]+[g for g in ['CTL','Lo','Hi'] if g!=ref])
            f=smf.gee('y ~ G*Ph',groups='Mouse',data=d,family=sm.families.Binomial(),cov_struct=sm.cov_struct.Exchangeable()).fit()
            print(c,phs,'reference',ref,{k:(round(float(np.exp(f.params[k])),2),round(float(f.pvalues[k]),4)) for k in f.params.index if 'Ph' in k})
