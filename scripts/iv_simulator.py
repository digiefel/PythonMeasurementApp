"""Deterministic instrument substitute for sweep tests and the HTML preview.

Only instrument transport and plot rendering are substituted. Production
procedure execution, channel selection, stream parsing and CSV writing run as-is.
This is a behavioral fixture, not a model of B1500 timing or analogue accuracy.
"""
from pathlib import Path
from types import SimpleNamespace
import threading

from runner import MeasurementAbortRequested


class MemoryPlot:
    def __init__(self):
        self.sources = {}
        self.saved = []

    def replace_source(self, name, xs, ys):
        self.sources[name] = (list(xs), list(ys))

    def save_png(self, *args):
        self.saved.append(args)


class MemoryRunner:
    def __init__(self):
        self.plot = MemoryPlot()
        self.logs, self.statuses = [], []
        self.stop_event, self.skip_device_event = threading.Event(), threading.Event()
        self.current_chip = 'simulation'
        self.current_site = SimpleNamespace(name='site')
        self.current_subsite = SimpleNamespace(name='subsite')
        self.current_temp_c = None

    def log(self, text):
        self.logs.append(text)

    def report_status(self, status):
        self.statuses.append(status)

    def configure_plot(self, title, plots, **layout):
        self.title, self.plots, self.layout = title, plots, layout


class SimulatedB1500:
    wgfmu = None

    def __init__(self, condition='normal', symmetric=False, missing_time=False):
        self.condition, self.symmetric, self.missing_time = condition, symmetric, missing_time
        self.calls = []
        self.active = False
        self.clock = 0.0
        self.records = iter(())
        self.read_count = 0

    def __getattr__(self, name):
        def record(*args, **kwargs):
            if self.active:
                raise AssertionError(f'{name} called before EOD/finish_measure')
            self.calls.append((name, args, kwargs))
        return record

    def set_iv_sweep(self, source, mode, range_, start, stop, points, **kwargs):
        assert not self.active
        self.sweep = source, mode, start, stop, points
        self.calls.append(('set_iv_sweep', (source, mode, range_, start, stop, points), kwargs))

    def start_measure(self, channels, modes, ranges, **kwargs):
        assert not self.active
        self.active = True
        self.calls.append(('start_measure', (channels, modes, ranges), kwargs))
        source, mode, start, stop, points = self.sweep
        values = [start + (stop - start) * i / (points - 1) for i in range(points)] if points > 1 else [start]
        if abs(mode) == 3:
            values += values[-2::-1]
        records = []
        for i, output in enumerate(values):
            # A 1 kΩ inner sample plus 100 Ω on each side. Actual sourced
            # current deliberately differs from its setpoint in Force I.
            current = output * .92 if mode < 0 else output * (2 if self.symmetric else 1) / 1200
            if self.condition == 'compliance':
                current = max(-0.0006, min(0.0006, current))
            vlow = -output if self.symmetric else 0.0
            actual = {4: (current, vlow + 1200 * current), 3: (-current * .99, vlow),
                      5: (0.0, vlow + 1100 * current + 2e-4),
                      6: (0.0, vlow + 100 * current - 1e-4)}
            for j, (ch, kind) in enumerate(zip(channels, modes)):
                timestamp = self.clock + j * .003
                if not self.missing_time:
                    records.append((0, 0, 5, timestamp, 0, ch))
                flag = 8 if self.condition == 'compliance' and abs(current) >= .0006 else 0
                records.append((0, 0, kind, actual[ch][kind - 1], flag, ch))
                if self.condition == 'interrupted' and i == 2 and j == 0:
                    records.append(MeasurementAbortRequested('Simulated interruption during point 3'))
            # Output flag arrives last: parser must not lose it after plotting.
            flag = 4 if self.condition == 'compliance' and i == len(values) - 1 else 0
            records.append((0, 0, 3 if mode < 0 else 4, output, flag, source))
            self.clock += .1
        records.append((0, 1, 16, 0.0, 0, -1))
        self.records = iter(records)

    def read_data(self):
        self.calls.append(('read_data', (), {}))
        self.read_count += 1
        value = next(self.records)
        if isinstance(value, Exception):
            raise value
        self.eod = bool(value[1])
        return value

    def finish_measure(self):
        assert self.eod
        self.active = False
        self.calls.append(('finish_measure', (), {}))


def simulate(procedure_class, settings, directory, condition='normal', **instrument_options):
    runner = MemoryRunner()
    procedure = procedure_class(dict(settings), str(directory), '', runner)
    instrument = SimulatedB1500(condition, settings.get('symmetric_terminals', False), **instrument_options)
    error = None
    try:
        procedure.execute(instrument, SimpleNamespace(name='sample'))
    except MeasurementAbortRequested as exc:
        if condition != 'interrupted':
            raise
        error = str(exc)
    files = list(Path(directory).glob('*.csv'))
    if len(files) != 1:
        raise AssertionError(f'Expected one CSV, got {files}')
    return procedure, runner, instrument, files[0].read_text(), error
