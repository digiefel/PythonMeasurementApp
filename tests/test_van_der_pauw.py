import csv
import math
from pathlib import Path
import queue
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from plotting import DataSource, PlotDef

# Only the prober is stubbed; procedure, fitting, CSV and plotting models are real.
with patch.dict(sys.modules, {'prober': SimpleNamespace(ProberController=Mock())}):
    from procedures.van_der_pauw import (
        VanDerPauwProcedure, CONTACT_SWEEPS, Reading, sheet_resistance, analyze_measurement,
    )
    from runner import MeasurementAbortRequested
    from instrumentio.constants import SMU_CHANNEL_MAP

class MemoryPlot:
    def __init__(self):
        self.sources = {}
        self.save_png = Mock()

    def replace_source(self, name, xs, ys):
        source = self.sources.setdefault(name, DataSource())
        source.clear()
        source.append_many(xs, ys)


class FakeB1500:
    """Simulated sheet with different RA and RB values and voltage offsets."""
    rs = 500.0
    ra = 60.0
    rb = -rs / math.pi * math.log(1 - math.exp(-math.pi * ra / rs))

    def __init__(self, flagged=False, truncated=False, negative=False, swapped_scale=1.0):
        self.calls = []
        self.swapped_scale = swapped_scale
        self.flagged = flagged
        self.truncated = truncated
        self.negative = negative
        self.on_read = None

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record

    def set_iv_sweep(self, source, mode, range_, start, stop, points, **kwargs):
        self.sweep = source, start, stop, points
        self.calls.append(('set_iv_sweep', (source, mode, range_, start, stop, points), kwargs))

    def start_measure(self, channels, modes, ranges, **kwargs):
        self.calls.append(('start_measure', (channels, modes, ranges), kwargs))
        source, start, stop, count = self.sweep
        # Expected channel wiring, written out independently of CONTACT_SWEEPS.
        forward = ((3, 5, 4, 6), (4, 3, 6, 5), (6, 4, 5, 3), (5, 6, 3, 4))
        swapped = ((4, 6, 3, 5), (6, 5, 4, 3), (5, 3, 6, 4), (3, 4, 5, 6))
        assert tuple(channels) in forward + swapped, channels
        assert modes == [1, 2, 1, 2]
        resistance = self.ra if set((channels[0], channels[2])) in ({3, 4}, {5, 6}) else self.rb
        if tuple(channels) in swapped:
            resistance *= self.swapped_scale
        if self.negative:
            resistance *= -1
        records = []
        for i in range(count - int(self.truncated)):
            set_current = start + (stop - start) * i / (count - 1)
            current = set_current * 0.92  # distinguish measured from programmed current
            common = current * 300
            differential = resistance * current + source * 2e-6
            status = 1 if self.flagged and i == 0 else 0
            for ch, mode, value, flag in zip(channels, modes,
                                            (current, common + differential, -current, common),
                                            (0, 0, status, 0)):
                records.extend([(0, 0, 5, i * .1 + channels.index(ch) * .01, 0, ch),
                                (0, 0, mode, value, flag, ch)])
            # Source status arrives AFTER the final voltage record.
            records.append((0, 0, 3, set_current, status, source))
        records.append((0, 1, 16, 0, 0, -1))
        self.records = iter(records)

    def read_data(self):
        record = next(self.records)
        self.calls.append(('read_data', (), {}))
        if self.on_read:
            self.on_read()
        return record


class VanDerPauwTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.runner = SimpleNamespace(
            log=Mock(), configure_plot=Mock(), report_status=Mock(), plot=MemoryPlot(),
            stop_event=threading.Event(), skip_device_event=threading.Event(),
            current_chip='chip', current_site=SimpleNamespace(name='site'),
            current_subsite=SimpleNamespace(name='subsite'), current_temp_c=None,
        )
        self.device = SimpleNamespace(name='sample')

    def procedure(self, **settings):
        return VanDerPauwProcedure({'points': 9, **settings}, self.directory.name, '', self.runner)

    def saved(self, suffix):
        files = list(Path(self.directory.name).glob('*' + suffix))
        self.assertEqual(len(files), 1, files)
        with files[0].open() as stream:
            return list(csv.DictReader(line for line in stream if not line.startswith('#')))

    def results_header(self):
        files = list(Path(self.directory.name).glob('*.csv'))
        self.assertEqual(len(files), 1)
        with files[0].open() as stream:
            return dict(line[2:].strip().split(': ', 1) for line in stream
                        if line.startswith('# ') and ': ' in line)

    def test_full_measurement_recovers_sheet_resistance_and_preserves_raw_data(self):
        instrument = FakeB1500()
        self.procedure(measurement_range=-2.0).execute(instrument, self.device)
        summary = self.results_header()
        self.assertAlmostEqual(float(summary['SheetResistance_ohm_per_square']), 500)
        self.assertNotIn('Quality', summary)
        raw_files = [p for p in Path(self.directory.name).glob('*.csv') if p.stem.endswith('VanDerPauw')]
        with raw_files[0].open() as stream:
            raw = list(csv.DictReader(line for line in stream if not line.startswith('#')))
        self.assertEqual(len(raw), 72)
        self.assertAlmostEqual(float(raw[1]['SourceTime_s']), .1)
        self.assertEqual({(r['CurrentSMUs'], r['VoltageSMUs']) for r in raw},
                         {('1->2', '3-4'), ('2->1', '4-3'), ('2->4', '1-3'), ('4->2', '3-1'),
                          ('4->3', '2-1'), ('3->4', '1-2'), ('3->1', '4-2'), ('1->3', '2-4')})
        self.assertAlmostEqual(float(summary['I 1->2 / V 3-4_VoltageAtZeroCurrent_V']), 6e-6)
        pair_values = self.runner.plot.sources['sheet_forward'].y
        self.assertEqual(len(pair_values), 4)
        for value in pair_values:
            self.assertAlmostEqual(value, 500)
        self.assertEqual(len(self.runner.plot.sources['top_raw'].x), 9)
        self.assertAlmostEqual(self.runner.plot.sources['sheet_fit'].y[-1], 500)
        force_calls = [c for c in instrument.calls if c[0] == 'force_current']
        self.assertEqual(len(force_calls), 16)
        for _, args, kwargs in force_calls:
            self.assertEqual(args[1], 0.0)
            self.assertEqual(kwargs, {'compliance': 10.0, 'range_': 0.0})
        starts = [c for c in instrument.calls if c[0] == 'start_measure']
        self.assertEqual(len(starts), 8)
        self.assertTrue(all(c[1][2] == [0, -2, 0, -2] for c in starts))
        # All records including EOD must be read before output shutdown.
        positions = [i for i, c in enumerate(instrument.calls) if c[0] == 'zero_output']
        self.assertEqual(len(positions), 8)
        for pos in positions:
            self.assertEqual(instrument.calls[pos - 1][0], 'read_data')
        self.runner.plot.save_png.assert_called_once()

    def test_swapped_sweeps_are_averaged_and_disagreement_is_visible(self):
        procedure = self.procedure()
        procedure.execute(FakeB1500(swapped_scale=1.1), self.device)
        header = self.results_header()
        self.assertAlmostEqual(float(header['Forward_SheetResistance_ohm_per_square']), 500)
        self.assertAlmostEqual(float(header['Swapped_SheetResistance_ohm_per_square']), 550)
        self.assertAlmostEqual(float(header['SheetResistance_ohm_per_square']), 525)
        self.assertAlmostEqual(float(header['I 1->2 / V 3-4_SwapDifference_pct']), -100 * .1 / 1.05)
        self.assertTrue(all(abs(value - 500) < 1e-6 for value in self.runner.plot.sources['sheet_forward'].y))
        self.assertTrue(all(abs(value - 550) < 1e-6 for value in self.runner.plot.sources['sheet_swapped'].y))
        self.assertEqual(len(self.runner.plot.sources['top_swapped_raw'].x), 9)
        plots = self.runner.configure_plot.call_args.args[1]
        self.assertIn('dR -9.52%', plots[1].title)
        self.assertEqual(len(plots), 5)

    def test_defaults_use_smu_numbers_and_follow_discovered_slots(self):
        with patch.dict(SMU_CHANNEL_MAP, {'SMU1': 7, 'SMU2': 2, 'SMU3': 9, 'SMU4': 5}, clear=True):
            procedure = self.procedure()
            self.assertEqual((procedure.TL_channel, procedure.TR_channel,
                              procedure.BL_channel, procedure.BR_channel), (7, 2, 9, 5))
            self.assertEqual(procedure.plot_definitions()[1].title, 'I 1->2 / V 3-4')
            instrument = Mock()
            instrument.read_data.return_value = (0, 1, 16, 0, 0, -1)
            procedure.perform_iv_sweep(instrument, CONTACT_SWEEPS[0], [])
            self.assertEqual(instrument.start_measure.call_args.args[0], [7, 9, 2, 5])
            self.assertIn('# TL: SMU1', procedure.csv_metadata_lines())

    def test_changed_wiring_updates_plot_labels_and_sweep_channels(self):
        procedure = self.procedure(TL_channel='SMU4', TR_channel='SMU3',
                                   BL_channel='SMU2', BR_channel='SMU1')
        self.assertEqual(procedure.plot_definitions()[1].title, 'I 4->3 / V 2-1')
        instrument = Mock()
        instrument.read_data.return_value = (0, 1, 16, 0, 0, -1)
        procedure.perform_iv_sweep(instrument, CONTACT_SWEEPS[0], [])
        self.assertEqual(instrument.start_measure.call_args.args[0], [6, 4, 5, 3])

    def test_instrument_flags_are_shown_without_excluding_points(self):
        self.procedure().execute(FakeB1500(flagged=True), self.device)
        self.assertEqual(len(self.runner.plot.sources['sheet_forward'].y), 4)
        self.assertEqual(len(self.runner.plot.sources['top_flagged'].x), 1)
        self.assertAlmostEqual(float(self.results_header()['SheetResistance_ohm_per_square']), 500)
        self.assertNotIn('Quality', self.results_header())

    def test_one_amplitude_sets_both_sweep_endpoints_and_even_points_work(self):
        instrument = FakeB1500()
        self.procedure(ibias=2e-6, points=4, current_compliance=1e-7).execute(instrument, self.device)
        sweeps = [args for name, args, kwargs in instrument.calls if name == 'set_iv_sweep']
        self.assertEqual(len(sweeps), 8)
        for args in sweeps:
            self.assertEqual(args[3:6], (-2e-6, 2e-6, 4))
        self.assertAlmostEqual(float(self.results_header()['SheetResistance_ohm_per_square']), 500)

    def test_short_stream_keeps_available_data(self):
        self.procedure().execute(FakeB1500(truncated=True), self.device)
        self.assertEqual(len(self.runner.plot.sources['top_raw'].x), 8)
        self.assertAlmostEqual(float(self.results_header()['SheetResistance_ohm_per_square']), 500)

    def test_negative_slopes_are_saved_and_undefined_sheet_resistance_is_nan(self):
        self.procedure().execute(FakeB1500(negative=True), self.device)
        self.assertTrue(list(Path(self.directory.name).glob('*VanDerPauw.csv')))
        self.assertTrue(math.isnan(float(self.results_header()['SheetResistance_ohm_per_square'])))
        self.assertTrue(all(float(self.results_header()[name + '_Resistance_ohm']) < 0
                            for name in ('I 1->2 / V 3-4', 'I 2->4 / V 1-3', 'I 4->3 / V 2-1', 'I 3->1 / V 4-2')))

    def test_abort_during_read_keeps_complete_points_and_leaves_cleanup_to_runner(self):
        instrument = FakeB1500()
        count = 0
        def stop():
            nonlocal count
            count += 1
            if count == 11:
                self.runner.stop_event.set()
        instrument.on_read = stop
        with self.assertRaises(MeasurementAbortRequested):
            self.procedure().execute(instrument, self.device)
        self.assertEqual(len(self.saved('_partial.csv')), 1)
        self.assertEqual(instrument.calls[-1][0], 'read_data')

    def test_headless_measurement(self):
        self.runner.plot = None
        self.procedure().execute(FakeB1500(), self.device)
        self.assertAlmostEqual(float(self.results_header()['SheetResistance_ohm_per_square']), 500)

    def test_equation_for_symmetric_and_asymmetric_sheets(self):
        self.assertAlmostEqual(sheet_resistance(100, 100), math.pi * 100 / math.log(2))
        self.assertAlmostEqual(sheet_resistance(FakeB1500.ra, FakeB1500.rb), 500)
        for a, b in ((0, 1), (-1, 1), (math.nan, 1), (1, math.inf)):
            self.assertTrue(math.isnan(sheet_resistance(a, b)))

    def test_nonlinear_data_is_fitted_without_quality_grading(self):
        readings_by_contacts = {}
        for name, *_ in CONTACT_SWEEPS:
            rows = []
            for i in range(9):
                current = (i - 4) * 1e-6
                slope = 100 if name != 'bottom' else 130
                voltage = slope * current + (1e13 * current ** 3 if name == 'right' else 0)
                rows.append(Reading(name, '', i, current, current, -current, voltage, 0, i, 0, 0, 0, 0, 0))
            readings_by_contacts[name] = rows
        result = analyze_measurement(readings_by_contacts, 9)
        self.assertLess(result['fits']['right'].r_squared, .995)
        self.assertEqual(result['fits']['bottom'].slope, 130)
        self.assertNotIn('warnings', result)
        self.assertTrue(math.isfinite(result['sheet']))


