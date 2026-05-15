from procedures.base import Choice, MeasurementProcedure, SMU, parameter
from instrumentio.constants import B1500_VOLTAGE_RANGES
from instrumentio.codes import (
    B1500_AUTO_RANGE,
    B1500_CH_ALL,
    B1500_CH_NOCH,
    B1500_IM_MODE,
    B1500_VM_MODE,
    B1500_SWP_IF_SGLLIN,
)
from instrumentio.descriptors import describe_status_bits
from plotting import PlotDef, Curve, LinearFit
from plotting import linear_fit

class VanDerPauwProcedure(MeasurementProcedure):
    NAME = "VanDerPauw"
    PARAMETERS = (
        parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
        parameter('A_channel', 'Terminal A SMU', 4, SMU),
        parameter('B_channel', 'Terminal B SMU', 5, SMU),
        parameter('C_channel', 'Terminal C SMU', 6, SMU),
        parameter('D_channel', 'Terminal D SMU', 7, SMU),
        parameter('start_current', 'Start Current (A)', 0.0, float),
        parameter('stop_current', 'Stop Current (A)', 1e-6, float),
        parameter('points', 'Points', 75, int),
        parameter('voltage_compliance', 'Voltage Compliance (V)', 10.0, float),
        parameter('power_compliance', 'Power Compliance (W)', 0.0, float),
        parameter('measurement_range', 'Voltage Meas Range', 0.0, Choice(B1500_VOLTAGE_RANGES, float)),
        parameter('current_compliance', 'Return Current Compliance (A)', 0.01, float),
        parameter('hold_time', 'Hold Time (s)', 0.0, float),
        parameter('delay_time', 'Delay Time (s)', 0.0, float),
        parameter('second_delay', 'Second Delay (s)', 0.0, float),
    )

    def measure(self, device):
        b1500 = self.b1500
        self.check_stop(b1500)

        self.log(f'Starting 4-Terminal I-V Sweep on {device.name}')

        try:
            # Initialize B1500 session
            b1500.reset()
            b1500.enable_error_detect(True)

            # This procedure currently only reserves the Van der Pauw terminal definitions.
            # The helper below should be called four times once the sweep configurations are wired in.
            # Perform the I-V sweep
            # For Van der Pauw, we will do sweeps in both configurations:
            # 1) Force current A->B, sense voltage C-D
            # 2) Force current B->C, sense voltage D-A
            # 3) Force current C->D, sense voltage A-B
            # 4) Force current D->A, sense voltage B-C

            # Save results
            base = self.format_filename("VanDerPauw", device.name)
            self.save_plot_png(f'{base}_plot.png')
            self.log(f'Van der Pauw measurement completed for {device.name}')

        except Exception as e:
            self.log(f'Error during 4-terminal I-V sweep: {str(e)}')
            raise

    def perform_iv_sweep(self, b1500, device):
        """
        Perform the 4-terminal I-V sweep measurement.
        Forces current through force terminals, holds a return SMU at 0 V, and measures voltage on two sense SMUs.
        Returns list of [Current, VoltageDiff, Time, Status] tuples.
        """
        # This mirrors the four-terminal sweep and assumes a future setup step supplies force/sense channels.
        runner = self.runner
        source_channel = self.force_high_channel
        return_channel = self.force_low_channel
        sense_high = self.sense_high_channel
        sense_low = self.sense_low_channel
        
        self.check_stop(b1500)
        self.prepare_asu_channels(b1500, (source_channel, return_channel, sense_high, sense_low))

        # Enable all four SMUs: two current-force terminals and two zero-current voltage probes.
        b1500.set_switch(source_channel, True)
        b1500.set_switch(return_channel, True)
        b1500.set_switch(sense_high, True)
        b1500.set_switch(sense_low, True)

        self.check_stop(b1500)

        # Reset timestamp
        b1500.reset_timestamp()

        # Hold the return SMU at 0 V with a safe current compliance
        b1500.force_voltage(return_channel, 0.0, self.current_compliance)
        # Sense channels force 0 A so their measured voltages do not intentionally load the sample.
        b1500.force_current(sense_high, 0.0, B1500_AUTO_RANGE)
        b1500.force_current(sense_low, 0.0, B1500_AUTO_RANGE)

        # Generate current sweep vector (inclusive of stop)
        if self.points < 2:
            current_points = [self.start_current]
        else:
            step = (self.stop_current - self.start_current) / (self.points - 1)
            current_points = [self.start_current + i * step for i in range(self.points)]

        self.check_stop(b1500)

        # Program the sweep on the source channel
        b1500.set_iv_sweep(
            source_channel,
            B1500_SWP_IF_SGLLIN,
            B1500_AUTO_RANGE,
            self.start_current,
            self.stop_current,
            self.points,
            hold=self.hold_time,
            delay=self.delay_time,
            second_delay=self.second_delay,
            compliance=self.voltage_compliance,
            power_compliance=self.power_compliance
        )

        # Configure the same interleaved stream shape as four_terminal_iv_sweep.py.
        channels = [source_channel, sense_high, return_channel, sense_low]
        modes = [B1500_IM_MODE, B1500_VM_MODE, B1500_IM_MODE, B1500_VM_MODE]
        ranges = [B1500_AUTO_RANGE, B1500_AUTO_RANGE, B1500_AUTO_RANGE, B1500_AUTO_RANGE]

        self.check_stop(b1500)

        runner.configure_plot(f'4-Terminal I-V - {device.name}', [
            PlotDef("iv", xlabel="Current (A)", ylabels=("Voltage (V)",),
                    elements=[
                        Curve("V_I", mode="scatter", marker="x", color="C0", legend_label="V(I)"),
                        LinearFit("V_I", color="C1",
                                  legend_label_template="R = {slope:.4g} Ω  (R² = {r_squared:.4f})"),
                    ]),
        ])

        # Start streaming for live plot updates and full capture
        # it's called "start_measure", but it does not return until the sweep is complete
        b1500.start_measure(channels, modes, ranges, source_output=1, timestamp=1)

        # We can shut down the source since now the measurement is done
        b1500.zero_output(B1500_CH_ALL)
        b1500.set_switch(B1500_CH_ALL, False)

        data_by_ch = {ch: [] for ch in channels}
        status_by_ch = {ch: [] for ch in channels}
        timestamps = []
        source_values = []
        source_status = []
        plotted = 0
        max_points = len(current_points)
        nonzero_statuses = set()
        while True:
            self.check_stop(b1500)
            _ret, eod, data_type, value, status, channel = b1500.read_data()
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
            if channel in data_by_ch and data_type in (1, 2): # I measure, V measure
                if len(data_by_ch[channel]) < max_points:
                    # Store records per channel; all downstream pairing is by sweep-point index.
                    data_by_ch[channel].append(value)
                    status_by_ch[channel].append(status)
            elif data_type in (3, 4):  # source output data
                if channel not in (source_channel, B1500_CH_NOCH, B1500_CH_ALL):
                    continue
                source_values.append(value)
                source_status.append(status)
            elif data_type == 5:
                timestamps.append(value)

            # Push live plot when we have paired sense readings and source current
            # Van der Pauw resistance uses a differential voltage between the two sense terminals.
            paired = min(len(data_by_ch[sense_high]), len(data_by_ch[sense_low]), len(data_by_ch[source_channel]), max_points)
            while plotted < paired:
                idx = plotted
                v_diff = data_by_ch[sense_high][idx] - data_by_ch[sense_low][idx]
                runner.plot.append_point("V_I", current_points[idx], v_diff)
                plotted += 1

            # Stop if we received all expected points or instrument signaled end
            if eod or plotted >= max_points:
                break

        results = []
        point_count = min(len(current_points), len(data_by_ch[source_channel]), len(data_by_ch[sense_high]), len(data_by_ch[sense_low]))
        for i in range(point_count):
            current_set = data_by_ch[source_channel][i]
            v_high = data_by_ch[sense_high][i]
            v_low = data_by_ch[sense_low][i]
            t_val = timestamps[i] if i < len(timestamps) else 0.0
            # Keep raw high/low voltages in the CSV; combine status bits for quick bad-point filtering.
            status_combined = 0
            if i < len(status_by_ch[sense_high]):
                status_combined |= status_by_ch[sense_high][i]
            if i < len(status_by_ch[sense_low]):
                status_combined |= status_by_ch[sense_low][i]
            if i < len(status_by_ch[source_channel]):
                status_combined |= status_by_ch[source_channel][i]
            if i < len(source_status):
                status_combined |= source_status[i]
            results.append([
                current_set,
                v_high,
                v_low,
                t_val,
                status_combined
            ])

        self.log(f'Collected {len(results)} 4-terminal I-V sweep points')
        return results
