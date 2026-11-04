"""Waveform preview: draw the WGFMU patterns a procedure would send, in the plot window.

The procedure runs with the form's settings against a stand-in WGFMU that only
records patterns, and stops where the real run would start. Nothing is sent to
an instrument and no files are written.
"""
import threading

from plotting import Curve, PlotDef

# One small plot per pattern; more than this makes the window unreadable.
MAX_PLOTS = 12
COLUMNS = 2


class _Started(BaseException):
    """Raised at execute(). A BaseException, so a procedure's ``except Exception`` cannot swallow it."""


class _Ignore:
    """Accepts any method call and does nothing."""
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _PatternRecorder(_Ignore):
    """Stands in for ``b1500.wgfmu``: keeps every pattern as (time, voltage) points."""
    def __init__(self):
        self.patterns = {}

    def create_pattern(self, name, initial_voltage=0.0):
        self.patterns[name] = [(0.0, initial_voltage)]

    def add_vector(self, name, dt, voltage):
        points = self.patterns[name]
        points.append((points[-1][0] + dt, voltage))

    def execute(self):
        raise _Started


class _QuietRunner(_Ignore):
    """Just enough of the measurement runner for a procedure to build its patterns."""
    plot = None
    current_chip = 'preview'
    current_temp_c = None

    def __init__(self):
        self.stop_event, self.skip_device_event = threading.Event(), threading.Event()
        self.current_site = self.current_subsite = self.device = _Named()


class _Named(_Ignore):
    name = 'preview'


def record_patterns(procedure_class, settings):
    """Return ``{pattern name: [(time_s, voltage), ...]}`` in the order the procedure creates them."""
    procedure = procedure_class(dict(settings), '', '', _QuietRunner())
    b1500 = _Ignore()
    b1500.wgfmu = _PatternRecorder()
    try:
        procedure.execute(b1500, _Named())
    except _Started:
        pass
    # Procedures add the run timestamp to pattern names to keep them unique; it is noise in a title.
    stamp = f"_{procedure.get_run_timestamp()}"
    return {name.replace(stamp, ""): points for name, points in b1500.wgfmu.patterns.items()}


def show_wgfmu_preview(ui):
    """Draw the current procedure's patterns in the plot window, one plot per pattern."""
    from tkinter import messagebox
    proc_name = ui.proc_var.get()
    try:
        patterns = record_patterns(ui.procedure_classes[proc_name], ui.collect_settings())
    except Exception as exc:
        messagebox.showerror("Waveform Preview", f"Could not build the waveform: {exc}", parent=ui.root)
        return
    if not patterns:
        messagebox.showinfo("Waveform Preview", "These settings send no patterns.", parent=ui.root)
        return

    names = list(patterns)[:MAX_PLOTS]
    title = f"{proc_name} waveform"
    if len(patterns) > MAX_PLOTS:
        title += f" (first {MAX_PLOTS} of {len(patterns)} patterns)"
    ui.runner.configure_plot(title, [
        PlotDef(f"pattern_{i}", row=i // COLUMNS, col=i % COLUMNS, title=name,
                xlabel="Time (s)", ylabels=("Voltage (V)",),
                elements=[Curve(f"wave_{i}", show_in_legend=False)])
        for i, name in enumerate(names)
    ])
    for i, name in enumerate(names):
        times, voltages = zip(*patterns[name])
        ui.runner.plot.replace_source(f"wave_{i}", times, voltages)
