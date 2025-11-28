import os
from procedures.base import MeasurementProcedure
from bindings import B1500Session, SMU_CHANNEL_MAP

class FourTerminalIVProcedure(MeasurementProcedure):
    def __init__(self, settings, output_dir):
        super().__init__(settings, output_dir)
        # Default settings for 4-terminal I-V sweep
        self.gpib_address = settings.get('gpib_address', 'GPIB0::17::INSTR')

        # SMU channel assignments for 4-terminal measurement (default to installed modules on this tool)
        self.force_high_channel = settings.get('force_high_channel', 4)  # Force high terminal
        self.sense_high_channel = settings.get('sense_high_channel', 5)  # Sense high terminal
        self.force_low_channel = settings.get('force_low_channel', 3)   # Force low terminal
        self.sense_low_channel = settings.get('sense_low_channel', 6)   # Sense low terminal

        # Sweep parameters (current forcing for 4-terminal measurement)
        self.start_current = settings.get('start_current', 0.0)
        self.stop_current = settings.get('stop_current', 1e-6)
        self.points = settings.get('points', 75)
        self.voltage_compliance = settings.get('voltage_compliance', 10.0)  # Voltage compliance
        self.power_compliance = settings.get('power_compliance', 0.0)
        self.measurement_range = settings.get('measurement_range', 0.0)  # Voltage measurement range (0 = auto)
        self.current_compliance = settings.get('current_compliance', 0.01)  # Current limit when holding 0 V on return

        # Timing parameters
        self.hold_time = settings.get('hold_time', 0.0)
        self.delay_time = settings.get('delay_time', 0.0)
        self.second_delay = settings.get('second_delay', 0.0)

        # Optional ASU configuration
        self.asu_channels = settings.get('asu_channels', [])
        self.asu_path_mode = settings.get('asu_path_mode', None)
        self.asu_range_mode = settings.get('asu_range_mode', None)

        # Normalize SMU names to channel numbers if needed
        self.force_high_channel = SMU_CHANNEL_MAP.get(str(self.force_high_channel), self.force_high_channel)
        self.sense_high_channel = SMU_CHANNEL_MAP.get(str(self.sense_high_channel), self.sense_high_channel)
        self.force_low_channel = SMU_CHANNEL_MAP.get(str(self.force_low_channel), self.force_low_channel)
        self.sense_low_channel = SMU_CHANNEL_MAP.get(str(self.sense_low_channel), self.sense_low_channel)

    def run(self, device, runner):
        self.log(f'Starting 4-Terminal I-V Sweep on {device.name}', runner)
        self.log(
            f'ASU config -> channels: {self.asu_channels}, path: {self.asu_path_mode}, range: {self.asu_range_mode}',
            runner
        )

        try:
            # Initialize B1500 session
            b1500 = B1500Session(self.gpib_address)
            b1500.reset()
            b1500.set_timeout(10000)  # 10 second timeout
            b1500.enable_error_detect(True)
            self.log(f'Connected to B1500 at {self.gpib_address}', runner)

            # Perform the I-V sweep
            results = self.perform_iv_sweep(b1500, device, runner)

            # Save results
            base = self.format_filename(runner, "FourTerminalIV", device.name)
            filename = f'{base}.csv'
            self.save_data(results, filename,
                          ['Current_A', 'VoltageHigh_V', 'VoltageLow_V', 'Time_sec', 'Status'],
                          runner, add_timestamp=False)
            plot_path = self.make_output_path(f'{base}_plot.png', add_timestamp=False)
            runner.finalize_plot(plot_path)
            self.log(f'4-Terminal I-V sweep completed for {device.name}', runner)

        except Exception as e:
            self.log(f'Error during 4-terminal I-V sweep: {str(e)}', runner)
            raise
        finally:
            try:
                b1500.close()
            except:
                pass

    def perform_iv_sweep(self, b1500: B1500Session, device, runner):
        """
        Perform the 4-terminal I-V sweep measurement.
        Forces current through force terminals, holds a return SMU at 0 V, and measures voltage on two sense SMUs.
        Returns list of [Current, VoltageDiff, Time, Status] tuples.
        """
        source_channel = self.force_high_channel
        return_channel = self.force_low_channel
        sense_high = self.sense_high_channel
        sense_low = self.sense_low_channel

        # Enable all four SMUs
        b1500.set_switch(source_channel, True)
        b1500.set_switch(return_channel, True)
        b1500.set_switch(sense_high, True)
        b1500.set_switch(sense_low, True)

        # If requested, configure ASU path/range for low-leakage channels
        asu_list = [SMU_CHANNEL_MAP.get(str(ch), ch) for ch in self.asu_channels] if self.asu_channels else []
        for ch in asu_list:
            if self.asu_path_mode is not None:
                b1500.asu_path(ch, self.asu_path_mode)
            if self.asu_range_mode is not None:
                b1500.asu_range(ch, self.asu_range_mode)

        # Reset timestamp
        b1500.reset_timestamp()

        # Hold the return SMU at 0 V with a safe current compliance
        b1500.force_voltage(return_channel, 0.0, self.current_compliance)
        b1500.force_current(sense_high, 0.0, B1500Session.AUTO_RANGE)
        b1500.force_current(sense_low, 0.0, B1500Session.AUTO_RANGE)

        # Generate current sweep vector (inclusive of stop)
        if self.points < 2:
            current_points = [self.start_current]
        else:
            step = (self.stop_current - self.start_current) / (self.points - 1)
            current_points = [self.start_current + i * step for i in range(self.points)]

        # Program the sweep on the source channel
        b1500.set_ic_sweep(
            source_channel,
            B1500Session.SWP_IF_SGLLIN,
            B1500Session.AUTO_RANGE,
            self.start_current,
            self.stop_current,
            self.points,
            hold=self.hold_time,
            delay=self.delay_time,
            second_delay=self.second_delay,
            compliance=self.voltage_compliance,
            power_compliance=self.power_compliance
        )

        # Configure multi-channel measurement and run sweepMiv to capture data
        channels = [source_channel, sense_high, return_channel, sense_low]
        modes = [B1500Session.IM_MODE, B1500Session.VM_MODE, B1500Session.IM_MODE, B1500Session.VM_MODE]
        ranges = [B1500Session.AUTO_RANGE, B1500Session.AUTO_RANGE, B1500Session.AUTO_RANGE, B1500Session.AUTO_RANGE]

        # Initialize live plot
        runner.start_live_plot(
            title=f'4-Terminal I-V - {device.name}',
            xlabel='Current (A)',
            ylabel='Voltage (V)',
            series_label='V(I)',
            styles={'V(I)': {'marker': 'x'}, 'R_fit': {'marker': None, 'color': 'C1'}},
            secondary_series=[]
        )

        # Start streaming for live plot updates and full capture
        b1500.start_measure(channels, modes, ranges, source_output=1, timestamp=1)
        data_by_ch = {ch: [] for ch in channels}
        status_by_ch = {ch: [] for ch in channels}
        timestamps = []
        source_values = []
        source_status = []
        plotted = 0
        max_points = len(current_points)
        while True:
            eod, data_type, value, status, channel = b1500.read_data()
            if channel in data_by_ch and data_type in (1, 2): # I measure, V measure
                if len(data_by_ch[channel]) < max_points:
                    data_by_ch[channel].append(value)
                    status_by_ch[channel].append(status)
            elif data_type in (3, 4):  # source output data
                source_values.append(value)
                source_status.append(status)
            elif data_type == 5:
                timestamps.append(value)

            # Push live plot when we have paired sense readings and source current
            paired = min(len(data_by_ch[sense_high]), len(data_by_ch[sense_low]), len(data_by_ch[source_channel]), max_points)
            while plotted < paired:
                idx = plotted
                v_diff = data_by_ch[sense_high][idx] - data_by_ch[sense_low][idx]
                current_set = data_by_ch[source_channel][idx]
                runner.add_live_point(current_points[idx], v_diff, 'V(I)')
                plotted += 1

            # Stop if we received all expected points or instrument signaled end
            if eod or plotted >= max_points:
                break

        results = []
        point_count = min(len(current_points), len(data_by_ch[source_channel]), len(data_by_ch[sense_high]), len(data_by_ch[sense_low]))
        # Compute a simple linear regression V = R*I + b for the differential voltage
        if point_count >= 2:
            currents = data_by_ch[source_channel][:point_count]
            voltages = [data_by_ch[sense_high][i] - data_by_ch[sense_low][i] for i in range(point_count)]
            mean_i = sum(currents) / point_count
            mean_v = sum(voltages) / point_count
            num = sum((currents[i] - mean_i) * (voltages[i] - mean_v) for i in range(point_count))
            den = sum((currents[i] - mean_i) ** 2 for i in range(point_count))
            slope = num / den if den != 0 else None
            intercept = mean_v - (slope * mean_i) if slope is not None else None
            if slope is not None:
                x_min, x_max = min(currents), max(currents)
                y_min = slope * x_min + (intercept or 0.0)
                y_max = slope * x_max + (intercept or 0.0)
                label = f'R_fit={slope/1e3:.2f} kΩ'
                runner.add_live_point(x_min, y_min, label)
                runner.add_live_point(x_max, y_max, label)
        for i in range(point_count):
            current_set = data_by_ch[source_channel][i]
            v_high = data_by_ch[sense_high][i]
            v_low = data_by_ch[sense_low][i]
            t_val = timestamps[i] if i < len(timestamps) else 0.0
            status_combined = max(
                status_by_ch[sense_high][i] if i < len(status_by_ch[sense_high]) else 0,
                status_by_ch[sense_low][i] if i < len(status_by_ch[sense_low]) else 0,
                status_by_ch[source_channel][i] if i < len(status_by_ch[source_channel]) else 0,
            )
            results.append([
                current_set,
                v_high,
                v_low,
                t_val,
                status_combined
            ])

        # Zero outputs and disable switches
        b1500.zero_output(B1500Session.CH_ALL)
        b1500.set_switch(B1500Session.CH_ALL, False)

        self.log(f'Collected {len(results)} 4-terminal I-V sweep points', runner)
        return results
