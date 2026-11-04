"""CVSweep and CfSweep against a simulated parallel-RC device on the CMU."""
import cmath
import csv
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from instrumentio.codes import B1500_CH_ALL, B1500_CMUM_Z_TDEG
from instrumentio.sessions import B1500Session
from procedures.cf_sweep import CfSweepProcedure
from procedures.cv_sweep import CVSweepProcedure
from scripts.iv_simulator import MemoryPlot, MemoryRunner

C_DUT, R_DUT = 1e-9, 1e6


def z_theta(freq):
    """|Z| (Ohm) and phase (deg) of R_DUT parallel to C_DUT."""
    z = 1 / (1 / R_DUT + 2j * math.pi * freq * C_DUT)
    return abs(z), math.degrees(cmath.phase(z))


class StreamingPlot(MemoryPlot):
    def append_point(self, name, x, y):
        xs, ys = self.sources.setdefault(name, ([], []))
        xs.append(x)
        ys.append(y)

    def set_progress(self, *args, **kwargs):
        pass


class SimulatedCMU:
    """Records every call; the two streaming sweeps return Z-theta of the RC model."""
    wgfmu = None

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))

    def set_cv(self, channel, mode, start, stop, points, **kwargs):
        self.calls.append(('set_cv', (channel, mode, start, stop, points), kwargs))
        self.cv = start, stop, points

    def set_cmu_freq(self, channel, freq):
        self.calls.append(('set_cmu_freq', (channel, freq), {}))
        self.freq = freq

    def stream_cv_sweep(self, channel, mode, rng, count, callback):
        start, stop, points = self.cv
        for step in range(count):
            bias = start + (stop - start) * step / max(points - 1, 1)
            callback(step, bias, *z_theta(self.freq), 0.1 * step, 0, 0)

    def stream_cf_sweep(self, channel, mode, rng, bias, log_scale, start, stop, points,
                        hold, delay, step_delay, callback):
        self.calls.append(('stream_cf_sweep', (channel, mode, rng, bias, log_scale, start, stop, points), {}))
        for step in range(points):
            t = step / max(points - 1, 1)
            freq = start * (stop / start) ** t if log_scale else start + (stop - start) * t
            freq = float(f"{freq:.6g}")  # FMT5 reports 6 significant digits
            callback(step, freq, *z_theta(freq), bias, 0.1 * step, 0, 0)


def run(cls, settings):
    with tempfile.TemporaryDirectory() as directory:
        runner = MemoryRunner()
        runner.plot = StreamingPlot()
        instrument = SimulatedCMU()
        procedure = cls({'cmu_channel': 7, 'cmu_mode': B1500_CMUM_Z_TDEG, **settings}, directory, '', runner)
        procedure.execute(instrument, SimpleNamespace(name='sample'))
        [path] = Path(directory).glob('*.csv')
        rows = list(csv.DictReader(line for line in path.read_text().splitlines() if not line.startswith('#')))
    return runner, instrument, rows


def panel(runner, plot_id):
    return next(p for p in runner.plots if p.id == plot_id)


