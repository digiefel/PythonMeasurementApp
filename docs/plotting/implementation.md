# Implementation plan

## Files to create

### `plot_elements.py`

Dataclass definitions shared by both processes:
- `PlotDef`
- `Curve`, `Histogram`, `LinearFit`, `HLine`, `VLine`
- `DataSource` (holds `.x` and `.y` lists, with `append` for scalar or array)

### `stats.py`

Shared statistical functions. Single implementation used by both the viewer
(for live overlays) and procedures (for computed results).

- `linear_fit(x, y) -> LinearFitResult` (wraps `scipy.stats.linregress`)
- `LinearFitResult` dataclass with `slope`, `intercept`, `r_squared`

### `plot_bridge.py`

Main-process proxy. Holds local data sources and the queue.

```
class PlotBridge:
    _queue: multiprocessing.Queue
    _process: multiprocessing.Process
    _sources: dict[str, DataSource]

    configure(title, plots)      # serialize PlotDefs + elements onto queue
    append(source, x, y)         # store locally + send to viewer
    append(data_dict)            # batch form: {"source": (xs, ys), ...}
    save(filename, ...)          # send save command; main process does makedirs
    source(name) -> DataSource   # return local copy for procedure to read
    shutdown()                   # send quit + join process
```

Uses `multiprocessing.get_context("spawn")` for queue and process creation.
`_send` helper checks `_process.is_alive()` and uses `put_nowait`.

### `viewer.py`

Separate-process PyQtGraph application.

```
def viewer_main(queue):
    app = QApplication(sys.argv)
    window = PlotViewer(queue)
    window.show()
    app.exec()

class PlotViewer(QMainWindow):
    - Central widget with QGridLayout
    - One PlotPanel per PlotDef
    - QTimer(16ms) polls queue, drains all messages per tick
    - Dispatches: configure, append, save, quit
    - Dark theme, crosshair, grid enabled by default
    - Window geometry persisted via QSettings

class PlotPanel:
    - Wraps a pg.PlotWidget
    - Manages N y-axes (ViewBox per additional axis, linked x)
    - Holds element instances (curves, histograms, fits)
    - Handles resize synchronization for multi-axis
```

Element handling in the viewer:

| Element | On configure | On data append |
|---------|-------------|----------------|
| Curve | Create `PlotDataItem`, add to target ViewBox | `setData(xs, ys)` |
| Histogram | Create `BarGraphItem` | Recompute bins from y-values, update bars |
| LinearFit | Create `PlotDataItem` + `TextItem` | Recompute `stats.linear_fit`, update line endpoints + label text |
| HLine | Create `InfiniteLine(angle=0)` | (static) |
| VLine | Create `InfiniteLine(angle=90)` | (static) |

### Queue message protocol

All messages are plain dicts (pickle-serializable).

```python
# configure
{"cmd": "configure", "title": str, "plots": list[PlotDef]}

# append (single source)
{"cmd": "append", "source": str, "x": scalar_or_list, "y": scalar_or_list}

# append (batch)
{"cmd": "append_batch", "data": {"source": (xs, ys), ...}}

# save
{"cmd": "save", "path": str}

# quit
{"cmd": "quit"}
```

## Files to modify

### `runner.py`

- Remove all 6 `plot_*_callback` attributes and their invocation methods.
- Add `self.plot: PlotBridge` attribute (set by UI at init).
- The temperature-in-title logic moves into `configure` (runner appends temp to title
  before forwarding).

### `ui.py`

- Remove: `from matplotlib.figure import Figure`, `from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg`, `from plot_manager import PlotManager, PlotSpec`.
- Remove: PlotManager instantiation (line 510), canvas grid placement (lines 511-513), column 2 weight (lines 134, 139).
- Remove: all `_post_plot_*` wrappers, `start_plot`, `add_plot_point`, `add_plot_series`, `set_plot_limits`, `append_plot_points`.
- Add: `from plot_bridge import PlotBridge`.
- Add: `self.plot_bridge = PlotBridge()` in `__init__`.
- Add: `self.runner.plot = self.plot_bridge` in `__init__`.
- Modify `finish_plot` to use `self.plot_bridge.save(...)`. Keep directory-creation
  and fallback logic in `ui.py` (runs on Tk thread for safe `self.log()` calls).
- Add: `self.plot_bridge.shutdown()` in `_on_close`.
- Shrink window geometry (no embedded plot canvas).

### `procedures/*.py`

All procedures switch from runner callback API to `runner.plot.*`.
Changes are mechanical: replace `runner.start_live_plot(...)` with `runner.plot.configure(...)`,
`runner.add_live_point(...)` with `runner.plot.append(...)`, etc.

Files: `rv_sweep.py`, `four_terminal_iv_sweep.py`, `oxide_breakdown.py`, `cv_sweep.py`,
`PUND.py`, `pund_fatigue.py`, `wgfmu_sampling.py`, `van_der_pauw.py`.

### `requirements.txt`

Add `pyqtgraph` and `PyQt6`. Keep `matplotlib` (used by `ui_temperature.py`).

## Files to delete

### `plot_manager.py`

Replaced entirely by the new system.

## Style translation

The viewer translates matplotlib-compatible color/style values to PyQtGraph equivalents.

Colors:
- `"C0"`-`"C9"` -> hardcoded hex map matching matplotlib's default cycle.
- `"k"`, `"r"`, `"b"`, `"g"` -> hex values.
- `(r, g, b)` float tuples (0-1) -> `(int(r*255), int(g*255), int(b*255))`.
- Hex strings -> pass through.

Linestyles:
- `"-"` -> `Qt.PenStyle.SolidLine`
- `"--"` -> `Qt.PenStyle.DashLine`
- `":"` -> `Qt.PenStyle.DotLine`
- `"-."` -> `Qt.PenStyle.DashDotLine`

Markers: PyQtGraph supports `"o"`, `"s"`, `"t"`, `"d"`, `"+"`, `"x"` natively.

## Viewer UX

- Dark background (`pg.setConfigOption("background", "k")`)
- Crosshair per plot panel with coordinate readout
- Grid enabled by default
- Auto-range by default, disabled per-axis when `xlim`/`ylims` are set in PlotDef
- Right-click context menu (native PyQtGraph: export, transform, auto-range)
- Window geometry persisted between sessions via `QSettings`
- `xlink` synchronizes pan/zoom on x-axis between linked plots

## Verification

1. RV sweep: single curve in viewer window, PNG saved.
2. 4-term IV: scatter + live fit line updating as points stream in.
3. Oxide breakdown: dual y-axis (linear + log), three series.
4. CV sweep: multiple frequencies, correct colors, dual axis.
5. PUND / PUND fatigue: color gradient series, bulk data, preset limits.
6. WGFMU: curve + live histogram sidebar updating together.
7. Close viewer mid-measurement: measurement continues.
8. Close main app: viewer terminates.
9. Crosshair, grid, auto-range, x-axis linking all functional.
