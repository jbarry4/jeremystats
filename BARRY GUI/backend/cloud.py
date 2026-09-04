"""
cloud.py -- BARRY's Supabase sync.

Why both this and the files
---------------------------
The per-machine JSON files stay. They are what makes BARRY work on a rig with
no network, on a drive that is not mounted, and at 2am when the internet is
out -- and they are why nothing has ever been lost. Postgres is the shared
source of truth; the files are the local buffer and the offline queue.

That split is also why the sharding work still earns its keep: every local
record already carries a stamp saying when each thing on it last changed, so
a machine that has been offline for a week pushes edits that can be ordered
against what is already on the server rather than clobbering it. The database
enforces that too -- see barry_keep_newest() in 01_schema.sql -- so no client
can get it wrong, including this one.

No new dependencies
-------------------
Plain urllib against PostgREST. `pip install supabase` would pull in httpx,
pydantic and a stack of transitive pins into an environment that also has to
keep Kilosort and MATLAB's Python bridge happy. The REST API is a handful of
URLs; the trade is not close.

Credentials
-----------
Two files, and the difference between them is the whole point.

    BARRY GUI/cloud.json      tracked. Which project to sync to, and how
                              often. No key. Everyone who clones gets it.
    GUI_logs/.cloud.json      gitignored. The key, on this machine only.

So a clone already knows where to go, and only has to be told the key once --
which BARRY asks for when it starts rather than making anyone edit a file.

The key is never written to a tracked path: save_shared_config() drops it,
load_config() refuses to use one found there and says so instead, and
cloud_setup.py asks git before writing anything. If a key is ever committed
anyway, rotate it in the Supabase dashboard. That is the only real fix and it
takes a minute.

The environment beats both, for a rig that would rather keep it in a shell
profile: BARRY_SUPABASE_URL and BARRY_SUPABASE_KEY.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from . import shards

TIMEOUT = 60


def _quiet_rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _explain(method, path, code, detail):
    """Turn a PostgREST failure into something worth reading.

    The raw form is `GET /rest/v1/sessions?... -> HTTP 401 {"code":"PGRST303",
    "message":"JWT issued at future"}`, which says what happened and nothing
    about what to do. These are the ones that actually come up.
    """
    d = detail or ""
    hint = None
    if "PGRST303" in d or "issued at future" in d:
        hint = ("This machine's clock is ahead of Supabase's, so the token it "
                "signs looks like it was issued in the future and is "
                "rejected. Set the clock (Windows: Settings > Time & "
                "language > Date & time > Sync now). Nothing is wrong with "
                "the key or the data.")
    elif "PGRST301" in d or "JWT expired" in d:
        hint = ("The key has expired, or this machine's clock is behind. "
                "Check the clock first; if it is right, the key needs "
                "replacing in the Cloud panel.")
    elif "PGRST205" in d or "schema cache" in d:
        hint = ("That table is not in the database yet. Run the files in "
                "supabase/ against the project (01_schema.sql first), then "
                "sync again.")
    elif code == 401 or code == 403:
        hint = ("The key was refused. Check it in the Cloud panel -- a "
                "publishable key cannot write, so this needs the secret one.")
    elif code and int(code) >= 500:
        hint = ("The database itself returned an error, not a refusal -- "
                "nothing is wrong with the request or the key. These are "
                "usually brief; the next sync will pick up where this one "
                "stopped. If it keeps happening, check the Supabase project "
                "status page.")
    elif "22007" in d or "invalid input syntax for type timestamp" in d:
        hint = ("A timestamp reached the database malformed -- usually a '+' "
                "in a query string that was read as a space. This is a bug "
                "here, not a configuration problem; please report it.")
    base = "%s %s -> HTTP %s %s" % (method, path, code, d)
    return base + (chr(10) + chr(10) + hint if hint else "")


PAGE = 1000            # PostgREST's own default ceiling
BATCH = 200            # rows per upsert; keeps request bodies sane


class CloudError(RuntimeError):
    pass


class NotConfigured(CloudError):
    pass


# ==========================================================================
# Configuration
# ==========================================================================
def config_path(logs_dir):
    """This machine's file. Gitignored, and the only place the key lives."""
    return os.path.join(logs_dir, ".cloud.json")


