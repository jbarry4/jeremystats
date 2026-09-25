"""
sessreg.py -- The session registry: one record per recording, everywhere.

Jarvis already kept a file per session under GUI_logs/sessions/, keyed by
mouse + session + header start time. That key is good at recognising the same
recording across machines, and it is exactly the wrong thing to hang years of
work off, because it is *derived*. Re-read a header slightly differently, fix
a mistyped folder name, or meet a recording whose header time is missing, and
the key changes -- taking the bad channels, the layer labels and the curated
events with it.

So: a global id, minted once on first contact and never recomputed.

    gid   s7f3a91c04b2e     assigned when Jarvis first meets a recording
    key   m007_s002_2023-08-22_15-46-13   derived, and allowed to change
    paths every absolute path it has ever been opened from, on any machine

Everything that belongs to a recording -- bad channels, layer labels, curated
dentate spikes, which storyboards and results mention it -- hangs off the gid.
A machine that has never seen the recording resolves it by the derived key,
finds the gid, and is then talking about the same thing as everyone else.

Projects (KCNT1, PTEN, ...) are guessed from the path on first contact and can
be overridden by hand, because a guess from a folder name is right most of the
time and wrong in exactly the cases that matter.

Nothing here reads recording data. It reads and writes the record of what is
known about recordings.
"""
from __future__ import annotations

import os
import re
import uuid

from . import ids, probes, shards

SCHEMA = 2

# The lab's projects. Not a closed set -- anything already on disk shows up
# alongside these -- but these are what most recordings belong to, so they
# are offered first and spelled consistently.
#
# ORDER IS LOAD-BEARING. `guess_project` returns the FIRST name that matches,
# and a project name that starts with another project's name has to come
# first or it can never win: "KCNT1 Urethane" contains "KCNT1", so with the
# shorter one first every urethane recording would be filed under KCNT1.
#
# That is not a tidiness problem. The urethane work is a separate body of
# work whose mouse and session numbers restart from one, so m13 s3 exists in
# both -- and filing them together would put two different animals under one
# name and make `loose_key` ambiguous across the pair.
KNOWN_PROJECTS = ("KCNT1 Urethane", "KCNT1", "PTEN", "DEWEY")

UNFILED = "Unfiled"

#: Other spellings of a project, for when the folders on disk do not say the
#: name the lab uses. DEWEY's recordings live under "Joe Multisite 2026 data",
#: which says who collected them rather than what they are; renaming the share
#: would break every path already recorded on four machines, so the name is
#: taught here instead. The project name itself is always tried first.
PROJECT_ALIASES = {
    "DEWEY": ("Joe Multisite",),
}


def new_gid():
    """A short, permanent name for a recording.

    Deliberately not derived from anything: a derived id is a id that changes
    when the thing it was derived from is corrected.
    """
    return "s" + uuid.uuid4().hex[:12]


# Whether a folder will open, remembered against its mtime.
#
# `os.path.isdir` is not the question -- a folder can survive its contents,
# and a recording with no CSC .ncs and no converted .mat cannot be opened
# however much else is in it. Asking the loader is authoritative and costs a
# listdir, which over a network share is worth caching: 28ms each, 184 of
# them, and the registry is read on every visit to the Sessions view.
_OPENS = {}


def _opens(path):
    """True when `csc.describe_path` would accept this folder."""
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        _OPENS.pop(path, None)
        return False
    was = _OPENS.get(path)
    if was and was[0] == stamp:
        return was[1]
    try:
        from . import csc
        ok = bool((csc.describe_path(path) or {}).get("ok"))
    except Exception:                                    # noqa: BLE001
        # An unreadable share is not a verdict about the recording. Say no
        # for now and ask again when its mtime changes.
        ok = False
    _OPENS[path] = (stamp, ok)
    return ok


def warm_opens(paths, workers=16):
    """Fill the `_opens` cache for many paths at once.

    `_opens` asks the loader whether a folder will actually open, which
    costs a listdir -- 71 ms a path on this lab's drives, measured. Done one
    after another over 417 reachable paths that is about thirty seconds, and
    it is what made the first read of the registry after a restart feel
    broken.

    None of that time is computation. It is sixteen drives being asked one
    at a time, so this asks them at once. The cache `_opens` already keeps
    does the rest: the second read is thousandths of a second.

    Deliberately best-effort and silent. A share that hangs must slow this
    down, not break it -- the caller is about to fall back to asking each
    path itself anyway, which is exactly what used to happen.
    """
    todo = [p for p in dict.fromkeys(paths or []) if p and p not in _OPENS]
    if len(todo) < 2:
        for p in todo:
            _opens(p)
        return
    try:
        from concurrent.futures import ThreadPoolExecutor
    except ImportError:
        for p in todo:
            _opens(p)
        return
    n = max(2, min(int(workers), len(todo)))
    try:
        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(_opens, todo))
    except Exception:                                    # noqa: BLE001
        # A pool that will not start is not a reason to fail a read.
        for p in todo:
            try:
                _opens(p)
            except Exception:                            # noqa: BLE001
                pass


