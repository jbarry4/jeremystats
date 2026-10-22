"""The story of the deck: main() for plan.py (kept apart so it reads as the
script it is). Every number is read from tab 8 and tab 9."""
import json
import os

from plan import (APP, FIGS, HERE, CARD_RED, FAMILY, Deck, Img, NEW, bold_runs, fig_img, measure_sentence, p_say, view)


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
    follows = [f for f in F["figures"] if f["kind"] == "follow"]
    D = Deck()

    # ---- the title -------------------------------------------------------
    CARD_RED["Did the cues change how the regions talk?"] = "talk?"
    D.slide(title="Joe’s figures, explained", card=("Did the cues change how the regions talk?",
                                                     "Precon1 → Precon4 · 8 rats · gamma coherence\nShahriar · 22 October 2026"),
            speaker="From Jarvis, tabs 8 and 9 (the Monolith page). Every number on these slides is the tab's own.")
    D.slide(title="How to read this deck", view_=view(ill["coherence"]), focus=ill["coherence"].boxes["instep"],
            note="One idea per slide. The blue box is where to look; the black boxes say what it means.",
            runs=bold_runs("One idea per slide. The blue box is where to look; the black boxes say what it means.", "blue box", "black boxes"),
            speaker="The newest note is the big red one; older ones shrink and stay on the right until the topic ends.")

    # ---- what was measured -------------------------------------------------
    c = ill["coherence"]
    D.slide(title="What was measured", view_=view(c), focus=c.boxes["instep"], clear=True,
            note="Coherence: how much two regions’ rhythms rise and fall together. In step, it is near 1.",
            speaker="Coherence is computed the way Dickson et al. 2022 and Jeremy’s MATLAB do it (mscohere).")
    D.slide(view_=view(c), focus=c.boxes["outstep"],
            note="When B’s timing drifts against A’s, it is near 0. In step, B’s peaks keep the same distance from A’s (the dotted lines).")
    D.slide(view_=view(c), focus=None,
            note="Here: gamma (30–90 Hz), between every pair of 12 regions. 44 pairs had at least 4 rats on both days.",
            speaker="Theta (5–12 Hz) was measured too; no main comparison passed in theta, so this deck is gamma.")
    t = ill["timeline"]
    bar = [t.boxes["baseline"][0], t.boxes["baseline"][1], t.boxes["cues"][2], t.boxes["cues"][3]]
    D.slide(view_=view(t), focus=bar, clear=True, note="Each trial: a baseline before cue 1, then cue 1 and cue 2.")
    D.slide(view_=view(t), focus=t.boxes["cmp1"], note="Comparison 1: the 20 s baseline against both cues (20 s).")
    D.slide(view_=view(t), focus=t.boxes["cmp2"], note="Comparison 2: the 10 s baseline against cue 1.",
            speaker="Coherence in each window is the mean over the session’s trials (12 to 16 a session), per rat and day.")
    r1, r2 = res[("m1", "gamma")], res[("m2", "gamma")]
    up1, n1 = B["_rats_up"]["m1"]
    rm = ill["rats_m1"]
    q = "The question: did the cues’ effect on coherence change from Precon1 to Precon4?"
    D.slide(view_=view(rm), focus=None, clear=True, note=q, runs=bold_runs(q, "change"))
    D.slide(view_=view(rm), focus=rm.boxes["dots"],
            note="Each dot is one rat (comparison 1): cue − baseline on Precon4, minus the same on Precon1, averaged over its pairs. %d of %d are above 0." % (up1, n1),
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
            note="12 comparisons, each in theta and gamma. Green: unlikely to be chance (P < 0.05). Amber: a check that lit. Grey: not clear of chance, which is not the same as no change.")
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

    # ---- the rings ---------------------------------------------------------
    COLX, ROWY = (14.0, 70.0, 126.0), (9.0, 71.0, 133.0)
    cell = lambda ri, ci: (COLX[ci] - 3, ROWY[ri] + 1.5, COLX[ci] + 56, ROWY[ri] + 60)        # noqa: E731
    ring = lambda ri, ci: (COLX[ci] - 3, ROWY[ri] + 1.5, COLX[ci] + 56, ROWY[ri] + 43)        # noqa: E731
    hist = lambda ri, ci: (COLX[ci] + 6, ROWY[ri] + 42.5, COLX[ci] + 50, ROWY[ri] + 59)      # noqa: E731
    row = lambda ri: (1, ROWY[ri] - 4, 183, ROWY[ri] + 61)                                     # noqa: E731
    col = lambda ci: (COLX[ci] - 4, 0.5, COLX[ci] + 57, 196)                                   # noqa: E731

    def card(fid, cmp_no, cmp_title):
        im = fig_img(fid)
        CARD_RED["Figure %s" % fid] = "Figure %s" % fid
        D.slide(title="Figure %s · %s · gamma" % (fid, cmp_title), view_=view(im),
                card=("Figure %s" % fid, "Comparison %d, %s: the whole network" % (cmp_no, cmp_title)), clear=True)
        f = figs[fid]
        return (f, im, {(x["row"], x["kind"]): x for x in f["stats"]["graphs"]},
                {(x["row"], x["kind"]): x for x in f["alt"]["stats"]["graphs"]})

    def counts(f, rowk):
        e = [x for x in f["stats"]["edges"][rowk] if x is not None]
        return sum(x > 0 for x in e), sum(x < 0 for x in e), len(e)

    f, im, g, gt = card("1", 1, "baseline → both cues")
    full = view(im)
    nsig, nr = f["stats"]["n_signs"], len(f["stats"]["rats"])
    D.slide(view_=full, focus=None,
            note="Every ring is the same 12 regions. Each line is one pair, %d pairs in all. Grey dots: regions no pair reached with 4 rats." % len(f["stats"]["pairs"]),
            speaker=f["legend"]["title"] + " " + f["legend"]["body"])
    D.slide(view_=view(im, ring(0, 0)), focus=None,
            note="A line’s width is how much that pair’s coherence went from baseline to the cues, averaged over the rats. Orange: up.")
    D.slide(view_=view(im, ring(0, 1)), focus=None, note="Purple: down.")
    u, d, n = counts(f, "Precon1")
    D.slide(view_=full, focus=row(0), note="Top row: Precon1. The cues lowered gamma coherence in %d of the %d pairs." % (d, n))
    u, d, n = counts(f, "Precon4")
    D.slide(view_=full, focus=row(1), note="Middle row: Precon4. About even: %d pairs up, %d down." % (u, d) if abs(u - d) <= 4 else
            "Middle row: Precon4. Mostly %s: %d pairs up, %d down." % ("up" if u > d else "down", u, d))
    bt = "Bottom row: the change, Precon4 − Precon1. This is what tab 8’s light tested."
    D.slide(view_=full, focus=row(2), note=bt, runs=bold_runs(bt, "the change"))
    D.slide(view_=full, focus=col(0), clear=True, note="Left column: only the lines that went up. Middle: only those that went down. Right: both.")
    gp, gi = g[("delta", "pos")], g[("delta", "net")]
    D.slide(view_=view(im, cell(2, 0)), focus=ring(2, 0), clear=True,
            note="Each ring becomes one number: its lines added up. Here the change’s increases add up to %.2f: the black line under the ring." % gp["stat"])
    D.slide(view_=view(im, cell(2, 0)), focus=hist(2, 0),
            note="The test: if the cues’ effect were the same on both days, each rat’s change could as well point the other way. Flip the rats’ signs every way (%s for %d rats) and add up again each time: those sums are the grey hill." % (
                format(nsig, ","), nr),
            speaker="Exact sign-flip test, the rat as the unit (as the mixed model behind tab 8's light). P is the share of the %d patterns at least as extreme, the real one included." % nsig)
    k_ = int(round(gp["p"] * gp["n"]))
    D.slide(view_=view(im, cell(2, 0)), focus=hist(2, 0),
            note="The black line is the real sum. Only %d of the %d sums reach it (itself included): %s." % (k_, gp["n"], p_say(gp["p"])),
            speaker="Rank %d of %d." % (gp["rank"], gp["n"]))
    D.slide(view_=view(im, cell(2, 2)), focus=hist(2, 2),
            note="Ups and downs together: %s, in line with tab 8’s light (%s)." % (p_say(gi["p"]), p_say(tm1["p"])))
    p1min = min(g[("Precon1", k)]["p"] for k in ("pos", "neg", "net"))
    p4min = min(g[("Precon4", k)]["p"] for k in ("pos", "neg", "net"))
    D.slide(view_=full, focus=row(0), focus2=row(1),
            note="Neither day passes on its own (Precon1 %s at best, Precon4 %s): it is the change between them." % (p_say(p1min), p_say(p4min)))
    imt = fig_img("1_trials")
    gti = gt[("delta", "net")]
    vt = view(imt, cell(2, 2))
    D.slide(view_=vt, focus=hist(2, 2), clear=True,
            note="Same ring, a second test (the toggle on tab 9): in every session, each trial’s baseline and cue swapped at random, 10,000 times. Single trials vary a lot, so the hill is much wider: %s (the rats’ test: %s)." % (
                p_say(gti["p"]), p_say(gi["p"])),
            speaker="Trial-to-trial noise inside a session is about 1.7 times wider than the spread between rats.")
    D.slide(view_=vt, focus=hist(2, 2),
            note="The rats moved together, the test that matches tab 8’s light; single trials are too noisy to confirm it. Figure 1 is a lead, not a finding.")

    f2, im2, g2, gt2 = card("2", 2, "baseline → cue 1")
    D.slide(view_=view(im2), focus=row(2), note="Same layout, comparison 2: the 10 s baseline against cue 1.")
    gp2, gi2, gtp2 = g2[("delta", "pos")], g2[("delta", "net")], gt2[("delta", "pos")]
    D.slide(view_=view(im2, cell(2, 0)), focus=hist(2, 0),
            note="The change’s increases: only %d of %d sums reach it: %s. The trial shuffle agrees (%s): the one network result that passes both tests." % (
                int(round(gp2["p"] * gp2["n"])), gp2["n"], p_say(gp2["p"]), p_say(gtp2["p"])))
    D.slide(view_=view(im2, cell(2, 2)), focus=hist(2, 2), note="Ups and downs together: %s, just short." % p_say(gi2["p"]))
    gn1, gtn1 = g2[("Precon1", "neg")], gt2[("Precon1", "neg")]
    D.slide(view_=view(im2, cell(0, 1)), focus=hist(0, 1), clear=True,
            note="One ring splits the other way: on Precon1 alone, the decreases pass the trial shuffle (%s) but not the rats’ test (%s). It is one day, not the change, so it does not answer the question." % (
                p_say(gtn1["p"]), p_say(gn1["p"])))

    # ---- the follow-ups --------------------------------------------------------
    fam = ill["families"]
    n_tests = n_pass = n_pairs = 0
    for mid in ("m1", "m2"):
        fo = res[(mid, "gamma")]["follow"]
        n_pairs += len(fo["pairs"])
        for pr in fo["pairs"]:
            for m in pr["measures"].values():
                if m.get("p") is not None:
                    n_tests += 1
                    n_pass += m["p"] < 0.05
    D.slide(title="The follow-ups", view_=view(fam), focus=None, clear=True,
            note="Then tab 8 looked closer at single pairs inside comparisons 1 and 2, with four kinds of extra test.")
    D.slide(view_=view(fam), focus=fam.boxes["conduction"],
            note="Not just a shared signal: two wires can look coherent because they pick up the same source. PLI and imaginary coherence count only coupling with a delay: PLI asks how steadily one rhythm runs ahead, imaginary coherence also weighs how strongly.")
    D.slide(view_=view(fam), focus=fam.boxes["direction"], clear=True,
            note="Which leads: Granger asks if one region’s past predicts the other’s future; the lag asks whose gamma bursts come first.")
    D.slide(view_=view(fam), focus=fam.boxes["amplitude"],
            note="Bursts rise together: do the two regions’ gamma get loud at the same moments?")
    D.slide(view_=view(fam), focus=fam.boxes["pac"], clear=True,
            note="Theta paces gamma: do gamma bursts in one region ride the theta cycle of another (or its own)?")

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

    def follow(fid):
        fg = figs[fid]
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
                    note="c: each rat’s change, Precon4 − Precon1, with the mean and its 95% range. The t-test asks if the mean is away from 0.")
            D.slide(view_=view(im, bx["cd"](0)), focus=bx["d"](0),
                    note="d: the same change against 10,000 within-session shuffles: a second opinion on the same data.")
            tx = "Tab 8 ran %d of these t-tests (%d pairs × 10 measures); %d passed, where about %d would by chance. Those %d are the measures in these %d figures." % (
                n_tests, n_pairs, n_pass, round(0.05 * n_tests), n_pass, len(follows))
            D.slide(view_=full, focus=None, clear=True, note=tx, runs=bold_runs(tx, "about %d would by chance" % round(0.05 * n_tests)))
        for ki, k in enumerate(fg["keys"]):
            ms, nl = fg["stats"]["measures"][k], fg["stats"]["nulls"][k]
            both = ms["p"] < 0.05 and nl["p"] < 0.05
            word = "Both agree: a stronger lead." if both else "The shuffles do not agree: a weaker lead."
            if k == "xlag":
                lead = fg["a"] if ms["delta"] < 0 else fg["b"]
                sent = ("Gamma-burst lag, %s with %s: how the cue shifted it differs between the days by %.0f ms, toward %s leading on Precon4 compared with Precon1." % (
                    fg["a"], fg["b"], abs(ms["delta"]), lead))
            else:
                sent = measure_sentence(k, fg["a"], fg["b"], ms["delta"])
            D.slide(title=title, view_=full, focus=bx["c"](ki), clear=(ki == 0), note=sent,
                    speaker=(fg["legend"]["title"] + " " + fg["legend"]["body"]) if ki == 0 else "")
            txt = "t-test %s (%d rats). Shuffles %s. %s" % (p_say(ms["p"]), ms["df"] + 1, p_say(nl["p"]), word)
            D.slide(view_=view(im, bx["cd"](ki)), focus=bx["c"](ki), focus2=bx["d"](ki), note=txt, runs=bold_runs(txt, word),
                    speaker="t(%d) = %.2f, %s; mean change %.4g. Shuffles: rank %d of %d, %s." % (
                        ms["df"], ms["t"], p_say(ms["p"]), ms["delta"], nl["rank"], nl["n"], p_say(nl["p"])))
        if fg.get("pac_profiles"):
            k = fg["pac_profiles"][0]
            pf = {"pac_ab": (fg["a"], fg["b"]), "pac_ba": (fg["b"], fg["a"]), "pac_aa": (fg["a"], fg["a"]), "pac_bb": (fg["b"], fg["b"])}[k]
            if first_pac[0]:
                first_pac[0] = False
                D.slide(view_=view(im, bx["roses"]), focus=bx["roses"], clear=True,
                        note="The roses: %s gamma around the %s theta cycle, averaged over rats. Orange: louder at that phase than its average over the cycle; purple: quieter." % (pf[1], pf[0]),
                        speaker="Mean over rats of each rat's normalised gamma amplitude in 18 theta-phase bins, read from the recordings (the VACC's copies) through tab 8's own wires; the four roses share one scale.")
                D.slide(view_=view(im, bx["roses"]), focus=bx["roses"],
                        note="Precon1 on the left, Precon4 on the right; baseline, then the cue. Rats that prefer different phases cancel, so a rose shows where in the cycle, not how much: b and c are what was tested.")
                D.slide(view_=view(im, bx["comod"]), focus=bx["comod"],
                        note="The comodulogram: the same change (cue − baseline, Precon4 minus Precon1) split into narrow theta bands (across) and gamma bands (up). Orange: the cue raised coupling more on Precon4; purple: less. A map, not the test: c is the result.")
            else:
                D.slide(view_=view(im, bx["pac"]), focus=bx["roses"], clear=True,
                        note="Its roses: %s gamma around the %s theta cycle, averaged over rats, Precon1 then Precon4. Where in the cycle, not how much: c is the result." % (pf[1], pf[0]))

    for fid in [f["id"] for f in follows]:
        follow(fid)

    # ---- the end ------------------------------------------------------------
    solid = []
    for fg in follows:
        for k in fg["keys"]:
            ms, nl = fg["stats"]["measures"][k], fg["stats"]["nulls"][k]
            if ms["p"] < 0.05 and nl["p"] < 0.05:
                solid.append(fg["id"])
                break
    u1, d1, n_ = counts(f, "Precon1")
    u4, d4, _n = counts(f, "Precon4")
    bottom = (1, 129, 183, 196)
    D.slide(title="What it adds up to", view_=view(im, bottom), focus=hist(2, 0), focus2=hist(2, 2), clear=True,
            note="From Precon1 to Precon4 the cues’ effect on gamma coherence swung across the network: on Precon1 they lowered it in %d of %d pairs; on Precon4, about even (%d up, %d down)." % (
                d1, n_, u4, d4))
    D.slide(view_=view(im, bottom), focus=hist(2, 0), focus2=hist(2, 2),
            note="The rats agreed on that swing: Figure 1, increases %s, ups and downs together %s. The trial shuffle does not confirm Figure 1 (%s)." % (
                p_say(gp["p"]), p_say(gi["p"]), p_say(gti["p"])))
    D.slide(view_=view(im2, bottom), focus=hist(2, 0),
            note="Figure 2 (cue 1): the increases pass both tests (%s by the rats, %s by the trials)." % (p_say(gp2["p"]), p_say(gtp2["p"])))
    D.slide(view_=view(fam), focus=None, clear=True,
            note="%d of the %d follow-up figures also pass the trial shuffle: %s. They were picked from %d t-tests, %d of which passed where about %d would by chance." % (
                len(solid), len(follows), ", ".join(solid), n_tests, n_pass, round(0.05 * n_tests)))
    tx = "Nothing is corrected across tests, and the rings re-test the data that lit the light. All of this is leads to test again, not findings yet."
    D.slide(view_=view(fam), focus=None, note=tx, runs=bold_runs(tx, "leads to test again"))
    D.slide(view_=view(fam), focus=None, clear=True,
            note="Everything is in Jarvis: tab 9 has each figure as PDF, SVG and PNG with its legend; tab 8 has the SPSS files to recreate the lights.",
            speaker="Monolith page, tabs 8 (Joe's data) and 9 (Joe's figures). Questions to Shahriar.")
    return D
