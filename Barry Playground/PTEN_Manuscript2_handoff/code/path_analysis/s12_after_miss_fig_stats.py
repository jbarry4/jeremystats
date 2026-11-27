"""Step 12. Figure 25 and its table: returns within 3 s after a miss, and pauses within 2.5 zone radii of the
current goal vs the other zones (hidden phases 8-10 pooled per mouse); pauses per session and exit speed by phase.

## NOT IN MATLAB. Tests: paired t-test current vs other zones within group; Mann-Whitney between groups.
For the 5 s and 10 s windows reported as robustness checks, change the 3 in r3 = ret <= 3.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu as mw, ttest_rel
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':9,'figure.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb'})
INK='#0b0b0b'; MUT='#52514e'; GRID='#e4e3de'
COL={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948'}; LAB={'CTL':'WT','Lo':'Pten KO Lo','Hi':'Pten KO Hi'}
D=WORK+'/approach/'
p=pd.read_pickle(WORK+'/probe.pkl'); G=p.drop_duplicates('MouseID').set_index('MouseID').G3
E=pd.read_pickle(D+'exits.pkl'); E['G3']=E.Mouse.map(G); E=E[E.G3.isin(['CTL','Lo','Hi'])]; E['r3']=E.ret.notna()&(E.ret<=3)
Pz=pd.read_pickle(D+'pauses.pkl'); Pz['G3']=Pz.Mouse.map(G); Pz=Pz[Pz.G3.isin(['CTL','Lo','Hi'])]
for z in [1,2,3,4]: Pz[f'n{z}']=Pz[f'd{z}']<2.5
Pz['near_c']=[r[f"n{int(r.cur)}"] for _,r in Pz.iterrows()]
Pz['near_o']=[np.mean([r[f"n{z}"] for z in [1,2,3,4] if z!=r.cur]) for _,r in Pz.iterrows()]
def ret_tab(cond,phs):
    x=E[(E.Cond==cond)&E.Phase.isin(phs)]
    a=x[(x.role=='current')&~x.rewarded].groupby(['G3','Mouse']).r3.mean().rename('c').to_frame().join(x[x.role!='current'].groupby(['G3','Mouse']).r3.mean().rename('o'))
    return a.reset_index()
def pz_tab(cond,phs):
    x=Pz[(Pz.Cond==cond)&Pz.Phase.isin(phs)]
    return x.groupby(['G3','Mouse']).agg(c=('near_c','mean'),o=('near_o','mean')).reset_index()
def style(ax):
    for s in ['top','right']: ax.spines[s].set_visible(False)
    for s in ['left','bottom']: ax.spines[s].set_color('#9a9993')
    ax.tick_params(colors=MUT,labelsize=7.8); ax.grid(axis='y',color=GRID,lw=0.6); ax.set_axisbelow(True)
fig=plt.figure(figsize=(6.6,6.9))
rows=[]
for j,(tab,tt,yl) in enumerate([(ret_tab('H',[8,9,10]),'Back in the goal within 3 s\nafter a miss','% of exits'),(pz_tab('H',[8,9,10]),'Pauses near the goal','% of pauses')]):
    ax=fig.add_axes([0.09+j*0.5,0.55,0.39,0.3])
    for gi,g in enumerate(['CTL','Lo','Hi']):
        x=tab[tab.G3==g]; xs=np.array([gi-0.17,gi+0.17])
        for _,r in x.iterrows(): ax.plot(xs,[r.c*100,r.o*100],color=COL[g],alpha=0.3,lw=0.8)
        ax.plot(xs,[x.c.mean()*100,x.o.mean()*100],color=COL[g],lw=2.2)
        ax.scatter([xs[0]],[x.c.mean()*100],s=34,color=COL[g],zorder=5,edgecolor='#fcfcfb'); ax.scatter([xs[1]],[x.o.mean()*100],s=34,facecolor='#fcfcfb',edgecolor=COL[g],lw=1.6,zorder=5)
        pv=ttest_rel(x.c,x.o).pvalue; lab='***' if pv<.001 else '**' if pv<.01 else '*' if pv<.05 else 'ns'
        ax.text(gi,1.0,lab,transform=ax.get_xaxis_transform(),ha='center',va='bottom',fontsize=8.5,color=INK if lab!='ns' else MUT)
    ax.set_xticks([0,1,2]); ax.set_xticklabels(['WT','Lo','Hi'],fontsize=8.5); ax.set_xlim(-0.5,2.5)
    ax.set_title(tt,fontsize=9.2,color=INK,fontweight='semibold',pad=14); ax.set_ylabel(yl,fontsize=8,color=MUT); style(ax)
    ax.text(0.5,-0.13,'● current goal   ○ other zones (mean of each)',transform=ax.transAxes,ha='center',va='top',fontsize=7.2,color=MUT)
# by phase: pauses per session, exit speed
ps=Pz[Pz.Cond=='H'].groupby(['G3','Mouse','Phase']).size().rename('n').reset_index()
es=E[(E.Cond=='H')&(E.role=='current')].groupby(['G3','Mouse','Phase']).exit_spd.median().rename('n').reset_index()
for j,(tab,tt,yl) in enumerate([(ps,'Pauses per session','pauses away from the wall'),(es,'Speed leaving the goal','cm/s')]):
    ax=fig.add_axes([0.09+j*0.5,0.13,0.39,0.28])
    for g,off in [('CTL',-0.1),('Lo',0),('Hi',0.1)]:
        z=tab[tab.G3==g].groupby('Phase').n; ax.errorbar(z.mean().index+off,z.mean().values,yerr=z.sem().values,color=COL[g],marker='o',ms=3.8,lw=1.6,capsize=1.8,label=LAB[g])
    for ph in [7,8,9,10]:
        w=tab[tab.Phase==ph].set_index('G3').n; pp=(mw(w.loc['Hi'],w.loc['CTL']).pvalue, mw(w.loc['Lo'],w.loc['Hi']).pvalue, mw(w.loc['Lo'],w.loc['CTL']).pvalue)
        lab=('†' if pp[0]<.05 else '')+('‡' if pp[1]<.05 else '')+('§' if pp[2]<.05 else '')
        if lab: ax.text(ph,1.0,lab,transform=ax.get_xaxis_transform(),ha='center',va='bottom',fontsize=8.5,color=INK)
        rows.append((tt,ph,w.loc['CTL'].mean(),w.loc['Lo'].mean(),w.loc['Hi'].mean())+pp)
    ax.set_xticks([7,8,9,10]); ax.set_xlabel('Hidden phase',fontsize=8,color=MUT); ax.set_ylabel(yl,fontsize=8,color=MUT)
    ax.set_title(tt,fontsize=9.2,color=INK,fontweight='semibold',pad=12); style(ax)
    if j==0: ax.legend(frameon=False,fontsize=7.4,loc='lower left')
fig.suptitle('After a miss: coming back and pausing (hidden sessions)',fontsize=11.5,y=0.985,color=INK,fontweight='semibold')
fig.text(0.5,0.012,'Top: phases 8–10 combined; thin lines are mice; stars: paired t-test, current goal vs other zones.\nBottom: mean ± SE across mice; Mann-Whitney p < 0.05: † Hi vs WT, ‡ Hi vs Lo, § Lo vs WT.',ha='center',fontsize=7.2,color=MUT)
fig.savefig(FIGS+'/ap6_aftermiss.png',dpi=200); plt.close()
for r in rows: print(r[0].replace('\n',' '),r[1],' '.join(f'{v:.3f}' for v in r[2:]))
for cond in ['H','V']:
    for nm,f in [('ret',ret_tab),('pause',pz_tab)]:
        t=f(cond,[8,9,10]); t['d']=t.c-t.o; w=t.set_index('G3')
        print(cond,nm,{g:(round(w.loc[g].c.mean()*100,1),round(w.loc[g].o.mean()*100,1),round(ttest_rel(w.loc[g].c,w.loc[g].o).pvalue,4)) for g in ['CTL','Lo','Hi']},
              'cur: Hi-WT %.3f Lo-WT %.3f Lo-Hi %.3f'%(mw(w.loc['Hi'].c,w.loc['CTL'].c).pvalue,mw(w.loc['Lo'].c,w.loc['CTL'].c).pvalue,mw(w.loc['Lo'].c,w.loc['Hi'].c).pvalue),
              'diff: Hi-WT %.3f Lo-WT %.3f Lo-Hi %.3f'%(mw(w.loc['Hi'].d,w.loc['CTL'].d).pvalue,mw(w.loc['Lo'].d,w.loc['CTL'].d).pvalue,mw(w.loc['Lo'].d,w.loc['Hi'].d).pvalue))
