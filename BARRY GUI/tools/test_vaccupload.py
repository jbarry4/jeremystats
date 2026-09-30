# -*- coding: utf-8 -*-
"""Uploading to Jarvis Data, end to end, with no cluster. Offline.

    python tools/test_vaccupload.py

The far side is a folder on this machine (vaccupload.LocalRemote), the
registry is stood in for with one fake recording, and the real ssh path is
checked by standing in for Popen -- so what it WOULD run and stream is
checked, and nothing is sent anywhere. The local recording is only read.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import app as appmod, cfc, ids, vacc, vaccupload as U  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-66s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


def make_recording(root):
    rec_dir = os.path.join(root, "ProjX", "M7_Foo", "M7s3oct2", "2024-01-02_10-00-00")
    os.makedirs(os.path.join(rec_dir, "sub"))
    for name, n in (("CSC1.ncs", 300000), ("CSC2.ncs", 250000),
                    ("Events.nev", 1234), (os.path.join("sub", "note.txt"), 10)):
        with open(os.path.join(rec_dir, name), "wb") as fh:
            fh.write(os.urandom(n))
    return rec_dir


def main():
    work = tempfile.mkdtemp(prefix="zz-upload-")
    local = make_recording(os.path.join(work, "local"))
    far = os.path.join(work, "far")
    cfg = {"netid": "zztester", "host": "login.vacc.uvm.edu", "configured": True,
           "shared": vacc._shared_of({})}
    rec = {"gid": "zz-gid-7", "label": "zz ProjX m7 s3", "project": "ProjX",
           "mouse": 7, "session": 3, "paths": [local]}
    remote = U.LocalRemote(far)

    print("\nwhere it goes")
    dest = U.destination(cfg, rec, local)
    check("Jarvis Data/<project>/<mouse folder>/.../<recording>",
          dest == "/gpfs2/scratch/sakhava1/Jarvis Data/ProjX/M7_Foo/M7s3oct2/"
                  "2024-01-02_10-00-00", dest)
    check("and it identifies as the same recording",
          ids.identify(dest).get("key") == ids.identify(local).get("key")
          and ids.identify(dest).get("key"), (ids.identify(dest).get("key"),
                                              ids.identify(local).get("key")))
    try:
        U.destination(cfg, rec, os.path.join(work, "no-mouse-here"))
        check("a folder that names no mouse and session is refused", False)
    except U.UploadError as exc:
        check("a folder that names no mouse and session is refused",
              "mouse and a session" in str(exc), exc)

    print("\nsending")
    pl = U.plan_one(remote, local, dest)
    check("the plan sends every file the first time", len(pl["send"]) == 4
          and pl["skip"] == 0 and pl["bytes"] == 300000 + 250000 + 1234 + 10, pl)
    seen = []
    got = U.send(remote, local, dest, plan=pl, on_bytes=seen.append)
    landed = remote.sizes(dest)
    check("every file lands, at its size", landed == {
        "CSC1.ncs": 300000, "CSC2.ncs": 250000, "Events.nev": 1234,
        "sub/note.txt": 10}, landed)
    check("byte for byte", open(os.path.join(local, "CSC1.ncs"), "rb").read()
          == open(os.path.join(far, dest.lstrip("/"), "CSC1.ncs"), "rb").read())
    check("progress is reported in bytes", sum(seen) == pl["bytes"], sum(seen))
    parts = [f for _d, _s, fs in os.walk(far) for f in fs if f.endswith(".part")]
    check("nothing is left as .part", not parts, parts)
    check("the local copy is untouched", sorted(os.listdir(local)) ==
          ["CSC1.ncs", "CSC2.ncs", "Events.nev", "sub"])

    print("\nagain")
    pl2 = U.plan_one(remote, local, dest)
    check("a second upload sends nothing: every file is there at its size",
          not pl2["send"] and pl2["skip"] == 4, pl2)
    with open(os.path.join(local, "Events.nev"), "ab") as fh:
        fh.write(b"more")
    pl3 = U.plan_one(remote, local, dest)
    check("a file that changed size is sent again, and only it",
          [f[0] for f in pl3["send"]] == ["Events.nev"], pl3["send"])

    print("\na connection cut halfway")
    target = os.path.join(far, dest.lstrip("/"), "CSC2.ncs")
    os.remove(target)
    n = [0]

    def cut():
        n[0] += 1
        if n[0] > 1:
            raise cfc.Canceled("Stopped.")
    old_chunk = U.CHUNK
    U.CHUNK = 50000
    try:
        U.send(remote, local, dest, plan={"send": [("CSC2.ncs", 250000,
               os.path.join(local, "CSC2.ncs"))], "skip": 0, "bytes": 250000},
               check=cut)
        check("stopping mid-file stops", False)
    except cfc.Canceled:
        check("stopping mid-file stops", True)
    finally:
        U.CHUNK = old_chunk
    check("and leaves no file that looks whole", not os.path.exists(target))
    pl4 = U.plan_one(remote, local, dest)
    check("the next upload sends it again (a .part is not counted)",
          "CSC2.ncs" in [f[0] for f in pl4["send"]], pl4["send"])

    print("\nthe real far side, with ssh stood in for")
    runs = []

    class FakeProc:
        def __init__(self, cmd, **k):
            runs.append({"cmd": cmd, "data": b""})
            self.stdin = self
            self.stderr = self
        def write(self, b):
            runs[-1]["data"] += b
        def close(self):
            pass
        def read(self):
            return b""
        def wait(self, timeout=None):
            return 0
    real_popen, real_have = subprocess.Popen, vacc.have_ssh
    subprocess.Popen = FakeProc
    vacc.have_ssh = lambda: True
    try:
        U.SshRemote(cfg).put(os.path.join(local, "sub", "note.txt"), dest,
                             "sub/note.txt")
    finally:
        subprocess.Popen, vacc.have_ssh = real_popen, real_have
    cmd = runs[0]["cmd"] if runs else []
    remote_cmd = cmd[-1] if cmd else ""
    check("one ssh, as this account", cmd and cmd[0] == "ssh"
          and "zztester@login.vacc.uvm.edu" in cmd, cmd)
    check("it makes the folder, writes a .part, then renames it",
          remote_cmd.startswith("mkdir -p ") and "cat > " in remote_cmd
          and ".part" in remote_cmd and " && mv -f " in remote_cmd, remote_cmd)
    check("with the path quoted, spaces and all",
          "'/gpfs2/scratch/sakhava1/Jarvis Data/ProjX/M7_Foo/M7s3oct2/"
          "2024-01-02_10-00-00/sub/note.txt.part'" in remote_cmd, remote_cmd)
    check("and the file streamed in, not on the command line",
          runs[0]["data"] == open(os.path.join(local, "sub", "note.txt"), "rb").read())

    print("\nthe routes")
    shutil.rmtree(far, ignore_errors=True)
    added, soon = [], []
    real = {"all": appmod.REG.all, "add_path": appmod.REG.add_path,
            "load": vacc.load_config, "status": vacc.status,
            "soon": vacc.inventory_soon, "remote": appmod.UPLOAD_REMOTE}
    appmod.REG.all = lambda: [rec]
    appmod.REG.add_path = lambda *a, **k: added.append(a)
    vacc.load_config = lambda d: dict(cfg)
    vacc.status = lambda: {"shared": dict(cfg["shared"], state="ok",
                                          data_state="creatable", why="")}
    vacc.inventory_soon = lambda c, root=None: soon.append(root)
    appmod.UPLOAD_REMOTE = lambda c: U.LocalRemote(far)
    try:
        c = appmod.app.test_client()
        plan = c.post("/api/vacc/upload/plan", json={"gids": ["zz-gid-7", "nope"]}).get_json()
        check("the plan: one recording, four files, where they go",
              plan["ok"] and plan["n"] == 1 and plan["files"] == 4
              and plan["items"][0]["dest"] == dest, plan)
        check("and says why the other cannot go",
              plan["blocked"] and plan["blocked"][0]["why"] == "not in the registry",
              plan["blocked"])
        check("the plan sent nothing", not os.path.exists(far))
        r = c.post("/api/vacc/upload", json={"gids": ["zz-gid-7"]})
        check("an upload without confirm is refused", r.status_code == 400
              and "confirmed" in (r.get_json() or {}).get("error", ""), r.get_json())
        check("and sends nothing", not os.path.exists(far))
        r = c.post("/api/vacc/upload", json={"gids": ["zz-gid-7"], "confirm": True})
        body = r.get_json()
        check("confirmed, it starts a job", body.get("ok") and body.get("job"), body)
        jid = body["job"]["id"]
        t0 = time.time()
        while cfc.get(jid).status == "running" and time.time() - t0 < 30:
            time.sleep(0.05)
        job = cfc.get(jid)
        check("the job finishes", job.status == "done", (job.status, job.error))
        check("and reports what it sent", (job.result or {}).get("files_sent") == 4,
              job.result)
        check("the files are there", len(U.LocalRemote(far).sizes(dest)) == 4)
        check("NO path went into the registry", not added, added)
        check("and the inventory is asked to look at Jarvis Data",
              soon == [cfg["shared"]["data_path"]], soon)
    finally:
        appmod.REG.all = real["all"]
        appmod.REG.add_path = real["add_path"]
        vacc.load_config = real["load"]
        vacc.status = real["status"]
        vacc.inventory_soon = real["soon"]
        appmod.UPLOAD_REMOTE = real["remote"]
        shutil.rmtree(work, ignore_errors=True)

    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
