"""Method B, "simulate and match": what the recording should look like if
the probe were here.

No landmark is picked. For a candidate probe the atlas says which layer lies
under every 10 um of the line; each synaptic pathway puts its current sink in
its own layer and its return current in the cell layer it belongs to:

    perforant path, lateral   sink: outer molecular layer   (DS1; slow gamma)
    perforant path, medial    sink: middle molecular layer  (DS2; fast gamma)
        (each blade separately; return current in the granule cells, inner
         molecular layer and hilus)
    CA1, entorhinal           sink: stratum lacunosum-moleculare (theta)
    CA1, Schaffer             sink: stratum radiatum (the sharp wave)
        (return current in the pyramidal layer and oriens)

A current spread over a layer is turned into voltage at every contact with
the standard laminar volume conductor -- a sheet of radius R in a uniform
medium (Pettersen et al. 2006 iCSD; R = 400 um, the sheet a laminar input
lights at once):

    V(z) = 1/(2 sigma) * integral C(z') [sqrt((z - z')^2 + R^2) - |z - z'|] dz'

Each recorded depth profile (dentate spikes, P-spikes, BTs and the sharp wave
at their peaks; theta as a complex wave) is then fitted by least squares as a
sum of its pathways' voltages plus a constant (the reference), and the
misfit is the score: a probe placed wrongly puts the predicted sinks on the
wrong contacts, and no choice of strengths repairs that. Multiunit activity
and ripple power, which are local and not volume conducted, are fitted as
levels per layer group (cell layers vs neuropil).
"""
from __future__ import annotations

import numpy as np

from . import fit as F

R_UM = 400.0
DT = F.DT
# layer groups (atlas codes)
G = {
    "so": (10, 14, 18), "sp": (11, 15, 19), "sr": (12, 16, 20, 21), "slm": (13, 17, 22),
    "oml1": (1,), "mml1": (2,), "iml1": (3,), "gcl1": (4,), "hil": (5,),
    "gcl2": (6,), "iml2": (7,), "mml2": (8,), "oml2": (9,),
}
# pathways: (sink groups, return-current groups)
PATH = {
    "lpp1": (("oml1",), ("iml1", "gcl1", "hil")),
    "mpp1": (("mml1",), ("iml1", "gcl1", "hil")),
    "lpp2": (("oml2",), ("iml2", "gcl2", "hil")),
    "mpp2": (("mml2",), ("iml2", "gcl2", "hil")),
    "ec_ca1": (("slm",), ("sp", "sr")),
    "sc_ca1": (("sr",), ("sp", "so")),
    "dg_all": (("oml1", "mml1", "oml2", "mml2"), ("iml1", "gcl1", "hil", "gcl2", "iml2")),
}
# which pathways each profile is explained by
MODEL = {
    "ds": ("lpp1", "mpp1", "lpp2", "mpp2", "ec_ca1"),
    "ps": ("lpp1", "mpp1", "lpp2", "mpp2", "ec_ca1", "sc_ca1"),
    "bt": ("lpp1", "mpp1", "lpp2", "mpp2", "ec_ca1"),
    "spw": ("sc_ca1", "ec_ca1", "dg_all"),
    "theta": ("ec_ca1", "sc_ca1", "dg_all"),
}
# Pathways whose strength must stay positive -- a synaptic sink stays a sink.
# Unconstrained, a "sink" pathway with a negative strength becomes a source,
# and two pathways of opposite sign can put a sink anywhere (seen on m2: B
# alone fitted its profiles at a pose that broke every landmark). The CA1
# entorhinal pathway is left free in the dentate events and the sharp wave,
# where lacunosum-moleculare carries return current.
POSITIVE = {
    "ds": ("lpp1", "mpp1", "lpp2", "mpp2"),
    "ps": ("lpp1", "mpp1", "lpp2", "mpp2"),
    "bt": ("lpp1", "mpp1", "lpp2", "mpp2"),
    "spw": ("sc_ca1", "dg_all"),
}
LOCAL = {
    "mua": (("sp",), ("gcl1", "gcl2", "hil"), ("below",)),
    "rip": (("sp",),),
}
BELOW = (33, 34, 35, 36, 38)


def _kernel(T):
    d = np.arange(-(T - 1), T) * DT
    return (np.sqrt(d ** 2 + R_UM ** 2) - np.abs(d)) * DT / 1000.0


