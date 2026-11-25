"""SUPERSEDED / NOT USED IN THE REPORT. One-off edit that rewrote the Figure 1 block of figs.py (already applied).

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
p = os.path.dirname(os.path.abspath(__file__))+'/figs.py'
s = open(p).read()
a = s.index("# ---------- Fig 1")
b = s.index("# ---------- Fig 2")
new = r'''# ---------- Fig 1
fig,ax=plt.subplots(figsize=(6.6,4.4))
grp=[('CTL',cr[cr.g=='CTL'],COL['CTL'],'o'),('Lo',cr[cr.g=='Lo'],COL['Lo'],'^'),('Hi',cr[cr.g=='Hi'],COL['Hi'],'s'),('ALL',cr[cr.GRP=='PTEN'],'#6b6a65','D')]
for i,(g,d,c,mk) in enumerate(grp):
    d=d.sort_values('y'); xs=[]; seen={}
    for v in d.y:
        k=seen.get(v,0); seen[v]=k+1; xs.append(i+((k+1)//2)*0.07*(1 if k%2 else -1))
    ax.scatter(xs,d.y,s=46 if g!='ALL' else 38,color=c,marker=mk,edgecolor='#fcfcfb',linewidth=1,alpha=.95,zorder=3)
    m,se=d.y.mean(),d.y.sem(); ax.errorbar(i+0.42,m,yerr=se,fmt='_',color='#0b0b0b',ms=16,mew=2,capsize=4,elinewidth=1.4,zorder=4)
    ax.text(i+0.51,m+(0.9 if g=='CTL' else 0),f"{m:.1f} ± {se:.1f}",va='center',ha='left',fontsize=9.5,color='#0b0b0b')
wm=cr[cr.g=='CTL'].y.mean(); ax.axhline(wm,color='#9a9993',lw=1,ls=(0,(4,3)),zorder=1); ax.text(4.12,wm+.3,'WT mean',ha='right',va='bottom',fontsize=8.5,color='#52514e')
ax.axvline(2.86,color='#d9d8d2',lw=1,zorder=0)
ax.set_xticks(range(4)); ax.set_xticklabels(['WT\nn = 18','Pten KO Lo\nn = 5','Pten KO Hi\nn = 6','All Pten KO\nn = 13']); ax.set_xlim(-.5,4.15); ax.set_ylim(0,35)
ax.set_ylabel('Sessions to criterion'); ax.grid(axis='x',visible=False)
def br(x1,x2,y,t):
    ax.plot([x1,x1,x2,x2],[y-.5,y,y,y-.5],color='#52514e',lw=1); ax.text((x1+x2)/2,y+.2,t,ha='center',va='bottom',fontsize=8.5,color='#0b0b0b')
br(0,0.97,29.6,'p < 0.001'); br(1.03,2,29.6,'p = 0.08'); br(0,3,32.4,'p < 0.001')
ax.set_title('Sessions to criterion by KO level (mean ± SE; M6 excluded)',loc='left')
fig.tight_layout(); fig.savefig('figs/fig1_criterion.png',dpi=200); plt.close()
'''
open(p, 'w').write(s[:a] + new + s[b:])
r = open(WORK+'/report.md').read()
o = "*Figure 1. Each point is one mouse; bars are mean ± SE. The dashed line marks the WT mean.*"
assert o in r
n = '*Figure 1. Each point is one mouse; bars are mean ± SE. The dashed line marks the WT mean. "All Pten KO" pools the Lo and Hi mice with the two mice that have no histology.*'
open(WORK+'/report.md', 'w').write(r.replace(o, n))
print('patched')
