"""
syncitems.py -- Has this thing reached the shared database?

Two jobs, both about the records people work on (Event Bank entries,
curation sets, layer sheets, artifacts):

1. **Ask for a push the moment one changes.** Through `shards.ON_CHANGE`,
   so it does not matter what made the change. A request already asked for
   a push on its way out (app.py, `_note_local_write`), but a VACC batch
   banking its results in a thread made no request, so its entries sat until
   the next timed push. A timed push does not come at all while Jarvis is
   idle-paused, which is exactly when a batch finishes overnight.

2. **Say, per record, whether it has gone up.** `GET /api/cloud/items`,
   answered from the push cursor (`Sync.item_states`), so it costs no
   request at Supabase. Supabase egress is counted in requests, so a status
   that asked the database on every poll would cost more than the sync does.

Installed by `install(app, ...)` from app.py, so app.py gains one call
rather than another three hundred lines.
"""
from __future__ import annotations

import os
import threading
import time

from flask import jsonify, request

from . import shards

# A status poll from every open ToolKit panel would otherwise walk every
# store each time. Five seconds is shorter than anybody can notice and
# longer than a burst of panels asking at once.
CACHE_S = 5.0


def install(app, *, cloud_sync, stores, registry, last, touch, lock):
    """Wire the change hook and the status route.

    `cloud_sync` is the cloudsync.Sync; `stores` the directories whose
    records are shared (a Book whose directory is under one of them asks
    for a push); `registry` the sessreg.Registry; `last` app.py's
    `_cloud_last`; `touch(urgent=True)` its `cloud_touch`; `lock` the sync
    lock, held while a sync runs.
    """
    roots = tuple(os.path.normcase(os.path.abspath(d)).rstrip("\\/") + os.sep
                  for d in stores if d)

    def changed(book):
        # A sync applying what it pulled writes through these Books too.
        # Those rows came FROM the cloud, so asking to push them back is a
        # round of requests for nothing. Changes made by people while a sync
        # runs still go up: the request that made them asks on its way out.
        if lock.locked():
            return
        here = os.path.normcase(os.path.abspath(book.dir)) + os.sep
        if here.startswith(roots):
            touch(urgent=True)

    shards.ON_CHANGE = changed

    # The first answer reads every store cold -- three seconds here, most of
    # it the registry and the artifact shards. Paid in a thread after start
    # rather than by the first panel that asks.
    def warm():
        time.sleep(12)
        try:
            cloud_sync.item_states(last_push=None, known_gids=known_gids())
        except Exception:                                # noqa: BLE001
            pass
    threading.Thread(target=warm, daemon=True,
                     name="barry-syncitems-warm").start()

    cache = {"at": 0.0, "key": None, "body": None}
    guard = threading.Lock()

    def known_gids():
        try:
            return {r.get("gid") for r in (registry.all() or [])
                    if r.get("gid")}
        except Exception:                                # noqa: BLE001
            return None

    @app.route("/api/cloud/items")
    def api_cloud_items():
        """Per record: synced, waiting, or never travels. And why not, when
        the last sync failed. `?kinds=bank,curation` narrows it."""
        kinds = [k for k in (request.args.get("kinds") or "").split(",")
                 if k in cloud_sync.ITEM_KINDS] or list(cloud_sync.ITEM_KINDS)
        c = cloud_sync.cloud
        cfg = {}
        try:
            cfg = c.cfg or {}
        except Exception:                                # noqa: BLE001
            cfg = {}
        try:
            state = c.state() or {}
        except Exception:                                # noqa: BLE001
            state = {}
        last_push = state.get("last_push")
        key = (tuple(kinds), last_push, last.get("at"), last.get("ok"),
               bool(last.get("running")))
        with guard:
            if (cache["key"] == key and cache["body"] is not None
                    and time.time() - cache["at"] < CACHE_S):
                return jsonify(cache["body"])

        configured = bool(getattr(c, "configured", False))
        # The same test the background loop makes before syncing anything.
        enabled = bool(configured and cfg.get("enabled"))
        items = {}
        if enabled:
            items = cloud_sync.item_states(kinds, last_push=last_push,
                                           known_gids=known_gids())
        n_wait = sum(1 for d in items.values() for v in d.values()
                     if v.get("state") == "waiting")
        body = {
            "ok": True,
            # "off": this machine is not connected, so nothing here is
            # shared and saying "waiting" would be a promise nobody keeps.
            "on": enabled,
            "configured": configured,
            "auto": bool(cfg.get("auto")),
            "last_push": last_push,
            "last": {
                "at": last.get("at"), "ok": last.get("ok"),
                "error": last.get("error"),
                "failures": last.get("failures", 0),
                "running": bool(last.get("running")),
                "blocked_note": last.get("blocked_note"),
            },
            "waiting": n_wait,
            "items": items,
        }
        with guard:
            cache.update(at=time.time(), key=key, body=body)
        return jsonify(body)

    return changed
