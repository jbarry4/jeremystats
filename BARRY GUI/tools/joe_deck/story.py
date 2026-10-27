"""The story of the deck: main() for plan.py (kept apart so it reads as the
script it is). Every number is read from tab 8 and tab 9.

Since 2026-10-23 tab 9 draws comparisons 1, 2 and 5 in theta and gamma, its
rings open on FP, and its three tests go FP, shuffles (P), t-test or the rats'
flips (T): the deck says them in that order too, and calls a row a "cue
effect" (cue − baseline), not a delta."""
import json
import os

from plan import (APP, FIGS, HERE, CARD_RED, FAMILY, Deck, Img, NEW, bold_runs, fig_img, measure_sentence, p_say, view)

TESTS = (("fp", "FP"), ("trials", "shuffles"), ("rats", "rats’ flips"))


def main():
    import sys
    sys.path.insert(0, APP)
    from backend import monolith as MO, joe
    MO.configure(os.path.join(APP, "GUI_logs"))
    R = joe.result()
    F = json.load(open(os.path.join(FIGS, "figs.json"), encoding="utf-8"))
    B = json.load(open(os.path.join(HERE, "img", "boxes.json"), encoding="utf-8"))
    ill = {k: Img("!!I_" + k, v["file"], v["w_mm"], v["h_mm"], v["boxes"]) for k, v in B.items() if not k.startswith("_")}
    res = {(r["model"], r["band"]): r for r in R["results"] if r["method"] == "dickson"}
    figs = {f["id"]: f for f in F["figures"]}
    rings = {(f["model"], f["band"]): f for f in F["figures"] if f["kind"] == "connectome"}
    follows = [f for f in F["figures"] if f["kind"] == "follow"]
    D = Deck()

    def graphs(f):
        """A ring's graphs under each test: {null: {(row, kind): graph}}."""
        out = {f["null"]: f["stats"]["graphs"]}
        out.update({a["null"]: a["stats"]["graphs"] for a in f.get("alts") or []})
        return {k: {(x["row"], x["kind"]): x for x in v} for k, v in out.items()}

    # ---- the title -------------------------------------------------------
    CARD_RED["Did the cues change how the regions talk?"] = "talk?"
    D.slide(title="Joe’s figures, explained", card=("Did the cues change how the regions talk?",
                                                     "Precon1 → Precon4 · 8 rats · theta and gamma coherence\nShahriar · 23 October 2026"),
            speaker="From Jarvis, tabs 8 and 9 (the Monolith page). Every number on these slides is the tab's own.")
    D.slide(title="How to read this deck", view_=view(ill["coherence"]), focus=ill["coherence"].boxes["instep"],
            note="One idea per slide. The blue box is where to look; the black boxes say what it means.",
            runs=bold_runs("One idea per slide. The blue box is where to look; the black boxes say what it means.", "blue box", "black boxes"),
            speaker="The newest note is the big red one; older ones shrink and stay on the right until the topic ends.")

    # ---- what was measured -------------------------------------------------
    c = ill["coherence"]
    r1g = rings[("m1", "gamma")]
    D.slide(title="What was measured", view_=view(c), focus=c.boxes["instep"], clear=True,
            note="Coherence: how much two regions’ rhythms rise and fall together. In step, it is near 1.",
            speaker="Coherence is computed the way Dickson et al. 2022 and Jeremy’s MATLAB do it (mscohere).")
    D.slide(view_=view(c), focus=c.boxes["outstep"],
            note="When B’s timing drifts against A’s, it is near 0. In step, B’s peaks keep the same distance from A’s (the dotted lines).")
    D.slide(view_=view(c), focus=None,
            note="Two rhythms, as in Joe’s proposal: theta (5–12 Hz) and gamma (30–90 Hz), between every pair of 12 regions. %d pairs had at least 4 rats on both days." % len(r1g["stats"]["pairs"]))
    t = ill["timeline"]
    bar = [t.boxes["baseline"][0], t.boxes["baseline"][1], t.boxes["cues"][2], t.boxes["cues"][3]]
    D.slide(view_=view(t), focus=bar, clear=True, note="Each trial: a baseline before cue 1, then cue 1 and cue 2.")
    D.slide(view_=view(t), focus=t.boxes["cmp1"], note="Comparison 1: the 20 s baseline against both cues (20 s).")
    D.slide(view_=view(t), focus=t.boxes["cmp2"], note="Comparison 2: the 10 s baseline against cue 1.",
            speaker="Coherence in each window is the mean over the session’s trials (12 to 16 a session), per rat and day.")
    D.slide(view_=view(t), focus=t.boxes["cmp5"],
            note="Comparison 5: cue 1 against cue 2, on every trial whatever its sounds: not A against B, nor C against D.",
            speaker="Pooled over the four sounds, so the comparison is first cue against second cue, agnostic of pair identity.")
    r1, r2 = res[("m1", "gamma")], res[("m2", "gamma")]
    up1, n1 = B["_rats_up"]["m1"]
    rm = ill["rats_m1"]
    q = "The question: did the cues’ effect on coherence change from Precon1 to Precon4?"
    D.slide(view_=view(rm), focus=None, clear=True, note=q, runs=bold_runs(q, "change"))
    D.slide(view_=view(rm), focus=rm.boxes["dots"],
            note="Each dot is one rat (comparison 1, gamma): its cue effect (cue − baseline) on Precon4, minus its cue effect on Precon1, averaged over its pairs. %d of %d are above 0." % (up1, n1),
            speaker="Per rat: the mean over its pairs of (Precon4 cue − baseline) − (Precon1 cue − baseline). A one-sample t-test of these 8 numbers: t(%d) = %.2f, P = %.3f." % (
                r1["quick"]["df"], r1["quick"]["t"], r1["quick"]["p"]))

    # ---- tab 8's answer ----------------------------------------------------
    L = ill["lights"]
    tm1 = r1["mixed"]["terms"]["Day × Phase"]
    tm2 = r2["mixed"]["terms"]["Day × Phase"]
    up2, n2 = B["_rats_up"]["m2"]
    c1 = next(r for r in R["results"] if r["model"] == "c1" and r["band"] == "theta" and r["method"] == "dickson")
    lit = [r for r in R["results"] if r["method"] == ("welch" if r["model"] == "m7" else "dickson") and (r.get("gate") or {}).get("passed")]
    D.slide(title="Tab 8: what lit up", view_=view(L), focus=None, clear=True,
            note="12 comparisons, each in theta and gamma. Blue: unlikely to be chance (P < 0.05). Orange diamond: a check that lit. Hollow: not clear of chance, which is not the same as no change.",
            speaker="The lights are drawn in colours that colour-blind readers tell apart, with a shape for each state as well.")
    D.slide(view_=view(L), focus=L.boxes["m1_gamma"], focus2=L.boxes["m2_gamma"],
            note="Two lit, both in gamma: comparison 1 (%s, %d of %d rats the same way) and comparison 2 (%s, %d of %d)." % (
                p_say(tm1["p"]), up1, n1, p_say(tm2["p"]), up2, n2),
            speaker="Mixed model, rat as the unit, Day × Phase: comparison 1 F(%d, %d) = %.2f, P = %.3f; comparison 2 F(%d, %d) = %.2f, P = %.3f." % (
                tm1["df1"], tm1["df2"], tm1["F"], tm1["p"], tm2["df1"], tm2["df2"], tm2["F"], tm2["p"]))
    D.slide(view_=view(L), focus=L.boxes["c1_theta"],
            note="One check lit too: Noise vs Click in theta (%s). The checks were expected to stay dark: worth a look, not a finding." % p_say(c1["gate"]["p"]))
    D.slide(view_=view(L), focus=None,
            note="Nothing is corrected across the 24 lights, and each has two ways to pass. If nothing had changed anywhere, about 2 would light by chance; %d lit." % len(lit),
            speaker="A light passes if either its Day × factor term or its Day × factor × Pair term has P < 0.05: about 24 × (1 − 0.95²) ≈ 2.3 expected by chance alone; %d lit." % len(lit))

    # ---- what a ring's rows are (Supplementary Figure S1) ------------------
    if "S1" in figs:
        s1, ims = figs["S1"], fig_img("S1")
        st = s1["stats"]
        thirds = [(0, 0, 62, ims.h), (61, 0, 122, ims.h), (121, 0, ims.w, ims.h)]
        CARD_RED["Figure S1"] = "Figure S1"
        D.slide(title="Figure S1 · what a row is", view_=view(ims), card=("Figure S1", "How each row of a ring is made, on one pair"),
                clear=True, speaker=s1["legend"]["title"] + " " + s1["legend"]["body"])
        D.slide(view_=view(ims), focus=thirds[0],
                note="One pair, %s, comparison 1 in gamma. The Precon1 cue effect: cues minus baseline on Precon1, %+.3f." % (s1["pair"], st["effect1"]))
        D.slide(view_=view(ims), focus=thirds[1], note="The Precon4 cue effect: the same on Precon4, %+.3f." % st["effect4"])
        tx = "The change in cue effect: Precon4’s minus Precon1’s, %+.3f. This is what tab 8’s light tested." % st["change"]
        D.slide(view_=view(ims), focus=thirds[2], note=tx, runs=bold_runs(tx, "change in cue effect"))
        D.slide(view_=view(ims), focus=None,
                note="A ring draws these three numbers for every pair at once: its three rows.")

    # ---- the rings ---------------------------------------------------------
    COLX, ROWY = (14.0, 70.0, 126.0), (9.0, 71.0, 133.0)
    cell = lambda ri, ci: (COLX[ci] - 3, ROWY[ri] + 1.5, COLX[ci] + 56, ROWY[ri] + 60)        # noqa: E731
    ring = lambda ri, ci: (COLX[ci] - 3, ROWY[ri] + 1.5, COLX[ci] + 56, ROWY[ri] + 43)        # noqa: E731
    hist = lambda ri, ci: (COLX[ci] + 6, ROWY[ri] + 42.5, COLX[ci] + 50, ROWY[ri] + 59)      # noqa: E731
    row = lambda ri: (1, ROWY[ri] - 4, 183, ROWY[ri] + 61)                                     # noqa: E731
    col = lambda ci: (COLX[ci] - 4, 0.5, COLX[ci] + 57, 196)                                   # noqa: E731

    def img_of(f, null):
        """The picture of a ring under one test: fig_N (rats), fig_N_trials, fig_N_fp."""
        return fig_img(f["id"] if null == "rats" else "%s_%s" % (f["id"], null))

    def card(f, cmp_title):
        CARD_RED["Figure %s" % f["id"]] = "Figure %s" % f["id"]
        im = img_of(f, f["null"])
        D.slide(title="Figure %s · %s · %s" % (f["id"], cmp_title, f["band"]), view_=view(im),
                card=("Figure %s" % f["id"], "Comparison %d, %s, %s: the whole network" % (f["comparison"], cmp_title, f["band"])), clear=True)
        return im, graphs(f)

    def counts(f, rowk):
        e = [x for x in f["stats"]["edges"][rowk] if x is not None]
        return sum(x > 0 for x in e), sum(x < 0 for x in e), len(e)

    def three(G, key):
        """FP, shuffles, rats' flips: their P for one graph, in that order."""
        return ", ".join("%s %s" % (say, p_say(G[nk][key]["p"])) for nk, say in TESTS if nk in G)

    def best(G):
        ps = [(g["p"], nk, k) for nk in G for k, g in G[nk].items()]
        return min(ps), sum(p < 0.05 for p, _n, _k in ps), len(ps)

    KIND = {"pos": "increases", "neg": "decreases", "net": "ups and downs together"}

    def hits(f, G, rows_):
        """What passes in one ring, in words: for each (row, kind) that a
        test passes, which tests, FP first."""
        out = []
        names = {r[0]: r[1] for r in f["stats"]["rows"]}
        for rk in rows_:
            for kind in ("pos", "neg", "net"):
                ok = [(say, G[nk][(rk, kind)]["p"]) for nk, say in TESTS if nk in G and G[nk][(rk, kind)]["p"] < 0.05]
                if ok:
                    out.append("the %s’s %s pass %s" % (names[rk].lower() if rk == "delta" else names[rk].replace(rk + " ", ""), KIND[kind],
                                                       " and ".join("%s (%s)" % (s, p_say(p)) for s, p in ok)))
        return out

    f = r1g
    im, G = card(f, "baseline → both cues")
    full = view(im)
    nsig, nr = f["stats"]["n_signs"], len(f["stats"]["rats"])
    rows = f["stats"]["rows"]
    D.slide(view_=full, focus=None,
            note="Every ring is the same 12 regions. Each line is one pair, %d pairs in all. Grey dots: regions no pair reached with 4 rats." % len(f["stats"]["pairs"]),
            speaker=f["legend"]["title"] + " " + f["legend"]["body"])
    D.slide(view_=view(im, ring(0, 0)), focus=None,
            note="A line’s width is that pair’s cue effect, averaged over the rats. Orange: the cues raised coherence.")
    D.slide(view_=view(im, ring(0, 1)), focus=None, note="Purple: they lowered it.")
    u, d, n = counts(f, "Precon1")
    D.slide(view_=full, focus=row(0), note="Top row: the %s (%s). The cues lowered gamma coherence in %d of the %d pairs." % (rows[0][1], rows[0][2], d, n))
    u, d, n = counts(f, "Precon4")
    D.slide(view_=full, focus=row(1), note=("Middle row: the %s. About even: %d pairs up, %d down." % (rows[1][1], u, d)) if abs(u - d) <= 4 else
            "Middle row: the %s. Mostly %s: %d pairs up, %d down." % (rows[1][1], "up" if u > d else "down", u, d))
    bt = "Bottom row: the change in cue effect, Precon4’s minus Precon1’s. This is what tab 8’s light tested."
    D.slide(view_=full, focus=row(2), note=bt, runs=bold_runs(bt, "the change in cue effect"))
    D.slide(view_=full, focus=col(0), clear=True, note="Left column: only the lines that went up. Middle: only those that went down. Right: both.")
    gp, gi = G["rats"][("delta", "pos")], G["rats"][("delta", "net")]
    D.slide(view_=view(im, cell(2, 0)), focus=ring(2, 0), clear=True,
            note="Each ring becomes one number: its lines added up. Here the change’s increases add up to %.2f: the black line under the ring." % gp["stat"])
    # the three tests, FP first
    gf = G.get("fp")
    if gf:
        gfp, gfi = gf[("delta", "pos")], gf[("delta", "net")]
        D.slide(view_=view(im, cell(2, 0)), focus=hist(2, 0),
                note="Test 1, FP: the same rats in FP1 and FP2, with no cues. Fake trials at random moments, measured as real ones are; 10,000 sets, each session as many as it had real trials. Each set’s sum is the grey hill.",
                speaker="A fake cue onset every 10 s of FP1 and FP2 (%s fake trials in all), the trial's own windows round it, measured with the same wires, clipping and measures; each set draws each session's fake trials at random, with replacement, losing the windows its real trials lost." % format(F["fp"]["fake_trials"], ","))
        D.slide(view_=view(im, cell(2, 0)), focus=hist(2, 0),
                note="The black line is the real sum. Against FP: %s. %s" % (
                    p_say(gfp["p"]), "It does not stand out of what the rats do with no cues." if gfp["p"] >= 0.05 else
                    "It stands out of what the rats do with no cues."),
                speaker="Rank %d of %d." % (gfp["rank"], gfp["n"]))
    imt = img_of(f, "trials")
    gtp, gti = G["trials"][("delta", "pos")], G["trials"][("delta", "net")]
    D.slide(view_=view(imt, cell(2, 0)), focus=hist(2, 0), clear=True,
            note="Test 2, the shuffles (P, a toggle on tab 9): in every session, each trial’s baseline and cue swapped at random, 10,000 times. Single trials vary a lot, so the hill is wide: %s." % p_say(gtp["p"]),
            speaker="Trial-to-trial noise inside a session is about 1.7 times wider than the spread between rats.")
    imr = img_of(f, "rats")
    k_ = int(round(gp["p"] * gp["n"]))
    D.slide(view_=view(imr, cell(2, 0)), focus=hist(2, 0), clear=True,
            note="Test 3, the rats’ flips (T): if the cues’ effect were the same on both days, each rat’s change could as well point the other way. Flip the signs every way (%s for %d rats): only %d sums reach the real one, %s." % (
                format(nsig, ","), nr, k_, p_say(gp["p"])),
            speaker="Exact sign-flip test, the rat as the unit (as the mixed model behind tab 8's light). P is the share of the %d patterns at least as extreme, the real one included; rank %d." % (nsig, gp["rank"]))
    D.slide(view_=view(imr, cell(2, 2)), focus=hist(2, 2),
            note="Ups and downs together: %s." % three(G, ("delta", "net")))
    pm = {d_: min(G[nk][(d_, k)]["p"] for nk in G for k in ("pos", "neg", "net")) for d_ in ("Precon1", "Precon4")}
    D.slide(view_=view(imr), focus=row(0), focus2=row(1),
            note="Neither day’s cue effect passes a test on its own (Precon1 %s at best, Precon4 %s): it is the change between them." % (p_say(pm["Precon1"]), p_say(pm["Precon4"]))
            if max(pm.values()) >= 0.05 and min(pm.values()) >= 0.05 else
            "On its own, Precon1’s cue effect is at best %s and Precon4’s %s." % (p_say(pm["Precon1"]), p_say(pm["Precon4"])))
    passed = [say for nk, say in TESTS if nk in G and G[nk][("delta", "pos")]["p"] < 0.05]
    D.slide(view_=view(imr, cell(2, 0)), focus=hist(2, 0), clear=True,
            note=("So: the increases pass only the rats’ flips, the test that matches tab 8’s light; neither FP nor the shuffles confirm it. Figure %s is a lead, not a finding." % f["id"])
            if passed == ["rats’ flips"] else "So: the increases pass %s." % (" and ".join(passed) or "no test"))

    f2 = rings[("m2", "gamma")]
    im2, G2 = card(f2, "baseline → cue 1")
    D.slide(view_=view(im2), focus=row(2), note="Same layout, comparison 2: the 10 s baseline against cue 1.",
            speaker=f2["legend"]["title"] + " " + f2["legend"]["body"])
    k2 = ("delta", "pos")
    all3 = all(G2[nk][k2]["p"] < 0.05 for nk, _s in TESTS if nk in G2)
    D.slide(view_=view(im2, cell(2, 0)), focus=hist(2, 0),
            note="The change’s increases: %s.%s" % (three(G2, k2), " The one network result that passes every test." if all3 else ""))
    D.slide(view_=view(im2, cell(2, 2)), focus=hist(2, 2), note="Ups and downs together: %s." % three(G2, ("delta", "net")))
    kn = ("Precon1", "neg")
    pas = [say for nk, say in TESTS if nk in G2 and G2[nk][kn]["p"] < 0.05]
    if pas:
        D.slide(view_=view(im2, cell(0, 1)), focus=hist(0, 1), clear=True,
                note="One ring splits the tests: on Precon1 alone, the decreases (%s). It is one day’s cue effect, not the change, so it does not answer the question." % three(G2, kn))

    # ---- theta, and cue 1 → cue 2 ----------------------------------------------
    def rings_say(fr, im_, G_):
        """The change row first (the question), then any single day that passes."""
        dh = hits(fr, G_, ("delta",))
        pd = min(G_[nk][("delta", k)]["p"] for nk in G_ for k in ("pos", "neg", "net"))
        D.slide(view_=view(im_), focus=row(2),
                note=("The change in cue effect: %s." % "; ".join(dh)) if dh else
                "The change in cue effect passes none of its 9 tests (smallest P = %.2f): no change from Precon1 to Precon4 here." % pd,
                speaker=fr["legend"]["title"] + " " + fr["legend"]["body"])
        for ri, rk in ((0, "Precon1"), (1, "Precon4")):
            sh = hits(fr, G_, (rk,))
            if sh:
                tx_ = "On %s alone, %s." % (rk, "; ".join(sh))
                D.slide(view_=view(im_), focus=row(ri), note=tx_[:1].upper() + tx_[1:],
                        speaker="One day's cue effect, not the change across days: on that day the cue moved %s coherence beyond what FP or the shuffles give." % fr["band"])

    for mid, title in (("m1", "baseline → both cues"), ("m2", "baseline → cue 1")):
        ft = rings.get((mid, "theta"))
        if not ft:
            continue
        imt_, Gt = card(ft, title)
        rings_say(ft, imt_, Gt)
    for band in ("gamma", "theta"):
        f5 = rings.get(("m5", band))
        if not f5:
            continue
        im5, G5 = card(f5, "cue 1 → cue 2")
        r5 = f5["stats"]["rows"]
        D.slide(view_=view(im5), focus=row(0),
                note="Here a row is the %s: %s on each day, every trial whatever its sounds; the bottom row its change." % (r5[0][1].replace("Precon1 ", ""), r5[0][2].lower()),
                speaker=f5["legend"]["title"] + " " + f5["legend"]["body"])
        rings_say(f5, im5, G5)

    # ---- the follow-ups --------------------------------------------------------
    fam = ill["families"]
    n_tests = n_pass = n_pairs = 0
    for gr in F["groups"]:
        fo = (res.get((gr["model"], gr["band"])) or {}).get("follow") if gr["gated"] else None
        for pr in (fo or {}).get("pairs") or []:
            n_pairs += 1
            for m in pr["measures"].values():
                if m.get("p") is not None:
                    n_tests += 1
                    n_pass += m["p"] < 0.05
    D.slide(title="The follow-ups", view_=view(fam), focus=None, clear=True,
            note="Where a light lit (comparisons 1 and 2, gamma), tab 8 looked closer at single pairs, with four kinds of extra test.")
    D.slide(view_=view(fam), focus=fam.boxes["conduction"],
            note="Not just a shared signal: two wires can look coherent because they pick up the same source. PLI and imaginary coherence count only coupling with a delay: PLI asks how steadily one rhythm runs ahead, imaginary coherence also weighs how strongly.")
    D.slide(view_=view(fam), focus=fam.boxes["direction"], clear=True,
            note="Which leads: Granger asks if one region’s past predicts the other’s future; the lag asks whose gamma bursts come first.")
    D.slide(view_=view(fam), focus=fam.boxes["amplitude"],
            note="Bursts rise together: do the two regions’ gamma get loud at the same moments?")
    D.slide(view_=view(fam), focus=fam.boxes["pac"], clear=True,
            note="Theta paces gamma: do gamma bursts in one region ride the theta cycle of another (or its own)? Measured as a modulation index over each trial’s whole window, then the mean of the trials.")

    def fbox(fg):
        yp = 3 + 44 * len(fg["keys"])
        return {"a": (0, 0, 47, 45),
                "b": lambda k: (48, 3 + 44 * k - 1, 113, 3 + 44 * k + 38),
                "c": lambda k: (113, 3 + 44 * k - 1, 149.6, 3 + 44 * k + 38),
                "d": lambda k: (150.4, 3 + 44 * k - 1, 183, 3 + 44 * k + 38),
                "cd": lambda k: (111, 3 + 44 * k - 2, 183, 3 + 44 * k + 39),
                "roses": (0, yp - 1, 129, yp + 40), "comod": (129, yp - 1, 183, yp + 40),
                "pac": (0, yp - 2, 183, yp + 41)}

    first_pac = [True]
    taught = [False]
    WORD = {3: "All three tests agree: the strongest lead.", 2: "Two of the three agree: a middling lead.",
            1: "One test only: a weaker lead.", 0: "No test passes."}

    def follow(fg):
        fid = fg["id"]
        im = fig_img(fid)
        bx = fbox(fg)
        full = view(im)
        title = "%s · %s · %s" % (fid, fg["pair"], FAMILY[fg["family"]])
        if not taught[0]:
            taught[0] = True
            D.slide(title=title, view_=view(im, bx["a"]), focus=bx["a"], clear=True,
                    note="How to read a follow-up figure. a: the pair, on the same ring (an arrow when a direction was measured).",
                    speaker=fg["legend"]["title"] + " " + fg["legend"]["body"])
            D.slide(view_=view(im, bx["b"](0)), focus=bx["b"](0), note="b: each rat’s baseline and cue, Precon1 in grey and Precon4 in black.")
            D.slide(view_=view(im, bx["cd"](0)), focus=bx["c"](0),
                    note="c: each rat’s change in cue effect, Precon4’s − Precon1’s, with the mean and its 95% range. The t-test asks if the mean is away from 0.")
            D.slide(view_=view(im, bx["cd"](0)), focus=bx["d"](0),
                    note="d: the same change against FP (blue, 10,000 sets of fake trials) and the shuffles (grey, 10,000 within-session swaps).")
            tx = "Tab 8 ran %d of these t-tests (%d pairs × 10 measures); %d passed, where about %d would by chance. Those %d are the measures in these %d figures, sorted by how many of FP, shuffles and t-test they pass." % (
                n_tests, n_pairs, n_pass, round(0.05 * n_tests), n_pass, len(follows))
            D.slide(view_=full, focus=None, clear=True, note=tx, runs=bold_runs(tx, "about %d would by chance" % round(0.05 * n_tests)))
        for ki, k in enumerate(fg["keys"]):
            ms, nl = fg["stats"]["measures"][k], fg["stats"]["nulls"][k]
            nf = (fg["stats"].get("nulls_fp") or {}).get(k)
            npass = int(bool(nf) and nf["p"] < 0.05) + int(nl["p"] < 0.05) + int(ms["p"] < 0.05)
            word = WORD[npass]
            if k == "xlag":
                lead = fg["a"] if ms["delta"] < 0 else fg["b"]
                sent = ("Gamma-burst lag, %s with %s: how the cue shifted it differs between the days by %.0f ms, toward %s leading on Precon4 compared with Precon1." % (
                    fg["a"], fg["b"], abs(ms["delta"]), lead))
            else:
                sent = measure_sentence(k, fg["a"], fg["b"], ms["delta"])
            D.slide(title=title, view_=full, focus=bx["c"](ki), clear=(ki == 0), note=sent,
                    speaker=(fg["legend"]["title"] + " " + fg["legend"]["body"]) if ki == 0 else "")
            txt = "%sShuffles %s. t-test %s (%d rats). %s" % (("FP %s. " % p_say(nf["p"])) if nf else "", p_say(nl["p"]), p_say(ms["p"]),
                                                             ms["df"] + 1, word)
            D.slide(view_=view(im, bx["cd"](ki)), focus=bx["c"](ki), focus2=bx["d"](ki), note=txt, runs=bold_runs(txt, word),
                    speaker="%sShuffles: rank %d of %d, %s. t(%d) = %.2f, %s; mean change %.4g." % (
                        ("FP: rank %d of %d, %s. " % (nf["rank"], nf["n"], p_say(nf["p"]))) if nf else "",
                        nl["rank"], nl["n"], p_say(nl["p"]), ms["df"], ms["t"], p_say(ms["p"]), ms["delta"]))
        if fg.get("pac_profiles"):
            k = fg["pac_profiles"][0]
            pf = {"pac_ab": (fg["a"], fg["b"]), "pac_ba": (fg["b"], fg["a"]), "pac_aa": (fg["a"], fg["a"]), "pac_bb": (fg["b"], fg["b"])}[k]
            if first_pac[0]:
                first_pac[0] = False
                D.slide(view_=view(im, bx["roses"]), focus=bx["roses"], clear=True,
                        note="The roses: %s gamma around the %s theta cycle, over each trial’s whole window, averaged over trials and then rats. Orange: louder at that phase than its average over the cycle; purple: quieter." % (pf[1], pf[0]),
                        speaker="Mean over rats of each rat's normalised gamma amplitude in 18 theta-phase bins, read from the recordings (the VACC's copies) through tab 8's own wires; the four roses share one scale.")
                D.slide(view_=view(im, bx["roses"]), focus=bx["roses"],
                        note="Precon1 on the left, Precon4 on the right; baseline, then the cue. Rats that prefer different phases cancel, so a rose shows where in the cycle, not how much: b and c are what was tested.")
                D.slide(view_=view(im, bx["comod"]), focus=bx["comod"],
                        note="The comodulogram: the same change in cue effect split into narrow theta bands (across) and gamma bands (up). Orange: the cue raised coupling more on Precon4; purple: less. A map, not the test: c is the result.")
            else:
                D.slide(view_=view(im, bx["pac"]), focus=bx["roses"], clear=True,
                        note="Its roses: %s gamma around the %s theta cycle, averaged over trials and rats, Precon1 then Precon4. Where in the cycle, not how much: c is the result." % (pf[1], pf[0]))

    for fg in follows:
        follow(fg)

    # ---- the end ------------------------------------------------------------
    by_n = {n_: [fg["id"] for fg in follows if fg["passes"]["n"] == n_] for n_ in (3, 2, 1)}
    u1, d1, n_ = counts(f, "Precon1")
    u4, d4, _n = counts(f, "Precon4")
    bottom = (1, 129, 183, 196)
    D.slide(title="What it adds up to", view_=view(imr, bottom), focus=hist(2, 0), focus2=hist(2, 2), clear=True,
            note="From Precon1 to Precon4 the cues’ effect on gamma coherence swung across the network: on Precon1 they lowered it in %d of %d pairs; on Precon4, about even (%d up, %d down)." % (
                d1, n_, u4, d4))
    D.slide(view_=view(imr, bottom), focus=hist(2, 0), focus2=hist(2, 2),
            note="Figure %s (both cues): the rats agreed on that swing (increases %s), but FP and the shuffles do not confirm it." % (
                f["id"], p_say(gp["p"])) if passed == ["rats’ flips"] else "Figure %s (both cues), increases: %s." % (f["id"], three(G, ("delta", "pos"))))
    D.slide(view_=view(im2, bottom), focus=hist(2, 0),
            note="Figure %s (cue 1): the increases%s (%s)." % (f2["id"], " pass every test" if all3 else "", three(G2, k2)))
    still = [r_["id"] for r_ in rings.values() if not hits(r_, graphs(r_), ("delta",))]
    days_ = [r_["id"] for r_ in rings.values() if r_["band"] == "theta" and hits(r_, graphs(r_), ("Precon1", "Precon4"))]
    if still:
        D.slide(view_=view(im2, bottom), focus=None,
                note="The change in cue effect passes no test in Figures %s (theta, and cue 1 → cue 2).%s" % (
                    ", ".join(still), (" In theta, some single days’ cue effects stand out of FP (Figures %s): the cues move theta, but no differently on Precon4 than on Precon1." % ", ".join(days_)) if days_ else ""))
    D.slide(view_=view(fam), focus=None, clear=True,
            note="Of the %d follow-up figures, %d pass all three tests (%s), %d pass two (%s), the rest only the t-test. They were picked from %d t-tests, %d of which passed where about %d would by chance." % (
                len(follows), len(by_n[3]), ", ".join(by_n[3]), len(by_n[2]), ", ".join(by_n[2]), n_tests, n_pass, round(0.05 * n_tests)))
    D.slide(view_=view(fam), focus=None,
            note="FP is the most physiological of the three yardsticks: it carries what these rats’ brains do with no cues, with every session’s own lost windows. A result it passes and the shuffle does not is still worth a second look.")
    tx = "Nothing is corrected across tests, and the rings re-test the data that lit the light. All of this is leads to test again, not findings yet."
    D.slide(view_=view(fam), focus=None, note=tx, runs=bold_runs(tx, "leads to test again"))
    D.slide(view_=view(fam), focus=None, clear=True,
            note="Everything is in Jarvis: tab 9 has each figure as PDF, SVG and PNG with its legend, and its numbers for Prism (.xlsx and .pzfx); tab 8 has the SPSS files to recreate the lights.",
            speaker="Monolith page, tabs 8 (Joe's data) and 9 (Joe's figures). Questions to Shahriar.")
    return D
