"""
demo.py -- recordings that are not on disk.

Why
---
Nothing in BARRY does anything until somebody has scanned a drive and found
a session. That is fine on the rig and useless everywhere else: a new person
opening it for the first time, on a laptop, with no drive mounted, has an
empty application and a Guide that walks them past features it cannot
demonstrate. The Guide is the first thing anybody uses and it was the thing
least able to show itself.

So there are two recordings that always exist. They behave like any other --
they open, they draw, they have events, bad channels, a curation set, a
layer sheet -- and they are generated rather than stored.

Generated, not shipped
----------------------
Thirty-two channels at 30 kHz for two minutes is about 460 MB of float32.
Shipping that is out of the question, and it is unnecessary: the samples are
a function of (channel, time), so only the window being looked at is ever
computed. The repository cost is this file.

Deterministic
-------------
Panning back to a second you have already seen must show the same trace, or
the app looks broken in a way that is hard to describe. So the noise is
seeded per channel and per one-second block from the session id, which makes
every window reproducible and identical on every machine -- the demo in the
Guide looks the same for everyone, which is the point of using it to teach.

What is in the signal
---------------------
Enough for the panels to be worth looking at, and no more:

  theta        ~8 Hz, amplitude and phase varying with depth, so the CSD
               and the theta panel show a real laminar pattern instead of
               a flat field
  dentate      scripted times, a fast negative deflection largest at
  spikes       mid-depth -- which is what makes the curation exercise
               meaningful rather than a coin toss
  one bad      channel 17 is loud and uncorrelated, so "mark the bad
  channel      channel" has something to find
  noise        pink-ish, because white noise looks nothing like an LFP and
               people learn the wrong thing from it
"""
from __future__ import annotations

import collections
import hashlib

import numpy as np

FS = 30000.0
BLOCK_S = 1.0            # generated a second at a time, then sliced

# Two, deliberately. One short enough to open instantly and walk the Guide
# with; one long enough that panning, the overview strip and the event
# navigation have something to do.
SESSIONS = {
    "ds-tutorial": {
        "id": "ds-tutorial",
        "gid": "demo-ds-tutorial",
        "label": "DEMO m1 s1 (dentate spikes)",
        "project": "DEMO",
        "mouse": 1,
        "session": 1,
        "date": "2020-01-01",
        "duration_s": 120.0,
        "n_channels": 32,
        "bad": [17],
        "note": "A made-up recording, so the Guide has something to show on "
                "a machine with no data mounted. Nothing here is real.",
        # Dentate spikes, in seconds. Irregular on purpose: evenly spaced
        # ones teach a rhythm that does not exist.
        "spikes": [3.4, 7.9, 8.2, 14.6, 21.05, 21.4, 27.8, 33.2, 33.9,
                   41.5, 48.0, 55.7, 56.1, 62.4, 69.9, 70.3, 77.2, 84.6,
                   91.1, 91.8, 98.3, 105.0, 112.7, 118.2],
        # Which of those are real, for the curation exercise. The rest are
        # artifacts that look like one, which is the whole difficulty.
        "real": [0, 1, 3, 4, 6, 7, 9, 10, 12, 13, 15, 16, 18, 20, 22],
    },
    "long-session": {
        "id": "long-session",
        "gid": "demo-long-session",
        "label": "DEMO m2 s3 (a longer one)",
        "project": "DEMO",
        "mouse": 2,
        "session": 3,
        "date": "2020-01-02",
        "duration_s": 900.0,
        "n_channels": 64,
        "bad": [41, 59],
        "note": "Made up, and long enough that panning and the overview "
                "strip have something to do.",
        "spikes": [round(11.3 + i * 37.7, 3) for i in range(23)],
        "real": list(range(0, 23, 2)),
    },
}

PREFIX = "demo:"


def is_demo(path):
    return isinstance(path, str) and path.startswith(PREFIX)


def demo_id(path):
    return str(path)[len(PREFIX):] if is_demo(path) else None


def get(path_or_id):
    key = demo_id(path_or_id) if is_demo(path_or_id) else path_or_id
    return SESSIONS.get(str(key))


