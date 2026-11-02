"""Large JSON answers, gzipped for a browser that asks for it -- and tagged,
so an unchanged one is not sent at all.

The registry answer is 2.2 MB of JSON: nothing on the lab network, and
seconds over the VPN on a laptop, which is where the Sessions view felt slow.
At level 5 it is 103 kB and costs 8 ms (measured 2026-09-30 on the cached
registry). The browser decompresses it transparently, so no page changes.

Only JSON, only above MIN_BYTES, only when the request says `Accept-Encoding:
gzip`, and never a file (`send_file` responses are direct passthrough) or a
stream. A test client sends no Accept-Encoding, so tools reading `.data` see
exactly what they saw before.

THE TAG (2026-10-21). Every GET answer under /api/ of at least ETAG_MIN
bytes carries an ETag, a hash of its body. A page that sends it back as
`If-None-Match` (web/js/data.js does, for every list it keeps) is answered
304 with no body when nothing has changed: nothing to send, nothing to
parse, nothing to redraw. Nothing that does not send it sees any difference.
"""
from __future__ import annotations

import gzip
import hashlib

MIN_BYTES = 64 * 1024
LEVEL = 5
ETAG_MIN = 1024


def _etag(body):
    return 'W/"%s"' % hashlib.sha1(body).hexdigest()[:20]


def _matches(header, tag):
    if not header:
        return False
    if header.strip() == "*":
        return True
    return tag in [t.strip() for t in header.split(",")]


def install(app):
    from flask import request

    @app.after_request
    def _gzip_large_json(resp):
        try:
            if (resp.direct_passthrough or resp.is_streamed
                    or resp.status_code < 200 or resp.status_code >= 300
                    or "Content-Encoding" in resp.headers
                    or (resp.mimetype or "") != "application/json"):
                return resp
            body = resp.get_data()
            if (request.method == "GET" and request.path.startswith("/api/")
                    and len(body) >= ETAG_MIN):
                tag = _etag(body)
                resp.headers["ETag"] = tag
                if _matches(request.headers.get("If-None-Match"), tag):
                    resp.status_code = 304
                    resp.set_data(b"")
                    return resp
            if ("gzip" not in (request.headers.get("Accept-Encoding")
                               or "").lower()
                    or len(body) < MIN_BYTES):
                return resp
            resp.set_data(gzip.compress(body, LEVEL))
            resp.headers["Content-Encoding"] = "gzip"
            resp.headers["Content-Length"] = str(len(resp.get_data()))
            vary = resp.headers.get("Vary")
            resp.headers["Vary"] = (vary + ", Accept-Encoding") if vary \
                else "Accept-Encoding"
        except Exception:                                # noqa: BLE001
            pass                                         # never break an answer
        return resp
