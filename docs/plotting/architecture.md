# Plotting System Architecture

## Overview

The plotting system runs as a **separate process** from the main Tkinter application.
A DearPyGui viewer (ImPlot backend) runs its own render loop, receives data over a
bounded `multiprocessing.Queue`, and renders all visuals independently. The measurement
thread is never blocked by rendering.

```
WORKER THREAD          MAIN PROCESS (Tk)         VIEWER PROCESS (DearPyGui)
Procedure.run()        PlotBridge                 DearPyGui render loop
  |                      |                          |
  |-- runner.plot -----► append_point/many/batch    |
  |                      |-- store in DataSource    |
  |                      |-- coalesce deltas        |
  |                      |-- flush @ 30 Hz -------► cmd_queue
  |                                                  |-- apply deltas to mirrors
  |                                                  |-- redraw bound elements
  |                                                  |
  |                      cmd_queue (main -> viewer)  |
  |                      rsp_queue (viewer -> main)  |
```

## Process isolation

- **IPC**: Two bounded `multiprocessing.Queue`s.
  - `cmd_queue` (main -> viewer, maxsize 512): commands and data deltas.
  - `rsp_queue` (viewer -> main, maxsize 256): acknowledgements and errors.
- **Start method**: `spawn` via `multiprocessing.get_context("spawn")`.
- **Lifecycle**: spawned once at application start, reused across all measurements.
- **Shutdown**: main sends `quit` command; viewer process is `daemon=True` as safety net.

## Message envelope

Every message uses a standard envelope for tracing:

```python
# command (main -> viewer)
{"cmd": str, "req_id": str, "ts_ns": int, "payload": dict}

# response (viewer -> main)
{"type": "ack" | "error", "req_id": str, "payload": dict}
```

Response rules:
- `configure_figure`, `save_png`, `clear_figure`, `ping`, `quit`: must emit ack or error.
- `append_batch`: no per-message ack (throughput path).

## Data flow

The `PlotBridge` (main process) keeps a local copy of every data source.
When a procedure appends data, the bridge stores it locally immediately.
Viewer deltas are coalesced and flushed at 30 Hz (every ~33 ms).
Multiple appends to the same source within one interval are merged into a single
`append_batch` command.

This means:
- Procedure-visible data is never dependent on viewer queue state.
- High-frequency appends produce bounded queue traffic.
- The viewer always receives complete batches.

## Data model: sources and elements

The system separates **data** from **visuals**.

**Data sources** are named `(x, y)` streams. They live in the PlotBridge (main process)
and are mirrored to the viewer. Sources are referenced by name in element definitions.

**Elements** are visual primitives bound to data sources by name.
When a source updates, every element referencing it redraws.

```
DataSource "I1" ---+--- Curve on main plot
                   +--- Histogram on sidebar

DataSource "V_I" --+--- Curve (scatter) on IV plot
                   +--- LinearFit line on IV plot
```

This is a reactive/observable pattern: sources are observables, elements are observers.

## Backpressure

- PlotBridge maintains per-source pending buffers between flushes.
- If `cmd_queue` is full at flush time, deltas stay buffered; next flush retries.
- Throttled warning logged once per 5 seconds while saturated.
- Measurement execution is never blocked by queue state.

## Save handshake

`save_png` is the only blocking bridge call:

1. Main process resolves output path (primary, then fallback on directory error).
2. Main sends `save_png` command with `req_id`.
3. Viewer captures framebuffer to requested path.
4. Viewer validates file exists and size > 0.
5. Viewer sends ack or error with `req_id`.
6. PlotBridge returns path or raises `RuntimeError` / `TimeoutError`.

## File layout

| File | Process | Role |
|------|---------|------|
| `plot_elements.py` | Both | Dataclass definitions: `PlotDef`, `AxisDef`, `Curve`, `Histogram`, `LinearFit`, `HLine`, `VLine`, `DataSource`. |
| `stats.py` | Both | Shared statistical functions (`linear_fit`, etc.). Single implementation used by both viewer and procedures. |
| `plot_bridge.py` | Main | Stores data sources locally. Coalesces deltas. Manages cmd/rsp queues. Exposes procedure-facing API. |
| `viewer_dpg.py` | Viewer | DearPyGui render loop. Builds ImPlot widgets from PlotDef specs. Applies data deltas. Handles save export. |
| `dpg_style.py` | Viewer | Color/linestyle/marker translation. Theme constants. |
| `dpg_export.py` | Viewer | Framebuffer capture and PNG validation. |

`plot_manager.py` is deleted. The temperature plot (`ui_temperature.py`) stays in Tk
and keeps its own matplotlib embed.
