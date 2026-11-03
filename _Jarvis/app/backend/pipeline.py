"""
pipeline.py -- Declarative definition of the IED pipeline.

The pipeline runs on folders, in two tracks:

  SESSION track  input = one recording folder (the CSC*.ncs session dir).
                 Each stage writes back into that same folder, so the output
                 of one stage is the input of the next and the whole chain is
                 driven by a single path.

  COHORT track   input = a parent folder holding many processed sessions.
                 Aggregates across sessions into grand averages and stats.

Each stage records what it needs and what it leaves behind, so the GUI can
show a live readiness check against a chosen folder rather than making the
user remember the ordering.
"""
from __future__ import annotations

import os
import re

SESSION_STAGES = [
    {
        "key": "convert",
        "n": 1,
        "title": "CSC Conversion",
        "script": "IED/02_CSC_Conversion/CSC2LL_uV_mex_disk.m",
        "lang": "matlab",
        "func": "CSC2LL_uV_mex_disk",
        "summary": "Neuralynx CSC*.ncs to a LLspikedetector-ready .mat in microvolts.",
        "arg_folder": "basePath",
        "options": [
            {"name": "nTotalCh", "value": "64", "hint": "channels expected"},
            {"name": "evenOnly", "value": "true", "hint": "keep even channels only"},
            {"name": "storeClass", "value": "single", "hint": "single | double"},
        ],
        "requires": {"any_glob": ["CSC*.ncs"]},
        "produces": {"any_glob": ["*.mat"]},
    },
    {
        "key": "detect",
        "n": 2,
        "title": "IED Detection",
        "script": "IED/03_IED_Detection/vacc_ied_detect.m",
        "lang": "matlab",
        "func": "vacc_ied_detect",
        "summary": "Line-length spike detector; writes event times (ets) and channels (ech).",
        "arg_folder": "basePath",
        "positional_extra": [
            {"name": "eightBad", "value": "false", "hint": "mark channel 8 bad"},
        ],
        "requires": {"any_glob": ["*.mat"]},
        "produces": {"any_glob": ["ets*.mat", "*LLspikes*.mat"]},
    },
    {
        "key": "curate",
        "n": 3,
        "title": "Event Curation",
        "script": "IED/04_Event_Curation/TheVisionOverlay.m",
        "lang": "matlab",
        "func": "TheVisionOverlay",
        "summary": "Overlay detected events for solid/sputter review before analysis.",
        "arg_folder": "inputFolder",
        "requires": {"any_glob": ["ets*.mat", "*LLspikes*.mat", "*.xlsx"]},
        "produces": {"any_glob": ["*.xlsx", "*.png"]},
        "optional": True,
    },
    {
        "key": "session",
        "n": 4,
        "title": "Session Pipeline",
        "script": "IED/05_Session_Pipeline/Pipeline_Main.m",
        "lang": "matlab",
        "func": "Pipeline_Main",
        "summary": "Theta, voltage raster, CSD, slices, event stacks and scalogram "
                   "into one triptych plus Master_Stats.csv.",
        "arg_folder": "inputFolder",
        "requires": {"any_glob": ["*.mat"]},
        "produces": {"any_dir": ["Pipeline Output"]},
    },
]

COHORT_STAGES = [
    {
        "key": "grand_csd",
        "n": 5,
        "title": "Grand Average - CSD",
        "script": "IED/07_Grand_Average/CSDRaster_GrandAverage.m",
        "lang": "matlab",
        "func": "CSDRaster_GrandAverage",
        "summary": "Averages CSD rasters across every session under the root folder.",
        "arg_folder": "rootFolder",
        "requires": {"any_subdir_glob": ["*.mat"]},
        "produces": {"any_glob": ["*.png", "*.fig"]},
    },
    {
        "key": "grand_volt",
        "n": 6,
        "title": "Grand Average - Voltage",
        "script": "IED/07_Grand_Average/VoltageRaster_GrandAverage.m",
        "lang": "matlab",
        "func": "VoltageRaster_GrandAverage",
        "summary": "Averages voltage rasters across every session under the root folder.",
        "arg_folder": "rootFolder",
        "requires": {"any_subdir_glob": ["*.mat"]},
        "produces": {"any_glob": ["*.png", "*.fig"]},
    },
    {
        "key": "ipp",
        "n": 7,
        "title": "IPP (Take 4)",
        "script": "IED/06_IPP_Take4/Run_Take4_IPP.m",
        "lang": "matlab",
        "func": "Run_Take4_IPP",
        "summary": "Inter-paroxysmal propagation analysis across sessions.",
        "arg_folder": "inputParent",
        "second_folder": "outputParent",
        "requires": {"any_subdir_glob": ["*.mat"]},
        "produces": {},
        "optional": True,
    },
    {
        "key": "anat",
        "n": 8,
        "title": "Anatomical Labeling",
        "script": "IED/08_Anatomical_Labeling/IED Anatomical Labeling/main.py",
        "lang": "python",
        "summary": "Runs the 5-step Python chain: scan sessions, collect anatomy, "
                   "aggregate values, merge/collapse, plot comparisons.",
        "arg_folder": None,
        "requires": {},
        "produces": {"any_glob": ["*.csv", "*.png"]},
    },
    {
        "key": "stats",
        "n": 9,
        "title": "Stats Tables",
        "script": "IED/09_Stats/CSD and Voltage Delta stats/build_tables.py",
        "lang": "python",
        "summary": "Builds the paired CNO-vs-baseline analysis tables from the "
                   "long-format CSV.",
        "arg_folder": None,
        "requires": {},
        "produces": {"any_glob": ["*.csv"]},
    },
]


