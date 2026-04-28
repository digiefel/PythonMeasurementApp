# Implementation plan

## Files to create

### `plot_elements.py`

Dataclass definitions shared by both processes:

- `PlotDef` — subplot position, axes, elements list
- `AxisDef` — label, scale, limits (used within PlotDef)
- `Curve`, `Histogram`, `LinearFit`, `HLine`, `VLine` — visual elements
- `DataSource` — holds `.x` and `.y` lists with `append_point`, `append_many`, `append_pairs`, `clear`
- `LinearFitResult` — `slope`, `intercept`, `r_squared`

### `stats.py`

Shared statistical functions. Single implementation used by both the viewer
(for live overlays) and procedures (for computed results).

- `linear_fit(x, y) -> LinearFitResult` (wraps `scipy.stats.linregress`)

### `plot_bridge.py`

Main-process proxy. Holds local data sources and manages IPC.

```
class PlotBridge:
    _cmd_queue: Queue (maxsize=512)
    _rsp_queue: Queue (maxsize=256)
    _process: Process
    _sources: dict[str, DataSource]
    _pending: dict[str, list]         # per-source delta buffers
    _flush_timer: threading.Timer     # 30 Hz flush cadence

    configure(title, plots)
    append_point(source, x, y)
    append_many(source, xs, ys)
    append_batch(data)
    set_limits(plot_id, xlim, ylims)
    save_png(filename, output_root, output_relative, fallback_root, timeout_s)
    source(name) -> DataSource
    shutdown(timeout_s)
```

Uses `multiprocessing.get_context("spawn")`.

Delta coalescing: appends buffer into `_pending`. A 30 Hz flush merges all
pending deltas into a single `append_batch` command. If `cmd_queue` is full,
deltas stay buffered; next flush retries.

### `viewer_dpg.py`

Separate-process DearPyGui application.

```
def viewer_main(cmd_queue, rsp_queue):
    dpg.create_context()
    dpg.create_viewport(title="Plot Viewer")
    viewer = PlotViewer(cmd_queue, rsp_queue)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    while dpg.is_dearpygui_running():
        viewer.poll_queue()
        dpg.render_dearpygui_frame()
    dpg.destroy_context()
```

Layout:
- One top-level window per figure.
- Grid layout from PlotDef row/col/rowspan/colspan.
- Each PlotDef produces one ImPlot widget with up to 3 y-axes.

Element rendering:

| Element | On configure | On data update |
|---------|-------------|----------------|
| Curve (line) | `dpg.add_line_series` | `dpg.set_value` with updated arrays |
| Curve (scatter) | `dpg.add_scatter_series` | `dpg.set_value` with updated arrays |
| Curve (line_scatter) | Both series bound to same source | Both updated |
| Histogram | `dpg.add_bar_series` | Recompute `numpy.histogram`, update bars |
| LinearFit | `dpg.add_line_series` + `dpg.add_plot_annotation` | Recompute `stats.linear_fit`, update endpoints + text |
| HLine | `dpg.add_line_series` (2-point) | Recompute when axis limits change |
| VLine | `dpg.add_line_series` (2-point) | Recompute when axis limits change |

### `dpg_style.py`

Color/linestyle/marker translation and theme constants.

Colors:
- `"C0"`-`"C9"` -> hex map matching matplotlib's default cycle -> RGBA int tuples.
- `"k"`, `"r"`, `"b"`, `"g"` -> RGBA.
- `(r, g, b)` float (0-1) -> `(int(r*255), int(g*255), int(b*255), 255)`.
- Hex strings -> parsed to RGBA.

Linestyles (emulated via segmented polyline):
- `"solid"` -> direct
- `"dash"` -> segmented with gaps
- `"dot"` -> short segments with gaps
- `"dash_dot"` -> alternating segments

Dark theme applied as constants at startup.

### `dpg_export.py`

Framebuffer capture and PNG file validation.

Save flow:
1. Receive `save_png` command.
2. Render one frame to ensure state is current.
3. Capture framebuffer to target path.
4. Validate file exists and size > 0.
5. Send ack or error on `rsp_queue`.

## Files to modify

### `runner.py`

- Remove all 6 `plot_*_callback` attributes and their invocation methods
  (`start_live_plot`, `add_live_point`, `add_live_series`, `set_plot_limits`,
  `append_plot_points`, `finalize_plot`).
- Add `self.plot: PlotBridge` attribute (set by UI at init).
- Temperature-in-title logic moves into a helper that wraps `configure`
  (runner appends temp to title before forwarding).

