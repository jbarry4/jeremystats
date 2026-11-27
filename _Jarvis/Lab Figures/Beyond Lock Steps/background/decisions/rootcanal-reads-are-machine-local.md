# rootcanal-reads-are-machine-local

_Root Canal reads (.npz), Incisor scans and Doppler runs live in gitignored GUI_logs/.cache; since 2026-10-30 the app copies them to the VACC answers shelf and fetches on a miss -- but only the app process, never tools/checks._

A Root Canal read (`GUI_logs/.cache/rootcanal/<gid>__<readhash>.npz`, and
the `.rows2-*.json` member-rows cache beside it) is cache: gitignored. The
same goes for Incisor's and Doppler's full answers (`.cache/incisor`,
`.cache/doppler`). Their *records* (`GUI_logs/<tool>/results`) sync, so
another machine knows a result exists without having it.

Consequence found 2026-10-06: all 18 saved pools were saved on Strawbarry,
and opened on Bluebarry every press failed with "u:… is not a Root Canal
result or a cached read on this machine". Fixed in 2026.10.06.2: pool
requests carry `saved: {artifact_id, version}`, and an away member is
rebuilt from that saved payload.

**The shelf (2026.10.30.3).** The user asked that anything processed on any
device be openable everywhere without reprocessing. `backend/answers.py`
copies each new cache file to the VACC shared space,
`/gpfs2/scratch/sakhava1/Jarvis Data/_answers/<tool>/<name>.gz`, which has
default ACLs for the lab. A backfill sends existing caches a few minutes
after start. A miss in `_incisor_recall`, `_doppler_recall` or
`_rootcanal_have` fetches from there. The listing is one `ls` per tool,
cached for 2 minutes. Status is at `/api/answers/status`.
- **Only the app process** (`Jarvis_CLOUD_SYNC` on) touches the shelf.
  Tools and checks do not, so a check that moves a .npz aside keeps testing
  "elsewhere".
- The shelf is scratch and can be purged. The computing machine's own
  .cache is still the real copy.

**Why:** it is easy to assume that something which syncs (records,
artifacts) implies what it points at (the read) is present too.

**How to apply:** a new Root Canal feature that touches a read must still
say so when neither the disk nor the shelf has it. Test "elsewhere" in a
throwaway store, as `_saved_elsewhere` in tools/check_rootcanal.py does. See
[machine-has-two-names](machine-has-two-names.md), `cloud-pull-ran-on-the-writers-clock` (a note not copied here).
