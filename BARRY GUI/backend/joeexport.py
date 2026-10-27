"""Tab 10, Joe's export: everything that goes to Joe, in one list, and the
same list as a site of its own he downloads it from (Shahriar, 2026-10-26).

What goes (not the slides: they are sent another way, 2026-10-26):
  * every tab 9 figure, in the order tab 9 shows it, each view (FP, the
    shuffles, the rats' flips) as PDF, SVG and 600 dpi PNG, and its numbers
    for Prism (.xlsx and .pzfx, zipped together: the .pzfx is XML and
    shrinks to a quarter);
  * every legend in one text file;
  * tab 8's results table, its read-me and the SPSS zip;
  * the standalone script and its inputs, to make the numbers again
    without Jarvis.

manifest() is the list (tab 10 shows it; /data/joeexport). site() writes
the site: review/joe_site (the password gate and the page), the shared
renderer web/js/joe_export.js, the files and manifest.json, into
GUI_logs/.cache/joe_site. Nothing here deploys: `npx vercel deploy --prod`
from that folder does, once Shahriar has said so.

Reads joe.json and figs.json straight off the disk: no numpy, no scipy (two
page requests importing scipy at once deadlocked, 2026-10-21).

    python -m backend.joeexport site      # assemble the site, print its size
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import time
import zipfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_SRC = os.path.join(APP, "review", "joe_site")
RENDERER = os.path.join(APP, "web", "js", "joe_export.js")
#: Vercel Hobby takes 100 MB a deploy; leave room for the page itself.
BUDGET_MB = 95.0
DECK_RE = re.compile(r"^Joe figures explained (\d{4}-\d{2}-\d{2})\.pptx$")
TESTS_SAY = {"fp": "FP", "shuffle": "Shuffles", "t": "t-test", "rats": "Rats’ flips"}
VIEW_SAY = {"fp": "Against FP", "trials": "Against the shuffles", "rats": "Against the rats’ flips"}


def _mono():
    from . import monolith as MO
    return MO


def joe_root(*parts):
    return os.path.join(_mono()._path("joe"), *parts)


def cache_dir(*parts):
    """Where the Prism zips and the legends file are made (git-ignored)."""
    d = joe_root("export_joe")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, *parts)


def site_dir():
    return os.path.join(APP, "GUI_logs", ".cache", "joe_site")


def _read(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def deck_path():
    """The newest dated deck in the app folder, or None (not exported: the
    check uses it to see that it stays out)."""
    got = sorted((m.group(1), os.path.join(APP, f)) for f in os.listdir(APP) for m in [DECK_RE.match(f)] if m)
    return got[-1][1] if got else None


def _prism_zip(stem, xlsx, pzfx):
    """<stem>.zip of a figure's two Prism files, made again when either is newer."""
    out = cache_dir(stem + ".zip")
    srcs = [p for p in (xlsx, pzfx) if p and os.path.isfile(p)]
    if not srcs:
        return None
    if not os.path.isfile(out) or os.path.getmtime(out) < max(os.path.getmtime(p) for p in srcs):
        tmp = out + ".part"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in srcs:
                z.write(p, os.path.basename(p))
        os.replace(tmp, out)
    return out


def _legends_file(figs):
    """Every legend, in tab 9's order, as one plain-text file."""
    out = cache_dir("Joe_figure_legends.txt")
    lines = ["Joe's figures: every legend, in the order of the figures.",
             "Made by Jarvis (tab 9) on %s. Figure numbers are tab 9's." % (figs.get("at") or "")[:10], ""]
    for f in figs["figures"]:
        name = "Supplementary Figure %s" % f["id"] if f["kind"] == "schematic" else "Figure %s" % f["id"]
        views = [f] + list(f.get("alts") or []) if f["kind"] == "connectome" else [f]
        for v in views:
            lg = v.get("legend") or {}
            head = name + ((" (%s)" % VIEW_SAY.get(v.get("null"), v.get("null"))) if f["kind"] == "connectome" else "")
            lines += [head + ". " + (lg.get("title") or ""), lg.get("body") or "", ""]
    text = "\n".join(lines)
    if not os.path.isfile(out) or open(out, encoding="utf-8").read() != text:
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return out


