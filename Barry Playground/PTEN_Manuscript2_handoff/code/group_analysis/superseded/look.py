"""SUPERSEDED / NOT USED IN THE REPORT. Prints a .sav file.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys, pyreadstat, pandas as pd
pd.set_option('display.width',250); pd.set_option('display.max_columns',60); pd.set_option('display.max_rows',500)
df,meta=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else PROBE_SAV))
print(df.shape); print(meta.column_names_to_labels); print(meta.variable_value_labels)
print(df.dtypes)
for c in df.columns:
    if df[c].nunique()<25: print(c, df[c].value_counts(dropna=False).to_dict())
print(df.head(40).to_string())
