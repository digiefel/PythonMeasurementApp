"""Bipolar four-SMU Van der Pauw sheet-resistance measurement."""
import math
import time
from dataclasses import dataclass

from procedures.base import Choice, MeasurementProcedure, SMU, parameter
from instrumentio.constants import B1500_CURRENT_RANGES, B1500_VOLTAGE_RANGES
from instrumentio.codes import (
    B1500_AUTO_RANGE, B1500_CH_ALL, B1500_CH_NOCH, B1500_IM_MODE,
    B1500_VM_MODE, B1500_SWP_IF_SGLLIN,
)
from instrumentio.descriptors import describe_status_bits
from plotting import PlotDef, Curve, HLine, linear_fit

# Each row is: name, current source, current return, voltage +, voltage -.
# TL/TR are the top-left/top-right contacts; BL/BR are bottom-left/bottom-right.
# The second sweep exchanges both the current and voltage contacts.
# Resistance keeps the same sign, but a different SMU now holds 0 V.
CONTACT_SWEEPS = (
    ("top", "TL", "TR", "BL", "BR"),
    ("top_swapped", "TR", "TL", "BR", "BL"),
    ("right", "TR", "BR", "TL", "BL"),
    ("right_swapped", "BR", "TR", "BL", "TL"),
    ("bottom", "BR", "BL", "TR", "TL"),
    ("bottom_swapped", "BL", "BR", "TL", "TR"),
    ("left", "BL", "TL", "BR", "TR"),
    ("left_swapped", "TL", "BL", "TR", "BR"),
)



@dataclass(frozen=True)
class Reading:
    current_smus: str
    voltage_smus: str
    point: int
    current_set: float
    current: float
    return_current: float
    voltage_high: float
    voltage_low: float
    time: float
    source_status: int
    return_status: int
    high_status: int
    low_status: int
    output_status: int

    @property
    def voltage(self):
        return self.voltage_high - self.voltage_low

    @property
    def status(self):
        return (self.source_status | self.return_status | self.high_status
                | self.low_status | self.output_status)

    @property
    def finite(self):
        return math.isfinite(self.current) and math.isfinite(self.voltage)

    def csv_row(self):
        return [*self.__dict__.values(), self.voltage, self.status]


RAW_HEADERS = [
    "CurrentSMUs", "VoltageSMUs", "Point", "CurrentSet_A", "Current_A", "ReturnCurrent_A",
    "VoltageHigh_V", "VoltageLow_V", "SourceTime_s", "SourceStatus", "ReturnStatus",
    "SenseHighStatus", "SenseLowStatus", "OutputStatus", "VoltageDiff_V", "Status",
]


def sheet_resistance(ra, rb):
    """Solve exp(-pi RA/Rs) + exp(-pi RB/Rs) = 1 for sheet resistance."""
    if not all(math.isfinite(r) and r > 0 for r in (ra, rb)):
        return math.nan  # No positive sheet-resistance solution for these inputs.
    scale = max(ra, rb)
    a, b = ra / scale, rb / scale
    low, high = 0.0, math.pi / math.log(2)
    for _ in range(100):
        middle = (low + high) / 2
        if math.exp(-math.pi * a / middle) + math.exp(-math.pi * b / middle) > 1:
            high = middle
        else:
            low = middle
    return (low + high) / 2 * scale


def fit_iv_curve(readings):
    rows = [r for r in readings if r.finite]
    if len({r.current for r in rows}) < 2:
        return None  # A slope needs at least two different current values.
    return linear_fit([r.current for r in rows], [r.voltage for r in rows])


def direction_resistances(slopes, suffix=''):
    return ((slopes['top' + suffix] + slopes['bottom' + suffix]) / 2,
            (slopes['right' + suffix] + slopes['left' + suffix]) / 2)


def difference_percent(first, second):
    mean = (abs(first) + abs(second)) / 2
    return 100 * (first - second) / mean if mean else math.nan


