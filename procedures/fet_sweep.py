"""Transistor curves: sweep one terminal while the other is held at each step value."""
from procedures.base import Choice, MeasurementProcedure, SMU, SMUOrGNDU, ValueList, parameter
from procedures._hardware_sweep import CURRENT, SOURCE_VOLTAGE, setup_smus, stream_sweep
from procedures._smu_parameters import ACQUISITION_PARAMETERS
from instrumentio.constants import B1500_CURRENT_RANGES
from instrumentio.codes import B1500_CH_ALL, B1500_SWP_VF_DBLLIN, B1500_SWP_VF_SGLLIN
from plotting import Curve, PlotDef
from si_utils import parse_si_list

HEADERS = ['Step', 'Point', 'Vg_V', 'Vd_V', 'Ig_A', 'Id_A', 'Is_A', 'Time_s', 'Status']


class FETSweepProcedure(MeasurementProcedure):
    """Transfer curves (sweep Vg, one curve per Vd) or output curves (sweep Vd, one per Vg).

    Currents are positive when supplied by the SMU. Source at GNDU leaves Is empty.
    """
    NAME = 'FET Sweep'
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('gate_channel', 'Gate SMU', 1, SMU),
        parameter('drain_channel', 'Drain SMU', 2, SMU),
        parameter('source_channel', 'Source Terminal', 'GNDU', SMUOrGNDU),
        parameter('mode', 'Curve Type', 'Transfer', Choice((('Transfer', 'Transfer (sweep Vg, step Vd)'),
                                                            ('Output', 'Output (sweep Vd, step Vg)')), str)),
        parameter('sweep_start', 'Sweep Start (V)', -2.0, float),
        parameter('sweep_stop', 'Sweep Stop (V)', 2.0, float),
        parameter('points', 'Points', 101, int),
        parameter('double_sweep', 'Sweep Back (hysteresis)', True, bool),
        parameter('step_values', 'Step Values (V)', '0.1, 1', ValueList,
                  help='Voltage on the non-swept terminal; one curve per value.'),
        parameter('gate_compliance', 'Gate Current Compliance (A)', 1e-4, float),
        parameter('drain_compliance', 'Drain Current Compliance (A)', 1e-2, float),
        parameter('current_range', 'Current Measurement Range (A)', 0.0, Choice(B1500_CURRENT_RANGES, float)),
        *ACQUISITION_PARAMETERS,
        parameter('hold_time', 'Hold Time (s)', 0.0, float, help='Before the first point of each curve.', section='Timing'),
        parameter('delay_time', 'Delay Time (s)', 0.0, float, help='After setting each point.', section='Timing'),
    )

    def measure(self, device):
        b1500, transfer = self.b1500, self.mode == 'Transfer'
        steps = parse_si_list(self.step_values)
        gate, drain, source = self.gate_channel, self.drain_channel, self.source_channel
        swept, held = (gate, drain) if transfer else (drain, gate)
        channels = [gate, drain] + ([source] if source != 'GNDU' else [])
        if not steps or len(set(channels)) != len(channels) or not 2 <= self.points <= 10001:
            raise ValueError('Need at least one step value, distinct SMUs and 2–10001 points.')
        compliance = {gate: self.gate_compliance, drain: self.drain_compliance, source: self.drain_compliance}
        self._configure_plot(device, steps, transfer)
        rows, complete = [], False
        try:
            setup_smus(self, b1500, channels, self.current_range)
            if source != 'GNDU':
                b1500.force_voltage(source, 0.0, compliance=self.drain_compliance)
            for i, step in enumerate(steps):
                self.check_stop(b1500)
                self.report_progress(i, len(steps), f'{"Vd" if transfer else "Vg"} = {step:g} V')
                b1500.force_voltage(held, step, compliance=compliance[held])
                b1500.set_iv_sweep(swept, B1500_SWP_VF_DBLLIN if self.double_sweep else B1500_SWP_VF_SGLLIN,
                                   0.0, self.sweep_start, self.sweep_stop, self.points, hold=self.hold_time,
                                   delay=self.delay_time, compliance=compliance[swept])
                start = len(rows)
                stream_sweep(self, b1500, {ch: (CURRENT, self.current_range) for ch in channels}, swept,
                             SOURCE_VOLTAGE, lambda data: self._add_rows(rows, start, i, step, data, transfer))
            b1500.set_switch(B1500_CH_ALL, False)
            complete = True
        finally:
            # Saved even after Stop or an error; the plot image only for a full run.
            self.save_measurement_outputs(rows, self.NAME, device, HEADERS, save_plot=complete)

    def _add_rows(self, rows, start, step_index, step, data, transfer):
        """Rebuild this curve's rows from everything received so far, then redraw it."""
        g, d = data.readings[self.gate_channel], data.readings[self.drain_channel]
        s = data.readings.get(self.source_channel)
        count = min(len(data.outputs), len(g), len(d))
        rows[start:] = [[step_index, p,
                         data.outputs[p][0] if transfer else step, step if transfer else data.outputs[p][0],
                         g[p][0], d[p][0], s[p][0] if s and p < len(s) else '', '' if d[p][2] is None else d[p][2],
                         data.outputs[p][1] | g[p][1] | d[p][1]] for p in range(count)]
        plot, new = self.runner.plot, rows[start:]
        if plot is not None:
            x = [r[2] if transfer else r[3] for r in new]
            plot.replace_source(f'id{step_index}', x, [r[5] for r in new])
            plot.replace_source(f'id{step_index}_abs', x, [abs(r[5]) for r in new])
            plot.replace_source(f'ig{step_index}_abs', x, [abs(r[4]) for r in new])

    def _configure_plot(self, device, steps, transfer):
        held = 'Vd' if transfer else 'Vg'
        xlabel = 'Gate voltage Vg (V)' if transfer else 'Drain voltage Vd (V)'
        # Id, |Id| and |Ig| each on their own axes; the step colors match across panels.
        linear, log_id, log_ig = [], [], []
        for i, step in enumerate(steps):
            color, label = f'C{i % 10}', f'{held} = {step:g} V'
            linear.append(Curve(f'id{i}', mode='line_scatter', marker='o', marker_size=3, color=color, legend_label=label))
            log_id.append(Curve(f'id{i}_abs', color=color, legend_label=label))
            log_ig.append(Curve(f'ig{i}_abs', color=color, legend_label=label))
        panels = {
            'linear': dict(title='Drain current', ylabels=('Id (A)',), elements=linear),
            'log': dict(title='|Id|', ylabels=('|Id| (A)',), yscales=('log',), elements=log_id),
            'gate': dict(title='Gate leakage |Ig|', ylabels=('|Ig| (A)',), yscales=('log',), elements=log_ig),
        }
        # The window is taller than wide: the main plot spans the top row, the other two share
        # the bottom row. Transfer curves are read on |Id| (log, subthreshold); output curves on Id.
        main = 'log' if transfer else 'linear'
        secondary = [name for name in panels if name != main]
        self.runner.configure_plot(f'{self.NAME} — {device.name}', [
            PlotDef(main, row=0, col=0, colspan=2, xlabel=xlabel, **panels[main]),
            *(PlotDef(name, row=1, col=col, xlabel=xlabel, **panels[name]) for col, name in enumerate(secondary)),
        ], row_ratios=(1.6, 1.0))
