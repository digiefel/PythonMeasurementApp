"""DearPyGui plot viewer that runs in a separate process."""

from __future__ import annotations

import logging
import queue
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from multiprocessing import Queue

import dearpygui.dearpygui as dpg
import numpy as np

from app_logging import configure_logging
from plotting.elements import Curve, DataSource, HLine, Histogram, LinearFit, PlotDef, ToolbarButton, VLine
from plotting.export import capture_framebuffer
from plotting.stats import linear_fit
from plotting.style import (
    IMPLOT_MARKER_MAP,
    UI_ITEM_SPACING_X,
    UI_ITEM_SPACING_Y,
    VIEWER_FONT_SCALE,
    VIEWER_VIEWPORT_HEIGHT,
    VIEWER_VIEWPORT_WIDTH,
    apply_plot_theme,
    resolve_color,
)
from si_utils import format_si_compact

logger = logging.getLogger(__name__)


def _ack(rsp_queue: Queue, req_id: str, payload: dict | None = None) -> None:
    rsp_queue.put_nowait({"type": "ack", "req_id": req_id, "payload": payload or {}})


def _error(rsp_queue: Queue, req_id: str, message: str) -> None:
    rsp_queue.put_nowait({"type": "error", "req_id": req_id, "payload": {"message": message}})


class _CurveState:
    __slots__ = ("plot_id", "element", "series_ids")

    def __init__(self, plot_id: str, element: Curve, series_ids: list[int | str]) -> None:
        self.plot_id = plot_id
        self.element = element
        self.series_ids = series_ids


class _HistogramState:
    __slots__ = ("plot_id", "element", "series_id")

    def __init__(self, plot_id: str, element: Histogram, series_id: int | str) -> None:
        self.plot_id = plot_id
        self.element = element
        self.series_id = series_id


class _LinearFitState:
    __slots__ = ("plot_id", "element", "line_id")

    def __init__(self, plot_id: str, element: LinearFit, line_id: int | str) -> None:
        self.plot_id = plot_id
        self.element = element
        self.line_id = line_id


class _HLineState:
    __slots__ = ("plot_id", "element", "series_id")

    def __init__(self, plot_id: str, element: HLine, series_id: int | str) -> None:
        self.plot_id = plot_id
        self.element = element
        self.series_id = series_id


@dataclass(slots=True)
class _AxisFitState:
    axis_tag: int | str
    axis_role: str
    scale_name: str
    dirty: bool = False
    last_limits: tuple[float, float] | None = None
    pending_auto_release: bool = False


@dataclass(slots=True)
class _PlotState:
    plot_id: str
    plot_tag: int | str
    x_axis_tag: int | str
    y_axis_tags: list[int | str]
    x_fit: _AxisFitState | None = None
    y_fits: list[_AxisFitState | None] = field(default_factory=list)
    live_fit_locked: bool = False
    live_fit_idle: bool = False
    last_data_ts: float = 0.0


_AXIS_SCALE_MAP = {
    "linear": dpg.mvPlotScale_Linear,
    "log": dpg.mvPlotScale_Log10,
    "log10": dpg.mvPlotScale_Log10,
    "time": dpg.mvPlotScale_Time,
    "symlog": dpg.mvPlotScale_SymLog,
}

_LINEAR_FIT_MARGIN = 0.08
_LOG_FIT_MARGIN = 0.08
_MIN_LOG_DECADES = 0.20
_MIN_ZERO_Y_PAD = 1e-12
_MIN_ZERO_X_PAD = 0.5
_LIVE_FIT_IDLE_TIMEOUT_S = 0.75

_DEFAULT_TOOLBAR_BUTTONS: tuple[ToolbarButton, ...] = (
    ToolbarButton("documentation", "Documentation", "tool:documentation"),
    ToolbarButton("style_editor", "Style", "tool:style_editor"),
    ToolbarButton("debug", "Debug", "tool:debug"),
    ToolbarButton("about", "About", "tool:about"),
    ToolbarButton("metrics", "Metrics", "tool:metrics"),
    ToolbarButton("font_manager", "Fonts", "tool:font_manager"),
    ToolbarButton("item_registry", "Registry", "tool:item_registry"),
)

# Add new viewer-side toolbar actions here. Procedures can request any registered
# action by passing ToolbarButton(..., action="<key>") to configure_plot(...).
_TOOLBAR_ACTIONS: dict[str, Callable[[], None]] = {
    "tool:documentation": dpg.show_documentation,
    "tool:style_editor": dpg.show_style_editor,
    "tool:debug": dpg.show_debug,
    "tool:about": dpg.show_about,
    "tool:metrics": dpg.show_metrics,
    "tool:font_manager": dpg.show_font_manager,
    "tool:item_registry": dpg.show_item_registry,
}

_LINE_THEME_CACHE: dict[tuple[int, int, int, int], int | str] = {}
_SCATTER_THEME_CACHE: dict[tuple[tuple[int, int, int, int] | None, str | None], int | str] = {}
_BAR_THEME_CACHE: dict[tuple[int, int, int, int], int | str] = {}
_INF_LINE_THEME_CACHE: dict[tuple[int, int, int, int], int | str] = {}


