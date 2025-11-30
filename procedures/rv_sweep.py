import time

import numpy as np
import pyvisa
from procedures.base import MeasurementProcedure

class RVSweepProcedure(MeasurementProcedure):
    def __init__(self, settings, output_dir, runner):
        super().__init__(settings, output_dir, runner)
        # Default settings for RV sweep
        self.rv_start = settings.get('rv_start', 0.1)
        self.rv_stop = settings.get('rv_stop', 2.0)
        self.rv_step = settings.get('rv_step', 0.1)
        self.pulse_length = settings.get('pulse_length', 100e-6)  # 100 microseconds
        self.read_bias = settings.get('read_bias', 0.3)
        self.set_amplitude = settings.get('set_amplitude', -1.8)
        self.mock_mode = settings.get('mock_mode', True)  # Enable mock mode by default

    def run(self, device):
        runner = self.runner
        self.log(f'Starting RV Sweep on {device.name}')

        try:
            if self.mock_mode:
                self.log('Running in MOCK mode - no hardware connection')
                instr = None
            else:
                # Open instrument connection
                rm = pyvisa.ResourceManager()
                instr = rm.open_resource(runner.config.data['gpib_address'])
                self.log(f'Connected to instrument at {runner.config.data["gpib_address"]}')

            # Build RV vector (similar to C# implementation)
            rv_vector = self.build_rv_vector()
            self.log(f'RV sweep will test {len(rv_vector)} voltage levels')

            # Initialize results storage
            results = []

            # Initialize live plot
            runner.start_live_plot(
                title=f'RV Sweep - {device.name}',
                xlabel='Voltage (V)',
                ylabel='Current (A)',
                series_label='I(V)'
            )

            # Perform measurements for each voltage level
            for i, voltage in enumerate(rv_vector):
                if runner.should_stop():
                    self.log("Stop requested; aborting RV sweep.")
                    break
                self.log(f'Pulse {i+1}/{len(rv_vector)}: {voltage:.3f} V')

                # Perform the measurement
                current = self.perform_measurement(instr, voltage)
                results.append([voltage, current])
                runner.add_live_point(voltage, current, 'I(V)')

                # Small delay between measurements
                time.sleep(0.01)

            # Save results
            base = self.format_filename("RVSweep", device.name)
            self.save_data(results, f'{base}.csv', ['Voltage_V', 'Current_A'], add_timestamp=False)
            plot_path = self.make_output_path(f'{base}_plot.png', add_timestamp=False)
            runner.finalize_plot(plot_path)
            self.log(f'RV sweep completed for {device.name}')

        except Exception as e:
            self.log(f'Error during RV sweep: {str(e)}')
            raise
        finally:
            if not self.mock_mode and 'instr' in locals():
                try:
                    instr.close()
                except:
                    pass

    def build_rv_vector(self):
        """Build the RV (Read/Verify) voltage vector similar to C# implementation."""
        values = [self.set_amplitude]

        span = self.rv_stop - self.rv_start
        if span <= 0:
            raise ValueError("RV stop must be greater than start")

        steps = int(round(span / self.rv_step))

        # Sweep up
        for i in range(1, steps + 1):
            values.append(self.rv_start + i * self.rv_step)

        # Sweep down
        for i in range(1, steps + 1):
            values.append(self.rv_stop - i * self.rv_step)

        # Negative sweep up
        for i in range(1, steps + 1):
            values.append(-self.rv_start - i * self.rv_step)

        # Negative sweep down
        for i in range(1, steps + 1):
            values.append(-self.rv_stop + i * self.rv_step)

        return values

    def perform_measurement(self, instr, voltage):
        """
        Perform a single measurement at the given voltage.
        In mock mode, returns simulated current values.
        """
        if self.mock_mode:
            # Simulate current measurement with some noise
            # For demonstration, use a simple diode-like I-V characteristic
            if voltage > 0:
                current = 1e-6 * (np.exp(voltage / 0.025) - 1) + np.random.normal(0, 1e-9)
            else:
                current = -1e-9 + np.random.normal(0, 1e-10)
            return current
        else:
            try:
                # For now, use simple SCPI commands to set voltage and measure current
                # This is a placeholder - real implementation would use WGFMU patterns

                # Set voltage (simplified - would need proper channel setup)
                instr.write(f'VOLT {voltage}')

                # Wait for settling
                time.sleep(self.pulse_length)

                # Measure current (simplified)
                current_str = instr.query('MEAS:CURR?')
                current = float(current_str.strip())

                return current

            except Exception as e:
                self.log(f'Measurement error at {voltage}V: {str(e)}')
                return 0.0  # Return 0 on error
