# PTEN poster v5 (2026-11-27): the comments on v4

v5 answers the seven comments saved in `PTEN_poster_v4.pptx`. v4 and Rain's deck are unchanged.

- **Deck:** `PTEN_poster_v5.pptx`. Also `PTEN_poster_v5.pdf` and `PTEN_poster_v5_preview.png`.
- **Figures:** `v5_assets/`.
- **Code:** `code/v5/`. The build is `build_v5.py RAIN.pptx OUT.pptx`.

## Every panel is redrawn

No figure on v5 is a crop any more, except the PTEN pathway diagram and v3's four pipeline images.

The other panels were read back out of their vector sources and redrawn with the poster's own matplotlib style (`style.py`, Aptos). This is the user's "keep the general shape and reproduce the graph":
- Every point, line, band and polygon was taken from the source PDF's paths.
- Axes were calibrated on the source's own ticks, read off grid renders (`gridview.py`).
- Error bars that the PDF hides in forms were read from a high-resolution render (`vec.Render.whisker`).

Every P value, ρ, n and slope printed on a source is carried over exactly.

| Script | Panels | Source |
|---|---|---|
| `fig_theta.py` | T_rasters, T_ied_example, T_ied_cno | Opening4 panels D, E, F; behavior menu p.25 a, b |
| `fig_theta2.py` | T_profiles, T_roc, T_dreadd | behavior menu p.20 b, p.22 a, p.23 b |
| `fig_behavior.py`, `fig_behavior2.py` | B_* (14 panels) | behavior menu p.3, 4, 6, 10, 13, 17 |
| `fig_dsx.py` | X_output, X_in_time, X_spectra, X_vs_wt, X_borders, X_examples | Jeremy menu p.2 c, 5 a, 8b a and b; follow-up p.3 b; DS story p.2 c |
| `fig_photos.py` | X_task, X_histology | Opening4 panels A, G (pictures only, no Helvetica titles) |
| `vec.py` | the reader | page paths with their clips applied |

**The clip filter matters.** The menu pages draw some report figures several times over, each copy clipped to its own panel. `vec.paths` keeps only what each clip leaves visible.

## The comments

| Where | Comment | v5 |
|---|---|---|
| Biomarkers C (IED example) | "rebuild with the new voltage raster/spectrogram look... can't see" | Rebuilt at 8.2 × 3.2 in. The voltage map is read back through its own colour bar into µV and shown on the poster's blue–red map, with the layers named. Both spectrograms keep the jet colouring, and the white traces are recovered from the render. |
| Theta A (rasters) | "rebuild with the new CSD raster trace look" | Rebuilt as on the KCNT1 laminar figure. The CSD is read back from the jet pictures through the source's colour bar, then shown sink-blue / source-red. The 30 vector traces of each mouse are overlaid. The lab's cell drawings and the CA1/DG bars sit beside the layer names. |
| Theta D (IED with CNO) | "same thing applies" | Rebuilt in the same way. The source pictures are stored bottom row first; v5 flips them back, which was checked against the source. The IP and PP bars are kept. |
| Theta C (DREADD) | "text over figure" | The drug-effect line now sits above the graph. |
| Behavior | "match the color scheme from the IEDs and dentate spikes" | Behavior and theta now use the DS section's colours: WT/control grey, Lo/IED− pink, Hi/IED+ magenta. IED+ mice are diamonds. A coloured key opens the behavior legend. |
| Title | "lots of different fonts... cohesive aesthetic harmony" | Every redrawn figure uses Aptos at the poster's sizes, on white, with no grey panel fills. |
| Funding | "cooler looking version from the KCNT1 poster" | Funding is now the KCNT1 strip: a dark-green band across the right column with the white PTEN Research and NIH logos and the grants. References moved beside the Discussion. |

The theta profile stars are now explained as on the source: GEE against the WT hilus, the reference. One star is P < 0.05; two stars also hold after Holm.

## Read off, not printed (worth a glance)

- **Hidden phase 10 "Entries into current goal" (L):** the source prints no group means. The bars come from its drawn mean ± SE: WT 48.7, Lo 32.4, Hi 43.5.
- **Arena numbers (A–B):** the three numbers under each arena are rewards · entries · s per entry. The menu does not define the third; it reads as seconds per entry.
- **Stars in the theta change panel:** these are placed at the source's positions. Where a red and a green star sat together, one can hide the other.
