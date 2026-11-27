# mouse-session-is-not-an-identity

_Mouse+session numbering restarts per project in this lab, so m1 s1 exists many times; anything matching on loose_key alone can merge two recordings._

`ids.match` has three tiers: exact key, then `loose_key` (mouse + session),
then nearest start time. The middle one used to return a confident "strong"
match with **no check on when either recording was made**.

**Why:** this lab's numbering restarts per project — PTEN m1 s1 and KCNT1 m1 s1
are two different recordings sharing one loose key. `upsert_session` patches
whatever `get_session` returns, so a scan that met the second would append its
path to the first, and the two became one record silently. It cost three real
2023/2024 records on 2026-09-09: a test fixture named `m1s1`/`m1s2`/`m2s1`
took them over and a harness's cleanup then erased them (restored from git,
un-tombstoned). A six-hour window on the start time is now required for a
loose match.

**How to apply:** never invent test data with plausible mouse/session numbers —
`m1 s1` is the most dangerous name in this repo. Derive fixture identities
from the clock. And treat any code that looks up a recording by mouse+session,
label, or "the first row" as suspect: the only safe identifiers are the gid and
the full key (which includes the start time). See also
`curation-view-is-a-workbench` (a note not copied here) and `harness-runner-shares-the-app-server` (a note not copied here).
