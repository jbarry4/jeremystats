"""The sound for "Watching a seizure spread": an original score and the effects,
written from the film's cues (film.js FILM.cues(), saved by render_film.py as
NAME.cues.json), then laid under the picture.

    python tools/seahorse/film/soundtrack.py film.cues.json --wav sound.wav
    python tools/seahorse/film/soundtrack.py film.cues.json --mux film.picture.mp4 film.mp4

Nothing here is a recording: every sound is made from sine, saw and noise, so
the film carries no one else's music. The score follows the film's moods, one
section per run of scenes with the same mood, its chords changing on a slow
bar (64 bpm) that starts with the section:
  open    D major, a warm pad and a soft piano arpeggio      title to the model
  method  the same key, lighter, the arpeggio an octave up   the probe, the cells
  tense   D minor over a low D drone, no arpeggio            the seizure
  loop    B minor, open fifths, quiet                        around the loop
  spread  D minor rising, a chord a step, to A at the end    across the brain
  hope    back to D major, the arpeggio and a held last chord  next, the end card
The effects (whoosh at every change of angle, a boom at the seizure's start, a
knock per discharge in the run-up, plucks around the loop, a thud per jerk)
sit where the cues put them. The mix is brought to -15 LUFS, peaks under -1.5 dBTP
(ffmpeg loudnorm, two passes), AAC 192 kb/s in the film."""
import argparse, json, os, re, subprocess, sys, tempfile
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
BPM = 64.0
BAR = 4 * 60.0 / BPM
RNG = np.random.default_rng(459)
mtof = lambda m: 440.0 * 2 ** ((m - 69) / 12.0)  # noqa: E731


# ---------------------------------------------------------------- building blocks
def place(buf, x, t, gain=1.0, pan=0.5):
    """Add mono or stereo x into the stereo buffer at time t (s)."""
    i0 = int(round(t * SR))
    if x.ndim == 1:
        x = np.stack([x * np.cos(pan * np.pi / 2), x * np.sin(pan * np.pi / 2)], 1) * np.sqrt(2)
    a, b = max(0, i0), min(len(buf), i0 + len(x))
    if b > a:
        buf[a:b] += gain * x[a - i0:b - i0]


def lowpass(x, fc, order=2):
    sos = signal.butter(order, min(fc, SR * 0.45), "low", fs=SR, output="sos")
    return signal.sosfilt(sos, x, axis=0)


def highpass(x, fc, order=2):
    sos = signal.butter(order, fc, "high", fs=SR, output="sos")
    return signal.sosfilt(sos, x, axis=0)


def env(n, att, rel_from, rel, curve=3.0):
    """Raised-cosine attack over att s, held, then an exponential release from rel_from s lasting about rel s."""
    t = np.arange(n) / SR
    e = np.ones(n)
    if att > 0:
        k = t < att
        e[k] = 0.5 - 0.5 * np.cos(np.pi * t[k] / att)
    k = t > rel_from
    e[k] *= np.exp(-curve * (t[k] - rel_from) / max(rel, 1e-3))
    return e


def saw(freq, n, phase0=0.0):
    ph = phase0 + np.cumsum(freq) / SR if np.ndim(freq) else phase0 + freq * np.arange(n) / SR
    return 2.0 * (ph - np.floor(ph + 0.5))


def pink(n):
    w = RNG.standard_normal(n)
    b, a = [0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400]
    return signal.lfilter(b, a, w) * 4.0


