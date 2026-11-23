"""
sanity.py -- the Monolith page's thirteenth tab: the sanity check report.

The last look before Joe's numbers leave the lab (the user, 2026-11-04):
did the right data go in, was the right logic applied, do the words say
what the numbers say, can it all be made again from the raw recordings,
and what should a careful reader know. Nothing here is taken on trust from
the tab that made it: the rat-days are found again in the manifest and on
disk, the models are refitted from the tabs' own row builders, the FDR is
worked out again from the stored p values, and the words are read back
against the numbers they describe.

Every check says how it was checked and what it found, with the numbers.
A check that cannot run says why, as "warn": a check that did not run is
never "ok". The verdict is red when any check fails, amber when none fails
but some warn, green otherwise.

    python -m backend.sanity [quick]   -> GUI_logs/.cache/monolith/sanity/sanity.json

`quick` leaves out the three check tools (minutes each); the rest takes
about a minute. Nothing here writes anywhere but the sanity folder.
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import subprocess
import sys
import time

import numpy as np

from . import evenmore as E
from . import finalstage as FS
from . import joe
from . import joepub as JP

SCHEMA = 1
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: The eight rats (J5 has no Precon4 recording and no histology row: the
#: manifest's own note). Written here, not read, so it is an expectation.
STUDY_RATS = (3, 4, 6, 7, 8, 9, 10, 11)
SECTIONS = (("data", "The right data went in", "Are the recordings, trials, wires and rats the ones the analysis says it used?"),
            ("logic", "The right logic was applied", "Do the stored statistics come out again when the models are fitted afresh?"),
            ("words", "The words match the numbers", "Does every sentence Joe is sent say what its numbers say?"),
            ("repro", "It can be made again from the raw data", "Could someone with the recordings and the repository make it all again?"),
            ("concerns", "What a careful reader should know", "What the results themselves say about how far to trust them."))
TOOLS = ("check_evenmore.py", "check_final.py", "check_joeexport.py")
TOOL_TIMEOUT = 30 * 60
REL_TOL = 1e-8
INTERNAL = re.compile(r"\b(Spark|Coupling|Circuit|Drift|Monolith|Jarvis)\b")
#: Words that are also plain English at the start of a sentence.
INTERNAL_ENGLISH = ("Coupling", "Circuit", "Drift")
#: The code whose changes change a number or a word Joe is sent.
RESULT_CODE = ("backend/evenmore.py", "backend/finalstage.py", "backend/joepub.py", "backend/joestats.py", "backend/joe.py",
               "backend/coupling.py", "backend/sweep.py", "backend/probes.py", "backend/monolith.py", "backend/joeexport.py",
               "tools/joe_standalone.py")
PAIR_KINDS = ("p1pair", "p2pair", "p3pair")
STAR_KINDS = ("p1pair", "p3pair", "power", "granger", "pac")


class SanityError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _root(*parts):
    from . import monolith as MO
    return MO._path("sanity", *parts)


# --------------------------------------------------------------------------
# What the checks read, each loaded once
# --------------------------------------------------------------------------
class _Ctx:
    """The manifest, the tabs' results and the rat-days, loaded on first
    use and kept: several checks read the same things."""

    def __init__(self, quick):
        self.quick = quick
        self._c = {}
        self.tool_out = {}          # L1's output, which L4 reads back

    def _get(self, key, fn):
        if key not in self._c:
            self._c[key] = fn()
        return self._c[key]

    @property
    def man(self):
        from . import monolith as MO
        return self._get("man", MO.manifest)

    @property
    def names(self):
        from . import sweep
        return self._get("names", lambda: list((self.man or {}).get("regions") or sweep.regions()))

    def day(self, rat, day):
        """The manifest's record of one rat-day, or None."""
        idx = self._get("dayidx", lambda: {(int(d["rat"]), d["day"]): d for d in (self.man or {}).get("days") or []})
        return idx.get((rat, day))

    def em(self, rs):
        return self._get(("em", rs), lambda: E.result(rs))

    def fn(self, rs):
        return self._get(("fn", rs), lambda: FS.result(rs))

    @property
    def pub(self):
        return self._get("pub", JP.result)

    @property
    def every(self):
        """Tab 11's pooled rat-days, every rat."""
        return self._get("every", E.load_days)

    def days(self, rs):
        return self._get(("days", rs), lambda: {k: v for k, v in self.every.items() if k[0] not in E.RATSET_DROP[rs]})

    def T(self, rs):
        return self._get(("T", rs), lambda: E.tables(self.days(rs)))

    def PT(self, rs):
        return self._get(("PT", rs), lambda: FS.power_tables(self.days(rs)))

    @property
    def sat(self):
        return self._get("sat", JP.saturation_counts)

    @property
    def refs(self):
        return self._get("refs", JP._refs_of_recordings)


def _sets():
    return [k for k, _s, _d in E.RATSETS]


def _check(cid, status, title, how, result, detail=None, table=None):
    out = {"id": cid, "status": status, "title": title, "how": how, "result": result}
    if detail:
        out["detail"] = [str(x) for x in detail]
    if table and table.get("rows"):
        out["table"] = {"head": [str(h) for h in table["head"]], "rows": [[_cell(c) for c in r] for r in table["rows"]]}
    return out


def _cell(c):
    if c is None:
        return ""
    if isinstance(c, float):
        return "%.4g" % c
    return str(c)


def _rd(rat, day):
    return "J%d %s" % (rat, day)


def _same(a, b, rel=REL_TOL):
    """Two stored numbers agree: both missing, or within `rel` of each other."""
    if a is None or b is None:
        return a is None and b is None
    a, b = float(a), float(b)
    if not (math.isfinite(a) and math.isfinite(b)):
        return (math.isnan(a) and math.isnan(b)) or a == b
    return abs(a - b) <= rel * max(abs(a), abs(b)) or a == b


def _iso_mtime(path):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(path)))


def _plural(n, one, many=None):
    return "%d %s" % (n, one if n == 1 else (many or one + "s"))


def _text_of_pdf(path):
    import fitz
    with fitz.open(path) as d:
        t = "".join(pg.get_text() for pg in d)
    return re.sub(r"\s+", " ", t)


def _figures(pub, rs):
    return [f for g in ((pub or {}).get("by_set") or {}).get(rs, {}).get("groups") or [] for f in g["figures"]]


# --------------------------------------------------------------------------
# The right data went in
# --------------------------------------------------------------------------
def d1_rat_days(X):
    title = "Every tested rat-day is in, at every stage"
    how = ("Each of the eight rats' Precon1 and Precon4 was looked up in the Monolith manifest; then tab 8's day file, under the name "
           "that hashes its inputs (trials, wires marked bad, histology, folders), so a file that exists was made from these inputs; "
           "then tab 11's pooled-spectra day file, under the name that hashes tab 8's.")
    if not X.man:
        return _check("D1", "warn", title, how, "There is no Monolith manifest under the current schema here, so nothing could be looked up.")
    rows, gaps = [], []
    for rat in STUDY_RATS:
        for day in E.DAYS:
            d = X.day(rat, day)
            if not d:
                rows.append([_rd(rat, day), "no", "", ""])
                gaps.append("%s is not in the manifest" % _rd(rat, day))
                continue
            jp = joe._day_path(d, joe.day_key(d, X.names))
            ep = E._day_path(d, E.day_key(d, jp))
            j_ok, e_ok = os.path.isfile(jp), os.path.isfile(ep)
            rows.append([_rd(rat, day), "yes", "yes" if j_ok else "no", "yes" if e_ok else "no"])
            if not j_ok:
                gaps.append("%s: tab 8's day file for these inputs is missing (its trials, bad wires or histology changed since)" % _rd(rat, day))
            if not e_ok:
                gaps.append("%s: tab 11's day file for tab 8's file is missing" % _rd(rat, day))
    extra = sorted({(int(d["rat"]), d["day"]) for d in X.man.get("days") or [] if d["day"] in E.DAYS} - {(r, d) for r in STUDY_RATS for d in E.DAYS})
    detail = ["The manifest also has %s, not tested here." % ", ".join(_rd(*k) for k in extra)] if extra else []
    detail.append("Manifest made %s; %s in it (%s)." % (X.man.get("at"), _plural(len(X.man.get("rats") or []), "rat"),
                                                       ", ".join("J%d" % r for r in X.man.get("rats") or [])))
    n_ok = sum(1 for r in rows if r[1:] == ["yes", "yes", "yes"])
    table = {"head": ["Rat-day", "In the manifest", "Tab 8 day file", "Tab 11 day file"], "rows": rows}
    if gaps:
        return _check("D1", "fail", title, how, "%d of %d rat-days are in at every stage. %s." % (n_ok, len(rows), "; ".join(gaps)), detail, table)
    return _check("D1", "ok", title, how, "All %d rat-days (8 rats, Precon1 and Precon4) are in the manifest, with tab 8's and tab 11's "
                  "day files made from the inputs the manifest holds now." % len(rows), detail, table)


def _meta_only(path):
    """A day file's meta, without loading its arrays."""
    with np.load(path, allow_pickle=False) as z:
        return json.loads(str(z["meta"]))


def d2_trials(X):
    title = "The same trials at every stage"
    how = ("For each rat-day: the trials in the manifest (its curated units), the trials in tab 8's day-file record, and the trials "
           "tab 11 counted (evenmore.json, all rats); the trial names were compared too, not only their number.")
    em = X.em("all")
    if not X.man or not em:
        return _check("D2", "warn", title, how, "The manifest or tab 11's result is missing, so the counts could not be compared.")
    rows, bad, short = [], [], []
    for rat in STUDY_RATS:
        for day in E.DAYS:
            d = X.day(rat, day)
            if not d:
                continue
            ids = [u["id"] for u in d.get("units") or []]
            jp = joe._day_path(d, joe.day_key(d, X.names))
            j_ids = [t["id"] for t in _meta_only(jp)["trials"]] if os.path.isfile(jp) else None
            ep = E._day_path(d, E.day_key(d, jp))
            e_ids = _meta_only(ep)["trials"] if os.path.isfile(ep) else None
            n11 = (em.get("trials") or {}).get("%s r%d" % (day, rat))
            same = j_ids == ids and e_ids == ids and n11 == len(ids)
            rows.append([_rd(rat, day), len(ids), len(j_ids) if j_ids is not None else "missing", n11 if n11 is not None else "missing",
                         "yes" if same else "no"])
            if not same:
                bad.append(_rd(rat, day))
            if len(ids) < 16:
                short.append("%s (%d)" % (_rd(rat, day), len(ids)))
    tot = sum(r[1] for r in rows)
    detail = []
    if short:
        detail.append("Sessions with fewer than the 16 trials presented (trials left out when curated): %s." % ", ".join(short))
    tr = sorted(r[1] for r in rows)
    meth = " ".join(p for s in (X.pub or {}).get("methods") or [] for p in s["paras"])
    m = re.search(r"sessions contributed (\d+) to (\d+) trials", meth)
    if m:
        detail.append("The methods say sessions contributed %s to %s trials; counted here, %d to %d." % (m.group(1), m.group(2), tr[0], tr[-1]))
        if (int(m.group(1)), int(m.group(2))) != (tr[0], tr[-1]):
            bad.append("the methods' range")
    table = {"head": ["Rat-day", "Manifest", "Tab 8", "Tab 11", "Same trials"], "rows": rows}
    if bad:
        return _check("D2", "fail", title, how, "The trials differ between stages for %s." % ", ".join(bad), detail, table)
    return _check("D2", "ok", title, how, "%d trials over %d rat-days, the same trials (by name) in the manifest, tab 8 and tab 11."
                  % (tot, len(rows)), detail, table)