def path_for(spec):
    return PREFIX + spec["id"]


# --------------------------------------------------------------------------
# The session, shaped exactly like a real one
# --------------------------------------------------------------------------
def open_session(path, even_only=None, invert=True):
    spec = get(path)
    if not spec:
        return {"ok": False, "error": "No such demo recording: %s" % path}
    n = spec["n_channels"]
    channels = []
    for i in range(n):
        num = i + 1
        channels.append({
            "index": i,
            "number": num,
            "label": "CSC%d" % num,
            "file": None,             # there is no file; that is the point
            "bad": num in spec["bad"],
        })
    return {
        "ok": True,
        "source": "demo",
        "path": path,
        "name": spec["label"],
        "fs": FS,
        "duration_s": spec["duration_s"],
        "n_samples": int(spec["duration_s"] * FS),
        "channels": channels,
        "even_only": False,
        "invert": bool(invert),
        "demo": True,
        "demo_note": spec["note"],
        # A demo has no header clock; a fixed start keeps its identity stable.
        "start": spec["date"] + "T00:00:00",
    }


# --------------------------------------------------------------------------
# The samples
# --------------------------------------------------------------------------
def _seed(spec_id, ch_index, block):
    """A stable 32-bit seed for one channel's one-second block."""
    key = "%s|%d|%d" % (spec_id, ch_index, block)
    return int(hashlib.sha1(key.encode()).hexdigest()[:8], 16)


