# GUI_logs

Everything BARRY GUI remembers, kept as plain JSON so it travels through git.

| Folder | What it holds |
|---|---|
| `runs/YYYY-MM-DD/` | One file per script or pipeline stage run: what ran, with which parameters, against which session, and how it ended. |
| `sessions/` | One file per recording: bad channels, notes, and every path the session has been seen at. |
| `presets/` | Named filter presets, event-import presets, and figure layouts. |
| `errors/` | One JSONL file per day, one error per line. |
| `index.json` | A pooled roll-up of everything above, regenerated on demand. |

## Why one file per run and per session

Git merges separate files without conflict. Two people can both work, both
commit, and a pull brings in both sets. A single shared log would conflict on
almost every push.

## Sync

BARRY never commits or pushes on its own. It only writes files here. To share
your work:

    git add "BARRY GUI/GUI_logs"
    git commit -m "session logs"
    git push

To pick up everyone else's, just `git pull` -- new files appear and BARRY reads
them on the next refresh.

## Session identity

Sessions are keyed on mouse number + session number + recording start time,
parsed from the folder names and the Neuralynx header. That key is identical on
every machine, so a bad channel marked on one computer is found on the next,
even though one mounts the data at `D:\PTEN` and another at
`\\netfiles03.uvm.edu\bigdata_jbarry`.
