"""Step 3. Example-mouse figures (report Figures 16-19), after the TargetTrajectories.m plots.

Figure 16 / 19: full path (grey), the 3 s approach before each rewarded entry (colour), reward locations (dots),
                hidden (exA) and visible (exE) sessions.
Figure 17:      dwell map (exB).   Figure 18: speed map (exC).

## DEVIATIONS FROM MATLAB
## 1. Layout: MATLAB makes one 2x3 figure per session (path, speed map, position map, approaches,
##    reward scatter, zone-time bars). Here each figure shows one panel type for 3 mice x 4 phases.
## 2. Arena normalisation (display only): each session is re-centred and scaled with arena_fit.fit_arena
##    so all arenas have the same size and centre. MATLAB plots raw coordinates on a fixed 0-260 axis.
## 3. Approach window: MATLAB plots X(tSck - tbefEnter : tSck - tbefSck) with tbefSck = ZoneLatSecs*SF
##    read from the header and tbefEnter = tbefSck + 3 s. Here the latency is fixed at 1.2 s, i.e. frames
##    reward - 4.2 s to reward - 1.2 s. (1.2 s is the latency in all probe sessions.)
## 4. Position (dwell) map: same 8-pixel (32 x 32) grid. MATLAB: hist3 counts x 0.033 s, jet colormap,
##    caxis [0 17], no smoothing. Here: frames / 30 s per bin, Gaussian smoothing (sigma = 1 bin), grey
##    colormap 0-4 s, and the wall zone (outer 35 px, MATLAB's annulus) is blanked so the open arena is visible.
## 5. Speed map: MATLAB re-computes speed on the binned coordinates (X/8, Y/8) with a new pixel size and
##    averages per bin, jet colormap, caxis [0 40]. Here speed is computed once at full resolution
##    (traj_lib.speed_matlab) and averaged per bin, smoothed (sigma = 1 bin), bins with < 0.25 s of
##    occupancy left blank, viridis colormap 0-30 cm/s.
## 6. Zone circles show the current goal (solid), previous goal (dashed) and trained goal (dotted) rather
##    than MATLAB's single target circle plus centre and annulus circles.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS
import pickle, numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from scipy.ndimage import gaussian_filter
plt.rcParams.update({'font.family':['Inter','Helvetica','Arial','DejaVu Sans'],'font.size':9.5,'figure.facecolor':'#fcfcfb','savefig.facecolor':'#fcfcfb','axes.facecolor':'#fcfcfb'})
T=pickle.load(open(os.path.join(WORK,'traj','traj_examples.pkl'),'rb'))
from arena_fit import fit_arena
RD=121.0  # display radius of the path boundary (the mouse's centre cannot reach the wall)
SHIFT={}
for key,o in T.items():
    cx,cy,Rf=fit_arena(o['X'],o['Y']); k=RD/Rf; ok=o['X']>0
    Xn=np.where(ok,(o['X']-cx)*k+127.5,0.); Yn=np.where(ok,(o['Y']-cy)*k+127.5,0.)
    o['raw']=(o['X'],o['Y']); o['X'],o['Y']=Xn,Yn; o['fit']=(cx,cy,Rf)
    o['zc_raw']=o['zc']; o['zc']={z:((x-cx)*k+127.5,(y-cy)*k+127.5) for z,(x,y) in o['zc'].items()}
    o['targ']=(None,None,o['targ'][2]*k)

MICE=[(22,'WT','M22 (WT)','#2a78d6'),(33,'Lo','M33 (Lo KO, 8.8%, IED−)','#008300'),(34,'Hi','M34 (Hi KO, 28.4%, IED+)','#e34948')]
NR=len(MICE)
INK='#0b0b0b'; MUT='#52514e'; R0=127.5
def arena(ax,o,ph,cond,fill=True):
    ax.add_patch(Circle((R0,R0),R0,fill=False,ec='#9a9993',lw=1))
    r=o['targ'][2]
    for z,(x,y) in o['zc'].items():
        cur=(z==ph-6); prev=(z==ph-7); trained=(z==1)
        ec=INK if cur else ('#52514e' if (prev or trained) else '#b8b7b0')
        ls='-' if cur else ((0,(3,2)) if prev else ((0,(1,1.5)) if trained else '-'))
        ax.add_patch(Circle((x,y),r,fill=False,ec=ec,lw=1.8 if cur else 1.1,ls=ls,zorder=6))
    ax.set_xlim(-4,259); ax.set_ylim(259,-4); ax.set_aspect('equal'); ax.axis('off')
def tpe(o): return np.isin(o['state'],[1,2,3]).sum()/30/max(o['n_ent'],1)
def stats_txt(o): return f"{o['n_rew']} rewards · {o['n_ent']} entries · {tpe(o):.2f} s/entry"

# ---------- Fig A: paths
def figA(cond,fn,title):
    fig=plt.figure(figsize=(10.4,9.0)); axs=np.empty((NR,4),object)
    L=.075; W=(1-2*L)/4; top=.915; rowh=(top-.07)/NR
    for i in range(NR):
        for j in range(4): axs[i,j]=fig.add_axes([L+j*W+.004,top-(i+1)*rowh+.035,W-.008,rowh-.04])
    for i,(m,g,lab,col) in enumerate(MICE):
        for j,ph in enumerate(range(7,11)):
            ax=axs[i,j]; o=T[(m,ph,cond)]
            X=np.where(o['X']==0,np.nan,o['X']); Y=np.where(o['Y']==0,np.nan,o['Y'])
            ax.plot(X,Y,color='#c9c8c2',lw=.35,zorder=1)
            for e in o['rew']:
                a=max(0,e-int(4.2*30)); b=e-int(1.2*30)
                if b>a: ax.plot(X[a:b+1],Y[a:b+1],color=col,lw=.9,alpha=.9,zorder=3)
            ax.scatter(X[o['rew']],Y[o['rew']],s=9,color=INK,zorder=7,lw=0)
            arena(ax,o,ph,cond)
            ax.text(127.5,268,stats_txt(o),ha='center',va='top',fontsize=8.3,color=MUT)
            if i==0: ax.set_title(f'Phase {ph}'+(' (trained)' if ph==7 else ''),fontsize=10.5,fontweight='600',color=INK)
        axs[i,0].text(-30,127.5,lab,rotation=90,va='center',ha='center',fontsize=10.5,fontweight='600',color=col)
    fig.suptitle(title,x=.5,ha='center',y=.975,fontsize=12.5,fontweight='600',color=INK)
    fig.text(.5,.012,'Grey: full 30-min path. Coloured: the 3 s of approach before each rewarded entry. Black dots: where each reward was triggered (1.2 s in the zone).\nCircles: solid black = current goal; dashed = previous goal; dotted = original trained goal (zone 1); light grey = zone not yet used.',fontsize=8.3,color=MUT,ha='center')
    fig.savefig(fn,dpi=170); plt.close()
figA('H',FIGS+'/exA_paths_hidden.png','Example mice, hidden goal: paths, approaches and reward locations')
figA('V',FIGS+'/exE_paths_visible.png','Example mice, visible goal (control): paths, approaches and reward locations')

# ---------- Fig B/C: dwell and speed maps (32x32 bins of 8 px, as in the MATLAB code)
def maps(o):
    X=o['X']; Y=o['Y']; ok=X>0
    xb=np.clip((X[ok]//8).astype(int),0,31); yb=np.clip((Y[ok]//8).astype(int),0,31)
    occ=np.zeros((32,32)); np.add.at(occ,(yb,xb),1/30)
    v=o['v'][ok]; sp=np.zeros((32,32)); n=np.zeros((32,32)); good=~np.isnan(v)
    np.add.at(sp,(yb[good],xb[good]),v[good]); np.add.at(n,(yb[good],xb[good]),1)
    ss=gaussian_filter(sp,1.0); nn=gaussian_filter(n,1.0)
    with np.errstate(invalid='ignore'): spm=ss/nn
    spm[gaussian_filter(occ,1.0)<0.25]=np.nan
    return occ,spm
def figMap(kind,fn,title,cmap,vmax,cblab):
    fig=plt.figure(figsize=(10.4,10.4)); axs=np.empty((NR,4),object)
    L=.075; W=(1-2*L)/4; top=.915; rowh=(top-.115)/NR
    for i in range(NR):
        for j in range(4): axs[i,j]=fig.add_axes([L+j*W+.004,top-(i+1)*rowh+.04,W-.008,rowh-.045])
    for i,(m,g,lab,col) in enumerate(MICE):
        for j,ph in enumerate(range(7,11)):
            ax=axs[i,j]; o=T[(m,ph,'H')]; occ,spm=maps(o)
            M=gaussian_filter(occ,1.0) if kind=='occ' else spm
            if kind=='occ':
                cc=(np.arange(32)+.5)*8; XX,YY=np.meshgrid(cc,cc); ring=np.hypot(XX-R0,YY-R0)>R0-35
                Xo,Yo=o['X'],o['Y']; ok=Xo>0; ann=(np.hypot(Xo[ok]-R0,Yo[ok]-R0)>R0-35).mean()
            M=np.ma.masked_invalid(M)
            cm=plt.get_cmap(cmap).copy(); cm.set_bad('#fcfcfb')
            im=ax.imshow(M,extent=(0,256,256,0),cmap=cm,vmin=0,vmax=vmax,interpolation='nearest')
            clip=Circle((R0,R0),R0,transform=ax.transData); im.set_clip_path(clip)
            if kind=='occ':
                from matplotlib.patches import Wedge
                ax.add_patch(Wedge((R0,R0),R0,0,360,width=35,facecolor='#efeee9',lw=0,zorder=4))
                ax.add_patch(Circle((R0,R0),R0-35,fill=False,ec='#9a9993',lw=.7,ls=(0,(2,2)),zorder=5))
            arena(ax,o,ph,'H')
            if kind=='occ':
                z=o['z']; ax.text(127.5,266,'zones 1–4: '+' · '.join(f"{'*' if k==ph-6 else ''}{z[k]*100:.1f}" for k in range(1,5))+f' %\nwall zone: {ann*100:.0f}% of session',ha='center',va='top',fontsize=8.1,color=MUT,linespacing=1.35)
            else:
                ax.text(127.5,268,f"mean {o['meanspeed']:.1f} cm/s · at goal entry {o['targspeed']:.1f} cm/s",ha='center',va='top',fontsize=8.2,color=MUT)
            if i==0: ax.set_title(f'Phase {ph}'+(' (trained)' if ph==7 else ''),fontsize=10.5,fontweight='600',color=INK)
        axs[i,0].text(-30,127.5,lab,rotation=90,va='center',ha='center',fontsize=10.5,fontweight='600',color=col)
    cax=fig.add_axes([.35,.108,.3,.008]); cb=fig.colorbar(im,cax=cax,orientation='horizontal',extend='max'); cb.set_label(cblab,color=MUT,fontsize=8.5); cb.outline.set_visible(False); cb.ax.tick_params(labelsize=8)
    fig.suptitle(title,x=.5,ha='center',y=.975,fontsize=12.5,fontweight='600',color=INK)
    note=('Seconds spent in each 8-pixel bin (≈2.4 cm), lightly smoothed. The wall zone (outer 35 pixels, the MATLAB annulus) is blanked so the\ncolour scale shows the open arena; its share of session time is given under each map. Zone times are % of session; * = current goal.' if kind=='occ'
          else 'Mean running speed in each 8-pixel bin (smoothed over neighbouring bins; rarely visited bins left blank). Speed is computed over 0.5 s windows, matching the MATLAB output to within 0.2 cm/s.')
    fig.text(.5,.006,note+'\nCircles as in the path figure: solid = current goal, dashed = previous goal, dotted = original trained goal.',fontsize=8.1,color=MUT,ha='center')
    fig.savefig(fn,dpi=170); plt.close()
figMap('occ',FIGS+'/exB_dwell_hidden.png','Example mice, hidden goal: where time is spent away from the wall','Greys',4,'seconds per bin')
figMap('spd',FIGS+'/exC_speed_hidden.png','Example mice, hidden goal: running speed across the arena','viridis',30,'cm/s')

