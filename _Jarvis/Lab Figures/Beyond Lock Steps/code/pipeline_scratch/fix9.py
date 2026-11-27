import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_words.py")
s = io.open(p, encoding="utf-8").read()
a0 = s.index("e, The six separable recordings.")
a1 = s.index("Figure 3 |")
new = """e, The six separable recordings: mean sink amplitude (+- s.e.m.) of DS1 and DS2 by depth in the analysed band, both on one
scale per recording. Dashed lines, the noise floor of each mean (99th percentile of the mean's |CSD| more than 30 ms from the
DS peak); ticks at the right, the sink centroid above the floor. DS1 is 7-16%% of events (median 8%%) and its peak sink is
0.28-0.54 times DS2's. Where DS1 clears its floor its sink lies at the outermost contacts of the band, 98-260 µm distal to
DS2's; the classifier sorts events by sink position, so this offset is partly a consequence of the classification.
f, DS1 peak sink over its noise floor (the larger of the two blades), by whether DS1 and DS2 are separable. No test is made.

"""
s = s[:a0] + new + s[a1:]
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
