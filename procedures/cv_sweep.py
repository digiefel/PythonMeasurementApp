from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, ValueList, parameter, action
from instrumentio.constants import (
    B1500_CMU_CHANNELS,
    B1500_CMU_INTEGRATION_MODES,
    B1500_CMU_MEASUREMENT_MODES,
    B1500_CMU_SWEEP_RANGES,
)
from instrumentio.codes import (
    B1500_AUTO_RANGE,
    B1500_CH_ALL,
    B1500_CMUM_CP_D,
    B1500_CMUM_Z_TDEG,
    B1500_CMUM_Z_TRAD,
    B1500_LAST_STOP,
    B1500_STOP_DISABLE,
    B1500_SWP_VF_DBLLIN,
    B1500_SWP_VF_SGLLIN,
)
from instrumentio.descriptors import (
    format_cmu_component_label,
    get_cmu_mode_components,
    get_cmu_mode_name,
)
from procedures._cmu import (
    append_z_theta_point,
    calibrated_frequencies,
    freq_key,
    freq_label,
    phase_compensated,
    report_cmu_status,
    resolve_cmu_channel,
    z_theta_plots,
)
from si_utils import parse_si_list


CV_SWEEP_TYPES = (
    ('single', 'Single (Start → Stop)'),
    ('double', 'Double (Start → Stop → Start)'),
    ('butterfly', 'Butterfly (0 → Vmax → Vmin → 0)'),
)


