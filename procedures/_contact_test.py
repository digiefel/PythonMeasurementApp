"""Standalone ContactTest, launched by its own button, never by the device queue.

Settings are deliberately not persisted. Only operator/probe selections enter
this workflow; all acquisition settings and the output directory are fixed here.
CSV contains one row of fitted two-terminal resistances, with no raw readings,
metadata or extra files. Completed fits are checkpointed after each pair.
"""
import csv
from datetime import datetime
from itertools import combinations
import math
from pathlib import Path
import re
import os
import tempfile
import time

from instrumentio.codes import B1500_CH_ALL, B1500_CH_NOCH, B1500_SWP_VF_SGLLIN, B1500_STOP_DISABLE, B1500_LAST_STOP
from instrumentio.constants import SMU_CHANNEL_MAP
from instrumentio.descriptors import describe_status_bits
from plotting import Curve, PlotDef, linear_fit
from procedures.base import MeasurementProcedure, MeasurementAbortRequested

OUTPUT_DIRECTORY = Path('C:/Users/EMN Lab/Desktop/ContactTestLog')
SUMMARY_ORDER = ('12', '13', '14', '1G', '23', '24', '2G', '34', '3G', '4G')
VOLTAGE_START, VOLTAGE_STOP, POINTS = -.01, .01, 20
CURRENT_COMPLIANCE = .01  # 10 mA; flags exclude compliance-limited points from fits.
CURRENT_RANGE = 1e-7  # Limited autorange: never below 100 nA.


def pair_sequence(selected, ground):
    selected = sorted(set(selected))
    if any(number not in (1, 2, 3, 4) for number in selected):
        raise ValueError('Select only SMU1–4.')
    first = [(number, 'G') for number in selected] if ground else []
    second = list(combinations(selected, 2))
    if not first and not second:
        raise ValueError('Select at least two probes, counting GND.')
    return first, second


def format_resistance(value):
    if value is None:
        return '—'
    return f'{value:.1f}'


def filename_part(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value.strip()).rstrip('. ')
    if not value:
        raise ValueError('Operator name and chip name must not be empty.')
    return value


def fitted_current(rows):
    # Fit I=G*V+offset: the commanded voltage is the independent sweep quantity.
    # Flags, missing data and B1500 overflow sentinels do not constitute a fit.
    valid = [(v, i) for v, i, status in rows if not status and v is not None and i is not None
             and math.isfinite(v) and math.isfinite(i) and abs(v) < 1e99 and abs(i) < 1e99]
    if len({v for v, _ in valid}) < 3:
        return None
    fit = linear_fit([v for v, _ in valid], [i for _, i in valid])
    return fit if math.isfinite(fit.slope) and math.isfinite(fit.intercept) and fit.slope > 0 else None


def fitted_resistance(rows):
    fit = fitted_current(rows)
    return 1 / fit.slope if fit is not None else math.nan


