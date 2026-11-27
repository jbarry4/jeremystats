# ied-hand-sorts-are-on-concat-time

_The PTEN IED hand-sort stamps in the bank are concatenated-sample seconds, not true seconds; Doppler answers in true seconds — map before scoring_

The hand-sorted PTEN IED entries (imported from the MATLAB `ets`, via
tools/import_ied.py) carry stamps on CONCATENATED time: sample index / fs,
with acquisition pauses squeezed out. Doppler's engine reports TRUE recording
seconds (`continuity.sample_to_true`). On M34 s8 a 125 ms pause puts the last
Solid 119 ms apart on the two clocks — outside the 100 ms match window, so it
scored as missed although it was found.

**Why:** a scoring artifact like this almost got blamed on the detector.

**How to apply:** before comparing any Doppler/VACC result with the hand-sorts,
move the stamps with `continuity.sample_to_true(rep, round(t*fs))`
(`validate_production.py` in the IED study folder does it). The study's own
2 kHz cache is concatenated too, so study-vs-hand-sort comparisons need no
mapping. Related: [bank-identifies-events-by-time](bank-identifies-events-by-time.md).
