"""
Jarvis -- launcher.

Windows: double-click "Wake up Jarvis.bat"
macOS:   double-click "Wake up Jarvis.command"
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


def banner():
    """The thing the window opens with."""
    art = BLOCK if _fits(BLOCK) else PLAIN
    tint = _colour()
    cyan, dim, bold, off = (("\033[38;5;45m", "\033[38;5;245m",
                             "\033[1m", "\033[0m")
                            if tint else ("", "", "", ""))
    lines = [""]
    lines.append("  " + dim + "Hello. " + off + bold + _greeting() + off)
    lines.append("")
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


def ask_for_key(logs_dir):
    """First start on a new machine: get the key, once.

    The repo carries the project id, so a clone already knows where to sync.
    What it deliberately does not carry is the key -- so somebody has to hand
    it over exactly once per machine, and the sensible moment is now, in the
    window they are already looking at, rather than in a README they will
    read afterwards.

    Skipping is a first-class answer. Jarvis writes locally first and works
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
        print("     one below. Jarvis is ignoring the one in the file.")

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
    print("  Press Enter to skip -- Jarvis works fine without it, and you")
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
            print("  Saved anyway; Jarvis will keep trying in the background.")
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


def ask_for_netid(logs_dir):
    """First start on a new machine: which VACC account is this.

    A NetID is the whole question. `<netid>@login.vacc.uvm.edu` is the
    account, `/gpfs1/home/<n>/<e>/<netid>` is the home directory and
    `/gpfs2/scratch/<netid>` is the scratch space -- all of it derived, so
    there is nothing else to ask for and no reason to ask for it twice.

    Deliberately no password here. Installing a key needs one, and a console
    that may be a double-clicked window is the wrong place to type one:
    there is no way to promise it was not echoed, and the Duo push that
    follows needs somebody watching. So this records the NetID, and the
    sign-in panel in the app does the part that needs a password -- in a
    password field, with the push explained, on a screen that can say what
    is happening while it waits.

    Skipping is a first-class answer, for the same reason it is for the
    cloud key: Jarvis runs entirely without the cluster, and start-up must
    never depend on somebody having a credential to hand.
    """
    from backend import vacc

    cfg = vacc.load_config(logs_dir)
    if cfg.get("configured"):
        print("  VACC    : %s@%s" % (cfg.get("netid"), cfg.get("host")))
        return
    if not cfg.get("needs_netid"):
        return
    if not vacc.have_ssh():
        # Nothing here can work without it, and saying so once is better
        # than every later button failing differently.
        print("  VACC    : no ssh client on this machine, so the cluster is "
              "out of reach")
        return

    print()
    print("  Jarvis can run Incisor and Panorama on the VACC, if you have")
    print("  an account. All it needs is your NetID -- the part of your UVM")
    print("  email before the @.")
    print()
    print("  It is stored in GUI_logs/.vacc.json, which git ignores.")
    print("  No password is asked for here: the one time one is needed, the")
    print("  Sign in to VACC panel in the app asks for it, installs an SSH")
    print("  key, and never asks again.")
    print()
    print("  Press Enter to skip.")
    print()

    if not sys.stdin or not sys.stdin.isatty():
        print("  (not a terminal, so skipping the question)")
        return

    try:
        netid = input("  UVM NetID: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not netid:
        print("  Skipped. Turn VACC Mode on later and it will offer to set "
              "this up.")
        return
    if not vacc.NETID_RE.match(netid):
        print("  That does not look like a NetID (letters and digits, no")
        print("  spaces, no @). Skipping -- the app can set it up later.")
        return

    vacc.save_config(logs_dir, netid=netid)
    keys = [k for k in vacc.existing_keys()]
    if keys:
        print("  Saved. There %s already %d SSH key%s on this machine; if one"
              % ("are" if len(keys) != 1 else "is", len(keys),
                 "s" if len(keys) != 1 else ""))
        print("  of them works on the cluster, Jarvis will use it. Otherwise")
        print("  open Sign in to VACC in the app and it will install one.")
    else:
        print("  Saved. Open Sign in to VACC in the app to install a key --")
        print("  that is the one time your password is needed.")


def main():
    print(banner())
    if not check_deps():
        pause()
        return 1

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

    # Before anything starts serving: if this machine has never been given
    # the sync key, ask for it here, where somebody is looking.
    try:
        ask_for_key(LOGS_DIR)
    except Exception as exc:                       # noqa: BLE001
        print("  (could not check the sync settings: %s)" % exc)

    # Same moment, same reason: the cluster needs a NetID and nothing else,
    # and a machine that has never been told one cannot offer to run
    # anything on it. Never fatal -- Jarvis runs entirely without a cluster.
    try:
        ask_for_netid(LOGS_DIR)
    except Exception as exc:                       # noqa: BLE001
        print("  (could not check the VACC settings: %s)" % exc)

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
