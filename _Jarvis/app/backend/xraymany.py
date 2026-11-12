# -*- coding: utf-8 -*-
"""xraymany.py -- X-ray Many: folders of recordings, one bundle each.

Asked 2026-11-07: "everything that went through the PCA analysis should be
preprocessed in the Many, ready for me to come in and select the border
for ... For each one indicate if separation was possible, and how powerful
the sinks were, then bank that. Save each X-ray analyzed data as an
artifact bundle (similar to Root Canal files) with version control."

THE SHAPE
A FOLDER is one Root Canal workflow run. Its MEMBERS are the run's
recordings, and a member's events are the run's `cols` rows with
`cls == "inside"` for that gid, at `cols.t`. Those stamps are read by X-ray
like any bank set's (dspca.read), named by `rootcanal.stamps_hash` so the
5% and 10% reads of one recording are two reads, not one. Each member is
then boxed (a box drawn on its own average CSD, or the automatic one),
fitted, tested for separation, and kept as an `xray_single` artifact: the
BUNDLE, one per folder and recording, a version per run that differs.

The folders, the boxes and each folder's parameters are shared preferences
(store.PREFS_SPEC, merged per id). Nothing here touches the disk or a
store: app.py reads and writes, this works out what to read and write.

WHAT THE NUMBERS ARE
  separation  two Gaussians against one on the method's own axis -- the
              1-D sink gap under `delta`, PC1 x PC2 under the PCA methods
              -- by BIC, plus the smaller class's share from the fit's own
              counts. yes: dBIC >= 10 and the smaller class >= 10%; weak:
              dBIC >= 2 and >= 10%; no: anything else; too few: under 20.
  sinks       each class's mean CSD at its own sink row, with its SEM, in
              the fit's own unit: A/m^2 at h_power 1, which is uA/mm^2.

THE SINK GAP IS DISCRETE, so its GMM is regularised (2026-11-07). It takes
one of (span - 1) values, and a Gaussian fitted to a pile of identical
values has no width: with sklearn's default `reg_covar` a single hump of
gaps 0.6 contacts wide scored dBIC +360 for "two groups" on synthetic data,
against -3.5 with the variance a rounding to that grid adds (step^2 / 12,
Sheppard). The rounding variance is the honest floor; the PCA axes are
continuous and keep the default.

Where a bundle goes next is The Extraction Room (backend/extraction.py,
2026-11-10; first called Novocaine, hence the key): every bundle says
`novocaine: {ready: true, extracted: false}`, and the room copies what it
needs out of the bundle when it is extracted -- the bundle is never
changed by it.
"""
from __future__ import annotations

import math
import time
import uuid
import warnings

import numpy as np

from . import dspca
from . import rootcanal

KIND = "xray_single"
SCHEMA = "xray.single/1"

FOLDERS_KEY = "dspca_many_folders"
BOXES_KEY = "dspca_many_boxes"
PARAMS_KEY = "dspca_many_params"

# The two the user asked for (2026-11-07), made on the first visit. Their ids
# are fixed rather than minted: two machines visiting first must make the
# SAME two folders, or the merge holds four (memory: a set made twice
# doubles).
DEFAULT_FOLDERS = (
    {"id": "xm-df8f89c45c34-v2", "name": "Verified DS 5%",
     "source": {"artifact_id": "df8f89c45c34", "version": 2}},
    {"id": "xm-f7e3cb9cee38-v2", "name": "Verified DS 10%",
     "source": {"artifact_id": "f7e3cb9cee38", "version": 2}},
)

# A folder's global parameters, Single's defaults. Two classes: the
# question is DS1 against DS2.
DEFAULT_PARAMS = {"method": "delta", "rule": "tort", "features": "minmax",
                  "notch": True, "min_sep": dspca.MIN_SINK_SEP,
                  "gap_weight": dspca.GAP_WEIGHT, "nclasses": 2}
