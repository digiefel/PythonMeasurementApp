"""Hardware voltage sweep with optional voltage probes."""
from procedures.base import Choice, parameter
from procedures._iv_sweep import IVSweepBase, CHANNEL_PARAMETERS, SWEEP_PARAMETERS
from instrumentio.constants import B1500_VOLTAGE_RANGES


class VSweepProcedure(IVSweepBase):
    """Sweep voltage and measure force-terminal currents.

    Optional sense SMUs replace programmed voltage endpoints in the main plot.
    Both sense SMUs give a measured-only I–V plot. A single probe gives an
    explicitly labelled mixed voltage difference. GNDU is a nominal reference.
    """
    NAME = 'Vsweep'
    FORCE_MODE = 'Force V'
    PARAMETERS = (
        *CHANNEL_PARAMETERS,
        parameter('start_voltage', 'Start Voltage (V)', 0.0, float),
        parameter('v_max', 'Stop Voltage / Butterfly Amplitude (V)', 15.0, float),
        parameter('symmetric_terminals', 'Symmetric Terminal Voltages (±V/2)', False, bool,
                  help='Requires a return SMU. Sweep values denote the full force-terminal voltage difference.'),
        parameter('current_compliance', 'Force SMU Current Compliance (A)', 1e-3, float),
        parameter('source_range', 'Source Voltage Range (V)', 0.0,
                  Choice(tuple((v, label) for v, label in B1500_VOLTAGE_RANGES if v >= 0), float)),
        *SWEEP_PARAMETERS,
    )
