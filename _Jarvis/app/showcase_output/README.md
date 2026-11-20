# Jarvis showcase

Pictures, clips and screenshots of Jarvis and the data it has produced. Everything here was made on 2026-11-11 from real recordings and real Jarvis results. The only exception is the screenshots, which show the app itself.

| Folder | What is in it |
|---|---|
| `logo/` | The Jarvis mark as SVG, ICO and PNG at 16 to 256 px |
| `ui/bundles_and_views/` | The main views at 1920×1080 in UVM Dark: ToolKit (with The Dentist, The Storm, The Confluence and The Arc bundles), Xplorefinder, Event Bank, Sessions, History, Results, Storyboard and Pipeline |
| `ui/toolkit_tools/` | Every ToolKit tool's own page, 21 of them |
| `notch_60hz/` | The 60 Hz mains notch on PTEN m1 s2 (the recording with the strongest hum): three before/after examples, the hum that was removed, the spectrum, and 16 contacts raw → notched → DS filter |
| `dentate_spikes/` | Eight single dentate spikes as CSD + voltage; DS1 vs DS2 class means and depth profiles; 4 s of 32 contacts with every verified DS marked |
| `rootcanal_3d_clusters/` | Root Canal's pooled K-means (k = 2) in amplitude × half-width × 500 to 1000 Hz power, for the pools "CTL & PTEN Baseline v2" (18 mice) and "PTEN Baseline v2" (9 mice), each from the front and from three sides |
| `clips/` | Three short clips, each as MP4 and GIF: a scrolling trace with dentate spikes lighting up (4 s), a dentate spike's sink sweeping in at 10× slow motion (3.5 s), and a pool of about 5,200 events turning (5 s) |
| `depth_profile_pipeline/` | The poster *From a recording to a depth profile* (8 steps, one control recording). Also every Verified DS 5% recording's DS1/DS2 depth profile, and `ui_steps/`: the tool pages in pipeline order (Incisor → Checkup → Braces, Doppler → Spotter → Eye, Junction → Panning → Lock, X-ray) |
| `classifiers/` | Tooth Fairy and Prospector: 18 feature families → five boosted forests → one score, with their real held-out score distributions, the tolerance dial and the Spike bar |

Most DS figures use **PTEN m59 s4 2025-07-07**, a control mouse. Its X-ray result is 488 Verified DS 5% events, split into DS1 (119) and DS2 (369), ΔBIC 188.

The scripts that made these are not in the repo. Ask in the lab if you need them re-run.
