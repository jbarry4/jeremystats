"""histoimg.py -- The histology slide photographs, made viewable.

The problem
-----------
`E:\\Joebot Multisite 2026` holds 63 photographs of stained sections, one
folder per rat, J3 through J11. 62 are TIFF and one is JPEG; together they
are 30.5 GB. A single TIFF averages 470 MB and the largest -- J8's left
hippocampus -- is 679 MB. They are single-frame, uncompressed RGB, around
13858x8914 (123 megapixels); the biggest is 17806x12710 (226 MP).

Two facts make them unusable as they are:

1. **No browser will display a TIFF.** Chrome, Edge and Firefox all refuse
   it. So the original is not merely large, it is unviewable -- shrinking it
   is not an optimisation, it is the only way the GUI can show it at all.
2. **Half a gigabyte is not something to send down a socket**, and at 30.5 GB
   the set is not something to put in a bucket either.

So this module derives two small JPEGs per slide and those are what travel.
The original never moves and is never uploaded: it stays on `E:`, and the
record points at both, so a machine with the drive opens the real thing at
full resolution and a machine without it gets the 2400px copy.

What it costs, measured on this machine
---------------------------------------
Timed against real files rather than guessed (`python tools/check_histoimg.py
--time <file>` re-measures):

    J8_HPC_L_Maybe.tif   679 MB, 226 MP, cold    open 0.11s  decode 5.55s
                                                 web 1.46s   thumb 0.02s
                                                 -> 7.15s total
    J3_ACC.tif           371 MB, 123 MP, warm    decode 0.49s -> 1.42s total
    J11_L_OFC_ACC.jpg    9.1 MB,  88 MP          -> 0.63s total

Decoding is bound by reading the bytes off `E:` -- about 120 MB/s -- and the
LANCZOS resize is bound by pixel count, about 7 ns/px. For an uncompressed
RGB TIFF the two are the same number (bytes are 3 x pixels), which collapses
the whole estimate to one measured constant: **about 88 MB of source per
second, end to end.**

That constant is not arithmetic off the two files above -- it is the whole
batch, timed. All 63 derived in one pass took **345.9 seconds** and produced
**66.4 MB**: 65.3 MB of web copies averaging 1.05 MB each (742 kB to 1.30 MB)
and 1.1 MB of thumbnails averaging 17 kB. Nothing failed. Predicting that run
from the two sample files gave 329 s, five per cent optimistic, which is why
the constant here is the batch figure and not the sample one.

`Image.draft()` is called on every source, and it is worth knowing that it
does nothing for these TIFFs -- Pillow implements draft-mode downscaling for
JPEG and a few raw formats only, and it returned the full 17806x12710 for
every TIFF tried. It halves the one JPEG (11180x7842 -> 5590x3921) and that
is why that file is the fastest in the set by an order of magnitude. The call
stays because it is free when it does not apply and it is the whole cost when
it does.

**RAM: one image at a time, always.** A decoded 123 MP RGB frame is 370 MB
and the largest is 679 MB. Two at once on a 16 GB rig that is also running
Kilosort is not a risk worth taking for a pipeline that is I/O bound anyway,
so `derive_all` holds exactly one open image and closes it before the next.

Why the parser is a table
-------------------------
The filenames are a second source of truth. They carry things the histology
spreadsheet does not -- whether a track missed, whether the region is a guess
-- and they carry them in whatever spelling the person at the microscope used
that month. Hippocampus is spelled four ways in this batch alone (`DHc`,
`DHC`, `HPC`, `hpc`, `Dhc`), the side token appears before the region in
`J11_L_Prh` and after it in `J4_DHc_L`, two names contain a space, and one
slide is both `.jpg` and `.tif`.

These were typed by hand over months and the next batch will spell something
a fifth way. So the vocabulary is **data** -- five dicts below -- and adding a
spelling is adding one line, not editing a regex somebody else has to
re-derive. Anything the tables do not account for is returned in `unparsed`
rather than dropped, so a name nobody anticipated is visible on the listing
instead of silently half-read.

Storage
-------
Derived copies live under `GUI_logs/histo_cache/<rat>/<filename>.web.jpg` and
`.thumb.jpg`, keyed on a `size:mtime` signature of the source in exactly the
way `cloudsync.upload_results` keys its uploads -- so a second run derives
nothing and a source that is re-scanned re-derives.

Note `<filename>`, not `<stem>`: J11 has `J11_L_OFC_ACC.jpg` and
`J11_L_OFC_ACC.tif`, two different files of the same slide. Keyed on the stem
they would share one cache entry, each run would find the other's signature,
and the pair would re-derive for ever.

The signature is kept in a small sidecar beside each pair rather than in one
index file. Two Jarviss against the same `GUI_logs` would contend for an
index, and the constitution's rule about never writing another machine's
record is easier to keep when there is no shared file to write (sec 6b).
Deleting a JPEG by hand also just works: the sidecar is checked against the
files it describes.
"""
from __future__ import annotations