# What a run may set beyond those. The box is not here: it comes per
# recording, from `boxes`.
_FIT_EXTRA = ("screen", "csd_bad_x", "csd_span", "flip", "seed", "cond",
              "f_order", "f_sigma", "no_vaknin", "h_power", "dead",
              "delta_cut", "manual_bad")
BOX_KEYS = ("sel_lo", "sel_hi", "t_lo_ms", "t_hi_ms")

# The separation test, as the user set it (2026-11-07).
MIN_N = 20
DBIC_YES = 10.0
DBIC_WEAK = 2.0
MIN_SHARE = 0.10
GMM_N_INIT = 5
GMM_SEED = 0
GMM_REG = 1e-6           # sklearn's own default, for the continuous axes


# --------------------------------------------------------------------------
# Folders and members
# --------------------------------------------------------------------------
def new_folder_id():
    return "xm-" + uuid.uuid4().hex[:10]


def folder_record(name, wf, version, run, prov=None):
    """What `dspca_many_folders[fid]` holds for one workflow run."""
    prov = prov or {}
    return {
        "name": str(name or wf.get("nickname") or wf.get("name")
                    or wf.get("id")).strip(),
        "at": prov.get("at") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "by": prov.get("user"),
        "source": {"artifact_id": wf.get("id"), "version": int(version),
                   "nickname": wf.get("nickname") or wf.get("name"),
                   "grace": run.get("grace"), "kind": run.get("kind")},
    }


def inside_by_gid(run):
    """{gid: [t, ...]} -- each recording's events the run kept inside the
    border, sorted. Times as the run rounded them (6 decimals)."""
    cols = run.get("cols") or {}
    gids = cols.get("gids") or []
    out = {}
    for cls, g, t in zip(cols.get("cls") or [], cols.get("g") or [],
                         cols.get("t") or []):
        if cls != "inside" or g is None or t is None:
            continue
        try:
            gid = gids[int(g)]
        except (IndexError, TypeError, ValueError):
            continue
        out.setdefault(gid, []).append(round(float(t), 6))
    for ts in out.values():
        ts.sort()
    return out


# A run's payload is written once and never rewritten, so its members are
# worked out once per (workflow, version, run time).
_MEMBERS = {}


def members_of(aid, version, run):
    """One row per recording of a run, with its kept stamps and their name.

    `n` is how many events the run kept inside the border for it;
    `stamps_hash` names that list (rootcanal.stamps_hash), and is what tells
    this folder's read of the recording from another folder's."""
    key = (aid, int(version), run.get("at"))
    hit = _MEMBERS.get(key)
    if hit is not None:
        return [dict(m) for m in hit]
    inside = inside_by_gid(run)
    out, seen = [], set()
    rows = list(run.get("members") or [])
    rows += [{"gid": g} for g in inside if g not in
             {m.get("gid") for m in rows}]
    for m in rows:
        gid = m.get("gid")
        if not gid or gid in seen:
            continue
        seen.add(gid)
        ts = inside.get(gid) or []
        out.append({"gid": gid, "entry_id": m.get("entry_id"),
                    "session_label": m.get("session_label"),
                    "mouse_key": m.get("mouse_key"),
                    "ts": ts, "n": len(ts),
                    "stamps_hash": rootcanal.stamps_hash(ts) if ts else None})
    _MEMBERS[key] = out
    return [dict(m) for m in out]


def box_key(fid, gid):
    return "%s|%s" % (fid, gid)


def bundle_key(fid, gid):
    """The artifact's subject key (artifacts._xray_single_key)."""
    return "%s|%s|%s" % (KIND, fid, gid)


