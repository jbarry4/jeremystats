cd /c/Users/Z390/Desktop/jeremystats/_Jarvis/app
S=/c/Users/Z390/AppData/Local/Temp/claude/4f94f33fe0a28c30/7a6601ed-d746-46d4-b1b0-3073ab9de62e/scratchpad
export PYTHONIOENCODING=utf-8
set -e
echo "== read $(date +%T)"; python $S/p4.py read "No P-spikes"
echo "== copy $(date +%T)"; python $S/p4.py copy "No P-spikes" --apply
echo "== extract $(date +%T)"; python $S/p4.py extract "No P-spikes"
echo "== check $(date +%T)"; python $S/p4.py check "No P-spikes" 2>/dev/null
echo "STRICT ER DONE $(date +%T)"
