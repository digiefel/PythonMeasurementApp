"""
Pulse Switching Procedure - a write pulse, a wait, then two equal read pulses (P and U).

Each measurement applies these square pulses on WGFMU channel 1:

    Write (Vw for tw) -> Wait (t_wait at V_hold) -> P (Vr for tr) -> Gap (t_gap at 0 V) -> U (Vr for tr)

Write and read voltages have opposite signs. The write sets the polarization. P
switches it, so it carries the switching current plus the charging current. U finds
the polarization already switched and carries the charging current only, so P - U
is the switching current. Channel 2 stays at 0 V and measures the current.

Every field except Edge Time and Sample Interval takes a list, and the run measures
every combination, each with its own write. A list of wait times gives a retention,
imprint or charge-trapping measurement. A list of read voltages gives the switching
current against voltage. The last field in the form varies fastest.

A width is the time at full voltage. Every voltage change takes one Edge Time on
top of it. Wait and Gap run from the end of one edge to the start of the next.

Each combination is saved as its own CSV, numbered in run order and named after the
value of every field that has more than one, e.g. ``<base>_003_twait100u.csv``. Its
rows are the Write, P and U samples, each from one Baseline before its rising edge to
one Baseline after its falling edge. The baseline samples show the offset of the
voltage and current at rest. Time_s counts from the start of the rising edge, so
samples before it have negative times.
"""
import itertools
import time

import numpy as np

from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, ValueList, WGFMUChannel, parameter
from procedures.pund_fatigue import PUNDFatigueProcedure
from instrumentio.codes import WGFMU_MEASURE_EVENT_DATA_AVERAGED
from instrumentio.constants import WGFMU_MEASURE_CURRENT_RANGES, WGFMU_MEASURE_VOLTAGE_RANGES
from si_utils import format_si_compact, parse_si_list

RESOLUTION = 1e-8  # WGFMU timing resolution and shortest sample interval
# The WGFMU caps one vector at about 10995 s, so longer waits are split into pieces.
MAX_VECTOR_S = 1e4
# 0 V before each write and after each U, so every combination starts and ends at rest.
REST_S = 1e-6
# The WGFMU inserts 50 ns between consecutive sequences on a channel (WGFMU guide, WGFMU_addSequence).
SEQUENCE_DELAY_S = 50e-9
STATUS_COMPLETED = 10000
SEGMENTS = ("Write", "P", "U")
HEADERS = ["Segment", "Time_s", "Voltage_V", "Current_A"]
# Swept fields in form order, with the short name used in file names and legends.
SWEPT = (
    ('write_voltage', 'Vw'), ('write_width', 'tw'), ('wait_time', 'twait'), ('hold_voltage', 'Vhold'),
    ('read_voltage', 'Vr'), ('read_width', 'tr'), ('gap', 'tgap'),
)
TIME_FIELDS = ('write_width', 'wait_time', 'read_width', 'gap')


