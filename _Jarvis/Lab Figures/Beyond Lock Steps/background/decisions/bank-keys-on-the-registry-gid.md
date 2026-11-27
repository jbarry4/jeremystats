# bank-keys-on-the-registry-gid

_Event bank and curation sets key on the registry's session gid (sXXXXXXXXXXXX), not on ids.identify()'s identity string — matching a recording folder to banked data by identity silently returns zero._

`EventBank` entries and curation shards carry `gid` values that look like
`s83ce541881d3` — the id `sessreg.Registry` minted for that session. What
`ids.identify(folder)` returns is a different thing: a key like
`m008_s009_2024-02-09_16-43-46`. The two never compare equal.

To go from a recording folder to its banked data, walk `Registry.all()` and
match on the session record's own `paths` list (normcase + abspath, strip the
trailing separator), then use that record's `gid`.

**Why:** matching by identity string does not raise, it returns an empty
list — so the answer comes back as "no banked events are affected by this",
which is the reassuring direction. I reported exactly that about the seven
PTEN recordings with acquisition gaps before re-checking through the
registry, where the real answer was seven banked DS sets holding ~2,139
events. A join that silently yields nothing is worse than one that throws.

**How to apply:** whenever a question is "which sessions/recordings does this
file-system fact affect", resolve through the registry's path list and sanity
check the join by printing how many rows matched at all. A zero from a join is
a result to distrust, not to report. Same family as
[mouse-session-is-not-an-identity](mouse-session-is-not-an-identity.md) and [machine-has-two-names](machine-has-two-names.md); see also
[measure-dont-guess](measure-dont-guess.md).
