"""
healthlog.py -- when was this recording checked, by whom, and what did it say?

A continuity check is cheap and its answer is durable: it only changes when
the files do. Running one and throwing the answer away means nobody can ask
the question that actually matters at the scale of an archive -- *which* of
these three hundred recordings have gaps, who established that, and has
anything been done about it.

So every check is kept, with its time, its author, its machine, and the
segmentation hash it produced. That gives three things nothing else could:

  * a filter. "Show me the recordings with a concat issue" is a question
    about the whole archive, and it cannot be answered by a check that runs
    when you open one session.

  * provenance. A gap map is what a re-timing is stamped with, so "this set
    was corrected against map 724351c3..." is only meaningful next to "that
    map was produced here, on this date, by this person, from these files".

  * a way to tell corrected from uncorrected. Whether a banked set has been
    re-timed lives on the entry's `time_basis`; whether it NEEDS to be lives
    here. Neither is much use without the other.

Sharded per machine like everything else that gets written, and the checks
list merges BYID -- so two people checking the same recording on two machines
produces one history containing both, rather than one overwriting the other.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from . import retime, shards

# The history unions across machines rather than the newest file winning.
# Two people checking the same recording is two facts, not a conflict.
HEALTH_SPEC = {"checks": shards.BYID}

# How many checks to keep per recording. The answer only changes when the
# files do, so the history is short in practice; this is a guard against a
# script in a loop, not a real limit.
MAX_CHECKS = 200


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class HealthLog:
    def __init__(self, logs_dir, store=None):
        self.dir = os.path.join(logs_dir, "health")
        self.book = shards.Book(self.dir, HEALTH_SPEC, store)
        self.store = store

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def record(self, gid, path, report, label=None, deep=False, level=None):
        """File one continuity check against a session.

        Returns the check that was written, or None when there is nothing
        worth filing -- no gid to file it against, or no readable report.
        A check that cannot say which recording it is about is not a record
        of anything.
        """
        if not gid or not report or not report.get("ok"):
            return None

        prov = self.store.provenance() if self.store else {}
        check = {
            "id": uuid.uuid4().hex[:12],
            "at": _now(),
            "by": prov.get("user") or "unknown",
            "machine": prov.get("machine") or "unknown",
            "level": level or ("warn" if (report.get("n_segments") or 1) > 1
                               else "ok"),
            "n_segments": int(report.get("n_segments") or 1),
            "n_gaps": len(report.get("gaps") or []),
            "seconds_lost": float(report.get("seconds_lost") or 0.0),
            "max_time_error_ms": float(report.get("max_time_error_ms") or 0.0),
            "sub_threshold_lost_s": float(
                report.get("sub_threshold_lost_s") or 0.0),
            "true_duration_s": float(report.get("true_duration_s") or 0.0),
            "concat_duration_s": float(report.get("concat_duration_s") or 0.0),
            # The identity of the answer. A re-timing is stamped with this,
            # so the two records can be put side by side later.
            "gap_map_sha": report.get("gap_map_sha"),
            "gap_rule": report.get("gap_rule"),
            "n_ncs": report.get("n_ncs"),
            "n_probed": len(report.get("probed") or []),
            "all_channels": bool(deep),
            "mismatches": len(report.get("mismatches") or []),
        }

        rec = self.book.read(gid) or {}
        rec["gid"] = gid
        if path:
            rec["path"] = path
        if label:
            rec["label"] = label
        checks = list(rec.get("checks") or [])

        # A repeat of an answer already on record is not a new fact. Same
        # map, same machine, same verdict -- the stamp moves and the history
        # does not grow, because a scan re-run nightly would otherwise bury
        # the one check somebody actually made.
        same = None
        for old in checks:
            if (old.get("gap_map_sha") == check["gap_map_sha"]
                    and old.get("machine") == check["machine"]
                    and old.get("all_channels") == check["all_channels"]):
                same = old
                break
        if same is not None:
            same["at"] = check["at"]
            same["by"] = check["by"]
            same["seen"] = int(same.get("seen") or 1) + 1
            check = same
        else:
            checks.append(check)
        checks.sort(key=lambda c: str(c.get("at") or ""))
        rec["checks"] = checks[-MAX_CHECKS:]
        self.book.write(gid, rec)
        return check

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def get(self, gid):
        return self.book.read(gid) if gid else None

    def all(self):
        out = []
        for base in self.book.bases():
            rec = self.book.read(base)
            if rec:
                out.append(rec)
        return out

    @staticmethod
    def latest(rec):
        """The most recent check on a record, on the moment not the string.

        The machines in these logs do not share a clock and write their own
        offsets, so sorting the text is meaningless -- the same mistake this
        codebase has made in eleven other places.
        """
        checks = (rec or {}).get("checks") or []
        if not checks:
            return None
        def when(c):
            try:
                return datetime.fromisoformat(
                    str(c.get("at") or "").replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return datetime.min.replace(tzinfo=timezone.utc)
        return max(checks, key=when)

    def summary(self, bank=None):
        """One row per recording anybody has checked, for the session list.

        `bank`, if given, adds what is banked against each session and
        whether it has been re-timed -- which is the difference between
        "this recording has a problem" and "this recording has a problem
        nobody has dealt with".
        """
        by_gid = {}
        if bank is not None:
            for entry in bank.all():
                gid = entry.get("gid")
                if not gid:
                    continue
                by_gid.setdefault(gid, []).append(entry)

        out = {}
        for rec in self.all():
            gid = rec.get("gid")
            last = self.latest(rec)
            if not gid or not last:
                continue
            entries = by_gid.get(gid) or []
            # What clock each banked set is on, asked of the one function
            # that knows. NOT read straight off `time_basis`: that stamp is
            # written by the correction, so a set which never needed
            # correcting -- detected in house, already on the recording's
            # own clock -- has none, and reading the stamp alone called its
            # recording unpatched and invited somebody to go and fix it.
            #
            # `basis_of` answers from the stamp where there is one and from
            # the pipeline where there is not, with the evidence for each
            # written down in `retime.py`.
            bases = [retime.basis_of(e) for e in entries]
            stamped = [b.get("basis") for b in bases]
            patched = bool(entries) and all(k == retime.TRUE
                                            for k in stamped)
            # Of those, the ones that were born right rather than repaired.
            # A different fact from `patched`, and worth its own word: this
            # recording needs nothing done to it and never did.
            safe = sum(1 for b in bases
                       if b.get("basis") == retime.TRUE
                       and not b.get("stamped"))
            out[gid] = {
                "gid": gid,
                "path": rec.get("path"),
                "label": rec.get("label"),
                "checked_at": last.get("at"),
                "checked_by": last.get("by"),
                "checked_on": last.get("machine"),
                "n_checks": len(rec.get("checks") or []),
                "level": last.get("level"),
                "n_segments": last.get("n_segments"),
                "n_gaps": last.get("n_gaps"),
                "seconds_lost": last.get("seconds_lost"),
                "max_time_error_ms": last.get("max_time_error_ms"),
                "gap_map_sha": last.get("gap_map_sha"),
                "all_channels": last.get("all_channels"),
                "concat_issue": int(last.get("n_segments") or 1) > 1,
                # Sets that never needed the correction because of how they
                # were made. `patched` says the problem was dealt with;
                # this says there was never one to deal with.
                "concat_safe": safe,
                "all_concat_safe": bool(entries) and safe == len(entries),
                "n_banked": len(entries),
                "n_events": sum(int(e.get("n") or 0) for e in entries),
                "patched": patched,
                # The thing worth filtering on: a real problem that nothing
                # has been done about.
                "unpatched": (int(last.get("n_segments") or 1) > 1
                              and bool(entries) and not patched),
            }
        return out


def rows_for_cloud(log):
    """Every check, flat, one row each -- the shape the database wants.

    Append-only and keyed on the check's own id, so two machines' histories
    union up there exactly as they do down here.
    """
    rows = []
    for rec in log.all():
        gid = rec.get("gid")
        for check in (rec.get("checks") or []):
            if not check.get("id"):
                continue
            rows.append({
                "id": check["id"],
                "gid": gid,
                "path": rec.get("path"),
                "label": rec.get("label"),
                "at": check.get("at"),
                "by_user": check.get("by"),
                "machine": check.get("machine"),
                "level": check.get("level"),
                "n_segments": check.get("n_segments"),
                "n_gaps": check.get("n_gaps"),
                "seconds_lost": check.get("seconds_lost"),
                "max_time_error_ms": check.get("max_time_error_ms"),
                "true_duration_s": check.get("true_duration_s"),
                "concat_duration_s": check.get("concat_duration_s"),
                "gap_map_sha": check.get("gap_map_sha"),
                "gap_rule": check.get("gap_rule"),
                "n_ncs": check.get("n_ncs"),
                "n_probed": check.get("n_probed"),
                "all_channels": bool(check.get("all_channels")),
                "mismatches": check.get("mismatches"),
                "updated_at": check.get("at"),
            })
    return rows
