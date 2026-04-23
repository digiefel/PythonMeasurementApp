"""Color and theme helpers for DearPyGui plotting."""

from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg


# ---------------------------------------------------------------------------
# Viewer sizing and styling knobs
# ---------------------------------------------------------------------------

# These are the primary knobs to change if the viewer feels too small or dense.
# Keep the viewport footprint stable and scale the content instead.
VIEWER_VIEWPORT_WIDTH = 960
VIEWER_VIEWPORT_HEIGHT = 960
VIEWER_FONT_SCALE = 1.0

UI_WINDOW_PADDING_X = 12
UI_WINDOW_PADDING_Y = 10
UI_FRAME_PADDING_X = 10
UI_FRAME_PADDING_Y = 8
UI_ITEM_SPACING_X = 10
UI_ITEM_SPACING_Y = 8

PLOT_PADDING_X = 2
PLOT_PADDING_Y = 4
LABEL_PADDING_X = 4
LABEL_PADDING_Y = 5
LEGEND_PADDING_X = 4
LEGEND_PADDING_Y = 5
FIT_PADDING_X = 0.10
FIT_PADDING_Y = 0.10

LINE_WEIGHT = 2.75
MARKER_SIZE = 10.0
MARKER_WEIGHT = 2.0


# ---------------------------------------------------------------------------
# Matplotlib default color cycle (C0-C9)
# ---------------------------------------------------------------------------

_CYCLE_COLORS: list[tuple[int, int, int, int]] = [
    ( 31, 119, 180, 255),  # C0 — blue
    (255, 127,  14, 255),  # C1 — orange
    ( 44, 160,  44, 255),  # C2 — green
    (214,  39,  40, 255),  # C3 — red
    (148, 103, 189, 255),  # C4 — purple
    (140,  86,  75, 255),  # C5 — brown
    (227, 119, 194, 255),  # C6 — pink
    (127, 127, 127, 255),  # C7 — gray
    (188, 189,  34, 255),  # C8 — olive
    ( 23, 190, 207, 255),  # C9 — cyan
]

_NAMED_COLORS: dict[str, tuple[int, int, int, int]] = {
    "k": (  0,   0,   0, 255),
    "w": (255, 255, 255, 255),
    "r": (214,  39,  40, 255),
    "g": ( 44, 160,  44, 255),
    "b": ( 31, 119, 180, 255),
    "c": ( 23, 190, 207, 255),
    "m": (227, 119, 194, 255),
    "y": (188, 189,  34, 255),
}


def resolve_color(color: Any) -> tuple[int, int, int, int] | None:
    """Translate a color spec to a DearPyGui RGBA tuple, or None for auto-pick.

    Accepted formats:
    - None → auto-pick (returns None)
    - "C0"–"C9" → matplotlib default cycle
    - "k", "r", "b", "g", etc. → named color
    - "#RRGGBB" / "#RRGGBBAA" → hex
    - (r, g, b) floats 0–1 → converted to ints
    - (r, g, b) or (r, g, b, a) ints 0–255 → passed through
    """
    if color is None:
        return None

    if isinstance(color, str):
        if len(color) == 2 and color[0] == "C" and color[1].isdigit():
            return _CYCLE_COLORS[int(color[1]) % 10]
        if color in _NAMED_COLORS:
            return _NAMED_COLORS[color]
        if color.startswith("#"):
            return _parse_hex(color)
        raise ValueError(f"Unrecognized color string: {color!r}")

    if isinstance(color, (list, tuple)):
        if len(color) == 3:
            r, g, b = color
            if isinstance(r, float):
                return (int(r * 255), int(g * 255), int(b * 255), 255)
            return (int(r), int(g), int(b), 255)
        if len(color) == 4:
            r, g, b, a = color
            if isinstance(r, float):
                return (int(r * 255), int(g * 255), int(b * 255), int(a * 255))
            return (int(r), int(g), int(b), int(a))

    raise ValueError(f"Cannot interpret color: {color!r}")


def _parse_hex(hex_str: str) -> tuple[int, int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    if len(h) == 8:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
    raise ValueError(f"Cannot parse hex color: {hex_str!r}")


# ---------------------------------------------------------------------------
# Marker translation
# ---------------------------------------------------------------------------

IMPLOT_MARKER_MAP: dict[str, int] = {}


def _build_marker_map() -> None:
    candidates = {
        "o": "mvPlotMarker_Circle",
        "s": "mvPlotMarker_Square",
        "t": "mvPlotMarker_Up",
        "d": "mvPlotMarker_Diamond",
        "+": "mvPlotMarker_Cross",
        "x": "mvPlotMarker_Asterisk",
    }
    for key, const_name in candidates.items():
        val = getattr(dpg, const_name, None)
        if val is not None:
            IMPLOT_MARKER_MAP[key] = val


# ---------------------------------------------------------------------------
# Viewer theme
# ---------------------------------------------------------------------------

def apply_plot_theme() -> None:
    """Apply a neutral plot-first theme and shared plot style defaults.

    To retune the viewer, start with the constants near the top of this file.
    """
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,      (242, 244, 247, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,       (242, 244, 247, 255))
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg,       (255, 255, 255, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border,        (206, 212, 218, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,       (255, 255, 255, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (224, 229, 236, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (205, 216, 229, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (186, 202, 220, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,       (230, 234, 239, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (220, 226, 232, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          ( 33,  37,  41, 255))
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, UI_WINDOW_PADDING_X, UI_WINDOW_PADDING_Y, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, UI_FRAME_PADDING_X, UI_FRAME_PADDING_Y, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, UI_ITEM_SPACING_X, UI_ITEM_SPACING_Y, category=dpg.mvThemeCat_Core)

        with dpg.theme_component(dpg.mvPlot):
            dpg.add_theme_color(dpg.mvPlotCol_PlotBg,       (255, 255, 255, 255), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_PlotBorder,   (198, 204, 212, 255), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_LegendBg,     (255, 255, 255, 230), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_LegendBorder, (198, 204, 212, 255), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_LegendText,   ( 33,  37,  41, 255), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_TitleText,    ( 33,  37,  41, 255), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_InlayText,    (108, 117, 125, 255), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_AxisText,     ( 73,  80,  87, 255), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_AxisGrid,     (222, 226, 230, 255), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_PlotPadding, PLOT_PADDING_X, PLOT_PADDING_Y, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_LabelPadding, LABEL_PADDING_X, LABEL_PADDING_Y, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_LegendPadding, LEGEND_PADDING_X, LEGEND_PADDING_Y, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_FitPadding, FIT_PADDING_X, FIT_PADDING_Y, category=dpg.mvThemeCat_Plots)

        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, LINE_WEIGHT, category=dpg.mvThemeCat_Plots)

        with dpg.theme_component(dpg.mvScatterSeries):
            dpg.add_theme_style(dpg.mvPlotStyleVar_MarkerSize, MARKER_SIZE, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_MarkerWeight, MARKER_WEIGHT, category=dpg.mvThemeCat_Plots)

    dpg.bind_theme(global_theme)


_build_marker_map()
