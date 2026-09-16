-- ===========================================================================
-- BARRY GUI -- migration 13: the layer workbench
--
-- Run after 01-12. Idempotent.
--
-- StrataScope now has the workbench event curation has had: sheets you have
-- picked up, whose they are, and ones filed away. `curation_sets` has carried
-- the same three facts from the start; `layer_sheets` had nowhere to put them,
-- so a bench existed per computer and could not answer "is anybody already
-- labelling this recording" -- which is the whole reason to share it.
--
-- `is_open` rather than `open`: `open` is not reserved in Postgres but it is
-- in enough of the tools that read this table that quoting it everywhere is a
-- worse trade than naming it plainly. `curation_sets.is_open` did the same.
-- ===========================================================================
alter table layer_sheets add column if not exists name text;
alter table layer_sheets add column if not exists assignee text;
alter table layer_sheets add column if not exists is_open boolean default false;
alter table layer_sheets add column if not exists opened_at timestamptz;
alter table layer_sheets add column if not exists opened_by text;
alter table layer_sheets add column if not exists archived boolean default false;
alter table layer_sheets add column if not exists archived_at timestamptz;
alter table layer_sheets add column if not exists archived_by text;

comment on column layer_sheets.is_open is
  'On somebody''s bench right now. Not a stage and not a lock: it says who is '
  'working on what, so two people do not label one recording twice.';

comment on column layer_sheets.archived is
  'Filed away -- off the bench and off the shelf. Nothing is deleted: the '
  'labels, the versions and the snapshots all stay.';

comment on column layer_sheets.name is
  'What the work set is called, when that is not simply the recording. A '
  'second pass after a probe map was corrected is not the same work as the '
  'first.';