class CVSweepProcedure(MeasurementProcedure):
    """CMU-based capacitance-voltage sweep for B1500.

    Supports three sweep shapes (sweep_type):
      'single'    — Start → Stop (one pass)
      'double'    — Start → Stop → Start (return pass)
      'butterfly' — 0 → Vmax → Vmin → 0 (three-leg, always starts/ends at zero)
                    where start_bias = Vmax and stop_bias = Vmin.

    Multiple frequencies may be specified (comma-separated with SI prefixes, e.g. '100k, 1M').
    The sweep is executed once per frequency; all traces are plotted together and the CSV
    always includes a Frequency_Hz column.

    Each point sets DC bias, waits for settling and measures impedance using the
    selected AC frequency/level and CMU integration time. Results plot as acquired.
    PLC integration rejects line-frequency noise: N cycles take N × 20 ms at 50 Hz.
    Calibration controls apply open/short/load correction and phase compensation.
    Hover over settings for their meanings.

    When cmu_mode is Z-Theta, the plot shows |Z|-Theta (measured), then the
    Nyquist plot (-Z'' against Z', with bias running along each curve), then
    the Rp-Cp, Rs-Cs and G-B pairs against bias (calculated at the sweep
    frequency). The CSV holds only the measured values; every pair can be
    recalculated from Z and Theta.
    """

    NAME = "CVSweep"
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('cmu_channel', 'CMU Channel', -1, Choice(B1500_CMU_CHANNELS, int)),
        parameter('sweep_type', 'Sweep Type', 'single', Choice(CV_SWEEP_TYPES, str)),
        parameter('cmu_mode', 'C-V Meas Output', B1500_CMUM_Z_TDEG, Choice(B1500_CMU_MEASUREMENT_MODES, int), help="Selects the impedance representation returned by the CMU. Z–Theta modes also plot the Nyquist plot and the Rp-Cp, Rs-Cs and G-B pairs."),
        parameter('start_bias', 'Start Bias (V)', -2.0, float),
        parameter('stop_bias', 'Stop Bias (V)', 2.0, float),
        parameter('points', 'Points', 101, int),
        parameter('measurement_range', 'MFCMU Meas Range', B1500_AUTO_RANGE, Choice(B1500_CMU_SWEEP_RANGES, float)),
        parameter('ac_level_mv', 'AC Level (mV)', 30.0, float, help='AC excitation superimposed on the swept DC bias for impedance measurement.'),
        parameter('frequencies', 'Frequencies', '100k', ValueList, help="Comma-separated frequencies in Hz; SI prefixes are accepted, e.g. '10k, 100k, 1M'. One sweep per frequency."),
        parameter('integration_mode', 'Integration Mode', 0, Choice(B1500_CMU_INTEGRATION_MODES, int)),
        parameter('integration_value', 'Integration Coefficient (N)', 1, int, help="Auto: the CMU averages N times the number of samples the B1500 picks itself, N from 1 to 1023 "
                  "(the B1500's own default is 2). PLC: averaging lasts N power line cycles, 20 ms each at 50 Hz, N from 1 to 100."),
        parameter('hold_time', 'Hold Time (s)', 0.0, float),
        parameter('delay_time', 'Delay Time (s)', 0.0, float),
        parameter('second_delay', 'Second Delay (s)', 0.0, float),
        parameter('require_cmu_calibration', 'Require Calibration', False, bool),
    )
    UI_ACTIONS = (
        action("Open", "_on_cv_calibration_button", "open", section="CMU Calibration", tooltip="Open-circuit calibration"),
        action("Short", "_on_cv_calibration_button", "short", section="CMU Calibration", tooltip="Short-circuit calibration"),
        action("Phase", "_on_cv_calibration_button", "phase", section="CMU Calibration", tooltip="Phase compensation"),
        action("Load", "_on_cv_calibration_button", "load", section="CMU Calibration", tooltip="Load calibration"),
    )

    def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
        settings = dict(settings)
        # Accept old saved settings while new procedure definitions expose one sweep_type field.
        if 'sweep_type' not in settings and 'double_sweep' in settings:
            settings['sweep_type'] = 'double' if bool(settings['double_sweep']) else 'single'
        if 'frequencies' not in settings and 'frequency_hz' in settings:
            settings['frequencies'] = str(settings['frequency_hz'])
        super().__init__(settings, output_root, output_relative, runner, fallback_root)
        self.cmu_channel = resolve_cmu_channel(
            self.settings, self.cmu_channel, self.log)
        self.settings['cmu_channel'] = self.cmu_channel
        self.frequencies = self._parse_frequencies(self.settings.get('frequencies', '100k'))
        self.ac_level = self.ac_level_mv / 1000.0
        self.cmu_calibration = settings.get("cmu_calibration", {}) or {}
        self._validate_settings()

    def _calibration_gaps(self):
        """Return missing calibration coverage by type for current channel/frequencies."""
        # Coverage is checked per selected frequency because CMU open/short/load corrections are frequency-specific.
        selected_keys = {freq_key(f) for f in self.frequencies}
        calibrated = calibrated_frequencies(self.cmu_calibration, self.cmu_channel)
        missing = {
            corr_type: selected_keys - {freq_key(f) for f in calibrated[corr_type]}
            for corr_type in ("open", "short", "load")
        }
        missing["phase"] = not phase_compensated(self.cmu_calibration, self.cmu_channel)
        return missing

    def _report_calibration_coverage(self):
        missing = self._calibration_gaps()
        msgs = []
        for corr_type in ("open", "short", "load"):
            miss = missing[corr_type]
            if not miss:
                continue
            freq_list = sorted(float(k) for k in miss)
            labels = ", ".join(freq_label(f) for f in freq_list)
            msgs.append(f"{corr_type}: [{labels}]")
        if missing["phase"]:
            msgs.append("phase: missing")

        if not msgs:
            self.log(f"CMU calibration coverage OK on channel {self.cmu_channel}.")
            return

        joined = "; ".join(msgs)
        if self.require_cmu_calibration:
            raise ValueError(
                f"Missing required CMU calibration on channel {self.cmu_channel}: {joined}"
            )
        self.log(
            f"Warning: incomplete CMU calibration coverage on channel {self.cmu_channel}: {joined}"
        )

    @staticmethod
    def _parse_frequencies(text):
        freqs = sorted(parse_si_list(str(text)))
        if not freqs:
            raise ValueError("At least one frequency is required.")
        for f in freqs:
            if not (1e3 <= f <= 5e6):
                raise ValueError(f"Frequency {f:.6g} Hz out of range [1 kHz, 5 MHz].")
        return freqs

    def _validate_settings(self):
        if self.sweep_type not in ('single', 'double', 'butterfly'):
            raise ValueError(f"Invalid sweep_type: {self.sweep_type!r}")
        if self.points < 1:
            raise ValueError("C-V points must be >= 1")
        if self.sweep_type == 'butterfly' and self.start_bias == self.stop_bias:
            raise ValueError("For butterfly sweep, Start Bias (Vmax) and Stop Bias (Vmin) must differ.")
        if self.sweep_type != 'butterfly' and self.start_bias == self.stop_bias and self.points > 1:
            raise ValueError("Start Bias and Stop Bias are equal; use points=1 for spot-like measurement.")
        if not (0.0 <= self.ac_level_mv <= 250.0):
            raise ValueError("AC Level must be between 0 and 250 mV for CMU.")
        if self.integration_mode not in (0, 1, 2):
            raise ValueError("Integration Mode must be Auto (0), Manual (1), or PLC (2).")
        if self.integration_value < 1:
            raise ValueError("Integration Value must be >= 1.")

    def _compute_butterfly_segments(self):
        """Split 0 → Vmax → Vmin → 0 into 3 (start, stop, npoints) legs.

        self.start_bias = Vmax (positive peak), self.stop_bias = Vmin (negative peak).
        Points are distributed proportionally to each leg's voltage span.
        Legs 2 and 3 share a boundary with the prior leg (their first point is
        skipped on concatenation), so the pool is self.points + 2.
        """
        vmax = self.start_bias
        vmin = self.stop_bias
        spans = [abs(vmax), abs(vmax - vmin), abs(vmin)]
        total_span = sum(spans)
        if total_span == 0:
            raise ValueError("Butterfly sweep: all voltage spans are zero.")
        # Allocate the requested visible points in proportion to voltage span, then remove shared leg boundaries.
        pool = self.points + 2  # +2 to account for 2 boundary dedup skips
        raw = [max(2, round(pool * s / total_span)) for s in spans]
        # Ensure sum(raw) - 2 = self.points by adjusting middle leg
        diff = (self.points + 2) - sum(raw)
        raw[1] = max(2, raw[1] + diff)
        return [
            (0.0,  vmax, raw[0]),
            (vmax, vmin, raw[1]),
            (vmin, 0.0,  raw[2]),
        ]

    def _is_z_theta_mode(self) -> bool:
        return self.cmu_mode in (B1500_CMUM_Z_TDEG, B1500_CMUM_Z_TRAD)

    def measure(self, device):
        b1500 = self.b1500
        self._report_calibration_coverage()
        primary_name, monitor_name = get_cmu_mode_components(self.cmu_mode)
        primary_label = format_cmu_component_label(primary_name)
        monitor_label = format_cmu_component_label(monitor_name)

        freq_str = ", ".join(freq_label(f) for f in self.frequencies)
        self.log(f"Starting C-V sweep on {device.name}")
        self.log(
            f"CMU setup: channel={self.cmu_channel}, output={get_cmu_mode_name(self.cmu_mode)}, "
            f"sweep={self.sweep_type}, freq=[{freq_str}], Vac={self.ac_level_mv:.1f} mV"
        )

        self.check_stop(b1500)
        b1500.reset()
        b1500.set_timeout(10000)
        b1500.enable_error_detect(True)
        # Leave the CMU at the final bias level until the explicit cleanup in perform_cv_sweep.
        b1500.stop_mode(B1500_STOP_DISABLE, B1500_LAST_STOP)

        results = self.perform_cv_sweep(b1500, device, primary_name, monitor_name, primary_label, monitor_label)

        columns = ["Frequency_Hz", "Bias_V", primary_label, monitor_label, "Time_sec",
                   f"Status_{primary_name}", f"Status_{monitor_name}", "Status_Combined"]
        self.save_measurement_outputs(results, "CVSweep", device, columns)
        self.log(f"C-V sweep completed for {device.name}")

    def perform_cv_sweep(self, b1500, device, primary_name, monitor_name, primary_label, monitor_label):
        self.check_stop(b1500)

        # Curves are named by position in the frequency list, one curve per sweep.
        labels = [freq_label(freq) for freq in self.frequencies]
        if self._is_z_theta_mode():
            self.runner.configure_plot(f"C-V Sweep - {device.name}",
                                       z_theta_plots(labels, [f"C{i % 10}" for i in range(len(labels))],
                                                     "Bias (V)", "linear",
                                                     self.cmu_mode == B1500_CMUM_Z_TDEG))
        else:
            # Other CMU modes stream two named parameters directly from the B1500 descriptor table.
            elements = []
            for i, label in enumerate(labels):
                elements.append(Curve(f"p_{i}", color=f'C{i % 10}', line_style="solid",
                                      legend_label=f"{primary_label} @ {label}"))
                elements.append(Curve(f"m_{i}", color=f'C{i % 10}', line_style="dash", yaxis=1,
                                      legend_label=f"{monitor_label} @ {label}"))
            self.runner.configure_plot(f"C-V Sweep - {device.name}", [
                PlotDef("cv", xlabel="Bias (V)", ylabels=(primary_label, monitor_label),
                        elements=elements),
            ])

        nonzero_statuses = set()
        all_results = []
        self.report_progress(0, len(self.frequencies), 'Frequency sweeps')

        try:
            # Start from all switches open so the selected CMU channel is the only active path.
            b1500.set_switch(B1500_CH_ALL, False)
            b1500.set_switch(self.cmu_channel, True)
            b1500.set_cmu_integ(self.integration_mode, self.integration_value)
            b1500.force_cmu_ac_level(self.cmu_channel, self.ac_level)

            for index, freq in enumerate(self.frequencies):
                self.check_stop(b1500)
                b1500.set_cmu_freq(self.cmu_channel, freq)
                if self.sweep_type == 'butterfly':
                    rows = self._run_butterfly_sweep(b1500, index, freq, nonzero_statuses)
                else:
                    rows = self._run_standard_sweep(b1500, index, freq, nonzero_statuses)

                for row in rows:
                    # Prefix every row with frequency so the CSV stays self-describing after concatenating sweeps.
                    all_results.append([freq] + row)
                self.report_progress(index + 1, len(self.frequencies), 'Frequency sweeps')

        finally:
            try:
                # Cleanup runs on success, instrument error, or user abort to avoid leaving the DUT biased.
                b1500.zero_output(B1500_CH_ALL)
            except Exception as e:
                self.log(f"Warning: failed to zero outputs after C-V sweep: {e}")
            try:
                b1500.set_switch(B1500_CH_ALL, False)
            except Exception as e:
                self.log(f"Warning: failed to open switches after C-V sweep: {e}")

        if all_results:
            p_vals = [row[2] for row in all_results]
            m_vals = [row[3] for row in all_results]
            self.log(
                f"{primary_name} range: {min(p_vals):.6g} to {max(p_vals):.6g}; "
                f"{monitor_name} range: {min(m_vals):.6g} to {max(m_vals):.6g}"
            )
        self.log(f"Collected {len(all_results)} C-V data points")
        return all_results

    def _plot_point(self, curve, source_v, para1, para2, freq):
        """Add one bias point to curve `curve` of the figure set up in perform_cv_sweep."""
        if self._is_z_theta_mode():
            append_z_theta_point(self.runner.plot, curve, source_v, para1, para2, freq,
                                 self.cmu_mode == B1500_CMUM_Z_TDEG)
        else:
            self.runner.plot.append_point(f"p_{curve}", source_v, para1)
            self.runner.plot.append_point(f"m_{curve}", source_v, para2)

    def _run_standard_sweep(self, b1500, curve, freq, nonzero_statuses):
        """Single or double linear sweep with per-point live SCPI streaming."""
        mode = B1500_SWP_VF_DBLLIN if self.sweep_type == 'double' else B1500_SWP_VF_SGLLIN
        rows = []

        b1500.reset_timestamp()
        b1500.set_cv(
            self.cmu_channel, mode,
            self.start_bias, self.stop_bias, self.points,
            hold=self.hold_time, delay=self.delay_time, second_delay=self.second_delay,
        )

        def on_point(_, source_v, para1, para2, time_s, s1, s2):
            # stream_cv_sweep calls this once per bias point with source voltage, two CMU values, time, and statuses.
            self.check_stop(b1500)
            self._plot_point(curve, source_v, para1, para2, freq)
            report_cmu_status(self.runner, self.cmu_channel, nonzero_statuses, s1, s2)
            rows.append([source_v, para1, para2, time_s, s1, s2, s1 | s2])

        b1500.stream_cv_sweep(self.cmu_channel, self.cmu_mode, self.measurement_range, on_point)
        return rows

    def _run_butterfly_sweep(self, b1500, curve, freq, nonzero_statuses):
        """Three-segment butterfly sweep (0→Vmax→Vmin→0) with per-point live SCPI streaming."""
        segments = self._compute_butterfly_segments()
        rows = []

        for seg_idx, (seg_start, seg_stop, npts) in enumerate(segments):
            self.check_stop(b1500)
            # Only the first leg applies hold_time; later legs continue the already-biased waveform.
            hold = self.hold_time if seg_idx == 0 else 0.0
            first_point_skip = seg_idx > 0  # skip shared boundary with prior leg

            b1500.reset_timestamp()
            b1500.set_cv(
                self.cmu_channel, B1500_SWP_VF_SGLLIN,
                seg_start, seg_stop, npts,
                hold=hold, delay=self.delay_time, second_delay=self.second_delay,
            )

            def on_point(step, source_v, para1, para2, time_s, s1, s2, _skip=first_point_skip):
                if _skip and step == 0:
                    # Segment boundaries duplicate the previous endpoint; skip them for clean CSV/plot traces.
                    return
                self.check_stop(b1500)
                self._plot_point(curve, source_v, para1, para2, freq)
                report_cmu_status(self.runner, self.cmu_channel, nonzero_statuses, s1, s2)
                rows.append([source_v, para1, para2, time_s, s1, s2, s1 | s2])

            b1500.stream_cv_sweep(self.cmu_channel, self.cmu_mode, self.measurement_range, on_point)

        return rows
