# story-menu-figure-rules

_2026-11-23 rules for story-menu figures (Lab Figures menus): finding headings, star brackets that never touch a line, CSDs on one scale across groups, depth always on y, no lab layer labels, fit lines and bands, significance bars on line plots, every mouse on scale._

The user's notes on the KCNT1 AA story menu and the DS story menu (both 2026-11-23), meant for every figure in these menus:

- **Significance as brackets and stars** (* < 0.05, ** < 0.01, *** < 0.001) on every group comparison, "not just written out". The star must never touch or overlap a bracket line ("asterisk overlapping with line; do an audit"): lay brackets out in points after the axis limits are final (figlib `defer_brackets`).
- **Panel letter headings state the finding**, as a sentence a reader can quote. Good: "Voltage was off: no speed jump at the s0 'shocks'"; "Hom mice learned worse than Het and WT: more shocks". Bad: "Was the voltage off in s0?", "One number per mouse". Wrap long ones (they grow upward) and leave room above.
- **Numbers must not clutter**: no three-line P-value titles over every panel, no stacks of mouse names. Name mice only where it helps, placed where they overlap nothing (dots, lines, text).
- **Every mouse stays on the scale**: an off-scale triangle with a printed value ("m3 151") was confusing. Use a log axis for skewed positive numbers (plain tick labels, not 10^2).
- **Correlation scatters get the fitted line and its 95% band** ("where is the line and the shading?"); mean curves get their shaded band.
- **On line plots, significance is a bar along the axis** (P < 0.05 at that depth or window), not star-shaped markers ("what the hell is the star icon?"; "there has to be a good way that's not a star"). The KCNT1 note asked for a star over each session where a group differs; for continuous line plots use the bar.
- **CSDs that compare groups share one scale across the groups** ("do not normalize the CSD so we can see the difference"): divide every mouse by one number (the control average's deepest sink). Within one mouse, classes or types share that mouse's scale. Never scale each curve to itself when curves are compared.
- **Depth is always on the vertical axis**, running down the page as on the probe; the two blades mirror (upper blade: distal dendrites up from its cell layer; lower blade: distal down).
- **No lab layer labels** (the user is iffy on them; "make sure the cell layer data is not used"): depth registered on each recording's own DS (sink peaks, cell-layer sources); regions named CA1 / upper blade distal and proximal dendrites / hilus / lower blade proximal and distal dendrites.
- **3D panels**: pre-render each view at 600 dpi and embed it as a picture (vector 3D looked blurry in the PDF); frame each view with a header naming its mice.
- **When one mouse looks off, test it** (asked for m7): Grubbs' test inside its group and its studentized residual from the line; show P with and without it, keep the main panel with every mouse.
- **No coded stand-ins for "never"** (17 = never was "such a weird choice"): time-to-event measures as cumulative curves with survival tests.
- **Don't let a meaningless baseline squish the scale**: leave s0 / habituation out of learning curves (see `kcnt1-aa-story-menu-1123` (a note not copied here)).
- **Paths must be crisp**: rasterized parts at 600 dpi in the PDF, PNG at 300 dpi.
- **Faint red background on any panel or table cell whose groups ran at different floor speeds** (user, 11-24, KCNT1 AA confound/rescue supplements), with a one-line key on the page.

**Why:** the menus go to the lab and to the PI; findings must be readable at a glance and the stats visible.
**How to apply:** any Lab Figures story menu or supplement. This overrides `joe-figures-plain-and-polished` (a note not copied here)'s "no headline sentence in a figure" for menus; captions still explain how to read each panel. Related: [ds-story-menu-1123](ds-story-menu-1123.md), [ds-pten-m6-excluded-and-figure-rules](ds-pten-m6-excluded-and-figure-rules.md).
