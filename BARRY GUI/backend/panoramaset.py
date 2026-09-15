"""
panoramaset.py -- Panorama over many recordings, and what survives a restart.

One recording at a time is a question you can answer while watching. Forty is
not: a set takes long enough that the app will be restarted under it, the
machine will be used for something else, and a colleague will run half of it.
So the interesting part of bulk is not the loop -- it is what is written down.

THREE BOOKS, AND WHY THEY ARE SEPARATE

  results/     one record per (recording, parameters). The expensive thing.
  <set_id>     which recordings, which parameters, and where each one got to.
  groupings/   which recording is in which group. Reusable across sets.

**Results are keyed on the recording and the parameters, not on the set.** Two
sets that ask the same question of the same recording share the answer, so
adding a recording to a second set costs nothing, and re-running a set after
changing the frequency range does not overwrite the old numbers -- it writes
different ones beside them. This is also what makes resume free: a member
whose record already exists is skipped in milliseconds rather than recomputed.

WHAT IS NOT IN HERE

The spectrogram. It is two thousand columns by four hundred bins, which is
megabytes per recording, and it is a *picture* -- so it goes to
`GUI_logs/.cache/panorama/`, which git ignores, and is regenerated from the
recording if it is ever missing. The durable record holds the numbers a
figure or a statistic is made from, about thirty kilobytes a recording, which
is small enough to commit and to sync.

WHY `state` IS A MAP AND NOT A LIST

Two people running different halves of one set is the ordinary case, not the
exception. `state` is `MAPLWW`, so their shards merge key by key and both
keep their work; the same recording run twice is a genuine disagreement and
last-writer-wins settles it and terminates. The entries must stay small --
scalars and a pointer -- because `Book.write` fingerprints every value in a
MAPLWW field on every write, so putting a histogram in one would re-hash
forty histograms every time a member finished.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

from . import shards

SCHEMA = 1

# The set: what was asked, of which recordings, and where each one got to.
SET_SPEC = {
    "created": shards.FIRST,
    "set_id": shards.FIRST,
    # Frozen at creation. A set whose members were computed under different
    # parameters is a set whose convergence plot pools things that cannot be
    # pooled, and nothing about the file would say so. Changing the question
    # makes a new set; `params_hash` is what enforces it and FIRST is the
    # policy that says so out loud.
    "params": shards.FIRST,
    "params_hash": shards.FIRST,
    "members": shards.BYID,
    "state": shards.MAPLWW,
    "saved": shards.BYID,
}

# One record per recording per question asked of it.
RESULT_SPEC = {
    "created": shards.FIRST,
    "gid": shards.FIRST,
    "params_hash": shards.FIRST,
}

# Who is in which group. Reusable, and referenced by id from a set.
GROUPING_SPEC = {
    "created": shards.FIRST,
    "id": shards.FIRST,
    "groups": shards.BYID,
    # gid -> [group_id, ...], NOT group -> [gid].
    #
    # Under UNION the other way round, one person moving a recording from CTL
    # to PTEN while another leaves it alone resurrects it in CTL, and it is
    # then in both arms on every machine with nothing to say which is meant.
    # Keyed on the recording, the value is its whole membership: different
    # recordings merge key by key, and the same one edited twice is a real
    # disagreement that last-writer-wins settles.
    "assign": shards.MAPLWW,
}

# What a member can be doing. `interrupted` is not a failure: the process
# holding the job went away, which after a restart is the ordinary case.
STATES = ("waiting", "running", "done", "failed", "interrupted", "skipped")

# How a member's channel was arrived at, kept beside the channel itself so a
# number chosen by rule and a number chosen by hand are never confused.
CHANNEL_FROM = ("layers", "manual", "fallback", "none")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def new_set_id():
    return "pn" + uuid.uuid4().hex[:10]


def params_hash(params):
    """A short name for one question.

    Only the fields that change the numbers. The colormap and the picture's
    scale are deliberately left out: re-colouring a spectrogram does not make
    the histogram behind it a different measurement, and including them would
    split the store into copies that differ by nothing.
    """
    keep = {k: params.get(k) for k in (
        "f_lo", "f_hi", "sub_s", "win_s", "step_s", "line_hz", "bins",
        "hist_scale", "t0", "t1",
        "peak_width_limits", "max_n_peaks", "min_peak_height",
        "aperiodic_mode") if params.get(k) is not None}
    blob = json.dumps(keep, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


class Sets:
    def __init__(self, logs_dir, store):
        self.root = os.path.join(logs_dir, "panorama")
        self.cache = os.path.join(logs_dir, ".cache", "panorama")
        self.store = store
        os.makedirs(self.root, exist_ok=True)
        os.makedirs(os.path.join(self.root, "results"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "groupings"), exist_ok=True)
        os.makedirs(self.cache, exist_ok=True)

        self.book = shards.Book(self.root, SET_SPEC, store)
        self.results = shards.Book(os.path.join(self.root, "results"),
                                   RESULT_SPEC, store)
        self.groupings = shards.Book(os.path.join(self.root, "groupings"),
                                     GROUPING_SPEC, store)

    # -- provenance ------------------------------------------------------
    def _who(self):
        return self.store.provenance() if self.store else {"at": _now()}

    # ==================================================================
    # Sets
    # ==================================================================
    def create(self, name, params, members=None, grouping="auto", note=None):
        ph = params_hash(params)
        rec = {
            "schema": SCHEMA,
            "set_id": new_set_id(),
            "name": (name or "").strip() or "Untitled set",
            "note": note or None,
            "params": dict(params),
            "params_hash": ph,
            "members": [],
            "state": {},
            "saved": [],
            "grouping": grouping or "auto",
            "open": True,
            "archived": False,
            "created": self._who(),
        }
        if members:
            rec = self._add(rec, members)
        return self._write(rec)

    def _write(self, rec):
        rec["updated"] = self._who()
        return self.book.write(shards.safe_base(rec["set_id"]), rec)

    def get(self, set_id):
        return self.book.read(shards.safe_base(set_id))

    def all(self, include_archived=False):
        got = [r for r in self.book.all() if r.get("set_id")]
        if not include_archived:
            got = [r for r in got if not r.get("archived")]
        got.sort(key=lambda r: ((r.get("updated") or {}).get("at") or ""),
                 reverse=True)
        return got

    def _add(self, rec, members):
        """`members` is [{gid, label, path, channel, channel_from, region}]."""
        have = {m["id"] for m in (rec.get("members") or [])}
        for m in members:
            gid = m.get("gid") or m.get("id")
            if not gid or gid in have:
                continue
            have.add(gid)
            rec.setdefault("members", []).append({
                "id": gid,
                "gid": gid,
                "label": m.get("label"),
                "path": m.get("path"),
                "channel": m.get("channel"),
                "channel_label": m.get("channel_label"),
                "channel_from": m.get("channel_from") or "none",
                "region": m.get("region"),
                "enabled": True,
                "added": self._who(),
            })
            rec.setdefault("state", {})[gid] = {
                "status": "waiting", "at": _now(),
            }
        return rec

    @shards.atomic
    def add_members(self, set_id, members):
        rec = self.get(set_id)
        if not rec:
            return None
        return self._write(self._add(rec, members))

    @shards.atomic
    def remove_member(self, set_id, gid):
        rec = self.get(set_id)
        if not rec:
            return None
        rec["members"] = [m for m in (rec.get("members") or [])
                          if m.get("id") != gid]
        # The state entry stays. A tombstone costs nothing and "this was in
        # the set and was taken out" is a different fact from "this was never
        # in it" -- which matters when a colleague's shard still has it.
        st = (rec.get("state") or {}).get(gid)
        if st:
            st["status"] = "skipped"
            st["removed"] = _now()
        return self._write(rec)

    @shards.atomic
    def set_channel(self, set_id, gid, channel, channel_label=None,
                    how="manual", region=None):
        """Override which channel one recording is analysed on.

        Marked `manual` so the tree can say which rows were chosen by rule and
        which by hand. A channel chosen by hand is evidence about that
        recording; a channel chosen by rule is evidence about the rule.
        """
        rec = self.get(set_id)
        if not rec:
            return None
        for m in rec.get("members") or []:
            if m.get("id") == gid:
                m["channel"] = (None if channel is None else int(channel))
                m["channel_label"] = channel_label
                m["channel_from"] = how if channel is not None else "none"
                if region is not None:
                    m["region"] = region
                break
        # The answer was for a different channel, so it is no longer this
        # member's answer.
        st = (rec.get("state") or {}).setdefault(gid, {})
        if st.get("status") == "done":
            st["status"] = "waiting"
            st["at"] = _now()
            st.pop("result", None)
        return self._write(rec)

    @shards.atomic
    def mark(self, set_id, gid, **patch):
        """Merge scalars into one member's state entry.

        Scalars and a pointer only -- see the note at the top of the module
        on why this map has to stay small.
        """
        rec = self.get(set_id)
        if not rec:
            return None
        st = (rec.setdefault("state", {})).setdefault(gid, {})
        for k, v in patch.items():
            if isinstance(v, (list, dict, tuple, set)):
                raise TypeError(
                    "mark(%r): %r is not a scalar. The numbers live in the "
                    "result record, not in the set's state map." % (gid, k))
            st[k] = v
        st["at"] = _now()
        return self._write(rec)

    @shards.atomic
    def rename(self, set_id, name):
        rec = self.get(set_id)
        if not rec:
            return None
        rec["name"] = (name or "").strip() or rec.get("name")
        return self._write(rec)

    @shards.atomic
    def archive(self, set_id, on=True):
        rec = self.get(set_id)
        if not rec:
            return None
        rec["archived"] = bool(on)
        return self._write(rec)

    @shards.atomic
    def set_grouping(self, set_id, grouping):
        rec = self.get(set_id)
        if not rec:
            return None
        rec["grouping"] = grouping or "auto"
        return self._write(rec)

    @shards.atomic
    def record_saved(self, set_id, entry):
        rec = self.get(set_id)
        if not rec:
            return None
        got = dict(entry)
        got.setdefault("id", "out" + uuid.uuid4().hex[:8])
        got.setdefault("at", _now())
        rec.setdefault("saved", []).append(got)
        return self._write(rec)

    # ==================================================================
    # Results -- one per recording per question
    # ==================================================================
    def result_base(self, gid, ph):
        return shards.safe_base(gid, ph)

    def result_get(self, gid, ph):
        return self.results.read(self.result_base(gid, ph))

    def result_put(self, rec):
        rec["updated"] = self._who()
        return self.results.write(
            self.result_base(rec["gid"], rec["params_hash"]), rec)

    def png_path(self, gid, ph):
        """Where a member's spectrogram lives. Cache, not record."""
        return os.path.join(self.cache, "%s__%s.png"
                            % (shards.safe_base(gid), ph))

    def has_png(self, gid, ph):
        p = self.png_path(gid, ph)
        return os.path.exists(p) and os.path.getsize(p) > 0

    # ==================================================================
    # What still has to run
    # ==================================================================
    def pending(self, rec, force=False):
        """The members a run would actually do, and why the rest are skipped.

        A member whose result already exists under this set's parameters is
        not recomputed -- which is what makes Resume after a restart, and
        adding a recording to a second set, both free.

        A member that cannot run carries the reason. Everything knowable
        before the run is settled before it: a recording with no channel
        chosen, or none this machine can reach, should say so while
        somebody can still fix it -- not wait its turn behind thirty
        others and then fail.
        """
        ph = rec.get("params_hash")
        todo, cached, blocked = [], [], []
        for m in rec.get("members") or []:
            if not m.get("enabled", True):
                continue
            gid = m["id"]
            why = None
            if not m.get("path"):
                why = "no folder this machine can read"
            elif m.get("channel") is None:
                why = "no channel chosen"
            if why:
                got = dict(m)
                got["blocked_why"] = why
                blocked.append(got)
                continue
            if not force and self.result_get(gid, ph):
                cached.append(m)
                continue
            todo.append(m)
        return {"todo": todo, "cached": cached, "blocked": blocked}

    def reconcile(self, rec, alive):
        """Mark members whose job died as interrupted rather than running.

        `alive(job_id)` is `cfc.exists`. After a restart the record still says
        "running" and the thread it names is gone with the last process --
        which is `interrupted`, and showing it as running leaves the view
        waiting for progress that will never come.
        """
        changed = False
        for gid, st in (rec.get("state") or {}).items():
            if st.get("status") == "running" and not alive(st.get("job")):
                st["status"] = "interrupted"
                st["at"] = _now()
                changed = True
        return changed

    # ==================================================================
    # Groupings
    # ==================================================================
    def grouping_get(self, gid_):
        return self.groupings.read(shards.safe_base(gid_))

    def grouping_all(self):
        return [g for g in self.groupings.all() if g.get("id")]

    def grouping_create(self, name, groups=None, assign=None, note=None):
        rec = {
            "schema": SCHEMA,
            "id": "grp" + uuid.uuid4().hex[:8],
            "name": (name or "").strip() or "Untitled grouping",
            "note": note or None,
            "groups": list(groups or []),
            "assign": dict(assign or {}),
            "created": self._who(),
        }
        return self._write_grouping(rec)

    def _write_grouping(self, rec):
        rec["updated"] = self._who()
        return self.groupings.write(shards.safe_base(rec["id"]), rec)

    @shards.atomic
    def grouping_assign(self, grouping_id, gid, group_ids):
        """Set one recording's whole membership at once.

        The whole list, never an add or a remove: that is what makes two
        machines editing different recordings merge cleanly and two machines
        editing the SAME one resolve to one answer instead of a union of
        both.
        """
        rec = self.grouping_get(grouping_id)
        if not rec:
            return None
        rec.setdefault("assign", {})[gid] = [str(g) for g in (group_ids or [])]
        return self._write_grouping(rec)

    @shards.atomic
    def grouping_edit(self, grouping_id, groups=None, name=None, note=None):
        rec = self.grouping_get(grouping_id)
        if not rec:
            return None
        if groups is not None:
            rec["groups"] = list(groups)
        if name is not None:
            rec["name"] = name.strip() or rec.get("name")
        if note is not None:
            rec["note"] = note
        return self._write_grouping(rec)