class PulseSwitchingProcedure(MeasurementProcedure):
    NAME = "PulseSwitching"
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('channel_1', 'WGFMU Channel 1 (PG Vmeas)', 101, WGFMUChannel),
        parameter('channel_2', 'WGFMU Channel 2 (FastIV Imeas)', 102, WGFMUChannel),
        parameter('write_voltage', 'Write Voltage (V)', '-3', ValueList,
                  help="Sets the polarization before each measurement. Opposite in sign to the read voltage."),
        parameter('write_width', 'Write Width (s)', '1u', ValueList),
        parameter('wait_time', 'Wait Time (s)', '1u, 10u, 100u, 1m', ValueList,
                  help="Time between the write and P. A log-spaced list gives a retention measurement."),
        parameter('hold_voltage', 'Hold Voltage During Wait (V)', '0', ValueList,
                  help="Voltage held during the wait. Not 0 for imprint or charge-trapping studies."),
        parameter('read_voltage', 'Read Voltage (V)', '3', ValueList,
                  help="Amplitude of both reads, P and U."),
        parameter('read_width', 'Read Width (s)', '1u', ValueList),
        parameter('gap', 'Gap Between P and U (s)', '1u', ValueList),
        parameter('edge_time', 'Edge Time (s)', 70e-9, float,
                  help="Rise and fall time of every pulse. At least 10 ns; around 70 ns limits overshoot."),
        parameter('sample_interval', 'Sample Interval (s)', 10e-9, float,
                  help="Time between samples during the write, P and U. At least 10 ns."),
        parameter('baseline', 'Baseline (s)', 200e-9, float,
                  help="Time also sampled before and after every pulse, to read the offset at rest. "
                       "At most half the shortest Wait Time and Gap."),
        parameter('meas_range_1', 'Meas Range Ch1 (V)', WGFMU_MEASURE_VOLTAGE_RANGES[0][0],
                  Choice(WGFMU_MEASURE_VOLTAGE_RANGES, int)),
        parameter('meas_range_2', 'Meas Range Ch2 (I)', WGFMU_MEASURE_CURRENT_RANGES[-1][0],
                  Choice(WGFMU_MEASURE_CURRENT_RANGES, int)),
    )

    def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
        super().__init__(settings, output_root, output_relative, runner, fallback_root)
        labels = {p.key: p.label for p in self.PARAMETERS}
        lists = {}
        for key, _ in SWEPT:
            values = parse_si_list(str(getattr(self, key)))
            if not values:
                raise ValueError(f"{labels[key]} needs at least one value")
            if key in TIME_FIELDS:
                if min(values) < 0:
                    raise ValueError(f"{labels[key]} must not be negative")
                # Times run on the 10 ns grid of the WGFMU.
                values = [round(v / RESOLUTION) * RESOLUTION for v in values]
            lists[key] = values
        if self.edge_time < RESOLUTION or self.sample_interval < RESOLUTION:
            raise ValueError("Edge Time and Sample Interval must be at least 10 ns")
        self.edge = round(self.edge_time / RESOLUTION) * RESOLUTION
        self.interval = round(self.sample_interval / RESOLUTION) * RESOLUTION
        self.baseline_s = round(self.baseline / RESOLUTION) * RESOLUTION
        # Measurement windows must not overlap: the WGFMU would overwrite the earlier one.
        if self.baseline_s < 0 or 2 * self.baseline_s > min(lists['wait_time'] + lists['gap']):
            raise ValueError("Baseline must be between 0 and half the shortest Wait Time and Gap")
        self.rest = max(REST_S, self.baseline_s)
        self.combinations = [dict(zip(lists, values)) for values in itertools.product(*lists.values())]
        self.swept = [(key, tag) for key, tag in SWEPT if len(lists[key]) > 1]

    def _build_combination(self, c):
        """Channel-1 vectors of one combination, plus each pulse's (rising edge start, sample count)."""
        edge = self.edge
        vectors, segments, t = [(self.rest, 0.0)], {}, self.rest
        for name, level, width, after, rest in (
            ('Write', c['write_voltage'], c['write_width'], c['hold_voltage'], c['wait_time']),
            ('P', c['read_voltage'], c['read_width'], 0.0, c['gap']),
            ('U', c['read_voltage'], c['read_width'], 0.0, self.rest),
        ):
            # Rising edge, flat top, falling edge to the level that follows; all three are sampled,
            # plus one baseline on either side.
            window = 2 * edge + width
            segments[name] = (t, max(1, round((window + 2 * self.baseline_s) / self.interval)))
            vectors += [(edge, level), (width, level), (edge, after)]
            for piece_start in np.arange(0.0, rest, MAX_VECTOR_S):
                vectors.append((min(MAX_VECTOR_S, rest - piece_start), after))
            t += window + rest
        return vectors, segments, t

    def _label(self, c):
        return ", ".join(f"{tag}={format_si_compact(c[key], 4)}" for key, tag in self.swept)

    def measure(self, device):
        b1500 = self.b1500
        wgfmu = b1500.wgfmu
        self.check_stop(b1500)

        built = [self._build_combination(c) for c in self.combinations]
        pattern_starts = np.cumsum([0.0] + [duration + SEQUENCE_DELAY_S for _, _, duration in built])
        sample_ends = np.cumsum([sum(n for _, n in segments.values()) for _, segments, _ in built])
        expected_total = int(sample_ends[-1])

        reads, switching = [], []
        for index, c in enumerate(self.combinations):
            color = f'C{index % 10}'
            # Legend entries for the first and last combination only, so long sweeps stay readable.
            legend = index in (0, len(self.combinations) - 1) and bool(self.swept)
            reads += [Curve(f"P_{index}", color=color, legend_label=self._label(c), show_in_legend=legend),
                      Curve(f"U_{index}", color=color, line_style="dash", show_in_legend=False)]
            switching.append(Curve(f"PU_{index}", color=color, legend_label=self._label(c), show_in_legend=legend))
        self.runner.configure_plot(f'Pulse Switching - {device.name}', [
            PlotDef("reads", row=0, col=0, title="P (solid) and U (dashed)",
                    xlabel="Time from rising edge (µs)", ylabels=("Current (mA)",), elements=reads),
            PlotDef("switching", row=0, col=1, title="P − U",
                    xlabel="Time from rising edge (µs)", ylabels=("Current (mA)",), elements=switching),
        ])
        self.report_progress(0, len(built), "Combinations measured")
        self.log(f"Starting Pulse Switching on {device.name}: {len(built)} combinations, "
                 f"{expected_total} samples, about {format_si_compact(pattern_starts[-1], 3)}s of pulses")

        ts = self.get_run_timestamp()
        base = self.format_filename("PulseSwitching", device.name)
        try:
            PUNDFatigueProcedure._configure_wgfmu(self, wgfmu)
            for index, (vectors, segments, _) in enumerate(built):
                for channel, name, levels in (
                    (self.channel_1, f"PSW_PG_{index}_{ts}", [v for _, v in vectors]),
                    # Channel 2 stays at 0 V and only measures current.
                    (self.channel_2, f"PSW_IV_{index}_{ts}", [0.0] * len(vectors)),
                ):
                    wgfmu.create_pattern(name, 0.0)
                    for (dt, _), level in zip(vectors, levels):
                        if dt > 0:
                            wgfmu.add_vector(name, dt, level)
                    for segment, (start, points) in segments.items():
                        wgfmu.set_measure_event(name, segment, start - self.baseline_s, points,
                                                self.interval, self.interval,
                                                WGFMU_MEASURE_EVENT_DATA_AVERAGED)
                    wgfmu.add_sequence(channel, name, 1.0)

            self.check_stop(b1500)
            wgfmu.execute()

            samples_v, samples_i = [], []  # every sample of the run, in order
            done = 0  # combinations already plotted and saved
            while True:
                self.check_stop(b1500)
                status, _, _ = wgfmu.get_status()
                measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
                measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
                available = min(measured_1, measured_2, expected_total)
                if available > len(samples_v):
                    start = len(samples_v)
                    samples_v += wgfmu.read_chunk(self.channel_1, start, available - start)
                    samples_i += wgfmu.read_chunk(self.channel_2, start, available - start)

                # Plot and save every combination that is now complete.
                while done < len(built) and sample_ends[done] <= len(samples_v):
                    _, segments, _ = built[done]
                    rows, currents = [], {}
                    first = int(sample_ends[done]) - sum(n for _, n in segments.values())
                    for segment, (segment_start, points) in segments.items():
                        span = slice(first, first + points)
                        first += points
                        t0 = pattern_starts[done] + segment_start
                        rows += [[segment, t - t0, v, cur] for (t, v), (_, cur) in zip(samples_v[span], samples_i[span])]
                        currents[segment] = np.array([cur for _, cur in samples_i[span]])
                    tags = "".join(f"_{tag}{format_si_compact(self.combinations[done][key], 4)}" for key, tag in self.swept)
                    self.save_data(rows, f"{base}_{done:03d}{tags}.csv", HEADERS, add_timestamp=False)

                    t_us = (np.arange(len(currents['P'])) * self.interval - self.baseline_s) * 1e6
                    self.runner.plot.append_batch({
                        f"P_{done}": list(zip(t_us, currents['P'] * 1e3)),
                        f"U_{done}": list(zip(t_us, currents['U'] * 1e3)),
                        f"PU_{done}": list(zip(t_us, (currents['P'] - currents['U']) * 1e3)),
                    })
                    # TODO: analysis of the pulse-switching method: fit I(t) = I0 exp(-t / tau) to P - U,
                    #  then I0 against Vr gives R_L and Vc, C_i = tau / R_L, and the integral of P - U
                    #  checks against 2 Pr A.
                    done += 1
                    self.report_progress(done, len(built), "Combinations measured")

                # Status was read before fetching, so a completed run has no samples left to read.
                if status == STATUS_COMPLETED:
                    break
                time.sleep(0.05)

            if done:
                self.save_plot_png(f"{base}_plot.png")
            if done < len(built):
                self.log(f"Warning: only {done} of {len(built)} combinations were measured "
                         f"({len(samples_v)}/{expected_total} samples).")
            self.log(f"Pulse Switching complete: {done} combinations saved as separate files")
        finally:
            try:
                wgfmu.clear()
                wgfmu.disconnect(self.channel_1)
                wgfmu.disconnect(self.channel_2)
            except Exception:
                pass
