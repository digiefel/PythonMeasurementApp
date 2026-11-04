"""Waveform preview: patterns recorded from real procedures, drawn one plot each."""
from types import SimpleNamespace
import unittest

from procedures import load_procedures
from procedures.PUND import PUNDProcedure
from procedures.base import WGFMUChannel
from procedures.pulse_switching import PulseSwitchingProcedure
from scripts.iv_simulator import MemoryRunner
import ui_wgfmu_preview
from ui_wgfmu_preview import record_patterns, show_wgfmu_preview

WGFMU_PROCEDURES = {name: cls for name, cls in load_procedures().items()
                    if any(p.kind is WGFMUChannel for p in cls.PARAMETERS)}


def preview(cls, settings):
    runner = MemoryRunner()
    ui = SimpleNamespace(proc_var=SimpleNamespace(get=lambda: cls.NAME), root=None, runner=runner,
                         procedure_classes={cls.NAME: cls}, collect_settings=lambda: settings)
    show_wgfmu_preview(ui)
    return runner


class WGFMUPreviewTests(unittest.TestCase):
    def test_every_wgfmu_procedure_records_channel_patterns_with_its_defaults(self):
        self.assertIn('PulseSwitching', WGFMU_PROCEDURES)
        for name, cls in WGFMU_PROCEDURES.items():
            with self.subTest(name):
                patterns = record_patterns(cls, cls.ui_defaults())
                self.assertTrue(patterns)
                for pattern in patterns:
                    self.assertIn(pattern.channel, (1, 2))
                    self.assertNotIn('CLEANUP', pattern.name)
                    times = [t for t, _ in pattern.points]
                    self.assertEqual(times, sorted(times))

    def test_points_follow_the_vectors(self):
        settings = {'write_voltage': '-3', 'write_width': '1u', 'wait_time': '10u', 'read_voltage': '3',
                    'read_width': '1u', 'gap': '1u', 'edge_time': 100e-9}
        patterns = record_patterns(PulseSwitchingProcedure, settings)
        pg = next(p.points for p in patterns if p.name.startswith('PSW_PG'))
        self.assertEqual(pg[0], (0.0, 0.0))
        self.assertAlmostEqual(pg[2][0], 1.1e-6, delta=1e-12)  # 1 µs rest, then the write edge
        self.assertEqual(pg[2][1], -3)
        self.assertEqual(max(v for _, v in pg), 3)

    def test_pund_draws_both_channels_in_one_plot_with_dots_on_captured_points(self):
        runner = preview(PUNDProcedure, PUNDProcedure.ui_defaults())
        self.assertEqual([p.title for p in runner.plots], ['PUND'])
        lines = [e for e in runner.plots[0].elements if e.mode == 'line']
        dots = [e for e in runner.plots[0].elements if e.mode == 'scatter']
        self.assertEqual([(e.legend_label, e.color) for e in lines], [('Channel 1', 'C0'), ('Channel 2', 'C1')])
        self.assertEqual([e.color for e in dots], ['C0', 'C1'])
        # PUND captures its whole active pattern, so the dots reach the pulse peaks.
        wave_t, wave_v = runner.plot.sources['wave_0_1']
        dot_t, dot_v = runner.plot.sources['samples_0_1']
        self.assertGreater(len(dot_t), 1000)
        self.assertLessEqual(dot_t[-1], wave_t[-1])
        self.assertAlmostEqual(max(dot_v), max(wave_v))
        self.assertAlmostEqual(min(dot_v), min(wave_v))

    def test_patterns_that_play_together_share_a_plot(self):
        runner = preview(PulseSwitchingProcedure, {'wait_time': '1u, 1m'})
        self.assertEqual([p.title for p in runner.plots], ['PSW_0', 'PSW_1'])
        self.assertEqual(len(runner.plot.sources), 8)  # 2 steps x 2 channels x (line + dots)

    def test_many_steps_are_capped_and_the_title_says_so(self):
        runner = preview(PulseSwitchingProcedure, {'wait_time': ', '.join(['1u'] * 13)})
        self.assertEqual(len(runner.plots), ui_wgfmu_preview.MAX_PLOTS)
        self.assertIn('first 12 of 13 steps', runner.title)

if __name__ == '__main__':
    unittest.main()
