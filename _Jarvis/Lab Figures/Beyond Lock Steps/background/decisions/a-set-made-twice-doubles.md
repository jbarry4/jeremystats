# a-set-made-twice-doubles

_A curation set created on a machine that has not pulled it mints fresh event ids; the shard merge unions them and every event appears twice._

`Curation.create` keeps an event's id only if THIS machine already holds the set (`id_at` from `self._read`). A machine that has not pulled the set mints fresh uuids for the same times. Shards merge events by id, so the merged set holds every event twice: one copy carries the decisions, the other is undecided.

- **Happened twice:**
  - m33 s8 on 2026-09-08: 416 events became 832. That led to the keep-ids fix.
  - KCNT1 m1606 s1's pool on 2026-11-05: 518 + 520 = 1038. Isabella's laptop (Blackbarry, LCOM549913, on app 2026.10.30.3) made the pool from bank v0 at 13:09. Rain's 352 decisions and Prospector's flags sit on the other copy.
- **How it shows:** a sweep or a count reports about 2x the events. The shards' id sets don't overlap, but their starts match.
- **Proposed to the user, not done (11-05):**
  - Mint ids deterministically from (gid, kind, start), so two machines converge.
  - Clean up m1606 s1 by tombstoning the 520 undecided duplicates. This is shared data, so confirm first.

**Why:** shared curation data; undoing a merge is hard. See [another-agent-may-commit-your-work](another-agent-may-commit-your-work.md) and `harnesses-must-restore-not-clear` (a note not copied here).

**How to apply:** when a set's count looks doubled, compare the event ids across `GUI_logs/curation/<gid>__<kind>@*.json` before anything else.
