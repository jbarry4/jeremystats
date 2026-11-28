"""Does the sound line up with the picture? python tools/seahorse/film/check_sync.py FILM.mp4 FILM.cues.json
Measured on the finished file, both streams as a player decodes them:
 1. picture: the frames where the picture cuts (big frame-to-frame change) vs the scene starts in the cues
 2. sound: the onset of each sharp sound (impact, knock, thud) vs its cue time
 3. sound vs picture: whoosh peaks vs the cuts they cover."""
import json, subprocess, sys
import numpy as np

film, cues = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))
FPS = 30
# --- the picture, decoded small and grey, every frame
W, H = 160, 90
raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", film, "-vf", "scale=%d:%d,format=gray" % (W, H), "-f", "rawvideo", "-"], capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)
diff = np.r_[0, np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))]
print("picture: %d frames = %.3f s" % (len(fr), len(fr) / FPS))
# --- the sound, decoded mono 48 kHz
SR = 48000
a = np.frombuffer(subprocess.run(["ffmpeg", "-loglevel", "error", "-i", film, "-map", "0:a", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout, np.float32)
print("sound:   %.3f s" % (len(a) / SR))
env = np.sqrt(np.convolve(a.astype(np.float64) ** 2, np.ones(240) / 240, mode="same"))  # 5 ms rms

# 1. hard cuts in the picture (scenes that start without a cross-fade change at once) and where the cross-fades begin
print("\n1. picture vs the film's own clock (scene starts)")
for s in cues["scenes"]:
    f0 = round(s["t0"] * FPS)
    if f0 < 2:
        continue
    lo, hi = max(1, f0 - 6), min(len(diff) - 1, f0 + 6)
    k = lo + int(np.argmax(diff[lo:hi + 1]))
    print("  %-9s cue %7.3f s  biggest change at %7.3f s  (%+d frames)" % (s["name"], s["t0"], k / FPS, k - f0))

# 2. sharp sounds: the first rise above the noise before the onset, within +-150 ms of the cue
print("\n2. sound vs its cues (onset of sharp sounds)")
offs = []
for c in cues["cues"]:
    if c["kind"] not in ("impact", "knock", "thud", "pluck"):
        continue
    i0 = int(c["t"] * SR)
    w0, w1 = i0 - int(0.15 * SR), i0 + int(0.15 * SR)
    if w0 < SR or w1 >= len(env):
        continue
    seg = env[w0:w1]
    base = np.median(env[w0 - int(0.3 * SR):w0])
    jump = np.diff(seg)
    k = int(np.argmax(jump))  # the steepest rise: the attack
    offs.append((c["kind"], c["t"], (w0 + k) / SR - c["t"]))
by = {}
for kind, t, o in offs:
    by.setdefault(kind, []).append(o * 1000)
for kind, v in by.items():
    v = np.array(v)
    print("  %-7s n=%3d  onset - cue: median %+6.1f ms, middle half %+6.1f..%+6.1f ms" % (kind, len(v), np.median(v), np.percentile(v, 25), np.percentile(v, 75)))

# 3. whooshes: their loudest moment vs the cut they cover
print("\n3. whoosh peaks vs the picture's change")
for c in cues["cues"]:
    if c["kind"] != "whoosh":
        continue
    i0 = int(c["t"] * SR)
    w = env[i0 - int(0.8 * SR):i0 + int(0.8 * SR)]
    pk = (i0 - int(0.8 * SR) + int(np.argmax(w))) / SR
    f0 = int(c["t"] * FPS)
    seg = diff[max(1, f0 - 15):f0 + 45]
    ch = (max(1, f0 - 15) + int(np.argmax(seg))) / FPS
    print("  cue %7.2f  sound peak %7.2f  picture change %7.2f  (sound - picture %+5.2f s)" % (c["t"], pk, ch, pk - ch))
