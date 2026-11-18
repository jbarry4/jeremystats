-- ===========================================================================
-- BARRY GUI -- row level security
--
-- Run this after 01_schema.sql.
--
-- Read this bit before you run it
-- -------------------------------
-- This is unpublished recording data: mouse ids, session times, curated
-- events, and the paths they live at. A Supabase *publishable* key is meant
-- to be public -- it goes in web pages, it ends up in browser history, it is
-- not a secret. So the default here is that the publishable key can do
-- nothing at all: RLS is on, and there are no policies for `anon`.
--
-- That means BARRY talks to this project with the **secret** key, which lives
-- in a gitignored file on each machine and is never committed. That is the
-- same trust boundary the lab already has -- anyone who can clone the repo
-- can read the logs -- so it is not a downgrade, and it is a great deal
-- better than "anyone who ever saw the project URL".
--
-- When you want per-person access instead (recommended once more than a
-- couple of people are on it), turn on Supabase Auth, invite the lab, and
-- uncomment the block at the bottom. Then each person signs in and the secret
-- key can be retired entirely.
-- ===========================================================================

alter table machines          enable row level security;
alter table sessions          enable row level security;
alter table session_paths     enable row level security;
alter table session_sightings enable row level security;
alter table mice              enable row level security;
alter table bank_entries      enable row level security;
alter table curation_sets     enable row level security;
alter table curation_events   enable row level security;
alter table layer_sheets      enable row level security;
alter table layer_labels      enable row level security;
alter table results           enable row level security;
alter table storyboards       enable row level security;
alter table runs              enable row level security;
alter table activity          enable row level security;
alter table errors            enable row level security;
alter table error_marks       enable row level security;
alter table presets           enable row level security;
alter table prefs             enable row level security;

-- Nothing for `anon` on purpose. The service role bypasses RLS entirely, so
-- BARRY with the secret key keeps working and a leaked publishable key buys
-- nobody anything.
--
-- Belt and braces: revoke the grants PostgREST would otherwise expose, so
-- even a policy added by accident later cannot open a table to the public
-- key without someone also re-granting.
do $$
declare
  t text;
begin
  foreach t in array array[
    'machines', 'sessions', 'session_paths', 'session_sightings', 'mice',
    'bank_entries', 'curation_sets', 'curation_events', 'layer_sheets',
    'layer_labels', 'results', 'storyboards', 'runs', 'activity', 'errors',
    'error_marks', 'presets', 'prefs'
  ]
  loop
    execute format('revoke all on table %I from anon', t);
  end loop;
end;
$$;

revoke all on v_session_overview  from anon;
revoke all on v_curation_progress from anon;


-- ===========================================================================
-- Optional: per-person access via Supabase Auth
--
-- Uncomment everything below once the lab has accounts. Every signed-in
-- person gets full read and write -- which is the honest description of how
-- a lab shares a dataset, rather than an elaborate permission scheme nobody
-- maintains. Delete a person's account and their access goes with it.
--
-- After enabling this you can rotate the secret key out of every machine and
-- have BARRY sign in instead.
-- ===========================================================================
--
-- do $$
-- declare
--   t text;
-- begin
--   foreach t in array array[
--     'machines', 'sessions', 'session_paths', 'session_sightings', 'mice',
--     'bank_entries', 'curation_sets', 'curation_events', 'layer_sheets',
--     'layer_labels', 'results', 'storyboards', 'runs', 'activity', 'errors',
--     'error_marks', 'presets', 'prefs'
--   ]
--   loop
--     execute format('grant select, insert, update, delete on table %I
--                     to authenticated', t);
--     execute format('drop policy if exists %I on %I',
--                    t || '_lab_all', t);
--     execute format(
--       'create policy %I on %I for all to authenticated
--        using (true) with check (true)', t || '_lab_all', t);
--   end loop;
-- end;
-- $$;
--
-- grant select on v_session_overview, v_curation_progress to authenticated;