def shared_config_path(logs_dir):
    """The tracked one, beside the app: which project, and how often.

    Committed on purpose. Somebody who clones the repo should not have to be
    told the project id as well as the key -- one secret to hand over is
    enough friction for a lab.
    """
    return os.path.join(os.path.dirname(os.path.abspath(logs_dir)),
                        "cloud.json")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


def load_config(logs_dir):
    """Where we sync to, and with what key.

    Environment beats this machine's file, which beats the repo's. A key
    sitting in the tracked file is ignored and reported rather than used:
    quietly working would be the surest way for nobody to notice it had been
    committed.
    """
    shared = _read(shared_config_path(logs_dir))
    leaked = bool(shared.pop("key", None))
    cfg = dict(shared)
    cfg.update(_read(config_path(logs_dir)))

    url = os.environ.get("BARRY_SUPABASE_URL") or cfg.get("url")
    key = os.environ.get("BARRY_SUPABASE_KEY") or cfg.get("key")
    if url and not url.startswith("http"):
        # A bare project id is what people have to hand.
        url = "https://%s.supabase.co" % url
    return {
        "url": (url or "").rstrip("/"),
        "key": key or "",
        "enabled": bool(cfg.get("enabled", True)) and bool(url and key),
        "auto": bool(cfg.get("auto", True)),
        "interval": int(cfg.get("interval", 120)),
        "upload_results": bool(cfg.get("upload_results", True)),
        "project": cfg.get("project")
        or (re.sub(r"^https://([^.]+)\..*$", r"\1", url) if url else None),
        # A project is set but no key yet -- which is exactly the state a
        # fresh clone is in, and what makes BARRY ask for one.
        "needs_key": bool(url) and not key,
        "key_in_repo": leaked,
    }


def save_shared_config(logs_dir, **patch):
    """The tracked file: which project, and how often. Never a key."""
    patch.pop("key", None)
    p = shared_config_path(logs_dir)
    cur = _read(p)
    cur.update({k: v for k, v in patch.items() if v is not None})
    cur["_note"] = (
        "Which Supabase project BARRY syncs to. Tracked on purpose, so a "
        "clone knows where to go. The key is NOT here: BARRY asks for it the "
        "first time it starts and keeps it in GUI_logs/.cloud.json, which "
        "git ignores.")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cur, fh, indent=2, sort_keys=True)
    os.replace(tmp, p)
    return cur


def save_config(logs_dir, **patch):
    """This machine's file. The key goes here and nowhere else."""
    p = config_path(logs_dir)
    cur = _read(p)
    cur.update({k: v for k, v in patch.items() if v is not None})
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cur, fh, indent=2, sort_keys=True)
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)      # best effort; Windows largely ignores it
    except OSError:
        pass
    return cur


def looks_like_a_key(text):
    """Is this plausibly a Supabase key, and is it the right one?

    Pasting the publishable key is the obvious mistake -- they sit next to
    each other in the dashboard and differ by one word -- and it fails later
    with a permissions error that explains nothing.
    """
    t = (text or "").strip()
    if not t:
        return False, "Nothing pasted."
    if t.startswith("sb_publishable_") or t.startswith("eyJ") and \
            "anon" in t:
        return False, ("That is the publishable key. BARRY needs the secret "
                       "one (it starts sb_secret_), because the publishable "
                       "key is deliberately given no access at all.")
    if not (t.startswith("sb_secret_") or t.startswith("eyJ")):
        return False, ("That does not look like a Supabase key. Copy the "
                       "service_role / secret key from Project Settings -> "
                       "API Keys.")
    if len(t) < 20:
        return False, "That looks truncated."
    return True, ""


# ==========================================================================
# Timestamps
# ==========================================================================
_OFFSET = re.compile(r"([+-]\d{2})(\d{2})$")


