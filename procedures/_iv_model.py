"""Hardware-sweep channel plan, CSV schema and plots. No instrument I/O.

One quantity per SMU per sweep. All consumers (live plots, CSV and preview)
use this plan; programmed values are never substituted for missing readings.
"""
from dataclasses import dataclass
import math

from plotting import Curve, PlotDef, linear_fit


@dataclass(frozen=True)
class Measurement:
    role: str
    channel: int
    kind: int  # B1500: 1=current, 2=voltage

    @property
    def column(self):
        return f'{self.role}_{"Current" if self.kind == 1 else "Voltage"}_Measured_{"A" if self.kind == 1 else "V"}'

    @property
    def time_column(self):
        return f'{self.role}_Time_s'

    @property
    def status_column(self):
        return f'{self.role}_Status'


@dataclass(frozen=True)
class Quantity:
    column: str
    label: str
    basis: str
    sign: int = 1

    def value(self, row):
        value = row.get(self.column)
        return math.nan if value is None else self.sign * value


@dataclass(frozen=True)
class Trace:
    name: str
    x: str
    y: str
    label: str
    sign: int = 1
    color: str = 'C0'


class IVPlan:
    def __init__(self, force_mode, high, low, sense_high=None, sense_low=None, symmetric=False, show_fit=True):
        if force_mode not in ('Force V', 'Force I'):
            raise ValueError('Select Force V or Force I.')
        channels = [c for c in (high, low, sense_high, sense_low) if c not in (None, 'GNDU')]
        if len(channels) != len(set(channels)):
            raise ValueError('Force and sense SMUs must all be different channels.')
        if symmetric and (force_mode != 'Force V' or low == 'GNDU'):
            raise ValueError('Symmetric voltages require Force V and a return SMU.')
        self.force_mode, self.high, self.low = force_mode, high, low
        self.sense_high, self.sense_low, self.symmetric = sense_high, sense_low, symmetric
        self.show_fit = show_fit
        self.measurements = []
        # In Force I, a force terminal measures V if no separate probe supplies
        # its voltage. Otherwise that SMU is free to measure I.
        for role, ch, sense in (('ForceHigh', high, sense_high), ('ForceLow', low, sense_low)):
            if ch != 'GNDU':
                kind = 1 if force_mode == 'Force V' or sense is not None else 2
                self.measurements.append(Measurement(role, ch, kind))
        for role, ch in (('SenseHigh', sense_high), ('SenseLow', sense_low)):
            if ch is not None:
                self.measurements.append(Measurement(role, ch, 2))
        self.source_column = f'ForceHigh_{"Voltage_Programmed_V" if force_mode == "Force V" else "Current_Programmed_A"}'
        self.low_programmed = 'ForceLow_Voltage_Programmed_V'
        self.voltage_high = self._voltage_endpoint('High', sense_high)
        self.voltage_low = self._voltage_endpoint('Low', sense_low)
        bases = {self.voltage_high.basis, self.voltage_low.basis}
        if 'programmed' in bases and 'measured' in bases:
            basis = 'Mixed'
        elif 'programmed' in bases:
            basis = 'Programmed'
        elif 'GNDU reference' in bases:
            basis = 'GNDUReferenced'
        else:
            basis = 'Measured'
        self.voltage = Quantity(f'VoltageDifference_{basis}_V',
                                f'Voltage difference ({basis.replace("GNDUReferenced", "GNDU referenced").lower()}, V)', basis)
        currents = [m for m in self.measurements if m.kind == 1]
        if currents:
            m = currents[0]
            sign = 1 if m.role == 'ForceHigh' else -1
            self.current = Quantity(m.column, 'Measured current (A)' if sign == 1 else 'Measured -return current (A)', 'measured', sign)
        else:
            self.current = Quantity(self.source_column, 'Programmed current (A)', 'programmed')
        self.x, self.y = ((self.voltage, self.current) if force_mode == 'Force V'
                          else (self.current, self.voltage))

    def _voltage_endpoint(self, side, sense):
        role = f'Sense{side}' if sense is not None else f'Force{side}'
        measured = next((m for m in self.measurements if m.role == role and m.kind == 2), None)
        if measured:
            return Quantity(measured.column, f'{role} measured V', 'measured')
        if side == 'Low' and self.low == 'GNDU':
            return Quantity('', 'GNDU nominal 0 V', 'GNDU reference')
        return Quantity(f'{role}_Voltage_Programmed_V', f'{role} programmed V', 'programmed')

    @property
    def headers(self):
        columns = ['Point', 'Segment', self.source_column, 'SourceOutput_Status']
        if self.low != 'GNDU':
            columns.append(self.low_programmed)
        for m in self.measurements:
            columns.extend((m.column, m.time_column, m.status_column))
        return columns + [self.voltage.column, 'Status']

    @property
    def csv_quantities(self):
        quantities = {'VoltageHigh_V': self.voltage_high, 'VoltageLow_V': self.voltage_low}
        for side in ('High', 'Low'):
            m = next((m for m in self.measurements if m.role == f'Force{side}' and m.kind == 1), None)
            if m:
                quantities[f'Current{side}_A'] = Quantity(m.column, f'Force{side} measured current', 'measured')
            elif side == 'High' and self.force_mode == 'Force I':
                quantities['CurrentHigh_A'] = Quantity(self.source_column, 'ForceHigh programmed current', 'programmed')
            elif side == 'Low' and self.low == 'GNDU':
                quantities['CurrentLow_A'] = Quantity('', 'GNDU current unavailable', 'unavailable')
        return quantities

    @property
    def csv_headers(self):
        return [*self.csv_quantities, 'Time_s', 'Status']

    def csv_row(self, row):
        values = []
        for quantity in self.csv_quantities.values():
            if quantity.basis in ('GNDU reference', 'unavailable'):
                values.append(math.nan)
            else:
                values.append(row.get(quantity.column))
        values += [row.get(self.measurements[0].time_column), row['Status']]
        return ['' if value is None else value for value in values]

    @property
    def metadata(self):
        lines = [
            '# IVSchema: 2',
            '# Acquisition: instrument-controlled hardware staircase sweep; one quantity per SMU',
            '# VoltageHigh/Low are the selected sensing endpoints, or force terminals when no probe is selected',
            '# CurrentHigh/Low refer to the force terminals; positive means current supplied by that SMU',
            '# Programmed values are source settings, not independent measurements',
            '# Unavailable quantities are omitted; GNDU quantities are NaN; missing records are empty cells',
            f'# Time_s: {self.measurements[0].role} reading, seconds since run timer reset; other channels may measure later',
            '# Status: bitwise OR of all acquired measurement and source-output statuses',
            '# Main voltage: VoltageHigh_V minus VoltageLow_V; GNDU uses nominal zero only for this calculation',
            f'# Main current: {self.current.label}; {"minus CurrentLow_A" if self.current.sign == -1 else "CurrentHigh_A"}',
        ]
        for column, quantity in self.csv_quantities.items():
            lines.append(f'# {column}: {quantity.label} ({quantity.basis})')
        for m in self.measurements:
            lines.append(f'# {m.role}: hardware channel {m.channel}; measures {"current" if m.kind == 1 else "voltage"}')
        return lines

    def row(self, point, segment, samples, output=None):
        """samples maps role -> (value, status, time). Keep incomplete rows too."""
        row = dict.fromkeys(self.headers)
        row.update(Point=point, Segment=segment)
        status = 0
        if output is not None:
            row[self.source_column], row['SourceOutput_Status'] = output
            status |= output[1]
        if self.low != 'GNDU':
            row[self.low_programmed] = (-output[0] if output is not None else None) if self.symmetric else 0.0
        for m in self.measurements:
            if m.role in samples:
                value, flag, timestamp = samples[m.role]
                row[m.column], row[m.status_column], row[m.time_column] = value, flag, timestamp
                status |= flag
        high = self.voltage_high.value(row)
        low = 0.0 if self.voltage_low.basis == 'GNDU reference' else self.voltage_low.value(row)
        difference = high - low
        # B1500 overflow/dummy sentinels must not cancel into a plausible zero.
        row[self.voltage.column] = (difference if math.isfinite(difference)
                                   and abs(high) < 1e99 and abs(low) < 1e99 else None)
        row['Status'] = status
        return row

    def diagnostics(self):
        time_column = self.measurements[0].time_column
        unit = 'V' if self.force_mode == 'Force V' else 'A'
        tracking = [Trace('tracking_set', time_column, self.source_column, f'Force high programmed ({unit})')]
        if self.force_mode == 'Force I' and self.current.basis == 'measured':
            current_m = next(m for m in self.measurements if m.column == self.current.column)
            tracking.append(Trace('tracking_measured', current_m.time_column, self.current.column,
                                  self.current.label, self.current.sign, 'C1'))
        panels = [('tracking', 'Sweep progression', 'Time (s)', f'Force high ({unit})', tracking)]
        voltages = [m for m in self.measurements if m.kind == 2]
        if voltages:
            panels.append(('voltages', 'Individual measured voltages', self.current.label, 'Voltage (V)', [
                Trace(f'voltage_{m.role}', '@current', m.column, m.role, color=f'C{i}')
                for i, m in enumerate(voltages)]))
        currents = [m for m in self.measurements if m.kind == 1]
        if len(currents) == 2:
            panels.append(('balance', 'Current balance', 'Time (s)', 'Current (A)', [
                Trace(f'current_{m.role}', m.time_column, m.column,
                      'Force high' if m.role == 'ForceHigh' else '-Force low',
                      1 if m.role == 'ForceHigh' else -1, f'C{i}') for i, m in enumerate(currents)]))
        elif not voltages:
            # Two-terminal Force V + GNDU: still provide the measured response.
            m = currents[0]
            panels.append(('response', 'Measured response', 'Time (s)', 'Current (A)', [
                Trace('current_response', m.time_column, m.column, 'Force high')]))
        return panels

    def plot_definitions(self):
        panels = self.diagnostics()
        plots = [PlotDef(name, row=0, col=i, title=title, xlabel=xlabel, ylabels=(ylabel,),
                         elements=[Curve(t.name, mode='line_scatter', marker='o', marker_size=3,
                                         legend_label=t.label, color=t.color) for t in traces])
                 for i, (name, title, xlabel, ylabel, traces) in enumerate(panels)]
        plots.append(PlotDef('iv', row=1, col=0, colspan=len(panels), title='I–V',
                             xlabel=self.x.label, ylabels=(self.y.label,), elements=[
                                 Curve('main', mode='line_scatter', marker='o', marker_size=3, color='C0'),
                                 Curve('flagged', mode='scatter', marker='x', marker_size=6,
                                       color='C3', legend_label='Instrument flag'),
                             ]))
        if self.show_fit:
            plots[-1].elements.append(Curve('fit', color='C2', legend_label='Whole-trace linear fit'))
        return plots

    def fit(self, rows):
        pairs = [(self.current.value(r), self.voltage.value(r)) for r in rows]
        pairs = [(i, v) for i, v in pairs if math.isfinite(i) and math.isfinite(v)
                 and abs(i) < 1e99 and abs(v) < 1e99]
        if not self.show_fit or len({i for i, _ in pairs}) < 2:
            return None
        # The physical fit is always V=R*I+b, independent of display orientation.
        fit = linear_fit([i for i, _ in pairs], [v for _, v in pairs])
        return fit, min(i for i, _ in pairs), max(i for i, _ in pairs)

    def plot_sources(self, rows):
        sources = {'main': ([], []), 'flagged': ([], []), 'fit': ([], [])}
        traces = [t for *_, ts in self.diagnostics() for t in ts]
        sources.update({t.name: ([], []) for t in traces})

        def append(name, x, y):
            if (x is not None and y is not None and math.isfinite(x) and math.isfinite(y)
                    and abs(x) < 1e99 and abs(y) < 1e99):
                sources[name][0].append(x)
                sources[name][1].append(y)

        for row in rows:
            x, y = self.x.value(row), self.y.value(row)
            append('main', x, y)
            if row['Status']:
                append('flagged', x, y)
            for t in traces:
                x = self.current.value(row) if t.x == '@current' else row.get(t.x)
                y = row.get(t.y)
                append(t.name, x, None if y is None else t.sign * y)
        result = self.fit(rows)
        if result is not None:
            fit, low, high = result
            for current in (low, high):
                voltage = fit.slope * current + fit.intercept
                x, y = (voltage, current) if self.force_mode == 'Force V' else (current, voltage)
                append('fit', x, y)
        return sources


def sweep_segments(start, stop, points, pattern):
    """Hardware segments. Butterfly avoids repeating zero between its halves."""
    if pattern not in ('Single', 'Return', 'Butterfly'):
        raise ValueError('Select Single, Return or Butterfly sweep.')
    if not 2 <= points <= 10001:
        raise ValueError('Points must be between 2 and 10001.')
    if not all(math.isfinite(v) for v in (start, stop)):
        raise ValueError('Sweep endpoints must be finite.')
    if pattern == 'Butterfly':
        amplitude = abs(stop)
        if amplitude == 0:
            raise ValueError('Butterfly amplitude must be nonzero.')
        step = amplitude / (points - 1)
        return [(0.0, amplitude, True, points),
                (-step, -amplitude, False, points - 1),
                (-(amplitude - step), 0.0, False, points - 1)]
    return [(start, stop, pattern == 'Return', points)]
