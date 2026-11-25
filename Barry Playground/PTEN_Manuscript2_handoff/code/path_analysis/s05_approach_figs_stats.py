"""Step 5. Figures 20-22 and the approach statistics.

## NOT IN MATLAB: TargetTrajectories.m has no equivalent of this analysis; it was designed here.
Figure 20 (ap1_paths): every wall-to-goal run for M22, M33, M34, each session rotated so the goal is at 12 o'clock;
           rewarded runs coloured, unrewarded grey. Columns: visible 7-10, hidden 7-10, hidden 10.
Figure 21 (ap2_metrics): visible vs hidden per mouse for launch distance, straightness, run duration, path per reward.
Figure 22 (ap3_launch_phase): launch distance by phase.
Per mouse: launch and run duration = medians over all entries of phases 7-10; straightness = mean over runs;
path per reward = median over the four sessions. Tests: paired t-test visible vs hidden within group;
Mann-Whitney (two-sided) KO group vs WT on hidden, visible and visible - hidden.
Prints the statistics tables used in the report. Writes WORK/approach/mouseF.pkl, statsF.pkl.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from scipy.stats import ttest_rel, mannwhitneyu
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':9.5,'figure.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb'})
INK='#0b0b0b'; MUT='#52514e'; GRID='#e4e3de'
COL={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948'}; LAB={'CTL':'WT','Lo':'Pten KO Lo','Hi':'Pten KO Hi'}
D=WORK+'/approach/'
segs=pd.read_pickle(D+'segs.pkl'); E=pd.read_pickle(D+'entF.pkl'); S=pd.read_pickle(D+'sesF.pkl')
p=pd.read_pickle(WORK+'/probe.pkl'); G=p.drop_duplicates('MouseID').set_index('MouseID').G3
for d in (E,S): d['G3']=d.Mouse.map(G)
CM=75/255
# ---------- Fig 21: approaches rotated so the goal is at 12 o'clock
MICE=[(22,'CTL','M22 (WT)'),(33,'Lo','M33 (Lo KO, IED−)'),(34,'Hi','M34 (Hi KO, IED+)')]
COLS=[('V',[7,8,9,10],'Visible, phases 7–10'),('H',[7,8,9,10],'Hidden, phases 7–10'),('H',[10],'Hidden, phase 10')]
fig=plt.figure(figsize=(6.6,7.7)); RD=121
for i,(m,g,lab) in enumerate(MICE):
    for j,(c,phs,ct) in enumerate(COLS):
        ax=fig.add_axes([0.05+j*0.318,0.655-i*0.297,0.29,0.255])
        ax.add_patch(Circle((0,0),RD+6,fill=False,ec='#9a9993',lw=0.9))
        n=0; nr=0; lines=[]
        for ph in phs:
            o=segs.get((m,ph,c))
            if o is None: continue
            k=RD/o['R']; gx,gy=(o['gx']-o['cx'])*k,(o['gy']-o['cy'])*k
            th=np.arctan2(gx,-gy); cs,sn=np.cos(th),np.sin(th)
            for xs,ys,rw in o['s']:
                x=(xs-o['cx'])*k; y=(ys-o['cy'])*k
                lines.append((x*cs+y*sn,-x*sn+y*cs,rw)); n+=1; nr+=rw
            gr=np.hypot(gx,gy); zr=o['gr']*k
        lw=0.55 if len(phs)>1 else 0.9
        for xr,yr,rw in lines:
            if not rw: ax.plot(xr,yr,color='#b9b8b2',lw=lw,alpha=0.35)
        for xr,yr,rw in lines:
            if rw: ax.plot(xr,yr,color=COL[g],lw=lw*1.3,alpha=0.55 if len(phs)>1 else 0.8)
        ax.add_patch(Circle((0,-gr),zr,fill=False,ec=INK,lw=1.4,zorder=6))
        ax.text(0,RD+16,f"{n} runs · {100*nr/max(n,1):.0f}% rewarded",ha='center',va='top',fontsize=7.6,color=MUT)
        ax.set_xlim(-RD-8,RD+8); ax.set_ylim(RD+28,-RD-8); ax.set_aspect('equal'); ax.axis('off')
        if i==0: ax.set_title(ct,fontsize=9.6,color=INK,pad=3,fontweight='semibold')
        if j==0: ax.text(-RD-14,0,lab,rotation=90,ha='right',va='center',fontsize=9,color=INK)
fig.suptitle('Runs from the wall to the goal',fontsize=12,y=0.985,color=INK,fontweight='semibold')
fig.text(0.5,0.008,'Coloured: runs that ended in a reward. Grey: runs that entered the goal without earning one.',ha='center',fontsize=8,color=MUT)
fig.savefig(FIGS+'/ap1_paths.png',dpi=200); plt.close()

# ---------- mouse-level table
W=E[E.from_wall]
a=E.groupby(['G3','Mouse','Cond']).launch.median().to_frame().join(
  W.groupby(['G3','Mouse','Cond']).agg(wall_st=('wall_straight','mean'),wall_dur=('wall_dur','median')))
b=S.groupby(['G3','Mouse','Cond']).path_per_rew.median()/100
M=a.join(b).reset_index(); M=M[M.G3.isin(['CTL','Lo','Hi'])]; M.to_pickle(D+'mouseF.pkl')
MET=[('launch','Launch distance (cm)','Distance from the goal where the final run toward it begins'),
     ('wall_st','Straightness, wall → goal','Straight-line distance ÷ path length'),
     ('wall_dur','Duration, wall → goal (s)','Median per mouse'),
     ('path_per_rew','Path per reward (m)','Distance run ÷ rewards earned')]
fig,axs=plt.subplots(2,2,figsize=(6.5,6.4)); axs=axs.ravel(); fig.subplots_adjust(left=0.1,right=0.98,top=0.855,bottom=0.12,wspace=0.32,hspace=0.55)
from matplotlib.ticker import NullFormatter, NullLocator
rows=[]
for ax,(v,t,sub) in zip(axs,MET):
    w=M.set_index(['G3','Mouse','Cond'])[v].unstack()
    for gi,g in enumerate(['CTL','Lo','Hi']):
        x=w.loc[g]; xs=np.array([gi*1.0-0.18,gi*1.0+0.18])
        for _,rr in x.iterrows(): ax.plot(xs,[rr.V,rr.H],color=COL[g],alpha=0.35,lw=0.8)
        ax.plot(xs,[x.V.mean(),x.H.mean()],color=COL[g],lw=2.2,marker='o',ms=5,mec='#fcfcfb',mew=1)
        pv=ttest_rel(x.V,x.H).pvalue
        rows.append(dict(metric=v,G=g,n=len(x),V=x.V.mean(),H=x.H.mean(),p_paired=pv,
            p_H=np.nan if g=='CTL' else mannwhitneyu(x.H,w.loc['CTL'].H).pvalue,
            p_V=np.nan if g=='CTL' else mannwhitneyu(x.V,w.loc['CTL'].V).pvalue,
            p_diff=np.nan if g=='CTL' else mannwhitneyu(x.V-x.H,w.loc['CTL'].V-w.loc['CTL'].H).pvalue))
        lab='***' if pv<.001 else '**' if pv<.01 else '*' if pv<.05 else 'ns'
        ax.text(gi,1.0,lab,transform=ax.get_xaxis_transform(),ha='center',va='bottom',fontsize=9,color=INK if lab!='ns' else MUT)
    lo,hi=np.nanmin(w.values),np.nanmax(w.values)
    if v=='path_per_rew':
        ax.set_yscale('log'); ax.yaxis.set_minor_locator(NullLocator()); ax.set_yticks([5,10,20,50]); ax.set_yticklabels(['5','10','20','50']); ax.set_ylim(4,hi*1.25)
    else: ax.set_ylim(lo-(hi-lo)*0.05,hi+(hi-lo)*0.1)
    ax.set_xticks([0,1,2]); ax.set_xticklabels(['WT','Lo','Hi'],fontsize=9); ax.set_xlim(-0.5,2.5)
    ax.set_title(t,fontsize=9.8,color=INK,pad=26,fontweight='semibold'); ax.text(0.5,1.115,sub.replace('\n',' '),transform=ax.transAxes,ha='center',va='bottom',fontsize=7.4,color=MUT)
    for s_ in ['top','right']: ax.spines[s_].set_visible(False)
    for s_ in ['left','bottom']: ax.spines[s_].set_color('#9a9993')
    ax.tick_params(colors=MUT,labelsize=8.2); ax.grid(axis='y',color=GRID,lw=0.6); ax.set_axisbelow(True)
fig.text(0.5,0.015,'Each pair of points: visible (left) and hidden (right) for one group; thin lines are mice, thick lines group means.\nStars: paired t-test, visible vs hidden, within the group (* p < 0.05, ** p < 0.01, *** p < 0.001).',ha='center',fontsize=7.6,color=MUT)
fig.suptitle('How the mice travel to the goal: visible vs hidden',fontsize=12,y=0.99,color=INK,fontweight='semibold')
fig.savefig(FIGS+'/ap2_metrics.png',dpi=200); plt.close()
R=pd.DataFrame(rows); R.to_pickle(D+'statsF.pkl'); print(R.round(4).to_string())

# ---------- Fig 23: launch distance by phase
a=E[E.G3.isin(['CTL','Lo','Hi'])].groupby(['G3','Mouse','Phase','Cond']).launch.median().reset_index()
fig,axs=plt.subplots(1,3,figsize=(6.5,2.8),sharey=True); fig.subplots_adjust(left=0.09,right=0.99,top=0.8,bottom=0.25,wspace=0.12)
ph_rows=[]
for ax,g in zip(axs,['CTL','Lo','Hi']):
    for c,ls,mk in [('V','-','o'),('H',(0,(3,2)),'s')]:
        z=a[(a.G3==g)&(a.Cond==c)].groupby('Phase').launch; m=z.mean(); se=z.sem()
        ax.errorbar(m.index,m.values,yerr=se.values,color=COL[g],ls=ls,marker=mk,ms=4.5,lw=1.8,capsize=2,mfc=COL[g] if c=='V' else '#fcfcfb',label='Visible' if c=='V' else 'Hidden')
    w=a[a.G3==g].pivot_table(index=['Mouse','Phase'],columns='Cond',values='launch').reset_index()
    for ph in [7,8,9,10]:
        q=w[w.Phase==ph].dropna(); pv=ttest_rel(q.V,q.H).pvalue
        ph_rows.append(dict(G=g,Phase=ph,n=len(q),V=q.V.mean(),H=q.H.mean(),p=pv))
        if pv<0.05: ax.text(ph,25.3,'*' if pv>=.01 else '**',ha='center',fontsize=10,color=INK)
    ax.set_title(LAB[g],fontsize=10,color=COL[g],fontweight='semibold'); ax.set_xticks([7,8,9,10]); ax.set_xlabel('Phase',fontsize=8.5,color=MUT)
    for s in ['top','right']: ax.spines[s].set_visible(False)
    for s in ['left','bottom']: ax.spines[s].set_color('#9a9993')
    ax.tick_params(colors=MUT,labelsize=8); ax.grid(axis='y',color=GRID,lw=0.6); ax.set_axisbelow(True); ax.set_ylim(10,27)
axs[0].set_ylabel('Launch distance (cm)',fontsize=8.5,color=MUT); axs[0].legend(frameon=False,fontsize=7.8,loc='lower right')
fig.suptitle('Launch distance by phase (mean ± SE across mice)',fontsize=11,y=0.98,color=INK,fontweight='semibold')
fig.text(0.5,0.02,'Stars: paired t-test, visible vs hidden at that phase (* p < 0.05, ** p < 0.01).',ha='center',fontsize=7.6,color=MUT)
fig.savefig(FIGS+'/ap3_launch_phase.png',dpi=200); plt.close()
print(pd.DataFrame(ph_rows).round(4).to_string())

# ---------- share of entries that begin with a run from the wall (table rows "Entries that start at the wall")
w=E.groupby(['G3','Mouse','Cond']).from_wall.mean().unstack()
for g in ['CTL','Lo','Hi']:
    x=w.loc[g]; line=f"{g}: V {x.V.mean()*100:.0f}% H {x.H.mean()*100:.0f}% paired p={ttest_rel(x.V,x.H).pvalue:.2f}"
    if g!='CTL': line+=' | MW vs WT: H %.2f V %.2f V-H %.2f'%(mannwhitneyu(x.H,w.loc['CTL'].H).pvalue,mannwhitneyu(x.V,w.loc['CTL'].V).pvalue,mannwhitneyu(x.V-x.H,w.loc['CTL'].V-w.loc['CTL'].H).pvalue)
    print(line)
