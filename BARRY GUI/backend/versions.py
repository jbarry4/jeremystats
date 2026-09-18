"""
versions.py -- which version you are working on, and what the next one is.

Curation, layer sheets and event banks all keep a history. Until now that
history was a straight line: every save was the next whole number, and going
back to an earlier one to try something different meant either overwriting
what came after it or keeping a second copy somewhere with a name like
"final_v2_REAL". Neither is a history.

THE RULE, WHICH IS THE WHOLE MODULE

Picking up a version starts a new one from it.

  Pick up the tip of a line, and the next one continues that line.
      v3 is the newest -> the next is v4
  Pick up something with work already after it, and the next one branches.
      v1, with v2 and v3 after it -> the next is v1.1

That is all. Applied again it keeps working without a second rule: v1.1 is
the tip of the v1 line, so picking it up gives v1.2; picking up v1.1 once
v1.2 exists gives v1.1.1.

WHY BRANCH RATHER THAN REFUSE

Going back to an earlier version is not a mistake to be prevented. Somebody
re-curates a recording because the first pass used the wrong channel, or
because a detector was re-run, or because they disagree with a call made six
months ago. What must not happen is that doing so silently destroys the work
that came after -- so it does not become v4, sitting on top of v3 as though
it were later. It becomes v1.1: visibly a second line out of v1, with v2 and
v3 untouched beside it.

WHY THE ID IS A STRING AND THE ORDER IS A TUPLE

"1.10" sorts before "1.9" as text and after it as numbers, and a history
that lists its own versions in the wrong order is worse than one with no
numbers at all. So the id is written as a dotted string because that is what
a person reads, and every comparison goes through `key`, which is the tuple
of integers. `"2"` and `2` mean the same version: the integer histories that
already exist in `layers.py` and `eventbank.py` are dotted ids that never
branched.
"""
from __future__ import annotations

ROOT = "0"


def key(vid):
    """The sort key for a version id. `"1.10"` after `"1.9"`, not before."""
    if vid is None:
        return ()
    if isinstance(vid, (int, float)):
        return (int(vid),)
    out = []
    for part in str(vid).strip().lstrip("vV").split("."):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            # Not a number. Sorts last rather than raising: a history with
            # one odd id in it should still list.
            return (10 ** 9,)
    return tuple(out)


def fmt(parts):
    """A tuple back to the id people read."""
    return ".".join(str(int(p)) for p in parts) or ROOT


def norm(vid):
    """One spelling per version, so `2`, `"2"` and `"v2"` are one thing."""
    k = key(vid)
    return fmt(k) if k else ROOT


def parent(vid):
    """The version this one branched from, or None for the trunk."""
    k = key(vid)
    return fmt(k[:-1]) if len(k) > 1 else None


def is_tip(vid, existing):
    """Whether anything continues this line after it.

    Only siblings count. `v1` with `v1.1` under it is still the tip of the
    trunk if no `v2` exists -- a branch hanging off a version does not make
    that version historical, and treating it as though it did would send
    the next pick-up to v1.2 when it should be v2.
    """
    k = key(vid)
    if not k:
        return True
    have = {key(x) for x in existing}
    return not any(o[:-1] == k[:-1] and o[-1] > k[-1]
                   for o in have if len(o) == len(k))


def children(vid, existing):
    """The versions branched directly off this one."""
    k = key(vid)
    return [x for x in existing
            if len(key(x)) == len(k) + 1 and key(x)[:len(k)] == k]


def next_after(vid, existing):
    """What picking up `vid` should produce.

    The tip of a line continues it; anything else starts a branch off it.
    See the note at the top -- this function is the rule.
    """
    k = key(vid) or (0,)
    have = list(existing or [])
    if is_tip(vid, have):
        # Continue the line. The next number after the highest sibling, not
        # after this one: two people picking up v3 at the same time must not
        # both produce v4.
        sibs = [key(x) for x in have
                if len(key(x)) == len(k) and key(x)[:-1] == k[:-1]]
        top = max([s[-1] for s in sibs] or [k[-1]])
        return fmt(k[:-1] + (top + 1,))
    kids = [key(x) for x in children(vid, have)]
    top = max([c[-1] for c in kids] or [0])
    return fmt(k + (top + 1,))


def newest(ids):
    """The highest version there is, by number.

    What "pick up the latest" means when nobody has said otherwise. By
    number rather than by time on purpose: a branch made yesterday off v1 is
    not a later version of the recording than v3, and offering it as the
    default would quietly hide the trunk.
    """
    got = [x for x in (ids or [])]
    if not got:
        return None
    return sorted(got, key=key)[-1]


def order(ids):
    """Every version, in reading order: a branch after what it came from."""
    return sorted([x for x in (ids or [])], key=key)