def clean_box(b):
    """A drawn box as the fit takes it, or None for the automatic one.

    Contact numbers and milliseconds, each end optional: a click is one
    time sample (t_lo_ms == t_hi_ms) at the box's depth or the automatic
    depth."""
    if not isinstance(b, dict):
        return None
    out = {}
    for k in ("sel_lo", "sel_hi"):
        v = b.get(k)
        out[k] = None if v is None or v == "" else int(round(float(v)))
    for k in ("t_lo_ms", "t_hi_ms"):
        v = b.get(k)
        out[k] = None if v is None or v == "" else round(float(v), 3)
    if all(out[k] is None for k in BOX_KEYS):
        return None
    for lo, hi in (("sel_lo", "sel_hi"), ("t_lo_ms", "t_hi_ms")):
        if out[lo] is not None and out[hi] is not None and out[lo] > out[hi]:
            out[lo], out[hi] = out[hi], out[lo]
    return out


def clean_params(p):
    """A folder's parameters, defaults filled in. Only fit settings: the
    read is the folder's, and the box is each recording's."""
    p = p if isinstance(p, dict) else {}
    out = dict(DEFAULT_PARAMS)
    for k in tuple(DEFAULT_PARAMS) + _FIT_EXTRA:
        if p.get(k) is not None:
            out[k] = p[k]
    return out


# --------------------------------------------------------------------------
# The two numbers per recording
# --------------------------------------------------------------------------
def _sig(v, n=4):
    """Rounded to `n` significant figures, or None when not a number. A CSD
    in A/m^2 runs from thousandths to tens, so decimal places would keep
    nothing of the small ones."""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    if x == 0:
        return 0.0
    return float("%.*g" % (n, x))


def _r(v, d=4):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, d) if math.isfinite(x) else None


def separation(res):
    """Is this recording two kinds of event? Two-vs-one dBIC plus size.

    On the method's own axis: the sink gap under `delta`, [pc1, pc2] under
    `pca` and `pca_gap` -- the space the classes were cut in. sklearn's
    GaussianMixture, full covariance, n_init 5, random_state 0, as
    rootcanalpool.gmm_test. The smaller class's share is the fit's own
    count, not the mixture's."""
    types = np.asarray(res.get("types"), dtype=int)
    n = int(types.size)
    k = int(res.get("k") or 2)
    sizes = [int((types == c).sum()) for c in range(1, k + 1)]
    share = (min(sizes) / float(n)) if n else None
    method = res.get("method") or "delta"
    if method == "delta":
        X = np.asarray(res.get("gap") or [], dtype=float).reshape(-1, 1)
        space = "sink gap"
        # The gap's grid: (gap - 1) / (span - 2) over the box's contacts.
        span = len(res.get("nums_sel") or [])
        step = 1.0 / max(span - 2.0, 1.0)
        reg = max(GMM_REG, step * step / 12.0)
    else:
        X = np.asarray(res.get("coords"), dtype=float)
        X = X.reshape(len(X), -1)[:, :2]
        space = "PC1 × PC2"
        reg = GMM_REG
    if X.size:
        X = X[np.isfinite(X).all(axis=1)]
    out = {"verdict": None, "dbic": None, "bic1": None, "bic2": None,
           "min_share": _r(share), "n": n, "sizes": sizes,
           "space": space, "dims": int(X.shape[1]) if X.ndim == 2 else 1,
           "reg_covar": _sig(reg, 3), "words": None, "why": None}
    pct = ("%.0f%%" % (100 * share)) if share is not None else "?"
    if n < MIN_N or len(X) < MIN_N:
        out["verdict"] = "too_few"
        out["why"] = ("Too few: %d events, and the test needs at least %d."
                      % (n, MIN_N))
        return out
    try:
        from sklearn.mixture import GaussianMixture      # first use only
        with warnings.catch_warnings():
            # A collapsed second component warns; its BIC still says so.
            warnings.simplefilter("ignore")
            g1 = GaussianMixture(n_components=1, covariance_type="full",
                                 n_init=GMM_N_INIT, random_state=GMM_SEED,
                                 reg_covar=reg).fit(X)
            g2 = GaussianMixture(n_components=2, covariance_type="full",
                                 n_init=GMM_N_INIT, random_state=GMM_SEED,
                                 reg_covar=reg).fit(X)
            bic1, bic2 = float(g1.bic(X)), float(g2.bic(X))
    except Exception as exc:                             # noqa: BLE001
        out["verdict"] = "no"
        out["why"] = "Not separable: the mixture could not be fitted (%s)." \
            % exc
        return out
    dbic = bic1 - bic2
    out.update(dbic=_r(dbic, 2), bic1=_r(bic1, 2), bic2=_r(bic2, 2))
    big = share is not None and share >= MIN_SHARE
    if dbic >= DBIC_YES and big:
        out["verdict"] = "yes"
        lead = "Separable"
    elif dbic >= DBIC_WEAK and big:
        out["verdict"] = "weak"
        lead = "Weak"
    else:
        out["verdict"] = "no"
        lead = "Not separable"
    out["why"] = ("%s: two groups against one on the %s, ΔBIC %+.1f; the "
                  "smaller class is %s of %d events." % (lead, space, dbic,
                                                         pct, n))
    return out