def _resolve_axis_scale(scale_name: str | None) -> int:
    if not scale_name:
        return dpg.mvPlotScale_Linear
    return _AXIS_SCALE_MAP.get(scale_name.lower(), dpg.mvPlotScale_Linear)


def _line_theme(color: tuple[int, int, int, int] | None):
    if color is None:
        return None
    theme = _LINE_THEME_CACHE.get(color)
    if theme is not None:
        return theme

    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Line, color, category=dpg.mvThemeCat_Plots)
    _LINE_THEME_CACHE[color] = theme
    return theme


def _scatter_theme(color: tuple[int, int, int, int] | None, marker: str | None):
    key = (color, marker)
    theme = _SCATTER_THEME_CACHE.get(key)
    if theme is not None:
        return theme

    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvScatterSeries):
            if color is not None:
                dpg.add_theme_color(dpg.mvPlotCol_MarkerFill, color, category=dpg.mvThemeCat_Plots)
                dpg.add_theme_color(dpg.mvPlotCol_MarkerOutline, color, category=dpg.mvThemeCat_Plots)
            marker_value = IMPLOT_MARKER_MAP.get(marker or "")
            if marker_value is not None:
                dpg.add_theme_style(dpg.mvPlotStyleVar_Marker, marker_value, category=dpg.mvThemeCat_Plots)
    _SCATTER_THEME_CACHE[key] = theme
    return theme


def _bar_theme(color: tuple[int, int, int, int]):
    theme = _BAR_THEME_CACHE.get(color)
    if theme is not None:
        return theme

    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvBarSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Fill, color, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_Line, color, category=dpg.mvThemeCat_Plots)
    _BAR_THEME_CACHE[color] = theme
    return theme


def _inf_line_theme(color: tuple[int, int, int, int] | None):
    if color is None:
        return None
    theme = _INF_LINE_THEME_CACHE.get(color)
    if theme is not None:
        return theme

    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvInfLineSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Line, color, category=dpg.mvThemeCat_Plots)
    _INF_LINE_THEME_CACHE[color] = theme
    return theme


