set -e
cd /c/Users/Z390/AppData/Local/Temp/claude/4f94f33fe0a28c30/7a6601ed-d746-46d4-b1b0-3073ab9de62e/scratchpad
export PYTHONIOENCODING=utf-8
for s in "deep_extract.py 7" "deep_extra_7.py" "deep_pca2_7.py" "deep_opt_7.py" "deep_opt2_7.py" "deep_ds3_7.py"; do
  echo "== $s $(date +%T)"; python $s > /dev/null 2>v7_err.log || { echo FAILED $s; tail -5 v7_err.log; exit 1; }
done
cd "/c/Users/Z390/Desktop/DS_PTEN_figures_2026-11-16/battery" && python build_dataset.py 7 | tail -2
echo "V7 DONE $(date +%T)"
