"""Figure 12: time in each of the four zones in hidden sessions, by phase and group; "ns" marks zones not significantly below the current goal (paired t-test). Usage: python gz_bars_fig.py H fig_bars_hidden.png

Group comparisons use two-sided Mann-Whitney U tests; within-group comparisons use paired t-tests.
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
from matplotlib.lines import Line2D
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':10.5,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#9a9993','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','axes.titlesize':11.5,'axes.titleweight':'600','figure.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.grid':True,'grid.color':'#e9e8e3','grid.linewidth':0.7,'axes.axisbelow':True,'legend.frameon':False})
GC={'CTL':'#2a78d6','Lo':'#008300','Hi':'#e34948'}; GN={'CTL':'WT (n = 19)','Lo':'Pten KO Lo (n = 5)','Hi':'Pten KO Hi (n = 6)'}
OLD,NEW='#9a9993','#d6d5cf'
B=pd.read_pickle('bars.pkl'); cond=sys.argv[1]; out=sys.argv[2]
fp=lambda p: 'p < 0.001' if p<.001 else (f'p = {p:.3f}' if (p<.01 or .04<=p<.06) else f'p = {p:.2f}')
fig,axs=plt.subplots(3,1,figsize=(11.5,11),sharex=True,sharey=True)
w=0.19; xs={7:0,8:1.25,9:2.5,10:3.75}
ymax=(B[B.cond==cond][[f'm{z}' for z in range(1,5)]].values+B[B.cond==cond][[f'se{z}' for z in range(1,5)]].values).max()
for ax,g in zip(axs,['CTL','Lo','Hi']):
    for ph in [7,8,9,10]:
        r=B[(B.cond==cond)&(B.group==g)&(B.phase==ph)].iloc[0]; cur=ph-6
        for z in range(1,5):
            x=xs[ph]+(z-2.5)*w; m=r[f'm{z}']; se=r[f'se{z}']
            col=GC[g] if z==cur else (OLD if z<cur else NEW)
            ax.bar(x,m,width=w*0.92,color=col,edgecolor='#0b0b0b' if z==cur else 'none',linewidth=1.3 if z==cur else 0,zorder=3)
            ax.errorbar(x,m,yerr=se,fmt='none',ecolor='#3d3d3a',elinewidth=1,capsize=2.5,zorder=4)
            if z==cur:
                ax.text(x,m+se+ymax*.025,'★',ha='center',va='bottom',fontsize=13,color='#0b0b0b',zorder=5)
                if g!='CTL' and r[f'p_vsWT_{z}']<.05: ax.text(x,m+se+ymax*.17,'vs WT\n'+fp(r[f'p_vsWT_{z}']),ha='center',va='bottom',fontsize=8.3,color='#0b0b0b',fontweight='600',zorder=5)
            else:
                p=r[f't_cur_vs_{z}']
                if p>=.05: ax.text(x,m+se+ymax*.02,'ns',ha='center',va='bottom',fontsize=8.5,color='#52514e',zorder=5)
            ax.text(x,-ymax*.035,str(z),ha='center',va='top',fontsize=8.5,color='#52514e')
        ax.text(xs[ph],ymax*1.36,f'zones differ: {fp(r.friedman)}',ha='center',va='top',fontsize=8.8,color='#0b0b0b' if r.friedman<.05 else '#6b6a65',fontweight='600' if r.friedman<.05 else '400')
    ax.set_title(GN[g],loc='left',color=GC[g]); ax.set_ylabel('Time in zone (% of session)'); ax.grid(axis='x',visible=False)
    ax.set_ylim(0,ymax*1.38); ax.tick_params(axis='x',length=0,pad=16)
axs[-1].set_xticks([xs[p] for p in [7,8,9,10]]); axs[-1].set_xticklabels(['Phase 7 (trained)\ngoal = zone 1','Phase 8\ngoal = zone 2','Phase 9\ngoal = zone 3','Phase 10\ngoal = zone 4'])
leg=[Patch(fc='#6b6a65',ec='#0b0b0b',lw=1.3,label='★ Current goal (group colour)'),Patch(fc=OLD,label='Former goal'),Patch(fc=NEW,label='Not yet a goal'),Line2D([],[],ls='',marker='$ns$',ms=14,color='#52514e',label='Not lower than the current goal (paired t, p ≥ 0.05)')]

fig.legend(handles=leg,loc='lower center',ncol=4,fontsize=9.5,bbox_to_anchor=(.5,.0))
fig.suptitle(f"Time in each of the four zones, {'hidden' if cond=='H' else 'visible'} goal sessions (mean ± SE)",x=.008,ha='left',fontsize=13,fontweight='600',color='#0b0b0b',y=.995)
fig.tight_layout(rect=(0,.045,1,.97)); fig.savefig(out,dpi=165); print('ok')
