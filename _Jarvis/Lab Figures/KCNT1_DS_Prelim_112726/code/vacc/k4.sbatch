#!/bin/bash
#SBATCH -p general
#SBATCH -t 04:00:00
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -o /gpfs2/scratch/sakhava1/kcnt1_prelim/logs/%x_%j.out
# K4 / K7 data steps, by part:  sbatch -J k4_band k4.sbatch band | -J k4_reads k4.sbatch reads | -J k4_menu k4.sbatch menu
set -e
W=/gpfs2/scratch/sakhava1/kcnt1_prelim
export JAPP=$W/app KBAT=$W/battery KSCR=$W/deep KROOM=dentate_spike_kcnt1 KV=1 Jarvis_MACHINE=home-14fe PYTHONIOENCODING=utf-8
PY="$W/k/py $W/k/krun.py"
say() { echo "== $* $(date +%T)"; }
case "$1" in
  band)
    # the Halo set read again from the raw recordings under seven filters (battery/extract), then the filter sets
    cd $W/battery/extract
    say "band_read"; $PY band_read.py
    say "band_build"; $PY band_build.py
    ;;
  reads)
    # Root Canal events (m0_data) and every Halo-workflow event of every mouse read at 2 kHz (m2_extract)
    cd $W/menus
    say "m0_data"; $PY m0_data.py
    say "m2_extract"; $PY m2_extract.py
    ;;
  menu)
    cd $W/menus
    say "m3_profiles"; $W/k/py m3_profiles.py
    say "m7_uprof"; $W/k/py m7_uprof.py
    say "tight_layers"; $W/k/py tight_layers.py
    say "j1 (old rule)"; $W/k/py j1_battery.py
    say "j1 (tight)"; JM_LAYERS=tight $W/k/py j1_battery.py
    say "j2 (old rule)"; $W/k/py j2_freq.py
    say "j2 (tight)"; JM_LAYERS=tight $W/k/py j2_freq.py
    ;;
esac
say "K4 $1 DONE"