def _workbook_map():
    """{side name: [CSC]} for the ten analysed sides, as electrode_map.xlsx
    has them, read by tools/check_electrode_map.py's own reader."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_check_electrode_map", os.path.join(APP, "tools", "check_electrode_map.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sheet = mod.from_workbook()
    if sheet is None:
        return None, mod.BOOK
    words = (("orbitofrontal", "OFC"), ("cingulate", "ACC"), ("perirhinal", "PER"), ("retrosplenial", "RSC"), ("hippocamp", "DHC"),
             ("postrhinal", "POR"))
    out = {}
    for ch, (_label, full, hemi) in sheet.items():
        st = next((s for w, s in words if w in full.lower()), None)
        if st:
            out.setdefault("%s %s" % (hemi.capitalize(), st), []).append(int(ch))
    return {k: sorted(v) for k, v in out.items() if k in E.SIDE_NAMES}, mod.BOOK


def d3_channel_map(X):
    title = "The channel map is the lab's final one"
    how = ("The map the analysis reads (coupling.dewey_map(), the ten analysed sides) was compared channel by channel with "
           "electrode_map.xlsx, read the way tools/check_electrode_map.py reads it; the final map has left OFC on CSC 21-22 and left ACC "
           "on CSC 23-24 (resolved 2026-09-30).")
    from . import coupling
    used = {k: sorted(int(c) for c in v) for k, v in coupling.dewey_map().items() if k in E.SIDE_NAMES}
    book, path = _workbook_map()
    if book is None:
        return _check("D3", "warn", title, how, "The workbook could not be read here (%s), so the map was not compared." % path)
    diff = ["%s: analysis %s, workbook %s" % (k, used.get(k), book.get(k)) for k in E.SIDE_NAMES if used.get(k) != book.get(k)]
    fixed = used.get("Left OFC") == [21, 22] and used.get("Left ACC") == [23, 24]
    rows = [[k, ", ".join(str(c) for c in used.get(k) or []), ", ".join(str(c) for c in book.get(k) or [])] for k in E.SIDE_NAMES]
    table = {"head": ["Side", "Analysis (CSC)", "Workbook (CSC)"], "rows": rows}
    if diff or not fixed:
        return _check("D3", "fail", title, how, "The map differs from the workbook: %s." % ("; ".join(diff) or "left OFC and ACC are not on 21-22 and 23-24"),
                      table=table)
    return _check("D3", "ok", title, how, "All ten sides match the workbook, %d channels; left OFC is CSC 21-22 and left ACC CSC 23-24."
                  % sum(len(v) for v in used.values()), table=table)


def d4_histology(X):
    title = "Histology decided which regions each rat gives"
    how = ("Each rat's sides left out by histology were read from the manifest (a side is left out on both days or neither); a region "
           "counts for a rat when at least one of its sides is kept on both days. Those counts were compared with the rats tab 12 "
           "fitted for each region, theta and gamma, in every set of rats.")
    if not X.man:
        return _check("D4", "warn", title, how, "There is no manifest here, so histology could not be read.")
    rows, odd = [], []
    kept = {}
    for rat in STUDY_RATS:
        b = [set(k for k in ((X.day(rat, d) or {}).get("blocked") or {}) if k in E.SIDE_NAMES) for d in E.DAYS]
        if b[0] != b[1]:
            odd.append("J%d's sides left out differ between Precon1 (%s) and Precon4 (%s)" % (rat, ", ".join(sorted(b[0])), ", ".join(sorted(b[1]))))
        out = b[0] | b[1]
        rows.append(["J%d" % rat, ", ".join(sorted(out)) or "none"])
        kept[rat] = {r for r in FS.REGIONS if any("%s %s" % (s, r) not in out for s in E.SIDES)}
    counts, mism = [], []
    for rs in _sets():
        fn = X.fn(rs)
        if not fn:
            mism.append("tab 12 has no result for %s" % E.RATSET_SAY[rs])
            continue
        for r in FS.REGIONS:
            want = sorted(rat for rat in STUDY_RATS if rat not in E.RATSET_DROP[rs] and r in kept[rat])
            got = {b: next(((x or {}).get("rats") for x in fn["power"][b] if x and x["region"] == r), None) for b in ("theta", "gamma")}
            if rs == "all":
                counts.append([FS.REGION_SAY[r], len(want), len(got["theta"] or []), len(got["gamma"] or [])])
            for b, g in got.items():
                if (g or []) != want and not (g is None and len(want) < E.MIN_RATS):
                    mism.append("%s, %s %s: histology gives %s, tab 12 fitted %s" % (E.RATSET_SAY[rs], FS.REGION_SAY[r], b,
                                                                                   want, g))
    detail = ["Rats per region (all rats): %s." % "; ".join("%s %d" % (c[0], c[1]) for c in counts)] + odd
    table = {"head": ["Rat", "Sides left out by histology"], "rows": rows}
    if mism or odd:
        return _check("D4", "fail", title, how, "Histology and tab 12 disagree: %s." % "; ".join(mism + odd), detail, table)
    return _check("D4", "ok", title, how, "In all four sets of rats, every region's rats in tab 12 (theta and gamma) are exactly the rats "
                  "histology keeps for it (all rats: %s)." % ", ".join("%s %d" % (c[0], c[1]) for c in counts), detail, table)


def _rats_in(em, fn, pub_set):
    """Every rat named anywhere in one set's results: (where, rat)."""
    out = []

    def add(where, rats):
        out.extend((where, int(r)) for r in rats or [])
    if em:
        add("tab 11 rats", em.get("rats"))
        for x in em.get("pairs") or []:
            add("tab 11 pair %s" % x.get("say"), x.get("rats"))
        for B in em.get("bands") or []:
            for ph in ("phase1", "phase2", "phase3"):
                for x in B[ph]["pairs"]:
                    if x:
                        add("tab 11 %s %s %s" % (B["band"], ph, E.PAIR_SAY[x["pair"]]), x.get("rats"))
        for r in em.get("robust") or []:
            add("tab 11 leave-one-out", [x["rat"] for x in r.get("loo") or []])
        add("tab 11 trials", [int(k.split(" r")[1]) for k in em.get("trials") or {}])
    if fn:
        add("tab 12 rats", fn.get("rats"))
        for b, per in (fn.get("power") or {}).items():
            for x in per:
                if x:
                    add("tab 12 power %s %s" % (b, x["region"]), x.get("rats"))
        for b, t in (fn.get("tiers") or {}).items():
            for k, v in t.items():
                add("tab 12 %s tier %s" % (b, k), v.get("rats"))
        for k, per in (fn.get("fooof") or {}).items():
            for x in per:
                add("tab 12 FOOOF %s %s" % (k, x["region"]), x.get("rats"))
        for x in fn.get("granger") or []:
            add("tab 12 Granger %s %s" % (E.PAIR_SAY[x["pair"]], x["band"]), x.get("rats"))
        for x in fn.get("pac") or []:
            add("tab 12 coupling %s" % x["region"], x.get("rats"))
        for r in fn.get("robust") or []:
            add("tab 12 leave-one-out", [x["rat"] for x in r.get("loo") or []])
    if pub_set:
        add("Joe's figures", pub_set.get("rats"))
    return out


def d5_sets(X):
    title = "Each set of rats holds the rats it says"
    how = ("Every list of rats in each set's results was read: tab 11's pairs in every phase, tab 12's regions, tiers, FOOOF, Granger and "
           "coupling, every leave-one-rat-out run, and the publication set. A set without J3 or J4 must not name them anywhere; "
           "all rats must hold all eight.")
    bad, rows = [], []
    for rs in _sets():
        em, fn = X.em(rs), X.fn(rs)
        ps = ((X.pub or {}).get("by_set") or {}).get(rs)
        if not em or not fn:
            bad.append("%s: tab 11 or 12 has no result" % E.RATSET_SAY[rs])
            continue
        drop = set(E.RATSET_DROP[rs])
        seen = _rats_in(em, fn, ps)
        leak = sorted({"%s (J%d)" % (w, r) for w, r in seen if r in drop})
        want = sorted(set(STUDY_RATS) - drop)
        top = sorted(em.get("rats") or [])
        named = sorted({r for _w, r in seen})
        rows.append([E.RATSET_SAY[rs], ", ".join("J%d" % r for r in top), len(seen), "none" if not leak else "%d" % len(leak)])
        if leak:
            bad.append("%s names a rat it leaves out: %s" % (E.RATSET_SAY[rs], "; ".join(leak[:6])))
        if top != want or fn.get("rats") != want or (ps and ps.get("rats") != want):
            bad.append("%s holds %s, not %s" % (E.RATSET_SAY[rs], top, want))
        if not set(named) <= set(want):
            bad.append("%s names rats outside the study: %s" % (E.RATSET_SAY[rs], sorted(set(named) - set(want))))
    table = {"head": ["Set", "Its rats", "Lists of rats read", "Left-out rats found"], "rows": rows}
    if bad:
        return _check("D5", "fail", title, how, "; ".join(bad) + ".", table=table)
    return _check("D5", "ok", title, how, "All four sets hold exactly their rats (all rats J3 to J11, eight), and no set without J3 or J4 "
                  "names them in any of the %d lists of rats read." % sum(r[2] for r in rows), table=table)


def d6_recordings(X):
    title = "The raw recordings are where the record says"
    how = ("For each rat-day, the session folder the manifest names (role SPC) was opened and its .ncs channel files counted and "
           "sized with os.stat (no file was read), then compared with the sizes the manifest recorded when it was made.")
    if not X.man:
        return _check("D6", "warn", title, how, "There is no manifest here, so the folders are not known.")
    rows, gone, differ, recs = [], [], [], []
    for rat in STUDY_RATS:
        for day in E.DAYS:
            d = X.day(rat, day) or {}
            f = next((x for x in d.get("folders") or [] if x.get("role") == "SPC"), None)
            if not f:
                gone.append("%s has no session folder in the manifest" % _rd(rat, day))
                continue
            want = {k: v for k, v in (f.get("files") or {}).items() if k.lower().endswith(".ncs")}
            folder = f.get("local") or ""
            if os.path.isdir(folder):
                have = {n: os.stat(os.path.join(folder, n)).st_size for n in os.listdir(folder) if n.lower().endswith(".ncs")}
                same = have == want
                if not same:
                    differ.append("%s: %d .ncs files here, %d recorded; %d sizes differ" % (
                        _rd(rat, day), len(have), len(want), sum(1 for k in want if have.get(k) != want[k])))
                rows.append([_rd(rat, day), len(have), "%.1f GB" % (sum(have.values()) / 1e9), "yes" if same else "no"])
                recs.append({"rat": rat, "day": day, "folder": folder, "files": len(have), "bytes": int(sum(have.values())), "on_disk": True,
                             "vacc": (f.get("remote") or {}).get("scratch")})
            else:
                gone.append("%s: %s cannot be opened here" % (_rd(rat, day), folder))
                rows.append([_rd(rat, day), len(want), "%.1f GB" % (sum(want.values()) / 1e9), "not here"])
                recs.append({"rat": rat, "day": day, "folder": folder, "files": len(want), "bytes": int(sum(want.values())), "on_disk": False,
                             "vacc": (f.get("remote") or {}).get("scratch")})
    X.recordings = recs
    tot = sum(r["bytes"] for r in recs)
    table = {"head": ["Rat-day", ".ncs files", "Size", "Sizes as recorded"], "rows": rows}
    detail = ["Each session also has its free-period recordings (FP1, FP2), which tab 8 reads for its comparisons with free periods."]
    if differ:
        return _check("D6", "fail", title, how, "Recordings differ from what the manifest recorded: %s." % "; ".join(differ), detail, table)
    if gone:
        vacc = sum(1 for r in recs if r["vacc"])
        return _check("D6", "warn", title, how, "%s. The drive may be unplugged; the VACC holds byte-identical copies of %d of these "
                      "folders (scratch, Jarvis Data/DEWEY)." % ("; ".join(gone), vacc), detail, table)
    return _check("D6", "ok", title, how, "All %d session folders are here, %d .ncs files, %.1f GB, every file the size the manifest "
                  "recorded." % (len(recs), sum(r["files"] for r in recs), tot / 1e9), detail, table)


