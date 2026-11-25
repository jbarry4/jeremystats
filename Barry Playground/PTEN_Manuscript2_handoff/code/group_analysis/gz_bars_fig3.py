"""Figures 12 and 13: time in each zone by phase and group. Usage: python gz_bars_fig3.py H fig_bars_hidden_mwu.png  (and V for visible).

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work/gz) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(os.path.join(WORK,'gz'))
import pandas as pd, numpy as np, sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':10.5,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','axes.titlesize':11.5,'axes.titleweight':'600','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.7,'axes.axisbelow':True,'legend.frameon':False})
GC={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948'}; GN={'CTL':'WT (n = 19)','Lo':'Pten KO Lo (n = 5)','Hi':'Pten KO Hi (n = 6)'}
OLD,NEW,ORIG='#9a9993','#d6d5cf','#5f5e5a'
B=pd.read_pickle('bars.pkl'); T=pd.read_pickle('mwu.pkl'); cond=sys.argv[1]; out=sys.argv[2]
def fp(p): return 'p < 0.001' if p<.001 else (f'p = {p:.3f}' if (p<.01 or .04<=p<.06) else f'p = {p:.2f}')
fig,axs=plt.subplots(3,1,figsize=(11.5,11.2),sharex=True,sharey=True)
w=0.19; xs={7:0,8:1.25,9:2.5,10:3.75}
ymax=(B[B.cond==cond][[f'm{z}' for z in range(1,5)]].values+B[B.cond==cond][[f'se{z}' for z in range(1,5)]].values).max()
for ax,g in zip(axs,['CTL','Lo','Hi']):
    for ph in [7,8,9,10]:
        r=B[(B.cond==cond)&(B.group==g)&(B.phase==ph)].iloc[0]; t=T[(T.cond==cond)&(T.group==g)&(T.phase==ph)].iloc[0]; cur=ph-6
        tops={}
        for z in range(1,5):
            x=xs[ph]+(z-2.5)*w; m=r[f'm{z}']; se=r[f'se{z}']; tops[z]=m+se
            if z==cur: col,ec,lw,hatch=GC[g],'#0b0b0b',1.3,None
            elif z==1: col,ec,lw,hatch=ORIG,'none',0,None
            else: col,ec,lw,hatch=(OLD if z<cur else NEW),'none',0,None
            ax.bar(x,m,width=w*0.92,color=col,edgecolor=ec,linewidth=lw,zorder=3)
            ax.errorbar(x,m,yerr=se,fmt='none',ecolor='#3d3d3a',elinewidth=1,capsize=2.5,zorder=4)
            if z==cur: ax.text(x,m+se+ymax*.02,'★',ha='center',va='bottom',fontsize=13,color='#0b0b0b',zorder=5)
            ax.text(x,-ymax*.035,str(z),ha='center',va='top',fontsize=8.5,color='#52514e')
        xc=xs[ph]+(cur-2.5)*w; x1=xs[ph]+(1-2.5)*w
        if ph>7:
            p=t.p_cur_vs_orig; y=max(tops[1],tops[cur])+ymax*.17
            ax.plot([x1,x1,xc,xc],[y-ymax*.025,y,y,y-ymax*.025],color='#3d3d3a',lw=1,zorder=5)
            ax.text((x1+xc)/2,y+ymax*.01,('goal > zone 1: ' if p<.05 else 'goal vs zone 1: ')+fp(p),ha='center',va='bottom',fontsize=8.6,color='#0b0b0b' if p<.05 else '#6b6a65',fontweight='600' if p<.05 else '400',zorder=5)
        if g!='CTL':
            p=t.mwu_cur_vsWT; ax.text(xs[ph],ymax*1.42,'goal time vs WT: '+fp(p),ha='center',va='top',fontsize=8.8,color='#0b0b0b' if p<.05 else '#6b6a65',fontweight='600' if p<.05 else '400')
    ax.set_title(GN[g],loc='left',color=GC[g]); ax.set_ylabel('Time in zone (% of session)'); ax.grid(axis='x',visible=False)
    ax.set_ylim(0,ymax*1.45); ax.tick_params(axis='x',length=0,pad=16)
axs[-1].set_xticks([xs[p] for p in [7,8,9,10]]); axs[-1].set_xticklabels(['Phase 7 (trained)\ngoal = zone 1','Phase 8\ngoal = zone 2','Phase 9\ngoal = zone 3','Phase 10\ngoal = zone 4'])
leg=[Patch(fc='#9a9993',ec='#0b0b0b',lw=1.3,label='★ Current goal (group colour)'),Patch(fc=ORIG,label='Zone 1, original trained goal'),Patch(fc=OLD,label='Other former goal'),Patch(fc=NEW,label='Not yet a goal')]
fig.legend(handles=leg,loc='lower center',ncol=4,fontsize=9.5)
fig.suptitle(f"Time at the current goal vs WT and vs the original zone, {'hidden' if cond=='H' else 'visible'} goal sessions (mean ± SE)",x=.008,ha='left',fontsize=13,fontweight='600',color='#0b0b0b',y=.995)
fig.text(.008,.035,'Brackets: current goal vs zone 1 within each group (paired t-test). Top line (KO rows): current-goal time vs WT (Mann-Whitney U test). Uncorrected.',fontsize=8.5,color='#52514e')
fig.tight_layout(rect=(0,.055,1,.97)); fig.savefig(out,dpi=165); print('ok')
