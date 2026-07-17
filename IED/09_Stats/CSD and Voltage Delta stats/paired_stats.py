#!/usr/bin/env python3
"""
paired_stats.py  --  minimal paired-sample statistics, Python standard library only.

Provides, for a list of paired differences d = CNO - Baseline:
  ttest_rel(d)        -> (t, df, p_two_sided)   paired t-test (t-distribution p via incomplete beta)
  wilcoxon(d)         -> (W, p_two_sided)        Wilcoxon signed-rank (EXACT for n<=18, else normal approx)
  cohen_dz(d)         -> dz                      standardized paired effect size mean(d)/sd(d)
  describe(x)         -> dict(n,mean,sd,sem,ci95_lo,ci95_hi)

No SciPy/NumPy required, so it runs under the cluster's base python3.
"""
import math, statistics as st
from itertools import product

# ---- incomplete beta (Numerical Recipes) for t-distribution p-values ----
def _betacf(a, b, x):
    MAXIT, EPS, FPMIN = 200, 3e-12, 1e-300
    qab, qap, qam = a+b, a+1.0, a-1.0
    c = 1.0
    d = 1.0 - qab*x/qap
    if abs(d) < FPMIN: d = FPMIN
    d = 1.0/d; h = d
    for m in range(1, MAXIT+1):
        m2 = 2*m
        aa = m*(b-m)*x/((qam+m2)*(a+m2))
        d = 1.0+aa*d;  d = FPMIN if abs(d)<FPMIN else d
        c = 1.0+aa/c;  c = FPMIN if abs(c)<FPMIN else c
        d = 1.0/d; h *= d*c
        aa = -(a+m)*(qab+m)*x/((a+m2)*(qap+m2))
        d = 1.0+aa*d;  d = FPMIN if abs(d)<FPMIN else d
        c = 1.0+aa/c;  c = FPMIN if abs(c)<FPMIN else c
        d = 1.0/d; de = d*c; h *= de
        if abs(de-1.0) < EPS: break
    return h

def _betai(a, b, x):
    if x <= 0.0: return 0.0
    if x >= 1.0: return 1.0
    lbeta = math.lgamma(a+b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbeta + a*math.log(x) + b*math.log(1.0-x))
    if x < (a+1.0)/(a+b+2.0):
        return bt*_betacf(a, b, x)/a
    return 1.0 - bt*_betacf(b, a, 1.0-x)/b

def t_p_two_sided(t, df):
    if df <= 0: return float('nan')
    if t == 0: return 1.0
    return _betai(df/2.0, 0.5, df/(df + t*t))

# ---- paired tests ----
def ttest_rel(d):
    d = [x for x in d if x is not None]
    n = len(d)
    if n < 2: return (float('nan'), n-1, float('nan'))
    m = st.mean(d); s = st.stdev(d)
    if s == 0: return (float('inf') if m != 0 else 0.0, n-1, 0.0 if m != 0 else 1.0)
    t = m/(s/math.sqrt(n))
    return (t, n-1, t_p_two_sided(t, n-1))

def _ranks_abs(d):
    vals = [abs(x) for x in d]
    order = sorted(range(len(d)), key=lambda k: vals[k])
    ranks = [0.0]*len(d); j = 0
    while j < len(d):
        k = j
        while k+1 < len(d) and vals[order[k+1]] == vals[order[j]]: k += 1
        avg = (j+1 + k+1)/2.0
        for t in range(j, k+1): ranks[order[t]] = avg
        j = k+1
    return ranks

def wilcoxon(d):
    d = [x for x in d if x is not None and x != 0]
    n = len(d)
    if n == 0: return (float('nan'), float('nan'))
    ranks = _ranks_abs(d)
    Wpos = sum(ranks[i] for i in range(n) if d[i] > 0)
    Wneg = sum(ranks[i] for i in range(n) if d[i] < 0)
    W = min(Wpos, Wneg); T = sum(ranks)
    if n <= 18:                                   # exact two-sided
        cnt = tot = 0
        for signs in product((0, 1), repeat=n):
            s = sum(ranks[i] for i in range(n) if signs[i]); tot += 1
            if min(s, T-s) <= W + 1e-9: cnt += 1
        return (W, min(1.0, cnt/tot))
    mu = T/2.0; var = sum(r*r for r in ranks)/4.0   # normal approx
    z = (W - mu)/math.sqrt(var) if var > 0 else 0.0
    return (W, 2.0*0.5*math.erfc(abs(z)/math.sqrt(2)))

def cohen_dz(d):
    d = [x for x in d if x is not None]
    if len(d) < 2: return float('nan')
    s = st.stdev(d)
    return st.mean(d)/s if s != 0 else float('inf')

def describe(x):
    x = [v for v in x if v is not None]
    n = len(x)
    if n == 0: return dict(n=0, mean=float('nan'), sd=float('nan'), sem=float('nan'),
                           ci95_lo=float('nan'), ci95_hi=float('nan'))
    m = st.mean(x); s = st.stdev(x) if n > 1 else 0.0; sem = s/math.sqrt(n) if n > 0 else 0.0
    # 95% CI via t critical (approx: use 1.96 for large n, else crude t table)
    tcrit = {1:12.71,2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306,9:2.262,10:2.228}.get(n-1, 1.96)
    return dict(n=n, mean=m, sd=s, sem=sem, ci95_lo=m-tcrit*sem, ci95_hi=m+tcrit*sem)