def d7_freshness(X):
    title = "Each stage was made after the one it reads"
    how = ("Times compared: tab 8's and tab 11's day files (when written) against each set's tab 11 result (its \"at\"); tab 12's "
           "\"from\" against tab 11's \"at\"; the publication set (pub.json \"made\") against both; Joe's assembled site "
           "(joe_site/manifest.json \"made\") against the publication set. Measured before the check tools run, because "
           "check_joeexport.py assembles the site again.")
    out_of_order, rows, detail = [], [], []
    if not X.man:
        return _check("D7", "warn", title, how, "There is no manifest here.")
    j_t, e_t = [], []
    for rat in STUDY_RATS:
        for day in E.DAYS:
            d = X.day(rat, day)
            if not d:
                continue
            jp = joe._day_path(d, joe.day_key(d, X.names))
            if os.path.isfile(jp):
                j_t.append(_iso_mtime(jp))
                ep = E._day_path(d, E.day_key(d, jp))
                if os.path.isfile(ep):
                    e_t.append(_iso_mtime(ep))
    j_last, e_last = (max(j_t) if j_t else None), (max(e_t) if e_t else None)
    rows.append(["Tab 8 day files", "newest %s" % j_last, ""])
    rows.append(["Tab 11 day files", "newest %s" % e_last, "after tab 8's" if (e_last or "") >= (j_last or "") else "BEFORE tab 8's"])
    if (e_last or "") < (j_last or ""):
        out_of_order.append("tab 11's day files are older than tab 8's: work tab 11 out again")
    pub = X.pub or {}
    made = pub.get("made")
    for rs in _sets():
        em, fn = X.em(rs) or {}, X.fn(rs) or {}
        at, fat, frm = em.get("at"), fn.get("at"), fn.get("from")
        ok11 = at and (e_last or "") <= at and (j_last or "") <= at
        ok12 = frm == at and fat and fat >= (at or "")
        okp = made and made >= (fat or "") and made >= (at or "")
        rows.append(["Tab 11, %s" % E.RATSET_SAY[rs], at, "after the day files" if ok11 else "BEFORE the day files"])
        rows.append(["Tab 12, %s" % E.RATSET_SAY[rs], fat, "from tab 11's run" if ok12 else "NOT from tab 11's latest run (from %s)" % frm])
        if not ok11:
            out_of_order.append("%s: tab 11 is older than its day files (rerun python -m backend.evenmore build %s)" % (E.RATSET_SAY[rs], rs))
        if not ok12:
            out_of_order.append("%s: tab 12 was not made from tab 11's latest result (rerun python -m backend.finalstage %s)" % (E.RATSET_SAY[rs], rs))
        if not okp:
            out_of_order.append("%s: the publication set is older than tab 11 or 12 (rerun python -m backend.joepub)" % E.RATSET_SAY[rs])
    rows.append(["Publication set", made, ""])
    sp = os.path.join(os.path.dirname(os.path.dirname(_root())), "joe_site", "manifest.json")
    site = None
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8") as fh:
            site = json.load(fh).get("made")
    rows.append(["Joe's site, assembled", site or "not assembled here", "after the publication set" if site and made and site >= made else ""])
    if site and made and site < made:
        out_of_order.append("Joe's site was assembled before the publication set was last made (rerun python -m backend.joeexport site, then deploy)")
    J = joe.result() or {}
    detail.append("Tab 8's models (joe.json) were made %s; the manifest %s." % (J.get("at"), (X.man or {}).get("at")))
    newer = []
    for rel, stamp, what in (("backend/evenmore.py", min((X.em(rs) or {}).get("at") or "9" for rs in _sets()), "tab 11"),
                             ("backend/finalstage.py", min((X.fn(rs) or {}).get("at") or "9" for rs in _sets()), "tab 12"),
                             ("backend/joepub.py", made or "9", "the publication set"),
                             ("backend/joestats.py", made or "9", "the publication set")):
        p = os.path.join(APP, rel)
        if os.path.isfile(p) and _iso_mtime(p) > stamp:
            newer.append("%s (changed %s, after %s was made)" % (rel, _iso_mtime(p), what))
    if newer:
        detail.append("Code changed after the results it makes: %s. A rebuild may change figures or words; the refits (L2) say whether "
                      "the numbers change." % "; ".join(newer))
    table = {"head": ["Stage", "Made", "In order"], "rows": rows}
    if out_of_order:
        return _check("D7", "warn", title, how, "Out of order: %s." % "; ".join(out_of_order), detail, table)
    return _check("D7", "ok", title, how, "Every stage was made after the one it reads: day files (newest %s), tab 11 and 12 for all four "
                  "sets, the publication set (%s) and Joe's site (%s)." % (e_last, made, site), detail, table)


