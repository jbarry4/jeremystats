#!/bin/bash
# Battery run 5 (2026-11-19): everything again on Extraction Room v9 (deduplicated Halo set).
S=/c/Users/Z390/AppData/Local/Temp/claude/4f94f33fe0a28c30/7a6601ed-d746-46d4-b1b0-3073ab9de62e/scratchpad
B="/c/Users/Z390/Desktop/DS_PTEN_figures_2026-11-16/battery"
export PYTHONIOENCODING=utf-8
say() { echo "== $* $(date +%T)"; }
alive() { ps -W 2>/dev/null | grep -i python | grep -q "$1"; }
step() { say "$1"; shift; "$@" > "$S/run5_last.log" 2>&1 || { echo "FAILED: $*"; tail -15 "$S/run5_last.log"; exit 1; }; tail -2 "$S/run5_last.log"; }

cd "$B"
step "leads" python make_leads.py leads.json leads_ds3.json leads_general.json
step "filter leads" env BATTERY_MERGED=merged_filters python make_leads.py leads_band.json
step "before/after leads" env BATTERY_MERGED=merged_around python make_leads.py leads_around.json
step "quality check pages" python qc_source/deep_qc11.py
say "RUN5 DONE"
