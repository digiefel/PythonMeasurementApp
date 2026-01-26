import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Iterable, Tuple

import tkinter as tk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.artist import Artist


@dataclass
class PlotSpec:
    title: str
    xlabel: str
    ylabel: str
    primary_series: str = "Data"
    styles: Dict[str, dict] = field(default_factory=dict)
    secondary_series: List[str] = field(default_factory=list)
    secondary_ylabel: Optional[str] = None
    secondary_yscale: Optional[str] = None
    initial_series: List[str] = field(default_factory=list)


class PlotManager:
    """Encapsulates matplotlib <-> Tk embedding and simple live plotting."""

    # Relative change threshold before we treat limits as updated
    LIMIT_CHANGE_RATIO = 0.01

    def __init__(self, root: tk.Tk, use_blit: bool = True):
        self.root = root
        self.fig = Figure(figsize=(5, 4), dpi=100, layout='compressed')
        self.fig.patch.set_alpha(0)
        self.ax = self.fig.add_subplot(111)
        self.ax2 = None
        # Series bookkeeping: label -> {line, x, y, ax}
        self.lines: Dict[str, dict] = {}
        self.secondary_series = set()
        self.styles: Dict[str, dict] = {}

        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.use_blit = use_blit
        # Blitting state (this is the "BlitManager" folded into the class)
        self._bg = None
        self._animated: List[Artist] = []
        self._last_limits = None
        self._full_draw_pending = False
        if self.use_blit:
            self.canvas.mpl_connect("draw_event", self._on_draw)

    def start(self, spec: PlotSpec):
        """
        Reset plot with a new specification and perform an initial full draw.

        Clears any existing data, configures titles/labels/grid, sets up
        a secondary y-axis if requested, creates any initial series, and
        draws the empty-but-configured plot. After this, use add_point
        and add_series to stream in data.
        """
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.ax2 = None

        self.lines.clear()
        self.secondary_series = set(spec.secondary_series or [])
        self.styles = spec.styles or {}
        self._animated.clear()
        self._bg = None
        self._last_limits = None

        self.ax.set_title(spec.title)
        self.ax.set_xlabel(spec.xlabel)
        self.ax.set_ylabel(spec.ylabel)
        self.ax.grid(True, linestyle="--", alpha=0.4)

        if self.secondary_series:
            self.ax2 = self.ax.twinx()
            self.ax2.set_ylabel(spec.secondary_ylabel or "")
            if spec.secondary_yscale:
                self.ax2.set_yscale(spec.secondary_yscale)

        initial_labels = spec.initial_series or (
            [spec.primary_series] if spec.primary_series else []
        )
        for lbl in initial_labels:
            self._ensure_line(lbl)
        for lbl in self.secondary_series:
            self._ensure_line(lbl)

        self._update_legend()

        # Full draw so the background (including legend) is captured on draw_event.
        self._request_full_draw()
        self._last_limits = self._capture_limits()

    def append_point(self, x: float, y: float, series_label: str = "Data"):
        """
        Append a point to a series and refresh the view (with blitting if possible).
        """
        if series_label not in self.lines:
            self._ensure_line(series_label)
            self._update_legend()

        series = self.lines[series_label]
        series["x"].append(x)
        series["y"].append(y)
        series["line"].set_data(series["x"], series["y"])

        self._update_after_data_change()

    def add_series(self, xs: Iterable[float], ys: Iterable[float], series_label: str):
        """Set or replace the full data of a series and refresh the view. """
        if series_label not in self.lines:
            self._ensure_line(series_label)
            self._update_legend()
        series = self.lines[series_label]
        series["x"] = list(xs)
        series["y"] = list(ys)
        series["line"].set_data(series["x"], series["y"])
        self._update_after_data_change()

    def set_limits(self, xlim: Optional[Tuple[float, float]] = None, ylim: Optional[Tuple[float, float]] = None, y2lim: Optional[Tuple[float, float]] = None):
        """
        Set fixed axis limits and disable autoscaling.
        Call this after start() to pre-set known bounds.
        """
        if xlim is not None:
            self.ax.set_xlim(xlim)
            self.ax.autoscale(enable=False, axis='x')
        if ylim is not None:
            self.ax.set_ylim(ylim)
            self.ax.autoscale(enable=False, axis='y')
        if y2lim is not None and self.ax2:
            self.ax2.set_ylim(y2lim)
            self.ax2.autoscale(enable=False, axis='y')
        self._last_limits = self._capture_limits()
        self._request_full_draw()

    def append_points(self, points: dict):
        """
        Append multiple points to multiple series in one update.
        points: {series_label: [(x1, y1), (x2, y2), ...], ...}
        Only triggers one redraw at the end.
        """
        for series_label, xy_list in points.items():
            if series_label not in self.lines:
                self._ensure_line(series_label)
                self._update_legend()
            series = self.lines[series_label]
            for x, y in xy_list:
                series["x"].append(x)
                series["y"].append(y)
            series["line"].set_data(series["x"], series["y"])
        self._update_after_data_change()

    def finish(self, save_path):
        """Save the current visual state to an image file."""
        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            self.fig.savefig(save_path, dpi=150, bbox_inches="tight")

    def _ensure_line(self, label: str):
        """Create a line for the given label if it does not exist."""
        if label in self.lines:
            return
        target_ax = self.ax2 if (self.ax2 and label in self.secondary_series) else self.ax

        style = self.styles.get(label, {})

        line, = target_ax.plot(
            [],
            [],
            label=label,
            marker=style.get("marker", None),
            color=style.get("color", None),
            linestyle=style.get("linestyle", "-"),
            linewidth=style.get("linewidth", None),
        )

        self.lines[label] = {"line": line, "x": [], "y": [], "ax": target_ax}

        if self.use_blit:
            self._add_animated(line)

    def _update_legend(self):
        handles = [meta["line"] for meta in self.lines.values()]
        if handles:
            self.ax.legend(handles=handles, loc="upper left")
        if self.use_blit:
            # Legend changed layout; force full draw so background is updated.
            self._bg = None
            self._request_full_draw()
            self._last_limits = self._capture_limits()

    # ------------------------------------------------------------------
    # Internal helpers: blitting (BlitManager logic)
    # ------------------------------------------------------------------
    
    def _request_full_draw(self) -> None:
        """Schedule a full draw once, to be executed in the Tk event loop."""
        if not self.use_blit:
            self.canvas.draw_idle()
            return
        if self._full_draw_pending:
            return  # one is already queued
        self._full_draw_pending = True

        def _do_draw():
            # This runs once after Tk gets back to the event loop.
            self._full_draw_pending = False
            # Background and limits will be updated in _on_draw via draw_event.
            self.canvas.draw_idle()

        # Use after_idle to mirror Tk's own delayed drawing model.
        self.root.after_idle(_do_draw)


    def _add_animated(self, art: Artist) -> None:
        if art.figure is not self.fig:
            raise RuntimeError("Animated artist must belong to this figure.")
        art.set_animated(True)
        self._animated.append(art)

    def _on_draw(self, event) -> None:
        """
        draw_event callback: copy the full-figure background and draw
        all animated artists once. This synchronizes background capture
        exactly with Matplotlib's drawing.
        """
        cv = self.canvas
        if event is not None and event.canvas is not cv:
            return
        self._bg = cv.copy_from_bbox(self.fig.bbox)
        self._draw_animated()

    def _draw_animated(self) -> None:
        for a in self._animated:
            self.fig.draw_artist(a)

    def _blit_update(self) -> None:
        cv = self.canvas
        if self._bg is None:
            # If we missed a draw_event for some reason, synthesize one.
            self._on_draw(None)
        else:
            cv.restore_region(self._bg)
            self._draw_animated()
            cv.blit(self.fig.bbox)
        cv.flush_events()

    # ------------------------------------------------------------------
    # Internal helpers: autoscaling + redraw policy
    # ------------------------------------------------------------------

    def _update_after_data_change(self) -> None:
        # Recompute limits.
        self.ax.relim()
        self.ax.autoscale_view()
        if self.ax2:
            self.ax2.relim()
            self.ax2.autoscale_view(scalex=False)

        if not self.use_blit:
            self._request_full_draw()
            return

        new_limits = self._capture_limits()
        if self._last_limits is None or self._limits_changed(new_limits, self._last_limits):
            # Axis limits changed significantly: full draw → new background.
            self._request_full_draw()
            self._last_limits = self._capture_limits()
        else:
            # Fast path: blit only the animated artists (lines).
            self._blit_update()

    def _capture_limits(self):
        lims = [self.ax.get_xlim(), self.ax.get_ylim()]
        if self.ax2:
            lims.append(self.ax2.get_ylim())
        return tuple(lims)

    def _limits_changed(self, new_limits, old_limits) -> bool:
        if len(new_limits) != len(old_limits):
            return True
        for new_bounds, old_bounds in zip(new_limits, old_limits):
            if self._bounds_changed(new_bounds, old_bounds):
                return True
        return False

    def _bounds_changed(self, new_bounds, old_bounds) -> bool:
        new_min, new_max = new_bounds
        old_min, old_max = old_bounds
        span = max(abs(old_max - old_min), 1e-12)
        tol = span * self.LIMIT_CHANGE_RATIO
        return (abs(new_min - old_min) > tol) or (abs(new_max - old_max) > tol)
