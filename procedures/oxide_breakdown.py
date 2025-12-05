import os

from procedures.base import MeasurementProcedure, MeasurementAbortRequested
from bindings import B1500Session, SMU_CHANNEL_MAP


class OxideBreakdownProcedure(MeasurementProcedure):
    """
    Two-terminal oxide breakdown sweep.
    Forces a voltage ramp on the high SMU while holding the low SMU at 0 V,
    measuring the sourced voltage and current at each step.
    """
    def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
        super().__init__(settings, output_root, output_relative, runner, fallback_root)
        self.gpib_address = settings.get('gpib_address', 'GPIB0::17::INSTR')

        self.high_channel = SMU_CHANNEL_MAP.get(str(settings.get('high_channel', 4)), settings.get('high_channel', 4))
        self.low_channel = SMU_CHANNEL_MAP.get(str(settings.get('low_channel', 3)), settings.get('low_channel', 3))
        self.sense_high = SMU_CHANNEL_MAP.get(str(settings.get('sense_high', None)), settings.get('sense_high', None))
        self.sense_low = SMU_CHANNEL_MAP.get(str(settings.get('sense_low', None)), settings.get('sense_low', None))

        self.start_voltage = settings.get('start_voltage', 0.0)
        self.v_max = settings.get('v_max', 15.0)
        self.points = max(1, int(float(settings.get('points', 75))))
        self.current_compliance = float(settings.get('current_compliance', 1e-3))
        self.current_range = float(settings.get('current_range', B1500Session.AUTO_RANGE))
        self.double_sweep = bool(settings.get('double_sweep', True))

        # Timing controls (optional; default to immediate sweep)
        self.hold_time = float(settings.get('hold_time', 0.0))
        self.delay_time = float(settings.get('delay_time', 0.0))
        self.second_delay = float(settings.get('second_delay', 0.0))

        # Optional ASU configuration
        self.asu_channels = settings.get('asu_channels', [])
        self.asu_path_mode = settings.get('asu_path_mode', None)
        self.asu_range_mode = settings.get('asu_range_mode', None)

        # Normalize ASU channel labels to numeric indices
        self.asu_channels = [SMU_CHANNEL_MAP.get(str(ch), ch) for ch in self.asu_channels]

    def run(self, b1500: B1500Session, device):
        runner = self.runner
        self.log(f'Starting Oxide Breakdown sweep on {device.name}')
        try:
            # Initialize B1500 session
            self.check_stop(b1500)
            b1500.reset()
            b1500.set_timeout(10000)
            b1500.enable_error_detect(True)
            # Do not abort the sweep on compliance; hold final level at end.
            b1500.stop_mode(B1500Session.STOP_DISABLE, B1500Session.LAST_START)

            results = self.perform_breakdown_sweep(b1500, device)

            base = self.format_filename("OxideBreakdown", device.name)
            filename = f'{base}.csv'
            csv_path = self.save_data(
                results,
                filename,
                ['Voltage_V', 'Current_High_A', 'Current_Low_A', 'Time_sec', 'Status'],
                add_timestamp=False
            )
            plot_filename = f'{base}_plot.png'
            runner.finalize_plot(plot_filename, self.output_root, self.output_relative, self.fallback_root)
            self.log(f'Oxide breakdown sweep completed for {device.name}')
        except Exception as e:
            self.log(f'Error during oxide breakdown sweep: {str(e)}')
            raise

    def perform_breakdown_sweep(self, b1500: B1500Session, device):
        """Run a voltage sweep on the high SMU and record voltage/current pairs."""
        runner = self.runner
        high = self.high_channel
        low = self.low_channel
        sense_high = self.sense_high
        sense_low = self.sense_low

        self.check_stop(b1500)

        # Enable SMUs
        b1500.set_switch(high, True)
        b1500.set_switch(low, True)
        # use the other SMUs to sense voltage (i.e. force zero current)
        if sense_high is not None:
            b1500.set_switch(sense_high, True)
            b1500.force_current(sense_high, 0.0, B1500Session.AUTO_RANGE)
        if sense_low is not None:
            b1500.set_switch(sense_low, True)
            b1500.force_current(sense_low, 0.0, B1500Session.AUTO_RANGE)

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
        sweep_mode = B1500Session.SWP_VF_DBLLIN if self.double_sweep else B1500Session.SWP_VF_SGLLIN
        b1500.set_iv_sweep(
            high,
            sweep_mode,
            B1500Session.AUTO_RANGE,
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

        runner.start_live_plot(
            title=f'Oxide Breakdown - {device.name}',
            xlabel='Voltage (V)',
            ylabel='Current (A)',
            series_label=None,
            series_labels=['$I_+(V)$', '$-I_-(V)$'],
            styles={
                '$I_+(V)$': {'color': 'C0'},
                '$-I_-(V)$': {'color': 'C1'},
                'log(I)': {'color': 'k', 'linestyle': 'dashed'}
            },
            secondary_series=['log(I)'],
            secondary_ylabel='log(I) (A)',
            secondary_yscale='log'
        )

        # Begin sweep with streaming readout
        channels = [high, low]
        modes = [B1500Session.IM_MODE, B1500Session.IM_MODE]
        ranges = [self.current_range, self.current_range]
        if sense_high is not None:
            channels.append(sense_high)
            modes.append(B1500Session.VM_MODE)
            ranges.append(B1500Session.AUTO_RANGE)
        if sense_low is not None:
            channels.append(sense_low)
            modes.append(B1500Session.VM_MODE)
            ranges.append(B1500Session.AUTO_RANGE)

        self.check_stop(b1500)

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
                    desc = B1500Session.describe_status_bits(status)
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
                if channel in (high, b1500.CH_NOCH, b1500.CH_ALL) and len(v_source_values) < max_points:
                    v_source_values.append(value)
                    v_source_status.append(status)
            elif data_type == 5:  # timestamp
                timestamps.append(value)

            # Update plot with any newly paired points
            while plotted < min(len(high_currents), len(low_currents), max_points):
                v_val = v_source_values[plotted] if plotted < len(v_source_values) else voltages[plotted]
                ip_val = high_currents[plotted]
                in_val = low_currents[plotted]
                runner.add_live_point(v_val, ip_val, '$I_+(V)$')
                runner.add_live_point(v_val, -in_val, '$-I_-(V)$')
                plotted += 1

            if eod or plotted >= max_points:
                break

        # Ensure any remaining points are pushed to the plot
        for idx in range(plotted, min(len(high_currents), len(low_currents), max_points)):
            v_val = v_source_values[idx] if idx < len(v_source_values) else voltages[idx]
            ip_val = high_currents[idx]
            in_val = low_currents[idx]
            runner.add_live_point(v_val, ip_val, '$I_+(V)$')
            runner.add_live_point(v_val, -in_val, '$-I_-(V)$')

        # Add log-magnitude series once, at the end, in one shot
        floor = 1e-15
        xs = [v_source_values[idx] if idx < len(v_source_values) else voltages[idx] for idx in range(min(len(high_currents), max_points))]
        ys = [max(abs(high_currents[idx]), floor) for idx in range(min(len(high_currents), max_points))]
        runner.add_live_series(xs, ys, 'log(I)')

        results = []
        point_count = min(max_points, len(high_currents), len(low_currents))
        for i in range(point_count):
            v_val = v_source_values[i] if i < len(v_source_values) else voltages[i]
            ip_val = high_currents[i]
            in_val = low_currents[i]
            t_val = timestamps[i] if i < len(timestamps) else 0.0
            status_combined = 0
            if i < len(i_high_status):
                status_combined |= i_high_status[i]
            if i < len(i_low_status):
                status_combined |= i_low_status[i]
            if i < len(v_source_status):
                status_combined |= v_source_status[i]
            results.append([v_val, ip_val, in_val, t_val, status_combined])

        self.log(f'Collected {len(results)} oxide breakdown points')
        return results

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
