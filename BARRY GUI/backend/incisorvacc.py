"""
incisorvacc.py -- Incisor on a recording only the cluster can read.

WHAT CHANGES, AND WHAT DOES NOT

The detector does not change: a compute node runs the same `incisor.run`
the desk runs (vacc_run.py), and the panel draws the same three plots, the
same picks and the same hilus range from what comes back. What changes is
everything that used to need the recording on THIS computer before anything
was sent:

  the channel list   only exists on the cluster, so the node resolves it,
                     by the one rule (`incisor.resolve_channels`): every
                     channel less the bad ones, by CSC number.
  the segmentation   is made on the node, which `vacc_run.py` already did
                     when no report travelled; the login node never reads a
                     whole file.
  the cache key      is computed when the answer lands, from the
                     `time_basis.breaks_sha` it carries -- the same key a
                     report in hand would have given. Its path is
                     `vacc:<gid>`, the same on every machine.

So a recording on the lab's netfiles share, which this desk cannot see at
all, scans, comes back, and is reviewed and banked exactly as a local one.

WHERE THE ANSWER LIVES

The summary goes in the vault, which syncs. The per-channel events are
megabytes and are cached only on the machine that filed them -- so the vault
record says where the whole answer still sits on the cluster
(`computed_on.workspace` / `.file`, in the backed-up workspace, not scratch),
and a machine reviewing it without the cache fetches it once from there.
"""
from __future__ import annotations

import hashlib
import json

from . import incisor, vacc

PREFIX = "vacc:"

#: What a request is, before the cluster has resolved channels or measured
#: gaps. Used to say "already answered" before submitting anything.
REQ_FIELDS = ("invert", "estimator", "bad_channels", "height_sd", "abs_uv",
              "dist_ms", "prom_uv", "wlen_ms", "band", "lfp_fs",
              "threshold_uv")


def path_of(gid):
    return PREFIX + str(gid)


def is_vacc(path):
    return isinstance(path, str) and path.startswith(PREFIX)


def request_hash(gid, spec):
    """The question, as asked: which recording, which settings, which bad
    channels. Not the answer's key -- that needs the channel list and the
    segmentation, which only the cluster has -- but enough to recognise a
    question already answered, so a batch skips it."""
    body = {"gid": str(gid)}
    for k in REQ_FIELDS:
        v = (spec or {}).get(k)
        if isinstance(v, float):
            v = round(v, 6)
        if k == "bad_channels":
            v = sorted(int(b) for b in (v or []))
        if k == "band" and v:
            v = [round(float(x), 6) for x in v]
        body[k] = v
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def spec_for(gid, body, rec, probe_id, probe_name, fill):
    """The spec for a recording the desk cannot open.

    `channels` is None: the node resolves it. Bad channels come from the
    request when it says (an explicit list, even an empty one, overrides),
    else from the recording's own record -- the same rule `_incisor_spec`
    applies to a session open here. `fill` is `app._incisor_params`, so the
    detection defaults are the same object in both.
    """
    if body.get("bad_channels") is None:
        bad = sorted({int(b) for b in ((rec or {}).get("bad_channels") or [])})
    else:
        bad = sorted({int(b) for b in body["bad_channels"]})
    spec = {
        "path": path_of(gid),
        "channels": None,
        "invert": bool(body.get("invert", True)),
        "estimator": body.get("estimator") or "sd",
        "bad_channels": bad,
        "excluded": [],
        "probe": probe_id,
        "probe_name": probe_name or probe_id,
    }
    return fill(spec, body)


def filed_spec(spec_local, out):
    """The spec as the node resolved it: the channels it actually read."""
    return dict(spec_local,
                channels=list((out or {}).get("spec_channels") or []),
                excluded=list((out or {}).get("spec_excluded") or []))


def key_for(spec_local, out):
    """The answer's cache key, from what the answer carries."""
    tb = (out or {}).get("time_basis") or {}
    return incisor.cache_key(filed_spec(spec_local, out),
                             breaks_sha=tb.get("breaks_sha"))


