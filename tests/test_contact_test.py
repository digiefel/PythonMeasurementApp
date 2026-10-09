import contextlib
import csv
from copy import deepcopy
from itertools import combinations
import math
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from procedures._contact_test import ContactTest, SUMMARY_ORDER, pair_sequence, fitted_resistance, format_resistance
from runner import MeasurementRunner, MeasurementAbortRequested


class Plot:
    def __init__(self):
        self.sources = {}
        self.set_progress = Mock()
        self.clear_progress = Mock()

    def configure(self, title, plots, **kwargs):
        self.definitions, self.layout = plots, kwargs

    def replace_source(self, name, xs, ys):
        self.sources[name] = (list(xs), list(ys))


class Instrument:
    wgfmu = None
    mapping = {'SMU1': 6, 'SMU2': 3, 'SMU3': 5, 'SMU4': 4}
    resistances = {key: 10450 + index * 1000 for index, key in enumerate(SUMMARY_ORDER)}

    def __init__(self, flagged=False, broken=False):
        self.calls, self.pairs, self.vectors = [], [], []
        self.active = False
        self.low = None
        self.flagged, self.broken = flagged, broken
        self.fail_next = False

    def exclusive(self):
        return contextlib.nullcontext()

    def __getattr__(self, name):
        def call(*args, **kwargs):
            if self.active and name != 'cancel':
                raise AssertionError(f'Command {name} while stream pending')
            self.calls.append((name, args, kwargs))
        return call

    def set_switch(self, channel, on):
        assert not self.active
        self.calls.append(('set_switch', (channel, on), {}))
        if channel == 0 and not on:
            self.low = None

    def force_voltage(self, channel, value, **kwargs):
        self.calls.append(('force_voltage', (channel, value), kwargs))
        self.low = channel

    def set_iv_sweep(self, channel, mode, range_, start, stop, points, **kwargs):
        self.sweep = channel, start, stop, points
        self.calls.append(('set_iv_sweep', (channel, mode, range_, start, stop, points), kwargs))

    def start_measure(self, channels, modes, ranges, **kwargs):
        assert not self.active
        self.active = True
        self.calls.append(('start_measure', (channels, modes, ranges), kwargs))
        names = {value: key[-1] for key, value in self.mapping.items()}
        source, start, stop, points = self.sweep
        key = names[source] + (names[self.low] if self.low is not None else 'G')
        self.pairs.append(key)
        resistance = self.resistances[key]
        voltages = [start + i * (stop - start) / (points - 1) for i in range(points)]
        self.vectors.append(voltages)
        records = []
        for index, voltage in enumerate(voltages):
            current = voltage / resistance + 2e-9  # Offset tests inverse-slope fitting.
            flag = 8 if self.flagged and index == 5 else 0
            if flag:
                current = .01  # Outlier must not bias the fit.
            for ch in channels:
                records.append((0, 0, 1, current if ch == source else -current, flag, ch))
            records.append((0, 0, 4, voltage, 4 if self.flagged and index == 5 else 0, source))
        if self.broken:
            records.pop()  # Missing last output, but EOD still arrives.
        records.append((0, 1, 16, 0, 0, -1))
        self.records = iter(records)

    def read_data(self):
        self.calls.append(('read_data', (), {}))
        if self.fail_next:
            raise MeasurementAbortRequested('Simulated stop')
        row = next(self.records)
        self.eod = row[1]
        return row

    def finish_measure(self):
        assert self.eod
        self.active = False
        self.calls.append(('finish_measure', (), {}))


class ContactTestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = patch('procedures._contact_test.OUTPUT_DIRECTORY', Path(self.directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner = SimpleNamespace(config=SimpleNamespace(data={'b1500': {'smu_channel_map': Instrument.mapping}}),
                                      log=Mock(), report_status=Mock(), plot=Plot(),
                                      stop_event=threading.Event(), skip_device_event=threading.Event())

    def procedure(self, selected=(1, 2, 3, 4), ground=True, callback=None):
        return ContactTest(self.runner, 'ChipA', 'Operator', selected, ground, callback or Mock(return_value=True))

    def test_full_order_fit_plot_csv_and_outputs_off_before_prompt(self):
        instrument = Instrument()
        def confirm():
            self.assertEqual(instrument.pairs, ['1G', '2G', '3G', '4G'])
            self.assertEqual(instrument.calls[-1], ('set_switch', (0, False), {}))
            self.assertFalse(instrument.active)
            return True
        procedure = self.procedure(callback=confirm)
        procedure.execute(instrument, None)
        self.assertEqual(instrument.pairs, ['1G', '2G', '3G', '4G', '12', '13', '14', '23', '24', '34'])
        for key, value in procedure.results.items():
            self.assertAlmostEqual(value, instrument.resistances[key])
            xs, ys = self.runner.plot.sources[f'{key}_fit']
            self.assertEqual(xs, [-10., 10.])
            self.assertAlmostEqual(ys[0], value)
            self.assertEqual(len(self.runner.plot.sources[f'{key}_rv'][0]), 20)
        self.assertEqual(len(self.runner.plot.definitions), 11)
        with procedure.path.open() as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ['R' + key for key in SUMMARY_ORDER])
        self.assertEqual(len(list(Path(self.directory.name).iterdir())), 1)
        self.assertRegex(procedure.path.name, r'^ContactTest_\d{8}_\d{6}_\d{6}_Operator_ChipA\.csv$')
        for vector in instrument.vectors:
            self.assertEqual(len(vector), 20)
            self.assertEqual(vector[0], -.01)
            self.assertEqual(vector[-1], .01)
            self.assertNotIn(0.0, vector)

    def test_all_probe_selection_combinations(self):
        for ground in (False, True):
            for count in range(5):
                for selected in combinations((1, 2, 3, 4), count):
                    with self.subTest(ground=ground, selected=selected):
                        if count + int(ground) < 2:
                            with self.assertRaises(ValueError):
                                self.procedure(selected, ground)
                            continue
                        prompt = Mock(return_value=True)
                        procedure = self.procedure(selected, ground, prompt)
                        instrument = Instrument()
                        procedure.execute(instrument, None)
                        expected = ([f'{n}G' for n in selected] if ground else [])
                        expected += [f'{a}{b}' for a, b in combinations(selected, 2)]
                        self.assertEqual(instrument.pairs, expected)
                        self.assertEqual(prompt.call_count, int(ground and count >= 2))
                        self.assertEqual(set(procedure.results), set(expected))

    def test_cancel_at_prompt_preserves_ground_results(self):
        instrument = Instrument()
        procedure = self.procedure(callback=Mock(return_value=False))
        with self.assertRaises(MeasurementAbortRequested):
            procedure.execute(instrument, None)
        self.assertEqual(instrument.pairs, ['1G', '2G', '3G', '4G'])
        self.assertEqual(instrument.calls[-1], ('set_switch', (0, False), {}))
        with procedure.path.open() as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], ['R1G', 'R2G', 'R3G', 'R4G'])

    def test_fast_adc_and_100na_floor_are_configured_once(self):
        instrument = Instrument()
        self.procedure().execute(instrument, None)
        acquisitions = [c for c in instrument.calls if c[0] == 'configure_smu_acquisition']
        self.assertEqual(len(acquisitions), 1)
        self.assertEqual(acquisitions[0][2], dict(adc=0, mode=1, coefficient=1, parallel=True, autozero=False,
                            source_wait_factor=1., source_wait_offset=0., measurement_wait_factor=1., measurement_wait_offset=0.))
        for _, (channels, modes, ranges), options in [c for c in instrument.calls if c[0] == 'start_measure']:
            self.assertEqual(ranges, [1e-7] * len(channels))
            self.assertEqual(modes, [1] * len(channels))
            self.assertEqual(options, dict(source_output=1, timestamp=0))
        for _, args, kwargs in [c for c in instrument.calls if c[0] == 'set_iv_sweep']:
            self.assertEqual(args[1:3], (1, 0.))
            self.assertEqual(kwargs, dict(hold=0., delay=0., second_delay=0., compliance=.01, power_compliance=0.))

    def test_flagged_outlier_does_not_bias_fitted_resistance(self):
        instrument = Instrument(flagged=True)
        procedure = self.procedure((1, 2), False)
        procedure.execute(instrument, None)
        self.assertAlmostEqual(procedure.results['12'], Instrument.resistances['12'])
        self.assertEqual(len(self.runner.plot.sources['12_flagged'][0]), 1)
        self.runner.report_status.assert_called()

    def test_short_stream_is_not_saved_as_a_completed_fit(self):
        instrument = Instrument(broken=True)
        procedure = self.procedure((1,), True)
        with self.assertRaisesRegex(RuntimeError, 'expected 20 points'):
            procedure.execute(instrument, None)
        self.assertFalse(procedure.path.exists())
        self.assertFalse(instrument.active)

    def test_mid_stream_abort_does_not_issue_further_commands(self):
        instrument = Instrument()
        instrument.fail_next = True
        with self.assertRaises(MeasurementAbortRequested):
            self.procedure().execute(instrument, None)
        self.assertEqual(instrument.calls[-1][0], 'read_data')

    def test_display_format_and_undefined_fit(self):
        for value, expected in ((10450., '10450'), (132000., '1.3e5'), (99999., '99999'),
                                (100000., '1.0e5'), (math.nan, 'unavailable'), (None, '—')):
            self.assertEqual(format_resistance(value), expected)
        self.assertTrue(math.isnan(fitted_resistance([(-.01, 0., 0), (.001, 0., 0), (.01, 0., 0)])))

    def test_plot_layout_supports_ten_small_panels(self):
        from plotting.viewer import PlotViewer
        plots = self.procedure().plot_definitions()
        spec = PlotViewer._split_span_layout_spec(None, plots, 5, 3)
        self.assertEqual(spec['row_count'], 5)
        self.assertEqual(len(spec['stack_plots']), 10)

    def test_not_discoverable_as_persisted_procedure(self):
        from procedures import load_procedures
        self.assertNotIn('ContactTest', load_procedures())

    def real_runner(self, instrument):
        runner = MeasurementRunner.__new__(MeasurementRunner)
        runner.config = self.runner.config
        runner.plot = self.runner.plot
        runner.log = Mock()
        runner.report_status = Mock()
        runner.stop_event = threading.Event()
        runner.skip_device_event = threading.Event()
        runner.cancel_queue_event = threading.Event()
        runner.prober_motion_inhibited = False
        runner.b1500 = instrument
        runner.get_b1500 = Mock(return_value=instrument)
        runner.prober_ctrl = Mock()
        runner._prepare_for_measurement = Mock(side_effect=AssertionError('Must not prepare device'))
        runner.is_prober_available = Mock(side_effect=AssertionError('Must not query prober'))
        return runner

    def test_runner_never_uses_prober_or_writes_settings(self):
        instrument = Instrument()
        runner = self.real_runner(instrument)
        before = deepcopy(runner.config.data)
        result, path = runner.run_contact_test('ChipA', 'Operator', (1, 2), False, Mock(), 'GPIB0::17::INSTR')
        self.assertEqual(set(result), {'12'})
        self.assertTrue(path.exists())
        self.assertEqual(runner.config.data, before)
        self.assertFalse(runner.prober_motion_inhibited)
        self.assertEqual(runner.prober_ctrl.mock_calls, [])

    def test_abort_and_skip_do_not_move_prober_even_when_guard_changes_during_shutdown(self):
        for method in ('safe_stop', 'safe_skip_device'):
            runner = self.real_runner(Instrument())
            runner.prober_motion_inhibited = True
            runner._stop_instrument = lambda: setattr(runner, 'prober_motion_inhibited', False)
            getattr(runner, method)()
            runner.is_prober_available.assert_not_called()
            self.assertEqual(runner.prober_ctrl.mock_calls, [])

    def test_runner_cancellation_shuts_down_instrument_without_prober(self):
        instrument = Instrument()
        runner = self.real_runner(instrument)
        with self.assertRaises(MeasurementAbortRequested):
            runner.run_contact_test('ChipA', 'Operator', (1, 2), True, Mock(return_value=False), 'GPIB0::17::INSTR')
        self.assertEqual(instrument.calls[-1][0], 'cancel')
        self.assertEqual(runner.prober_ctrl.mock_calls, [])

    def test_abort_preserves_ui_snapshot_after_contact_test_finishes(self):
        runner = self.real_runner(Instrument())
        runner.prober_motion_inhibited = False
        runner.safe_stop(move_prober=False)
        runner.is_prober_available.assert_not_called()
        self.assertEqual(runner.prober_ctrl.mock_calls, [])

    def test_cancelled_queued_lift_prompt_never_opens(self):
        from ui_contact_test import confirm_lift
        ui = SimpleNamespace(root=Mock(), runner=Mock(), _post=Mock())
        ui.runner.check_stop.side_effect = MeasurementAbortRequested('Stopped')
        with patch('ui_contact_test.tk.Toplevel') as dialog:
            with self.assertRaises(MeasurementAbortRequested):
                confirm_lift(ui)
            ui._post.call_args.args[0]()
            dialog.assert_not_called()

    def test_options_reset_and_blank_name_prompts_without_persisting(self):
        from ui_contact_test import ask_options
        ui = SimpleNamespace(root=Mock())
        for _ in range(2):
            buttons = {}

            def button(*args, **kwargs):
                buttons[kwargs['text']] = kwargs['command']
                return Mock()

            ui.root.wait_window.side_effect = lambda _: buttons['Start']()
            with patch('ui_contact_test.tk.Toplevel'), \
                 patch('ui_contact_test.ttk.Frame'), patch('ui_contact_test.ttk.Label'), \
                 patch('ui_contact_test.ttk.Entry'), patch('ui_contact_test.ttk.Checkbutton'), \
                 patch('ui_contact_test.ttk.Button', side_effect=button), \
                 patch('ui_contact_test.tk.StringVar', return_value=Mock(get=lambda: '')), \
                 patch('ui_contact_test.tk.BooleanVar', side_effect=lambda **kw: Mock(get=lambda: kw['value'])) as checks, \
                 patch('ui_contact_test.center_popup'), \
                 patch('ui_contact_test.simpledialog.askstring', return_value=' Operator ') as prompt:
                self.assertEqual(ask_options(ui), ('Operator', (1, 2, 3, 4), True))
                self.assertEqual(checks.call_count, 5)
                self.assertEqual(prompt.call_args.args[1], 'please enter your name:')
