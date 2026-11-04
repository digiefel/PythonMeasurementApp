"""Waveform preview: draw the WGFMU patterns a procedure would send, in the plot window.

The procedure runs with the form's settings against a stand-in WGFMU that only
records patterns, and stops where the real run would start. Nothing is sent to
an instrument and no files are written.

Patterns that the channels play at the same time share one plot, one color per
channel. Each waveform is a line, with a dot at every point the channel captures.
"""
from dataclasses import dataclass
import re
import threading

import numpy as np

from plotting import Curve, PlotDef
from procedures.base import WGFMUChannel

# One small plot per step; more than this makes the window unreadable.
MAX_PLOTS = 12
COLUMNS = 2


@dataclass
class ChannelPattern:
    channel: int    # 1 for the procedure's first WGFMU channel setting, 2 for the second
    name: str       # pattern name without the run timestamp
    points: list    # (time_s, voltage) at each vector end
    samples: list   # times at which the channel captures a point, in seconds


class _Started(BaseException):
    """Raised at execute(). A BaseException, so a procedure's ``except Exception`` cannot swallow it."""


class _Ignore:
    """Accepts any method call and does nothing."""
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _PatternRecorder(_Ignore):
    """Stands in for ``b1500.wgfmu``: keeps each pattern's points and capture times, and which channel plays it."""
    def __init__(self):
        self.patterns, self.samples, self.sequence = {}, {}, []

    def create_pattern(self, name, initial_voltage=0.0):
        self.patterns[name] = [(0.0, initial_voltage)]
        self.samples[name] = []

    def add_vector(self, name, dt, voltage):
        points = self.patterns[name]
        points.append((points[-1][0] + dt, voltage))

    def set_measure_event(self, name, event, start, points, interval, *args):
        self.samples[name].extend(start + k * interval for k in range(points))

    def add_sequence(self, channel, name, count):
        self.sequence.append((channel, name))

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
    """Return the patterns the WGFMU channels play, in the order the procedure queues them.

    A pattern queued several times appears once. Cleanup patterns, which only return
    the channels to their idle level after the run, are left out.
    """
    procedure = procedure_class(dict(settings), '', '', _QuietRunner())
    b1500 = _Ignore()
    wgfmu = b1500.wgfmu = _PatternRecorder()
    try:
        procedure.execute(b1500, _Named())
    except _Started:
        pass
    channels = [getattr(procedure, p.attr or p.key) for p in procedure.PARAMETERS if p.kind is WGFMUChannel]
    # Procedures add the run timestamp to pattern names to keep them unique; it is noise in a title.
    stamp = f"_{procedure.get_run_timestamp()}"
    result, seen = [], set()
    for channel, name in wgfmu.sequence:
        # Every procedure names its cleanup patterns ..._CLEANUP_...
        if name in seen or 'CLEANUP' in name:
            continue
        seen.add(name)
        number = channels.index(channel) + 1 if channel in channels else channel
        result.append(ChannelPattern(number, name.replace(stamp, ""), wgfmu.patterns[name], wgfmu.samples[name]))
    return result


def show_wgfmu_preview(ui):
    """Draw the current procedure's patterns in the plot window, one plot per step."""
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

    # Procedures queue one pattern per channel for each step, so each channel's k-th
    # pattern plays at the same time as the other channel's k-th: they share plot k.
    steps, per_channel = [], {}
    for p in patterns:
        k = per_channel[p.channel] = per_channel.get(p.channel, -1) + 1
        if k == len(steps):
            steps.append([])
        steps[k].append(p)

    shown = steps[:MAX_PLOTS]
    title = f"{proc_name} waveform (dots: captured points)"
    if len(steps) > MAX_PLOTS:
        title += f", first {MAX_PLOTS} of {len(steps)} steps"
    ui.runner.configure_plot(title, [
        # _PG and _IV in pattern names only say which channel plays it; the legend says that.
        PlotDef(f"pattern_{i}", row=i // COLUMNS, col=i % COLUMNS,
                title=re.sub(r'_(PG|IV)(?=_|$)', '', step[0].name),
                xlabel="Time (s)", ylabels=("Voltage (V)",),
                elements=[curve
                          for p in step
                          for curve in (Curve(f"wave_{i}_{p.channel}", color=f"C{p.channel - 1}",
                                              legend_label=f"Channel {p.channel}"),
                                        Curve(f"samples_{i}_{p.channel}", mode="scatter", marker="o",
                                              marker_size=2.0, color=f"C{p.channel - 1}",
                                              show_in_legend=False))])
        for i, step in enumerate(shown)
    ])
    for i, step in enumerate(shown):
        for p in step:
            times, voltages = zip(*p.points)
            ui.runner.plot.replace_source(f"wave_{i}_{p.channel}", times, voltages)
            ui.runner.plot.replace_source(f"samples_{i}_{p.channel}", p.samples,
                                          np.interp(p.samples, times, voltages).tolist())
