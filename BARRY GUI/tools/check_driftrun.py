# -*- coding: utf-8 -*-
"""Does Drift's orchestration file what drift.build says, pinned and cited?

backend/driftrun.py turns two groups of circuit ARTIFACTS into a filed Drift
artifact. This drives the real routes (Flask's test client on backend.app,
the real ARTIFACTS store) on circuits it makes itself from the two real
fixtures -- J7 s1 Click -> High tone and J4 s2 High tone -> Noise, built by
backend/circuit.py -- on `harness-` gids through /api/artifacts/_test/make,
and checks:

  1. the member list: every harness circuit, its versions, n_pairs, the
     params digest, and -- given a chosen set -- compatible / cue-only /
     why, in words;
  2. the pre-flight: compatible sets pass with a cost stated first;
     incompatible ones are refused naming the field (low, kind, cue_type,
     both sides); a cue-type-only refusal offers the equivalence;
  3. a local run: the filed payload is EXACTLY drift.build on the same
     pinned payloads (the route adds nothing and loses nothing); inputs are
     pinned by version_id and each is CITED; a cited circuit's delete is
     refused with a sentence naming the drift; an older version can be
     pinned while a newer one exists;
  4. re-running the same members in another order confirms rather than
     adding a version; the cue-equivalence choice is recorded, shown and
     carried (re-stating it confirms); a k = 1 side is labelled;
  5. `--vacc`: one real run on the cluster (cost stated first), its payload
     digest equal to the local one, so it CONFIRMS; cancelled if it does not
     land inside the deadline.

Negative controls (`--break`, monkeypatches in this process only):
  cite   filing does not cite       -> the citation and delete checks FAIL
  pin    inputs pinned by number    -> the version_id checks FAIL
  sort   member order kept as given -> the re-run-confirms check FAILS

Everything it makes is erased in a `finally`, drifts first, then circuits
(citations point from drifts to circuits), and the erasure is checked.

Run (PowerShell):  python tools\\check_driftrun.py [--break cite|pin|sort] [--vacc]
"""
import copy
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

FAILED = []
PASSED = [0]


def ck(name, ok, detail=""):
    print("  %-5s %s%s" % ("ok" if ok else "FAIL", name,
                           ("   [%s]" % detail) if detail and not ok else ""))
    if ok:
        PASSED[0] += 1
    else:
        FAILED.append(name)


FIX = os.path.join(APP, "web", "_dev", "fixtures")
TAG = "harness-drift-%s" % hex(int(time.time()))[2:]