def analyze_measurement(readings_by_contacts, points):
    """Fit V=R*I+b using measured source current; retain flagged finite readings.

    Average the four top/bottom slopes into RA and the four left/right slopes
    into RB, then solve the Van der Pauw equation. The per-current plot instead
    pairs opposite sweep indices (+I/-I) to cancel constant voltage offsets,
    keeping forward and swapped contact assignments separate. An unpaired zero
    point contributes to the fit but not to these pairs. Undefined results are NaN.

    Interpretation assumes a uniform sheet without holes, uniform thickness,
    small ohmic contacts on the perimeter, and zero magnetic field.
    Reference: https://www.nist.gov/pml/nanoscale-device-characterization-division/popular-links/hall-effect/hall-effect
    """
    fits = {name: fit_iv_curve(rows) for name, rows in readings_by_contacts.items()}
    slopes = {name: fit.slope if fit is not None else math.nan for name, fit in fits.items()}
    ra_forward, rb_forward = direction_resistances(slopes)
    ra_swapped, rb_swapped = direction_resistances(slopes, '_swapped')
    ra, rb = (ra_forward + ra_swapped) / 2, (rb_forward + rb_swapped) / 2
    differences = {name: difference_percent(slopes[name], slopes[name + '_swapped'])
                   for name in ('top', 'right', 'bottom', 'left')}
    # Compare opposite edges after averaging the source/return assignments.
    averaged = {name: (slopes[name] + slopes[name + '_swapped']) / 2 for name in differences}
    opposite_differences = (difference_percent(averaged['top'], averaged['bottom']),
                            difference_percent(averaged['right'], averaged['left']))

    # Subtract the voltages at +I and -I to remove any constant voltage contribution.
    indexed = {name: {r.point: r for r in rows} for name, rows in readings_by_contacts.items()}
    pairs = []
    for i in range(points // 2):
        resistances, currents = {}, []
        for name, rows in indexed.items():
            first, last = rows.get(i), rows.get(points - 1 - i)
            if first is None or last is None or not first.finite or not last.finite:
                break
            delta_i = last.current - first.current
            if delta_i == 0:
                break
            resistances[name] = (last.voltage - first.voltage) / delta_i
            currents.append(abs(delta_i) / 2)
        if len(resistances) != 8:
            continue
        forward_a, forward_b = direction_resistances(resistances)
        swapped_a, swapped_b = direction_resistances(resistances, '_swapped')
        pairs.append((sum(currents) / 8,
                      sheet_resistance((forward_a + swapped_a) / 2, (forward_b + swapped_b) / 2),
                      sheet_resistance(forward_a, forward_b), sheet_resistance(swapped_a, swapped_b)))
    return dict(fits=fits, ra=ra, rb=rb, sheet=sheet_resistance(ra, rb), pairs=sorted(pairs),
                forward_sheet=sheet_resistance(ra_forward, rb_forward),
                swapped_sheet=sheet_resistance(ra_swapped, rb_swapped),
                swap_differences=differences, opposite_differences=opposite_differences)


class VanDerPauwProcedure(MeasurementProcedure):
    """Measure sheet resistance with four perimeter contacts (TL, TR, BL, BR).

    Select the SMU wired to each contact. All eight bipolar sweeps run
    automatically: four edge configurations, each repeated with current and
    voltage contacts exchanged. Ibias sets the limits from -|Ibias| to +|Ibias|.
    Plot labels use the selected SMU numbers; the return SMU holds 0 V.

    Each sweep fits V = R*I + b using measured source current. Top/bottom slopes
    form RA and left/right slopes form RB; the sheet resistance Rs solves
    exp(-pi*RA/Rs) + exp(-pi*RB/Rs) = 1.

    Small plots overlay exchanged contacts; dR is their signed slope difference
    as a percentage of mean magnitude. Red crosses mark instrument flags, which
    do not exclude readings from fits. Only non-finite readings are excluded.
    The main plot pairs +I/-I to cancel constant offsets, showing forward and
    swapped results separately. Its horizontal line uses all eight fitted slopes.
    Opposite-edge differences are saved without a pass/fail threshold.

    Results assume a uniform sheet without holes, uniform thickness, small ohmic
    perimeter contacts and zero magnetic field. A completed run saves one CSV
    and one PNG. Settings, fits and results are in the CSV header; interrupted
    runs save available complete readings in a partial CSV.

    Hover over settings for units, timing behavior and ADC restrictions.
    """
    NAME = "VanDerPauw"
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('TL_channel', 'TL (Top Left)', 'SMU1', SMU),
        parameter('TR_channel', 'TR (Top Right)', 'SMU2', SMU),
        parameter('BL_channel', 'BL (Bottom Left)', 'SMU3', SMU),
        parameter('BR_channel', 'BR (Bottom Right)', 'SMU4', SMU),
        parameter('ibias', 'Ibias (A)', 1e-6, float, help='Each sweep runs from -|Ibias| to +|Ibias|. Fits use measured current, not this setpoint.'),
        parameter('points', 'Points', 75, int, help='Points per sweep, repeated for eight contact configurations. Even counts are supported; odd counts include zero.'),
        parameter('voltage_compliance', 'Voltage Compliance (V)', 10.0, float),
        parameter('power_compliance', 'Power Compliance (W)', 0.0, float),
        parameter('measurement_range', 'Voltage Meas Range', 0.0, Choice(B1500_VOLTAGE_RANGES, float), help='Applies to both voltage-sensing SMUs. Auto selects a range; Auto ≥ sets a lower bound; Fixed prevents range changes.'),
        parameter('current_measurement_range', 'Current Meas Range', 1e-9, Choice(B1500_CURRENT_RANGES, float), help='Applies to source and return current measurements. Auto ≥1 nA prevents smaller ranges near zero. Fixed avoids range searching; choose a range covering the sweep.'),
        parameter('current_compliance', 'Return Current Compliance (A)', 0.01, float),
        parameter('adc_type', 'ADC Type', 0, Choice(((0, 'High-speed'), (1, 'High-resolution')), int), help='Selects the ADC for all four SMUs. High-speed supports parallel measurements. High-resolution measurements run sequentially.'),
        parameter('adc_mode', 'ADC Integration Mode', 0,
                  Choice(((0, 'Auto'), (1, 'Manual'), (2, 'Power line cycles')), int),
                  help='Auto scales instrument-selected averaging/integration. Manual uses sample count for high-speed or 80 µs units for high-resolution. PLC uses whole power line cycles (20 ms each at 50 Hz).'),
        parameter('adc_coefficient', 'ADC Samples / Factor / PLC (0 = mode default)', 0.0, float,
                  help='Integer coefficient. Auto/Manual: 1–1023 for high-speed, 1–127 for high-resolution. PLC: 1–100. Zero selects the mode default: HS Auto/Manual 1, HR Auto 6, HR Manual 3, PLC 1.'),
        parameter('parallel_measurement', 'Parallel Measurement (high-speed ADC)', False, bool,
                  help='Measure the four SMUs in parallel within each sweep step. Requires high-speed ADC; does not run separate contact sweeps concurrently.'),
        parameter('adc_autozero', 'ADC Autozero (high-resolution ADC)', False, bool,
                  help='Cancels high-resolution ADC offset, adding integration time. Has no effect with high-speed ADC.'),
        parameter('auto_calibration', 'Auto Calibration (terminals must be open when idle)', False, bool,
                  help='Allows automatic calibration after all SMU switches have been off for 30 minutes. Open the measurement terminals for calibration.'),
        parameter('source_wait_factor', 'Source Settling Factor (0–10, step 0.1)', 1.0, float,
                  help='Source wait = factor × instrument automatic wait + offset, before changing output. Default 1 preserves automatic timing; 0 removes its automatic component.'),
        parameter('source_wait_offset', 'Source Settling Offset (s, step 0.0001)', 0.0, float,
                  help='Adds 0–1 seconds to the source wait. Separate from hold and step delays.'),
        parameter('measurement_wait_factor', 'Measurement Settling Factor (0–10, step 0.1)', 1.0, float,
                  help='Measurement wait = factor × instrument automatic wait + offset. Default 1 preserves automatic settling even when Delay Time is zero. Reducing it may measure before the device settles.'),
        parameter('measurement_wait_offset', 'Measurement Settling Offset (s, step 0.0001)', 0.0, float,
                  help='Adds 0–1 seconds to the measurement wait. The instrument wait can be covered by a longer Delay Time.'),
        parameter('hold_time', 'Hold Time (s)', 0.0, float, help='Wait at the beginning of each sweep, before the first step delay.'),
        parameter('delay_time', 'Delay Time (s)', 0.0, float, help='Wait after setting each step output and before measurement. Zero does not disable automatic settling.'),
        parameter('second_delay', 'Second Delay (s)', 0.0, float, help='Step delay from measurement start to the next output step. The instrument also waits for measurement completion if that takes longer.'),
    )

    def smu_numbers(self, contact_sweep):
        # Use the same SMU names as the selectors, not the hardware slot numbers.
        return tuple(SMU.display_value(getattr(self, f'{contact}_channel')).removeprefix('SMU')
                     for contact in contact_sweep[1:])

    def sweep_label(self, contact_sweep):
        source, ret, high, low = self.smu_numbers(contact_sweep)
        return f'I {source}->{ret} / V {high}-{low}'

    def csv_metadata_lines(self, extra=None):
        lines = super().csv_metadata_lines(extra) + [
            '# Contact layout: TL (top left), TR (top right), BL (bottom left), BR (bottom right)',
            '# Fit: V = R*I + b; b is the fitted voltage at zero current',
            '# Instrument flags are saved and shown, but do not exclude points from the fit',
        ]
        for contact in ('TL', 'TR', 'BL', 'BR'):
            lines.append(f"# {contact}: {SMU.display_value(getattr(self, f'{contact}_channel'))}")
        for sweep in CONTACT_SWEEPS:
            lines.append(f'# SMU sweep: {self.sweep_label(sweep)}')
        result = getattr(self, '_result', None)
        if result is not None:
            lines.extend([
                f"# RA_ohm: {result['ra']}",
                f"# RB_ohm: {result['rb']}",
                f"# SheetResistance_ohm_per_square: {result['sheet']}",
            ])
            lines.extend([
                f"# Forward_SheetResistance_ohm_per_square: {result['forward_sheet']}",
                f"# Swapped_SheetResistance_ohm_per_square: {result['swapped_sheet']}",
                f"# TopBottom_Difference_pct: {result['opposite_differences'][0]}",
                f"# RightLeft_Difference_pct: {result['opposite_differences'][1]}",
            ])
            for sweep in CONTACT_SWEEPS[::2]:
                lines.append(f"# {self.sweep_label(sweep)}_SwapDifference_pct: {result['swap_differences'][sweep[0]]}")
            for sweep in CONTACT_SWEEPS:
                fit = result['fits'][sweep[0]]
                name = self.sweep_label(sweep)
                if fit is not None:
                    lines.extend([
                        f'# {name}_Resistance_ohm: {fit.slope}',
                        f'# {name}_VoltageAtZeroCurrent_V: {fit.intercept}',
                        f'# {name}_R_squared: {fit.r_squared}',
                    ])
        return lines

    def plot_definitions(self, result=None):
        plots = [PlotDef(
            'sheet', row=0, col=0, rowspan=2, title='Sheet resistance',
            xlabel='Current magnitude (uA)', ylabels=('Sheet resistance (Ohm/sq)',),
            elements=[
                Curve('sheet_forward', mode='scatter', marker='o', marker_size=4, color='C0',
                      legend_label='Forward'),
                Curve('sheet_swapped', mode='scatter', marker='x', marker_size=4, color='C1',
                      legend_label='Swapped'),
                HLine(source='sheet_fit', color='C7', legend_label='Average',
                      legend_label_template='Average: {value:.5g} Ohm/sq'),
            ],
        )]
        for index, forward in enumerate(CONTACT_SWEEPS[::2]):
            name = forward[0]
            elements = []
            for sweep, color in ((forward, 'C0'), (CONTACT_SWEEPS[2 * index + 1], 'C1')):
                key = sweep[0]
                source, ret, _, _ = self.smu_numbers(sweep)
                elements.extend([
                    Curve(f'{key}_raw', mode='scatter', marker='o', marker_size=3, color=color,
                          legend_label=f'{source}->{ret}'),
                    Curve(f'{key}_flagged', mode='scatter', marker='x', marker_size=4, color='C3', show_in_legend=False),
                    Curve(f'{key}_fit', color=color, show_in_legend=False),
                ])
            title = self.sweep_label(forward)
            if result is not None:
                title += f"  dR {result['swap_differences'][name]:+.2f}%"
            plots.append(PlotDef(
                name, row=index // 2, col=1 + index % 2, title=title,
                xlabel='Current (uA)', ylabels=('Voltage (mV)',), xlink='top' if index else '',
                elements=elements,
            ))
        return plots

    def measure(self, device):
        b1500 = self.b1500
        self.check_stop(b1500)
        self.log(f'Starting Van der Pauw measurement on {device.name}')
        self.runner.configure_plot(f'Van der Pauw — {device.name}', self.plot_definitions(),
                                   column_ratios=(1.6, 1.0, 1.0))
        rows, readings_by_contacts = [], {}
        self._result = None
        base = self.format_filename('VanDerPauw', device.name)
        try:
            b1500.reset()
            b1500.enable_error_detect(True)
            b1500.configure_smu_acquisition(
                [getattr(self, f'{contact}_channel') for contact in ('TL', 'TR', 'BL', 'BR')],
                adc=self.adc_type, mode=self.adc_mode, coefficient=self.adc_coefficient,
                parallel=self.parallel_measurement, autozero=self.adc_autozero,
                auto_calibration=self.auto_calibration,
                source_wait_factor=self.source_wait_factor, source_wait_offset=self.source_wait_offset,
                measurement_wait_factor=self.measurement_wait_factor,
                measurement_wait_offset=self.measurement_wait_offset,
            )
            for contact_sweep in CONTACT_SWEEPS:
                self.check_stop(b1500)
                name = contact_sweep[0]
                self.log(f'Measuring SMUs: {self.sweep_label(contact_sweep)}')
                readings_by_contacts[name] = self.perform_iv_sweep(b1500, contact_sweep, rows)
                self._plot_raw(name, readings_by_contacts[name])
            result = analyze_measurement(readings_by_contacts, self.points)
            self._result = result
            self.save_data([r.csv_row() for r in rows], f'{base}.csv', RAW_HEADERS, add_timestamp=False)
        except Exception:
            # The runner owns abort/error instrument cleanup. Do not issue further
            # instrument commands here, including after transport cancellation.
            if rows:
                try:
                    self.save_data([r.csv_row() for r in rows], f'{base}.csv',
                                   RAW_HEADERS, add_timestamp=False)
                except Exception as save_error:
                    self.log(f'Could not save partial Van der Pauw data: {save_error}')
            raise

        plot = self.runner.plot
        if plot is not None:
            self.runner.configure_plot(f'Van der Pauw — {device.name}', self.plot_definitions(result),
                                       column_ratios=(1.6, 1.0, 1.0))
            for name, readings in readings_by_contacts.items():
                self._plot_raw(name, readings)
            for source, column in (('sheet_forward', 2), ('sheet_swapped', 3)):
                plot.replace_source(source, [p[0] * 1e6 for p in result['pairs']],
                                    [p[column] for p in result['pairs']])
            plot.replace_source('sheet_fit', [0.0, abs(self.ibias) * 1e6], [result['sheet']] * 2)
        self.log(f"Van der Pauw: Rs = {result['sheet']:.6g} Ω/□")
        for sweep in CONTACT_SWEEPS[::2]:
            self.log(f"{self.sweep_label(sweep)}: swap difference {result['swap_differences'][sweep[0]]:+.2f}%")
        self.log(f"Opposite-edge differences: top/bottom {result['opposite_differences'][0]:+.2f}%, "
                 f"right/left {result['opposite_differences'][1]:+.2f}%")
        self.save_plot_png(f'{base}_plot.png')
        self.log(f'Van der Pauw measurement completed for {device.name}')

    def perform_iv_sweep(self, b1500, contact_sweep, all_rows):
        name, *terminals = contact_sweep
        source_smu, return_smu, high_smu, low_smu = self.smu_numbers(contact_sweep)
        label = self.sweep_label(contact_sweep)
        source, ret, high, low = [getattr(self, f'{t}_channel') for t in terminals]
        channels = [source, high, ret, low]
        modes = [B1500_IM_MODE, B1500_VM_MODE, B1500_IM_MODE, B1500_VM_MODE]
        self.prepare_asu_channels(b1500, channels)
        b1500.set_switch(B1500_CH_ALL, False)
        for channel in channels:
            b1500.set_switch(channel, True)
        b1500.force_voltage(ret, 0.0, compliance=self.current_compliance)
        for channel in (high, low):
            b1500.force_current(channel, 0.0, compliance=self.voltage_compliance, range_=B1500_AUTO_RANGE)
        b1500.reset_timestamp()
        b1500.set_iv_sweep(
            source, B1500_SWP_IF_SGLLIN, B1500_AUTO_RANGE,
            -abs(self.ibias), abs(self.ibias), self.points,
            hold=self.hold_time, delay=self.delay_time, second_delay=self.second_delay,
            compliance=self.voltage_compliance, power_compliance=self.power_compliance,
        )
        self.check_stop(b1500)
        b1500.start_measure(channels, modes,
                            [self.current_measurement_range, self.measurement_range,
                             self.current_measurement_range, self.measurement_range],
                            source_output=1, timestamp=1)
        data = {ch: [] for ch in channels}
        expected = dict(zip(channels, modes))
        outputs, seen = [], set()
        pending_time = math.nan
        rows = []
        last_plot_time = 0.0
        plotted_count = 0

        def collect_readings():
            # Pair records by point only once all four SMUs have reported.
            # Rebuild from the buffers so trailing output/status records are
            # included in the final saved data even if a point was plotted earlier.
            count = min((len(values) for values in data.values()), default=0)
            return [Reading(
                f'{source_smu}->{return_smu}', f'{high_smu}-{low_smu}', i,
                outputs[i][0] if i < len(outputs) else math.nan,
                data[source][i][0], data[ret][i][0],
                data[high][i][0], data[low][i][0], data[source][i][2],
                data[source][i][1], data[ret][i][1], data[high][i][1], data[low][i][1],
                outputs[i][1] if i < len(outputs) else 0,
            ) for i in range(count)]

        try:
            while True:
                self.check_stop(b1500)
                _ret, eod, kind, value, status, channel = b1500.read_data()
                if status and (channel, kind, status) not in seen:
                    seen.add((channel, kind, status))
                    self.runner.report_status(dict(channel=channel, data_type=kind, status=status,
                                                   desc=describe_status_bits(status)))
                if channel in data and kind == expected[channel]:
                    data[channel].append((value, status, pending_time))
                    pending_time = math.nan
                elif kind == 3 and channel in (source, B1500_CH_NOCH, B1500_CH_ALL):
                    outputs.append((value, status))
                elif kind == 5:
                    # B1500 Programming Guide, Data Output Format 1-26:
                    # each TimeN precedes its DataN, including multi-SMU sweeps.
                    pending_time = value
                count = min(len(values) for values in data.values())
                now = time.monotonic()
                if count > plotted_count and (plotted_count == 0 or now - last_plot_time >= 0.1):
                    self._plot_raw(name, collect_readings())
                    plotted_count = count
                    last_plot_time = now
                # Drain through EOD, including trailing source status/time records.
                if eod:
                    break
        finally:
            rows = collect_readings()
            all_rows.extend(rows)
        b1500.finish_measure()
        # CL disables the channels and resets output settings; DZ before it is redundant.
        b1500.set_switch(B1500_CH_ALL, False)
        self.log(f'{label}: collected {len(rows)} points')
        return rows

    def _plot_raw(self, name, rows):
        plot = self.runner.plot
        if plot is None:
            return
        for suffix, flagged in (('raw', False), ('flagged', True)):
            selected = [r for r in rows if bool(r.status) == flagged and r.finite]
            plot.replace_source(f'{name}_{suffix}', [r.current * 1e6 for r in selected],
                                [r.voltage * 1e3 for r in selected])
        fit = fit_iv_curve(rows)
        if fit is None:
            return
        currents = [r.current for r in rows if r.finite]
        endpoints = [min(currents), max(currents)]
        plot.replace_source(f'{name}_fit', [i * 1e6 for i in endpoints],
                            [(fit.slope * i + fit.intercept) * 1e3 for i in endpoints])
