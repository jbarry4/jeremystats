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

import errno
import os
import socket
import subprocess
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
            # Not on Windows. There SO_REUSEADDR lets a bind succeed on a
            # port another Jarvis is LISTENING on (measured 2026-11-03: this
            # probe returned 8733 with a live server on it), so a second
            # launch shared the first one's port instead of taking the next.
            # Elsewhere it only skips TIME_WAIT, which is what it was for.
            if os.name != "nt":
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 0        # let the OS choose


# The child's exit code that means "start me again" (POST /api/restart in
# backend/app.py). 75 is EX_TEMPFAIL: a temporary stop, try again.
RESTART_CODE = 75

# The child's exit code for "the port you gave me belongs to someone else":
# the supervisor picks the next free one and starts it there. 98 is
# EADDRINUSE's number on Linux; nothing else here exits with it.
PORT_TAKEN = 98

# Whether the server's own bind failed because the port was in use.
_BIND = {"taken": False}


def _bind_exclusively():
    """Make the server's bind fail, not share, when the port is held.

    Werkzeug's server sets SO_REUSEADDR (allow_reuse_address = True). On
    Windows that lets a bind SUCCEED on a port another server is listening
    on, and the system then hands each connection to either of them --
    two servers, each with its own caches, sync loop and resumed work, on
    one address (the free_port note, 2026-11-03). Probing first does not
    close it: a second launch can probe in the seconds before the first
    one's child binds. So on Windows the server binds without it, and with
    SO_EXCLUSIVEADDRUSE so nothing can bind on top of it either. Elsewhere
    SO_REUSEADDR only skips TIME_WAIT and is kept. Either way, a bind that
    fails because the port is in use is noted in _BIND for `_serve`."""
    from werkzeug import serving
    cls = serving.BaseWSGIServer
    if getattr(cls, "_jarvis_exclusive", False):
        return
    if os.name == "nt":
        cls.allow_reuse_address = False
    plain = cls.server_bind

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET,
                                       socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        try:
            plain(self)
        except OSError as exc:
            # 10048 is Windows' "in use"; 10013 is what a bind gets on a
            # port another socket holds exclusively.
            if (exc.errno == errno.EADDRINUSE
                    or getattr(exc, "winerror", None) in (10048, 10013)):
                _BIND["taken"] = True
            raise

    cls.server_bind = server_bind
    cls._jarvis_exclusive = True


def main():
    """Two roles in one file.

    Launched normally, this is the SUPERVISOR: it prints the banner, checks
    the packages, picks the port, opens the browser once, and then runs the
    server as a child process, starting it again whenever it exits asking to
    be restarted. The point is a restart button that loads new code without
    a new window, a new port or a new browser tab -- the page reconnects to
    the same address and finds a new server behind it.

    Launched by the supervisor (JARVIS_CHILD=1), it is the SERVER: what this
    function did on its own before, from the catalogue onwards.
    """
    if os.environ.get("JARVIS_CHILD") == "1":
        return serve()
    return supervise()


def _tidy_launchers():
    """Before anything reads GUI_logs: carry across what the move from
    "BARRY GUI" to _Jarvis/app left in the old folder (the Supabase key and
    the VACC sign-in among it), give the Mac launchers back their run bit,
    and make this machine's shortcut. backend/launchers.py; standard library
    only, so it runs even when the dependencies are missing."""
    try:
        from backend import launchers
        left = launchers.leftovers()
        if left and left["moved"]:
            print("  Moved   : %d item(s) across from the old %s folder"
                  % (left["moved"], os.path.basename(left["from"])))
        if left and left["kept"]:
            print("  Left    : %d item(s) in %s -- see the note there"
                  % (len(left["kept"]), left["from"]))
        # The case that can lose work: the old folder has a copy written
        # AFTER the one this app is about to use (an old server still
        # running from there when the move was pulled). Said in full, every
        # start, until someone has dealt with it -- a count alone is easy to
        # read past, and the note is only seen by whoever opens the folder.
        if left and left.get("newer"):
            print("\n  CHECK   : %d file(s) in the old %s folder are NEWER "
                  "than the copy in use here." % (len(left["newer"]),
                                                  os.path.basename(left["from"])))
            print("            Nothing was overwritten. If the old app is "
                  "still open, close it, then compare these")
            print("            with the same files in %s before deleting "
                  "anything:" % HERE)
            for path in left["newer"]:
                print("              " + os.path.relpath(path, left["from"]))
            print()
        launchers.make_runnable()
        # A PowerShell start-up per launch; beside the boot, not before it.
        threading.Thread(target=launchers.make_shortcut, daemon=True,
                         name="shortcut").start()
    except Exception as exc:                       # noqa: BLE001
        print("  (could not tidy the launchers: %s)" % exc)


