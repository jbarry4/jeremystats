"""Builds Rain_Figure_Info.pdf: everything Rain asked for, item by item
(time stamps, windows, filters, channels, how the DS was chosen, legend).
    python make_info_pdf.py
"""
import io
import os

import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))

CSS = """
* { font-family: sans-serif; }
body { font-size: 9.5pt; line-height: 1.35; color: #111; }
h1 { font-size: 16pt; margin: 0 0 2pt 0; }
h2 { font-size: 11.5pt; margin: 12pt 0 4pt 0; border-bottom: 0.6pt solid #888; padding-bottom: 2pt; }
h3 { font-size: 10pt; margin: 8pt 0 3pt 0; }
p { margin: 0 0 5pt 0; }
.sub { color: #555; font-size: 9pt; margin-bottom: 8pt; }
table { border-collapse: collapse; width: 100%; margin: 3pt 0 6pt 0; }
th, td { border: 0.5pt solid #999; padding: 2.5pt 4pt; vertical-align: top; font-size: 8.8pt; }
th { background-color: #eeeeee; text-align: left; }
.big { font-size: 11pt; font-weight: bold; }
.note { background-color: #f6f6f6; border-left: 2pt solid #c80; padding: 4pt 6pt; margin: 5pt 0; }
li { margin-bottom: 2pt; }
.mono { font-family: monospace; font-size: 8.5pt; }
"""

