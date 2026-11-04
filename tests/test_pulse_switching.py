"""PulseSwitching waveform, combinations and per-combination files, against a fake WGFMU."""
import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from procedures.pulse_switching import PulseSwitchingProcedure
from scripts.iv_simulator import MemoryPlot, MemoryRunner


class Plot(MemoryPlot):
    def append_batch(self, batch):
        for name, points in batch.items():
            self.sources.setdefault(name, []).extend(points)

    def set_progress(self, *args, **kwargs):
        pass


class FakeWGFMU:
    """Plays the channel-1 sequence back as samples: V is the level being forced, I = V / 1 MΩ."""

    def __init__(self):
        self.patterns, self.sequences, self.samples = {}, {}, []

    def __getattr__(self, name):
        return lambda *args, **kwargs: None

    def create_pattern(self, name, initial):
        self.patterns[name] = {'vectors': [], 'events': []}

    def add_vector(self, name, dt, voltage):
        self.patterns[name]['vectors'].append((dt, voltage))

    def set_measure_event(self, name, _label, start, points, interval, _average, _mode):
        self.patterns[name]['events'].append((start, points, interval))

    def add_sequence(self, channel, name, count):
        self.sequences.setdefault(channel, []).append(name)

    def execute(self):
        clock = 0.0
        for name in self.sequences[101]:
            pattern = self.patterns[name]
            ends, t = [], 0.0
            for dt, voltage in pattern['vectors']:
                t += dt
                ends.append((t, voltage))
            for start, points, interval in pattern['events']:
                for k in range(points):
                    t = start + k * interval
                    self.samples.append((clock + t, next(v for end, v in ends if end > t)))
            clock += ends[-1][0]

    def get_status(self):
        return 10000, 0, 0

    def get_measure_value_size(self, channel):
        return len(self.samples), len(self.samples)

    def read_chunk(self, channel, start, count):
        chunk = self.samples[start:start + count]
        return chunk if channel == 101 else [(t, v * 1e-6) for t, v in chunk]


SETTINGS = {'write_voltage': '-3', 'write_width': '1u', 'wait_time': '10u', 'hold_voltage': '0.5',
            'read_voltage': '3', 'read_width': '2u', 'gap': '1u', 'edge_time': 100e-9, 'sample_interval': 50e-9}


class PulseSwitchingTests(unittest.TestCase):
    def test_square_pulses_follow_the_slots(self):
        procedure = PulseSwitchingProcedure(SETTINGS, '', '', MemoryRunner())
        vectors, segments, duration = procedure._build_combination(procedure.combinations[0])
        edge = 100e-9
        expected = [(1e-6, 0.0),
                    (edge, -3), (1e-6, -3), (edge, 0.5), (10e-6, 0.5),  # write, then wait at the hold voltage
                    (edge, 3), (2e-6, 3), (edge, 0.0), (1e-6, 0.0),     # P, then gap at 0 V
                    (edge, 3), (2e-6, 3), (edge, 0.0), (1e-6, 0.0)]     # U, then rest
        self.assertEqual(len(vectors), len(expected))
        for (dt, v), (dt_expected, v_expected) in zip(vectors, expected):
            self.assertAlmostEqual(dt, dt_expected, delta=1e-12)
            self.assertEqual(v, v_expected)
        self.assertAlmostEqual(duration, sum(dt for dt, _ in vectors), delta=1e-12)
        # Each pulse is sampled from its rising edge to the end of its falling edge.
        self.assertAlmostEqual(segments['P'][0], 1e-6 + 1.2e-6 + 10e-6, delta=1e-12)
        self.assertEqual([n for _, n in segments.values()], [24, 44, 44])

    def test_long_waits_are_split_into_pieces_the_wgfmu_accepts(self):
        procedure = PulseSwitchingProcedure({**SETTINGS, 'wait_time': '25k'}, '', '', MemoryRunner())
        vectors, _, _ = procedure._build_combination(procedure.combinations[0])
        self.assertEqual([dt for dt, _ in vectors[4:7]], [1e4, 1e4, 5e3])

    def test_every_combination_is_measured_and_saved_in_its_own_file(self):
        settings = {**SETTINGS, 'wait_time': '1u, 10u, 100u', 'read_voltage': '2, 3'}
        with tempfile.TemporaryDirectory() as directory, patch('procedures.pulse_switching.time.sleep'):
            runner = MemoryRunner()
            runner.plot = Plot()
            procedure = PulseSwitchingProcedure(settings, directory, '', runner)
            wgfmu = FakeWGFMU()
            procedure.execute(SimpleNamespace(wgfmu=wgfmu), SimpleNamespace(name='dev'))

            # One pattern per combination, with a fresh write each; the last field varies fastest.
            self.assertEqual(len(wgfmu.sequences[101]), 6)
            names = sorted(path.stem.split('PulseSwitching_')[1] for path in Path(directory).glob('*.csv'))
            self.assertEqual(names, ['000_twait1u_Vr2', '001_twait1u_Vr3', '002_twait10u_Vr2',
                                     '003_twait10u_Vr3', '004_twait100u_Vr2', '005_twait100u_Vr3'])
            rows = list(csv.DictReader(line for line in
                                       next(Path(directory).glob('*_005_*.csv')).read_text().splitlines()
                                       if not line.startswith('#')))
            self.assertEqual([r['Segment'] for r in rows], ['Write'] * 24 + ['P'] * 44 + ['U'] * 44)
            p_rows = [r for r in rows if r['Segment'] == 'P']
            # Time counts from the rising edge; the flat top is at the read voltage.
            self.assertAlmostEqual(float(p_rows[0]['Time_s']), 0.0, delta=1e-12)
            self.assertEqual(float(p_rows[10]['Voltage_V']), 3.0)
            self.assertEqual(float(rows[10]['Voltage_V']), -3.0)
            # The fake's P and U are identical, so P - U is zero.
            self.assertTrue(all(i == 0 for _, i in runner.plot.sources['PU_5']))
            self.assertEqual(len(runner.plot.saved), 1)

    def test_bad_settings_are_refused(self):
        for bad in ({'wait_time': '1u, -1u'}, {'edge_time': 5e-9}, {'read_voltage': ''}):
            with self.assertRaises(ValueError):
                PulseSwitchingProcedure({**SETTINGS, **bad}, '', '', MemoryRunner())


if __name__ == '__main__':
    unittest.main()
