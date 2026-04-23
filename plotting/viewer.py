"""DearPyGui plot viewer — runs in a separate process.

Receives commands from PlotBridge via cmd_queue, renders plots using ImPlot,
and sends acknowledgements back via rsp_queue.
"""

from __future__ import annotations

import logging
import queue
import traceback
from multiprocessing import Queue

import dearpygui.dearpygui as dpg
import numpy as np

from plotting.style import resolve_color, IMPLOT_MARKER_MAP, apply_dark_theme
from plotting.elements import Curve, DataSource, Histogram, HLine, LinearFit, PlotDef, VLine
from plotting.stats import linear_fit
from plotting.export import capture_framebuffer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _ack(rsp_queue: Queue, req_id: str, payload: dict | None = None) -> None:
    rsp_queue.put_nowait({"type": "ack", "req_id": req_id, "payload": payload or {}})


def _error(rsp_queue: Queue, req_id: str, message: str) -> None:
    rsp_queue.put_nowait({"type": "error", "req_id": req_id, "payload": {"message": message}})


# ---------------------------------------------------------------------------
# Internal element state
# ---------------------------------------------------------------------------

class _CurveState:
    __slots__ = ("element", "series_ids")

    def __init__(self, element: Curve, series_ids: list) -> None:
        self.element = element
        self.series_ids = series_ids


class _HistogramState:
    __slots__ = ("element", "series_id")

    def __init__(self, element: Histogram, series_id) -> None:
        self.element = element
        self.series_id = series_id


class _LinearFitState:
    __slots__ = ("element", "line_id")

    def __init__(self, element: LinearFit, line_id) -> None:
        self.element = element
        self.line_id = line_id


# ---------------------------------------------------------------------------
# Theme helpers
# ---------------------------------------------------------------------------

LINE_WEIGHT = 2.0
MARKER_SIZE = 6.0
MARKER_WEIGHT = 1.5


def _line_theme(color: tuple | None):
    """Per-series theme: always sets line weight; sets color only if provided.

    Applied to every line series unconditionally. ImPlot auto-picks color when
    the theme does not override it.
    """
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, LINE_WEIGHT, category=dpg.mvThemeCat_Plots)
            if color is not None:
                dpg.add_theme_color(dpg.mvPlotCol_Line, color, category=dpg.mvThemeCat_Plots)
    return theme


def _scatter_theme(color: tuple | None, marker: str | None):
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvScatterSeries):
            dpg.add_theme_style(dpg.mvPlotStyleVar_MarkerSize,   MARKER_SIZE,   category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_MarkerWeight, MARKER_WEIGHT, category=dpg.mvThemeCat_Plots)
            if color is not None:
                dpg.add_theme_color(dpg.mvPlotCol_MarkerFill,    color, category=dpg.mvThemeCat_Plots)
                dpg.add_theme_color(dpg.mvPlotCol_MarkerOutline, color, category=dpg.mvThemeCat_Plots)
            if marker is not None:
                val = IMPLOT_MARKER_MAP.get(marker)
                if val is not None:
                    dpg.add_theme_style(dpg.mvPlotStyleVar_Marker, val, category=dpg.mvThemeCat_Plots)
    return theme


def _bar_theme(color: tuple):
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvBarSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Fill, color, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_Line, color, category=dpg.mvThemeCat_Plots)
    return theme


# ---------------------------------------------------------------------------
# PlotViewer
# ---------------------------------------------------------------------------

