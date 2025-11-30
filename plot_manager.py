import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import tkinter as tk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


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

    def __init__(self, root: tk.Tk, use_blit: bool = True):
        self.root = root
        self.fig = Figure(figsize=(5, 4), dpi=100, layout='compressed')
        self.fig.patch.set_alpha(0)
        self.ax = self.fig.add_subplot(111)
        self.ax2 = None
        self.lines = {}
        self.secondary_series = set()
        self.styles = {}
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.use_blit = use_blit
        self._background = None
        self._last_limits = None

    def start(self, spec: PlotSpec):
        """Reset plot with a new specification."""
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.ax2 = None
        self.secondary_series = set(spec.secondary_series or [])
        self.styles = spec.styles or {}
        self.ax.set_title(spec.title)
        self.ax.set_xlabel(spec.xlabel)
        self.ax.set_ylabel(spec.ylabel)
        self.ax.grid(True, linestyle="--", alpha=0.4)
        self.lines = {}
        if self.secondary_series:
            self.ax2 = self.ax.twinx()
            self.ax2.set_ylabel(spec.secondary_ylabel or "Resistance (Ohm)")
            if spec.secondary_yscale:
                self.ax2.set_yscale(spec.secondary_yscale)
        initial_labels = spec.initial_series or ([spec.primary_series] if spec.primary_series else [])
        for lbl in initial_labels:
            self._ensure_line(lbl)
        for sec in self.secondary_series:
            self._ensure_line(sec)
        self._update_legend()
        self._redraw_full()
        self._last_limits = self._capture_limits()

    def add_point(self, x, y, series_label: str = "Data"):
        if series_label not in self.lines:
            self._ensure_line(series_label)
            self._update_legend()

        series = self.lines[series_label]
        series["x"].append(x)
        series["y"].append(y)
        series["line"].set_data(series["x"], series["y"])

        self.ax.relim()
        self.ax.autoscale_view()
        if self.ax2:
            self.ax2.relim()
            self.ax2.autoscale_view()
        self._maybe_redraw()

    def add_series(self, xs, ys, series_label: str):
        """Set an entire series in one shot (avoids per-point redraw)."""
        if series_label not in self.lines:
            self._ensure_line(series_label)
            self._update_legend()
        series = self.lines[series_label]
        series["x"] = list(xs)
        series["y"] = list(ys)
        series["line"].set_data(series["x"], series["y"])
        self.ax.relim()
        self.ax.autoscale_view()
        if self.ax2:
            self.ax2.relim()
            self.ax2.autoscale_view()
        self._maybe_redraw()

    def finish(self, save_path: Optional[str] = None):
        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            self.fig.savefig(save_path, dpi=150, bbox_inches="tight")

    def _ensure_line(self, label):
        """Create a line for the given label if it does not exist."""
        if label in self.lines:
            return
        target_ax = self.ax2 if (self.ax2 and label in self.secondary_series) else self.ax
        style_key = label if label in self.styles else ("R_fit" if "R_fit" in self.styles else label)
        style = self.styles.get(style_key, {})
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
        self._background = None  # force full redraw next time
        self._last_limits = None

    def _update_legend(self):
        """Refresh legend including secondary axis series."""
        handles = [meta["line"] for meta in self.lines.values()]
        if handles:
            self.ax.legend(handles=handles, loc="upper left")
            self._background = None  # legend changes require new background
            self._last_limits = None

    def _redraw_full(self):
        """Full draw and capture background for blitting."""
        self.canvas.draw()
        if self.use_blit:
            self._background = self.canvas.copy_from_bbox(self.fig.bbox)
        else:
            self._background = None
        self._last_limits = self._capture_limits()
        self.root.update_idletasks()

    def _maybe_redraw(self):
        """Redraw if limits changed; otherwise blit."""
        if not self.use_blit:
            self.canvas.draw_idle()
            self.root.update_idletasks()
            self._last_limits = self._capture_limits()
            return
        limits = self._capture_limits()
        if self._background is None or self._limits_changed(limits):
            self._redraw_full()
        else:
            self._blit_draw()
            self._last_limits = limits

    def _blit_draw(self):
        """Draw updated artists using blit when available."""
        if self.use_blit and self._background is not None:
            self.canvas.restore_region(self._background)
            # Draw all lines on both axes
            for meta in self.lines.values():
                meta["ax"].draw_artist(meta["line"])
            # Draw legend if present
            if self.ax.legend_:
                self.ax.draw_artist(self.ax.legend_)
            if self.ax2 and self.ax2.legend_:
                self.ax2.draw_artist(self.ax2.legend_)
            self.canvas.blit(self.fig.bbox)
            self.canvas.flush_events()
        else:
            self.canvas.draw_idle()
        self.root.update_idletasks()

    def _capture_limits(self):
        """Capture current axis limits for change detection."""
        lims = [self.ax.get_xlim(), self.ax.get_ylim()]
        if self.ax2:
            lims.append(self.ax2.get_ylim())
        return tuple(lims)

    def _limits_changed(self, limits):
        """Detect if axis limits changed since last redraw."""
        if self._last_limits is None:
            return True
        if len(limits) != len(self._last_limits):
            return True
        for a, b in zip(limits, self._last_limits):
            if a != b:
                return True
        return False
