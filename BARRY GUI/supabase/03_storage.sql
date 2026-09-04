-- ===========================================================================
-- BARRY GUI -- storage for the figures
--
-- Run this after 02_rls.sql.
--
-- Results are PNGs, PDFs and CSVs. They are committed to the repo today,
-- which is deliberate -- a figure viewable on GitHub beside the code and the
-- log entry that produced it is the point of it -- and that stays true. This
-- bucket is so a machine that has not pulled can still show the thumbnail,
-- and so the repo stops being the only copy.
--
-- Private, for the same reason the tables are: unpublished data.
-- ===========================================================================

insert into storage.buckets (id, name, public, file_size_limit,
                             allowed_mime_types)
values (
  'results',
  'results',
  false,                       -- never public; BARRY fetches with a key
  104857600,                   -- 100 MB, the same ceiling git is happy with
  array['image/png', 'image/jpeg', 'image/svg+xml', 'image/webp',
        'application/pdf', 'text/csv', 'text/plain', 'application/json',
        'video/mp4']
)
on conflict (id) do update
  set file_size_limit    = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types,
      public             = false;

-- No policies for `anon`, exactly as with the tables: the service role
-- bypasses RLS, so BARRY works and the publishable key does not.
--
-- Uncomment alongside the Auth block in 02_rls.sql when the lab has accounts.
--
-- drop policy if exists results_read  on storage.objects;
-- drop policy if exists results_write on storage.objects;
-- create policy results_read on storage.objects
--   for select to authenticated using (bucket_id = 'results');
-- create policy results_write on storage.objects
--   for all to authenticated
--   using (bucket_id = 'results') with check (bucket_id = 'results');
