"""
PUND Wakeup Procedure - repeated fatigue bursts with one read trace per Vmax.

For each Vmax value, the WGFMU applies repeated square fatigue cycles on the
PG channel, then measures a read waveform at the same amplitude. The FastIV
channel always stays at 0 V and only measures current.
"""
import time

import numpy as np

from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, WGFMUChannel, parameter
from instrumentio.codes import (
    WGFMU_FORCE_VOLTAGE_RANGE_AUTO,
    WGFMU_MEASURE_ENABLED_ENABLE,
    WGFMU_MEASURE_EVENT_DATA_AVERAGED,
    WGFMU_MEASURE_MODE_CURRENT,
    WGFMU_MEASURE_MODE_VOLTAGE,
    WGFMU_OPERATION_MODE_FASTIV,
    WGFMU_OPERATION_MODE_PG,
)
from instrumentio.constants import (
    WGFMU_MEASURE_CURRENT_RANGES,
    WGFMU_MEASURE_VOLTAGE_RANGES,
)
from si_utils import parse_si_list


class PUNDWakeUpProcedure(MeasurementProcedure):
    NAME = "PUNDWakeUp"
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('channel_1', 'WGFMU Channel 1 (PG Vmeas)', 101, WGFMUChannel),
        parameter('channel_2', 'WGFMU Channel 2 (FastIV Imeas)', 102, WGFMUChannel),
        parameter('vmax', 'List of Vmax values (V)', "1.0, 1.5, 2.0", str),
        parameter('base_voltage', 'Base Voltage (V)', 0.0, float), # baseline voltage: V = V_base +- V_max
        parameter('hold_base', 'Hold Base V continuously', True, bool), # hold baseline for the entire time?
        parameter('fatigue_freq', 'Fatigue Frequency (Hz)', 1e3, float), # inverse duration of the fatigue pulses
        parameter('fatigue_delay', 'Fatigue Cycle Delay (s)', 0.0, float), # wait time between fatigue pulses
        parameter('fatigue_count', 'Fatigue Cycle Count', 1e3, float), # fatigue pulse count per value of Vmax
        parameter('read_pulse_freq', 'Read Frequency (Hz)', 1e4, float), # inverse duration of the read pulses
        parameter('read_pulse_type', 'Shape of Read Pulse', 'pund', 
                  Choice((('pund', 'PUND'), ('pn', 'PN'), ('both', 'PN+PUND')))),
        parameter('meas_range_1', 'Meas Range Ch1 (V)', WGFMU_MEASURE_VOLTAGE_RANGES[0][0], 
                  Choice(WGFMU_MEASURE_VOLTAGE_RANGES, int)),
        parameter('meas_range_2', 'Meas Range Ch2 (I)', WGFMU_MEASURE_CURRENT_RANGES[0][0], 
                  Choice(WGFMU_MEASURE_CURRENT_RANGES, int)),
    )

    MIN_INTERVAL = 1e-8
    RESOLUTION = 1e-8
    STATUS_COMPLETED = 10000
    POST_COMPLETION_DRAIN_TIMEOUT_S = 30.0

    def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
        super().__init__(settings, output_root, output_relative, runner, fallback_root)
        self.vmax_values = self._parse_vmax_values(self.vmax)
        self.fatigue_count_int = int(float(self.fatigue_count))
        self._validate_settings()

    @staticmethod
    def _parse_vmax_values(raw_value):
        values = parse_si_list(str(raw_value))
        if not values:
            raise ValueError("At least one Vmax value is required.")
        if any(v == 0.0 for v in values):
            raise ValueError("Vmax values must be non-zero. Use negative values to invert polarity.")
        return values

    def _validate_settings(self):
        if self.fatigue_freq <= 0:
            raise ValueError("fatigue_freq must be > 0")
        if self.read_pulse_freq <= 0:
            raise ValueError("read_pulse_freq must be > 0")
        if self.fatigue_delay < 0:
            raise ValueError("fatigue_delay must be >= 0")
        if self.fatigue_count_int < 0:
            raise ValueError("fatigue_count must be >= 0")
        if self.read_pulse_type not in ('pund', 'pn', 'both'):
            raise ValueError(f"Invalid read_pulse_type: {self.read_pulse_type!r}")

    def _idle_voltage(self):
        return self.base_voltage if self.hold_base else 0.0

    def _positive_level(self, vmax):
        return self.base_voltage + vmax

    def _negative_level(self, vmax):
        return self.base_voltage - vmax

    def _append_square_level(self, vectors, level, duration):
        """Append an approximately-square segment ending at level for duration seconds."""
        if duration <= 0:
            return
        edge = min(self.MIN_INTERVAL, duration)
        vectors.append((edge, level))
        hold = duration - edge
        if hold > 0:
            vectors.append((hold, level))

    def _append_idle_hold(self, vectors, duration):
        if duration <= 0:
            return
        self._append_square_level(vectors, self._idle_voltage(), duration)

    def _build_fatigue_vectors(self, vmax):
        """Square fatigue cycle: +Vmax segment, -Vmax segment, optional idle delay."""
        segment = 1.0 / self.fatigue_freq
        vectors = []
        self._append_square_level(vectors, self._positive_level(vmax), segment)
        self._append_square_level(vectors, self._negative_level(vmax), segment)
        self._append_idle_hold(vectors, self.fatigue_delay)
        return vectors

    def _build_pn_vectors(self, vmax):
        """Seamless triangular PN read pulse with total ramp duration 2/read_pulse_freq."""
        idle = self._idle_voltage()
        ramp = (2.0 / self.read_pulse_freq) / 3.0
        return [
            (ramp, self._positive_level(vmax)),
            (ramp, self._negative_level(vmax)),
            (ramp, idle),
        ]

    def _build_pund_vectors(self, vmax):
        """Four square read pulses: P, U, N, D with base holds between pulses."""
        pulse = 1.0 / self.read_pulse_freq
        between = self.base_voltage
        idle = self._idle_voltage()
        vectors = []
        for idx, level in enumerate((
            self._positive_level(vmax),
            self._positive_level(vmax),
            self._negative_level(vmax),
            self._negative_level(vmax),
        )):
            self._append_square_level(vectors, level, pulse)
            # Between PUND pulses, hold the base level even when the rest of the sequence idles at 0 V.
            if idx < 3:
                self._append_square_level(vectors, between, pulse)
            else:
                vectors.append((self.MIN_INTERVAL, idle))
        return vectors

    def _build_read_vectors(self, vmax):
        if self.read_pulse_type == 'pn':
            return self._build_pn_vectors(vmax)
        if self.read_pulse_type == 'pund':
            return self._build_pund_vectors(vmax)

        vectors = []
        vectors.extend(self._build_pn_vectors(vmax))
        self._append_idle_hold(vectors, 1.0 / self.read_pulse_freq)
        vectors.extend(self._build_pund_vectors(vmax))
        return vectors

    def _read_phase_spans(self, vmax):
        """Return plotted read phases as (key, label, start_s, end_s)."""
        pn_duration = sum(dt for dt, _ in self._build_pn_vectors(vmax))
        pund_duration = sum(dt for dt, _ in self._build_pund_vectors(vmax))

        if self.read_pulse_type == 'pn':
            return [('pn', 'PN', 0.0, pn_duration)]
        if self.read_pulse_type == 'pund':
            return [('pund', 'PUND', 0.0, pund_duration)]

        gap_duration = 1.0 / self.read_pulse_freq
        pund_start = pn_duration + gap_duration
        return [
            ('pn', 'PN', 0.0, pn_duration),
            ('pund', 'PUND', pund_start, pund_start + pund_duration),
        ]

    @staticmethod
    def _phase_for_time(rel_t, phase_spans):
        for phase in phase_spans:
            _key, _label, start, end = phase
            if start <= rel_t < end:
                return phase
        if phase_spans and rel_t == phase_spans[-1][3]:
            return phase_spans[-1]
        return None

    @staticmethod
    def _phase_color(phase_key, intensity):
        shade = 0.45 + 0.55 * intensity
        if phase_key == 'pn':
            return (0.12 * shade, 0.47 * shade, 0.71 * shade)
        return (1.0 * shade, 0.5 * shade, 0.05 * shade)

    def _iv_vectors_for(self, vectors):
        # Channel 2 must never receive PG voltage; it mirrors timing only and always targets 0 V.
        return [(dt, 0.0) for dt, _ in vectors]

    def _sample_interval(self):
        raw_interval = 1e-3 / self.read_pulse_freq
        sample_interval = max(raw_interval, self.MIN_INTERVAL)
        sample_interval = round(sample_interval / self.RESOLUTION) * self.RESOLUTION
        return max(sample_interval, self.MIN_INTERVAL)

    def _configure_wgfmu(self, wgfmu):
        wgfmu.clear()
        wgfmu.connect(self.channel_1)
        wgfmu.connect(self.channel_2)

        wgfmu.set_operation_mode(self.channel_1, WGFMU_OPERATION_MODE_PG)
        wgfmu.set_operation_mode(self.channel_2, WGFMU_OPERATION_MODE_FASTIV)
        wgfmu.set_force_voltage_range(self.channel_1, WGFMU_FORCE_VOLTAGE_RANGE_AUTO)
        wgfmu.set_force_voltage_range(self.channel_2, WGFMU_FORCE_VOLTAGE_RANGE_AUTO)

        wgfmu.set_measure_mode(self.channel_1, WGFMU_MEASURE_MODE_VOLTAGE)
        wgfmu.set_measure_mode(self.channel_2, WGFMU_MEASURE_MODE_CURRENT)
        wgfmu.set_measure_voltage_range(self.channel_1, self.meas_range_1)
        wgfmu.set_measure_current_range(self.channel_2, self.meas_range_2)
        wgfmu.set_measure_enabled(self.channel_1, WGFMU_MEASURE_ENABLED_ENABLE)
        wgfmu.set_measure_enabled(self.channel_2, WGFMU_MEASURE_ENABLED_ENABLE)

    @staticmethod
    def _add_vectors(wgfmu, pattern_name, vectors):
        for dt, voltage in vectors:
            if dt > 0:
                wgfmu.add_vector(pattern_name, dt, voltage)

    def _create_pattern_pair(self, wgfmu, pg_name, iv_name, initial_pg, pg_vectors, measure_points=None, sample_interval=None):
        wgfmu.create_pattern(pg_name, initial_pg)
        self._add_vectors(wgfmu, pg_name, pg_vectors)

        wgfmu.create_pattern(iv_name, 0.0)
        self._add_vectors(wgfmu, iv_name, self._iv_vectors_for(pg_vectors))

        if measure_points is not None and sample_interval is not None:
            wgfmu.set_measure_event(
                pg_name,
                "meas",
                0.0,
                measure_points,
                sample_interval,
                sample_interval,
                WGFMU_MEASURE_EVENT_DATA_AVERAGED,
            )
            wgfmu.set_measure_event(
                iv_name,
                "meas",
                0.0,
                measure_points,
                sample_interval,
                sample_interval,
                WGFMU_MEASURE_EVENT_DATA_AVERAGED,
            )

    def _plot_sources(self, index, phase_key):
        return (
            f"V_{index}_{phase_key}",
            f"I_{index}_{phase_key}",
            f"IV_{index}_{phase_key}",
            f"QV_{index}_{phase_key}",
        )

    def _configure_plot(self, device, read_duration):
        elements = []
        iv_elements = []
        qv_elements = []
        source_map = {}
        max_abs_v = max(abs(v) for v in self.vmax_values)

        for idx, vmax in enumerate(self.vmax_values):
            frac = 0.2 + 0.7 * (idx / max(1, len(self.vmax_values) - 1))
            show = True
            label = f"Vmax {vmax:g} V"
            source_map[idx] = {}
            for phase_key, phase_label, _start, _end in self._read_phase_spans(vmax):
                color = self._phase_color(phase_key, frac)
                v_source, i_source, iv_source, qv_source = self._plot_sources(idx, phase_key)
                series_label = f"{phase_label} {label}"
                elements.append(Curve(v_source, color=color, yaxis=0,
                                      legend_label=f"V ({series_label})", show_in_legend=show))
                elements.append(Curve(i_source, color=color, yaxis=1,
                                      legend_label=f"I ({series_label})", show_in_legend=show))
                iv_elements.append(Curve(iv_source, color=color,
                                         legend_label=series_label, show_in_legend=show))
                qv_elements.append(Curve(qv_source, color=color,
                                         legend_label=series_label, show_in_legend=show))
                source_map[idx][phase_key] = (v_source, i_source, iv_source, qv_source)

        v_margin = max(max_abs_v * 0.1, 0.1)
        y_min = min(0.0, self.base_voltage - max_abs_v) - v_margin
        y_max = max(0.0, self.base_voltage + max_abs_v) + v_margin

        self.runner.configure_plot(f'PUND Wakeup Overlay - {device.name}', [
            PlotDef("pund_wakeup", row=0, col=0, colspan=2,
                    xlabel="Time (s)",
                    ylabels=("Voltage (V)", "Current (uA)"),
                    xlim=(0, read_duration),
                    ylims=((y_min, y_max), None),
                    elements=elements),
            PlotDef("iv_loop", row=1, col=0,
                    xlabel="Voltage (V)",
                    ylabels=("Current (uA)",),
                    elements=iv_elements),
            PlotDef("qv_loop", row=1, col=1,
                    xlabel="Voltage (V)",
                    ylabels=("Charge (nC)",),
                    elements=qv_elements),
        ], row_ratios=[2.0, 1.0])

        return source_map

    def measure(self, device):
        b1500 = self.b1500
        wgfmu = b1500.wgfmu
        self.check_stop(b1500)

        sample_interval = self._sample_interval()
        read_vectors_by_vmax = [self._build_read_vectors(vmax) for vmax in self.vmax_values]
        phase_spans_by_vmax = [self._read_phase_spans(vmax) for vmax in self.vmax_values]
        read_durations = [sum(dt for dt, _ in vectors) for vectors in read_vectors_by_vmax]
        max_read_duration = max(read_durations)
        sample_points = max(1, int(max_read_duration / sample_interval))
        expected_total = sample_points * len(self.vmax_values)
        source_map = self._configure_plot(device, max_read_duration)

        fatigue_period = (2.0 / self.fatigue_freq) + self.fatigue_delay
        total_time = sum((self.fatigue_count_int * fatigue_period) + duration for duration in read_durations)
        self.log(f"Starting PUND Wakeup on {device.name}")
        self.log(
            f"  Vmax values: {', '.join(f'{v:g} V' for v in self.vmax_values)}; "
            f"fatigue cycles per value: {self.fatigue_count_int}"
        )
        self.log(
            f"  Fatigue period: {fatigue_period:.6g} s, read sample interval: {sample_interval:.9g} s, "
            f"read points per value: {sample_points}"
        )
        self.log(f"  Estimated waveform duration: {total_time:.1f} s")

        ts = self.get_run_timestamp()
        initial_pg = self._idle_voltage()

        try:
            self._configure_wgfmu(wgfmu)

            for idx, (vmax, read_vectors) in enumerate(zip(self.vmax_values, read_vectors_by_vmax)):
                self.check_stop(b1500)

                fat_pg = f"WAKE_FAT_PG_{ts}_{idx}"
                fat_iv = f"WAKE_FAT_IV_{ts}_{idx}"
                read_pg = f"WAKE_READ_PG_{ts}_{idx}"
                read_iv = f"WAKE_READ_IV_{ts}_{idx}"
                fatigue_vectors = self._build_fatigue_vectors(vmax)

                self._create_pattern_pair(wgfmu, fat_pg, fat_iv, initial_pg, fatigue_vectors)
                self._create_pattern_pair(
                    wgfmu,
                    read_pg,
                    read_iv,
                    initial_pg,
                    read_vectors,
                    measure_points=sample_points,
                    sample_interval=sample_interval,
                )

                if self.fatigue_count_int > 0:
                    wgfmu.add_sequence(self.channel_1, fat_pg, float(self.fatigue_count_int))
                    wgfmu.add_sequence(self.channel_2, fat_iv, float(self.fatigue_count_int))
                wgfmu.add_sequence(self.channel_1, read_pg, 1.0)
                wgfmu.add_sequence(self.channel_2, read_iv, 1.0)

            cleanup_pg = f"WAKE_CLEANUP_PG_{ts}"
            cleanup_iv = f"WAKE_CLEANUP_IV_{ts}"
            self._create_pattern_pair(
                wgfmu,
                cleanup_pg,
                cleanup_iv,
                initial_pg,
                [(1e-4, 0.0)],
            )
            wgfmu.add_sequence(self.channel_1, cleanup_pg, 1.0)
            wgfmu.add_sequence(self.channel_2, cleanup_iv, 1.0)

            self.check_stop(b1500)
            wgfmu.execute()

            plotted_count = 0
            data_ch1 = []
            data_ch2 = []
            i_baseline_samples: dict[int, list] = {}
            i_baseline: dict[int, float] = {}
            q_accum: dict[tuple[int, str], float] = {}
            last_t_per_phase: dict[tuple[int, str], float] = {}
            last_progress_time = time.monotonic()

            while True:
                self.check_stop(b1500)
                status, _elapsed, _total = wgfmu.get_status()
                measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
                measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
                available = min(measured_1, measured_2, expected_total)

                if available > plotted_count:
                    batches: dict[tuple[int, str], dict] = {}

                    for sample_index in range(plotted_count, available):
                        self.check_stop(b1500)
                        t_v, voltage = wgfmu.get_measure_value(self.channel_1, sample_index)
                        t_i, current = wgfmu.get_measure_value(self.channel_2, sample_index)
                        data_ch1.append((t_v, voltage))
                        data_ch2.append((t_i, current))

                        read_idx = sample_index // sample_points
                        sample_in_read = sample_index % sample_points
                        if read_idx >= len(self.vmax_values):
                            continue

                        rel_t = sample_in_read * sample_interval
                        phase = self._phase_for_time(rel_t, phase_spans_by_vmax[read_idx])
                        if phase is None:
                            continue
                        phase_key, _phase_label, _start, _end = phase
                        if phase_key not in source_map[read_idx]:
                            continue

                        batch_key = (read_idx, phase_key)
                        batch = batches.setdefault(batch_key, {'v': [], 'i': [], 'iv': [], 'qv': []})
                        batch['v'].append((rel_t, voltage))
                        batch['i'].append((rel_t, current * 1e6))

                        if read_idx not in i_baseline:
                            samples = i_baseline_samples.setdefault(read_idx, [])
                            if len(samples) < 50:
                                samples.append(current)
                            if len(samples) == 50:
                                i_baseline[read_idx] = float(np.mean(samples))

                        if read_idx in i_baseline:
                            current_adj = -(current - i_baseline[read_idx])
                            batch['iv'].append((voltage, current_adj * 1e6))
                            if batch_key not in q_accum:
                                q_accum[batch_key] = 0.0
                                last_t_per_phase[batch_key] = rel_t
                            else:
                                dt = rel_t - last_t_per_phase[batch_key]
                                if dt > 0:
                                    q_accum[batch_key] += current_adj * dt
                                last_t_per_phase[batch_key] = rel_t
                            batch['qv'].append((voltage, q_accum[batch_key] * 1e9))

                    plot_batch = {}
                    for (read_idx, phase_key), batch in batches.items():
                        v_source, i_source, iv_source, qv_source = source_map[read_idx][phase_key]
                        plot_batch[v_source] = batch['v']
                        plot_batch[i_source] = batch['i']
                        plot_batch[iv_source] = batch['iv']
                        plot_batch[qv_source] = batch['qv']
                    if plot_batch:
                        self.runner.plot.append_batch(plot_batch)

                    plotted_count = available
                    last_progress_time = time.monotonic()
                    continue

                if status == self.STATUS_COMPLETED:
                    if plotted_count >= expected_total:
                        break
                    if (time.monotonic() - last_progress_time) > self.POST_COMPLETION_DRAIN_TIMEOUT_S:
                        self.log(
                            "Warning: WGFMU completed before all read samples were available "
                            f"({plotted_count}/{expected_total} samples)."
                        )
                        break

                time.sleep(0.05)

            all_rows = []
            for read_idx, vmax in enumerate(self.vmax_values):
                offset = read_idx * sample_points
                for i in range(sample_points):
                    row_idx = offset + i
                    if row_idx < len(data_ch1) and row_idx < len(data_ch2):
                        _t_v, voltage = data_ch1[row_idx]
                        _t_i, current = data_ch2[row_idx]
                        all_rows.append([vmax, i * sample_interval, voltage, current])

            self.save_measurement_outputs(
                all_rows,
                "PUND_Wakeup",
                device,
                ["Vmax_V", "Time_s", "Voltage_V", "Current_A"],
                plot_suffix="_overlay.png",
                save_plot=bool(all_rows),
            )
            self.log(f"PUND Wakeup complete: {len(self.vmax_values)} read trace(s), {len(all_rows)} samples")

        finally:
            try:
                wgfmu.clear()
                wgfmu.disconnect(self.channel_1)
                wgfmu.disconnect(self.channel_2)
            except Exception:
                pass