def load(name):
    with open(os.path.join(FIX, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def derive(base, i, off=0.0, scale=1.0, label=None):
    """A schema-valid synthetic circuit from a real one, on a harness gid:
    every value v -> v * scale + off (so the mean moves the same way and the
    SD scales), per-cell offsets so recordings differ."""
    P = copy.deepcopy(base)
    gid = "%s-%s%d" % (TAG, label or "c", i)
    P["source"] = dict(P["source"], gid=gid,
                       session_label="HARNESS %s (from %s)"
                       % (gid, base["source"]["session_label"]))
    P["computed_on"] = {"kind": "local", "harness": True}
    k = 0
    for w in P["windows"]:
        for m in P["methods"]:
            for key, c in P["cells"][w][m].items():
                k += 1
                o = off + ((k * 7 + i * 3) % 5 - 2) * 0.004
                for x in c["values"]:
                    x["v"] = x["v"] * scale + o
                vs = [x["v"] for x in c["values"]]
                c["mean"] = sum(vs) / len(vs)
                if c.get("sd") is not None and len(vs) > 1:
                    mu = c["mean"]
                    c["sd"] = (sum((v - mu) ** 2 for v in vs)
                               / (len(vs) - 1)) ** 0.5
    return P


def subject_of(P, mouse, phase_n):
    return {"gid": P["source"]["gid"], "project": "DEWEY", "mouse": mouse,
            "session": phase_n, "phase": "Precon", "phase_n": phase_n,
            "run": "SPC", "session_label": P["source"]["session_label"],
            "cue_type": P["cue_type"], "cue_label": P["cue_label"],
            "window_kind": P["kind"]}


def main():
    brk = sys.argv[sys.argv.index("--break") + 1] if "--break" in sys.argv \
        else None
    want_vacc = "--vacc" in sys.argv

    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    from backend import app as appmod
    from backend import cfc, drift, driftrun
    A = appmod.ARTIFACTS
    client = appmod.app.test_client()

    if brk == "cite":
        A_cite = A.cite
        A.cite = lambda *a, **k: None
        print("*** NEGATIVE CONTROL: filing does not cite -- checks SHOULD "
              "fail ***")
    elif brk == "pin":
        orig_pin = driftrun._pin

        def pin_by_number(host, ref, side):
            got = orig_pin(host, ref, side)
            got["ref"] = dict(got["ref"], version_id=None)
            return got
        driftrun._pin = pin_by_number
        print("*** NEGATIVE CONTROL: inputs pinned by number only -- checks "
              "SHOULD fail ***")
    elif brk == "sort":
        def unsorted_pins(host, refs, side):
            return [driftrun._pin(host, r, side) for r in (refs or [])]
        driftrun._pins = unsorted_pins
        print("*** NEGATIVE CONTROL: member order kept as given -- checks "
              "SHOULD fail ***")
    elif brk:
        raise SystemExit("unknown --break %r" % brk)

    circuits, drifts = [], []

    def post(url, body):
        r = client.post(url, json=body)
        return r.status_code, r.get_json()

    def get(url):
        r = client.get(url)
        return r.status_code, r.get_json()

    def make(P, mouse, phase_n, nickname=None):
        code, j = post("/api/artifacts/_test/make", {
            "kind": "circuit", "payload": P,
            "subject": subject_of(P, mouse, phase_n),
            "params": P["params"], "nickname": nickname,
            "inputs": [{"kind": "bank", "entry": "harness", "version": 1}]})
        if not (j or {}).get("ok"):
            raise SystemExit("could not make a harness circuit: %s" % j)
        a = j["artifact"]
        if a["id"] not in circuits:
            circuits.append(a["id"])
        cur = a["current"]
        return {"id": a["id"], "version": cur["v"], "version_id": cur["id"],
                "digest": cur["digest"], "name": a["name"],
                "nickname": a.get("nickname")}

    def wait(job_id, limit=120.0):
        t0 = time.time()
        while time.time() - t0 < limit:
            j = cfc.get(job_id)
            if j is not None and j.status in ("done", "failed", "canceled"):
                return j
            time.sleep(0.1)
        return cfc.get(job_id)

    def run(left, right, labels=("Precon1", "Precon4"), eq=None,
            where="local", nickname=None, limit=120.0):
        body = {"left": [{"id": x["id"], "version_id": x["version_id"]}
                         for x in left],
                "right": [{"id": x["id"], "version_id": x["version_id"]}
                          for x in right],
                "labels": {"left": labels[0], "right": labels[1]},
                "where": where}
        if eq is not None:
            body["cue_equivalence"] = eq
        if nickname:
            body["nickname"] = nickname
        code, j = post("/api/arc/drift/run", body)
        if code != 200:
            return code, j, {"_refused": (j or {}).get("error")}
        job = wait(j["job"], limit)
        res = job.result if job and job.status == "done" else None
        if res and res.get("artifact_id") and res["artifact_id"] not in drifts:
            drifts.append(res["artifact_id"])
        return code, j, (res if res else {"_job": job and job.snapshot()})

    try:
        A7 = load("circuit_s360e48254222.json")     # Click -> High tone
        A4 = load("circuit_s56104b75ad01.json")     # High tone -> Noise
        print("fixtures: %s (%s), %s (%s)" % (
            A7["source"]["session_label"], A7["cue_label"],
            A4["source"]["session_label"], A4["cue_label"]))

        print("\n1. harness circuits (from the two real fixtures)")
        L = [make(derive(A7, i, 0.0, 1.0, "L"), 7, 1, None) for i in range(3)]
        R = [make(derive(A7, i, 0.03, 1.0, "R"), 7, 4,
                  "harness right %d" % i) for i in range(3)]
        B = [make(derive(A4, i, 0.0, 1.0, "B"), 4, 2) for i in range(2)]
        low = derive(A7, 9, 0.0, 1.0, "low")
        low["params"] = dict(low["params"], low=6.0)
        LOW = make(low, 7, 2)
        tr = derive(A7, 8, 0.0, 1.0, "tr")
        tr["kind"] = "transition"
        tr["params"] = dict(tr["params"], kind="transition",
                            before_s=1.0, after_s=2.0)
        tr["windows"] = ["onset", "switch", "offset"]
        tr["cells"] = {"onset": tr["cells"]["pre"],
                       "switch": tr["cells"]["cue1"],
                       "offset": tr["cells"]["cue2"]}
        tr["region_usable"] = {"onset": tr["region_usable"]["pre"],
                               "switch": tr["region_usable"]["cue1"],
                               "offset": tr["region_usable"]["cue2"]}
        TR = make(tr, 7, 3)
        # A second version of L[0]: the member list must offer both, and a
        # drift must be able to pin the OLDER one.
        L0v2 = make(derive(A7, 0, 0.01, 1.0, "L"), 7, 1)
        ck("made %d harness circuits; L0 now has v1 and v2 (%s, %s)"
           % (len(circuits), L[0]["version_id"], L0v2["version_id"]),
           len(circuits) == 10 and L0v2["id"] == L[0]["id"]
           and L0v2["version"] == 2)

        print("\n2. the member list")
        code, j = get("/api/arc/drift/circuits?kind=state")
        rows = {r["artifact_id"]: r for r in (j or {}).get("rows") or []}
        mine = [rows.get(c) for c in circuits]
        ck("every harness state circuit is listed (the transition one is "
           "filtered out by kind=state)",
           all(rows.get(x["id"]) for x in L + R + B + [LOW])
           and TR["id"] not in rows)
        r0 = rows.get(L[0]["id"]) or {}
        ck("L0 lists both versions, current first, each with n_pairs and a "
           "params digest",
           [v["v"] for v in r0.get("versions") or []] == [2, 1]
           and all(v["n_pairs"] == 8 and v["params_digest"]
                   for v in r0.get("versions") or []))
        ck("rows carry cue type, kind, n_pairs and a group (rat + phase): %s"
           % r0.get("group"),
           r0.get("cue_type") == "Click_HighTone" and r0.get("kind") == "state"
           and r0.get("n_pairs") == 8 and r0.get("group") == "DEWEY r7 Precon1")
        ck("groups come in order with their ids",
           any(L[0]["id"] in g["ids"] for g in (j or {}).get("groups") or []))
        code, j = get("/api/arc/drift/circuits?kind=state&cue_type="
                      "HighTone_Noise")
        ids = {r["artifact_id"] for r in (j or {}).get("rows") or []}
        ck("cue_type narrows the list", B[0]["id"] in ids
           and L[0]["id"] not in ids)
        code, j = get("/api/arc/drift/circuits?with=%s@%s" % (
            L[1]["id"], L[1]["version_id"]))
        rows = {r["artifact_id"]: r for r in (j or {}).get("rows") or []}
        ck("with a chosen set: a same-kind same-params circuit is compatible",
           rows[R[0]["id"]]["compatible"] is True)
        ck("  a different pairing is marked cue-only, in words: %s"
           % rows[B[0]["id"]]["why"],
           rows[B[0]["id"]]["compatible"] is False
           and rows[B[0]["id"]]["cue_only"] is True
           and "High tone → Noise" in rows[B[0]["id"]]["why"][0])
        ck("  other parameters are not compatible, and not cue-only: %s"
           % rows[LOW["id"]]["why"],
           rows[LOW["id"]]["compatible"] is False
           and not rows[LOW["id"]]["cue_only"])
        ck("  another kind is said: %s" % rows[TR["id"]]["why"],
           rows[TR["id"]]["compatible"] is False
           and "transition" in rows[TR["id"]]["why"][0])

        print("\n3. the pre-flight")
        ref = lambda xs: [{"id": x["id"], "version_id": x["version_id"]}
                          for x in xs]
        code, c = post("/api/arc/drift/check", {"left": ref(L), "right":
                                                ref(R)})
        ck("3 v 3 of one pairing is compatible", code == 200
           and c["compatible"] and not c["reasons"], c and c.get("reasons"))
        ck("  the cost is stated first: %s" % c["cost"]["sentence"],
           c["cost"]["n_circuits"] == 6 and c["cost"]["n_cells"] == 66 * 4 * 3
           and "here" in c["cost"]["sentence"])
        ck("  the members come back pinned (version and version_id)",
           [m["version_id"] for m in c["members"]["left"]]
           == [x["version_id"] for x in sorted(
               L, key=lambda x: (x["id"], x["version_id"]))])
        code, c = post("/api/arc/drift/check", {"left": ref(L + [LOW]),
                                                "right": ref(R)})
        s = next((x for x in c["reasons"] if " low " in x), "")
        ck("a circuit at another low cut-off is refused naming low: %s" % s,
           not c["compatible"] and bool(s) and not c["cue_only"])
        code, c = post("/api/arc/drift/check", {"left": ref(L),
                                                "right": ref([TR])})
        ck("a transition circuit against state ones is refused naming kind",
           not c["compatible"] and any("kind" in x for x in c["reasons"]))
        code, c = post("/api/arc/drift/check", {"left": ref(L),
                                                "right": ref(B)})
        s = next((x for x in c["reasons"] if "cue_type" in x), "")
        ck("two pairings are refused with a sentence naming both: %s" % s,
           not c["compatible"] and "Click → High tone" in s
           and "High tone → Noise" in s)
        ck("  and the check says the equivalence is the only way through: %s"
           % c["suggest"], c["cue_only"] and c["suggest"]
           == [{"from": "Click_HighTone", "to": "HighTone_Noise"}])
        code, c = post("/api/arc/drift/check", {"left": ref(L),
                                                "right": ref(B),
                                                "cue_equivalence":
                                                c["suggest"]})
        ck("  with it, they are compatible", c["compatible"], c["reasons"])
        code, c = post("/api/arc/drift/check", {"left": ref(L),
                                                "right": ref([L[1]])})
        ck("the same circuit version on both sides is refused",
           not c["compatible"] and any("both sides" in x
                                       for x in c["reasons"]))
        code, c = post("/api/arc/drift/check", {"left": ref(L[:1]),
                                                "right": ref(R)})
        ck("a k = 1 side is said in the pre-flight: %s" % c["warn"],
           any(drift.K1_SAY in w for w in c["warn"]))

        print("\n4. a local run")
        code, j, res = run(L, R, nickname="harness drift")
        ck("the run starts (200) and lands", code == 200 and res
           and res.get("artifact_id"), j if code != 200 else res.get("_job"))
        if not res or not res.get("artifact_id"):
            raise RuntimeError("the drift did not land")
        ck("a new drift at v1: %s" % res["name"],
           res["version"] == 1 and res["new_version"] is True)
        # The route adds nothing and loses nothing: drift.build on the same
        # pinned payloads, read independently from the store, in the same
        # sorted order, with the same labels and computed_on.
        pins = sorted(L, key=lambda x: (x["id"], x["version_id"]))
        pinsR = sorted(R, key=lambda x: (x["id"], x["version_id"]))
        mk_refs = lambda xs: [{"artifact_id": x["id"], "version": x["version"],
                               "version_id": x["version_id"],
                               "digest": x["digest"],
                               "name": x["nickname"] or x["name"]}
                              for x in xs]
        indep = drift.build(
            [A.payload(x["id"], x["version_id"]) for x in pins],
            [A.payload(x["id"], x["version_id"]) for x in pinsR],
            mk_refs(pins), mk_refs(pinsR),
            {"left": "Precon1", "right": "Precon4"},
            computed_on=res["payload"]["computed_on"])
        same = (json.dumps(indep, sort_keys=True)
                == json.dumps(res["payload"], sort_keys=True))
        ck("the filed payload equals drift.build on the same inputs, key for "
           "key", same)
        stored = A.payload(res["artifact_id"], res["version_id"])
        ck("and the store holds exactly that payload (digest %s)"
           % res["digest"],
           json.dumps(stored, sort_keys=True)
           == json.dumps(res["payload"], sort_keys=True)
           and __import__("backend.artifacts", fromlist=["digest"])
           .digest(stored) == res["digest"])
        rec = A.get(res["artifact_id"])
        vrow = [v for v in rec["versions"] if v["id"] == res["version_id"]][0]
        want_inputs = sorted(
            [{"kind": "artifact", "id": x["id"], "version": x["version"],
              "version_id": x["version_id"], "digest": x["digest"],
              "side": s} for s, xs in (("left", L), ("right", R))
             for x in xs], key=lambda d: (d["side"], d["id"]))
        got_inputs = sorted(vrow["inputs"], key=lambda d: (d["side"], d["id"]))
        ck("the version's inputs are the six pins, by version_id and digest",
           got_inputs == want_inputs,
           json.dumps(got_inputs)[:300])
        cites_ok = True
        for x in L + R:
            cb = A.cited_by(x["id"], x["version_id"])
            if not any(c["by_id"] == res["artifact_id"]
                       and c["by_version"] == 1
                       and c["version_id"] == x["version_id"] for c in cb):
                cites_ok = False
        ck("each input version is CITED by this drift at v1", cites_ok)
        code, dj = post("/api/artifacts/%s/delete" % R[0]["id"], {})
        ck("deleting a cited circuit is refused (409) with a sentence naming "
           "the drift: %s" % (dj or {}).get("error"),
           code == 409 and "harness drift" in ((dj or {}).get("error") or ""))
        ck("  and the circuit is still live",
           not (A.get(R[0]["id"]) or {}).get("deleted"))
        ck("the payload's members say version and version_id",
           all(m.get("version_id") for m in res["payload"]["left"]["members"]
               + res["payload"]["right"]["members"]))

        print("\n5. re-running")
        code, j, res2 = run(list(reversed(L)), [R[2], R[0], R[1]],
                            nickname="harness drift")
        ck("the same members in another order CONFIRM: same artifact, same "
           "version, no new one",
           res2.get("artifact_id") == res["artifact_id"]
           and res2.get("version") == 1 and res2.get("new_version") is False,
           "%s v%s new=%s" % (res2.get("artifact_id"), res2.get("version"),
                              res2.get("new_version")))
        rec = A.get(res["artifact_id"])
        ck("  one version, stamped confirmed once",
           len(rec["versions"]) == 1
           and len(rec["versions"][0].get("confirmed") or []) == 1)
        # An OLDER circuit version, pinned while a newer one exists.
        L_old = [dict(L[0])] + L[1:]
        code, j, res3 = run(L_old, R)
        ck("pinning L0 v1 while v2 exists files a drift that reads v1",
           res3.get("payload") and any(
               m["artifact_id"] == L[0]["id"] and m["version"] == 1
               and m["version_id"] == L[0]["version_id"]
               for m in res3["payload"]["left"]["members"]))
        L_new = [L0v2] + L[1:]
        code, j, res4 = run(L_new, R)
        ck("the same drift over L0 v2 is a DIFFERENT drift (a different "
           "comparison), not a version of the first",
           res4.get("artifact_id") and res4["artifact_id"]
           != res["artifact_id"] and res4.get("version") == 1)

        print("\n6. the cue-equivalence choice")
        eq = [{"from": "HighTone_Noise", "to": "Click_HighTone",
               "by": "harness", "at": "2026-09-28T01:02:03+00:00"}]
        code, j, e1 = run(L, B, labels=("Click-High", "High-Noise"), eq=eq)
        ce = (e1.get("payload") or {}).get("cue_equivalence")
        ck("refused without it, filed with it; recorded as {from,to,by,at}: "
           "%s" % ce, ce == [{"from": "Click_HighTone",
                              "to": "HighTone_Noise", "by": "harness",
                              "at": "2026-09-28T01:02:03+00:00"}])
        code0, j0 = post("/api/arc/drift/run", {"left": ref(L), "right":
                                                ref(B)})
        ck("  (without it the run is refused 409 naming both pairings)",
           code0 == 409 and "High tone → Noise" in (j0.get("error") or ""))
        ck("  and both pairings are named on the result: %s"
           % e1["payload"]["cue_label"],
           e1["payload"]["cue_types"] == ["Click_HighTone", "HighTone_Noise"])
        eq2 = [dict(eq[0], at="2026-12-31T00:00:00+00:00", by="someone")]
        code, j, e2 = run(L, B, labels=("Click-High", "High-Noise"), eq=eq2)
        ck("re-stating the same choice later confirms (the first by/at is "
           "carried): %s" % (e2.get("payload") or {}).get("cue_equivalence"),
           e2.get("artifact_id") == e1.get("artifact_id")
           and e2.get("new_version") is False
           and e2["payload"]["cue_equivalence"] == ce)
        ck("an equivalence drift is its own artifact, not a version of an "
           "unequivalenced one", e1["artifact_id"] not in (res["artifact_id"],
                                                           res4.get(
                                                               "artifact_id")))

        print("\n7. k = 1, and refusals at run time")
        code, j, k1 = run(L[:1], R)
        P1 = k1.get("payload") or {}
        ck("a k = 1 left side is labelled: %s" % P1.get("warn"),
           (P1.get("left") or {}).get("one_recording") is True
           and any(drift.K1_SAY in w for w in P1.get("warn") or []))
        ck("the optimistic-z note is on every result",
           drift.Z_NOTE in (P1.get("notes") or []))
        code, j = post("/api/arc/drift/run", {"left": ref(L + [LOW]),
                                              "right": ref(R)})
        ck("an incompatible run is refused 409 with the reasons",
           code == 409 and any(" low " in r for r in j.get("reasons") or []))

        if want_vacc:
            print("\n8. the VACC")
            st = appmod.vaccmod.status()
            can, why = driftrun.vacc_ok(st)
            code, c = post("/api/arc/drift/check", {"left": ref(L),
                                                    "right": ref(R)})
            print("   cost first: %s" % c["cost"]["sentence"])
            if not can:
                ck("VACC run (skipped: %s)" % why, True)
            else:
                t0 = time.time()
                limit = float(sys.argv[sys.argv.index("--vacc-limit") + 1]) \
                    if "--vacc-limit" in sys.argv else 480.0
                code, j, v = run(L, R, where="vacc", nickname="harness drift",
                                 limit=limit)
                job = cfc.get(j["job"]) if code == 200 else None
                if job is not None and job.status == "running":
                    # Not waited on any longer: cancelled, and the cancel
                    # reaches the cluster (VaccRun.work's finally scancels).
                    job.cancel()
                    wait(job.id, 60.0)
                    print("   not landed inside %d s: cancelled" % limit)
                snap = job.snapshot() if job else {}
                print("   job %s: %s in %.0f s; stages %s" % (
                    j.get("job"), snap.get("status"), time.time() - t0,
                    [(s["name"], s["status"], s["seconds"])
                     for s in snap.get("stages") or []]))
                on = (v.get("payload") or {}).get("computed_on") or {}
                ck("a real Drift ran on the cluster: slurm %s on %s"
                   % (on.get("slurm_id"), on.get("partition")),
                   on.get("kind") == "vacc" and on.get("slurm_id"),
                   snap.get("error"))
                ck("  its digest equals the local run's (%s), so it CONFIRMS"
                   % res["digest"],
                   v.get("digest") == res["digest"]
                   and v.get("artifact_id") == res["artifact_id"]
                   and v.get("new_version") is False)
    except Exception as exc:                             # noqa: BLE001
        import traceback
        traceback.print_exc()
        ck("CRASH: %s" % exc, False)
    finally:
        if brk == "cite":
            A.cite = A_cite
        print("\ncleaning up: %d drifts, then %d circuits" % (
            len(drifts), len(circuits)))
        code, j = post("/api/artifacts/_test/erase", {"ids": list(drifts)})
        code2, j2 = post("/api/artifacts/_test/erase",
                         {"ids": list(circuits)})
        left_over = [x for x in drifts + circuits if A.get(x)]
        ck("every drift and circuit this made is erased, and nothing was "
           "refused (%d + %d)" % (len((j or {}).get("erased") or []),
                                  len((j2 or {}).get("erased") or [])),
           not left_over and not (j or {}).get("refused")
           and not (j2 or {}).get("refused"), left_over)

    print()
    print("%d passed, %d failed" % (PASSED[0], len(FAILED)))
    if FAILED:
        for f in FAILED:
            print("  FAILED: " + f)
        sys.exit(1)


if __name__ == "__main__":
    main()