import json
import os
import re
import time

from . import cloud as cloudmod

# --------------------------------------------------------------------------
# Where the slides are
# --------------------------------------------------------------------------
#: The drive the photographs live on. Read only -- nothing here writes,
#: moves or renames anything under it.
ROOT_DEFAULT = r"E:\Joebot Multisite 2026"

_LOGS_DIR = None


def configure(logs_dir):
    """Where to cache. Called once by app.py."""
    global _LOGS_DIR
    _LOGS_DIR = os.path.abspath(logs_dir)


def root():
    """The slide folder on this machine, or wherever it has been pointed.

    The environment wins so a second rig with the drive on a different letter
    needs no edit here -- the same reason cloud.py lets the environment beat
    both of its config files.
    """
    return os.environ.get("Jarvis_HISTO_IMAGES") or ROOT_DEFAULT


def have_drive():
    return os.path.isdir(root())


def cache_dir():
    if not _LOGS_DIR:
        raise RuntimeError("histoimg.configure(logs_dir) was never called")
    return os.path.join(_LOGS_DIR, "histo_cache")


# --------------------------------------------------------------------------
# Derived sizes
# --------------------------------------------------------------------------
WEB_EDGE = 2400          # long edge; 1.05 MB a slide measured, 65 MB for
                         # the set
WEB_QUALITY = 85
THUMB_EDGE = 320         # long edge; 17 kB a slide, 1.1 MB for the set
THUMB_QUALITY = 80

#: End-to-end megabytes of source per second, measured (see the docstring).
#: Only used to say what a run will cost before it is spent.
MB_PER_SECOND = 88.0

#: A compressed source is pixel-bound rather than byte-bound and draft() gets
#: to help, so its size on disk says nothing about the wait. One flat second,
#: measured at 0.63s on the one JPEG in the set.
SECONDS_PER_COMPRESSED = 1.0

#: What one slide weighs once derived -- the web copy plus its thumbnail.
#: 66.4 MB over 63 slides, measured on the whole batch.
MB_PER_SLIDE = 1.055

#: Extensions treated as slides. `.tif` and `.jpg` are what is there;
#: the rest are here so a batch saved differently is picked up rather than
#: silently ignored.
IMAGE_EXTS = (".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp")

#: Which of those Pillow can shrink while decoding.
DRAFTABLE = (".jpg", ".jpeg")


# --------------------------------------------------------------------------
# Supabase
# --------------------------------------------------------------------------
#: The bucket, and it is deliberately the one cloudsync.py already uses.
#:
#: A `histology` bucket of its own would be tidier, but a bucket has to be
#: created in the dashboard with a policy attached before a single byte can
#: go into it -- infrastructure this code cannot create and a report cannot
#: either. `results` exists, works, and is reached by the same key.
#:
#: The prefix keeps the two apart, and nothing collides: `pull_files` fetches
#: the keys named in the `results` *table*, not whatever is in the bucket, and
#: nothing here writes a `results` row. If it did, every laptop would find 126
#: JPEGs of rat brains appearing in its figures folder.
BUCKET = "results"
PREFIX = "histology"

#: Where the upload signatures live in `cloud.state()`. Same mechanism as
#: `upload_results`, a different key: that one owns "uploaded" and sharing it
#: would mean either pipeline's re-run wiping the other's record.
STATE_KEY = "histo_uploaded"


# ==========================================================================
# The name parser
# ==========================================================================
# Every token below was seen in this batch. The point of writing them as
# tables is that the fifth spelling of hippocampus is one line here, added by
# whoever hits it, rather than a regex somebody has to reverse-engineer.

#: Region spellings -> the one id Jarvis uses. Hippocampus is spelled four
#: ways across nine rats; they all mean the hippocampus and they normalise to
#: one id. The spelling itself is not thrown away -- each region carries the
#: `raw` token -- because `DHc` says *dorsal* and `HPC` does not.
REGIONS = {
    "acc": "acc",
    "ofc": "ofc",
    "rsc": "rsc",
    "por": "por",
    "prh": "prh",
    "dhc": "hpc",
    "hpc": "hpc",
}