class PlotViewer:
    def __init__(self, cmd_queue: Queue, rsp_queue: Queue) -> None:
        self._cmd_queue = cmd_queue
        self._rsp_queue = rsp_queue

        self._sources: dict[str, DataSource] = {}
        self._plot_tags: dict[str, int | str] = {}
        self._xaxis_tags: dict[str, int | str] = {}
        self._yaxis_tags: dict[str, list] = {}
        self._xlinks: dict[str, str] = {}
        self._plot_defs: dict[str, PlotDef] = {}
        self._window_tag = None
        self._table_tag = None

        # Element registries: source_name → list of state objects
        self._curves: dict[str, list[_CurveState]] = {}
        self._histograms: dict[str, list[_HistogramState]] = {}
        self._linear_fits: dict[str, list[_LinearFitState]] = {}

    # ------------------------------------------------------------------
    # Queue dispatch
    # ------------------------------------------------------------------

    def poll_queue(self) -> None:
        while True:
            try:
                msg = self._cmd_queue.get_nowait()
            except queue.Empty:
                break
            self._dispatch(msg)

    def _dispatch(self, msg: dict) -> None:
        cmd = msg["cmd"]
        req_id = msg["req_id"]
        payload = msg.get("payload", {})
        try:
            handler = getattr(self, f"_handle_{cmd}", None)
            if handler is None:
                _error(self._rsp_queue, req_id, f"Unknown command: {cmd}")
                return
            handler(req_id, payload)
        except Exception:
            _error(self._rsp_queue, req_id, traceback.format_exc())

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_ping(self, req_id: str, payload: dict) -> None:
        _ack(self._rsp_queue, req_id)

    def _handle_quit(self, req_id: str, payload: dict) -> None:
        _ack(self._rsp_queue, req_id)
        dpg.stop_dearpygui()

    def _handle_configure_figure(self, req_id: str, payload: dict) -> None:
        title: str = payload["title"]
        plots: list[PlotDef] = payload["plots"]

        self._clear_figure()

        for plot_def in plots:
            for elem in plot_def.elements:
                if hasattr(elem, "source") and elem.source not in self._sources:
                    self._sources[elem.source] = DataSource()

        max_row = max((p.row + p.rowspan for p in plots), default=1)
        max_col = max((p.col + p.colspan for p in plots), default=1)

        self._window_tag = dpg.add_window(label=title, tag="__plot_window__",
                                          width=-1, height=-1)

        self._table_tag = dpg.add_table(
            parent=self._window_tag,
            header_row=False,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
        )
        for _ in range(max_col):
            dpg.add_table_column(parent=self._table_tag)

        plots_by_cell: dict[tuple[int, int], PlotDef] = {}
        occupied: set[tuple[int, int]] = set()
        for p in plots:
            plots_by_cell[(p.row, p.col)] = p
            for dr in range(p.rowspan):
                for dc in range(p.colspan):
                    occupied.add((p.row + dr, p.col + dc))

        for row_idx in range(max_row):
            with dpg.table_row(parent=self._table_tag):
                for col_idx in range(max_col):
                    cell = (row_idx, col_idx)
                    if cell in plots_by_cell:
                        self._create_plot(plots_by_cell[cell])
                    elif cell not in occupied:
                        dpg.add_text("")

        for p in plots:
            if p.xlink and p.xlink in self._plot_tags:
                self._xlinks[p.id] = p.xlink

        dpg.set_primary_window("__plot_window__", True)
        _ack(self._rsp_queue, req_id)

    def _handle_append_batch(self, req_id: str, payload: dict) -> None:
        data: dict[str, list] = payload["data"]
        for source_name, pairs in data.items():
            ds = self._sources.get(source_name)
            if ds is not None:
                ds.append_pairs(pairs)
                self._redraw_source(source_name)

    def _handle_set_axis_limits(self, req_id: str, payload: dict) -> None:
        plot_id: str = payload["plot_id"]
        xlim = payload.get("xlim")
        ylims = payload.get("ylims")

        if xlim is not None and plot_id in self._xaxis_tags:
            dpg.set_axis_limits(self._xaxis_tags[plot_id], xlim[0], xlim[1])

        if ylims is not None:
            yaxis_list = self._yaxis_tags.get(plot_id, [])
            for idx, lim in ylims.items():
                idx = int(idx)
                if idx < len(yaxis_list) and lim is not None:
                    dpg.set_axis_limits(yaxis_list[idx], lim[0], lim[1])

    def _handle_save_png(self, req_id: str, payload: dict) -> None:
        path: str = payload["path"]
        try:
            capture_framebuffer(path)
            _ack(self._rsp_queue, req_id, {"path": path})
        except Exception as e:
            _error(self._rsp_queue, req_id, f"save_png failed: {e}")

    def _handle_clear_figure(self, req_id: str, payload: dict) -> None:
        self._clear_figure()
        _ack(self._rsp_queue, req_id)

    # ------------------------------------------------------------------
    # Figure building
    # ------------------------------------------------------------------

    def _clear_figure(self) -> None:
        if self._window_tag is not None and dpg.does_item_exist("__plot_window__"):
            dpg.delete_item("__plot_window__")
        self._window_tag = None
        self._table_tag = None
        self._sources.clear()
        self._plot_tags.clear()
        self._xaxis_tags.clear()
        self._yaxis_tags.clear()
        self._xlinks.clear()
        self._plot_defs.clear()
        self._curves.clear()
        self._histograms.clear()
        self._linear_fits.clear()

    def _create_plot(self, p: PlotDef) -> None:
        self._plot_defs[p.id] = p

        plot_tag = dpg.add_plot(label=p.title or None, width=-1, height=-1,
                                anti_aliased=True, crosshairs=True)
        self._plot_tags[p.id] = plot_tag

        x_axis = dpg.add_plot_axis(dpg.mvXAxis, label=p.xlabel, parent=plot_tag,
                                    auto_fit=(p.xlim is None))
        self._xaxis_tags[p.id] = x_axis
        if p.xlim is not None:
            dpg.set_axis_limits(x_axis, p.xlim[0], p.xlim[1])

        yaxis_tags = []
        yaxis_codes = [dpg.mvYAxis, dpg.mvYAxis2, dpg.mvYAxis3]
        ylims = p.ylims or ()
        for i, ylabel in enumerate(p.ylabels):
            if i >= len(yaxis_codes):
                break  # ImPlot supports at most 3 y-axes
            lim = ylims[i] if i < len(ylims) else None
            y_axis = dpg.add_plot_axis(yaxis_codes[i], label=ylabel, parent=plot_tag,
                                        auto_fit=(lim is None))
            yaxis_tags.append(y_axis)
            if lim is not None:
                dpg.set_axis_limits(y_axis, lim[0], lim[1])

        self._yaxis_tags[p.id] = yaxis_tags

        for elem in p.elements:
            if isinstance(elem, Curve):
                self._create_curve(elem, p.id, yaxis_tags)
            elif isinstance(elem, Histogram):
                self._create_histogram(elem, p.id, yaxis_tags)
            elif isinstance(elem, LinearFit):
                self._create_linear_fit(elem, p.id, yaxis_tags)
            elif isinstance(elem, HLine):
                self._create_hline(elem, p.id, yaxis_tags)
            elif isinstance(elem, VLine):
                self._create_vline(elem, p.id, yaxis_tags)

    def _y_axis(self, plot_id: str, yaxis_idx: int):
        tags = self._yaxis_tags.get(plot_id, [])
        return tags[yaxis_idx] if yaxis_idx < len(tags) else (tags[0] if tags else None)

    def _create_curve(self, elem: Curve, plot_id: str, yaxis_tags: list) -> None:
        y_axis = self._y_axis(plot_id, elem.yaxis)
        color = resolve_color(elem.color)
        label = elem.legend_label if elem.show_in_legend else f"##{elem.source}_line"
        series_ids = []

        if elem.mode in ("line", "line_scatter"):
            sid = dpg.add_line_series([], [], label=label, parent=y_axis)
            dpg.bind_item_theme(sid, _line_theme(color))
            series_ids.append(sid)

        if elem.mode in ("scatter", "line_scatter"):
            sc_label = label if elem.mode == "scatter" else f"##{elem.source}_scatter"
            sid = dpg.add_scatter_series([], [], label=sc_label, parent=y_axis)
            dpg.bind_item_theme(sid, _scatter_theme(color, elem.marker))
            series_ids.append(sid)

        self._curves.setdefault(elem.source, []).append(_CurveState(elem, series_ids))

    def _create_histogram(self, elem: Histogram, plot_id: str, yaxis_tags: list) -> None:
        y_axis = self._y_axis(plot_id, elem.yaxis)
        color = resolve_color(elem.color)
        label = elem.legend_label if elem.show_in_legend else f"##{elem.source}_hist"

        horizontal = (elem.orientation == "horizontal")
        sid = dpg.add_bar_series([], [], label=label, parent=y_axis, horizontal=horizontal)
        if color is not None:
            dpg.bind_item_theme(sid, _bar_theme(color))

        self._histograms.setdefault(elem.source, []).append(_HistogramState(elem, sid))

    def _create_linear_fit(self, elem: LinearFit, plot_id: str, yaxis_tags: list) -> None:
        y_axis = self._y_axis(plot_id, elem.yaxis)
        color = resolve_color(elem.color)
        label = elem.legend_label_template if elem.show_in_legend else f"##{elem.source}_fit"

        line_id = dpg.add_line_series([], [], label=label, parent=y_axis)
        dpg.bind_item_theme(line_id, _line_theme(color))

        self._linear_fits.setdefault(elem.source, []).append(_LinearFitState(elem, line_id))

    def _create_hline(self, elem: HLine, plot_id: str, yaxis_tags: list) -> None:
        y_axis = self._y_axis(plot_id, elem.yaxis)
        color = resolve_color(elem.color)
        label = elem.legend_label if elem.show_in_legend else f"##hline_{elem.value}"

        sid = dpg.add_inf_line_series([elem.value], label=label, parent=y_axis, horizontal=True)
        dpg.bind_item_theme(sid, _line_theme(color))

    def _create_vline(self, elem: VLine, plot_id: str, yaxis_tags: list) -> None:
        y_axis = yaxis_tags[0] if yaxis_tags else None
        color = resolve_color(elem.color)
        label = elem.legend_label if elem.show_in_legend else f"##vline_{elem.value}"

        sid = dpg.add_inf_line_series([elem.value], label=label, parent=y_axis, horizontal=False)
        dpg.bind_item_theme(sid, _line_theme(color))

    # ------------------------------------------------------------------
    # Data update → element redraw
    # ------------------------------------------------------------------

    def _redraw_source(self, source_name: str) -> None:
        ds = self._sources.get(source_name)
        if ds is None:
            return

        for state in self._curves.get(source_name, []):
            for sid in state.series_ids:
                dpg.set_value(sid, [list(ds.x), list(ds.y)])

        for state in self._histograms.get(source_name, []):
            self._redraw_histogram(state, ds)

        for state in self._linear_fits.get(source_name, []):
            self._redraw_linear_fit(state, ds)

    def _redraw_histogram(self, state: _HistogramState, ds: DataSource) -> None:
        if not ds.y:
            return
        counts, edges = np.histogram(ds.y, bins=state.element.bins)
        centers = (edges[:-1] + edges[1:]) / 2
        if state.element.orientation == "horizontal":
            dpg.set_value(state.series_id, [counts.tolist(), centers.tolist()])
        else:
            dpg.set_value(state.series_id, [centers.tolist(), counts.tolist()])

    def _redraw_linear_fit(self, state: _LinearFitState, ds: DataSource) -> None:
        if len(ds.x) < 2:
            return
        try:
            fit = linear_fit(ds.x, ds.y)
        except Exception:
            return

        x_min, x_max = min(ds.x), max(ds.x)
        dpg.set_value(state.line_id, [
            [x_min, x_max],
            [fit.slope * x_min + fit.intercept, fit.slope * x_max + fit.intercept],
        ])

        if state.element.legend_label_template:
            label = state.element.legend_label_template.format(
                slope=fit.slope,
                intercept=fit.intercept,
                r_squared=fit.r_squared,
            )
            dpg.set_item_label(state.line_id, label)

    # ------------------------------------------------------------------
    # X-link propagation (called each frame)
    # ------------------------------------------------------------------

    def _propagate_xlinks(self) -> None:
        for linked_id, anchor_id in self._xlinks.items():
            if anchor_id not in self._xaxis_tags or linked_id not in self._xaxis_tags:
                continue
            lims = dpg.get_axis_limits(self._xaxis_tags[anchor_id])
            dpg.set_axis_limits(self._xaxis_tags[linked_id], lims[0], lims[1])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def viewer_main(cmd_queue: Queue, rsp_queue: Queue) -> None:
    """Entry point for the viewer process. Launched by PlotBridge."""
    dpg.create_context()
    dpg.create_viewport(title="Plot Viewer", width=1200, height=800)

    apply_dark_theme()
    dpg.set_global_font_scale(1.15)

    viewer = PlotViewer(cmd_queue, rsp_queue)

    dpg.setup_dearpygui()
    dpg.show_viewport()

    while dpg.is_dearpygui_running():
        viewer.poll_queue()
        viewer._propagate_xlinks()
        dpg.render_dearpygui_frame()

    dpg.destroy_context()
