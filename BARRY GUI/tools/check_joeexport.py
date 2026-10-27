"""check_joeexport.py -- tab 10, Joe's export, on this machine's real tabs 8
and 9: everything tab 9 drew is in the list, every file in the list is what
it says, and the assembled site holds exactly the list and nothing of this
machine's (no local paths), behind a gate of its own.

    python tools/check_joeexport.py

Assembles GUI_logs/.cache/joe_site (git-ignored) as tab 10's button does;
deploys nothing.
"""
import json
import os
import subprocess
import sys
import zipfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from backend import monolith as MO                     # noqa: E402

MO.configure(os.path.join(APP, "GUI_logs"))
from backend import joeexport as JX                    # noqa: E402

ok = bad = 0


def check(name, cond, detail=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    " + name)
    else:
        bad += 1
        print("  FAIL  " + name + ("   " + repr(detail)[:300] if detail is not None else ""))


print("The list (tab 10)")
man, paths = JX.manifest()
check("tabs 8 and 9 are there to list", man.get("ok"), man.get("error"))
F = json.load(open(JX.joe_root("figs", "figs.json"), encoding="utf-8"))
figsec = next(s for s in man["sections"] if s["id"] == "figures")
listed = [f for g in figsec["groups"] for f in g["figures"]]
check("every figure tab 9 drew, in its order (%d)" % len(F["figures"]), [f["id"] for f in listed] == [f["id"] for f in F["figures"]],
      [f["id"] for f in listed][:6])
want = set()
for f in F["figures"]:
    for v in [f] + list(f.get("alts") or []):
        want |= {v["files"][k] for k in ("pdf", "svg", "png") if v.get("files", {}).get(k)}
check("every view of every figure as PDF, SVG and PNG (%d files)" % len(want), want <= set(paths), sorted(want - set(paths))[:4])
pz = [f for f in listed if f["kind"] != "schematic"]
okz = True
for f in pz:
    src = next(x for x in F["figures"] if x["id"] == f["id"])["files"]
    with zipfile.ZipFile(paths[f["prism"]["name"]]) as z:
        got = {i.filename: i.file_size for i in z.infolist()}
    okz &= got == {src[k]: os.path.getsize(JX.joe_root("figs", src[k])) for k in ("xlsx", "pzfx")}
check("each figure's Prism zip holds its .xlsx and .pzfx, byte for byte (%d)" % len(pz), okz)
check("each figure's three tests, FP first", all([t["key"] for t in f["tests"]] == ["fp", "shuffle", "t"] for f in pz))
ring = [f for f in listed if f["kind"] == "connectome"]
check("each ring three ways: FP, then the shuffles, then the rats' flips",
      all([v["null"] for v in f["views"]] == ["fp", "trials", "rats"] for f in ring), [[v["null"] for v in f["views"]] for f in ring][:2])
leg = open(paths["Joe_figure_legends.txt"], encoding="utf-8").read()
check("every legend in one text file, each view's",
      all((v["legend"].get("title") or "") in leg for f in listed for v in f["views"]))
check("no slides: no .pptx anywhere in the list (sent another way, 2026-10-26)",
      not any(n.lower().endswith(".pptx") for n in paths) and all(s["id"] != "slides" for s in man["sections"]))
st = next(s for s in man["sections"] if s["id"] == "stats")
J = json.load(open(JX.joe_root("joe.json"), encoding="utf-8"))
lit = sum(b["lit"] for r in st["lights"] for b in r["bands"].values())
want_lit = sum(1 for r in J["results"] if r["method"] == ("welch" if r["model"] == "m7" else "dickson")
               and (r.get("gate") or {}).get("passed") and (r.get("mixed") or {}).get("ok"))
check("tab 8's lights: %d lit, as tab 8 says" % want_lit, lit == want_lit and len(st["lights"]) == len(J["models"]), lit)
check("tab 8's files: results, read-me, SPSS zip; the script and its inputs",
      {"joe_tab8_results.csv", "joe_tab8_README.txt", "joe_tab8_spss.zip", "joe_standalone.py", "joe_inputs.json"} <= set(paths))
check("the size the list says is the files' (%.1f MB), under the %.0f MB a deploy takes" % (man["bytes"] / 1e6, JX.BUDGET_MB),
      man["bytes"] == sum(os.path.getsize(p) for p in paths.values()) and man["bytes"] < JX.BUDGET_MB * 1e6)

print("\nThe site")
s = JX.site()
out = JX.site_dir()
sm = json.load(open(os.path.join(out, "manifest.json"), encoding="utf-8"))
check("assembled: the page, the gate, the renderer, the manifest",
      all(os.path.isfile(os.path.join(out, p)) for p in ("index.html", "login.html", "middleware.js", "api/login.js", "api/logout.js",
                                                          "lib/gate.js", "js/joe_export.js", "package.json", "vercel.json")))
check("its files/ is exactly the list, byte for byte",
      sorted(os.listdir(os.path.join(out, "files"))) == sorted(paths)
      and all(os.path.getsize(os.path.join(out, "files", n)) == os.path.getsize(p) for n, p in paths.items()))
raw = open(os.path.join(out, "manifest.json"), encoding="utf-8").read()
check("nothing of this machine in what Joe is sent: no local paths in the manifest", "GUI_logs" not in raw and ":\\\\" not in raw
      and sm.get("site") is None)
check("under the deploy limit (%.1f MB)" % (s["bytes"] / 1e6), s["bytes"] < JX.BUDGET_MB * 1e6)
check("its own project name", json.load(open(os.path.join(out, "package.json")))["name"] == "joe-export")
try:
    vj = json.load(open(os.path.join(out, "vercel.json"), encoding="utf-8"))
except ValueError as exc:                                # a hand-edit broke it (2026-10-26: "\." in a source)
    vj = {"error": str(exc)}
check("vercel.json reads as JSON, with its headers", isinstance(vj.get("headers"), list), vj.get("error"))
# The gate: its own cookie, and a review-site cookie signed with the same
# secret does not open it.
node = r"""
const j = await import(process.argv[1]); const r = await import(process.argv[2]);
const until = Date.now() + 864e5;
const tj = await j.sign('s3cret', until), tr = await r.sign('s3cret', until);
console.log(JSON.stringify({ own: await j.valid('s3cret', tj), other: await j.valid('s3cret', tr), cookie: j.COOKIE, rcookie: r.COOKIE,
  wrong: await j.samePassword('s3cret', 'nope', 'pw'), right: await j.samePassword('s3cret', 'pw', 'pw') }));
"""
url = lambda p: "file:///" + p.replace("\\", "/")              # noqa: E731
got = subprocess.run(["node", "--input-type=module", "-e", node, url(os.path.join(out, "lib", "gate.js")),
                      url(os.path.join(APP, "review", "site", "lib", "gate.js"))], capture_output=True, text=True)
try:
    g = json.loads(got.stdout.strip().splitlines()[-1])
except (ValueError, IndexError):
    g = {}
check("the gate: its own cookie opens it, the review site's does not, and only the right password signs in",
      g.get("own") is True and g.get("other") is False and g.get("cookie") != g.get("rcookie") and g.get("right") is True
      and g.get("wrong") is False, g or got.stderr[-300:])

print("\n%d passed, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