# ==========================================================================
# Running a set
# ==========================================================================
def plan_for_set(rec, opener, members=None):
    """What a run would cost, without doing any of it.

    Sums the spans, so the estimate is in the same seconds-of-recording the
    `panorama bulk` stage counts and the learned rate is per. Recordings
    this machine cannot reach are reported rather than silently dropped: a
    set assembled on the rig and opened on a laptop is mostly unreachable,
    and an estimate that quietly ignores that is an estimate for a different
    run.
    """
    from . import panorama

    members = members if members is not None else [
        m for m in (rec.get("members") or []) if m.get("enabled", True)]
    span_s, n_ok, unreachable = 0.0, 0, []
    for m in members:
        sess = opener(m)
        if not sess or not sess.get("ok"):
            unreachable.append(m.get("id"))
            continue
        # The span does not depend on which channel, so an empty list
        # would do -- but plan_for wants one and this keeps the estimate
        # computed from exactly what the run will use.
        plan = panorama.plan_for(sess, dict(rec.get("params") or {},
                                            channels=[0]))
        span_s += plan["span_s"]
        n_ok += 1
    return {
        "n_members": len(members),
        "n_reachable": n_ok,
        "unreachable": unreachable,
        "span_s": round(span_s, 1),
        "seconds": round(span_s * _rate(), 1),
    }