def plan_for(rec, spec, rate_read, rate_detect, found=None):
    """What one scan would cost on the cluster.

    From the cluster's own listing of the folder when there is one (`found`:
    its channel files counted and CSC1's size and sampling rate, read where
    the data is), else from the registry. The listing wins because the
    registry can be describing a different copy: measured 2026-10-08, a PTEN
    recording on record as 64 channels and 601 s was 128-plus channel files
    and about 35 minutes on the share, and a walltime set from the record
    would have killed the scan before it finished.

    The rates are what the cluster has measured on this filesystem, or this
    machine's seed until it has run one (`cfc.rate_for`). Said as an
    estimate, because it is one.
    """
    src = dict(rec or {})
    if found:
        _start, fs_f, dur_f = vaccfind_facts(found)
        if dur_f:
            src["duration_s"] = dur_f
        if fs_f:
            src["fs"] = fs_f
        if found.get("n_channels"):
            src["n_channels"] = found["n_channels"]
    n_all = int(src.get("n_channels") or 0)
    n = max(1, n_all - len(spec.get("bad_channels") or [])) if n_all else 0
    span = float(src.get("duration_s") or 0.0)
    fs = float(src.get("fs") or 30000.0)
    seconds = rate_read * span * max(1, n) + rate_detect * max(1, n)
    return {
        "n_channels": n, "n_all": n_all, "span_s": span, "fs": fs,
        "from": "cluster" if found and found.get("n_channels") else "registry",
        "megasamples": span * fs * max(1, n) / 1e6,
        # What a node holds at once: one channel at a time, read in chunks
        # and decimated -- not the whole recording. Asking slurm for memory
        # in proportion to every channel together asked a 128-channel,
        # 35-minute recording for half a terabyte.
        "megasamples_held": span * fs * 2 / 1e6,
        "seconds": round(max(1.0, seconds), 1),
    }


def vaccfind_facts(row):
    """(start, fs, duration) from a cluster listing row -- vaccfind's reader,
    imported late so this module stays importable on a compute node."""
    from . import vaccfind
    return vaccfind.facts_of(row)


def task_for(gid, label, remote, spec, plan):
    """One member of a VACC array: the same shape `_incisor_prepare` builds,
    with no session, no report and no key -- those arrive with the answer."""
    nch = max(1, int(plan.get("n_channels") or 1))
    return {
        "gid": gid, "label": label,
        "sess": None, "report": None, "key": None,
        "spec_local": spec,
        "spec_remote": dict(spec, path=remote),
        "tool_steps": [("ds read", int((plan.get("span_s") or 1) * nch)),
                       ("ds detect", nch)],
        "seconds": float(plan.get("seconds") or 60.0),
        # Sized for what a node holds, one channel at a time (`plan_for`).
        "megasamples": max(0.001, float(plan.get("megasamples_held")
                                        or plan.get("megasamples") or 1.0)),
        "resume": {"vacc_only": True,
                   "request": request_hash(gid, spec)},
        "plan": plan,
    }


def answered(records, gid, rhash):
    """The key of a vault record that answers this exact request, or None."""
    for rec in (records or []):
        if rec.get("gid") == gid and rec.get("request_hash") == rhash:
            return rec.get("params_hash")
    return None


def fetch_full(cfg, computed_on, ssh=None):
    """The whole answer -- with every channel's events -- off the cluster.

    For a machine that has the vault's summary and not the cached events: the
    run directory is in the workspace, which is backed up and not purged, and
    the answer is still there. Raises with a sentence when it is not.
    """
    on = computed_on or {}
    ws, name = on.get("workspace"), on.get("file")
    if not (ws and name) or on.get("kind") != "vacc":
        raise LookupError("This scan does not say where its full answer is "
                          "on the cluster, so it cannot be fetched again. "
                          "Run it again.")
    path = vacc._remote_path(ws, name)
    run = vacc._runner(cfg, ssh)
    raw = run("f=%s; if [ -f \"$f\" ]; then cat \"$f\"; else echo "
              "JARVIS_GONE; fi" % vacc.q(path), timeout=180)
    if (raw or "").strip() == "JARVIS_GONE":
        raise LookupError("The full answer is no longer on the cluster (%s). "
                          "Run the scan again." % path)
    try:
        out = json.loads(raw)
    except ValueError:
        raise LookupError("The answer on the cluster could not be read.")
    rows = out.get("_rows")
    if isinstance(rows, dict):
        out["_rows"] = {(int(k) if str(k).lstrip("-").isdigit() else k): v
                        for k, v in rows.items()}
    return out