# --------------------------------------------------------------------------
# The right logic was applied
# --------------------------------------------------------------------------
def _run_tool(name, check=None):
    """One check tool as its own process, its output to a file (a pipe
    nobody reads stops a chatty process), stoppable between polls."""
    os.makedirs(_root("logs"), exist_ok=True)
    log = _root("logs", name.replace(".py", ".txt"))
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen([sys.executable, os.path.join(APP, "tools", name)], cwd=APP, env=env, stdout=fh, stderr=subprocess.STDOUT)
        try:
            while p.poll() is None:
                if check:
                    check()
                if time.time() - t0 > TOOL_TIMEOUT:
                    p.kill()
                    p.wait()
                    break
                time.sleep(0.5)
        except BaseException:
            p.kill()
            p.wait()
            raise
    with open(log, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return {"code": p.returncode, "text": text, "seconds": time.time() - t0, "log": log, "timed_out": time.time() - t0 > TOOL_TIMEOUT}


def l1_tools(X, check=None):
    title = "The three check tools pass"
    how = ("tools/check_evenmore.py (tab 11: its arithmetic against independent code, its saved result against itself), "
           "tools/check_final.py (tab 12: its measures on planted signals, its result against itself) and tools/check_joeexport.py "
           "(Joe's export and site: every figure, statistics PDF, star and file) were each run as their own process from the app "
           "folder, up to 30 minutes each.")
    if X.quick:
        return _check("L1", "info", title, how, "Not run in the quick pass: the three tools take minutes. The full pass runs them.")
    rows, failed, broken, detail = [], [], [], []
    for name in TOOLS:
        got = _run_tool(name, check)
        X.tool_out[name] = got
        m = re.findall(r"(\d+) passed, (\d+) failed", got["text"])
        if got["timed_out"]:
            broken.append("%s ran past 30 minutes and was stopped" % name)
            rows.append([name, "", "", "%.0f s" % got["seconds"], "stopped"])
            continue
        if not m:
            tail = [ln for ln in got["text"].splitlines() if ln.strip()][-1:] or ["no output"]
            broken.append("%s ended without its count (exit %s: %s)" % (name, got["code"], tail[0]))
            rows.append([name, "", "", "%.0f s" % got["seconds"], "no count"])
            continue
        ok, bad = int(m[-1][0]), int(m[-1][1])
        rows.append([name, ok, bad, "%.0f s" % got["seconds"], "OK" if bad == 0 else "Problem"])
        for ln in got["text"].splitlines():
            if ln.strip().startswith("FAIL"):
                failed.append("%s: %s" % (name, ln.strip()[4:].strip()))
    detail += failed
    detail.append("Their output is kept in %s." % _root("logs"))
    table = {"head": ["Tool", "Passed", "Failed", "Took", "Result"], "rows": rows}
    tot_ok = sum(r[1] for r in rows if isinstance(r[1], int))
    tot_bad = sum(r[2] for r in rows if isinstance(r[2], int))
    if tot_bad:
        return _check("L1", "fail", title, how, "%d passed, %d failed: %s." % (tot_ok, tot_bad, "; ".join(f.split("   ")[0] for f in failed)),
                      detail, table)
    if broken:
        return _check("L1", "warn", title, how, "%d passed; %s." % (tot_ok, "; ".join(broken)), detail, table)
    return _check("L1", "ok", title, how, "%d passed, 0 failed across the three tools." % tot_ok, detail, table)


def _refit_set(X, rs):
    """Every pair's Late vs Early (phase 1) and Session x Period (phase 3),
    and every region's tier-3a Session x Period, fitted again from the row
    builders as the tabs fit them. [(what, stored, refit)]"""
    em, fn = X.em(rs), X.fn(rs)
    T, PT = X.T(rs), X.PT(rs)
    out = []
    for bid, _lo, _hi in E.BANDS:
        B = next(b for b in em["bands"] if b["band"] == bid)
        keep, rows, _rb = E.rows_phase1(T, bid)
        df = E._frame(rows)
        for p in range(len(E.PAIRS)):
            st = (B["phase1"]["pairs"][p] or {}).get("a2")
            if p not in keep:
                out.append(("%s %s Late vs Early" % (bid, E.PAIR_SAY[p]), st, None))
                continue
            sub = df[df["pair"] == "p%02d" % p]
            got, _err = E._safe(lambda: E.ratio(E.gee(sub, "y ~ C(day, Treatment('Precon1'))"), "Precon4"))
            out.append(("%s %s Late vs Early" % (bid, E.PAIR_SAY[p]), st, got))
        keep, rows = E.rows_phase3(T, bid)
        df = E._frame(rows)
        for p in range(len(E.PAIRS)):
            st = (B["phase3"]["pairs"][p] or {}).get("sp")
            if p not in keep:
                out.append(("%s %s Session × Period" % (bid, E.PAIR_SAY[p]), st, None))
                continue
            sub = df[df["pair"] == "p%02d" % p]
            ts, _err = E._safe(lambda: E.terms(E.gee(sub, "y ~ C(day, Sum) * C(period, Sum)")))
            out.append(("%s %s Session × Period" % (bid, E.PAIR_SAY[p]), st, next((t for t in ts or [] if t["term"] == "Session × Period"), None)))
        for ri, r in enumerate(FS.REGIONS):
            x = next((z for z in fn["power"][bid] if z and z["region"] == r), None)
            st = (x or {}).get("sp")
            rats = FS.region_rats(PT, ri)
            if len(rats) < E.MIN_RATS:
                out.append(("%s power %s Session × Period" % (bid, FS.REGION_SAY[r]), st, None))
                continue
            rows, _rb = FS.power_rows(PT, bid, ri, rats)
            ts, _err = E._safe(lambda: E.terms(E.gee(E._frame(rows), "y ~ C(day, Sum) * C(period, Sum)", "normal")))
            out.append(("%s power %s Session × Period" % (bid, FS.REGION_SAY[r]), st, next((t for t in ts or [] if t["term"] == "Session × Period"), None)))
    return out


def l2_refits(X, check=None):
    title = "The key tests come out the same when fitted again"
    how = ("For every set of rats, the rows were built again from tab 11's pooled rat-days with the tabs' own row builders "
           "(evenmore.rows_phase1, rows_phase3, finalstage.power_rows) and each model fitted again with the same GEE: every pair's "
           "Late vs Early (phase 1), every pair's Session × Period (baseline, cue 1, cue 2), every region's tier-3a Session × Period "
           "(power, normal family). Wald chi-square and p compared with the stored ones, to a relative 1e-8.")
    if not X.every:
        return _check("L2", "warn", title, how, "Tab 11's pooled rat-days are not here, so nothing could be fitted again.")
    n = n_ok = 0
    worst, bad, rows = 0.0, [], []
    for rs in _sets():
        if not X.em(rs) or not X.fn(rs):
            bad.append("%s: tab 11 or 12 has no result" % E.RATSET_SAY[rs])
            continue
        k = k_ok = 0
        for what, st, got in _refit_set(X, rs):
            if check:
                check()
            if st is None and got is None:
                continue
            k += 1
            same = bool(st and got) and _same(st.get("chi2"), got.get("chi2")) and _same(st.get("p"), got.get("p"))
            if st and got and st.get("chi2") and got.get("chi2"):
                worst = max(worst, abs(st["chi2"] - got["chi2"]) / max(abs(st["chi2"]), 1e-300))
            if same:
                k_ok += 1
            else:
                bad.append("%s, %s: stored %s, fitted again %s" % (E.RATSET_SAY[rs], what,
                                                                  "χ² %.6g p %.6g" % (st["chi2"], st["p"]) if st and st.get("p") is not None else "none",
                                                                  "χ² %.6g p %.6g" % (got["chi2"], got["p"]) if got and got.get("p") is not None else "none"))
        rows.append([E.RATSET_SAY[rs], k, k_ok, k - k_ok])
        n += k
        n_ok += k_ok
    table = {"head": ["Set", "Tests fitted again", "Same", "Different"], "rows": rows}
    detail = ["Largest relative difference in chi-square: %.1e." % worst]
    if bad:
        return _check("L2", "fail", title, how, "%d of %d tests came out the same; different: %s." % (n_ok, n, "; ".join(bad[:8])),
                      detail + bad[8:], table)
    return _check("L2", "ok", title, how, "All %d tests fitted again came out the same (largest relative difference in chi-square %.1e)."
                  % (n, worst), detail, table)


def _fdr_families(em, fn):
    """[(family, [(stored p, stored q)])], every corrected family as the tabs
    correct it, in the tabs' own order (None where a test is missing)."""
    fams = []
    for B in em["bands"]:
        b = B["band"]
        P1, P2, P3 = B["phase1"]["pairs"], B["phase2"]["pairs"], B["phase3"]["pairs"]
        fams.append(("tab 11 %s Late vs Early, ten pairs" % b, [((x or {}).get("a2") or {}).get("p") if x else None for x in P1],
                     [((x or {}).get("a2") or {}).get("q") if x else None for x in P1]))
        fams.append(("tab 11 %s Session × Frequency, ten pairs" % b, [E._term_p(x.get("b2"), "Session × Frequency") if x and x.get("b2") else None for x in P1],
                     [x.get("b2_q") if x else None for x in P1]))
        fams.append(("tab 11 %s Session × Cue, ten pairs" % b, [E._term_p(x.get("terms"), "Session × Cue") if x and x.get("terms") else None for x in P2],
                     [x.get("q") if x else None for x in P2]))
        for d in E.DAYS:
            fams.append(("tab 11 %s cue 2 vs cue 1 in %s, ten pairs" % (b, d), [((x or {}).get("days") or {}).get(d, {}).get("p") if x else None for x in P2],
                         [((x or {}).get("days") or {}).get(d, {}).get("q") if x else None for x in P2]))
        fams.append(("tab 11 %s Session × Period, ten pairs" % b, [((x or {}).get("sp") or {}).get("p") if x else None for x in P3],
                     [((x or {}).get("sp") or {}).get("q") if x else None for x in P3]))
        for a, c, say in E.CONTRASTS:
            k = E.contrast_key(a, c)
            fams.append(("tab 11 %s Session × (%s), ten pairs" % (b, say.lower()), [((x or {}).get("contrasts") or {}).get(k, {}).get("p") if x else None for x in P3],
                         [((x or {}).get("contrasts") or {}).get(k, {}).get("q") if x else None for x in P3]))
    per = [x for b in ("theta", "gamma") for x in fn["power"].get(b) or []]
    fams.append(("tab 12 tier 3a Session × Period, ten region models", [((x or {}).get("sp") or {}).get("p") if x else None for x in per],
                 [((x or {}).get("sp") or {}).get("q") if x else None for x in per]))
    fams.append(("tab 12 tier 3b Session × Period × Frequency, ten region models", [((x or {}).get("spf") or {}).get("p") if x else None for x in per],
                 [((x or {}).get("spf") or {}).get("q") if x else None for x in per]))
    for a, c, say in E.CONTRASTS:
        k = E.contrast_key(a, c)
        fams.append(("tab 12 tier 3a Session × (%s), ten region models" % say.lower(), [((x or {}).get("contrasts") or {}).get(k, {}).get("p") if x else None for x in per],
                     [((x or {}).get("contrasts") or {}).get(k, {}).get("q") if x else None for x in per]))
    for key, say, _u in FS.FOOOF_PARAMS:
        xs = fn["fooof"].get(key) or []
        fams.append(("tab 12 FOOOF %s Session × Period, five regions" % say.lower(), [((x or {}).get("sp") or {}).get("p") for x in xs],
                     [((x or {}).get("sp") or {}).get("q") for x in xs]))
    for tier, keys in (("t1", FS.TIER1_KEYS), ("t2", FS.TIER2_KEYS)):
        for name, _h, _x in keys:
            xs = [fn["tiers"][b][tier]["key"][name] for b in ("theta", "gamma") if b in fn.get("tiers") or {}]
            fams.append(("tab 12 tier %s %s, two bands" % (tier[1], name), [x.get("p") for x in xs], [x.get("q") for x in xs]))
            fams.append(("tab 12 tier %s %s (mixed model), two bands" % (tier[1], name), [(x.get("lmm") or {}).get("p") for x in xs],
                         [(x.get("lmm") or {}).get("q") for x in xs]))
    G = [x for x in fn.get("granger") or [] if (x.get("in") or {}).get("fdr") and "error" not in x]
    for k, say in (("ab", "first to second"), ("ba", "second to first"), ("sd", "Session × Direction")):
        fams.append(("tab 12 Granger %s, the corrected hits" % say, [(x.get(k) or {}).get("p") for x in G], [(x.get(k) or {}).get("q") for x in G]))
    M = [x for x in fn.get("pac") or [] if (x.get("in") or {}).get("fdr") and "le" in x]
    fams.append(("tab 12 coupling Late vs Early, the corrected hits", [(x.get("le") or {}).get("p") for x in M], [(x.get("le") or {}).get("q") for x in M]))
    return fams


def l3_fdr(X):
    title = "The FDR correction is Benjamini-Hochberg over the right families"
    how = ("For every set, each corrected family was rebuilt from the stored p values (tab 11: each test across the ten pairs; tab 12: "
           "tier 3 across the ten per-region models, FOOOF across the five regions, tiers 1 and 2 across the two bands, Granger and "
           "coupling across their corrected hits) and Benjamini-Hochberg applied again (evenmore.bh); every q compared with the stored q.")
    n_f = n_q = 0
    bad, rows = [], []
    for rs in _sets():
        em, fn = X.em(rs), X.fn(rs)
        if not em or not fn:
            bad.append("%s: tab 11 or 12 has no result" % E.RATSET_SAY[rs])
            continue
        k_f = k_q = k_bad = 0
        for fam, ps, qs in _fdr_families(em, fn):
            if not any(p is not None for p in ps):
                continue
            k_f += 1
            for i, (want, have) in enumerate(zip(E.bh(ps), qs)):
                if ps[i] is None:
                    continue
                k_q += 1
                if not _same(want, have, 1e-12):
                    k_bad += 1
                    bad.append("%s, %s, test %d: q %s stored, %s worked out again" % (E.RATSET_SAY[rs], fam, i + 1, have, want))
        rows.append([E.RATSET_SAY[rs], k_f, k_q, k_bad])
        n_f += k_f
        n_q += k_q
    table = {"head": ["Set", "Families", "q values", "Different"], "rows": rows}
    if bad:
        return _check("L3", "fail", title, how, "%d of %d q values differ: %s." % (len(bad), n_q, "; ".join(bad[:6])), bad[6:], table)
    return _check("L3", "ok", title, how, "All %d q values in %d families, over the four sets, are Benjamini-Hochberg of their family's "
                  "stored p values." % (n_q, n_f), table=table)


def l4_figures(X):
    title = "Every figure's stars and statistics PDF match its tests"
    how = ("For every figure of every set in the publication set: its statistics PDF is on disk and prints each main test's Wald "
           "chi-square and p as the site lists it (read with PyMuPDF); an asterisk appears in the figure only when one of its tests "
           "passes under that reading (corrected, or uncorrected for the second drawing), and always when its main test passes "
           "(the rule tools/check_joeexport.py applies to all rats, applied here to every set).")
    from . import monolith as MO
    pub = X.pub
    if not pub:
        return _check("L4", "warn", title, how, "The publication set (pub.json) is not here.")
    rows, nostats, unprinted, stray, missing = [], [], [], [], []
    n_fig = n_pdf = n_prim = 0
    for rs in _sets():
        figs = _figures(pub, rs)
        k_bad = 0
        for f in figs:
            n_fig += 1
            if not f.get("stats") or not os.path.isfile(MO._path("joepub", rs, f["stats"])):
                nostats.append("%s %s" % (rs, f["id"]))
                k_bad += 1
                continue
            t = _text_of_pdf(MO._path("joepub", rs, f["stats"]))
            for x in [x for x in f.get("tests") or [] if x.get("primary")]:
                n_prim += 1
                m = re.search(r"χ²\((\d+)\) = ([\d.]+), (p [<>=] [.\d]+|p not estimable)", x["stat"])
                pc = m.group(3)
                pc = pc[4:] if pc.startswith("p = ") else pc[2:] if pc.startswith("p ") else pc
                if not m or m.group(2) not in t or pc not in t:
                    unprinted.append("%s %s: %s" % (rs, f["id"], x["name"]))
                    k_bad += 1
            for mode, name in (("fdr", f.get("pdf")), ("raw", f.get("pdf_raw"))):
                if not name:
                    continue
                n_pdf += 1
                ft = _text_of_pdf(MO._path("joepub", rs, name))
                star = "*" in ft
                any_pass = any((x.get("pass") or {}).get(mode) for x in f.get("tests") or [])
                prim_pass = any((x.get("pass") or {}).get(mode) for x in f.get("tests") or [] if x.get("primary"))
                if star and not any_pass:
                    stray.append("%s %s (%s)" % (rs, f["id"], "corrected" if mode == "fdr" else "uncorrected"))
                    k_bad += 1
                if f["kind"] in STAR_KINDS and prim_pass and not star:
                    missing.append("%s %s (%s)" % (rs, f["id"], "corrected" if mode == "fdr" else "uncorrected"))
                    k_bad += 1
        rows.append([E.RATSET_SAY[rs], len(figs), k_bad])
    detail = []
    tj = X.tool_out.get("check_joeexport.py")
    if tj:
        line = next((ln.strip() for ln in tj["text"].splitlines() if "a star only where" in ln), None)
        if line:
            detail.append("check_joeexport.py, all rats: %s" % line)
    table = {"head": ["Set", "Figures", "Problems"], "rows": rows}
    probs = (["no statistics PDF: " + ", ".join(nostats)] if nostats else []) + \
            (["a main test not printed in its PDF: " + "; ".join(unprinted)] if unprinted else []) + \
            (["a star with no passing test: " + ", ".join(stray)] if stray else []) + \
            (["no star although the main test passes: " + ", ".join(missing)] if missing else [])
    if probs:
        return _check("L4", "fail", title, how, "; ".join(probs) + ".", detail, table)
    return _check("L4", "ok", title, how, "%d figures over four sets: every statistics PDF is there and prints all %d main tests; %d "
                  "drawings read, each starred exactly as its tests say." % (n_fig, n_prim, n_pdf), detail, table)


def l5_standalone(X):
    title = "Tab 8 agrees with the standalone script"
    how = ("Read from tab 8's result (joe.json, \"agreement\"): tools/joe_standalone.py, which uses only NumPy and SciPy and reads the "
           "recordings itself, was compared with tab 8's exported tables cell by cell.")
    J = joe.result()
    ag = (J or {}).get("agreement")
    if not ag:
        return _check("L5", "info", title, how, "No comparison is recorded: the standalone script has not been run against tab 8 here.")
    files = ag.get("files") or []
    cells = sum(f.get("cells") or 0 for f in files)
    worst = max([f.get("worst") or 0 for f in files] or [0])
    where = "on the VACC (job %s)" % ag.get("slurm_id") if ag.get("where") == "vacc" else "here"
    detail = ["Tab 8's models were made %s; the comparison is worked out again each time tab 8 is, against the script's output of %s."
              % ((J or {}).get("at"), ag.get("ran_at")),
              "Tab 8 feeds tabs 11 and 12 its trials and the wire each window used; their spectra and models are checked by L1 to L3."]
    bad = [f["file"] for f in files if not f.get("ok")]
    if not ag.get("ok"):
        return _check("L5", "warn", title, how, "The script disagrees in %d of %d tables: %s." % (len(bad), len(files), ", ".join(bad[:8])), detail)
    return _check("L5", "ok", title, how, "Run %s on %s: all %d tables, %s cells, agree to %g (largest difference %g)."
                  % (where, str(ag.get("ran_at"))[:10], len(files), "{:,}".format(cells), ag.get("tol"), worst), detail)


def l6_head_bumps(X):
    title = "Head bumps were removed as the methods say"
    how = ("joepub.saturation_counts() was run: for every region and side in every 10-s window of every trial, which wire tab 8 used "
           "against the wires excluded by hand in that window. The totals were compared with the methods' head-bump paragraph.")
    rows = X.sat
    if not rows:
        return _check("L6", "warn", title, how, "Tab 8's day files are not here, so nothing could be counted.")
    tab = []
    for x in rows:
        tab.append([_rd(x["rat"], x["day"]), x["trials"], x["windows"], x["replaced"], x["omitted"],
                    "%.1f%%" % (100.0 * x["segments_lost"] / x["segments"]) if x["segments"] else "0%",
                    "yes" if x["replaced_hand"] == x["replaced"] and x["omitted_hand"] == x["omitted"] else "no"])
    tw, rp, om = sum(x["windows"] for x in rows), sum(x["replaced"] for x in rows), sum(x["omitted"] for x in rows)
    rh, oh = sum(x["replaced_hand"] for x in rows), sum(x["omitted_hand"] for x in rows)
    all_hand = rh == rp and oh == om
    meth = " ".join(p for s in (X.pub or {}).get("methods") or [] if s["title"] == "Artefacts from head bumps" for p in s["paras"])
    says_all = "Every replacement and every omission followed a hand exclusion" in meth
    agree = bool(meth) and (says_all == all_hand) and ("{:,}".format(om) in meth) and ("{:,}".format(rp) in meth)
    table = {"head": ["Rat-day", "Trials", "Region-windows", "Replaced wire", "Omitted", "Segments lost", "All after a hand exclusion"],
             "rows": tab}
    res = ("%s region-windows: %s used a replacement wire and %s were omitted; %s." % (
        "{:,}".format(tw), "{:,}".format(rp), "{:,}".format(om),
        "every replacement and omission followed a hand exclusion" if all_hand else
        "%s of the replacements and %s of the omissions followed a hand exclusion, the rest automatic saturation detection"
        % ("{:,}".format(rh), "{:,}".format(oh))))
    if not agree:
        return _check("L6", "warn", title, how, res + " The methods' head-bump paragraph does not state these numbers (%s)."
                      % ("it is missing" if not meth else "made before the last change"), table=table)
    return _check("L6", "ok", title, how, res + " The methods state the same.", table=table)


# --------------------------------------------------------------------------
# The words match the numbers
# --------------------------------------------------------------------------
def _figure_texts(f):
    out = [f.get("title"), f.get("name"), f.get("caption"), f.get("caption_raw"), f.get("note")]
    out += list(f.get("results") or []) + list(f.get("sensitivity") or [])
    for t in f.get("tests") or []:
        out += [t.get("name"), t.get("effect"), t.get("stat")]
    return [x for x in out if isinstance(x, str)]


def _internal_names(text):
    """Jarvis's own names in a text, not counting a plain English word that
    opens a sentence ("Coupling was measured")."""
    hits = []
    for m in INTERNAL.finditer(text):
        start = text[:m.start()].rstrip()
        if m.group(1) in INTERNAL_ENGLISH and (not start or start[-1] in ".:;"):
            continue
        hits.append(m.group(1))
    return hits


def w1_names(X):
    title = "No internal names, no missing values, no ellipsis"
    how = ("Every paragraph of the methods and every text of every figure in the publication set (title, caption, methods note, "
           "results, sensitivity, each test) was searched for Jarvis's names for its steps (Spark, Coupling, Circuit, Drift, "
           "Monolith, Jarvis; a sentence opening with the English word is allowed), for None, nan and inf, and for an ellipsis.")
    pub = X.pub
    if not pub:
        return _check("W1", "warn", title, how, "The publication set (pub.json) is not here.")
    texts = [("methods, %s" % s["title"], p) for s in pub.get("methods") or [] for p in s["paras"]]
    for rs in _sets():
        for f in _figures(pub, rs):
            texts += [("%s %s" % (rs, f["id"]), t) for t in _figure_texts(f)]
    found = []
    for where, t in texts:
        for nm in _internal_names(t):
            found.append("%s: %s" % (where, nm))
        for m in re.finditer(r"\b(None|nan|NaN|inf|Inf|Infinity)\b", t):
            found.append("%s: %s" % (where, m.group(1)))
        if "..." in t or "…" in t:
            found.append("%s: an ellipsis" % where)
    detail = []
    stats_pdf = next((f for f in _figures(pub, "all") if f.get("stats")), None)
    if stats_pdf:
        from . import monolith as MO
        p = MO._path("joepub", "all", stats_pdf["stats"])
        if os.path.isfile(p) and "Jarvis" in _text_of_pdf(p):
            detail.append("The statistics PDFs name Jarvis in their source line (\"statistics from Jarvis tabs 11 and 12\"): provenance "
                          "for Joe, not words for the dissertation.")
    if found:
        return _check("W1", "fail", title, how, "%d found in %d texts: %s." % (len(found), len(texts), "; ".join(found[:8])), detail + found[8:])
    return _check("W1", "ok", title, how, "None found in %s (the methods and every figure of the four sets)." % _plural(len(texts), "text"), detail)


DIR_RE = re.compile(r"(higher|lower|larger|smaller) in Late (?:than|as) in Early")
EST_RE = re.compile(r"(?:ratio Late/Early|ratio)\s*=\s*([0-9]*\.?[0-9]+)|(?:Late − Early|difference)\s*=\s*([−+-]?[0-9]*\.?[0-9]+)")
STOP_RE = re.compile(r"did not differ|was not significant|\.\s+(?=[A-Z])")
SESSION_RE = re.compile(r"Session(?:,| \()\s*χ²\(1\) = [0-9.]+, p [<>=] [0-9.]+(?:, FDR q [<>=] [0-9.]+)?, "
                        r"(?:ratio Late/Early = ([0-9.]+)|Late − Early = ([−+-]?[0-9.]+))")


def _num(s):
    return float(s.replace("−", "-"))


def _directions(text):
    """Each direction word in a paragraph and the estimates in its reach:
    [(word, [(value, is_ratio)], sentence)]."""
    ms = list(DIR_RE.finditer(text))
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        st = STOP_RE.search(text, m.end(), end)
        span = text[m.end():st.start() if st else end]
        ests = [(float(r), True) if r else (_num(d), False) for r, d in EST_RE.findall(span)]
        out.append((m.group(1), ests, text[max(0, m.start() - 80):m.end() + 60]))
    return out


def w2_directions(X):
    title = "Every higher or lower says what its estimate says"
    how = ("In every results paragraph of every figure and set, each \"higher/lower (or larger/smaller) in Late than in Early\" was "
           "matched with the estimates that follow it (a ratio Late/Early above or below 1, a Late − Early difference above or below 0). "
           "A summary sentence with no estimate of its own was matched with its paragraph's Session effect.")
    pub = X.pub
    if not pub:
        return _check("W2", "warn", title, how, "The publication set (pub.json) is not here.")
    own = by_session = loose = 0
    wrong = []
    for rs in _sets():
        for f in _figures(pub, rs):
            for para in f.get("results") or []:
                for word, ests, ctx in _directions(para):
                    up = word in ("higher", "larger")
                    if ests:
                        own += 1
                        for v, is_ratio in ests:
                            if (v > 1 if is_ratio else v > 0) != up:
                                wrong.append("%s %s: \"%s\" but %s %g" % (rs, f["id"], word, "ratio" if is_ratio else "difference", v))
                        continue
                    m = SESSION_RE.search(" ".join(f.get("results") or []))
                    if not m:
                        loose += 1
                        continue
                    by_session += 1
                    v, is_ratio = (float(m.group(1)), True) if m.group(1) else (_num(m.group(2)), False)
                    if (v > 1 if is_ratio else v > 0) != up:
                        wrong.append("%s %s: \"%s\" but the Session effect is %g" % (rs, f["id"], word, v))
    n = own + by_session + loose
    res = ("%d direction words: %d checked against the estimates beside them, %d against their paragraph's Session effect%s"
           % (n, own, by_session, ", %d with no estimate found" % loose if loose else ""))
    if wrong:
        return _check("W2", "fail", title, how, res + "; %d disagree: %s." % (len(wrong), "; ".join(wrong[:6])), wrong[6:])
    if loose:
        return _check("W2", "warn", title, how, res + "; none disagrees, but %d could not be checked." % loose)
    return _check("W2", "ok", title, how, res + "; every one agrees.")


def w3_primary_in_text(X):
    title = "Every main test is stated in its figure's results"
    how = ("For every figure of every set, each main (primary) test the site lists, its chi-square with its df and its p exactly as "
           "printed there, was looked for in that figure's results paragraph.")
    pub = X.pub
    if not pub:
        return _check("W3", "warn", title, how, "The publication set (pub.json) is not here.")
    n = 0
    miss = []
    for rs in _sets():
        for f in _figures(pub, rs):
            text = " ".join(f.get("results") or [])
            for x in [x for x in f.get("tests") or [] if x.get("primary")]:
                n += 1
                m = re.search(r"Wald (χ²\(\d+\) = [\d.]+, (?:p [<>=] [.\d]+|p not estimable))", x["stat"])
                if not m or m.group(1) not in text:
                    miss.append("%s %s: %s (%s)" % (rs, f["id"], x["name"], x["stat"]))
    if miss:
        return _check("W3", "fail", title, how, "%d of %d main tests are not stated in their results: %s." % (len(miss), n, "; ".join(miss[:6])), miss[6:])
    return _check("W3", "ok", title, how, "All %d main tests, over the four sets, are stated in their figure's results with the same "
                  "chi-square and p." % n)


def _expected_rats(f, em, fn):
    """The rats a figure's statistics rest on, from tabs 11 and 12's own lists."""
    k, band = f["kind"], f.get("band")
    if k in PAIR_KINDS + ("p1pool", "p2pool", "p3pool"):
        B = next(b for b in em["bands"] if b["band"] == band)
        ph = "phase%s" % k[1]
        if k in PAIR_KINDS:
            return set((B[ph]["pairs"][f["pair"]] or {}).get("rats") or [])
        return {r for x in B[ph]["pairs"] if x for r in x.get("rats") or []}
    if k == "power":
        return set(next(x for x in fn["power"][band] if x and x["region"] == f["region"])["rats"])
    if k == "powerall":
        return {r for t in fn["tiers"][band].values() for r in t.get("rats") or []}
    if k == "fooof":
        return {r for xs in fn["fooof"].values() for x in xs if not x.get("error") and x.get("terms") for r in x.get("rats") or []}
    if k == "granger":
        return set(next(x for x in fn["granger"] if x["pair"] == f["pair"] and x["band"] == band)["rats"])
    if k == "pac":
        return set(next(x for x in fn["pac"] if x["region"] == f["region"])["rats"])
    return None


def w4_rat_counts(X):
    title = "Every \"data are from N rats\" counts the right rats"
    how = ("For every figure of every set, the number of rats its results paragraph and caption state (\"Data are from N rats\", "
           "\"n = N rats\") was compared with the rats tabs 11 and 12 fitted for that figure's pair, region or model, which must also "
           "lie within its set.")
    pub = X.pub
    if not pub:
        return _check("W4", "warn", title, how, "The publication set (pub.json) is not here.")
    n = 0
    bad = []
    for rs in _sets():
        em, fn = X.em(rs), X.fn(rs)
        if not em or not fn:
            bad.append("%s: tab 11 or 12 has no result" % E.RATSET_SAY[rs])
            continue
        allowed = set(STUDY_RATS) - set(E.RATSET_DROP[rs])
        for f in _figures(pub, rs):
            want = _expected_rats(f, em, fn)
            if want is None:
                continue
            said = [int(v) for t in [(f.get("results") or [""])[0], f.get("caption") or ""]
                    for v in re.findall(r"(?:Data are from|n =) (\d+) rats", t)]
            n += len(said)
            if any(v != len(want) for v in said) or not want <= allowed:
                bad.append("%s %s: says %s, tabs 11 and 12 fitted %d (%s)" % (rs, f["id"], ", ".join(str(v) for v in said), len(want),
                                                                            ", ".join("J%d" % r for r in sorted(want))))
    if bad:
        return _check("W4", "fail", title, how, "%d of the stated counts are wrong: %s." % (len(bad), "; ".join(bad[:6])), bad[6:])
    return _check("W4", "ok", title, how, "All %d stated counts of rats, over the four sets, are the number of rats fitted." % n)


def _placeholders(texts):
    return [(w, m.group(0)) for w, t in texts for m in re.finditer(r"\[[^\]]*[A-Za-z]{3,}[^\]]*\]", t) if "CI" not in m.group(0)]


def w5_placeholders(X):
    title = "Placeholders Joe must still fill"
    how = "Every bracketed note in the methods (and in any figure's words) that asks for something to be added or confirmed was listed."
    pub = X.pub
    if not pub:
        return _check("W5", "warn", title, how, "The publication set (pub.json) is not here.")
    texts = [("methods, %s" % s["title"], p) for s in pub.get("methods") or [] for p in s["paras"]]
    for rs in _sets():
        for f in _figures(pub, rs):
            texts += [("%s %s" % (rs, f["id"]), t) for t in _figure_texts(f)]
    found = _placeholders(texts)
    X.placeholders = found
    if found:
        return _check("W5", "warn", title, how, "%s to fill: %s." % (_plural(len(found), "placeholder"), "; ".join("%s (%s)" % (p, w) for w, p in found)))
    return _check("W5", "ok", title, how, "None: the methods and the figures have no bracketed placeholder left.")


# --------------------------------------------------------------------------
# It can be made again from the raw data
# --------------------------------------------------------------------------
def _git(*args):
    got = subprocess.run(["git"] + list(args), cwd=APP, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if got.returncode != 0:
        raise RuntimeError(got.stderr.strip() or "git %s failed" % args[0])
    return got.stdout


def r1_code(X):
    title = "The code that made it is in the repository"
    how = ("git rev-parse HEAD for the commit; git status --porcelain for backend and tools, every changed or untracked file sorted "
           "by whether it makes a number or a word Joe is sent.")
    try:
        head = _git("rev-parse", "HEAD").strip()
        lines = [ln for ln in _git("status", "--porcelain", "--untracked-files=all", "--", "backend", "tools").splitlines() if ln.strip()]
    except Exception as exc:                                  # noqa: BLE001
        X.code = {"commit": None, "dirty": []}
        return _check("R1", "warn", title, how, "git could not be asked here (%s)." % exc)
    affect, other = [], []
    for ln in lines:
        st, path = ln[:2], ln[3:].strip().strip('"')
        rel = path.split("_Jarvis/app/", 1)[-1]
        say = "%s (%s)" % (rel, "not in the repository at all" if st.strip() == "??" else "changed")
        (affect if rel in RESULT_CODE else other).append((rel, say))
    X.code = {"commit": head, "dirty": [r for r, _s in affect]}
    detail = ["Commit %s." % head]
    if other:
        detail.append("Also changed, not used to make Joe's numbers: %s." % ", ".join(s for _r, s in other))
    if affect:
        return _check("R1", "warn", title, how, "These changes are not committed: %s. Someone rebuilding from the repository would not get "
                      "these numbers and words." % "; ".join(s for _r, s in affect), detail)
    return _check("R1", "ok", title, how, "Everything that makes Joe's numbers is committed at %s." % head[:10], detail)


def r2_versions(X):
    title = "The software versions are recorded"
    how = "The versions of Python and each library the analysis imports, read here (joepub._versions()) and from pub.json."
    now = JP._versions()
    X.versions = now
    was = (X.pub or {}).get("versions") or {}
    differ = ["%s %s then, %s now" % (k, was[k], now.get(k)) for k in sorted(was) if was.get(k) != now.get(k)]
    say = ", ".join("%s %s" % (k, v) for k, v in now.items())
    if differ:
        return _check("R2", "warn", title, how, "Recorded: %s. The publication set was made with other versions: %s." % (say, "; ".join(differ)))
    return _check("R2", "info", title, how, "Recorded: %s; the publication set was made with the same." % say)


def r3_determinism(X):
    title = "The same data give the same numbers"
    how = ("One GEE (all rats, theta, the first pair, Late vs Early) fitted twice and compared bit for bit, then fitted with its rows "
           "shuffled; the code of tabs 11 and 12 and the publication set was searched for random draws.")
    if not X.every:
        return _check("R3", "warn", title, how, "Tab 11's pooled rat-days are not here.")
    keep, rows, _rb = E.rows_phase1(X.T("all"), "theta")
    df = E._frame(rows)
    sub = df[df["pair"] == "p%02d" % keep[0]]
    f = "y ~ C(day, Treatment('Precon1'))"
    a, b = E.gee(sub, f), E.gee(sub, f)
    same = (np.asarray(a.params).tobytes() == np.asarray(b.params).tobytes()
            and np.asarray(a.cov_robust_bc).tobytes() == np.asarray(b.cov_robust_bc).tobytes())
    sh = sub.sample(frac=1.0, random_state=np.random.RandomState(0))
    ra, rb = E.ratio(a, "Precon4"), E.ratio(E.gee(sh, f), "Precon4")
    rel = abs(ra["chi2"] - rb["chi2"]) / max(abs(ra["chi2"]), 1e-300)
    draws = []
    for rel_path in ("backend/evenmore.py", "backend/finalstage.py", "backend/joepub.py", "backend/joestats.py"):
        p = os.path.join(APP, rel_path)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                n = len(re.findall(r"np\.random|default_rng|\brandom\.", fh.read()))
            if n:
                draws.append("%s (%d)" % (rel_path, n))
    detail = ["Tab 8's free-period snippets are drawn with a fixed seed, %d (joe.FP_SEED), so the same snippets come every time." % joe.FP_SEED,
              "With the rows in another order the chi-square agreed to a relative %.1e (the working correlation is the same within a rat)." % rel]
    if draws:
        detail.append("Random draws found in: %s." % ", ".join(draws))
    if not same:
        return _check("R3", "fail", title, how, "Two fits of the same rows differ.", detail)
    return _check("R3", "ok", title, how, "Fitted twice, the estimates and the robust covariance are identical to the bit; %s."
                  % ("no random draw in tabs 11, 12 or the publication set" if not draws else "random draws are listed below"), detail)


def r4_exports(X):
    title = "Everything another tool needs is exported"
    how = ("Each set's tab 11 and tab 12 export folder was opened for the rows each model was fitted to, the results, and the R "
           "(geepack) and SPSS (GENLIN) scripts that fit them again; tab 8's standalone script and its inputs were looked for.")
    want11 = ("evenmore_long.csv", "evenmore_results.csv", "evenmore_gee.R", "evenmore_gee.sps", "evenmore_README.txt")
    want12 = ("final_long.csv", "final_results.csv", "final_gee.R", "final_gee.sps", "final_coefficients_spss.csv")
    rows, miss = [], []
    for rs in _sets():
        for tab, folder, want in (("tab 11", E.set_root(rs, "export"), want11), ("tab 12", FS.set_root(rs, "export"), want12)):
            gone = [w for w in want if not os.path.isfile(os.path.join(folder, w))]
            rows.append([E.RATSET_SAY[rs], tab, len(want) - len(gone), ", ".join(gone) or "none"])
            miss += ["%s %s: %s" % (E.RATSET_SAY[rs], tab, g) for g in gone]
    for p, say in ((joe.script_path(), "tools/joe_standalone.py"), (joe.joe_dir("joe_inputs.json"), "tab 8's joe_inputs.json")):
        if not os.path.isfile(p):
            miss.append(say)
    table = {"head": ["Set", "Tab", "Files there", "Missing"], "rows": rows}
    if miss:
        return _check("R4", "warn", title, how, "Missing: %s." % "; ".join(miss), table=table)
    return _check("R4", "ok", title, how, "Every set's rows, results, R and SPSS scripts are there for tabs 11 and 12, and tab 8's "
                  "standalone script with its inputs.", table=table)


#: How to make everything again, from APP, in order: (what it makes,
#: command, the module that must answer it, what its entry must contain).
REGENERATE = (
    ("The Monolith manifest: the trials (curated in the event bank), wires marked bad and histology v2",
     "In Jarvis: Drift, then Monolith (the manifest is made there)", None, ()),
    ("Tab 8: each rat-day's trials and the wire each window used, from the recordings",
     "In Jarvis: Monolith, tab 8, Work it out", None, ()),
    ("Tab 8 checked without Jarvis (optional)",
     "python tools/joe_standalone.py --inputs GUI_logs/.cache/monolith/joe/joe_inputs.json --out <a new folder> --jobs 4",
     "tools/joe_standalone.py", ("add_argument(\"--inputs\"", "add_argument(\"--out\"")),
    ("Tab 11: the pooled spectra of every rat-day from the recordings, then every set of rats' models, figures and exports",
     "python -m backend.evenmore", "backend/evenmore.py", ("print(work(_W()))",)),
    ("Tab 12: power, FOOOF, Granger and coupling, every set of rats", "python -m backend.finalstage", "backend/finalstage.py",
     ("for rs in sys.argv[1:] or",)),
    ("Joe's publication set: figures, statistics PDFs, words and methods", "python -m backend.joepub", "backend/joepub.py",
     ("o = build(",)),
    ("This report", "python -m backend.sanity", "backend/sanity.py", ("build(",)),
    ("Joe's site, assembled (then deployed from tab 10)", "python -m backend.joeexport site", "backend/joeexport.py",
     ("sys.argv[1:] == [\"site\"]",)),
)


def r5_regenerate(X):
    title = "The way to make it all again"
    how = ("Each step's command was checked by reading its module: a command-line entry (if __name__ == \"__main__\") that does what "
           "the step says. The steps in Jarvis have no command line.")
    steps, bad = [], []
    for what, cmd, mod, needs in REGENERATE:
        steps.append({"step": what, "command": cmd})
        if not mod:
            continue
        p = os.path.join(APP, mod)
        if not os.path.isfile(p):
            bad.append("%s is missing" % mod)
            continue
        with open(p, encoding="utf-8") as fh:
            src = fh.read()
        entry = src.split('if __name__ == "__main__":', 1)
        if len(entry) < 2 and "def main(" not in src:
            bad.append("%s has no command-line entry" % mod)
            continue
        tail = entry[1] if len(entry) > 1 else src
        gone = [n for n in needs if n not in tail and n not in src]
        if gone:
            bad.append("%s's entry does not do what the step says (looked for %s)" % (mod, ", ".join(gone)))
    X.regenerate = steps
    detail = ["%d. %s: %s" % (i, s["step"], s["command"]) for i, s in enumerate(steps, 1)]
    detail.append("python -m backend.evenmore build only rebuilds the models from pooled rat-days already measured; from the raw "
                  "recordings, run it without build.")
    if bad:
        return _check("R5", "warn", title, how, "Some commands could not be confirmed: %s." % "; ".join(bad), detail)
    return _check("R5", "ok", title, how, "%d steps, from the recordings to Joe's site; every command's entry was found in its module "
                  "and does what the step says." % len(steps), detail)


# --------------------------------------------------------------------------
# What a careful reader should know
# --------------------------------------------------------------------------
def c1_model_based(X):
    title = "Some effects rest on model-based standard errors"
    how = ("Every term in tabs 11 and 12 (all rats) tested on the model's own standard errors (more than 2 df, where 8 rats cannot "
           "give robust ones) and significant there (q < .05 where corrected, p < .05 otherwise) was counted.")
    em, fn = X.em("all"), X.fn("all")
    if not em or not fn:
        return _check("C1", "warn", title, how, "Tab 11 or 12 has no result for all rats.")
    hits = []

    def scan(where, ts, q_of=None):
        for t in ts or []:
            q = (q_of or {}).get(t["term"])
            if t.get("errors") == E.NAIVE and t.get("p") is not None and (q if q is not None else t["p"]) < E.ALPHA:
                hits.append("%s: %s" % (where, t["term"]))
    for B in em["bands"]:
        b = B["band"]
        scan("tab 11 %s, all pairs (band)" % b, B["phase1"].get("a1"))
        scan("tab 11 %s, all pairs (bins)" % b, B["phase1"].get("b1"))
        scan("tab 11 %s, all pairs (cues)" % b, B["phase2"].get("omnibus"))
        for x in B["phase1"]["pairs"]:
            if x:
                scan("tab 11 %s %s (bins)" % (b, E.PAIR_SAY[x["pair"]]), x.get("b2"), {"Session × Frequency": x.get("b2_q")})
    for b, per in fn["power"].items():
        for x in per:
            if x:
                scan("tab 12 %s power %s (bins)" % (b, FS.REGION_SAY[x["region"]]), x.get("e2"),
                     {"Session × Period × Frequency": (x.get("spf") or {}).get("q")})
        for tier in ("t1", "t2"):
            t = fn["tiers"][b][tier]
            scan("tab 12 %s power tier %s" % (b, tier[1]), t.get("terms"), {k: v.get("q") for k, v in t["key"].items()})
    res = ("%d significant terms rest on model-based standard errors, which assume the working correlation is right; the methods call "
           "them secondary and each paragraph says which errors a test used." % len(hits)) if hits else \
        "No significant term rests on model-based standard errors."
    return _check("C1", "info", title, how, res, hits)


def c2_fragile(X):
    title = "Significant results that do not survive the checks beside them"
    how = ("Every result with p < .05 in tabs 11 and 12 (all rats) was refitted leaving each rat out in turn and as a linear mixed "
           "model (tab 11's and tab 12's \"robust\" lists). Solid: holds under both; shaky: under one; fragile: under neither.")
    em, fn = X.em("all"), X.fn("all")
    if not em or not fn:
        return _check("C2", "warn", title, how, "Tab 11 or 12 has no result for all rats.")
    rows, count = [], {"solid": 0, "shaky": 0, "fragile": 0}
    weak = []
    for r in (em.get("robust") or []) + (fn.get("robust") or []):
        v = JP._robust(r)
        name = r.get("name") or "%s %s, %s" % (r["band"], E.PAIR_SAY[r["pair"]], r["label"])
        t = r.get("test") or {}
        corr = bool((r.get("passes") or {}).get("fdr"))
        rows.append([name, JP.fp(t.get("p")), JP.fq(t.get("q")) or "not corrected", "yes" if corr else "no", v["loo"],
                     "J%s" % v["worst_rat"] if v["worst_rat"] is not None else "", JP.fp(v["lmm_p"]) if v["lmm_p"] is not None else "",
                     v["verdict"]])
        if corr:
            count[v["verdict"]] += 1
            if v["verdict"] != "solid":
                weak.append("%s (%s)" % (name, v["verdict"]))
    n = sum(count.values())
    table = {"head": ["Test", "p", "q", "Significant after correction", "Leave one rat out", "Weakest without", "Mixed model p", "Verdict"],
             "rows": rows}
    res = ("Of %d results significant after correction, %d are solid, %d shaky and %d fragile; %d more pass only uncorrected."
           % (n, count["solid"], count["shaky"], count["fragile"], len(rows) - n))
    detail = ["With 8 rats, the GEE's robust p can be much smaller than the mixed model's; the results paragraphs report both checks "
              "beside every such test."]
    if weak:
        return _check("C2", "warn", title, how, res + " Not solid: %s." % "; ".join(weak), detail, table)
    return _check("C2", "info", title, how, res, detail, table)


def c3_omnibus_only(X):
    title = "A Session × Period interaction with no planned contrast behind it"
    how = ("In tab 11's pairs (baseline, cue 1, cue 2) and tab 12's regions (tier 3a power), all rats: a Session × Period significant "
           "after correction (q < .05) where none of its three planned contrasts is.")
    em, fn = X.em("all"), X.fn("all")
    if not em or not fn:
        return _check("C3", "warn", title, how, "Tab 11 or 12 has no result for all rats.")
    found = []

    def one(where, x):
        sp = (x or {}).get("sp") or {}
        cs = [(x.get("contrasts") or {}).get(E.contrast_key(a, b)) or {} for a, b, _s in E.CONTRASTS]
        if sp.get("q") is not None and sp["q"] < E.ALPHA and not any(c.get("q") is not None and c["q"] < E.ALPHA for c in cs):
            found.append("%s (%s)" % (where, JP.fq(sp["q"])))
    for B in em["bands"]:
        for x in B["phase3"]["pairs"]:
            if x:
                one("%s coherence %s" % (B["band"], E.PAIR_SAY[x["pair"]]), x)
    for b, per in fn["power"].items():
        for x in per:
            if x:
                one("%s power %s" % (b, FS.REGION_SAY[x["region"]]), x)
    if found:
        return _check("C3", "info", title, how, "%s: %s. The response to the cues changed, but no single comparison says where; "
                      "the paragraphs say so." % (_plural(len(found), "case"), "; ".join(found)))
    return _check("C3", "info", title, how, "None: every corrected Session × Period has at least one planned contrast behind it.")


def c4_omitted(X):
    title = "How much data head bumps took"
    how = "From the head-bump counts (L6): the share of one-second segments omitted, overall and in the worst rat-day."
    rows = X.sat
    if not rows:
        return _check("C4", "warn", title, how, "Tab 8's day files are not here, so nothing could be counted.")
    ts, sl = sum(x["segments"] for x in rows), sum(x["segments_lost"] for x in rows)
    worst = max(rows, key=lambda x: x["segments_lost"] / max(1, x["segments"]))
    over = ["%s %.0f%%" % (_rd(x["rat"], x["day"]), 100.0 * x["segments_lost"] / x["segments"]) for x in rows
            if x["segments"] and x["segments_lost"] / x["segments"] > 0.10]
    res = ("%.1f%% of %s one-second segments were omitted overall; the worst rat-day, %s, lost %.1f%%." % (
        100.0 * sl / max(1, ts), "{:,}".format(ts), _rd(worst["rat"], worst["day"]), 100.0 * worst["segments_lost"] / max(1, worst["segments"])))
    detail = ["Rat-days that lost more than a tenth: %s." % ", ".join(over)] if over else []
    detail.append("Pooled spectra weight each rat-day by what is left of it; a rat-day that lost much is estimated from fewer segments.")
    return _check("C4", "info", title, how, res, detail)


def c5_reference(X):
    title = "Recording conditions differ between sessions in some rats"
    how = ("Each rat-day's acquisition reference and hardware high-pass were read from its recording's own header (CSC19.ncs, the "
           "first 16 kB, joepub._refs_of_recordings()).")
    refs = X.refs
    rows, changed, both_ref, lowcut = [], [], [], []
    for rat in STUDY_RATS:
        a, b = refs.get((rat, "Precon1")) or {}, refs.get((rat, "Precon4")) or {}
        rows.append(["J%d" % rat, a.get("ref") or "not read", b.get("ref") or "not read", a.get("lowcut") or "", b.get("lowcut") or ""])
        if a.get("ref") and b.get("ref") and a["ref"] != b["ref"]:
            changed.append("J%d" % rat)
        if "Reference" in (a.get("ref") or "") and "Reference" in (b.get("ref") or ""):
            both_ref.append("J%d" % rat)
        if a.get("lowcut") and b.get("lowcut") and a["lowcut"] != b["lowcut"]:
            lowcut.append("J%d (%s Hz, then %s Hz)" % (rat, a["lowcut"], b["lowcut"]))
    table = {"head": ["Rat", "Reference, Precon1", "Reference, Precon4", "High-pass Hz, Precon1", "High-pass Hz, Precon4"], "rows": rows}
    if not refs:
        return _check("C5", "warn", title, how, "The headers could not be read here (the recordings are not reachable). As the methods "
                      "record it: J3 and J4 carry a signal shared by every wire (the sets without them exist for this), and J8, J9 and "
                      "J10 changed reference between Precon1 and Precon4.")
    res = ("J3 and J4 carry a signal common to every wire (a contaminated reference; the sets without them exist for this). The "
           "reference changed between Precon1 and Precon4 in %s%s. A Session main effect (an absolute difference between the two "
           "days) can therefore reflect recording conditions; Session × Period and the contrasts compare each day with its own "
           "baseline and are protected from a constant offset." % (", ".join(changed) or "no rat",
                                                                  "; the hardware high-pass changed in %s" % ", ".join(lowcut) if lowcut else ""))
    detail = ["Recorded against a reference electrode on both days: %s." % (", ".join(both_ref) or "none")]
    return _check("C5", "warn", title, how, res, detail, table)


def c6_small(X):
    title = "Small samples"
    how = "The rats behind each pair (tab 11, phase 1), each region (tab 12, power) and each follow-up, all rats; fewer than seven listed."
    em, fn = X.em("all"), X.fn("all")
    if not em or not fn:
        return _check("C6", "warn", title, how, "Tab 11 or 12 has no result for all rats.")
    small = []
    for B in em["bands"][:1]:
        for x in B["phase1"]["pairs"]:
            if x and len(x["rats"]) < 7:
                small.append("coherence %s (%d)" % (E.PAIR_SAY[x["pair"]], len(x["rats"])))
    for x in fn["power"]["theta"]:
        if x and len(x["rats"]) < 7:
            small.append("power %s (%d)" % (FS.REGION_SAY[x["region"]], len(x["rats"])))
    for x in fn.get("granger") or []:
        if len(x.get("rats") or []) < 7:
            small.append("Granger %s %s (%d)" % (E.PAIR_SAY[x["pair"]], x["band"], len(x["rats"])))
    for x in fn.get("pac") or []:
        if len(x.get("rats") or []) < 7:
            small.append("coupling %s (%d)" % (FS.REGION_SAY[x["region"]], len(x["rats"])))
    res = ("%s rest on fewer than seven of the eight rats: %s. With five or six clusters, a GEE's robust errors are small-sample "
           "corrected but still uncertain, and leaving one rat out removes a fifth or a sixth of the data."
           % (_plural(len(small), "test family", "test families"), "; ".join(small))) if small else "Every pair and region has seven or eight rats."
    return _check("C6", "info", title, how, res)


def _bank_people(X):
    """Who saved the versions of the bank entries the manifest cites
    (the shard files, read only): {name: versions}."""
    from . import monolith as MO
    bank = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(MO._path()))), "event_bank")
    who = {}
    for rat in STUDY_RATS:
        for day in E.DAYS:
            e = ((X.day(rat, day) or {}).get("bank") or {}).get("entry")
            if not e:
                continue
            seen = set()
            for p in glob.glob(os.path.join(bank, "*_%s@*.json" % e)):
                try:
                    with open(p, encoding="utf-8") as fh:
                        rec = json.load(fh)
                except (OSError, ValueError):
                    continue
                for v in (rec.get("versions") or []) + (rec.get("history") or []):
                    k = (v.get("id") or v.get("at"), v.get("by"))
                    if v.get("by") and k not in seen:
                        seen.add(k)
                        who[v["by"]] = who.get(v["by"], 0) + 1
    return who


