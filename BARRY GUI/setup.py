"""
BARRY GUI -- one-time setup.

Run this once per machine (or double-click "Setup Windows.bat" /
"Setup Mac.command"). It installs the Python packages BARRY needs, then checks
for the two optional external tools -- MATLAB and ffmpeg -- and tells you
exactly what to do if either is missing.

It never installs anything without asking, and it never touches your data.
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BANNER = r"""
  ___   _   ___ _____   __  ___ _   _ ___     ___      _
 | _ ) /_\ | _ \ _ \ \ / / / __| | | |_ _|   / __| ___| |_ _  _ _ __
 | _ \/ _ \|   /   /\ V / | (_ | |_| || |    \__ \/ -_)  _| || | '_ \
 |___/_/ \_\_|_\_|_\ |_|   \___|\___/|___|   |___/\___|\__|\_,_| .__/
                                                               |_|
"""

MIN_PYTHON = (3, 9)

# requirements.txt is the single source of truth for WHAT is needed; this table
# only supplies the human explanation and whether BARRY can run without it.
# Keeping the list in one place means the two cannot drift apart.
PACKAGE_INFO = {
    "flask":      ("the local web server", True),
    "numpy":      ("array maths", True),
    "scipy":      ("filters, spectrograms, .mat reading", True),
    "matplotlib": ("figure rendering and export", True),
    "h5py":       ("MATLAB v7.3 .mat files (most converted CSC files)", False),
    "pandas":     ("CSV / Excel event imports", False),
    "openpyxl":   (".xlsx event files", False),
}

# pip name -> module name, where they differ.
IMPORT_NAME = {"openpyxl": "openpyxl"}

REQ_RE = None


def read_requirements():
    """Parse requirements.txt into (pip_name, spec, why, required) rows."""
    import re
    global REQ_RE
    if REQ_RE is None:
        REQ_RE = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(.*)$")

    path = os.path.join(HERE, "requirements.txt")
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        # Fall back to the descriptions we know about, so setup still works
        # even if requirements.txt has gone missing.
        for name, (why, req) in PACKAGE_INFO.items():
            rows.append((name, "", why, req))
        return rows

    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = REQ_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        spec = (m.group(2) or "").strip()
        why, required = PACKAGE_INFO.get(name.lower(), ("", False))
        rows.append((name, spec, why, required))
    return rows


def c(text, color):
    """Color, but only where the terminal will actually render it."""
    if os.name == "nt" and not os.environ.get("WT_SESSION"):
        return text
    codes = {"green": "92", "yellow": "93", "red": "91", "dim": "90", "bold": "1"}
    return "\033[%sm%s\033[0m" % (codes.get(color, "0"), text)


def ok(msg):
    print("  " + c("[ok]", "green") + "   " + msg)


def warn(msg):
    print("  " + c("[--]", "yellow") + "   " + msg)


def bad(msg):
    print("  " + c("[!!]", "red") + "   " + msg)


def ask(question, default=True):
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input("  " + question + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


def indent(text, pad="     "):
    """Indent a multi-line hint so it lines up under the status markers."""
    return "\n".join(pad + line for line in str(text).splitlines())


def have(mod):
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def pip_install(packages):
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + packages
    print("\n  Running: " + " ".join(cmd) + "\n")
    try:
        return subprocess.call(cmd) == 0
    except Exception as exc:
        bad("Could not run pip: %s" % exc)
        return False


# --------------------------------------------------------------------------
def check_python():
    print(c("\n1. Python", "bold"))
    v = sys.version_info
    print("     %d.%d.%d at %s" % (v.major, v.minor, v.micro, sys.executable))
    if v[:2] < MIN_PYTHON:
        bad("BARRY needs Python %d.%d or newer." % MIN_PYTHON)
        print("     Install a newer Python from https://www.python.org/downloads/")
        return False
    ok("Version is fine.")
    return True


def installed_version(pip_name):
    """Installed version string, or None if the package is absent."""
    mod = IMPORT_NAME.get(pip_name.lower(), pip_name.lower())
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            return version(pip_name)
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    # Some packages import fine without clean metadata; fall back to importing.
    return "present" if have(mod) else None


def version_ok(have_ver, spec):
    """Check an installed version against a '>=x.y' style requirement."""
    if not spec or not have_ver or have_ver == "present":
        return True
    import re
    m = re.match(r"^(>=|==|>)\s*([0-9][0-9A-Za-z.\-]*)$", spec.replace(" ", ""))
    if not m:
        return True                      # nothing we can usefully compare
    op, want = m.group(1), m.group(2)

    def parts(v):
        out = []
        for chunk in str(v).split("."):
            digits = "".join(ch for ch in chunk if ch.isdigit())
            out.append(int(digits) if digits else 0)
        return out

    a, b = parts(have_ver), parts(want)
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    if op == "==":
        return a == b
    if op == ">":
        return a > b
    return a >= b


def check_packages():
    print(c("\n2. Python packages", "bold"))
    rows = read_requirements()

    todo, missing_req, outdated = [], [], []
    for pip_name, spec, why, required in rows:
        ver = installed_version(pip_name)
        label = "%-12s %s" % (pip_name, why or "")
        if ver is None:
            (bad if required else warn)(label + "  -- NOT INSTALLED")
            todo.append(pip_name + spec)
            if required:
                missing_req.append(pip_name)
        elif not version_ok(ver, spec):
            warn(label + "  -- have %s, need %s" % (ver, spec))
            todo.append(pip_name + spec)
            outdated.append(pip_name)
        else:
            ok(label + ("  (%s)" % ver if ver != "present" else ""))

    if not todo:
        ok("Everything BARRY needs is already installed.")
        return True

    print()
    if missing_req:
        print("  " + c("Required packages are missing: ", "red")
              + ", ".join(missing_req))
    optional_missing = [t for t in todo
                        if t.split(">")[0].split("=")[0] not in missing_req
                        and t.split(">")[0].split("=")[0] not in outdated]
    if optional_missing:
        print("  Optional but recommended: " + ", ".join(optional_missing))
    if outdated:
        print("  Too old: " + ", ".join(outdated))

    if not ask("Install/upgrade them now with pip?", True):
        warn("Skipped. Install them yourself with:")
        print("       %s -m pip install -r \"%s\""
              % (sys.executable, os.path.join(HERE, "requirements.txt")))
        return not missing_req

    if not pip_install(todo):
        bad("pip failed. Try again from a terminal opened as administrator, or "
            "install manually with the command above.")
        return False

    still = [n for n, spec, why, required in rows
             if required and installed_version(n) is None]
    if still:
        bad("Still missing after install: " + ", ".join(still))
        return False
    ok("Packages installed.")
    return True


def check_matlab():
    print(c("\n3. MATLAB (needed for the IED pipeline stages)", "bold"))
    try:
        from backend import sysinfo
    except Exception as exc:
        warn("Could not load BARRY's platform helper yet (%s)." % exc)
        return
    exe = sysinfo.find_matlab()
    if exe:
        rel = sysinfo.matlab_release(exe) or ""
        ok("Found MATLAB %s" % (rel or "").strip())
        print("     " + exe)
        return "%s  (%s)" % (rel or "found", exe)

    warn("MATLAB not found.")
    print("     The Python half of BARRY works fine without it; the MATLAB")
    print("     pipeline stages will be grayed out.")
    if sysinfo.IS_MAC:
        print("     Looked in /Applications, ~/Applications and $PATH.")
        print("     Expected something like /Applications/MATLAB_R2024b.app")
        print("     If MATLAB is installed elsewhere, add its bin folder to PATH.")
    else:
        print("     Looked in C:\\Program Files\\MATLAB, "
              "C:\\Program Files (x86)\\MATLAB and PATH.")
        print("     Expected something like C:\\Program Files\\MATLAB\\R2023b")
    return None


def check_ffmpeg():
    print(c("\n4. ffmpeg (needed to play VT1.mpg session video)", "bold"))
    try:
        from backend import sysinfo
    except Exception:
        return
    exe = sysinfo.find_ffmpeg()
    if exe:
        ok("Found ffmpeg")
        print("     " + exe)
        return exe

    warn("ffmpeg not found.")
    print("     Everything except video playback works without it.")
    print("     Neuralynx VT1.mpg is MPEG-1, which no browser can decode, so")
    print("     BARRY transcodes a few seconds at a time using ffmpeg.")
    print()

    if sysinfo.IS_WINDOWS:
        if ask("Try installing it now with winget?", True):
            try:
                rc = subprocess.call(["winget", "install", "--id", "Gyan.FFmpeg",
                                      "-e", "--accept-package-agreements",
                                      "--accept-source-agreements"])
                if rc == 0:
                    ok("ffmpeg installed. Open a NEW terminal so PATH refreshes.")
                    return sysinfo.find_ffmpeg() or "installed (restart terminal)"
                else:
                    warn("winget did not complete (exit %d)." % rc)
                    print(indent(sysinfo.ffmpeg_install_hint()))
            except FileNotFoundError:
                warn("winget is not available on this machine.")
                print(indent(sysinfo.ffmpeg_install_hint()))
        else:
            print(indent(sysinfo.ffmpeg_install_hint()))
    elif sysinfo.IS_MAC:
        brew = subprocess.call(["which", "brew"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) == 0
        if brew:
            if ask("Try installing it now with Homebrew?", True):
                rc = subprocess.call(["brew", "install", "ffmpeg"])
                if rc == 0:
                    ok("ffmpeg installed.")
                    return sysinfo.find_ffmpeg() or "installed"
                warn("brew install failed (exit %d)." % rc)
        else:
            warn("Homebrew is not installed.")
            print("     Install it first:")
            print('       /bin/bash -c "$(curl -fsSL '
                  'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')
            print("     then:  brew install ffmpeg")
    else:
        print(indent(sysinfo.ffmpeg_install_hint()))

    return sysinfo.find_ffmpeg()


def check_repo():
    print(c("\n5. Repo and logs", "bold"))
    repo = os.path.abspath(os.path.join(HERE, ".."))
    print("     Repo:     " + repo)
    logs = os.path.join(HERE, "GUI_logs")
    print("     GUI_logs: " + logs)

    try:
        from backend import registry
        n = len(registry.scan_repo(repo))
        ok("Indexed %d scripts." % n)
    except Exception as exc:
        warn("Could not index the repo yet: %s" % exc)

    try:
        res = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                             cwd=repo, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and (res.stdout or "").strip() == "true":
            ok("This is a git repo -- GUI_logs will sync through it.")
            who = subprocess.run(["git", "config", "user.name"], cwd=repo,
                                 capture_output=True, text=True, timeout=10)
            name = (who.stdout or "").strip()
            if name:
                print("     Your work will be attributed to: " + name)
            else:
                warn("git user.name is not set. Set it so runs are attributed:")
                print('       git config --global user.name "Your Name"')
        else:
            warn("Not a git repo -- GUI_logs will still be written, just not synced.")
    except Exception:
        warn("git not found -- GUI_logs will be written but cannot be synced.")


def main():
    print(BANNER)
    print("  Setting up BARRY GUI in:\n     " + HERE)

    py_ok = check_python()

    # Every check runs even when an earlier one failed. Bailing out early is
    # exactly wrong here: if packages are missing you still want to know
    # whether MATLAB and ffmpeg are present before you go fix things.
    pkg_ok = check_packages() if py_ok else False
    matlab = check_matlab()
    ffmpeg = check_ffmpeg()
    check_repo()

    print(c("\n" + "=" * 66, "dim"))
    if py_ok and pkg_ok:
        print(c("  Setup complete.", "green"))
    else:
        print(c("  Setup incomplete -- see the [!!] lines above.", "red"))

    print("\n  Summary")
    print("    Python packages : " + ("ready" if pkg_ok else "MISSING (required)"))
    print("    MATLAB          : " + (matlab or "not found -- MATLAB pipeline stages disabled"))
    print("    ffmpeg          : " + (ffmpeg or "not found -- session video disabled"))

    if py_ok and pkg_ok:
        if os.name == "nt":
            print('\n  Start BARRY by double-clicking "Start BARRY GUI.bat"')
        else:
            print('\n  Start BARRY by double-clicking "Start BARRY GUI.command"')
    print(c("=" * 66, "dim"))
    finish(0 if (py_ok and pkg_ok) else 1)
    return 0 if (py_ok and pkg_ok) else 1


def finish(code):
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\n  Press Enter to close...")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    sys.exit(main())
