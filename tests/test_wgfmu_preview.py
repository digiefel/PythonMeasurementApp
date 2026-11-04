"""Waveform preview: patterns recorded from real procedures, drawn one plot each."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from procedures import load_procedures
from procedures.base import WGFMUChannel
from procedures.pulse_switching import PulseSwitchingProcedure
from scripts.iv_simulator import MemoryRunner
import ui_wgfmu_preview
from ui_wgfmu_preview import record_patterns, show_wgfmu_preview

WGFMU_PROCEDURES = {name: cls for name, cls in load_procedures().items()
                    if any(p.kind is WGFMUChannel for p in cls.PARAMETERS)}


class WGFMUPreviewTests(unittest.TestCase):
    def test_every_wgfmu_procedure_records_patterns_with_its_defaults(self):
        self.assertIn('PulseSwitching', WGFMU_PROCEDURES)
        for name, cls in WGFMU_PROCEDURES.items():
            with self.subTest(name):
                patterns = record_patterns(cls, cls.ui_defaults())
                self.assertTrue(patterns)
                for points in patterns.values():
                    times = [t for t, _ in points]
                    self.assertEqual(times, sorted(times))

    def test_points_follow_the_vectors(self):
        settings = {'write_voltage': '-3', 'write_width': '1u', 'wait_time': '10u', 'read_voltage': '3',
                    'read_width': '1u', 'gap': '1u', 'edge_time': 100e-9}
        patterns = record_patterns(PulseSwitchingProcedure, settings)
        pg = next(points for name, points in patterns.items() if name.startswith('PSW_PG'))
        self.assertEqual(pg[0], (0.0, 0.0))
        self.assertAlmostEqual(pg[2][0], 1.1e-6, delta=1e-12)  # 1 µs rest, then the write edge
        self.assertEqual(pg[2][1], -3)
        self.assertEqual(max(v for _, v in pg), 3)

    def test_each_pattern_gets_a_plot_titled_with_its_name(self):
        runner = MemoryRunner()
        ui = SimpleNamespace(proc_var=SimpleNamespace(get=lambda: 'PulseSwitching'), root=None, runner=runner,
                             procedure_classes={'PulseSwitching': PulseSwitchingProcedure},
                             collect_settings=lambda: {'wait_time': '1u, 1m'})
        show_wgfmu_preview(ui)
        self.assertEqual([p.title.split('_')[:2] for p in runner.plots],
                         [['PSW', 'PG'], ['PSW', 'IV'], ['PSW', 'PG'], ['PSW', 'IV']])
        self.assertEqual(len(runner.plot.sources), 4)

    def test_many_patterns_are_capped_and_the_title_says_so(self):
        runner = MemoryRunner()
        ui = SimpleNamespace(proc_var=SimpleNamespace(get=lambda: 'PulseSwitching'), root=None, runner=runner,
                             procedure_classes={'PulseSwitching': PulseSwitchingProcedure},
                             collect_settings=lambda: {'wait_time': ', '.join(['1u'] * 10)})
        show_wgfmu_preview(ui)
        self.assertEqual(len(runner.plots), ui_wgfmu_preview.MAX_PLOTS)
        self.assertIn('first 12 of 20 patterns', runner.title)


if __name__ == '__main__':
    unittest.main()
