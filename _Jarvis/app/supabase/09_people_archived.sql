-- ===========================================================================
-- BARRY GUI -- migration 09: archived profiles
--
-- Run after 01-08. Idempotent.
--
-- Who should no longer be OFFERED work. Somebody who has left the lab cannot
-- be removed from the roster -- it is compiled from the decisions, the banked
-- sets and the layer sheets, so their name is there because the data says so,
-- and taking it off could not un-say it. Archiving is the answer the curation
-- shelf already gives: off the bench, nothing destroyed.
--
-- Shared, because being offered work is a lab-wide question. An archive that
-- lived on one machine would take somebody off one person's pickers and leave
-- them on everybody else's.
--
-- It changes no count anywhere. An archived person's decisions are still
-- theirs and still counted, their name still appears on every record it is
-- on, and their aliases still fold -- a merge and an archive are unrelated
-- statements. Reversible, with nothing lost.
-- ===========================================================================
alter table people add column if not exists archived boolean;

comment on column people.archived is
  'True when this person should no longer be offered as an owner for new '
  'work -- they have left, or the entry was a test. NOT a deletion and not '
  'a statement about the past: every decision, banked set and layer sheet '
  'they touched still carries their name and is still counted for them.';

-- Ordinary reads want the ones who are still around.
create index if not exists people_not_archived
  on people (name) where archived is not true;
