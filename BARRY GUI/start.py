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
