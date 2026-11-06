"""Tab 14, Joe Prompt: Joe's final round of Aim 2 follow-ups (his run sheet,
`Aim2_Jarvis_Run_Sheet_Final_2026-11-06.docx`, 23 requests A1-C5), for the
Monolith and Joe's site alike (Shahriar, 2026-11-06).

Only J6-J11 (tab 11's "Without J3 and J4"). What tabs 11 and 12 already
measured is read from them, not recomputed (C1, B1, A6/B7 where they have
it, C2's main run, C3); what they could not answer needs each 1-s piece of
every trial on its own, so one more pass over the recordings keeps, per
trial, the cross- and auto-spectra of every wire pair, the phase sums
debiased wPLI and PPC are made of, and 2.048-s windows at the edges of the
cues (measure()). Everything else is arithmetic on what is stored.

Shahriar's answers (2026-11-06): Early / Late in every graph; B6 (movement)
and B12 (the cue-pair split) not run; B11 answered by how the data were
cleaned, not by a second automatic screen; B5 without 100-200 Hz; C2's
cheap asks only; C4 run; volume conduction its own part of the tab.

    measure(worker)     the extra pass (cached per rat-day)
    build(progress)     every request, its PDF and CSV, joeprompt.json
    result()            the last build, or None
"""
import csv
import hashlib
import io
import json
import math
import os
import time

import numpy as np

from . import coupling
from . import evenmore as E
from . import finalstage as FS
from . import joe
from . import sweep

SCHEMA = 1
RS = "no34"
DROP = (3, 4)
RATS_SAY = "J6–J11"
TAG = "NoJ3J4"
#: The full windows (tab 11's) and the 2.048-s ones (B9): three 1.024-s
#: pieces half overlapping, cut from the notched full window.
WF = ("base10", "cue1", "cue2", "pair")
SHORT = (("b_last", "base10", -1, "Last 2 s of baseline"), ("c1_first", "cue1", 0, "First 2 s of cue 1"),
         ("c1_last", "cue1", -1, "Last 2 s of cue 1"), ("c2_first", "cue2", 0, "First 2 s of cue 2"))
SHORT_N = E.SEG + 2 * E.STEP                       # 2,048 samples
#: Welch's equivalent number of pieces for a Hann window at 50% overlap
#: (the correlation of neighbouring pieces is 0.167): K / (1 + 2 rho^2).
RHO = 0.1667
SUB = (("low", 30.0, 56.0, "Low gamma (30–56 Hz)"), ("high", 64.0, 90.0, "High gamma (64–90 Hz)"))
DAY_SAY = {"Precon1": "Early", "Precon4": "Late"}
STATUS = ("Done", "Needs decision", "Skipped", "Failed")

REQUESTS = (
    ("A1", "Coherence decomposition", "Whether each coherence change is coupling or power", "P1"),
    ("A2", "Phase-lag coupling: the volume-conduction test", "Whether coherence changes survive removing zero-lag signal", "P1"),
    ("A3", "H1 checks: LMM, leave-one-out, node model", "The H1 verdict; network vs. region-level change", "P1"),
    ("A4", "Trial-mean coherence and noise floors", "Within-trial coupling vs. cross-trial phase consistency", "P1"),
    ("A5", "Per-bin frequency tests", "Every claim about specific frequencies", "P1"),
    ("A6", "Robustness checks for interpreted effects", "Which effects can be called robust", "P1"),
    ("C1", "Coherence by cue and by period", "Cue-related vs. session-wide coherence change", "P1"),
    ("B1", "FOOOF estimates, contrasts, n and settings", "Size of the ACC and OFC effects; the PER exponent claim", "P2"),
    ("B2", "Power output: Session q and period comparisons", "The [direction] placeholder; table q-values", "P2"),
    ("B3", "RSC cue 2 exploratory test", "Whether RSC's cue 2 dip grew", "P2"),
    ("B4", "Theta vs. gamma comparison (Q3)", "Band-specific vs. band-general change", "P2"),
    ("B5", "Technical checks: outside-band coherence, reference, J9", "Technical explanations for the coherence changes", "P2"),
    ("B6", "Behavioral-state control", "Whether movement drives the theta frequency and coherence changes", "P2"),
    ("B7", "Session × Region LMM for power", "The Discussion argument against implant-wide drift", "P2"),
    ("B8", "Ipsilateral and contralateral wire pairs", "Whether wire-pair changes or volume conduction drive the results", "P2"),
    ("B9", "Time-resolved windows and trial blocks", "Whether brief or early-session changes were averaged away", "P2"),
    ("B10", "Sub-band splits (low and high gamma)", "Whether peak shifts or opposite sub-band changes were averaged away", "P2"),
    ("B11", "How the data were cleaned", "Whether artifact segments or the louder channel drive the pooled estimates", "P2"),
    ("B12", "Cue pairs: split by pair", "Whether effects hold in both cue pairs", "P2"),
    ("C2", "Granger causality follow-ups", "Direction of coupling in pairs that changed", "P3"),
    ("C3", "Modulation index", "Theta–gamma coupling within regions", "P3"),
    ("C4", "H2: paired vs. unpaired cues", "H2, or revising it", "P3"),
    ("C5", "SPC test behavior", "Whether this cohort learned", "P3"),
)
#: Where each request is shown: the parts of the tab.
PARTS = (("overview", "Overview"), ("vc", "Volume conduction"), ("clean", "Data cleaning"), ("coh", "Coherence"),
         ("power", "Power and FOOOF"), ("dir", "Granger and coupling"), ("h2", "H2 and behavior"), ("tech", "Technical checks"))
