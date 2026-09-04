# Supabase

The shared copy of everything BARRY knows.

## Run these, in this order

In the Supabase dashboard → **SQL Editor** → paste, Run. Each is safe to run
more than once.

| file | what it does |
|---|---|
| `01_schema.sql` | the tables, indexes, the newest-wins trigger, two views |
| `02_rls.sql` | locks it down — **read the note at the top of that file** |
| `03_storage.sql` | the `results` bucket for figures |

## Then, on each machine: nothing

Clone the repo and start BARRY. `cloud.json` is tracked, so a clone already
knows which project to sync to. The only thing it cannot carry is the key —
so BARRY asks for it, once, in the terminal as it starts:

```
  This copy syncs to Supabase project 'svyymanowlfoyblinnny',
  but this machine has not been given the key yet.
  ...
  Supabase secret key: _
```

Press Enter to skip and BARRY runs exactly as before — the sync is an
addition, never a requirement. The Sync panel asks too, so whichever window
somebody is looking at is enough. Either way it goes to
`GUI_logs/.cloud.json`, which git ignores.

Pasting the publishable key by mistake is caught by name, because the two sit
next to each other in the dashboard and the alternative is a permissions
error six steps later that explains nothing.

The first machine to sync uploads everything. Every one after that finds it
already there and only sends what is new — every write is an upsert, and the
database drops anything older than what it already has, so a re-run after a
failure picks up rather than duplicating.

## About the key

`02_rls.sql` gives the **publishable** key no access at all. That is
deliberate: a publishable key is meant to be public, and this is unpublished
recording data. BARRY uses the **secret** key.

Two config files, and the difference between them is the point:

| file | tracked? | holds |
|---|---|---|
| `BARRY GUI/cloud.json` | yes | which project, how often. **No key.** |
| `GUI_logs/.cloud.json` | no | the key, on that machine only |

Nothing writes a key to a tracked path: `save_shared_config()` drops it,
`load_config()` refuses to *use* one found there and says so instead, the
`/api/cloud/key` endpoint asks git before saving, and `cloud_setup.py` does
the same. `tools/test_freshclone.py` builds what a clone would actually get
and greps it for anything key-shaped.

**This repo is currently public.** `jbarry4/jeremystats` returns
`private: false`, which means anyone can already read `GUI_logs` — mouse ids,
recording times, bad channels, the paths on your drives, and the email on
every record. The key is not in there and will not be, but the data is.
Settings → General → Change visibility → Private.

Once more than a couple of people are on this, turn on Supabase Auth, invite
the lab, and uncomment the block at the bottom of `02_rls.sql`. Then each
person signs in and the secret key can be retired from every machine.

If a secret key ever does get committed: rotate it in the dashboard. That is
the only real fix, and it takes a minute.

## What syncs, and which way

**Both ways** — things two people edit:
sessions, the paths and sightings under them, mice, the event bank, curation
sets and every individual decision in them, layer sheets and every channel
label, result tags and notes, storyboards, presets, shared preferences.

**Up only** — append-only history:
runs, activity, errors. Pulling another machine's activity into this machine's
day log would be writing their actions into a file that says it is yours. The
combined history is a query instead:

```sql
select at, machine, git_user, action, detail from activity order by at desc;
```

**Files**: figures go up into the `results` bucket, and a machine that does
not have one pulls it down into the same folder the Results view shows. What
you see in BARRY is what is in `BARRY GUI/Results/`.

**Not synced**: theme, pane sizes, window state. Those describe the screen in
front of you, not the project.

## The folders on disk

Two trees are meant to be opened by people, not just by BARRY:

- `BARRY GUI/Results/` — figures, in the folders the Results view shows.
  Filing something in the GUI **moves the file**. One idea, not a label
  beside a path that disagrees with it.
- `BARRY GUI/Data Bank/` — the Event Bank as `Project/mouse/session/` with a
  CSV of times and a JSON of everything else, plus `_index.csv` over the lot.
  Derived and gitignored: it is rebuilt whenever the bank changes, so delete
  it freely.

## Why the files did not go away

BARRY writes locally first, always. That is what makes it work on a rig with
no network and on a drive that is not mounted, and it is why nothing has been
lost so far. Postgres is the shared source of truth; the per-machine JSON in
`GUI_logs` is the local buffer and the offline queue.

It also means the sync can be honest about time. A laptop that has been off
since Tuesday pushes edits stamped Tuesday, and `barry_keep_newest()` in
`01_schema.sql` drops them if Wednesday's work is already up there — enforced
in the database, so no client can get it wrong.

## Checking it

```
python tools/cloud_setup.py --check      # reachable? schema applied? counts?
python tools/cloud_migrate.py --dry-run  # what would go, table by table
```

and in the app, the **Sync** chip says when it last synced and what moved.

## Turning it off

```
python tools/cloud_setup.py --auto off
```

BARRY carries on exactly as before. Nothing depends on the network.
