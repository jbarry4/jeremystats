"""
sessreg.py -- The session registry: one record per recording, everywhere.

BARRY already kept a file per session under GUI_logs/sessions/, keyed by
mouse + session + header start time. That key is good at recognising the same
recording across machines, and it is exactly the wrong thing to hang years of
work off, because it is *derived*. Re-read a header slightly differently, fix
a mistyped folder name, or meet a recording whose header time is missing, and
the key changes -- taking the bad channels, the layer labels and the curated
events with it.

So: a global id, minted once on first contact and never recomputed.

    gid   s7f3a91c04b2e     assigned when BARRY first meets a recording
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

from . import ids

SCHEMA = 2

# The lab's projects. Not a closed set -- anything already on disk shows up
# alongside these -- but these two are what most recordings belong to, so they
# are offered first and spelled consistently.
KNOWN_PROJECTS = ("KCNT1", "PTEN")

UNFILED = "Unfiled"


def new_gid():
    """A short, permanent name for a recording.

    Deliberately not derived from anything: a derived id is a id that changes
    when the thing it was derived from is corrected.
    """
    return "s" + uuid.uuid4().hex[:12]


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
        if re.search(r"(?<![A-Z0-9])" + re.escape(name), hay):
            return name
    g = (identity.get("group") or "").strip()
    return g or UNFILED


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
    def all(self):
        return self.store.all_sessions()

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
        who = prov.get("machine") or "unknown"
        seen = dict((rec or {}).get("seen") or {})
        seen[who] = {"at": prov.get("at"), "by": prov.get("user"),
                     "path": where, "root": root, "scan": scan_id}
        return seen

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

        A recording BARRY has *seen* and one somebody has *worked on* are
        different facts, and only the second used to get written down -- so
        the registry knew about six recordings when the drive held two
        hundred, and there was no way to sort or explore the rest.

        A scan is the moment BARRY has the whole picture of a drive, so it is
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

    def set_project(self, gid, project):
        """Move a recording into a project, by hand.

        Marked as a manual choice so a later guess cannot quietly overrule it.
        """
        rec = self.by_gid(gid)
        if not rec:
            raise KeyError(gid)
        return self._patch(rec, {
            "project": (project or "").strip() or UNFILED,
            "project_source": "manual",
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
        so the derived key no longer matches and BARRY would otherwise mint a
        second record for it.
        """
        rec = self.by_gid(gid)
        if not rec:
            raise KeyError(gid)
        p = os.path.abspath(str(path))
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
        ident = {k: rec.get(k) for k in
                 ("key", "loose_key", "mouse", "session", "start", "label")}
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
        out = {}
        for rec in self.all():
            if rec.get("retired"):
                continue
            proj = rec.get("project") or UNFILED
            mouse = rec.get("mouse")
            mkey = "m%03d" % mouse if isinstance(mouse, int) else "unknown"
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
        row = {
            "gid": rec.get("gid"),
            "key": rec.get("key"),
            "loose_key": rec.get("loose_key"),
            "label": rec.get("label"),
            "project": rec.get("project") or UNFILED,
            "project_source": rec.get("project_source") or "guessed",
            # The sub-grouping the folders name, when it is not just the
            # project again -- PTEN_DKO inside PTEN. Visible and filterable
            # without splitting the project it belongs to.
            "cohort": rec.get("cohort") or cohort_of(rec),
            "mouse": rec.get("mouse"),
            "session": rec.get("session"),
            "date": (rec.get("start") or "")[:10] or None,
            "start": rec.get("start"),
            "note": rec.get("note") or "",
            "paths": paths,
            "n_paths": len(paths),
            # Which of those paths this machine can actually reach. The point
            # of listing them all is to see, at a glance, that a recording is
            # known but not mounted here.
            "here": [p for p in paths if os.path.isdir(p)],
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
            "n_channels": rec.get("n_channels"),
            "fs": rec.get("fs"),
            "duration_s": rec.get("duration_s"),
            "has_video": bool(rec.get("has_video")),
            "converted": bool(rec.get("converted")),
        }
        row["reachable"] = bool(row["here"])
        if attachments:
            row["has"] = attachments(rec) or {}
        return row
