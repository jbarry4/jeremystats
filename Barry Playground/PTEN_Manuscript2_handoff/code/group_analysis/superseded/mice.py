"""SUPERSEDED / NOT USED IN THE REPORT. Lists mice in a .sav file.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys, pyreadstat, pandas as pd
pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
df,_=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else PROBE_SAV)); df=df[df.Group!='DKO']
t=df.groupby('MouseID').agg(Group=('Group','first'),Sub=('SubGroup',lambda s:'|'.join(sorted(set(s)))),HBH=('SubgroupHBH',lambda s:'|'.join(sorted(set(s)))),n=('Phase','size'),phases=('Phase',lambda s:sorted(set(s))),miss=('PGoalTime',lambda s:s.isna().sum()))
print(t.to_string()); print(df.isna().sum()); print(df.describe().T.round(3).to_string())
print(df[df.Group=='PTEN'].to_string())
