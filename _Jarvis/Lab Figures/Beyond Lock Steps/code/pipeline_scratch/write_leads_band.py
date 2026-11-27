# -*- coding: utf-8 -*-
import json
B = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\leads_band.json"
WIN = "each recording's winning classifier"
SAME = ("Same events, same DS1/DS2/DS3 labels as the Halo set; only the filter on the waveform changes (zero-phase Butterworth, order 3, 60 Hz notch "
        "always, read with 2 s of margin). ")
L = [
    dict(id="waveform|sink_pre_mean|b_none||all", contrast="IEDneg_vs_CTL",
         title="Without the DS filter, IED− mice show a slow sink building up before the DS",
         plain="With no band filter, the sink 10–30 ms before the DS peak is already 24 to 95% of the peak in IED− mice and under 26% in every control; the 5–100 Hz filter takes this slow lead-in away.",
         how=SAME + "No filter (notch only). Every event. Per event: the sink trace (mean of the two main-sink rows) from 30 to 10 ms before the peak, divided by its value at the peak. Per recording: mean. Contrast: IED− against control.",
         ylabel="Sink 30–10 ms before the peak\n(share of the peak, mean)",
         why="Every IED− value above every control (P = 0.012). Under the DS filter P = 0.93; with 1–100 Hz P = 0.042. So it lives below 5 Hz: a slow sink that starts before the DS.",
         against="Not on the 1–300 Hz copy (P = 0.41), which also keeps the slow part; m7 (0.95) and m1 (0.77) carry it. IED+ mice look like controls. A slow drift unrelated to the DS would do the same; the before/after battery tests that directly.",
         test="The before/after battery's 1–4 Hz power before the DS in the same mice; a planned test in new IED− mice."),
    dict(id="waveform|sink_area_cv|b_none||all", contrast="IEDneg_vs_CTL",
         title="Without the DS filter, IED− mice's sinks vary more from event to event",
         plain="With no band filter, the size of the sink (summed over ±10 ms) varies more from one event to the next in every IED− mouse than in any control.",
         how=SAME + "No filter. Every event. Per event: the sink at the two main-sink rows summed from −10 to +10 ms. Per recording: CV over events (no units). Contrast: IED− against control.",
         ylabel="Sink size, event to event\n(CV over events, no filter)",
         why="IED− 0.63 to 1.26, controls 0.39 to 0.56: no overlap (P = 0.006). Under the DS filter P = 0.16; low knockout against control P = 0.017.",
         against="m3 (IED+, 0.92) is as variable as IED− mice. The slow part the filter removes may be drift that adds to some events and not others.",
         test="CV of the sink after removing the 1 s around each event's baseline, unfiltered; planned."),
    dict(id="waveform|source_fwhm_cv|b_10_40||all", contrast="IEDneg_vs_CTL",
         title="With a narrow 10–40 Hz filter, IED− mice's source duration varies more",
         plain="Kept to 10–40 Hz, the duration of the source between the blades varies more from event to event in every IED− mouse than in any control.",
         how=SAME + "10–40 Hz. Every event. Per event: the source trace and its full width at half its peak (ms). Per recording: CV over events. Contrast: IED− against control.",
         ylabel="Source duration, event to event\n(CV over events, 10–40 Hz)",
         why="IED− 0.26 to 0.29, controls 0.21 to 0.26: no overlap (P = 0.006). 5–50 Hz P = 0.073; DS filter P = 0.32.",
         against="The difference is small (0.26 against 0.25 at the edges). A narrow filter rings, and ringing makes widths depend on the filter as much as on the event.",
         test="The same at 5–50 Hz with more mice."),
    dict(id="laminar|net_between_mean|b_1_100||all", contrast="KO_dose_PTEN",
         title="Keeping 1–5 Hz, the net source between the blades falls more clearly with knockout",
         plain="The net-source lead (main lead 1, sinks left out) is stronger when the filter keeps the slow part (1–100 Hz) than under the DS filter.",
         how=SAME + "1–100 Hz. Every event. Per event: mean CSD over the rows between the two blades' sinks (sink rows left out), over the sink at the main-sink rows. Per recording: mean. Contrast: rank correlation with % knockout within PTEN.",
         ylabel="Net source between the blades\n(sinks left out; over the sink, mean, 1–100 Hz)",
         why="Within PTEN rho −0.80 (P = 0.014). No filter P = 0.025, 1–300 Hz P = 0.017, 10–40 Hz P = 0.025, DS filter P = 0.059.",
         against="Gone at 5–50 Hz (P = 0.68). m8 (1.22) and m33 (0.95), the two lowest-knockout mice, carry the correlation.",
         test="As main lead 1."),
    dict(id="waveform|sink_pre_median|b_1_300|winner|ds2", contrast="IEDpos_vs_CTL",
         title="Keeping 1–5 Hz and fast activity, DS2 in IED+ mice has almost no sink before the peak",
         plain="Filtered 1–300 Hz, the sink 10–30 ms before a DS2 peak is about 0 to 6% of the peak in IED+ mice and 2 to 12% in controls.",
         how=SAME + "1–300 Hz. DS2 events of " + WIN + ". Per event: the sink trace (main-sink rows) from 30 to 10 ms before the peak, divided by its value at the peak. Per recording: median. Contrast: IED+ against control.",
         ylabel="Sink 30–10 ms before a DS2 peak\n(share of the peak, median, 1–300 Hz)",
         why="P = 0.010; IED+ against IED− P = 0.016 (IED− 0.09 to 0.18). 1–100 Hz P = 0.048; DS filter P = 0.15.",
         against="Not without any filter (P = 0.43), so it depends on cutting below 1 Hz. m59 (0.02) sits with IED+.",
         test="The before/after battery's slow power before DS2; planned test in new mice."),
]
json.dump(L, open(B, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(len(L))