class PlotViewer:
    def __init__(self, cmd_queue: Queue, rsp_queue: Queue) -> None:
        self._cmd_queue = cmd_queue
        self._rsp_queue = rsp_queue

        self._sources: dict[str, DataSource] = {}
        self._plot_tags: dict[str, int | str] = {}
        self._xaxis_tags: dict[str, int | str] = {}
        self._yaxis_tags: dict[str, list[int | str]] = {}
        self._xlinks: dict[str, str] = {}
        self._plot_states: dict[str, _PlotState] = {}
        self._plot_defs: dict[str, PlotDef] = {}
        self._window_tag: int | str | None = None
        self._toolbar_tag: int | str | None = None
        self._body_anchor_tag: int | str | None = None
        self._absolute_layout: dict[str, object] | None = None

        self._curves: dict[str, list[_CurveState]] = {}
        self._histograms: dict[str, list[_HistogramState]] = {}
        self._linear_fits: dict[str, list[_LinearFitState]] = {}
        self._hlines_by_source: dict[str, list[_HLineState]] = {}
        self._all_hlines: list[_HLineState] = []
        self._axis_release_tags: set[int | str] = set()

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

    def _handle_ping(self, req_id: str, payload: dict) -> None:
        _ack(self._rsp_queue, req_id)

    def _handle_quit(self, req_id: str, payload: dict) -> None:
        _ack(self._rsp_queue, req_id)
        dpg.stop_dearpygui()

    def _merge_toolbar_buttons(self, extra_buttons: list[ToolbarButton]) -> list[ToolbarButton]:
        merged: dict[str, ToolbarButton] = {button.id: button for button in _DEFAULT_TOOLBAR_BUTTONS}
        for button in extra_buttons:
            merged[button.id] = button
        return list(merged.values())

    def _activate_toolbar_button(self, sender, app_data, user_data) -> None:
        button: ToolbarButton = user_data
        action = _TOOLBAR_ACTIONS.get(button.action)
        if action is None:
            logger.warning("Unknown toolbar action: %s", button.action)
            return
        action()

    def _handle_configure_figure(self, req_id: str, payload: dict) -> None:
        title: str = payload["title"]
        plots: list[PlotDef] = payload["plots"]
        toolbar_buttons: list[ToolbarButton] = payload.get("toolbar_buttons", [])
        row_ratios: list[float] = payload.get("row_ratios", [])
        column_ratios: list[float] = payload.get("column_ratios", [])

        self._clear_figure()

        for plot_def in plots:
            for elem in plot_def.elements:
                source_name = getattr(elem, "source", "")
                if source_name and source_name not in self._sources:
                    self._sources[source_name] = DataSource()

        max_row = max((p.row + p.rowspan for p in plots), default=1)
        max_col = max((p.col + p.colspan for p in plots), default=1)

        self._window_tag = dpg.add_window(label=title, tag="__plot_window__", width=-1, height=-1)

        merged_buttons = self._merge_toolbar_buttons(toolbar_buttons)
        self._toolbar_tag = dpg.add_group(parent=self._window_tag, horizontal=True)
        for button in merged_buttons:
            dpg.add_button(
                parent=self._toolbar_tag,
                label=button.label,
                callback=self._activate_toolbar_button,
                user_data=button,
            )

        dpg.add_separator(parent=self._window_tag)
        self._body_anchor_tag = dpg.add_group(parent=self._window_tag)
        split_layout = self._split_span_layout_spec(plots, max_row, max_col)
        top_span_layout = self._top_span_layout_spec(plots, max_row, max_col)
        if split_layout is not None:
            self._build_split_span_layout(split_layout, row_ratios=row_ratios, column_ratios=column_ratios)
        elif top_span_layout is not None:
            self._build_top_span_layout(top_span_layout, row_ratios=row_ratios, column_ratios=column_ratios)
        else:
            plots_by_cell: dict[tuple[int, int], PlotDef] = {(p.row, p.col): p for p in plots}
            subplots_tag = dpg.add_subplots(
                max_row, max_col,
                parent=self._window_tag,
                width=-1,
                height=-1,
                row_ratios=self._normalize_ratios(row_ratios, max_row),
                column_ratios=self._normalize_ratios(column_ratios, max_col),
                no_title=True,
            )
            for row_idx in range(max_row):
                for col_idx in range(max_col):
                    plot_def = plots_by_cell.get((row_idx, col_idx))
                    if plot_def is not None:
                        self._create_plot(plot_def, parent=subplots_tag)
                    else:
                        dpg.add_plot(parent=subplots_tag)

        for plot_def in plots:
            if plot_def.xlink and plot_def.xlink in self._plot_tags:
                self._xlinks[plot_def.id] = plot_def.xlink
                plot_state = self._plot_states.get(plot_def.id)
                if plot_state is not None:
                    plot_state.x_fit = None

        dpg.set_primary_window("__plot_window__", True)
        _ack(self._rsp_queue, req_id)

    def _handle_append_batch(self, req_id: str, payload: dict) -> None:
        data: dict[str, list[tuple[float, float]]] = payload["data"]
        for source_name, pairs in data.items():
            ds = self._sources.get(source_name)
            if ds is None:
                continue
            ds.append_pairs(pairs)
            self._redraw_source(source_name)

    def _handle_replace_source(self, req_id: str, payload: dict) -> None:
        source_name: str = payload["source"]
        xs = payload["xs"]
        ys = payload["ys"]
        ds = self._sources.get(source_name)
        if ds is None:
            return
        ds.clear()
        ds.append_many(xs, ys)
        self._redraw_source(source_name)

    def _handle_set_axis_limits(self, req_id: str, payload: dict) -> None:
        plot_id: str = payload["plot_id"]
        xlim = payload.get("xlim")
        ylims = payload.get("ylims")
        plot_state = self._plot_states.get(plot_id)

        if xlim is not None and plot_id in self._xaxis_tags:
            axis_tag = self._xaxis_tags[plot_id]
            dpg.set_axis_limits(axis_tag, xlim[0], xlim[1])
            self._axis_release_tags.add(axis_tag)
            if plot_state is not None:
                plot_state.x_fit = None

        if ylims is not None:
            yaxis_list = self._yaxis_tags.get(plot_id, [])
            for idx, lim in ylims.items():
                axis_idx = int(idx)
                if axis_idx < len(yaxis_list) and lim is not None:
                    axis_tag = yaxis_list[axis_idx]
                    dpg.set_axis_limits(axis_tag, lim[0], lim[1])
                    self._axis_release_tags.add(axis_tag)
                    if plot_state is not None and axis_idx < len(plot_state.y_fits):
                        plot_state.y_fits[axis_idx] = None

    def _handle_save_png(self, req_id: str, payload: dict) -> None:
        path: str = payload["path"]
        try:
            capture_framebuffer(path)
            _ack(self._rsp_queue, req_id, {"path": path})
        except Exception as exc:
            _error(self._rsp_queue, req_id, f"save_png failed: {exc}")

    def _handle_clear_figure(self, req_id: str, payload: dict) -> None:
        self._clear_figure()
        _ack(self._rsp_queue, req_id)

    def _clear_figure(self) -> None:
        if self._window_tag is not None and dpg.does_item_exist("__plot_window__"):
            dpg.delete_item("__plot_window__")
        self._window_tag = None
        self._toolbar_tag = None

        self._body_anchor_tag = None
        self._absolute_layout = None
        self._sources.clear()
        self._plot_tags.clear()
        self._xaxis_tags.clear()
        self._yaxis_tags.clear()
        self._xlinks.clear()
        self._plot_states.clear()
        self._plot_defs.clear()
        self._curves.clear()
        self._histograms.clear()
        self._linear_fits.clear()
        self._hlines_by_source.clear()
        self._all_hlines.clear()
        self._axis_release_tags.clear()

    def _normalize_ratios(self, ratios: list[float] | tuple[float, ...], count: int) -> list[float]:
        if count <= 0:
            return []
        normalized = list(ratios[:count]) if ratios else []
        if len(normalized) < count:
            normalized.extend([1.0] * (count - len(normalized)))
        clean: list[float] = []
        for value in normalized[:count]:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = 1.0
            clean.append(numeric if numeric > 0 else 1.0)
        return clean

    def _split_span_layout_spec(
        self,
        plots: list[PlotDef],
        max_row: int,
        max_col: int,
    ) -> dict[str, object] | None:
        if len(plots) != 3 or max_row != 2 or max_col != 2:
            return None

        spanning = [
            plot_def
            for plot_def in plots
            if plot_def.row == 0 and plot_def.rowspan == 2 and plot_def.colspan == 1
        ]
        if len(spanning) != 1:
            return None

        spanning_plot = spanning[0]
        stack_col = 1 - spanning_plot.col
        stack_plots = [plot_def for plot_def in plots if plot_def.id != spanning_plot.id]
        if len(stack_plots) != 2:
            return None
        if any(
            plot_def.col != stack_col or plot_def.rowspan != 1 or plot_def.colspan != 1
            for plot_def in stack_plots
        ):
            return None

        ordered_stack = sorted(stack_plots, key=lambda plot_def: plot_def.row)
        if [plot_def.row for plot_def in ordered_stack] != [0, 1]:
            return None

        return {
            "spanning_plot": spanning_plot,
            "stack_plots": ordered_stack,
            "spanning_col": spanning_plot.col,
        }

    def _top_span_layout_spec(
        self,
        plots: list[PlotDef],
        max_row: int,
        max_col: int,
    ) -> dict[str, object] | None:
        if len(plots) != 3 or max_row != 2 or max_col != 2:
            return None

        spanning = [p for p in plots if p.colspan == 2 and p.rowspan == 1]
        if len(spanning) != 1:
            return None

        spanning_plot = spanning[0]
        stack_row = 1 - spanning_plot.row
        stack_plots = [p for p in plots if p.id != spanning_plot.id]
        if any(p.row != stack_row or p.rowspan != 1 or p.colspan != 1 for p in stack_plots):
            return None

        ordered_stack = sorted(stack_plots, key=lambda p: p.col)
        if [p.col for p in ordered_stack] != [0, 1]:
            return None

        return {
            "spanning_plot": spanning_plot,
            "stack_plots": ordered_stack,
            "spanning_row": spanning_plot.row,
        }

    def _build_split_span_layout(
        self,
        layout_spec: dict[str, object],
        *,
        row_ratios: list[float],
        column_ratios: list[float],
    ) -> None:
        spanning_plot = layout_spec["spanning_plot"]
        stack_plots = layout_spec["stack_plots"]
        spanning_col = int(layout_spec["spanning_col"])
        assert isinstance(spanning_plot, PlotDef)
        assert isinstance(stack_plots, list)

        main_container = dpg.add_child_window(
            parent=self._window_tag,
            width=16,
            height=16,
            pos=[0, 0],
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        )
        self._create_plot(spanning_plot, parent=main_container)

        stack_container = dpg.add_child_window(
            parent=self._window_tag,
            width=16,
            height=16,
            pos=[0, 0],
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        )
        stack_tag = dpg.add_subplots(
            2,
            1,
            parent=stack_container,
            width=-1,
            height=-1,
            row_ratios=self._normalize_ratios(row_ratios, 2),
            column_ratios=[1.0],
            no_title=True,
        )
        for plot_def in stack_plots:
            self._create_plot(plot_def, parent=stack_tag)

        self._absolute_layout = {
            "kind": "split_span",
            "main_container": main_container,
            "stack_container": stack_container,
            "stack_tag": stack_tag,
            "spanning_col": spanning_col,
            "column_ratios": self._normalize_ratios(column_ratios, 2),
        }

    def _build_top_span_layout(
        self,
        layout_spec: dict[str, object],
        *,
        row_ratios: list[float],
        column_ratios: list[float],
    ) -> None:
        spanning_plot = layout_spec["spanning_plot"]
        stack_plots = layout_spec["stack_plots"]
        spanning_row = int(layout_spec["spanning_row"])
        assert isinstance(spanning_plot, PlotDef)
        assert isinstance(stack_plots, list)

        span_container = dpg.add_child_window(
            parent=self._window_tag,
            width=16,
            height=16,
            pos=[0, 0],
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        )
        self._create_plot(spanning_plot, parent=span_container)

        stack_container = dpg.add_child_window(
            parent=self._window_tag,
            width=16,
            height=16,
            pos=[0, 0],
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        )
        stack_tag = dpg.add_subplots(
            1,
            2,
            parent=stack_container,
            width=-1,
            height=-1,
            row_ratios=[1.0],
            column_ratios=self._normalize_ratios(column_ratios, 2),
            no_title=True,
        )
        for plot_def in stack_plots:
            self._create_plot(plot_def, parent=stack_tag)

        self._absolute_layout = {
            "kind": "top_span",
            "span_container": span_container,
            "stack_container": stack_container,
            "stack_tag": stack_tag,
            "spanning_row": spanning_row,
            "row_ratios": self._normalize_ratios(row_ratios, 2),
        }

    def _create_plot(self, plot_def: PlotDef, parent: int | str | None = None) -> None:
        self._plot_defs[plot_def.id] = plot_def

        plot_tag = dpg.add_plot(
            label=plot_def.title or None,
            width=-1,
            height=-1,
            parent=parent or 0,
            no_inputs=False,
            no_menus=False,
            no_box_select=False,
            crosshairs=True,
        )
        self._plot_tags[plot_def.id] = plot_tag
        dpg.add_plot_legend(parent=plot_tag)

        x_axis = dpg.add_plot_axis(
            dpg.mvXAxis,
            label=plot_def.xlabel,
            scale=_resolve_axis_scale(plot_def.xscale),
            parent=plot_tag,
            auto_fit=False
        )
        self._xaxis_tags[plot_def.id] = x_axis
        if plot_def.xlim is not None:
            dpg.set_axis_limits(x_axis, plot_def.xlim[0], plot_def.xlim[1])
            self._axis_release_tags.add(x_axis)

        yaxis_tags: list[int | str] = []
        yaxis_codes = [dpg.mvYAxis, dpg.mvYAxis2, dpg.mvYAxis3]
        ylims = plot_def.ylims or ()
        yscales = plot_def.yscales or ()

        for idx, ylabel in enumerate(plot_def.ylabels):
            if idx >= len(yaxis_codes):
                break
            lim = ylims[idx] if idx < len(ylims) else None
            scale_name = yscales[idx] if idx < len(yscales) else "linear"
            y_axis = dpg.add_plot_axis(
                yaxis_codes[idx],
                label=ylabel,
                parent=plot_tag,
                scale=_resolve_axis_scale(scale_name),
                auto_fit=False,
            )
            yaxis_tags.append(y_axis)
            if lim is not None:
                dpg.set_axis_limits(y_axis, lim[0], lim[1])
                self._axis_release_tags.add(y_axis)

        self._yaxis_tags[plot_def.id] = yaxis_tags
        self._plot_states[plot_def.id] = _PlotState(
            plot_id=plot_def.id,
            plot_tag=plot_tag,
            x_axis_tag=x_axis,
            y_axis_tags=yaxis_tags,
            x_fit=None if plot_def.xlim is not None else _AxisFitState(x_axis, axis_role="x", scale_name="linear"),
            y_fits=[
                None
                if ((ylims[idx] if idx < len(ylims) else None) is not None)
                else _AxisFitState(
                    axis_tag,
                    axis_role="y",
                    scale_name=(yscales[idx] if idx < len(yscales) else "linear"),
                )
                for idx, axis_tag in enumerate(yaxis_tags)
            ],
        )

        for elem in plot_def.elements:
            if isinstance(elem, Curve):
                self._create_curve(elem, plot_def.id)
            elif isinstance(elem, Histogram):
                self._create_histogram(elem, plot_def.id)
            elif isinstance(elem, LinearFit):
                self._create_linear_fit(elem, plot_def.id)
            elif isinstance(elem, HLine):
                self._create_hline(elem, plot_def.id)
            elif isinstance(elem, VLine):
                self._create_vline(elem, plot_def.id)

    def _y_axis(self, plot_id: str, yaxis_idx: int):
        tags = self._yaxis_tags.get(plot_id, [])
        return tags[yaxis_idx] if yaxis_idx < len(tags) else (tags[0] if tags else None)

    def _create_curve(self, elem: Curve, plot_id: str) -> None:
        y_axis = self._y_axis(plot_id, elem.yaxis)
        color = resolve_color(elem.color)
        label = elem.legend_label if elem.show_in_legend else f"##{elem.source}_line"
        series_ids: list[int | str] = []

        if elem.mode in ("line", "line_scatter"):
            series_id = dpg.add_line_series([], [], label=label, parent=y_axis)
            theme = _line_theme(color)
            if theme is not None:
                dpg.bind_item_theme(series_id, theme)
            series_ids.append(series_id)

        if elem.mode in ("scatter", "line_scatter"):
            scatter_label = label if elem.mode == "scatter" else f"##{elem.source}_scatter"
            series_id = dpg.add_scatter_series([], [], label=scatter_label, parent=y_axis)
            theme = _scatter_theme(color, elem.marker)
            if theme is not None:
                dpg.bind_item_theme(series_id, theme)
            series_ids.append(series_id)

        self._curves.setdefault(elem.source, []).append(_CurveState(plot_id, elem, series_ids))

    def _create_histogram(self, elem: Histogram, plot_id: str) -> None:
        y_axis = self._y_axis(plot_id, elem.yaxis)
        color = resolve_color(elem.color)
        label = elem.legend_label if elem.show_in_legend else f"##{elem.source}_hist"
        series_id = dpg.add_bar_series([], [], label=label, parent=y_axis, horizontal=(elem.orientation == "horizontal"))
        if color is not None:
            dpg.bind_item_theme(series_id, _bar_theme(color))
        self._histograms.setdefault(elem.source, []).append(_HistogramState(plot_id, elem, series_id))

    def _create_linear_fit(self, elem: LinearFit, plot_id: str) -> None:
        y_axis = self._y_axis(plot_id, elem.yaxis)
        color = resolve_color(elem.color)
        label = elem.legend_label_template if elem.show_in_legend else f"##{elem.source}_fit"
        line_id = dpg.add_line_series([], [], label=label, parent=y_axis)
        theme = _line_theme(color)
        if theme is not None:
            dpg.bind_item_theme(line_id, theme)
        self._linear_fits.setdefault(elem.source, []).append(_LinearFitState(plot_id, elem, line_id))

    def _create_hline(self, elem: HLine, plot_id: str) -> None:
        y_axis = self._y_axis(plot_id, elem.yaxis)
        color = resolve_color(elem.color)
        label = elem.legend_label if elem.show_in_legend else f"##hline_{elem.value}"
        initial_values = [] if elem.source else [elem.value]
        series_id = dpg.add_inf_line_series(initial_values, label=label, parent=y_axis, horizontal=True)
        theme = _inf_line_theme(color)
        if theme is not None:
            dpg.bind_item_theme(series_id, theme)
        state = _HLineState(plot_id, elem, series_id)
        self._all_hlines.append(state)
        if elem.source:
            self._hlines_by_source.setdefault(elem.source, []).append(state)

    def _create_vline(self, elem: VLine, plot_id: str) -> None:
        y_axis = self._y_axis(plot_id, 0)
        color = resolve_color(elem.color)
        label = elem.legend_label if elem.show_in_legend else f"##vline_{elem.value}"
        series_id = dpg.add_inf_line_series([elem.value], label=label, parent=y_axis, horizontal=False)
        theme = _inf_line_theme(color)
        if theme is not None:
            dpg.bind_item_theme(series_id, theme)

    def _redraw_source(self, source_name: str) -> None:
        ds = self._sources.get(source_name)
        if ds is None:
            return

        dirty_plots: set[str] = set()

        for state in self._curves.get(source_name, []):
            for series_id in state.series_ids:
                dpg.set_value(series_id, [list(ds.x), list(ds.y)])
            dirty_plots.add(state.plot_id)

        for state in self._histograms.get(source_name, []):
            self._redraw_histogram(state, ds)
            dirty_plots.add(state.plot_id)

        for state in self._linear_fits.get(source_name, []):
            self._redraw_linear_fit(state, ds)
            dirty_plots.add(state.plot_id)

        for state in self._hlines_by_source.get(source_name, []):
            self._redraw_hline(state, ds)
            dirty_plots.add(state.plot_id)

        for plot_id in dirty_plots:
            self._mark_plot_fit_dirty(plot_id)

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
        dpg.set_value(
            state.line_id,
            [
                [x_min, x_max],
                [fit.slope * x_min + fit.intercept, fit.slope * x_max + fit.intercept],
            ],
        )

        if state.element.legend_label_template:
            resistance = np.inf if fit.slope == 0 else (1.0 / fit.slope)
            dpg.set_item_label(
                state.line_id,
                state.element.legend_label_template.format(
                    slope=fit.slope,
                    intercept=fit.intercept,
                    r_squared=fit.r_squared,
                    resistance=resistance,
                    resistance_si=f"{format_si_compact(resistance)}Ohm",
                ),
            )

    def _redraw_hline(self, state: _HLineState, ds: DataSource) -> None:
        if not ds.y:
            return
        value = next((entry for entry in reversed(ds.y) if np.isfinite(entry)), None)
        if value is None:
            return
        dpg.set_value(state.series_id, [[float(value)]])

    def _mark_plot_fit_dirty(self, plot_id: str) -> None:
        plot_state = self._plot_states.get(plot_id)
        if plot_state is None or plot_state.live_fit_locked:
            return
        plot_state.last_data_ts = time.monotonic()
        plot_state.live_fit_idle = False
        if plot_state.x_fit is not None:
            plot_state.x_fit.dirty = True
        for fit_state in plot_state.y_fits:
            if fit_state is not None:
                fit_state.dirty = True

    def _axis_limits_match(
        self,
        actual: tuple[float, float] | list[float],
        expected: tuple[float, float] | None,
    ) -> bool:
        if expected is None:
            return True
        if len(actual) < 2:
            return False
        a0, a1 = float(actual[0]), float(actual[1])
        e0, e1 = float(expected[0]), float(expected[1])
        tol0 = max(abs(e0) * 1e-6, 1e-12)
        tol1 = max(abs(e1) * 1e-6, 1e-12)
        return abs(a0 - e0) <= tol0 and abs(a1 - e1) <= tol1

    def _plot_limits_changed_from_auto(self, plot_state: _PlotState) -> bool:
        managed_axes: list[_AxisFitState] = []
        if plot_state.x_fit is not None:
            managed_axes.append(plot_state.x_fit)
        managed_axes.extend(fit_state for fit_state in plot_state.y_fits if fit_state is not None)

        for fit_state in managed_axes:
            if fit_state.last_limits is None or not dpg.does_item_exist(fit_state.axis_tag):
                continue
            current_limits = dpg.get_axis_limits(fit_state.axis_tag)
            if not self._axis_limits_match(current_limits, fit_state.last_limits):
                return True
        return False

    def _curve_states_for_plot(self, plot_id: str) -> list[_CurveState]:
        states: list[_CurveState] = []
        for entries in self._curves.values():
            for state in entries:
                if state.plot_id == plot_id:
                    states.append(state)
        return states

    def _hline_states_for_plot(self, plot_id: str) -> list[_HLineState]:
        return [state for state in self._all_hlines if state.plot_id == plot_id]

    def _current_hline_value(self, state: _HLineState) -> float | None:
        if state.element.source:
            ds = self._sources.get(state.element.source)
            if ds is None or not ds.y:
                return None
            return next((entry for entry in reversed(ds.y) if np.isfinite(entry)), None)
        return state.element.value if np.isfinite(state.element.value) else None

    def _fit_linear_axis(self, axis_tag: int | str, values: list[float], axis_role: str) -> tuple[float, float] | None:
        if not values:
            return None
        low = min(values)
        high = max(values)
        span = high - low
        if span > 0:
            pad = span * _LINEAR_FIT_MARGIN
        else:
            center = (low + high) / 2.0
            if axis_role == "x":
                pad = max(abs(center) * _LINEAR_FIT_MARGIN, _MIN_ZERO_X_PAD)
            else:
                pad = max(abs(center) * _LINEAR_FIT_MARGIN, _MIN_ZERO_Y_PAD)
        limits = (low - pad, high + pad)
        dpg.set_axis_limits(axis_tag, limits[0], limits[1])
        return limits

    def _fit_log_axis(self, axis_tag: int | str, values: list[float]) -> tuple[float, float] | None:
        if not values:
            return None
        low = max(min(values), 1e-300)
        high = max(max(values), low * (1.0 + 1e-6))
        low_log = np.log10(low)
        high_log = np.log10(high)
        pad = max((high_log - low_log) * _LOG_FIT_MARGIN, _MIN_LOG_DECADES)
        limits = (10 ** (low_log - pad), 10 ** (high_log + pad))
        dpg.set_axis_limits(axis_tag, limits[0], limits[1])
        return limits

    def _fit_x_axis_from_sources(self, plot_id: str, fit_state: _AxisFitState) -> bool:
        values: list[float] = []
        for state in self._curve_states_for_plot(plot_id):
            ds = self._sources.get(state.element.source)
            if ds is None:
                continue
            values.extend(val for val in ds.x if np.isfinite(val))
        limits = self._fit_linear_axis(fit_state.axis_tag, values, axis_role="x")
        if limits is None:
            return False
        fit_state.last_limits = limits
        fit_state.pending_auto_release = True
        return True

    def _fit_y_axis_from_sources(self, plot_id: str, yaxis_idx: int, fit_state: _AxisFitState) -> bool:
        values: list[float] = []
        for state in self._curve_states_for_plot(plot_id):
            if state.element.yaxis != yaxis_idx:
                continue
            ds = self._sources.get(state.element.source)
            if ds is None:
                continue
            if fit_state.scale_name.lower() in ("log", "log10"):
                values.extend(val for val in ds.y if np.isfinite(val) and val > 0)
            else:
                values.extend(val for val in ds.y if np.isfinite(val))
        for state in self._hline_states_for_plot(plot_id):
            if state.element.yaxis != yaxis_idx:
                continue
            value = self._current_hline_value(state)
            if value is None:
                continue
            if fit_state.scale_name.lower() in ("log", "log10"):
                if value > 0:
                    values.append(value)
            else:
                values.append(value)
        if fit_state.scale_name.lower() in ("log", "log10"):
            limits = self._fit_log_axis(fit_state.axis_tag, values)
        else:
            limits = self._fit_linear_axis(fit_state.axis_tag, values, axis_role="y")
        if limits is None:
            return False
        fit_state.last_limits = limits
        fit_state.pending_auto_release = True
        return True

    def _apply_absolute_layouts(self) -> None:
        if self._absolute_layout is None or self._body_anchor_tag is None:
            return
        if not dpg.does_item_exist(self._body_anchor_tag):
            return

        state = dpg.get_item_state(self._body_anchor_tag)
        pos = state.get("pos")
        content_region = state.get("content_region_avail")
        if pos is None or content_region is None:
            return

        body_x, body_y = int(pos[0]), int(pos[1])
        body_w, body_h = int(content_region[0]), int(content_region[1])
        if body_w <= 0 or body_h <= 0:
            return

        kind = self._absolute_layout.get("kind")

        if kind == "split_span":
            column_ratios = self._absolute_layout["column_ratios"]
            assert isinstance(column_ratios, list)
            gap_x = min(UI_ITEM_SPACING_X, max(body_w - 2, 0))
            usable_w = max(body_w - gap_x, 1)
            ratio_sum = max(sum(column_ratios), 1.0)
            left_w = max(int(round(usable_w * column_ratios[0] / ratio_sum)), 1)
            right_w = max(usable_w - left_w, 1)

            spanning_col = int(self._absolute_layout["spanning_col"])
            main_container = self._absolute_layout["main_container"]
            stack_container = self._absolute_layout["stack_container"]
            stack_tag = self._absolute_layout["stack_tag"]

            if spanning_col == 0:
                main_x = body_x
                stack_x = body_x + left_w + gap_x
                main_w = left_w
                stack_w = right_w
            else:
                stack_x = body_x
                main_x = body_x + right_w + gap_x
                stack_w = right_w
                main_w = left_w

            if dpg.does_item_exist(main_container):
                dpg.configure_item(main_container, pos=[main_x, body_y], width=max(main_w, 1), height=max(body_h, 1))
            if dpg.does_item_exist(stack_container):
                dpg.configure_item(stack_container, pos=[stack_x, body_y], width=max(stack_w, 1), height=max(body_h, 1))
            if dpg.does_item_exist(stack_tag):
                dpg.configure_item(stack_tag, width=-1, height=-1)

        elif kind == "top_span":
            row_ratios = self._absolute_layout["row_ratios"]
            assert isinstance(row_ratios, list)
            gap_y = min(UI_ITEM_SPACING_Y, max(body_h - 2, 0))
            usable_h = max(body_h - gap_y, 1)
            ratio_sum = max(sum(row_ratios), 1.0)
            top_h = max(int(round(usable_h * row_ratios[0] / ratio_sum)), 1)
            bottom_h = max(usable_h - top_h, 1)

            spanning_row = int(self._absolute_layout["spanning_row"])
            span_container = self._absolute_layout["span_container"]
            stack_container = self._absolute_layout["stack_container"]
            stack_tag = self._absolute_layout["stack_tag"]

            if spanning_row == 0:
                span_y, span_h = body_y, top_h
                stack_y, stack_h = body_y + top_h + gap_y, bottom_h
            else:
                stack_y, stack_h = body_y, top_h
                span_y, span_h = body_y + top_h + gap_y, bottom_h

            if dpg.does_item_exist(span_container):
                dpg.configure_item(span_container, pos=[body_x, span_y], width=max(body_w, 1), height=max(span_h, 1))
            if dpg.does_item_exist(stack_container):
                dpg.configure_item(stack_container, pos=[body_x, stack_y], width=max(body_w, 1), height=max(stack_h, 1))
            if dpg.does_item_exist(stack_tag):
                dpg.configure_item(stack_tag, width=-1, height=-1)

    def _release_pending_axis_limits(self) -> None:
        if self._axis_release_tags:
            for axis_tag in list(self._axis_release_tags):
                if dpg.does_item_exist(axis_tag):
                    dpg.set_axis_limits_auto(axis_tag)
            self._axis_release_tags.clear()

        for plot_state in self._plot_states.values():
            managed_axes: list[_AxisFitState] = []
            if plot_state.x_fit is not None:
                managed_axes.append(plot_state.x_fit)
            managed_axes.extend(fit_state for fit_state in plot_state.y_fits if fit_state is not None)

            for fit_state in managed_axes:
                if not fit_state.pending_auto_release:
                    continue
                if dpg.does_item_exist(fit_state.axis_tag):
                    dpg.set_axis_limits_auto(fit_state.axis_tag)
                fit_state.pending_auto_release = False

    def _update_live_fits(self) -> None:
        now = time.monotonic()
        for plot_state in self._plot_states.values():
            if plot_state.live_fit_locked:
                continue

            if self._plot_limits_changed_from_auto(plot_state):
                plot_state.live_fit_locked = True
                continue

            if plot_state.last_data_ts and (now - plot_state.last_data_ts) > _LIVE_FIT_IDLE_TIMEOUT_S:
                plot_state.live_fit_idle = True

            if plot_state.live_fit_idle:
                continue

            if plot_state.x_fit is not None and plot_state.x_fit.dirty:
                self._fit_x_axis_from_sources(plot_state.plot_id, plot_state.x_fit)
                plot_state.x_fit.dirty = False

            for yaxis_idx, fit_state in enumerate(plot_state.y_fits):
                if fit_state is None or not fit_state.dirty:
                    continue
                self._fit_y_axis_from_sources(plot_state.plot_id, yaxis_idx, fit_state)
                fit_state.dirty = False

    def _propagate_xlinks(self) -> None:
        for linked_id, anchor_id in self._xlinks.items():
            if anchor_id not in self._xaxis_tags or linked_id not in self._xaxis_tags:
                continue
            limits = dpg.get_axis_limits(self._xaxis_tags[anchor_id])
            dpg.set_axis_limits(self._xaxis_tags[linked_id], limits[0], limits[1])

