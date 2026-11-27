# vacc-temp-has-a-1tb-quota

_gpfs3tmp ("Temp", Jarvis_temp) is NOT unlimited — pi-jbarry4's group quota there is 1000 GB (hard 1010), and on 2026-10-01 it was full_

The user said Temp (`/gpfs3tmp/pi/jbarry4/sakhava1/Jarvis_temp`) "allows basically any amount of files". That is true of the file count (a 1M limit). It is not true of bytes.

Measured 2026-10-01 with `mmlsquota -g pi-jbarry4 -Y --block-size 1K gpfs3tmp`:
- The quota is 1000 GiB, with a hard limit of 1010 GiB. Usage was 1010 GiB, grace expired.
- 1010 GB of that was `sakhava1/DEWEY GUI Project`.

Every upload write failed with `cat: write error: Disk quota exceeded`. Jarvis surfaced it as `[Errno 32] Broken pipe`, because the remote `cat` exited before ssh's stdin was drained.

Scratch (gpfs2) for the same group: 3.69 TB of a 4.4 TB quota, hard limit 8.8 TB.

`vacc.space(cfg, root)` and `vacc.room(space, need)` now read this before an upload sends anything. `vaccupload.refused()` turns a quota refusal into a `QuotaError` that carries the cluster's own words.

**How to apply:** never describe Temp as unlimited. Before recommending a destination for a big upload, read `vacc.space`. If a "Broken pipe" from ssh shows up anywhere else, read the far side's stderr. Related: `monolith-sweep-decisions` (a note not copied here), [vacc-upload-speed-is-per-stream](vacc-upload-speed-is-per-stream.md).