def unit_of(p, band=None):
    """The fit's CSD unit, said as it is computed: -sigma * d2V / h^h_power
    with V in volts and h in metres, Gaussian-smoothed over depth, on the
    band-limited, mains-out trace."""
    lo, hi = (band or dspca.T_DS_FREQ)[:2]
    hp = int(getattr(p, "h_power", 1) or 1)
    what = {1: "µA/mm²", 2: "A/m³"}.get(hp, "A/m^%d" % (1 + hp))
    return "%s (CSD, %g–%g Hz)" % (what, float(lo), float(hi))


def sinks(res, p, band=None):
    """Each class's sink: the class-mean CSD at its own sink row, and SEM.

    The row is `decide[c].sink`, the class mean's minimum in the box --
    its strongest sink. Not `decide[c].row`, the naming rule's marker:
    under `sources` that is a source peak, and under `tort` on a synthetic
    pair it landed on a positive row at the box's edge (2026-11-07), which
    is no sink at all. The marker is kept beside it as `rule_csc`. The
    value is what the profile panel draws there -- the same `prof` every
    rule was scored on, averaged over the box's samples -- negative for a
    sink, and its size is the sink's strength.

    `depth_row` is the contact's place down the read's whole shank, in
    probe order (0 is the first contact read)."""
    types = np.asarray(res.get("types"), dtype=int)
    prof = np.asarray(res.get("prof"), dtype=float)
    ns = [int(x) for x in res.get("nums_sel") or []]
    nums_all = [int(x) for x in res.get("nums_all") or ns]
    unit = unit_of(p, band)
    out = []
    for d in res.get("decide") or []:
        c = int(d.get("c"))
        rr = np.where(types == c)[0]
        if rr.size == 0 or not ns:
            out.append({"cls": c, "csc": None, "depth_row": None,
                        "value": None, "sem": None, "unit": unit, "n": 0})
            continue
        mu = np.nanmean(prof[rr], axis=0)
        # = decide's own `sink` (dspca._working: argmin of the same mean).
        j = int(np.nanargmin(mu))
        vals = prof[rr, j]
        # As dspca.profiles does it, so the bar here is the band there.
        sem = float(np.nanstd(vals) / np.sqrt(rr.size))
        csc = int(ns[j])
        out.append({"cls": c, "csc": csc,
                    "depth_row": (nums_all.index(csc) if csc in nums_all
                                  else None),
                    "value": _sig(mu[j]), "sem": _sig(sem), "unit": unit,
                    "n": int(rr.size), "rule_csc": d.get("csc")})
    return out


