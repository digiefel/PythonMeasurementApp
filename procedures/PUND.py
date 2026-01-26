import time
import numpy as np
from procedures.base import MeasurementProcedure
from bindings import (
	WGFMUSession,
	WGFMU_OPERATION_MODE_PG,
	WGFMU_OPERATION_MODE_FASTIV,
	WGFMU_FORCE_VOLTAGE_RANGE_AUTO,
	WGFMU_MEASURE_MODE_VOLTAGE,
	WGFMU_MEASURE_MODE_CURRENT,
	WGFMU_MEASURE_ENABLED_ENABLE,
	WGFMU_MEASURE_EVENT_DATA_AVERAGED,
	WGFMU_MEASURE_VOLTAGE_RANGES,
	WGFMU_MEASURE_CURRENT_RANGES,
)


class PUNDProcedure(MeasurementProcedure):
	def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
		super().__init__(settings, output_root, output_relative, runner, fallback_root)
		self.gpib_address = settings.get('gpib_address', 'GPIB0::17::INSTR')

		self.channel_1 = int(settings.get('channel_1', 1))  # PG Vmeas
		self.channel_2 = int(settings.get('channel_2', 2))  # FastIV Imeas

		self.vmax = float(settings.get('vmax', 1.0))
		self.frequency = float(settings.get('frequency', 1e3))
		self.pulse_delay = float(settings.get('pulse_delay', 0.0))
		self.repetition_count = int(settings.get('repetition_count', 1))
		self.repetition_delay = float(settings.get('repetition_delay', 0.0))
		self.invert_polarity = bool(settings.get('invert_polarity', False))

		self.meas_range_1 = int(settings.get('meas_range_1', WGFMU_MEASURE_VOLTAGE_RANGES[0][0]))
		self.meas_range_2 = int(settings.get('meas_range_2', WGFMU_MEASURE_CURRENT_RANGES[0][0]))

	def _build_pund_vectors(self):
		if self.frequency <= 0:
			raise ValueError("Frequency must be > 0")
		if self.vmax <= 0:
			raise ValueError("Vmax must be > 0")
		if self.repetition_count < 1:
			raise ValueError("Repetition count must be >= 1")
		if self.pulse_delay < 0:
			raise ValueError("Pulse delay must be >= 0")
		if self.repetition_delay < 0:
			raise ValueError("Repetition delay must be >= 0")

		pbias = self.vmax
		nbias = -self.vmax
		if self.invert_polarity:
			pbias, nbias = nbias, pbias

		scale = 1.0e4 / self.frequency
		seq = [
			(1.0e-5, 0.0),
			(4.0e-5, nbias),
			(4.0e-5, 0.0),
			(2.0e-5, 0.0),
			(4.0e-5, pbias),
			(4.0e-5, 0.0),
			(2.0e-5, 0.0),
			(4.0e-5, pbias),
			(4.0e-5, 0.0),
			(2.0e-5, 0.0),
			(4.0e-5, nbias),
			(4.0e-5, 0.0),
			(2.0e-5, 0.0),
			(4.0e-5, nbias),
			(4.0e-5, 0.0),
			(1.0e-5, 0.0),
		]

		vectors = [(dt * scale, v) for dt, v in seq]
		if self.repetition_delay > 0:
			vectors.append((self.repetition_delay, 0.0))
		return vectors

	def run(self, b1500, device):
		self.check_stop(b1500)
		self.log(f"Starting PUND on {device.name}")

		wgfmu = WGFMUSession(self.gpib_address)
		pattern_pg = f"PUND_PG_{self.get_run_timestamp()}"
		pattern_iv = f"PUND_IV_{self.get_run_timestamp()}"

		try:
			wgfmu.clear()

			wgfmu.connect(self.channel_1)
			wgfmu.connect(self.channel_2)

			wgfmu.set_operation_mode(self.channel_1, WGFMU_OPERATION_MODE_PG)
			wgfmu.set_operation_mode(self.channel_2, WGFMU_OPERATION_MODE_FASTIV)

			wgfmu.set_force_voltage_range(self.channel_1, WGFMU_FORCE_VOLTAGE_RANGE_AUTO)
			wgfmu.set_force_voltage_range(self.channel_2, WGFMU_FORCE_VOLTAGE_RANGE_AUTO)

			wgfmu.set_measure_mode(self.channel_1, WGFMU_MEASURE_MODE_VOLTAGE)
			wgfmu.set_measure_mode(self.channel_2, WGFMU_MEASURE_MODE_CURRENT)

			wgfmu.set_measure_voltage_range(self.channel_1, self.meas_range_1)
			wgfmu.set_measure_current_range(self.channel_2, self.meas_range_2)

			wgfmu.set_measure_enabled(self.channel_1, WGFMU_MEASURE_ENABLED_ENABLE)
			wgfmu.set_measure_enabled(self.channel_2, WGFMU_MEASURE_ENABLED_ENABLE)

			vectors = self._build_pund_vectors()
			sample_points = 5000
			sample_interval = 1.0e-3 / self.frequency
			averaging_time = sample_interval

			wgfmu.create_pattern(pattern_pg, 0.0)
			for dt, voltage in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_pg, dt, voltage)

			wgfmu.create_pattern(pattern_iv, 0.0)
			for dt, _ in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_iv, dt, 0.0)

			wgfmu.set_measure_event(
				pattern_pg,
				"meas",
				0.0,
				sample_points,
				sample_interval,
				averaging_time,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)
			wgfmu.set_measure_event(
				pattern_iv,
				"meas",
				0.0,
				sample_points,
				sample_interval,
				averaging_time,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)

			wgfmu.add_sequence(self.channel_1, pattern_pg, float(self.repetition_count))
			wgfmu.add_sequence(self.channel_2, pattern_iv, float(self.repetition_count))

			# Calculate expected limits for the plot
			total_pattern_time = sum(dt for dt, _ in vectors)
			total_time = total_pattern_time * self.repetition_count
			# Voltage is ±vmax, current we estimate but can adjust
			v_margin = self.vmax * 0.1
			xlim = (0, total_time)
			ylim = (-self.vmax - v_margin, self.vmax + v_margin)

			# Initialize live plot before starting execution
			runner = self.runner
			runner.start_live_plot(
				title=f'PUND - {device.name}',
				xlabel='Time (s)',
				ylabel='Voltage (V)',
				series_label='V(t)',
				styles={
					'V(t)': {'color': 'C0', 'marker': None, 'linestyle': '-'},
					'I(t)': {'color': 'C1', 'marker': None, 'linestyle': '-'},
				},
				secondary_series=['I(t)'],
				secondary_ylabel='Current (μA)',
			)
			# Set fixed limits to avoid autoscaling overhead
			# y2lim for current will autoscale on first batch since we don't know the range
			runner.set_plot_limits(xlim=xlim, ylim=ylim)

			wgfmu.execute()

			# Poll for data and plot live
			# Status codes from wgfmu.h:
			# WGFMU_STATUS_COMPLETED = 10000
			STATUS_COMPLETED = 10000

			data = []
			plotted_count = 0
			while True:
				self.check_stop(b1500)

				status, elapsed, total = wgfmu.get_status()

				# Get available measurement data
				measured_1, total_1 = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, total_2 = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2)

				# Fetch and plot new points in batches
				if available > plotted_count:
					batch_v = []
					batch_i = []
					for i in range(plotted_count, available):
						t_v, v = wgfmu.get_measure_value(self.channel_1, i)
						t_i, cur = wgfmu.get_measure_value(self.channel_2, i)
						t = t_v if t_v is not None else t_i
						data.append([t, cur, v])
						batch_v.append((t, v))
						batch_i.append((t, cur * 1e6))  # Convert to μA

					# Single batched update for all new points
					runner.append_plot_points({
						'V(t)': batch_v,
						'I(t)': batch_i,
					})
					plotted_count = available

				# Check if measurement is complete and data is ready
				# STATUS_COMPLETED (10000) means all data is ready to read
				# STATUS_DONE (10001) means just completed but data may not be ready yet
				if status == STATUS_COMPLETED:
					break

				time.sleep(0.05)  # Small delay to avoid hammering the instrument

			base = self.format_filename("PUND", device.name)
			filename = f"{base}.csv"
			self.save_data(data, filename, ["Time_s", "Current_A", "Voltage_V"], add_timestamp=False)
			self.log(f"PUND complete: {len(data)} points")

			# Finalize and save plot
			plot_filename = f'{base}_plot.png'
			runner.finalize_plot(plot_filename, self.output_root, self.output_relative, self.fallback_root)
		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
				wgfmu.close()
			except Exception:
				pass
