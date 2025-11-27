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
        self.force_current_range = settings.get('force_current_range', 0.0)

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

        # Normalize SMU names to channel numbers if needed
        self.force_high_channel = SMU_CHANNEL_MAP.get(str(self.force_high_channel), self.force_high_channel)
        self.sense_high_channel = SMU_CHANNEL_MAP.get(str(self.sense_high_channel), self.sense_high_channel)
        self.force_low_channel = SMU_CHANNEL_MAP.get(str(self.force_low_channel), self.force_low_channel)
        self.sense_low_channel = SMU_CHANNEL_MAP.get(str(self.sense_low_channel), self.sense_low_channel)

    def run(self, device, runner):
        self.log(f'Starting 4-Terminal I-V Sweep on {device.name}', runner)

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
            filename = f'four_terminal_iv_{device.name}.csv'
            self.save_data(results, filename,
                          ['Current_A', 'Voltage_V', 'Time_sec', 'Status'],
                          runner)
            plot_path = self.make_output_path(f'four_terminal_iv_{device.name}_plot.png')
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

        # Reset timestamp
        b1500.reset_timestamp()

        # Hold the return SMU at 0 V with a safe current compliance
        b1500.force_voltage(return_channel, 0.0, self.current_compliance)

        # Generate current sweep vector (inclusive of stop)
        if self.points < 2:
            current_points = [self.start_current]
        else:
            step = (self.stop_current - self.start_current) / (self.points - 1)
            current_points = [self.start_current + i * step for i in range(self.points)]

        results = []

        runner.start_live_plot(
            title=f'4-Terminal I-V - {device.name}',
            xlabel='Current (A)',
            ylabel='Voltage (V)',
            series_label='V(I)'
        )

        # Sweep by stepping current; measure voltages on both sense channels per point
        for idx, current_set in enumerate(current_points):
            b1500.force_current(source_channel, current_set, self.voltage_compliance, self.force_current_range)

            if self.delay_time > 0:
                import time
                time.sleep(self.delay_time)

            v_high, status_high, t_high = b1500.spot_meas(sense_high, B1500Session.VM_MODE, self.measurement_range)
            v_low, status_low, _ = b1500.spot_meas(sense_low, B1500Session.VM_MODE, self.measurement_range)

            v_diff = v_high - v_low
            status_combined = max(status_high, status_low)

            results.append([
                current_set,
                v_diff,
                t_high,
                status_combined
            ])
            runner.add_live_point(current_set, v_diff, 'V(I)')

        # Zero outputs and disable switches
        b1500.zero_output(B1500Session.CH_ALL)
        b1500.set_switch(B1500Session.CH_ALL, False)

        self.log(f'Collected {len(results)} 4-terminal I-V sweep points', runner)
        return results
