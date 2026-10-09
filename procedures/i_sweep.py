"""Hardware current sweep with optional voltage probes."""
from procedures.base import Choice, parameter
from procedures._iv_sweep import IVSweepBase, CHANNEL_PARAMETERS, SWEEP_PARAMETERS
from instrumentio.constants import B1500_CURRENT_RANGES


class ISweepProcedure(IVSweepBase):
    """Sweep current. Optional sense SMUs provide measured sample voltages.

    Without a voltage probe, its force SMU measures voltage instead of current.
    Main-plot current is measured where available, otherwise programmed. The
    CSV header identifies the provenance of all four terminal quantities.
    """
    NAME = 'Isweep'
    FORCE_MODE = 'Force I'
    PARAMETERS = (
        *CHANNEL_PARAMETERS,
        parameter('start_current', 'Start Current (A)', 0.0, float),
        parameter('stop_current', 'Stop Current / Butterfly Amplitude (A)', 1e-6, float),
        parameter('voltage_compliance', 'Source Voltage Compliance (V)', 10.0, float),
        parameter('return_current_compliance', 'Return Current Compliance (A)', 0.01, float),
        parameter('source_range', 'Source Current Range (A)', 0.0,
                  Choice(tuple((v, label) for v, label in B1500_CURRENT_RANGES if v >= 0), float),
                  help='Auto or a minimum source range. Each hardware segment uses one range covering its endpoints.'),
        *SWEEP_PARAMETERS,
    )
