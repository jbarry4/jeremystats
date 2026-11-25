"""Paths used by every script in this package. Edit these if you move things.

DATA_ROOT  : the AllBehavior folder that holds the raw Bio-Signal Tracker .dat files
INPUTS     : put the SPSS / Excel inputs here (names below, without the upload prefixes)
WORK       : intermediate files (pickles, csv) are written here
FIGS       : figures are written here
"""
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = '/mnt/user-data/uploads/AllBehavior'
INPUTS = os.path.join(ROOT, 'inputs')
WORK = '/home/claude/work'
FIGS = '/home/claude/work/figs'

ZONE_SAV = os.path.join(INPUTS, 'AllProbes_ByGZLocation.sav')     # time in each of the 4 goal zones, per probe session
PROBE_SAV = os.path.join(INPUTS, 'AllProbeSessions.sav')           # PlaceAccuracy probe measures per session
CRIT_SAV = os.path.join(INPUTS, 'ROC_heterotopia_Fixed_hilo.sav')  # sessions to criterion
SESS2CRIT_SAV = os.path.join(INPUTS, 'PTEN_sess2crtit_hilo.sav')          # earlier criterion file (second upload, has PercentKO)
SESS2CRIT_SAV_FIRST = os.path.join(INPUTS, 'PTEN_sess2crtit_hilo_first.sav')  # first upload of that file (no PercentKO column)
CNO_XLSX = os.path.join(INPUTS, 'Data4Claude.xlsx')                # earlier theta CSD / CNO summary (superseded; still the source of % KO for most KO mice)
CSD_SAV = os.path.join(INPUTS, 'CSD_sansM2.sav')                   # channel-level theta CSD with layer labels, baseline and CNO (current)
CNO_BEHAV_SAV = os.path.join(INPUTS, 'AllProbeSessions_CNO.sav')   # probe sessions, baseline and after CNO, visible and hidden (current)
IED_DIR = os.path.join(INPUTS, 'ied')                                # IED analyses from the recording pipeline (grand averages, onsets, per-session counts, laminar stats)
EPHYS_EXCLUDE = [26]   # M26 (WT): problem after implantation surgery; excluded from CSD, kept in behaviour
M59_BASELINE = 'M59s4' # M59 has two baseline CSD sessions; s4 is used (as in Data4Claude)
PCT_EXTRA = {29: 22.00, 30: 5.97}   # % KO for M29, M30 (not in Data4Claude), from the project % KO list

for d in (WORK, FIGS, os.path.join(WORK, 'approach'), os.path.join(WORK, 'traj'), os.path.join(WORK, 'gz'), os.path.join(WORK, 'figs'), os.path.join(WORK, 'csd3')):
    os.makedirs(d, exist_ok=True)

# raw whole-cell recordings for the CNO patch figure (AxoGraph .axgd)
PATCH_RAW = os.environ.get('PATCH_RAW', os.path.join(os.path.dirname(DATA_ROOT), 'ClaudeOutput', 'raw recordings'))
