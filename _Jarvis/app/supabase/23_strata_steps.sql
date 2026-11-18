-- ===========================================================================
-- BARRY GUI -- migration 23: StrataScope's steps
--
-- Run after 01-22. Idempotent.
--
-- StrataScope now labels in steps (0 Theta Walk, 1 CA1, 2 the hilus, 3 the
-- molecular layer in thirds, 4 sign off), and a sheet keeps how each line was
-- decided beside the label: the Theta Walk bouts painted by hand, wheel times
-- typed from the notes, the parameters (contact spacing, species, the GCL
-- half-thickness, the reference channel ...), a confidence per boundary
-- (sure / likely / guess), the anchors (sp, the fissure, the granule
-- layers), the checks as they stood at sign-off, and who signed it.
--
-- One jsonb column for all of it, plus the time any of it last changed. The
-- per-field merge happens on each machine (layers.py keeps them as separate
-- shard fields); the cloud only has to carry the newest whole, and
-- `strata_at` is what a pull compares to decide whether it is newer.
--
-- Until this is run the sheets still sync -- labels, names, the bench -- and
-- the steps travel by git only, as the shard files do.
-- ===========================================================================
alter table layer_sheets add column if not exists strata jsonb;
alter table layer_sheets add column if not exists strata_at timestamptz;

comment on column layer_sheets.strata is
  'StrataScope''s steps for this sheet: states (Theta Walk bouts), wheel, '
  'params, confidence (per boundary: sure/likely/guess), steps (status per '
  'step), anchors, checks, signed. Written by Jarvis; see backend/layers.py '
  'STRATA_FIELDS.';

comment on column layer_sheets.strata_at is
  'When any of `strata` last changed, on the machine that changed it. A pull '
  'takes the cloud''s copy only when this is newer than its own.';