class PlotLayoutTests(unittest.TestCase):
    def test_five_panels_span_and_existing_three_panel_layout(self):
        from plotting.viewer import PlotViewer
        viewer = PlotViewer(queue.Queue(), queue.Queue())
        layout = viewer._split_span_layout_spec(VanDerPauwProcedure({}, '', '', Mock()).plot_definitions(), 2, 3)
        self.assertIsNotNone(layout)
        self.assertEqual(layout['spanning_plot'].id, 'sheet')
        self.assertEqual([p.id for p in layout['stack_plots']], ['top', 'right', 'bottom', 'left'])
        existing = [PlotDef('main', rowspan=2), PlotDef('top', col=1), PlotDef('bottom', row=1, col=1)]
        self.assertIsNotNone(viewer._split_span_layout_spec(existing, 2, 2))
        self.assertIsNone(viewer._split_span_layout_spec(existing[:-1], 2, 2))

    def test_dynamic_sheet_result_label(self):
        from plotting.viewer import PlotViewer, _HLineState
        viewer = PlotViewer(queue.Queue(), queue.Queue())
        element = VanDerPauwProcedure({}, '', '', Mock()).plot_definitions()[0].elements[2]
        source = DataSource()
        source.append_point(1, 500)
        with patch('plotting.viewer.dpg.set_value') as values, patch('plotting.viewer.dpg.set_item_label') as label:
            viewer._redraw_hline(_HLineState('sheet', element, 123), source)
        values.assert_called_once_with(123, [[500.0]])
        label.assert_called_once_with(123, 'Average: 500 Ohm/sq')


if __name__ == '__main__':
    unittest.main()