def sink_words(sk):
    """The plain reading: "DS2 sink 2.3× DS1". None with fewer than two."""
    got = [s for s in sk or [] if s.get("value") is not None]
    if len(got) < 2:
        return None
    pos = [s for s in got if s["value"] >= 0]
    if pos:
        return "; ".join("DS%d has no sink at CSC%s (the CSD there is %s, "
                         "not negative)" % (s["cls"], s["csc"],
                                            "zero" if s["value"] == 0
                                            else "positive")
                         for s in pos)
    got.sort(key=lambda s: -abs(s["value"]))
    weak = got[-1]
    # NEXT TO NOTHING, SAID SO (2026-11-09): a ratio over a sink no bigger
    # than its own SEM, or under a twentieth of the other's, read "DS2 sink
    # 255.1× DS1" -- a number about the denominator, not the sinks.
    if (abs(weak["value"]) <= abs(weak.get("sem") or 0)
            or abs(weak["value"]) < abs(got[0]["value"]) / 20.0):
        return ("DS%d has the sink; DS%d hardly any at CSC%s (%s ± %s %s)"
                % (got[0]["cls"], weak["cls"], weak["csc"], weak["value"],
                   weak.get("sem"), weak.get("unit") or ""))
    return "; ".join("DS%d sink %.1f× DS%d" % (s["cls"],
                                               abs(s["value"])
                                               / abs(weak["value"]),
                                               weak["cls"])
                     for s in got[:-1])


# --------------------------------------------------------------------------
# The bundle
# --------------------------------------------------------------------------
def used_box(res, asked):
    """The box the fit actually used, in a drawn box's units."""
    ns = [int(x) for x in res.get("nums_sel") or []]
    tw = np.asarray(res.get("tw"))
    t0, t1 = int(res.get("t0") or 0), int(res.get("t1") or 0)
    return {"sel_lo": min(ns) if ns else None,
            "sel_hi": max(ns) if ns else None,
            "t_lo_ms": _r(tw[t0], 3) if tw.size else None,
            "t_hi_ms": _r(tw[max(t0, t1 - 1)], 3) if tw.size else None,
            "n_contacts": len(ns), "n_samples": int(max(t1 - t0, 0)),
            # Nobody drew one, or only part of one: the server chose
            # the rest (dspca.depth_band, and the stamp's sample).
            "auto": asked is None,
            "asked": asked}


def _plain_params(p):
    out = {}
    for k, v in p.fit_params().items():
        if k == "manual_bad":
            v = {str(a): b for a, b in (v or {}).items()}
        out[k] = v
    return out


def bundle_payload(res, got, p, asked, read, stamps_hash, sep, sk):
    """One recording's run as a compact, columnar payload, the way
    rootcanal.single_payload is: every event's call, the class profiles,
    the separation test and the sinks. No timestamps and no machine, so the
    same run again is the same digest and confirms its version."""
    rows = got.get("rows") or []
    types = [int(t) for t in res.get("types")]
    n = len(types)
    coords = np.asarray(res.get("coords"), dtype=float).reshape(n, -1)
    pcs = (res.get("method") != "delta") and coords.shape[1] >= 2
    counts = {}
    for t in types:
        counts[str(t)] = counts.get(str(t), 0) + 1
    profs = []
    for pr in dspca.profiles(res):
        q = dict(pr)
        q["mean"] = [_sig(v) for v in pr.get("mean") or []]
        q["sem"] = [_sig(v) for v in pr.get("sem") or []]
        if isinstance(q.get("sinks"), dict):
            q["sinks"] = dict(q["sinks"], value=_r(q["sinks"].get("value")))
        profs.append(q)
    decide = []
    for d in res.get("decide") or []:
        q = {k: v for k, v in d.items() if k != "mu"}
        if "value" in q:
            q["value"] = _sig(q["value"])
        if isinstance(q.get("peaks"), list):
            q["peaks"] = [[a, _sig(b), _sig(c)] for a, b, c in q["peaks"]]
        decide.append(q)
    var = (res.get("variants") or {}).get(res.get("method")) or {}
    return {
        "schema": SCHEMA,
        "n": n, "k": int(res.get("k") or 0),
        "method": res.get("method"),
        "params": _plain_params(p),
        "box": used_box(res, asked),
        "read": read, "stamps_hash": stamps_hash,
        "cols": {
            "t": [round(float(r.get("stamp_s")), 6) for r in rows],
            "type": types,
            "gap": [_r(v) for v in res.get("gap") or []],
            # Under `delta` the space is a line and there are no
            # components, so these are nulls rather than a copy of `gap`.
            "pc1": [_r(v) for v in coords[:, 0]] if pcs else [None] * n,
            "pc2": [_r(v) for v in coords[:, 1]] if pcs else [None] * n,
        },
        "counts": counts,
        "explained": [_r(v) for v in res.get("explained") or []],
        "bounds": [_r(v) for v in var.get("bounds") or []],
        "missed": len(got.get("missed") or []),
        "bad": {str(a): b for a, b in (res.get("bad") or {}).items()},
        "decide": decide,
        "profiles": profs,
        "separation": sep,
        "sinks": sk,
        "novocaine": {"ready": True, "extracted": False},
    }


