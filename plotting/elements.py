"""Dataclass definitions for the plotting system.

Shared by the main process (PlotBridge) and the viewer process (DearPyGui).
These are plain data containers — no DearPyGui or UI imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class DataSource:
    """Named (x, y) data stream. Held locally by PlotBridge; mirrored in the viewer."""

    __slots__ = ("x", "y")

    def __init__(self) -> None:
        self.x: list[float] = []
        self.y: list[float] = []

    def append_point(self, x: float, y: float) -> None:
        self.x.append(x)
        self.y.append(y)

    def append_many(self, xs: Sequence[float], ys: Sequence[float]) -> None:
        self.x.extend(xs)
        self.y.extend(ys)

    def append_pairs(self, pairs: list[tuple[float, float]]) -> None:
        for x, y in pairs:
            self.x.append(x)
            self.y.append(y)

    def clear(self) -> None:
        self.x.clear()
        self.y.clear()


@dataclass(frozen=True)
class LinearFitResult:
    slope: float
    intercept: float
    r_squared: float


# ---------------------------------------------------------------------------
# Visual elements — each wraps one ImPlot primitive
# ---------------------------------------------------------------------------

@dataclass
class Curve:
    """Line, scatter, or line+scatter series bound to a data source."""
    source: str
    mode: str = "line"                  # "line" | "scatter" | "line_scatter"
    color: Any = None                   # None = auto-pick
    marker: str | None = None           # "o", "x", "s", "t", "d", "+"
    line_style: str = "solid"           # "solid" | "dash" | "dot" | "dash_dot"
    yaxis: int = 0
    legend_label: str = ""
    show_in_legend: bool = True


@dataclass
class Histogram:
    """Bar histogram recomputed from a data source's y-values on every update."""
    source: str
    bins: int = 50
    color: Any = None
    orientation: str = "horizontal"     # "horizontal" | "vertical"
    yaxis: int = 0
    legend_label: str = ""
    show_in_legend: bool = True


@dataclass
class LinearFit:
    """Live linear regression line + annotation, recomputed on source update."""
    source: str
    color: Any = None
    yaxis: int = 0
    legend_label_template: str = ""     # supports {slope}, {intercept}, {r_squared}
    show_in_legend: bool = True


@dataclass
class HLine:
    """Horizontal reference line at a fixed y-value."""
    value: float
    color: Any = None
    line_style: str = "solid"
    yaxis: int = 0
    legend_label: str = ""
    show_in_legend: bool = True


@dataclass
class VLine:
    """Vertical reference line at a fixed x-value."""
    value: float
    color: Any = None
    line_style: str = "solid"
    legend_label: str = ""
    show_in_legend: bool = True


# ---------------------------------------------------------------------------
# Plot definition
# ---------------------------------------------------------------------------

@dataclass
class PlotDef:
    """Defines a subplot in the figure grid.

    Grid dimensions are inferred from the maximum row/col across all PlotDefs.
    ylabels determines the number of y-axes (1 to 3).
    """
    id: str
    row: int = 0
    col: int = 0
    rowspan: int = 1
    colspan: int = 1
    title: str = ""
    xlabel: str = ""
    ylabels: tuple[str, ...] = ("",)
    yscales: tuple[str, ...] = ("linear",)
    xlim: tuple[float, float] | None = None
    ylims: tuple[tuple[float, float] | None, ...] | None = None
    xlink: str = ""
    elements: list = field(default_factory=list)
