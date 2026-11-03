"""
syncstate.py -- Is this on GitHub, in the shared database, both, or neither?

Records leave this computer by two roads, and until now the page could only
see one of them. `/api/cloud/items` (syncitems.py) says whether a record has
reached Supabase; nothing said whether it had been committed and pushed to
GitHub, which is the road a colleague's `git pull` takes and the only one
archives travel by. "Is my work safe and can Jeremy see it" is a question
about both, so the chip beside a set, a bank entry, a run, a figure or a
recording answers both: two small marks, each lit or dim.

The two halves are answered very differently, and neither touches a network.

GIT. Two commands per answer, both local and both fast on this repo (~80 ms
and ~45 ms measured 2026-11-03):

  git status --porcelain -z --untracked-files=all -- GUI_logs Results
      what is modified, added, deleted or untracked here -> "changed";
  git diff --name-only -z origin/master...HEAD -- GUI_logs Results
      what local commits changed that origin/master does not have yet ->
      "committed".

Everything else in a tracked folder is "pushed". The three dots matter: they
compare from the merge base, so a file a colleague changed in a commit this
machine has fetched but not pulled is NOT reported as "committed" -- the
two-dot form says "differs from origin", which reads every one of a
colleague's unpulled edits as our own unpushed work. And it is origin/master
AS LAST FETCHED: nothing here fetches. A fetch is a network call and a
credential prompt waiting to happen, and the answer it would correct is
"pushed" versus "committed", which `git push` settles anyway.

Only the files git names are looked at. The status of a record that has no
line in either answer is "pushed" without opening, listing or statting its
files -- the registry and the stores are slow to walk (memory: REG.by_gid
re-stats every shard; the registry read is listdir-bound), and a few hundred
lines of git output are all that ever differ.

CLOUD. Answered from cloudsync's own knowledge of what it has sent: the push
cursor (`last_push`) against each record's stamp, the artifact fingerprints
and shard hashes the last push remembered. That is `Sync.item_states` for
the kinds it already covers, and the same `_after(stamp, last_push)` test
`_push` uses to choose rows for the kinds it does not. ZERO requests to
Supabase: egress there is counted in requests, and a status that asked the
database every thirty seconds from every open window would cost more than the
sync it reports on (memory: Supabase egress is requests, not bytes).

The answer is kept CACHE_S seconds. The chips ask every thirty seconds while
one is on screen, and after every sync line in the feed; twenty seconds of
staleness is shorter than a push cycle, and a burst of views asking at once
costs one pair of git calls rather than one per view.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

from . import cloud as cloudmod
from . import cloudsync, shards
from .store import git_exe

CACHE_S = 20.0
#: The least time between two rebuilds asked for with ?fresh=1.
FRESH_S = 3.0

#: The kinds this answers for, and which road each one takes. A kind that
#: never travels by a road says so rather than showing that mark dim
#: forever, because "not yet" and "never" are different promises.
#:
#: `runs` go to Supabase push-only, like activity; `prefs` and `presets`
#: both ways. Everything listed travels by git: the folders git ignores
#: under GUI_logs (errors, activity, .cache, vacc_runs, histo_cache) hold
#: nothing a person would put a chip on.
KINDS = ("curation", "bank", "sessions", "runs", "results", "storyboards",
         "presets", "prefs", "artifacts", "braces", "aibeta", "layers")

#: git states, worst first. A record made of several files (one shard per
#: machine, a figure and its tag file) is as far along as its least
#: travelled file.
GIT_ORDER = ("changed", "committed", "pushed")


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _git(args, cwd):
    """Run git, return (ok, stdout bytes). Never raises."""
    exe = git_exe()
    if not exe:
        return False, b""
    try:
        res = subprocess.run([exe] + list(args), cwd=cwd,
                             capture_output=True, timeout=20,
                             creationflags=_no_window())
    except Exception:                                    # noqa: BLE001
        return False, b""
    return res.returncode == 0, res.stdout or b""


def _z(blob):
    return [p.decode("utf-8", "replace") for p in blob.split(b"\0") if p]


class SyncState:
    """Per record, where it has got to. Built once by app.py."""

    def __init__(self, app_dir, logs_dir, cloud_sync, store, results=None,
                 last=None):
        self.app = os.path.abspath(app_dir)
        self.logs = os.path.abspath(logs_dir)
        self.sync = cloud_sync
        self.store = store
        self.results = results
        # app.py's `_cloud_last`: whether the last sync went through, so a
        # chip waiting on a database that is not answering can say so.
        self.last = last if last is not None else {}
        # The app folder relative to the git top level ("BARRY GUI/"), asked
        # of git once rather than spelled here: the folder is about to be
        # renamed, and git paths come back relative to the top level.
        self._prefix = None
        # The logs folder relative to the app folder, for the same reason.
        self._logs_rel = os.path.relpath(self.logs, self.app).replace(
            "\\", "/").strip("/") + "/"
        self._cache = {"at": 0.0, "body": None}
        self._lock = threading.Lock()

    # -- git ----------------------------------------------------------------
    def _git_prefix(self):
        if self._prefix is None:
            ok, out = _git(["rev-parse", "--show-prefix"], self.app)
            self._prefix = out.decode("utf-8", "replace").strip() if ok else ""
        return self._prefix

    def _start_git(self):
        """Start both git questions in threads; `_git_files` collects them.

        Each is a separate process that spends its time in git, not in
        Python, so asking both at once and working out the cloud half while
        they run makes the answer as slow as the slowest of the three rather
        than their sum (measured 2026-11-03: ~170 ms of git in a ~340 ms
        answer, before; the cloud half alone, after)."""
        where = ["--", self._logs_rel.rstrip("/"), "Results"]
        jobs = {
            "status": ["status", "--porcelain", "-z",
                       "--untracked-files=all"] + where,
            "ahead": ["diff", "--name-only", "-z",
                      "origin/master...HEAD"] + where,
        }
        got = {}
        threads = []
        for name, args in jobs.items():
            def run(name=name, args=args):
                got[name] = _git(args, self.app)
            th = threading.Thread(target=run, daemon=True,
                                  name="barry-syncstate-git")
            th.start()
            threads.append(th)
        return threads, got

    def _git_files(self, started=None):
        """({app-relative path: "changed"|"committed"}, facts about git).

        Paths are relative to the app folder with forward slashes, the way
        the rest of the answer names them. Only files that are NOT pushed
        are listed; the rest are pushed by elimination.
        """
        facts = {"ok": False}
        pre = self._git_prefix()
        threads, got = started or self._start_git()
        for th in threads:
            th.join(30)
        ok, out = got.get("status", (False, b""))
        if not ok:
            facts["error"] = ("git is not answering here, so whether these "
                              "are on GitHub is not known.")
            return {}, facts
        files = {}
        toks = _z(out)
        i = 0
        while i < len(toks):
            tok = toks[i]
            i += 1
            if len(tok) < 4:
                continue
            xy, path = tok[:2], tok[3:]
            # A rename or copy staged in the index carries its old name as
            # the next NUL-separated field. Skipped, not counted: the old
            # name is a file that is no longer here.
            if "R" in xy or "C" in xy:
                i += 1
            if path.startswith(pre):
                files[path[len(pre):]] = "changed"
        facts["ok"] = True
        facts["changed"] = sum(1 for v in files.values() if v == "changed")
        # Commits here that origin/master (as last fetched) has not got.
        ok, out = got.get("ahead", (False, b""))
        if ok:
            n = 0
            for path in _z(out):
                if path.startswith(pre):
                    rel = path[len(pre):]
                    if rel not in files:
                        files[rel] = "committed"
                        n += 1
            facts["committed"] = n
        else:
            # No origin/master to compare with: a clone without the remote,
            # or a branch named otherwise. Committed is the most that can be
            # said honestly, so nothing is called pushed.
            facts["no_upstream"] = True
        facts["fetched_at"] = self._fetched_at()
        return files, facts

    def _fetched_at(self):
        """When origin/master was last fetched: FETCH_HEAD's time. The chip's
        "pushed" means "in origin/master as of then"."""
        p = getattr(self, "_fetch_head", None)
        if p is None:
            # Where the file is never moves while this process runs, so git
            # is asked once; after that it is one stat.
            ok, out = _git(["rev-parse", "--git-path", "FETCH_HEAD"], self.app)
            if not ok:
                return None
            p = out.decode("utf-8", "replace").strip()
            if not os.path.isabs(p):
                p = os.path.join(self.app, p)
            self._fetch_head = p
        try:
            return cloudmod.ts(os.path.getmtime(p))
        except (OSError, TypeError, ValueError):
            return None

    # -- which record a file belongs to -------------------------------------
    def _owner(self, rel, maps):
        """(kind, id) for an app-relative path, or None.

        From the name alone, because every store here names its shards by
        the record: `<base>@<machine>.json`, the base being the record's id
        or ending in it. Where it does not (sessions are filed under their
        key; a figure under its path) `maps` turns it into the id the page
        uses.
        """
        if rel.startswith("Results/"):
            rid = maps["results_by_rel"].get(rel[len("Results/"):].lower())
            return ("results", rid) if rid else None
        if not rel.startswith(self._logs_rel):
            return None
        parts = rel[len(self._logs_rel):].split("/")
        name = parts[-1]
        stem = name[:-5] if name.endswith(".json") else None
        if stem is None:
            return None
        base = shards.split_name(name)[0] or stem
        top = parts[0]
        if len(parts) == 2:
            if top == "curation":
                # The file drops what is not a letter or digit from the
                # set's kind ("ds.e4091b..." is filed as "dse4091b..."), so
                # the set id is looked up rather than read off the name.
                return ("curation", maps["curation_by_base"].get(base, base))
            if top == "event_bank":
                return ("bank", base.rsplit("_", 1)[-1])
            if top == "sessions":
                gid = maps["session_by_base"].get(base)
                return ("sessions", gid) if gid else None
            if top == "storyboards":
                return ("storyboards", base)
            if top == "presets":
                return ("presets", base)
            if top == "prefs":
                return ("prefs", base)
            if top == "layers":
                return ("layers", base)
            if top == "braces":
                return ("braces", base.rsplit("_", 1)[-1])
            return None
        if top == "runs" and len(parts) == 3:
            return ("runs", stem)
        if top == "results" and len(parts) == 3 and parts[1] == "curation":
            # A figure's tags, notes and star: named by the result id.
            return ("results", base)
        if top == "aibeta" and len(parts) == 3 and parts[1] == "runs":
            return ("aibeta", base)
        if top == "artifacts":
            if len(parts) == 3:
                return ("artifacts", base)
            if len(parts) == 4 and parts[1] == "snap":
                # A version's snapshot, filed under the artifact's id.
                return ("artifacts", parts[2])
        return None

    # -- cloud --------------------------------------------------------------
    def _cloud_states(self, last_push, on):
        """{kind: {id: (state, why)}} for every record in every kind, and
        the gids the push treats as known (see `_push`'s orphans)."""
        S = self.sync
        out = {k: {} for k in KINDS}
        maps = {"session_by_base": {}, "results_by_rel": {},
                "curation_by_base": {}}

        def judge(stamp):
            # Exactly `Sync.item_states`'s rule, and so `_push`'s.
            if not last_push:
                return "waiting"
            if not stamp:
                return "synced"
            return ("waiting" if cloudsync._after(stamp, last_push)
                    else "synced")

        # Sessions first: their gids are what every other table's rows are
        # checked against before a push sends them.
        known = set()
        for rec in (self.store.all_sessions() or []):
            gid = rec.get("gid")
            if not gid:
                continue
            for b in (rec.get("key"), gid):
                if b:
                    maps["session_by_base"][shards.safe_base(b)] = gid
            if S._is_demo(rec):
                out["sessions"][gid] = ("never", "demo")
                continue
            known.add(gid)
            out["sessions"][gid] = (judge(cloudmod.ts(
                cloudsync._prov(rec, "updated").get("at"))), None)

        # The kinds the push cursor already answers for, with the same
        # known-gid test it applies (a record of a recording the shared
        # table has not got stays here).
        try:
            items = S.item_states(None, last_push=last_push,
                                  known_gids=known or None)
        except Exception:                                # noqa: BLE001
            items = {}
        for sid in (items.get("curation") or {}):
            gid, _sep, ck = sid.partition("__")
            maps["curation_by_base"][shards.safe_base(
                gid, "".join(c for c in ck if c.isalnum()))] = sid
        for kind in ("bank", "curation", "layers", "artifacts", "braces",
                     "aibeta"):
            for rid, st in (items.get(kind) or {}).items():
                s = st.get("state")
                out[kind][rid] = (
                    "never" if s == "local" else
                    s if s in ("synced", "waiting", "unknown") else "unknown",
                    st.get("why"))

        # Runs: push-only history, stamped when they ran.
        for r in (self.store.all_runs() or []):
            rid = r.get("id")
            if not rid:
                continue
            prov = r.get("provenance") or {}
            out["runs"][rid] = (judge(cloudmod.ts(
                prov.get("at") or r.get("started"))), None)

        # Figures: the catalogue row, stamped the way rows_results stamps it.
        if self.results is not None:
            try:
                cat = self.results.catalog() or []
            except Exception:                            # noqa: BLE001
                cat = []
            for r in cat:
                rid = r.get("id")
                if not rid:
                    continue
                if r.get("rel"):
                    maps["results_by_rel"][str(r["rel"]).lower()] = rid
                gid = r.get("gid")
                if gid and known and gid not in known:
                    out["results"][rid] = ("never", "no recording")
                    continue
                up = cloudsync._prov(r, "updated")
                stamp = (cloudmod.ts(up.get("at"))
                         or cloudmod.ts(r.get("created"))
                         or cloudmod.ts(r.get("mtime")) or cloudsync.UNSTAMPED)
                out["results"][rid] = (judge(stamp), None)
            # Storyboards: from the book directly. `list_decks` draws each
            # deck's thumbnail, which is not a question this asks.
            try:
                decks = self.results.decks.all()
            except Exception:                            # noqa: BLE001
                decks = []
            for d in decks:
                if d.get("id"):
                    out["storyboards"][d["id"]] = (judge(cloudmod.ts(
                        cloudsync._prov(d, "updated").get("at"))), None)

        # Presets: one record per kind of preset, as newest as its newest.
        try:
            kinds = self.store.presets.bases()
        except Exception:                                # noqa: BLE001
            kinds = []
        for kind in kinds:
            stamps = [cloudmod.ts((p.get("saved") or {}).get("at"))
                      for p in (self.store.get_presets(kind) or [])]
            stamps = [s for s in stamps if s]
            out["presets"][kind] = (judge(
                max(stamps, key=cloudsync._ts_key) if stamps
                else cloudsync.UNSTAMPED), None)

        # Shared preferences: this machine's own shard of each, by the time
        # it was written -- the stand-in rows_prefs uses for the keys it
        # writes without a stamp. Another machine's shard is theirs to send.
        try:
            bases = self.store.prefs.bases()
        except Exception:                                # noqa: BLE001
            bases = []
        for base in bases:
            try:
                t = os.path.getmtime(self.store.prefs.mine(base))
            except OSError:
                out["prefs"][base] = ("synced", "from another machine")
                continue
            out["prefs"][base] = (judge(cloudmod.ts(t)), None)

        if not on:
            # Not connected: nothing here is shared, and "waiting" would be
            # a promise nobody keeps.
            out = {k: {rid: ("off", None) for rid in d} for k, d in out.items()}
        return out, maps

    # -- the answer ---------------------------------------------------------
    def answer(self, kinds=None, fresh=False):
        """The answer, from the cache unless it is older than CACHE_S.

        `fresh` is what the page sends after the feed reports a sync: the
        cache is then likely to be wrong in exactly the way the person is
        watching for. Still not more than one rebuild every FRESH_S, so a
        burst of sync lines in several windows is one pair of git calls.
        """
        want = [k for k in (kinds or "").split(",") if k in KINDS] or list(KINDS)
        with self._lock:
            body = self._cache["body"]
            age = time.time() - self._cache["at"]
            if (body is None or age > CACHE_S
                    or (fresh and age > FRESH_S)):
                body = self._build()
                self._cache.update(at=time.time(), body=body)
        if len(want) == len(KINDS):
            return body
        return dict(body, kinds={k: v for k, v in body["kinds"].items()
                                 if k in want})

    def _build(self):
        t0 = time.time()
        c = self.sync.cloud
        try:
            cfg = c.cfg or {}
        except Exception:                                # noqa: BLE001
            cfg = {}
        on = bool(getattr(c, "configured", False) and cfg.get("enabled"))
        try:
            last_push = (c.state() or {}).get("last_push")
        except Exception:                                # noqa: BLE001
            last_push = None

        self._git_prefix()            # once per process, before the threads
        started = self._start_git()
        states, maps = self._cloud_states(last_push, on)
        files, gfacts = self._git_files(started)

        # Each file git named to the record it belongs to, keeping the
        # worst state among a record's files.
        git = {}
        for rel, st in files.items():
            who = self._owner(rel, maps)
            if not who:
                continue
            have = git.get(who)
            if have is None or GIT_ORDER.index(st) < GIT_ORDER.index(have):
                git[who] = st
        default_git = ("pushed" if gfacts.get("ok") and not
                       gfacts.get("no_upstream")
                       else "committed" if gfacts.get("ok") else "unknown")

        # Grouped by the pair of states, ids listed under each: a few
        # thousand ids fall into a handful of groups, which is a much
        # smaller answer than a state pair spelled out per id.
        kinds, why = {}, {}
        for kind, d in states.items():
            groups = {}
            for rid, (cst, cwhy) in d.items():
                gst = git.get((kind, rid), default_git)
                groups.setdefault(gst + "|" + cst, []).append(rid)
                if cwhy and cst == "never":
                    why.setdefault(kind, {})[rid] = cwhy
            # Records git named that the stores did not (deleted here, a
            # file being written as this ran): said, so a chip for one is
            # not left guessing.
            for (k, rid), gst in git.items():
                if k == kind and rid not in d:
                    groups.setdefault(gst + "|unknown", []).append(rid)
            kinds[kind] = groups

        last = self.last or {}
        return {
            "ok": True,
            "at": cloudmod.now(),
            "took_ms": int((time.time() - t0) * 1000),
            "git": dict(gfacts, upstream="origin/master"),
            "cloud": {
                "on": on,
                "last_push": last_push,
                "last_ok": last.get("ok"),
                "running": bool(last.get("running")),
                # The sentence the existing marks already show for a failed
                # sync, said once here rather than per record.
                "error": (last.get("blocked_note") or last.get("error"))
                if last.get("ok") is False else None,
            },
            "kinds": kinds,
            # Why a record never reaches the database (a demo, a recording
            # the shared table has not got), only for those that do not.
            "why": why,
            # The files themselves, for a caller holding a path rather than
            # an id. Only those not yet pushed; anything else in a tracked
            # folder is pushed.
            "files": {st: sorted(p for p, s in files.items() if s == st)
                      for st in ("changed", "committed")},
        }
