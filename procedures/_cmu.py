"""Shared helpers for CMU (impedance) procedures: CVSweep, CfSweep and CVFatigue."""

import cmath
import math

from instrumentio.codes import B1500_SWP_VF_DBLLIN, B1500_SWP_VF_SGLLIN
from instrumentio.constants import B1500_CMU_CHANNELS
from plotting import Curve, PlotDef
from instrumentio.descriptors import describe_status_bits
from procedures.base import action
from si_utils import format_si_value, parse_si_list

# The frequencies CLCORR chnum,2 puts in the correction list (Programming Guide, CLCORR).
DEFAULT_CORRECTION_FREQUENCIES = (
    1e3, 2e3, 5e3, 10e3, 20e3, 50e3, 100e3, 200e3, 500e3, 1e6, 1.2e6, 1.5e6, 2e6,
    2.5e6, 2.7e6, 3e6, 3.2e6, 3.5e6, 3.7e6, 4e6, 4.2e6, 4.5e6, 5e6,
)

# Wiring: the SCUU outputs feed the From-SMU inputs of two RSUs, so the CMU reaches the
# probes there whenever those WGFMU channels are idle. CMU-H shares RSU 201 with SMU4,
# CMU-L shares RSU 102 with SMU3 (checked by switching each RSU and watching the CMU).
CMU_RSU = {'H': 201, 'L': 102}

CV_SWEEP_TYPES = (
    ('single', 'Single (Start → Stop)'),
    ('double', 'Double (Start → Stop → Start)'),
    ('butterfly', 'Butterfly (0 → Vmax → Vmin → 0)'),
)


def parse_cmu_frequencies(text):
    """Sorted CMU frequencies from a comma-separated list with SI prefixes, each 1 kHz to 5 MHz."""
    freqs = sorted(parse_si_list(str(text)))
    if not freqs:
        raise ValueError("At least one frequency is required.")
    for f in freqs:
        if not (1e3 <= f <= 5e6):
            raise ValueError(f"Frequency {f:.6g} Hz out of range [1 kHz, 5 MHz].")
    return freqs


def freq_label(freq_hz):
    return f"{format_si_value(freq_hz)}Hz"


def freq_key(freq_hz) -> str:
    # Use stable text keys for calibration JSON; raw float strings can differ by representation.
    return f"{float(freq_hz):.12g}"


def resolve_cmu_channel(settings, channel, log) -> int:
    """Return the CMU slot to use: the requested one if installed, else the first installed CMU.

    `settings['b1500']['module_inventory']` lists installed modules when the
    instrument has been discovered; without it, -1 (auto) maps to the first known CMU slot.
    """
    discovered = []
    b1500_cfg = settings.get("b1500", {}) or {}
    for module in b1500_cfg.get("module_inventory") or []:
        if not isinstance(module, dict) or module.get("kind") != "CMU":
            continue
        try:
            discovered.append(int(module.get("channel", module.get("slot"))))
        except (TypeError, ValueError):
            continue

    replacement = None
    if discovered and channel not in discovered:
        replacement = sorted(set(discovered))[0]
    elif channel == -1 and B1500_CMU_CHANNELS:
        replacement = int(B1500_CMU_CHANNELS[0][0])

    if replacement is None:
        return channel
    if replacement != channel:
        log(f"CMU channel auto -> slot {replacement} (was {channel})")
    return replacement


def record_calibration(cmu_calibration, channel, cal_type, result, timestamp) -> dict:
    """Store a calibration result in the cmu_calibration dict (as kept in the global config).

    result is what B1500Session.run_cmu_phase_compensation or measure_cmu_correction
    returned. A correction that rebuilt the instrument's frequency list cleared the
    other correction types there, so their records go too. Returns the channel's records.
    """
    records = cmu_calibration.setdefault(str(channel), {})
    if cal_type == "phase":
        records["phase"] = {"timestamp": timestamp, "result": result}
        return records
    if result.get("list_changed"):
        for other in ("open", "short", "load"):
            records.pop(other, None)
    records[cal_type] = {
        "timestamp": timestamp,
        "frequencies_hz": list(result["frequencies_hz"]),
        "results_by_frequency": {freq_key(row["frequency_hz"]): {"coefficients": row} for row in result["table"]},
    }
    return records


