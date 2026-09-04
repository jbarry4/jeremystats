"""
spikesort.py -- Getting Kilosort and Phy working, and then working with them.

Kilosort is not hard to run. It is hard to *start* running, because the first
attempt fails for one of about eight reasons and the error rarely says which:
no CUDA build of torch, a probe file that does not match the recording, a
binary written with the wrong channel count, bad channels given as 1-64 when
Kilosort counts from 0. Every one of those is checkable in advance, and none
of them is checked by anything today.

So this module does two things:

    check()     one honest answer per requirement -- present, wrong version,
                or missing -- with the exact command that fixes it
    plan()      what a run would do to a specific recording, resolved against
                what is actually on disk, before anything is launched

The lab's existing workflow is the shape this follows, not a replacement for
it: MATLAB writes CSC_Raw.dat, a .prb describes the probe, a settings .json
holds the Kilosort parameters, and results land in a folder named after the
thresholds. That workflow is in Kilosort/Kilosort-4_additional_code and it
works; what it lacks is a way to see, without running it, whether this machine
can run it at all.

One thing here is a genuine improvement rather than a wrapper: bad channels.
Kilosort takes them as 0-based indices, the lab records them as CSC numbers,
and BARRY already knows which channels were marked bad for the recording. That
conversion is done here, once, with the off-by-one written down, rather than
in each person's head.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys

from . import sysinfo

# Where the lab keeps the pieces. Relative to the repo root, so a clone on
# another machine finds them at the same place.
KIT = os.path.join("Kilosort", "Kilosort-4_additional_code")
PROBE_DIR = os.path.join(KIT, "Probes")
SETTINGS_DIR = os.path.join(KIT, "automate_kilosort")
CONVERTER_DIR = os.path.join(KIT, "neuralynx  converter")

# What Kilosort 4 needs, in the order it needs them.
# torch publishes wheels for a range of Python versions and nothing outside
# it. Asking pip to install torch on a version it does not build for gives
# "from versions: none", which reads like a network problem and is not one.
TORCH_MIN = (3, 9)
TORCH_MAX = (3, 13)

REQUIREMENTS = [
    {
        "id": "python",
        "name": "Python",
        "why": "Kilosort 4 is a Python package, and torch only publishes "
               "builds for Python %d.%d to %d.%d -- outside that, pip says "
               "\"from versions: none\", which looks like a network problem "
               "and is not one."
               % (TORCH_MIN + TORCH_MAX),
        "fix": None,
    },
    {
        "id": "torch",
        "name": "PyTorch",
        "why": "Kilosort does its work on tensors. The CPU build runs, but a "
               "session that takes twenty minutes on a GPU takes hours.",
        "fix": "pip install torch --index-url "
               "https://download.pytorch.org/whl/cu124",
    },
    {
        "id": "cuda",
        "name": "A GPU torch can see",
        "why": "Not required, but the difference between an afternoon and a "
               "coffee break.",
        "fix": "Install the CUDA build of torch (above). If torch is already "
               "installed as the CPU build, uninstall it first: "
               "pip uninstall torch",
    },
    {
        "id": "kilosort",
        "name": "Kilosort 4",
        "why": "The sorter itself.",
        "fix": "pip install kilosort",
    },
    {
        "id": "phy",
        "name": "Phy",
        "why": "For looking at what Kilosort decided and changing your mind.",
        "fix": "pip install phy --pre --upgrade",
    },
    {
        "id": "matlab",
        "name": "MATLAB",
        "why": "Only for the .ncs to binary conversion the lab currently "
               "does in MATLAB. Not needed if the binary already exists.",
        "fix": None,
    },
    {
        "id": "probes",
        "name": "A probe file",
        "why": "Kilosort needs the geometry, or every cluster lands in the "
               "wrong place.",
        "fix": None,
    },
]


def _run(args, timeout=25):
    try:
        res = subprocess.run(args, capture_output=True, text=True,
                             timeout=timeout, **sysinfo.popen_kwargs())
        return res.returncode, (res.stdout or "") + (res.stderr or "")
    except Exception as exc:                       # noqa: BLE001
        return -1, str(exc)


PROBE_SNIPPET = (
    "import json,sys\n"
    "out={}\n"
    "try:\n"
    "    import torch\n"
    "    out['torch']=torch.__version__\n"
    "    out['cuda']=bool(torch.cuda.is_available())\n"
    "    out['cuda_build']=getattr(torch.version,'cuda',None)\n"
    "    if out['cuda']:\n"
    "        out['gpu']=torch.cuda.get_device_name(0)\n"
    "except Exception as e:\n"
    "    out['torch_error']=str(e)\n"
    "try:\n"
    "    import kilosort\n"
    "    out['kilosort']=getattr(kilosort,'__version__','installed')\n"
    "except Exception as e:\n"
    "    out['kilosort_error']=str(e)\n"
    "try:\n"
    "    import phy\n"
    "    out['phy']=getattr(phy,'__version__','installed')\n"
    "except Exception as e:\n"
    "    out['phy_error']=str(e)\n"
    "print(json.dumps(out))\n"
)


def torch_supports(version):
    """(ok, why) for a (major, minor) tuple."""
    if not version:
        return False, "unknown version"
    if version < TORCH_MIN:
        return False, "too old for torch"
    if version > TORCH_MAX:
        return False, ("torch has no build for Python %d.%d" % version)
    return True, ""


def _version_of(exe):
    code, out = _run([exe, "-c",
                      "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
                     timeout=30)
    for line in (out or "").splitlines():
        line = line.strip()
        if re.fullmatch(r"\d+\.\d+\.\d+", line):
            return line
    return None


def interpreters():
    """Every Python on this machine, and whether torch can run on it.

    Worth doing rather than telling somebody to go and install one: the
    machine that hit this already had two usable versions sitting there, and
    every Kilosort route here already accepts a `python` argument. So the fix
    is a dropdown, not a download.
    """
    seen, out = set(), []

    def add(exe, note=""):
        exe = (exe or "").strip().strip('"')
        if not exe or not os.path.isfile(exe):
            return
        real = os.path.normcase(os.path.abspath(exe))
        if real in seen:
            return
        seen.add(real)
        ver = _version_of(exe)
        tup = tuple(int(x) for x in ver.split(".")[:2]) if ver else None
        ok, why = torch_supports(tup)
        out.append({
            "path": exe, "version": ver, "usable": ok, "why": why,
            "current": real == os.path.normcase(os.path.abspath(sys.executable)),
            "note": note,
        })

    add(sys.executable, "the one BARRY is running on")

    # The Windows launcher knows about every registered install.
    code, listing = _run(["py", "-0p"], timeout=30)
    if code == 0:
        for line in (listing or "").splitlines():
            m = re.search(r"(-V:[^\s]+)\s+\*?\s*(.+\.exe)\s*$", line.strip())
            if m:
                add(m.group(2), m.group(1).replace("-V:", "Python "))

    for pat in (r"C:\Python3*\python.exe",
                r"C:\Users\*\AppData\Local\Programs\Python\Python3*"
                r"\python.exe",
                r"C:\Users\*\anaconda3\python.exe",
                r"C:\Users\*\miniconda3\python.exe",
                r"C:\ProgramData\anaconda3\python.exe"):
        for hit in glob.glob(pat):
            add(hit)

    # Best first: usable, then newest.
    out.sort(key=lambda i: (not i["usable"],
                            [-int(x) for x in (i["version"] or "0")
                             .split(".")]))
    return out


def probe_environment(python=None):
    """Ask a Python interpreter what it has, by importing rather than guessing.

    `pip show` lies when two environments are on the PATH, and a torch that
    imports but cannot see the GPU is the single most common reason a run
    takes six hours. Importing in the interpreter that would actually run the
    job is the only answer worth printing.
    """
    exe = python or sys.executable
    code, out = _run([exe, "-c", PROBE_SNIPPET], timeout=90)
    for line in reversed((out or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"error": (out or "").strip()[:400] or "no answer"}


def probe_files(repo_root):
    """Every probe geometry the lab has, with a note of what it describes."""
    folder = os.path.join(repo_root, PROBE_DIR)
    out = []
    for name in sorted(_ls(folder)):
        if not name.lower().endswith((".prb", ".json", ".mat")):
            continue
        path = os.path.join(folder, name)
        note, n_chan = _probe_note(path)
        out.append({"name": name, "path": path, "note": note,
                    "channels": n_chan,
                    "kind": name.rsplit(".", 1)[-1].lower()})
    return out


def _probe_note(path):
    """A one-line description, and how many channels it covers.

    Two shapes to read. A .prb is Python with a comment block at the top, and
    the first comment that is not just the filename is the description people
    wrote for themselves. A geometry .json has no comments, so the description
    is assembled from what it contains.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(20000)
    except OSError:
        return "", None

    if path.lower().endswith(".json"):
        return _geometry_note(head)

    note = ""
    base = os.path.basename(path).lower()
    for line in head.splitlines():
        t = line.strip()
        if not t.startswith("#"):
            break                      # past the comment block
        t = t.lstrip("#").strip()
        if t and base[:6] not in t.lower():
            note = t
            break

    # Channels: count the list Kilosort will actually read, which is the
    # 'channels' array. Counting geometry entries instead is off by one on
    # probe_config.prb, because its channel_groups keys are floats and the
    # geometry has one fewer entry than the channel list.
    total = 0
    for block in re.findall(r"['\"]channels['\"]\s*:\s*\[([^\]]*)\]",
                            head, re.S):
        total += len([x for x in block.split(",") if x.strip()])
    n = total or None
    if not n:
        n = len(re.findall(r"^\s*(\d+)\s*:\s*[\[(]", head, re.M)) or None
    if not n:
        m = re.search(r"(\d+)\s*ch(?:annel)?", head, re.I)
        n = int(m.group(1)) if m else None
    return note, n