def bases(codes):
    """Per line (n, T codes): {pathway: (n, T) voltage along the line}, and
    {group: (n, T) indicator} for the local models."""
    n, T = codes.shape
    ind = {g: np.isin(codes, c).astype(np.float32) for g, c in G.items()}
    ind["below"] = np.isin(codes, BELOW).astype(np.float32)
    K = _kernel(T).astype(np.float32)
    nfft = int(2 ** np.ceil(np.log2(3 * T)))
    Kf = np.fft.rfft(K, nfft)
    out = {}
    for name, (sink, src) in PATH.items():
        si = sum(ind[g] for g in sink)
        so = sum(ind[g] for g in src)
        ns = si.sum(1, keepdims=True)
        nq = so.sum(1, keepdims=True)
        ok = (ns[:, 0] > 0) & (nq[:, 0] > 0)
        C = np.where(ok[:, None], -si / np.maximum(ns, 1) + so / np.maximum(nq, 1), 0.0)
        V = np.fft.irfft(np.fft.rfft(C, nfft, axis=1) * Kf[None, :], nfft, axis=1)
        out[name] = V[:, T - 1:2 * T - 1].astype(np.float32)
    return out, ind


def _sample(A, tc):
    """A (n, T) along the line, sampled at positions tc (n, m, 64) (um from
    the reference) by linear interpolation -> (n, m, 64)."""
    n, T = A.shape
    f = (tc - F.T0) / DT
    i0 = np.clip(np.floor(f).astype(np.int64), 0, T - 2)
    w = np.clip(f - i0, 0.0, 1.0).astype(np.float32)
    rows = np.arange(n)[:, None, None]
    return A[rows, i0] * (1 - w) + A[rows, i0 + 1] * w


def csd_operator(bad, n=64, pitch_mm=0.020):
    """The recording's own CSD as a matrix (evidence.csd): bad rows filled by
    straight lines, 1-2-1 smoothing, minus the second difference over 20 um.
    Applied to the model's voltages it gives the model's CSD exactly as the
    recording's was computed. Rows 0 and n-1 are zero (no CSD there)."""
    bad = np.asarray(bad, bool)
    P = np.eye(n)
    good = np.flatnonzero(~bad)
    for i in np.flatnonzero(bad):
        lo, hi = good[good < i], good[good > i]
        P[i] = 0.0
        if lo.size and hi.size:
            a, c = lo[-1], hi[0]
            w = (i - a) / float(c - a)
            P[i, a], P[i, c] = 1 - w, w
        elif lo.size:
            P[i, lo[-1]] = 1.0
        elif hi.size:
            P[i, hi[0]] = 1.0
    S = np.zeros((n, n))
    for i in range(n):
        for j, w in ((i - 1, 0.25), (i, 0.5), (i + 1, 0.25)):
            S[i, min(max(j, 0), n - 1)] += w
    D = np.zeros((n, n))
    for i in range(1, n - 1):
        D[i, i - 1], D[i, i], D[i, i + 1] = -1.0, 2.0, -1.0
    D /= pitch_mm ** 2
    return D @ S @ P


def _ls_rss(X, y, good, positive=None, const=True):
    """Least squares y ~ X g + b per pose, over the good contacts, with the
    columns in `positive` (a boolean per column) held at or above zero by an
    active set: a column that comes out negative is pinned to zero and the
    rest refitted (three rounds; the set only grows).
    X (n, m, 64, k) real or complex, y (64,). Returns RSS (n, m), gains."""
    Xg = X[:, :, good, :]
    yg = y[good].astype(Xg.dtype)
    if const:
        ones = np.ones(Xg.shape[:3] + (1,), dtype=Xg.dtype)
        A = np.concatenate([Xg, ones], -1)                   # (n, m, g, k+1)
    else:
        A = Xg
    AH = np.conj(np.swapaxes(A, -1, -2))
    M0 = AH @ A
    k = M0.shape[-1]
    tr = np.abs(np.trace(M0, axis1=-2, axis2=-1))[..., None, None]
    eye = np.eye(k, dtype=M0.dtype)
    M0 = M0 + (1e-6 * tr + 1e-12) * eye
    r0 = AH @ yg[:, None]                                    # (n, m, k+1, 1)
    pos = np.zeros(k, bool)
    if positive is not None:
        pos[:len(positive)] = positive
    pinned = np.zeros(M0.shape[:2] + (k,), bool)
    for _round in range(4):
        big = (1e6 * tr + 1.0) * pinned[..., None, :] * eye
        M = M0 + big
        r = np.where(pinned[..., None], 0.0, r0)
        g = np.linalg.solve(M, r)
        if not pos.any():
            break
        neg = (np.real(g[..., 0]) < 0) & pos[None, None, :] & ~pinned
        if not neg.any():
            break
        pinned |= neg
    res = (A @ g)[..., 0] - yg
    rss = np.sum(np.abs(res) ** 2, -1).real
    return rss, (g[..., :-1, 0] if const else g[..., 0])


