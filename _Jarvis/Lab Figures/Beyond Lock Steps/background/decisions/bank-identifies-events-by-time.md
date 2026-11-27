# bank-identifies-events-by-time

_A banked event's identity IS its time, so anything that moves a stamp must carry from_t or the version diff reads as a total replacement._

`eventbank.py` keys its version diff on `round(float(ev["start"]), 4)`, and
`_dup_key` uses the same. Time is the only identity a banked event has.

Anything that **moves** a stamp therefore breaks the diff: the old times
match nothing and the new ones match nothing, so a pass in which no decision
changed reads as *N lost, N gained* — a history claiming the whole set was
replaced.

Two tools move stamps:

- `retime()` — sidesteps it by writing `changed/gained/lost/moves` as zeros
  by hand, with a comment saying why.
- `align()` (Braces) — carries **`from_t`** on each moved event: the time it
  had before. The diff matches in TWO passes — events still where they were
  claim their slot first, leftovers are then matched on `from_t`. One pass,
  whichever key it preferred, could hand a moved event the slot of an event
  that never moved. Versions gained a `shifted` count.

`from_t` must also be in the field whitelist `add()` builds each event from
(around the `("channel", "amplitude", "label", "label_id")` loop) or it is
silently dropped on the way in and the next diff is blind again.

**Why:** this is invisible to unit tests that only check the arithmetic, and
it corrupts the one record that says what a pass actually did.

**How to apply:** any new operation that rewrites event times must either
carry `from_t` or zero the diff fields deliberately — never leave the
time-keyed diff to guess. Related: `dentist-bundle-naming` (a note not copied here)