PART_OF = {"A2": "vc", "B11": "clean", "A1": "coh", "A3": "coh", "A4": "coh", "A5": "coh", "B4": "coh", "B8": "coh", "B9": "coh",
           "B10": "coh", "C1": "coh", "A6": "power", "B1": "power", "B2": "power", "B3": "power", "B7": "power", "C2": "dir",
           "C3": "dir", "C4": "h2", "C5": "h2", "B6": "h2", "B5": "tech", "B12": "tech"}


class PromptError(RuntimeError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _root(*parts):
    from . import monolith as MO
    return MO._path("joeprompt", *parts)


def out_dir(*parts):
    """The one folder every export goes to (prompt 1, item 5)."""
    return _root("Aim 2 follow-up", *parts)


# --------------------------------------------------------------------------
# The extra pass: each trial's spectra, the phase sums, the 2-s windows
# --------------------------------------------------------------------------
def _ffts(x):
    """(K, NF) complex: the pieces of one notched signal, Dickson's way."""
    segs = sweep._segments(x[None, :], E.SEG, E.STEP)
    if segs is None:
        return None
    return np.fft.rfft(segs[0] * coupling.matlab_hanning(E.SEG), n=E.NFFT, axis=1)[:, :E.NF]


def _notched(sigs):
    """Each side's signal notched (59-61 Hz), all cut to the shortest usable
    one, as evenmore._spectra_of does; None where a side is missing."""
    ok = [s is not None and np.asarray(s).size >= E.SEG for s in sigs]
    if not any(ok):
        return [None] * len(sigs)
    n = min(np.asarray(s).size for s, k in zip(sigs, ok) if k)
    out = []
    for s, k in zip(sigs, ok):
        x = np.asarray(s, dtype=np.float64)[:n] if k else None
        if x is None or not np.all(np.isfinite(x)) or x.std() <= 0:
            out.append(None)
            continue
        out.append(joe.dickson_notch(x))
    return out


def day_compute(d, chan_map, joe_path):
    """One rat-day, J6-J11: per trial and full window, every wire pair's
    summed cross- and auto-spectra and pieces, every side's power; pooled
    over trials, the phase sums (sum Im, sum |Im|, sum Im^2, sum of unit
    cross-spectra); and the 2.048-s windows, pooled. The wires are tab 8's,
    as tab 11 reads them."""
    t0 = time.time()
    arrs, _fp, meta = joe.load_day(joe_path)
    names = meta["regions"]
    wires = arrs["wires"]
    ri = {nm: names.index(nm) for nm in E.SIDE_NAMES}
    wi8 = {w: joe.WINDOWS.index(w) for w in WF}
    folder = next((f.get("local") for f in d.get("folders") or [] if f.get("role") == "SPC"), None)
    if not folder or not os.path.isdir(folder):
        raise PromptError("r%d %s: its SPC folder cannot be opened here." % (d["rat"], d["day"]), 409)
    units = list(d.get("units") or [])
    if [u["id"] for u in units] != [t["id"] for t in meta["trials"]]:
        raise PromptError("r%d %s: its trials changed since tab 8 was worked out." % (d["rat"], d["day"]), 409)
    cm = {nm: list(chan_map[nm]) for nm in E.SIDE_NAMES}
    blocked = {k: v for k, v in (d.get("blocked") or {}).items() if k in cm}
    WP = E.wire_pairs()
    W, P, C, T, S, NF = len(WF), len(E.PAIRS), len(E.COMBOS), len(units), len(E.SIDE_NAMES), E.NF
    tsab = np.zeros((W, T, P, C, NF), np.complex128)
    tsaa = np.zeros((W, T, P, C, NF))
    tsbb = np.zeros((W, T, P, C, NF))
    tn = np.zeros((W, T, P, C), np.int32)
    tpsd = np.zeros((W, T, S, NF))
    tpn = np.zeros((W, T, S), np.int32)
    sim = np.zeros((W, P, C, NF))
    sabs = np.zeros((W, P, C, NF))
    sim2 = np.zeros((W, P, C, NF))
    su = np.zeros((W, P, C, NF), np.complex128)
    nph = np.zeros((W, P, C), np.int64)
    K = len(SHORT)
    ssab = np.zeros((K, P, C, NF), np.complex128)
    ssaa = np.zeros((K, P, C, NF))
    ssbb = np.zeros((K, P, C, NF))
    sn = np.zeros((K, P, C), np.int32)
    spsd = np.zeros((K, S, NF))
    spn = np.zeros((K, S), np.int32)
    notes = []
    for ui, u in enumerate(units):
        wins = [w for w in joe.trial_windows(u["pair"]) if w[0] in WF]
        drop = {}
        for wn, _a, _b in wins:
            out = set()
            for nm in E.SIDE_NAMES:
                wire = int(wires[wi8[wn], ui, ri[nm]])
                out |= set(cm[nm]) - ({wire} if wire >= 0 else set())
            drop[wn] = sorted(out)
        try:
            got = coupling._signals_for_windows(folder, cm, wins, drop, E.FS, blocked=blocked)
        except coupling.CouplingError as exc:
            notes.append("r%d %s %s: %s" % (d["rat"], d["day"], u["id"], exc))
            continue
        for wn, _a, _b in wins:
            w = WF.index(wn)
            reg = got[wn]["regions"]
            sigs = []
            for nm in E.SIDE_NAMES:
                r = reg.get(nm) or {}
                want = int(wires[wi8[wn], ui, ri[nm]])
                sigs.append(r["signal"] if r.get("usable") and want >= 0 else None)
            X = dict(zip(E.SIDE_NAMES, _notched(sigs)))
            F = {nm: (_ffts(x) if x is not None else None) for nm, x in X.items()}
            for si, nm in enumerate(E.SIDE_NAMES):
                if F[nm] is not None:
                    tpsd[w, ui, si] = (np.abs(F[nm]) ** 2).sum(axis=0)
                    tpn[w, ui, si] = F[nm].shape[0]
            for p, c, a, b in WP:
                Fa, Fb = F[a], F[b]
                if Fa is None or Fb is None:
                    continue
                Xc = Fa * np.conj(Fb)
                tsab[w, ui, p, c] = Xc.sum(axis=0)
                tsaa[w, ui, p, c] = (np.abs(Fa) ** 2).sum(axis=0)
                tsbb[w, ui, p, c] = (np.abs(Fb) ** 2).sum(axis=0)
                tn[w, ui, p, c] = Fa.shape[0]
                im = Xc.imag
                sim[w, p, c] += im.sum(axis=0)
                sabs[w, p, c] += np.abs(im).sum(axis=0)
                sim2[w, p, c] += (im * im).sum(axis=0)
                with np.errstate(invalid="ignore", divide="ignore"):
                    uu = Xc / np.abs(Xc)
                su[w, p, c] += np.nan_to_num(uu).sum(axis=0)
                nph[w, p, c] += Fa.shape[0]
            # the 2.048-s windows inside this full one
            for k, (_key, src, end, _say) in enumerate(SHORT):
                if src != wn:
                    continue
                G = {}
                for nm, x in X.items():
                    if x is None or x.size < SHORT_N:
                        G[nm] = None
                        continue
                    G[nm] = _ffts(x[-SHORT_N:] if end < 0 else x[:SHORT_N])
                for si, nm in enumerate(E.SIDE_NAMES):
                    if G[nm] is not None:
                        spsd[k, si] += (np.abs(G[nm]) ** 2).sum(axis=0)
                        spn[k, si] += G[nm].shape[0]
                for p, c, a, b in WP:
                    if G[a] is None or G[b] is None:
                        continue
                    ssab[k, p, c] += (G[a] * np.conj(G[b])).sum(axis=0)
                    ssaa[k, p, c] += (np.abs(G[a]) ** 2).sum(axis=0)
                    ssbb[k, p, c] += (np.abs(G[b]) ** 2).sum(axis=0)
                    sn[k, p, c] += G[a].shape[0]
    trials = [{"id": u["id"], "cue": u.get("cue_type") or u.get("label"), "label": u.get("cue_label") or u.get("label"),
               "t": [u["pair"]["opener_t"], u["pair"]["closer_t"], u["pair"]["offset_t"]]} for u in units]
    meta_out = {"schema": SCHEMA, "rat": int(d["rat"]), "day": d["day"], "trials": trials, "notes": notes,
                "seconds": round(time.time() - t0, 1), "nf": E.NF}
    return {"tsab": tsab.astype(np.complex64), "tsaa": tsaa.astype(np.float32), "tsbb": tsbb.astype(np.float32), "tn": tn,
            "tpsd": tpsd.astype(np.float32), "tpn": tpn, "sim": sim, "sabs": sabs, "sim2": sim2, "su": su, "nph": nph,
            "ssab": ssab, "ssaa": ssaa, "ssbb": ssbb, "sn": sn, "spsd": spsd, "spn": spn}, meta_out


def _day_path(d, jp):
    blob = json.dumps({"schema": SCHEMA, "joe": os.path.basename(jp), "seg": [E.SEG, E.STEP, E.NFFT, E.NF], "short": SHORT_N},
                      sort_keys=True)
    return _root("days", "r%d_%s_%s.npz" % (int(d["rat"]), d["day"], hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]))