def c7_undocumented(X):
    title = "Steps a reader cannot yet check from the write-up"
    how = ("The methods' placeholders (W5), the trials with a wire excluded by hand (the manifest's curated units), and who saved the "
           "event-bank versions those trials come from (the bank's own records, read only).")
    hand_trials = hand_days = 0
    if X.man:
        for rat in STUDY_RATS:
            for day in E.DAYS:
                us = (X.day(rat, day) or {}).get("units") or []
                n = sum(1 for u in us if any((u.get("manual") or {}).get(k) for k in ("flat", "pre", "cue1", "cue2")))
                hand_trials += n
                hand_days += bool(n)
    who = _bank_people(X)
    ph = getattr(X, "placeholders", None) or []
    items = []
    if ph:
        items.append("%s in the methods" % _plural(len(ph), "placeholder"))
    items.append("%d trials in %d rat-days have wires excluded by hand; the bank records who saved each version (%s), but not who "
                 "inspected the trials or what was counted as an artefact" % (hand_trials, hand_days,
                                                                              ", ".join("%s, %d" % kv for kv in sorted(who.items())) or "no name found"))
    items.append("tab 8 is worked out in Jarvis, with no command line, so its first step cannot be scripted")
    return _check("C7", "warn", title, how, "%s." % "; ".join(items)[0:1].upper() + "%s." % "; ".join(items)[1:] if False else
                  "; ".join(items)[0].upper() + "; ".join(items)[1:] + ".")


