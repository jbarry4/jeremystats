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
import re
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
        want |= {v["files"]["pdf"]} if v.get("files", {}).get("pdf") else set()
views = [v for f in listed for v in f["views"]]
check("every view of every figure as a PDF and nothing else to download, with a preview to look at (%d PDFs; 2026-10-30, \"keep just PDF\")"
      % len(want), want <= set(paths) and all([x["name"].endswith(".pdf") for x in v["files"]] == [True] for v in views)
      and all(v["preview"] in paths and v["preview"].endswith("_preview.webp") for v in views)          # WebP since 2026-11-04
      and not any(n.endswith(".svg") or (n.endswith(".png") and not n.endswith("_preview.png")) for n in paths), sorted(want - set(paths))[:4])
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

print("\nDickson's way (tab 11) and Part 2 (tab 12)")
EMj = MO._path("evenmore", "evenmore.json")
FNj = MO._path("final", "final.json")
PUBj = MO._path("joepub", "pub.json")
secs = {s["id"]: s for s in man["sections"]}
if os.path.isfile(PUBj):
    # 2026-11-02: tabs 11 and 12 as the publication set, every set of rats, and the methods
    PUB = json.load(open(PUBj, encoding="utf-8"))
    from backend import evenmore as E_, finalstage as FS_
    sets_ = [s["key"] for s in PUB["sets"]]
    check("the methods for the dissertation come first (after volume conduction, in Wrapping up), every section with its words, as Word and as text",
          [s["id"] for s in man["sections"] if s["id"] != "conduction"][0] == "methods" and len(secs["methods"]["prose"]) >= 10
          and all(s["paras"] for s in secs["methods"]["prose"])
          and {f["name"] for f in secs["methods"]["files"]} == {"Methods_for_the_dissertation.docx", "Methods_for_the_dissertation.txt"})
    meth = " ".join(p for s in secs["methods"]["prose"] for p in s["paras"])
    check("the methods name no step by Jarvis's own names (Spark, Coupling, Circuit, Drift, Monolith, Jarvis)",
          not re.search(r"\b(Spark|Coupling|Circuit|Drift|Monolith|Jarvis)\b", meth), re.findall(r"\b(Spark|Coupling|Circuit|Drift|Monolith|Jarvis)\b", meth)[:5])
    check("the methods cover the recordings to the statistics: events, saturation, the wire rule, decimation, the notch, pooled spectra, "
          "GEE, FDR, the tiers, robustness, the excluded rats, the exploratory survey",
          all(w in meth for w in ("TTL", "saturation", "lowest-numbered", "Chebyshev", "59–61 Hz", "pooled spectra", "generalized estimating",
                                  "Benjamini–Hochberg", "Tier 1", "Tier 3b", "omitted in turn", "without J3", "DerSimonian–Laird",
                                  "head stage", "excluded from that window by hand", "not normalised separately for each rat")))
    hb = next((s for s in secs["methods"]["prose"] if s["title"] == "Artefacts from head bumps"), None)
    check("the head bumps have their own section: how they were found, what was removed, and every rat-day's losses",
          hb is not None and len(re.findall(r"J\d+ Precon[14], \d+; \d+; \d+; [\d,]+ of [\d,]+", " ".join(hb["paras"]))) == 16,
          hb and hb["paras"][-1][:200])
    for sid, tab in (("dickson", "tab 11"), ("final", "tab 12")):
        sec = secs[sid]
        for rs in sets_:
            figs = [f for g in sec["sets"].get(rs, []) for f in g["figures"]]
            if sid == "dickson":
                ES = E_.result(rs)
                want = sum(len(B[k]["figures"]) for B in ES["bands"] for k in ("phase1", "phase2", "phase3"))
            else:
                FSr = FS_.result(rs)
                want = sum(len(v) for k, v in FSr["figures"].items() if k != "side")
            check("%s, %s: every figure (%d), each a PDF with a preview, its statistics PDF, a caption under each reading, a results "
                  "paragraph, a methods note and its tests" % (tab, rs, want), len(figs) == want and all(
                      f["files"][0]["name"].endswith(".pdf") and f["stats"] and f["stats"]["name"].endswith("_statistics.pdf")
                      and f["files"][-1]["name"] == f["stats"]["name"] and f["preview"] in paths
                      and f["caption"].startswith("Figure ") and "Benjamini–Hochberg" in f["caption"] and "uncorrected" in f["caption_raw"]
                      and " displayed in Figure %s" % f["id"] in f["results"][0] and f["note"] and f["tests"] is not None for f in figs),
                  (len(figs), want))
            fr = [f for f in figs if f.get("files_raw")]
            check("%s, %s: the uncorrected drawing only where it differs (%d), with its own preview" % (tab, rs, len(fr)),
                  all(f["files_raw"][0]["name"].endswith("_uncorrected.pdf") and f["preview_raw"] in paths for f in fr))
            fo = [f for f in figs if f.get("files_own")]
            check("%s, %s: a version fitted to each figure where it differs (%d of %d), with its preview, and the axes said in each caption"
                  % (tab, rs, len(fo), len(figs)),
                  all(f["files_own"][0]["name"].endswith("_fitted.pdf") and f["preview_own"] in paths for f in fo)
                  and all((f.get("files_own_raw") is None or (f["files_own_raw"][0]["name"].endswith("_fitted_uncorrected.pdf")
                                                              and f["preview_own_raw"] in paths)) for f in figs)
                  and all("shared by every figure of this kind" in f["axes_say"]["shared"] and "fitted to this figure alone" in f["axes_say"]["own"]
                          and (("cut off" in f["axes_say"]["shared"]) == bool(f.get("cut"))) for f in figs))
    import fitz
    allf = [f for s in ("dickson", "final") for g in secs[s]["sets"]["all"] for f in g["figures"]]
    leaks, stray, missing = [], [], []
    for f in allf:
        for mode, fs in (("fdr", f["files"]), ("raw", f.get("files_raw")), ("fdr", f.get("files_own")), ("raw", f.get("files_own_raw"))):
            if not fs:
                continue
            t = "".join(pg.get_text() for pg in fitz.open(paths[fs[0]["name"]]))
            if re.search(r"χ|FDR|q = |p = |p < |GEE|passes", t):
                leaks.append(fs[0]["name"])
            star = "*" in t
            any_pass = any((x.get("pass") or {}).get(mode) for x in f["tests"])
            if star and not any_pass:
                stray.append(fs[0]["name"])
            # a figure that stars its main test must show the star when that test passes
            if f["kind"] in ("p1pair", "p3pair", "power", "granger", "pac") and any((x.get("pass") or {}).get(mode) for x in f["tests"] if x["primary"]) and not star:
                missing.append(fs[0]["name"])
    check("no statistic or title inside any figure (%d PDFs read)" % len(allf), not leaks, leaks[:4])
    check("a star only where one of the figure's tests passes under that reading, and on every figure whose main test passes",
          not stray and not missing, (stray[:4], missing[:4]))
    bad_stats = []
    for f in allf:
        t = "".join(pg.get_text() for pg in fitz.open(paths[f["stats"]["name"]]))
        prim = [x for x in f["tests"] if x["primary"]]
        if "generalized estimating equation" not in t or "Results" not in t or "Wald" not in t \
                or any(("%.2f" % float(re.search(r"= ([\d.]+)", x["stat"]).group(1))) not in t for x in prim):
            bad_stats.append(f["stats"]["name"])
    check("each statistics PDF (%d) has the design, the Wald table and the results, and prints its figure's main tests as the page does"
          % len(allf), not bad_stats, bad_stats[:4])
    gr = [f for rs in sets_ for g in secs["final"]["sets"][rs] for f in g["figures"] if f["kind"] == "granger"]
    check("every Granger figure (%d) has its note for Joe: what both directions changing together means, and the cautions" % len(gr),
          gr and all(f.get("reading") and any("Granger causality" in p for p in f["reading"]) and "Two cautions" in f["reading"][-1] for f in gr))
    if "sanity" in secs:
        sr = secs["sanity"]["sanity"]
        check("the sanity check report is the last section, with its verdict and every check's status, result and how",
              man["sections"][-1]["id"] == "sanity" and sr.get("verdict") in ("green", "amber", "red")
              and all(c.get("status") in ("ok", "warn", "fail", "info") and c.get("result") and c.get("how")
                      for s in sr["sections"] for c in s["checks"]))
    # how volume conduction was handled (backend/conduction.py, 2026-11-05)
    cv = (secs.get("conduction") or {}).get("conduction") or {}
    m_cv = next((s for s in secs["methods"].get("prose") or [] if s["title"] == "Volume conduction"), None)
    refs = " ".join(next((s["paras"] for s in secs["methods"].get("prose") or [] if s["title"] == "References"), []))
    check("volume conduction: its own section, first (the site's Wrapping up tab, before the methods), every step with a line and a More, what is still open, "
          "and a methods section whose citations are in the references",
          [s["id"] for s in man["sections"]][:2] == ["conduction", "methods"] and len(cv.get("steps") or []) >= 6
          and all(s.get("title") and s.get("line") and s.get("more") for s in cv["steps"]) and bool(cv.get("open"))
          and m_cv is not None and all(a in refs for a in ("Nolte G", "Stam CJ", "Vinck M")),
          ([s["id"] for s in man["sections"]][:3], len(cv.get("steps") or []), m_cv is not None))
    lag = next((s for s in cv.get("steps") or [] if s["key"] == "lag"), None)
    lagn = (cv.get("numbers") or {}).get("lag") or []
    j3 = next((x for x in lagn if x["rat"] == 3 and x["day"] == "Precon4"), None)
    rest = [x for x in lagn if x["rat"] not in (3, 4)]
    check("volume conduction: J3's Precon4 excess is at zero lag, as its words say (coherence far above, imaginary part inside the rest)",
          lag and j3 and rest and j3["coh"] > 2 * max(x["coh"] for x in rest) and j3["icoh"] <= max(x["icoh"] for x in rest), j3)
    raw_json = json.dumps(man, ensure_ascii=False)
    check("the side question never reaches Joe: no figure, no file, no word of it",
          "side_question" not in raw_json and "Side question" not in raw_json and not any("side" in n.lower() for n in paths))
    check("Granger and coupling figures say which side of the switch they belong to; the rats' sets are offered, all of them first",
          all(f.get("show_in") is not None for rs in sets_ for g in secs["final"]["sets"][rs] if g["key"] == "follow" for f in g["figures"])
          and [s["key"] for s in man["rat_sets"]][0] == "all" and man.get("switch", {}).get("default") == "fdr")
