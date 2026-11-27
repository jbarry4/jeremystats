import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import style as S
import section as X

t = time.time()
fig = S.figure(12.0, 1.9)
PH = [(["Hilus"], "Hilus", "firing"), (["Hilus", "Supra blade"], "Supra blade", "firing"),
      (["Hilus", "Supra blade", "Infra blade"], "Infra blade", "silent"), (["Hilus", "Supra blade", "Infra blade", "CA1"], "CA1", "silent")]
for k, (act, new, un) in enumerate(PH):
    a = S.ax_at(fig, 0.1 + 3.0 * k, 0.05, 2.75, 1.8)
    X.draw(a, act, new, un, labels=(k == 0))
S.save(fig, sys.argv[1])
print("%.1f s" % (time.time() - t))
