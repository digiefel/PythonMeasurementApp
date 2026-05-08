import math

from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, parameter, action
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
    describe_status_bits,
    format_cmu_component_label,
    get_cmu_mode_components,
    get_cmu_mode_name,
)
from si_utils import parse_si_list, format_si_value


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

    Data is streamed point-by-point via raw VISA SCPI (FMT 5,0 + XE) for live plotting.

    When cmu_mode is Z-Theta (mode 11 or 10), Rp and Cp are computed from Z and Theta
    per-point and plotted live in a 2×2 panel layout alongside Z and Theta.
    """

    NAME = "CVSweep"
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('cmu_channel', 'CMU Channel', -1, Choice(B1500_CMU_CHANNELS, int)),
        parameter('sweep_type', 'Sweep Type', 'single', Choice(CV_SWEEP_TYPES, str)),
        parameter('cmu_mode', 'C-V Meas Output', B1500_CMUM_Z_TDEG, Choice(B1500_CMU_MEASUREMENT_MODES, int)),
        parameter('start_bias', 'Start Bias (V)', -2.0, float),
        parameter('stop_bias', 'Stop Bias (V)', 2.0, float),
        parameter('points', 'Points', 101, int),
        parameter('measurement_range', 'MFCMU Meas Range', B1500_AUTO_RANGE, Choice(B1500_CMU_SWEEP_RANGES, float)),
        parameter('ac_level_mv', 'AC Level (mV)', 30.0, float),
        parameter('frequencies', 'Frequencies (e.g. 100k, 1M)', '100k', str),
        parameter('integration_mode', 'Integration Mode', 0, Choice(B1500_CMU_INTEGRATION_MODES, int)),
        parameter('integration_value', 'Integration (manual/PLC)', 1, int),
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
        self.frequencies = self._parse_frequencies(self.settings.get('frequencies', '100k'))
        self.ac_level = self.ac_level_mv / 1000.0
        self.cmu_calibration = settings.get("cmu_calibration", {}) or {}
        self._validate_settings()

    @staticmethod
    def _freq_key(freq_hz: float) -> str:
        # Use stable text keys for calibration JSON; raw float strings can differ by representation.
        return f"{float(freq_hz):.12g}"

    def _entry_freq_keys(self, entry: dict) -> set[str]:
        if not isinstance(entry, dict):
            return set()
        # Calibration data can be stored as a per-frequency map or as an older single-frequency entry.
        by_freq = entry.get("results_by_frequency", {})
        if isinstance(by_freq, dict) and by_freq:
            keys = set()
            for fk in by_freq.keys():
                try:
                    keys.add(self._freq_key(float(fk)))
                except Exception:
                    continue
            return keys
        freq_hz = entry.get("frequency_hz")
        if freq_hz is None:
            return set()
        try:
            return {self._freq_key(float(freq_hz))}
        except Exception:
            return set()

    def _phase_entry_valid(self, entry: dict) -> bool:
        if not isinstance(entry, dict):
            return False
        result = entry.get("result")
        if isinstance(result, dict):
            try:
                # Newer phase entries store the instrument return code under result.result; zero means OK.
                return int(result.get("result", 0)) == 0
            except Exception:
                return False
        return bool(result)

    def _calibration_gaps(self):
        """Return missing calibration coverage by type for current channel/frequencies."""
        channel_data = self.cmu_calibration.get(str(self.cmu_channel), {})
        # Coverage is checked per selected frequency because CMU open/short/load corrections are frequency-specific.
        selected_keys = {self._freq_key(f) for f in self.frequencies}

        missing = {
            "open": set(selected_keys),
            "short": set(selected_keys),
            "load": set(selected_keys),
            "phase": not self._phase_entry_valid(channel_data.get("phase")),
        }

        for corr_type in ("open", "short", "load"):
            present = self._entry_freq_keys(channel_data.get(corr_type, {}))
            missing[corr_type] = selected_keys - present

        return missing

    def _report_calibration_coverage(self):
        missing = self._calibration_gaps()
        msgs = []
        for corr_type in ("open", "short", "load"):
            miss = missing[corr_type]
            if not miss:
                continue
            freq_list = sorted(float(k) for k in miss)
            labels = ", ".join(self._freq_label(f) for f in freq_list)
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

    @staticmethod
    def _freq_label(freq_hz):
        return f"{format_si_value(freq_hz)}Hz"

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

    def _expected_points(self):
        if self.sweep_type == 'double':
            # Double sweep reuses the turnaround endpoint, so the streamed point count is N forward + N-1 back.
            return max(1, (2 * self.points) - 1)
        return self.points

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

    @staticmethod
    def _rp_cp_from_z_theta(Z: float, theta: float, freq: float, is_degrees: bool):
        """Compute parallel-RC equivalent from impedance magnitude and phase angle.

        Returns (Rp, Cp) in Ohm and Farad respectively, or (nan, nan) on degenerate input.
        """
        theta_rad = math.radians(theta) if is_degrees else theta
        omega = 2.0 * math.pi * freq
        cos_t = math.cos(theta_rad)
        sin_t = math.sin(theta_rad)
        if abs(cos_t) < 1e-15 or abs(Z) < 1e-30 or omega < 1e-15:
            return float('nan'), float('nan')
        # Convert the series-like Z/theta stream into the parallel RC values users usually inspect.
        return Z / cos_t, -sin_t / (omega * Z)

    def measure(self, device):
        b1500 = self.b1500
        self._report_calibration_coverage()
        primary_name, monitor_name = get_cmu_mode_components(self.cmu_mode)
        primary_label = format_cmu_component_label(primary_name)
        monitor_label = format_cmu_component_label(monitor_name)

        freq_str = ", ".join(self._freq_label(f) for f in self.frequencies)
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

        is_z_theta = self._is_z_theta_mode()
        if is_z_theta:
            theta_unit = "deg" if self.cmu_mode == B1500_CMUM_Z_TDEG else "rad"
            columns = [
                "Frequency_Hz",
                "Bias_V",
                primary_label,
                monitor_label,
                "Rp (Ohm)",
                "Cp (F)",
                "Time_sec",
                f"Status_{primary_name}",
                f"Status_{monitor_name}",
                "Status_Combined",
            ]
        else:
            columns = [
                "Frequency_Hz",
                "Bias_V",
                primary_label,
                monitor_label,
                "Time_sec",
                f"Status_{primary_name}",
                f"Status_{monitor_name}",
                "Status_Combined",
            ]

        self.save_measurement_outputs(results, "CVSweep", device, columns)
        self.log(f"C-V sweep completed for {device.name}")

    def perform_cv_sweep(self, b1500, device, primary_name, monitor_name, primary_label, monitor_label):
        self.check_stop(b1500)

        is_z_theta = self._is_z_theta_mode()
        is_degrees = self.cmu_mode == B1500_CMUM_Z_TDEG
        theta_unit = "deg" if is_degrees else "rad"

        if is_z_theta:
            # Z-theta mode is special: the instrument streams Z and angle, while Rp/Cp are derived locally.
            elements_z, elements_theta, elements_rp, elements_cp = [], [], [], []
            for i, freq in enumerate(self.frequencies):
                color = f'C{i % 10}'
                tag = self._freq_label(freq)
                elements_z.append(    Curve(f"z_{tag}",     color=color, legend_label=f"Z @ {tag}"))
                elements_theta.append(Curve(f"theta_{tag}", color=color, legend_label=f"θ @ {tag}"))
                elements_rp.append(   Curve(f"rp_{tag}",    color=color, legend_label=f"Rp @ {tag}"))
                elements_cp.append(   Curve(f"cp_{tag}",    color=color, legend_label=f"Cp @ {tag}"))

            self.runner.configure_plot(f"C-V Sweep - {device.name}", [
                    PlotDef("z",     row=0, col=0, xlabel="Bias (V)", ylabels=("Z (Ohm)",),
                            elements=elements_z),
                    PlotDef("theta", row=0, col=1, xlabel="Bias (V)", ylabels=(f"Theta ({theta_unit})",),
                            xlink="z", elements=elements_theta),
                    PlotDef("rp",    row=1, col=0, xlabel="Bias (V)", ylabels=("Rp (Ohm)",),
                            xlink="z", elements=elements_rp),
                    PlotDef("cp",    row=1, col=1, xlabel="Bias (V)", ylabels=("Cp (F)",),
                            xlink="z", elements=elements_cp),
                    ],
                    row_ratios=(1.0, 1.0), column_ratios=(1.0, 1.0)
                )
        else:
            # Other CMU modes stream two named parameters directly from the B1500 descriptor table.
            elements = []
            for i, freq in enumerate(self.frequencies):
                color = f'C{i % 10}'
                tag = self._freq_label(freq)
                elements.append(Curve(f"p_{tag}", color=color, line_style="solid",
                                      legend_label=f"{primary_label} @ {tag}"))
                elements.append(Curve(f"m_{tag}", color=color, line_style="dash", yaxis=1,
                                      legend_label=f"{monitor_label} @ {tag}"))

            self.runner.configure_plot(f"C-V Sweep - {device.name}", [
                PlotDef("cv", xlabel="Bias (V)", ylabels=(primary_label, monitor_label),
                        elements=elements),
            ])

        nonzero_statuses = set()
        all_results = []

        try:
            # Start from all switches open so the selected CMU channel is the only active path.
            b1500.set_switch(B1500_CH_ALL, False)
            b1500.set_switch(self.cmu_channel, True)
            b1500.set_cmu_integ(self.integration_mode, self.integration_value)
            b1500.force_cmu_ac_level(self.cmu_channel, self.ac_level)

            for freq in self.frequencies:
                self.check_stop(b1500)
                b1500.set_cmu_freq(self.cmu_channel, freq)
                tag = self._freq_label(freq)

                # Plot source names are frequency-tagged so multiple frequency sweeps can share one figure.
                if is_z_theta:
                    p_source  = f"z_{tag}"
                    m_source  = f"theta_{tag}"
                    rp_source = f"rp_{tag}"
                    cp_source = f"cp_{tag}"
                else:
                    p_source  = f"p_{tag}"
                    m_source  = f"m_{tag}"
                    rp_source = None
                    cp_source = None

                if self.sweep_type == 'butterfly':
                    rows = self._run_butterfly_sweep(
                        b1500, p_source, m_source, nonzero_statuses,
                        rp_source=rp_source, cp_source=cp_source,
                        freq=freq, is_degrees=is_degrees,
                    )
                else:
                    rows = self._run_standard_sweep(
                        b1500, p_source, m_source, nonzero_statuses,
                        rp_source=rp_source, cp_source=cp_source,
                        freq=freq, is_degrees=is_degrees,
                    )

                for row in rows:
                    # Prefix every row with frequency so the CSV stays self-describing after concatenating sweeps.
                    all_results.append([freq] + row)

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
            # The summary intentionally uses the same column positions for all modes after Frequency/Bias.
            p_vals = [row[2] for row in all_results]
            m_vals = [row[3] for row in all_results]
            self.log(
                f"{primary_name} range: {min(p_vals):.6g} to {max(p_vals):.6g}; "
                f"{monitor_name} range: {min(m_vals):.6g} to {max(m_vals):.6g}"
            )
            if is_z_theta:
                rp_vals = [row[4] for row in all_results if math.isfinite(row[4])]
                cp_vals = [row[5] for row in all_results if math.isfinite(row[5])]
                if rp_vals:
                    self.log(f"Rp range: {min(rp_vals):.6g} to {max(rp_vals):.6g} Ohm")
                if cp_vals:
                    self.log(f"Cp range: {min(cp_vals):.6g} to {max(cp_vals):.6g} F")
        self.log(f"Collected {len(all_results)} C-V data points")
        return all_results

    def _run_standard_sweep(self, b1500, p_source, m_source, nonzero_statuses, *,
                             rp_source=None, cp_source=None, freq=None, is_degrees=True):
        """Single or double linear sweep with per-point live SCPI streaming."""
        mode = B1500_SWP_VF_DBLLIN if self.sweep_type == 'double' else B1500_SWP_VF_SGLLIN
        expected = self._expected_points()
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
            self.runner.plot.append_point(p_source, source_v, para1)
            self.runner.plot.append_point(m_source, source_v, para2)
            self._report_status(nonzero_statuses, s1, s2)
            if rp_source is not None:
                # Only Z-theta sweeps have derived Rp/Cp columns and plot traces.
                rp, cp = self._rp_cp_from_z_theta(para1, para2, freq, is_degrees)
                if math.isfinite(rp):
                    self.runner.plot.append_point(rp_source, source_v, rp)
                if math.isfinite(cp):
                    self.runner.plot.append_point(cp_source, source_v, cp)
                rows.append([source_v, para1, para2, rp, cp, time_s, s1, s2, s1 | s2])
            else:
                rows.append([source_v, para1, para2, time_s, s1, s2, s1 | s2])

        b1500.stream_cv_sweep(self.cmu_channel, self.cmu_mode, self.measurement_range, expected, on_point)
        return rows

    def _run_butterfly_sweep(self, b1500, p_source, m_source, nonzero_statuses, *,
                              rp_source=None, cp_source=None, freq=None, is_degrees=True):
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
                self.runner.plot.append_point(p_source, source_v, para1)
                self.runner.plot.append_point(m_source, source_v, para2)
                self._report_status(nonzero_statuses, s1, s2)
                if rp_source is not None:
                    rp, cp = self._rp_cp_from_z_theta(para1, para2, freq, is_degrees)
                    if math.isfinite(rp):
                        self.runner.plot.append_point(rp_source, source_v, rp)
                    if math.isfinite(cp):
                        self.runner.plot.append_point(cp_source, source_v, cp)
                    rows.append([source_v, para1, para2, rp, cp, time_s, s1, s2, s1 | s2])
                else:
                    rows.append([source_v, para1, para2, time_s, s1, s2, s1 | s2])

            b1500.stream_cv_sweep(self.cmu_channel, self.cmu_mode, self.measurement_range, npts, on_point)

        return rows

    def _report_status(self, seen, s1, s2):
        # CMU streaming reports para1/para2 status separately; report each unique status once to the UI.
        if s1 and (self.cmu_channel, 8, s1) not in seen:
            seen.add((self.cmu_channel, 8, s1))
            self.runner.report_status({
                "channel": self.cmu_channel, "data_type": 8, "status": s1,
                "desc": describe_status_bits(s1),
            })
        if s2 and (self.cmu_channel, 9, s2) not in seen:
            seen.add((self.cmu_channel, 9, s2))
            self.runner.report_status({
                "channel": self.cmu_channel, "data_type": 9, "status": s2,
                "desc": describe_status_bits(s2),
            })
