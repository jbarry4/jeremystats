# first-importer-pays

_Heavy libraries in backend/ go through lazyimp.py; making one module lazy just moves the cost to the next importer. cfc.py is the exception._

Start-up cost of a Python package lands on whichever backend module imports
it FIRST, so making one module lazy only moves the cost: making `cfc` lazy
handed its ~1 s of scipy.signal to `csc`, then fooof (which pulls scipy) took
it via Panorama. The cost only disappears when EVERY module-level import of
the package is lazy. `app.py` imports every backend module at boot.

**Why:** set 2026-09-28 — imports were ~3 of the 3.6 s before the server
served; after `backend/lazyimp.py` across 15 modules, 3.6 s → 1.9 s. 831 ms
left is `drift.py`'s `from scipy import stats` (held for last by the user).

**How to apply:** in backend modules use `lazyimp.have("pkg")`,
`lazyimp.module("scipy.signal")`, `lazyimp.names("scipy.signal", "butter", ...)`
— never a module-level `import scipy/sklearn/fooof/matplotlib.pyplot`.
Measure with `python -X importtime -c "import backend.app"` (JARVIS_WARM=0).
EXCEPTION: `cfc.py` must have no package-relative imports — two scripts in
`FOOOF Playgroun` import it as a plain module; `tools/check_panorama.py`
catches a break.

Related: `virtual-time-cannot-time` (a note not copied here)
