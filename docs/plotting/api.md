# Plotting API

## Three phases

1. **Configure** the figure layout and visual elements.
2. **Append** data to named sources.
3. **Save** the figure to disk.

Procedures access the API through `runner.plot`.

## PlotDef

Defines a subplot in the figure grid. The grid dimensions are inferred from the
maximum `row`/`col` values across all PlotDefs.

```python
@dataclass
class PlotDef:
    id: str
    row: int = 0
    col: int = 0
    rowspan: int = 1
    colspan: int = 1
    title: str = ""
    xlabel: str = ""
    ylabels: tuple[str, ...] = ("",)
    yscales: tuple[str, ...] = ("linear",)    # per y-axis: "linear" | "log"
    xlim: tuple[float, float] | None = None
    ylims: tuple[tuple[float, float] | None, ...] | None = None
    xlink: str = ""
    elements: list = field(default_factory=list)
```

- `ylabels` determines the number of y-axes. `("V",)` = one axis. `("V", "I")` = two.
  ImPlot supports up to 3 y-axes per plot.
- `yscales` maps 1:1 to `ylabels`. Supported: `"linear"`, `"log"`.
- `ylims` maps 1:1 to `ylabels`. `None` entries mean auto-range.
- `xlink` references another PlotDef's `id`. Linked plots share pan/zoom on x-axis.
- `elements` is a list of visual primitives (Curve, Histogram, LinearFit, HLine, VLine).
- If `xlim`/`ylims` are left as `None`, the viewer live-fits those axes while data is
  streaming, adds a small margin, and stops live-fitting once the visible limits no
  longer match the last auto-fit limits it set.

## ToolbarButton

Figure-level toolbar buttons are defined separately from plots.

```python
@dataclass(frozen=True)
class ToolbarButton:
    id: str
    label: str
    action: str
```

- `id` must be unique within a figure.
- `label` is the button text.
- `action` is a viewer-side action key such as `"tool:documentation"` or
  `"tool:metrics"`.
- The viewer always includes the standard debug/doc buttons. Procedures can append more.
- For DearPyGui built-in tool windows, these buttons follow the demo style and call
  `show_tool(...)` once. They do not stay latched on in the viewer.

Built-in action keys:
- `"tool:documentation"`
- `"tool:style_editor"`
- `"tool:debug"`
- `"tool:about"`
- `"tool:metrics"`
- `"tool:font_manager"`
- `"tool:item_registry"`

## Elements

Each element wraps a single ImPlot primitive and binds to a data source by name.
When the source receives data, all bound elements redraw.

### Curve

```python
@dataclass
class Curve:
    source: str                        # data source name
    mode: str = "line"                 # "line" | "scatter" | "line_scatter"
    color: ... = None                  # auto-pick if None
    marker: str | None = None          # "o", "x", "s", "t", "d", "+"
    line_style: str = "solid"          # "solid" | "dash" | "dot" | "dash_dot"
    yaxis: int = 0                     # index into ylabels
    legend_label: str = ""
    show_in_legend: bool = True
```

ImPlot mapping:
- `mode="line"` -> `add_line_series`
- `mode="scatter"` -> `add_scatter_series`
- `mode="line_scatter"` -> both series items bound to same source

### Histogram

```python
@dataclass
class Histogram:
    source: str                        # uses y-values from this source
    bins: int = 50
    color: ... = None
    orientation: str = "horizontal"    # "horizontal" | "vertical"
    yaxis: int = 0
    legend_label: str = ""
    show_in_legend: bool = True
```

Recomputed on every data update using `numpy.histogram`.
Horizontal orientation draws bars along the y-axis (sidebar showing distribution).

### LinearFit

```python
@dataclass
class LinearFit:
    source: str                        # computes fit from this source's (x, y) data
    color: ... = None
    yaxis: int = 0
    legend_label_template: str = ""    # supports {slope}, {intercept}, {r_squared}, {resistance}, {resistance_si}
    show_in_legend: bool = True
```

Recomputed using the shared `stats.linear_fit` function.
The legend label is formatted with current fit parameters on each update.
`{resistance_si}` is a compact SI-formatted string such as `1.5GOhm`.
Example: `legend_label_template="R = {resistance_si} (R^2 = {r_squared:.4f})"`.

### HLine

```python
@dataclass
class HLine:
    value: float = 0.0
    source: str = ""
    color: ... = None
    line_style: str = "solid"
    yaxis: int = 0
    legend_label: str = ""
    show_in_legend: bool = True
```

Rendered as an ImPlot infinite horizontal reference line.
If `source` is set, the latest `y` value from that source becomes the current line value.

### VLine

```python
@dataclass
class VLine:
    value: float
    color: ... = None
    line_style: str = "solid"
    legend_label: str = ""
    show_in_legend: bool = True
```

Rendered as an ImPlot infinite vertical reference line.

## API methods

All methods are on `runner.plot` (the `PlotBridge` instance).

### configure

```python
configure(title: str, plots: list[PlotDef],
          toolbar_buttons: list[ToolbarButton] | None = None,
          row_ratios: list[float] | tuple[float, ...] | None = None,
          column_ratios: list[float] | tuple[float, ...] | None = None) -> None
```

