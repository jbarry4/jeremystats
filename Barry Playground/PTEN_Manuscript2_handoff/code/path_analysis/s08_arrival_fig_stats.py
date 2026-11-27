"""Step 8. Arrival at the goal (report Figure 23 and its table).

## NOT IN MATLAB: TargetTrajectories.m has no equivalent of this analysis; it was designed here.
Per mouse x phase x condition, from s06 visits to the current zone: % of entries reached by a directed run
(launch >= 20 cm), median entry speed, median time in the goal per visit, % of directed runs rewarded.
Mann-Whitney (two-sided) for Hi vs WT, Hi vs Lo, Lo vs WT at each phase. Also prints the visible-session values
and the phase-10 share of directed runs that go to the current zone out of all four zones.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu as mw
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':9,'figure.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb'})
INK='#0b0b0b'; MUT='#52514e'; GRID='#e4e3de'
COL={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948'}; LAB={'CTL':'WT','Lo':'Pten KO Lo','Hi':'Pten KO Hi'}
D=WORK+'/approach/'
p=pd.read_pickle(WORK+'/probe.pkl'); G=p.drop_duplicates('MouseID').set_index('MouseID').G3
A=pd.read_pickle(D+'arrival.pkl'); A['G3']=A.Mouse.map(G)
V=pd.read_pickle(D+'visits.pkl'); V['G3']=V.Mouse.map(G); V=V[V.G3.isin(['CTL','Lo','Hi'])&(V.role=='current')]; V['dir']=V.launch>=20
def per(x):
    d=x[x.dir]
    return pd.Series(dict(fdir=x.dir.mean()*100,spd=x.ent_spd.median(),dwell=x.dwell.median(),rwdir=d.rewarded.mean()*100))
M=V.groupby(['G3','Mouse','Phase','Cond']).apply(per).reset_index(); M.to_pickle(D+'arrival_mouse.pkl')
def style(ax):
    for s in ['top','right']: ax.spines[s].set_visible(False)
    for s in ['left','bottom']: ax.spines[s].set_color('#9a9993')
    ax.tick_params(colors=MUT,labelsize=7.8); ax.grid(axis='y',color=GRID,lw=0.6); ax.set_axisbelow(True)
fig=plt.figure(figsize=(6.6,7.0))
t=np.arange(-90,91)/30
for j,(c,ph,tt) in enumerate([('H',7,'Hidden, phase 7 (trained location)'),('H',10,'Hidden, phase 10 (last rotation)'),('V',10,'Visible, phase 10')]):
    ax=fig.add_axes([0.075+j*0.315,0.6,0.27,0.29])
    ax.axvspan(0,1.2,color='#ecebe6',lw=0)
    for g in ['CTL','Lo','Hi']:
        x=A[(A.G3==g)&(A.Phase==ph)&(A.Cond==c)]; P=np.vstack(x.prof.values); m=np.nanmean(P,0); se=np.nanstd(P,0)/np.sqrt(len(P))
        ax.fill_between(t,m-se,m+se,color=COL[g],alpha=0.15,lw=0); ax.plot(t,m,color=COL[g],lw=1.8,label=LAB[g])
    ax.set_title(tt,fontsize=8.8,color=INK,fontweight='semibold'); ax.set_xlabel('Time from goal entry (s)',fontsize=8,color=MUT)
    ax.set_ylim(0,32); ax.set_xlim(-3,3); style(ax)
    # label the shaded band: it is the dwell the task requires before a reward is given
    ax.plot([0,0],[0,30],color='#9a9993',lw=0.8,ls=':',zorder=1)
    ax.annotate('',xy=(0,27.4),xytext=(1.2,27.4),
                arrowprops=dict(arrowstyle='<->',color=MUT,lw=0.7,shrinkA=0,shrinkB=0))
    ax.text(0.6,28.0,'1.2 s in the zone\nearns the reward',fontsize=6.6,color=MUT,ha='center',va='bottom',linespacing=0.95)
    ax.text(-0.12,1.0,'enters',fontsize=6.6,color=MUT,ha='right',va='bottom',rotation=90)
    if j==0: ax.set_ylabel('Speed (cm/s)',fontsize=8,color=MUT); ax.legend(frameon=False,fontsize=7.4,loc='upper left',bbox_to_anchor=(0,0.88))
    else: ax.set_yticklabels([])
MET=[('fdir','Entries reached by a\ndirected run (%)'),('spd','Speed on entry\n(cm/s)'),('dwell','Time in goal\nper visit (s)'),('rwdir','Directed runs that\nend in a reward (%)')]
rows=[]
for j,(v,tt) in enumerate(MET):
    ax=fig.add_axes([0.075+j*0.237,0.12,0.18,0.27])
    for g,off in [('CTL',-0.12),('Lo',0),('Hi',0.12)]:
        x=M[(M.G3==g)&(M.Cond=='H')].groupby('Phase')[v]; m=x.mean(); se=x.sem()
        ax.errorbar(m.index+off,m.values,yerr=se.values,color=COL[g],marker='o',ms=3.8,lw=1.6,capsize=1.8)
    top=ax.get_ylim()[1]
    for ph in [7,8,9,10]:
        z=M[(M.Cond=='H')&(M.Phase==ph)].set_index('G3')[v]
        ph_=dict(Phase=ph,metric=v,WT=z.loc['CTL'].mean(),Lo=z.loc['Lo'].mean(),Hi=z.loc['Hi'].mean(),
                 p_LoWT=mw(z.loc['Lo'],z.loc['CTL']).pvalue,p_HiWT=mw(z.loc['Hi'],z.loc['CTL']).pvalue,p_LoHi=mw(z.loc['Lo'],z.loc['Hi']).pvalue)
        rows.append(ph_)
        lab=('†' if ph_['p_HiWT']<0.05 else '')+('‡' if ph_['p_LoHi']<0.05 else '')+('§' if ph_['p_LoWT']<0.05 else '')
        if lab: ax.text(ph,1.0,lab,transform=ax.get_xaxis_transform(),ha='center',va='bottom',fontsize=8.5,color=INK)
    ax.set_xticks([7,8,9,10]); ax.set_xlabel('Hidden phase',fontsize=8,color=MUT)
    ax.set_title(tt,fontsize=8.2,color=INK,fontweight='semibold',pad=16); style(ax)
fig.suptitle('Arriving at the goal: speed, stopping and reward',fontsize=11.5,y=0.985,color=INK,fontweight='semibold')
fig.text(0.5,0.505,'Top: speed around EVERY entry into the current goal (directed runs and chance crossings alike), mean ± SE across mice.',ha='center',fontsize=7.6,color=MUT)
fig.text(0.5,0.008,'Bottom: hidden sessions, mean ± SE across mice. Directed run = the final run toward the goal began at least 20 cm away.\nMann-Whitney p < 0.05: † Hi vs WT, ‡ Hi vs Lo, § Lo vs WT.',ha='center',fontsize=7.4,color=MUT)
fig.savefig(FIGS+'/ap4_arrival.png',dpi=200); plt.close()
R=pd.DataFrame(rows); R.to_pickle(D+'arrival_stats.pkl'); print(R.round(3).to_string())
# visible too
for v,_ in MET:
    for ph in [7,8,9,10]:
        z=M[(M.Cond=='V')&(M.Phase==ph)].set_index('G3')[v]
        print('V',v,ph,round(z.loc['CTL'].mean(),2),round(z.loc['Lo'].mean(),2),round(z.loc['Hi'].mean(),2),
              round(mw(z.loc['Lo'],z.loc['CTL']).pvalue,3),round(mw(z.loc['Hi'],z.loc['CTL']).pvalue,3),round(mw(z.loc['Lo'],z.loc['Hi']).pvalue,3))

# ---------- phase 10 hidden: share of directed runs (launch >= 20 cm) that go to the current zone, out of all 4 zones
Vall=pd.read_pickle(D+'visits.pkl'); Vall['G3']=Vall.Mouse.map(G); Vall=Vall[Vall.G3.isin(['CTL','Lo','Hi'])]; Vall['dir']=Vall.launch>=20
x=Vall[(Vall.Cond=='H')&(Vall.Phase==10)]
a=x.groupby(['G3','Mouse','role']).dir.sum().unstack(fill_value=0); a['share_cur']=a.current/a.sum(axis=1)
a=a.reset_index().set_index('G3').share_cur
print('share of directed runs to current zone, hidden phase 10:',{g:round(a.loc[g].mean(),3) for g in ['CTL','Lo','Hi']},
      'Hi-WT p=%.3f Lo-WT p=%.3f Lo-Hi p=%.3f'%(mw(a.loc['Hi'],a.loc['CTL']).pvalue,mw(a.loc['Lo'],a.loc['CTL']).pvalue,mw(a.loc['Lo'],a.loc['Hi']).pvalue))
