import pandas as pd
from pathlib import PurePosixPath

CSV = "C:/Users/info/Desktop/Barry/jeremystats/IED/batch_input.csv"  # change to your path if needed
ROOT = "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA"

df = pd.read_csv(CSV)

# auto-detect columns
def find_col(cands):
    cols = {c.lower(): c for c in df.columns}
    for cand in cands:
        for lc, orig in cols.items():
            if cand in lc:
                return orig
    raise RuntimeError(f"Missing column like: {cands}")

path_col = find_col(["path", "dir", "folder", "relative"])
flag_col = find_col(["eightbad", "eight_bad", "bad", "flag"])

def tf(x):
    s = str(x).strip().lower()
    return {"1":"true","0":"false","true":"true","false":"false","t":"true","f":"false","yes":"true","no":"false","y":"true","n":"false"}.get(s,"false")

paths, flags = [], []
for _, r in df.iterrows():
    rel = str(r[path_col]).strip()
    if not rel or rel.lower() in ("nan","none"):
        continue
    rel = rel.replace("\\","/").lstrip("/")          # force forward slashes
    full = str(PurePosixPath(ROOT) / rel)            # POSIX-safe join
    paths.append(full)
    flags.append(tf(r[flag_col]))

print("# 1) folders (order matters)")
print("dirs=(")
for p in paths:
    print(f'  "{p}"')
print(")")

print("\n# 2) eightBad flags aligned to the dirs above")
print("# make sure it matches the order of the section 1")
print("flags=(")
print(" ".join(flags))
print(")")