# ---------------------------------------------------------------- instruments
def pad(notes, dur, bright=2400, att=1.8, rel=2.8, detune=0.0055, gain=1.0):
    """A chord on a soft analogue pad: three detuned saws a note, slowly chorused, low-passed, spread in stereo."""
    n = int((dur + rel * 1.6) * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for j, m in enumerate(notes):
        f = mtof(m)
        for k, (dt, pan) in enumerate([(-detune, 0.18), (0.0, 0.5), (detune, 0.82)]):
            wob = 1 + 0.0022 * np.sin(2 * np.pi * (0.13 + 0.05 * k + 0.02 * j) * t + 1.7 * k + j)
            v = saw(f * (1 + dt) * wob, n, RNG.random())
            out[:, 0] += v * np.cos(pan * np.pi / 2)
            out[:, 1] += v * np.sin(pan * np.pi / 2)
    out = lowpass(out, bright, 2)
    out = lowpass(out, bright * 1.6, 1)
    e = env(n, att, dur, rel)
    return out * e[:, None] * gain / (len(notes) * 3) * 1.6


def drone(note, dur, gain=1.0):
    """A low drone: a dark saw and a sine on the same note (D3 and D2 here), with a slow swell; nothing much under 60 Hz,
    which small speakers can't play and big ones turn to boom."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = mtof(note)
    v = 0.6 * saw(f * (1 + 0.0015 * np.sin(2 * np.pi * 0.07 * t)), n) + 0.45 * np.sin(2 * np.pi * f / 2 * t)
    v = lowpass(v, 620, 2)
    sw = 0.75 + 0.25 * np.sin(2 * np.pi * 0.045 * t - 1.2)
    e = env(n, 3.0, dur - 3.0, 2.0)
    m = v * sw * e * gain
    return np.stack([m, m * 0.96], 1)


def piano(m, vel=0.3, dur=4.5, soft=2600):
    """A felt piano note: slightly stretched partials, each dying faster than the last, a soft hammer."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = mtof(m)
    y = np.zeros(n)
    for k in range(1, 10):
        fk = f * k * np.sqrt(1 + 0.00035 * k * k)
        if fk > SR * 0.42:
            break
        amp = 1.0 / k ** 1.45
        dec = 0.42 + 0.33 * k + f / 1100
        y += amp * np.exp(-dec * t) * np.sin(2 * np.pi * fk * t + RNG.random() * 6.28)
    y *= np.minimum(1, t / 0.004)
    ham = lowpass(RNG.standard_normal(min(n, 1200)) * np.exp(-np.arange(min(n, 1200)) / 180.0), 1800) * 0.25
    y[:len(ham)] += ham
    y = lowpass(y, soft * (0.6 + vel), 2)
    return y * vel


def bell(m, vel=0.4, dur=5.0, att=0.03):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = mtof(m)
    y = np.zeros(n)
    for r, a, d in [(1.0, 1.0, 0.7), (2.0, 0.35, 1.1), (2.76, 0.18, 1.6), (4.07, 0.09, 2.4), (5.4, 0.05, 3.2)]:
        if f * r < SR * 0.42:
            y += a * np.exp(-d * t) * np.sin(2 * np.pi * f * r * t + RNG.random() * 6.28)
    y *= np.minimum(1, t / att)
    return y * vel


def pluck(m, vel=0.4, dur=2.0):
    """A soft mallet: a marimba's partials, the high ones gone at once."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = mtof(m)
    y = np.sin(2 * np.pi * f * t) * np.exp(-3.2 * t) + 0.22 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-14 * t) \
        + 0.06 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-30 * t)
    y *= np.minimum(1, t / 0.003)
    return y * vel


def strings(notes, dur, gain=1.0, att=2.5, rel=2.5, bright=3000):
    """Bowed strings, more or less: saws with vibrato, a slow bow."""
    n = int((dur + rel * 1.5) * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for j, m in enumerate(notes):
        for k, pan in enumerate([0.3, 0.7]):
            vib = 1 + 0.0045 * np.sin(2 * np.pi * (5.1 + 0.4 * k + 0.13 * j) * t + j) * np.minimum(1, t / 1.5)
            v = saw(mtof(m) * (1 + (k - 0.5) * 0.004) * vib, n, RNG.random())
            out[:, 0] += v * np.cos(pan * np.pi / 2)
            out[:, 1] += v * np.sin(pan * np.pi / 2)
    out = lowpass(highpass(out, 140), bright, 2)
    return out * env(n, att, dur, rel)[:, None] * gain / (len(notes) * 2)


# ---------------------------------------------------------------- effects
def band_noise(n, fc, bw, seed_noise=None):
    """Noise through a band that moves: fc and bw (Hz) are arrays over the sound, applied frame by frame (STFT)."""
    x = seed_noise if seed_noise is not None else RNG.standard_normal(n)
    f, tt, Z = signal.stft(x, SR, nperseg=1024, noverlap=768)
    idx = np.clip((tt * SR).astype(int), 0, n - 1)
    c, w = fc[idx][None, :], bw[idx][None, :]
    mask = np.exp(-0.5 * ((f[:, None] - c) / w) ** 2)
    _, y = signal.istft(Z * mask, SR, nperseg=1024, noverlap=768)
    y = y[:n] if len(y) >= n else np.pad(y, (0, n - len(y)))
    return y / (np.sqrt(np.mean(y ** 2)) + 1e-9)


def whoosh(dur=2.0, peak=0.62, up=2800.0, wap='wap'):
    """Air rushing past and away, panned across; at its peak a soft low 'wap', or a quick falling 'lop'."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    pk = peak * dur
    u = np.where(t < pk, t / pk, 1 - (t - pk) / (dur - pk))
    fc = 260 + (up - 260) * np.clip(u, 0, 1) ** 1.6
    y = band_noise(n, fc, 0.28 * fc + 120)
    e = np.where(t < pk, (t / pk) ** 2.6, np.exp(-5.2 * (t - pk) / (dur - pk)))
    y *= e
    k = t >= pk
    tk = t[k] - pk
    if wap == 'wap':
        y[k] += 0.9 * np.sin(2 * np.pi * (115 * tk - 30 * tk ** 2)) * np.exp(-tk / 0.09)
    elif wap == 'lop':
        # a pitch falling 540 -> 190 Hz in a tenth of a second, a drop into water
        ph = 2 * np.pi * (540 * tk - 0.5 * 3500 * np.minimum(tk, 0.1) ** 2 - 350 * np.maximum(tk - 0.1, 0))
        y[k] += 0.55 * np.sin(ph) * np.exp(-tk / 0.07) * np.minimum(1, tk / 0.004)
    pan = np.clip(0.2 + 0.6 * t / dur, 0, 1)
    return np.stack([y * np.cos(pan * np.pi / 2), y * np.sin(pan * np.pi / 2)], 1) * np.sqrt(2), pk


def swell(dur=4.0):
    """A breath drawn in: noise and a fifth that rise together and stop short."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    u = t / dur
    y = band_noise(n, 300 + 3200 * u ** 2, 400 + 900 * u) * 0.5
    y += 0.5 * (np.sin(2 * np.pi * mtof(62) * t) + 0.6 * np.sin(2 * np.pi * mtof(69) * t)) * (0.4 + 0.6 * u)
    e = u ** 2.4 * np.where(u > 0.94, np.cos((u - 0.94) / 0.06 * np.pi / 2), 1)
    return y * e


def impact():
    n = int(3.2 * SR)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * (72 * t - 6 * t ** 2)) * np.exp(-t / 0.75)
    body = lowpass(RNG.standard_normal(n), 900) * np.exp(-t / 0.18) * 0.8
    sub = np.sin(2 * np.pi * 50 * t) * np.exp(-t / 1.2) * 0.25
    y = boom + body + sub
    y *= np.minimum(1, t / 0.004)
    return y


def knock(pitch=1.0):
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * (170 * pitch * t - 260 * t ** 2)) * np.exp(-t / 0.035)
    y += 0.25 * lowpass(RNG.standard_normal(n), 2500) * np.exp(-t / 0.006)
    return y


def thud():
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * (72 * t - 38 * t ** 2)) * np.exp(-t / 0.11) + 0.3 * lowpass(RNG.standard_normal(n), 400) * np.exp(-t / 0.03)
    return y


def slide(dur=4.4):
    n = int(dur * SR)
    t = np.arange(n) / SR
    u = t / dur
    y = band_noise(n, 1900 - 1300 * u, np.full(n, 260.0)) * (0.8 + 0.2 * np.sin(2 * np.pi * 7 * t))
    y += 0.15 * np.sin(2 * np.pi * (220 - 60 * u) * t)
    return y * np.sin(np.pi * u) ** 0.8


def rush(dur=5.2):
    """The seizure, sped up: a storm of noise beating fast, over a low rumble, rising then held."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    u = t / dur
    beat = 0.55 + 0.45 * np.sin(2 * np.pi * (5.5 + 2.5 * u) * t) ** 2
    y = band_noise(n, 500 + 900 * u, 500 + 300 * u) * beat * 0.6
    y += lowpass(RNG.standard_normal(n), 160) * 2.2
    return y * np.minimum(1, t / 0.6) * np.where(u > 0.85, (1 - u) / 0.15, 1)


def release():
    n = int(3.5 * SR)
    t = np.arange(n) / SR
    u = t / 3.5
    y = band_noise(n, 1800 - 1500 * u, 600 - 300 * u) * np.exp(-2.6 * u) * 0.7
    y += 0.6 * np.sin(2 * np.pi * (110 - 45 * u) * t) * np.exp(-1.8 * u) * np.minimum(1, t / 0.05)
    return y


# ---------------------------------------------------------------- reverb
def impulse(rt60=3.0, pre=0.025, damp=5200.0, seed=0):
    rng = np.random.default_rng(seed)
    n = int((rt60 * 1.1 + pre) * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2))
    tail = rng.standard_normal((n, 2)) * np.exp(-6.91 * t / rt60)[:, None]
    tail[: int(pre * SR)] = 0
    # the tail darkens as it dies
    early, late = lowpass(tail, damp, 1), lowpass(tail, damp * 0.35, 1)
    mix = np.clip(t / rt60, 0, 1)[:, None]
    ir = early * (1 - mix) + late * mix
    for d, g in [(0.011, 0.5), (0.019, 0.35), (0.027, 0.3), (0.041, 0.22)]:
        i = int((pre + d) * SR)
        ir[i, 0] += g * (1 if rng.random() > 0.5 else -1)
        ir[i + 7, 1] += g * (1 if rng.random() > 0.5 else -1)
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