def _rate():
    from . import cfc
    return cfc.rate_for("panorama bulk") or 7.0e-2


def run_set(sets, set_id, opener, job, force=False, on_member=None):
    """Read, fit and file one recording at a time.

    Sequential on purpose. The sessions cache in `app.py` holds six and is a
    plain dict whose eviction iterates while request threads insert, so a
    fan-out of workers through it is a race as well as a thrash -- and one
    recording at a time means the six never matters. `opener` is handed in so
    this never touches that cache at all.

    Every recording is filed the moment it finishes. A set is long enough
    that the process will be restarted under it, and work that is only in
    memory when that happens was never done.
    """
    from . import panorama

    rec = sets.get(set_id)
    if not rec:
        raise ValueError("No such set.")
    ph = rec["params_hash"]
    params = dict(rec.get("params") or {})

    split = sets.pending(rec, force=force)
    todo = split["todo"]
    enabled = [m for m in (rec.get("members") or []) if m.get("enabled", True)]

    # The whole tree up front, so forty recordings show as forty waiting
    # rather than growing a row at a time -- which reads as "it has only
    # found one of them".
    job.members_init([{"id": m["id"], "label": m.get("label") or m["id"]}
                      for m in enabled])
    for m in split["cached"]:
        job.member(m["id"], status="done", cached=True, step="already done")
        sets.mark(set_id, m["id"], status="done", cached=True)
    for m in split["blocked"]:
        why = m.get("blocked_why") or "cannot be run"
        job.member(m["id"], status="skipped", step=why, error=why)
        sets.mark(set_id, m["id"], status="skipped", error=why)

    done_s = 0.0
    ok_n, fail_n = 0, 0
    for m in todo:
        job.check()
        gid = m["id"]
        job.member(gid, status="running", step="opening")
        sets.mark(set_id, gid, status="running", job=job.id)

        sess = opener(m)
        if not sess or not sess.get("ok"):
            why = (sess or {}).get("error") or "not reachable from here"
            job.member(gid, status="failed", step=None, error=why[:200])
            sets.mark(set_id, gid, status="failed", error=why[:200])
            fail_n += 1
            continue

        # Number to row, now that the recording is open. CSC14 is CSC14
        # in every recording; row 14 is not.
        by_number = {c.get("number"): c for c in (sess.get("channels") or [])}
        ch = by_number.get(m.get("channel"))
        if not ch:
            why = "CSC%s is not in this recording" % m.get("channel")
            job.member(gid, status="failed", step=None, error=why)
            sets.mark(set_id, gid, status="failed", error=why)
            fail_n += 1
            continue
        plan = panorama.plan_for(sess, dict(params,
                                            channels=[ch["index"]]))

        def step(name, done, of, _gid=gid):
            job.member(_gid, step=name, done=int(done), of=int(of))

        t_started = time.time()
        try:
            got = panorama.read_channel(sess, ch, plan, job, on_step=step)
            if "error" not in got:
                got = panorama.fit_channel(got, plan, job, on_step=step)
        except Exception as exc:                         # noqa: BLE001
            if exc.__class__.__name__ == "Canceled":
                raise
            got = {"error": str(exc)[:300]}

        if "error" in got or "hist" not in got:
            why = got.get("error") or "produced nothing"
            job.member(gid, status="failed", step=None, error=why[:200])
            sets.mark(set_id, gid, status="failed", error=why[:200])
            fail_n += 1
        else:
            out = panorama.compact(got, plan, gid, ph, m)
            out["computed"] = {"seconds": round(time.time() - t_started, 2),
                               "at": _now(),
                               "machine": shards.machine_id()}
            sets.result_put(out)
            png = panorama.png_bytes_of(got)
            if png:
                try:
                    with open(sets.png_path(gid, ph), "wb") as fh:
                        fh.write(png)
                except OSError:
                    pass    # a cache of a picture; it redraws without it
            job.member(gid, status="done", step=None,
                       done=out["n_windows"], of=out["n_windows"],
                       modal_hz=out.get("modal_hz"),
                       n_nopeak=out.get("n_nopeak"),
                       n_windows=out.get("n_windows"),
                       seconds=out["computed"]["seconds"])
            sets.mark(set_id, gid, status="done",
                      n_windows=out.get("n_windows"),
                      n_used=out.get("n_used"),
                      n_nopeak=out.get("n_nopeak"),
                      modal_hz=out.get("modal_hz"),
                      seconds=out["computed"]["seconds"])
            ok_n += 1
            if on_member:
                on_member(gid, out)

        done_s += plan["span_s"]
        job.tick("panorama bulk", int(done_s))

    return {"ok": True, "set_id": set_id, "params_hash": ph,
            "done": ok_n, "failed": fail_n,
            "cached": len(split["cached"]),
            "skipped": len(split["blocked"])}