elif os.path.isfile(EMj):
    EMd = json.load(open(EMj, encoding="utf-8"))
    dfig = [f for g in secs["dickson"]["groups"] for f in g["figures"]]
    nfig = sum(len(B[k]["figures"]) for B in EMd["bands"] for k in ("phase1", "phase2", "phase3"))
    check("Dickson's way: every tab 11 figure, all three phases (%d), each drawn both sides of the switch" % nfig,
          len(dfig) == nfig and all([v["key"] for v in f["views"]] == ["fdr", "raw"] for f in dfig))
    check("its files named apart from tab 9's (Dickson_)", all(x["name"].startswith("Dickson_") for f in dfig for v in f["views"] for x in v["files"]))
if os.path.isfile(FNj) and not os.path.isfile(PUBj):
    FNd = json.load(open(FNj, encoding="utf-8"))
    ffig = [f for g in secs["final"]["groups"] for f in g["figures"]]
    nf = sum(len(v) for k, v in FNd["figures"].items() if k != "side")
    check("Part 2: every tab 12 figure but the side question (%d), each both sides of the switch" % nf,
          len(ffig) == nf and all([v["key"] for v in f["views"]] == ["fdr", "raw"] for f in ffig))
    raw_json = json.dumps(man, ensure_ascii=False)
    check("the side question never reaches Joe: no figure, no file, no word of it",
          "side_question" not in raw_json and "Side question" not in raw_json and not any("side" in n.lower() for n in paths), )
    with zipfile.ZipFile(paths["Final_GEE_files.zip"]) as z:
        check("Part 2's zip holds the methods (Word and text), the rows and SPSS's coefficients, and no side question",
              {"final_methods.docx", "final_methods.txt", "final_long.csv", "final_coefficients_spss.csv"} <= set(z.namelist())
              and not any("side" in n for n in z.namelist()), z.namelist())
    check("the methods are in the page with the four power tiers; “20 × 16 × 8 × 2” is gone (J Charles: drop it); the switch starts corrected",
          bool(secs["final"].get("methods")) and "Tier 1" in raw_json and "Tier 3b" in raw_json and "20 × 16" not in raw_json
          and "twenty" not in man and man.get("switch", {}).get("default") == "fdr")
    check("Granger and coupling figures say which side of the switch they belong to",
          all(f.get("show_in") is not None for g in secs["final"]["groups"] if g["key"] == "F-follow" for f in g["figures"]))

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
