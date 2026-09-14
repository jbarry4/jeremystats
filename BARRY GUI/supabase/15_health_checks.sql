-- ===========================================================================
-- Jarvis -- migration 15: continuity checks
--
-- Run after 01-14. Idempotent.
--
-- Cheetah closes a record early when acquisition hiccups, and Toothy
-- concatenates across the break -- which closes the gap and labels every
-- later sample earlier than it truly is, by up to 121.9 ms on the recordings
-- in this archive. The check that finds this is cheap and its answer is
-- durable: it only changes when the files do.
--
-- Which is exactly why throwing the answer away was wrong. "Does this session
-- have gaps" is answerable one session at a time by running the check. "Which
-- of these three hundred have gaps, who established that, and has anything
-- been done about it" is not, and that is the question at the scale anybody
-- actually works at.
--
-- Why this table is safe
-- ----------------------
-- Append-only, keyed on the check's own id. A check is a thing that happened
-- on a date on a machine; it is never edited. So:
--
--   * Two machines checking the same recording produce two rows, which is
--     correct -- they are two facts, not a conflict. No last-writer, no
--     clock comparison, no merge. (Comparing two machines' timestamps has
--     been wrong in eleven places in this codebase; this table cannot join
--     that list.)
--
--   * `updated_at` is the check's own time, not now(). It never changes, so
--     the incremental push sends each check exactly once.
--
-- `gap_map_sha` is the hinge. A re-timed event set is stamped with the map it
-- was corrected against, and that hash is produced here -- so "this set was
-- corrected against 724351c3a1ea17a1" and "that map came from these files, on
-- this date, checked by this person" can be put side by side. Without it, a
-- correction is an assertion; with it, it is traceable.
--
-- No foreign key to `sessions`. A check on a recording that has not been
-- registered yet is still a fact worth keeping, and migration 14 is a
-- standing reminder that an FK rejection here aborts the whole push.
-- ===========================================================================
create table if not exists health_checks (
  id         text        primary key,
  -- The registry's session id. NOT an identity string: the bank and the
  -- health log both key on this, and matching on the other silently returns
  -- nothing, which reads as "nothing is filed against this recording".
  gid        text,
  path       text,
  label      text,

  -- When the check ran, who ran it, and where.
  at         timestamptz,
  by_user    text,
  machine    text,

  level      text,

  -- What it found. `n_segments = 1` is a clean recording; anything more is
  -- the concat issue, and `max_time_error_ms` is how wrong the times are by
  -- the end of it.
  n_segments          integer,
  n_gaps              integer,
  seconds_lost        double precision,
  max_time_error_ms   double precision,
  true_duration_s     double precision,
  concat_duration_s   double precision,

  -- The identity of the answer, and the rule that produced it. Pinned so a
  -- future spikeinterface default is a visible change rather than a mystery.
  gap_map_sha text,
  gap_rule    text,

  -- How thorough the check was. A four-channel spot-check and a full parse
  -- of all sixty-four are both worth keeping and are not the same evidence.
  n_ncs        integer,
  n_probed     integer,
  all_channels boolean default false,
  -- Channels that segmented differently from the reference: a folder that
  -- was mixed or partly copied looks like this, not like a recording with
  -- gaps.
  mismatches   integer default 0,

  updated_at timestamptz not null default now()
);

create index if not exists health_checks_gid_idx on health_checks (gid);
create index if not exists health_checks_updated_idx on health_checks (updated_at);
-- The archive-wide question: which recordings have gaps?
create index if not exists health_checks_segments_idx on health_checks (n_segments);

alter table health_checks enable row level security;

comment on table health_checks is
  'Every continuity check anybody has run: when, by whom, on which machine, '
  'and what it found. Append-only and keyed on the check''s own id, so two '
  'machines checking one recording produce two rows rather than a conflict. '
  'Makes "which of these recordings have gaps" a question about the archive '
  'rather than one you can only ask a session at a time.';
comment on column health_checks.gap_map_sha is
  'Hash of the segment map this check produced. A re-timed event set is '
  'stamped with the map it was corrected against, so this is what connects '
  'a correction to the evidence for it.';
comment on column health_checks.updated_at is
  'The check''s own time, never now(). It does not change, so the '
  'incremental push sends each check exactly once.';
comment on column health_checks.all_channels is
  'Whether every .ncs was parsed or only a spot-check. Both are worth '
  'keeping and they are not the same evidence.';
