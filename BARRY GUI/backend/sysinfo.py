"""
sysinfo.py -- Platform abstraction so BARRY runs identically on Windows and macOS.

Everything OS-specific lives here: locating MATLAB and ffmpeg, revealing a path
in the file manager, killing a process tree, and opening the native file picker.
The rest of the backend stays platform-agnostic.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MAC


def describe():
    """A short human summary of the machine, for logs and the UI footer."""
    return {
        "os": "Windows" if IS_WINDOWS else ("macOS" if IS_MAC else "Linux"),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "python_exe": sys.executable,
        "hostname": platform.node(),
        "user": current_user(),
    }


def current_user():
    """Prefer the git identity -- that is who the work will be attributed to."""
    try:
        res = subprocess.run(["git", "config", "user.name"],
                             capture_output=True, text=True, timeout=10)
        name = (res.stdout or "").strip()
        if res.returncode == 0 and name:
            return name
    except Exception:
        pass
    try:
        import getpass
        return getpass.getuser()
    except Exception:
        return ""


# --------------------------------------------------------------------------
# MATLAB
# --------------------------------------------------------------------------
def find_matlab():
    """Locate the MATLAB executable, newest release first.

    Windows: C:\\Program Files\\MATLAB\\R20XXx\\bin\\matlab.exe
    macOS:   /Applications/MATLAB_R20XXx.app/bin/matlab
    """
    exe = shutil.which("matlab")
    if exe:
        return exe

    found = []
    if IS_WINDOWS:
        roots = [r"C:\Program Files\MATLAB", r"C:\Program Files (x86)\MATLAB"]
        for root in roots:
            if not os.path.isdir(root):
                continue
            try:
                entries = os.listdir(root)
            except OSError:
                continue
            for rel in entries:
                cand = os.path.join(root, rel, "bin", "matlab.exe")
                if os.path.isfile(cand):
                    found.append((rel, cand))
    else:
        # macOS installs land in /Applications as MATLAB_R2024b.app, but sites
        # also use /Applications/MATLAB/R2024b and per-user Applications, so
        # check a nested level too rather than assuming one shape.
        roots = ["/Applications", os.path.expanduser("~/Applications"),
                 "/Applications/MATLAB", "/opt/MATLAB", "/usr/local/MATLAB"]
        for root in roots:
            if not os.path.isdir(root):
                continue
            try:
                entries = os.listdir(root)
            except OSError:
                continue
            for rel in entries:
                name = rel.upper()
                if not (name.startswith("MATLAB") or name.startswith("R20")):
                    continue
                for cand in (os.path.join(root, rel, "bin", "matlab"),
                             os.path.join(root, rel, "Contents", "MacOS", "matlab")):
                    if os.path.isfile(cand):
                        found.append((rel, cand))
                        break

    if not found:
        return None
    found.sort(reverse=True)          # newest release name wins
    return found[0][1]


def matlab_release(path):
    """Pull the R20XXx release tag out of a MATLAB path, if present."""
    if not path:
        return None
    import re
    m = re.search(r"R20\d{2}[ab]", path)
    return m.group(0) if m else None


# --------------------------------------------------------------------------
# ffmpeg (needed for VT1.mpg video, which browsers cannot decode)
# --------------------------------------------------------------------------
def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    candidates = []
    if IS_WINDOWS:
        candidates = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            os.path.expanduser(r"~\scoop\shims\ffmpeg.exe"),
            os.path.expanduser(r"~\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"),
        ]
    else:
        candidates = [
            "/opt/homebrew/bin/ffmpeg",     # Apple silicon Homebrew
            "/usr/local/bin/ffmpeg",        # Intel Homebrew
            "/opt/local/bin/ffmpeg",        # MacPorts
        ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def find_ffprobe():
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    ff = find_ffmpeg()
    if not ff:
        return None
    cand = os.path.join(os.path.dirname(ff),
                        "ffprobe.exe" if IS_WINDOWS else "ffprobe")
    return cand if os.path.isfile(cand) else None


def ffmpeg_install_hint():
    """Copy-pasteable install instructions for whichever OS we are on."""
    if IS_WINDOWS:
        return ("Install ffmpeg, then restart BARRY GUI:\n"
                "    winget install Gyan.FFmpeg\n"
                "or download from https://www.gyan.dev/ffmpeg/builds/ and add "
                "its bin folder to PATH.")
    if IS_MAC:
        return ("Install ffmpeg, then restart BARRY GUI:\n"
                "    brew install ffmpeg\n"
                "(Homebrew: https://brew.sh)")
    return "Install ffmpeg with your package manager (e.g. apt install ffmpeg)."


# --------------------------------------------------------------------------
# Process control
# --------------------------------------------------------------------------
def popen_kwargs():
    """Extra Popen kwargs so a child can be killed as a group."""
    if IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    # POSIX: give the child its own process group so we can signal the whole tree.
    return {"start_new_session": True}


def kill_tree(proc):
    """Kill a process and everything it spawned. MATLAB especially needs this."""
    if proc is None:
        return False
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=20)
        else:
            import signal
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
        return True
    except Exception:
        try:
            proc.kill()
            return True
        except Exception:
            return False


# --------------------------------------------------------------------------
# File manager
# --------------------------------------------------------------------------
def reveal(path):
    """Show a file or folder in Explorer / Finder."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if IS_WINDOWS:
        if os.path.isdir(path):
            subprocess.Popen(["explorer", path])
        else:
            subprocess.Popen(["explorer", "/select,", path])
    elif IS_MAC:
        if os.path.isdir(path):
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", path if os.path.isdir(path)
                          else os.path.dirname(path)])


def default_roots():
    """Sensible starting points for the folder browser on this machine."""
    roots = []
    home = os.path.expanduser("~")
    if IS_WINDOWS:
        import string
        for letter in string.ascii_uppercase:
            drive = letter + ":\\"
            if os.path.exists(drive):
                roots.append({"name": drive, "path": drive})
    else:
        roots.append({"name": "/", "path": "/"})
        for name in ("Volumes",):
            p = os.path.join("/", name)
            if os.path.isdir(p):
                roots.append({"name": "/" + name, "path": p})
    roots.append({"name": "Home", "path": home})
    for name in ("Desktop", "Documents", "Downloads"):
        p = os.path.join(home, name)
        if os.path.isdir(p):
            roots.append({"name": name, "path": p})
    return roots
