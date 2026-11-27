#!/bin/bash
# Battery run 5 (2026-11-19): everything again on Extraction Room v9 (deduplicated Halo set).
S=/c/Users/Z390/AppData/Local/Temp/claude/4f94f33fe0a28c30/7a6601ed-d746-46d4-b1b0-3073ab9de62e/scratchpad
B="/c/Users/Z390/Desktop/DS_PTEN_figures_2026-11-16/battery"
export PYTHONIOENCODING=utf-8
say() { echo "== $* $(date +%T)"; }
alive() { ps -W 2>/dev/null | grep -i python | grep -q "$1"; }
step() { say "$1"; shift; "$@" > "$S/run5_last.log" 2>&1 || { echo "FAILED: $*"; tail -15 "$S/run5_last.log"; exit 1; }; tail -2 "$S/run5_last.log"; }

say "waiting for the v9 freeze"
until grep -q "V9 DONE\|FAILED" "$S/run_v9.log"; do sleep 20; done
grep -q FAILED "$S/run_v9.log" && { cat "$S/run_v9.log"; exit 1; }
mv "$B/data/ds_v9.pkl" "$B/data/ds_v6.pkl"
for k in "" _full _pca2 _opt _opt2 _ds3; do cp "$S/deep${k}_v9.pkl" "$B/qc_source/deep${k}_v6.pkl"; done
cd "$B"
step "No P-spikes set from the Halo set" python derive_v8.py

say "waiting for the filter reads"
while [ "$(ls "$S/bandread9"/*.pkl 2>/dev/null | wc -l)" -lt 18 ]; do
  grep -l "Traceback" "$S"/band9_*.log >/dev/null 2>&1 && { echo "band read failed"; tail -20 "$S"/band9_*.log; exit 1; }
  sleep 30; done
cd /c/Users/Z390/Desktop/jeremystats/_Jarvis/app
step "filter sets" env BAND_OUT=bandread9 python "$S/band_build_9.py"

say "waiting for the before/after reads"
while [ "$(ls "$S/around9"/*.npz 2>/dev/null | grep -v part | wc -l)" -lt 16 ]; do
  grep -l "Traceback" "$S"/around9_*.log >/dev/null 2>&1 && { echo "around read failed"; tail -20 "$S"/around9_*.log; exit 1; }
  sleep 30; done
mkdir -p "$B/data/around"; cp "$S"/around9/m*.npz "$B/data/around/"; rm -f "$B"/data/around/*.part.npz

cd "$B"
step "measures (Halo + No P-spikes)" python measures.py
step "measures (filters)" env BATTERY_SETS=b_ds,b_none,b_1_100,b_1_300,b_5_300,b_5_50,b_10_40 BATTERY_OUT=results_filters python measures.py waveform laminar structure
step "measures (before/after)" python around_measures.py
step "analyze" python analyze.py
step "analyze (filters)" env BATTERY_OUT=results_filters BATTERY_MERGED=merged_filters python analyze.py
step "analyze (before/after)" env BATTERY_OUT=results_around BATTERY_MERGED=merged_around python analyze.py
step "reports" python make_reports.py
step "summary table" python make_table.py
step "supplement" python make_supplement.py
step "sanity check" python make_sanity.py
step "averaged" python make_averaged2.py
step "averaged, no cutoff" python make_averaged2.py nocut
step "leads" python make_leads.py leads.json leads_ds3.json leads_general.json
step "filter leads" env BATTERY_MERGED=merged_filters python make_leads.py leads_band.json
step "before/after leads" env BATTERY_MERGED=merged_around python make_leads.py leads_around.json
step "quality check pages" python qc_source/deep_qc11.py
say "RUN5 DONE"
