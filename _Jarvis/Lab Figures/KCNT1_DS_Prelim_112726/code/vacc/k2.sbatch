#!/bin/bash
#SBATCH -p general
#SBATCH -t 03:00:00
#SBATCH -c 4
#SBATCH --mem=48G
#SBATCH -o /gpfs2/scratch/sakhava1/kcnt1_prelim/logs/%x_%j.out
# usage: sbatch -J xr_halo k2.sbatch <folder id> <app dir>
export JAPP="$2"
export Jarvis_MACHINE=home-14fe
cd /gpfs2/scratch/sakhava1/kcnt1_prelim/k
./py k2_xray_read.py "$1"
