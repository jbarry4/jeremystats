"""
export_extraction.py -- The Extraction Room's results as a site of their own
(asked 2026-11-11), Vercel project `extraction-room`.

"Create a different Vercel page for the results in The Extraction Room.
Have the password be 2 ... Once the password is in: I understand this is
preliminary data. I understand Rain and Shahriar are still fine tuning
things. This is not a final result. Have the user check those, and type out
NOT FINAL, before clicking to see the results. And organise them in a nice
way."

The site's source is review/extraction_site (tracked): the password gate
(Joe's, with its own cookie), the acknowledgement and the results page. This
assembles it with the room's data into GUI_logs/.cache/extraction_site,
which is what is deployed.

    python tools/export_extraction.py build [--out DIR]
        Asks the room's own routes, in this process (no running Jarvis
        needed), for every set in the room (an X-ray Many folder): its
        newest extraction, Round I (/api/extraction/stats) and Round II
        (/api/extraction/round2), at the room's defaults -- Low KO under
        10%, a class needs 5 events, nobody left out -- with the separable
        calls and swaps made by hand counted, as the room counts them.
        Writes nothing outside the site folder.

    python tools/export_extraction.py env --set --confirm --password PW
        SITE_PASSWORD and a fresh SITE_SECRET into the linked Vercel
        project, as exact bytes (a PowerShell pipe adds a line ending, and
        the login then refuses the right password).

Nothing here deploys: `vercel deploy --prod --yes` from the site folder
does, once you have said so.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import shutil
import subprocess
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
SRC = os.path.join(APP, "review", "extraction_site")
OUT = os.path.join(APP, "GUI_logs", ".cache", "extraction_site")
KEEP = (".vercel", "node_modules", "package-lock.json")


def say(*a):
    print(*a, flush=True)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data.encode("utf-8") if isinstance(data, str) else data)
    os.replace(tmp, path)


def _ok(j, where):
    if not j or j.get("ok") is False:
        raise SystemExit("%s: %s" % (where, (j or {}).get("error") or "no answer"))
    return {k: v for k, v in j.items() if k != "ok"}


def _recording(r, flips, seps, split, ex):
    """One recording, as the site draws it: the room's own numbers, the
    call that counts (a person's over X-ray's) and its %KO group."""
    g = r.get("gid")
    ko = r.get("ko_now") if "ko_now" in r else r.get("ko_pct")
    verdict, by_hand = ex.sep_shown(r, (seps.get(g) or {}).get("verdict"))
    sep = r.get("separation") or {}
    return {
        "gid": g, "label": r.get("session_label"),
        "mouse": str(r.get("mouse_key") or "").split("|")[-1] or r.get("session_label"),
        "group": r.get("group"), "ko": ko,
        "ko_group": ex.ko_group(r, ko, split),
        "ied": r.get("ied"), "n": r.get("n"), "counts": r.get("counts"),
        "xray": {k: sep.get(k) for k in ("verdict", "dbic", "min_share", "n")},
        "call": {"verdict": verdict, "by_hand": by_hand,
                 "by": (seps.get(g) or {}).get("by") if by_hand else None},
        "flipped": bool((flips.get(g) or {}).get("flip")),
        "box": r.get("box"), "contacts": r.get("contacts"), "t_ms": r.get("t_ms"),
        "unit": r.get("unit"), "spacing_um": r.get("spacing_um"),
        "classes": [{"c": c.get("c"), "n": c.get("n"), "csd": c.get("csd"),
                     "profile": {"mean": (c.get("profile") or {}).get("mean"),
                                 "sem": (c.get("profile") or {}).get("sem")},
                     "sink": c.get("sink"), "delta": c.get("delta"),
                     "source": c.get("source")}
                    for c in r.get("classes") or []],
    }


def build(args):
    os.environ.setdefault("BARRY_HARNESS_SERVER", "1")
    say("Opening Jarvis in this process …")
    from backend import app as A                         # noqa: E402
    from backend import extraction as ex                 # noqa: E402
    C = A.app.test_client()
    idx = _ok(C.get("/api/extraction").get_json(), "/api/extraction")
    room = next((r for r in idx.get("rooms") or []
                 if r.get("room") == "dentate_spike"), None)
    if not room or not room.get("artifact_id"):
        raise SystemExit("The Dentate Spike room has nothing extracted yet.")
    aid = room["artifact_id"]
    newest = {}
    for v in room.get("versions") or []:
        f = v.get("folder_id")
        if f and v.get("here", True) and (f not in newest or v["v"] > newest[f]["v"]):
            newest[f] = v
    if not newest:
        raise SystemExit("None of the room's versions is on this machine.")

    out = os.path.abspath(args.out)
    if os.path.isdir(out):
        # The assembled copy only: keep the Vercel link, replace the rest.
        for name in os.listdir(out):
            if name in KEEP:
                continue
            p = os.path.join(out, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    shutil.copytree(SRC, out, dirs_exist_ok=True)

    sets = []
    for fid, v in sorted(newest.items(), key=lambda kv: kv[1].get("folder") or ""):
        one = _ok(C.get("/api/extraction/%s?version=%s" % (aid, v["v"])).get_json(),
                  "room v%s" % v["v"])
        body = {"artifact_id": aid, "version": v["v"]}
        st = _ok(C.post("/api/extraction/stats", json=body).get_json(),
                 "Round I of v%s" % v["v"])
        r2 = _ok(C.post("/api/extraction/round2", json=body).get_json(),
                 "Round II of v%s" % v["v"])
        pay = one["payload"]
        wf = (pay.get("source") or {}).get("workflow") or {}
        wpay = A.ARTIFACTS.payload(wf.get("artifact_id"), wf.get("version")) or {}
        grace = (wpay.get("run") or {}).get("grace")
        split = float(st.get("split") or ex.KO_SPLIT)
        data = {
            "id": fid, "name": v.get("folder"), "v": v["v"], "at": v.get("at"),
            "by": v.get("by"), "grace": grace, "workflow": wf.get("nickname"),
            "ko_from": pay.get("ko_from"),
            "left_out": [{"label": x.get("session_label"), "why": x.get("why")}
                         for x in pay.get("left_out") or []],
            "recordings": [_recording(r, one.get("flips") or {}, one.get("seps") or {},
                                      split, ex)
                           for r in pay.get("recordings") or []],
            "stats": st, "round2": r2,
        }
        name = "set-%s.json" % fid
        write(os.path.join(out, "data", name), json.dumps(data, separators=(",", ":")))
        sets.append({"id": fid, "name": v.get("folder"), "v": v["v"], "at": v.get("at"),
                     "by": v.get("by"), "n": len(data["recordings"]), "file": name})
        say("  %s (v%s): %d recordings, Round I and II worked out"
            % (v.get("folder"), v["v"], len(data["recordings"])))
    latest = max(sets, key=lambda s: s["v"])
    write(os.path.join(out, "data", "index.json"), json.dumps({
        "room": "Dentate Spike",
        "built": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "default": latest["id"], "sets": sets}, indent=1))
    n = sum(os.path.getsize(os.path.join(b, f)) for b, _d, fs in os.walk(out)
            if ".vercel" not in b and "node_modules" not in b for f in fs)
    say("Assembled %s (%.1f MB)." % (out, n / 1e6))
    say("Deploy: cd \"%s\" && vercel deploy --prod --yes" % out)


def env_cmd(args):
    site = os.path.abspath(args.out)
    rows = [("SITE_PASSWORD", args.password, "--password"),
            ("SITE_SECRET", secrets.token_hex(32), "a random secret, made here")]
    for name, value, where in rows:
        say("  %-14s %s  (%s)" % (name, "ready" if value else "—", where))
    if not args.set:
        return
    if not args.confirm:
        raise SystemExit("--set writes these into the Vercel project: add --confirm.")
    if not os.path.isfile(os.path.join(site, ".vercel", "project.json")):
        raise SystemExit("The site folder is not linked to a Vercel project yet: "
                         "run `vercel link` in %s." % site)
    vc = shutil.which("vercel") or shutil.which("vercel.cmd")
    for name, value, _w in rows:
        if not value:
            continue
        for target in ("production", "preview"):
            subprocess.run([vc, "env", "rm", name, target, "--yes"], cwd=site,
                           capture_output=True)
            p = subprocess.run([vc, "env", "add", name, target], cwd=site,
                               input=value.encode("utf-8"), capture_output=True)
            err = (p.stderr or p.stdout or b"").decode("utf-8", "replace").strip()
            say("  %s -> %s: %s" % (name, target, "set" if p.returncode == 0
                                    else err[-300:]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", default=OUT)
    e = sub.add_parser("env")
    e.add_argument("--set", action="store_true")
    e.add_argument("--confirm", action="store_true")
    e.add_argument("--password")
    e.add_argument("--out", default=OUT)
    args = ap.parse_args()
    {"build": build, "env": env_cmd}[args.cmd](args)


if __name__ == "__main__":
    main()
