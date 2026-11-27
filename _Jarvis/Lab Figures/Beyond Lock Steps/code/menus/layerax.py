"""A common depth axis built from each recording's own hand layer labels (StrataScope, in Jarvis).

Every recording's contacts are placed on one axis on which each layer has the same span, so
profiles from mice whose layers sit at different depths (and are of different thickness) can be
averaged layer by layer. Contacts labeled with a placeholder ("CA1", "DG") are left out.

Axis, top to bottom:  SLM | OML1 | MML1 | GCL1 | HIL | GCL2 | MML2 | OML2
Upper blade = suprapyramidal (1), lower blade = infrapyramidal (2).
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LAYERS = ["ca1_slm", "dg_oml1", "dg_mml1", "dg_gcl1", "hil", "dg_gcl2", "dg_mml2", "dg_oml2"]
NAMES = ["SLM", "OML1", "MML1", "GCL1", "HIL", "GCL2", "MML2", "OML2"]
PER = 8                      # grid points per layer
GRID = np.concatenate([k + (np.arange(PER) + 0.5) / PER for k in range(len(LAYERS))])
PITCH_UM = 20.0              # H3: 64 contacts, 20 um apart
_LAB = json.load(open(os.path.join(HERE, "layers.json"), encoding="utf-8"))


def labels_of(lab):
    """{row (0-based, top contact 0): region id} for one recording."""
    lab_map = _LAB[lab]["labels"]
    return {int(ch) - 1: reg for ch, reg in lab_map.items()}


def coords(lab, n_rows=64):
    """Each row's position on the common axis (nan where the row is not in a target layer)."""
    lm = labels_of(lab)
    c = np.full(n_rows, np.nan)
    for k, layer in enumerate(LAYERS):
        rows = sorted(r for r, reg in lm.items() if reg == layer and r < n_rows)
        if not rows:
            continue
        a, b = rows[0], rows[-1]
        n = b - a + 1
        for r in range(a, b + 1):
            if lm.get(r) in (layer, "dg", "ca1_sr", None) or lm.get(r) == layer:
                c[r] = k + (r - a + 0.5) / n
    return c


def spans(lab):
    """(first row, last row, thickness in um) per layer present."""
    lm = labels_of(lab)
    out = {}
    for layer, name in zip(LAYERS, NAMES):
        rows = sorted(r for r, reg in lm.items() if reg == layer)
        if rows:
            out[name] = (rows[0], rows[-1], (rows[-1] - rows[0] + 1) * PITCH_UM)
    return out


def to_grid(lab, profile):
    """A per-row profile (64,) or (64, T) put on the common axis: (len(GRID),) or (len(GRID), T).
    Linear between the contacts that carry a coordinate; nan outside them and across missing layers."""
    prof = np.asarray(profile, float)
    c = coords(lab, prof.shape[0])
    ok = np.isfinite(c)
    if prof.ndim == 1:
        prof2 = prof[:, None]
    else:
        prof2 = prof
    order = np.argsort(c[ok])
    xs = c[ok][order]
    out = np.full((GRID.size, prof2.shape[1]), np.nan)
    if xs.size < 2:
        return out[:, 0] if prof.ndim == 1 else out
    for j in range(prof2.shape[1]):
        ys = prof2[ok, j][order]
        good = np.isfinite(ys)
        if good.sum() < 2:
            continue
        out[:, j] = np.interp(GRID, xs[good], ys[good], left=np.nan, right=np.nan)
    # blank grid points inside a layer the recording has no label for
    present = {k for k in range(len(LAYERS)) if np.any((c >= k) & (c < k + 1))}
    for k in range(len(LAYERS)):
        if k not in present:
            out[(GRID >= k) & (GRID < k + 1)] = np.nan
    return out[:, 0] if prof.ndim == 1 else out


def label_axis(ax, which="y", invert=True, color="#5a6273", lines=True):
    """Layer names at layer centers; thin lines at layer edges; blades bracketed."""
    centers = np.arange(len(LAYERS)) + 0.5
    if which == "y":
        ax.set_yticks(centers)
        ax.set_yticklabels(NAMES)
        if lines:
            for k in range(1, len(LAYERS)):
                ax.axhline(k, color="#e1e4e9", lw=0.5, zorder=0)
        ax.set_ylim(len(LAYERS), 0) if invert else ax.set_ylim(0, len(LAYERS))
    else:
        ax.set_xticks(centers)
        ax.set_xticklabels(NAMES)
        if lines:
            for k in range(1, len(LAYERS)):
                ax.axvline(k, color="#e1e4e9", lw=0.5, zorder=0)
        ax.set_xlim(0, len(LAYERS))