def _geometry_note(head):
    """Describe a probeinterface-style geometry file from its contents."""
    try:
        data = json.loads(head)
    except ValueError:
        return "probe geometry", None
    probes = data.get("probes") if isinstance(data, dict) else None
    if isinstance(probes, list) and probes:
        p = probes[0]
        n = len(p.get("contact_positions") or []) or None
        name = ((p.get("annotations") or {}).get("model_name")
                or (p.get("annotations") or {}).get("name") or "probe")
        return "%s geometry, %s contacts" % (name, n or "?"), n
    for key in ("contact_positions", "positions", "geometry", "channels"):
        v = data.get(key) if isinstance(data, dict) else None
        if isinstance(v, (list, dict)) and v:
            return "probe geometry, %d entries" % len(v), len(v)
    return "probe geometry", None


def settings_files(repo_root):
    out = []
    for folder in (os.path.join(repo_root, SETTINGS_DIR),
                   os.path.join(repo_root, PROBE_DIR)):
        for name in sorted(_ls(folder)):
            if not name.lower().endswith(".json"):
                continue
            path = os.path.join(folder, name)
            data = _read_settings(path)
            if data is None or "main" not in data:
                continue
            main = data.get("main") or {}
            out.append(jsonsafe({
                "name": name, "path": path,
                "n_chan_bin": main.get("n_chan_bin"),
                "fs": main.get("fs"),
                "Th_universal": main.get("Th_universal"),
                "Th_learned": main.get("Th_learned"),
            }))
    return out