def phase_compensated(cmu_calibration, channel) -> bool:
    entry = (cmu_calibration or {}).get(str(channel), {}).get("phase")
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


def z_theta_pairs(Z: float, theta: float, freq: float, is_degrees: bool) -> dict[str, float]:
    """Equivalent-circuit pairs from |Z| and phase: Z'-Z'' ("zre", "zim"), Rp-Cp, Rs-Cs, G-B.

    Series view: Z = Z' + jZ'' (Rs = Z', Cs = -1/(ω Z'')).
    Parallel view: Y = 1/Z = G + jB (Rp = 1/G, Cp = B/ω).
    """
    z = cmath.rect(Z, math.radians(theta) if is_degrees else theta)
    y = 1 / z
    omega = 2.0 * math.pi * freq
    return {
        "zre": z.real,
        "zim": z.imag,
        "rp": 1 / y.real,
        "cp": y.imag / omega,
        "rs": z.real,
        # A purely resistive reading (phase exactly 0) has no series capacitance.
        "cs": -1 / (omega * z.imag) if z.imag else math.nan,
        "g": y.real,
        "b": y.imag,
    }


def z_theta_plots(labels, colors, xlabel, xscale, is_degrees) -> list[PlotDef]:
    """Plot layout for Z-theta sweeps, with one curve per entry of labels in every panel.

    colors[i] is curve i's colour; an empty labels[i] leaves curve i out of the legend.

    Rows: |Z|-Theta (measured), the Nyquist plot (-Z'' against Z', one wide panel),
    then Rp-Cp, Rs-Cs and G-B (from z_theta_pairs). All panels except the Nyquist
    plot share the sweep variable as x axis (xlabel, xscale).
    """
    def curves(plot_id):
        return [Curve(f"{plot_id}_{i}", color=color, legend_label=label, show_in_legend=bool(label))
                for i, (label, color) in enumerate(zip(labels, colors))]

    def vs_sweep(plot_id, row, col, ylabel, yscale):
        return PlotDef(plot_id, row=row, col=col, xlabel=xlabel, ylabels=(ylabel,), xscale=xscale,
                       yscales=(yscale,), xlink="" if plot_id == "z" else "z", elements=curves(plot_id))

    return [
        vs_sweep("z", 0, 0, "|Z| (Ohm)", "log"),
        vs_sweep("theta", 0, 1, f"Theta ({'deg' if is_degrees else 'rad'})", "linear"),
        PlotDef("nyquist", row=1, col=0, colspan=2, xlabel="Z' (Ohm)", ylabels=("-Z'' (Ohm)",),
                elements=curves("nyquist")),
        vs_sweep("rp", 2, 0, "Rp (Ohm)", "log"),
        vs_sweep("cp", 2, 1, "Cp (F)", "linear"),
        vs_sweep("rs", 3, 0, "Rs (Ohm)", "log"),
        vs_sweep("cs", 3, 1, "Cs (F)", "linear"),
        vs_sweep("g", 4, 0, "G (S)", "log"),
        vs_sweep("b", 4, 1, "B (S)", "log"),
    ]


def append_z_theta_point(plot, i, x, Z, theta, freq, is_degrees):
    """Add one Z-theta reading to curve i of every z_theta_plots panel; x is the sweep variable."""
    pairs = z_theta_pairs(Z, theta, freq, is_degrees)
    plot.append_point(f"z_{i}", x, Z)
    plot.append_point(f"theta_{i}", x, theta)
    plot.append_point(f"nyquist_{i}", pairs["zre"], -pairs["zim"])
    for plot_id in ("rp", "cp", "rs", "cs", "g", "b"):
        # Plots cannot show nan, e.g. Cs of a purely resistive reading.
        if math.isfinite(pairs[plot_id]):
            plot.append_point(f"{plot_id}_{i}", x, pairs[plot_id])


