"""Shared execution for Isweep and Vsweep. Only hardware staircase sweeps."""
import math

from procedures.base import Choice, MeasurementProcedure, OptionalSMU, SMU, SMUOrGNDU, parameter
from procedures._hardware_sweep import CURRENT, SOURCE_CURRENT, SOURCE_VOLTAGE, setup_smus, stream_sweep
from procedures._iv_model import IVPlan, sweep_segments
from procedures._smu_parameters import ACQUISITION_PARAMETERS
from instrumentio.constants import B1500_CURRENT_RANGES, B1500_VOLTAGE_RANGES
from instrumentio.codes import (
    B1500_CH_ALL, B1500_SWP_VF_SGLLIN, B1500_SWP_VF_DBLLIN,
    B1500_SWP_IF_SGLLIN, B1500_SWP_IF_DBLLIN, B1500_VF_MODE,
)

CHANNEL_PARAMETERS = (
    parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
    parameter('high_channel', 'Force High SMU', 4, SMU),
    parameter('sense_high', 'Sense High SMU (optional)', None, OptionalSMU),
    parameter('low_channel', 'Force Low Terminal', 3, SMUOrGNDU),
    parameter('sense_low', 'Sense Low SMU (optional)', None, OptionalSMU),
)
SWEEP_PARAMETERS = (
    parameter('points', 'Points (outward leg)', 75, int),
    parameter('sweep_pattern', 'Sweep Pattern', 'Return',
              Choice(tuple((v, v) for v in ('Single', 'Return', 'Butterfly')), str),
              help='Butterfly: 0 → +|stop| → 0 → −|stop| → 0, ignoring Start. Uses hardware sweep segments.'),
    parameter('power_compliance', 'Source Power Compliance (W; 0 = off)', 0.0, float),
    parameter('current_range', 'Current Measurement Range (A)', 0.0, Choice(B1500_CURRENT_RANGES, float)),
    parameter('voltage_range', 'Voltage Measurement Range (V)', 0.0, Choice(B1500_VOLTAGE_RANGES, float)),
    parameter('sense_voltage_compliance', 'Sense Probe Voltage Compliance (V)', 10.0, float,
              help='Only used by optional voltage probes. They force 0 A on a 1 nA source range.'),
    parameter('show_fit', 'Show R Fit', True, bool,
              help='Fits V=R*I+b across all finite points, including flagged points and return branches. Disable for nonlinear/hysteretic devices. Fit results are saved in the header, not extra columns.'),
    *ACQUISITION_PARAMETERS,
    parameter('hold_time', 'Hold Time (s)', 0.0, float, help='At the start of each hardware segment.', section='Timing'),
    parameter('delay_time', 'Delay Time (s)', 0.0, float, help='After setting each step; automatic settling remains active.', section='Timing'),
    parameter('second_delay', 'Second Delay (s)', 0.0, float,
              help='Hardware step delay from measurement start; also waits for measurement completion.', section='Timing'),
)


