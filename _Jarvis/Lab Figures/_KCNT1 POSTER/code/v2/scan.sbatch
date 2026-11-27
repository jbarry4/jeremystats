#!/bin/bash
#SBATCH --job-name=poster-kcnt1-scan
#SBATCH --partition=short
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1
#SBATCH --output=/gpfs2/scratch/sakhava1/_claude_poster_112526/scan_%j.out
module load miniforge/26.7.2-py3.14 >/dev/null 2>&1
cd /gpfs2/scratch/sakhava1/_claude_poster_112526
/users/s/a/sakhava1/jarvis/env/bin/python scan_lock.py