def tree(versions, id_of=lambda v: v.get("v")):
    """The history as a list of rows with a depth, for drawing it.

    Flat with a depth rather than nested: the panel draws one row per
    version and indents it, and a nested shape would have to be flattened
    again to do that.
    """
    rows = []
    for v in sorted(versions or [], key=lambda x: key(id_of(x))):
        vid = norm(id_of(v))
        rows.append({
            "v": vid,
            "depth": max(0, len(key(vid)) - 1),
            "parent": parent(vid),
            "rec": v,
        })
    return rows


def describe(vid, existing):
    """What picking this up would do, in the words the panel uses."""
    nxt = next_after(vid, existing)
    if parent(nxt) == parent(norm(vid)):
        return "continues from %s as %s" % (norm(vid), nxt)
    return "branches off %s as %s, leaving what came after it alone" % (
        norm(vid), nxt)


# ==========================================================================
# Lineage labels over a plain integer history
# ==========================================================================
# The Event Bank numbers its versions with an increasing integer, and that
# number is the key the cloud table and the sync are built on -- `version` is
# an integer column and `cloudsync` casts to int. So the stored number stays
# what it is, every version records which one it was BASED ON, and the name
# people say out loud is worked out from that.
#
# The rule is the one at the top of this module, seen from the other side:
#
#   The first version built on X continues X's line.
#   Every version after that built on X is a branch off X.
#
# Which is the same thing. Picking up the tip means nothing is built on it
# yet, so you continue it; picking up an older version means something
# already is, so you branch.
def label_rows(rows, id_of=lambda r: r.get("v"),
               from_of=lambda r: r.get("from_v"),
               at_of=lambda r: r.get("at") or ""):
    """[(row, name)] in creation order, for one entry's whole history.

    Rows rather than a lookup keyed on the version number, because that
    number is NOT unique in real data. Measured on this bank: entry
    7d5fa32206b4 holds seven versions numbered 0,1,2,3,4,3,4 -- two machines
    minted 3 and 4 independently and the union kept both, which is what the
    per-version `id` exists for and is the right outcome. Keyed on the
    number, two of those versions would share a name and a third would
    silently vanish from the list.

    Walked in creation order, because a version's name depends on how many
    others were already built on its parent when it was made. Reordering
    would rename history.
    """
    got = sorted(rows or [], key=lambda r: (_num(id_of(r)), at_of(r)))
    name, kids, used = {}, {}, set()

    def take(want):
        """The name, or the next one along if something already has it.

        Two versions with the same name is worse than an ugly name: the
        history is read to settle which pass a number refers to, and a
        duplicate makes it unanswerable. Collisions only arise from an
        orphan -- a branch that reached this machine before the version it
        came from -- so this is rare and has to be safe rather than pretty.
        """
        k = key(want)
        while fmt(k) in used:
            k = k[:-1] + (k[-1] + 1,)
        out = fmt(k)
        used.add(out)
        return out

    trunk = 0
    out = []
    for r in got:
        vid = id_of(r)
        par = from_of(r)
        if par is None or par not in name:
            # A root. The detector's import is 0 and the first pass is 1, so
            # roots are numbered as they come -- and a version whose parent
            # this machine has never seen is treated as one rather than
            # dropped: a branch can arrive from the cloud before its parent
            # does, and it still has to appear.
            got_name = take(str(trunk))
            trunk = key(got_name)[-1] + 1
        else:
            seen = kids.get(par, 0)
            kids[par] = seen + 1
            base = key(name[par])
            if seen == 0:
                # Nothing was built on the parent yet: continue its line.
                got_name = take(fmt(base[:-1] + (base[-1] + 1,)))
            else:
                # Something already was: branch off it.
                got_name = take(fmt(base + (seen,)))
        # The LAST row with a given number wins the lookup a later row's
        # `from_v` resolves against -- a branch made today off "v3" means
        # the v3 that was there when it was made.
        name[vid] = got_name
        out.append((r, got_name))
    return out


def labels(rows, id_of=lambda r: r.get("v"),
           from_of=lambda r: r.get("from_v")):
    """{version number -> name}. Only safe when the numbers are unique.

    Kept for histories that are known to be clean. Anything reading real
    bank data wants `label_rows`: see the note there on duplicate numbers.
    """
    return {id_of(r): nm for r, nm in label_rows(rows, id_of, from_of)}


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 10 ** 9


def based_on_default(rows, id_of=lambda r: r.get("v")):
    """Which version a fresh pick-up should be based on by default.

    The highest stored id: the newest thing anybody has banked. Not the
    highest LABEL -- "1.10" and "2" are not comparable as lineage, and the
    question being answered is "what did I just see", which is a question
    about time.
    """
    got = [id_of(r) for r in (rows or []) if id_of(r) is not None]
    return max(got, key=_num) if got else None