def supervise():
    print(banner())
    _tidy_launchers()
    if not check_deps():
        pause()
        return 1

    # JARVIS_PORT here is only where to start looking (a test's way of
    # keeping clear of the port a real Jarvis is using).
    try:
        preferred = int(os.environ.get("JARVIS_PORT") or 8733)
    except ValueError:
        preferred = 8733
    port = free_port(preferred)

    # What the browser opener needs, kept current by the loop below: the
    # port, and the name (`boot`) the running child answers /api/ping with,
    # so the page is opened on THIS server and not on another one that
    # happens to answer on the same port first.
    browser = os.environ.get("JARVIS_NO_BROWSER") != "1"
    target = {"port": port, "boot": "", "opened": False}

    def open_browser():
        threading.Thread(target=_open_when_up, args=(target,),
                         daemon=True, name="open-browser").start()

    env = dict(os.environ, JARVIS_CHILD="1", JARVIS_SUPERVISED="1",
               JARVIS_PORT=str(port))
    starts = 0
    moves = 0
    while True:
        env["JARVIS_STARTS"] = str(starts)
        target["boot"] = env["JARVIS_BOOT"] = os.urandom(6).hex()
        if browser and moves == 0 and starts == 0:
            open_browser()
        # What this process printed goes out before the child prints
        # anything, so the window reads in order even when it is a file.
        sys.stdout.flush()
        try:
            proc = subprocess.Popen([sys.executable,
                                     os.path.abspath(__file__)],
                                    env=env, cwd=HERE)
        except OSError as exc:
            print("\n  Could not start the server: %s" % exc)
            return 1
        code = _wait_child(proc)
        if code is None:
            print("\n  Stopped.")
            return 0
        if code == PORT_TAKEN and moves < 5:
            # Someone else holds the port (a second launch, most often).
            # Start again on the next free one. `starts` is not counted up:
            # nothing was served, so a first start is still one. A page
            # already open on the old port is on another server now, so
            # the browser is opened again on the new one.
            moves += 1
            taken, port = port, free_port(port + 1)
            if not port:
                print("\n  Could not find a free port after %d." % taken)
                return code
            print("\n  Port %d is in use by another program; starting on "
                  "%d instead." % (taken, port))
            env["JARVIS_PORT"] = str(port)
            target["port"] = port
            if browser and target["opened"]:
                target["opened"] = False
                open_browser()
            continue
        if code != RESTART_CODE:
            return code
        starts += 1
        print("\n  Restarting to load the new version.")


def _wait_child(proc):
    """The child's exit code, or None when Ctrl+C stopped it.

    Ctrl+C reaches both processes -- they share the console on Windows and
    the process group on macOS -- so the child is already on its way out;
    it is given a few seconds to finish, then made to.
    """
    try:
        return proc.wait()
    except KeyboardInterrupt:
        pass
    deadline = time.time() + 6.0
    while time.time() < deadline:
        try:
            if proc.poll() is not None:
                return None
            time.sleep(0.1)
        except KeyboardInterrupt:
            continue
    try:
        proc.kill()
    except OSError:
        pass
    return None