def reverb(x, ir, wet):
    y = np.stack([signal.oaconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], 1)
    return x * (1 - wet) + y * wet


# ---------------------------------------------------------------- the score
P = {  # chords: (bass, pad notes)
    'D9': (38, [50, 57, 64, 66, 69]), 'Bm7': (35, [50, 54, 57, 62, 66]), 'Gma9': (43, [50, 54, 59, 62, 69]),
    'Asus': (45, [52, 57, 62, 64, 69]), 'A': (45, [52, 57, 61, 64, 69]), 'D/F#': (42, [50, 57, 62, 66, 69]),
    'Em7': (40, [50, 55, 59, 62, 67]), 'Gma7': (43, [50, 54, 59, 62, 66]), 'A/C#': (37, [52, 57, 61, 64, 69]),
    'G9': (43, [50, 55, 57, 59, 66]),
    'Dm9': (38, [50, 57, 64, 65]), 'Bbma7': (34, [50, 53, 57, 64]), 'Gm9': (43, [50, 55, 57, 62, 70]), 'A7sus': (45, [50, 55, 57, 64, 70]),
    'Bm9': (35, [50, 54, 61, 62, 66]), 'Gma7#11': (43, [50, 54, 59, 61, 66]), 'Em9': (40, [50, 54, 55, 59, 62]),
    'F#sus': (42, [49, 54, 59, 61, 66]), 'F#': (42, [49, 54, 58, 61, 66]),
    'F': (41, [48, 53, 57, 60, 65]), 'C/E': (40, [48, 52, 55, 60, 64]), 'Gm': (43, [50, 55, 58, 62, 67]), 'Dm': (38, [50, 53, 57, 62, 65]),
}
MOODS = {
    'open': dict(prog=['D9', 'Bm7', 'Gma9', 'Asus', 'D/F#', 'Em7', 'Gma7', 'Asus'], pad=0.52, bright=2300, arp=0.0, arp_from=1, bass=0.22),
    'method': dict(prog=['Gma9', 'D/F#', 'Em7', 'Asus', 'Bm7', 'Gma9', 'D9', 'Asus'], pad=0.44, bright=2600, arp=0, arp_from=0, bass=0.18),
    'tense': dict(prog=['Dm9', 'Bbma7', 'Gm9', 'A7sus'], pad=0.4, bright=1400, arp=None, drone=50, bass=0.0),
    'loop': dict(prog=['Bm9', 'Gma7#11', 'Em9', 'F#sus'], pad=0.4, bright=1700, arp=None, bass=0.16),
    'spread': dict(prog=['Dm', 'F', 'C/E', 'Bbma7', 'Gm', 'A7sus'], pad=0.42, bright=1900, arp=None, bass=0.22, strings=True),
    'hope': dict(prog=['D9', 'A/C#', 'Bm7', 'G9', 'D/F#', 'Em7', 'Gma9', 'Asus', 'D9'], pad=0.5, bright=2500, arp=0, arp_from=0, bass=0.22),
}
ARP = [0, 2, 4, 3, 1, 3, 4, 2]