def report_cmu_status(runner, channel, seen, s1, s2):
    # CMU streaming reports para1/para2 status separately; report each unique status once to the UI.
    for data_type, status in ((8, s1), (9, s2)):
        if status and (channel, data_type, status) not in seen:
            seen.add((channel, data_type, status))
            runner.report_status({
                "channel": channel, "data_type": data_type, "status": status,
                "desc": describe_status_bits(status),
            })


def cv_sweep_legs(sweep_type, start_bias, stop_bias, points):
    """The legs of a C-V sweep, as (start, stop, points, double) per CMU sweep command.

    'single' is start → stop and 'double' start → stop → start, both one command.
    'butterfly' is 0 → Vmax → Vmin → 0 in three legs, with start_bias = Vmax and
    stop_bias = Vmin. Its points are shared out in proportion to each leg's span;
    legs 2 and 3 repeat the previous leg's last point, which run_cv_sweep drops,
    so the pool is points + 2.
    """
    if sweep_type != 'butterfly':
        return [(start_bias, stop_bias, points, sweep_type == 'double')]
    vmax, vmin = start_bias, stop_bias
    spans = [abs(vmax), abs(vmax - vmin), abs(vmin)]
    total_span = sum(spans)
    if total_span == 0:
        raise ValueError("Butterfly sweep: all voltage spans are zero.")
    raw = [max(2, round((points + 2) * s / total_span)) for s in spans]
    # Make the visible point count (sum - 2 shared boundaries) exactly `points`, through the middle leg.
    raw[1] = max(2, raw[1] + (points + 2) - sum(raw))
    return [(0.0, vmax, raw[0], False), (vmax, vmin, raw[1], False), (vmin, 0.0, raw[2], False)]


def validate_cv_sweep(sweep_type, start_bias, stop_bias, points):
    if sweep_type not in ('single', 'double', 'butterfly'):
        raise ValueError(f"Invalid sweep_type: {sweep_type!r}")
    if points < 1:
        raise ValueError("C-V points must be >= 1")
    if sweep_type == 'butterfly' and start_bias == stop_bias:
        raise ValueError("For butterfly sweep, Start Bias (Vmax) and Stop Bias (Vmin) must differ.")
    if sweep_type != 'butterfly' and start_bias == stop_bias and points > 1:
        raise ValueError("Start Bias and Stop Bias are equal; use points=1 for spot-like measurement.")
    cv_sweep_legs(sweep_type, start_bias, stop_bias, points)


def run_cv_sweep(b1500, channel, cmu_mode, measurement_range, sweep_type, start_bias, stop_bias, points,
                 hold, delay, second_delay, on_point):
    """Run one C-V sweep at the frequency and AC level already set, streaming every point.

    on_point(source_v, para1, para2, time_s, s1, s2) is called as each point arrives.
    Only the first leg waits the hold time; later legs continue from the bias the
    previous one ended at. The CMU stays at the last bias afterwards.
    """
    for leg, (start, stop, n, double) in enumerate(cv_sweep_legs(sweep_type, start_bias, stop_bias, points)):
        b1500.reset_timestamp()
        b1500.set_cv(channel, B1500_SWP_VF_DBLLIN if double else B1500_SWP_VF_SGLLIN, start, stop, n,
                     hold=hold if leg == 0 else 0.0, delay=delay, second_delay=second_delay)

        def point(step, source_v, para1, para2, time_s, s1, s2, _skip=leg > 0):
            # A later leg starts at the previous leg's last bias, which is already recorded.
            if not (_skip and step == 0):
                on_point(source_v, para1, para2, time_s, s1, s2)

        b1500.stream_cv_sweep(channel, cmu_mode, measurement_range, point)


