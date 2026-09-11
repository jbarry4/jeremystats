# -*- coding: utf-8 -*-
"""Who is curating what, at this moment.

Everything else Jarvis stores is a record of something that happened, and is
still true tomorrow. This is the opposite: a claim that somebody is at their
keyboard right now, which stops being true the moment a lid closes and sends
nothing to say so. Two consequences shape the whole module.

The first is that it lives only in Supabase. There is no local shard and
nothing in GUI_logs, because a presence row that survives a restart is a lie
-- and a file that says "Rain is curating m33 s8" three days after she
stopped is worse than no file. If the cloud is unreachable the answer is
"nobody is reported present", which is exactly the truth available.

The second is that it expires rather than unlocks. A lock somebody has to
give back is a lock that strands the set when a machine crashes, and the one
thing worse than two people in a set is nobody able to get into it. So a
session is present while it keeps saying so, and a set is held while somebody
is present in it.

The holding is deliberately advisory. The ask was to stop two people curating
the same file *accidentally*, and an accident is prevented by being told; a
hard block would also stop the deliberate case, which is legitimate and
common -- somebody left a set open on a rig and went home.
"""
import datetime
import time

from . import cloud as cloudmod
from . import shards

TABLE = "curation_presence"

# How long a session stays "present" after its last heartbeat. Comfortably
# more than the client's beat (see PRESENCE_BEAT in curate.js) so one dropped
# request does not make somebody vanish mid-sentence, and short enough that a
# closed laptop stops holding a set within a coffee break.
TTL_S = 150

# Anything older than this is not worth reading or keeping.
STALE_S = 24 * 3600


def _now():
    return cloudmod.now()


def _parse(stamp):
    """An ISO timestamp as an aware datetime, or None.

    Postgres hands back `+00:00` and sometimes `Z`, and microseconds are
    optional; `fromisoformat` refuses `Z` before 3.11, and this has to run on
    whatever Python a rig happens to have.
    """
    if not stamp:
        return None
    text = str(stamp).strip().replace("Z", "+00:00")
    try:
        got = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if got.tzinfo is None:
        got = got.replace(tzinfo=datetime.timezone.utc)
    return got


def _age_s(stamp):
    """Seconds since `stamp`, or None if it cannot be read.

    Clocks differ between machines -- one of them being ahead is what broke
    syncing for a week -- so this is only ever used for "roughly how long",
    never for deciding who wins. A row from a machine running a few seconds
    fast reads as a negative age, which is clamped to zero rather than
    treated as ancient.
    """
    got = _parse(stamp)
    if got is None:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    return max(0.0, (now - got).total_seconds())


