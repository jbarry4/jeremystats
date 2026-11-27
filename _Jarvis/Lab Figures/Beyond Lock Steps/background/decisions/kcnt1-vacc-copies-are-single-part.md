# kcnt1-vacc-copies-are-single-part

_On the VACC copies the _0001 suffix is a naming artifact, not a continuation file — unlike the local copies._

Measured 2026-09-21 across all 18 VACC sessions: no channel has more than
one file. The `_0001` suffix still appears, in two shapes, and neither means
a split recording.

  5 sessions (M7s3, M8s3, M9s3, M10s2, M12s4) — all 128 files suffixed
    `_0001`, with no unsuffixed sibling anywhere.
  2 sessions (M11s6, M14s2) — ch 1-64 as `CSCn.ncs`, ch 65-128 as
    `CSCn_0001.ncs`. The two halves start at the *identical* microsecond
    timestamp and hold the identical record count, so the suffix tracks the
    headstage, not a restart.

**Why:** this is the opposite of `kcnt1-urethane-recordings-are-split` (a note not copied here),
which describes the copies the registry audits — there each channel exists as
both `CSCn.ncs` and `CSCn_0001.ncs` and half the recording goes unread. Two
trees, the same suffix, different meanings; assuming the audit's finding
holds on the VACC would have it stitching parts that do not exist.

**How to apply:** on the VACC, glob `CSC*.ncs` and take what you find. Never
build the name as `CSC<n>.ncs` — on the two split-naming sessions that
silently finds 64 of 128 channels, and on the five all-suffixed ones it finds
none at all.