class CMUCalibration:
    """CMU calibration for a procedure: the calibration buttons, the coverage check, and using it.

    Mix into a MeasurementProcedure that has 'cmu_channel', 'ac_level_mv' and
    'require_cmu_calibration' parameters, and implement cmu_calibration_frequencies.
    The UI then shows the "CMU Calibration" section: its buttons calibrate at
    cmu_calibration_frequencies(settings), and its readout follows the fields in
    CMU_FREQUENCY_FIELDS.

    Calibration data stay in the B1500 until it is switched off, but *RST, which
    every CMU procedure sends first, stops their use. Call apply_cmu_calibration
    after the reset to use them again.
    """
    UI_ACTIONS = (
        action("Open", "_on_cv_calibration_button", "open", section="CMU Calibration",
               tooltip="Open correction: probes up, at the calibration frequencies"),
        action("Short", "_on_cv_calibration_button", "short", section="CMU Calibration",
               tooltip="Short correction: probes on a short, at the calibration frequencies"),
        action("Phase", "_on_cv_calibration_button", "phase", section="CMU Calibration",
               tooltip="Phase compensation: probes up. Run it before the corrections."),
        action("Load", "_on_cv_calibration_button", "load", section="CMU Calibration",
               tooltip="Load correction: probes on a 50 Ohm standard, at the calibration frequencies"),
    )
    # Fields that change cmu_calibration_frequencies; the UI refreshes the readout when they change.
    CMU_FREQUENCY_FIELDS = ('frequencies',)

    @classmethod
    def cmu_calibration_frequencies(cls, settings) -> list[float]:
        """The frequencies the calibration buttons measure, sorted, from the form settings."""
        raise NotImplementedError

    def apply_cmu_calibration(self, b1500):
        """Use the stored phase compensation and the corrections the instrument still holds.

        Call after b1500.reset(). A correction type is used when it was measured at
        the frequencies now in the instrument's correction list; it is reported as
        incomplete when those do not span this run's calibration frequencies (the
        CMU interpolates between list frequencies). With require_cmu_calibration,
        missing phase compensation, a missing open correction or incomplete coverage
        is an error. Records what is in use as the 'cmu_correction' setting, so the
        CSV header shows it. Returns that list.
        """
        channel = self.cmu_channel
        records = (self.cmu_calibration or {}).get(str(channel), {})
        needed = self.cmu_calibration_frequencies(self.settings)
        lo, hi = min(needed), max(needed)
        # `or`: the waveform preview's stand-in instrument answers None.
        instrument_freqs = sorted(b1500.get_cmu_correction_frequencies(channel) or [])
        problems, corrections = [], []
        for corr_type in ("open", "short", "load"):
            entry = records.get(corr_type)
            if not isinstance(entry, dict):
                continue
            stored = sorted(float(f) for f in entry.get("frequencies_hz") or [])
            if not stored or len(stored) != len(instrument_freqs) or any(
                    abs(a - b) > 1e-6 * b for a, b in zip(stored, instrument_freqs)):
                problems.append(f"{corr_type}: no longer in the instrument (switched off since, "
                                f"or recalibrated at other frequencies); measure it again")
                continue
            corrections.append(corr_type)
            if stored[0] > lo * (1 + 1e-9) or stored[-1] < hi * (1 - 1e-9):
                problems.append(f"{corr_type}: calibrated {freq_label(stored[0])}–{freq_label(stored[-1])}, "
                                f"which does not span {freq_label(lo)}–{freq_label(hi)}")

        want_phase = phase_compensated(self.cmu_calibration, channel)
        applied = b1500.apply_cmu_calibration(channel, want_phase, corrections) or {}
        used = list(corrections)
        if not want_phase:
            problems.append("phase: never run")
        elif applied.get("phase_result") == 0:
            used.insert(0, "phase")
        else:
            # ADJ? 3: no phase compensation since the B1500 was switched on.
            problems.append(f"phase: the instrument holds no compensation data (ADJ? {applied.get('phase_result')}); "
                            f"run Phase again")
            b1500.apply_cmu_calibration(channel, False, corrections)
        if "open" not in corrections:
            problems.append("open: missing")

        self.settings['cmu_correction'] = ", ".join(used) or "none"
        self.log(f"CMU calibration in use on channel {channel}: {self.settings['cmu_correction']}")
        if problems:
            message = f"CMU calibration on channel {channel}: " + "; ".join(problems)
            if self.require_cmu_calibration:
                raise ValueError(message)
            self.log(f"Warning: {message}")
        return used
