# -*- coding: utf-8 -*-
"""family.py -- where a set came from and where it went (PROJECT EVOLVE
phase 2, 2026-11-21: "family tree in the bank and every version picker").

One question, asked of a bank entry or of an artifact: what are its
PARENTS (what it was made from) and its CHILDREN (what was made from it),
and theirs in turn. Worked out on read from what each thing already records
-- a workflow's definition, a bank entry's parameters and `parent`, an X-ray
Many folder's source, a room version's folder, an artifact version's
`inputs` -- and never stored, because a stored tree would go stale the
moment a colleague's branch synced in.

A NODE is {kind, id, name, sub, version, n, archived, ref}. `kind` is one
of: entry, workflow, pool, border, sources, folder, room, xray, cells,
sort, artifact. `ref` says how the page opens it: {entry: id},
{artifact: id, version}, {folder: fid}, {room: artifact id, version}.
A node may carry `children` of its own (a folder's room sets).

Nothing here touches the disk. app.py hands in what it has read.
"""
from __future__ import annotations

KIND_WORDS = {
    "entry": "Bank entry", "workflow": "Root Canal workflow",
    "pool": "Root Canal pool", "border": "Border", "sources": "Sets",
    "folder": "X-ray Many folder", "room": "Extraction Room set",
    "xray": "X-ray bundle", "cells": "Cell curation", "sort": "Kilosort sort",
    "artifact": "Artifact",
}


def _params(row):
    return (((row or {}).get("source") or {}).get("parameters")
            or (row or {}).get("parameters") or {})


def entry_node(row, sub=None):
    row = row or {}
    vers = row.get("versions") or []
    return {"kind": "entry", "id": row.get("id"),
            "name": row.get("name") or row.get("id"),
            "type": row.get("type"),
            "type_name": row.get("type_name") or row.get("type"),
            "sub": sub, "n": row.get("n"),
            "versions": len(vers),
            "archived": bool(row.get("archived")),
            "ref": {"entry": row.get("id")}}


def _art_node(kind, aid, version, name, sub=None, n=None, archived=False):
    return {"kind": kind, "id": aid, "name": name or aid, "sub": sub,
            "version": version, "n": n, "archived": bool(archived),
            "ref": {"artifact": aid, "version": version}}


def _labels_words(labels):
    labs = [str(x.get("label") if isinstance(x, dict) else x)
            for x in (labels or [])]
    return " + ".join(labs)


