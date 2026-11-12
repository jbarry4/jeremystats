-- ===========================================================================
-- BARRY GUI -- migration 11: event version history
--
-- Run after 01-10. Idempotent.
--
-- A banked entry has a version history -- v0 is the detector's import, and
-- every curation pass after it is another version with its own author, time
-- and label mix. None of it was ever sent here, so a version created on the
-- rig only appeared on the desktop after a git pull, which is not what
-- anybody means by a shared bank.
--
-- Metadata only, deliberately. Measured on this store: 110 versions are
-- 44 KB without their snapshots and 0.5 MB with them. The metadata is what
-- makes a version visible -- who made it, when, how many events, the mix of
-- labels -- and the snapshot is what lets it be RESTORED. The snapshots stay
-- in the JSON shards, which is the redundancy copy that travels with the
-- repository. Restoring a version whose snapshot has not reached this
-- machine is refused with an explanation rather than half-done.
-- ===========================================================================
alter table bank_entries add column if not exists versions jsonb;
alter table bank_entries add column if not exists version integer;

comment on column bank_entries.versions is
  'Version history without the snapshots: [{v, at, by, n, note, by_label}]. '
  'The snapshot that lets a version be restored lives in the JSON shard, '
  'which is the redundancy copy -- this is what makes a version visible on '
  'another machine without waiting for a git pull.';
comment on column bank_entries.version is
  'The current version number. Highest v in `versions`.';
