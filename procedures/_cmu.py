"""Shared helpers for CMU (impedance) procedures: CVSweep and CfSweep."""

import cmath
import math

from instrumentio.constants import B1500_CMU_CHANNELS
from plotting import Curve, PlotDef
from instrumentio.descriptors import describe_status_bits
from si_utils import format_si_value


def freq_label(freq_hz):
    return f"{format_si_value(freq_hz)}Hz"


def freq_key(freq_hz) -> str:
    # Use stable text keys for calibration JSON; raw float strings can differ by representation.
    return f"{float(freq_hz):.12g}"


def resolve_cmu_channel(settings, channel, log=None) -> int:
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
    if replacement != channel and log is not None:
        log(f"CMU channel auto -> slot {replacement} (was {channel})")
    return replacement


def calibrated_frequencies(cmu_calibration, channel) -> dict[str, list[float]]:
    """Return the sorted frequencies with stored open/short/load correction data on a channel."""
    channel_data = (cmu_calibration or {}).get(str(channel), {})
    result = {}
    for corr_type in ("open", "short", "load"):
        entry = channel_data.get(corr_type, {})
        freqs = set()
        if isinstance(entry, dict):
            # Calibration data can be stored as a per-frequency map or as an older single-frequency entry.
            by_freq = entry.get("results_by_frequency", {})
            raw = list(by_freq.keys()) if isinstance(by_freq, dict) and by_freq else [entry.get("frequency_hz")]
            for value in raw:
                try:
                    freqs.add(float(value))
                except (TypeError, ValueError):
                    continue
        result[corr_type] = sorted(freqs)
    return result


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


def rp_cp_from_z_theta(Z: float, theta: float, freq: float, is_degrees: bool):
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


def z_theta_pairs(Z: float, theta: float, freq: float, is_degrees: bool) -> dict[str, float]:
    """Equivalent-circuit pairs from |Z| and phase: Z' and -Z'' ("zre", "zim"), Rp-Cp, Rs-Cs, G-B.

    Series view: Z = Z' + jZ'' (Rs = Z', Cs = -1/(ω Z'')).
    Parallel view: Y = 1/Z = G + jB (Rp = 1/G, Cp = B/ω).
    """
    z = cmath.rect(Z, math.radians(theta) if is_degrees else theta)
    y = 1 / z
    omega = 2.0 * math.pi * freq
    return {
        "zre": z.real,
        "zim": -z.imag,
        "rp": 1 / y.real,
        "cp": y.imag / omega,
        "rs": z.real,
        # A purely resistive reading (phase exactly 0) has no series capacitance.
        "cs": -1 / (omega * z.imag) if z.imag else math.nan,
        "g": y.real,
        "b": y.imag,
    }


# Z-theta figure panels: (plot id, row, col, y label, y scale), all against the sweep variable.
# Row 1 holds the Nyquist plot instead. "z" and "theta" are measured; the rest come from z_theta_pairs.
Z_THETA_PANELS = (
    ("z", 0, 0, "|Z| (Ohm)", "log"),
    ("theta", 0, 1, "Theta", "linear"),
    ("rp", 2, 0, "Rp (Ohm)", "log"),
    ("cp", 2, 1, "Cp (F)", "linear"),
    ("rs", 3, 0, "Rs (Ohm)", "log"),
    ("cs", 3, 1, "Cs (F)", "linear"),
    ("g", 4, 0, "G (S)", "log"),
    ("b", 4, 1, "B (S)", "log"),
)


def z_theta_plots(labels, xlabel, xscale, is_degrees) -> list[PlotDef]:
    """Plot layout for Z-theta sweeps, with one curve per entry of labels in every panel.

    Rows: |Z|-Theta, the Nyquist plot (-Z'' against Z', one wide panel), Rp-Cp, Rs-Cs and G-B.
    All panels except the Nyquist plot share the sweep variable as x axis (xlabel, xscale).
    """
    def curves(plot_id):
        return [Curve(f"{plot_id}_{i}", color=f"C{i % 10}", legend_label=label) for i, label in enumerate(labels)]

    plots = [PlotDef("nyquist", row=1, col=0, colspan=2, xlabel="Z' (Ohm)", ylabels=("-Z'' (Ohm)",),
                     elements=curves("nyquist"))]
    for plot_id, row, col, ylabel, yscale in Z_THETA_PANELS:
        if plot_id == "theta":
            ylabel = f"Theta ({'deg' if is_degrees else 'rad'})"
        plots.append(PlotDef(plot_id, row=row, col=col, xlabel=xlabel, ylabels=(ylabel,), xscale=xscale,
                             yscales=(yscale,), xlink="" if plot_id == "z" else "z", elements=curves(plot_id)))
    return plots


def append_z_theta_point(plot, i, x, Z, theta, freq, is_degrees):
    """Add one Z-theta reading to curve i of every z_theta_plots panel; x is the sweep variable."""
    pairs = z_theta_pairs(Z, theta, freq, is_degrees)
    plot.append_point(f"z_{i}", x, Z)
    plot.append_point(f"theta_{i}", x, theta)
    plot.append_point(f"nyquist_{i}", pairs["zre"], pairs["zim"])
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
