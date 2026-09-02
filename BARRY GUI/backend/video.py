"""
video.py -- Session video and position tracking, synced to the trace cursor.

Neuralynx writes two very different "VT" things and they are easy to confuse:

    VT1.mpg   real video, MPEG-1/2. No browser can decode this natively, so it
              is transcoded on demand -- and only the few seconds around the
              cursor, never the whole file.
    VT1.nvt   position tracking (x/y/angle per frame), not video at all. This
              needs no transcoding: it is drawn as a live path that scrubs with
              the trace cursor.

Anything already browser-native (.mp4/.webm/.m4v with H.264/VP9) is streamed
directly with HTTP range support and seeks natively, no ffmpeg involved.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time

from . import nlx, sysinfo

# Containers a browser can usually play as-is.
NATIVE_EXTS = {".mp4", ".m4v", ".webm", ".ogv"}
# Containers that need transcoding to be viewable.
TRANSCODE_EXTS = {".mpg", ".mpeg", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".m2v", ".vob"}
VIDEO_EXTS = NATIVE_EXTS | TRANSCODE_EXTS

# Codecs that are fine inside an .mp4/.mkv; anything else gets transcoded even
# in a "native" container.
NATIVE_CODECS = {"h264", "vp8", "vp9", "av1", "theora"}

_CACHE_LOCK = threading.Lock()
_CLIP_CACHE = {}
MAX_CACHED_CLIPS = 24
MAX_CLIP_SECONDS = 120

# How far before the requested time to begin decoding, so the clip starts on a
# real keyframe. MPEG-1 from Cheetah typically has a GOP of well under a
# second, but network-copied files vary; 3 s is cheap insurance.
PREROLL_S = 3.0


class VideoError(Exception):
    """Video failure with a message meant to be shown to the user."""


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
def find_media(folder):
    """List the video and tracking files that sit beside a recording."""
    if not folder or not os.path.isdir(folder):
        return {"videos": [], "tracking": []}

    videos, tracking = [], []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return {"videos": [], "tracking": []}

    for name in names:
        full = os.path.join(folder, name)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(name)[1].lower()
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        if ext in VIDEO_EXTS:
            videos.append({
                "name": name, "path": full, "ext": ext, "bytes": size,
                "native": ext in NATIVE_EXTS,
                "needs_ffmpeg": ext in TRANSCODE_EXTS,
            })
        elif ext == ".nvt":
            tracking.append({"name": name, "path": full, "bytes": size})
    return {"videos": videos, "tracking": tracking}


def probe(path):
    """Duration, codec and size for a video, via ffprobe when available."""
    if not os.path.isfile(path):
        raise VideoError("Video not found: " + path)

    ext = os.path.splitext(path)[1].lower()
    info = {
        "path": path, "name": os.path.basename(path), "ext": ext,
        "bytes": os.path.getsize(path),
        "native": ext in NATIVE_EXTS,
        "duration_s": None, "codec": None, "width": None, "height": None,
        "fps": None, "probed": False,
    }

    ffprobe = sysinfo.find_ffprobe()
    if not ffprobe:
        info["note"] = ("ffprobe not found, so duration and codec are unknown. "
                        + sysinfo.ffmpeg_install_hint())
        return info

    try:
        res = subprocess.run(
            [ffprobe, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", "-select_streams", "v:0", path],
            capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            info["note"] = "ffprobe failed: " + (res.stderr or "").strip()[:300]
            return info
        data = json.loads(res.stdout or "{}")
    except subprocess.TimeoutExpired:
        info["note"] = "ffprobe timed out reading this file."
        return info
    except Exception as exc:
        info["note"] = "ffprobe error: %s" % exc
        return info

    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    if streams:
        s = streams[0]
        info["codec"] = s.get("codec_name")
        info["width"] = s.get("width")
        info["height"] = s.get("height")
        rate = s.get("avg_frame_rate") or s.get("r_frame_rate") or ""
        if "/" in rate:
            try:
                num, den = rate.split("/")
                info["fps"] = round(float(num) / float(den), 3) if float(den) else None
            except (ValueError, ZeroDivisionError):
                pass
    try:
        info["duration_s"] = float(fmt.get("duration"))
    except (TypeError, ValueError):
        pass

    info["probed"] = True
    # A native container can still hold a codec browsers refuse.
    info["playable_direct"] = bool(
        info["native"] and (info["codec"] or "").lower() in NATIVE_CODECS)
    return info


# --------------------------------------------------------------------------
# Clip extraction
# --------------------------------------------------------------------------
def clip(path, t0, duration, offset=0.0, width=480, quality=28):
    """Transcode a short window to browser-playable MP4. Returns a file path.

    Only the requested window is decoded, so this stays fast even on a
    multi-gigabyte MPEG on a network share. See the seek comment below for why
    it is a two-stage seek rather than a single one.

    `offset` shifts video time relative to recording time, for rigs where the
    camera and the acquisition did not start together.
    """
    ffmpeg = sysinfo.find_ffmpeg()
    if not ffmpeg:
        raise VideoError(
            "This video needs ffmpeg to play in a browser, and ffmpeg was not "
            "found.\n\n" + sysinfo.ffmpeg_install_hint())

    if not os.path.isfile(path):
        raise VideoError("Video not found: " + path)

    duration = float(max(0.2, min(duration, MAX_CLIP_SECONDS)))
    start = max(0.0, float(t0) + float(offset))

    key = "%s|%.3f|%.3f|%d|%d" % (os.path.abspath(path), start, duration,
                                  int(width), int(quality))
    with _CACHE_LOCK:
        hit = _CLIP_CACHE.get(key)
        if hit and os.path.isfile(hit["path"]):
            hit["used"] = time.time()
            return hit["path"]

    import tempfile
    out_dir = os.path.join(tempfile.gettempdir(), "barrygui_clips")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "clip_%s.mp4" % abs(hash(key)))

    # Two-stage seek. A single `-ss` before `-i` is fast but lands on whatever
    # keyframe precedes the target, so an MPEG-1 file (long GOPs, few
    # I-frames) decodes garbage or a frozen frame until the next keyframe
    # arrives -- which on a 30 s clip can be most of the clip.
    #
    # So: seek fast to PREROLL seconds before the target (input seek, cheap),
    # then seek accurately forward by that preroll (output seek, exact). The
    # decoder gets a clean keyframe to start from and the first displayed frame
    # is the one actually asked for.
    preroll = min(PREROLL_S, start)
    coarse = max(0.0, start - preroll)

    # Long clips re-encode a lot of frames; a faster preset keeps the wait
    # bounded at a small quality cost nobody will see in a behavior video.
    preset = "ultrafast" if duration > 12 else "veryfast"

    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", "%.3f" % coarse,         # fast input seek to a keyframe
        "-i", path,
        "-ss", "%.3f" % preroll,        # accurate output seek from there
        "-t", "%.3f" % duration,
        "-an",                          # no audio: these recordings have none
        "-vf", "scale=%d:-2" % int(width),
        "-c:v", "libx264", "-preset", preset, "-crf", str(int(quality)),
        "-pix_fmt", "yuv420p",
        # Start the clip on a keyframe and keep them frequent, so the browser
        # can render immediately and scrub within the clip.
        "-g", "30", "-force_key_frames", "expr:gte(t,0)",
        "-avoid_negative_ts", "make_zero",
        "-max_muxing_queue_size", "1024",
        # faststart alone (moov atom moved to the front). It must NOT be
        # combined with frag_keyframe/empty_moov -- fragmented output has no
        # moov to relocate, and the mix produces a file some browsers refuse.
        "-movflags", "+faststart",
        out,
    ]
    # Budget scales with clip length; a fixed timeout truncates long extracts
    # on a network share and leaves a half-written file behind.
    timeout = int(max(90, min(600, 30 + duration * 12)))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.remove(out)
        except OSError:
            pass
        raise VideoError(
            "ffmpeg timed out after %ds extracting %.1f s at %.1f s.\n\n"
            "The file may be on a slow share. Try a shorter clip, or copy the "
            "video locally first." % (timeout, duration, start))
    except Exception as exc:
        raise VideoError("Could not run ffmpeg: %s" % exc)

    if res.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
        raise VideoError(
            "ffmpeg could not extract that clip.\n\nffmpeg said:\n%s"
            % (res.stderr or "(no output)").strip()[:600])

    with _CACHE_LOCK:
        _CLIP_CACHE[key] = {"path": out, "used": time.time()}
        if len(_CLIP_CACHE) > MAX_CACHED_CLIPS:
            oldest = sorted(_CLIP_CACHE.items(), key=lambda kv: kv[1]["used"])
            for k, v in oldest[:len(_CLIP_CACHE) - MAX_CACHED_CLIPS]:
                _CLIP_CACHE.pop(k, None)
                try:
                    os.remove(v["path"])
                except OSError:
                    pass
    return out


def frame(path, t, offset=0.0, width=480):
    """Single JPEG frame at a time point, for a cheap scrubbing preview."""
    ffmpeg = sysinfo.find_ffmpeg()
    if not ffmpeg:
        raise VideoError("Extracting a frame needs ffmpeg.\n\n"
                         + sysinfo.ffmpeg_install_hint())
    if not os.path.isfile(path):
        raise VideoError("Video not found: " + path)

    start = max(0.0, float(t) + float(offset))
    preroll = min(PREROLL_S, start)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error",
           "-ss", "%.3f" % (start - preroll), "-i", path,
           "-ss", "%.3f" % preroll,          # accurate seek, same as clip()
           "-frames:v", "1",
           "-vf", "scale=%d:-2" % int(width),
           "-f", "image2pipe", "-vcodec", "mjpeg", "-"]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise VideoError("ffmpeg timed out grabbing a frame at %.2f s." % start)
    if res.returncode != 0 or not res.stdout:
        raise VideoError("No frame at %.2f s. The video may be shorter than the "
                         "recording, or the offset may be wrong." % start)
    return res.stdout


def cleanup_clips():
    """Delete cached clips; called on shutdown and from the Misc utilities."""
    import tempfile, shutil
    removed = 0
    with _CACHE_LOCK:
        for v in _CLIP_CACHE.values():
            try:
                os.remove(v["path"])
                removed += 1
            except OSError:
                pass
        _CLIP_CACHE.clear()
    out_dir = os.path.join(tempfile.gettempdir(), "barrygui_clips")
    if os.path.isdir(out_dir):
        try:
            shutil.rmtree(out_dir, ignore_errors=True)
        except Exception:
            pass
    return removed


# --------------------------------------------------------------------------
# Position tracking (.nvt)
# --------------------------------------------------------------------------
def tracking(path, t0=None, t1=None, max_points=4000):
    """Read .nvt position, optionally limited to a time window."""
    if not os.path.isfile(path):
        raise VideoError("Tracking file not found: " + path)
    try:
        t, x, y, ang, meta = nlx.read_nvt(path)
    except Exception as exc:
        raise VideoError("Could not read %s: %s" % (os.path.basename(path), exc))

    if t.size == 0:
        raise VideoError("%s contains no tracking records." % os.path.basename(path))

    import numpy as np
    mask = np.ones(t.size, dtype=bool)
    if t0 is not None:
        mask &= t >= float(t0)
    if t1 is not None:
        mask &= t <= float(t1)
    ts, xs, ys, angs = t[mask], x[mask], y[mask], ang[mask]

    if ts.size > max_points:
        step = int(np.ceil(ts.size / max_points))
        ts, xs, ys, angs = ts[::step], xs[::step], ys[::step], angs[::step]

    def clean(a):
        return [None if not np.isfinite(v) else round(float(v), 2) for v in a]

    finite_x = x[np.isfinite(x)]
    finite_y = y[np.isfinite(y)]
    return {
        "ok": True,
        "name": os.path.basename(path),
        "t": [round(float(v), 4) for v in ts],
        "x": clean(xs), "y": clean(ys), "angle": clean(angs),
        "n": int(ts.size),
        "bounds": {
            "x": [float(finite_x.min()), float(finite_x.max())] if finite_x.size else [0, 1],
            "y": [float(finite_y.min()), float(finite_y.max())] if finite_y.size else [0, 1],
        },
        "duration_s": meta["duration_s"],
        "fps": round(meta["fps"], 2),
        "lost_frac": round(meta["lost_frac"], 4),
    }


def status():
    """What video support is available on this machine."""
    ff = sysinfo.find_ffmpeg()
    return {
        "ffmpeg": ff,
        "ffprobe": sysinfo.find_ffprobe(),
        "available": bool(ff),
        "hint": None if ff else sysinfo.ffmpeg_install_hint(),
        "native_exts": sorted(NATIVE_EXTS),
        "transcode_exts": sorted(TRANSCODE_EXTS),
    }
