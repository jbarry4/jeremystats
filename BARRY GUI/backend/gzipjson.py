"""Large JSON answers, gzipped for a browser that asks for it.

The registry answer is 2.2 MB of JSON: nothing on the lab network, and
seconds over the VPN on a laptop, which is where the Sessions view felt slow.
At level 5 it is 103 kB and costs 8 ms (measured 2026-09-30 on the cached
registry). The browser decompresses it transparently, so no page changes.

Only JSON, only above MIN_BYTES, only when the request says `Accept-Encoding:
gzip`, and never a file (`send_file` responses are direct passthrough) or a
stream. A test client sends no Accept-Encoding, so tools reading `.data` see
exactly what they saw before.
"""
from __future__ import annotations

import gzip

MIN_BYTES = 64 * 1024
LEVEL = 5


def install(app):
    from flask import request

    @app.after_request
    def _gzip_large_json(resp):
        try:
            if (resp.direct_passthrough or resp.is_streamed
                    or resp.status_code < 200 or resp.status_code >= 300
                    or "Content-Encoding" in resp.headers
                    or (resp.mimetype or "") != "application/json"
                    or "gzip" not in (request.headers.get("Accept-Encoding")
                                      or "").lower()):
                return resp
            body = resp.get_data()
            if len(body) < MIN_BYTES:
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