def _lights(J):
    """Tab 8's 24 lights: comparison × band, lit or not, and its P."""
    shown = J.get("shown") or "dickson"
    res = {(r["model"], r["band"]): r for r in J["results"]
           if r["method"] == ("welch" if r["model"] == "m7" else shown)}
    out = []
    for m in J["models"]:
        row = {"no": m["no"], "title": m.get("title") or m.get("label"), "check": m.get("kind") == "check", "bands": {}}
        for b in ("theta", "gamma"):
            r = res.get((m["id"], b))
            g = (r or {}).get("gate") or {}
            # a dark light's P: the smaller of its two terms (Day × factor,
            # and that × Pair), the ones that would have lit it
            terms = ((r or {}).get("mixed") or {}).get("terms") or {}
            ps = [t["p"] for n, t in terms.items() if n.startswith("Day × ") and n.split(" × ")[1] not in ("Pair", "Region")
                  and t.get("p") is not None]
            row["bands"][b] = {"lit": bool(g.get("passed") and (r.get("mixed") or {}).get("ok")),
                               "p": g.get("p") if g.get("passed") else (min(ps) if ps else None)}
        out.append(row)
    return out


def _tests(f):
    """A figure's three tests, FP first, each passed or not."""
    ps = f.get("passes") or {}
    if f["kind"] == "connectome":
        return [{"key": "fp", "say": "FP", "pass": ps.get("fp")}, {"key": "shuffle", "say": "Shuffles", "pass": ps.get("trials")},
                {"key": "t", "say": "Rats’ flips", "pass": ps.get("rats")}]
    if f["kind"] == "follow":
        return [{"key": "fp", "say": "FP", "pass": ps.get("fp")}, {"key": "shuffle", "say": "Shuffles", "pass": ps.get("shuffle")},
                {"key": "t", "say": "t-test", "pass": ps.get("t")}]
    return []


def manifest():
    """Everything that goes to Joe, with each file's name, size and where it
    is here (`files`: name -> path, kept out of what the page is sent)."""
    J = _read(joe_root("joe.json"))
    F = _read(joe_root("figs", "figs.json"))
    if J is None or F is None:
        return {"ok": False, "error": "Tabs 8 and 9 must be worked out and drawn first."}, {}
    paths = {}

    def add(path, name=None, say=None):
        if not path or not os.path.isfile(path):
            return None
        name = name or os.path.basename(path)
        paths[name] = path
        return {"name": name, "size": os.path.getsize(path), "say": say}

    fd = lambda n: joe_root("figs", n)        # noqa: E731
    sections = []
    # 1. the figures, in tab 9's order, grouped by window then band (the
    # slides are not sent from here: Shahriar, 2026-10-26)
    groups, cur = [], None
    for f in F["figures"]:
        gk = "S" if f["kind"] == "schematic" else (f.get("group") or {}).get("key")
        if cur is None or cur["key"] != gk:
            g = f.get("group") or {}
            cur = {"key": gk, "title": "Supplementary" if gk == "S" else "Comparison %s · %s · %s" % (g.get("no"), g.get("title"), f.get("band")),
                   "band": f.get("band"), "gated": g.get("gated"), "figures": []}
            groups.append(cur)
        name = "Supplementary Figure %s" % f["id"] if f["kind"] == "schematic" else "Figure %s" % f["id"]
        views = []
        for v in ([f] + list(f.get("alts") or [])) if f["kind"] == "connectome" else [f]:
            fl = v.get("files") or {}
            views.append({"null": v.get("null"), "say": VIEW_SAY.get(v.get("null")) if f["kind"] == "connectome" else None,
                          "legend": v.get("legend") or {},
                          "files": [x for x in [add(fd(fl[k]), say=k.upper()) for k in ("pdf", "svg", "png") if fl.get(k)] if x],
                          "preview": fl.get("svg")})
        pf = f.get("files") or {}
        prism = None
        if pf.get("xlsx") or pf.get("pzfx"):
            zp = _prism_zip("%s_prism" % ("fig_" + f["id"].replace(".", "_")),
                            fd(pf["xlsx"]) if pf.get("xlsx") else None, fd(pf["pzfx"]) if pf.get("pzfx") else None)
            prism = add(zp, say="Prism (.xlsx and .pzfx)")
        cur["figures"].append({"id": f["id"], "name": name, "kind": f["kind"], "pair": f.get("pair"),
                               "title": (f.get("legend") or {}).get("title"), "tests": _tests(f), "views": views, "prism": prism})
    leg = add(_legends_file(F), say="Every legend, in one text file")
    sections.append({"id": "figures", "title": "The figures",
                     "say": "Nature format (Arial, 183 mm wide): PDF and SVG to edit, a 600 dpi PNG to paste. Each ring figure comes "
                            "three ways, one per test; each figure’s numbers come for Prism.",
                     "groups": groups, "files": [x for x in [leg] if x]})
    # 2. tab 8's statistics
    st = [add(joe_root("export", n), say=s) for n, s in (("joe_tab8_results.csv", "Every comparison’s result, one row each"),
                                                         ("joe_tab8_README.txt", "What every file and column is"),
                                                         ("joe_tab8_spss.zip", "The data and SPSS syntax to recreate every result"))]
    sections.append({"id": "stats", "title": "The statistics",
                     "say": "Tab 8’s twelve comparisons in theta and gamma: the mixed models behind the lights, as tables and as SPSS files.",
                     "lights": _lights(J), "files": [x for x in st if x]})
    # 3. make it again
    sc = [add(os.path.join(APP, "tools", "joe_standalone.py"), say="The standalone script (numpy and scipy only)"),
          add(joe_root("joe_inputs.json"), say="Its inputs: folders, channels, regions, seed")]
    ag = J.get("agreement") or {}
    sections.append({"id": "repro", "title": "Make the numbers again",
                     "say": "One Python file that reads the recordings and makes tab 8’s tables without Jarvis." + (
                         " Run on %s, its output matched Jarvis’s to %g in every cell." % (str(ag.get("ran_at"))[:10], ag.get("tol"))
                         if ag.get("ok") else ""),
                     "files": [x for x in sc if x]})
    total = sum(os.path.getsize(p) for p in paths.values())
    n_fig = sum(len(g["figures"]) for g in groups)
    return ({"ok": True, "schema": 1, "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "joe_at": J.get("at"), "figs_at": F.get("at"),
             "rats": len(J.get("rats") or []), "days": J.get("tested"), "n_figures": n_fig, "n_files": len(paths),
             "bytes": total, "budget_mb": BUDGET_MB, "fp": F.get("fp"), "n_perm": F.get("n_perm"),
             "sections": sections, "site": site_status()}, paths)


