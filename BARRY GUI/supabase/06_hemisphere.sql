-- ===========================================================================
-- BARRY GUI -- migration 06: hemisphere, and layer sheet history
--
-- Run after 01-05. Idempotent: every statement is `if not exists` or `add
-- column if not exists`, so running it twice is harmless.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- Which side of the brain a recording came from.
--
-- The lab's feeder sheet has carried this in a `side` column all along, which
-- means it has been true only for whoever had the spreadsheet open. It is not
-- a detail: a CA1 electrode in the left hippocampus and one in the right are
-- different recordings, and pooling them without saying so is the sort of
-- thing that survives all the way into a figure.
--
-- A plain text column rather than an enum. Every session in the sheet is
-- exactly one of L or R, but "both" and "unknown" are real answers for a
-- recording nobody has checked, and an enum would have to be migrated to say
-- either of them.
-- ---------------------------------------------------------------------------
alter table sessions add column if not exists hemisphere text;
alter table sessions add column if not exists hemisphere_source text;

comment on column sessions.hemisphere is
  'L or R. Which hippocampus the probe was in. Imported from the feeder '
  'sheet''s `side` column; null means nobody has said.';
comment on column sessions.hemisphere_source is
  'Where the value came from, so a wrong one can be traced back rather than '
  'argued about.';

create index if not exists sessions_hemisphere
  on sessions (hemisphere) where hemisphere is not null;

-- ---------------------------------------------------------------------------
-- Layer sheet history.
--
-- StrataScope sheets now carry versions, the same way banked event sets do,
-- and for the same reason: a layer sheet is evidence, and evidence with no
-- history cannot be cited. "The layers as they were migrated from the feeder
-- sheet" and "the layers after somebody corrected two channels" are different
-- facts, and a figure made from one should not be described by the other.
--
-- v0 is the empty sheet -- the state before anybody said anything. It looks
-- pointless until you need to answer "was this channel ever unlabelled, or
-- has it always said HIL", which is exactly the question that comes up when a
-- migration turns out to have been wrong.
--
-- Held as jsonb on the sheet rather than as its own table: a version is a
-- snapshot of at most a few dozen short strings, nothing joins to it, and a
-- table would buy normalisation nobody is going to query.
-- ---------------------------------------------------------------------------
alter table layer_sheets add column if not exists versions jsonb
  default '[]'::jsonb;

comment on column layer_sheets.versions is
  'Ordered history: [{v, at, by, machine, n, note, snap}], where snap is the '
  'whole channel->region mapping at that version. v0 is always the empty '
  'sheet.';
