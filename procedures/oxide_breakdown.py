from procedures.base import MeasurementProcedure
from bindings import B1500Session, SMU_CHANNEL_MAP


class OxideBreakdownProcedure(MeasurementProcedure):
    """
    Two-terminal oxide breakdown sweep.
    Forces a voltage ramp on the high SMU while holding the low SMU at 0 V,
    measuring the sourced voltage and current at each step.
    """
    def __init__(self, settings, output_dir):
        super().__init__(settings, output_dir)
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

    def run(self, device, runner):
        self.log(f'Starting Oxide Breakdown sweep on {device.name}', runner)
        try:
            b1500 = B1500Session(self.gpib_address)
            b1500.reset()
            b1500.set_timeout(10000)
            b1500.enable_error_detect(True)
            # Do not abort the sweep on compliance; hold final level at end.
            b1500.stop_mode(B1500Session.STOP_DISABLE, B1500Session.LAST_START)
            self.log(f'Connected to B1500 at {self.gpib_address}', runner)

            results = self.perform_breakdown_sweep(b1500, device, runner)

            base = self.format_filename(runner, "OxideBreakdown", device.name)
            filename = f'{base}.csv'
            self.save_data(
                results,
                filename,
                ['Voltage_V', 'Current_High_A', 'Current_Low_A', 'Time_sec', 'Status'],
                runner,
                add_timestamp=False
            )
            plot_path = self.make_output_path(f'{base}_plot.png', add_timestamp=False)
            runner.finalize_plot(plot_path)
            self.log(f'Oxide breakdown sweep completed for {device.name}', runner)
        except Exception as e:
            self.log(f'Error during oxide breakdown sweep: {str(e)}', runner)
            raise
        finally:
            try:
                b1500.close()
            except Exception:
                self.log('Warning: Failed to close B1500 session', runner)
                pass

    def perform_breakdown_sweep(self, b1500: B1500Session, device, runner):
        """Run a voltage sweep on the high SMU and record voltage/current pairs."""
        high = self.high_channel
        low = self.low_channel
        sense_high = self.sense_high
        sense_low = self.sense_low

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

        b1500.start_measure(
            channels,
            modes,
            ranges,
            source_output=1,
            timestamp=1
        )
        # Allow stop button to abort safely
        self.register_abort_handler(runner, lambda: self.abort_b1500(b1500))

        high_currents, i_high_status = [], []
        low_currents, i_low_status = [], []
        sense_high_voltages = []
        sense_low_voltages = []

        v_source_values, v_source_status = [], [] # source = high SMU, but forced (not measured)
        timestamps = []
        plotted = 0
        nonzero_statuses = set()

        while True:
            if self.stop_requested(runner):
                self.log("Stop requested; aborting measurement", runner)
                self.abort_b1500(b1500)
                break
            try:
                _ret, eod, data_type, value, status, channel = b1500.read_data()
            except Exception as exc:
                self.log(f'B1500 read_data error', runner)
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

        if not self.stop_requested(runner):
            # Ensure any remaining points are pushed to the plot
            for idx in range(plotted, min(len(high_currents), len(low_currents), max_points)):
                v_val = v_source_values[idx] if idx < len(v_source_values) else voltages[idx]
                ip_val = high_currents[idx]
                in_val = low_currents[idx]
                runner.add_live_point(v_val, ip_val, '$I_+(V)$')
                runner.add_live_point(v_val, -in_val, '$-I_-(V)$')

        if not self.stop_requested(runner):
            # Add log-magnitude series once, at the end, on a log-scale secondary axis
            floor = 1e-15
            for idx in range(min(len(high_currents), max_points)):
                v_val = v_source_values[idx] if idx < len(v_source_values) else voltages[idx]
                mag_i = max(abs(high_currents[idx]), floor)
                runner.add_live_point(v_val, mag_i, 'log(I)')

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

        # Return instrument to safe state
        self.abort_b1500(b1500)

        self.log(f'Collected {len(results)} oxide breakdown points', runner)
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
