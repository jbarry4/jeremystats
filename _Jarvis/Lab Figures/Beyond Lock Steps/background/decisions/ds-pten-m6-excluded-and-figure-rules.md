# ds-pten-m6-excluded-and-figure-rules

_2026-11-17 standing rules for the DS/PTEN pilot: m6 is out (experiment confounds); the user makes the separable call; no folded or "main sink" figures; explain every axis._

Said by the user on 2026-11-17 about the DS/PTEN dentate-spike pilot ([ds-pten-deep-round-1116](ds-pten-deep-round-1116.md)):

- **Exclude m6 (CTL) from everything**: "it had confounding factors during the experiment." Control group is now m2, m21, m22, m26, m59, m60, m61 (m51 already out, 5 events).
- **"Leave the separable / not separable judgement call to me."** Show the separation index per recording; never label a recording separable, never filter or average "separable recordings only", no filled/open separable markers.
- **No folded figures** (both blades folded onto one source-outward axis) and no figures whose axis is "the main sink" — the user asked "what is the main sink?". If depth is normalized, keep the blades unfolded and say in plain words what 0 and 1 are.
- Depth normalization: one figure is enough — DS1 and DS2 separated, normalized, with DS3 removed.
- "What the hell is contact spacing?" — my jargon. Say "how far apart the two contacts used as outer and middle layer are" instead.
- Dot plots: the user could not tell what most y axes were. Every lead needs build-up panels showing where on the waveform the number is taken and how it is calculated.

- 2026-11-17: on per-mouse dot plots against knockout, draw correlation lines with confidence bands (I use Theil–Sen + 95% bootstrap). 2026-11-23: drawing one outlier at the edge with its value ("m3 151") confused the user; keep every mouse on the scale (log axis for skewed numbers). See [story-menu-figure-rules](story-menu-figure-rules.md).
- Prefer the framing the user finds clearer ("lower blade sink is larger") only where the data support it; say so when they don't (absolute lower sink was not larger, only its share).

- 2026-11-18 (Google Doc notes): **one classifier per recording, "the winner"** = round 11 QC's FINAL OPTIMIZED SEPARATION row (best DS1–DS2 index after DS3 removal among best-eligible / best PCA-plane / optimized curve); never vary classifiers in the battery (`dsdata.Rec.winner`, `measures.WINNER_ONLY`). v8 keeps v6's labels by time.
- "Between the blades" must exclude the sink lobes (landmarks `src_rows`). No absolute µm distances / absolute amplitudes as leads (probe placement differs); single shared source = "1 peak vs two", per-blade source distances meaningless there.
- "Filter" means frequency filters on the waveforms (battery rerun per band, same events and labels), NOT dropping events. Border sets v7 and the border "filter" family dropped.
- Explain every term in plain words on the page (the user asked "what the hell is the noise floor?", "what does CAN mean").
- Don't claim causes I haven't tested: I called the LFP-peak-position result a "reference artifact" — wrong (a reference shifts all contacts equally and cannot move where the maximum is). All recordings share the same reference setup (External Hardware Reference; CSC59 referenced to AD 43, bad everywhere).

**How to apply:** any DS/PTEN figure or table from now on. My interpretation: the separable rule (index ≥ 0.45, 5% minimum) may still be used internally to pick the "best eligible classifier", but no verdict word on the page.
