# vacc-upload-speed-is-per-stream

_One ssh stream to the VACC login node carries ~10 MB/s; parallel streams scale (4 → 52, 8 → 89 MB/s), measured 2026-10-01_

Measured from the lab desktop to login.vacc.uvm.edu on 2026-10-01 by streaming random bytes into `cat > /dev/null` (nothing written):

| streams | throughput |
|---|---|
| 1 | about 10 MB/s |
| 4 | about 52 MB/s |
| 8 | about 89 MB/s |

The limit is per connection, not the link. `vaccupload.STREAMS = 6` sends that many files at once. The Monolith's 250 GB (48 folders) is therefore about 50 minutes, not 7 hours.

**How to apply:** quote upload times at about 80 MB/s with six streams. Do not quote the single-stream rate. If uploads seem slow, check that `streams` is actually being passed. Related: `monolith-sweep-decisions` (a note not copied here).
