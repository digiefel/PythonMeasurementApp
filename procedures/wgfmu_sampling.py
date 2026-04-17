import math
import time
from itertools import product

from plotting import PlotDef, Curve
from procedures.base import MeasurementProcedure
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

    MAX_PLOT_POINTS = 10000
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

    def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
        super().__init__(settings, output_root, output_relative, runner, fallback_root)
        self.gpib_address = settings.get('gpib_address', 'GPIB0::17::INSTR')

        self.channel_1 = int(settings.get('channel_1', 101))
        self.channel_2 = int(settings.get('channel_2', 102))

        self.force_voltage_1_values = self._parse_float_list(settings.get('force_voltage_1', '0.1'), 'force_voltage_1')
        self.force_voltage_2_values = self._parse_float_list(settings.get('force_voltage_2', '0.1'), 'force_voltage_2')

        self.smu_channel_list_1 = self._parse_channel_list(settings.get('smu_channel_list_1', 'SMU1'), 'smu_channel_list_1')
        self.smu_channel_list_2 = self._parse_channel_list(settings.get('smu_channel_list_2', 'SMU2'), 'smu_channel_list_2')
        self.smu_voltage_1_values = self._parse_float_list(settings.get('smu_voltage_1', '0.0'), 'smu_voltage_1')
        self.smu_voltage_2_values = self._parse_float_list(settings.get('smu_voltage_2', '0.0'), 'smu_voltage_2')
        self.smu_compliance_1 = float(settings.get('smu_compliance_1', 0.01))
        self.smu_compliance_2 = float(settings.get('smu_compliance_2', 0.01))

        self.hold_time_s = float(settings.get('hold_time_s', 0.0))

        self.sampling_rate_hz = float(settings.get('sampling_rate_hz', 1e4))
        self.total_samples = int(float(settings.get('total_samples', 100000)))

        self.meas_range_1 = int(settings.get('meas_range_1', WGFMU_MEASURE_CURRENT_RANGES[0][0]))
        self.meas_range_2 = int(settings.get('meas_range_2', WGFMU_MEASURE_CURRENT_RANGES[0][0]))

    @staticmethod
    def _split_csv(raw_value):
        if raw_value is None:
            return []
        if isinstance(raw_value, (list, tuple)):
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
        b1500.set_switch(smu_channel_1, True)
        b1500.set_switch(smu_channel_2, True)
        b1500.force_voltage(smu_channel_1, smu_voltage_1, self.smu_compliance_1, B1500_AUTO_RANGE)
        b1500.force_voltage(smu_channel_2, smu_voltage_2, self.smu_compliance_2, B1500_AUTO_RANGE)

    @staticmethod
    def _release_smu_channels(b1500, channels):
        for channel in channels:
            try:
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

    def _push_plot_sample(self, t_val, i1_val, i2_val, state, out_i1, out_i2):
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

    def run(self, b1500, device):
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

        total_combinations = (
            len(self.smu_channel_list_1)
            * len(self.smu_channel_list_2)
            * len(self.force_voltage_1_values)
            * len(self.force_voltage_2_values)
            * len(self.smu_voltage_1_values)
            * len(self.smu_voltage_2_values)
        )
        if total_combinations <= 0:
            raise ValueError("No parameter combinations available to run")

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
            f"  Parameter combinations: {total_combinations} "
            f"(SMU1 channels={len(self.smu_channel_list_1)}, "
            f"SMU2 channels={len(self.smu_channel_list_2)}, "
            f"WGFMU V1 values={len(self.force_voltage_1_values)}, "
            f"WGFMU V2 values={len(self.force_voltage_2_values)}, "
            f"SMU V1 values={len(self.smu_voltage_1_values)}, "
            f"SMU V2 values={len(self.smu_voltage_2_values)})"
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

        runner = self.runner
        runner.configure_plot(f'WGFMU Sampling - {device.name}', [
            PlotDef("samp", xlabel="Time (s)", ylabels=("Current (A)",),
                    xlim=(0.0, sampling_duration_s),
                    elements=[
                        Curve("I1", color="C0", legend_label="I1(t)"),
                        Curve("I2", color="C1", legend_label="-I2(t)"),
                    ]),
        ])

        wgfmu = b1500.wgfmu
        ts = self.get_run_timestamp()

        csv_rows = []
        active_smu_channels = sorted(set(self.smu_channel_list_1 + self.smu_channel_list_2))

        try:
            for combo_index, (
                smu_channel_1,
                smu_channel_2,
                force_voltage_1,
                force_voltage_2,
                smu_voltage_1,
                smu_voltage_2,
            ) in enumerate(self._iter_parameter_combinations(), start=1):
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
                wgfmu.add_sequence(self.channel_1, pattern_1, 1.0)
                wgfmu.add_sequence(self.channel_2, pattern_2, 1.0)
                wgfmu.execute()

                next_index = 0
                expected_total = self.total_samples
                last_progress_time = time.monotonic()
                plot_state = {
                    'bucket_size': plot_bucket_size,
                    'count': 0,
                    'sum_t': 0.0,
                    'sum_i1': 0.0,
                    'sum_i2': 0.0,
                }

                while True:
                    self.check_stop(b1500)
                    status, _elapsed, _total = wgfmu.get_status()

                    measured_1, _total_1 = wgfmu.get_measure_value_size(self.channel_1)
                    measured_2, _total_2 = wgfmu.get_measure_value_size(self.channel_2)
                    available = min(measured_1, measured_2, expected_total)

                    if available > next_index:
                        read_until = min(available, next_index + self.MAX_READ_CHUNK_POINTS)
                        plot_i1 = []
                        plot_i2 = []
                        for idx in range(next_index, read_until):
                            t1, i1 = wgfmu.get_measure_value(self.channel_1, idx)
                            t2, i2 = wgfmu.get_measure_value(self.channel_2, idx)
                            t_raw = t1 if t1 is not None else t2
                            t_val = t_raw - hold_time_s

                            csv_rows.append([
                                combo_index,
                                idx,
                                smu_channel_1,
                                smu_voltage_1,
                                smu_channel_2,
                                smu_voltage_2,
                                t_val,
                                i1,
                                force_voltage_1,
                                i2,
                                force_voltage_2,
                            ])

                            self._push_plot_sample(t_val, i1, i2, plot_state, plot_i1, plot_i2)

                        if plot_i1 or plot_i2:
                            runner.plot.append_batch({'I1': plot_i1, 'I2': plot_i2})
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
                    runner.plot.append_batch({'I1': tail_i1, 'I2': tail_i2})

                if next_index < self.total_samples:
                    self.log(
                        f"Warning: combo {combo_index} requested {self.total_samples} samples, "
                        f"collected {next_index}."
                    )

            base = self.format_filename("WGFMU_Sampling", device.name)
            filename = f"{base}.csv"
            self.save_data(
                csv_rows,
                filename,
                [
                    "Combination_Index",
                    "Sample_Index",
                    "SMU_Channel_1",
                    "SMU_Voltage_1_V",
                    "SMU_Channel_2",
                    "SMU_Voltage_2_V",
                    "Time_s",
                    "Current_1_A",
                    "Voltage_1_V",
                    "Current_2_A",
                    "Voltage_2_V",
                ],
                add_timestamp=False,
            )

            plot_filename = f"{base}_plot.png"
            runner.plot.save_png(plot_filename, self.output_root, self.output_relative, self.fallback_root)

            self.log(
                f"WGFMU Sampling complete: {len(csv_rows)} samples captured "
                f"across {total_combinations} combinations"
            )

        finally:
            self._release_smu_channels(b1500, active_smu_channels)
            try:
                wgfmu.clear()
                wgfmu.disconnect(self.channel_1)
                wgfmu.disconnect(self.channel_2)
            except Exception:
                pass