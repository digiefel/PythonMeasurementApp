import csv
import itertools
import math
import tempfile
import unittest

from procedures._iv_model import IVPlan, sweep_segments
from procedures.i_sweep import ISweepProcedure
from procedures.v_sweep import VSweepProcedure
from scripts.iv_simulator import MemoryRunner, SimulatedB1500, simulate


def read_csv(text):
    return list(csv.DictReader(line for line in text.splitlines() if not line.startswith('#')))


class IVSweepTests(unittest.TestCase):
    def run_case(self, cls=VSweepProcedure, condition='normal', **settings):
        with tempfile.TemporaryDirectory() as directory:
            return simulate(cls, {'points': 5, 'v_max': 1.2, 'stop_current': .001,
                                  'sweep_pattern': 'Single', **settings}, directory, condition)

    def test_all_supported_wiring_and_pattern_combinations_use_hardware_sweeps(self):
        for cls, sh, sl, low, pattern, sym in itertools.product(
                (ISweepProcedure, VSweepProcedure), (None, 5), (None, 6), (3, 'GNDU'),
                ('Single', 'Return', 'Butterfly'), (False, True)):
            if sym and (cls is ISweepProcedure or low == 'GNDU'):
                continue
            with self.subTest(cls=cls.NAME, sh=sh, sl=sl, low=low, pattern=pattern, sym=sym):
                proc, runner, instrument, text, _ = self.run_case(
                    cls, sense_high=sh, sense_low=sl, low_channel=low,
                    sweep_pattern=pattern, symmetric_terminals=sym)
                rows = read_csv(text)
                expected = {'Single': 5, 'Return': 9, 'Butterfly': 17}[pattern]
                self.assertEqual(len(rows), expected)
                self.assertLessEqual(len(rows[0]), 6)
                self.assertEqual(set(rows[0]), set(proc.plan().csv_headers))
                self.assertEqual(len(runner.plot.sources['main'][0]), expected)
                self.assertTrue(2 <= len(runner.plots) - 1 <= 3)
                self.assertIn('# RunState: complete', text)
                if low == 'GNDU':
                    self.assertTrue(all(math.isnan(float(r['CurrentLow_A'])) for r in rows))
                    if sl is None:
                        self.assertTrue(all(math.isnan(float(r['VoltageLow_V'])) for r in rows))
                starts = [call for call in instrument.calls if call[0] == 'start_measure']
                self.assertEqual(len(starts), 3 if pattern == 'Butterfly' else 1)
                for _, (channels, modes, _), kwargs in starts:
                    self.assertEqual(len(channels), len(set(channels)))
                    self.assertEqual(modes, [m.kind for m in proc.plan().measurements])
                    self.assertNotIn('GNDU', channels)
                    self.assertEqual(kwargs, {'source_output': 1, 'timestamp': 1})
                self.assertEqual(instrument.calls[-1], ('set_switch', (0, False), {}))
                self.assertEqual(len(runner.plot.saved), 1)

    def test_measured_current_is_used_when_both_probes_exist(self):
        _, runner, _, text, _ = self.run_case(ISweepProcedure, sense_high=5, sense_low=6)
        rows = read_csv(text)
        self.assertAlmostEqual(float(rows[-1]['CurrentHigh_A']), .00092)
        self.assertAlmostEqual(runner.plot.sources['main'][0][-1], .00092)
        self.assertAlmostEqual(runner.plot.sources['main'][1][-1], .9203)
        self.assertAlmostEqual(float(rows[1]['Time_s']), .1)
        self.assertIn('# CurrentHigh_A: ForceHigh measured current (measured)', text)
        self.assertNotIn('Programmed', ','.join(rows[0]))

    def test_two_terminal_current_sweep_does_not_invent_a_return_current(self):
        _, runner, _, text, _ = self.run_case(ISweepProcedure)
        rows = read_csv(text)
        self.assertNotIn('CurrentLow_A', rows[0])
        self.assertEqual(float(rows[-1]['CurrentHigh_A']), .001)
        self.assertAlmostEqual(float(rows[-1]['VoltageHigh_V']), 1.104)
        self.assertIn('ForceHigh programmed current (programmed)', text)
        self.assertEqual(runner.plot.sources['main'][0][-1], .001)

    def test_single_low_probe_current_sweep_uses_negated_measured_return(self):
        _, runner, _, text, _ = self.run_case(ISweepProcedure, sense_low=6)
        row = read_csv(text)[-1]
        self.assertAlmostEqual(runner.plot.sources['main'][0][-1], -float(row['CurrentLow_A']))
        self.assertNotEqual(runner.plot.sources['main'][0][-1], float(row['CurrentHigh_A']))
        self.assertIn('minus CurrentLow_A', text)

    def test_symmetric_voltage_setpoints_are_terminal_values(self):
        _, runner, instrument, text, _ = self.run_case(symmetric_terminals=True)
        row = read_csv(text)[-1]
        self.assertAlmostEqual(float(row['VoltageHigh_V']), .6)
        self.assertAlmostEqual(float(row['VoltageLow_V']), -.6)
        self.assertAlmostEqual(runner.plot.sources['main'][0][-1], 1.2)
        calls = [c for c in instrument.calls if c[0] == 'set_sweep_sync']
        self.assertEqual(calls[0][1][3:5], (0, -.6))

    def test_compliance_keeps_programmed_voltage_and_measured_current_distinct(self):
        _, runner, _, text, _ = self.run_case(condition='compliance', sense_high=5, sense_low=6)
        row = read_csv(text)[-1]
        self.assertAlmostEqual(float(row['CurrentHigh_A']), .0006)
        self.assertAlmostEqual(runner.plot.sources['main'][0][-1], .6003)
        self.assertEqual(int(row['Status']), 12)  # Includes trailing output flag.
        self.assertTrue(runner.plot.sources['flagged'][0])
        self.assertEqual(runner.plot.sources['tracking_set'][1][-1], 1.2)

    def test_interruption_saves_acquired_partial_point_without_more_instrument_commands(self):
        _, runner, instrument, text, error = self.run_case(condition='interrupted', sense_high=5, sense_low=6)
        rows = read_csv(text)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]['VoltageHigh_V'], '')
        self.assertNotEqual(rows[-1]['CurrentHigh_A'], '')
        self.assertEqual(instrument.calls[-1][0], 'read_data')
        self.assertIn('# RunState: partial', text)
        self.assertIsNotNone(error)
        self.assertEqual(runner.plot.saved, [])

    def test_missing_timestamp_is_empty_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, text, _ = simulate(VSweepProcedure, {'points': 3, 'sweep_pattern': 'Single'},
                                        directory, missing_time=True)
        self.assertTrue(all(r['Time_s'] == '' for r in read_csv(text)))

    def test_ranges_compliances_and_adc_settings_reach_the_driver(self):
        _, _, instrument, _, _ = self.run_case(ISweepProcedure, sense_high=5, sense_low=6,
            current_range=-1e-3, voltage_range=-2.0, source_range=1e-6,
            voltage_compliance=3.0, return_current_compliance=.002, power_compliance=.001,
            adc_type=1, adc_mode=2, adc_coefficient=4, adc_autozero=True,
            source_wait_factor=2, measurement_wait_offset=.001)
        start = next(c for c in instrument.calls if c[0] == 'start_measure')
        self.assertEqual(start[1][2], [-1e-3, -1e-3, -2.0, -2.0])
        setup = next(c for c in instrument.calls if c[0] == 'configure_smu_acquisition')[2]
        self.assertEqual((setup['adc'], setup['mode'], setup['coefficient'], setup['autozero']), (1, 2, 4, True))
        sweep = next(c for c in instrument.calls if c[0] == 'set_iv_sweep')
        self.assertEqual(sweep[1][2], 1e-6)
        self.assertEqual(sweep[2]['compliance'], 3.0)
        self.assertEqual(sweep[2]['power_compliance'], .001)
        probes = [c for c in instrument.calls if c[0] == 'force_current']
        self.assertTrue(all(c[2] == {'compliance': 10.0, 'range_': 1e-9} for c in probes))

    def test_invalid_wiring_and_symmetric_modes_are_rejected(self):
        for args in [('Force V', 4, 4), ('Force I', 4, 3, 4),
                     ('Force V', 4, 'GNDU', None, None, True),
                     ('Force I', 4, 3, None, None, True)]:
            with self.assertRaises(ValueError):
                IVPlan(*args)
        with self.assertRaises(ValueError):
            sweep_segments(0, 1, 1, 'Single')
        instrument = SimulatedB1500()
        proc = VSweepProcedure({'high_channel': 3, 'low_channel': 3}, '/tmp', '', MemoryRunner())
        with self.assertRaises(ValueError):
            proc.execute(instrument, type('Device', (), {'name': 'sample'})())
        self.assertEqual(instrument.calls, [])

    def test_new_procedures_are_discoverable_and_old_ones_are_gone(self):
        from procedures import load_procedures
        procedures = load_procedures()
        self.assertIn('Isweep', procedures)
        self.assertIn('Vsweep', procedures)
        self.assertNotIn('IVSweep', procedures)
        self.assertNotIn('FourTerminalIV', procedures)

    def test_three_diagnostics_span_the_main_plot(self):
        from plotting.viewer import PlotViewer
        plan = IVPlan('Force V', 4, 3, 5, 6)
        spec = PlotViewer._top_span_layout_spec(None, plan.plot_definitions(), 2, 3)
        self.assertEqual(spec['spanning_plot'].id, 'iv')
        self.assertEqual(len(spec['stack_plots']), 3)

    def test_fit_is_voltage_against_measured_current_in_both_orientations(self):
        for cls in (ISweepProcedure, VSweepProcedure):
            _, runner, _, text, _ = self.run_case(cls, sense_high=5, sense_low=6)
            resistance = next(line.split(': ')[1] for line in text.splitlines()
                              if line.startswith('# FitResistance_ohm:'))
            self.assertAlmostEqual(float(resistance), 1000.)
            self.assertEqual(len(runner.plot.sources['fit'][0]), 2)
        _, runner, _, text, _ = self.run_case(show_fit=False)
        self.assertNotIn('# FitResistance_ohm:', text)
        self.assertEqual(runner.plot.sources['fit'], ([], []))

    def test_overflow_voltage_sentinels_cannot_cancel_into_a_valid_main_point(self):
        plan = IVPlan('Force I', 4, 3, 5, 6)
        row = plan.row(0, 0, {'ForceHigh': (.001, 0, 0.), 'ForceLow': (-.001, 0, .001),
                             'SenseHigh': (1.99999e101, 1, .002),
                             'SenseLow': (1.99999e101, 1, .003)}, (.001, 0))
        self.assertEqual(plan.plot_sources([row])['main'], ([], []))
        saved = dict(zip(plan.csv_headers, plan.csv_row(row)))
        self.assertEqual(saved['VoltageHigh_V'], 1.99999e101)
        self.assertEqual(saved['Status'], 1)
