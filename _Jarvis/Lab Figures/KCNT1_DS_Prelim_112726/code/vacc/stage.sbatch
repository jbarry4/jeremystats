#!/bin/bash
#SBATCH -p general
#SBATCH -t 02:00:00
#SBATCH -c 6
#SBATCH --mem=8G
#SBATCH -J stage
#SBATCH -o /gpfs2/scratch/sakhava1/kcnt1_prelim/logs/%x_%j.out
# Copy (read only) the six recordings off /netfiles onto GPFS scratch: the X-ray reader seeks every channel per
# event, which over the NFS mount of netfiles read 115 GB for one 11 GB recording in an hour.
N=/netfiles/bigdata_jbarry/Jeremy3/KCNT1
R=/gpfs2/scratch/sakhava1/kcnt1_prelim/rec
mkdir -p $R
cp_one() {
  mkdir -p "$R/$1"
  t0=$(date +%s)
  rsync -a "$2/" "$R/$1/"
  echo "$1 $(du -sh "$R/$1" | cut -f1) in $(( $(date +%s) - t0 )) s"
}
cp_one sdcedca6715fb "$N/Summer'26/KCNT1_m1619/KCNT1_m1619_s01_081826/2026-08-18_13-11-23" &
cp_one s44851809ecd5 "$N/Spring'26/KCNT1_526/kcnt1_m526_s1_mar26/2026-03-26_14-35-57" &
cp_one se0c7b6ba6d5a "$N/Summer'26/KCNT1_m1609/KCNT1_m1609_s1_071526/2026-07-15_11-57-58" &
cp_one s6d234609d2c2 "$N/Summer'26/KCNT1_m0576/KCNT1m576_s1_72326/2026-07-23_13-05-13" &
cp_one s655a06b22296 "$N/Summer'26/KCNT1_m1603/KCNT1_m1603_s2_06-24-26/2026-06-24_14-38-31" &
cp_one s9619387fd35c "$N/Spring'26/KCNT1_hom306/KCNT1_hom306_s1_feb24/2026-02-24_17-46-28" &
wait
echo STAGED
