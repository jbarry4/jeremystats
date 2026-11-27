import json, os, shutil, re
S = os.path.dirname(os.path.abspath(__file__))
LF = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures"
OLD = os.path.join(LF, "DS_PTEN_112026")
NEW = os.path.join(LF, "DS_PTEN_112326")
RUNS = r"C:\Users\Z390\AppData\Local\Jarvis\er2\runs"

if not os.path.exists(NEW):
    shutil.copytree(OLD, NEW)

# ML leaderboards and a plain summary
ml = os.path.join(NEW, "ml_runs")
os.makedirs(ml, exist_ok=True)
NAMES = {
    "r006": "Halo, all events (16 mice)", "r007": "Strict, all events",
    "r008": "Halo, DS1 vs DS2", "r009": "Halo, DS1 minus DS2 per mouse",
    "r010": "Halo, one DS type at a time", "r011": "Halo, random twins (same event count, random events)",
    "r012": "Strict, DS1 vs DS2", "r013": "Strict, DS1 minus DS2 per mouse",
    "r014": "Strict, one DS type at a time", "r015": "Strict, random twins",
    "r016": "Halo, all events with the raw event", "r017": "Strict, all events with the raw event",
}
lines = ["Machine-learning runs (Extraction Room 2.0), 2026-11-23", "",
         "Every score is on mice the model never saw. Bar: AUC 0.80 (rho 0.70 for knockout %).",
         "DS1 vs DS2 score = mean AUC within each held-out mouse.", ""]
for rid, nm in NAMES.items():
    p = os.path.join(RUNS, rid, "leaderboard.json")
    if not os.path.exists(p):
        continue
    shutil.copy(p, os.path.join(ml, "%s_leaderboard.json" % rid))
    L = json.load(open(p))
    lines.append("== %s  %s" % (rid, nm))
    by = {}
    for x in L["rows"]:
        v = x["view"]
        key = x["target"] + ("  [" + v.split("@")[1] + "]" if "@" in v else "")
        by.setdefault(key, []).append(x)
    for k in sorted(by):
        xs = sorted(by[k], key=lambda x: -(x["main"] or -9))
        b = xs[0]
        lines.append("   %-34s at bar %3d/%-3d best %.2f (%s / %s; top input %s)" % (
            k, sum(bool(x["passes"]) for x in xs), len(xs), b["main"] or 0, b["view"], b["model"], b["top_feature"]))
    lines.append("")
open(os.path.join(ml, "ML_summary.txt"), "w", encoding="utf-8").write("\n".join(lines))

# deck as one standalone HTML file
D = os.path.join(S, "deck", "project")
deck = json.load(open(os.path.join(D, "deck.json"), encoding="utf-8"))
css = open(os.path.join(D, "deck.css"), encoding="utf-8").read()
secs = []
for sid in deck["order"]:
    h = open(os.path.join(D, "slides", sid + ".html"), encoding="utf-8").read()
    h = re.sub(r"<aside>(.*?)</aside>", r'<div class="notes">Notes: \1</div>', h, flags=re.S)
    secs.append(h)
html = """<!doctype html><html><head><meta charset="utf-8"><title>Dentate spikes: what we found</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400..700&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>%s
html,body{margin:0;background:#2a2f3a;}
section{width:1920px;height:1080px;box-sizing:border-box;position:relative;margin:40px auto;overflow:hidden;}
.notes{position:absolute;left:0;right:0;bottom:0;font-size:20px;padding:8px 128px;color:#555;background:rgba(255,255,255,.6);display:none;}
body.shownotes .notes{display:block;}
</style></head><body ondblclick="document.body.classList.toggle('shownotes')">
%s
</body></html>""" % (css, "\n".join(secs))
open(os.path.join(NEW, "Dentate_spikes_what_we_found.html"), "w", encoding="utf-8").write(html)

# README
rd = os.path.join(NEW, "README.txt")
old = open(rd, encoding="utf-8").read()
new = old.replace("as of 2026-11-20", "as of 2026-11-23") + """

Added 2026-11-23
ml_runs/                          all ML runs r006 to r017 (leaderboards) and ML_summary.txt in plain text:
                                  DS1 vs DS2, DS1 minus DS2 per mouse, one DS type at a time with random
                                  twins, and all events with the raw event (CSD, LFP, spectrogram).
Dentate_spikes_what_we_found.html the summary deck (12 slides; open in a browser; double-click shows notes).
Exploratory pilot: P values are per test.
"""
open(rd, "w", encoding="utf-8").write(new)
print("ok", NEW)