def sections(scenes):
    out = []
    for s in scenes:
        m = s.get('mood') or 'open'
        if out and out[-1]['mood'] == m:
            out[-1]['t1'] = s['t0'] + s['dur']
        else:
            out.append({'mood': m, 't0': s['t0'], 't1': s['t0'] + s['dur'], 'scenes': []})
        out[-1]['scenes'].append(s)
    return out


def score(total, scenes, cues):
    n = int((total + 4) * SR)
    mus = np.zeros((n, 2))
    secs = sections(scenes)
    for si, sec in enumerate(secs):
        M = MOODS[sec['mood']]
        t0, t1 = sec['t0'], sec['t1']
        last = si == len(secs) - 1
        # when the chords change: on the bar, or (spread) on each of the film's steps, its blooms
        if sec['mood'] == 'spread':
            steps = [t0] + [c['t'] - 0.2 for c in cues if c['kind'] == 'bloom' and t0 + 1 < c['t'] < t1]
            times = sorted(set(round(x, 3) for x in steps))
        else:
            times = list(np.arange(t0, t1 - 0.5, BAR))
        prog = M['prog']
        for ci, ts in enumerate(times):
            name = prog[ci % len(prog)] if not (last and ts + BAR > t1 - 2 * BAR) else prog[-1]
            nxt = times[ci + 1] if ci + 1 < len(times) else t1
            dur = max(0.8, nxt - ts)
            bass, notes = P[name]
            k = (ci + 0.5) / max(1, len(times))
            gpad = M['pad'] * (0.7 + 0.6 * k if sec['mood'] == 'spread' else 1.0)
            if si == 0 and ci == 0:
                gpad *= 0.8
            att = 2.4 if ci == 0 else 1.6
            place(mus, pad(notes, dur + 0.3, bright=M['bright'] * (0.9 + 0.3 * k if sec['mood'] == 'spread' else 1), att=att, gain=gpad), ts - 0.15)
            if M.get('bass'):
                # the root: a soft low piano note, and a sine an octave under it held for the chord
                nb = int((dur + 1.2) * SR)
                sub = np.sin(2 * np.pi * mtof(bass) * np.arange(nb) / SR) * env(nb, 0.6, max(0.1, dur - 0.3), 1.0)
                place(mus, sub * M['bass'] * 0.8, ts, 1.0, 0.5)
                place(mus, piano(bass + 12, vel=M['bass'] * 1.1, dur=min(6.0, dur + 1.5), soft=900), ts, 0.8, 0.5)
            if M.get('strings') and ci >= 2:
                place(mus, strings([notes[0] + 12, notes[2] + 12, notes[-1]], dur + 0.4, gain=0.32 * (0.6 + 0.8 * k)), ts - 0.2)
            # the arpeggio: eighths through the chord, soft, a little loose
            if M.get('arp') is not None and ci >= M.get('arp_from', 0):
                eighth = BAR / 8
                for j in range(int(dur / eighth + 0.01)):
                    if RNG.random() < 0.12 and j % 4:
                        continue
                    note = sorted(notes)[ARP[j % 8]] + 12 + M['arp']
                    vel = (0.17 if j % 4 == 0 else 0.11) * (0.85 + 0.3 * RNG.random())
                    if last and ts + j * eighth > t1 - 6:
                        vel *= max(0.0, (t1 - 2.5 - ts - j * eighth) / 3.5)
                    if vel > 0.005:
                        place(mus, piano(note, vel, dur=3.5), ts + j * eighth + RNG.normal(0, 0.008), 1.0, 0.35 + 0.3 * RNG.random())
            # the spread's pulse: low eighths on the root from the third step, a heartbeat that quickens
            if sec['mood'] == 'spread' and ci >= 2:
                beat = 60.0 / BPM / (2 if ci >= 3 else 1)
                for j in range(int(dur / beat)):
                    place(mus, thud() * 0.35 * (0.6 + 0.5 * k), ts + j * beat, 1.0, 0.5)
        if M.get('drone'):
            place(mus, drone(M['drone'], t1 - t0 + 2.5, gain=0.32), t0 - 0.5)
        # the tense section's glass: a high tone now and then
        if sec['mood'] in ('tense', 'loop'):
            for tt in np.arange(t0 + 3.0, t1 - 3, BAR * 2):
                place(mus, bell(81 + int(RNG.choice([0, 3, 5, 7])), vel=0.035, dur=6.0, att=0.6), tt + RNG.random(), 1.0, RNG.random())
    # in from silence; out with the picture's fade to black
    t = np.arange(n) / SR
    fadein = np.clip(t / 2.5, 0, 1) ** 2
    fadeout = np.clip((total - 0.3 - t) / 3.2, 0, 1) ** 1.5
    return mus * (fadein * fadeout)[:, None]