def site_status():
    """The assembled site, if any: when, how big, and its manifest's stamp."""
    m = _read(os.path.join(site_dir(), "manifest.json"))
    if not m:
        return {"built": False}
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _d, fs in os.walk(site_dir()) for f in fs
               if ".vercel" not in r and "node_modules" not in r)
    return {"built": True, "made": m.get("made"), "bytes": size, "dir": site_dir(),
            "deployed": _read(os.path.join(site_dir(), ".vercel", "project.json")) is not None}


def site():
    """Assemble Joe's site in GUI_logs/.cache/joe_site: the gate and page
    (review/joe_site), the renderer, the files under files/, manifest.json.
    Keeps .vercel (the project link) and node_modules; replaces the rest."""
    man, paths = manifest()
    if not man.get("ok"):
        raise RuntimeError(man.get("error"))
    out = site_dir()
    os.makedirs(out, exist_ok=True)
    for n in os.listdir(out):
        if n in (".vercel", "node_modules"):
            continue
        p = os.path.join(out, n)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    shutil.copytree(SITE_SRC, out, dirs_exist_ok=True)
    os.makedirs(os.path.join(out, "js"), exist_ok=True)
    shutil.copyfile(RENDERER, os.path.join(out, "js", "joe_export.js"))
    fdir = os.path.join(out, "files")
    os.makedirs(fdir, exist_ok=True)
    for name, path in paths.items():
        shutil.copyfile(path, os.path.join(fdir, name))
    man = dict(man, site=None)
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False)
    st = site_status()
    if st["bytes"] > BUDGET_MB * 1e6:
        raise RuntimeError("Joe's site is %.1f MB, over the %.0f MB a deploy can take." % (st["bytes"] / 1e6, BUDGET_MB))
    return st


if __name__ == "__main__":
    import sys
    sys.path.insert(0, APP)
    from backend import monolith as MO
    MO.configure(os.path.join(APP, "GUI_logs"))
    if sys.argv[1:] == ["site"]:
        s = site()
        print("Joe's site: %s, %.1f MB of %.0f" % (s["dir"], s["bytes"] / 1e6, BUDGET_MB))
    else:
        m, p = manifest()
        print(json.dumps({k: v for k, v in m.items() if k != "sections"}, indent=1))