class ContactTest(MeasurementProcedure):
    NAME = 'ContactTest'
    # Private procedure module keeps it out of the normal selector/config path.
    PARAMETERS = ()

    def __init__(self, runner, chip, operator, selected, ground, confirm_lift):
        selected = tuple(selected)
        self.first, self.second = pair_sequence(selected, ground)
        self.operator, self.chip = filename_part(operator), filename_part(chip)
        hardware = runner.config.data.get('b1500', {})
        mapping = hardware.get('smu_channel_map') or SMU_CHANNEL_MAP
        try:
            self.channels = {n: int(mapping[f'SMU{n}']) for n in selected}
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError('A selected SMU is missing from the instrument channel map.') from exc
        if len(set(self.channels.values())) != len(self.channels):
            raise ValueError('Selected SMUs must map to distinct hardware channels.')
        super().__init__({'b1500': hardware}, str(OUTPUT_DIRECTORY), '', runner)
        self.confirm_lift = confirm_lift
        self.results, self.readings = {}, {}
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.path = OUTPUT_DIRECTORY / f'ContactTest_{timestamp}_{self.operator}_{self.chip}.csv'

    def plot_definitions(self):
        plots, overlays = [], []
        selected = {f'{a}{b}' for a, b in self.first + self.second}
        for index, key in enumerate(SUMMARY_ORDER):
            color = f'C{index}'
            elements = [Curve(f'{key}_iv', mode='scatter', marker='o', marker_size=3,
                              color=color, legend_label=f'R{key}',
                              legend_label_source=f'{key}_fit',
                              legend_label_template=f'R{key}={{value:.1f}}Ω'),
                        Curve(f'{key}_iv_fit', mode='line', color=color, show_in_legend=False)]
            plots.append(PlotDef(key, row=index // 3, col=index % 3,
                                 xlabel='V (mV)', ylabels=('I (mA)',), elements=elements))
            if key in selected:
                overlays.append(Curve(f'{key}_resistance', mode='bar', color=color, show_in_legend=False))
        plots.append(PlotDef('all', row=3, col=1, colspan=2,
                             ylabels=('R (Ω)',), elements=overlays,
                             xlim=(-0.5, len(SUMMARY_ORDER) - 0.5),
                             xticks=tuple((f'R{key}', index) for index, key in enumerate(SUMMARY_ORDER))))
        return plots

    def measure(self, device=None):
        if not self.path.is_absolute():
            raise RuntimeError('ContactTest saves to C:/Users/EMN Lab/Desktop/ContactTestLog on the instrument PC.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise FileExistsError(self.path)
        b1500 = self.b1500
        self.check_stop(b1500)
        if self.runner.plot is not None:
            self.runner.plot.configure(f'ContactTest — {self.chip}', self.plot_definitions())
        b1500.reset()
        b1500.enable_error_detect(True)
        b1500.stop_mode(B1500_STOP_DISABLE, B1500_LAST_STOP)
        self.prepare_asu_channels(b1500, self.channels.values(), 0.0)
        # ADC/wait setup persists across CL. Configure it once, rather than
        # repeating the driver's setup/error queries for every short sweep.
        for channel in self.channels.values():
            b1500.set_switch(channel, True)
        b1500.configure_smu_acquisition(list(self.channels.values()), adc=0, mode=1, coefficient=1,
                                       parallel=True, autozero=False,
                                       source_wait_factor=1.0, source_wait_offset=0.0,
                                       measurement_wait_factor=1.0, measurement_wait_offset=0.0)
        total = len(self.first) + len(self.second)
        for stage in (self.first, self.second):
            if stage is self.second and self.first and self.second:
                # Every completed sweep has already disabled all SMU outputs.
                self.check_stop(b1500)
                if not self.confirm_lift():
                    raise MeasurementAbortRequested('ContactTest cancelled at the GNDU prompt.')
                self.check_stop(b1500)
            for pair in stage:
                self.check_stop(b1500)
                key = f'{pair[0]}{pair[1]}'
                self.report_progress(len(self.results), total, f'ContactTest: R{key}')
                rows = self.sweep_pair(pair)
                self.readings[key] = rows
                self.results[key] = fitted_resistance(rows)
                self.update_pair_plot(key, rows, self.results[key])
                self.save_results()
                self.log(f'ContactTest R{key}: {format_resistance(self.results[key])} Ω')
        self.report_progress(total, total, 'ContactTest complete')
        self.log(f'ContactTest saved to {self.path}')
        return self.results

    def sweep_pair(self, pair):
        b1500 = self.b1500
        high = self.channels[pair[0]]
        low = None if pair[1] == 'G' else self.channels[pair[1]]
        channels = [high] if low is None else [high, low]
        b1500.set_switch(B1500_CH_ALL, False)
        for channel in channels:
            b1500.set_switch(channel, True)
        if low is not None:
            b1500.force_voltage(low, 0.0, compliance=CURRENT_COMPLIANCE)
        b1500.set_iv_sweep(high, B1500_SWP_VF_SGLLIN, 0.0, VOLTAGE_START, VOLTAGE_STOP, POINTS,
                          hold=0.0, delay=0.0, second_delay=0.0,
                          compliance=CURRENT_COMPLIANCE, power_compliance=0.0)
        self.check_stop(b1500)
        b1500.start_measure(channels, [1] * len(channels), [CURRENT_RANGE] * len(channels), source_output=1, timestamp=0)
        currents = {channel: [] for channel in channels}
        outputs, seen = [], set()
        key = f'{pair[0]}{pair[1]}'
        last_plot = 0.0

        def paired_rows():
            count = min(len(outputs), *(len(values) for values in currents.values()))
            rows = []
            for i in range(count):
                status = outputs[i][1]
                for values in currents.values():
                    status |= values[i][1]
                rows.append((outputs[i][0], currents[high][i][0], status))
            return rows

        while True:
            self.check_stop(b1500)
            _, eod, kind, value, status, channel = b1500.read_data()
            if status and (channel, kind, status) not in seen:
                seen.add((channel, kind, status))
                self.runner.report_status(dict(channel=channel, data_type=kind, status=status,
                                               desc=describe_status_bits(status)))
            if kind == 1 and channel in currents:
                currents[channel].append((value, status))
            elif kind == 4 and channel in (high, B1500_CH_NOCH, B1500_CH_ALL):
                outputs.append((value, status))
            now = time.monotonic()
            if eod or now - last_plot >= .1:
                self.update_pair_plot(key, paired_rows())
                last_plot = now
            if eod:
                break
        b1500.finish_measure()
        b1500.set_switch(B1500_CH_ALL, False)
        counts = [len(outputs), *(len(values) for values in currents.values())]
        if any(count != POINTS for count in counts):
            raise RuntimeError(f'ContactTest R{key}: expected {POINTS} points, got {counts}.')
        return paired_rows()

    def update_pair_plot(self, key, rows, resistance=None):
        plot = self.runner.plot
        if plot is None:
            return
        current = [(v * 1000, i * 1000) for v, i, _ in rows
                   if math.isfinite(v) and math.isfinite(i) and abs(v) < 1e99 and abs(i) < 1e99]
        plot.replace_source(f'{key}_iv', [v for v, _ in current], [i for _, i in current])
        if resistance is not None:
            plot.replace_source(f'{key}_fit', [-10., 10.], [resistance, resistance])
            fit = fitted_current(rows)
            if fit is not None:
                voltages = [VOLTAGE_START, VOLTAGE_STOP]
                plot.replace_source(f'{key}_iv_fit', [v * 1000 for v in voltages],
                                    [(fit.slope * v + fit.intercept) * 1000 for v in voltages])
            if math.isfinite(resistance):
                plot.replace_source(f'{key}_resistance', [SUMMARY_ORDER.index(key)], [resistance])

    def save_results(self):
        """Atomic checkpoint, no generic output fallback, metadata or raw data."""
        keys = [key for key in SUMMARY_ORDER if key in self.results]
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8',
                                             dir=self.path.parent, suffix='.tmp', delete=False) as stream:
                temporary = stream.name
                writer = csv.writer(stream)
                writer.writerow([f'R{key}' for key in keys])
                writer.writerow([self.results[key] for key in keys])
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