class Family:
    """Built once per request from what app.py read:

      entries   BANK.summaries() (each with `went_into` attached)
      artifact  fn(aid) -> the artifact record or None
      folders   {fid: folder} X-ray Many's shared folders
      rooms     [artifact summary] of kind `extraction`
      workflows [artifact summary] of kind `rootcanal_workflow`
      defn_of   fn(aid) -> a workflow's current definition, or {}
    """

    def __init__(self, entries, artifact, folders, rooms, workflows,
                 defn_of, curations=()):
        self.entries = list(entries or [])
        self.by_id = {r.get("id"): r for r in self.entries if r.get("id")}
        self.artifact = artifact
        self.folders = {k: v for k, v in (folders or {}).items()
                        if isinstance(v, dict) and not v.get("gone")}
        self.rooms = list(rooms or [])
        self.workflows = list(workflows or [])
        self.defn_of = defn_of
        self.curations = list(curations or [])

    # ------------------------------------------------------------------
    # Pieces
    # ------------------------------------------------------------------
    def _wf_name(self, aid):
        rec = self.artifact(aid) or {}
        return rec.get("nickname") or rec.get("name") or aid

    def workflow_node(self, aid, version, sub=None):
        rec = self.artifact(aid) or {}
        kind = (self.defn_of(aid) or {}).get("kind")
        return _art_node("workflow", aid, version,
                         rec.get("nickname") or rec.get("name") or aid,
                         sub or ({"ds": "Verified DS", "pspike":
                                  "Verified P-spike", "ambiguous": "Ambiguous",
                                  "pca": "Pooled PCA"}.get(kind)),
                         archived=bool(rec.get("deleted")))

    def _ref_node(self, kind, ref, sub=None):
        ref = ref or {}
        aid = ref.get("artifact_id")
        if not aid:
            return None
        rec = self.artifact(aid) or {}
        return _art_node(kind, aid, ref.get("version"),
                         ref.get("nickname") or rec.get("nickname")
                         or rec.get("name") or aid, sub)

    def room_children(self, fid):
        """Every room version taken from folder `fid`, newest first."""
        out = []
        for r in self.rooms:
            room = (r.get("subject") or {}).get("room") or ""
            for v in r.get("versions") or []:
                if (v.get("params") or {}).get("folder") != fid:
                    continue
                ns = v.get("n_summary") or {}
                out.append({"kind": "room", "id": r.get("id"),
                            "name": "%s v%s" % (
                                "Dentate Spike" if room == "dentate_spike"
                                else room, v.get("v")),
                            "sub": ns.get("folder"),
                            "version": v.get("v"),
                            "n": ns.get("events"),
                            "archived": False,
                            "ref": {"room": r.get("id"),
                                    "version": v.get("v")}})
        out.sort(key=lambda x: -(x.get("version") or 0))
        return out

    def folder_node(self, fid, f, why=None):
        src = (f or {}).get("source") or {}
        labs = src.get("labels")
        sub = "reads %s" % ((src.get("label_words") or _labels_words(labs))
                            if labs else "the DS side")
        if why:
            sub += " · " + why
        return {"kind": "folder", "id": fid, "name": f.get("name") or fid,
                "sub": sub, "version": None,
                "archived": bool(f.get("archived")),
                "ref": {"folder": fid},
                "children": self.room_children(fid)}

    def folders_of_run(self, aid, version, entry_id=None):
        """The X-ray Many folders that read this run (or this entry)."""
        out = []
        for fid, f in sorted(self.folders.items(),
                             key=lambda kv: str(kv[1].get("at") or "")):
            src = f.get("source") or {}
            if entry_id and src.get("entry_id") == entry_id:
                out.append(self.folder_node(fid, f))
            elif (src.get("artifact_id") == aid
                  and (version is None
                       or int(src.get("version") or 0) == int(version or 0))
                  and not (entry_id and src.get("entry_id"))):
                out.append(self.folder_node(
                    fid, f, None if entry_id is None else
                    "reads the same run, made before bundles"))
        return out

    # ------------------------------------------------------------------
    # A bank entry
    # ------------------------------------------------------------------
    def of_entry(self, entry_id):
        row = self.by_id.get(entry_id)
        if not row:
            raise KeyError("There is no bank entry %s." % entry_id)
        prm = _params(row)
        parents, children = [], []

        par = row.get("parent") or prm.get("parent")
        if isinstance(par, dict) and par.get("entry_id"):
            p = self.by_id.get(par["entry_id"])
            node = entry_node(p) if p else {
                "kind": "entry", "id": par["entry_id"],
                "name": par.get("name") or par["entry_id"],
                "ref": {"entry": par["entry_id"]}, "archived": False}
            node["sub"] = "branched from %s%s" % (
                par.get("version_label") or (
                    "v%s" % par["version"] if par.get("version") else
                    "its newest version"),
                (", labels " + _labels_words(par.get("labels")))
                if par.get("labels") else "")
            parents.append(node)

        if prm.get("tool") == "rootcanal_workflow":
            wf = prm.get("workflow") or {}
            if wf.get("artifact_id"):
                parents.append(self.workflow_node(
                    wf["artifact_id"], wf.get("version")))
            t = self._ref_node("pool", prm.get("target"), "target pool")
            if t:
                parents.append(t)
            srcs = prm.get("sources") or []
            if srcs:
                parents.append({
                    "kind": "sources", "id": None,
                    "name": "%d recording%s' sets" % (
                        len(srcs), "" if len(srcs) == 1 else "s"),
                    "sub": ", ".join(str(s.get("session_label") or
                                         s.get("entry_id")) for s in srcs[:6])
                           + (" and %d more" % (len(srcs) - 6)
                              if len(srcs) > 6 else ""),
                    "n": sum(int(s.get("n") or 0) for s in srcs),
                    "ref": None, "archived": False})
        if prm.get("tool") == "cells":
            cur = prm.get("curation") or {}
            if cur.get("artifact_id"):
                parents.append(_art_node(
                    "cells", cur["artifact_id"], cur.get("version"),
                    "Cell curation v%s" % cur.get("version"),
                    cur.get("source_name")))
            if prm.get("run"):
                parents.append({"kind": "sort", "id": prm.get("run_dir"),
                                "name": prm.get("run"),
                                "sub": prm.get("run_dir"), "ref": None,
                                "archived": False})

        # Children: entries branched out of it.
        for r in self.entries:
            p = r.get("parent") or _params(r).get("parent")
            if isinstance(p, dict) and p.get("entry_id") == entry_id:
                children.append(entry_node(r, "branched by hand%s" % (
                    (", labels " + _labels_words(p.get("labels")))
                    if p.get("labels") else "")))
        # Where its events went (Root Canal entries, X-ray bundles).
        seen = set()
        for w in row.get("went_into") or []:
            if w.get("kind") == "xray":
                key = ("xray", w.get("artifact_id"))
                if key in seen:
                    continue
                seen.add(key)
                children.append(_art_node(
                    "xray", w.get("artifact_id"), w.get("version"),
                    w.get("name") or w.get("artifact_id"),
                    "X-ray bundle"))
            else:
                key = ("entry", w.get("entry_id"))
                if key in seen:
                    continue
                seen.add(key)
                r = self.by_id.get(w.get("entry_id"))
                node = entry_node(r) if r else {
                    "kind": "entry", "id": w.get("entry_id"),
                    "name": w.get("name") or w.get("entry_id"),
                    "ref": {"entry": w.get("entry_id")}, "archived": False}
                node["sub"] = "%s events went in%s" % (
                    w.get("n") if w.get("n") is not None else "Its",
                    (" (workflow ‘%s’)" % w["workflow"])
                    if w.get("workflow") else "")
                children.append(node)
        # X-ray Many folders that read it -- or, made before bundles, the
        # same workflow run it was banked from.
        if prm.get("tool") == "rootcanal_workflow":
            wf = prm.get("workflow") or {}
            children.extend(self.folders_of_run(
                wf.get("artifact_id"), wf.get("version"), entry_id))
        else:
            for fid, f in self.folders.items():
                if (f.get("source") or {}).get("entry_id") == entry_id:
                    children.append(self.folder_node(fid, f))
        return {"self": entry_node(row), "parents": parents,
                "children": children}

    # ------------------------------------------------------------------
    # An artifact
    # ------------------------------------------------------------------
    def of_artifact(self, aid, version=None):
        rec = self.artifact(aid)
        if not rec:
            raise KeyError("There is no artifact %s." % aid)
        kind = rec.get("kind")
        name = rec.get("nickname") or rec.get("name") or aid
        parents, children = [], []
        me = _art_node("artifact", aid, version or rec.get("version"), name,
                       KIND_WORDS.get(kind) or kind)

        if kind == "rootcanal_workflow":
            me["kind"] = "workflow"
            d = self.defn_of(aid) or {}
            t = self._ref_node("pool", d.get("target"), "target pool")
            if t:
                parents.append(t)
            for p in d.get("pools") or []:
                n = self._ref_node("pool", p, "pool")
                if n:
                    parents.append(n)
            src = d.get("source") or {}
            if src.get("type") == "pool":
                n = self._ref_node("pool", src, "border drawn around")
                if n:
                    parents.append(n)
            for k, ref in (d.get("uses") or {}).items():
                n = self._ref_node("workflow", ref, "%s border" % (
                    "DS" if k == "ds" else "P-spike"))
                if n:
                    parents.append(n)
            for r in self.entries:
                wf = _params(r).get("workflow") or {}
                if _params(r).get("tool") == "rootcanal_workflow" and \
                        wf.get("artifact_id") == aid:
                    children.append(entry_node(r, "banked from v%s" %
                                               wf.get("version")))
            children.extend(self.folders_of_run(aid, None))
            # Workflows that use this one's border.
            for w in self.workflows:
                if w.get("id") == aid:
                    continue
                d2 = self.defn_of(w.get("id")) or {}
                for k, ref in (d2.get("uses") or {}).items():
                    if (ref or {}).get("artifact_id") == aid:
                        children.append(self.workflow_node(
                            w["id"], (self.artifact(w["id"]) or {})
                            .get("version"), "uses its border"))
        elif kind == "xray_single":
            me["kind"] = "xray"
            sub = rec.get("subject") or {}
            f = self.folders.get(sub.get("folder"))
            if f:
                node = self.folder_node(sub["folder"], f)
                node.pop("children", None)
                parents.append(node)
            for r in self.rooms:
                for v in r.get("versions") or []:
                    if any((i or {}).get("artifact_id") == aid
                           for i in v.get("inputs") or []
                           if isinstance(i, dict)):
                        children.append({
                            "kind": "room", "id": r.get("id"),
                            "name": "Dentate Spike v%s" % v.get("v"),
                            "version": v.get("v"), "archived": False,
                            "sub": (v.get("n_summary") or {}).get("folder"),
                            "ref": {"room": r.get("id"),
                                    "version": v.get("v")}})
        elif kind == "extraction":
            me["kind"] = "room"
            seen = set()
            for v in rec.get("versions") or []:
                fid = (v.get("params") or {}).get("folder")
                if fid and fid not in seen and fid in self.folders:
                    seen.add(fid)
                    node = self.folder_node(fid, self.folders[fid])
                    node.pop("children", None)
                    parents.append(node)
        elif kind == "cell_curation":
            me["kind"] = "cells"
            sub = rec.get("subject") or {}
            parents.append({"kind": "sort", "id": sub.get("run_dir"),
                            "name": sub.get("run"), "sub": sub.get("run_dir"),
                            "ref": None, "archived": False})
            for r in self.entries:
                cur = _params(r).get("curation") or {}
                if _params(r).get("tool") == "cells" and \
                        cur.get("artifact_id") == aid:
                    children.append(entry_node(
                        r, "banked from v%s" % cur.get("version")))
        else:
            cur = None
            for v in rec.get("versions") or []:
                if version is None or str(v.get("v")) == str(version):
                    cur = v
            for i in (cur or {}).get("inputs") or []:
                if isinstance(i, dict) and i.get("artifact_id"):
                    n = self._ref_node("artifact", i)
                    if n:
                        parents.append(n)
            # Workflows whose definition names this pool or border.
            for w in self.workflows:
                d2 = self.defn_of(w.get("id")) or {}
                refs = [d2.get("target")] + list(d2.get("pools") or []) + [
                    d2.get("source")]
                if any((x or {}).get("artifact_id") == aid for x in refs):
                    children.append(self.workflow_node(
                        w["id"], (self.artifact(w["id"]) or {})
                        .get("version"), "reads it"))
        return {"self": me, "parents": parents, "children": children}
