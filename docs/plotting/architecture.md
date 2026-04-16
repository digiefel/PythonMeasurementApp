# Plotting System Architecture

## Overview

The plotting system runs as a **separate process** from the main Tkinter application.
A PyQtGraph viewer runs its own Qt event loop, receives data over a `multiprocessing.Queue`,
and renders all visuals independently. The measurement thread is never blocked by rendering.

```
WORKER THREAD          MAIN PROCESS (Tk)         VIEWER PROCESS (Qt/PyQtGraph)
Procedure.run()        PlotBridge                 PlotViewer
  |                      |                          |
  |-- runner.plot -----► append(source, x, y)       |
  |                      |-- store locally           |
  |                      |-- queue.put({...}) -----► QTimer polls queue
  |                                                  |-- update data sources
  |                                                  |-- redraw bound elements
```

### Process isolation

- **IPC**: `multiprocessing.Queue` with dict messages.
- **Start method**: `spawn` via `multiprocessing.get_context("spawn")`. `fork` is not Qt-safe.
- **Lifecycle**: spawned once at application start, reused across all measurements.
- **Shutdown**: main app sends `{"cmd": "quit"}` on close; viewer process is `daemon=True` as a safety net.

### Data flow

The `PlotBridge` (main process) keeps a local copy of every data source.
When a procedure appends data, the bridge stores it locally AND sends it to the viewer.
This means procedures can read their own data (e.g. for CSV output or fit computation)
without IPC round-trips.

## Data model: sources and elements

The system separates **data** from **visuals**.

**Data sources** are named `(x, y)` streams. They live in the PlotBridge (main process)
and are mirrored to the viewer. A source is created implicitly on first `append`.

**Elements** are visual primitives bound to data sources by name.
When a source updates, every element referencing it redraws.

```
DataSource "I1" ---+--- Curve on main plot
                   +--- Histogram on sidebar

DataSource "V_I" --+--- Curve (scatter) on IV plot
                   +--- LinearFit line on IV plot
```

This is a reactive/observable pattern: sources are observables, elements are observers.

## File layout

| File | Process | Role |
|------|---------|------|
| `plot_bridge.py` | Main | Thin proxy. Stores data sources locally. Serializes commands onto the queue. Exposes `configure`, `append`, `save`, `source`. |
| `viewer.py` | Viewer | `QMainWindow` with `QGridLayout` of `PlotWidget`s. Polls queue via `QTimer`. Creates and updates PyQtGraph objects from element specs. |
| `plot_elements.py` | Both | Dataclass definitions for `PlotDef`, `Curve`, `Histogram`, `LinearFit`, `HLine`, `VLine`. Imported by both processes. |
| `stats.py` | Both | Shared statistical functions (`linear_fit`, etc.). Single implementation used by both the viewer (for live overlays) and procedures (for computed results). |

`plot_manager.py` is deleted. The temperature plot (`ui_temperature.py`) stays in Tk and keeps its own matplotlib embed.
