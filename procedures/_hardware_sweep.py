"""Shared B1500 hardware staircase sweep: SMU setup and reading the data stream.

Procedures program the sweep themselves (set_iv_sweep, set_sweep_sync, constant
biases) and then call stream_sweep. It returns the raw readings per channel;
turning them into rows, plots and CSV files stays with each procedure.
"""
from dataclasses import dataclass, field
import time

from instrumentio.codes import B1500_CH_ALL, B1500_CH_NOCH, B1500_LAST_STOP, B1500_STOP_DISABLE
from instrumentio.descriptors import describe_status_bits

# B1500 data-type codes in the output stream.
CURRENT, VOLTAGE, SOURCE_CURRENT, SOURCE_VOLTAGE, TIME = 1, 2, 3, 4, 5
PLOT_INTERVAL_S = 0.1


def setup_smus(proc, b1500, channels, current_range=None):
    """Reset, connect only ``channels`` and apply the procedure's ADC settings.

    ``proc`` must declare ACQUISITION_PARAMETERS. Outputs stay at the last
    sweep value between sweeps; the runner turns everything off at the end.
    """
    b1500.reset()
    b1500.enable_error_detect(True)
    b1500.stop_mode(B1500_STOP_DISABLE, B1500_LAST_STOP)
    proc.prepare_asu_channels(b1500, channels, current_range)
    b1500.set_switch(B1500_CH_ALL, False)
    for ch in channels:
        b1500.set_switch(ch, True)
    b1500.configure_smu_acquisition(
        channels, adc=proc.adc_type, mode=proc.adc_mode, coefficient=proc.adc_coefficient,
        parallel=proc.parallel_measurement, autozero=proc.adc_autozero,
        source_wait_factor=proc.source_wait_factor, source_wait_offset=proc.source_wait_offset,
        measurement_wait_factor=proc.measurement_wait_factor,
        measurement_wait_offset=proc.measurement_wait_offset)


@dataclass
class SweepData:
    """What the instrument reported, one list entry per sweep step.

    readings[channel] holds (value, status, time); time is None when the
    instrument sent no timestamp. outputs holds the swept source's (value, status).
    """
    readings: dict = field(default_factory=dict)
    outputs: list = field(default_factory=list)


def stream_sweep(proc, b1500, measure, source_channel, source_kind, on_update=None):
    """Run the programmed sweep and collect every record up to end-of-data.

    measure: {channel: (CURRENT or VOLTAGE, measurement range)}.
    source_kind: SOURCE_VOLTAGE for a voltage sweep, SOURCE_CURRENT for a current sweep.
    on_update(data) is called about every 0.1 s, at the end, and also when the
    sweep is interrupted, so callers always keep the partial data.
    """
    channels = list(measure)
    b1500.start_measure(channels, [kind for kind, _ in measure.values()],
                        [rng for _, rng in measure.values()], source_output=1, timestamp=1)
    data = SweepData({ch: [] for ch in channels})
    seen_flags = set()
    pending_time = None
    last_update = 0.0

    def update():
        if on_update is not None:
            on_update(data)

    try:
        while True:
            proc.check_stop(b1500)
            _, eod, kind, value, status, channel = b1500.read_data()
            if status and (channel, kind, status) not in seen_flags:
                seen_flags.add((channel, kind, status))
                proc.runner.report_status(dict(channel=channel, data_type=kind, status=status,
                                               desc=describe_status_bits(status)))
            # Each timestamp record comes just before the reading it belongs to.
            if kind == TIME:
                pending_time = value
            elif channel in measure and kind == measure[channel][0]:
                data.readings[channel].append((value, status, pending_time))
                pending_time = None
            elif kind == source_kind and channel in (source_channel, B1500_CH_NOCH, B1500_CH_ALL):
                data.outputs.append((value, status))
                pending_time = None
            now = time.monotonic()
            if now - last_update >= PLOT_INTERVAL_S or eod:
                update()
                last_update = now
            if eod:
                break
    finally:
        # No instrument I/O here: after an abort the connection may be gone.
        update()
    b1500.finish_measure()
    counts = [len(data.outputs), *(len(r) for r in data.readings.values())]
    if len(set(counts)) > 1 or not counts[0]:
        raise RuntimeError(f'Incomplete hardware sweep stream: record counts {counts}; available data saved.')
    return data
