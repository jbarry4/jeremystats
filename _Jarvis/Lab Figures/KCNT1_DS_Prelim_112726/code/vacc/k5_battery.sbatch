#!/bin/bash
#SBATCH -p general
#SBATCH -t 06:00:00
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -J k5_battery
#SBATCH -o /gpfs2/scratch/sakhava1/kcnt1_prelim/logs/%x_%j.out
# K4: the test battery on the KCNT1 sets, in run5.sh's order (filter sets are made by k4.sbatch band first):
# before / after reads, measures (Halo + Strict), measures under the filters, before / after measures, analyze x3.
set -e
W=/gpfs2/scratch/sakhava1/kcnt1_prelim
export JAPP=$W/app KBAT=$W/battery KSCR=$W/deep KROOM=dentate_spike_kcnt1 KV=1 Jarvis_MACHINE=home-14fe PYTHONIOENCODING=utf-8
PY="$W/k/py"
say() { echo "== $* $(date +%T)"; }
cd $W/battery/extract
say "around_read"; $PY $W/k/krun.py around_read.py
mkdir -p $W/battery/data/around
cp around/m*.npz $W/battery/data/around/ 2>/dev/null || true
rm -f $W/battery/data/around/*.part.npz
cd $W/battery
say "measures (Halo + Strict)"; $PY measures.py
say "measures (filters)"; BATTERY_SETS=b_ds,b_none,b_1_100,b_1_300,b_5_300,b_5_50,b_10_40 BATTERY_OUT=results_filters $PY measures.py waveform laminar structure
say "measures (before/after)"; $PY around_measures.py
say "analyze"; $PY analyze.py
say "analyze (filters)"; BATTERY_OUT=results_filters BATTERY_MERGED=merged_filters $PY analyze.py
say "analyze (before/after)"; BATTERY_OUT=results_around BATTERY_MERGED=merged_around $PY analyze.py
say "K5 DONE"
