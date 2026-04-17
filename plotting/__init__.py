"""Plotting system: DearPyGui viewer in a separate process.

Public surface used by procedures and runner:

    from plotting import PlotBridge, PlotDef, Curve, Histogram, LinearFit, HLine, VLine
    from plotting import linear_fit, DataSource, LinearFitResult
"""

from plotting.elements import (
    DataSource,
    LinearFitResult,
    PlotDef,
    Curve,
    Histogram,
    LinearFit,
    HLine,
    VLine,
)
from plotting.stats import linear_fit
from plotting.bridge import PlotBridge

__all__ = [
    "PlotBridge",
    "PlotDef",
    "Curve",
    "Histogram",
    "LinearFit",
    "HLine",
    "VLine",
    "DataSource",
    "LinearFitResult",
    "linear_fit",
]