Define the figure layout and all visual elements. Clears any previous figure.
The viewer creates the grid of ImPlot widgets and instantiates render elements.
Blocks until viewer acknowledges.

- `row_ratios` / `column_ratios` are optional layout weights.
- They apply to stretched grid columns and to the supported split-span layout used by
  `IVSweep`.

### append_point

```python
append_point(source: str, x: float, y: float) -> None
```

Append a single point to a named source. Stores locally immediately.
Viewer update is deferred to the next 30 Hz flush.

### append_many

```python
append_many(source: str, xs: Sequence[float], ys: Sequence[float]) -> None
```

Append an array of points to a named source.

### append_batch

```python
append_batch(data: dict[str, list[tuple[float, float]]]) -> None
```

Append points to multiple sources in one call.
Format: `{"source_name": [(x1, y1), (x2, y2), ...], ...}`.

### set_limits

```python
set_limits(plot_id: str, xlim: tuple[float, float] | None = None,
           ylims: dict[int, tuple[float, float]] | None = None) -> None
```

Set axis limits dynamically. `ylims` maps y-axis index to `(min, max)`.
Disables live-fitting for the specified axes.

### save_png

```python
save_png(filename: str | None, output_root: str, output_relative: str,
         fallback_root: str, timeout_s: float = 8.0) -> str | None
```

Export the figure as PNG. The main process creates the output directory.
The viewer captures the framebuffer, validates the file, and acknowledges.

Returns the saved path on success. Returns `None` if `filename` is `None`.
Raises `RuntimeError` on viewer error. Raises `TimeoutError` if no ack within timeout.

### source

```python
source(name: str) -> DataSource
```

Access the backing data for a source. Returns an object with `.x` and `.y` lists.
Used by procedures to read data for post-processing (CSV output, fit parameters).

```python
ds = runner.plot.source("V_I")
fit = stats.linear_fit(ds.x, ds.y)
resistance = fit.slope
```

### shutdown

```python
shutdown(timeout_s: float = 3.0) -> None
```

Send quit command and join the viewer process. Called by `ui.py` on app close.

## DataSource

```python
class DataSource:
    x: list[float]
    y: list[float]

    append_point(x: float, y: float) -> None
    append_many(xs: Sequence[float], ys: Sequence[float]) -> None
    append_pairs(pairs: list[tuple[float, float]]) -> None
    clear() -> None
```

## Colors

Elements accept colors in these formats:

| Format | Example |
|--------|---------|
| Matplotlib cycle | `"C0"`, `"C1"`, ..., `"C9"` |
| Named | `"k"`, `"r"`, `"b"`, `"g"` |
| Hex string | `"#1f77b4"` |
| RGB float tuple (0-1) | `(0.5, 0.0, 0.8)` |
| RGB int tuple (0-255) | `(128, 0, 204)` |
| `None` | Auto-picked from default palette |

The viewer's style layer (`plotting/style.py`) translates all formats to DearPyGui RGBA.

## Viewer Tuning

The primary viewer size/style knobs live at the top of `plotting/style.py`.

- `VIEWER_VIEWPORT_WIDTH` / `VIEWER_VIEWPORT_HEIGHT`: default viewer window size.
- `VIEWER_FONT_SCALE`: global UI and axis text size.
- `UI_WINDOW_PADDING_*`: padding inside the viewer window.
- `UI_FRAME_PADDING_*`: button/input padding.
- `UI_ITEM_SPACING_*`: spacing between controls.
- `LINE_WEIGHT`: default line thickness for all line series.
- `MARKER_SIZE` / `MARKER_WEIGHT`: default scatter marker size and outline thickness.
- `PLOT_PADDING_*`, `LABEL_PADDING_*`, `LEGEND_PADDING_*`: whitespace inside plots.
- `FIT_PADDING_*`: default DearPyGui fit padding.

If the viewer feels too small but the outer window is already large enough:

- first increase `VIEWER_FONT_SCALE`
- then increase `UI_FRAME_PADDING_*`
- then increase `LINE_WEIGHT` and `MARKER_SIZE`

## Live fitting

The viewer does **not** leave DearPyGui axis `auto_fit=True` during streaming.
That mode keeps the data glued to the plot bounds and prevents normal panning/zooming.

Instead:

- The viewer mirrors every data source locally.
- For axes without explicit limits, it computes bounds from the mirrored data.
- Linear axes get a small additive margin.
- Log axes get a multiplicative margin in log space.
- After applying those bounds for the current frame, it releases them with
  `set_axis_limits_auto(...)` on the next frame so DearPyGui does not continue
  constraining pan/zoom.
- If the visible axis limits stop matching the last auto-fit limits the viewer set,
  live-fitting locks off for that plot until the next `configure(...)`.

This gives streaming follow behavior without fighting manual navigation.

## Line styles

DearPyGui does not expose native dashed/dotted line series in this wrapper.
`line_style` is stored on the element model for future use, but live curves currently
render as solid lines.

## Single source of truth for computations

Statistical functions live in `stats.py` and are imported by both the viewer
and procedure code. The viewer uses them for live overlays (LinearFit element).
Procedures use them for computed results (resistance for CSV output).

Both operate on the same data (PlotBridge holds the local copy; viewer holds
a mirrored copy synced via the queue). Same data + same function = identical results.