class IVSweepBase(MeasurementProcedure):
    """Shared channel planning, streaming, plotting and compact CSV output.

    Four-terminal main plots use measured I and measured sense voltage. Missing
    voltage probes fall back to force-terminal readings in Isweep or programmed
    terminal voltages in Vsweep. CSV metadata explicitly describes each column.
    GNDU measurements are NaN; its nominal zero is used only as a plot reference.
    """
    FORCE_MODE = None

    def plan(self):
        return IVPlan(self.FORCE_MODE, self.high_channel, self.low_channel,
                      self.sense_high, self.sense_low, getattr(self, 'symmetric_terminals', False), self.show_fit)

    def segments(self):
        start, stop = ((self.start_voltage, self.v_max) if self.FORCE_MODE == 'Force V'
                       else (self.start_current, self.stop_current))
        return sweep_segments(start, stop, self.points, self.sweep_pattern)

    def validate(self):
        plan = self.plan()
        self.segments()
        for p in self.PARAMETERS:
            value = getattr(self, p.attr or p.key)
            if p.kind is float and not math.isfinite(value):
                raise ValueError(f'{p.label} must be finite.')
        for key in ('current_compliance', 'return_current_compliance', 'voltage_compliance', 'sense_voltage_compliance'):
            if hasattr(self, key) and getattr(self, key) <= 0:
                raise ValueError(f'{key} must be positive.')
        if self.power_compliance < 0:
            raise ValueError('Power compliance must be nonnegative.')
        for key, limit in (('hold_time', 655.35), ('delay_time', 65.535), ('second_delay', 1.0)):
            if not 0 <= getattr(self, key) <= limit:
                raise ValueError(f'{key} must be between 0 and {limit} seconds.')
        if self.source_range < 0:
            raise ValueError('Source range must be Auto or a positive range floor.')
        return plan

    def csv_metadata_lines(self, extra=None):
        lines = super().csv_metadata_lines(extra) + self.plan().metadata
        lines += [f'# RunState: {getattr(self, "_run_state", "not started")}',
                  '# Source settings and segment endpoints are in the parameter/header metadata; no extra setpoint columns']
        for index, segment in enumerate(self.segments()):
            lines.append(f'# Segment {index}: start={segment[0]}, stop={segment[1]}, return={segment[2]}, points={segment[3]}')
        if getattr(self, '_failure', None):
            lines.append(f'# Interruption: {self._failure}')
        if getattr(self, '_fit_result', None) is not None:
            fit = self._fit_result[0]
            lines += ['# Fit: V=R*I+b over the whole trace, including instrument-flagged points',
                      f'# FitResistance_ohm: {fit.slope}', f'# FitOffset_V: {fit.intercept}',
                      f'# FitR_squared: {fit.r_squared}']
        return lines

    def measure(self, device):
        plan = self.validate()  # No instrument commands until the wiring is valid.
        b1500 = self.b1500
        rows = []
        self._run_state, self._failure, self._fit_result = 'partial', None, None
        base = self.format_filename(self.NAME, device.name)
        self.runner.configure_plot(f'{self.NAME} — {device.name}', plan.plot_definitions(),
                                   row_ratios=(1.0, 2.8))
        try:
            self.check_stop(b1500)
            asu_range = self.current_range
            if self.FORCE_MODE == 'Force I' and self.source_range == 1e-12:
                asu_range = 1e-12
            setup_smus(self, b1500, [m.channel for m in plan.measurements], asu_range)
            if self.low_channel != 'GNDU':
                compliance = self.return_current_compliance if self.FORCE_MODE == 'Force I' else self.current_compliance
                b1500.force_voltage(self.low_channel, 0.0, compliance=compliance)
            for ch in (self.sense_high, self.sense_low):
                if ch is not None:
                    b1500.force_current(ch, 0.0, compliance=self.sense_voltage_compliance, range_=1e-9)
            b1500.reset_timestamp()
            for index, segment in enumerate(self.segments()):
                self.check_stop(b1500)
                self._program_segment(b1500, plan, segment)
                self._collect_segment(b1500, plan, index, rows)
            b1500.set_switch(B1500_CH_ALL, False)
            self._run_state = 'complete'
        except Exception as exc:
            self._failure = str(exc).replace('\n', ' ')
            # Never issue instrument commands here: transport may be cancelled.
            # Local data already includes even a partly acquired last point.
            try:
                self._save_rows(plan, rows, base)
            except Exception as save_error:
                self.log(f'Could not save partial sweep: {save_error}')
            raise
        self._save_rows(plan, rows, base)
        self.save_plot_png(f'{base}_plot.png')
        self.log(f'{self.NAME}: saved {len(rows)} points for {device.name}')

    def _save_rows(self, plan, rows, base):
        self._fit_result = plan.fit(rows)
        self.save_data([plan.csv_row(row) for row in rows], f'{base}.csv',
                       plan.csv_headers, add_timestamp=False)

    def _program_segment(self, b1500, plan, segment):
        start, stop, double, points = segment
        if self.FORCE_MODE == 'Force V':
            mode = B1500_SWP_VF_DBLLIN if double else B1500_SWP_VF_SGLLIN
            compliance = self.current_compliance
        else:
            mode = B1500_SWP_IF_DBLLIN if double else B1500_SWP_IF_SGLLIN
            compliance = self.voltage_compliance
        divisor = 2 if plan.symmetric else 1
        b1500.set_iv_sweep(self.high_channel, mode, self.source_range, start / divisor, stop / divisor,
                          points, hold=self.hold_time, delay=self.delay_time, second_delay=self.second_delay,
                          compliance=compliance, power_compliance=self.power_compliance)
        if plan.symmetric:
            b1500.set_sweep_sync(self.low_channel, B1500_VF_MODE, self.source_range,
                                -start / 2, -stop / 2, self.current_compliance, self.power_compliance)

    def _collect_segment(self, b1500, plan, segment, all_rows):
        measure = {m.channel: (m.kind, self.current_range if m.kind == CURRENT else self.voltage_range)
                   for m in plan.measurements}
        base_index = len(all_rows)

        def update_rows(data):
            # No assumed count or reconstructed setpoint vector: retain exactly
            # what the instrument reported, including trailing status records.
            buffers = {m.role: data.readings[m.channel] for m in plan.measurements}
            count = max([len(data.outputs), *(len(b) for b in buffers.values())])
            all_rows[base_index:] = [
                plan.row(base_index + i, segment,
                         {role: values[i] for role, values in buffers.items() if i < len(values)},
                         data.outputs[i] if i < len(data.outputs) else None) for i in range(count)]
            self._plot_rows(plan, all_rows)

        stream_sweep(self, b1500, measure, self.high_channel,
                     SOURCE_VOLTAGE if self.FORCE_MODE == 'Force V' else SOURCE_CURRENT, update_rows)

    def _plot_rows(self, plan, rows):
        if self.runner.plot is not None:
            for name, (xs, ys) in plan.plot_sources(rows).items():
                self.runner.plot.replace_source(name, xs, ys)
