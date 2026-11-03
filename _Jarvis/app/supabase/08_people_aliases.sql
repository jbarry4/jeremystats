-- ===========================================================================
-- BARRY GUI -- migration 08: roster aliases
--
-- Run after 01-07. Idempotent.
--
-- Which other spellings of a name are the same person. Written when somebody
-- merges two roster entries, and read every time the roster is compiled --
-- which is why it has to be shared: an alias that lives on one machine folds
-- the name on one machine, and the lab then disagrees about who is who.
--
-- The records themselves are never rewritten. `added.by` on a bank entry is
-- immutable across the shard merge, on purpose, so nobody editing a
-- description can quietly change who added the events; the activity log is
-- append-only for the same reason. Both mean a name in a record is what the
-- machine believed at the time, and both are right. So the record keeps what
-- it said and the roster does the folding -- which is also reversible:
-- remove an alias and the two names come apart again, with nothing lost.
-- ===========================================================================
alter table people add column if not exists aliases text[];

comment on column people.aliases is
  'Other spellings that are this same person. Set by a roster merge. The '
  'records that carry the old name are deliberately NOT rewritten -- '
  'provenance fields are immutable and the logs are append-only -- so this '
  'is what folds them at read time, and removing an alias undoes the merge.';