def bundle_row(rec):
    """A bundle as the Many grid shows it, off its record's current version
    row -- no payload read."""
    cur = rec.get("current") or {}
    ns = cur.get("n_summary") or {}
    vp = cur.get("params") or {}
    return {"artifact_id": rec.get("id"),
            "version": cur.get("v") or rec.get("version"),
            "at": cur.get("at"), "by": cur.get("by"),
            "here": bool(cur.get("here", True)),
            "counts": ns.get("counts") or {},
            "separation": ns.get("separation") or {},
            "sinks": ns.get("sinks") or [],
            "box": ns.get("box"), "method": ns.get("method"),
            "events": ns.get("events"),
            "read": vp.get("read"), "stamps_hash": vp.get("stamps_hash"),
            "n_versions": rec.get("n_versions")}


def bundle_listing(rec):
    """A bundle for Single's "previously processed": the grid's row plus
    what it is of, and its versions (light)."""
    out = bundle_row(rec)
    sub = rec.get("subject") or {}
    out.update({k: sub.get(k) for k in ("folder", "folder_name", "gid",
                                         "entry_id", "session_label",
                                         "mouse_key", "group", "source")})
    out["name"] = rec.get("nickname") or rec.get("name")
    out["params"] = {k: v for k, v in ((rec.get("current") or {})
                                        .get("params") or {}).items()}
    out["versions"] = [{"v": v.get("v"), "id": v.get("id"), "at": v.get("at"),
                        "by": v.get("by"), "note": v.get("note"),
                        "here": bool(v.get("here", True)),
                        "n": (v.get("n_summary") or {}).get("events"),
                        "verdict": ((v.get("n_summary") or {})
                                    .get("separation") or {}).get("verdict")}
                       for v in rec.get("versions") or []]
    return out


def bank_links(arts):
    """(stamp, links) for EventBank.add_link_source: each live bundle as a
    side branch on its recording's set -- "N events went into the X-ray
    bundle '<session> · <folder>' vK". Off the records alone (n_summary),
    so the bank listing never opens a payload."""
    book = arts.book(KIND)
    stamp = book.signature()
    links = []
    for raw in book.all():
        if raw.get("deleted"):
            continue
        sub = raw.get("subject") or {}
        eid = sub.get("entry_id")
        vers = [v for v in raw.get("versions") or [] if isinstance(v, dict)]
        if not eid or not vers:
            continue
        top = int(raw.get("version") or 0)
        cur = next((v for v in vers if v.get("v") == top), None) \
            or max(vers, key=lambda v: v.get("v") or 0)
        links.append({
            # The workflow read the set as it stood, so the newest version.
            "entry_id": eid, "version": None,
            "link": {"kind": "xray", "artifact_id": raw.get("id"),
                     "name": "%s · %s" % (
                         sub.get("session_label") or sub.get("gid"),
                         sub.get("folder_name") or sub.get("folder")),
                     "version": cur.get("v"),
                     "n": (cur.get("n_summary") or {}).get("events"),
                     "folder": sub.get("folder"), "gid": sub.get("gid"),
                     "archived": False}})
    return stamp, links
