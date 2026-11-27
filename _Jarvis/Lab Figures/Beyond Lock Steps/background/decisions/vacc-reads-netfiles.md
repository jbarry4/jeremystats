# vacc-reads-netfiles

_Since 2026-10-01 sakhava1 can read AND write /netfiles/bigdata_jbarry on the VACC (group jarvis_writes); compute nodes see it too. 1,461 recordings there._

The VACC NFS-mounts `netfiles03.uvm.edu:/sparta/bigdata_jbarry` at `/netfiles/bigdata_jbarry` (nfs4.2). It is the same share Windows reaches as `\\netfiles03.uvm.edu\bigdata_jbarry` (the rigs' `Y:`).

Measured 2026-10-07/08:
- Mode `drwxrws---+ jbarry4:jarvis_writes` (mtime Oct 1). `getent group jarvis_writes` = sakhava1, jbarry4. Before that it was grouped to `root` and refused to everyone.
- A compute node (node403, short partition) reads it: header read OK, 173 MB/s.
- A walk of the whole share for `CSC1.ncs`/`CSC1_0001.ncs` takes ~141-153 s and finds 1,461 recording folders (Jeremy3 807, Jeremy2 301, ProcessedPtenData 247, Cdrivebckup 55, HOF 46).
- (2026-10-13: DESKTOP-4H65AI7 *does* reach `\\netfiles03.uvm.edu\bigdata_jbarry` over SMB now, ~90 MB/s; the older "cannot reach" note is out of date.)

**The group can write the share, and it is the lab's primary data.** Jarvis must never write there; runs write only under `workspace/runs/<rid>`. The one sanctioned exception is the user's own archive run, `netfiles-archive-run` (a note not copied here). Since 2026-11-27 the user also allows analysis files in `\netfiles03.uvm.edubigdata_jbarryJarvis Data (Non VACC)`; nowhere else.

From Claude's tools, reach the VACC through the Bash tool (Git Bash's OpenSSH 8.7) with `< /dev/null`; Windows OpenSSH run from the PowerShell tool hangs without output.

**How to apply:** don't describe netfiles as refused any more (CHANGELOG and old comments say it was). Other netids are still refused: the fix is adding them to `jarvis_writes` (Shahriar), not vacchelp. Supersedes the "permission-denied" line in [kcnt1-vacc-trees](kcnt1-vacc-trees.md). The registry-side machinery is `backend/vaccfind.py` and `BARRY.vacc.reach` (see `vacc-loaded-at-the-catalogue-level` (a note not copied here)).