def _is_ours(port, boot):
    """Is the server answering on `port` the child this supervisor started?
    Asked through /api/ping, which reports the name the supervisor gave it.
    No proxy: a system proxy must never be asked for 127.0.0.1."""
    import json
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open("http://127.0.0.1:%d/api/ping" % port,
                         timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8")).get("boot") == boot
    except (OSError, ValueError, AttributeError):
        return False


def _open_when_up(target, limit_s=180.0):
    """Open the browser once, when this supervisor's server first answers.

    Not on a fixed timer: the server is a separate process now, and opening
    the page before it is listening shows the browser's own error page.
    Not on the first answer from the port either: during a second launch,
    the first launch's server can be the one answering there, and that
    window got a tab on a server that was not its own. `target` is read on
    every try, so a move to another port (PORT_TAKEN) is followed.
    """
    deadline = time.time() + limit_s
    while time.time() < deadline:
        port = target["port"]
        if _is_ours(port, target["boot"]):
            if target["port"] != port:
                continue        # moved while asking: ask the new port
            target["opened"] = True
            webbrowser.open("http://127.0.0.1:%d/" % port)
            return
        time.sleep(0.25)


def _wait_for_port(port, limit_s=10.0):
    """Wait for the port to be free again after a restart.

    The old server's socket is closed by the operating system when its
    process ends, which is usually before this runs -- usually. The test is
    free_port's rule: a plain bind on Windows, where SO_REUSEADDR would let
    it succeed on a port something is still LISTENING on; SO_REUSEADDR
    everywhere else, where a plain bind fails for as long as any TIME_WAIT
    socket is left on the port. The page holds keep-alive and stream
    connections when /api/restart exits, so on macOS there always are some
    (about 30 s of them), and every restart used to sit here for the full
    limit. With it, the bind fails only when something really listens.
    False past the limit: the port is held by something else."""
    deadline = time.time() + limit_s
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if os.name != "nt":
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                pass
        if time.time() > deadline:
            return False
        time.sleep(0.25)


# Set by serve() from what the supervisor handed over; see there.
SUPERVISED = False


def serve():
    """The server itself: the child the supervisor runs.

    The supervisor's variables are read once and then taken OUT of the
    environment, before anything else is imported. Left in, every process
    this server starts inherits them -- runner.py jobs, git, PowerShell, the
    terminal the Kilosort button opens with `cmd /k` -- and `python
    start.py` typed in that terminal saw JARVIS_CHILD=1, skipped the
    supervisor, and served on the live server's JARVIS_PORT beside it. A
    script or harness server started from such a terminal also claimed to
    be supervised, so its Restart stopped it for good. Whether this server
    may restart itself is told to backend/app.py directly (app.SUPERVISED),
    never through the environment."""
    global SUPERVISED
    SUPERVISED = os.environ.pop("JARVIS_SUPERVISED", None) == "1"
    os.environ.pop("JARVIS_CHILD", None)
    starts = os.environ.pop("JARVIS_STARTS", "0")
    boot = os.environ.pop("JARVIS_BOOT", "")
    try:
        port = int(os.environ.pop("JARVIS_PORT", "") or 0)
    except ValueError:
        port = 0
    supervised = SUPERVISED
    try:
        return _serve(first=starts == "0", port=port, boot=boot)
    except KeyboardInterrupt:
        # Ctrl+C while starting up. The supervisor says "Stopped."; a
        # traceback here would only be noise.
        if not supervised:
            print("\n  Stopped.")
        return 0


def _serve(first=True, port=0, boot=""):
    t_boot = time.time()
    from backend import feed as feedmod
    # The supervisor's name for this process, so its browser opener can
    # tell this server from another one answering on the same port (see
    # `_open_when_up`). /api/ping already reports feed.BOOT; it only has
    # to be one the supervisor knows. Still new on every start.
    if boot:
        feedmod.BOOT = boot
    feedmod.say("Starting the server" if first
                else "Starting the server again with the new version",
                kind="boot", key="boot", progress=[0, 3])

    # This is the app, so it syncs. Tools and the harness import the same
    # module for its routes and do not set this, so they no longer run a
    # background sync loop of their own (backend/app.py, _cloud_loop).
    os.environ.setdefault("Jarvis_CLOUD_SYNC", "on")
    from backend.app import (app, refresh_catalog, warm_start,
                             REPO_ROOT, LOGS_DIR)
    from backend import runner, sysinfo, video
    import backend.app as appmod
    appmod.SUPERVISED = SUPERVISED

    feedmod.say("Loaded the server's code in %.1f s" % (time.time() - t_boot),
                kind="boot", key="boot", progress=[1, 3])

    # The machine lines once per window: a restart is the same machine, and
    # printing them again would push what happened before off the screen.
    if first:
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

        # How the two accounts stand, one line each. Asking for them is
        # Setup's job now (setup.py -> backend/onboard.py, the user's ruling
        # of 2026-10-20): activating Jarvis just opens it.
        try:
            from backend import onboard
            print("  " + onboard.cloud_line(LOGS_DIR))
            print("  " + onboard.vacc_line(LOGS_DIR))
        except Exception as exc:                   # noqa: BLE001
            print("  (could not read the account settings: %s)" % exc)

    stale = runner.sweep_temp_files(REPO_ROOT)
    if stale and first:
        print("  Cleaned : %d leftover temp script(s)" % stale)
    video.cleanup_clips()

    t0 = time.time()
    cat = refresh_catalog()
    if first:
        print("  Indexed : %d scripts in %d sections (%.2fs)"
              % (len(cat["items"]), len(cat["sections"]), time.time() - t0))

    # The supervisor chose the port and the browser is pointed at it, so a
    # restart must come back on exactly that one -- waiting, if need be, for
    # the old server's socket to finish closing. Run on its own (no
    # supervisor), it picks one as it always did.
    #
    # Still held after the wait means another program has it -- most often a
    # second launch whose supervisor probed the port in the seconds before
    # this one's child bound it. Binding anyway is how two servers came to
    # share 8733 on Windows (see `_bind_exclusively`), so this server stops
    # with PORT_TAKEN instead, and the supervisor moves on to the next port.
    if port:
        if not _wait_for_port(port):
            print("  Port %d is in use by another program." % port)
            return PORT_TAKEN
    else:
        port = free_port()
    url = "http://127.0.0.1:%d/" % port
    if first:
        print("\n  Serving : " + url)
        print("  Stop    : Ctrl+C in this window\n")
    else:
        print("  Restarted : " + url + "\n")
    # The browser is the supervisor's business (`_open_when_up`), opened
    # once per window rather than once per server.

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

    feedmod.say("Ready" if first else "Restarted with the new version",
                kind="boot", level="ok", key="boot", done=True,
                progress=[3, 3], ms=(time.time() - t_boot) * 1000)

    # Threaded so a long-running job's log stream never blocks the UI.
    _bind_exclusively()
    try:
        app.run(host="127.0.0.1", port=port, debug=False,
                threaded=True, use_reloader=False)
    except SystemExit:
        # Werkzeug answers a failed bind with sys.exit(1). A port taken in
        # the moment between the wait above and this bind is the
        # supervisor's to solve, so it gets the code that says so.
        if _BIND["taken"]:
            return PORT_TAKEN
        raise
    except KeyboardInterrupt:
        # Under the supervisor, it says "Stopped." once for both.
        if not SUPERVISED:
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
