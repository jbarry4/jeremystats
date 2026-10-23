"""
figkit/units.py -- what an axis measures, and the units it may be shown in.

Nobody types a unit. An axis says which quantity it carries and the unit its
numbers arrive in, and the builder offers exactly the units that quantity can
be converted to. Choosing one rescales the ticks -- the numbers drawn are the
same numbers, said in another unit -- so a label can never claim "ms" over
data that is in seconds. The words in front of the unit are the person's;
the unit in brackets is always this module's.

    QUANTITIES          id -> {name, words, units: [(id, factor to SI)]}
    choices(q)          the units an axis of quantity q may show
    factor(q, a, b)     multiply a value in unit a by this to get unit b
    axis_text(words, q, unit)
                        "Time (ms)" -- the only way a label is ever assembled
"""
from __future__ import annotations

# Each unit's factor is to the quantity's SI unit, so any two units of one
# quantity convert through it. Unicode, not "u": a printed figure says µV.
QUANTITIES = {
    "time": {"name": "Time", "words": "Time",
             "units": [("s", 1.0), ("ms", 1e-3), ("µs", 1e-6),
                       ("min", 60.0)]},
    "voltage": {"name": "Voltage", "words": "Voltage",
                "units": [("V", 1.0), ("mV", 1e-3), ("µV", 1e-6)]},
    "frequency": {"name": "Frequency", "words": "Frequency",
                  "units": [("Hz", 1.0), ("kHz", 1e3)]},
    "depth": {"name": "Depth", "words": "Depth",
              "units": [("µm", 1e-6), ("mm", 1e-3)]},
    "distance": {"name": "Distance", "words": "Distance",
                 "units": [("µm", 1e-6), ("mm", 1e-3), ("cm", 1e-2)]},
    "power_db": {"name": "Power", "words": "Power",
                 "units": [("dB", 1.0)]},
    "psd": {"name": "Power", "words": "Power",
            "units": [("µV²", 1.0)]},
    "csd": {"name": "Current source density", "words": "CSD",
            "units": [("µA/mm³", 1.0)]},
    "rate": {"name": "Rate", "words": "Rate",
             "units": [("Hz", 1.0), ("per min", 1.0 / 60.0)]},
    "angle": {"name": "Phase", "words": "Phase",
              "units": [("rad", 1.0), ("°", 3.141592653589793 / 180.0)]},
    "channel": {"name": "Channel", "words": "Channel", "units": [("", 1.0)]},
    "count": {"name": "Count", "words": "Count", "units": [("", 1.0)]},
    "ratio": {"name": "Ratio", "words": "Ratio", "units": [("", 1.0)]},
    "percent": {"name": "Percent", "words": "Percent",
                "units": [("%", 1.0)]},
    "zscore": {"name": "z-score", "words": "z", "units": [("SD", 1.0)]},
    "index": {"name": "Index", "words": "Index", "units": [("", 1.0)]},
    "pc": {"name": "Component score", "words": "PC", "units": [("a.u.", 1.0)]},
    "coherence": {"name": "Coherence", "words": "Coherence",
                  "units": [("", 1.0)]},
}

#: The spelling a tool might hand over for a unit, mapped to this module's.
#: Anything a tool reports that is not here is treated as a quantity of its
#: own with exactly that one unit -- shown, never converted.
ALIASES = {"us": "µs", "uv": "µV", "μv": "µV",
           "um": "µm", "μm": "µm", "sec": "s", "seconds": "s",
           "hz": "Hz", "khz": "kHz", "mv": "mV", "v": "V", "db": "dB",
           "deg": "°", "degrees": "°",
           "ua/mm3": "µA/mm³", "uv^2": "µV²",
           "db re 1 uv^2": "dB"}


class UnitError(ValueError):
    pass


def norm_unit(unit):
    """A tool's spelling of a unit, in this module's."""
    if unit is None:
        return ""
    u = str(unit).strip()
    return ALIASES.get(u.lower(), u)


def quantity(q):
    """The quantity record, or a one-unit stand-in for one nobody declared."""
    got = QUANTITIES.get(q)
    if got:
        return got
    return {"name": str(q or "value"), "words": str(q or "Value"),
            "units": [("", 1.0)]}


def choices(q, base_unit=None):
    """The units an axis of this quantity may show.

    A quantity this module does not know offers the tool's own unit and
    nothing else: shown, not converted, because there is no way to know what
    "a.u." is in anything else.
    """
    got = QUANTITIES.get(q)
    if got:
        return [u for u, _f in got["units"]]
    base = norm_unit(base_unit)
    return [base]


def _factor_of(q, unit):
    for u, f in quantity(q)["units"]:
        if u == unit:
            return f
    raise UnitError("%s is not a unit of %s" % (unit or "(none)",
                                                quantity(q)["name"]))


def factor(q, src, dst):
    """Multiply a value in `src` by this to say it in `dst`."""
    src, dst = norm_unit(src), norm_unit(dst)
    if src == dst:
        return 1.0
    if q not in QUANTITIES:
        raise UnitError("%s cannot be converted" % quantity(q)["name"])
    return _factor_of(q, src) / _factor_of(q, dst)


def pick(q, base_unit, wanted):
    """The unit to show: `wanted` if this quantity has it, else the base."""
    base = norm_unit(base_unit)
    want = norm_unit(wanted) if wanted else base
    return want if want in choices(q, base) else base


def axis_text(words, q, unit):
    """The one way an axis label is assembled: the words, then the unit.

    Empty words fall back to the quantity's own, so clearing the field gives
    "Time (ms)" back rather than a bare "(ms)".
    """
    w = (words or "").strip() or quantity(q)["words"]
    u = norm_unit(unit)
    return "%s (%s)" % (w, u) if u else w


def describe():
    """Everything the builder needs to offer the pick-lists."""
    return {q: {"name": v["name"], "words": v["words"],
                "units": [u for u, _f in v["units"]]}
            for q, v in QUANTITIES.items()}
