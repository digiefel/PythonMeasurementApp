import math
import os

from plotting import PlotDef, Curve, HLine, LinearFit, linear_fit
from procedures.base import Choice, MeasurementProcedure, MeasurementAbortRequested, OptionalSMU, SMU, parameter
from instrumentio.constants import B1500_CURRENT_RANGES
from instrumentio.codes import (
    B1500_AUTO_RANGE,
    B1500_CH_ALL,
    B1500_CH_NOCH,
    B1500_IM_MODE,
    B1500_LAST_START,
    B1500_STOP_DISABLE,
    B1500_SWP_VF_DBLLIN,
    B1500_SWP_VF_SGLLIN,
    B1500_VM_MODE,
)
from instrumentio.descriptors import describe_status_bits


class IVSweepProcedure(MeasurementProcedure):
    """
    Two-terminal IV sweep.
    Forces a voltage ramp on the high SMU while holding the low SMU at 0 V,
    measuring the sourced voltage and current at each step.
    """
    NAME = "IVSweep"
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('high_channel', 'High SMU', 4, SMU),
        parameter('low_channel', 'Low SMU', 3, SMU),
        parameter('sense_high', 'Sense High SMU (optional)', None, OptionalSMU),
        parameter('sense_low', 'Sense Low SMU (optional)', None, OptionalSMU),
        parameter('start_voltage', 'Start Voltage (V)', 0.0, float),
        parameter('v_max', 'Vmax (V)', 15.0, float),
        parameter('points', 'Points', 75, int),
        parameter('double_sweep', 'Double Sweep (return)', True, bool),
        parameter('current_compliance', 'Current Compliance (A)', 1e-3, float),
        parameter('current_range', 'Current Range (A)', B1500_AUTO_RANGE, Choice(B1500_CURRENT_RANGES, float)),
        parameter('hold_time', 'Hold Time (s)', 0.0, float),
        parameter('delay_time', 'Delay Time (s)', 0.0, float),
        parameter('second_delay', 'Second Delay (s)', 0.0, float),
    )

    def measure(self, device):
        b1500 = self.b1500
        runner = self.runner
        self.log(f'Starting IV sweep on {device.name}')
        try:
            # Initialize B1500 session
            self.check_stop(b1500)
            b1500.reset()
            b1500.set_timeout(10000)
            b1500.enable_error_detect(True)
            # Do not abort the sweep on compliance; hold final level at end.
            b1500.stop_mode(B1500_STOP_DISABLE, B1500_LAST_START)

            results = self.perform_iv_sweep(b1500, device)

            self.save_measurement_outputs(
                results,
                "IVSweep",
                device,
                ['Voltage_V', 'Current_High_A', 'Current_Low_A', 'Time_sec', 'Status'],
            )
            self.log(f'IV sweep completed for {device.name}')
        except Exception as e:
            self.log(f'Error during IV sweep: {str(e)}')
            raise

    def perform_iv_sweep(self, b1500, device):
        """Run a voltage sweep on the high SMU and record voltage/current pairs."""
        runner = self.runner
        high = self.high_channel
        low = self.low_channel
        sense_high = self.sense_high
        sense_low = self.sense_low

        self.check_stop(b1500)

        # make sure that all channels are open unless otherwise configured
        b1500.set_switch(B1500_CH_ALL, False)
        # Enable the force pair; optional sense SMUs are enabled below as high-impedance voltage probes.
        b1500.set_switch(high, True)
        b1500.set_switch(low, True)
        # use the other SMUs to sense voltage (i.e. force zero current)
        if sense_high is not None:
            b1500.set_switch(sense_high, True)
            b1500.force_current(sense_high, 0.0, B1500_AUTO_RANGE)
        if sense_low is not None:
            b1500.set_switch(sense_low, True)
            b1500.force_current(sense_low, 0.0, B1500_AUTO_RANGE)

        # Apply ASU config if present
        self.check_stop(b1500)
        for ch in self.asu_channels:
            if self.asu_path_mode is not None:
                b1500.asu_path(ch, self.asu_path_mode)
            if self.asu_range_mode is not None:
                b1500.asu_range(ch, self.asu_range_mode)

        # Prepare sweep vector
        voltages = self._build_voltage_vector()
        max_points = len(voltages)

        # Hold low terminal at 0 V with compliance
        b1500.reset_timestamp()
        b1500.force_voltage(low, 0.0, self.current_compliance)

        # Program voltage sweep on high terminal
        # The B1500 performs the actual ramp; _build_voltage_vector mirrors it for fallback plot/CSV x values.
        sweep_mode = B1500_SWP_VF_DBLLIN if self.double_sweep else B1500_SWP_VF_SGLLIN
        b1500.set_iv_sweep(
            high,
            sweep_mode,
            B1500_AUTO_RANGE,
            self.start_voltage,
            self.v_max,
            self.points,
            hold=self.hold_time,
            delay=self.delay_time,
            second_delay=self.second_delay,
            compliance=self.current_compliance,
            power_compliance=0.0
        )

        self.check_stop(b1500)

        runner.configure_plot(f'IV sweep - {device.name}', [
            PlotDef(
                "iv",
                row=0,
                col=0,
                rowspan=2,
                title="Current",
                xlabel="Voltage (V)",
                ylabels=("Current (A)",),
                elements=[
                    Curve("I_pos", color="C0", legend_label="I+(V)"),
                    Curve("I_neg", color="C1", legend_label="-I-(V)"),
                    LinearFit(
                        "I_pos",
                        color="C3",
                        legend_label_template="Fit (R={resistance_si})",
                    ),
                ],
            ),
            PlotDef(
                "log_i",
                row=0,
                col=1,
                title="log |I|",
                xlabel="Voltage (V)",
                ylabels=("log |I| (A)",),
                yscales=("log",),
                xlink="iv",
                elements=[
                    Curve("log_I", color="C2", legend_label="|I+|(V)"),
                ],
            ),
            PlotDef(
                "resistance",
                row=1,
                col=1,
                title="Resistance",
                xlabel="Voltage (V)",
                ylabels=("Resistance (Ohm)",),
                xlink="iv",
                elements=[
                    Curve("R_fit", color="C3", legend_label="R(V)"),
                    HLine(source="R_fit", color="C7", legend_label="Latest fit R"),
                ],
            ),
        ], row_ratios=(1.0, 1.0), column_ratios=(2.0, 1.0))

        # Begin sweep with streaming readout
        channels = [high, low]
        modes = [B1500_IM_MODE, B1500_IM_MODE]
        ranges = [self.current_range, self.current_range]
        if sense_high is not None:
            channels.append(sense_high)
            modes.append(B1500_VM_MODE)
            ranges.append(B1500_AUTO_RANGE)
        if sense_low is not None:
            channels.append(sense_low)
            modes.append(B1500_VM_MODE)
            ranges.append(B1500_AUTO_RANGE)

        self.check_stop(b1500)

        # start_measure streams interleaved records: high I, low I, optional sense V, source V, and timestamps.
        b1500.start_measure(
            channels,
            modes,
            ranges,
            source_output=1,
            timestamp=1
        )

        high_currents, i_high_status = [], []
        low_currents, i_low_status = [], []
        sense_high_voltages = []
        sense_low_voltages = []

        v_source_values, v_source_status = [], [] # source = high SMU, but forced (not measured)
        timestamps = []
        plotted = 0
        nonzero_statuses = set()
        floor = 1e-15

        while True:
            try:
                self.check_stop(b1500)
                _ret, eod, data_type, value, status, channel = b1500.read_data()
            except MeasurementAbortRequested:
                raise
            except Exception as exc:
                self.log(f'B1500 read_data error: {exc}')
                raise
            if status:
                key = (channel, data_type, status)
                if key not in nonzero_statuses:
                    nonzero_statuses.add(key)
                    desc = describe_status_bits(status)
                    runner.report_status({
                        "channel": channel,
                        "data_type": data_type,
                        "status": status,
                        "desc": desc,
                    })
            if data_type == 1:  # I measurement
                if channel == high:
                    high_currents.append(value)
                    i_high_status.append(status)
                elif channel == low:
                    low_currents.append(value)
                    i_low_status.append(status)
            elif data_type == 2:  # V measurement
                if channel == sense_high:
                    sense_high_voltages.append(value)
                elif channel == sense_low:
                    sense_low_voltages.append(value)
            elif data_type == 4:  # source output (voltage)
                if channel in (high, B1500_CH_NOCH, B1500_CH_ALL) and len(v_source_values) < max_points:
                    # Source-output voltage is the programmed sweep value, not a separate voltage measurement.
                    v_source_values.append(value)
                    v_source_status.append(status)
            elif data_type == 5:  # timestamp
                timestamps.append(value)

            # Update plot with any newly paired points
            # High and low current records can arrive at different times, so plot only complete pairs.
            while plotted < min(len(high_currents), len(low_currents), max_points):
                v_val = v_source_values[plotted] if plotted < len(v_source_values) else voltages[plotted]
                ip_val = high_currents[plotted]
                in_val = low_currents[plotted]
                runner.plot.append_point("I_pos", v_val, ip_val)
                runner.plot.append_point("I_neg", v_val, -in_val)
                runner.plot.append_point("log_I", v_val, max(abs(ip_val), floor))
                self._update_resistance_source(runner, v_val)
                plotted += 1

            if eod or plotted >= max_points:
                break

        # Ensure any remaining points are pushed to the plot
        for idx in range(plotted, min(len(high_currents), len(low_currents), max_points)):
            v_val = v_source_values[idx] if idx < len(v_source_values) else voltages[idx]
            ip_val = high_currents[idx]
            in_val = low_currents[idx]
            runner.plot.append_point("I_pos", v_val, ip_val)
            runner.plot.append_point("I_neg", v_val, -in_val)
            runner.plot.append_point("log_I", v_val, max(abs(ip_val), floor))
            self._update_resistance_source(runner, v_val)

        results = []
        point_count = min(max_points, len(high_currents), len(low_currents))
        for i in range(point_count):
            v_val = v_source_values[i] if i < len(v_source_values) else voltages[i]
            ip_val = high_currents[i]
            in_val = low_currents[i]
            t_val = timestamps[i] if i < len(timestamps) else 0.0
            # Collapse per-record status bits into one CSV status column for the point.
            status_combined = 0
            if i < len(i_high_status):
                status_combined |= i_high_status[i]
            if i < len(i_low_status):
                status_combined |= i_low_status[i]
            if i < len(v_source_status):
                status_combined |= v_source_status[i]
            results.append([v_val, ip_val, in_val, t_val, status_combined])

        self.log(f'Collected {len(results)} IV sweep points')
        return results

    def _update_resistance_source(self, runner, voltage: float) -> None:
        ds = runner.plot.source("I_pos")
        if len(ds.x) < 2:
            return
        try:
            # Re-fit the full positive current trace after each point to show a live incremental resistance.
            fit = linear_fit(ds.x, ds.y)
        except Exception:
            return
        if fit.slope == 0.0 or not math.isfinite(fit.slope):
            return
        resistance = 1.0 / fit.slope
        if math.isfinite(resistance):
            runner.plot.append_point("R_fit", voltage, resistance)

    def _build_voltage_vector(self):
        if self.points < 2:
            base = [self.v_max]
        else:
            step = (self.v_max - self.start_voltage) / (self.points - 1)
            base = [self.start_voltage + i * step for i in range(self.points)]
        if self.double_sweep and len(base) > 1:
            # Return to the start voltage without duplicating the endpoint
            return base + base[-2::-1]
        return base
