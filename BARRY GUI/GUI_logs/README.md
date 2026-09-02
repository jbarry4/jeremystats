# GUI_logs

Everything BARRY GUI remembers, kept as plain JSON so it travels through git.

## The rule

**No two machines ever write the same file.**

That is what makes a merge conflict impossible here rather than merely
unlikely. A conflict requires two sides to have changed one file, and no file
in this folder has more than one possible author.

One file per session was already better than one shared log, but it only moved
the problem: two people both editing m1s2's bad channels still collided on
`sessions/m1s2.json`. So every record that can be **edited** is split again, by
machine:

    sessions/m1s2@z390-4f1a.json       what the Z390 knows about m1s2
    sessions/m1s2@lab-nlx-9c02.json    what the rig machine knows about m1s2

Git sees two unrelated files and brings both in. The merge happens on read, in
`backend/shards.py`, which is the right place for it -- only code knows that
two `paths` lists should be unioned while two `note` strings should not.

| Folder | What it holds |
|---|---|
| `runs/YYYY-MM-DD/` | One file per script or pipeline stage run. Written once by the machine that ran it, so it needs no machine tag. |
| `sessions/` | One file per recording **per machine**: bad channels, notes, the permanent id, and every path the recording has been seen at. |
| `mice/` | What is true about the animal rather than the recording -- group, genotype, whatever the lab invents. |
| `event_bank/` | Detected events, per entry per machine. |
| `curation/` | Curation sets: one decision per candidate, merged per candidate. |
| `layers/` | StrataScope layer sheets, merged per channel. |
| `storyboards/` | Decks. |
| `results/curation/` | Tags and notes on saved figures. |
| `presets/` | Named filter presets, event-import presets, figure layouts. |
| `prefs/` | Workbench preferences. Theme and pane sizes stay on the machine that set them; favourites and collections are shared. |
| `errors/`, `activity/` | One JSONL file per day **per machine**, one record per line. |
| `.cache/` | Derived roll-ups. Git ignores this: a file regenerated on every boot conflicts on every pull, and anyone can rebuild it in a second. |

## How the merge decides

Each shard records when that machine last changed each thing, and the compile
is per field:

- **last one wins** for anything that is one person's decision: a note, a
  label, a project.
- **earliest wins** for facts that must never move -- the permanent id, so two
  machines minting one for the same recording settle on the earlier rather
  than flipping forever.
- **union** for `paths`: every machine knows a different mount and none of
  them is wrong.
- **per key** for layer labels, curation decisions and mouse attributes, so
  two people working on the same recording from opposite ends both keep every
  call they made.

Deletions carry a stamp too, so removing something sticks instead of being
undone by an older shard that still lists it.

## Checking it

    python tools/conflict_check.py

It walks this folder and reports anything tracked by git that has no machine
tag. The sync chip in the app says the same thing. If you add a new kind of
record, that check is what tells you it was not sharded -- rather than the
first bad pull.

## Sync

BARRY never commits or pushes on its own. It only writes files here.

    git add "BARRY GUI/GUI_logs"
    git commit -m "session logs"
    git push

To pick up everyone else's, `git pull` -- new files appear and BARRY reads
them on the next refresh.

## Session identity

Recordings are recognised by mouse number + session number + recording start
time, parsed from the folder names and the Neuralynx header. That key is
identical on every machine, so a bad channel marked on one computer is found
on the next, even though one mounts the data at `D:\PTEN` and another at
`\\netfiles03.uvm.edu\bigdata_jbarry`.

The key is how a recording is *recognised*; the permanent id in each record is
what work hangs off. Re-read a header or fix a folder name and the key can
change -- the id never does.