def _iso_ago(seconds):
    """An ISO stamp `seconds` in the past, for a `lt.` filter."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - datetime.timedelta(seconds=seconds)).isoformat()


class Presence(object):
    """Reads and writes the presence table. Never raises for a caller.

    Every method returns something usable when the cloud is unavailable,
    because presence is a courtesy: nothing about curation should stop
    working because the network did.
    """

    def __init__(self, cloud, store=None):
        self.cloud = cloud
        self.store = store
        self._last_sweep = 0.0

    # -- identity ---------------------------------------------------------
    def machine(self):
        return shards.machine_id()

    def _person(self):
        """The name this machine credits work to, or None.

        The same name `curation_events.decided_by` carries, so the feed can
        say "Rain" rather than a machine id -- and so a colleague reading it
        recognises the person they would go and talk to.
        """
        try:
            if self.store is not None and self.store.profile is not None:
                eff = self.store.profile.effective() or {}
                # `user` is what the profile calls it, and it is the string
                # every decision is stamped with -- so the feed says the same
                # name the data does. `name` as a fallback in case that ever
                # changes; a feed that says "None is curating" is useless.
                for key in ("user", "name"):
                    got = (eff.get(key) or "").strip()
                    if got:
                        return got
        except Exception:                                # noqa: BLE001
            pass
        return None

    def _device(self):
        try:
            if self.store is not None and self.store.profile is not None:
                eff = self.store.profile.effective() or {}
                got = (eff.get("machine") or eff.get("device") or "").strip()
                if got:
                    return got
        except Exception:                                # noqa: BLE001
            pass
        return self.machine()

    # -- writing ----------------------------------------------------------
    def beat(self, gid, kind, **what):
        """Say that this machine is in this set, and how far it has got.

        An upsert on (gid, kind, machine): a heartbeat is not history, so
        there is one row per session and it is overwritten, not appended.
        `started_at` is left alone once set -- it is how long they have been
        at it, and re-stamping it on every beat would make every session look
        like it just began.
        """
        if not self.cloud or not self.cloud.configured or not gid:
            return None
        row = {
            "gid": gid, "kind": kind or "ds",
            "machine": self.machine(),
            "person": self._person(),
            "device": self._device(),
            "last_seen": _now(),
        }
        for key in ("n_total", "n_decided", "n_this_visit", "at_index",
                    "at_time_s", "doing"):
            if key in what and what[key] is not None:
                row[key] = what[key]
        if what.get("first"):
            row["started_at"] = _now()
            # A fresh pick-up clears any note that it was taken from us.
            row["yielded_to"] = None
            row["yielded_at"] = None
        try:
            self.cloud.upsert(TABLE, [row], on_conflict="gid,kind,machine")
            return row
        except Exception:                                # noqa: BLE001
            # A heartbeat that does not arrive is not an error worth showing
            # anybody: the reader's own TTL will notice soon enough.
            return None

    def release(self, gid, kind):
        """Leave a set. Best effort -- the TTL is what actually guarantees it.

        Worth doing anyway: closing a set properly should free it now rather
        than in two and a half minutes, and somebody waiting to pick it up is
        usually standing right there.
        """
        if not self.cloud or not self.cloud.configured or not gid:
            return False
        try:
            self.cloud.delete(TABLE, "gid=eq.%s&kind=eq.%s&machine=eq.%s"
                              % (gid, kind or "ds", self.machine()))
            return True
        except Exception:                                # noqa: BLE001
            return False

    def take(self, gid, kind, from_machine):
        """Take a set another session is in, and tell that session so.

        The row is marked rather than deleted, so the machine that had it can
        find out on its next beat and say so on screen -- instead of carrying
        on writing decisions into a set it no longer holds, which is the
        silent version of the very collision this exists to prevent.
        """
        if not self.cloud or not self.cloud.configured:
            return False
        who = self._person() or self.machine()
        try:
            self.cloud.patch_rows(
                TABLE,
                "gid=eq.%s&kind=eq.%s&machine=eq.%s"
                % (gid, kind or "ds", from_machine),
                {"yielded_to": who, "yielded_at": _now()})
            return True
        except Exception:                                # noqa: BLE001
            return False

    # -- reading ----------------------------------------------------------
    def all(self, include_self=True):
        """Every session seen recently, newest first.

        Returned with `active` and `age_s` worked out here rather than in the
        browser, so the workbench and the curation bar cannot disagree about
        who counts as present.
        """
        if not self.cloud or not self.cloud.configured:
            return []
        try:
            rows = self.cloud.select(TABLE, limit=500) or []
        except Exception:                                # noqa: BLE001
            return []

        mine = self.machine()
        out = []
        for r in rows:
            age = _age_s(r.get("last_seen"))
            if age is not None and age > STALE_S:
                continue
            if not include_self and r.get("machine") == mine:
                continue
            out.append(dict(
                r,
                age_s=age,
                # Unknown age counts as present: a row we cannot date was
                # written by somebody, and guessing "gone" would hand out a
                # set that may well be in use.
                active=(age is None or age <= TTL_S),
                is_me=(r.get("machine") == mine),
            ))
        out.sort(key=lambda x: (x.get("age_s") is None, x.get("age_s") or 0))
        return out

    def for_set(self, gid, kind, include_self=True):
        return [r for r in self.all(include_self=include_self)
                if r.get("gid") == gid and (r.get("kind") or "ds") == (kind or "ds")]

    def holder(self, gid, kind):
        """Whoever else is actively in this set, or None.

        Never this machine: a second window on one computer is the same
        person, and warning somebody that they already have a set open is
        noise rather than protection.
        """
        for r in self.for_set(gid, kind, include_self=False):
            if r.get("active"):
                return r
        return None

    def taken_from_me(self, gid, kind):
        """Has somebody taken this set off this machine?"""
        for r in self.for_set(gid, kind):
            if r.get("is_me") and r.get("yielded_to"):
                return {"by": r.get("yielded_to"), "at": r.get("yielded_at")}
        return None

    def sweep(self, every_s=3600):
        """Drop rows nobody could still be behind. Rate-limited, best effort.

        The readers all filter on age anyway, so this is tidiness rather than
        correctness -- which is why it is allowed to fail quietly and why it
        does not run on every call.
        """
        if not self.cloud or not self.cloud.configured:
            return 0
        now = time.time()
        if now - self._last_sweep < every_s:
            return 0
        self._last_sweep = now
        try:
            cutoff = _iso_ago(STALE_S)
            self.cloud.delete(TABLE, "last_seen=lt.%s" % cutoff)
            return 1
        except Exception:                                # noqa: BLE001
            return 0
