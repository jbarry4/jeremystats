# mains-is-inside-the-ds-band

_60 Hz sits inside the 5-100 Hz DS band and a CSD cannot reject it; notch before timing anything._

The dentate-spike band is 5–100 Hz and the mains is 60 Hz, inside it. A CSD
is a second spatial DIFFERENCE, which rejects nothing common to every contact
but not quite equal on them — so the mains survives into the measure, not out
of it. Measured on M1ptens2oct2: the 60.06 Hz line in the CSD is **5,950×**
the power either side (1.7e8 vs 2.9e4).

**Why:** one mains period is 16.7 ms. Any peak-spacing near that (Braces used
12 ms) makes `find_peaks` resolve individual MAINS CYCLES as candidates, and
"nearest peak" then snaps a stamp onto one — corrections quantised to the
mains period, about nothing. It also breaks template matching quietly: a
periodic signal gives equal optima every cycle, so an ensemble slides between
them and produces a beautiful 60 Hz event-triggered average with a coherence
of 0.90, measuring nothing.

**How to apply:** notch 60 Hz (Q=30, zero-phase — it must not shift a thing
being timed) before the CSD and before any peak finding. 120 Hz is outside
the band and measures at 1.0× its neighbours, so only the fundamental
matters. Also screen the contacts first: a CSD *amplifies* a dead wire, so a
dead contact is the largest deflection on the shank and wins any depth or
peak chosen by magnitude — **CSC59 has been dead on both M1ptens2oct2 and
m26s2jun28**, so treat it as a suspect wire, not a one-off. Interpolate bad
contacts rather than dropping them: a second difference over an uneven grid
is not a CSD.

**What Braces actually ships** (2026.09.18.4) is `FOOOF
Playgroun/dentate_spike_aligner.py`'s rule: mains notched per channel BEFORE
the bandpass, screen, repair, signed CSD, trace = mean |CSD| across depth,
and the stamp goes to the LARGEST peak of that curve in the window with no
floor. `ds_align.py` is the earlier one (event-triggered template, projection
onto the depth profile, nearest peak over a 4.5 SD floor) and is where the
coherence test comes from: the event-triggered average of the signed CSD on
the sink row, peak over mean single-trial peak. Scores on M1ptens2oct2's 64
spikes — curated 0.599, ds_align 0.712, shipped 0.718. See
`the-dentist-bundle` (a note not copied here).