SFX = {
    'whoosh': 0.5, 'swell': 0.34, 'impact': 0.85, 'bloom': 0.42, 'pluck': 0.36, 'knock': 0.35,
    'rush': 0.42, 'release': 0.42, 'thud': 0.55, 'slide': 0.22,
}


def effects(total, cues):
    n = int((total + 4) * SR)
    fx = np.zeros((n, 2))
    nwhoosh = 0
    for c in cues:
        k, t, g = c['kind'], c['t'], c.get('gain', 1.0) * SFX.get(c['kind'], 0.4)
        if k == 'whoosh':
            # "sheeeewap" and "sheeeelop", by turns
            d = c.get('dur', 2.0)
            y, pk = whoosh(d, wap='wap' if nwhoosh % 2 == 0 else 'lop')
            nwhoosh += 1
            place(fx, y, t - pk, g)
        elif k == 'swell':
            d = c.get('dur', 4.0)
            place(fx, swell(d), t - d * 0.6, g, 0.5)
        elif k == 'impact':
            place(fx, impact(), t, g, 0.5)
        elif k == 'bloom':
            base = 62 - (12 if c.get('low') else 0)
            y = bell(base + c.get('pitch', 0), vel=1.0, dur=5.0, att=0.04) + 0.5 * bell(base + c.get('pitch', 0) + 7, vel=0.5, dur=5.0, att=0.06)
            place(fx, y, t, g, 0.5)
        elif k == 'pluck':
            place(fx, pluck(74 + c.get('pitch', 0), 1.0), t, g, 0.35 + 0.3 * RNG.random())
        elif k == 'knock':
            place(fx, knock(0.9 + 0.2 * RNG.random()), t, g, 0.42 + 0.16 * RNG.random())
        elif k == 'rush':
            place(fx, rush(c.get('dur', 5.2)), t, g, 0.5)
        elif k == 'release':
            place(fx, release(), t, g, 0.5)
        elif k == 'thud':
            place(fx, thud(), t, g, 0.5)
        elif k == 'slide':
            place(fx, slide(c.get('dur', 4.4)), t, g, 0.5)
    return fx


