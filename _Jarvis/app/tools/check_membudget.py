# -*- coding: utf-8 -*-
"""Check backend/membudget.py: one byte budget, oldest-used first, across
every cache that registers.

    python tools/check_membudget.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import membudget as mb  # noqa: E402

fails = 0


def check(what, ok, note=""):
    global fails
    if not ok:
        fails += 1
    print(("ok    " if ok else "FAIL  ") + what + (("   [%s]" % note) if note and not ok else ""))


class Fake:
    """A cache: key -> (nbytes, last_used)."""

    def __init__(self, rows):
        self.rows = dict(rows)

    def items(self):
        return [(k, n, t) for k, (n, t) in self.rows.items()]

    def drop(self, k):
        self.rows.pop(k, None)


def main():
    MB = mb.MB
    ram = mb.total_ram()
    check("the machine's memory is known", bool(ram and ram > 512 * MB), ram)
    proc = mb.process_memory()
    check("this process's memory is known", bool(proc.get("rss")), proc)

    full = mb.budget()
    check("the budget is between 256 MB and 1 GB", mb.FLOOR <= full <= mb.CEILING,
          full // MB)
    mb.set_light(True)
    check("Jarvis Light halves it", mb.budget() == full // 2, mb.budget() // MB)
    mb.set_light(False)

    a = Fake({"a1": (300 * MB, 10), "a2": (300 * MB, 40)})
    b = Fake({"b1": (300 * MB, 20), "b2": (300 * MB, 50)})
    mb._CACHES.clear()
    mb.register("a", a.items, a.drop)
    mb.register("b", b.items, b.drop)
    orig = mb.budget
    mb.budget = lambda: 700 * MB
    try:
        freed = mb.settle()
        left = sorted(list(a.rows) + list(b.rows))
        check("evicts across caches until under budget", mb.used() <= 700 * MB,
              mb.used() // MB)
        check("oldest-used first, whichever cache it is in", left == ["a2", "b2"], left)
        check("says how much it freed", freed == 600 * MB, freed // MB)
        check("does nothing when already under", mb.settle() == 0)

        def broken():
            raise RuntimeError("no")
        mb.register("broken", broken, lambda k: None)
        check("a cache that cannot answer does not stop the rest", mb.settle() == 0)
        rep = mb.report()
        check("the report lists every cache", set(rep["caches"]) >= {"a", "b", "broken"},
              list(rep["caches"]))
        check("and the process", rep["process"].get("rss") is not None, rep["process"])
    finally:
        mb.budget = orig
        mb._CACHES.clear()

    print("\n%d failed" % fails if fails else "\nall passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