#: How to print one.
REGION_NAMES = {
    "acc": "ACC", "ofc": "OFC", "rsc": "RSC",
    "por": "POR", "prh": "PRH", "hpc": "HPC",
}

#: Side. It appears before the region (`J11_L_Prh`, `J8_Maybe_L_PRH`) and
#: after it (`J4_DHc_L`, `J10_ACC_R`) with equal frequency, which is why
#: position cannot be part of the rule.
SIDES = {
    "l": "left",
    "r": "right",
}

#: What the person at the microscope concluded, folded onto three words. The
#: raw token is kept beside each: "JustMissed" and "Missed" are both a miss,
#: and the difference between them is worth reading.
VERDICTS = {
    "missed": "missed",
    "justmissed": "missed",
    "not": "not",
    "no": "not",
    "maybe": "maybe",
}

#: Words that are notes about the slide and are NOT interpreted here.
#: `Full` (a whole-section scan), `insular` and `V2` are somebody's aside to
#: the next reader; guessing at them would be inventing data. They are
#: recognised only so that a word nobody has seen before still stands out in
#: `unparsed`.
NOTES = {"full", "insular", "v2"}

#: `J3`, `J10`. The leading token and nothing else.
_RAT = re.compile(r"^j(\d+)$", re.I)

#: Underscore, space or dash. Two filenames in this batch contain a space
#: ("J5_not por.tif", "J6_Not POR_R.tif") so splitting on underscore alone
#: reads `not por` as one unknown token.
_SPLIT = re.compile(r"[\s_\-]+")


def parse_name(filename):
    """What a slide's filename claims, and what of it could not be read.

    Case-insensitive throughout: `DHc`, `DHC` and `hpc` are the same region,
    `Maybe` and `maybe` the same verdict.

    Returns a dict. The fields that matter to a caller:

        rat            "J6", or None
        regions        [{"id": "ofc", "raw": "OFC"}, ...] -- often TWO, since
                       one section can carry OFC and ACC at once
        side           "left" / "right" / None
        side_specific  False when the name carries no side at all. An image
                       that is not side-specific is a fact; a guessed side
                       is not.
        side_ambiguous True when the name carries two different sides and
                       there is no defensible way to pick one
        verdicts       [{"id": "maybe", "raw": "Maybe"}, ...]
        notes          ["Full"] -- verbatim, uninterpreted
        unparsed       every token none of the tables accounted for
    """
    base = os.path.basename(filename or "")
    stem, ext = os.path.splitext(base)
    tokens = [t for t in _SPLIT.split(stem) if t]

    out = {
        "file": base, "stem": stem, "ext": ext.lower(),
        "rat": None, "rat_n": None,
        "regions": [], "region_ids": [],
        "side": None, "side_specific": False, "side_ambiguous": False,
        "side_candidates": [], "side_where": None,
        "verdicts": [], "verdict_ids": [],
        "notes": [], "unparsed": [], "tokens": list(tokens),
    }

    region_at, side_at = [], []
    for i, tok in enumerate(tokens):
        low = tok.lower()
        if i == 0 and _RAT.match(tok):
            out["rat"] = "J" + _RAT.match(tok).group(1)
            out["rat_n"] = int(_RAT.match(tok).group(1))
            continue
        if low in REGIONS:
            out["regions"].append({"id": REGIONS[low], "raw": tok,
                                   "name": REGION_NAMES[REGIONS[low]]})
            out["region_ids"].append(REGIONS[low])
            region_at.append(i)
            continue
        if low in SIDES:
            side_at.append((i, SIDES[low], tok))
            continue
        if low in VERDICTS:
            out["verdicts"].append({"id": VERDICTS[low], "raw": tok})
            out["verdict_ids"].append(VERDICTS[low])
            continue
        if low in NOTES:
            out["notes"].append(tok)          # verbatim, on purpose
            continue
        out["unparsed"].append(tok)

    # -- side ------------------------------------------------------------
    # One distinct side is the answer wherever in the name it sits, which is
    # what makes `J5_OFC_R_ACC_` readable: the R is between two regions, so
    # it is unclear which region it belongs to, but the slide is a right-hand
    # slide either way and that is the question being asked.
    #
    # Two DIFFERENT sides is not answerable. `J11_R_Dhc_L_Maybe` carries R
    # before the region and L after it, and nothing in the name says which
    # was the mistake. It is reported ambiguous rather than resolved, for the
    # same reason the event bank refuses an ambiguous version number: a wrong
    # answer here labels a hemisphere somebody will analyse.
    distinct = sorted({s for _i, s, _raw in side_at})
    if side_at:
        out["side_specific"] = True
        out["side_candidates"] = distinct
        if len(distinct) == 1:
            out["side"] = distinct[0]
        else:
            out["side_ambiguous"] = True
        if region_at:
            lo, hi = min(region_at), max(region_at)
            idx = [i for i, _s, _raw in side_at]
            if all(i < lo for i in idx):
                out["side_where"] = "before"
            elif all(i > hi for i in idx):
                out["side_where"] = "after"
            else:
                out["side_where"] = "inside"

    return out


