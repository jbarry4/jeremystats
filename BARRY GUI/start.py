"""
BARRY GUI -- launcher.

Windows: double-click "Start BARRY GUI.bat"
macOS:   double-click "Start BARRY GUI.command"
Either:  python start.py

Starts the local server and opens your browser. Nothing is installed and
nothing leaves this machine -- the server binds to 127.0.0.1 only.

First time on a machine? Run the setup script beside this one.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BANNER = r"""
  ___   _   ___ _____   __  ___ _   _ ___
 | _ ) /_\ | _ \ _ \ \ / / / __| | | |_ _|
 | _ \/ _ \|   /   /\ V / | (_ | |_| || |
 |___/_/ \_\_|_\_|_\ |_|   \___|\___/|___|
"""

REQUIRED = [("flask", "flask"), ("numpy", "numpy"),
            ("scipy", "scipy"), ("matplotlib", "matplotlib")]
OPTIONAL = [
    ("h5py", "h5py -- MATLAB v7.3 .mat files"),
    ("pandas", "pandas -- CSV / Excel event imports"),
]


def setup_hint():
    return ('"Setup Windows.bat"' if os.name == "nt" else '"Setup Mac.command"')


def check_deps():
    import importlib
    missing = []
    for mod, pip_name in REQUIRED:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        print("\n  Missing required packages: " + ", ".join(missing))
        print("  Run " + setup_hint() + ", or install them yourself:\n")
        print("      " + sys.executable + " -m pip install " + " ".join(missing))
        print()
        return False

    for mod, note in OPTIONAL:
        try:
            importlib.import_module(mod)
        except ImportError:
            print("  note: " + note + " (not installed)")
    return True


def free_port(preferred=8733):
    for port in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 0        # let the OS choose


def ask_for_key(logs_dir):
    """First start on a new machine: get the key, once.

    The repo carries the project id, so a clone already knows where to sync.
    What it deliberately does not carry is the key -- so somebody has to hand
    it over exactly once per machine, and the sensible moment is now, in the
    window they are already looking at, rather than in a README they will
    read afterwards.

    Skipping is a first-class answer. BARRY writes locally first and works
    completely without the network; the sync is an addition, never a
    prerequisite, and starting up must never depend on someone having a
    password to hand.
    """
    from backend import cloud

    cfg = cloud.load_config(logs_dir)

    if cfg.get("key_in_repo"):
        print()
        print("  !! cloud.json in the repo contains a key. That file is")
        print("     tracked by git, so the key should be treated as public:")
        print("     rotate it in the Supabase dashboard, then paste the new")
        print("     one below. BARRY is ignoring the one in the file.")

    if not cfg.get("needs_key"):
        if cfg.get("enabled"):
            print("  Sync    : %s" % cfg.get("project"))
        return

    print()
    print("  This copy syncs to Supabase project '%s'," % cfg.get("project"))
    print("  but this machine has not been given the key yet.")
    print()
    print("  Get it from the Supabase dashboard:")
    print("     Project Settings -> API Keys -> secret / service_role")
    print()
    print("  It is stored in GUI_logs/.cloud.json, which git ignores, and")
    print("  never goes into the repo.")
    print()
    print("  Press Enter to skip -- BARRY works fine without it, and you")
    print("  can add it later from the Sync panel.")
    print()

    if not sys.stdin or not sys.stdin.isatty():
        print("  (not a terminal, so skipping the question)")
        return

    for attempt in range(3):
        try:
            key = input("  Supabase secret key: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not key:
            print("  Skipped. Sync is off until a key is set.")
            return
        ok, why = cloud.looks_like_a_key(key)
        if not ok:
            print("  %s" % why)
            continue

        cloud.save_config(logs_dir, key=key)
        c = cloud.Cloud(logs_dir)
        print("  Checking...")
        ping = c.ping()
        if not ping["reachable"]:
            print("  Could not reach the project: %s"
                  % (ping.get("error") or "")[:160])
            print("  Saved anyway; BARRY will keep trying in the background.")
            return
        if not ping["schema"]:
            print("  Connected, but the tables are not there yet. Run the SQL")
            print("  in supabase/ (01_schema, 02_rls, 03_storage), then")
            print("  python tools/cloud_migrate.py --write")
            return
        n = sum(v for v in (ping.get("counts") or {}).values()
                if isinstance(v, int))
        print("  Connected. %d row(s) already up there." % n)
        return

    print("  Skipping for now. Add it later from the Sync panel.")


def main():
    print(BANNER)
    if not check_deps():
        pause()
        return 1

    from backend.app import app, refresh_catalog, REPO_ROOT, LOGS_DIR
    from backend import runner, sysinfo, video

    sysdesc = sysinfo.describe()
    matlab = runner.MATLAB_EXE
    ffmpeg = sysinfo.find_ffmpeg()

    print("  Machine : %s %s (%s)" % (sysdesc["os"], sysdesc["release"],
                                      sysdesc["machine"]))
    print("  Repo    : " + REPO_ROOT)
    print("  Logs    : " + LOGS_DIR)
    print("  Python  : " + sys.executable)
    print("  MATLAB  : " + (matlab or "not found (MATLAB stages disabled)"))
    print("  ffmpeg  : " + (ffmpeg or "not found (session video disabled)"))

    # Before anything starts serving: if this machine has never been given
    # the sync key, ask for it here, where somebody is looking.
    try:
        ask_for_key(LOGS_DIR)
    except Exception as exc:                       # noqa: BLE001
        print("  (could not check the sync settings: %s)" % exc)

    stale = runner.sweep_temp_files(REPO_ROOT)
    if stale:
        print("  Cleaned : %d leftover temp script(s)" % stale)
    video.cleanup_clips()

    t0 = time.time()
    cat = refresh_catalog()
    print("  Indexed : %d scripts in %d sections (%.2fs)"
          % (len(cat["items"]), len(cat["sections"]), time.time() - t0))

    port = free_port()
    url = "http://127.0.0.1:%d/" % port
    print("\n  Serving : " + url)
    print("  Stop    : Ctrl+C in this window\n")

    threading.Timer(0.9, lambda: webbrowser.open(url)).start()

    # Threaded so a long-running job's log stream never blocks the UI.
    try:
        app.run(host="127.0.0.1", port=port, debug=False,
                threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        video.cleanup_clips()
    return 0


def pause():
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\n  Press Enter to close...")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    sys.exit(main())
