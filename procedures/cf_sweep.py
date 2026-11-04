import math

from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, ValueList, parameter
from procedures._cmu import (
    calibrated_frequencies,
    freq_label,
    phase_compensated,
    report_cmu_status,
    resolve_cmu_channel,
    rp_cp_from_z_theta,
)
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
from si_utils import parse_si_list, parse_si_value


CF_SPACINGS = (
    ('log', 'Logarithmic'),
    ('linear', 'Linear'),
)


class CfSweepProcedure(MeasurementProcedure):
    """CMU-based capacitance-frequency sweep for B1500, repeated at several DC biases.

    The counterpart of CVSweep: here the DC bias is held constant while the AC
    frequency steps from Start to Stop, and the sweep is repeated once per bias.
    Biases run in the order typed (not sorted), stepping directly from one to
    the next, so history-dependent devices see a defined bias sequence.

    At each bias the CMU waits for the hold time, then measures every frequency
    point after the delay time. All traces are plotted against frequency, one
    colour per bias, and the CSV always includes a Bias_V column.

    When cmu_mode is Z-Theta, Rp and Cp are computed per point at the measured
    frequency and plotted in a 2×2 layout alongside Z and Theta.

    Open/short/load correction uses the calibration stored for the channel (for
    example by the CVSweep calibration buttons). The instrument interpolates
    correction data between calibrated frequencies, so coverage is checked
    against the sweep's frequency range.
    """

    # TODO: CMU calibration buttons. The shared UI handler reads a 'frequencies' list field, which this procedure does not have.
    NAME = "CfSweep"
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('cmu_channel', 'CMU Channel', -1, Choice(B1500_CMU_CHANNELS, int)),
        parameter('cmu_mode', 'C-f Meas Output', B1500_CMUM_Z_TDEG, Choice(B1500_CMU_MEASUREMENT_MODES, int), help='Selects the impedance representation returned by the CMU. Z–Theta modes also produce derived parallel resistance and capacitance plots.'),
        parameter('biases', 'DC Biases (V)', '0', ValueList, help="Comma-separated DC bias values in volts, e.g. '-1, 0, 1'. One frequency sweep per bias, run in the order typed."),
        parameter('start_frequency', 'Start Frequency (Hz)', '1k', str, help="SI prefixes are accepted, e.g. '1k'. Range 1 kHz to 5 MHz."),
        parameter('stop_frequency', 'Stop Frequency (Hz)', '5M', str, help="SI prefixes are accepted, e.g. '5M'. Range 1 kHz to 5 MHz."),
        parameter('points', 'Points', 51, int, help='Frequency points per bias, 1 to 1001.'),
        parameter('spacing', 'Frequency Spacing', 'log', Choice(CF_SPACINGS, str)),
        parameter('measurement_range', 'MFCMU Meas Range', B1500_AUTO_RANGE, Choice(B1500_CMU_SWEEP_RANGES, float)),
        parameter('ac_level_mv', 'AC Level (mV)', 30.0, float, help='AC excitation superimposed on the constant DC bias.'),
        parameter('integration_mode', 'Integration Mode', 0, Choice(B1500_CMU_INTEGRATION_MODES, int)),
        parameter('integration_value', 'Integration (manual/PLC)', 1, int, help='In PLC mode, integration lasts this many power line cycles. One PLC is 20 ms at 50 Hz.'),
        parameter('hold_time', 'Hold Time (s)', 0.0, float, help='Wait at each new bias before the first frequency point. 0 to 655.35 s.'),
        parameter('delay_time', 'Delay Time (s)', 0.0, float, help='Wait after each frequency step before measuring. 0 to 655.35 s.'),
        parameter('step_delay', 'Step Delay (s)', 0.0, float, help='Minimum time from the start of one measurement to the next frequency step. 0 to 1 s.'),
        parameter('require_cmu_calibration', 'Require Calibration', False, bool),
    )

    def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
        super().__init__(settings, output_root, output_relative, runner, fallback_root)
        self.cmu_channel = resolve_cmu_channel(
            self.settings, self.cmu_channel, self.log if runner is not None else None)
        self.settings['cmu_channel'] = self.cmu_channel
        self.bias_list = parse_si_list(str(self.biases))
        self.start_hz = parse_si_value(str(self.start_frequency))
        self.stop_hz = parse_si_value(str(self.stop_frequency))
        self.ac_level = self.ac_level_mv / 1000.0
        self.cmu_calibration = settings.get("cmu_calibration", {}) or {}

    def _report_calibration_coverage(self):
        # Correction is interpolated between calibrated frequencies, so each type must span the sweep range.
        f_lo, f_hi = sorted((self.start_hz, self.stop_hz))
        msgs = []
        for corr_type, freqs in calibrated_frequencies(self.cmu_calibration, self.cmu_channel).items():
            if not freqs:
                msgs.append(f"{corr_type}: none")
            elif freqs[0] > f_lo or freqs[-1] < f_hi:
                msgs.append(f"{corr_type}: {freq_label(freqs[0])}–{freq_label(freqs[-1])} "
                            f"does not span {freq_label(f_lo)}–{freq_label(f_hi)}")
        if not phase_compensated(self.cmu_calibration, self.cmu_channel):
            msgs.append("phase: missing")

        if not msgs:
            self.log(f"CMU calibration coverage OK on channel {self.cmu_channel}.")
            return
        joined = "; ".join(msgs)
        if self.require_cmu_calibration:
            raise ValueError(f"Missing required CMU calibration on channel {self.cmu_channel}: {joined}")
        self.log(f"Warning: incomplete CMU calibration coverage on channel {self.cmu_channel}: {joined}")

    @staticmethod
    def _bias_label(bias_v):
        return f"{bias_v:+g}V"

    def measure(self, device):
        b1500 = self.b1500
        self._report_calibration_coverage()
        primary_name, monitor_name = get_cmu_mode_components(self.cmu_mode)
        primary_label = format_cmu_component_label(primary_name)
        monitor_label = format_cmu_component_label(monitor_name)
        is_z_theta = self.cmu_mode in (B1500_CMUM_Z_TDEG, B1500_CMUM_Z_TRAD)
        is_degrees = self.cmu_mode == B1500_CMUM_Z_TDEG

        bias_str = ", ".join(self._bias_label(v) for v in self.bias_list)
        self.log(f"Starting C-f sweep on {device.name}")
        self.log(
            f"CMU setup: channel={self.cmu_channel}, output={get_cmu_mode_name(self.cmu_mode)}, "
            f"freq={freq_label(self.start_hz)}→{freq_label(self.stop_hz)} ({self.points} pts, {self.spacing}), "
            f"bias=[{bias_str}], Vac={self.ac_level_mv:.1f} mV"
        )

        # Plot source names are bias-tagged so all bias sweeps share one figure.
        xscale = "log" if self.spacing == 'log' else "linear"
        if is_z_theta:
            theta_unit = "deg" if is_degrees else "rad"
            panels = {"z": [], "theta": [], "rp": [], "cp": []}
            for i, bias in enumerate(self.bias_list):
                color = f'C{i % 10}'
                tag = self._bias_label(bias)
                panels["z"].append(    Curve(f"z_{tag}",     color=color, legend_label=f"Z @ {tag}"))
                panels["theta"].append(Curve(f"theta_{tag}", color=color, legend_label=f"θ @ {tag}"))
                panels["rp"].append(   Curve(f"rp_{tag}",    color=color, legend_label=f"Rp @ {tag}"))
                panels["cp"].append(   Curve(f"cp_{tag}",    color=color, legend_label=f"Cp @ {tag}"))
            self.runner.configure_plot(f"C-f Sweep - {device.name}", [
                PlotDef("z",     row=0, col=0, xlabel="Frequency (Hz)", ylabels=("Z (Ohm)",),
                        xscale=xscale, yscales=("log",), elements=panels["z"]),
                PlotDef("theta", row=0, col=1, xlabel="Frequency (Hz)", ylabels=(f"Theta ({theta_unit})",),
                        xscale=xscale, xlink="z", elements=panels["theta"]),
                PlotDef("rp",    row=1, col=0, xlabel="Frequency (Hz)", ylabels=("Rp (Ohm)",),
                        xscale=xscale, xlink="z", elements=panels["rp"]),
                PlotDef("cp",    row=1, col=1, xlabel="Frequency (Hz)", ylabels=("Cp (F)",),
                        xscale=xscale, xlink="z", elements=panels["cp"]),
            ], row_ratios=(1.0, 1.0), column_ratios=(1.0, 1.0))
            columns = ["Bias_V", "Frequency_Hz", primary_label, monitor_label, "Rp (Ohm)", "Cp (F)"]
        else:
            elements = []
            for i, bias in enumerate(self.bias_list):
                color = f'C{i % 10}'
                tag = self._bias_label(bias)
                elements.append(Curve(f"p_{tag}", color=color, line_style="solid",
                                      legend_label=f"{primary_label} @ {tag}"))
                elements.append(Curve(f"m_{tag}", color=color, line_style="dash", yaxis=1,
                                      legend_label=f"{monitor_label} @ {tag}"))
            self.runner.configure_plot(f"C-f Sweep - {device.name}", [
                PlotDef("cf", xlabel="Frequency (Hz)", ylabels=(primary_label, monitor_label),
                        xscale=xscale, elements=elements),
            ])
            columns = ["Bias_V", "Frequency_Hz", primary_label, monitor_label]
        columns += ["Bias_Monitor_V", "Time_sec",
                    f"Status_{primary_name}", f"Status_{monitor_name}", "Status_Combined"]

        self.check_stop(b1500)
        b1500.reset()
        b1500.set_timeout(10000)
        b1500.enable_error_detect(True)
        # Leave the CMU at the last bias between sweeps; the finally block below zeroes it.
        b1500.stop_mode(B1500_STOP_DISABLE, B1500_LAST_STOP)

        results = []
        nonzero_statuses = set()
        self.report_progress(0, len(self.bias_list), 'Bias sweeps')
        try:
            # Start from all switches open so the selected CMU channel is the only active path.
            b1500.set_switch(B1500_CH_ALL, False)
            b1500.set_switch(self.cmu_channel, True)
            b1500.set_cmu_integ(self.integration_mode, self.integration_value)
            b1500.force_cmu_ac_level(self.cmu_channel, self.ac_level)

            for index, bias in enumerate(self.bias_list, start=1):
                self.check_stop(b1500)
                tag = self._bias_label(bias)

                def on_point(_, freq, para1, para2, bias_monitor, time_s, s1, s2, _bias=bias, _tag=tag):
                    self.check_stop(b1500)
                    self.runner.plot.append_point(f"{'z' if is_z_theta else 'p'}_{_tag}", freq, para1)
                    self.runner.plot.append_point(f"{'theta' if is_z_theta else 'm'}_{_tag}", freq, para2)
                    report_cmu_status(self.runner, self.cmu_channel, nonzero_statuses, s1, s2)
                    row = [_bias, freq, para1, para2]
                    if is_z_theta:
                        # Only Z-theta sweeps have derived Rp/Cp columns and plot traces.
                        rp, cp = rp_cp_from_z_theta(para1, para2, freq, is_degrees)
                        if math.isfinite(rp):
                            self.runner.plot.append_point(f"rp_{_tag}", freq, rp)
                        if math.isfinite(cp):
                            self.runner.plot.append_point(f"cp_{_tag}", freq, cp)
                        row += [rp, cp]
                    results.append(row + [bias_monitor, time_s, s1, s2, s1 | s2])

                b1500.stream_cf_sweep(
                    self.cmu_channel, self.cmu_mode, self.measurement_range, bias,
                    self.spacing == 'log', self.start_hz, self.stop_hz, self.points,
                    self.hold_time, self.delay_time, self.step_delay, on_point,
                )
                self.report_progress(index, len(self.bias_list), 'Bias sweeps')
        finally:
            # Cleanup runs on success, instrument error, or user abort to avoid leaving the DUT biased.
            b1500.zero_output(B1500_CH_ALL)
            b1500.set_switch(B1500_CH_ALL, False)

        self.log(f"Collected {len(results)} C-f data points")
        self.save_measurement_outputs(results, "CfSweep", device, columns)
        self.log(f"C-f sweep completed for {device.name}")
