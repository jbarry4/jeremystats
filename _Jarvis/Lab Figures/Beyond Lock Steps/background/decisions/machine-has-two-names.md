# machine-has-two-names

_In BARRY, the same computer has several identifiers — provenance().machine, its host, and the shard/hostname id — and comparing the wrong one passes vacuously._

The same computer answers to several names in BARRY, and they are not
interchangeable:

- `STORE.provenance()["machine"]` — e.g. `"Bluebarry"`. This is what every
  **activity row and error row** carries, and the `machine` of an artifact
  version or a results record's `created`.
- `provenance()["host"]` — the Windows computer name, e.g. `"BarryLab"`.
  Event Bank versions have shown this in their `machine` field (seen
  2026-10-06).
- The shard id / `machines.hostname` / `/api/devices`'s `machine` — e.g.
  `"desktop-4h65ai7-d565"`. **Shard filenames** (`…@desktop-4h65ai7-d565.json`)
  and `_shard.machine` use this, as do the device table and presence rows.

Known mapping (verified 2026-10-06):
- Bluebarry = host DESKTOP-4H65AI7 = shard `desktop-4h65ai7-d565`. This is
  the machine Claude runs on.
- Strawbarry = host BarryLab = shard `barrylab-d8e8`. Rain's Root Canal
  pools and reads (2026-10-02) were made there.

**Why:** filtering "not this machine" against the device id matches nothing,
because no log row has ever carried it — so the filter silently passes and
the exclusion never happens. On 2026-09-08 this made me conclude this
machine's activity was stranded from the cloud (it was not; it was there
under the other name), and a harness check asserting "this machine is not in
the digest" passed vacuously for the same reason.

**How to apply:** when filtering or grouping log data by machine, use
`provenance().machine`. When talking to the device or presence tables or
reading shard filenames, use the shard id. When saying where something was
made, say the provenance name and, if useful, its host. Routes that exclude
a host should return the name they used (`/api/digest` returns
`excluded_host`) so a caller can compare the same one. The `machines` table
is incomplete — it holds only computers that registered a heartbeat (3 of 6
here) — so a machine list must union it with the names appearing in the
activity and error logs. See `curation-work-is-sharded-per-machine` (a note not copied here) and
[rootcanal-reads-are-machine-local](rootcanal-reads-are-machine-local.md).
