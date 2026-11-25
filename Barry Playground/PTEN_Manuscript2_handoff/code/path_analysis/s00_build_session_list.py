"""Step 0. List the 256 probe sessions (phases 7-10, visible and hidden) and find each raw .dat file.

Inputs : ZONE_SAV (AllProbes_ByGZLocation.sav), WORK/probe.pkl (from group_analysis/probe.py, gives the
         mice and their group labels), raw files under DATA_ROOT.
Outputs: WORK/approach/sessions.pkl and sessions.csv (Mouse, Group, Subgroup, Phase, Condition, File)
         WORK/approach/paths.json (File -> path relative to DATA_ROOT)

Not in the MATLAB code: MATLAB reads one session per row of PTEN_Feeder_GoalZones.xlsx with an explicit
file path. Here the file names come from the zone .sav file and are searched for under DATA_ROOT.

File matching rules (case-insensitive):
  <File>Track_Room.dat   (older cohort, e.g. M4s1Mar06p7_RoomTrack_Room.dat)
  <File>.dat             (newer cohort, e.g. m51s7p7u_101624.dat)
  Special case: m61s15p14c/u_033025 are saved as m61s15p14c/u_33025sc.dat.
If a session is found in more than one folder, the first match in PREFER order is used.
"""
import os, sys, json, collections
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, ZONE_SAV
import pandas as pd, pyreadstat

PREFER = ['PTEN Raw Data/Batch 1 Regular Raw', 'pten2024sa', 'AllPtenData']
SPECIAL = {'m61s15p14c_033025': 'm61s15p14c_33025sc.dat', 'm61s15p14u_033025': 'm61s15p14u_33025sc.dat'}

df, _ = pyreadstat.read_sav(ZONE_SAV)
probe = pd.read_pickle(os.path.join(WORK, 'probe.pkl'))           # DKO mice already removed there
df = df[df.Mouse.isin(probe.MouseID.unique())]
S = df.drop_duplicates(['Mouse', 'Phase', 'Condition'])[['Mouse', 'Group', 'Subgroup', 'Phase', 'Condition', 'File']]
S = S.sort_values(['Mouse', 'Phase', 'Condition']).reset_index(drop=True)

# index every .dat file under DATA_ROOT by lower-case name
idx = collections.defaultdict(list)
for root, _, files in os.walk(DATA_ROOT):
    for f in files:
        if f.lower().endswith('.dat'):
            idx[f.lower()].append(os.path.relpath(os.path.join(root, f), DATA_ROOT))

def rank(p):
    d = os.path.dirname(p)
    return PREFER.index(d) if d in PREFER else len(PREFER)

P = {}; missing = []
for f in S.File:
    cands = [f.lower() + 'track_room.dat', f.lower() + '.dat']
    if f in SPECIAL: cands.append(SPECIAL[f].lower())
    hits = [p for c in cands for p in idx.get(c, [])]
    if not hits: missing.append(f); continue
    hits.sort(key=rank); P[f] = hits[0]
    if len(set(hits)) > 1: print('note: more than one copy of', f, '->', hits, 'using', hits[0])

S.to_pickle(os.path.join(WORK, 'approach', 'sessions.pkl')); S.to_csv(os.path.join(WORK, 'approach', 'sessions.csv'), index=False)
json.dump(P, open(os.path.join(WORK, 'approach', 'paths.json'), 'w'), indent=1)
print(len(S), 'sessions;', len(P), 'files found;', len(missing), 'missing', missing[:10])
