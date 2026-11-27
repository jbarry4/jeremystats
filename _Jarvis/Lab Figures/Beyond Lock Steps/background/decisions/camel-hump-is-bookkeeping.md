# camel-hump-is-bookkeeping

_The "camel hump" (a notch inside a sink hump) was per-event top-2 bump bookkeeping, not bad channels; fixed 11-12 with sinkcut sink="humps". Off-gain contacts 25/49 in mid-2024 PTEN sessions._

On 2026-11-12 the user reported a "camel hump" on the Bite line raster. The worst case was m6 s4: a notch inside the top hump. They suspected bad channels, drift or filtering.

**Findings:**
- The notch is in the signal. Each contact was tested against a 4-point cubic prediction from two neighbours a side, in the baseline (`scratchpad/camel_gain.py` and `gain_scan.py` approach). On m6 s4 every contact is within 0.3%, and there is no drift by quarter.
- The cause was the Bite line's per-event "two biggest bumps". On events where the notch touched zero, the top hump counted as two bumps. On m6 s4, 20 of the 26 small-side events were those.
- Fix: `sinkcut` `sink="humps"` is now the default. The recording's two humps are parted at the source between the two biggest bumps of the mean profile (`hump_cut`). The blobs use them too.
- The room was refit: v5 is the 10% set and v6 the Halo set. v3/v4 keep "bumps".
- Bite cuts saved without `sink` are stale under humps, and are flagged on the card.

**Real off-gain contacts found (not yet marked):**
- Contacts 25 and 49 read 4–12% low in m21 s2, m22 s3 and m28 s2 (June–July 2024). 25 is 12% low in m22.
- m7 s2: contact 51 reads 3.7% high.
- Taking them out removes fake notches; for example, m28 s2's notched events go from 150 to 1. SI barely changes.
- I offered to mark them bad. The user had not answered as of 11-12.
- On 11-13 the user asked for a toggle instead. "Leave out low contacts" in Compare splits is a look only. With its iterative test (2%) it finds:
  - m21 s2: 49, 62, 25
  - m22 s3: 25, 62, 49
  - m28 s2: 25, 49, 5, 52, 44
  - m13 s2: 62, and m7 s2: 22 (both outside the band)
  - none anywhere else.
  - m7's 51 reads high, not low, so it is not flagged.
  - See [compare-splits-fifteen](compare-splits-fifteen.md).

**Tested, not adopted:**
- A DBSCAN trim, which is Toothy's idea, on Hellinger distance. It throws out the small genuine families as noise.
- Cubic instead of linear repair of bad rows. Linear repair zeroes the CSD at the repaired row; the effect is tiny on these sets.

**Calls carried over:** Shahriar Tafti's calls on m2 s3 and m59 s4 were "separable" on hand lines that are now stale.

**Why:** The user asked for the cause and a fix ("see what you can come up with").

**How to apply:**
- Before blaming channels for a notch, run the cubic gain test.
- Before changing the Bite sink again, check `tools/check_sinkcut.py`.

Related: [halo-biteline-impression-decisions](halo-biteline-impression-decisions.md), [extraction-room-decisions](extraction-room-decisions.md).
