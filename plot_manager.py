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

    def __init__(self, root: tk.Tk):
        self.root = root
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax2 = None
        self.lines = {}
        self.secondary_series = set()
        self.styles = {}
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas_widget = self.canvas.get_tk_widget()

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
        self.canvas.draw_idle()
        self.root.update_idletasks()

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
        self.canvas.draw_idle()
        self.root.update_idletasks()

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
        self.canvas.draw_idle()
        self.root.update_idletasks()

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

    def _update_legend(self):
        """Refresh legend including secondary axis series."""
        handles = [meta["line"] for meta in self.lines.values()]
        if handles:
            self.ax.legend(handles=handles, loc="upper left")