def describe(parsed):
    """One line a person can read. Says what is not known, rather than
    leaving the gap to be read as an absence of a problem."""
    bits = []
    if parsed.get("rat"):
        bits.append(parsed["rat"])
    regions = "+".join(r["name"] for r in parsed["regions"]) or "no region"
    bits.append(regions)
    if parsed.get("side_ambiguous"):
        bits.append("side unclear (%s)" % " and ".join(
            parsed["side_candidates"]))
    elif parsed.get("side"):
        bits.append(parsed["side"])
    else:
        bits.append("not side-specific")
    for v in parsed["verdicts"]:
        bits.append(v["raw"])
    bits.extend(parsed["notes"])
    if parsed["unparsed"]:
        bits.append("unread: " + " ".join(parsed["unparsed"]))
    return " - ".join(bits)


# ==========================================================================
# The catalogue
# ==========================================================================
def _sig(path):
    """`size:mtime`, exactly as cloudsync.upload_results spells it, so the
    two pipelines mean the same thing by "this file has not changed"."""
    try:
        return "%d:%d" % (os.path.getsize(path), int(os.path.getmtime(path)))
    except OSError:
        return None


def _cache_paths(rat, name):
    d = os.path.join(cache_dir(), rat)
    # The full filename, extension and all -- see the module docstring on
    # J11_L_OFC_ACC existing as both .jpg and .tif.
    return {
        "dir": d,
        "web": os.path.join(d, name + ".web.jpg"),
        "thumb": os.path.join(d, name + ".thumb.jpg"),
        "sidecar": os.path.join(d, name + ".json"),
    }


