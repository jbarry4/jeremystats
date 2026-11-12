-- ===========================================================================
-- BARRY GUI -- migration 10: archived computers
--
-- Run after 01-09. Idempotent.
--
-- A computer that has been retired still wrote every row it wrote, so it
-- cannot be deleted from the record -- but it should not go on cluttering
-- every device picker for ever. Same answer as an archived person: off the
-- lists, nothing destroyed, reversible.
--
-- On the machine row rather than in prefs, and that matters: prefs are
-- last-write-wins over the whole value, so two people archiving two
-- different computers would each undo the other. One row per machine makes
-- last-write-wins exactly right.
--
-- Keyed on `id` -- `slug(hostname)` plus a hash of the MAC -- because the
-- friendly name is the thing that changes. This lab has four names in its
-- logs for three computers, and two of those computers differ only by the
-- case of one letter in their friendly names.
-- ===========================================================================
alter table machines add column if not exists archived boolean;

comment on column machines.archived is
  'True when this computer should no longer be offered in device lists -- '
  'retired, reimaged, or replaced. NOT a deletion: every action and error '
  'it recorded is still on record under whatever name it was using, and '
  'still counted.';
