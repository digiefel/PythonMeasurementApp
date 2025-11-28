import math
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
        b1500.set_iv_sweep(
            high,
            B1500Session.SWP_VF_SGLLIN,
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
            series_label='I(V)',
            styles={
                '$I_+(V)$': {'color': 'C0'},
                '$I_-(V)$': {'color': 'C1'},
                'log10(I)': {'color': 'k', 'linestyle': '--'}
            },
            secondary_series=['log10(I)'],
            secondary_ylabel='log10(|I|)'
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

        high_currents, i_high_status = [], []
        low_currents, i_low_status = [], []
        sense_high_voltages = []
        sense_low_voltages = []

        v_source_values, v_source_status = [], [] # source = high SMU, but forced (not measured)
        timestamps = []
        plotted = 0

        while True:
            eod, data_type, value, status, channel = b1500.read_data()
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
                if len(v_source_values) < max_points:
                    v_source_values.append(value)
                    v_source_status.append(status)
            elif data_type == 5:  # timestamp
                timestamps.append(value)

            # Update plot with any newly paired points
            while plotted < min(len(high_currents), len(low_currents), max_points):
                v_val = v_source_values[plotted] if plotted < len(v_source_values) else voltages[plotted]
                ip_val = high_currents[plotted]
                in_val = low_currents[plotted]
                log_i = math.log10(max(abs(ip_val), 1e-15))
                runner.add_live_point(v_val, ip_val, '$I_+(V)$')
                runner.add_live_point(v_val, in_val, '$I_-(V)$')
                runner.add_live_point(v_val, log_i, 'log10(I)')
                plotted += 1

            if eod or plotted >= max_points:
                break

        # Ensure any remaining points are pushed to the plot
        for idx in range(plotted, min(len(high_currents), len(low_currents), max_points)):
            v_val = v_source_values[idx] if idx < len(v_source_values) else voltages[idx]
            ip_val = high_currents[idx]
            in_val = low_currents[idx]
            log_i = math.log10(max(abs(ip_val), 1e-15))
            runner.add_live_point(v_val, ip_val, '$I_+(V)$')
            runner.add_live_point(v_val, in_val, '$I_-(V)$')
            runner.add_live_point(v_val, log_i, 'log10(I)')

        results = []
        point_count = min(max_points, len(high_currents), len(low_currents))
        for i in range(point_count):
            v_val = v_source_values[i] if i < len(v_source_values) else voltages[i]
            ip_val = high_currents[i]
            in_val = low_currents[i]
            log_i = math.log10(max(abs(ip_val), 1e-15))
            t_val = timestamps[i] if i < len(timestamps) else 0.0
            status_combined = max(
                i_high_status[i] if i < len(i_high_status) else 0,
                i_low_status[i] if i < len(i_low_status) else 0,
                v_source_status[i] if i < len(v_source_status) else 0
            )
            results.append([v_val, ip_val, in_val, t_val, status_combined])

        # Return instrument to safe state
        b1500.zero_output(B1500Session.CH_ALL)
        b1500.set_switch(B1500Session.CH_ALL, False)

        self.log(f'Collected {len(results)} oxide breakdown points', runner)
        return results

    def _build_voltage_vector(self):
        if self.points < 2:
            return [self.v_max]
        step = (self.v_max - self.start_voltage) / (self.points - 1)
        return [self.start_voltage + i * step for i in range(self.points)]