def _glob_match(names, pattern):
    rx = re.compile("^" + re.escape(pattern).replace(r"\*", ".*") + "$", re.I)
    return [n for n in names if rx.match(n)]


def check_stage(stage, folder):
    """Report whether a stage's inputs exist and whether its outputs are present."""
    result = {"key": stage["key"], "ready": True, "done": False,
              "found": [], "missing": []}
    if not folder or not os.path.isdir(folder):
        result["ready"] = False
        result["missing"].append("folder not set")
        return result

    try:
        entries = os.listdir(folder)
    except OSError:
        result["ready"] = False
        result["missing"].append("folder unreadable")
        return result

    files = [e for e in entries if os.path.isfile(os.path.join(folder, e))]
    dirs = [e for e in entries if os.path.isdir(os.path.join(folder, e))]

    req = stage.get("requires") or {}
    for pattern in req.get("any_glob", []):
        hits = _glob_match(files, pattern)
        if hits:
            result["found"].append(f"{pattern} ({len(hits)})")
            break
    else:
        if req.get("any_glob"):
            result["ready"] = False
            result["missing"].append(" or ".join(req["any_glob"]))

    if req.get("any_subdir_glob"):
        n = 0
        for d in dirs[:400]:
            try:
                sub = os.listdir(os.path.join(folder, d))
            except OSError:
                continue
            if any(_glob_match(sub, p) for p in req["any_subdir_glob"]):
                n += 1
        if n:
            result["found"].append(f"{n} session folder(s)")
        else:
            result["ready"] = False
            result["missing"].append("sessions containing " +
                                     " or ".join(req["any_subdir_glob"]))

    prod = stage.get("produces") or {}
    for pattern in prod.get("any_glob", []):
        if _glob_match(files, pattern):
            result["done"] = True
            break
    for d in prod.get("any_dir", []):
        if os.path.isdir(os.path.join(folder, d)):
            result["done"] = True

    return result


def inspect_folder(folder):
    """Summarize a folder for the pipeline header strip."""
    if not folder or not os.path.isdir(folder):
        return {"ok": False, "error": "Folder not found."}
    try:
        entries = sorted(os.listdir(folder))
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    files = [e for e in entries if os.path.isfile(os.path.join(folder, e))]
    dirs = [e for e in entries if os.path.isdir(os.path.join(folder, e))]
    ncs = _glob_match(files, "CSC*.ncs")
    mats = [f for f in files if f.lower().endswith(".mat")]

    total = 0
    for f in files[:2000]:
        try:
            total += os.path.getsize(os.path.join(folder, f))
        except OSError:
            pass

    return {
        "ok": True, "path": folder,
        "name": os.path.basename(folder.rstrip("\\/")) or folder,
        "n_files": len(files), "n_dirs": len(dirs),
        "n_ncs": len(ncs), "mats": mats[:30], "subdirs": dirs[:60],
        "bytes": total,
    }


def build_stage_call(stage, folder, options=None, second=None):
    """Turn a stage + folder into the params/extra the runner expects."""
    options = options or {}
    params, extra = [], {}

    if stage["lang"] == "matlab":
        extra = {"kind": "function", "func": stage.get("func")}
        if stage.get("arg_folder"):
            params.append({"name": stage["arg_folder"], "value": folder,
                           "required": True})
        for p in stage.get("positional_extra", []):
            params.append({"name": p["name"],
                           "value": options.get(p["name"], p["value"]),
                           "required": True})
        if stage.get("second_folder"):
            params.append({"name": stage["second_folder"],
                           "value": second or os.path.join(folder, "IPP_Output"),
                           "required": True})
        for opt in stage.get("options", []):
            val = options.get(opt["name"], "")
            if str(val).strip() != "":
                params.append({"name": opt["name"], "value": val,
                               "namevalue": True, "required": False})
    return params, extra


def all_stages():
    return {"session": SESSION_STAGES, "cohort": COHORT_STAGES}
