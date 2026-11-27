"""Sextant -- where was the probe?  (Seahorse, 2026-11-27)

A sailor fixes a ship's position from angles to stars whose places are known.
Sextant fixes a linear probe's position from layers whose places are known:
every signal the recording carries that is tied to a layer -- ripples in
CA1's cell layer, theta peaking at the fissure, dentate spikes sinking in the
outer and middle molecular layers -- says where along the shank that layer
was crossed, and the Allen atlas says where those layers lie in a real brain.
The pose that makes the two agree is the probe's.

    cohort      the recordings placed (the Extraction Room's, one a mouse)
    atlas       Sextant's layer volume: the Seahorse laminae at 10 um,
                with cortex, white matter, ventricle and thalamus around
                them, and the bregma <-> CCF arithmetic
    evidence    per-contact curves and triggered profiles from a recording
                (StrataScope's read, plus DS / P-spike / BT events)
    detectors   evidence -> landmarks and per-contact layer likelihoods
                (Method A, "landmarks, then the atlas")
    forward     layer geometry -> predicted depth profiles
                (Method B, "simulate and match")
    fit         the pose search, the two methods consolidated, the cloud
    checks      drop one signal; plant a probe and find it again

The user's 12 answers (2026-11-27) are in the Sextant memory: lives in
Seahorse, click-by-click reveal, automatic then reviewed (nothing saved
until Accept), a cloud of probes, DS / P-spike / BT evidence allowed, the
lab's layer labels never used (not as evidence, not as a check), the
craniotomy (AP -2.2, ML +/-1.4 mm from bregma) as a loose prior, controls
learn what normal looks like and PTEN mice may stretch layer by layer.
"""
