-- ===========================================================================
-- Jarvis -- migration 16: what a result is of, and what a tool worked out
--
-- Run after 01-15. Idempotent.
--
-- Two things, and they are the same idea at two levels.
--
-- WHAT A RESULT IS OF
-- -------------------
-- A result could say which session it came from as a label -- "PTEN m1 s2
-- 2023-10-02" -- and nothing else. So grouping the catalogue by animal meant
-- taking that string apart again in the browser, and finding everything from
-- one recording meant hoping the label had been spelled the same way every
-- time it was written.
--
-- The run record already knew: the gid, the project, the mouse, the session
-- number. The catalogue was dropping all four. These columns are where they
-- land, so "what do we have on m306" is a query rather than a text search.
--
-- WHAT A TOOL WORKED OUT
-- ----------------------
-- `tool_results` is the expensive half of any tool that reads a recording and
-- produces numbers: keyed on the recording and on a short hash of the settings
-- that change the answer, so
--
--   * asking the same question of the same recording twice is free the second
--     time, on any machine that has the row;
--   * a bulk run that dies halfway resumes by skipping what is already there;
--   * two people running different halves of one set are not each doing the
--     other's;
--   * and re-running with a different frequency range does not overwrite the
--     old numbers -- it writes different ones beside them, under a different
--     hash, and both stay answerable.
--
-- Panorama has worked this way since it grew sets. Incisor now does too. The
-- point of the table is that the answers travel: a colleague's scan answers
-- your question without being re-run.
--
-- WHY THE NUMBERS AND NOT THE PICTURES
-- ------------------------------------
-- About thirty kilobytes a recording. The spectrogram behind it is megabytes
-- and is regenerable from the numbers in milliseconds, so it stays in
-- GUI_logs/.cache and is never sent anywhere. A row here is what a figure or
-- a statistic is made from, which is the part that cannot be got back without
-- the recording and the time it takes to read it.
--
-- Safe the same way bank_entries is: keyed on (tool, gid, params_hash), which
-- is deterministic, so two machines computing the same thing write the same
-- key rather than two rows. barry_keep_newest() arbitrates, as everywhere.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- results: what it is of, and which code made it
-- ---------------------------------------------------------------------------
alter table results add column if not exists project      text;
alter table results add column if not exists mouse        integer;
alter table results add column if not exists session_no   integer;
alter table results add column if not exists recorded_on  date;
alter table results add column if not exists tool         text;
-- exhibit | scratch. Scratch is a by-product -- a harness screenshot, a debug
-- report -- and is not expected to arrive here at all; the column exists so a
-- row that does can be told apart rather than counted as a result.
alter table results add column if not exists lane         text;
alter table results add column if not exists sha256       text;
alter table results add column if not exists app_version  text;
alter table results add column if not exists commit_sha   text;
-- The vault record this file is a rendering of, when it is one.
alter table results add column if not exists of_params_hash text;

create index if not exists results_project_idx on results (project);
create index if not exists results_mouse_idx   on results (mouse, session_no);
create index if not exists results_tool_idx    on results (tool);
create index if not exists results_sha_idx     on results (sha256);

-- ---------------------------------------------------------------------------
-- runs: which code, and the recipe that rebuilds it
-- ---------------------------------------------------------------------------
alter table runs add column if not exists app_version text;
alter table runs add column if not exists commit_sha  text;
-- The complete layout a rebuild reads back. It has always been written to the
-- run record on disk and has never had a column here -- so a colleague could
-- see that a figure was made and still not rebuild it.
alter table runs add column if not exists recipe      jsonb;

-- ---------------------------------------------------------------------------
-- tool_results: the vault
-- ---------------------------------------------------------------------------
create table if not exists tool_results (
  -- "<tool>:<gid>:<params_hash>", deterministic, so the same computation on
  -- two machines is one row.
  id            text primary key,
  tool          text not null,
  gid           text references sessions(gid) on delete cascade,
  params_hash   text not null,
  -- What was asked. The settings that change the answer, as sent.
  spec          jsonb not null default '{}'::jsonb,
  -- What came back. Freeform because every tool's numbers are its own; the
  -- shape belongs to the tool, not to this table.
  numbers       jsonb not null default '{}'::jsonb,
  -- Which library, at which version, produced the fit. The single most
  -- useful thing to have written down when two answers disagree.
  engine        jsonb,
  session_label text,
  region        text,
  channel_label text,
  seconds       double precision,
  computed_at   timestamptz,
  computed_by   text,
  machine       text,
  app_version   text,
  commit_sha    text,
  deleted_at    timestamptz,
  updated_at    timestamptz not null default now(),
  updated_by    text
);
create index if not exists tool_results_gid_idx  on tool_results (gid);
create index if not exists tool_results_tool_idx on tool_results (tool, params_hash);
create index if not exists tool_results_upd_idx  on tool_results (updated_at);

-- ---------------------------------------------------------------------------
-- Row level security, the same shape as every other table: the service role
-- works, a publishable key gets nothing.
-- ---------------------------------------------------------------------------
alter table tool_results enable row level security;
revoke all on tool_results from anon;

-- ---------------------------------------------------------------------------
-- Newest wins, server-side, so no client can get it wrong.
-- ---------------------------------------------------------------------------
drop trigger if exists tool_results_keep_newest on tool_results;
create trigger tool_results_keep_newest
  before insert or update on tool_results
  for each row execute function barry_keep_newest();
