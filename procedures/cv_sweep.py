from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, ValueList, parameter
from instrumentio.constants import (
    B1500_CMU_CHANNELS,
    B1500_CMU_INTEGRATION_MODES,
    B1500_CMU_MEASUREMENT_MODES,
    B1500_CMU_SWEEP_RANGES,
)
from instrumentio.codes import (
    B1500_AUTO_RANGE,
    B1500_CH_ALL,
    B1500_CMUM_Z_TDEG,
    B1500_CMUM_Z_TRAD,
    B1500_LAST_STOP,
    B1500_STOP_DISABLE,
)
from instrumentio.descriptors import (
    format_cmu_component_label,
    get_cmu_mode_components,
    get_cmu_mode_name,
)
from procedures._cmu import (
    CMUCalibration,
    CV_SWEEP_TYPES,
    append_z_theta_point,
    freq_label,
    parse_cmu_frequencies,
    report_cmu_status,
    resolve_cmu_channel,
    run_cv_sweep,
    validate_cv_sweep,
    z_theta_plots,
)


class CVSweepProcedure(CMUCalibration, MeasurementProcedure):
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
    The calibration buttons measure at the sweep frequencies. Every run uses the
    phase compensation and corrections the instrument holds, and the CSV header
    names them (cmu_correction). Hover over settings for their meanings.

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

    @classmethod
    def cmu_calibration_frequencies(cls, settings):
        return parse_cmu_frequencies(settings.get('frequencies', '100k'))

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
        self.frequencies = parse_cmu_frequencies(self.settings.get('frequencies', '100k'))
        self.ac_level = self.ac_level_mv / 1000.0
        self.cmu_calibration = settings.get("cmu_calibration", {}) or {}
        self._validate_settings()

    def _validate_settings(self):
        validate_cv_sweep(self.sweep_type, self.start_bias, self.stop_bias, self.points)
        if not (0.0 <= self.ac_level_mv <= 250.0):
            raise ValueError("AC Level must be between 0 and 250 mV for CMU.")
        if self.integration_mode not in (0, 1, 2):
            raise ValueError("Integration Mode must be Auto (0), Manual (1), or PLC (2).")
        if self.integration_value < 1:
            raise ValueError("Integration Value must be >= 1.")

    def _is_z_theta_mode(self) -> bool:
        return self.cmu_mode in (B1500_CMUM_Z_TDEG, B1500_CMUM_Z_TRAD)

    def measure(self, device):
        b1500 = self.b1500
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
        # *RST stops the use of the calibration data; switch it back on.
        self.apply_cmu_calibration(b1500)
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

                def on_point(source_v, para1, para2, time_s, s1, s2, _curve=index, _freq=freq):
                    self.check_stop(b1500)
                    self._plot_point(_curve, source_v, para1, para2, _freq)
                    report_cmu_status(self.runner, self.cmu_channel, nonzero_statuses, s1, s2)
                    # Every row starts with the frequency, so the CSV stays self-describing after concatenating sweeps.
                    all_results.append([_freq, source_v, para1, para2, time_s, s1, s2, s1 | s2])

                run_cv_sweep(b1500, self.cmu_channel, self.cmu_mode, self.measurement_range, self.sweep_type,
                             self.start_bias, self.stop_bias, self.points,
                             self.hold_time, self.delay_time, self.second_delay, on_point)
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