HTML = """
<h1>Rain's figure: time stamps, windows and methods</h1>
<p class="sub">Two versions of the same figure (same data, same events): <b>Rain_Figure.pdf</b> (plain journal style)
and <b>Rain_Figure_v2.pdf</b> (the same layout with the jet color map used in Figure 5 of the mTORC1/mTORC2
preprint, bioRxiv 2026.06.22.733785). Both label depth with even channel numbers on the theta and CSD panels
(no micron scale bar). Every panel is also saved on its own
(PDF and PNG) in the "Individual panels" subfolder.
Folder: _Jarvis\\Rain Figures. Prepared 2026-11-19.</p>

<h2>1. The time stamps (not shown in the figure)</h2>
<p>All times are seconds from the start of the recording (the first Neuralynx record), the clock Jarvis and the
event bank use.</p>
<table>
<tr><th>Panel</th><th>Recording</th><th>Time stamp (t = 0)</th><th>Window in the figure</th></tr>
<tr><td>Control DS</td><td>CTL m59 s4, 2025-07-07</td><td class="big">2024.8641 s</td>
<td>-150 to +150 ms (300 ms)<br/>2024.7141 - 2025.0141 s</td></tr>
<tr><td>PTEN IED</td><td>PTEN m34 s5, 2024-06-10</td><td class="big">1197.3657 s</td>
<td>-150 to +150 ms (300 ms)<br/>1197.2157 - 1197.5157 s</td></tr>
<tr><td>Theta, CTL / wild-type</td><td>CTL m6 s4, 2023-09-13</td><td>-</td><td>618.000 - 624.000 s (6 s)</td></tr>
<tr><td>Theta, PTEN</td><td>PTEN m13 s1, 2023-08-01</td><td>-</td><td>825.000 - 831.000 s (6 s)</td></tr>
<tr><td>Theta, DKO</td><td>DKO m41 s1, 2024-11-26</td><td>-</td><td>970.000 - 976.000 s (6 s)</td></tr>
</table>
<p><b>For the figure legend:</b> "Dentate spike and IED panels show 300 ms windows centered on the event
(-150 to +150 ms); theta panels show 6 s."</p>

<h2>2. What was asked for, and what is in the figure</h2>
<table>
<tr><th>Asked for</th><th>Done</th></tr>
<tr><td>Representative theta CSDs, 4-12 Hz: CTL, PTEN, DKO (the three from "Hella lit poster -- Jan-26th final")</td>
<td>Same three recordings and windows as the poster (found in IED DATA\\Take 3\\.Paper Figures\\Panel A - Theta Figures),
recomputed from the raw files: 4-12 Hz, every even contact, theta traces drawn over the CSD, one color scale
for all three.</td></tr>
<tr><td>Control representative DS, standalone, solid, chosen with Root Canal; good window with some surround</td>
<td>CTL m59 s4 at 2024.8641 s; nothing else detected within +-350 ms; 300 ms window. How it was chosen: section 3.</td></tr>
<tr><td>DS voltage: 5-100 Hz, 60 Hz notch, every even channel, no channel IDs</td><td>Yes (32 traces, CSC2-CSC64).</td></tr>
<tr><td>DS CSD: same filtering, every even channel</td><td>Yes.</td></tr>
<tr><td>DS spectrogram 1-800 Hz; channel IDs or subcompartments</td>
<td>Four contacts, labeled by channel ID (both versions).</td></tr>
<tr><td>PTEN IED, m34 s5, just before 1197.400 s</td><td>The event at 1197.3657 s; 300 ms window.</td></tr>
<tr><td>IED voltage: unfiltered, 60 Hz notch, every even channel, no channel IDs</td><td>Yes.</td></tr>
<tr><td>IED CSD: 1 Hz high-pass only if needed; 60 Hz notch</td>
<td>Not needed: no high-pass. Each contact's median over -150 to -60 ms was subtracted (an offset, not a filter).</td></tr>
<tr><td>IED spectrogram 1-800 Hz</td><td>Yes, as for the DS.</td></tr>
<tr><td>Publishing-ready PDF, standard style</td><td>Rain_Figure.pdf (version 1) and Rain_Figure_v2.pdf (version 2); vector, 180 mm wide.</td></tr>
</table>

<h2>3. How the control DS was chosen (Root Canal)</h2>
<ul>
<li><b>Pool:</b> every control dentate spike in the strict set ("PTEN and CTL Baseline ... No P-spikes": inside the
DS border, outside the P-spike border). Mice m2, m21, m22, m26, m59, m60 and m61 (1,766 events). m6 is left out (it
was excluded from the DS analysis) and so is m51 (5 events).</li>
<li><b>Root Canal's three numbers</b>, measured the way the pool measures them (10-150 Hz with 60 Hz removed;
window +-33 ms; half-width search +-75 ms; 240-420 Hz power): max amplitude, half-width, high-frequency power.</li>
<li><b>Closest to the middle:</b> this event sits 0.33 robust SD from the pooled control median:
781 uV (median 738), half-width 9.6 ms (9.4), 12.3 dB (13.7).</li>
<li><b>Typical shape:</b> its CSD over depth and time correlates 0.92 with its own recording's average DS.</li>
<li><b>Standalone:</b> no other detected event of any kind within +-350 ms (880 of the 1,766 qualify).</li>
<li><b>Result:</b> it ranked first on the two rankings combined, and Root Canal also calls it a DS when the recording is
classified on its own.</li>
<li>Upper-blade sink at +0.2 ms (Ch 34, -0.99 mV); hilar positivity at +1.0 ms (Ch 46, +0.80 mV);
lower-blade sink about 14 ms later (Ch 54).</li>
</ul>

<h2>4. The IED</h2>
<ul>
<li>Stamp 1197.3657 s is the event's Root Canal ("Hidden IEDs") and Incisor stamp; Doppler has the same event at
1197.3602 s.</li>
<li>The fast deflection starts at about 1197.360 s (-5 ms); the largest deflection is at 1197.3650 s in the hilus
(Ch 43, +2.19 mV).</li>
<li>m34 s5 has no clock breaks, so sample-count time and timestamp time agree to the millisecond.</li>
<li>A dentate spike at 1196.858 s and a rejected event at 1197.732 s both fall outside the window.</li>
</ul>

<h2>5. Spectrogram contacts</h2>
<table>
<tr><th>Event</th><th>Contacts (both versions)</th><th>Why these</th></tr>
<tr><td>Control DS (m59 s4)</td><td>Ch 10, 34, 46, 54</td><td>CA1 for contrast; upper-blade DS sink; hilar positivity; lower-blade sink</td></tr>
<tr><td>PTEN IED (m34 s5)</td><td>Ch 6, 28, 42, 56</td><td>CA1 for contrast; upper dentate; hilus; lower blade</td></tr>
</table>
<p>Colored arrowheads on the voltage traces mark these contacts.</p>

<h2>6. Methods (for the legend or methods section)</h2>
<ul>
<li><b>Data:</b> 64-contact linear silicon probe, 50 um spacing; every even contact shown (100 um apart), top = dorsal.
Raw Neuralynx CSC files were read through Jarvis and downsampled from 30 kHz to 2.5 kHz with a zero-phase
anti-alias filter.</li>
<li><b>Filters</b> (all zero-phase): 60 Hz notch (Q = 30) on everything; theta 4-12 Hz and DS 5-100 Hz Butterworth band-pass, order 3;
the IED is unfiltered apart from the notch.</li>
<li><b>CSD:</b> -d2V/dz2 over the even contacts (100 um), end contacts duplicated (Vaknin et al., 1988), conductivity
omitted; shown in mV/mm2 (sink negative). Version 1 uses a blue-white-red map, version 2 the jet map (green at zero).
Theta panels share one color scale.</li>
<li><b>Bad contacts:</b> replaced by the mean of the even neighbors: Ch 34 and 38 (CTL theta, m6), Ch 8 (IED, m34).
CSC59 is dead in every recording but is an odd contact, so it is not used.</li>
<li><b>Spectrograms:</b> complex Morlet wavelets, 1-800 Hz (90 log-spaced frequencies), 3 cycles at 1 Hz rising to 10
at 800 Hz. Power is in dB relative to each frequency's median over the surrounding 8 s, computed on the broadband
signal (60 Hz notch only).</li>
<li><b>Scale bars:</b> 50 ms; 1 mV (DS), 2 mV (IED). Depth is given by even channel numbers (2, 16, 32, 48, 64)
on the theta and CSD panels; contacts are 100 um apart.</li>
</ul>

<h2>7. Draft legend</h2>
<p><b>(A)</b> Representative theta-band (4-12 Hz) current source density (CSD) in a wild-type, a <i>Pten</i> KO and a
<i>Pten;Raptor</i> dKO mouse (6 s each). Every even contact of the 64-contact probe is shown (100 um apart); black
traces are the 4-12 Hz LFP on the same contacts. Sinks are negative, sources positive; one color scale for all three.
<b>(B)</b> A representative wild-type dentate spike (300 ms window centered on the spike): LFP (5-100 Hz), CSD of the
same signals, and wavelet spectrograms (1-800 Hz) from the contacts marked by arrowheads. <b>(C)</b> A representative
interictal epileptiform discharge (IED) from a <i>Pten</i> KO mouse (300 ms window): unfiltered LFP, its CSD, and
spectrograms as in (B). A 60 Hz notch filter was applied throughout.</p>

<h2>8. Things to know before using it</h2>
<div class="note">
<p><b>The wild-type theta mouse is m6</b>, the poster's control. The lab excluded m6 from the dentate-spike analysis
for confounds during the experiment. If that matters for this figure, another control can be swapped in.</p>
<p><b>On one shared color scale, DKO theta looks about as strong as PTEN</b> in these windows. The poster's
PTEN &gt; DKO &gt; CTL ordering does not come through clearly in single 6 s windows.</p>
<p><b>Channel numbers are not depths across mice.</b> The same channel sits in different layers in different
recordings (the probe went in at a different depth each time), so rows line up by contact, not by layer.</p>
</div>

<h2>9. Files</h2>
<table>
<tr><td class="mono">Rain_Figure.pdf / _preview.png</td><td>Version 1</td></tr>
<tr><td class="mono">Rain_Figure_v2.pdf / _v2_preview.png</td><td>Version 2 (jet color map)</td></tr>
<tr><td class="mono">Individual panels\\Rain_Figure\\, Individual panels\\Rain_Figure_v2\\</td>
<td>Each panel alone, PDF + 600 dpi PNG: a_Theta_CTL / PTEN / DKO / colorbar / all; b_DS_Voltage / CSD / Spectrogram / all;
c_IED_Voltage / CSD / Spectrogram / all</td></tr>
<tr><td class="mono">make_rain_figure.py, make_rain_figure_v2.py</td><td>Rebuild the figures from the raw recordings (needs D: and the netfiles share for m13 s1)</td></tr>
<tr><td class="mono">TIMESTAMPS_AND_LEGEND.txt</td><td>The same information as plain text</td></tr>
</table>
"""


def main():
    out = os.path.join(HERE, "Rain_Figure_Info.pdf")
    story = fitz.Story(html=HTML, user_css=CSS)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    page = fitz.paper_rect("letter")
    where = page + (54, 54, -54, -54)
    more = 1
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    # append the two figures as their own pages
    doc = fitz.open("pdf", buf.getvalue())
    for f in ("Rain_Figure_v2.pdf", "Rain_Figure.pdf"):
        src = fitz.open(os.path.join(HERE, f))
        doc.insert_pdf(src)
        src.close()
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    print("wrote", out)


if __name__ == "__main__":
    main()