### `ui.py`

- Remove: `from matplotlib.figure import Figure`,
  `from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg`,
  `from plot_manager import PlotManager, PlotSpec`.
- Remove: PlotManager instantiation (line 510), canvas grid placement (lines 511-513),
  column 2 weight (lines 134, 139).
- Remove: all `_post_plot_*` wrappers, `start_plot`, `add_plot_point`, `add_plot_series`,
  `set_plot_limits`, `append_plot_points`, `finish_plot`.
- Add: `from plot_bridge import PlotBridge`.
- Add: `self.plot_bridge = PlotBridge()` and `self.runner.plot = self.plot_bridge` in `__init__`.
- Add: `self.plot_bridge.shutdown()` in `_on_close`.
- Shrink window geometry (no embedded plot canvas).

### `procedures/*.py`

All procedures switch from runner callback API to `runner.plot.*`.

Migration mapping:
- `runner.start_live_plot(...)` -> `runner.plot.configure(...)`
- `runner.add_live_point(x, y, label)` -> `runner.plot.append_point(source, x, y)`
- `runner.add_live_series(xs, ys, label)` -> `runner.plot.append_many(source, xs, ys)`
- `runner.append_plot_points(dict)` -> `runner.plot.append_batch(...)`
- `runner.set_plot_limits(...)` -> `runner.plot.set_limits(plot_id, ...)`
- `runner.finalize_plot(...)` -> `runner.plot.save_png(...)`

Procedure-specific notes:
- `oxide_breakdown`: log(I) overlay becomes Curve source on yaxis=1 with log scale.
- `four_terminal_iv_sweep` / `van_der_pauw`: fit overlay becomes LinearFit element.
- `PUND` / `pund_fatigue`: hidden legend names become `show_in_legend=False`.
- `wgfmu_sampling`: bucketing stays; route through `append_batch`.

Files: `rv_sweep.py`, `four_terminal_iv_sweep.py`, `oxide_breakdown.py`, `cv_sweep.py`,
`PUND.py`, `pund_fatigue.py`, `wgfmu_sampling.py`, `van_der_pauw.py`.

### `requirements.txt`

Add `dearpygui`. Keep `matplotlib` (used by `ui_temperature.py`).

## Files to delete

### `plot_manager.py`

Replaced entirely.

## Implementation phases

### Phase 1: Contracts and bridge skeleton
- Dataclasses and stats module.
- PlotBridge process launch/shutdown.
- Command envelope and request tracking.
- Ping and configure handshake.
- **Accept**: viewer starts and acks ping/configure. Graceful shutdown within timeout.

### Phase 2: Viewer core and rendering primitives
- DearPyGui window/grid/plots.
- Curve, HLine, VLine support.
- Axis limits and x-link propagation.
- **Accept**: RV sweep equivalent renders. Fixed limits respected.

### Phase 3: Advanced elements and style parity
- Histogram, LinearFit.
- Line style emulation for dash/dot.
- Legend boolean behavior.
- **Accept**: WGFMU histogram sidebar updates live. 4-term fit matches offline values.

### Phase 4: Save reliability and UI integration
- save_png ack path.
- Fallback root handling in main process.
- ui.py integration and callback removal.
- **Accept**: Save success confirmed. Forced error produces explicit exception.

### Phase 5: Procedure migration and cleanup
- All procedures on new API.
- Remove runner plot callback surface.
- Remove plot_manager.py.
- **Accept**: No references to old plotting callbacks. No import of plot_manager.

### Phase 6: Verification and hardening
- Manual verification matrix.
- Unit tests for bridge/data/stats/style mapper.
- Performance soak test for high-rate append_batch.
- **Accept**: All scenarios pass. No queue warnings in nominal runs. Clean shutdown.

## Verification matrix

Functional:
1. RV sweep: single curve, PNG saved.
2. 4-term IV: scatter + live fit line updating as points stream.
3. 2-term IV: dual-axis with log current trace.
4. CV sweep: multiple frequencies with paired styles.
5. PUND: overlay with first/last legend labels only.
6. PUND fatigue: overlay with cycle-selection plotting.
7. WGFMU: curve + histogram sidebar co-update.

Resilience:
1. Close viewer during active measurement: measurement continues.
2. Save timeout: explicit TimeoutError with req_id.
3. Main app close: viewer exits, resources released.
4. Queue saturation: no measurement-thread blocking.

Numerical consistency:
- `stats.linear_fit` in viewer equals procedure post-processing for same source.
