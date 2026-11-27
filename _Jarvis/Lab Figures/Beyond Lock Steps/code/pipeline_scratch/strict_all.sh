#!/bin/bash
# The Strict set end to end (2026-11-19): Extraction Room (room v10), battery, ML variant.
S=/c/Users/Z390/AppData/Local/Temp/claude/4f94f33fe0a28c30/7a6601ed-d746-46d4-b1b0-3073ab9de62e/scratchpad
B="/c/Users/Z390/Desktop/DS_PTEN_figures_2026-11-16/battery"
APP=/c/Users/Z390/Desktop/jeremystats/_Jarvis/app
export PYTHONIOENCODING=utf-8
say() { echo "== $* $(date +%T)"; }
step() { say "$1"; shift; "$@" > "$S/strict_last.log" 2>&1 || { echo "FAILED: $*"; tail -15 "$S/strict_last.log"; exit 1; }; tail -3 "$S/strict_last.log"; }
say "waiting for Jarvis"
until curl -s -o /dev/null -m 10 http://127.0.0.1:8733/api/rootcanal/pools; do sleep 20; done
sleep 60   # let start-up settle
cd $APP
step "X-ray read of the Strict folder" python $S/p4.py read "No P-spikes"
step "carry the calls and bands" python $S/p4.py copy "No P-spikes" --apply
step "extract (room v10)" python $S/p4.py extract "No P-spikes"
step "check the cards" python $S/p4.py check "No P-spikes"
cd $S
for s in "deep_extract.py 10" deep_extra_10.py deep_pca2_10.py deep_opt_10.py deep_opt2_10.py deep_ds3_10.py; do step "$s" python $s; done
cd "$B"
step "freeze the Strict set" python build_dataset.py 10
mv data/ds_v8.pkl data/ds_v8_derived_from_halo.pkl; mv data/ds_v10.pkl data/ds_v8.pkl
step "measures (Halo + Strict)" python measures.py
step "measures (before/after)" python around_measures.py
step "analyze" python analyze.py
step "analyze (before/after)" env BATTERY_OUT=results_around BATTERY_MERGED=merged_around python analyze.py
step "reports" python make_reports.py
step "leads" python make_leads.py leads.json leads_ds3.json leads_general.json
step "before/after leads" env BATTERY_MERGED=merged_around python make_leads.py leads_around.json
cd $APP
step "amber (Strict)" python -m backend.er2.amber "C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery" v8
V=$(ls "$LOCALAPPDATA/Jarvis/er2/amber" | sed -n 's/^v\([0-9]*\)$/\1/p' | sort -n | tail -1)
say "submitting the Strict ML run on amber v$V"
curl -s -m 300 -H "Content-Type: application/json" -d "{\"amber_version\": $V, \"where\": \"vacc\", \"n_shuffle\": 0, \"explain\": true, \"drop\": true, \"note\": \"Strict set (room v10), same as r005\"}" http://127.0.0.1:8733/api/er2/run | head -c 400; echo
say "STRICT DONE"
