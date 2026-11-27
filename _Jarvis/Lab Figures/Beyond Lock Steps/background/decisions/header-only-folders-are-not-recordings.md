# header-only-folders-are-not-recordings

_Stub folders (every CSC 16384 B) hid real recordings: a record keyed on a stub got retired 'no data' (m531 s1 in Sessions, not Incisor). Fixed 11-03/04: prune tool, upsert_session refuses stub paths, audit judges every folder, retire refuses data, REG.live()._

A header-only folder is one where every CSC*.ncs is exactly 16384 bytes. The
rig leaves one when acquisition is started and stopped before a sample. It
keeps writing them into old session folders for months (m486 s8, m536 s6,
m14 s2).

**2026-11-03:** 90 KCNT1 records pointed only at stubs and were pruned.
**2026-11-04:** the vet was extended to every project, with
`tools/prune_header_only.py --all`.

**The holistic failure, user-visible as "m531 s1 is in Sessions, not in
Incisor":**
- A record was minted from the stub, so its key and start are the stub's time.
- The real folder joined it later. The matcher treats the same
  mouse/session within 6 h as one recording.
- `/api/registry/audit` judged `here[0]`, which was the stub. Housekeeping
  retired it as "no data in the folder".
- Every tool skips retired records. Sessions' scan cards drew it as normal.

Brought back: m531 s1, m531 s3, m576 s3, m576 s5 and m13 s3 (2022-08-16).
Their start moved to the real folder's time.

**What now stops it:**
- `store.upsert_session` refuses to add a path that is header-only. This is
  the one choke point; it uses `nlx.header_only_folder`, which checks every
  channel, never CSC1 alone.
- The audit judges every reachable folder. A record with stubs beside data
  gets verdict "stubs" and the action **Drop the empty folders**
  (`/api/registry/drop-paths`, which writes path tombstones).
- `/api/registry/retire` refuses a record with data unless `force`.
  `/api/registry/unretire` exists.
- Scan cards carry `stored.retired`, and Sessions shows **retired · bring
  back**.
- `REG.live()` returns one record per gid, never retired. The tree and the
  Incisor and Doppler batch lists read it. `_match_index` puts live records
  first.

**Gotchas met:**
- **A forget comes back.** "Forget" (erase + session tombstone) re-arrives
  from the cloud as a retired row once the push lands. While the live app
  syncs it is re-pulled within a minute. Writing `retired=True` into every
  base is the deterministic route.
- **102 DEWEY gids have two shard bases** (m### and r### keys). They differ
  in start, n_channels, view_state and bad_channels. `REG.all()` returns
  both, so I did NOT merge them; `REG.live()` takes the first live one.
- **Stubs still sit on netfiles.** Never delete them; that is the lab's call
  ([vacc-reads-netfiles](vacc-reads-netfiles.md)).

Related: [kcnt1-vacc-trees](kcnt1-vacc-trees.md), [mouse-session-is-not-an-identity](mouse-session-is-not-an-identity.md), `dewey-gid-holds-a-whole-day` (a note not copied here).