def c8_granger_both(X):
    title = "Granger rising both ways"
    how = ("Each Granger follow-up (all rats): the Late/Early ratio in each direction and whether each passes (p < .05). A rise in both "
           "directions together with a rise in coherence is what more shared signal (or a better signal-to-noise ratio) would give; "
           "it says the coupling grew, not which region leads.")
    fn = X.fn("all")
    if not fn:
        return _check("C8", "warn", title, how, "Tab 12 has no result for all rats.")
    both, rows = [], []
    for x in fn.get("granger") or []:
        if x.get("error"):
            continue
        ab, ba = x.get("ab") or {}, x.get("ba") or {}
        rows.append(["%s %s" % (E.PAIR_SAY[x["pair"]], x["band"]), "%.2f, %s" % (ab["ratio"], JP.fp(ab.get("p"))) if ab.get("ratio") else "",
                     "%.2f, %s" % (ba["ratio"], JP.fp(ba.get("p"))) if ba.get("ratio") else ""])
        up = [t for t in (ab, ba) if t.get("ratio") and t["ratio"] > 1]
        if len(up) == 2:
            both.append("%s %s (%s and %s)" % (E.PAIR_SAY[x["pair"]], x["band"], "%.2f" % ab["ratio"], "%.2f" % ba["ratio"]))
    table = {"head": ["Pair", "First to second: Late/Early, p", "Second to first: Late/Early, p"], "rows": rows}
    if both:
        return _check("C8", "info", title, how, "Granger rose in both directions in %s." % "; ".join(both), table=table)
    return _check("C8", "info", title, how, "No Granger follow-up rose in both directions.", table=table)