def _compute_one(d, chan_map, jp, path):
    arrs, meta = day_compute(d, chan_map, jp)
    E.save_day(path, arrs, meta)
    return {"rat": meta["rat"], "day": meta["day"], "notes": meta["notes"], "seconds": meta["seconds"]}


def measure(worker=None, workers=None):
    """The extra pass for every J6-J11 rat-day not yet done."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from . import monolith as MO
    man = MO.manifest()
    if not man:
        raise PromptError("There is no Monolith manifest yet.", 409)
    names = list(man.get("regions") or sweep.regions())
    chan_map = {k: v for k, v in coupling.dewey_map().items() if k in E.SIDE_NAMES}
    os.makedirs(_root("days"), exist_ok=True)
    todo, have, notes = [], {}, []
    for d in man.get("days") or []:
        if d["day"] not in E.DAYS or int(d["rat"]) in DROP:
            continue
        jp = joe._day_path(d, joe.day_key(d, names))
        if not os.path.isfile(jp):
            raise PromptError("Tab 8 has not measured r%d %s here." % (d["rat"], d["day"]), 409)
        p = _day_path(d, jp)
        if os.path.isfile(p):
            have[(int(d["rat"]), d["day"])] = p
        else:
            todo.append((d, jp, p))
    if worker:
        worker.note(phase="joeprompt", item="reading %d rat-days again (%d already done)" % (len(todo), len(have)), i=0, of=len(todo))
    if todo:
        n = workers or max(1, min(4, (os.cpu_count() or 2) - 1))
        with ProcessPoolExecutor(max_workers=n) as ex:
            futs = {ex.submit(_compute_one, d, chan_map, jp, p): (d, p) for d, jp, p in todo}
            for i, f in enumerate(as_completed(futs), 1):
                d, p = futs[f]
                try:
                    notes += f.result()["notes"]
                    have[(int(d["rat"]), d["day"])] = p
                except Exception as exc:                     # noqa: BLE001
                    notes.append("r%d %s: not measured (%s)" % (d["rat"], d["day"], exc))
                if worker:
                    worker.note(phase="joeprompt", i=i, of=len(todo), item="r%d %s (%d of %d)" % (d["rat"], d["day"], i, len(todo)))
    keep = {os.path.basename(p) for p in have.values()}
    for f in os.listdir(_root("days")):
        if f.endswith(".npz") and f not in keep:
            try:
                os.remove(_root("days", f))
            except OSError:
                pass
    return notes


def load_days():
    p = _root("days")
    out = {}
    for f in sorted(os.listdir(p)) if os.path.isdir(p) else []:
        if f.endswith(".npz") and not f.endswith(".tmp.npz"):
            arrs, meta = E.load_day(os.path.join(p, f))
            out[(int(meta["rat"]), meta["day"])] = (arrs, meta)
    return out


if __name__ == "__main__":
    import sys
    from . import monolith as MO
    MO.configure(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "GUI_logs"))

    class _W:
        def note(self, **kw):
            print(kw.get("item"), flush=True)

        def check(self):
            pass

    if sys.argv[1:2] == ["measure"]:
        for n in measure(_W()):
            print(n)