def _read_sidecar(paths):
    try:
        with open(paths["sidecar"], "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


def cache_state(rat, name, sig):
    """Is the derived pair present and still describing this source?

    Both JPEGs have to exist as well as the sidecar: somebody clearing space
    by deleting a folder of thumbnails should get them rebuilt, not a
    pipeline that believes a file it can see is missing.
    """
    paths = _cache_paths(rat, name)
    side = _read_sidecar(paths)
    have = os.path.isfile(paths["web"]) and os.path.isfile(paths["thumb"])
    fresh = bool(have and sig and side.get("sig") == sig)
    return {"derived": fresh, "files_present": have,
            "sig": side.get("sig"), "meta": side, "paths": paths}


def keys_for(rat, name):
    """The two bucket keys for one slide.

    Percent-encoding is `cloud.upload`'s job, so the key stays the literal
    path -- spaces and all, since two of these filenames have one -- and
    what is stored is what a listing shows.
    """
    return {"web": "%s/%s/%s.web.jpg" % (PREFIX, rat, name),
            "thumb": "%s/%s/%s.thumb.jpg" % (PREFIX, rat, name)}


#: What the bucket holds, held between renders. Supabase egress is counted
#: in REQUESTS, not bytes (sec 6b), and walking the prefix is eleven of them
#: -- one for the rat folders and one per rat. A panel that repainted every
#: few seconds would spend those eleven every time for a listing that changes
#: when somebody runs a derive, which is roughly never.
_CLOUD_LIST = {"at": 0.0, "rats": None}
CLOUD_LIST_TTL = 300


def cloud_index(cloud_client, force=False):
    """Which slides have a copy in the bucket, per rat.

    This is what a machine with no `E:` has instead of a drive walk. It
    cannot say how big the original is or when it was taken -- nothing up
    there knows -- so it says what it does know and leaves the rest null
    rather than filling it in.

    Storage listing is not recursive, so the prefix is walked a folder at a
    time. Eleven requests, held for CLOUD_LIST_TTL.
    """
    if cloud_client is None or not cloud_client.configured:
        return {}
    now_t = time.time()
    if (not force and _CLOUD_LIST["rats"] is not None
            and now_t - _CLOUD_LIST["at"] < CLOUD_LIST_TTL):
        return _CLOUD_LIST["rats"]
    rats = {}
    try:
        for top in cloud_client.list_objects(BUCKET, PREFIX + "/"):
            rat = top.get("name")
            # A folder comes back with no id. An object directly under the
            # prefix is not one of ours and is left alone.
            if not rat or top.get("id"):
                continue
            for obj in cloud_client.list_objects(
                    BUCKET, "%s/%s/" % (PREFIX, rat)):
                key = obj.get("name") or ""
                for suffix, kind in ((".web.jpg", "web"),
                                     (".thumb.jpg", "thumb")):
                    if key.endswith(suffix):
                        slide = key[:-len(suffix)]
                        rats.setdefault(rat, {}).setdefault(
                            slide, {})[kind] = (
                                (obj.get("metadata") or {}).get("size"))
                        break
    except Exception:                                      # noqa: BLE001
        # A listing that cannot be fetched is "nobody is reported present",
        # the same answer the presence layer gives: what is available, not a
        # claim that there is nothing there.
        return _CLOUD_LIST["rats"] or {}
    _CLOUD_LIST.update({"at": now_t, "rats": rats})
    return rats


def index(cloud_client=None):
    """Every slide on the drive, with what is known and what is derived.

    One directory read per rat folder and one small sidecar read per slide --
    no image is opened, so this is cheap enough to be the listing route.

    **With no drive it falls back to the bucket**, which is the entire point
    of uploading the copies: a laptop that has never seen `E:` still gets a
    list of slides and can open any of them. What it cannot get is the size
    of an original it has no access to, and that reads as null rather than
    as zero.
    """
    base = root()
    uploaded = {}
    if cloud_client is not None:
        try:
            uploaded = (cloud_client.state() or {}).get(STATE_KEY) or {}
        except Exception:                                  # noqa: BLE001
            uploaded = {}

    out = {"root": base, "present": os.path.isdir(base), "rats": [],
           "files": 0, "bytes": 0, "derived": 0, "uploaded": 0,
           "ambiguous": [], "unparsed": [], "source": "drive"}
    if not out["present"]:
        out["source"] = "cloud"
        return _index_from_cloud(out, cloud_index(cloud_client))

    for rat in sorted(os.listdir(base), key=_rat_key):
        rat_dir = os.path.join(base, rat)
        if not os.path.isdir(rat_dir):
            continue
        rows = []
        for name in sorted(os.listdir(rat_dir)):
            path = os.path.join(rat_dir, name)
            if not os.path.isfile(path):
                continue
            if os.path.splitext(name)[1].lower() not in IMAGE_EXTS:
                continue
            sig = _sig(path)
            parsed = parse_name(name)
            state = cache_state(rat, name, sig)
            keys = keys_for(rat, name)
            up = (uploaded.get(keys["web"]) == sig
                  and uploaded.get(keys["thumb"]) == sig)
            row = {
                "rat": rat, "file": name,
                # Both, always. A machine with E: opens the original; one
                # without it gets the web copy, and the record has to carry
                # each so neither has to guess what the other can reach.
                "original": path,
                "original_bytes": os.path.getsize(path) if sig else None,
                "sig": sig,
                "parsed": parsed,
                "says": describe(parsed),
                "derived": state["derived"],
                "web_bytes": state["meta"].get("web_bytes"),
                "thumb_bytes": state["meta"].get("thumb_bytes"),
                "pixels": state["meta"].get("pixels"),
                "uploaded": bool(up),
                "keys": keys,
            }
            rows.append(row)
            out["files"] += 1
            out["bytes"] += row["original_bytes"] or 0
            out["derived"] += 1 if row["derived"] else 0
            out["uploaded"] += 1 if row["uploaded"] else 0
            if parsed["side_ambiguous"]:
                out["ambiguous"].append(name)
            if parsed["unparsed"]:
                out["unparsed"].append({"file": name,
                                        "tokens": parsed["unparsed"]})
        if rows:
            out["rats"].append({"rat": rat, "n": len(rows),
                                "bytes": sum(r["original_bytes"] or 0
                                             for r in rows),
                                "files": rows})
    return out


def _index_from_cloud(out, rats):
    """The same listing shape, built from what is in the bucket.

    One shape, two sources -- so whatever draws this does not need to know
    which machine it is on (sec 6c). The fields a drive would fill and the
    cloud cannot are None, which is not the same as zero: `original_bytes`
    of None means "this machine cannot see the original", and a surface that
    reads that as "the file is empty" is claiming something nobody checked.
    """
    for rat in sorted(rats, key=_rat_key):
        rows = []
        for name in sorted(rats[rat]):
            parsed = parse_name(name)
            paths = _cache_paths(rat, name)
            rows.append({
                "rat": rat, "file": name,
                "original": None, "original_bytes": None, "sig": None,
                "parsed": parsed, "says": describe(parsed),
                # Cached here means fetched from the bucket earlier; there
                # is no source to check it against, and saying so is more
                # honest than calling it derived.
                "derived": os.path.isfile(paths["web"]),
                "web_bytes": rats[rat][name].get("web"),
                "thumb_bytes": rats[rat][name].get("thumb"),
                "pixels": None,
                "uploaded": True,
                "keys": keys_for(rat, name),
            })
            out["files"] += 1
            out["uploaded"] += 1
            out["derived"] += 1 if rows[-1]["derived"] else 0
            if parsed["side_ambiguous"]:
                out["ambiguous"].append(name)
            if parsed["unparsed"]:
                out["unparsed"].append({"file": name,
                                        "tokens": parsed["unparsed"]})
        if rows:
            out["rats"].append({"rat": rat, "n": len(rows), "bytes": None,
                                "files": rows})
    return out


def _rat_key(name):
    """J3 before J10. Sorted as text, nine rats come out J10, J11, J3..."""
    m = _RAT.match(name or "")
    return (0, int(m.group(1))) if m else (1, str(name).lower())


# ==========================================================================
# Cost, before it is spent (sec 6b)
# ==========================================================================
def estimate(force=False, idx=None):
    """How many, how many megabytes, and roughly how long.

    The seconds come from this machine's measured throughput, not from a
    guess -- see MB_PER_SECOND and the module docstring. Files already
    derived are excluded unless `force`, so the number shrinks as the work is
    done rather than restating the whole job every time somebody opens the
    panel.
    """
    idx = idx if idx is not None else index()
    if not idx.get("present"):
        # Nothing to spend. A machine with no drive is not a machine with
        # nothing to do -- it just is not the one that does this.
        return {"images": 0, "already_derived": 0, "source_mb": 0.0,
                "seconds": 0.0, "derived_mb": 0.0, "upload_mb": 0.0,
                "rate_mb_s": MB_PER_SECOND,
                "note": ("%s is not on this machine, so there is nothing "
                         "here to derive. Whatever has been uploaded is "
                         "still viewable." % idx.get("root"))}
    todo, todo_bytes, seconds = 0, 0, 0.0
    for rat in idx["rats"]:
        for row in rat["files"]:
            if row["derived"] and not force:
                continue
            todo += 1
            todo_bytes += row["original_bytes"] or 0
            if os.path.splitext(row["file"])[1].lower() in DRAFTABLE:
                seconds += SECONDS_PER_COMPRESSED
            else:
                seconds += (row["original_bytes"] or 0) / 1e6 / MB_PER_SECOND
    # What the derive produces. 66.4 MB over 63 slides, measured, not the
    # 0.5-1 MB a JPEG of this size was expected to come to.
    out_mb = todo * MB_PER_SLIDE
    return {
        "images": todo,
        "already_derived": idx["derived"] if not force else 0,
        "source_mb": round(todo_bytes / 1e6, 1),
        "seconds": round(seconds, 1),
        "derived_mb": round(out_mb, 1),
        "upload_mb": round(out_mb, 1),
        "rate_mb_s": MB_PER_SECOND,
        # Nothing to do is an answer, and it says what would change it
        # rather than quoting a cost of zero (sec 5).
        "note": (("All %d slides are already derived, so a run would read "
                  "nothing. Force one to redo them -- about %s and %.0f MB "
                  "back up." % (idx["derived"],
                                _mins(idx["bytes"] / 1e6 / MB_PER_SECOND),
                                idx["files"] * MB_PER_SLIDE))
                 if not todo else
                 ("%d images, %.1f GB to read, about %s, %.0f MB up. "
                  "Nothing is uploaded but the two small copies -- the "
                  "originals stay on %s."
                  % (todo, todo_bytes / 1e9, _mins(seconds), out_mb,
                     idx["root"]))),
    }


def _mins(seconds):
    if seconds < 90:
        return "%d seconds" % round(seconds)
    return "%.0f minutes" % (seconds / 60.0)


# ==========================================================================
# Deriving
# ==========================================================================
def _pillow():
    """Imported here, not at module scope.

    A missing Pillow should fail this one pipeline with a sentence somebody
    can act on, not stop app.py importing and take the whole GUI with it.
    """
    try:
        from PIL import Image
    except ImportError as exc:                             # noqa: BLE001
        raise RuntimeError(
            "Pillow is not installed in this environment, so the histology "
            "slides cannot be shrunk. `pip install Pillow`.") from exc
    return Image


class _NoBombLimit:
    """Lift Pillow's decompression-bomb ceiling, for our decode only.

    These slides are 123-226 megapixels and Pillow refuses anything over
    ~179 MP by default -- the guard exists because a hostile 50 KB file can
    claim to be 30000x30000 and exhaust the machine decoding it.

    Setting `Image.MAX_IMAGE_PIXELS = None` at module scope, which is the
    usual advice, turns that guard off for every other user of Pillow in the
    process too -- and this process also makes thumbnails of files it did not
    write. Scoped and restored instead: same effect here, no hole anywhere
    else.
    """

    def __enter__(self):
        self.Image = _pillow()
        self.was = self.Image.MAX_IMAGE_PIXELS
        self.Image.MAX_IMAGE_PIXELS = None
        return self.Image

    def __exit__(self, *exc):
        self.Image.MAX_IMAGE_PIXELS = self.was
        return False


def _shrink(im, edge, Image):
    w, h = im.size
    scale = float(edge) / max(w, h)
    if scale >= 1.0:
        return im.copy()
    return im.resize((max(1, int(round(w * scale))),
                      max(1, int(round(h * scale)))), Image.LANCZOS)


def derive_one(rat, name, force=False):
    """Make the web copy and the thumbnail for one slide.

    One image open at a time and closed before returning -- a decoded frame
    here is 370 to 679 MB.

    EXIF is stripped by construction: the resized image is a new object and
    nothing is copied onto it, so nothing goes up but pixels.
    """
    path = os.path.join(root(), rat, name)
    if not os.path.isfile(path):
        return {"ok": False, "file": name, "error": "not on this machine"}
    sig = _sig(path)
    state = cache_state(rat, name, sig)
    if state["derived"] and not force:
        return {"ok": True, "file": name, "skipped": True,
                "web_bytes": state["meta"].get("web_bytes"),
                "thumb_bytes": state["meta"].get("thumb_bytes")}

    paths = state["paths"]
    os.makedirs(paths["dir"], exist_ok=True)
    started = time.time()
    ext = os.path.splitext(name)[1].lower()

    with _NoBombLimit() as Image:
        im = None
        try:
            im = Image.open(path)
            pixels = im.size
            if ext in DRAFTABLE:
                # Free when it does not apply. For the one JPEG in this set
                # it halves the decode, which is most of that file's cost.
                try:
                    im.draft("RGB", (WEB_EDGE, WEB_EDGE))
                except Exception:                          # noqa: BLE001
                    pass
            rgb = im.convert("RGB")
            web = _shrink(rgb, WEB_EDGE, Image)
            web.save(paths["web"] + ".tmp", "JPEG", quality=WEB_QUALITY,
                     optimize=True)
            # From the web copy, not from the original: it is already the
            # right aspect, and resampling 2400px costs nothing next to
            # resampling 13858.
            thumb = _shrink(web, THUMB_EDGE, Image)
            thumb.save(paths["thumb"] + ".tmp", "JPEG",
                       quality=THUMB_QUALITY, optimize=True)
            web_size, thumb_size = web.size, thumb.size
        except Exception as exc:                           # noqa: BLE001
            for p in (paths["web"] + ".tmp", paths["thumb"] + ".tmp"):
                try:
                    os.remove(p)
                except OSError:
                    pass
            return {"ok": False, "file": name, "error": str(exc)[:200]}
        finally:
            # Explicit, because the next slide needs the memory before the
            # collector would otherwise get round to it.
            try:
                if im is not None:
                    im.close()
            except Exception:                              # noqa: BLE001
                pass
            rgb = web = thumb = None

    os.replace(paths["web"] + ".tmp", paths["web"])
    os.replace(paths["thumb"] + ".tmp", paths["thumb"])
    meta = {
        "sig": sig, "source": path, "rat": rat, "file": name,
        "pixels": list(pixels), "web_px": list(web_size),
        "thumb_px": list(thumb_size),
        "web_bytes": os.path.getsize(paths["web"]),
        "thumb_bytes": os.path.getsize(paths["thumb"]),
        "seconds": round(time.time() - started, 2),
        "at": cloudmod.now(),
    }
    tmp = paths["sidecar"] + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
    os.replace(tmp, paths["sidecar"])
    out = {"ok": True, "file": name, "skipped": False}
    out.update(meta)
    return out


def derive_all(on_progress=None, force=False, limit=None):
    """Every slide that needs one, one at a time.

    Failures are collected rather than raised, the way `upload_results` does
    it: one unreadable TIFF must not cost the other 62.
    """
    idx = index()
    if not idx["present"]:
        return {"derived": 0, "skipped": 0, "failed": [],
                "error": "%s is not on this machine." % idx["root"]}
    done, skipped, failed = 0, 0, []
    seconds = 0.0
    todo = [(r["rat"], row["file"])
            for r in idx["rats"] for row in r["files"]
            if force or not row["derived"]]
    total = len(todo)
    for i, (rat, name) in enumerate(todo):
        res = derive_one(rat, name, force=force)
        if not res.get("ok"):
            failed.append({"file": name, "rat": rat,
                           "error": res.get("error")})
        elif res.get("skipped"):
            skipped += 1
        else:
            done += 1
            seconds += res.get("seconds") or 0
        if on_progress:
            on_progress(rat, name, i + 1, total)
        if limit and done >= limit:
            break
    return {"derived": done, "skipped": skipped, "failed": failed,
            "seconds": round(seconds, 1), "of": total}


# ==========================================================================
# Uploading
# ==========================================================================
def upload_all(cloud_client, on_progress=None, force=False):
    """Put the two small copies in the bucket. Never the original.

    Modelled on `cloudsync.upload_results`, down to the `size:mtime`
    signature held in `cloud.state()` -- so a second run is a no-op, and a
    slide that was re-photographed goes up again because its signature moved.

    Note what the signature is of: the SOURCE, not the derived JPEG. Two
    machines deriving the same slide produce JPEGs that differ in the last
    byte and agree in every way that matters, and keying on the derived file
    would have them overwrite each other for ever.
    """
    idx = index(cloud_client)
    if not idx["present"]:
        return {"uploaded": 0, "skipped": 0, "failed": [],
                "error": "%s is not on this machine." % idx["root"]}
    state = cloud_client.state()
    seen = {} if force else dict((state.get(STATE_KEY) or {}))
    done, skipped, failed = 0, 0, []
    sent_bytes = 0
    for rat in idx["rats"]:
        for row in rat["files"]:
            if not row["derived"]:
                continue          # nothing to send yet; derive first
            sig, keys = row["sig"], row["keys"]
            paths = _cache_paths(rat["rat"], row["file"])
            for kind in ("web", "thumb"):
                key, src = keys[kind], paths[kind]
                if not os.path.isfile(src):
                    continue
                if seen.get(key) == sig and not force:
                    skipped += 1
                    continue
                try:
                    cloud_client.upload(BUCKET, key, src, "image/jpeg")
                    seen[key] = sig
                    sent_bytes += os.path.getsize(src)
                    done += 1
                    if on_progress:
                        on_progress(key, done)
                except cloudmod.CloudError as exc:
                    # Collected, never raised: a bad network at slide 4
                    # must not lose slides 5 to 63.
                    failed.append({"key": key, "error": str(exc)[:200]})
    cloud_client.save_state({STATE_KEY: seen})
    return {"uploaded": done, "skipped": skipped, "failed": failed,
            "mb": round(sent_bytes / 1e6, 1)}


# ==========================================================================
# Serving one
# ==========================================================================
def local_copy(rat, name, kind="web", cloud_client=None, derive=True):
    """A path on this machine for one derived image, or None.

    Three ways to get one, in the order that costs least:

      1. it is in the cache and matches the source            -- a stat
      2. the drive is here, so derive it now                  -- seconds
      3. the drive is NOT here, so fetch the copy from the bucket

    Three is the case that matters: a laptop that has never seen `E:` still
    shows the slide, because the web copy went up precisely so it could.
    """
    if kind not in ("web", "thumb"):
        return None, "kind must be web or thumb"
    paths = _cache_paths(rat, name)
    src = os.path.join(root(), rat, name)
    sig = _sig(src) if os.path.isfile(src) else None

    if sig:
        if cache_state(rat, name, sig)["derived"]:
            return paths[kind], None
        if derive:
            res = derive_one(rat, name)
            if res.get("ok"):
                return paths[kind], None
            return None, res.get("error")

    # No drive. A cached copy from a previous fetch is still the answer --
    # there is no source to check it against, and an unverifiable copy of the
    # right image beats no image.
    if os.path.isfile(paths[kind]):
        return paths[kind], None

    if cloud_client is None or not cloud_client.configured:
        return None, ("%s is not on this machine and the cloud is not "
                      "configured, so there is no copy of this slide to "
                      "show." % root())
    key = keys_for(rat, name)[kind]
    try:
        os.makedirs(paths["dir"], exist_ok=True)
        cloud_client.download(BUCKET, key, paths[kind])
        return paths[kind], None
    except cloudmod.CloudError as exc:
        return None, ("no copy of this slide has been uploaded yet (%s)"
                      % str(exc)[:160])
