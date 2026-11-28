#!/bin/bash
#SBATCH -p general
#SBATCH -t 02:00:00
#SBATCH -c 4
#SBATCH --mem=32G
#SBATCH -o /gpfs2/scratch/sakhava1/kcnt1_prelim/logs/%x_%j.out
# One recording's raw reads, so the six run side by side:
#   sbatch -J rd_m306 k4one.sbatch reads m306     (2 kHz reads of every Halo-workflow event; menus/reads)
#   sbatch -J bd_m306 k4one.sbatch band m306      (the Halo set under seven filters; battery/extract/bandread)
#   sbatch -J bd_build k4one.sbatch build         (the filter sets, once every band read is in)
set -e
W=/gpfs2/scratch/sakhava1/kcnt1_prelim
export JAPP=$W/app KBAT=$W/battery KSCR=$W/deep KROOM=dentate_spike_kcnt1 KV=1 Jarvis_MACHINE=home-14fe PYTHONIOENCODING=utf-8
PY="$W/k/py $W/k/krun.py"
case "$1" in
  reads) cd $W/menus && $PY m2_extract.py "$2" ;;
  band) cd $W/battery/extract && $PY band_read.py "$2" ;;
  build) cd $W/battery/extract && $PY band_build.py ;;
esac
echo "== $1 $2 DONE $(date +%T)"
