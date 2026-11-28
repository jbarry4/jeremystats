#!/bin/bash
#SBATCH -p general
#SBATCH -t 04:00:00
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -J k3_freeze
#SBATCH -o /gpfs2/scratch/sakhava1/kcnt1_prelim/logs/%x_%j.out
# K3: freeze the KCNT1 room's two sets (room 953d3a5a81a7: v1 = Halo, v2 = Strict) the way PTEN's were frozen
# (PIPELINE_PTEN.md step 3), then the battery's data/ds_v6.pkl (Halo) and ds_v8.pkl (Strict) and meta.json.
set -e
W=/gpfs2/scratch/sakhava1/kcnt1_prelim
export JAPP=$W/app KBAT=$W/battery KSCR=$W/deep KROOM=dentate_spike_kcnt1 Jarvis_MACHINE=home-14fe PYTHONIOENCODING=utf-8
PY="$W/k/py $W/k/krun.py"
say() { echo "== $* $(date +%T)"; }
for V in 1 2; do
  export KV=$V
  cd $W/deep
  for s in deep_extract.py deep_extra.py deep_pca2.py deep_opt.py deep_opt2.py deep_ds3.py; do
    say "room v$V $s"
    if [ $s = deep_extract.py ]; then $PY $s $V; else $PY $s; fi
  done
  cd $W/battery
  say "build_dataset v$V"
  $W/k/py build_dataset.py $V
done
cd $W/battery/data
mv -f ds_v1.pkl ds_v6.pkl
mv -f ds_v2.pkl ds_v8.pkl
cd $W/battery
say "meta"
$W/k/py make_meta.py
say "K3 DONE"
