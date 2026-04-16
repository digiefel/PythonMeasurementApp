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
    yscales: tuple[str, ...] = ("linear",)    # per y-axis
    xlim: tuple[float, float] | None = None
    ylims: tuple[tuple[float, float] | None, ...] | None = None  # per y-axis
    xlink: str = ""                            # sync x-axis to another plot id
    elements: list = field(default_factory=list)
```

- `ylabels` determines the number of y-axes. `("V",)` = one axis. `("V", "I")` = two.
- `yscales` maps 1:1 to `ylabels`. Supported values: `"linear"`, `"log"`.
- `ylims` maps 1:1 to `ylabels`. `None` entries mean auto-range.
- `xlink` references another PlotDef's `id`. Linked plots share pan/zoom on the x-axis.
- `elements` is a list of visual primitives (Curve, Histogram, LinearFit, HLine, VLine).

## Elements

Each element wraps a single PyQtGraph primitive and binds to a data source by name.

### Curve

Line plot, scatter plot, or both. Wraps `pg.PlotDataItem`.

```python
@dataclass
class Curve:
    source: str                    # data source name
    color: ... = None              # auto-pick if None
    marker: str | None = None      # "x", "o", "s", "t", "d", "+", None
    linestyle: str = "-"           # "-", "--", ":", "-.", None (no line)
    linewidth: float = 1.0
    yaxis: int = 0                 # which y-axis (index into ylabels)
    label: str = ""                # legend label; empty = hidden from legend
```

- `marker=None, linestyle="-"` = line only (default).
- `marker="x", linestyle=None` = scatter only.
- `marker="o", linestyle="-"` = line with markers.

### Histogram

Distribution of y-values. Wraps `pg.BarGraphItem`.

```python
@dataclass
class Histogram:
    source: str                    # uses y-values from this source
    bins: int = 50
    color: ... = None
    orientation: str = "horizontal"
    yaxis: int = 0
    label: str = ""
```

Orientation `"horizontal"` draws bars along the y-axis (useful as a sidebar showing
the distribution of a quantity). The histogram recomputes on every data update.

### LinearFit

Live regression line derived from a data source. Wraps `pg.PlotDataItem` + `pg.TextItem`.

```python
@dataclass
class LinearFit:
    source: str                    # computes fit from this source's (x, y) data
    color: ... = None
    yaxis: int = 0
    label: str = ""                # supports format strings: {slope}, {intercept}, {r_squared}
```

The label is formatted with the current fit parameters on each update. Example:
`label="R = {slope:.4g} Ohm (R^2 = {r_squared:.4f})"`.

The fit is recomputed using the shared `stats.linear_fit` function.

### HLine

Static horizontal reference line. Wraps `pg.InfiniteLine`.

```python
@dataclass
class HLine:
    y: float
    color: ... = None
    yaxis: int = 0
    label: str = ""
```

### VLine

Static vertical reference line. Wraps `pg.InfiniteLine`.

```python
@dataclass
class VLine:
    x: float
    color: ... = None
    label: str = ""
```

## API methods

All methods are on `runner.plot` (the `PlotBridge` instance).

### configure

```python
configure(title: str, plots: list[PlotDef])
```

Define the figure layout and all visual elements. Clears any previous figure.
The viewer creates the grid of `PlotWidget`s and instantiates PyQtGraph objects
for each element.

### append

```python
append(source: str, x, y)
```

Stream data to a named source. `x` and `y` can be scalars or arrays (list, tuple, numpy array).
There is no `plot_id` argument: data sources are global to the figure. An element in any
subplot can reference any source.

If `x` is a scalar, one point is appended. If `x` is an array, all points are appended.

Multiple sources can be appended in a single dict call:

```python
append({"I1": (times, currents1), "I2": (times, currents2)})
```

### save

```python
save(filename: str | None, output_root: str, output_relative: str, fallback_root: str)
```

Export the figure as PNG. The main process creates the output directory;
the viewer renders via `QWidget.grab()`.

### source

```python
source(name: str) -> DataSource
```

Access the backing data for a source. Returns an object with `.x` and `.y` lists.
Used by procedures to read their own data for computation (CSV output, fit parameters, etc.).

```python
ds = runner.plot.source("V_I")
fit = stats.linear_fit(ds.x, ds.y)
resistance = fit.slope
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
| `None` | Auto-picked from a default palette |

The viewer translates all formats to PyQtGraph-compatible values.

## Single source of truth for computations

Statistical functions live in `stats.py` and are imported by both the viewer
and procedure code. The viewer uses them for live overlays (e.g. `LinearFit` element).
Procedures use them for computed results (e.g. resistance for CSV output).

Both operate on the same data (the PlotBridge holds the local copy; the viewer holds
a mirrored copy). Same data + same function = identical results.
