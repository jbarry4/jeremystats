"""ROC: can theta CSD predict which mice have IEDs? Baseline vs post-CNO (Figure 27 numbers).
Run after cno2.py. WT counted as IED-negative. Writes work/csdroc/csd_ied_roc.csv."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from config import *
os.makedirs(os.path.join(WORK,'csdroc'),exist_ok=True)
import sys, numpy as np, pandas as pd
from scipy import stats
f=sys.argv[1] if len(sys.argv)>1 else CNO_XLSX
d=pd.read_excel(f); d['mouse']=d['UVM #'].astype(str).str.replace('M','').astype(int)
d['ied']=(d.Group=='PTEN -IED').astype(int); d['pten']=d.Group.str.startswith('PTEN').astype(int)
d['pct']=d['JB % hits']
base=[c for c in d.columns if c.startswith('BaseTheta CSD')]; cno=[c for c in d.columns if c.startswith('CNOTheta CSD')]
K=lambda a,b:((a[:,None]>b[None,:])+0.5*(a[:,None]==b[None,:])).mean()
def roc(x,y):
    x=np.asarray(x,float); y=np.asarray(y,int); ok=~np.isnan(x); x,y=x[ok],y[ok]
    pos,neg=x[y==1],x[y==0]; auc=K(pos,neg)
    rng=np.random.default_rng(0); bs=[K(rng.choice(pos,len(pos)),rng.choice(neg,len(neg))) for _ in range(5000)]
    lo,hi=np.percentile(bs,[2.5,97.5]); p=stats.mannwhitneyu(pos,neg,alternative='two-sided').pvalue
    best=max(((( pos>=c).mean()+(neg<c).mean()-1,c,(pos>=c).mean(),(neg<c).mean()) for c in np.unique(x)),key=lambda t:t[0])
    return dict(npos=len(pos),nneg=len(neg),AUC=auc,lo=lo,hi=hi,p=p,cut=best[1],sens=best[2],spec=best[3])
def paired_diff(df,c1,c2,yc='ied'):
    s=df.dropna(subset=[c1,c2]); y=s[yc].values; a,b=s[c1].values,s[c2].values
    A=lambda i: K(a[i][y[i]==1],a[i][y[i]==0])-K(b[i][y[i]==1],b[i][y[i]==0])
    obs=A(np.arange(len(s))); rng=np.random.default_rng(1); P,N=np.where(y==1)[0],np.where(y==0)[0]
    bs=[A(np.r_[rng.choice(P,len(P)),rng.choice(N,len(N))]) for _ in range(5000)]
    lo,hi=np.percentile(bs,[2.5,97.5]); p=2*min(np.mean(np.array(bs)<=0),np.mean(np.array(bs)>=0))
    return len(s),obs,lo,hi,min(p,1)
rows=[]
for label,sub in [('All mice (WT = IED-)',d),('Pten KO only',d[d.pten==1])]:
    for c in base+cno:
        r=roc(sub[c],sub.ied); r.update(set=label,predictor=c); rows.append(r)
    r=roc(sub.pct,sub.ied) if label=='Pten KO only' else roc(sub.pct.where(sub[base[0]].notna()),sub.ied); r.update(set=label,predictor='% KO (CSD mice)'); rows.append(r)
    for b,c in zip(base,cno):
        sub=sub.assign(**{'chg':sub[c]-sub[b],'pchg':100*(sub[c]-sub[b])/sub[b]})
        for k in ['chg','pchg']:
            r=roc(sub[k],sub.ied); r.update(set=label,predictor=f'CNO change ({k})'); rows.append(r)
R=pd.DataFrame(rows)[['set','predictor','npos','nneg','AUC','lo','hi','p','cut','sens','spec']]
pd.set_option('display.width',200); print(R.round(3).to_string(index=False))
print('\nBaseline AUC - CNO AUC, same mice (paired bootstrap):')
for label,sub in [('All mice',d),('Pten KO only',d[d.pten==1])]:
    for b,c in zip(base,cno): print(label,b,'n=%d diff=%.3f CI[%.2f,%.2f] p=%.3f'%paired_diff(sub,b,c))
print('\nPer mouse:'); print(d[['Group','UVM #','pct']+base+cno].round(4).to_string(index=False))
R.to_csv(os.path.join(WORK,'csdroc','csd_ied_roc.csv'),index=False)
