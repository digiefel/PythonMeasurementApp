import math
import os
import threading
import time
from itertools import product

import numpy as np

from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, WGFMUChannel, parameter
from instrumentio.codes import (
    B1500_AUTO_RANGE,
    WGFMU_FORCE_VOLTAGE_RANGE_AUTO,
    WGFMU_STATUS_ABORTED,
    WGFMU_STATUS_ABORT_COMPLETED,
    WGFMU_MEASURE_ENABLED_ENABLE,
    WGFMU_MEASURE_EVENT_DATA_AVERAGED,
    WGFMU_MEASURE_MODE_CURRENT,
    WGFMU_OPERATION_MODE_FASTIV,
    WGFMU_STATUS_COMPLETED,
    WGFMU_STATUS_DONE,
)
from instrumentio.constants import SMU_CHANNEL_MAP, WGFMU_MEASURE_CURRENT_RANGES


class WGFMUSamplingProcedure(MeasurementProcedure):
    """Dual-channel fixed-bias current sampling using WGFMU."""

    MAX_PLOT_POINTS = 100_000
    PSD_WINDOW_LEN = 2048
    MIN_SAMPLE_INTERVAL_S = 1e-8
    SAMPLE_INTERVAL_RESOLUTION_S = 1e-8
    MAX_MEAS_INTERVAL_S = 1.34217728
    MAX_AVERAGING_TIME_S = 0.020971512
    MAX_VECTOR_INTERVAL_S = 10995.11627775
    MAX_EVENT_POINTS = 2_147_483_647
    # B1530A guide: read channel data before stored data exceeds about 4,000,000.
    # Practical headroom depends on averaging and readout throughput.
    MAX_RECOMMENDED_POINTS = 4_000_000
    POLL_INTERVAL_S = 0.05
    MAX_READ_CHUNK_POINTS = 5000
    POST_COMPLETION_DRAIN_TIMEOUT_S = 30.0

    NAME = "WGFMU Sampling"
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('channel_1', 'WGFMU Channel 1', 101, WGFMUChannel),
        parameter('channel_2', 'WGFMU Channel 2', 102, WGFMUChannel),
        parameter('force_voltage_1', 'WGFMU Force Voltage Ch1 List (V, comma-separated)', '0.1', str),
        parameter('force_voltage_2', 'WGFMU Force Voltage Ch2 List (V, comma-separated)', '0.1', str),
        parameter('smu_channel_list_1', 'SMU Channel List 1 (comma-separated)', 'SMU1', str),
        parameter('smu_channel_list_2', 'SMU Channel List 2 (comma-separated)', 'SMU2', str),
        parameter('smu_voltage_1', 'SMU Voltage List 1 (V, comma-separated)', '0.0', str),
        parameter('smu_voltage_2', 'SMU Voltage List 2 (V, comma-separated)', '0.0', str),
        parameter('smu_compliance_1', 'SMU Compliance 1 (A)', 0.01, float),
        parameter('smu_compliance_2', 'SMU Compliance 2 (A)', 0.01, float),
        parameter('hold_time_s', 'Hold Time Before Sampling (s)', 0.0, float),
        parameter('sampling_rate_hz', 'Sampling Rate (Hz)', 1e4, float),
        parameter('total_samples', 'Total Samples', 100000, int),
        parameter('meas_range_1', 'Current Range Ch1', WGFMU_MEASURE_CURRENT_RANGES[0][0], Choice(WGFMU_MEASURE_CURRENT_RANGES, int)),
        parameter('meas_range_2', 'Current Range Ch2', WGFMU_MEASURE_CURRENT_RANGES[0][0], Choice(WGFMU_MEASURE_CURRENT_RANGES, int)),
    )

    def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
        super().__init__(settings, output_root, output_relative, runner, fallback_root)
        self.force_voltage_1_values = self._parse_float_list(self.force_voltage_1, 'force_voltage_1')
        self.force_voltage_2_values = self._parse_float_list(self.force_voltage_2, 'force_voltage_2')
        self.smu_channel_list_1 = self._parse_channel_list(self.smu_channel_list_1, 'smu_channel_list_1')
        self.smu_channel_list_2 = self._parse_channel_list(self.smu_channel_list_2, 'smu_channel_list_2')
        self.smu_voltage_1_values = self._parse_float_list(self.smu_voltage_1, 'smu_voltage_1')
        self.smu_voltage_2_values = self._parse_float_list(self.smu_voltage_2, 'smu_voltage_2')

    @staticmethod
    def _split_csv(raw_value):
        if raw_value is None:
            return []
        if isinstance(raw_value, (list, tuple)):
            # Saved configs may restore lists, while the UI supplies comma-separated text.
            tokens = []
            for item in raw_value:
                if item is None:
                    continue
                item_str = str(item)
                tokens.extend(token.strip() for token in item_str.split(',') if token.strip())
            return tokens
        return [token.strip() for token in str(raw_value).split(',') if token.strip()]

    def _parse_float_list(self, raw_value, field_name):
        tokens = self._split_csv(raw_value)
        if not tokens:
            raise ValueError(f"{field_name} must contain at least one numeric value")

        values = []
        for token in tokens:
            try:
                value = float(token)
            except ValueError as exc:
                raise ValueError(f"{field_name} contains an invalid numeric token: '{token}'") from exc
            if not math.isfinite(value):
                raise ValueError(f"{field_name} contains a non-finite value: '{token}'")
            values.append(value)
        return values

    def _parse_channel_list(self, raw_value, field_name):
        tokens = self._split_csv(raw_value)
        if not tokens:
            raise ValueError(f"{field_name} must contain at least one SMU channel")

        channels = []
        for token in tokens:
            # Accept either "SMU1" style names from the UI or numeric channel ids from saved files.
            mapped = SMU_CHANNEL_MAP.get(token, SMU_CHANNEL_MAP.get(token.upper(), token))
            try:
                channel = int(float(mapped))
            except ValueError as exc:
                raise ValueError(f"{field_name} contains an invalid channel token: '{token}'") from exc
            if channel <= 0:
                raise ValueError(f"{field_name} contains a non-positive channel index: '{token}'")
            channels.append(channel)
        return channels

    def _iter_parameter_combinations(self):
        # Each Cartesian-product combination is measured and saved as its own output file.
        return product(
            self.smu_channel_list_1,
            self.smu_channel_list_2,
            self.force_voltage_1_values,
            self.force_voltage_2_values,
            self.smu_voltage_1_values,
            self.smu_voltage_2_values,
        )

    def _configure_wgfmu_channels(self, wgfmu):
        wgfmu.connect(self.channel_1)
        wgfmu.connect(self.channel_2)

        # FastIV mode lets each WGFMU channel force a constant voltage while measuring current.
        wgfmu.set_operation_mode(self.channel_1, WGFMU_OPERATION_MODE_FASTIV)
        wgfmu.set_operation_mode(self.channel_2, WGFMU_OPERATION_MODE_FASTIV)

        wgfmu.set_force_voltage_range(self.channel_1, WGFMU_FORCE_VOLTAGE_RANGE_AUTO)
        wgfmu.set_force_voltage_range(self.channel_2, WGFMU_FORCE_VOLTAGE_RANGE_AUTO)

        wgfmu.set_measure_mode(self.channel_1, WGFMU_MEASURE_MODE_CURRENT)
        wgfmu.set_measure_mode(self.channel_2, WGFMU_MEASURE_MODE_CURRENT)
        wgfmu.set_measure_current_range(self.channel_1, self.meas_range_1)
        wgfmu.set_measure_current_range(self.channel_2, self.meas_range_2)
        wgfmu.set_measure_enabled(self.channel_1, WGFMU_MEASURE_ENABLED_ENABLE)
        wgfmu.set_measure_enabled(self.channel_2, WGFMU_MEASURE_ENABLED_ENABLE)

    def _apply_smu_biases(self, b1500, smu_channel_1, smu_voltage_1, smu_channel_2, smu_voltage_2):
        # SMUs provide the slow DC biases that surround the two high-speed WGFMU channels.
        b1500.set_switch(smu_channel_1, True)
        b1500.set_switch(smu_channel_2, True)
        b1500.force_voltage(smu_channel_1, smu_voltage_1, self.smu_compliance_1, B1500_AUTO_RANGE)
        b1500.force_voltage(smu_channel_2, smu_voltage_2, self.smu_compliance_2, B1500_AUTO_RANGE)

    @staticmethod
    def _release_smu_channels(b1500, channels):
        for channel in channels:
            try:
                # Best-effort cleanup because failed cleanup should not hide the original measurement error.
                b1500.zero_output(channel)
            except Exception:
                pass
            try:
                b1500.set_switch(channel, False)
            except Exception:
                pass

    def _compute_sampling_parameters(self):
        if self.sampling_rate_hz <= 0:
            raise ValueError("sampling_rate_hz must be > 0")
        if self.hold_time_s < 0:
            raise ValueError("hold_time_s must be >= 0")
        if self.smu_compliance_1 <= 0 or self.smu_compliance_2 <= 0:
            raise ValueError("smu_compliance_1 and smu_compliance_2 must be > 0")
        if self.total_samples <= 0:
            raise ValueError("total_samples must be > 0")
        if self.total_samples > self.MAX_EVENT_POINTS:
            raise ValueError(
                f"total_samples exceeds supported limit ({self.MAX_EVENT_POINTS}) for this procedure"
            )
        if self.total_samples > self.MAX_RECOMMENDED_POINTS:
            raise ValueError(
                "total_samples exceeds the conservative WGFMU channel-data limit (~4,000,000). "
                "Lower total_samples, or reduce averaging / ensure faster host readout to avoid overflow."
            )

        requested_interval = 1.0 / self.sampling_rate_hz
        if requested_interval > self.MAX_MEAS_INTERVAL_S:
            min_rate_hz = 1.0 / self.MAX_MEAS_INTERVAL_S
            raise ValueError(
                f"sampling_rate_hz is too low for WGFMU measure-event timing "
                f"(minimum supported is {min_rate_hz:.6g} Hz)."
            )

        # WGFMU timing is quantized to 10 ns; effective_rate_hz reflects the rounded interval.
        sample_interval = max(requested_interval, self.MIN_SAMPLE_INTERVAL_S)
        sample_interval = round(sample_interval / self.SAMPLE_INTERVAL_RESOLUTION_S) * self.SAMPLE_INTERVAL_RESOLUTION_S
        if sample_interval <= 0:
            raise ValueError("Computed sample interval must be > 0")
        if sample_interval > self.MAX_MEAS_INTERVAL_S:
            raise ValueError(
                f"Computed sample interval ({sample_interval:.9g} s) exceeds WGFMU limit "
                f"({self.MAX_MEAS_INTERVAL_S:.9g} s)."
            )

        hold_time_quantized_s = round(self.hold_time_s / self.SAMPLE_INTERVAL_RESOLUTION_S) * self.SAMPLE_INTERVAL_RESOLUTION_S
        hold_time_quantized_s = max(0.0, hold_time_quantized_s)
        hold_time_quantized = abs(hold_time_quantized_s - self.hold_time_s) > 1e-15

        effective_rate_hz = 1.0 / sample_interval
        sampling_duration_s = sample_interval * self.total_samples
        sequence_duration_s = hold_time_quantized_s + sampling_duration_s
        if sequence_duration_s > self.MAX_VECTOR_INTERVAL_S:
            raise ValueError(
                f"Requested duration including hold ({sequence_duration_s:.6g} s) exceeds WGFMU single-vector limit "
                f"({self.MAX_VECTOR_INTERVAL_S:.6g} s)."
            )

        # Averaging cannot exceed the instrument maximum even if the requested sampling interval is long.
        integration_time_s = min(sample_interval, self.MAX_AVERAGING_TIME_S)
        integration_clamped = integration_time_s < sample_interval

        return (
            requested_interval,
            sample_interval,
            effective_rate_hz,
            sampling_duration_s,
            sequence_duration_s,
            hold_time_quantized_s,
            hold_time_quantized,
            integration_time_s,
            integration_clamped,
        )

    @staticmethod
    def _combination_label(index, force_voltage_1, force_voltage_2):
        return f"#{index} V1={force_voltage_1:.3g}V V2={force_voltage_2:.3g}V"

    @staticmethod
    def _combo_source_names(index):
        return (
            f"I1_c{index}",
            f"I2_c{index}",
            f"PSD_I1_c{index}",
            f"PSD_I2_c{index}",
        )

    def _build_plot_elements(self, combos):
        time_elements = []
        psd_elements = []
        for i, (force_voltage_1, force_voltage_2) in enumerate(combos):
            combo_index = i + 1
            color_i1 = f"C{(2 * i) % 10}"
            color_i2 = f"C{(2 * i + 1) % 10}"
            label_suffix = self._combination_label(combo_index, force_voltage_1, force_voltage_2)
            i1_src, i2_src, psd1_src, psd2_src = self._combo_source_names(combo_index)
            time_elements.append(Curve(i1_src, color=color_i1, legend_label=f"I1 {label_suffix}"))
            time_elements.append(Curve(i2_src, color=color_i2, legend_label=f"-I2 {label_suffix}"))
            psd_elements.append(Curve(psd1_src, color=color_i1, legend_label=f"PSD I1 {label_suffix}"))
            psd_elements.append(Curve(psd2_src, color=color_i2, legend_label=f"PSD I2 {label_suffix}"))
        return time_elements, psd_elements

    @staticmethod
    def _rectangular_periodogram(samples, fs):
        """One-sided power spectral density for a rectangular-windowed segment."""
        x = np.asarray(samples, dtype=np.float64)
        x = x - x.mean()
        n = x.size
        spectrum = np.fft.rfft(x)
        psd = (np.abs(spectrum) ** 2) / (fs * n)
        if psd.size > 2:
            psd[1:-1] *= 2.0
        return psd

    def _new_plot_state(self, bucket_size):
        return {
            'bucket_size': bucket_size,
            'count': 0,
            'sum_t': 0.0,
            'sum_i1': 0.0,
            'sum_i2': 0.0,
        }

    def _push_plot_sample(self, t_val, i1_val, i2_val, state, out_i1, out_i2):
        # Bucket-average only the live plot; raw samples are still preserved for CSV output.
        state['count'] += 1
        state['sum_t'] += t_val
        state['sum_i1'] += i1_val
        state['sum_i2'] += i2_val

        if state['count'] >= state['bucket_size']:
            count = state['count']
            avg_t = state['sum_t'] / count
            out_i1.append((avg_t, state['sum_i1'] / count))
            out_i2.append((avg_t, -state['sum_i2'] / count))
            state['count'] = 0
            state['sum_t'] = 0.0
            state['sum_i1'] = 0.0
            state['sum_i2'] = 0.0

    def _flush_plot_bucket(self, state, out_i1, out_i2):
        if state['count'] <= 0:
            return
        count = state['count']
        avg_t = state['sum_t'] / count
        out_i1.append((avg_t, state['sum_i1'] / count))
        out_i2.append((avg_t, -state['sum_i2'] / count))
        state['count'] = 0
        state['sum_t'] = 0.0
        state['sum_i1'] = 0.0
        state['sum_i2'] = 0.0

    def _new_psd_state(self, fs):
        # PSD state is accumulated incrementally so long recordings do not need a second pass over all samples.
        freqs = np.fft.rfftfreq(self.PSD_WINDOW_LEN, d=1.0 / fs)
        return {
            'fs': fs,
            'freqs': freqs,
            'freqs_list': freqs.tolist(),
            'buf_i1': [],
            'buf_i2': [],
            'sum_psd_i1': np.zeros_like(freqs),
            'sum_psd_i2': np.zeros_like(freqs),
            'count': 0,
            'dirty': False,
        }

    def _push_psd_sample(self, psd_state, i1_val, i2_val):
        # Average non-overlapping PSD windows before replacing the plotted spectrum.
        psd_state['buf_i1'].append(i1_val)
        psd_state['buf_i2'].append(i2_val)
        if len(psd_state['buf_i1']) >= self.PSD_WINDOW_LEN:
            psd_state['sum_psd_i1'] += self._rectangular_periodogram(
                psd_state['buf_i1'][: self.PSD_WINDOW_LEN], psd_state['fs']
            )
            psd_state['sum_psd_i2'] += self._rectangular_periodogram(
                psd_state['buf_i2'][: self.PSD_WINDOW_LEN], psd_state['fs']
            )
            psd_state['count'] += 1
            del psd_state['buf_i1'][: self.PSD_WINDOW_LEN]
            del psd_state['buf_i2'][: self.PSD_WINDOW_LEN]
            psd_state['dirty'] = True

    def _flush_psd_to_plot(self, psd_state, psd1_source, psd2_source, plot, force=False):
        if psd_state['count'] <= 0:
            return
        if not force and not psd_state['dirty']:
            return
        count = psd_state['count']
        # replace_source redraws the whole spectrum because the averaged PSD changes at every window.
        avg_psd_i1 = psd_state['sum_psd_i1'] / count
        avg_psd_i2 = psd_state['sum_psd_i2'] / count
        freqs = psd_state['freqs_list']
        plot.replace_source(psd1_source, freqs, avg_psd_i1.tolist())
        plot.replace_source(psd2_source, freqs, avg_psd_i2.tolist())
        psd_state['dirty'] = False

    def _format_combo_header(
        self,
        *,
        combo_index,
        total_combinations,
        smu_channel_1,
        smu_voltage_1,
        smu_channel_2,
        smu_voltage_2,
        force_voltage_1,
        force_voltage_2,
        sample_interval,
        effective_rate_hz,
        sampling_duration_s,
        hold_time_s,
        integration_time_s,
        device_name,
    ):
        return [
            f"# Combination: {combo_index}/{total_combinations}",
            f"# SMU Channel 1: {smu_channel_1}",
            f"# SMU Voltage 1: {smu_voltage_1:.9e} V",
            f"# SMU Channel 2: {smu_channel_2}",
            f"# SMU Voltage 2: {smu_voltage_2:.9e} V",
            f"# WGFMU Force Voltage 1: {force_voltage_1:.9e} V",
            f"# WGFMU Force Voltage 2: {force_voltage_2:.9e} V",
            f"# Effective Sampling Rate: {effective_rate_hz:.9e} Hz",
            f"# Sample Interval: {sample_interval:.9e} s",
            f"# Integration Time: {integration_time_s:.9e} s",
            f"# Sampling Duration: {sampling_duration_s:.9e} s",
        ]

    def _write_combo_file(self, path, header_lines, rows):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            # Base metadata contains all procedure parameters; combo header adds the current Cartesian-product values.
            for line in self.csv_metadata_lines():
                f.write(line + '\n')
            for line in header_lines:
                f.write(line + '\n')
            f.write("Time_s,Current_1_A,Current_2_A\n")
            for t_val, i1, i2 in rows:
                f.write(f"{t_val:.9e},{i1:.7e},{i2:.7e}\n")

    def _save_combo_data(self, base, combo_index, header_lines, rows, primary_timeout=5.0):
        filename = f"{base}_c{combo_index:03d}.csv"
        primary_path = self.make_output_path(filename, add_timestamp=False)

        result = {}

        def _writer():
            try:
                self._write_combo_file(primary_path, header_lines, rows)
                result['success'] = True
            except Exception as exc:
                result['success'] = False
                result['error'] = exc

        thread = threading.Thread(target=_writer, daemon=True)
        thread.start()
        thread.join(timeout=primary_timeout)

        if thread.is_alive():
            self.log(f"Warning: primary save timed out after {primary_timeout}s; falling back.")
        elif result.get('success'):
            self.log(f"Saved combo {combo_index} to {primary_path}")
            return primary_path
        else:
            error = result.get('error', 'Unknown error')
            self.log(f"Warning: primary save failed ({error}); retrying in fallback directory.")

        fallback_path = self._make_fallback_path(primary_path)
        try:
            self._write_combo_file(fallback_path, header_lines, rows)
            self.output_root = self.fallback_root
            self.log(f"Saved combo {combo_index} to fallback path {fallback_path}")
            return fallback_path
        except Exception as exc:
            self.log(f"Error saving combo {combo_index} to fallback directory: {exc}")
            try:
                self.runner.safe_stop()
            finally:
                raise

    def measure(self, device):
        b1500 = self.b1500
        self.check_stop(b1500)

        (
            requested_interval,
            sample_interval,
            effective_rate_hz,
            sampling_duration_s,
            sequence_duration_s,
            hold_time_s,
            hold_time_quantized,
            integration_time_s,
            integration_clamped,
        ) = self._compute_sampling_parameters()

        overlap_channels = sorted(set(self.smu_channel_list_1).intersection(self.smu_channel_list_2))
        if overlap_channels:
            overlap_text = ', '.join(str(ch) for ch in overlap_channels)
            raise ValueError(
                "smu_channel_list_1 and smu_channel_list_2 must not overlap. "
                f"Overlapping channels: {overlap_text}"
            )

        combinations = list(self._iter_parameter_combinations())
        total_combinations = len(combinations)
        if total_combinations <= 0:
            raise ValueError("No parameter combinations available to run")

        # Keep the UI responsive by reducing only plotted points; every raw sample is still written to CSV.
        plot_bucket_size = max(1, math.ceil(self.total_samples / self.MAX_PLOT_POINTS))

        self.log(f"Starting WGFMU Sampling on {device.name}")
        self.log(
            f"  Requested sampling rate: {self.sampling_rate_hz:.6g} Hz, "
            f"effective: {effective_rate_hz:.6g} Hz"
        )
        self.log(
            f"  Sample interval: {sample_interval:.9g} s, integration time: {integration_time_s:.9g} s"
        )
        self.log(
            f"  Hold time: {hold_time_s:.9g} s"
        )
        self.log(
            f"  Samples: {self.total_samples}, sampling duration: {sampling_duration_s:.6g} s, "
            f"sequence duration: {sequence_duration_s:.6g} s, "
            f"plot bucket size: {plot_bucket_size}"
        )
        self.log(
            f"  SMU compliance: ch1 {self.smu_compliance_1:.6g} A, ch2 {self.smu_compliance_2:.6g} A"
        )
        self.log(
            f"  Parameter combinations: {total_combinations} "
            f"(SMU1 channels={len(self.smu_channel_list_1)}, "
            f"SMU2 channels={len(self.smu_channel_list_2)}, "
            f"WGFMU V1 values={len(self.force_voltage_1_values)}, "
            f"WGFMU V2 values={len(self.force_voltage_2_values)}, "
            f"SMU V1 values={len(self.smu_voltage_1_values)}, "
            f"SMU V2 values={len(self.smu_voltage_2_values)})"
        )
        self.log(
            f"  PSD window: rectangular, {self.PSD_WINDOW_LEN} samples "
            f"(resolution {effective_rate_hz / self.PSD_WINDOW_LEN:.6g} Hz)"
        )

        if abs(sample_interval - requested_interval) > (requested_interval * 1e-12):
            self.log(
                "  Note: sample interval was quantized to WGFMU timing resolution "
                f"({self.SAMPLE_INTERVAL_RESOLUTION_S:.0e} s)."
            )

        if integration_clamped:
            self.log(
                "  Note: integration time was clamped to WGFMU max averaging time "
                f"({self.MAX_AVERAGING_TIME_S:.9g} s)."
            )

        if hold_time_quantized:
            self.log(
                "  Note: hold time was quantized to WGFMU timing resolution "
                f"({self.SAMPLE_INTERVAL_RESOLUTION_S:.0e} s)."
            )

        if self.PSD_WINDOW_LEN > self.total_samples:
            self.log(
                f"  Note: PSD window ({self.PSD_WINDOW_LEN}) exceeds total_samples "
                f"({self.total_samples}); PSD will remain empty."
            )

        runner = self.runner
        time_elements, psd_elements = self._build_plot_elements(
            [(v1, v2) for (_, _, v1, v2, _, _) in combinations]
        )
        runner.configure_plot(
            f'WGFMU Sampling - {device.name}',
            [
                PlotDef(
                    "samp",
                    row=0,
                    col=0,
                    title="Time Domain",
                    xlabel="Time (s)",
                    ylabels=("Current (A)",),
                    elements=time_elements,
                ),
                PlotDef(
                    "psd",
                    row=1,
                    col=0,
                    title="PSD (rect, N=2048)",
                    xlabel="Frequency (Hz)",
                    xscale="log",
                    ylabels=("PSD (A²/Hz)",),
                    yscales=("log",),
                    elements=psd_elements,
                ),
            ],
            row_ratios=(1.0, 1.0),
        )

        wgfmu = b1500.wgfmu
        ts = self.get_run_timestamp()
        base = self.format_filename("WGFMU_Sampling", device.name)

        active_smu_channels = sorted(set(self.smu_channel_list_1 + self.smu_channel_list_2))

        try:
            for combo_index, (
                smu_channel_1,
                smu_channel_2,
                force_voltage_1,
                force_voltage_2,
                smu_voltage_1,
                smu_voltage_2,
            ) in enumerate(combinations, start=1):
                self.check_stop(b1500)
                self.log(
                    f"  Combination {combo_index}/{total_combinations}: "
                    f"SMU{smu_channel_1}={smu_voltage_1:.6g} V, "
                    f"SMU{smu_channel_2}={smu_voltage_2:.6g} V, "
                    f"WGFMU1={force_voltage_1:.6g} V, WGFMU2={force_voltage_2:.6g} V"
                )

                wgfmu.clear()
                self._configure_wgfmu_channels(wgfmu)
                self._apply_smu_biases(
                    b1500,
                    smu_channel_1,
                    smu_voltage_1,
                    smu_channel_2,
                    smu_voltage_2,
                )

                pattern_1 = f"WGSAMP1_{ts}_{combo_index}"
                pattern_2 = f"WGSAMP2_{ts}_{combo_index}"

                # Keep both WGFMU channels at constant bias by using a flat vector over the full duration.
                wgfmu.create_pattern(pattern_1, force_voltage_1)
                wgfmu.add_vector(pattern_1, sequence_duration_s, force_voltage_1)
                wgfmu.create_pattern(pattern_2, force_voltage_2)
                wgfmu.add_vector(pattern_2, sequence_duration_s, force_voltage_2)

                wgfmu.set_measure_event(
                    pattern_1,
                    "meas",
                    hold_time_s,
                    int(self.total_samples),
                    sample_interval,
                    integration_time_s,
                    WGFMU_MEASURE_EVENT_DATA_AVERAGED,
                )
                wgfmu.set_measure_event(
                    pattern_2,
                    "meas",
                    hold_time_s,
                    int(self.total_samples),
                    sample_interval,
                    integration_time_s,
                    WGFMU_MEASURE_EVENT_DATA_AVERAGED,
                )

                self.check_stop(b1500)
                # Both WGFMU channels run the same-duration pattern so their samples can be paired by index.
                wgfmu.add_sequence(self.channel_1, pattern_1, 1.0)
                wgfmu.add_sequence(self.channel_2, pattern_2, 1.0)
                wgfmu.execute()

                i1_source, i2_source, psd1_source, psd2_source = self._combo_source_names(combo_index)
                next_index = 0
                expected_total = self.total_samples
                last_progress_time = time.monotonic()
                plot_state = self._new_plot_state(plot_bucket_size)
                psd_state = self._new_psd_state(effective_rate_hz)
                combo_rows = []

                while True:
                    self.check_stop(b1500)
                    status, _elapsed, _total, measured_1, _total_1, measured_2, _total_2 = (
                        wgfmu.poll(self.channel_1, self.channel_2)
                    )
                    # Pair only samples available on both channels; otherwise channel skew would corrupt rows.
                    available = min(measured_1, measured_2, expected_total)

                    if available > next_index:
                        # Read in chunks to bound VISA transfer time and keep stop requests responsive.
                        chunk_size = min(available - next_index, self.MAX_READ_CHUNK_POINTS)
                        read_until = next_index + chunk_size
                        plot_i1 = []
                        plot_i2 = []
                        samples_1 = wgfmu.read_chunk(self.channel_1, next_index, chunk_size)
                        samples_2 = wgfmu.read_chunk(self.channel_2, next_index, chunk_size)
                        for (t1, i1), (_, i2) in zip(samples_1, samples_2):
                            # Remove the pre-sampling hold so CSV time starts at the first measured sample.
                            t_val = t1 - hold_time_s
                            combo_rows.append((t_val, i1, i2))
                            self._push_plot_sample(t_val, i1, i2, plot_state, plot_i1, plot_i2)
                            self._push_psd_sample(psd_state, i1, i2)

                        if plot_i1 or plot_i2:
                            runner.plot.append_batch({
                                i1_source: plot_i1,
                                i2_source: plot_i2,
                            })
                        self._flush_psd_to_plot(psd_state, psd1_source, psd2_source, runner.plot)
                        next_index = read_until
                        last_progress_time = time.monotonic()
                        continue

                    if status in (WGFMU_STATUS_COMPLETED, WGFMU_STATUS_DONE):
                        if next_index >= expected_total:
                            break

                        # The WGFMU can report completed status before all points are readable;
                        # keep draining until expected_total arrives or progress stops.
                        if (time.monotonic() - last_progress_time) > self.POST_COMPLETION_DRAIN_TIMEOUT_S:
                            self.log(
                                "Warning: WGFMU completed but no additional data became available "
                                f"for {self.POST_COMPLETION_DRAIN_TIMEOUT_S:.0f}s "
                                f"({next_index}/{expected_total} points read)."
                            )
                            break

                    if status in (WGFMU_STATUS_ABORT_COMPLETED, WGFMU_STATUS_ABORTED):
                        self.log(
                            f"Warning: WGFMU reported aborted status ({status}); "
                            f"captured {next_index}/{expected_total} points."
                        )
                        break

                    time.sleep(self.POLL_INTERVAL_S)

                tail_i1 = []
                tail_i2 = []
                self._flush_plot_bucket(plot_state, tail_i1, tail_i2)
                if tail_i1 or tail_i2:
                    runner.plot.append_batch({
                        i1_source: tail_i1,
                        i2_source: tail_i2,
                    })
                self._flush_psd_to_plot(psd_state, psd1_source, psd2_source, runner.plot, force=True)

                if next_index < self.total_samples:
                    self.log(
                        f"Warning: combo {combo_index} requested {self.total_samples} samples, "
                        f"collected {next_index}."
                    )

                header_lines = self._format_combo_header(
                    combo_index=combo_index,
                    total_combinations=total_combinations,
                    smu_channel_1=smu_channel_1,
                    smu_voltage_1=smu_voltage_1,
                    smu_channel_2=smu_channel_2,
                    smu_voltage_2=smu_voltage_2,
                    force_voltage_1=force_voltage_1,
                    force_voltage_2=force_voltage_2,
                    sample_interval=sample_interval,
                    effective_rate_hz=effective_rate_hz,
                    sampling_duration_s=sampling_duration_s,
                    hold_time_s=hold_time_s,
                    integration_time_s=integration_time_s,
                    device_name=device.name,
                )
                self._save_combo_data(base, combo_index, header_lines, combo_rows)

            self.save_plot_png(f"{base}_plot.png")

            self.log(
                f"WGFMU Sampling complete: {total_combinations} file(s) written"
            )

        finally:
            self._release_smu_channels(b1500, active_smu_channels)
            try:
                wgfmu.clear()
                wgfmu.disconnect(self.channel_1)
                wgfmu.disconnect(self.channel_2)
            except Exception:
                pass