def _read_settings(path):
    """The lab's settings file contains bare Infinity, which Python's decoder
    accepts and the JSON spec does not. Read it as written."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.loads(fh.read())
    except (OSError, ValueError):
        return None


def jsonsafe(value):
    """Replace non-finite numbers so the result is actually valid JSON.

    Kilosort settings use Infinity to mean "no limit" -- tmax, and the
    artifact threshold -- and Python happily writes that back out as a bare
    `Infinity` token. Every browser's JSON.parse then rejects the whole
    response, so one setting nobody looks at breaks the entire pane with a
    syntax error that names none of this.

    None means the same thing here (no limit) and survives the trip. The file
    on disk is untouched: the run reads the real settings, not this copy.
    """
    if isinstance(value, dict):
        return {k: jsonsafe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonsafe(v) for v in value]
    if isinstance(value, float) and (value != value or value in (
            float("inf"), float("-inf"))):
        return None
    return value


def check(repo_root, python=None):
    """One row per requirement: what is here, what is not, how to fix it."""
    env = probe_environment(python)
    exe = python or sys.executable
    matlab = sysinfo.find_matlab()
    probes = probe_files(repo_root)

    def row(rid, ok, detail, extra=None):
        base = next(r for r in REQUIREMENTS if r["id"] == rid)
        out = dict(base)
        out.update({"ok": bool(ok), "detail": detail})
        if extra:
            out.update(extra)
        return out

    here = _version_of(exe) if python else ".".join(
        str(v) for v in sys.version_info[:3])
    tup = tuple(int(x) for x in here.split(".")[:2]) if here else None
    py_ok, py_why = torch_supports(tup)
    others = interpreters()
    usable = [i for i in others if i["usable"] and not i["current"]]

    rows = [
        row("python", py_ok,
            "%s  (%s)%s" % (here, exe, "" if py_ok else "  -- " + py_why),
            {"fix": (("Point Kilosort at Python %s instead: %s"
                      % (usable[0]["version"], usable[0]["path"]))
                     if usable else
                     ("Install Python %d.%d-%d.%d and point Kilosort at it. "
                      "Nothing else on this machine has to change."
                      % (TORCH_MIN + TORCH_MAX)))} if not py_ok else None),
        row("torch",
            bool(env.get("torch")),
            env.get("torch") and ("torch " + env["torch"] + (
                "  built for CUDA " + env["cuda_build"]
                if env.get("cuda_build") else "  CPU-only build"))
            or (env.get("torch_error") or "not installed")),
        row("cuda",
            bool(env.get("cuda")),
            env.get("gpu") or (
                "torch is installed but sees no GPU"
                if env.get("torch") else "torch is not installed"),
            {"severity": "advice"}),
        row("kilosort", bool(env.get("kilosort")),
            env.get("kilosort") and ("kilosort " + str(env["kilosort"]))
            or (env.get("kilosort_error") or "not installed")),
        row("phy", bool(env.get("phy")),
            env.get("phy") and ("phy " + str(env["phy"]))
            or (env.get("phy_error") or "not installed"),
            {"severity": "advice"}),
        row("matlab", bool(matlab),
            matlab or "not found -- only needed to make the binary",
            {"severity": "advice"}),
        row("probes", bool(probes),
            "%d probe file(s) in %s" % (len(probes), PROBE_DIR)
            if probes else "none found in " + PROBE_DIR),
    ]

    blocking = [r for r in rows if not r["ok"]
                and r.get("severity") != "advice"]
    return {
        "rows": rows,
        # Every Python here, so the pane can offer one rather than telling
        # somebody to go and read the torch release notes.
        "interpreters": others,
        "python_ok": py_ok,
        "python_version": here,
        "suggest_python": usable[0]["path"] if usable else None,
        "ready": not blocking,
        "blocking": [r["id"] for r in blocking],
        "python": exe,
        "env": env,
        "probes": probes,
        "settings": settings_files(repo_root),
        # Everything in one line, for someone who would rather just paste it.
        "install_all": (
            "\"%s\" -m pip install torch --index-url "
            "https://download.pytorch.org/whl/cu124 && "
            "\"%s\" -m pip install kilosort phy --pre --upgrade"
            % (((usable[0]["path"] if usable and not py_ok else exe),) * 2)),
    }


# ==========================================================================
# Planning a run against one recording
# ==========================================================================
BINARY_NAMES = ("CSC_Raw.dat", "CSC_raw.dat", "raw.dat", "continuous.dat")


def find_binary(session_path):
    """The binary Kilosort would read, if the conversion has been done."""
    for name in BINARY_NAMES:
        p = os.path.join(session_path, name)
        if os.path.isfile(p):
            return p
    for name in sorted(_ls(session_path)):
        if name.lower().endswith((".dat", ".bin")):
            return os.path.join(session_path, name)
    return None


def results_dirs(session_path):
    """Runs already done here, newest first."""
    out = []
    for name in sorted(_ls(session_path)):
        folder = os.path.join(session_path, name)
        if not os.path.isdir(folder) or not name.lower().startswith("kilosort"):
            continue
        params = os.path.join(folder, "params.py")
        out.append({
            "name": name,
            "path": folder,
            "done": os.path.isfile(params),
            "params": params if os.path.isfile(params) else None,
            "at": _mtime(folder),
            "clusters": _cluster_count(folder),
        })
    out.sort(key=lambda d: d["at"] or "", reverse=True)
    return out


def _cluster_count(folder):
    p = os.path.join(folder, "cluster_group.tsv")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return max(0, sum(1 for _ in fh) - 1)
    except OSError:
        return None


def results_name(settings, invert):
    """The lab's naming scheme, kept exactly: the folder says what made it.

    tl / tu / fs / invert in the name means you can tell two runs apart
    months later without opening either.
    """
    main = (settings or {}).get("main") or {}
    tl = str(main.get("Th_learned", ""))[:1]
    tu = str(main.get("Th_universal", ""))[:1]
    fs = str(main.get("fs", ""))
    return "kilosort_tl%s_tu%s_fs%sinvert_%s" % (tl, tu, fs, bool(invert))


def bad_channels_for_kilosort(csc_numbers):
    """CSC numbers to Kilosort channel indices.

    The .ncs files are CSC1..CSC64 and Kilosort counts rows from zero, so
    CSC14 is index 13. This is the off-by-one that quietly excludes the wrong
    channel, and it is worth doing in one place with the reason written down
    rather than in each person's head at 6pm.
    """
    out = []
    for c in sorted({int(c) for c in (csc_numbers or [])}):
        if c >= 1:
            out.append(c - 1)
    return out


def plan(repo_root, session_path, probe, settings_path, bad_csc=(),
         invert=True, python=None):
    """What a run would do, resolved against what is actually on disk.

    Nothing is launched. The point is that every reason this would fail is
    visible before it takes an hour to fail.
    """
    settings = _read_settings(settings_path) if settings_path else None
    main = (settings or {}).get("main") or {}
    binary = find_binary(session_path) if session_path else None
    probe_path = probe if probe and os.path.isabs(probe) else (
        os.path.join(repo_root, PROBE_DIR, probe) if probe else None)
    _note, probe_chans = (_probe_note(probe_path)
                          if probe_path and os.path.isfile(probe_path)
                          else ("", None))

    n_chan = main.get("n_chan_bin")
    size = os.path.getsize(binary) if binary and os.path.isfile(binary) else 0
    # int16, n_chan interleaved: the file length has to divide evenly, and
    # when it does not the channel count is wrong -- which otherwise shows up
    # as a sort that "worked" and put every unit in the wrong place.
    per_sample = (n_chan or 0) * 2
    samples = (size // per_sample) if per_sample else 0
    remainder = (size % per_sample) if per_sample else 0
    fs = main.get("fs") or 0
    out_dir = os.path.join(session_path, results_name(settings, invert)) \
        if session_path else None

    problems = []
    if not binary:
        problems.append({
            "what": "There is no binary in this folder.",
            "why": "Kilosort reads a flat int16 file, not .ncs. The lab makes "
                   "it in MATLAB with perpl_NLX2Binary.m / "
                   "create_kilosort_binary.m.",
        })
    if not probe_path or not os.path.isfile(probe_path):
        problems.append({"what": "No probe file chosen.",
                         "why": "Without the geometry every unit lands in the "
                                "wrong place on the shank."})
    if not settings:
        problems.append({"what": "No settings file chosen.",
                         "why": "n_chan_bin and fs come from here, and both "
                                "have to match the binary."})
    if binary and per_sample and remainder:
        problems.append({
            "what": "The binary does not divide evenly by %d channels."
                    % n_chan,
            "why": "%d bytes leaves %d over. Either the channel count is "
                   "wrong or the file is truncated -- and Kilosort will not "
                   "notice, it will just interleave the wrong rows."
                   % (size, remainder),
        })
    if probe_chans and n_chan and probe_chans != n_chan:
        problems.append({
            "what": "The probe describes %d channels, the settings say %d."
                    % (probe_chans, n_chan),
            "why": "These have to agree, or the geometry is applied to the "
                   "wrong rows.",
        })
    if out_dir and os.path.isdir(out_dir):
        problems.append({
            "what": "A run with these settings is already here.",
            "why": "%s exists. The lab's automation skips a folder that "
                   "already exists rather than overwriting it; delete it or "
                   "change a threshold." % os.path.basename(out_dir),
        })

    return {
        "session_path": session_path,
        "binary": binary,
        "binary_bytes": size,
        "probe": probe_path,
        "probe_channels": probe_chans,
        "settings_file": settings_path,
        "settings": jsonsafe(main),
        "n_chan_bin": n_chan,
        "fs": fs,
        "samples": samples,
        "duration_s": (samples / fs) if fs else None,
        "invert": bool(invert),
        "bad_csc": sorted({int(c) for c in (bad_csc or [])}),
        "bad_channels": bad_channels_for_kilosort(bad_csc),
        "results_dir": out_dir,
        "existing": results_dirs(session_path) if session_path else [],
        "problems": problems,
        "ready": not problems,
        "script": runner_script(repo_root, session_path, probe_path,
                                settings_path, bad_csc, invert, out_dir),
    }


def runner_script(repo_root, session_path, probe_path, settings_path,
                  bad_csc, invert, out_dir):
    """The script a run would execute, as text.

    Written out rather than called in-process on purpose: it is readable
    before it runs, it can be re-run by hand without BARRY, and when it fails
    at 2am the file that failed is still sitting there to be read.
    """
    bad = bad_channels_for_kilosort(bad_csc)
    return '''"""