# ==========================================================================
# Converging
#
# The point of a set. Every recording's dominant-frequency histogram, pooled
# into one picture per group.
#
# THE WEIGHTING IS THE WHOLE ARGUMENT
#
# Recordings are different lengths, so they have different numbers of
# windows, so pooling raw counts makes the group curve an estimate of the
# longest recording's spectrum. Worse, windows inside a recording are
# strongly autocorrelated -- a rhythm does not stop between one second and
# the next -- so a pooled-count curve has an apparent n of tens of thousands
# and a real n of however many animals there were. Any interval computed on
# it is not optimistic, it is meaningless.
#
# So the default normalises each recording to a density and gives every
# recording one vote. Pooled counts stay available, because "how much of the
# cohort's recorded time was spent at 8 Hz" is occasionally the question --
# but it has to be asked for.
#
# AND THE DENOMINATOR IS THE SECOND ARGUMENT
#
# Dividing by the number of windows that HAVE a peak, not by the number of
# windows. A genotype that abolishes a rhythm shows up as windows with no
# peak in them; divide by all windows and that becomes a uniform height
# reduction across every bin, which reads as "somewhat less of everything",
# is the wrong conclusion, and is invisible to the eye. So the no-peak
# fraction is carried separately and plotted in its own right.
# ==========================================================================
UNGROUPED = "__ungrouped__"


