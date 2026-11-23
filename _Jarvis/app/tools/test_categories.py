# -*- coding: utf-8 -*-
"""Categories added in Spotter: one vocabulary across every set. Offline.

    python tools/test_categories.py

Run against a throwaway store in a temp folder -- never the lab's: a
category added is added for good, and a harness that made one would leave
it in everybody's Spotter.

What is guarded:

  * an added category is in the kind's vocabulary, after the built-in four,
    with the next free digit as its key and the colour asked for;
  * a set made BEFORE the category existed offers it, and can be labelled
    with it -- and then carries it in its own `labels`, which is what takes
    it to other computers through the cloud sync;
  * a category carried only by a set (one that arrived through the sync,
    with nothing in this machine's store) is still offered everywhere;
  * a second category with the same name, any case, is refused, and so is a
    colour that is not one, and a name that is empty or too long;
  * keys run 5, 6, 7, 8, 9, 0 and then there are none left;
  * the dentate-spike vocabulary is not touched;
  * an id never collides with a built-in one ("Garbage!" is not `garbage`).
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import curation as C  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-70s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


def refused(fn):
    try:
        fn()
    except C.CurationError as e:
        return str(e)
    return None


def main():
    tmp = tempfile.mkdtemp(prefix="jarvis-categories-")
    try:
        cur = C.Curation(tmp, None)
        print("\nadding one")
        before = cur.create("g-old", "ied", [{"start": 1.0}, {"start": 2.0}],
                            name="made before")
        lab = cur.add_category("ied", "Polyspike", "#7B3FA0", True)
        ids = [l["id"] for l in C.vocabulary("ied")]
        check("it is in the vocabulary, after the built-in four",
              ids[:4] == ["solid", "sputter", "garbage", "flag"]
              and ids[4] == "polyspike", ids)
        check("on key 5", lab.get("keys") == ["5"], lab.get("keys"))
        check("with the colour asked for, lower-cased",
              lab.get("color") == "#7b3fa0", lab.get("color"))
        check("marked as added, and as an IED when asked",
              lab.get("custom") is True and lab.get("good") is True, lab)

        print("\nevery set offers it")
        rec = cur.get("g-old", "ied")
        check("a set made before it existed offers it",
              "polyspike" in [l["id"] for l in rec["labels"]],
              [l["id"] for l in rec["labels"]])
        eid = rec["events"][0]["id"]
        ev, prog = cur.label("g-old", "ied", eid, "polyspike")
        check("and can be labelled with it",
              ev.get("label") == "polyspike"
              and prog["by_label"].get("polyspike") == 1, prog)
        raw = cur._read("g-old", "ied")
        check("and then carries it in its own labels, for the sync",
              "polyspike" in [l["id"] for l in raw.get("labels") or []])
        n, _ = cur.label_many("g-old", "ied",
                              {rec["events"][1]["id"]: "polyspike"})
        check("label_many takes it too", n == 1, n)
        check("an unknown label is still refused",
              bool(refused(lambda: cur.label("g-old", "ied", eid, "nope"))))

        print("\none that arrived only through a set")
        new = cur.create("g-new", "ied", [{"start": 5.0}], name="carries one")
        r2 = cur._read("g-new", "ied")
        r2["labels"] = list(r2["labels"]) + [{
            "id": "spike-wave", "name": "Spike and wave", "color": "#e11d48",
            "keys": ["6"], "custom": True}]
        cur._write(r2)
        cur._custom_memo.clear()
        check("is offered on every other set",
              "spike-wave" in [l["id"] for l in cur.get("g-old", "ied")["labels"]])
        check("and is in the vocabulary",
              "spike-wave" in [l["id"] for l in C.vocabulary("ied")])

        print("\nwhat is refused")
        check("the same name in another case",
              refused(lambda: cur.add_category("ied", "polyspike", "#123456"))
              == "There is already a category called Polyspike.")
        check("a built-in name",
              bool(refused(lambda: cur.add_category("ied", "garbage", "#123456"))))
        check("a colour that is not one",
              bool(refused(lambda: cur.add_category("ied", "Odd", "red"))))
        check("no name",
              bool(refused(lambda: cur.add_category("ied", "   ", "#123456"))))
        check("a name longer than a button",
              bool(refused(lambda: cur.add_category("ied", "x" * 40, "#123456"))))
        bang = cur.add_category("ied", "Garbage!", "#222222")
        check("an id never collides with a built-in one",
              bang["id"] != "garbage" and bang["id"].startswith("garbage"),
              bang["id"])

        print("\nkeys")
        made = [cur.add_category("ied", "K%d" % i, "#10101%d" % i)
                for i in range(4)]
        keys = [k[0] for k in (l["keys"] for l in C.vocabulary("ied")
                               if l.get("custom")) if k]
        # The one that arrived through a set already held 6, so the next
        # ones took 7, 8, 9, 0 -- every digit once, none twice.
        check("they use 5 6 7 8 9 0, each once",
              sorted(keys) == sorted(["5", "6", "7", "8", "9", "0"]), keys)
        last = cur.add_category("ied", "No key left", "#303030")
        check("and then there are none left", last["keys"] == [], last)

        print("\nthe other vocabulary")
        check("dentate spikes are untouched",
              [l["id"] for l in C.vocabulary("ds")]
              == [l["id"] for l in C.KINDS["ds"]["labels"]])
        _ = (before, new, made)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
