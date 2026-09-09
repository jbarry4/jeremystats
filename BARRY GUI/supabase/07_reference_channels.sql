-- ===========================================================================
-- BARRY GUI -- migration 07: the anatomical reference channels
--
-- Run after 01-06. Idempotent.
--
-- Which channel sits at the fissure, which one carries the ripple, which one
-- is in the hilus. These are facts about where a probe ended up, they are the
-- thing every CSD is read against, and BARRY had nowhere to put them -- so
-- the answer lived in the Toothy workbook and was true for whoever had it
-- open.
--
-- Integers rather than a jsonb blob: each one is a single channel number, and
-- three named columns can be filtered and joined where `{"ripple": 4}` cannot.
-- ===========================================================================
alter table sessions add column if not exists ripple_channel integer;
alter table sessions add column if not exists fissure_channel integer;
alter table sessions add column if not exists hilus_channel integer;

-- Why the extraction went the way it did. Mostly "Success: Clean
-- extraction", but the interesting ones say "Bad channel hit (8) for Ripple"
-- or "Missing: No CA1 SP channel" -- which is exactly what somebody needs to
-- know before trusting the numbers above.
alter table sessions add column if not exists extraction_note text;
alter table sessions add column if not exists needs_processing boolean;
alter table sessions add column if not exists reference_channels_source text;

comment on column sessions.fissure_channel is
  'Channel at the hippocampal fissure. Corroborated against the StrataScope '
  'sheet rather than trusted: the hilus channel named here is labelled HIL '
  'in the layer sheet in 57 of 57 cases, and those came from a different '
  'spreadsheet imported separately.';
comment on column sessions.extraction_note is
  'What the Toothy extraction said. "Bad channel hit" and "Missing: No CA1 '
  'SP" are the rows worth reading before using the channels above.';

create index if not exists sessions_needs_processing
  on sessions (needs_processing) where needs_processing;