class CfSweepTests(unittest.TestCase):
    def test_one_frequency_sweep_per_bias_in_typed_order(self):
        runner, instrument, rows = run(CfSweepProcedure, {
            'biases': '1, -500m, 0', 'start_frequency': '1k', 'stop_frequency': '1M', 'points': 4})
        self.assertEqual([float(r['Bias_V']) for r in rows], [1.0] * 4 + [-0.5] * 4 + [0.0] * 4)
        self.assertEqual([float(r['Frequency_Hz']) for r in rows[:4]], [1e3, 1e4, 1e5, 1e6])
        sweeps = [args for name, args, _ in instrument.calls if name == 'stream_cf_sweep']
        self.assertEqual([args[3] for args in sweeps], [1.0, -0.5, 0.0])
        self.assertTrue(all(args[4] for args in sweeps))
        self.assertEqual(instrument.calls[-2:], [('zero_output', (B1500_CH_ALL,), {}),
                                                 ('set_switch', (B1500_CH_ALL, False), {})])
        self.assertEqual(len(runner.plot.sources['cp_0'][0]), 4)
        self.assertEqual(panel(runner, 'z').xscale, 'log')

    def test_pair_panels_match_the_parallel_rc_and_csv_holds_measured_values(self):
        runner, _, rows = run(CfSweepProcedure, {'start_frequency': '1k', 'stop_frequency': '1M', 'points': 4})
        self.assertEqual(list(rows[0]), ['Bias_V', 'Frequency_Hz', 'Z (Ohm)', 'Theta_deg (deg)', 'Bias_Monitor_V',
                                         'Time_sec', 'Status_Z', 'Status_Theta_deg', 'Status_Combined'])
        self.assertEqual(sorted(p.id for p in runner.plots),
                         sorted(['z', 'theta', 'nyquist', 'rp', 'cp', 'rs', 'cs', 'g', 'b']))
        nyquist_x, nyquist_y = runner.plot.sources['nyquist_0']
        for step, row in enumerate(rows):
            omega = 2 * math.pi * float(row['Frequency_Hz'])
            z = 1 / (1 / R_DUT + 1j * omega * C_DUT)
            self.assertAlmostEqual(nyquist_x[step] / z.real, 1.0)
            self.assertAlmostEqual(nyquist_y[step] / -z.imag, 1.0)
            expected = {'rp': R_DUT, 'cp': C_DUT, 'rs': z.real,
                        'cs': -1 / (omega * z.imag), 'g': 1 / R_DUT, 'b': omega * C_DUT}
            for plot_id, value in expected.items():
                self.assertAlmostEqual(runner.plot.sources[f'{plot_id}_0'][1][step] / value, 1.0, msg=plot_id)

    def test_repeated_bias_gets_its_own_curve(self):
        runner, _, rows = run(CfSweepProcedure, {'biases': '0, 1, 0', 'points': 3})
        self.assertEqual(len(rows), 9)
        for i in range(3):
            self.assertEqual(len(runner.plot.sources[f'z_{i}'][0]), 3)
        self.assertEqual([c.legend_label for c in panel(runner, 'z').elements], ['1: +0V', '2: +1V', '3: +0V'])

    def test_linear_spacing(self):
        runner, instrument, rows = run(CfSweepProcedure, {
            'biases': '0', 'start_frequency': '1M', 'stop_frequency': '2M', 'points': 3, 'spacing': 'linear'})
        self.assertEqual([float(r['Frequency_Hz']) for r in rows], [1e6, 1.5e6, 2e6])
        self.assertEqual(panel(runner, 'z').xscale, 'linear')

    def test_calibration_must_span_the_sweep_range(self):
        calibration = {'7': {kind: {'results_by_frequency': {'10000': {}, '100000': {}}}
                             for kind in ('open', 'short', 'load')} | {'phase': {'result': {'result': 0}}}}
        settings = {'start_frequency': '10k', 'stop_frequency': '100k', 'cmu_calibration': calibration,
                    'require_cmu_calibration': True}
        runner, _, _ = run(CfSweepProcedure, settings)
        self.assertIn('CMU calibration coverage OK on channel 7.', runner.logs)
        with self.assertRaisesRegex(ValueError, 'open: 10kHz–100kHz does not span 1kHz–100kHz'):
            run(CfSweepProcedure, settings | {'start_frequency': '1k'})


class CVSweepTests(unittest.TestCase):
    def test_z_theta_sweep_per_frequency(self):
        _, instrument, rows = run(CVSweepProcedure, {
            'frequencies': '10k, 1M', 'start_bias': -1, 'stop_bias': 1, 'points': 3})
        self.assertEqual([float(r['Frequency_Hz']) for r in rows], [1e4] * 3 + [1e6] * 3)
        self.assertEqual([float(r['Bias_V']) for r in rows[:3]], [-1, 0, 1])
        for row in rows:
            self.assertAlmostEqual(float(row['Cp (F)']) / C_DUT, 1.0)
        self.assertEqual(instrument.calls[-1], ('set_switch', (B1500_CH_ALL, False), {}))


class CfStreamTests(unittest.TestCase):
    def test_commands_and_six_token_records(self):
        session = B1500Session.__new__(B1500Session)
        written, termchars = [], []
        # Two FMT 5,1 records: Time, Para1, Para2, Osc, DCBias, Frequency.
        tokens = iter('NCT+0.00100E+00 NCZ+1.59150E+05 NCY-8.99000E+01 NCV+3.00000E-02 '
                      'NCV+5.00000E-01 NCF+1.00000E+03 NCT+0.00200E+00 NCZ+1.59150E+03 '
                      'XCY-8.99000E+01 NCV+3.00000E-02 NCV+5.00000E-01 NCF+1.00000E+05'.split())
        session._visa_write = written.append
        session._visa_read = lambda _: next(tokens) + ','
        session._visa_set_termchar = lambda char, _: termchars.append(char)
        session._check_instrument_errors = lambda context: written.append('<ERR?>')
        points = []
        B1500Session.stream_cf_sweep.__wrapped__(
            session, 7, B1500_CMUM_Z_TDEG, 0, 0.5, True, 1e3, 1e5, 2, 0.1, 0.0, 0.0,
            lambda *point: points.append(point))
        self.assertEqual(written, ['FMT 5,1\n', 'TSC 1\n', 'LMN 1\n', 'WMFC 1,1\n', 'WTFC 0.1,0,0\n',
                                   'WFC 7,2,1000,100000,2\n', 'MM 22,7\n', f'IMP {B1500_CMUM_Z_TDEG}\n',
                                   'RC 7,0\n', 'DCV 7,0.5\n', '<ERR?>', 'TSR\n', 'XE\n'])
        self.assertEqual(termchars, [44, 10])
        self.assertEqual([p[:5] for p in points], [(0, 1e3, 1.5915e5, -89.9, 0.5), (1, 1e5, 1.5915e3, -89.9, 0.5)])
        self.assertEqual(points[0][6:], (0, 0))
        self.assertNotEqual(points[1][7], 0)  # 'X' status on para2 is reported


if __name__ == '__main__':
    unittest.main()