def ts(value):
    """Anything BARRY writes, as something Postgres will accept -- or None.

    BARRY has three timestamp shapes in its logs: local with a `-0400` style
    offset, UTC with microseconds from the shard layer, and bare
    `YYYY-MM-DD HH:MM:SS` from Neuralynx headers. A bad one returns None
    rather than failing the push, because a missing `made_at` is a small
    problem and a migration that stops halfway is a large one.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(" ", "T", 1) if re.match(r"^\d{4}-\d\d-\d\d ", s) else s
    s = _OFFSET.sub(r"\1:\2", s)          # -0400 -> -04:00
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return s
    except ValueError:
        return None


def now():
    return datetime.now(timezone.utc).isoformat()


# ==========================================================================
# The client
# ==========================================================================
class Cloud:
    def __init__(self, logs_dir, store=None):
        self.logs_dir = os.path.abspath(logs_dir)
        self.store = store
        self.cfg = load_config(self.logs_dir)
        self.machine = shards.machine_id()
        self._lock = threading.RLock()
        self.last = {"at": None, "ok": None, "pushed": 0, "pulled": 0,
                     "error": None}

    # -- plumbing -------------------------------------------------------
    @property
    def configured(self):
        return bool(self.cfg.get("url") and self.cfg.get("key"))

    def reload(self):
        self.cfg = load_config(self.logs_dir)
        return self.cfg

    def _headers(self, extra=None):
        if not self.configured:
            raise NotConfigured(
                "No Supabase project configured. Run "
                "tools/cloud_setup.py, or set BARRY_SUPABASE_URL and "
                "BARRY_SUPABASE_KEY.")
        h = {
            "apikey": self.cfg["key"],
            "Authorization": "Bearer " + self.cfg["key"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        h.update(extra or {})
        return h

    def _call(self, method, path, body=None, headers=None, raw=None,
              timeout=TIMEOUT):
        url = self.cfg["url"] + path
        data = raw if raw is not None else (
            json.dumps(body, default=str).encode("utf-8")
            if body is not None else None)
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=self._headers(headers))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                payload = res.read()
                if not payload:
                    return None, res.headers
                try:
                    return json.loads(payload.decode("utf-8")), res.headers
                except ValueError:
                    return payload, res.headers
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:600]
            except Exception:            # noqa: BLE001
                pass
            raise CloudError(_explain(method, path, exc.code, detail)) from None
        except urllib.error.URLError as exc:
            raise CloudError("cannot reach %s: %s"
                             % (self.cfg["url"], exc.reason)) from None

    # -- tables ---------------------------------------------------------
    @staticmethod
    def _safe_query(query):
        """Percent-encode what a URL cannot carry, leaving the syntax alone.

        PostgREST filters are written as `col=op.value`, and the values here
        are labels like "PTEN m1 s2 2023-10-02" and Windows paths -- so a raw
        space, quote or backslash is normal and http.client rejects the
        request outright. Only the characters that are actually illegal get
        encoded; =, & and . are the filter's own grammar and stay.
        """
        out = []
        for ch in query or "":
            # Note what is NOT in this list. "+" has to be encoded: a query
            # string reads it as a space, so the "+00:00" on every timestamp
            # arrives as " 00:00" and Postgres rejects it -- which only shows
            # up on the *second* incremental pull, because the first has no
            # timestamp to filter on.
            if ch.isalnum() or ch in "=&.-_~*()!'$,:/?[]@%":
                out.append(ch)
            else:
                out.append("".join("%%%02X" % b
                                   for b in ch.encode("utf-8")))
        return "".join(out)

    def select(self, table, query="", limit=PAGE, offset=0):
        q = self._safe_query(query)
        q = q + ("&" if q else "")
        path = "/rest/v1/%s?%sselect=*&limit=%d&offset=%d" % (
            table, q, limit, offset)
        rows, _h = self._call("GET", path)
        return rows or []

    def select_all(self, table, query=""):
        """Every matching row, paged. PostgREST caps a response; walking the
        pages here means a caller never silently sees the first thousand."""
        out, offset = [], 0
        while True:
            page = self.select(table, query, limit=PAGE, offset=offset)
            out.extend(page)
            if len(page) < PAGE:
                return out
            offset += PAGE

    def upsert(self, table, rows, on_conflict=None):
        """Insert or update, in batches, ignoring rows the trigger rejects.

        `resolution=merge-duplicates` is what makes this idempotent: running
        the migration twice, or pushing a record that is already up there,
        does nothing rather than erroring.
        """
        rows = [r for r in (rows or []) if r]
        if not rows:
            return 0
        prefer = "resolution=merge-duplicates,return=minimal"
        sent = 0
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            path = "/rest/v1/" + table
            if on_conflict:
                path += "?on_conflict=" + urllib.parse.quote(on_conflict)
            self._call("POST", path, body=chunk,
                       headers={"Prefer": prefer})
            sent += len(chunk)
        return sent

    def patch_rows(self, table, query, values):
        """Change existing rows, without needing their primary key.

        An upsert cannot do this: it would have to insert when no row matches,
        and inserting needs the key. "Mark whatever is at this path deleted"
        is a PATCH, and saying so is the difference between a tombstone that
        travels and one that silently does nothing.
        """
        rows, _h = self._call(
            "PATCH", "/rest/v1/%s?%s" % (table, self._safe_query(query)),
            body=values, headers={"Prefer": "return=representation"})
        return rows or []

    def delete(self, table, query):
        self._call("DELETE", "/rest/v1/%s?%s"
                   % (table, self._safe_query(query)),
                   headers={"Prefer": "return=minimal"})

    def count(self, table):
        path = "/rest/v1/%s?select=*&limit=1" % table
        _rows, headers = self._call(
            "GET", path, headers={"Prefer": "count=exact",
                                  "Range-Unit": "items", "Range": "0-0"})
        rng = headers.get("Content-Range") or ""
        try:
            return int(rng.split("/")[-1])
        except (ValueError, IndexError):
            return None

    # -- storage --------------------------------------------------------
    def upload(self, bucket, key, path, content_type=None):
        """Put one file in the bucket. Overwrites, so a re-run is a no-op."""
        with open(path, "rb") as fh:
            blob = fh.read()
        ct = content_type or mimetypes.guess_type(path)[0] \
            or "application/octet-stream"
        target = "/storage/v1/object/%s/%s" % (
            bucket, urllib.parse.quote(key))
        self._call("POST", target, raw=blob,
                   headers={"Content-Type": ct, "x-upsert": "true"},
                   timeout=180)
        return key

    def download(self, bucket, key, dest):
        target = "/storage/v1/object/%s/%s" % (
            bucket, urllib.parse.quote(key))
        blob, _h = self._call("GET", target, timeout=180)
        if isinstance(blob, (dict, list)):
            raise CloudError("expected a file, got JSON for " + key)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(blob if isinstance(blob, bytes)
                     else str(blob).encode("utf-8"))
        return dest

    def list_objects(self, bucket, prefix="", limit=1000):
        body = {"prefix": prefix, "limit": limit,
                "sortBy": {"column": "name", "order": "asc"}}
        rows, _h = self._call("POST", "/storage/v1/object/list/" + bucket,
                              body=body)
        return rows or []

    # -- health ---------------------------------------------------------
    def ping(self):
        """Is the project there, is the key good, is the schema applied?"""
        out = {"url": self.cfg.get("url"), "project": self.cfg.get("project"),
               "machine": self.machine, "reachable": False,
               "schema": False, "counts": {}, "error": None}
        try:
            self._call("GET", "/rest/v1/")
            out["reachable"] = True
        except CloudError as exc:
            out["error"] = str(exc)
            return out
        try:
            for t in ("sessions", "mice", "bank_entries", "curation_events",
                      "results", "runs", "activity"):
                out["counts"][t] = self.count(t)
            out["schema"] = True
        except CloudError as exc:
            out["error"] = ("the project is reachable but the schema is not "
                            "there yet -- run supabase/01_schema.sql. (%s)"
                            % str(exc)[:160])
        return out

    # -- sync bookkeeping ------------------------------------------------
    def _state_path(self):
        d = os.path.join(self.logs_dir, ".cache")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "cloud_state.json")

    def state(self):
        try:
            with open(self._state_path(), "r", encoding="utf-8") as fh:
                return json.load(fh) or {}
        except (OSError, ValueError):
            return {}

    def save_state(self, patch):
        """Remember where the sync got to.

        This is a cache, not data: it can be rebuilt by syncing again. So a
        failure to write it must not be reported as a sync failure, which is
        what was happening -- two BARRYs against the same GUI_logs contended
        for a shared "cloud_state.json.tmp" and the "Permission denied" that
        came back was logged as though the whole sync had broken.
        """
        import uuid as _uuid
        st = self.state()
        st.update(patch or {})
        target = self._state_path()
        # Private per process and attempt, so two BARRYs cannot collide.
        tmp = "%s.%d.%s.tmp" % (target, os.getpid(), _uuid.uuid4().hex[:6])
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(st, fh, indent=2, sort_keys=True)
        except OSError:
            _quiet_rm(tmp)
            return st                       # a cache; nothing is lost
        # The rename can be refused for a moment by an indexer or a backup
        # agent. Retried, then given up on quietly.
        for attempt in range(5):
            try:
                os.replace(tmp, target)
                return st
            except OSError:
                time.sleep(0.05 * (attempt + 1))
        _quiet_rm(tmp)
        return st