def _movavg(a, w=5):
    """Moving average along axis 1 (a contact's reach, +-20 um at 10 um)."""
    c = np.cumsum(np.pad(a, ((0, 0), (w // 2 + 1, w // 2)), mode="edge"), axis=1)
    return (c[:, w:] - c[:, :-w]) / w


def profiles(ev, bad):
    """The recorded profiles Method B fits (each scaled to unit RMS)."""
    out = {}
    for key, name in (("ds_peak", "ds"), ("ps_peak", "ps"), ("bt_peak", "bt"), ("spw", "spw")):
        if key in ev and ev.get("n_" + name, ev.get("n_ripples", 0)) >= (20 if name in ("ds", "spw") else 8):
            y = np.asarray(ev[key], float)
            out[name] = y
    if "theta_cx" in ev:
        out["theta"] = np.asarray(ev["theta_cx"], complex)
    if "c_mua" in ev:
        out["mua"] = np.log(np.asarray(ev["c_mua"], float))
    if "rip_power" in ev:
        out["rip"] = np.asarray(ev["rip_power"], float)
    good = ~np.asarray(bad, bool)
    Dop = csd_operator(bad)
    for k in [k for k in out if k in MODEL]:
        y = np.nan_to_num(out[k])
        c = Dop @ y
        c[[0, len(c) - 1]] = np.nan
        out[k] = np.where(good, c, np.nan)
    for k, y in list(out.items()):
        g = good & np.isfinite(np.abs(y))
        if g.sum() < 20:
            out.pop(k)
            continue
        yy = y - np.mean(y[g])
        sd = np.sqrt(np.mean(np.abs(yy[g]) ** 2))
        out[k] = np.where(g, yy / max(sd, 1e-12), np.nan)
    return out


def score(codes, offsets, scales, prof, bad, n_contacts=64):
    """Method B's log-likelihood for every line x offset x scale.

    codes (n, T); offsets (o,) um of contact 1 from the reference point;
    scales (s,). Returns LL (n, o, s) summed over profiles, and the per-
    profile parts. LL of one profile = -(m/2) log(RSS/m): the concentrated
    Gaussian likelihood with its own noise level."""
    n, T = codes.shape
    V, ind = bases(codes)
    x = np.arange(n_contacts, dtype=np.float32)
    O, S = np.meshgrid(offsets, scales, indexing="ij")
    tc = (O[..., None] + F.PITCH * S[..., None] * x).reshape(-1, n_contacts)   # (m, 64)
    tc = np.broadcast_to(tc[None], (n,) + tc.shape)
    good_all = ~np.asarray(bad, bool)
    Dop = csd_operator(bad).astype(np.float32)
    parts = {}
    for name, y in prof.items():
        good = good_all & np.isfinite(np.abs(y))
        m = int(good.sum())
        if name in MODEL:
            cols = [_sample(V[p], tc) for p in MODEL[name]]
            X = np.stack(cols, -1)                               # (n, m, 64, k)
            X = np.einsum("ij,nmjk->nmik", Dop, X).astype(np.float32)
            if np.iscomplexobj(y):
                X = X.astype(np.complex64)
        else:
            sm = []
            for grp in LOCAL[name]:
                a = sum(ind[g] for g in grp)
                sm.append(_sample(_movavg(a).astype(np.float32), tc))
            X = np.stack(sm, -1)
        posmask = None
        if name in POSITIVE:
            posmask = np.array([p in POSITIVE[name] for p in MODEL[name]])
        rss, _g = _ls_rss(X, np.nan_to_num(y), good, posmask, const=name not in MODEL)
        ll = -0.5 * m * np.log(np.maximum(rss, 1e-9) / m)
        parts[name] = ll.reshape(n, len(offsets), len(scales))
    total = sum(parts.values())
    return total, parts