def loudnorm(src, dst, target=-15.0, tp=-1.5):
    """ffmpeg's EBU R128 normalisation in two passes: measure, then apply (linear, so the mix keeps its shape)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", "loudnorm=I=%g:TP=%g:LRA=14:print_format=json" % (target, tp), "-f", "null", "-"],
                       capture_output=True, text=True)
    m = json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])
    af = ("loudnorm=I=%g:TP=%g:LRA=14:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true"
          % (target, tp, m["input_i"], m["input_tp"], m["input_lra"], m["input_thresh"], m["target_offset"]))
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", af + ",aresample=48000", "-c:a", "pcm_s24le", dst])
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cues")
    ap.add_argument("--wav", default="", help="write the finished sound here")
    ap.add_argument("--mux", nargs=2, metavar=("PICTURE", "OUT"), help="lay the sound under this picture-only MP4")
    ap.add_argument("--start", type=float, default=0.0, help="the film second the picture starts at")
    a = ap.parse_args()
    d = json.load(open(a.cues, encoding="utf-8"))
    total, scenes, cues = d["total"], d["scenes"], d["cues"]
    print("score: %d sections, %d cues, %.1f s" % (len(sections(scenes)), len(cues), total), flush=True)
    mus = score(total, scenes, cues)
    fx = effects(total, cues)
    mus = reverb(highpass(mus, 38), impulse(3.4, 0.03, 5600, 1), 0.36)
    fx = reverb(highpass(fx, 30), impulse(2.2, 0.02, 6500, 2), 0.24)
    mix = highpass(mus * 0.85 + fx * 1.0, 48, 2)
    mix = mix[int(a.start * SR):int((total + 0.2) * SR)]
    tmp = tempfile.mkdtemp(prefix="seahorse-sound-")
    raw = os.path.join(tmp, "raw.wav")
    wavfile.write(raw, SR, (mix / (np.max(np.abs(mix)) + 1e-9) * 0.7).astype(np.float32))
    wav = a.wav or os.path.join(tmp, "sound.wav")
    m = loudnorm(raw, wav)
    print("loudness before: %s LUFS, true peak %s dBTP; now -15 LUFS" % (m["input_i"], m["input_tp"]))
    if a.mux:
        pic, out = a.mux
        subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                               "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out])
        print("wrote", out)
    elif a.wav:
        print("wrote", a.wav)


if __name__ == "__main__":
    main()