Kilosort run, written by BARRY GUI.

Kept as a file rather than run inline so you can read it before it runs, and
re-run it afterwards without BARRY. Everything below is what the interface
resolved: paths as they are on this machine, and bad channels converted from
CSC numbers to the 0-based indices Kilosort counts in.
"""
import json
from kilosort import run_kilosort

DATA_DIR    = r"%(data)s"
BINARY      = r"%(binary)s"
PROBE       = r"%(probe)s"
SETTINGS    = r"%(settings)s"
RESULTS_DIR = r"%(results)s"

# CSC numbers %(bad_csc)s from BARRY, minus one each: the .ncs files are
# CSC1..CSC64 and Kilosort counts binary rows from zero.
BAD_CHANNELS = %(bad)s

with open(SETTINGS) as fh:
    settings = json.load(fh)["main"]

print("data     ", DATA_DIR)
print("binary   ", BINARY)
print("probe    ", PROBE)
print("results  ", RESULTS_DIR)
print("bad      ", BAD_CHANNELS, "(from CSC %(bad_csc)s)")
print("settings ", {k: settings[k] for k in
                    ("n_chan_bin", "fs", "Th_universal", "Th_learned")
                    if k in settings})
print()

run_kilosort(
    settings=settings,
    probe_name=PROBE,
    filename=BINARY,
    data_dir=DATA_DIR,
    results_dir=RESULTS_DIR,
    save_preprocessed_copy=True,
    bad_channels=BAD_CHANNELS,
    verbose_log=True,
    invert_sign=%(invert)s,
)
print()
print("Done. Look at it with:")
print("    phy template-gui " + RESULTS_DIR + r"\\params.py")
''' % {
        "data": session_path or "",
        "binary": find_binary(session_path) if session_path else "",
        "probe": probe_path or "",
        "settings": settings_path or "",
        "results": out_dir or "",
        "bad": bad,
        "bad_csc": sorted({int(c) for c in (bad_csc or [])}),
        "invert": bool(invert),
    }


# ==========================================================================
# Phy
# ==========================================================================
PHY_KEYS = [
    ("Moving around", [
        ("space", "next cluster"),
        ("shift+space", "previous cluster"),
        (":", "type a command"),
    ]),
    ("Deciding", [
        ("g", "good"),
        ("m", "MUA -- a real cluster, more than one cell"),
        ("n", "noise"),
        ("u", "unsorted again"),
    ]),
    ("Changing your mind", [
        ("ctrl+g", "merge the selected clusters"),
        ("k", "split by the current selection in the feature view"),
        ("ctrl+z", "undo"),
        ("ctrl+s", "save -- writes cluster_group.tsv beside the run"),
    ]),
]

PHY_VIEWS = [
    ("Waveform", "Is it a spike? A cluster whose mean waveform has no "
                 "trough, or is identical on all channels, is not a cell."),
    ("Correlogram", "The autocorrelogram must have a refractory gap. A "
                    "cluster firing 2 ms after itself is two cells."),
    ("Amplitude", "Amplitude against time. A cluster that fades out halfway "
                  "through is drift, not a unit that stopped firing."),
    ("Feature", "PCs. Two clouds that do not touch are two clusters, and "
                "this is the view you lasso in to split them."),
]


def phy_command(results_dir):
    params = os.path.join(results_dir or "", "params.py")
    return {
        "params": params,
        "exists": os.path.isfile(params),
        "command": "phy template-gui " + _quote(params),
        "cwd": results_dir,
    }


def _quote(p):
    return ('"%s"' % p) if p and " " in p else (p or "")


# ==========================================================================
def _ls(d):
    try:
        return os.listdir(d)
    except OSError:
        return []


def _mtime(p):
    try:
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%S",
                             time.localtime(os.path.getmtime(p)))
    except OSError:
        return None