def _newest_sighting(rec):
    """The most recent time any machine laid eyes on this recording."""
    best = None
    for who, s in ((rec or {}).get("seen") or {}).items():
        if not isinstance(s, dict) or not s.get("at"):
            continue
        if best is None or s["at"] > best["at"]:
            best = dict(s, machine=who)
    # Records written before sightings existed carry the older single field.
    if best is None and isinstance((rec or {}).get("last_seen"), dict):
        best = rec["last_seen"]
    return best


BANK_SIZE = 64


def banks_for(n_channels):
    """A 128-channel recording is two probes, and the registry should say so.

    STRUCTURE ONLY. This says "there are two banks of sixty-four"; it does
    NOT say which is hippocampus and which is cortex, because that is a fact
    about how a particular animal was implanted and this function only knows
    a number. The lab's KCNT1 recordings run 1-64 hippocampus and 65-128
    cortex, and writing that in here would apply it to the twenty
    128-channel recordings currently filed under no project at all, and to
    the one under PTEN, silently and with no way to tell which were guessed.

    So `region` is None until a person says. A blank that is visibly blank
    can be filled in; a guess that looks like a fact cannot be found again.

    One bank is not a bank -- a 64-channel recording gets nothing, because
    "this recording has one probe in it" is not information.
    """
    try:
        n = int(n_channels or 0)
    except (TypeError, ValueError):
        return None
    if n <= BANK_SIZE or n % BANK_SIZE:
        return None
    out = []
    for i in range(n // BANK_SIZE):
        first = i * BANK_SIZE + 1
        out.append({"id": "b%d" % (i + 1), "first": first,
                    "last": first + BANK_SIZE - 1, "region": None})
    return out


def _project_pattern(name):
    """A project name, however the folders happen to spell the gap in it.

    The same body of work is `KCNT1 Urethane` on the cluster and
    `D:\\KCNT1\\urethane\\hom\\...` on this lab's own drive -- a space in one
    place and a path separator in the other. Matching the literal string
    finds one and not the other, which is worse than finding neither: the
    recording is then KCNT1 from one machine and KCNT1 Urethane from
    another, and the cross-project guard in the cluster matcher refuses to
    connect a recording to its own copy.

    So any run of space, underscore, hyphen or slash counts as the gap.
    """
    words = [w for w in re.split(r"[\s_\-/\\]+", name.upper()) if w]
    return r"[\s_\-/\\]+".join(re.escape(w) for w in words)


def guess_project(identity, paths=()):
    """Which project a recording belongs to.

    A project is the body of work -- PTEN, KCNT1 -- not the genotype. So a
    PTEN_DKO folder is PTEN: the DKO part says which cohort within the project
    an animal is in, and that lives in `cohort` beside this rather than
    splitting the project in two.

    The known names are therefore matched as a prefix of the folder name, not
    only as a whole word: PTEN_DKO, PTEN-DKO and PTEN2 are all the PTEN
    project. Anything with no recognisable project keeps whatever grouping the
    folder tree gave it, and failing that is Unfiled for someone to file by
    hand.
    """
    hay = " ".join(
        [str(identity.get("group") or "")]
        + [str(p) for p in (paths or [])]
        + [str(identity.get("path") or "")]
    ).upper()
    for name in KNOWN_PROJECTS:
        # A path segment that STARTS with the project name. Anchored so
        # "PTEN_DKO" counts and an unrelated folder that merely contains the
        # letters somewhere in the middle does not.
        #
        # `name.upper()`, because `hay` is upper-cased and the name is not.
        # That was invisible while every project was spelled in capitals --
        # "KCNT1" matches itself either way -- and the first name with a
        # lower-case letter in it, "KCNT1 Urethane", silently never matched
        # and every urethane recording filed itself under KCNT1.
        #
        # The aliases are tried after the name itself, so a folder that says
        # both still files under the name the lab uses.
        for spelling in (name,) + tuple(PROJECT_ALIASES.get(name, ())):
            if re.search(r"(?<![A-Z0-9])" + _project_pattern(spelling), hay):
                return name
    g = (identity.get("group") or "").strip()
    return g or UNFILED


#: Words that name a project somewhere and something else somewhere else.
#: Each entry is (word, the project it suggests).
AMBIGUOUS_WORDS = (("urethane", "KCNT1 Urethane"),)


def project_flags(rec, paths=()):
    """Paths whose own text disagrees with the project the record is filed under.

    "Urethane" is the case this exists for, and it is worth writing down why
    it is a flag and not a rule.

    The word appears in two different roles in this lab's data. In
    `D:\\KCNT1\\urethane\\wt\\...` it names the project -- a separate body of
    work from KCNT1, with its own mice and its own session numbers that
    happen to collide. In

        Y:\\ProcessedPtenData\\PTEN_CSDsEtc\\CTL\\rejects\\M15_s3_baseline_urethane
        Y:\\ProcessedPtenData\\PTEN_CSDsEtc\\CTL\\rejects\\M15_s8_CNO_urethane

    it names the anaesthetic, and those two recordings are PTEN. A rule that
    reads the word and re-files on it moves them out of the project they
    belong to, and does it silently. `guess_project` gets all three right
    because it reads path *segments*, but it can only be as right as the
    paths it was given, and a path can be wrong.

    So: say what the path says, say what the record says, and let a person
    who can tell the difference look. Setting the project by hand clears the
    flag, because `project_source == "manual"` is already this codebase's
    way of recording that somebody decided.

    Returns [] for the ordinary case, so a caller can test it as a boolean.
    """
    if (rec.get("project_source") or "") == "manual":
        return []
    filed = (rec.get("project") or UNFILED)
    out = []
    for word, suggests in AMBIGUOUS_WORDS:
        if filed == suggests:
            continue                       # already filed the way it reads
        pat = re.compile(r"(?<![A-Z0-9])" + _project_pattern(word))
        for p in (paths if paths else (rec.get("paths") or [])):
            if not isinstance(p, str):
                continue
            if pat.search(p.upper()):
                out.append({"word": word, "path": p,
                            "suggests": suggests, "filed": filed})
    return out


def cohort_of(identity_or_rec):
    """The sub-grouping inside a project, when the folders name one.

    PTEN_DKO within PTEN, say. Kept separate from the project so a cohort is
    something you can see and filter on without it fragmenting the project it
    belongs to.
    """
    group = (identity_or_rec.get("group") or "").strip()
    if not group:
        return None
    project = guess_project(identity_or_rec,
                            identity_or_rec.get("paths") or [])
    if group.upper() == (project or "").upper():
        return None            # the group IS the project; not a cohort
    return group


class Registry:
    """Reads and writes the session records, and keeps their gids straight."""

    def __init__(self, store):
        self.store = store

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    # Every record, rebuilt only when the session files change.
    _all_sig = None
    _all_recs = None

    def all(self):
        """Every session record, merged from its shards.

        Cached against the shard directory's signature. Reading and merging
        515 records is 1.35 s, and one `/api/registry` did it three times --
        once directly, once inside `projects()` and once inside `tree()` --
        which is most of the eight and a half seconds that request took.

        The signature is the safety: it changes the moment any shard is
        written, by this machine or by a pull, so this cannot serve a record
        that has been superseded. `by_gid` below has kept an index the same
        way for the same reason.
        """
        try:
            sig = self.store.sessions.signature()
        except Exception:                                  # noqa: BLE001
            sig = None
        if sig is None:
            # No signature to trust, so no cache. Correctness first: this is
            # the path a store without shard stamps takes.
            return self.store.all_sessions()
        if sig != self._all_sig or self._all_recs is None:
            self._all_recs = self.store.all_sessions()
            self._all_sig = sig
        # Copies, because callers edit what they are handed -- `ensure` and
        # the appliers all do -- and editing this list would be editing the
        # cache. Shallow is enough: the mutations are top-level fields.
        return [dict(r) for r in self._all_recs]

    # gid -> record, rebuilt only when the session files change.
    _gid_sig = None
    _gid_map = None

    def by_gid(self, gid):
        """The session with this gid.

        Indexed rather than scanned: this used to walk -- and re-read from
        disk, and re-merge -- every session in the store on every call, which
        is half a second each and was being done once per curation set every
        time the Event curation list was opened.
        """
        if not gid:
            return None
        try:
            sig = self.store.sessions.signature()
        except Exception:                                  # noqa: BLE001
            sig = None
        if sig is None or sig != self._gid_sig or self._gid_map is None:
            self._gid_map = {r.get("gid"): r
                             for r in self.all() if r.get("gid")}
            self._gid_sig = sig
        rec = self._gid_map.get(gid)
        # A copy, because the index holds these between calls and a caller
        # that edits what it was handed would be editing the cache.
        return dict(rec) if rec else None

    def resolve(self, identity):
        """The record for this identity, and how sure we are.

        Falls back through the same tiers ids.match uses -- exact key, then
        mouse+session, then nearest start time -- because a recording opened
        from a different mount is the same recording.
        """
        return self.store.get_session(identity)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def ensure(self, identity):
        """Make sure this recording has a record and a gid. Returns the record.

        Called on every open. The first time, it mints the gid and guesses the
        project; after that it only adds the path if it is new, so opening the
        same recording from a second drive teaches the registry about that
        drive without disturbing anything else.
        """
        rec, how = self.resolve(identity)
        # Opening a recording is laying eyes on it, the same as a scan finding
        # it -- so it counts as confirmation and the view stops showing it as
        # merely remembered.
        patch = {"seen": self._seen_patch(rec, identity.get("path"))}

        if not rec:
            patch["gid"] = new_gid()
            patch["project"] = guess_project(identity)
            patch["project_source"] = "guessed"
            patch["schema"] = SCHEMA
            patch["first_seen_by"] = "opened"
        else:
            if not rec.get("gid"):
                # An older record from before gids. Give it one now, once.
                patch["gid"] = new_gid()
            if not rec.get("project"):
                patch["project"] = guess_project(identity, rec.get("paths"))
                patch["project_source"] = "guessed"

        # A path seen through a different mount is worth remembering even when
        # nothing else changed: it is how the next machine recognises it.
        out = self.store.upsert_session(identity, patch)
        return out, (how or "new")

    # ------------------------------------------------------------------
    # Sightings
    # ------------------------------------------------------------------
    # Where a recording has been seen, and when, belongs in git with
    # everything else -- the registry travelling between machines is the
    # whole point of it.
    #
    # What must not happen is one shared file that every machine writes to,
    # because then every pull is a conflict. A sighting goes on the
    # recording's own file, which is already one per session, under a key
    # named after the machine that made it. Two people scanning the same
    # drive write two different keys in two different files, so a pull takes
    # both sides instead of fighting over one line.
    def _seen_patch(self, rec, where, scan_id=None, root=None):
        """This machine's sighting, merged with whatever other machines wrote."""
        prov = self.store.provenance() if self.store else {}
        seen = dict((rec or {}).get("seen") or {})
        # Keyed on the machine id, not the label.
        #
        # `provenance().machine` is the name somebody typed into the device
        # field. It changes, and it is not unique: this one computer has
        # sightings filed under "Bluebarry", "DESKTOP-4H65AI7" and
        # "Strawbarrry", so asking "has this machine seen it" matched
        # nothing. The id is the hostname slug plus a hash of the MAC.
        #
        # The label rides along, because a human reading the table wants
        # "Bluebarry" and not "desktop-4h65ai7-d565".
        who = shards.machine_id()
        seen[who] = {"at": prov.get("at"), "by": prov.get("user"),
                     "path": where, "root": root, "scan": scan_id,
                     "machine": prov.get("machine")}
        return seen

    def seen_by(self, rec, names):
        """Has any of `names` seen this recording?

        `names` is every spelling one computer answers to -- its id, its
        current label, its real hostname, and the older labels it used. All
        of them, because the sightings already on record are keyed on
        whatever the label was at the time and those years are not being
        rewritten: guessing which old label belonged to which computer is
        how two people's machines were merged once already.
        """
        want = {str(n).strip().lower() for n in (names or []) if n}
        if not want:
            return False
        for key, got in ((rec or {}).get("seen") or {}).items():
            if str(key).strip().lower() in want:
                return True
            # A newer sighting is keyed on the id and carries the label.
            label = (got or {}).get("machine") if isinstance(got, dict) else None
            if label and str(label).strip().lower() in want:
                return True
        return False

    def _durable_patch(self, rec, ident, facts, first_seen_by="scan"):
        """Only what is worth a tracked write, or None for "nothing changed".

        A scan that finds nothing new should touch no files at all. Without
        this, every scan restamps `updated` on all two hundred records it
        walked past, and the next pull is a wall of conflicts over nothing.
        """
        patch = {}
        if not rec:
            patch["gid"] = new_gid()
            patch["project"] = guess_project(ident, [ident.get("path")])
            patch["project_source"] = "guessed"
            patch["schema"] = SCHEMA
            patch["first_seen_by"] = first_seen_by
        else:
            if not rec.get("gid"):
                patch["gid"] = new_gid()
            if not rec.get("project"):
                patch["project"] = guess_project(ident, rec.get("paths"))
                patch["project_source"] = "guessed"

        for key, value in (facts or {}).items():
            if value is None:
                continue
            if rec is not None and rec.get(key) == value:
                continue
            patch[key] = value

        # A path this record has not been seen at is worth writing down;
        # upsert_session is what actually appends it.
        path = ident.get("path")
        new_path = bool(path) and path not in ((rec or {}).get("paths") or [])
        if not patch and not new_path:
            return None
        return patch

    def ingest(self, found, scan_id=None, root=None):
        """Register everything a scan walked past, whether or not anyone opens it.

        A recording Jarvis has *seen* and one somebody has *worked on* are
        different facts, and only the second used to get written down -- so
        the registry knew about six recordings when the drive held two
        hundred, and there was no way to sort or explore the rest.

        A scan is the moment Jarvis has the whole picture of a drive, so it is
        the right moment to write it all down. Nothing here opens a file or
        reads a sample; it records that the recording exists, where, and when
        it was last laid eyes on.

        Returns (new, seen) -- how many were met for the first time, and how
        many were confirmed.
        """
        new = 0
        seen = 0
        for s in (found or []):
            ident = s.get("identity") or {}
            if not ident.get("path"):
                ident = dict(ident, path=s.get("path"))
            if not ident.get("path"):
                continue

            rec, _how = self.resolve(ident)
            # Cheap facts a scan can see without opening anything.
            facts = {
                "n_channels": s.get("channels") or None,
                "fs": s.get("fs") or None,
                "duration_s": s.get("duration_s") or None,
                "has_video": True if s.get("has_video") else None,
                "converted": True if s.get("converted") else None,
                # How many probes went in, which a scan CAN see -- it is the
                # channel count over sixty-four. Which one is hippocampus and
                # which is cortex it cannot see, and does not claim to: see
                # `banks_for`.
                #
                # Written ONCE, and never by a later scan. `_durable_patch`
                # writes any fact that differs from what is stored, and a
                # freshly computed bank list has every `region` back at None
                # -- so a second scan of the same drive would quietly erase
                # every anatomy somebody had filled in. The structure does
                # not change; the labels on it are decisions.
                "channel_banks": (None if (rec or {}).get("channel_banks")
                                  else banks_for(s.get("channels"))),
            }
            patch = self._durable_patch(rec, ident, facts) or {}
            if not rec:
                new += 1

            # The sighting is always refreshed -- it is what a scan is for --
            # but only this machine's key changes, in this recording's own
            # file.
            patch["seen"] = self._seen_patch(rec, ident["path"], scan_id, root)
            self.store.upsert_session(ident, patch)
            seen += 1
        return new, seen

    def backfill(self):
        """Give every record already on disk a gid and a project.

        Records written before the registry existed have neither. Without
        this they would only acquire them the next time someone happened to
        open that recording, which means the housekeeping view would start
        out mostly blank and fill in at random over weeks. Runs once, is
        cheap, and is idempotent.
        """
        done = 0
        for rec in self.all():
            patch = {}
            if not rec.get("gid"):
                patch["gid"] = new_gid()
            if not rec.get("project"):
                patch["project"] = guess_project(rec, rec.get("paths"))
                patch["project_source"] = "guessed"
            if not patch:
                continue
            patch["schema"] = SCHEMA
            self._patch(rec, patch)
            done += 1
        return done

    def set_project(self, gid, project, source="manual"):
        """Move a recording into a project, by hand.

        Marked as a manual choice so a later guess cannot quietly overrule
        it -- and so `project_flags` stops asking about it, because somebody
        has answered.

        `source` exists so a caller can put a record back exactly as it
        found one. `web/_dev/housekeeping.html` drives this picker and then
        restores the old value, which left the record reading "set by hand"
        for ever after, with nobody having set it by hand. That is not a
        cosmetic difference: a manual project is immune to `refile_projects`
        and raises no filing flag, so a harness run was quietly immunising a
        real recording against both. Only a restore should pass anything
        other than the default.
        """
        rec = self.by_gid(gid)
        if not rec:
            raise KeyError(gid)
        return self._patch(rec, {
            "project": (project or "").strip() or UNFILED,
            "project_source": source if source in ("manual", "guessed")
                              else "manual",
        })

    def set_label(self, gid, label):
        rec = self.by_gid(gid)
        if not rec:
            raise KeyError(gid)
        return self._patch(rec, {"label": (label or "").strip()
                                 or rec.get("label")})

    def set_note(self, gid, note):
        rec = self.by_gid(gid)
        if not rec:
            raise KeyError(gid)
        return self._patch(rec, {"note": note or ""})

    def add_path(self, gid, path):
        """Teach the registry that a recording also lives here.

        The edge case this exists for: a recording whose folder was renamed,
        so the derived key no longer matches and Jarvis would otherwise mint a
        second record for it.
        """
        rec = self.by_gid(gid)
        if not rec:
            raise KeyError(gid)
        p = str(path)
        # `abspath` only when the path is not already absolute.
        #
        # A POSIX path IS absolute, and on Windows `abspath` does not know
        # that: `/gpfs2/scratch/sakhava1/m22s3` comes back as
        # `C:\gpfs2\scratch\sakhava1\m22s3`, which is not anywhere. That
        # would be written into the shared registry and synced to everybody,
        # and nothing downstream would question it -- a path that does not
        # resolve is the ordinary state of a path belonging to another
        # machine.
        if not p.startswith("/"):
            p = os.path.abspath(p)
        paths = list(rec.get("paths") or [])
        if p not in paths:
            paths.append(p)
        return self._patch(rec, {"paths": paths})

    def forget_path(self, gid, path):
        rec = self.by_gid(gid)
        if not rec:
            raise KeyError(gid)
        paths = [p for p in (rec.get("paths") or []) if p != path]
        return self._patch(rec, {"paths": paths})

    def merge(self, keep_gid, drop_gid):
        """Two records that turned out to be one recording.

        Happens when the same recording was first met through two mounts whose
        folder names disagreed enough that the derived keys differed. The
        surviving record absorbs the other's paths, bad channels and notes;
        the absorbed one is left behind as a tombstone pointing at the
        survivor, so anything still referring to the old gid can follow it.
        """
        keep = self.by_gid(keep_gid)
        drop = self.by_gid(drop_gid)
        if not keep or not drop:
            raise KeyError(keep_gid if not keep else drop_gid)
        if keep_gid == drop_gid:
            raise ValueError("A record cannot be merged into itself.")

        paths = list(keep.get("paths") or [])
        for p in (drop.get("paths") or []):
            if p not in paths:
                paths.append(p)

        bad = sorted(set(keep.get("bad_channels") or [])
                     | set(drop.get("bad_channels") or []))

        notes = [n for n in (keep.get("note"), drop.get("note")) if n]
        merged = self._patch(keep, {
            "paths": paths,
            "bad_channels": bad,
            "note": "\n".join(notes) or "",
            "merged_in": sorted(set(keep.get("merged_in") or [])
                                | {drop_gid}
                                | set(drop.get("merged_in") or [])),
        })
        # The tombstone keeps its file so nothing 404s, but stops being a
        # session in its own right.
        self._patch(drop, {"merged_into": keep_gid, "retired": True})
        return merged

    def split(self, gid, path):
        """One record that turned out to be two recordings.

        The named path leaves and becomes its own record, re-identified from
        scratch. The opposite mistake to merge, and just as necessary: a loose
        match on mouse+session will happily fold two different days together
        when neither has a header time.
        """
        rec = self.by_gid(gid)
        if not rec:
            raise KeyError(gid)
        if path not in (rec.get("paths") or []):
            raise ValueError("That path is not on this record.")
        if len(rec.get("paths") or []) < 2:
            raise ValueError(
                "This record only knows one path, so there is nothing to "
                "split off.")

        fresh = ids.identify(path)

        # If the path re-identifies as the same recording, it IS the same
        # recording -- the same folder reached through a different mount --
        # and there is nothing to split. Refusing matters: the key would be
        # identical, so the "new" record would match the old one and
        # upsert_session would overwrite it, taking its permanent id with it.
        # That is not a hypothetical; it happened, and every attachment
        # hanging off that id would have come loose.
        if fresh.get("key") and fresh.get("key") == rec.get("key"):
            raise ValueError(
                "That path is the same recording as the rest of this record "
                "-- same mouse, same session, same start time, just a "
                "different mount. There is nothing to split off. Use "
                "'forget this path' if the mount is wrong.")

        self._patch(rec, {"paths": [p for p in rec["paths"] if p != path]})
        # A brand-new record, deliberately: it must not match its way back
        # into the one it just left, so the key is made distinct even when
        # the derived one would collide.
        forced = dict(fresh)
        forced["key"] = (fresh.get("key")
                         or "split_" + uuid.uuid4().hex[:8])
        if forced["key"] == rec.get("key"):
            forced["key"] = forced["key"] + "__split_" + uuid.uuid4().hex[:6]
        made = self.store.upsert_session(forced, {
            "gid": new_gid(),
            "project": rec.get("project") or guess_project(fresh, [path]),
            "project_source": "inherited",
            "split_from": gid,
            "schema": SCHEMA,
        })
        return made

    def _patch(self, rec, patch):
        # The gid goes in the identity, and it matters most for the records
        # that have nothing else.
        #
        # `get_session` looks the gid up first, so for an ordinary record
        # this changes nothing -- it finds the same row it found by key. For
        # a record with no key, no loose_key and no mouse, leaving the gid
        # out meant there was nothing at all to match on, so `upsert_session`
        # took the patch to be a NEW recording and minted another gid for
        # it. Retiring such a record created a fresh one instead of retiring
        # anything, which is the shape of a bug that quietly doubles a
        # registry: it was how twelve ids came to exist for two recordings.
        ident = {k: rec.get(k) for k in
                 ("gid", "key", "loose_key", "mouse", "session", "start",
                  "label")}
        return self.store.upsert_session(ident, patch)

    # ------------------------------------------------------------------
    # The view
    # ------------------------------------------------------------------
    def projects(self):
        """Every project name in play, the known ones first."""
        seen = []
        for rec in self.all():
            p = rec.get("project") or UNFILED
            if p not in seen:
                seen.append(p)
        ordered = [p for p in KNOWN_PROJECTS if p in seen]
        ordered += sorted(p for p in seen
                          if p not in KNOWN_PROJECTS and p != UNFILED)
        if UNFILED in seen:
            ordered.append(UNFILED)
        return ordered

    def tree(self, attachments=None):
        """project -> mouse -> sessions, with what is attached to each.

        `attachments` is a callable given a record and returning a dict of
        counts, so this module does not have to know what a storyboard is.
        """
        live = [r for r in self.all() if not r.get("retired")]

        # Ask every drive at once, before asking any record about itself.
        #
        # `summary` calls `_opens` per reachable path, and `_opens` is a
        # listdir: 71 ms each on this lab's drives, measured, over 417
        # reachable paths -- about thirty seconds of the first read after a
        # restart, spent entirely waiting. Warming them in parallel first
        # turns that into roughly the slowest single drive, and every
        # `summary` below then hits a cache that costs nothing.
        #
        # The order matters and is the whole trick: inside the loop the
        # calls are serial by construction, however many threads exist.
        warm_opens([p for r in live for p in (r.get("paths") or [])])

        out = {}
        for rec in live:
            proj = rec.get("project") or UNFILED
            mouse = rec.get("mouse")
            # `r` for a rat, `m` for a mouse. The tree is where the
            # animal is actually named, so this is the one place it is
            # worth getting right -- DEWEY's are rats and "m9" read wrong
            # in the only view that says the animal out loud.
            mkey = ("%s%03d" % (ids.subject_prefix(proj), mouse)
                    if isinstance(mouse, int) else "unknown")
            node = out.setdefault(proj, {})
            node.setdefault(mkey, []).append(self.summary(rec, attachments))

        def snum(s):
            v = s.get("session")
            return (v is None, v if isinstance(v, int) else 0,
                    s.get("date") or "")

        tree = []
        for proj in self.projects():
            if proj not in out:
                continue
            mice = []
            for mkey in sorted(out[proj],
                               key=lambda k: (k == "unknown",
                                              int(k[1:]) if k[1:].isdigit()
                                              else 0)):
                rows = sorted(out[proj][mkey], key=snum)
                mice.append({"mouse": mkey, "n": len(rows), "sessions": rows})
            tree.append({
                "project": proj,
                "n_mice": len(mice),
                "n_sessions": sum(m["n"] for m in mice),
                "mice": mice,
            })
        return tree

    def summary(self, rec, attachments=None):
        """One row of the housekeeping view."""
        paths = list(rec.get("paths") or [])
        # Computed once, and reused for the loadability check below: the
        # folders that do not exist must not be touched again. Reaching for
        # an unmounted network path costs a timeout, and checking all 471
        # rather than the 184 that answer took this read from 5s to 25s.
        here = [p for p in paths if os.path.isdir(p)]
        row = {
            "gid": rec.get("gid"),
            "key": rec.get("key"),
            "loose_key": rec.get("loose_key"),
            "label": rec.get("label"),
            "project": rec.get("project") or UNFILED,
            "project_source": rec.get("project_source") or "guessed",
            # Paths whose own text names a different project than the one
            # this is filed under. A flag for a person, never a re-file --
            # `project_flags` records why.
            "project_flags": project_flags(rec, paths),
            # The sub-grouping the folders name, when it is not just the
            # project again -- PTEN_DKO inside PTEN. Visible and filterable
            # without splitting the project it belongs to.
            "cohort": rec.get("cohort") or cohort_of(rec),
            "mouse": rec.get("mouse"),
            "session": rec.get("session"),
            # DEWEY only, and null everywhere else. The session number there
            # is a band -- Precon 1-4 are s1-s4, Con 1-6 are s11-s16, Test
            # 1-2 are s21-s22 -- which nobody says out loud, so the phase it
            # stands for travels beside it. `run` is which of the three
            # recordings in that session this is: FP1, FP2 or SPC.
            "phase": rec.get("phase"),
            "phase_n": rec.get("phase_n"),
            "run": rec.get("run"),
            "repeat": rec.get("repeat"),
            "date": (rec.get("start") or "")[:10] or None,
            "start": rec.get("start"),
            "note": rec.get("note") or "",
            "paths": paths,
            "n_paths": len(paths),
            # Which of those paths this machine can actually reach. The point
            # of listing them all is to see, at a glance, that a recording is
            # known but not mounted here.
            "here": here,
            # Which of them will actually open, which is not the same
            # question: a folder can outlive its contents. Asked of the
            # loader itself rather than guessed at, and only of the folders
            # that already answered `isdir` -- touching an unmounted network
            # path costs a timeout, and asking all 471 instead of the 184
            # that exist took the registry read from 5s to 25s.
            "loadable": [p for p in here if _opens(p)],
            "bad_channels": rec.get("bad_channels") or [],
            "merged_in": rec.get("merged_in") or [],
            "split_from": rec.get("split_from"),
            "created": rec.get("created") or {},
            "updated": rec.get("updated") or {},
            # Every machine's sighting, and the most recent of them.
            "seen": rec.get("seen") or {},
            "last_seen": _newest_sighting(rec),
            "first_seen_by": rec.get("first_seen_by") or "opened",
            # Cheap facts a scan can fill in without anyone opening anything.
            # From the Toothy workbook: base vs cno. A fact about the
            # recording, so it belongs on the recording rather than the mouse.
            "condition": rec.get("condition"),
            # Which hippocampus. From the lab's feeder sheet, where it lived
            # in a `side` column and was therefore true only for whoever had
            # the spreadsheet open -- and a left and a right CA1 recording
            # are not the same recording.
            "hemisphere": rec.get("hemisphere"),
            "hemisphere_source": rec.get("hemisphere_source"),
            # The landmarks a CSD is read against, and what the extraction
            # made of them. On the row rather than behind a click: "no CA1
            # SP channel" changes how the recording should be read.
            "ripple_channel": rec.get("ripple_channel"),
            "fissure_channel": rec.get("fissure_channel"),
            "hilus_channel": rec.get("hilus_channel"),
            "extraction_note": rec.get("extraction_note"),
            "needs_processing": rec.get("needs_processing"),
            "n_channels": rec.get("n_channels"),
            # Which probe went into the animal. A fact about the recording,
            # not about whoever has it open -- it used to live in the
            # Xplorefinder session's view state, so it lasted as long as the
            # window did and travelled to nobody. `probes.suggest` fills the
            # gap with a guess the row carries separately, so "nobody has
            # said" and "somebody said H3" stay different answers.
            "probe": rec.get("probe"),
            "probe_source": rec.get("probe_source"),
            "probe_suggested": probes.suggest(rec.get("n_channels")),
            # Three states, decided in one place: confirmed by a person,
            # detected from the channel count and not yet agreed, or
            # unknown. Every surface that draws a chip reads this rather
            # than working it out again from `probe` and `n_channels`,
            # because two copies of that rule would disagree.
            "probe_state": probes.state_of(rec),
            "fs": rec.get("fs"),
            "duration_s": rec.get("duration_s"),
            "has_video": bool(rec.get("has_video")),
            "converted": bool(rec.get("converted")),
        }
        row["reachable"] = bool(row["here"])
        # "Can I click this right now." The filter that says "on this
        # machine" means this one, not `reachable`.
        row["can_open"] = bool(row["loadable"])
        if attachments:
            row["has"] = attachments(rec) or {}
        return row
