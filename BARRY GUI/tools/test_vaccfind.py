# -*- coding: utf-8 -*-
"""Every recording on the cluster, and adding the ones Jarvis has not met.
Offline.

    python tools/test_vaccfind.py

What is guarded, in the order it can go wrong:

  * the walk's listing -- five fields with the header, four from an older
    script, and a folder holding CSC1.ncs AND CSC1_0001.ncs counted once;
  * the path map run backwards: a netfiles folder gets its UNC spelling,
    anything else gets none;
  * the survey's four piles, and above all that a registered row NEVER
    carries a cluster path (constitution section 6d) -- a netfiles find
    carries its UNC, a scratch find carries nothing;
  * `REG.ingest_found` on a throwaway store: new records, no sighting filed
    for this computer, a second run adding nothing;
  * a folder found on a mapped share resolves as `native`, and beats a
    scratch copy of the same recording instead of conflicting with it;
  * the add route refusing without `confirm` and with a stale digest.

Nothing talks to the cluster and nothing real is written: the inventory is
stood in for, and registration runs against a store in a temp folder.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import sessreg, store, vacc, vaccfind  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-70s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


CFG = {
    "netid": "zztester",
    "path_map": [{"unc": "//netfiles03.uvm.edu/bigdata_jbarry",
                  "vacc": "/netfiles/bigdata_jbarry"}],
    "temp": {"root": "/gpfs3tmp/pi/x/zztester/Jarvis_temp"},
}
NF = "/netfiles/bigdata_jbarry"
HDR = "-TimeCreated 2023/07/24 17:00:22 -SamplingFrequency 30000"


def listing():
    print("\nthe walk's listing")
    lines = "\n".join([
        "rec\t64\t38771752\t%s\t%s/P/M11_Pten/HF2_s4jul24/2023-07-24_17-00-22"
        % (HDR, NF),
        # The same folder again: CSC1.ncs and CSC1_0001.ncs both matched.
        "rec\t64\t38771752\t%s\t%s/P/M11_Pten/HF2_s4jul24/2023-07-24_17-00-22"
        % (HDR, NF),
        # An older four-field line still reads.
        "rec\t32\t1000\t/gpfs2/scratch/zz/A Folder/m3s2/2023-01-01_10-00-00",
        "end=1", ""])
    real = vacc._ssh
    vacc._ssh = lambda cfg, cmd, stdin=None, timeout=45: lines
    try:
        got = vacc.inventory(CFG, NF)
    finally:
        vacc._ssh = real
    check("two folders, the doubled one kept once", len(got) == 2, got)
    check("the header came back raw", got[0].get("header") == HDR, got[0])
    check("a four-field line has no header and keeps its spaced path",
          got[1]["header"] == "" and got[1]["path"].endswith(
              "A Folder/m3s2/2023-01-01_10-00-00"), got[1])
    check("the script looks for both names",
          "CSC1_0001.ncs" in vacc._INVENTORY and "CSC1.ncs" in vacc._INVENTORY)


def unc():
    print("\nthe path map, backwards")
    got = vacc.unc_for(CFG, NF + "/Jeremy3/KCNT1/m1s2/2025-01-01_10-00-00")
    check("netfiles -> the Windows UNC spelling",
          got == "\\\\netfiles03.uvm.edu\\bigdata_jbarry\\Jeremy3\\KCNT1\\"
                 "m1s2\\2025-01-01_10-00-00", got)
    check("and it resolves forward to the same cluster folder",
          vacc.resolve_path(got, CFG, drives={})[1]
          == NF + "/Jeremy3/KCNT1/m1s2/2025-01-01_10-00-00",
          vacc.resolve_path(got, CFG, drives={}))
    check("scratch has no UNC", vacc.unc_for(CFG, "/gpfs2/scratch/zz/x") is None)
    check("a prefix that is not a folder boundary is not under the rule",
          vacc.unc_for(CFG, NF + "_other/x") is None)


def facts():
    print("\nfacts from the header and the size")
    start, fs, dur = vaccfind.facts_of(
        {"header": HDR, "first_ncs_bytes": 16384 + 1044 * 30000})
    check("start from -TimeCreated", start == "2023-07-24T17:00:22", start)
    check("rate from -SamplingFrequency", fs == 30000.0, fs)
    check("30000 records of 512 at 30 kHz is 512 s", dur == 512.0, dur)
    start, fs, dur = vaccfind.facts_of({"header": "", "first_ncs_bytes": 99})
    check("no header claims nothing", (start, fs, dur) == (None, None, None))


def survey():
    print("\nthe survey's piles")
    known = {"gid": "sknown000001", "label": "known"}
    rows = [
        {"path": NF + "/P/PTEN_M1/m1s1/2023-07-24_17-00-22", "n_channels": 64,
         "first_ncs_bytes": 16384 + 1044 * 300, "header": HDR, "native": True},
        {"path": NF + "/P/PTEN_M2/m2s1/2023-08-01_10-00-00", "n_channels": 64,
         "first_ncs_bytes": 0, "header": "", "native": True},     # other-day
        {"path": NF + "/P/PTEN_M3/m3s1/2023-08-01_10-00-00", "n_channels": 64,
         "first_ncs_bytes": 0, "header": "", "native": True},     # other-project
        {"path": NF + "/P/New folder/2024-07-03_12-14-01", "n_channels": 64,
         "first_ncs_bytes": 0, "header": "", "native": True},     # unidentifiable
        # One new recording, on netfiles AND in scratch: netfiles wins.
        {"path": NF + "/P/PTEN_M4/m4s1/2023-09-09_09-09-09", "n_channels": 64,
         "first_ncs_bytes": 0, "header": "", "native": True},
        {"path": "/gpfs2/scratch/zz/PTEN_M4/m4s1/2023-09-09_09-09-09",
         "n_channels": 64, "first_ncs_bytes": 0, "header": ""},
        # A new recording only in scratch.
        {"path": "/gpfs2/scratch/zz/PTEN_M5/m5s1/2023-10-10_10-10-10",
         "n_channels": 32, "first_ncs_bytes": 0, "header": ""},
        # Two lab copies of one new recording: refused.
        {"path": NF + "/A/PTEN_M6/m6s1/2023-11-11_11-11-11", "n_channels": 64,
         "first_ncs_bytes": 0, "header": "", "native": True},
        {"path": NF + "/B/PTEN_M6/m6s1/2023-11-11_11-11-11", "n_channels": 64,
         "first_ncs_bytes": 0, "header": "", "native": True},
    ]

    def match(path, start):
        if "/m1s1/" in path:
            return known, "exact", None
        if "/m2s1/" in path:
            return None, "other-day", "same mouse and session, another day"
        if "/m3s1/" in path:
            return None, "other-project", "same mouse and session, another project"
        return None, None, None

    got = vaccfind.survey(rows, CFG, match)
    new = got.pop("_new")
    check("one matched", got["n_matched"] == 1, got)
    check("the other-project one refused, plus the two lab copies",
          got["n_refused"] == 3, got["refused"])
    check("the folder naming no mouse is unidentifiable",
          got["n_unidentifiable"] == 1, got["unidentifiable"])
    keys = {(r["identity"] or {}).get("mouse"): r for r in new}
    check("new: the other-day one, m4 (once) and m5",
          sorted(keys) == [2, 4, 5], sorted(keys))
    check("the other-day one goes in under its UNC",
          str(keys[2]["identity"].get("path", "")).startswith("\\\\netfiles03"),
          keys[2]["identity"])
    check("m4 is registered once, from netfiles, knowing it has two copies",
          keys[4]["kind"] == "netfiles" and keys[4]["copies"] == 2
          and str(keys[4]["identity"].get("path", "")).startswith("\\\\"),
          keys[4])
    check("m5, only in scratch, goes in with no path at all",
          "path" not in keys[5]["identity"], keys[5]["identity"])
    bad = [r for r in new if str((r["identity"] or {}).get("path") or "")
           .startswith("/")]
    check("NO registered row carries a cluster path", not bad, bad)
    check("the page's sample carries no identity or UNC",
          all("identity" not in r and "unc" not in r for r in got["new"]),
          got["new"][:1])
    check("a digest names the list",
          got["digest"] == vaccfind.digest(new) and len(got["digest"]) == 16)
    return new


def ingest(new):
    print("\nregistering, on a throwaway store")
    tmp = tempfile.mkdtemp(prefix="jarvis-vaccfind-")
    try:
        st = store.Store(tmp, auto_stage=False)
        reg = sessreg.Registry(st)
        added, joined = vaccfind.register(reg, new)
        recs = reg.all()
        check("three new records", added == 3 and len(recs) == 3,
              (added, joined, len(recs)))
        paths = [p for r in recs for p in (r.get("paths") or [])]
        check("every path written is a UNC spelling",
              paths and all(p.startswith("\\\\netfiles03") for p in paths),
              paths)
        check("each has a gid and says how it arrived",
              all(r.get("gid") and (r.get("found_on") or {}).get("via")
                  == "vacc" and r.get("first_seen_by") == "vacc"
                  for r in recs), [r.get("found_on") for r in recs])
        check("no sighting is filed for this computer",
              all(not r.get("seen") for r in recs),
              [r.get("seen") for r in recs])
        m5 = [r for r in recs if r.get("mouse") == 5]
        check("the scratch-only one has no paths",
              m5 and not (m5[0].get("paths") or []), m5)
        again = vaccfind.register(reg, new)
        check("registering the same list again adds nothing",
              again == (0, 0) and len(reg.all()) == 3, again)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def resolve():
    print("\nfound on a mapped share is native")
    staged = {"g1": {"path": NF + "/x/m1s1/2023-01-01_00-00-00", "native": True}}
    got = vacc.resolve_gid("g1", [], CFG, drives={}, staged=staged)
    check("native, read in place", got["state"] == vacc.NATIVE
          and got["remote"].startswith(NF), got)
    got = vacc.resolve_gid("g2", [], CFG, drives={},
                           staged={"g2": {"path": "/gpfs2/scratch/zz/a"}})
    check("a scratch copy is still staged", got["state"] == vacc.STAGED, got)


def app_side():
    print("\nthe app: a lab copy beats a scratch copy, and the add is guarded")
    from backend import app as appmod
    rec = next((r for r in (appmod.REG.all() or [])
                if r.get("gid") and r.get("key") and r.get("paths")), None)
    if rec is None:
        print("  (no registered recording here; skipped)")
        return
    parts = [x for x in rec["paths"][0].replace("\\", "/").split("/") if x]
    leaf = "/".join(parts[-3:])
    scratch = "/gpfs2/scratch/zztester"
    cfg = dict(CFG, scratch_root=scratch, places=[])
    lab = NF + "/zz/" + leaf
    copy = scratch + "/copies/" + leaf

    def fake_inventory(c, root=None, timeout=180):
        if root == scratch:
            return [{"path": copy, "n_channels": 64, "first_ncs_bytes": 1}]
        if root == NF:
            return [{"path": lab, "n_channels": 64, "first_ncs_bytes": 1}]
        return []

    real = {k: getattr(vacc, k) for k in
            ("inventory", "load_config", "readable_native_roots", "_inv_save",
             "_inv_load")}
    vacc.inventory = fake_inventory
    vacc.load_config = lambda logs_dir: dict(cfg)
    vacc.readable_native_roots = lambda c=None: [NF]
    vacc._inv_save = lambda *a, **k: None
    vacc._inv_load = lambda *a, **k: None
    vacc._INVS.clear()
    try:
        # The mapped share is never waited on: the first ask starts its walk
        # and answers without it.
        vacc.inventory_cached(cfg, NF, force=True)   # as if walked already
        staged, _unknown = appmod._vacc_staged()
        got = staged.get(rec["gid"]) or {}
        check("the recording resolves to the lab copy, not a conflict",
              got.get("native") and got.get("path") == lab, got)

        c = appmod.app.test_client()
        r = c.post("/api/vacc/found/add", json={})
        check("the add refuses without confirm", r.status_code == 400)
        r = c.post("/api/vacc/found/add", json={"confirm": True,
                                                "digest": "stale"})
        body = r.get_json() or {}
        check("and refuses a list that changed since it was shown",
              r.status_code == 409 and body.get("changed"), body)
        f = c.get("/api/vacc/found").get_json() or {}
        check("/api/vacc/found answers with counts and a digest",
              f.get("ok") and "n_new" in f and f.get("digest"), f)
        check("and sends no full rows to the page", "_new" not in f)
    finally:
        for k, v in real.items():
            setattr(vacc, k, v)
        vacc._INVS.clear()


def main():
    listing()
    unc()
    facts()
    new = survey()
    ingest(new)
    resolve()
    app_side()
    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
