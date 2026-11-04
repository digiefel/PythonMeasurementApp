"""FORCFatigue run order and per-read files, against a fake WGFMU."""
import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from procedures.forc_fatigue import FORCFatigueProcedure
from scripts.iv_simulator import MemoryPlot, MemoryRunner


class Plot(MemoryPlot):
    def append_batch(self, batch):
        for name, points in batch.items():
            self.sources.setdefault(name, []).extend(points)

    def set_progress(self, *args, **kwargs):
        pass


class FakeWGFMU:
    """Plays the sequences back as samples: V is the channel-1 level, I = V / 1 MΩ.

    Samples become available a few thousand at a time, so reads complete across polls.
    """
    CHUNK = 3000

    def __init__(self):
        self.patterns, self.sequences = {}, {}
        self.samples, self.released = [], 0

    def __getattr__(self, name):
        return lambda *args, **kwargs: None

    def create_pattern(self, name, initial):
        self.patterns[name] = {'vectors': [], 'measure': None}

    def add_vector(self, name, dt, voltage):
        self.patterns[name]['vectors'].append((dt, voltage))

    def set_measure_event(self, name, _label, start, points, interval, _average, _mode):
        self.patterns[name]['measure'] = (start, points, interval)

    def add_sequence(self, channel, name, count):
        self.sequences.setdefault(channel, []).append((name, count))

    def execute(self):
        clock = 0.0
        for name, count in self.sequences[min(self.sequences)]:
            pattern = self.patterns[name]
            if pattern['measure']:
                start, points, interval = pattern['measure']
                ends, t = [], 0.0
                for dt, voltage in pattern['vectors']:
                    t += dt
                    ends.append((t, voltage))
                for k in range(points):
                    t = start + k * interval
                    self.samples.append((clock + t, next((v for end, v in ends if end >= t), ends[-1][1])))
            clock += count * sum(dt for dt, _ in pattern['vectors'])

    def get_status(self):
        self.released = min(self.released + self.CHUNK, len(self.samples))
        return (10000 if self.released == len(self.samples) else 10001), 0, 0

    def get_measure_value_size(self, channel):
        return self.released, len(self.samples)

    def read_chunk(self, channel, start, count):
        chunk = self.samples[start:start + count]
        return chunk if channel == 101 else [(t, v * 1e-6) for t, v in chunk]


class FORCFatigueTests(unittest.TestCase):
    def test_reads_run_in_cycle_order_and_each_gets_its_own_file(self):
        settings = {'fatigue_count': 1e4, 'reads_per_decade': 2, 'forc_cycles': '100, 1e4', 'forc_count': 4}
        with tempfile.TemporaryDirectory() as directory, patch('procedures.forc_fatigue.time.sleep'):
            runner = MemoryRunner()
            runner.plot = Plot()
            procedure = FORCFatigueProcedure(settings, directory, '', runner)
            wgfmu = FakeWGFMU()
            procedure.execute(SimpleNamespace(wgfmu=wgfmu), SimpleNamespace(name='dev'))

            order = [name.split('_')[1] for name, _ in wgfmu.sequences[101]]
            self.assertEqual(order[:4], ['FORC', 'PUND', 'FAT', 'PUND'])  # pristine FORC, then PUND
            files = sorted(Path(directory).glob('*.csv'))
            suffixes = sorted(path.stem.split('FORC_Fatigue_')[1] for path in files)
            self.assertEqual(suffixes, sorted(['c0_FORC', 'c0_PUND', 'c1_PUND', 'c5_PUND', 'c10_PUND', 'c50_PUND',
                                               'c100_FORC', 'c100_PUND', 'c500_PUND', 'c1000_PUND', 'c5000_PUND',
                                               'c10000_FORC', 'c10000_PUND']))
            sample_count = 0
            for path in files:
                rows = list(csv.DictReader(line for line in path.read_text().splitlines() if not line.startswith('#')))
                self.assertEqual({row['Cycle'] for row in rows}, {path.stem.split('_c')[-1].split('_')[0]})
                sample_count += len(rows)
            self.assertEqual(sample_count, len(wgfmu.samples))
            self.assertEqual(len(runner.plot.saved), 1)

    def test_forc_cycles_beyond_the_fatigue_count_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            FORCFatigueProcedure({'fatigue_count': 1e3, 'forc_cycles': '100, 1e4'}, '', '', MemoryRunner())


if __name__ == '__main__':
    unittest.main()
