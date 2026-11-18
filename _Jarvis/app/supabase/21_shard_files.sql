-- ===========================================================================
-- Jarvis -- migration 21: shard files (Braces sets, AI Beta runs)
--
-- Run after 01-20. Idempotent.
--
-- Two of the stores people work in every day only ever travelled by git:
-- Braces' alignment sets (GUI_logs/braces) and AI Beta's runs
-- (GUI_logs/aibeta/runs). A set reviewed on the rig was not on the desktop
-- until somebody committed and pulled -- asked for 2026-10-06, with a mark
-- on each saying whether it has gone up.
--
-- Both are already sharded per machine: each computer writes only its own
-- shard of a record, and every computer reads all of them and merges by the
-- stamps inside. So this table carries exactly what git carries -- the shard
-- file -- and nothing has to be merged on the way:
--
--   * A machine sends only ITS OWN shards (`machine` is the sender), and only
--     when one's bytes change (`sha`). Each push carries at most ~800 KB of
--     them; the rest go on the next.
--   * A pull writes another machine's shard into GUI_logs/.cache/cloudshards,
--     which the store reads beside its own and git ignores -- so a pulled
--     file can never stand in the way of a `git pull`.
--   * `gz` is the file gzipped and base64'd, as artifact_payloads does it:
--     the database stores and serves a string, not a document.
--
-- AI Beta's trained models (.joblib, tens of MB) are NOT here: a run record
-- travels, its model stays on the machine that trained it.
-- ===========================================================================
create table if not exists shard_files (
  -- "<store>/<file name>", e.g. "braces/s016e132432c8_bracee80946a@barrylab-d8e8.json".
  path       text        primary key,
  store      text        not null,
  machine    text        not null,
  sha        text        not null,
  bytes      integer,
  gz         text        not null,
  updated_at timestamptz not null default now(),
  updated_by text
);

create index if not exists shard_files_updated_idx on shard_files (updated_at);
create index if not exists shard_files_store_idx on shard_files (store);

alter table shard_files enable row level security;

comment on table shard_files is
  'Shard files of stores that are sharded per machine (Braces sets, AI Beta '
  'runs), as git carries them: one row per machine''s shard of a record, '
  'sent by that machine when its bytes change, written by every other '
  'machine into GUI_logs/.cache/cloudshards.';
comment on column shard_files.gz is
  'The shard file, gzipped and base64''d.';
comment on column shard_files.machine is
  'The machine that wrote this shard -- the only one that ever sends it.';