def viewer_main(cmd_queue: Queue, rsp_queue: Queue, geometry: dict | None = None) -> None:
    """Entry point for the viewer process."""
    configure_logging()
    logger.info("Plot viewer process started.")
    dpg.create_context()
    dpg.configure_app(
        anti_aliased_lines=True,
        anti_aliased_lines_use_tex=True,
        anti_aliased_fill=True,
    )
    
    viewport_kwargs = {
        "title": "Plot Viewer",
        "width": VIEWER_VIEWPORT_WIDTH,
        "height": VIEWER_VIEWPORT_HEIGHT,
    }
    if geometry:
        viewport_kwargs["width"] = geometry.get("width", VIEWER_VIEWPORT_WIDTH)
        viewport_kwargs["height"] = geometry.get("height", VIEWER_VIEWPORT_HEIGHT)
        if "x_pos" in geometry:
            viewport_kwargs["x_pos"] = geometry["x_pos"]
        if "y_pos" in geometry:
            viewport_kwargs["y_pos"] = geometry["y_pos"]

    dpg.create_viewport(**viewport_kwargs)

    apply_plot_theme()
    dpg.set_global_font_scale(VIEWER_FONT_SCALE)

    viewer = PlotViewer(cmd_queue, rsp_queue)

    dpg.setup_dearpygui()
    dpg.show_viewport()

    while dpg.is_dearpygui_running():
        viewer.poll_queue()
        viewer._apply_absolute_layouts()
        viewer._update_live_fits()
        viewer._propagate_xlinks()
        dpg.render_dearpygui_frame()
        viewer._release_pending_axis_limits()
        viewer._apply_absolute_layouts()

    dpg.destroy_context()
