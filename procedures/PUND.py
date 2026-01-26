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
		"""Build PUND waveform: N-P-P-N-N sequence (or inverted P-N-N-P-P)."""
		if self.frequency <= 0:
			raise ValueError("Frequency must be > 0")
		if self.vmax <= 0:
			raise ValueError("Vmax must be > 0")

		# NPPNN = [-1, 1, 1, -1, -1], inverted = PNNPP
		signs = [1, -1, -1, 1, 1] if self.invert_polarity else [-1, 1, 1, -1, -1]

		# Timing as fractions of period T = 1/f
		# Each pulse: 0.4T high, 0.4T low, 0.2T gap; edges 0.1T; total = 5T
		T = 1.0 / self.frequency
		pulse_width = 0.4 * T
		gap = 0.2 * T + self.pulse_delay
		edge = 0.1 * T

		vectors = [(edge, 0.0)]
		for s in signs:
			vectors += [(pulse_width, s * self.vmax), (pulse_width, 0.0), (gap, 0.0)]
		vectors[-1] = (edge, 0.0)  # last gap becomes trailing edge

		# Track active duration (before repetition_delay)
		self._active_duration = sum(dt for dt, _ in vectors)

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
			pattern_duration = sum(dt for dt, _ in vectors)
			active_duration = self._active_duration

			# Compute sample interval and points per WGFMU constraints:
			# - interval >= 10 ns, in 10 ns resolution
			MIN_INTERVAL = 1e-8
			RESOLUTION = 1e-8
			raw_interval = 1e-3 / self.frequency
			sample_interval = max(raw_interval, MIN_INTERVAL)
			sample_interval = round(sample_interval / RESOLUTION) * RESOLUTION
			averaging_time = sample_interval
			active_points = int(active_duration / sample_interval)

			# For repetition_delay: sparse sampling (10 points or fewer)
			DELAY_POINTS = 100
			if self.repetition_delay > 0:
				delay_interval = max(self.repetition_delay / DELAY_POINTS, MIN_INTERVAL)
				delay_interval = round(delay_interval / RESOLUTION) * RESOLUTION
				delay_points = int(self.repetition_delay / delay_interval)
			else:
				delay_points = 0
				delay_interval = sample_interval

			wgfmu.create_pattern(pattern_pg, 0.0)
			for dt, voltage in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_pg, dt, voltage)

			wgfmu.create_pattern(pattern_iv, 0.0)
			for dt, _ in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_iv, dt, 0.0)

			# Measure event for active portion (full rate)
			wgfmu.set_measure_event(
				pattern_pg,
				"meas_active",
				0.0,
				active_points,
				sample_interval,
				averaging_time,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)
			wgfmu.set_measure_event(
				pattern_iv,
				"meas_active",
				0.0,
				active_points,
				sample_interval,
				averaging_time,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)

			# Measure event for repetition_delay portion (sparse)
			if delay_points > 0:
				wgfmu.set_measure_event(
					pattern_pg,
					"meas_delay",
					active_duration,
					delay_points,
					delay_interval,
					delay_interval,
					WGFMU_MEASURE_EVENT_DATA_AVERAGED,
				)
				wgfmu.set_measure_event(
					pattern_iv,
					"meas_delay",
					active_duration,
					delay_points,
					delay_interval,
					delay_interval,
					WGFMU_MEASURE_EVENT_DATA_AVERAGED,
				)

			wgfmu.add_sequence(self.channel_1, pattern_pg, float(self.repetition_count))
			wgfmu.add_sequence(self.channel_2, pattern_iv, float(self.repetition_count))

			# Calculate expected limits for the overlay plot
			v_margin = self.vmax * 0.1
			xlim = (0, pattern_duration)
			ylim = (-self.vmax - v_margin, self.vmax + v_margin)

			# Build styles with color gradient for each rep
			# Blues for voltage, oranges for current
			max_reps_to_plot = min(self.repetition_count, 50)
			step = max(1, self.repetition_count // max_reps_to_plot)
			reps_to_plot = list(range(0, self.repetition_count, step))
			if (self.repetition_count - 1) not in reps_to_plot:
				reps_to_plot.append(self.repetition_count - 1)

			styles = {}
			secondary_labels = []
			for idx, rep in enumerate(reps_to_plot):
				intensity = 0.2 + 0.7 * (idx / max(1, len(reps_to_plot) - 1))
				v_label = f'V (rep {rep+1})' if rep == 0 or rep == self.repetition_count - 1 else f'_V_{rep}'
				i_label = f'I (rep {rep+1})' if rep == 0 or rep == self.repetition_count - 1 else f'_I_{rep}'
				styles[v_label] = {'color': (0, 0, intensity), 'marker': None, 'linestyle': '-', 'linewidth': 0.8}
				styles[i_label] = {'color': (intensity, 0.3 * intensity, 0), 'marker': None, 'linestyle': '-', 'linewidth': 0.8}
				secondary_labels.append(i_label)

			# Initialize live overlay plot
			runner = self.runner
			runner.start_live_plot(
				title=f'PUND Overlay - {device.name}',
				xlabel='Time (s)',
				ylabel='Voltage (V)',
				series_label=None,
				styles=styles,
				secondary_series=secondary_labels,
				secondary_ylabel='Current (μA)',
			)
			runner.set_plot_limits(xlim=xlim, ylim=ylim)

			wgfmu.execute()

			# Poll for data and plot live in overlay mode
			STATUS_COMPLETED = 10000

			data = []
			plotted_count = 0
			# Track which rep we're currently in
			current_rep = 0
			rep_start_time = None

			while True:
				self.check_stop(b1500)

				status, elapsed, total = wgfmu.get_status()

				# Get available measurement data
				measured_1, total_1 = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, total_2 = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2)

				# Fetch new points
				if available > plotted_count:
					# Group points by rep for overlay plotting
					rep_batches = {}  # rep_index -> {'v': [...], 'i': [...]}
					
					for i in range(plotted_count, available):
						t_v, v = wgfmu.get_measure_value(self.channel_1, i)
						t_i, cur = wgfmu.get_measure_value(self.channel_2, i)
						t = t_v if t_v is not None else t_i
						data.append([t, cur, v])

						# Determine which rep this point belongs to
						rep_idx = int(t / pattern_duration) if pattern_duration > 0 else 0
						rep_idx = min(rep_idx, self.repetition_count - 1)

						# Only plot reps in our display list
						if rep_idx in reps_to_plot:
							# Calculate relative time within this rep
							rel_t = t - (rep_idx * pattern_duration)
							
							if rep_idx not in rep_batches:
								rep_batches[rep_idx] = {'v': [], 'i': []}
							rep_batches[rep_idx]['v'].append((rel_t, v))
							rep_batches[rep_idx]['i'].append((rel_t, cur * 1e6))

					# Build batch update for all reps
					batch_update = {}
					for rep_idx, batch_data in rep_batches.items():
						v_label = f'V (rep {rep_idx+1})' if rep_idx == 0 or rep_idx == self.repetition_count - 1 else f'_V_{rep_idx}'
						i_label = f'I (rep {rep_idx+1})' if rep_idx == 0 or rep_idx == self.repetition_count - 1 else f'_I_{rep_idx}'
						batch_update[v_label] = batch_data['v']
						batch_update[i_label] = batch_data['i']

					if batch_update:
						runner.append_plot_points(batch_update)

					plotted_count = available

				if status == STATUS_COMPLETED:
					break

				time.sleep(0.05)

			base = self.format_filename("PUND", device.name)
			filename = f"{base}.csv"
			self.save_data(data, filename, ["Time_s", "Current_A", "Voltage_V"], add_timestamp=False)
			self.log(f"PUND complete: {len(data)} points")

			# Finalize and save overlay plot
			plot_filename = f'{base}_overlay.png'
			runner.finalize_plot(plot_filename, self.output_root, self.output_relative, self.fallback_root)
		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
				wgfmu.close()
			except Exception:
				pass
