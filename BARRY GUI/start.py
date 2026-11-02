"""
Jarvis -- launcher.

Windows: double-click "Activate Jarvis.bat" (or its .lnk, which has the icon)
macOS:   double-click "Activate Jarvis.command"
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

# The wordmark, in blocks. Looks like something worth opening; costs nothing
# but a few lines of text.
BLOCK = """\
     \u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2557   \u2588\u2588\u2557\u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557
     \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2550\u2550\u255d
     \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557
\u2588\u2588   \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u255a\u2588\u2588\u2557 \u2588\u2588\u2554\u255d\u2588\u2588\u2551\u255a\u2550\u2550\u2550\u2550\u2588\u2588\u2551
\u255a\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2551  \u2588\u2588\u2551 \u255a\u2588\u2588\u2588\u2588\u2554\u255d \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551
 \u255a\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u255d  \u255a\u2550\u2550\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u255d"""

# The same word for a console that cannot encode a block. cmd.exe on an older
# machine is codepage 437, where every character above is unprintable -- and
# an exception from the banner would stop the launcher before it started.
PLAIN = r"""
     _   _    ______     _____ ____
    | | / \  |  _ \ \   / /_ _/ ___|
 _  | |/ _ \ | |_) \ \ / / | |\___ \
| |_| / ___ \|  _ < \ V /  | | ___) |
 \___/_/   \_\_| \_\ \_/  |___|____/"""


def _fits(text):
    """Can this console actually encode that?

    Asked rather than assumed. `sys.stdout.encoding` is utf-8 on a modern
    Windows console and cp437 on an old one, and the difference is an
    exception on the first line of main().
    """
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError, AttributeError):
        return False


def _colour():
    """Turn on ANSI if this console will take it, and say whether it did.

    Windows 10 understands the escape codes but only once virtual-terminal
    processing is enabled; a console that never got it prints them as
    literal garbage, which is worse than plain text.
    """
    if not (sys.stdout and getattr(sys.stdout, "isatty", lambda: False)()):
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:                              # noqa: BLE001
        return False


def _greeting():
    """What time it is, said the way a person would."""
    hour = time.localtime().tm_hour
    if hour < 5:
        return "Still up?"
    if hour < 12:
        return "Good morning."
    if hour < 18:
        return "Good afternoon."
    return "Good evening."


def _name_hidden():
    """Has this machine been told to keep the name out of sight?

    The switch is in the interface (web/js/jarvis.js) and is stored the way
    the theme is: a map keyed by hostname in the shared preferences, merged
    per key, newest stamp wins. Read straight off the shard files rather
    than through the store, because the banner is printed before the
    dependencies are checked and must not import anything that needs them.
    Any trouble reading is "not hidden", which is the default.
    """
    import glob
    import json
    import platform
    host = platform.node()
    newest, hidden = "", False
    pattern = os.path.join(HERE, "GUI_logs", "prefs", "workbench@*.json")
    for path in glob.glob(pattern):
        try:
            with open(path, encoding="utf-8") as fh:
                shard = json.load(fh)
            op, at = ((shard.get("_keys") or {}).get("jarvis") or {}).get(host)[:2]
        except (OSError, ValueError, AttributeError, TypeError):
            continue
        if at and at > newest:
            newest = at
            hidden = (op == "set"
                      and (shard.get("jarvis") or {}).get(host) is False)
    return hidden


def _console_title(text):
    """Retitle the console window; the .bat names it before Python starts."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(text)
    except Exception:                              # noqa: BLE001
        pass


def banner():
    """The thing the window opens with."""
    art = BLOCK if _fits(BLOCK) else PLAIN
    tint = _colour()
    cyan, dim, bold, off = (("\033[38;5;45m", "\033[38;5;245m",
                             "\033[1m", "\033[0m")
                            if tint else ("", "", "", ""))
    # Hidden on this machine: no wordmark, and the window is not called
    # Jarvis either. The interface has the switch that brings both back.
    hidden = _name_hidden()
    if hidden:
        _console_title("Workbench")
    lines = [""]
    lines.append("  " + dim + "Hello. " + off + bold + _greeting() + off)
    lines.append("")
    if not hidden:
        for row in art.strip("\n").splitlines():
            lines.append("  " + cyan + row + off)
        lines.append("")
    lines.append("  " + dim
                 + "a workbench for the recordings on this machine" + off)
    return "\n".join(lines)

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
    print(banner())
    if not check_deps():
        pause()
        return 1

    # This is the app, so it syncs. Tools and the harness import the same
    # module for its routes and do not set this, so they no longer run a
    # background sync loop of their own (backend/app.py, _cloud_loop).
    os.environ.setdefault("Jarvis_CLOUD_SYNC", "on")
    from backend.app import (app, refresh_catalog, warm_start,
                             REPO_ROOT, LOGS_DIR)
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

    # How the two accounts stand, one line each. Asking for them is Setup's
    # job now (setup.py -> backend/onboard.py, the user's ruling of
    # 2026-10-20): activating Jarvis just opens it.
    try:
        from backend import onboard
        print("  " + onboard.cloud_line(LOGS_DIR))
        print("  " + onboard.vacc_line(LOGS_DIR))
    except Exception as exc:                       # noqa: BLE001
        print("  (could not read the account settings: %s)" % exc)

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

    # The warm start, and this is the only place it is switched on.
    #
    # It hands the interface last boot's answer to the three roll-ups that
    # take five seconds each from cold, then recomputes all three behind the
    # page and tells it which -- if any -- actually changed. See
    # backend/warmcache.py for what bounds it; the short version is that the
    # window shuts as soon as the real answers are in hand or as soon as
    # somebody clicks something, whichever comes first.
    #
    # Only here, so a server started by the harness suite or by a script
    # reads the store live exactly as it always did.
    if os.environ.get("JARVIS_WARM", "1") != "0":
        warm_start()

    # The Precon1 -> Precon4 analysis carries on by itself if Jarvis or the
    # computer stopped while it ran (backend/preconrun.py). Only here, for
    # the same reason as the warm start: a harness server or a script that
    # imports the app must never start an hour of work.
    try:
        from backend.app import resume_precon
        resume_precon(port)
    except Exception as exc:                       # noqa: BLE001
        print("  (could not check for an interrupted analysis: %s)" % exc)

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