def _pink(rng, n):
    """Noise that looks like an LFP rather than like white noise.

    A 1/f-ish slope, made by summing a few octaves of smoothed white noise.
    Cheap, and much closer to the thing than randn() is -- people reading a
    demo trace should not learn what white noise looks like.
    """
    out = np.zeros(n, dtype=np.float32)
    amp = 1.0
    step = 1
    for _ in range(6):
        coarse = rng.standard_normal(n // step + 2).astype(np.float32)
        out += amp * np.repeat(coarse, step)[:n]
        amp *= 0.62
        step *= 3
    return out


# Blocks are a pure function of (session, channel, second), so they are
# worth keeping: panning back and forth over the same stretch is the
# commonest thing anybody does, and regenerating pink noise for it is the
# only expensive part of this file. Bounded, and cheap to lose.
_BLOCKS = collections.OrderedDict()
_BLOCK_CAP = 1200          # ~140 MB of float32 at 30 kHz, worst case


def _block(spec, ch, block):
    """One second of one channel, in microvolts. Deterministic, and cached."""
    key = (spec["id"], ch["index"], block)
    hit = _BLOCKS.get(key)
    if hit is not None:
        _BLOCKS.move_to_end(key)
        return hit
    out = _block_make(spec, ch, block)
    _BLOCKS[key] = out
    while len(_BLOCKS) > _BLOCK_CAP:
        _BLOCKS.popitem(last=False)
    return out


def _block_make(spec, ch, block):
    """One second of one channel, in microvolts. Deterministic."""
    n = int(BLOCK_S * FS)
    t0 = block * BLOCK_S
    t = t0 + np.arange(n, dtype=np.float32) / FS
    idx = ch["index"]
    depth = idx / max(1, spec["n_channels"] - 1)       # 0 top, 1 tip
    rng = np.random.default_rng(_seed(spec["id"], idx, block))

    # A bad channel is loud and uncorrelated. Nothing else in it.
    if ch["number"] in spec["bad"]:
        return (_pink(rng, n) * 900.0).astype(np.float32)

    sig = _pink(rng, n) * 55.0

    # Theta, phase-shifted with depth so the CSD has a laminar structure.
    theta_amp = 120.0 * (0.45 + 0.55 * np.sin(np.pi * depth))
    sig += theta_amp * np.sin(2 * np.pi * 8.1 * t + depth * 2.1)

    # Gamma riding on it, stronger where theta is.
    sig += 18.0 * np.sin(2 * np.pi * 62.0 * t + depth * 5.0) \
        * (0.5 + 0.5 * np.sin(2 * np.pi * 8.1 * t))

    # Dentate spikes: a fast negative deflection, biggest mid-depth, with a
    # depth-dependent lag so it looks like something travelling.
    hump = np.exp(-((depth - 0.55) ** 2) / (2 * 0.16 ** 2))
    for k, when in enumerate(spec["spikes"]):
        if when < t0 - 0.2 or when > t0 + BLOCK_S + 0.2:
            continue
        # The ones that are not real are shallower and wider -- the
        # difference a person is being asked to learn.
        real = k in spec["real"]
        width = 0.006 if real else 0.020
        peak = (-1400.0 if real else -420.0) * hump
        centre = when + depth * 0.0015
        sig += peak * np.exp(-((t - centre) ** 2) / (2 * width ** 2))

    return sig.astype(np.float32)


def read_window(session, ch, t0, t1):
    """(samples, actual_t0, fs) for one channel over [t0, t1).

    Generated a second at a time and sliced, so a two-minute recording never
    exists in memory and panning back gives byte-identical samples.
    """
    spec = get(session["path"])
    if not spec:
        return np.zeros(0, dtype=np.float32), float(t0), FS
    dur = spec["duration_s"]
    t0 = max(0.0, min(float(t0), dur))
    t1 = max(t0, min(float(t1), dur))
    if t1 <= t0:
        return np.zeros(0, dtype=np.float32), t0, FS

    first = int(np.floor(t0 / BLOCK_S))
    last = int(np.floor((t1 - 1e-9) / BLOCK_S))
    parts = [_block(spec, ch, b) for b in range(first, last + 1)]
    joined = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    start_of_first = first * BLOCK_S
    i0 = int(round((t0 - start_of_first) * FS))
    i1 = int(round((t1 - start_of_first) * FS))
    out = joined[max(0, i0):max(0, i1)]
    if session.get("invert", True):
        # Same convention as the real reader, so the demo and a recording do
        # not disagree about which way up a spike is.
        out = -out
    return out.astype(np.float32), t0, FS


# --------------------------------------------------------------------------
# What the rest of the app needs to know about them
# --------------------------------------------------------------------------
def registry_rows():
    """Demo sessions, shaped like registry entries so they just appear."""
    out = []
    for spec in SESSIONS.values():
        out.append({
            "gid": spec["gid"],
            "key": "demo_%s" % spec["id"],
            "loose_key": "demo_%s" % spec["id"],
            "label": spec["label"],
            "project": spec["project"],
            "mouse": spec["mouse"],
            "session": spec["session"],
            "date": spec["date"],
            "start": spec["date"] + "T00:00:00",
            "fs": FS,
            "duration_s": spec["duration_s"],
            "n_channels": spec["n_channels"],
            "here": [path_for(spec)],
            "paths": [path_for(spec)],
            "reachable": True,
            "demo": True,
            "note": spec["note"],
            "bad_channels": list(spec["bad"]),
            "has_video": False,
            "converted": False,
            "has": {"bad_channels": len(spec["bad"]), "banked": 1,
                    "ds": 1, "layers": 0, "figures": 0, "note": True,
                    "decks": 0, "spike_sets": 0},
        })
    return out


def events_for(spec_id):
    """The scripted spikes as event records."""
    spec = SESSIONS.get(spec_id)
    if not spec:
        return []
    return [{"start": t, "label": "candidate"} for t in spec["spikes"]]


def curation_events(spec_id):
    """The same spikes, with the answers -- for a pre-sorted demo set.

    Half decided and some flagged, so the Guide can show the flagged pass
    rather than describing it.
    """
    spec = SESSIONS.get(spec_id)
    if not spec:
        return []
    out = []
    for k, t in enumerate(spec["spikes"]):
        real = k in spec["real"]
        if k % 7 == 3:
            label = "flag"          # needs another look
        elif k % 5 == 4:
            label = None            # still undecided
        else:
            label = "spike" if real else "garbage"
        ev = {"start": t}
        if label:
            ev["label"] = label
        out.append(ev)
    return out