# --------------------------------------------------------------------------
# All of it
# --------------------------------------------------------------------------
CHECKS = (("data", (d1_rat_days, d2_trials, d3_channel_map, d4_histology, d5_sets, d6_recordings, d7_freshness)),
          ("logic", (l1_tools, l2_refits, l3_fdr, l4_figures, l5_standalone, l6_head_bumps)),
          ("words", (w1_names, w2_directions, w3_primary_in_text, w4_rat_counts, w5_placeholders)),
          ("repro", (r1_code, r2_versions, r3_determinism, r4_exports, r5_regenerate)),
          ("concerns", (c1_model_based, c2_fragile, c3_omnibus_only, c4_omitted, c5_reference, c6_small, c7_undocumented, c8_granger_both)))


def _run_one(fn, X, check):
    """One check; one that breaks says so as a warning, never as an ok."""
    cid = fn.__name__.split("_", 1)[0].upper()
    try:
        if fn in (l1_tools, l2_refits):
            return fn(X, check)
        return fn(X)
    except SanityError:
        raise
    except Exception as exc:                                  # noqa: BLE001
        from . import monolith as MO
        if isinstance(exc, MO.MonolithError) or type(exc).__name__ in ("Stopped", "WorkStopped"):
            raise
        return _check(cid, "warn", fn.__doc__.strip().split("\n")[0] if fn.__doc__ else cid, "This check stopped before it finished.",
                      "It could not run: %s: %s." % (type(exc).__name__, exc))