def _density(counts, n_used, edges):
    """One recording's histogram as a density: per analysed window, per Hz.

    Per Hz matters. Without it the curve's height depends on how many bins
    it was cut into, and two sets binned differently cannot be laid over
    each other.
    """
    import numpy as np

    c = np.asarray(counts or [], dtype=float)
    e = np.asarray(edges or [], dtype=float)
    if c.size == 0 or e.size != c.size + 1 or not n_used:
        return None
    w = np.diff(e)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = c / float(n_used) / w
    d[~np.isfinite(d)] = 0.0
    return d


def converge(sets, rec, groups_of, dominant="peak", weight="session"):
    """Pool the set's histograms by group.

    `groups_of(gid)` returns the group ids that recording is in -- derived
    from the registry, or read from a stored grouping. `dominant` picks which
    of the two histograms to pool. `weight` is "session" (one vote each) or
    "window" (pooled counts).

    Returns the curves, the per-recording lines behind them, and one scalar
    per recording for the strip plot -- which is the object a test can
    actually be run on, the pooled curve being the exploratory one.
    """
    import numpy as np

    ph = rec.get("params_hash")
    key = "counts_flat" if dominant == "flat" else "counts_peak"
    edges = None
    per = []          # one entry per recording that has an answer
    missing, empty = [], []

    for m in rec.get("members") or []:
        if not m.get("enabled", True):
            continue
        gid = m["id"]
        res = sets.result_get(gid, ph)
        if not res:
            missing.append(gid)
            continue
        if edges is None:
            edges = res.get("edges")
        n_used = int(res.get("n_used") or 0)
        if n_used <= 0:
            # Analysed, and nothing in it. Excluded from the mean and
            # reported: a row of zeros is a different claim -- that the
            # rhythm was uniformly absent -- and it would drag the mean
            # down in proportion to how many such recordings there were.
            empty.append(gid)
            continue
        d = _density(res.get(key), n_used, edges)
        if d is None:
            empty.append(gid)
            continue
        n_win = int(res.get("n_windows") or 0)
        per.append({
            "gid": gid,
            "label": m.get("label") or res.get("session_label") or gid,
            "groups": list(groups_of(gid) or []),
            "density": [float(v) for v in d],
            "counts": [int(v) for v in (res.get(key) or [])],
            "n_windows": n_win,
            "n_used": n_used,
            "n_nopeak": int(res.get("n_nopeak") or 0),
            "nopeak_frac": (float(res.get("n_nopeak") or 0) / n_win)
                            if n_win else None,
            "modal_hz": res.get("modal_hz"),
            "median_hz": res.get("median_hz"),
            "exponent": (res.get("fit") or {}).get("exponent"),
            "close_call_frac": res.get("close_call_frac"),
        })

    if edges is None:
        return {"ok": False,
                "error": "Nothing in this set has been run yet."}

    e = np.asarray(edges, dtype=float)
    widths = np.diff(e)
    centres = np.sqrt(e[:-1] * e[1:])

    # gid -> groups, but a recording in two groups of one facet would be
    # compared with itself. Refused, by name, rather than double-counted.
    clashes = [p for p in per if len(p["groups"]) > 1]
    bygroup = {}
    for p in per:
        gs = p["groups"] or [UNGROUPED]
        for g in gs:
            bygroup.setdefault(g, []).append(p)

    out_groups = []
    for g in sorted(bygroup):
        rows = bygroup[g]
        mat = np.asarray([r["density"] for r in rows], dtype=float)
        if weight == "window":
            # One vote per window: the raw counts added up and normalised
            # once. Longer recordings count for more, which is the point of
            # asking for it and the reason it is not the default.
            tot = np.asarray([r["counts"] for r in rows],
                             dtype=float).sum(axis=0)
            used = float(sum(r["n_used"] for r in rows)) or 1.0
            with np.errstate(divide="ignore", invalid="ignore"):
                mean = tot / used / widths
            mean[~np.isfinite(mean)] = 0.0
            sem = np.zeros_like(mean)
        else:
            mean = mat.mean(axis=0)
            sem = (mat.std(axis=0, ddof=1) / np.sqrt(mat.shape[0])
                   if mat.shape[0] > 1 else np.zeros_like(mean))
        med = np.median(mat, axis=0)
        q1 = np.percentile(mat, 25, axis=0)
        q3 = np.percentile(mat, 75, axis=0)
        nf = [r["nopeak_frac"] for r in rows if r["nopeak_frac"] is not None]
        out_groups.append({
            "id": g,
            "n": len(rows),
            "mean": [float(v) for v in mean],
            "sem": [float(v) for v in sem],
            "median": [float(v) for v in med],
            "q1": [float(v) for v in q1],
            "q3": [float(v) for v in q3],
            "modal_hz": float(centres[int(np.argmax(mean))]) if mean.size else None,
            "nopeak_mean": (float(np.mean(nf)) if nf else None),
            "gids": [r["gid"] for r in rows],
        })

    return {
        "ok": True,
        "edges": [float(v) for v in e],
        "centres": [float(v) for v in centres],
        "dominant": dominant,
        "weight": weight,
        "groups": out_groups,
        # The faint lines behind the mean. Not optional: a group mean over
        # six recordings where one is bimodal looks exactly like six mildly
        # broad ones, and these are the only thing that says which.
        "sessions": [{k: p[k] for k in
                      ("gid", "label", "groups", "density", "n_windows",
                       "n_used", "n_nopeak", "nopeak_frac", "modal_hz",
                       "median_hz", "exponent")} for p in per],
        "n_sessions": len(per),
        # How often, across the set, the dominant peak only just won.
        #
        # Measured at 84% on a real recording over 2-100 Hz, and 0% on a
        # synthetic one with a single clean rhythm -- so this is a property
        # of asking a wide range of a 1/f spectrum, not of any one
        # recording. It belongs where the histogram is being read rather
        # than as a mark against individual rows.
        "close_call_frac": (
            round(sum(p["close_call_frac"] for p in per
                      if p.get("close_call_frac") is not None)
                  / float(max(1, sum(1 for p in per
                                     if p.get("close_call_frac") is not None))),
                  4)
            if any(p.get("close_call_frac") is not None for p in per)
            else None),
        # Said, not swallowed: a figure six recordings short with nothing
        # to say so is how they vanish.
        "not_run": missing,
        "no_windows": empty,
        "in_several_groups": [p["gid"] for p in clashes],
    }
