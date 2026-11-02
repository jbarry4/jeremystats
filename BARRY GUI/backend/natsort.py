"""One order for names with numbers in them (2026-10-20).

"m1, m3, m5, m12" -- never "m1, m12, m3, m34, m5". The user, of every list of
recordings: "we generally want things to be numerical and in ascending
order". Every list the server sorts by a name goes through `key`, as every
list the page sorts by one goes through ui.js `natCompare`, and the two agree:
case is ignored, a run of digits compares as its number, and digits sort
before letters where one name has a number and the other a word.

A list in time order, or ranked by a count, keeps that order. This is the
order for names: recordings, mice, sessions, rats (J2 before J10), channels
(CSC9 before CSC10), sets and nicknames.
"""

from __future__ import annotations

import re

_DIGITS = re.compile(r"(\d+)")


def key(s):
    """A sort key for one name. Numbers compare by value ("m3" < "m12"),
    words case-folded; a tie in value ("01" against "1") falls back to the
    text, so the order is total."""
    out = []
    for i, part in enumerate(_DIGITS.split(str("" if s is None else s)
                                           .casefold())):
        if i % 2:
            out.append((0, int(part), part))
        elif part:
            out.append((1, 0, part))
    return tuple(out)


def keys(*names):
    """A key for several names compared in turn: keys(project, label)."""
    return tuple(key(n) for n in names)


def sort(items, by=None, reverse=False):
    """`items` sorted by the name `by(item)` gives (the item itself if no
    `by`), as a new list."""
    get = by or (lambda x: x)
    return sorted(items, key=lambda x: key(get(x)), reverse=reverse)