def _verdict(counts):
    return "red" if counts["fail"] else "amber" if counts["warn"] else "green"


def _say(sections, counts):
    """The verdict in one plain sentence."""
    by = {s["id"]: s for s in sections}
    first3 = [c for sid in ("data", "logic", "words") for c in by[sid]["checks"]]
    trouble = [c for c in first3 if c["status"] in ("fail", "warn")]
    know = [c for c in by["concerns"]["checks"] if c["status"] in ("warn", "info")]
    rep = [c for c in by["repro"]["checks"] if c["status"] in ("fail", "warn")]
    if counts["fail"]:
        bad = [c for s in sections for c in s["checks"] if c["status"] == "fail"]
        return "%s failed: %s." % (_plural(len(bad), "check"), "; ".join("%s %s" % (c["id"], c["title"].lower()) for c in bad))
    head = "No problem found in the data, the logic or the words" if not trouble else \
        "Nothing failed; %s in the data, the logic or the words %s a look (%s)" % (
            _plural(len(trouble), "check"), "needs" if len(trouble) == 1 else "need", ", ".join(c["id"] for c in trouble))
    tail = []
    if rep:
        tail.append("%s about making it again (%s)" % (_plural(len(rep), "warning"), ", ".join(c["id"] for c in rep)))
    tail.append("%s a careful reader should know" % _plural(len(know), "point"))
    return head + "; " + " and ".join(tail) + "."


def build(progress=None, quick=False, check=None):
    """Every check, in order, then sanity.json. `progress(i, n, item)`;
    `check()` between checks (a stopped job stops here)."""
    from . import monolith as MO
    t0 = time.time()
    X = _Ctx(quick)
    X.recordings, X.code, X.versions, X.regenerate = [], {"commit": None, "dirty": []}, {}, []
    n = sum(len(fs) for _s, fs in CHECKS)
    i = 0
    sections = []
    titles = {sid: (t, s) for sid, t, s in SECTIONS}
    for sid, fns in CHECKS:
        out = []
        for fn in fns:
            if check:
                check()
            i += 1
            if progress:
                progress(i, n, "%s: %s" % (titles[sid][0], fn.__name__.split("_", 1)[0].upper()))
            out.append(_run_one(fn, X, check))
        sections.append({"id": sid, "title": titles[sid][0], "say": titles[sid][1], "checks": out})
    counts = {k: sum(1 for s in sections for c in s["checks"] if c["status"] == k) for k in ("ok", "warn", "fail", "info")}
    rats = sorted({r["rat"] for r in X.recordings}) or list(STUDY_RATS)
    out = {"ok": True, "schema": SCHEMA, "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": _verdict(counts),
           "say": _say(sections, counts), "counts": counts, "sections": sections, "regenerate": X.regenerate,
           "versions": X.versions or JP._versions(), "code": X.code,
           "inputs": {"rat_days": len(X.recordings), "rats": rats, "recordings": X.recordings},
           "quick": bool(quick), "seconds": round(time.time() - t0, 1)}
    os.makedirs(MO._path("sanity"), exist_ok=True)
    path = MO._path("sanity", "sanity.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(joe._clean(out), fh, ensure_ascii=False, indent=1, allow_nan=False, default=joe._jsonable)
    os.replace(tmp, path)
    return out


def result():
    from . import monolith as MO
    p = MO._path("sanity", "sanity.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def work(worker):
    """The full pass, the check tools included, as a Jarvis job."""
    out = build(progress=lambda i, n, s: worker.note(phase="sanity", i=i, of=n, item=s), quick=False, check=worker.check)
    return {"verdict": out["verdict"], "counts": out["counts"]}


def work_safe(worker):
    from . import monolith as MO
    try:
        return work(worker)
    except (SanityError, E.EvenMoreError, FS.FinalError, joe.JoeError) as exc:
        raise MO.MonolithError(str(exc), exc.status)


if __name__ == "__main__":
    from . import monolith as MO
    MO.configure(os.path.join(APP, "GUI_logs"))
    t0 = time.time()
    quick = sys.argv[1:2] == ["quick"]
    o = build(progress=lambda i, n, s: print("%5.0f s  %d/%d %s" % (time.time() - t0, i, n, s), flush=True), quick=quick)
    print("%s: %s" % (o["verdict"].upper(), o["say"]))
    print("ok %(ok)d, warn %(warn)d, fail %(fail)d, info %(info)d" % o["counts"])
    for s in o["sections"]:
        for c in s["checks"]:
            print("  %-4s %-5s %s" % (c["id"], c["status"], c["result"]))
    print("%.0f s" % (time.time() - t0))
